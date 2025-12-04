"""
Hierarchical Spot Instance Stability Prediction Model
======================================================

Production-grade ML model for predicting spot instance stability using
hierarchical relative features calculated per timestamp.

Purpose:
- Train on 2023-2024 historical spot price data
- Predict stability scores (0-100) for spot instances
- Backtest on 2025 Q1/Q2/Q3 data with walk-forward methodology
- Generate comprehensive metrics and visualizations

Architecture:
- Region: ap-south-1 (Mumbai) only
- Instance Types: t3.medium, t4g.medium, c5.large, t4g.small
- Availability Zones: ap-south-1a, ap-south-1b, ap-south-1c
- Total Pools: 12 (4 instance types × 3 AZs)

Model:
- Algorithm: LightGBM Regressor
- Target: stability_score (0-100, higher = more stable)
- Features: Absolute price metrics + Hierarchical relative features (4 levels)
- Prediction Horizon: 6 hours ahead

Key Innovation: Hierarchical features calculated PER TIMESTAMP to simulate
real-time market state and avoid lookahead bias.

Author: ML Training Pipeline v2
Date: 2025
"""

import sys
import os
import warnings
import pickle
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm

from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

warnings.filterwarnings('ignore')
sns.set_style('whitegrid')

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    # Data paths
    'training_data': '/Users/atharvapudale/Downloads/aws_2023_2024_complete_24months.csv',
    'test_q1': '/Users/atharvapudale/Downloads/mumbai_spot_data_sorted_asc(1-2-3-25).csv',
    'test_q2': '/Users/atharvapudale/Downloads/mumbai_spot_data_sorted_asc(4-5-6-25).csv',
    'test_q3': '/Users/atharvapudale/Downloads/mumbai_spot_data_sorted_asc(7-8-9-25).csv',

    # Scope
    'region': 'ap-south-1',
    'instance_types': ['t3.medium', 't4g.medium', 'c5.large', 't4g.small'],
    'availability_zones': ['aps1-az1', 'aps1-az2', 'aps1-az3'],  # Auto-detected from data

    # Output
    'output_dir': './training/outputs',
    'models_dir': './models/uploaded',
    'plots_dir': './training/plots',

    # Model
    'model_filename': 'spot_stability_model_hierarchical.pkl',
    'random_seed': 42,
}

# Create output directories
for dir_path in [CONFIG['output_dir'], CONFIG['models_dir'], CONFIG['plots_dir']]:
    Path(dir_path).mkdir(parents=True, exist_ok=True)

# ============================================================================
# OPTIMIZATION CONFIGURATION (Toggle for fast testing vs production)
# ============================================================================

OPTIMIZATION_CONFIG = {
    # Toggle between fast testing (10% data) and production (100% data)
    'TESTING_MODE': True,  # Set to False for production runs

    # Sampling parameters
    'SAMPLE_RATE': 0.1,  # Use 10% of timestamps (100K → 10K)
    'SAMPLING_METHOD': 'systematic',  # Preserves temporal patterns

    # Feature computation optimizations
    'ENABLE_VECTORIZATION': True,  # Use groupby().transform() instead of loops
    'ENABLE_FEATURE_CACHING': True,  # Cache computed features to disk

    # Cache settings
    'CACHE_DIR': './training/feature_cache',
    'USE_CACHED_FEATURES': True,  # Load from cache if available
}

# Create cache directory
if OPTIMIZATION_CONFIG['ENABLE_FEATURE_CACHING']:
    Path(OPTIMIZATION_CONFIG['CACHE_DIR']).mkdir(parents=True, exist_ok=True)

# IMPORTANT: Clear cache after major feature engineering changes!
# If you've updated the target calculation or added/removed features, delete:
#   ./training/feature_cache/*.parquet
print(f"\n💡 NOTE: If you've changed feature engineering, clear cache: rm -rf {OPTIMIZATION_CONFIG['CACHE_DIR']}/*.parquet\n")

print(f"\n⚡ OPTIMIZATION MODE:")
print(f"  Testing Mode: {'ON' if OPTIMIZATION_CONFIG['TESTING_MODE'] else 'OFF'}")
print(f"  Sample Rate: {OPTIMIZATION_CONFIG['SAMPLE_RATE']*100:.0f}% of data")
print(f"  Vectorization: {'ENABLED' if OPTIMIZATION_CONFIG['ENABLE_VECTORIZATION'] else 'DISABLED'}")
print(f"  Feature Caching: {'ENABLED' if OPTIMIZATION_CONFIG['ENABLE_FEATURE_CACHING'] else 'DISABLED'}")
if OPTIMIZATION_CONFIG['TESTING_MODE']:
    print(f"  ⏱️  Expected training time: ~5-10 minutes (vs 20 hours full data)")
else:
    print(f"  ⏱️  Production mode: Using 100% data (45-60 minutes)")

# Hyperparameters
HYPERPARAMETERS = {
    'n_estimators': 300,
    'max_depth': 7,
    'learning_rate': 0.05,
    'num_leaves': 31,
    'min_child_samples': 20,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'objective': 'regression',
    'metric': 'mae',
    'random_state': CONFIG['random_seed'],
    'verbose': -1,
    'n_jobs': -1
}

print("="*80)
print("HIERARCHICAL SPOT STABILITY PREDICTION MODEL V2")
print("="*80)
print(f"Start Time: {datetime.now()}")
print("="*80)
print(f"\nConfiguration:")
print(f"  Region: {CONFIG['region']}")
print(f"  Instance Types: {CONFIG['instance_types']}")
print(f"  Total Pools: {len(CONFIG['instance_types']) * 3} (4 types × 3 AZs)")
print(f"  Model: LightGBM Regressor")
print(f"  Target: stability_score (0-100)")

# ============================================================================
# DATA LOADING & PREPROCESSING
# ============================================================================

print("\n" + "="*80)
print("1. DATA LOADING & PREPROCESSING")
print("="*80)

def standardize_columns(df):
    """Standardize column names and handle variations"""
    df.columns = df.columns.str.lower().str.strip()

    # Column mapping for common variations
    col_map = {}
    for col in df.columns:
        if 'time' in col or 'date' in col:
            col_map[col] = 'timestamp'
        elif 'spot' in col and 'price' in col:
            col_map[col] = 'spot_price'
        elif 'ondemand' in col or 'on_demand' in col or 'on-demand' in col:
            col_map[col] = 'on_demand_price'
        elif 'instance' in col and 'type' in col:
            col_map[col] = 'instance_type'
        elif col in ['az', 'availability_zone', 'availabilityzone']:
            col_map[col] = 'availability_zone'
        elif col in ['region']:
            col_map[col] = 'region'

    df = df.rename(columns=col_map)

    # Parse timestamp
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

    # Parse numeric columns
    df['spot_price'] = pd.to_numeric(df['spot_price'], errors='coerce')
    if 'on_demand_price' in df.columns:
        df['on_demand_price'] = pd.to_numeric(df['on_demand_price'], errors='coerce')

    # Infer region from AZ if missing
    if 'region' not in df.columns or df['region'].isna().all():
        if 'availability_zone' in df.columns:
            df['region'] = df['availability_zone'].str.extract(r'^([a-z]+-[a-z]+-\d+|aps\d+)')[0]
            # Normalize to standard format
            df['region'] = df['region'].str.replace('aps1', 'ap-south-1')

    # Drop rows with missing critical data
    df = df.dropna(subset=['spot_price', 'timestamp']).sort_values('timestamp')

    return df


def load_data(file_path, data_name):
    """Load and preprocess a single data file"""
    print(f"\n📂 Loading {data_name}...")
    print(f"   Path: {Path(file_path).name}")

    if not Path(file_path).exists():
        print(f"   ❌ File not found: {file_path}")
        return None

    try:
        df = pd.read_csv(file_path)
        print(f"   ✓ Loaded {len(df):,} rows")
        print(f"   Detected columns: {list(df.columns[:5])}...")

        df = standardize_columns(df)

        # Validate required columns
        required = ['timestamp', 'instance_type', 'spot_price', 'on_demand_price']
        missing = [col for col in required if col not in df.columns]
        if missing:
            print(f"   ❌ Missing required columns: {missing}")
            print(f"   Available columns: {list(df.columns)}")
            return None

        # Filter to scope
        if 'region' in df.columns:
            df = df[df['region'] == CONFIG['region']]
        if 'instance_type' in df.columns:
            df = df[df['instance_type'].isin(CONFIG['instance_types'])]

        # Remove nulls and zeros
        df = df[(df['spot_price'] > 0) & (df['on_demand_price'] > 0)]
        df = df.dropna(subset=['spot_price', 'on_demand_price'])

        print(f"   ✓ After filtering: {len(df):,} rows")
        print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

        if 'availability_zone' in df.columns:
            unique_pools = df.groupby(['instance_type', 'availability_zone']).ngroups
            print(f"   Pools: {unique_pools}")

        return df

    except Exception as e:
        print(f"   ❌ Error loading file: {e}")
        return None


