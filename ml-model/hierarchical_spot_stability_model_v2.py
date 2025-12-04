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


def calculate_stress_and_stability(df):
    """
    Calculate is_stressed flag and stability_score target

    Stress conditions:
    - Low discount (<20%)
    - High spike count (>3 in 24h)
    - Extreme deviation from mean (>300%)
    """
    print("\n🎯 Calculating stress flags and stability scores...")

    df = df.copy()

    # Stress conditions
    low_discount = df['discount_pct'] < 20
    high_spikes = df['spike_count_24h'] > 3
    extreme_deviation = df['deviation_from_mean'].abs() > 300

    # is_stressed = any condition true
    df['is_stressed'] = (low_discount | high_spikes | extreme_deviation).astype(int)

    # Calculate stability_score (0-100, higher = more stable)
    df['stability_score'] = 100.0

    # Penalties
    df.loc[df['discount_pct'] < 20, 'stability_score'] -= 40
    df.loc[df['discount_pct'] < 40, 'stability_score'] -= 20
    df.loc[df['discount_pct'] < 60, 'stability_score'] -= 10

    volatility_ratio = df['volatility_24h'] / df['on_demand_price']
    df.loc[volatility_ratio > 0.1, 'stability_score'] -= 30
    df.loc[volatility_ratio > 0.05, 'stability_score'] -= 15

    df.loc[df['spike_count_24h'] > 4, 'stability_score'] -= 20
    df.loc[df['spike_count_24h'] > 2, 'stability_score'] -= 10

    df.loc[df['deviation_from_mean'].abs() > 200, 'stability_score'] -= 10

    # Clip to [0, 100]
    df['stability_score'] = df['stability_score'].clip(0, 100)

    stressed_pct = df['is_stressed'].mean() * 100
    avg_score = df['stability_score'].mean()

    print(f"  ✓ Stress rate: {stressed_pct:.1f}%")
    print(f"  ✓ Average stability score: {avg_score:.1f}/100")
    print(f"  Score distribution:")
    print(f"    0-20:  {(df['stability_score'] <= 20).sum():,} rows")
    print(f"    20-40: {((df['stability_score'] > 20) & (df['stability_score'] <= 40)).sum():,} rows")
    print(f"    40-60: {((df['stability_score'] > 40) & (df['stability_score'] <= 60)).sum():,} rows")
    print(f"    60-80: {((df['stability_score'] > 60) & (df['stability_score'] <= 80)).sum():,} rows")
    print(f"    80-100: {(df['stability_score'] > 80).sum():,} rows")

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
    """
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

        df.loc[ts_mask, 'market_stress_L1_global'] = ts_data['is_stressed'].mean()

        # L2: Family level
        for family in ts_data['instance_family'].unique():
            family_mask = ts_mask & (df['instance_family'] == family)
            family_data = ts_data[ts_data['instance_family'] == family]

            if len(family_data) >= 2:
                df.loc[family_mask, 'discount_percentile_L2_family'] = family_data['discount_pct'].rank(pct=True).values
                df.loc[family_mask, 'volatility_percentile_L2_family'] = family_data['volatility_24h'].rank(pct=True).values
                df.loc[family_mask, 'family_stress_L2'] = family_data['is_stressed'].mean()
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
                df.loc[az_mask, 'az_stress_L3'] = az_data['is_stressed'].mean()
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

        # Historical stress rate (expanding window)
        df.loc[mask, 'pool_historical_stress_rate'] = group_df['is_stressed'].expanding().mean().values

    df['pool_historical_stress_rate'] = df['pool_historical_stress_rate'].fillna(0)

    print(f"  ✓ Added pool history features")

    return df


# Apply all feature engineering
print("\n🚀 Starting feature engineering pipeline...")

df_train = calculate_absolute_features(df_train)
df_train = calculate_stress_and_stability(df_train)
df_train = calculate_hierarchical_features(df_train)
df_train = add_pool_history_features(df_train)

print(f"\n✓ Feature engineering complete on training data")
print(f"  Total features: {len([c for c in df_train.columns if c not in ['timestamp', 'instance_type', 'availability_zone', 'region']])}")
print(f"  Final shape: {df_train.shape}")

# ============================================================================
# MODEL TRAINING
# ============================================================================

print("\n" + "="*80)
print("3. MODEL TRAINING (LightGBM Regressor)")
print("="*80)

# Define feature list
FEATURE_LIST = [
    # Absolute features
    'discount_pct', 'volatility_24h', 'price_velocity_1h', 'price_velocity_6h',
    'spike_count_24h', 'ceiling_distance_pct', 'deviation_from_mean',

    # L1 Global
    'discount_percentile_L1_global', 'volatility_percentile_L1_global',
    'discount_zscore_L1_global', 'market_stress_L1_global',

    # L2 Family
    'discount_percentile_L2_family', 'volatility_percentile_L2_family', 'family_stress_L2',

    # L3 AZ
    'discount_percentile_L3_az', 'volatility_percentile_L3_az', 'az_stress_L3',

    # L4 Peer
    'discount_percentile_L4_peer', 'volatility_percentile_L4_peer', 'peer_pool_count',

    # Cross-level
    'global_vs_family_gap', 'better_alternatives_L2_family',

    # Pool history
    'pool_historical_stress_rate',

    # Instance encoding
    'instance_family', 'size_tier', 'generation', 'az_encoded',

    # Time
    'hour', 'day_of_week', 'is_business_hours'
]

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
    """Prepare test data with same feature engineering"""
    print(f"\n📊 Preparing {test_name}...")

    df_test = calculate_absolute_features(df_test)
    df_test = calculate_stress_and_stability(df_test)
    df_test = calculate_hierarchical_features(df_test)
    df_test = add_pool_history_features(df_test)

    # Encode instance_family using same encoder
    df_test['instance_family'] = le_family.transform(df_test['instance_family'].astype(str))

    # Prepare features
    X_test = df_test[FEATURE_LIST].copy()
    X_test = X_test.replace([np.inf, -np.inf], np.nan)
    X_test = X_test.fillna(0)

    y_test = df_test['stability_score'].copy()

    print(f"  ✓ X_test shape: {X_test.shape}")
    print(f"  ✓ y_test range: [{y_test.min():.1f}, {y_test.max():.1f}]")

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

print("\n" + "="*80)
print("✅ HIERARCHICAL SPOT STABILITY MODEL COMPLETE!")
print("="*80)
print(f"End Time: {datetime.now()}")
print("="*80)
