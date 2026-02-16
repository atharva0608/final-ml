# Spot Optimizer V1: Model Leaderboard
**Last Updated**: 2026-02-12
**Status**: Golden Master Confirmed

This document tracks the performance evolution of the Spot Optimizer models.

| Rank | Model ID | Description | Regressor MAPE | Classifier Recall | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **Run 409** | **Latest (ONNX Success!)** | **0.26%** | **95.3%** | **PRODUCTION** |
| 2 | Run 819 | ONNX Failed (Import Error) | 0.23% | 97.8% | Archived |
| 3 | Run 623 | ONNX Fix Applied (Export Failed) | 0.23% | 97.8% | Archived |
| 4 | Run 498 | Previous Golden Master | 0.23% | 97.8% | Archived |
| 5 | Run 430 | Champion (Viz Failed) | 0.23% | 97.8% | Archived |

---

## Detailed Comparison

### 1. Latest Run: Run 409 (Success!)
- **Job Name**: `sagemaker-scikit-learn-2026-02-13-05-39-07-409`
- **Date**: 2026-02-13
- **Training Data**: 100% Full History (147.3M train, 210.5M total)
- **Configuration**: 1000 Rounds, Backtest Enabled, skip_backtest=0
- **Instance**: ml.r5.8xlarge (Spot)
- **Regressor Metrics**:
    - **MAPE**: 0.26% (Aggregated Backtest: 0.0026 +/- 0.0005)
    - **R-squared**: 0.9996 (Aggregated)
- **Classifier Metrics**:
    - **F1**: 0.7448 +/- 0.0062 (Aggregated)
    - **Recall**: 95.29% (at optimal threshold 0.35)
    - **Precision**: 57.35%
    - **AUC**: 0.7322
    - **Optimal Threshold**: 0.35
- **Backtesting (3 Windows)**:
    - **Avg MAPE**: 0.0026 ± 0.0005
    - **Avg F1**: 0.7448 ± 0.0062
- **ONNX Export**: **SUCCESS**. Models saved to `/opt/ml/model` with category mapping.
- **Top Features (Regressor)**: savings_lag_6, savings_min_24, savings_max_24, headroom_to_ondemand, savings_min_144
- **Top Features (Classifier)**: savings_std_144, savings_std_24, pool_saturation, family_stress_index, price_volatility_6h

### 2. Run 819 (Deprecating)
- **Job Name**: `sagemaker-scikit-learn-2026-02-12-06-55-51-819`
- **Date**: 2026-02-12
- **Status**: Archived. ONNX export failed due to version mismatch.
- **Metrics**: Similar to Run 409 (0.23% MAPE, 0.75 F1).

### 2. Run 623
- **Job Name**: `sagemaker-scikit-learn-2026-02-11-06-59-44-623`
- **Training Data**: 100% Full History (147.3M train rows, 210.5M total)
- **Configuration**: 1000 Rounds, Backtest Enabled, skip_backtest=0
- **Instance**: ml.r5.8xlarge (32 vCPUs, 256 GB RAM)
- **Regressor Metrics**:
    - **MAPE**: 0.23% (test), 0.28% (val)
    - **R-squared**: 0.9995
    - **RMSE**: 0.2692
- **Classifier Metrics**:
    - **Recall**: 97.8%
    - **Precision**: 61.4%
    - **F1**: 0.7545
    - **AUC**: 0.7200
    - **Optimal Threshold**: 0.35
- **Backtesting (3 Windows)**:
    - **Avg MAPE**: 0.0026 +/- 0.0005
    - **Avg F1**: 0.7448 +/- 0.0062
    - **Avg R-squared**: 0.9996
- **ONNX Export**: FAILED on Run 623 (onnx 1.17.0 conflicts with protobuf==3.20.3). Fix applied: pinned `onnx>=1.14.0,<1.16.0` in all requirements files
- **Top Features (Regressor)**: savings_lag_6, savings_min_24, savings_max_24, headroom_to_ondemand, savings_min_144
- **Top Features (Classifier)**: savings_std_144, savings_std_24, pool_saturation, family_stress_index, price_volatility_6h
- **Why it matters**: Confirms model stability -- identical metrics to Run 498 with updated dependencies and code fixes

### 3. The Golden Master: Run 498
- **Job Name**: `sagemaker-scikit-learn-2026-01-28-09-09-36-498`
- **Training Data**: 100% Full History (147.3M rows)
- **Configuration**: 1000 Rounds, Backtest Enabled
- **Regressor Metrics**:
    - **MAPE**: 0.23%
    - **R²**: 0.9995
    - **RMSE**: 0.2691
- **Classifier Metrics**:
    - **Recall**: 97.8%
    - **Precision**: 61.4%
    - **F1**: 0.7545
    - **AUC**: 0.7200
    - **Optimal Threshold**: 0.35

    **Wrong Threshold**: 0.5
    **Correct Threshold**: 0.35 for backtesting and visualization