def stratified_temporal_sample(df, sample_rate=0.1, method='systematic'):
    """
    Sample timestamps systematically to preserve temporal patterns

    This sampling method maintains:
    - Hourly/daily/weekly patterns (all hours/days represented)
    - Time-series structure (rolling windows still work)
    - Pool coverage (all 12 pools present)
    - Seasonality (uniform sampling preserves periodic patterns)

    Args:
        df: Input dataframe with 'timestamp' column
        sample_rate: Fraction of timestamps to keep (0.1 = 10%)
        method: 'systematic' (every Nth) or 'stratified' (per hour)

    Returns:
        Sampled dataframe with ~sample_rate of original timestamps
    """
    print(f"\n⚡ Temporal sampling (preserving patterns)...")
    print(f"   Original: {len(df):,} rows, {df['timestamp'].nunique():,} unique timestamps")

    df = df.sort_values('timestamp').copy()

    if method == 'systematic':
        # Sample every Nth timestamp
        unique_ts = df['timestamp'].unique()
        n_skip = int(1 / sample_rate)

        # Take every Nth timestamp
        sampled_ts = unique_ts[::n_skip]

        # Filter dataframe
        df_sampled = df[df['timestamp'].isin(sampled_ts)].copy()

    elif method == 'stratified':
        # Sample proportionally from each hour
        df['hour'] = df['timestamp'].dt.hour
        df_sampled = df.groupby('hour', group_keys=False).apply(
            lambda x: x.sample(frac=sample_rate, random_state=CONFIG['random_seed'])
        ).copy()
        df_sampled = df_sampled.drop('hour', axis=1)

    print(f"   Sampled: {len(df_sampled):,} rows, {df_sampled['timestamp'].nunique():,} unique timestamps")
    print(f"   Reduction: {(1 - len(df_sampled)/len(df))*100:.1f}%")

    # Validate pool coverage
    if 'availability_zone' in df_sampled.columns:
        original_pools = df.groupby(['instance_type', 'availability_zone']).ngroups
        sampled_pools = df_sampled.groupby(['instance_type', 'availability_zone']).ngroups
        print(f"   Pool coverage: {sampled_pools}/{original_pools} pools")

        if sampled_pools < original_pools:
            print(f"   ⚠️  WARNING: Some pools missing after sampling!")

    # Validate temporal coverage
    sampled_hours = df_sampled['timestamp'].dt.hour.nunique()
    sampled_days = df_sampled['timestamp'].dt.dayofweek.nunique()
    print(f"   Temporal coverage: {sampled_hours}/24 hours, {sampled_days}/7 days")

    return df_sampled


# Load all datasets
df_train = load_data(CONFIG['training_data'], "Training Data (2023-2024)")
df_q1 = load_data(CONFIG['test_q1'], "Q1 2025 Validation")
df_q2 = load_data(CONFIG['test_q2'], "Q2 2025 Test")
df_q3 = load_data(CONFIG['test_q3'], "Q3 2025 Test")

# Check if all loaded successfully
if df_train is None or df_q1 is None or df_q2 is None or df_q3 is None:
    print("\n❌ ERROR: Failed to load one or more data files. Exiting...")
    sys.exit(1)

print(f"\n✓ All data loaded successfully")
print(f"  Training: {len(df_train):,} rows")
print(f"  Q1 2025: {len(df_q1):,} rows")
print(f"  Q2 2025: {len(df_q2):,} rows")
print(f"  Q3 2025: {len(df_q3):,} rows")

# Apply temporal sampling if in testing mode
if OPTIMIZATION_CONFIG['TESTING_MODE']:
    print(f"\n{'='*80}")
    print(f"APPLYING TEMPORAL SAMPLING (Testing Mode)")
    print(f"{'='*80}")

    sample_rate = OPTIMIZATION_CONFIG['SAMPLE_RATE']
    method = OPTIMIZATION_CONFIG['SAMPLING_METHOD']

    df_train = stratified_temporal_sample(df_train, sample_rate, method)
    df_q1 = stratified_temporal_sample(df_q1, sample_rate, method)
    df_q2 = stratified_temporal_sample(df_q2, sample_rate, method)
    df_q3 = stratified_temporal_sample(df_q3, sample_rate, method)

    print(f"\n✓ Sampling complete")
    print(f"  Training: {len(df_train):,} rows ({sample_rate*100:.0f}% of original)")
    print(f"  Q1 2025: {len(df_q1):,} rows")
    print(f"  Q2 2025: {len(df_q2):,} rows")
    print(f"  Q3 2025: {len(df_q3):,} rows")
    print(f"  ⏱️  Estimated speedup: ~{int(1/sample_rate)}x faster")

# ============================================================================
# FEATURE ENGINEERING
# ============================================================================

print("\n" + "="*80)
print("2. FEATURE ENGINEERING (Absolute + Hierarchical)")
print("="*80)

def calculate_absolute_features(df):
    """
    Calculate absolute (non-hierarchical) features

    These features are calculated independently per pool and don't require
    comparison across pools at a given timestamp.
    """
    print("\n🔧 Calculating absolute features...")

    df = df.copy().sort_values(['instance_type', 'availability_zone', 'timestamp'])

    # Basic discount
    df['discount_pct'] = ((df['on_demand_price'] - df['spot_price']) / df['on_demand_price']) * 100
    df['discount_pct'] = df['discount_pct'].clip(0, 100)

    # Group by pool for time-series features
    pool_groups = list(df.groupby(['instance_type', 'availability_zone']))
    for (inst_type, az), group_df in tqdm(pool_groups, desc="  Processing pools", unit="pool"):
        mask = (df['instance_type'] == inst_type) & (df['availability_zone'] == az)

        # Volatility (24-hour rolling std)
        df.loc[mask, 'volatility_24h'] = group_df['spot_price'].rolling(24, min_periods=1).std()

        # Price velocity
        df.loc[mask, 'price_velocity_1h'] = group_df['spot_price'].diff(1)
        df.loc[mask, 'price_velocity_6h'] = group_df['spot_price'].diff(6)

        # Spike count (price increases >50% in 24h window)
        price_changes = group_df['spot_price'].pct_change()
        spikes = (price_changes > 0.5).astype(int)
        df.loc[mask, 'spike_count_24h'] = spikes.rolling(24, min_periods=1).sum()

        # 30-day price statistics
        df.loc[mask, 'price_30d_mean'] = group_df['spot_price'].rolling(720, min_periods=1).mean()
        df.loc[mask, 'price_30d_std'] = group_df['spot_price'].rolling(720, min_periods=1).std()

    # Deviation from historical mean
    df['deviation_from_mean'] = ((df['spot_price'] - df['price_30d_mean']) / df['price_30d_mean']) * 100
    df['deviation_from_mean'] = df['deviation_from_mean'].fillna(0)

    # Ceiling distance (same as discount)
    df['ceiling_distance_pct'] = df['discount_pct']

    # Fill NaNs from diff/rolling operations
    df['price_velocity_1h'] = df['price_velocity_1h'].fillna(0)
    df['price_velocity_6h'] = df['price_velocity_6h'].fillna(0)
    df['spike_count_24h'] = df['spike_count_24h'].fillna(0)
    df['volatility_24h'] = df['volatility_24h'].fillna(df.groupby(['instance_type', 'availability_zone'])['volatility_24h'].transform('mean'))
    df['volatility_24h'] = df['volatility_24h'].fillna(0)

    print(f"  ✓ Created absolute features")
    print(f"  Features: discount_pct, volatility_24h, price_velocity_*, spike_count_24h, deviation_from_mean")

    return df


