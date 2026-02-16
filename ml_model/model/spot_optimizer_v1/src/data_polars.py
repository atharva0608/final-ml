"""
Polars-optimized feature engineering functions.

These functions provide 5-10x speedup over pandas for rolling window operations
by leveraging Polars' native Rust implementation.
"""
from typing import List, Optional, Tuple, Union

import pandas as pd
import polars as pl
from src.logger import setup_sagemaker_logger

logger = setup_sagemaker_logger(__name__)


def create_rolling_features_polars(df: Union[pd.DataFrame, pl.DataFrame], windows: List[int]) -> pl.DataFrame:
    """
    Create rolling statistics using Polars (5-10x faster than pandas).

    # REF: OPTIMIZATION - Accepts Union, returns Polars directly.
    """
    logger.info("Creating Rolling Features (Polars Optimized)...")

    # Convert to Polars only if needed
    if isinstance(df, pd.DataFrame):
        df_pl = pl.from_pandas(df)
    else:
        df_pl = df

    # Create shifted savings column once
    df_pl = df_pl.with_columns(pl.col("Savings").shift(1).over(["InstanceType", "AZ"]).alias("_savings_shifted"))

    for window in windows:
        min_periods = max(1, window // 10)
        logger.info(f"  Processing window={window}...")

        # Compute all 4 rolling stats in one pass
        df_pl = df_pl.with_columns(
            [
                pl.col("_savings_shifted")
                .rolling_mean(window_size=window, min_periods=min_periods)
                .over(["InstanceType", "AZ"])
                .alias(f"savings_mean_{window}"),
                pl.col("_savings_shifted")
                .rolling_std(window_size=window, min_periods=min_periods)
                .over(["InstanceType", "AZ"])
                .alias(f"savings_std_{window}"),
                pl.col("_savings_shifted")
                .rolling_min(window_size=window, min_periods=min_periods)
                .over(["InstanceType", "AZ"])
                .alias(f"savings_min_{window}"),
                pl.col("_savings_shifted")
                .rolling_max(window_size=window, min_periods=min_periods)
                .over(["InstanceType", "AZ"])
                .alias(f"savings_max_{window}"),
            ]
        )

    # Drop temp column
    df_pl = df_pl.drop("_savings_shifted")

    logger.info("Rolling Features (Polars) created successfully.")
    return df_pl  # REF: OPTIMIZATION - Return Polars


def create_price_dynamics_polars(
    df: Union[pd.DataFrame, pl.DataFrame], median_price: Optional[float] = None
) -> pl.DataFrame:
    """
    Create price dynamics features using Polars (optimized version).

    # REF: OPTIMIZATION - Accepts median_price to avoid redundant calc.
    """
    logger.info("Creating Price Dynamics (Polars Optimized)...")

    if isinstance(df, pd.DataFrame):
        df_pl = pl.from_pandas(df)
    else:
        df_pl = df

    # Price velocity
    df_pl = df_pl.with_columns(
        pl.col("SpotPrice").pct_change(n=6).over(["InstanceType", "AZ"]).alias("price_velocity_1h")
    )

    # Price volatility
    df_pl = df_pl.with_columns(pl.col("SpotPrice").shift(1).over(["InstanceType", "AZ"]).alias("_price_shifted"))
    df_pl = df_pl.with_columns(
        pl.col("_price_shifted")
        .rolling_std(window_size=36, min_periods=6)
        .over(["InstanceType", "AZ"])
        .alias("price_volatility_6h")
    )

    # Headroom to on-demand
    df_pl = df_pl.with_columns(
        ((pl.col("OndemandPrice") - pl.col("SpotPrice")) / pl.col("OndemandPrice")).alias("headroom_to_ondemand")
    )

    # Pool saturation (simplified for Polars)
    window_1d = 144
    df_pl = df_pl.with_columns(
        pl.col("_price_shifted")
        .rolling_min(window_size=window_1d, min_periods=max(1, window_1d // 10))
        .over(["InstanceType", "AZ"])
        .alias("_price_min_1d")
    )

    # REF: OPTIMIZATION - Use injected median price if available
    if median_price is None:
        median_price = df_pl.select(pl.col("SpotPrice").median()).item()

    epsilon = median_price * 0.001

    df_pl = df_pl.with_columns(
        (
            (pl.col("SpotPrice") - pl.col("_price_min_1d"))
            / (pl.col("OndemandPrice") - pl.col("_price_min_1d") + epsilon)
        )
        .clip(0, 1.5)
        .alias("pool_saturation")
    )

    # Cleanup
    df_pl = df_pl.drop(["_price_shifted", "_price_min_1d"])

    logger.info("Price Dynamics (Polars) created successfully.")
    return df_pl  # REF: OPTIMIZATION


def create_family_time_pattern_features_polars(df: Union[pd.DataFrame, pl.DataFrame]) -> pl.DataFrame:
    """
    Create family-time pattern features using Polars (Optimized).
    """
    logger.info("Creating Family-Time Patterns (Polars Optimized)...")

    if isinstance(df, pd.DataFrame):
        df_pl = pl.from_pandas(df)
    else:
        df_pl = df

    # Pre-shift savings (lag 1)
    df_pl = df_pl.with_columns(pl.col("Savings").shift(1).over(["InstanceType", "AZ"]).alias("_savings_shifted"))

    # 1. Family x Hour (Window = 7 days)
    # We must ensure order is preserved (timestamp) within the over() groups
    df_pl = df_pl.sort("timestamp")

    logger.info("  Processing Family x Hour stats...")
    window_daily = 7
    df_pl = df_pl.with_columns(
        [
            pl.col("_savings_shifted")
            .rolling_mean(window_size=window_daily, min_periods=3)
            .over(["instance_family", "hour"])
            .alias("family_hour_avg_savings"),
            pl.col("_savings_shifted")
            .rolling_std(window_size=window_daily, min_periods=3)
            .over(["instance_family", "hour"])
            .alias("family_hour_std_savings"),
        ]
    )

    # 2. Family x Day of Week (Window = 4 weeks)
    logger.info("  Processing Family x DayOfWeek stats...")
    window_weekly = 4
    df_pl = df_pl.with_columns(
        pl.col("_savings_shifted")
        .rolling_mean(window_size=window_weekly, min_periods=2)
        .over(["instance_family", "day_of_week"])
        .alias("family_dow_avg_savings")
    )

    # 3. Deviations and Z-Scores (vectorized expressions)
    df_pl = df_pl.with_columns(
        (pl.col("_savings_shifted") - pl.col("family_hour_avg_savings")).alias("family_hour_deviation")
    )

    df_pl = df_pl.with_columns(
        (pl.col("family_hour_deviation") / (pl.col("family_hour_std_savings") + 1e-8))
        .clip(-5, 5)
        .alias("family_hour_zscore")
    )

    # 4. Family x Weekend
    logger.info("  Processing Family x Weekend stats...")
    df_pl = df_pl.with_columns(
        pl.col("_savings_shifted")
        .rolling_mean(window_size=window_weekly, min_periods=2)
        .over(["instance_family", "is_weekend"])
        .alias("family_weekend_avg_savings")
    )

    # Cleanup
    df_pl = df_pl.drop("_savings_shifted")

    logger.info("Family-Time Patterns (Polars) created successfully.")
    return df_pl  # REF: OPTIMIZATION


def calculate_family_stress_index_polars(
    df: Union[pd.DataFrame, pl.DataFrame], median_price: Optional[float] = None
) -> pl.DataFrame:
    """
    Calculate Family Stress Index using Polars (Optimized).
    """
    logger.info("Calculating Family Stress Index (Polars Optimized)...")

    if isinstance(df, pd.DataFrame):
        df_pl = pl.from_pandas(df)
    else:
        df_pl = df

    # 7-day window
    window_7d = 1008
    min_periods = max(1, window_7d // 10)

    # Pre-shift price
    df_pl = df_pl.with_columns(pl.col("SpotPrice").shift(1).over(["InstanceType", "AZ"]).alias("_price_shifted"))

    # 1. Price Range Stats (Rolling Min/Max)
    logger.info("  Computing rolling price ranges...")
    df_pl = df_pl.with_columns(
        [
            pl.col("_price_shifted")
            .rolling_min(window_size=window_7d, min_periods=min_periods)
            .over(["InstanceType", "AZ"])
            .alias("price_min_7d"),
            pl.col("_price_shifted")
            .rolling_max(window_size=window_7d, min_periods=min_periods)
            .over(["InstanceType", "AZ"])
            .alias("price_max_7d"),
        ]
    )

    # 2. Price Position
    if median_price is None:
        median_price = df_pl.select(pl.col("SpotPrice").median()).item()

    epsilon = median_price * 0.001

    df_pl = df_pl.with_columns(
        ((pl.col("SpotPrice") - pl.col("price_min_7d")) / (pl.col("price_max_7d") - pl.col("price_min_7d") + epsilon))
        .clip(0, 1)
        .alias("price_position")
    )

    # 3. Family Aggregation (Groupby Mean/Std) - NOT rolling, just simple groupby
    # But we need to map it back to the original dataframe.
    # In Pandas this was a merge. In Polars, we can use window functions over the group!
    # "family_stress" = mean of price_position over [family, AZ, timestamp]

    logger.info("  Aggregating family stress...")
    df_pl = df_pl.with_columns(
        [
            pl.col("price_position").mean().over(["instance_family", "AZ", "timestamp"]).alias("family_stress_index"),
            pl.col("Savings").mean().over(["instance_family", "AZ", "timestamp"]).alias("family_avg_savings"),
            pl.col("Savings")
            .std()
            .fill_null(0.0)  # usage of fill_null in polars
            .over(["instance_family", "AZ", "timestamp"])
            .alias("family_std_savings"),
        ]
    )

    # Cleanup
    df_pl = df_pl.drop(["_price_shifted", "price_min_7d", "price_max_7d", "price_position"])

    logger.info("Family Stress Index (Polars) calculated successfully.")
    return df_pl  # REF: OPTIMIZATION


def prepare_targets_polars(df, horizon: int = 6, return_polars: bool = False):
    """
    Create target variables using Polars (50x Faster than Pandas).
    Replicates logic from src/data.py::prepare_targets.

    Args:
        df: Input pandas.DataFrame OR polars.DataFrame
        horizon: Prediction horizon (e.g. 6 = 1h)
        return_polars: If True, returns polars.DataFrame. Else pandas.DataFrame.

    Returns:
        DataFrame with 'future_savings' and 'is_unstable' added.
    """
    logger.info(f"Generating Targets (Polars Optimized) for horizon={horizon}...")

    if isinstance(df, pd.DataFrame):
        df_pl = pl.from_pandas(df)
    else:
        df_pl = df

    # 1. Global Sort (Required for shift and rolling)
    df_pl = df_pl.sort(["InstanceType", "AZ", "timestamp"])

    # 2. Regression Target: Future Savings
    # Shift(-horizon) within each pool
    df_pl = df_pl.with_columns(pl.col("Savings").shift(-horizon).over(["InstanceType", "AZ"]).alias("future_savings"))

    # 3. Classification Target: Instability Risk
    # a. Create shifted feature for baseline calculation (exclude current row)
    df_pl = df_pl.with_columns(pl.col("Savings").shift(1).over(["InstanceType", "AZ"]).alias("_savings_shifted"))

    # b. Ensure 'hour' column exists
    if "hour" not in df_pl.columns:
        df_pl = df_pl.with_columns(pl.col("timestamp").dt.hour().alias("hour"))

    # c. Calculate Baseline (Mean & Std) per [Instance, AZ, Hour]
    # Window = 42 (7 days * 6 intervals) - consistent with src/data.py
    window_7d_hourly = 42
    min_periods = 14

    # Note: Polars rolling is fast.
    # Logic: Group by [InstanceType, AZ, hour], then roll.
    # IMPORTANT: To roll chronologically within (Family, Hour), the data must be sorted by timestamp.
    # Since we sorted globally above, and 'hour' grouping preserves relative order (days), this works.

    df_pl = df_pl.with_columns(
        [
            pl.col("_savings_shifted")
            .rolling_mean(window_size=window_7d_hourly, min_periods=min_periods)
            .over(["InstanceType", "AZ", "hour"])
            .alias("pool_baseline"),
            pl.col("_savings_shifted")
            .rolling_std(window_size=window_7d_hourly, min_periods=min_periods)
            .over(["InstanceType", "AZ", "hour"])
            .alias("pool_std"),
        ]
    )

    # d. Calculate is_unstable
    # Unstable if future_savings is outside [mean - std, mean + std]
    df_pl = df_pl.with_columns(
        (
            (pl.col("future_savings") < (pl.col("pool_baseline") - pl.col("pool_std")))
            | (pl.col("future_savings") > (pl.col("pool_baseline") + pl.col("pool_std")))
        )
        .cast(pl.Int8)
        .alias("is_unstable")
    )

    # 4. Cleanup & Drop NA
    df_pl = df_pl.drop(["_savings_shifted", "pool_baseline", "pool_std"])
    df_pl = df_pl.drop_nulls(subset=["future_savings", "is_unstable"])

    logger.info(f"Targets Generated. Final Rows: {df_pl.height:,}")
    return df_pl if return_polars else df_pl.to_pandas()


def chronological_split_polars(
    df: pl.DataFrame, train_pct: float = 0.70, val_pct: float = 0.15, test_pct: float = 0.15
) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """
    Split Polars DataFrame chronologically (NO SHUFFLING).
    Memory Optimized: Slices the dataframe without copying data immediately (lazy-ish).

    Args:
        df: Input Polars DataFrame
        train_pct, val_pct, test_pct: Split ratios

    Returns:
        train_df, val_df, test_df (Polars DataFrames)
    """
    assert abs(train_pct + val_pct + test_pct - 1.0) < 0.001, "Split percentages must sum to 1.0"

    # CRITICAL: Sort by timestamp before splitting
    # Polars sort is fast
    df = df.sort("timestamp")

    n = df.height
    train_idx = int(n * train_pct)
    val_idx = int(n * (train_pct + val_pct))

    # Slice (Zero-copy views in Polars)
    train_df = df.slice(0, train_idx)
    val_df = df.slice(train_idx, val_idx - train_idx)
    test_df = df.slice(val_idx, n - val_idx)

    # Verification (Lazy evaluation check)
    # Note: Accessing .item() triggers computation, but it's cheap for single values
    train_max = train_df.select(pl.col("timestamp").max()).item()
    val_min = val_df.select(pl.col("timestamp").min()).item()
    val_max = val_df.select(pl.col("timestamp").max()).item()
    test_min = test_df.select(pl.col("timestamp").min()).item()

    assert train_max <= val_min, f"Leakage: Train Max {train_max} > Val Min {val_min}"
    assert val_max <= test_min, f"Leakage: Val Max {val_max} > Test Min {test_min}"

    print("\n Chronological Split (Polars):")
    print(f" Train: {train_df.height:,} rows")
    print(f" Val:   {val_df.height:,} rows")
    print(f" Test:  {test_df.height:,} rows")

    return train_df, val_df, test_df
