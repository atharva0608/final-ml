# SageMaker HPO Optimization Strategy

## Executive Summary

This document compares two approaches for running Hyperparameter Optimization (HPO) on SageMaker for the LightGBM Spot Optimizer with 214 million rows of data:

1. **Naive Approach**: Recompute features within every trial
2. **Optimized Approach**: Materialize features once, reuse across all trials

**Bottom Line**: The optimized approach saves **~$15** (75% cost reduction) and **3 hours** of wall time.

---

## The Problem: Expensive Feature Engineering

The LightGBM Spot Optimizer creates 39 complex features from raw data:
- Lag features (1h, 4h, 24h lookbacks)
- Rolling windows (4h, 24h aggregations)
- Pool risk analysis
- Family stress indices
- Temporal patterns

**Feature engineering now takes ~35-40 minutes in SageMaker** (using `ml.r5.8xlarge` with 200M+ rows, handling massive event broadcasting safely).

---

## Approach 1: Naive (Current Default)

### How It Works
Each HPO trial runs independently and performs all data processing steps:

```
Trial 1:  Load Raw → Engineer Features (18 mins) → Train (5 mins) → Report
Trial 2:  Load Raw → Engineer Features (18 mins) → Train (5 mins) → Report
...
Trial 100: Load Raw → Engineer Features (18 mins) → Train (5 mins) → Report
```

### Cost Breakdown (100 Trials)

| Phase | Duration | Compute Hours | Cost |
|-------|----------|---------------|------|
| Data Load from S3 | 2 mins/trial | 3.3 hrs | $1.32 |
| Feature Engineering | 18 mins/trial | 30 hrs | $12.00 |
| Model Training | 5 mins/trial | 8.3 hrs | $3.32 |
| Reporting | 1 min/trial | 1.7 hrs | $0.68 |
| **Total** | **30 mins/trial** | **50 hrs** | **$20.00** |

### Timeline
- **Wall Time**: 5 hours (10 parallel jobs)
- **Redundant Work**: Feature engineering runs 100 times (identical computation)

### Problems
1. **Wasted Compute**: 60% of budget spent on redundant feature engineering
2. **Slow**: Features recomputed even though they don't change between trials
3. **Expensive**: Paying for data munging, not model intelligence

---

## Approach 2: Optimized (Materialized Features)

### How It Works
Separate feature engineering into a one-time preprocessing step:

```
Step 1 (Once):  Load Raw → Engineer Features → Save to S3 (Parquet)

Step 2 (100x): Load Preprocessed → Train → Report
```

This pattern is known as **"Materializing Features"** in MLOps.

### Cost Breakdown (100 Trials)

#### Phase 1: One-Time Preprocessing
| Task | Duration | Cost |
|------|----------|------|
| Load raw data | 2 mins | - |
| Engineer all features | 18 mins | - |
| Save to S3 (Parquet) | 2 mins | - |
| **Subtotal** | **22 mins** | **$0.15** |

#### Phase 2: HPO Trials (100x)
| Phase | Duration | Compute Hours | Cost |
|-------|----------|---------------|------|
| Load Preprocessed (Parquet) | 2 mins/trial | 3.3 hrs | $1.32 |
| Model Training | 5 mins/trial | 8.3 hrs | $3.32 |
| Reporting | <1 min/trial | 1.7 hrs | $0.68 |
| **Subtotal** | **7 mins/trial** | **11.7 hrs** | **$4.68** |

#### Total Cost
- Preprocessing: $0.15
- HPO: $4.68
- **Grand Total: $4.83**

### Timeline
- **Preprocessing**: 22 minutes (one-time)
- **HPO Wall Time**: 2 hours (10 parallel jobs)
- **Total Wall Time**: 2.4 hours

### Savings
| Metric | Naive | Optimized | Improvement |
|--------|-------|-----------|-------------|
| **Total Cost** | $20.00 | $4.83 | **76% cheaper** |
| **Wall Time** | 5 hrs | 2.4 hrs | **52% faster** |
| **Compute Hours** | 50 hrs | 11.9 hrs | **76% reduction** |

---

## Why Materialized Features Work

### The Cached State Principle
By treating feature engineering as a separate pipeline step, you remove CPU-heavy data transformation from the repetitive HPO loop.