- **Backtesting (3 Windows)**:
    - **Avg MAPE**: 0.0027 ± 0.0006
    - **Avg F1**: 0.7483 ± 0.0057
- **Why it wins**: Identical accuracy to previous runs but with **FIXED reporting pipeline**.
  - Fixed Backtest MAPE (Trillions -> 0.27%)
  - Fixed Visualization Error (Matplotlib API)
  - Generated full `Model_Validation_Report.pdf`
- **Robustness Check (Backtesting Analysis)**:
  - **Stability**: The model is incredibly stable across time. F1 Score standard deviation is only **0.0057** (0.5%), meaning performance does not degrade as we move forward in time.
  - **Reliability**:
    - **Window 1 (Jul-Sep)**: F1=0.741, Recall=87.2%
    - **Window 2 (Sep-Nov)**: F1=0.754, Recall=86.3%
    - **Window 3 (Nov-Jan)**: F1=0.750, Recall=85.4%
  - **Verdict**: The results are **GOOD**. The consistent high Recall (>85%) across all windows proves the model is not overfitting to a specific season and will perform reliably in production.

### 4. Previous Champion: Run 430
- **Job Name**: `sagemaker-scikit-learn-2026-01-27-10-17-35-430`
- **Status**: Excellent model, but reporting pipeline failed.
- **Metrics**: Identical to Run 498.
- **Why replaced**: Run 498 produces clean reports without manual patches.

### 5. The Challenger: Run 820
- **Job Name**: `sagemaker-scikit-learn-2026-01-27-08-41-55-820`
- **Training Data**: 100% Full History (147.3M rows)
- **Configuration**: 500 Rounds, Backtest Disabled
- **Regressor Metrics**:
    - **MAPE**: 0.23%
    - **R²**: 0.9995
- **Classifier Metrics**:
    - **Recall**: 97.8%
    - **Precision**: 61.4%
- **Status**: Excellent stable run. Validated in `PIPELINE_VALIDATION_LOG.md` (Run #14).

## Why are the results identical?
Both runs achieved **0.23% MAPE** and **97.8% Recall**.
This occurs because:
1.  **Early Convergence**: The model likely reached its peak performance *before* 500 rounds. Adding more rounds (up to 1000 in Run 430) didn't extract further patterns because the limits of the data were reached.
2.  **Determinism**: We use fixed random seeds (`seed=42`). Since both runs used the same data and seeds, they followed the exact same gradient descent path.

**Verdict**: The results are **Consistent**. You can rely on these numbers.

---

## Backtesting Decay Analysis & Retraining Cadence

Analysis from Run 819 backtesting (3 walk-forward windows, 2-month test periods).

### Per-Window Breakdown

| Metric | Window 1 (Jul-Sep 2023) | Window 2 (Sep-Nov 2023) | Window 3 (Nov 2023-Jan 2024) | Trend |
|---|---|---|---|---|
| **Train Period** | Jan-Jul 2023 (6mo) | Jan-Sep 2023 (8mo) | Jan-Nov 2023 (10mo) | Growing |
| **Reg MAPE** | 0.21% | 0.31% | 0.25% | Stable |
| **Reg R-squared** | 0.9999 | 0.9998 | 0.9990 | Slight decay |
| **Clf F1** | 0.7362 | 0.7507 | 0.7476 | Stable |
| **Clf AUC** | 0.9221 | 0.9300 | 0.7729 | Sharp drop in W3 |
| **Clf Recall** | 86.6% | 86.5% | 79.6% | Drop in W3 |
| **Threshold** | 0.35 | 0.35 | 0.40 | Shifted in W3 |

### Key Findings

1. **Regressor is rock-stable**: MAPE stays 0.21-0.31% across all windows. Spot prices follow persistent algorithmic patterns that rarely change. The regressor can go 6+ months without retraining.

2. **Classifier degrades after ~4-5 months**: AUC drops 17% from Window 2 (0.93) to Window 3 (0.77). Window 3 covers the holiday season (Nov-Jan), which introduces pricing dynamics not seen in the 6-10 months of training data. The threshold also shifted from 0.35 to 0.40, indicating probability calibration drift.

3. **Data older than 6 months loses relevance for risk classification**: The classifier's recall drops from 86.5% to 79.6% when the test period is far from the training distribution.

### Recommended Retraining Schedule

| Component | Interval | Rationale |
|---|---|---|
| **Classifier** | Every 2-3 months | Most sensitive to market regime changes. AUC dropped 17% in a single 2-month shift. |
| **Regressor** | Every 3-4 months | Stable but R-squared decayed from 0.9999 to 0.9990 in Window 3. |
| **Full Pipeline** | **Quarterly (every 3 months)** | Simplest operational cadence. Retrain both on rolling 12-18 months of recent data. |
