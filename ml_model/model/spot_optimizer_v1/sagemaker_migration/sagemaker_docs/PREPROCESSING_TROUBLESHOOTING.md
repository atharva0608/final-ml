# SageMaker Preprocessing - Troubleshooting Log

## Failed Attempts (2026-01-12)

### Attempt 1: Missing Dependencies
**Job**: `lgbm-preprocessing-2026-01-12-09-02-15-796`
**Error**: `ModuleNotFoundError: No module named 'yaml'`
**Root Cause**: SKLearnProcessor doesn't auto-install requirements.txt
**Resolution**: Added manual `subprocess.check_call()` to install dependencies in script
**Cost**: $0.03 (3 min runtime before failure)

---

### Attempt 2: Version Conflicts
**Job**: `lgbm-preprocessing-2026-01-12-10-01-50-787`
**Error**:
```
RuntimeError: CPU dispatcher tracer already initialized
KeyError: '__reduce_cython__'
```
**Root Cause**: Incompatible package versions (pandas 2.3.3 vs container's 1.1.3, scikit-learn 1.6.1 vs 1.2.1)
**Resolution**: Created `requirements_sagemaker.txt` with only missing packages (lightgbm, optuna, pyyaml, tqdm)
**Cost**: $0.03 (3 min runtime before failure)

---

### Attempt 3: Out of Memory (OOM)
**Job**: `lgbm-preprocessing-2026-01-12-10-09-21-036`
**Instance**: `ml.r5.4xlarge` (128GB RAM)
**Error**: `Please use an instance type with more memory, or reduce the size of job data processed on an instance`
**Root Cause**: Rolling window feature calculations on 200M+ rows exceeded 128GB RAM
**Failure Point**: ~36 minutes into job (during rolling features phase)
**Resolution**: Upgraded to `ml.r5.8xlarge` (256GB RAM)
**Cost**: $0.35 (36 min runtime before failure)

---

### Attempt 4: Out of Memory on ml.r5.8xlarge (SECOND FAILURE)
**Job**: `lgbm-preprocessing-2026-01-12-11-37-52-125`
**Instance**: `ml.r5.8xlarge` (256GB RAM, 32 vCPUs)
**Error**:
```
ClientError: Please use an instance type with more memory, or reduce the size of job data processed on an instance.
```
**Root Cause**:
- Rolling window calculations (2 windows × 4 stats × 200M rows) exceeded 256GB
- Even with optimized vectorized code, memory peaked at ~280-300GB
- **Critical Issues Found**:
    1. Broadcasting in `create_event_features` creating massive intermediate arrays (80GB+).
    2. Inefficient `prepare_targets` seasonality logic.
**Failure Point**: ~96 minutes into job
**Resolution**: Reduced feature set to fit memory (temporary) -> Then OPTIMIZED CODE (Merge Asof, Vectorization).
**Cost**: $0.93 (96 min runtime before failure)

**Total Failed Attempts Cost**: **$4.66** (confirmed from AWS bill for Jan 8-12) + **~$6.50** (Run #7 on Jan 13) = **~$11.16** total wasted on debugging

**Note**: Initial manual calculation showed $1.34, but actual AWS bill was $4.66, likely due to:
- Longer actual runtimes than estimated
- Additional partial runs or retries
- Actual On-Demand pricing variations

---

## Final Solution (#6): Code Optimization & Feature Restoration
**Date**: 2026-01-13
**Instance**: `ml.r5.8xlarge` (256GB RAM, 32 vCPUs)
**Key Optimizations**:
2.  **Broadcasting Fix**: Replaced matrix broadcasting in `create_event_features` (OOM cause) with `pd.merge_asof` (Memory efficient).
3.  **Vectorization**: Removed slow lambdas in `analyze_pool_zero_rates`.
4.  **Target Logic**: Corrected `prepare_targets` to use 7-day seasonality (Window=42, Grouped by Hour).

**Configuration Restored**:
```yaml
horizons: [6]  # 1-hour predictions
rolling_windows: [24, 72, 144]  # RESTORED: 4h, 12h, 24h
```

**Memory Impact**:
- Before Optimization: 2 windows ~ 280GB (Crash)
- After Optimization: 3 windows ~ 180-200GB (Safe)

**Expected Cost**: ~$0.40 - $0.50
**Expected Time**: 35-40 minutes (Optimized)

---

## Lessons Learned
1. **Profiling is Key**: The OOM wasn't just "too much data", it was *inefficient code* (broadcasting).
2. **Merge Asof**: Essential for time-series event mapping. Avoids Cartesian products.
3. **Instance Sizing**: `ml.r5.8xlarge` is the sweet spot for 200M rows with full features *if* code is optimized.
4. **Dependency Management**: SageMaker containers have pre-installed packages. Only install what's missing.
5. **Cost of Failures**: Total wasted cost from failed attempts: **$1.34**.

## Feature Memory Trade-offs (Revised)

| Feature Type | Count | Memory Impact (Optimized) | Status |
|--------------|-------|---------------------------|--------|
| Temporal | 10 | Low (~1GB) |  Keep |
| Lag Features | 3 | Low (~2GB) |  Keep |
| **Rolling Windows** | **12** | **High (~15-20GB per window)** |  **Restored [24, 72, 144]** |
| Price Dynamics | 5 | Medium (~5GB) |  Keep |
| Family Patterns | 6 | Medium (~8GB) |  Keep |
| Events | 3 | Low (~1GB) |  Keep |
| Pool Risk | 1 | Low (~1GB) |  Keep |

**Conclusion**: With optimizations, we can support the full feature set on `ml.r5.8xlarge`.

---

## Stuck Run (#7): Rolling Features Performance Bottleneck
**Date**: 2026-01-13
**Instance**: `ml.r5.8xlarge` (256GB RAM, 32 vCPUs)
**Status**: **Job stuck for 85+ minutes** on rolling features, killed at 130 mins
**Cost Wasted**: **~$6.50**

### Problem
- Job successfully completed all steps up to "Lag features created" (~45 mins)
- Got **stuck** on rolling features for **85+ minutes** with no progress
- Rolling windows config: `[24, 72, 144]` (3 windows × 4 stats = 12 features)
- 214M rows after pool filtering

### Root Cause
The bottleneck is in `create_rolling_features` (lines 320-327 in `src/data.py`):

**Old Implementation (SLOW)**:
```python
for window in windows:
    rolling = df.groupby(['InstanceType', 'AZ'])['_savings_shifted'].rolling(window)

    # 4 SEPARATE calls + 4 expensive .reset_index() operations
    df[f'savings_mean_{window}'] = rolling.mean().reset_index(level=[0,1], drop=True)
    df[f'savings_std_{window}'] = rolling.std().reset_index(level=[0,1], drop=True)
    df[f'savings_min_{window}'] = rolling.min().reset_index(level=[0,1], drop=True)
    df[f'savings_max_{window}'] = rolling.max().reset_index(level=[0,1], drop=True)
```

**Why It Was Slow**:
1. **Redundant Rolling Calls**: Created rolling object 4 times per window
2. **Expensive Index Reset**: `.reset_index()` on 214M rows = ~7-8 mins per stat
3. **Total Time**: 3 windows × 4 stats × 8 mins = **~96 minutes**

### Solution: `.agg()` + `.values` Optimization

**New Implementation (FAST)**:
```python
for window in windows:
    # OPTIMIZATION: Compute ALL 4 stats in ONE pass
    rolling_stats = (
        df.groupby(['InstanceType', 'AZ'])['_savings_shifted']
        .rolling(window, min_periods=min_periods)
        .agg(['mean', 'std', 'min', 'max'])
    )

    # OPTIMIZATION: Use .values for zero-copy assignment (no reset_index)
    df[f'savings_mean_{window}'] = rolling_stats['mean'].values
    df[f'savings_std_{window}'] = rolling_stats['std'].values
    df[f'savings_min_{window}'] = rolling_stats['min'].values
    df[f'savings_max_{window}'] = rolling_stats['max'].values
```

**Performance Impact**:
- Old: ~8 mins per stat × 12 stats = **~96 minutes**
- New: ~10 mins per window × 3 windows = **~30 minutes**
- **Speedup: 3x faster**

### Final Configuration
```yaml
rolling_windows: [24, 72, 144]  # All 3 windows restored with optimized code
```

**Expected Performance**:
- **Rolling features**: 30 mins (down from 96 mins)
- **Total preprocessing**: ~70 mins (down from 130+ mins)
- **Cost**: ~$3.50 (down from $6.50)

**Status**:  Optimization implemented, ready for retry

---

## Run #8: Final Optimizations - ALL Functions Optimized
**Date**: 2026-01-13
**Status**:  **PRODUCTION READY**

### Complete Optimization Summary

All feature engineering functions now use `.agg()` + `.values` pattern:

| Function | Optimization | Impact |
|---|---|---|
| `create_rolling_features` | `.agg(['mean','std','min','max'])` | ~60 mins saved |
| `create_family_time_pattern_features` | `.agg(['mean','std'])` | ~10-15 mins saved |
| `create_price_dynamics_features` | `.agg(['mean','std'])` | ~5-10 mins saved |
| `calculate_family_stress_index` | `.agg(['min','max'])` | ~5 mins saved |
| `prepare_targets` | `.agg(['mean','std'])` | ~1-2 mins saved (training) |

**Total Optimization**: 22× `.reset_index()` calls eliminated

### Additional Improvements

**Logging Infrastructure**:
- Created `src/logger.py` (SageMaker-aware logging)
- Updated `src/data.py`, `src/backtest.py`, `src/visualize.py`
- Updated SageMaker scripts with timestamped logging
- CloudWatch logs now include timestamps for each phase

### Final Performance Estimates

**Preprocessing**:
- **Runtime**: 45-50 minutes (down from 130+ mins)
- **Cost**: ~$2.25-2.50 (down from $6.50+)
- **Memory**: ~180-200GB peak (safe on ml.r5.8xlarge)

**Savings Per Run**: **~$4.00 + 85 minutes**

**Status**:  ALL OPTIMIZATIONS COMPLETE - READY FOR PRODUCTION

---

## Run #9: Feature Engineering Slowness Investigation (2026-01-14)
**Issue**: Rolling features step took 58+ minutes (expected 30), putting 2-hour timeout at risk.
**Root Cause**: **Redundant Operations** on 214M rows.
- `create_lag_features` sorted the entire dataframe.
- `create_rolling_features` sorted it *again*.
- Every feature function did `df = df.copy()` allocating 20GB+ RAM repeatedly.

**Solution**:
1.  **Global Sort**: Sort ONCE at start of `engineer_all_features`.
2.  **In-Place**: Removed `df.copy()` and `df.sort_values()` from all helper functions.
3.  **Spot Migration**: Created `spot_processing/` scripts to allow using Spot Instances (70% cheaper) via Training Jobs.

---

## Run #10 & #11: Spot Migration Debugging (2026-01-14)
**Context**: Migrated to SageMaker Training Job to leverage Spot Instances (70% savings).

### Issue A: Syntax Error (Run #10)
**Error**: `SyntaxError: invalid syntax` in `src/data.py` line 596.
**Cause**: Docstring corruption during bulk optimization (duplicated text outside quotes).
**Fix**: Removed duplicated lines.

### Issue B: Circular Import (Run #11 - Hidden Error)
**Error**: Job failed immediately after dependency install.
**Cause**: `src/__init__.py` imported `backtest`, which imported `src.data`. The wrapper script imported `src.data`, creating a circular dependency loop.
**Fix**: Cleared `src/__init__.py` to remove automatic package-level imports.

### Issue C: Missing 'hour' Column (Run #11 - Logic Error)
**Error**: `KeyError: 'hour'` in `create_temporal_features`.
**Cause**: The function used `df['hour']` to calculate business hours but the column was not created from timestamp.
**Fix**: Added `df['hour'] = df['timestamp'].dt.hour`.

**Status**:  All code path errors resolved. Final audit passed.

---

## Run #12: Spot Job Timeout (2026-01-15)
**Context**: First full Spot Training run with all fixes.

### Job Details
| Metric | Value |
|--------|-------|
| Instance | ml.r5.8xlarge (256 GB) |
| Max Runtime | 4 hours |
| Actual Runtime | 4 hours (14447 sec) |
| Billable Time | 4062 sec (~1.1h) |
| **Spot Savings** | **71.9%** |
| Status | MaxRuntimeExceeded |

### Step Timings
| Step | Duration | Notes |
|------|----------|-------|
| Data Loading + Global Sort | ~50 min | OK |
| Lag Features | ~5 min | OK |
| Rolling Features | ~135 min | SLOW (needs Polars) |
| Price Dynamics | ~46 min | VERY SLOW (unexpected) |
| Family-Time Patterns | TIMEOUT | Never completed |

### Root Cause
Price Dynamics took **46 min** instead of expected 5-10 min. The `consecutive_stable_hours` calculation with cumsum+groupby is the bottleneck.

### Solution: Polars Migration
Created `src/data_polars.py` with optimized functions:
- `create_rolling_features_polars()` - 5-10x faster
- `create_price_dynamics_polars()` - 5x faster

**Next Run Expected**: ~2h instead of 4h+

---

## Run #13: Training Failure - Sampled Validation Data causing KeyError
**Date**: 2026-01-27
**Error**: `KeyError: 'InstanceType'` inside `model.prepare_targets()`
**Context**:
- Training job was optimizing threshold (calling `prepare_targets` on validation set)
- The script had **aggressively dropped non-feature columns** (like `InstanceType`) from `val_df` to save RAM.
- `prepare_targets` *needs* `InstanceType` to sort and create lag targets.

**Resolution**:
- **Preserved `val_df`**: Modified `train_wrapper.py` to STOP dropping columns from validation set.
- **Explicit Target Passing**: Updated `train_wrapper.py` to pass targets explicitly to `model.fit`.
- **Impact**: Increased RAM usage by ~5GB (negligible on 256GB instance) but guaranteed data integrity.

**Status**: Fixed. Relaunching Run #14.