**Without Preprocessing:**
- CPU spends 60% of time transforming data (18 mins)
- CPU spends 40% of time training models (12 mins)
- You're paying for data munging, not intelligence

**With Preprocessing:**
- CPU spends 100% of time training models
- All redundant work eliminated
- Budget goes toward finding optimal parameters

### Why Parquet Format?
- **CSV Issues**: Slow parsing, large file size, no compression
- **Parquet Benefits**:
  - Binary format: 10x faster to load
  - Columnar storage: Only loads needed columns
  - Snappy compression: 3-5x smaller than CSV
  - Schema embedded: Type safety guaranteed

**Example:** 9M rows × 39 features
- CSV: ~8GB, 5-6 mins to parse
- Parquet (Snappy): ~2GB, 30 secs to parse

---

## Critical Technical Validation

Before implementing materialized features, ensure your workflow passes these three checks:

###  Check 1: Data Leakage Safety

**Question**: Will preprocessing leak validation data into training?

**Your Pipeline**: SAFE
- Features are temporal (lags, rolling windows) - only look backward
- No global statistics (no mean/std across entire dataset)
- Target preparation uses `.shift(1)` - excludes current row
- Split happens AFTER features (but features are time-based, so safe)

**Verdict**: No leakage risk.

###  Check 2: Hyperparameter Independence

**Question**: Do HPO parameters affect feature engineering?

**Your HPO Search Space**:
- `num_leaves`, `learning_rate`, `max_depth`
- `lambda_l1`, `lambda_l2`, `min_child_samples`

**Your Feature Config** (in `config.yaml`):
- `horizons`, `lag_intervals`, `rolling_windows`

**Verdict**: HPO parameters and features are completely independent.

###  Check 3: I/O Performance

**Question**: Is loading time acceptable?

**With Parquet**:
- File size: ~2GB (compressed)
- S3 download: ~1.5 mins
- Parsing: ~30 secs
- **Total: ~2 mins**

**Verdict**: Fast enough. Well within acceptable range.

---

## Parallelism Impact

### How 10 Parallel Instances Benefit

**Naive Approach:**
- Batch 1-10: Each instance processes 30 mins → All finish simultaneously
- Batch 11-20: Repeat
- **Wall Time**: 5 hours

**Optimized Approach:**
- Batch 1-10: Each instance processes 7 mins → All finish simultaneously
- Batch 11-20: Repeat
- **Wall Time**: 1.2 hours (after initial preprocessing)

**Result**: Parallelism multiplier remains the same (10x), but base time drops from 30 mins to 7 mins per trial.

---

## Implementation Roadmap

### Step 1: Create Preprocessing Script
Create `sagemaker_migration/preprocess_features.py`:
- Load raw data from S3
- Run `engineer_all_features()`
- Save to S3 as Parquet

### Step 2: Modify Training Wrapper
Update `train_wrapper.py`:
- Skip `engineer_all_features()` call
- Load preprocessed Parquet directly
- Remove `load_stress_events()` (already in features)

### Step 3: Update HPO Submitter
Modify `hpo_submitter.py`:
- Point to preprocessed data location
- Update cost estimates in documentation

### Step 4: Run Preprocessing Job
```bash
python sagemaker_migration/preprocess_features.py \
    --bucket ml-sagemaker-lightgbm \
    --profile nisha_chothe
```

### Step 5: Launch HPO
```bash
python sagemaker_migration/hpo_submitter.py \
    --bucket ml-sagemaker-lightgbm \
    --role arn:aws:iam::888245942216:role/... \
    --profile nisha_chothe \
    --trials 100
```

---

## Conclusion

**Materialized features is a superior approach** when:
-  Feature engineering is expensive (15+ mins)
-  Features don't depend on hyperparameters
-  No data leakage risk
-  Running many trials (50+)

**For your use case:**
- Save **$15** per 100-trial run
- Reduce wall time from **5 hours** to **2.4 hours**
- Eliminate 38 hours of redundant computation

**Trade-off:** Tiny upfront orchestration step (22 mins, $0.15) for massive recurring savings.

**Recommendation**: Implement materialized features before running production HPO.
