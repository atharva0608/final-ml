#  Pipeline Logic Guide - LightGBM Spot Optimizer V1

**Date**: January 14, 2026
**Version**: Optimized V1 (Production Ready)

##  High-Level Data Flow

1.  **Ingestion**: Load raw Spot Price history (Parquet) -> Filter by Family (e.g., c6i, m6i).
2.  **Cleaning**: Targeted `dropna()` on specific columns.
3.  **Feature Engineering**: 7 specialized steps (fully vectorized).
4.  **Target Creation**: Future Savings (Regression) + Instability Risk (Classification).
5.  **Output**: `preprocessed_features.parquet` ready for SageMaker Training.

---

## ️ Detailed Logic Steps

### 1. Data Loading (`load_all_data`)
*   **Input**: Raw AWS Parquet files (Month/Year partitions).
*   **Logic**:
    *   Loads data filtering by `sample_families` (e.g., "c6i", "m6i").
    *   **Optimization**: Filters *during* load to save RAM.
    *   **Output**: Sorted DataFrame `[InstanceType, AZ, timestamp]`.

### 2. Feature Engineering Pipeline

#### A. Temporal Features (Time Awareness)
*   **Logic**: Extracts Hour, Day, Month.
*   **Cyclical Encoding**: `hour_sin`, `hour_cos` (So 23:00 is close to 00:00).
*   **Business Logic**: Flags `is_weekend`, `is_business_hours`.

#### B. Lag Features (Recent History)
*   **Logic**: What was the savings 1 hour ago? 4 hours ago?
*   **Technique**: `.shift(interval)` (No leakage).

#### C. Rolling Features (Trends)
*   **Windows**: 4h (24), 12h (72), 24h (144).
*   **Stats**: Mean, Std, Min, Max.
*   **Optimization**: uses `.agg()` + `.values` (3x faster).

#### D. Price Dynamics (Velocity & Saturation)
*   **Velocity**: % change in price over last hour.
*   **Volatility**: 6h rolling standard deviation.
*   **Pool Saturation**: How close is current price to the recent floor?
    *   Formula: `(Price - Min) / (Ondemand - Min)`
    *   **Optimization**: Uses 1-day min (144) instead of 7-day min.

#### E. Family-Time Patterns (Seasonality)
*   **Goal**: Learn that "c6i instances spike at 9 AM" without hardcoding.
*   **Logic**: Calculate historical average for (Family, Hour).
*   **Optimization**:
    *   Daily Pattern lookback: 7 days.
    *   Weekly Pattern lookback: 4 weeks.
    *   (Corrected from 19-year bug).

#### F. Family Stress Index (Contagion)
*   **Goal**: Detect if a whole family (e.g., c6i) is under stress.
*   **Logic**:
    1. Calculate "Price Position" (0-1) for every instance.
    2. Aggregate Mean Position for the whole family/AZ.
    3. If `c6i.24xlarge` price spikes, `c6i.large` gets a high Stress Score.
*   **Optimization**: Uses `pd.merge()` instead of `join` (100x faster).

#### G. Event Features (External Factors)
*   **Input**: `stress_events.csv` (Prime Day, Black Friday).
*   **Logic**: Maps event flags to timestamps.
*   **Optimization**: `pd.merge_asof` (No OOM broadcasting).

### 3. Target Creation (`prepare_targets`)

#### A. Regression Target: `future_savings`
*   **Definition**: Actual savings percentage `horizon` steps into the future.
*   **Use**: "How much will I save?"

#### B. Classification Target: `is_unstable`
*   **Definition**: Risk of price spike.
*   **Logic**:
    1. Calculate Baseline: Moving average of savings (7-day window by hour).
    2. Threshold: If future savings drops > 1 StdDev below baseline -> **UNSTABLE (1)**.
    3. Else -> **STABLE (0)**.
*   **Why**: Adapts to market changes. A 50% savings might be "bad" if the baseline is 80%.

---

##  Performance Profile

| Step | Complexity | Optimization Applied |
| :--- | :--- | :--- |
| **Rolling Features** | O(N * W) | Vectorized `.agg()` |
| **Family Stress** | O(N log N) | `merge()` (vs join) |
| **Patterns** | O(N) | Corrected Window Sizes |
| **Dropna** | O(N) | In-place Subset |

**Total Runtime**: ~45 Minutes (was 130+)
**Memory**: ~180GB Peak (fits in ml.r5.8xlarge)