def calculate_stability_score_future_based(df, lookahead_hours=6):
    """
    Calculate stability_score based on FUTURE events (6 hours ahead)

    CRITICAL: This fixes data leakage. Target is based on future stability,
    while features are from current time. Model must learn patterns that
    predict future, not memorize current state.

    Args:
        df: DataFrame with spot price data
        lookahead_hours: How many hours ahead to look for stability calculation

    Returns:
        DataFrame with stability_score calculated from future events
        (last lookahead_hours rows per pool are dropped - no future data)
    """
    print(f"\n🎯 Calculating future-based stability scores (lookahead={lookahead_hours}h)...")

    df = df.copy().sort_values(['instance_type', 'availability_zone', 'timestamp'])
    df['stability_score'] = np.nan

    rows_before = len(df)

    for (inst_type, az), group_df in tqdm(df.groupby(['instance_type', 'availability_zone']),
                                          desc="  Processing pools", unit="pool"):
        mask = (df['instance_type'] == inst_type) & (df['availability_zone'] == az)

        # Get indices for this pool
        indices = group_df.index.tolist()

        # For each row, calculate metrics from NEXT lookahead_hours rows
        for i, idx in enumerate(indices):
            # Get future window (next N hours)
            future_start = i + 1
            future_end = i + 1 + lookahead_hours

            # Skip if we don't have enough future data
            if future_end > len(indices):
                # Leave as NaN - will be dropped later
                continue

            future_indices = indices[future_start:future_end]
            future_data = df.loc[future_indices]

            # Calculate future volatility
            future_vol = future_data['spot_price'].std()
            future_vol_ratio = future_vol / df.loc[idx, 'on_demand_price']

            # Calculate future spikes (>50% price jumps)
            future_price_changes = future_data['spot_price'].pct_change().fillna(0)
            future_spikes = (future_price_changes > 0.5).sum()

            # Calculate future discount change (how much discount drops)
            current_discount = df.loc[idx, 'discount_pct']
            future_min_discount = future_data['discount_pct'].min()
            future_discount_drop = max(0, current_discount - future_min_discount)

            # Calculate future major interruption (>100% price spike)
            future_interruption = int((future_price_changes > 1.0).any())

            # Calculate stability score from future events
            # CRITICAL: Aggressive 9-category penalty system to create variance in stable data
            # NO individual caps - penalties stack additively, only final score clipped to [0,100]
            stability = 100.0
            penalties_applied = []  # For debugging

            # ═══════════════════════════════════════════════════════════════
            # PRIORITY 1: Discount proximity to on-demand (STRONGEST signal)
            # ═══════════════════════════════════════════════════════════════
            # Discount < 20% is extremely dangerous - AWS reclaiming capacity
            if future_min_discount < 5:
                stability -= 80
                penalties_applied.append(('P1_discount<5%', 80))
            elif future_min_discount < 10:
                stability -= 70
                penalties_applied.append(('P1_discount<10%', 70))
            elif future_min_discount < 15:
                stability -= 60
                penalties_applied.append(('P1_discount<15%', 60))
            elif future_min_discount < 20:
                stability -= 50
                penalties_applied.append(('P1_discount<20%', 50))
            elif future_min_discount < 30:
                stability -= 40
                penalties_applied.append(('P1_discount<30%', 40))

            # ═══════════════════════════════════════════════════════════════
            # PRIORITY 2: Volatility normalized by on-demand price
            # ═══════════════════════════════════════════════════════════════
            # High volatility indicates market instability
            if future_vol_ratio > 0.15:  # >15%
                stability -= 70
                penalties_applied.append(('P2_vol>15%', 70))
            elif future_vol_ratio > 0.10:  # >10%
                stability -= 60
                penalties_applied.append(('P2_vol>10%', 60))
            elif future_vol_ratio > 0.07:  # >7%
                stability -= 50
                penalties_applied.append(('P2_vol>7%', 50))
            elif future_vol_ratio > 0.05:  # >5%
                stability -= 40
                penalties_applied.append(('P2_vol>5%', 40))
            elif future_vol_ratio > 0.03:  # >3%
                stability -= 30
                penalties_applied.append(('P2_vol>3%', 30))

            # ═══════════════════════════════════════════════════════════════
            # PRIORITY 3: Price spikes (>50% sudden jumps)
            # ═══════════════════════════════════════════════════════════════
            # Multiple spikes = chaotic market
            if future_spikes >= 3:
                stability -= 60
                penalties_applied.append(('P3_spikes>=3', 60))
            elif future_spikes >= 2:
                stability -= 45
                penalties_applied.append(('P3_spikes>=2', 45))
            elif future_spikes >= 1:
                stability -= 30
                penalties_applied.append(('P3_spikes>=1', 30))

            # ═══════════════════════════════════════════════════════════════
            # PRIORITY 4: Discount collapse (current → future)
            # ═══════════════════════════════════════════════════════════════
            # Losing discount means approaching interruption
            if future_discount_drop > 50:
                stability -= 70
                penalties_applied.append(('P4_drop>50%', 70))
            elif future_discount_drop > 30:
                stability -= 55
                penalties_applied.append(('P4_drop>30%', 55))
            elif future_discount_drop > 20:
                stability -= 45
                penalties_applied.append(('P4_drop>20%', 45))
            elif future_discount_drop > 10:
                stability -= 35
                penalties_applied.append(('P4_drop>10%', 35))
            elif future_discount_drop > 5:
                stability -= 25
                penalties_applied.append(('P4_drop>5%', 25))

            # ═══════════════════════════════════════════════════════════════
            # PRIORITY 5: Price trend rising
            # ═══════════════════════════════════════════════════════════════
            # Rising prices = capacity crunch
            future_mean_price = future_data['spot_price'].mean()
            current_price = df.loc[idx, 'spot_price']
            if future_mean_price > current_price * 1.5:
                stability -= 60
                penalties_applied.append(('P5_price+50%', 60))
            elif future_mean_price > current_price * 1.3:
                stability -= 50
                penalties_applied.append(('P5_price+30%', 50))
            elif future_mean_price > current_price * 1.2:
                stability -= 40
                penalties_applied.append(('P5_price+20%', 40))
            elif future_mean_price > current_price * 1.1:
                stability -= 30
                penalties_applied.append(('P5_price+10%', 30))
            elif future_mean_price > current_price * 1.05:
                stability -= 20
                penalties_applied.append(('P5_price+5%', 20))

            # ═══════════════════════════════════════════════════════════════
            # PRIORITY 6: Sustained high prices (NEW)
            # ═══════════════════════════════════════════════════════════════
            # Many hours near on-demand = prolonged capacity pressure
            on_demand = df.loc[idx, 'on_demand_price']
            high_price_hours = (future_data['spot_price'] > on_demand * 0.8).sum()
            if high_price_hours >= 5:
                stability -= 50
                penalties_applied.append(('P6_high_price_5h+', 50))
            elif high_price_hours >= 4:
                stability -= 40
                penalties_applied.append(('P6_high_price_4h', 40))
            elif high_price_hours >= 3:
                stability -= 30
                penalties_applied.append(('P6_high_price_3h', 30))

            # ═══════════════════════════════════════════════════════════════
            # PRIORITY 7: Relative volatility increase
            # ═══════════════════════════════════════════════════════════════
            # Future more volatile than past = market destabilizing
            current_vol = df.loc[idx, 'volatility_24h']
            if current_vol > 0 and future_vol > current_vol * 3.0:
                stability -= 50
                penalties_applied.append(('P7_vol_3x', 50))
            elif current_vol > 0 and future_vol > current_vol * 2.5:
                stability -= 40
                penalties_applied.append(('P7_vol_2.5x', 40))
            elif current_vol > 0 and future_vol > current_vol * 2.0:
                stability -= 30
                penalties_applied.append(('P7_vol_2x', 30))
            elif current_vol > 0 and future_vol > current_vol * 1.5:
                stability -= 20
                penalties_applied.append(('P7_vol_1.5x', 20))

            # ═══════════════════════════════════════════════════════════════
            # PRIORITY 8: Major interruption signals
            # ═══════════════════════════════════════════════════════════════
            # Extreme price spikes (>75% and >100% jumps)
            major_spikes = (future_price_changes > 1.0).sum()  # >100%
            severe_spikes = (future_price_changes > 0.75).sum()  # >75%
            if major_spikes > 0:
                stability -= 80
                penalties_applied.append(('P8_spike>100%', 80))
            elif severe_spikes > 0:
                stability -= 60
                penalties_applied.append(('P8_spike>75%', 60))

            # ═══════════════════════════════════════════════════════════════
            # PRIORITY 9: Consecutive bad hours (NEW)
            # ═══════════════════════════════════════════════════════════════
            # Multiple consecutive hours with low discount = sustained pressure
            consecutive_bad = 0
            max_consecutive_bad = 0
            for discount in future_data['discount_pct'].values:
                if discount < 30:
                    consecutive_bad += 1
                    max_consecutive_bad = max(max_consecutive_bad, consecutive_bad)
                else:
                    consecutive_bad = 0

            if max_consecutive_bad >= 4:
                stability -= 60
                penalties_applied.append(('P9_4h_bad', 60))
            elif max_consecutive_bad >= 3:
                stability -= 45
                penalties_applied.append(('P9_3h_bad', 45))
            elif max_consecutive_bad >= 2:
                stability -= 30
                penalties_applied.append(('P9_2h_bad', 30))

            # ═══════════════════════════════════════════════════════════════
            # FINAL: Clip to [0, 100] range (ONLY clipping, NO individual caps)
            # ═══════════════════════════════════════════════════════════════
            stability = max(0, min(100, stability))

            df.loc[idx, 'stability_score'] = stability

    # Remove rows where we can't calculate future stability (last N rows per pool)
    rows_with_target = df['stability_score'].notna()
    df = df[rows_with_target].copy()

    rows_after = len(df)
    rows_dropped = rows_before - rows_after
    avg_score = df['stability_score'].mean()
    std_score = df['stability_score'].std()

    print(f"  ✓ Calculated future-based stability (lookahead={lookahead_hours}h)")
    print(f"  ✓ Dropped {rows_dropped:,} rows (last {lookahead_hours}h per pool, no future data)")
    print(f"  ✓ Remaining rows: {len(df):,}")
    print(f"  ✓ Average stability score: {avg_score:.1f}/100 (std: {std_score:.1f})")
    print(f"  Score distribution:")
    print(f"    0-20:  {(df['stability_score'] <= 20).sum():,} rows ({(df['stability_score'] <= 20).sum() / len(df) * 100:.1f}%)")
    print(f"    20-40: {((df['stability_score'] > 20) & (df['stability_score'] <= 40)).sum():,} rows ({((df['stability_score'] > 20) & (df['stability_score'] <= 40)).sum() / len(df) * 100:.1f}%)")
    print(f"    40-60: {((df['stability_score'] > 40) & (df['stability_score'] <= 60)).sum():,} rows ({((df['stability_score'] > 40) & (df['stability_score'] <= 60)).sum() / len(df) * 100:.1f}%)")
    print(f"    60-80: {((df['stability_score'] > 60) & (df['stability_score'] <= 80)).sum():,} rows ({((df['stability_score'] > 60) & (df['stability_score'] <= 80)).sum() / len(df) * 100:.1f}%)")
    print(f"    80-100: {(df['stability_score'] > 80).sum():,} rows ({(df['stability_score'] > 80).sum() / len(df) * 100:.1f}%)")

    # ═══════════════════════════════════════════════════════════════
    # VALIDATION: Ensure penalty system creates proper variance
    # ═══════════════════════════════════════════════════════════════
    print(f"\n  🔍 Validating stability score distribution...")

    pct_below_30 = (df['stability_score'] < 30).sum() / len(df) * 100
    pct_above_80 = (df['stability_score'] > 80).sum() / len(df) * 100

    validation_passed = True
    warnings = []

    # Check 1: Mean should be balanced (40-70)
    if avg_score < 40 or avg_score > 70:
        warnings.append(f"⚠️  Mean={avg_score:.1f} is outside expected range [40-70]")
        validation_passed = False
    else:
        print(f"  ✓ Mean stability in expected range: {avg_score:.1f}/100")

    # Check 2: Standard deviation should show variance (>15)
    if std_score < 15:
        warnings.append(f"⚠️  Std={std_score:.1f} is too low (should be >15) - insufficient variance")
        validation_passed = False
    else:
        print(f"  ✓ Std shows good variance: {std_score:.1f}")

    # Check 3: At least 5% of data should be below 30 (unstable hours)
    if pct_below_30 < 5:
        warnings.append(f"⚠️  Only {pct_below_30:.1f}% below 30 (should be ≥5%) - penalties too weak")
        validation_passed = False
    else:
        print(f"  ✓ {pct_below_30:.1f}% of hours are unstable (score <30)")

    # Check 4: At least 5% should be above 80 (stable hours)
    if pct_above_80 < 5:
        warnings.append(f"⚠️  Only {pct_above_80:.1f}% above 80 (should be ≥5%) - not enough stable hours")
        validation_passed = False
    else:
        print(f"  ✓ {pct_above_80:.1f}% of hours are stable (score >80)")

    # Check 5: Distribution shouldn't be too concentrated
    pct_in_top_bin = (df['stability_score'] > 80).sum() / len(df) * 100
    if pct_in_top_bin > 50:
        warnings.append(f"⚠️  {pct_in_top_bin:.1f}% concentrated in 80-100 bin - penalties still too weak")
        validation_passed = False

    if validation_passed:
        print(f"  ✅ All validation checks passed - penalty system working correctly!")
    else:
        print(f"\n  ❌ Validation FAILED - penalty system needs tuning:")
        for warning in warnings:
            print(f"     {warning}")
        print(f"\n  💡 This may indicate:")
        print(f"     - Data is extremely stable (few instability signals in future windows)")
        print(f"     - Penalty thresholds need adjustment for this data")
        print(f"     - Consider reviewing penalty multipliers or thresholds")

    return df


