# AWS Spot Optimizer V1 - Technical Documentation

> **Last Updated:** 2026-01-05
> **Module Architecture & API Reference (Risk Score Edition)**

---

## Table of Contents

1. [Architecture](#architecture)
2. [Module Reference](#module-reference)
3. [Feature Engineering](#feature-engineering)
4. [Model Architecture](#model-architecture)
5. [Code Architecture](#code-architecture)
6. [Configuration](#configuration)
7. [Change Log](#change-log)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        V1 PIPELINE                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐                                                    │
│  │ Parquet  │────┐                                               │
│  │   Data   │    │    ┌──────────────┐    ┌──────────────────┐  │
│  └──────────┘    ├───►│   Feature    │───►│   Hybrid Model   │  │
│                  │    │  Engineering │    │  (Reg + Clf)     │  │
│  ┌──────────┐    │    └──────────────┘    └────────┬─────────┘  │
│  │ Stress   │────┘           │                     │            │
│  │ Events   │                ▼                     ▼            │
│  │  (CSV)   │        ┌──────────────┐    ┌──────────────────┐  │
│  └──────────┘        │ 39 Features  │    │ Predicted Savings│  │
│                      │ (No Leakage) │    │ + Stability Prob │  │
│                      └──────────────┘    └────────┬─────────┘  │
│                                                   │            │
│                                                   ▼            │
│                                         ┌──────────────────┐   │
│                                         │ Z-Score Risk Zone│   │
│                                         │ Safe/Warn/Danger │   │
│                                         └──────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Module Reference

### `src/data.py`

Data loading and feature engineering.

| Function | Description |
|----------|-------------|
| `load_config(path)` | Load YAML configuration |
| `load_all_data(config)` | Load parquet files with memory optimization |
| `load_stress_events(config)` | Load stress events CSV |
| `chronological_split(df, train, val, test)` | NO-SHUFFLE time-based split |
| `engineer_all_features(df, events, config)` | Complete feature pipeline |
| `get_feature_columns()` | Return list of 39 feature names |
| `prepare_targets(df, horizon)` | Create `future_savings` and `is_unstable` targets |


**Memory Optimization:**
- Optional family-based filtering (configurable filter list)
- Float32 for price columns (50% memory savings)
- Category dtypes for strings
- Garbage collection between loads

---

### `src/model.py`

LightGBM hybrid model (regressor + classifier).

| Method | Description |
|--------|-------------|
| `HybridSpotModel(horizon, device, n_jobs)` | Initialize model for horizon |
| `.fit(X_train, X_val, train_df, val_df)` | Train both regressor and classifier |
| `.predict(X)` | Return `{'savings': array, 'risk_score': array, 'risk_label': array}` |
| `.evaluate(X_test, test_df)` | Return metrics dict |
| `.save(output_dir)` | Save models as .txt files |
| `.load(model_dir, horizon)` | Load trained model |

**Model Configurations:**

```python
# Regressor
{'objective': 'regression', 'metric': 'mape', 'num_leaves': 31}

# Classifier (Risk Score)
{'objective': 'binary', 'metric': 'binary_logloss', 'num_leaves': 31}
```

> **Note:** Classifier uses `binary_logloss` for calibrated probabilities. Output is `risk_score` (0.0 = Safe, 1.0 = High Risk).

---

### `src/backtest.py`

Walk-forward time-series validation.

| Method | Description |
|--------|-------------|
| `WalkForwardBacktest(n_splits, test_size_months, min_train_months)` | Initialize backtester |
| `.create_windows(df)` | Create train/test windows |
| `.run_backtest(df, feature_cols, horizon)` | Run validation |
| `.save_results(path)` | Save JSON results |

**Strategy:**
```
Window 1: [Train Jan-Jun] → [Test Jul-Aug]
Window 2: [Train Jan-Aug] → [Test Sep-Oct]
Window 3: [Train Jan-Oct] → [Test Nov-Dec]
```

---

## Feature Engineering

### All 39 Features

| Category | Count | Features |
|----------|-------|----------|
| **Temporal** | 10 | hour, day_of_week, month, is_weekend, is_business_hours, cyclical encodings |
| **Lag** | 3 | savings_lag_{6,24,144} (1h, 4h, 24h lookback) |
| **Rolling** | 8 | mean/std/min/max over 4h, 24h windows |
| **Price Dynamics** | 5 | velocity_1h, volatility_6h, headroom_to_ondemand, pool_saturation, consecutive_stable_hours |
| **Family-Time** | 6 | Learned patterns per family × hour/day |
| **Family Stress** | 3 | Cross-instance contagion detection |
| **Events** | 3 | Holiday/stress event proximity |
| **Pool Risk** | 1 | pool_historical_zero_rate (% of zeros in pool history) |

### Key Innovations

**Family Stress Index:**
```python
price_position = (price - min_7d) / (max_7d - min_7d)
family_stress_index = mean(price_position across family)
```
Rising c6i.24xlarge prices predict c6i.large failures.

**Family-Time Patterns:**
```python
family_hour_avg_savings = expanding_mean(group['Savings'].shift(1))
```
Model learns batch job patterns (night) vs login peaks (morning) per family.

---

## Model Architecture

### Horizon Design Rationale

**Default: Single 6-Hour Horizon**

The **6-hour horizon (36 steps)** is the "sweet spot" for AWS Spot instances:

| Aspect | Reasoning |
|--------|-----------|
| **Focus vs. Breadth** | Single-horizon models optimize loss solely for that timeframe, improving accuracy |
| **Actionable Window** | Provides enough time to finish batch jobs or migrate before price changes |
| **Lower Uncertainty** | More accurate than 24-hour forecasts where dynamics are harder to predict |
| **Use Case** | Ideal for immediate instance management ("Should I launch this 4-hour job now?") |

> **Trade-off:** You lose the explicit 24-hour forecast. For job scheduling that requires tomorrow's prediction, train a separate dedicated model for that horizon.

### Multi-Horizon Configuration

If you need multiple horizons, update `config.yaml`:

```yaml
# Single horizon (recommended)
features:
  horizons: [36]  # 6h only

# Multiple horizons (if needed)
features:
  horizons: [6, 36, 144]  # 1h, 6h, 24h
```

| Name | Intervals | Time Ahead | Use Case |
|------|-----------|------------|----------|
| 1h | 6 | 1 hour | Emergency decisions |
| **6h** | 36 | 6 hours | **Default - batch jobs** |
| 24h | 144 | 24 hours | Next-day planning |

### Instability Target (Risk Score)

```python
pool_mean = 7-day rolling mean of savings
pool_std = 7-day rolling std of savings
is_unstable = (future_savings < mean - std) | (future_savings > mean + std)
```

> **Note:** Target is `is_unstable` (1 = Risk, 0 = Safe). Higher probability = Higher risk.

### Z-Score Risk Zones

```python
z_score = (predicted_savings - pool_mean) / pool_std

if z_score > -1:    zone = "Safe"
elif z_score > -2:  zone = "Moderate"
elif z_score > -3:  zone = "Warning"
else:               zone = "Danger"
```

---

## Configuration

### `config/config.yaml`

```yaml
data:
  parquet_files:
    - "../Data/aws_mumbai_2023_lgbm.parquet"
    - "../Data/aws_mumbai_2024_lgbm.parquet"
    - "../Data/aws_mumbai_2025_lgbm.parquet"
  stress_events: "../Data/mumbai_stress_events_validated.csv"
  sample_families: []  # Empty = ALL. Use ['c6i', 'm6i'] for local testing.

split:
  train: 0.70
  val: 0.15
  test: 0.15

features:
  horizons: [36]  # Single horizon: 6h (recommended)
  lag_intervals: [6, 24, 144]  # 1h, 4h, 24h
  rolling_windows: [24, 144]  # 4h, 24h
  use_family_stress: true

model:
  device: "cpu"
  n_jobs: 8
  early_stopping_rounds: 100

risk:
  z_score_thresholds:
    safe: -1.0
    moderate: -2.0
    warning: -3.0
```

---

## Optuna Hyperparameter Tuning

### Usage

```bash
# Quick test (1 trial)
python scripts/optimize_hyperparameters.py --dry-run

# Standard optimization (100 trials, ~1.5 hours)
python scripts/optimize_hyperparameters.py

# Resume interrupted run
python scripts/optimize_hyperparameters.py --resume

# Regressor or classifier only
python scripts/optimize_hyperparameters.py --regressor-only
```

### Search Space

| Parameter | Range | Scale |
|-----------|-------|-------|
| `num_leaves` | 20-50 | linear |
| `max_depth` | 6-10 | linear |
| `min_child_samples` | 15-50 | linear |
| `learning_rate` | 0.02-0.08 | log |
| `lambda_l2` | 0.05-0.5 | log |
| `feature_fraction` | 0.7-0.9 | linear |
| `bagging_fraction` | 0.7-0.9 | linear |

### Time Estimates

| Config | Trials | Time | Expected Gain |
|--------|--------|------|---------------|
| Quick | 10 | 15 min | ~5% |
| Standard | 50 | 2 hours | ~10-15% |
| Thorough | 100 | 4 hours | ~15-20% |

### Actual Results (December 2025)

**Regressor (63 trials):**
| Metric | Value |
|--------|-------|
| Best MAPE | **0.33%** |
| num_leaves | 21 |
| max_depth | 9 |
| learning_rate | 0.075 |
| lambda_l2 | 0.319 |

**Classifier (Log Loss Optimization):**
| Metric | Value |
|--------|-------|
| Best Log Loss | **0.42** |
| num_leaves | TBD |
| max_depth | TBD |
| learning_rate | TBD |

> **Note:** Classifier now uses `binary_logloss` for calibrated probabilities (no scale_pos_weight).

### Output

Results saved to `models/hpo_results/optuna_results_YYYYMMDD_HHMMSS.json`

---


### Interpreting Backtest Results (`reports/backtest_6h.json`)

The backtest report validates model performance across different time periods to ensure reliability before production deployment.

**File Structure:**
- **Results List**: Contains 5 "windows" (time periods), each testing the model on unseen future data.
- **Metrics**: Split into `regressor` (savings error) and `classifier` (stability detection).

**Key Metrics Guide:**

| Metric | Good Value | What It Means |
|--------|------------|---------------|
| **MAPE** (Regressor) | `< 0.01` (1%) | Average error in savings prediction. `0.0008` means 0.08% error (extremely accurate). |
| **R²** (Regressor) | `> 0.90` | How well the model explains price variance. `0.99` is near perfect. |
| **Precision** (Classifier)| `> 0.80` | Trustworthiness. If model says "Stable", is it actually stable? |
| **Recall** (Classifier) | `> 0.70` | Coverage. Did we catch all the stable/opportunities available? |

**Historical Performance Analysis (2023-2025):**

| Period | Performance | Interpretation |
|--------|-------------|----------------|
| **2023** (Windows 1-2) | 🟢 Excellent | Stable market conditions. Model achieves >85% F1 score. |
| **Late 2023** (Window 3) | 🟡 Good | Stress test (Diwali/Year-end). Error increases slightly (0.5%) but remains reliable. |
| **2024** (Windows 4-5) | 🟠 Mixed | **Regime Shift**. Market became more volatile. Regressor remains accurate (0.3% error), but Classifier becomes conservative (Recall drops). |

> **Note on 2024 Results**: The drop in classifier recall during 2024 is due to a shift in market stability (from ~70% stable to ~35% stable). The final production model (`model.py`) addresses this by training on the full 2023-2025 dataset, capturing these new patterns that the backtest split missed.

---

## Code Architecture


### File Overview

```
spot_optimizer_v1/
├── config/
│   └── config.yaml          # Training parameters
├── scripts/
│   ├── train.py              # Main training entry point
│   └── backtest.py           # Walk-forward validation script
├── src/
│   ├── data.py               # Data loading + feature engineering
│   ├── model.py              # HybridSpotModel (Regressor + Classifier)
│   ├── backtest.py           # WalkForwardBacktest class
│   └── visualize.py          # Time series-optimized dashboards
└── training_results/
    └── run_YYYYMMDD_HHMMSS/  # Timestamped training outputs
```

### File Descriptions

### File Descriptions

> **Understanding the Structure: `src` vs `scripts`**
>
> This project follows the standard **Library vs. Executable** pattern:
> - **`src/` (Library)**: Contains the *reusable logic*, class definitions, and heavy lifting. These files are designed to be imported, not run directly.
> - **`scripts/` (Executables)**: Contains the *entry points* (runners). These are the files you actually run in the terminal (`python scripts/file.py`). They handle configuration, command-line arguments, and orchestration, calling the logic from `src/`.
>
> **Why are there two `backtest.py` files?**
> - `src/backtest.py`: Defines the **Class** (`WalkForwardBacktest`). It contains the *logic* (how to split data, how to calculate metrics). It doesn't know about your config file or specific file paths.
> - `scripts/backtest.py`: Defines the **Action**. It imports the class from `src`, reads your `config.yaml`, loads your specific data, and tells the backtester to run.

#### `scripts/train.py`
**Purpose:** Main training entry point. Orchestrates the entire training pipeline.

| Function | Description |
|----------|-------------|
| `create_run_folder()` | Creates timestamped output folder |
| `compute_pool_baselines()` | Calculates mean/std per pool for z-score |
| `save_training_summary()` | Saves README.txt with settings |
| `main()` | Main training orchestration |

**Calls:** `data.load_config`, `data.load_all_data`, `data.engineer_all_features`, `data.chronological_split`, `model.HybridSpotModel`, `visualize.ModelVisualizer`

---

#### `src/data.py`
**Purpose:** Data loading, feature engineering, and pool risk analysis.

| Function | Description |
|----------|-------------|
| `load_config(path)` | Load YAML configuration |
| `load_all_data(config)` | Load parquet files with memory optimization |
| `load_stress_events(config)` | Load stress events CSV |
| `chronological_split()` | NO-SHUFFLE time-based split |
| `engineer_all_features()` | Complete 37-feature pipeline |
| `analyze_pool_zero_rates()` | Calculate zero-savings % per pool |
| `filter_critical_pools()` | Remove pools with >20% zeros |
| `add_pool_risk_feature()` | Add pool_historical_zero_rate feature |
| `get_feature_columns()` | Return list of 40 feature names |
| `prepare_targets()` | Create future_savings and is_unstable targets |

**Called by:** `scripts/train.py`, `scripts/backtest.py`, `src/model.py`

---

#### `src/model.py`
**Purpose:** HybridSpotModel - LightGBM regressor + classifier.

| Method | Description |
|--------|-------------|
| `HybridSpotModel(horizon, n_jobs)` | Initialize model |
| `.fit(X_train, X_val, train_df, val_df)` | Train both models |
| `.predict(X)` | Return savings + stability predictions |
| `.evaluate(X_test, test_df)` | Return metrics with confusion matrix |
| `.save(output_dir)` | Save models + feature importance |
| `.load(model_dir, horizon)` | Load trained model |

**Called by:** `scripts/train.py`, `src/backtest.py`
**Calls:** `data.prepare_targets`

---

#### `src/visualize.py`
**Purpose:** Time series-optimized visualization dashboards.

| Method | Description |
|--------|-------------|
| `ModelVisualizer(output_dir)` | Initialize with output path |
| `.generate_essential_dashboards()` | Generate all 3 dashboards |
| `.plot_performance_dashboard()` | 6 plots: confusion, ROC, PR, time series |
| `.plot_feature_analysis_dashboard()` | 3 plots: feature importance comparison |
| `.plot_business_impact_dashboard()` | 4 plots: risk by family, worst pools |

**Called by:** `scripts/train.py`

**Time Series Optimizations:**
- Daily aggregation (77M → 60 points)
- 100K sampling for histograms
- Curve decimation (→200 points)

---

#### `src/backtest.py`
**Purpose:** Walk-forward time-series cross-validation.

| Method | Description |
|--------|-------------|
| `WalkForwardBacktest(n_splits)` | Initialize backtester |
| `.create_windows(df)` | Create train/test windows |
| `.run_backtest()` | Run validation across windows |
| `.save_results(path)` | Save JSON results |

**Called by:** `scripts/backtest.py`
**Calls:** `model.HybridSpotModel`, `data.prepare_targets`

---

### Function Call Graph

```
scripts/train.py
    │
    ├── data.load_config()
    ├── data.load_all_data()
    │     └── data.load_parquet_filtered()
    ├── data.load_stress_events()
    ├── data.engineer_all_features()
    │     ├── data.analyze_pool_zero_rates()
    │     ├── data.filter_critical_pools()
    │     ├── data.add_pool_risk_feature()
    │     ├── data.extract_instance_metadata()
    │     ├── data.create_temporal_features()
    │     ├── data.create_lag_features()
    │     ├── data.create_rolling_features()
    │     ├── data.create_price_dynamics_features()
    │     ├── data.create_family_time_pattern_features()
    │     ├── data.calculate_family_stress_index()
    │     └── data.create_event_features()
    ├── data.chronological_split()
    ├── model.HybridSpotModel()
    │     ├── model.fit()
    │     │     ├── data.prepare_targets()
    │     │     ├── model.train_regressor()
    │     │     └── model.train_classifier()
    │     ├── model.evaluate()
    │     │     └── data.prepare_targets()
    │     └── model.save()
    └── visualize.ModelVisualizer()
          └── visualize.generate_essential_dashboards()
                ├── plot_performance_dashboard()
                ├── plot_feature_analysis_dashboard()
                └── plot_business_impact_dashboard()
```

---

## Change Log

### 2026-01-05 - Risk Score Refactor
- Changed target from `is_stable` to `is_unstable` (1 = Risk, 0 = Safe)
- Changed classifier metric from `auc` to `binary_logloss` for calibrated probabilities
- Added `pool_saturation` and `consecutive_stable_hours` features (now 39 total)
- Model output: `risk_score` (0.0-1.0, higher = more risk)
- Removed `scale_pos_weight` for true probability calibration
- Consolidated HPO scripts into `scripts/optimize_hyperparameters.py`
- Added TimeSeriesSplit CV, LightGBM Pruning, SQLite persistence
- Updated all dependent scripts (backtest.py, visualize.py)
- Rewrote OPTUNA_GUIDE.txt

### 2025-12-24 - Visualization & Documentation
- Added `src/visualize.py` with time series-optimized dashboards
- Added confusion matrix to model evaluation
- Created timestamped training result folders (`training_results/run_XXX/`)
- Added Code Architecture section to docs

### 2025-12-23 - Pool Risk Feature
- Added `pool_historical_zero_rate` feature (37 total features)
- Added pool filtering (removes >20% zero-savings pools)
- Fixed MAPE calculation (filters near-zero values)
- Added regularization to model (lambda_l2, max_depth, min_child_samples)

### 2025-12-22 - Data Leakage Fixes
- Fixed `family_hour_deviation` to use lagged values
- Fixed `prepare_targets` baseline with .shift(1)
- Centralized `prepare_targets` function

### 2025-12-19 - Project Restructuring
- Flattened `src/` directory structure
- Combined loader + feature engineering → `data.py`
- Added family-based filtering for local testing