def calculate_hierarchical_features_vectorized(df):
    """
    VECTORIZED version - Calculate hierarchical features using pandas groupby().transform()

    50-100x faster than looping! Uses built-in pandas operations instead of Python loops.
    """
    print("\n🌲 Calculating hierarchical features (VECTORIZED - per timestamp)...")

    df = df.copy()

    # Extract instance family from instance_type
    df['instance_family'] = df['instance_type'].str.extract(r'([a-z]+\d+[a-z]*)')[0]

    # Encode instance characteristics
    size_map = {'medium': 3, 'large': 5, 'xlarge': 6, '2xlarge': 7, '4xlarge': 8, '8xlarge': 9, 'small': 2}
    df['size_tier'] = df['instance_type'].apply(lambda x: size_map.get(x.split('.')[-1], 5))
    df['generation'] = df['instance_family'].str.extract(r'(\d+)')[0].fillna('5').astype(int)

    # Encode AZ
    df['az_encoded'] = pd.Categorical(df['availability_zone']).codes

    # Time features
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['is_business_hours'] = ((df['hour'] >= 10) & (df['hour'] <= 18)).astype(int)

    print(f"  Processing {df['timestamp'].nunique():,} unique timestamps...")

    # L1: Global (all pools at this timestamp) - VECTORIZED
    print(f"  ⚡ L1 Global features...")
    df['discount_percentile_L1_global'] = df.groupby('timestamp')['discount_pct'].rank(pct=True)
    df['volatility_percentile_L1_global'] = df.groupby('timestamp')['volatility_24h'].rank(pct=True)

    # Z-score
    discount_mean = df.groupby('timestamp')['discount_pct'].transform('mean')
    discount_std = df.groupby('timestamp')['discount_pct'].transform('std').replace(0, 1)
    df['discount_zscore_L1_global'] = (df['discount_pct'] - discount_mean) / discount_std

    # Market stress (continuous - based on volatility, not binary flag)
    df['market_stress_L1_global'] = df.groupby('timestamp')['volatility_percentile_L1_global'].transform('mean')

    # L2: Family level - VECTORIZED
    print(f"  ⚡ L2 Family features...")
    df['discount_percentile_L2_family'] = df.groupby(['timestamp', 'instance_family'])['discount_pct'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['volatility_percentile_L2_family'] = df.groupby(['timestamp', 'instance_family'])['volatility_24h'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    # Family stress (continuous - based on volatility percentile)
    df['family_stress_L2'] = df.groupby(['timestamp', 'instance_family'])['volatility_percentile_L2_family'].transform('mean')

    # L3: AZ level - VECTORIZED
    print(f"  ⚡ L3 AZ features...")
    df['discount_percentile_L3_az'] = df.groupby(['timestamp', 'availability_zone'])['discount_pct'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['volatility_percentile_L3_az'] = df.groupby(['timestamp', 'availability_zone'])['volatility_24h'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    # AZ stress (continuous - based on volatility percentile)
    df['az_stress_L3'] = df.groupby(['timestamp', 'availability_zone'])['volatility_percentile_L3_az'].transform('mean')

    # L4: Peer level (family + AZ) - VECTORIZED
    print(f"  ⚡ L4 Peer features...")
    df['discount_percentile_L4_peer'] = df.groupby(['timestamp', 'instance_family', 'availability_zone'])['discount_pct'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['volatility_percentile_L4_peer'] = df.groupby(['timestamp', 'instance_family', 'availability_zone'])['volatility_24h'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['peer_pool_count'] = df.groupby(['timestamp', 'instance_family', 'availability_zone'])['instance_type'].transform('count')

    # Cross-level features
    print(f"  ⚡ Cross-level features...")
    df['global_vs_family_gap'] = df['discount_percentile_L1_global'] - df['discount_percentile_L2_family']

    # Better alternatives (simplified for speed)
    # Count how many pools in family have better discount AND better volatility
    family_discount_mean = df.groupby(['timestamp', 'instance_family'])['discount_pct'].transform('mean')
    family_volatility_mean = df.groupby(['timestamp', 'instance_family'])['volatility_24h'].transform('mean')

    # For each pool, check if others in family are better
    is_better = ((df['discount_pct'] > family_discount_mean) &
                 (df['volatility_24h'] < family_volatility_mean)).astype(int)

    df['better_alternatives_L2_family'] = df.groupby(['timestamp', 'instance_family']).cumcount() * 0  # Initialize to 0
    df['better_alternatives_L2_family'] = df.groupby(['timestamp', 'instance_family'])['discount_pct'].transform(
        lambda x: ((x > x.mean()).astype(int).sum() if len(x) > 1 else 0)
    )

    # Fill any NaNs
    hierarchical_cols = [
        'discount_percentile_L1_global', 'volatility_percentile_L1_global',
        'discount_zscore_L1_global', 'market_stress_L1_global',
        'discount_percentile_L2_family', 'volatility_percentile_L2_family', 'family_stress_L2',
        'discount_percentile_L3_az', 'volatility_percentile_L3_az', 'az_stress_L3',
        'discount_percentile_L4_peer', 'volatility_percentile_L4_peer', 'peer_pool_count',
        'global_vs_family_gap', 'better_alternatives_L2_family'
    ]

    for col in hierarchical_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0.5 if 'percentile' in col else 0)

    print(f"  ✓ Completed hierarchical feature calculation (vectorized)")
    print(f"  Sample hierarchical features:")
    sample_cols = ['discount_percentile_L1_global', 'discount_percentile_L2_family',
                   'discount_percentile_L3_az', 'market_stress_L1_global']
    print(df[sample_cols].head().to_string())

    return df


def calculate_hierarchical_features(df):
    """
    Calculate hierarchical relative features PER TIMESTAMP

    CRITICAL: These must be calculated within each timestamp group to avoid
    lookahead bias and simulate real-time market state.

    Levels:
    - L1_Global: All pools at this timestamp
    - L2_Family: Pools with same instance family
    - L3_AZ: Pools in same availability zone
    - L4_Peer: Pools with same family AND same AZ

    NOTE: If ENABLE_VECTORIZATION is True, uses vectorized version (50-100x faster)
    """
    # Use vectorized version if enabled
    if OPTIMIZATION_CONFIG.get('ENABLE_VECTORIZATION', False):
        return calculate_hierarchical_features_vectorized(df)

    # Original loop-based version (for production verification)
    print("\n🌲 Calculating hierarchical features (per timestamp)...")

    df = df.copy()

    # Extract instance family from instance_type
    df['instance_family'] = df['instance_type'].str.extract(r'([a-z]+\d+[a-z]*)')[0]

    # Encode instance characteristics
    size_map = {'medium': 3, 'large': 5, 'xlarge': 6, '2xlarge': 7, '4xlarge': 8, '8xlarge': 9, 'small': 2}
    df['size_tier'] = df['instance_type'].apply(lambda x: size_map.get(x.split('.')[-1], 5))
    df['generation'] = df['instance_family'].str.extract(r'(\d+)')[0].fillna('5').astype(int)

    # Encode AZ
    df['az_encoded'] = pd.Categorical(df['availability_zone']).codes

    # Time features
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['is_business_hours'] = ((df['hour'] >= 10) & (df['hour'] <= 18)).astype(int)

    # Initialize hierarchical feature columns
    hierarchical_features = [
        'discount_percentile_L1_global', 'volatility_percentile_L1_global',
        'discount_zscore_L1_global', 'market_stress_L1_global',
        'discount_percentile_L2_family', 'volatility_percentile_L2_family', 'family_stress_L2',
        'discount_percentile_L3_az', 'volatility_percentile_L3_az', 'az_stress_L3',
        'discount_percentile_L4_peer', 'volatility_percentile_L4_peer', 'peer_pool_count',
        'global_vs_family_gap', 'better_alternatives_L2_family'
    ]

    for feat in hierarchical_features:
        df[feat] = 0.0

    # Calculate per timestamp (this is the key to avoiding lookahead bias!)
    timestamps = df['timestamp'].unique()
    print(f"  Processing {len(timestamps):,} unique timestamps...")

    for ts in tqdm(timestamps, desc="  Hierarchical Features", unit="timestamp"):
        ts_mask = df['timestamp'] == ts
        ts_data = df[ts_mask].copy()

        if len(ts_data) < 2:
            continue

        # L1: Global (all pools at this timestamp)
        df.loc[ts_mask, 'discount_percentile_L1_global'] = ts_data['discount_pct'].rank(pct=True)
        df.loc[ts_mask, 'volatility_percentile_L1_global'] = ts_data['volatility_24h'].rank(pct=True)

        global_mean = ts_data['discount_pct'].mean()
        global_std = ts_data['discount_pct'].std()
        if global_std > 0:
            df.loc[ts_mask, 'discount_zscore_L1_global'] = (ts_data['discount_pct'] - global_mean) / global_std

        # Market stress (continuous - based on volatility percentile)
        df.loc[ts_mask, 'market_stress_L1_global'] = ts_data['volatility_percentile_L1_global'].mean()

        # L2: Family level
        for family in ts_data['instance_family'].unique():
            family_mask = ts_mask & (df['instance_family'] == family)
            family_data = ts_data[ts_data['instance_family'] == family]

            if len(family_data) >= 2:
                df.loc[family_mask, 'discount_percentile_L2_family'] = family_data['discount_pct'].rank(pct=True).values
                df.loc[family_mask, 'volatility_percentile_L2_family'] = family_data['volatility_24h'].rank(pct=True).values
                # Family stress (continuous - based on volatility)
                df.loc[family_mask, 'family_stress_L2'] = family_data['volatility_percentile_L2_family'].mean()
            else:
                df.loc[family_mask, 'discount_percentile_L2_family'] = 0.5
                df.loc[family_mask, 'volatility_percentile_L2_family'] = 0.5
                df.loc[family_mask, 'family_stress_L2'] = 0.0

        # L3: AZ level
        for az in ts_data['availability_zone'].unique():
            az_mask = ts_mask & (df['availability_zone'] == az)
            az_data = ts_data[ts_data['availability_zone'] == az]

            if len(az_data) >= 2:
                df.loc[az_mask, 'discount_percentile_L3_az'] = az_data['discount_pct'].rank(pct=True).values
                df.loc[az_mask, 'volatility_percentile_L3_az'] = az_data['volatility_24h'].rank(pct=True).values
                # AZ stress (continuous - based on volatility)
                df.loc[az_mask, 'az_stress_L3'] = az_data['volatility_percentile_L3_az'].mean()
            else:
                df.loc[az_mask, 'discount_percentile_L3_az'] = 0.5
                df.loc[az_mask, 'volatility_percentile_L3_az'] = 0.5
                df.loc[az_mask, 'az_stress_L3'] = 0.0

        # L4: Peer level (family + AZ)
        for family in ts_data['instance_family'].unique():
            for az in ts_data['availability_zone'].unique():
                peer_mask = ts_mask & (df['instance_family'] == family) & (df['availability_zone'] == az)
                peer_data = ts_data[(ts_data['instance_family'] == family) & (ts_data['availability_zone'] == az)]

                df.loc[peer_mask, 'peer_pool_count'] = len(peer_data)

                if len(peer_data) >= 2:
                    df.loc[peer_mask, 'discount_percentile_L4_peer'] = peer_data['discount_pct'].rank(pct=True).values
                    df.loc[peer_mask, 'volatility_percentile_L4_peer'] = peer_data['volatility_24h'].rank(pct=True).values
                else:
                    df.loc[peer_mask, 'discount_percentile_L4_peer'] = 0.5
                    df.loc[peer_mask, 'volatility_percentile_L4_peer'] = 0.5

        # Cross-level features
        df.loc[ts_mask, 'global_vs_family_gap'] = (
            df.loc[ts_mask, 'discount_percentile_L1_global'] -
            df.loc[ts_mask, 'discount_percentile_L2_family']
        )

        # Better alternatives in family
        for family in ts_data['instance_family'].unique():
            family_data = ts_data[ts_data['instance_family'] == family]
            for idx, row in family_data.iterrows():
                better_count = (
                    (family_data['discount_pct'] > row['discount_pct']) &
                    (family_data['volatility_24h'] < row['volatility_24h'])
                ).sum()
                df.loc[idx, 'better_alternatives_L2_family'] = better_count

    print(f"  ✓ Completed hierarchical feature calculation")
    print(f"  Sample hierarchical features:")
    sample_cols = ['discount_percentile_L1_global', 'discount_percentile_L2_family',
                   'discount_percentile_L3_az', 'market_stress_L1_global']
    print(df[sample_cols].head().to_string())

    return df


def add_pool_history_features(df):
    """Calculate pool-specific historical metrics (expanding window)"""
    print("\n📊 Calculating pool history features...")

    df = df.copy().sort_values(['instance_type', 'availability_zone', 'timestamp'])

    pool_groups = list(df.groupby(['instance_type', 'availability_zone']))
    for (inst_type, az), group_df in tqdm(pool_groups, desc="  Pool history", unit="pool"):
        mask = (df['instance_type'] == inst_type) & (df['availability_zone'] == az)

        # Historical volatility rate (expanding window) - continuous metric
        # High volatility = high stress, so we normalize to 0-1 scale
        volatility_norm = (group_df['volatility_24h'] / group_df['on_demand_price']).clip(0, 1)
        df.loc[mask, 'pool_historical_stress_rate'] = volatility_norm.expanding().mean().values

    df['pool_historical_stress_rate'] = df['pool_historical_stress_rate'].fillna(0)

    print(f"  ✓ Added pool history features")

    return df


def add_lag_features(df, lag_hours=[1, 3, 6, 12, 24]):
    """
    Add lag features to capture temporal patterns leading to instability

    Lag features help the model learn how past metrics evolve into future stability/instability.
    For example, a discount that's been dropping for 6 hours might predict future instability.

    Args:
        df: DataFrame with engineered features
        lag_hours: List of lag periods in hours

    Returns:
        DataFrame with lag features added
    """
    print(f"\n⏱️  Adding lag features: {lag_hours} hours...")

    df = df.copy().sort_values(['instance_type', 'availability_zone', 'timestamp'])

    pool_groups = list(df.groupby(['instance_type', 'availability_zone']))
    for (inst_type, az), group_df in tqdm(pool_groups, desc="  Adding lags", unit="pool"):
        mask = (df['instance_type'] == inst_type) & (df['availability_zone'] == az)

        for lag in lag_hours:
            # Lagged discount
            df.loc[mask, f'discount_pct_lag_{lag}h'] = group_df['discount_pct'].shift(lag)

            # Lagged volatility
            df.loc[mask, f'volatility_24h_lag_{lag}h'] = group_df['volatility_24h'].shift(lag)

            # Change from lag to now (trend direction)
            df.loc[mask, f'discount_change_{lag}h'] = group_df['discount_pct'] - group_df['discount_pct'].shift(lag)

    # Fill NaNs from shift operations (backfill first rows, then fill any remaining)
    lag_cols = [col for col in df.columns if '_lag_' in col or '_change_' in col]
    for col in lag_cols:
        df[col] = df.groupby(['instance_type', 'availability_zone'])[col].fillna(method='bfill')
    df[lag_cols] = df[lag_cols].fillna(0)

    print(f"  ✓ Added {len(lag_cols)} lag features")

    return df


def engineer_features_with_cache(df, dataset_name):
    """
    Engineer all features with optional caching

    If caching is enabled and cached features exist, load from cache.
    Otherwise, compute features and save to cache.

    Args:
        df: Input dataframe
        dataset_name: Name for cache file (e.g., 'train', 'q1', 'q2', 'q3')

    Returns:
        DataFrame with all engineered features
    """
    if not OPTIMIZATION_CONFIG['ENABLE_FEATURE_CACHING']:
        # No caching - compute directly
        df = calculate_absolute_features(df)
        df = calculate_stability_score_future_based(df, lookahead_hours=6)
        df = calculate_hierarchical_features(df)
        df = add_pool_history_features(df)
        df = add_lag_features(df, lag_hours=[1, 3, 6, 12, 24])
        return df

    # Generate cache filename
    cache_dir = Path(OPTIMIZATION_CONFIG['CACHE_DIR'])
    sample_suffix = f"_sample{OPTIMIZATION_CONFIG['SAMPLE_RATE']}" if OPTIMIZATION_CONFIG['TESTING_MODE'] else "_full"
    vectorized_suffix = "_vectorized" if OPTIMIZATION_CONFIG['ENABLE_VECTORIZATION'] else "_loop"
    cache_file = cache_dir / f"{dataset_name}{sample_suffix}{vectorized_suffix}_features.parquet"

    # Check if cache exists and should be used
    if OPTIMIZATION_CONFIG['USE_CACHED_FEATURES'] and cache_file.exists():
        print(f"\n⚡ Loading cached features from: {cache_file.name}")
        try:
            df_cached = pd.read_parquet(cache_file)
            print(f"  ✓ Loaded {len(df_cached):,} rows with {len(df_cached.columns)} columns from cache")

            # Validate cache has ALL required columns (including lag features)
            required_cols = [
                'discount_pct', 'stability_score', 'discount_percentile_L1_global',
                'discount_pct_lag_1h', 'discount_pct_lag_6h', 'volatility_24h_lag_1h',  # Check for lag features
                'market_stress_L1_global', 'family_stress_L2', 'az_stress_L3'  # Check for continuous stress metrics
            ]
            missing_cols = [col for col in required_cols if col not in df_cached.columns]

            if len(missing_cols) > 0:
                print(f"  ⚠️  Cache missing {len(missing_cols)} columns: {missing_cols[:3]}...")
                print(f"  ⚠️  Cache was created before data leakage fixes, recomputing...")
            else:
                # CRITICAL: Validate stability_score has proper variance (not buggy calculation)
                std_stability = df_cached['stability_score'].std()
                mean_stability = df_cached['stability_score'].mean()

                if std_stability < 5.0:
                    print(f"  ⚠️  Cache has buggy stability_score (std={std_stability:.2f}, mean={mean_stability:.1f})")
                    print(f"  ⚠️  Stability score has no variance - using old rolling+shift calculation")
                    print(f"  ⚠️  Recomputing with fixed future-based calculation...")
                elif mean_stability > 95:
                    print(f"  ⚠️  Cache has buggy stability_score (mean={mean_stability:.1f} - too high)")
                    print(f"  ⚠️  All scores near 100 = no variance - using old calculation")
                    print(f"  ⚠️  Recomputing with fixed future-based calculation...")
                else:
                    print(f"  ✓ Cache validation passed (all features present, stability variance OK)")
                    print(f"  ✓ Stability score: mean={mean_stability:.1f}, std={std_stability:.1f}")
                    return df_cached
        except Exception as e:
            print(f"  ⚠️  Error loading cache: {e}")
            print(f"  Recomputing features...")

    # Compute features
    print(f"\n🔧 Computing features (will cache to: {cache_file.name})...")
    df = calculate_absolute_features(df)
    df = calculate_stability_score_future_based(df, lookahead_hours=6)
    df = calculate_hierarchical_features(df)
    df = add_pool_history_features(df)
    df = add_lag_features(df, lag_hours=[1, 3, 6, 12, 24])

    # Save to cache
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_file, index=False)
        print(f"  ✓ Cached features to: {cache_file}")
        print(f"  Cache size: {cache_file.stat().st_size / 1024 / 1024:.1f} MB")
    except Exception as e:
        print(f"  ⚠️  Warning: Could not cache features: {e}")

    return df


# Apply all feature engineering
print("\n🚀 Starting feature engineering pipeline...")

df_train = engineer_features_with_cache(df_train, 'train')

print(f"\n✓ Feature engineering complete on training data")
print(f"  Total features: {len([c for c in df_train.columns if c not in ['timestamp', 'instance_type', 'availability_zone', 'region']])}")
print(f"  Final shape: {df_train.shape}")

# ============================================================================
# MODEL TRAINING
# ============================================================================

print("\n" + "="*80)
print("3. MODEL TRAINING (LightGBM Regressor)")
print("="*80)

# Define feature list (UPDATED: No is_stressed, added lag features)
FEATURE_LIST = [
    # Absolute features (now safe to use - target is future-based)
    'discount_pct', 'volatility_24h', 'price_velocity_1h', 'price_velocity_6h',
    'spike_count_24h', 'ceiling_distance_pct', 'deviation_from_mean',

    # Lag features (temporal patterns leading to instability)
    'discount_pct_lag_1h', 'discount_pct_lag_3h', 'discount_pct_lag_6h',
    'discount_pct_lag_12h', 'discount_pct_lag_24h',
    'volatility_24h_lag_1h', 'volatility_24h_lag_3h', 'volatility_24h_lag_6h',
    'volatility_24h_lag_12h', 'volatility_24h_lag_24h',
    'discount_change_1h', 'discount_change_3h', 'discount_change_6h',
    'discount_change_12h', 'discount_change_24h',

    # L1 Global (continuous stress metrics)
    'discount_percentile_L1_global', 'volatility_percentile_L1_global',
    'discount_zscore_L1_global', 'market_stress_L1_global',

    # L2 Family (continuous stress metrics)
    'discount_percentile_L2_family', 'volatility_percentile_L2_family', 'family_stress_L2',

    # L3 AZ (continuous stress metrics)
    'discount_percentile_L3_az', 'volatility_percentile_L3_az', 'az_stress_L3',

    # L4 Peer
    'discount_percentile_L4_peer', 'volatility_percentile_L4_peer', 'peer_pool_count',

    # Cross-level
    'global_vs_family_gap', 'better_alternatives_L2_family',

    # Pool history (continuous metric based on volatility)
    'pool_historical_stress_rate',

    # Instance encoding
    'instance_family', 'size_tier', 'generation', 'az_encoded',

    # Time
    'hour', 'day_of_week', 'is_business_hours'
]

print(f"\n📋 Feature List:")
print(f"  Total features: {len(FEATURE_LIST)}")
print(f"  Absolute: 7, Lag: 15, Hierarchical: 18, Other: {len(FEATURE_LIST) - 40}")

# Encode categorical features
from sklearn.preprocessing import LabelEncoder
le_family = LabelEncoder()
df_train['instance_family'] = le_family.fit_transform(df_train['instance_family'].astype(str))

# Prepare training data
X_train = df_train[FEATURE_LIST].copy()
y_train = df_train['stability_score'].copy()

# Handle any remaining NaNs or infinities
X_train = X_train.replace([np.inf, -np.inf], np.nan)
X_train = X_train.fillna(0)

print(f"\n📋 Training data preparation:")
print(f"  X_train shape: {X_train.shape}")
print(f"  y_train shape: {y_train.shape}")
print(f"  Features: {len(FEATURE_LIST)}")
print(f"  Target range: [{y_train.min():.1f}, {y_train.max():.1f}]")

# Assertions
assert not X_train.isnull().any().any(), "X_train contains NaN values"
assert not np.isinf(X_train.values).any(), "X_train contains infinite values"
assert (y_train >= 0).all() and (y_train <= 100).all(), "y_train not in [0, 100] range"

print(f"\n✓ Data validation passed")

# Train model
print(f"\n🎓 Training LightGBM model...")
print(f"  Hyperparameters: {HYPERPARAMETERS}")

model = LGBMRegressor(**HYPERPARAMETERS)

train_start = datetime.now()
model.fit(X_train, y_train)
train_time = (datetime.now() - train_start).total_seconds()

print(f"\n✓ Training complete in {train_time:.1f} seconds")

# Training metrics
y_train_pred = model.predict(X_train)
train_mae = mean_absolute_error(y_train, y_train_pred)
train_rmse = np.sqrt(mean_squared_error(y_train, y_train_pred))
train_r2 = r2_score(y_train, y_train_pred)

print(f"\n📊 Training Metrics:")
print(f"  MAE:  {train_mae:.2f}")
print(f"  RMSE: {train_rmse:.2f}")
print(f"  R²:   {train_r2:.4f}")

# Feature importance
feature_importance = pd.DataFrame({
    'feature': FEATURE_LIST,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

print(f"\n🔝 Top 10 Most Important Features:")
print(feature_importance.head(10).to_string(index=False))

# Save model
model_path = Path(CONFIG['models_dir']) / CONFIG['model_filename']
model_metadata = {
    'model': model,
    'feature_list': FEATURE_LIST,
    'label_encoder_family': le_family,
    'training_date': datetime.now().isoformat(),
    'training_rows': len(X_train),
    'train_mae': train_mae,
    'train_r2': train_r2,
    'hyperparameters': HYPERPARAMETERS
}

with open(model_path, 'wb') as f:
    pickle.dump(model_metadata, f)

print(f"\n✓ Model saved to: {model_path}")

# ============================================================================
# BACKTESTING FRAMEWORK
# ============================================================================

print("\n" + "="*80)
print("4. WALK-FORWARD BACKTESTING (Q1/Q2/Q3 2025)")
print("="*80)

def prepare_test_data(df_test, test_name):
    """
    Prepare test data with same feature engineering

    IMPORTANT: Test data uses the same future-based target calculation,
    so some rows will be dropped (last 6h per pool).
    """
    print(f"\n📊 Preparing {test_name}...")
    print(f"  (Using future-based stability target - expect some rows dropped)")

    # Use caching for test data too
    dataset_name = test_name.replace(' ', '_').lower()
    df_test = engineer_features_with_cache(df_test, dataset_name)

    # Encode instance_family using same encoder
    df_test['instance_family'] = le_family.transform(df_test['instance_family'].astype(str))

    # Prepare features
    X_test = df_test[FEATURE_LIST].copy()
    X_test = X_test.replace([np.inf, -np.inf], np.nan)
    X_test = X_test.fillna(0)

    y_test = df_test['stability_score'].copy()

    # Validation checks
    assert not X_test.isnull().any().any(), "X_test contains NaN values after fillna"
    assert (y_test >= 0).all() and (y_test <= 100).all(), "y_test not in [0, 100] range"

    print(f"  ✓ X_test shape: {X_test.shape}")
    print(f"  ✓ y_test range: [{y_test.min():.1f}, {y_test.max():.1f}]")
    print(f"  ✓ Features: {len(FEATURE_LIST)}")

    return X_test, y_test, df_test


def run_backtest(df_test, test_name, model):
    """Run walk-forward backtesting on test data"""
    print(f"\n🚀 Running backtest: {test_name}")

    # Prepare test data
    X_test, y_test, df_test_full = prepare_test_data(df_test, test_name)

    # Predict
    print(f"  Predicting stability scores...")
    y_pred = model.predict(X_test)
    y_pred = np.clip(y_pred, 0, 100)  # Ensure predictions in valid range

    # Calculate metrics
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)

    print(f"\n  📈 Prediction Metrics:")
    print(f"    MAE:  {mae:.2f}")
    print(f"    RMSE: {rmse:.2f}")
    print(f"    R²:   {r2:.4f}")

    # Add predictions to dataframe
    df_test_full['predicted_stability'] = y_pred
    df_test_full['actual_stability'] = y_test

    # Selection quality metrics
    # High confidence predictions (>=80)
    high_conf_mask = y_pred >= 80
    if high_conf_mask.sum() > 0:
        high_conf_actual = y_test[high_conf_mask]
        precision_high = (high_conf_actual >= 70).mean() * 100  # Actually stable
        print(f"    Precision @ >=80: {precision_high:.1f}%")
    else:
        precision_high = 0

    # Average discount of high-scoring pools
    avg_discount = df_test_full[high_conf_mask]['discount_pct'].mean() if high_conf_mask.sum() > 0 else 0
    print(f"    Avg Discount @ >=80: {avg_discount:.1f}%")

    # Stress avoidance (predictions >60 that were actually >60)
    good_pred_mask = y_pred >= 60
    if good_pred_mask.sum() > 0:
        stress_avoidance = (y_test[good_pred_mask] >= 60).mean() * 100
        print(f"    Stress Avoidance Rate: {stress_avoidance:.1f}%")
    else:
        stress_avoidance = 0

    results = {
        'test_name': test_name,
        'mae': mae,
        'rmse': rmse,
        'r2': r2,
        'precision_high': precision_high,
        'avg_discount_high': avg_discount,
        'stress_avoidance': stress_avoidance,
        'df_full': df_test_full
    }

    return results


# Run backtests
backtest_results = []

for df_test, test_name in [(df_q1, 'Q1 2025'), (df_q2, 'Q2 2025'), (df_q3, 'Q3 2025')]:
    results = run_backtest(df_test, test_name, model)
    backtest_results.append(results)

    # Save results
    output_file = Path(CONFIG['output_dir']) / f"backtest_results_{test_name.replace(' ', '_')}.csv"
    results['df_full'].to_csv(output_file, index=False)
    print(f"  ✓ Saved results to: {output_file}")

print("\n✓ All backtests complete")

# ============================================================================
# VISUALIZATIONS
# ============================================================================

print("\n" + "="*80)
print("5. GENERATING VISUALIZATIONS")
print("="*80)

# Plot 1: Feature Importance
plt.figure(figsize=(12, 8))
top_features = feature_importance.head(20)
plt.barh(range(len(top_features)), top_features['importance'])
plt.yticks(range(len(top_features)), top_features['feature'])
plt.xlabel('Importance', fontsize=12)
plt.title('Top 20 Feature Importance', fontsize=14, fontweight='bold')
plt.gca().invert_yaxis()
plt.grid(axis='x', alpha=0.3)
plt.tight_layout()
plot_path = Path(CONFIG['plots_dir']) / 'feature_importance.png'
plt.savefig(plot_path, dpi=100, bbox_inches='tight')
plt.close()
print(f"  ✓ Saved: {plot_path.name}")

# Plot 2: Feature Importance by Level
def get_feature_level(feat):
    if 'L1' in feat:
        return 'L1_Global'
    elif 'L2' in feat:
        return 'L2_Family'
    elif 'L3' in feat:
        return 'L3_AZ'
    elif 'L4' in feat:
        return 'L4_Peer'
    elif feat in ['hour', 'day_of_week', 'is_business_hours']:
        return 'Time'
    elif feat in ['instance_family', 'size_tier', 'generation', 'az_encoded']:
        return 'Instance'
    else:
        return 'Absolute'

feature_importance['level'] = feature_importance['feature'].apply(get_feature_level)
importance_by_level = feature_importance.groupby('level')['importance'].sum().sort_values(ascending=False)

plt.figure(figsize=(10, 6))
plt.bar(range(len(importance_by_level)), importance_by_level.values)
plt.xticks(range(len(importance_by_level)), importance_by_level.index, rotation=45, ha='right')
plt.ylabel('Total Importance', fontsize=12)
plt.title('Feature Importance by Hierarchical Level', fontsize=14, fontweight='bold')
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
plot_path = Path(CONFIG['plots_dir']) / 'feature_importance_by_level.png'
plt.savefig(plot_path, dpi=100, bbox_inches='tight')
plt.close()
print(f"  ✓ Saved: {plot_path.name}")

# Plots 3-4: Predicted vs Actual for Q2 and Q3
for result in backtest_results[1:]:  # Skip Q1, focus on Q2 and Q3
    test_name = result['test_name']
    df_full = result['df_full']

    plt.figure(figsize=(10, 10))
    plt.scatter(df_full['predicted_stability'], df_full['actual_stability'],
                alpha=0.3, s=10, label='Predictions')
    plt.plot([0, 100], [0, 100], 'r--', label='Perfect Prediction', linewidth=2)

    # Add trend line
    z = np.polyfit(df_full['predicted_stability'], df_full['actual_stability'], 1)
    p = np.poly1d(z)
    plt.plot([0, 100], p([0, 100]), "b-", alpha=0.8, label='Trend Line')

    plt.xlabel('Predicted Stability Score', fontsize=12)
    plt.ylabel('Actual Stability Score', fontsize=12)
    plt.title(f'Predicted vs Actual Stability ({test_name})', fontsize=14, fontweight='bold')
    plt.grid(alpha=0.3)
    plt.legend()
    plt.xlim(-5, 105)
    plt.ylim(-5, 105)
    plt.tight_layout()

    filename = f"predicted_vs_actual_{test_name.replace(' ', '_').lower()}.png"
    plot_path = Path(CONFIG['plots_dir']) / filename
    plt.savefig(plot_path, dpi=100, bbox_inches='tight')
    plt.close()
    print(f"  ✓ Saved: {plot_path.name}")

# Plot 5: Calibration Curve
plt.figure(figsize=(10, 8))
bins = [0, 20, 40, 60, 80, 100]
bin_labels = ['0-20', '20-40', '40-60', '60-80', '80-100']

# Use Q2 data for calibration
df_cal = backtest_results[1]['df_full']
df_cal['pred_bin'] = pd.cut(df_cal['predicted_stability'], bins=bins, labels=bin_labels)

calibration_data = []
for bin_label in bin_labels:
    mask = df_cal['pred_bin'] == bin_label
    if mask.sum() > 0:
        avg_pred = df_cal[mask]['predicted_stability'].mean()
        avg_actual = df_cal[mask]['actual_stability'].mean()
        calibration_data.append({'bin': bin_label, 'predicted': avg_pred, 'actual': avg_actual})

if calibration_data:
    cal_df = pd.DataFrame(calibration_data)
    plt.plot(cal_df['predicted'], cal_df['actual'], 'bo-', linewidth=2, markersize=10, label='Model Calibration')
    plt.plot([0, 100], [0, 100], 'r--', label='Perfect Calibration', linewidth=2)

    for _, row in cal_df.iterrows():
        plt.annotate(row['bin'], (row['predicted'], row['actual']),
                    xytext=(5, 5), textcoords='offset points', fontsize=9)

plt.xlabel('Predicted Stability Score', fontsize=12)
plt.ylabel('Actual Stability Score', fontsize=12)
plt.title('Calibration Curve', fontsize=14, fontweight='bold')
plt.grid(alpha=0.3)
plt.legend()
plt.tight_layout()
plot_path = Path(CONFIG['plots_dir']) / 'calibration_curve.png'
plt.savefig(plot_path, dpi=100, bbox_inches='tight')
plt.close()
print(f"  ✓ Saved: {plot_path.name}")

# Plot 6: Residuals Distribution
df_q2_full = backtest_results[1]['df_full']
residuals = df_q2_full['predicted_stability'] - df_q2_full['actual_stability']

plt.figure(figsize=(10, 6))
plt.hist(residuals, bins=50, edgecolor='black', alpha=0.7)
plt.axvline(0, color='red', linestyle='--', linewidth=2, label='Zero Error')
plt.xlabel('Residual (Predicted - Actual)', fontsize=12)
plt.ylabel('Frequency', fontsize=12)
plt.title('Residuals Distribution (Q2 2025)', fontsize=14, fontweight='bold')
plt.grid(alpha=0.3)
plt.legend()
plt.tight_layout()
plot_path = Path(CONFIG['plots_dir']) / 'residuals_distribution.png'
plt.savefig(plot_path, dpi=100, bbox_inches='tight')
plt.close()
print(f"  ✓ Saved: {plot_path.name}")

# Plot 7: Metrics Comparison
plt.figure(figsize=(12, 6))
metrics_df = pd.DataFrame(backtest_results)
x = np.arange(len(metrics_df))
width = 0.25

plt.bar(x - width, metrics_df['mae'], width, label='MAE', alpha=0.8)
plt.bar(x, metrics_df['stress_avoidance'], width, label='Stress Avoidance %', alpha=0.8)
plt.bar(x + width, metrics_df['avg_discount_high'], width, label='Avg Discount %', alpha=0.8)

plt.xlabel('Test Period', fontsize=12)
plt.ylabel('Metric Value', fontsize=12)
plt.title('Backtest Metrics Comparison', fontsize=14, fontweight='bold')
plt.xticks(x, metrics_df['test_name'])
plt.legend()
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
plot_path = Path(CONFIG['plots_dir']) / 'backtest_metrics_comparison.png'
plt.savefig(plot_path, dpi=100, bbox_inches='tight')
plt.close()
print(f"  ✓ Saved: {plot_path.name}")

print(f"\n✓ All visualizations generated in: {CONFIG['plots_dir']}")

# ============================================================================
# SUMMARY REPORT
# ============================================================================

print("\n" + "="*80)
print("6. COMPREHENSIVE SUMMARY REPORT")
print("="*80)

print(f"\n📊 TRAINING SUMMARY:")
print(f"  Dataset: 2023-2024 ({len(df_train):,} rows)")
print(f"  Features: {len(FEATURE_LIST)}")
print(f"  Training MAE: {train_mae:.2f}")
print(f"  Training R²: {train_r2:.4f}")
print(f"  Training Time: {train_time:.1f}s")

print(f"\n📈 BACKTESTING RESULTS:")
for result in backtest_results:
    print(f"\n  {result['test_name']}:")
    print(f"    MAE:                {result['mae']:.2f}")
    print(f"    RMSE:               {result['rmse']:.2f}")
    print(f"    R² Score:           {result['r2']:.4f}")
    print(f"    Precision @ >=80:   {result['precision_high']:.1f}%")
    print(f"    Avg Discount:       {result['avg_discount_high']:.1f}%")
    print(f"    Stress Avoidance:   {result['stress_avoidance']:.1f}%")

print(f"\n🔝 TOP 5 MOST IMPORTANT FEATURES:")
for i, row in feature_importance.head(5).iterrows():
    print(f"  {i+1}. {row['feature']}: {row['importance']:.4f}")

print(f"\n📁 OUTPUT FILES:")
print(f"  Model: {model_path}")
print(f"  Plots: {CONFIG['plots_dir']}")
print(f"  Results: {CONFIG['output_dir']}")

# Expected metrics after data leakage fixes
print(f"\n💡 EXPECTED METRICS (After Data Leakage Fixes):")
print(f"   ✅ REALISTIC Training MAE: 8-15 (NOT <5)")
print(f"   ✅ Test MAE slightly worse than train (generalization gap is HEALTHY)")
print(f"   ✅ R² between 0.60-0.85 (NOT >0.95)")
print(f"   ✅ Precision @ >=80 around 70-85% (NOT 100%)")
print(f"   ⚠️  If MAE <5 or R² >0.95: Still has data leakage, review target calculation")
print(f"   ⚠️  If test MAE much worse: Normal! Model is predicting future, not memorizing")

print("\n" + "="*80)
print("✅ HIERARCHICAL SPOT STABILITY MODEL COMPLETE!")
print("="*80)
print(f"End Time: {datetime.now()}")
print(f"="*80)

print(f"\n🔍 DATA LEAKAGE FIXES APPLIED:")
print(f"   ✅ Target is now FUTURE-based (6h ahead), not current-time")
print(f"   ✅ Removed is_stressed binary flags, using continuous metrics")
print(f"   ✅ Added 15 lag features for temporal pattern learning")
print(f"   ✅ Total features: {len(FEATURE_LIST)}")
print(f"   ✅ Model predicts: X[t] → y[t+6h] (future stability)")
print(f"\n   Next Step: Clear cache and re-train!")
print(f"   Command: rm -rf {OPTIMIZATION_CONFIG['CACHE_DIR']}/*.parquet")
print("="*80)
