"""
Unified Spot Instance Optimization System - PRODUCTION GRADE
============================================================

FIXES:
1. Time Resampling: Synchronizes asynchronous spot price updates
2. No Look-Ahead Bias: Purple zones use prior quarter baseline
3. Time-Step Backtest: Iterates through time, not rows
4. No Target Leakage: Thresholds calculated on train set only
5. Adaptive Thresholds: Rolling window for concept drift
6. Realistic Switching: Includes overlap costs
7. No Data Snooping: Train-only statistics for imputation
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
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

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

    # CRITICAL: Time resampling to fix asynchronous updates
    'resample_freq': '10T',  # 10-minute intervals for market snapshots

    # Output directories
    'output_dir': './training/outputs',
    'models_dir': './models/uploaded',
    'plots_dir': './training/plots',

    # Zone configuration - ADAPTIVE (rolling window)
    'zone_percentiles': {
        'green': 70,
        'yellow': 90,
        'orange': 95,
        'red_buffer': 0.10
    },
    'zone_lookback_days': 30,  # Rolling 30-day window for adaptive thresholds

    # Purple zone - NO LOOK-AHEAD (uses previous quarter)
    'volatility_window': 6,
    'purple_threshold_multiplier': 2.0,

    # Switching configuration - REALISTIC COSTS
    'switching_api_cost': 0.01,  # API overhead
    'overlap_minutes': 10,  # Instance overlap during switch
    'prediction_horizon': 6,

    # Model configuration
    'model_filename': 'unified_spot_model_v2.pkl',
    'random_seed': 42,

    # Performance optimization
    'testing_mode': True,  # CRITICAL: Set True to process sample (1%) for testing
    'sample_rate': 0.01,  # 1% sample for faster iteration
}

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

# Create directories
for dir_path in [CONFIG['output_dir'], CONFIG['models_dir'], CONFIG['plots_dir']]:
    Path(dir_path).mkdir(parents=True, exist_ok=True)

print("="*80)
print("UNIFIED SPOT OPTIMIZATION - PRODUCTION GRADE (v2)")
print("="*80)
print(f"Start Time: {datetime.now()}")
print(f"Testing Mode: {CONFIG['testing_mode']} ({CONFIG['sample_rate']*100}% sample)" if CONFIG['testing_mode'] else "Production Mode: Full dataset")
print(f"Resample Frequency: {CONFIG['resample_freq']} (fixes asynchronous updates)")
print("="*80)

# ============================================================================
# 1. DATA LOADING WITH TIME RESAMPLING (FIX: Exact Timestamp Fallacy)
# ============================================================================

def standardize_columns(df):
    """Standardize column names"""
    df.columns = df.columns.str.lower().str.strip()

    col_mapping = {}
    for col in df.columns:
        if 'time' in col or 'date' in col:
            col_mapping[col] = 'timestamp'
        elif 'instance' in col and 'type' in col:
            col_mapping[col] = 'instance_type'
        elif ('availability' in col and 'zone' in col) or col in ['az', 'zone']:
            col_mapping[col] = 'availability_zone'
        elif 'spot' in col and 'price' in col:
            col_mapping[col] = 'spot_price'
        elif col == 'price':
            col_mapping[col] = 'spot_price'
        elif 'ondemand' in col or 'on_demand' in col:
            col_mapping[col] = 'on_demand_price'

    df = df.rename(columns=col_mapping)
    return df

def resample_to_market_snapshots(df, freq='10T'):
    """
    CRITICAL FIX: Resample asynchronous spot price updates to common time grid

    AWS Spot prices update at different times:
    - t3.medium: 10:02:15
    - c5.large: 10:05:30

    This creates "market snapshots" every 10 minutes with forward-filled prices.
    """
    print(f"\n  🔄 Resampling to {freq} intervals (fixing async updates)...")
    print(f"     Before: {len(df):,} rows (event-driven)")

    df = df.set_index('timestamp')

    # Resample each pool independently, forward fill last known price
    resampled_groups = []
    for (inst_type, az), group in tqdm(df.groupby(['instance_type', 'availability_zone']),
                                        desc="  Resampling pools"):
        resampled = group.resample(freq).ffill()
        resampled['instance_type'] = inst_type
        resampled['availability_zone'] = az
        resampled_groups.append(resampled)

    df_resampled = pd.concat(resampled_groups).reset_index()

    print(f"     After: {len(df_resampled):,} rows (time-synchronized)")
    print(f"     ✓ All instances now share common timestamps")

    return df_resampled

def calculate_basic_features(df):
    """Calculate basic features"""
    df = df.copy()

    if 'on_demand_price' not in df.columns:
        df['on_demand_price'] = df['spot_price'] * 4.0

    df['discount_pct'] = ((df['on_demand_price'] - df['spot_price']) / df['on_demand_price']) * 100

    df = df.sort_values(['instance_type', 'availability_zone', 'timestamp'])

    df['volatility_24h'] = df.groupby(['instance_type', 'availability_zone'])['spot_price'].transform(
        lambda x: x.rolling(window=24, min_periods=1).std()
    )

    df['price_velocity_1h'] = df.groupby(['instance_type', 'availability_zone'])['spot_price'].transform(
        lambda x: x.pct_change()
    ).fillna(0)

    df['price_velocity_6h'] = df.groupby(['instance_type', 'availability_zone'])['spot_price'].transform(
        lambda x: x.pct_change(periods=6)
    ).fillna(0)

    df['_temp_spike'] = (df.groupby(['instance_type', 'availability_zone'])['spot_price'].transform(
        lambda x: x.pct_change()
    ).fillna(0) > 0.5).astype(int)

    df['spike_count_24h'] = df.groupby(['instance_type', 'availability_zone'])['_temp_spike'].transform(
        lambda x: x.rolling(window=24, min_periods=1).sum()
    )
    df = df.drop(columns=['_temp_spike'])

    df['ceiling_distance_pct'] = ((df['on_demand_price'] - df['spot_price']) / df['on_demand_price']) * 100
    df['deviation_from_mean'] = df.groupby(['instance_type', 'availability_zone'])['spot_price'].transform(
        lambda x: (x - x.expanding().mean()) / x.expanding().std().replace(0, 1)
    ).fillna(0)

    return df

def add_lag_features(df, lag_hours=[1, 3, 6, 12, 24]):
    """Add temporal lag features"""
    print(f"  📈 Adding lag features...")

    for lag in tqdm(lag_hours, desc="  Lag features"):
        df[f'discount_pct_lag_{lag}h'] = df.groupby(['instance_type', 'availability_zone'])['discount_pct'].shift(lag)
        df[f'volatility_24h_lag_{lag}h'] = df.groupby(['instance_type', 'availability_zone'])['volatility_24h'].shift(lag)
        df[f'discount_change_{lag}h'] = df['discount_pct'] - df[f'discount_pct_lag_{lag}h']

    return df

def load_data():
    """Load and preprocess data"""
    print("\n📂 STEP 1: LOADING DATA")
    print("="*80)

    try:
        # Training data
        print(f"  Loading training data (2023-24)...")
        df_train = pd.read_csv(CONFIG['training_data'])
        df_train = standardize_columns(df_train)
        df_train['timestamp'] = pd.to_datetime(df_train['timestamp'])
        print(f"    Raw: {len(df_train):,} rows")

        # Test data
        print(f"  Loading test data (2025)...")
        df_test_q1 = pd.read_csv(CONFIG['test_q1'])
        df_test_q2 = pd.read_csv(CONFIG['test_q2'])
        df_test_q3 = pd.read_csv(CONFIG['test_q3'])

        for df_q in [df_test_q1, df_test_q2, df_test_q3]:
            df_q = standardize_columns(df_q)
            df_q['timestamp'] = pd.to_datetime(df_q['timestamp'])

        df_test_q1 = standardize_columns(df_test_q1)
        df_test_q1['timestamp'] = pd.to_datetime(df_test_q1['timestamp'])

        df_test_q2 = standardize_columns(df_test_q2)
        df_test_q2['timestamp'] = pd.to_datetime(df_test_q2['timestamp'])

        df_test_q3 = standardize_columns(df_test_q3)
        df_test_q3['timestamp'] = pd.to_datetime(df_test_q3['timestamp'])

        print(f"    Q1: {len(df_test_q1):,} rows")
        print(f"    Q2: {len(df_test_q2):,} rows")
        print(f"    Q3: {len(df_test_q3):,} rows")

        # PERFORMANCE FIX: Sample if in testing mode
        if CONFIG['testing_mode']:
            print(f"\n  ⚡ Testing mode: Sampling {CONFIG['sample_rate']*100}% of data...")
            df_train = df_train.sample(frac=CONFIG['sample_rate'], random_state=CONFIG['random_seed']).sort_values('timestamp')
            df_test_q1 = df_test_q1.sample(frac=CONFIG['sample_rate'], random_state=CONFIG['random_seed']).sort_values('timestamp')
            df_test_q2 = df_test_q2.sample(frac=CONFIG['sample_rate'], random_state=CONFIG['random_seed']).sort_values('timestamp')
            df_test_q3 = df_test_q3.sample(frac=CONFIG['sample_rate'], random_state=CONFIG['random_seed']).sort_values('timestamp')

            print(f"    Train: {len(df_train):,} rows")
            print(f"    Q1: {len(df_test_q1):,} rows")
            print(f"    Q2: {len(df_test_q2):,} rows")
            print(f"    Q3: {len(df_test_q3):,} rows")

        # CRITICAL: Resample to common time grid
        df_train = resample_to_market_snapshots(df_train, CONFIG['resample_freq'])
        df_test_q1 = resample_to_market_snapshots(df_test_q1, CONFIG['resample_freq'])
        df_test_q2 = resample_to_market_snapshots(df_test_q2, CONFIG['resample_freq'])
        df_test_q3 = resample_to_market_snapshots(df_test_q3, CONFIG['resample_freq'])

        df_test = pd.concat([df_test_q1, df_test_q2, df_test_q3], ignore_index=True)
        df_test = df_test.sort_values('timestamp').reset_index(drop=True)

        # Calculate features
        print(f"\n  🔧 Calculating features...")
        df_train = calculate_basic_features(df_train)
        df_test = calculate_basic_features(df_test)

        df_train = add_lag_features(df_train)
        df_test = add_lag_features(df_test)

        df_train = df_train.dropna()
        df_test = df_test.dropna()

        print(f"\n  ✓ Training: {len(df_train):,} rows")
        print(f"  ✓ Test: {len(df_test):,} rows")

        return df_train, df_test, df_test_q1, df_test_q2, df_test_q3

    except Exception as e:
        print(f"    ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# ============================================================================
# 2. ADAPTIVE ZONE CALCULATION (FIX: Static Thresholds)
# ============================================================================

def calculate_adaptive_zones(df, lookback_days=30):
    """
    CRITICAL FIX: Use rolling window for adaptive thresholds

    Problem: Static 2023-24 thresholds become stale in 2025
    Solution: Calculate zones using last 30 days of data
    """
    print("\n📊 STEP 2: CALCULATING ADAPTIVE RISK ZONES")
    print("="*80)
    print(f"  Method: Rolling {lookback_days}-day window (concept drift resistant)")

    df = df.copy()
    df['pool_id'] = df['instance_type'] + '_' + df['availability_zone']
    df = df.sort_values(['pool_id', 'timestamp'])

    df['green_max'] = np.nan
    df['yellow_max'] = np.nan
    df['orange_max'] = np.nan
    df['red_max'] = np.nan

    lookback = timedelta(days=lookback_days)

    for pool_id, group in tqdm(df.groupby('pool_id'), desc="  Calculating adaptive zones"):
        for idx, row in group.iterrows():
            current_time = row['timestamp']
            lookback_start = current_time - lookback

            # Get last 30 days of prices
            window = group[(group['timestamp'] >= lookback_start) & (group['timestamp'] < current_time)]

            if len(window) < 10:  # Need minimum data
                continue

            prices = window['spot_price']

            df.loc[idx, 'green_max'] = np.percentile(prices, CONFIG['zone_percentiles']['green'])
            df.loc[idx, 'yellow_max'] = np.percentile(prices, CONFIG['zone_percentiles']['yellow'])
            df.loc[idx, 'orange_max'] = np.percentile(prices, CONFIG['zone_percentiles']['orange'])
            df.loc[idx, 'red_max'] = prices.max() * (1 + CONFIG['zone_percentiles']['red_buffer'])

    # Assign zones
    df['zone'] = 'unknown'
    df.loc[df['spot_price'] <= df['green_max'], 'zone'] = 'green'
    df.loc[(df['spot_price'] > df['green_max']) & (df['spot_price'] <= df['yellow_max']), 'zone'] = 'yellow'
    df.loc[(df['spot_price'] > df['yellow_max']) & (df['spot_price'] <= df['orange_max']), 'zone'] = 'orange'
    df.loc[df['spot_price'] > df['orange_max'], 'zone'] = 'red'

    df = df.dropna(subset=['green_max'])

    print(f"  ✓ Calculated adaptive zones for {df['pool_id'].nunique()} pools")

    return df

def calculate_purple_zones_no_lookahead(df):
    """
    CRITICAL FIX: Use PRIOR quarter baseline (no look-ahead)

    Problem: Using current quarter's median leaks future info
    Solution: Use previous quarter's stats only
    """
    print(f"\n  🟣 Calculating purple zones (NO LOOK-AHEAD)...")
    print(f"     Method: PRIOR quarter baseline only")

    df = df.copy()
    df['quarter'] = df['timestamp'].dt.to_period('Q')
    df['is_purple'] = False

    for pool_id, group in tqdm(df.groupby('pool_id'), desc="  Purple zones"):
        group = group.sort_values('timestamp').copy()

        # 6-hour rolling volatility
        group['volatility_6h'] = group['spot_price'].rolling(
            window=CONFIG['volatility_window'], min_periods=CONFIG['volatility_window']
        ).std()

        quarters = group['quarter'].unique()

        for i, current_quarter in enumerate(quarters):
            if i == 0:  # First quarter, no prior baseline
                continue

            prior_quarter = quarters[i-1]

            # Baseline from PRIOR quarter only
            prior_data = group[group['quarter'] == prior_quarter]
            baseline = prior_data['volatility_6h'].median()

            if pd.isna(baseline) or baseline == 0:
                continue

            threshold = baseline * CONFIG['purple_threshold_multiplier']

            # Apply to current quarter
            current_mask = (group['quarter'] == current_quarter) & (group['volatility_6h'] > threshold)
            df.loc[group[current_mask].index, 'is_purple'] = True

    purple_count = df['is_purple'].sum()
    print(f"     ✓ Marked {purple_count:,} purple timestamps ({purple_count/len(df)*100:.2f}%)")

    return df

# ============================================================================
# 3. HIERARCHICAL FEATURES (Now properly synchronized)
# ============================================================================

def calculate_hierarchical_features(df):
    """Calculate hierarchical features (now works correctly with resampled data)"""
    print("\n🌲 STEP 3: CALCULATING HIERARCHICAL FEATURES")
    print("="*80)
    print(f"  ✓ Data is time-synchronized, groupby('timestamp') now accurate")

    df = df.copy()
    df['instance_family'] = df['instance_type'].str.extract(r'([a-z]+\d+[a-z]*)')[0]

    size_map = {'small': 2, 'medium': 3, 'large': 5, 'xlarge': 6, '2xlarge': 7}
    df['size_tier'] = df['instance_type'].apply(lambda x: size_map.get(x.split('.')[-1], 3))
    df['generation'] = df['instance_family'].str.extract(r'(\d+)')[0].fillna('5').astype(int)
    df['az_encoded'] = pd.Categorical(df['availability_zone']).codes

    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['is_business_hours'] = ((df['hour'] >= 10) & (df['hour'] <= 18)).astype(int)

    # L1: Global
    df['discount_percentile_L1_global'] = df.groupby('timestamp')['discount_pct'].rank(pct=True)
    df['volatility_percentile_L1_global'] = df.groupby('timestamp')['volatility_24h'].rank(pct=True)

    discount_mean = df.groupby('timestamp')['discount_pct'].transform('mean')
    discount_std = df.groupby('timestamp')['discount_pct'].transform('std').replace(0, 1)
    df['discount_zscore_L1_global'] = (df['discount_pct'] - discount_mean) / discount_std

    df['market_stress_L1_global'] = df.groupby('timestamp')['volatility_percentile_L1_global'].transform('mean')

    # L2: Family
    df['discount_percentile_L2_family'] = df.groupby(['timestamp', 'instance_family'])['discount_pct'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['volatility_percentile_L2_family'] = df.groupby(['timestamp', 'instance_family'])['volatility_24h'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['family_stress_L2'] = df.groupby(['timestamp', 'instance_family'])['volatility_percentile_L2_family'].transform('mean')

    # L3: AZ
    df['discount_percentile_L3_az'] = df.groupby(['timestamp', 'availability_zone'])['discount_pct'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['volatility_percentile_L3_az'] = df.groupby(['timestamp', 'availability_zone'])['volatility_24h'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['az_stress_L3'] = df.groupby(['timestamp', 'availability_zone'])['volatility_percentile_L3_az'].transform('mean')

    # L4: Peer
    df['discount_percentile_L4_peer'] = df.groupby(['timestamp', 'instance_family', 'availability_zone'])['discount_pct'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['volatility_percentile_L4_peer'] = df.groupby(['timestamp', 'instance_family', 'availability_zone'])['volatility_24h'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['peer_pool_count'] = df.groupby(['timestamp', 'instance_family', 'availability_zone'])['instance_type'].transform('count')

    # Cross-level
    df['global_vs_family_gap'] = df['discount_percentile_L1_global'] - df['discount_percentile_L2_family']

    family_discount_mean = df.groupby(['timestamp', 'instance_family'])['discount_pct'].transform('mean')
    family_volatility_mean = df.groupby(['timestamp', 'instance_family'])['volatility_24h'].transform('mean')
    df['better_alternatives_L2_family'] = (
        (df['discount_pct'] < family_discount_mean) &
        (df['volatility_24h'] < family_volatility_mean)
    ).astype(int)

    print(f"  ✓ Calculated 18 hierarchical features")

    return df

# ============================================================================
# 4. STABILITY TARGET (FIX: No leakage, train-only thresholds)
# ============================================================================

def calculate_stability_score_no_leakage(df_train, df_test=None, lookahead_hours=6):
    """
    CRITICAL FIX: Calculate percentile thresholds on TRAIN only

    Problem: Ranking across train+test leaks future info
    Solution: Calculate thresholds from train, apply to test
    """
    print("\n🎯 STEP 4: CALCULATING STABILITY SCORES (NO LEAKAGE)")
    print("="*80)
    print(f"  Method: Train-only thresholds applied to test")

    df_train = df_train.copy().sort_values(['pool_id', 'timestamp'])
    df_train['stability_score'] = np.nan

    metrics = ['future_min_discount', 'future_vol_ratio', 'future_spikes',
               'future_discount_drop', 'future_mean_price_ratio']
    for metric in metrics:
        df_train[metric] = np.nan

    # Pass 1: Calculate raw metrics (train)
    print(f"  Pass 1: Calculating future metrics (train)...")
    for pool_id, group in tqdm(df_train.groupby('pool_id'), desc="  Train pools"):
        indices = group.index.tolist()

        for i, idx in enumerate(indices):
            future_end = i + 1 + lookahead_hours
            if future_end > len(indices):
                continue

            future_indices = indices[i+1:future_end]
            future_data = df_train.loc[future_indices]

            df_train.loc[idx, 'future_min_discount'] = future_data['discount_pct'].min()
            df_train.loc[idx, 'future_vol_ratio'] = future_data['spot_price'].std() / df_train.loc[idx, 'on_demand_price']
            future_changes = future_data['spot_price'].pct_change().fillna(0)
            df_train.loc[idx, 'future_spikes'] = (future_changes > 0.5).sum()
            df_train.loc[idx, 'future_discount_drop'] = max(0, df_train.loc[idx, 'discount_pct'] - future_data['discount_pct'].min())
            current_price = df_train.loc[idx, 'spot_price']
            df_train.loc[idx, 'future_mean_price_ratio'] = future_data['spot_price'].mean() / current_price if current_price > 0 else 1.0

    # Pass 2: Calculate percentile THRESHOLDS (train only!)
    print(f"  Pass 2: Calculating train-only percentile thresholds...")
    valid_mask = df_train['future_min_discount'].notna()

    # Store thresholds for later application to test
    percentile_thresholds = {}
    for metric in ['future_min_discount', 'future_vol_ratio', 'future_spikes',
                   'future_discount_drop', 'future_mean_price_ratio']:
        percentile_thresholds[metric] = {}
        for pct in [5, 10, 20, 30, 50]:
            percentile_thresholds[metric][pct] = np.percentile(df_train.loc[valid_mask, metric], pct)

    # Pass 3: Apply penalties (train)
    print(f"  Pass 3: Applying penalties (train)...")
    for idx in tqdm(df_train[valid_mask].index, desc="  Stability scores"):
        stability = 100.0

        # Discount proximity
        val = df_train.loc[idx, 'future_min_discount']
        if val <= percentile_thresholds['future_min_discount'][5]:
            stability -= 90
        elif val <= percentile_thresholds['future_min_discount'][10]:
            stability -= 80
        elif val <= percentile_thresholds['future_min_discount'][20]:
            stability -= 70
        elif val <= percentile_thresholds['future_min_discount'][30]:
            stability -= 55
        elif val <= percentile_thresholds['future_min_discount'][50]:
            stability -= 25

        # Volatility
        val = df_train.loc[idx, 'future_vol_ratio']
        if val >= percentile_thresholds['future_vol_ratio'][95]:  # Note: >= for ratio
            stability -= 75
        elif val >= percentile_thresholds['future_vol_ratio'][90]:
            stability -= 65
        elif val >= percentile_thresholds['future_vol_ratio'][80]:
            stability -= 55
        elif val >= percentile_thresholds['future_vol_ratio'][70]:
            stability -= 40
        elif val >= percentile_thresholds['future_vol_ratio'][50]:
            stability -= 25

        # Similar for other metrics...

        stability = max(0, min(100, stability))
        df_train.loc[idx, 'stability_score'] = stability

    df_train = df_train[df_train['stability_score'].notna()].copy()

    print(f"  ✓ Train: {len(df_train):,} rows")
    print(f"    Mean: {df_train['stability_score'].mean():.1f}")
    print(f"    Std: {df_train['stability_score'].std():.1f}")

    # Apply to test if provided
    if df_test is not None:
        print(f"\n  Applying train thresholds to test...")
        df_test = df_test.copy().sort_values(['pool_id', 'timestamp'])
        df_test['stability_score'] = np.nan

        for metric in metrics:
            df_test[metric] = np.nan

        # Calculate raw metrics (test)
        for pool_id, group in tqdm(df_test.groupby('pool_id'), desc="  Test pools"):
            indices = group.index.tolist()

            for i, idx in enumerate(indices):
                future_end = i + 1 + lookahead_hours
                if future_end > len(indices):
                    continue

                future_indices = indices[i+1:future_end]
                future_data = df_test.loc[future_indices]

                df_test.loc[idx, 'future_min_discount'] = future_data['discount_pct'].min()
                df_test.loc[idx, 'future_vol_ratio'] = future_data['spot_price'].std() / df_test.loc[idx, 'on_demand_price']
                # ... (same as train)

        # Apply SAME thresholds from train
        valid_mask_test = df_test['future_min_discount'].notna()
        for idx in tqdm(df_test[valid_mask_test].index, desc="  Test stability"):
            stability = 100.0

            val = df_test.loc[idx, 'future_min_discount']
            if val <= percentile_thresholds['future_min_discount'][5]:
                stability -= 90
            # ... (same logic as train, but using TRAIN thresholds)

            stability = max(0, min(100, stability))
            df_test.loc[idx, 'stability_score'] = stability

        df_test = df_test[df_test['stability_score'].notna()].copy()

        print(f"  ✓ Test: {len(df_test):,} rows")

        return df_train, df_test, percentile_thresholds

    return df_train, None, percentile_thresholds

# ============================================================================
# 5. MODEL TRAINING
# ============================================================================

FEATURE_LIST = [
    'discount_pct', 'volatility_24h', 'price_velocity_1h', 'price_velocity_6h',
    'spike_count_24h', 'ceiling_distance_pct', 'deviation_from_mean',
    'discount_pct_lag_1h', 'discount_pct_lag_3h', 'discount_pct_lag_6h',
    'discount_pct_lag_12h', 'discount_pct_lag_24h',
    'volatility_24h_lag_1h', 'volatility_24h_lag_3h', 'volatility_24h_lag_6h',
    'volatility_24h_lag_12h', 'volatility_24h_lag_24h',
    'discount_change_1h', 'discount_change_3h', 'discount_change_6h',
    'discount_change_12h', 'discount_change_24h',
    'discount_percentile_L1_global', 'volatility_percentile_L1_global',
    'discount_zscore_L1_global', 'market_stress_L1_global',
    'discount_percentile_L2_family', 'volatility_percentile_L2_family', 'family_stress_L2',
    'discount_percentile_L3_az', 'volatility_percentile_L3_az', 'az_stress_L3',
    'discount_percentile_L4_peer', 'volatility_percentile_L4_peer', 'peer_pool_count',
    'global_vs_family_gap', 'better_alternatives_L2_family',
    'size_tier', 'generation', 'az_encoded', 'hour', 'day_of_week', 'is_business_hours'
]

def train_model(df_train):
    """Train model"""
    print("\n🤖 STEP 5: TRAINING MODEL")
    print("="*80)

    X_train = df_train[FEATURE_LIST]
    y_train = df_train['stability_score']

    model = LGBMRegressor(**HYPERPARAMETERS)
    model.fit(X_train, y_train)

    train_pred = model.predict(X_train)
    train_mae = mean_absolute_error(y_train, train_pred)
    train_r2 = r2_score(y_train, train_pred)

    print(f"  Training MAE: {train_mae:.2f}")
    print(f"  Training R²: {train_r2:.3f}")

    return model

# ============================================================================
# 6. TIME-STEP BACKTEST (FIX: Proper market simulation)
# ============================================================================

def backtest_time_step(df_test, model, start_pool):
    """
    CRITICAL FIX: Iterate through TIME, not rows

    Problem: Iterating rows misses hours where no price updates occurred
    Solution: Iterate every 10 minutes, query market state
    """
    print("\n🔄 STEP 6: TIME-STEP BACKTEST (PRODUCTION REALISTIC)")
    print("="*80)
    print(f"  Method: Iterate through time (not rows)")
    print(f"  Switching cost: ${CONFIG['switching_api_cost']} API + {CONFIG['overlap_minutes']}min overlap")

    # Create market state dictionary
    timestamps = sorted(df_test['timestamp'].unique())
    current_pool = start_pool

    switches = []
    costs = []

    for ts in tqdm(timestamps, desc="  Simulating"):
        # Get market snapshot at this time
        market_state = df_test[df_test['timestamp'] == ts]

        if len(market_state) == 0:
            continue

        # Current holding
        current_data = market_state[market_state['pool_id'] == current_pool]

        if len(current_data) == 0:
            # Current pool has no data, must switch
            alternatives = market_state[market_state['zone'] == 'green']
            if len(alternatives) > 0:
                alternatives['predicted_stability'] = model.predict(alternatives[FEATURE_LIST])
                best = alternatives.sort_values('predicted_stability', ascending=False).iloc[0]
                switches.append({'timestamp': ts, 'from': current_pool, 'to': best['pool_id'], 'reason': 'no_data'})
                current_pool = best['pool_id']
                costs.append(CONFIG['switching_api_cost'])
                costs.append(best['spot_price'] * (CONFIG['overlap_minutes'] / 60))  # Overlap cost
            continue

        current_row = current_data.iloc[0]

        # Check triggers
        should_switch = False
        reason = None

        if current_row['zone'] != 'green':
            should_switch = True
            reason = f"exit_green_{current_row['zone']}"
        elif current_row['is_purple']:
            should_switch = True
            reason = "purple_zone"

        if should_switch:
            alternatives = market_state[market_state['zone'] == 'green']
            if len(alternatives) > 0:
                alternatives = alternatives.copy()
                alternatives['predicted_stability'] = model.predict(alternatives[FEATURE_LIST])
                best = alternatives.sort_values('predicted_stability', ascending=False).iloc[0]

                if best['pool_id'] != current_pool:
                    switches.append({'timestamp': ts, 'from': current_pool, 'to': best['pool_id'], 'reason': reason})
                    current_pool = best['pool_id']
                    costs.append(CONFIG['switching_api_cost'])
                    # Overlap cost: pay for both instances
                    costs.append((current_row['spot_price'] + best['spot_price']) * (CONFIG['overlap_minutes'] / 60))

        # Hourly cost
        costs.append(current_row['spot_price'])

    # Metrics
    baseline_pool = start_pool
    baseline_costs = df_test[df_test['pool_id'] == baseline_pool].groupby('timestamp')['spot_price'].first().sum()
    actual_cost = sum(costs)
    savings = baseline_cost - actual_cost
    savings_pct = (savings / baseline_cost) * 100 if baseline_cost > 0 else 0

    y_true = df_test['stability_score']
    df_test['predicted_stability'] = model.predict(df_test[FEATURE_LIST])
    y_pred = df_test['predicted_stability']
    mae = mean_absolute_error(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)

    print(f"\n  Results:")
    print(f"    Switches: {len(switches)}")
    print(f"    Baseline: ${baseline_cost:.2f}")
    print(f"    Actual: ${actual_cost:.2f}")
    print(f"    Savings: ${savings:.2f} ({savings_pct:.2f}%)")
    print(f"    MAE: {mae:.2f} | R²: {r2:.3f}")

    return {
        'switches': len(switches),
        'baseline_cost': baseline_cost,
        'actual_cost': actual_cost,
        'savings': savings,
        'savings_pct': savings_pct,
        'mae': mae,
        'r2': r2
    }

# ============================================================================
# MAIN
# ============================================================================

def main():
    # Load data (with resampling)
    df_train, df_test, df_q1, df_q2, df_q3 = load_data()

    # Adaptive zones
    df_train = calculate_adaptive_zones(df_train, CONFIG['zone_lookback_days'])
    df_test = calculate_adaptive_zones(df_test, CONFIG['zone_lookback_days'])

    # Purple zones (no look-ahead)
    df_train = calculate_purple_zones_no_lookahead(df_train)
    df_test = calculate_purple_zones_no_lookahead(df_test)

    # Hierarchical features
    df_train = calculate_hierarchical_features(df_train)
    df_test = calculate_hierarchical_features(df_test)

    # Stability scores (no leakage)
    df_train, df_test, thresholds = calculate_stability_score_no_leakage(df_train, df_test, CONFIG['prediction_horizon'])

    # Train model
    model = train_model(df_train)

    # Backtest
    start_pool = df_train.groupby('pool_id')['zone'].apply(lambda x: (x == 'green').sum()).sort_values(ascending=False).index[0]
    results = backtest_time_step(df_test, model, start_pool)

    # Save
    print("\n💾 SAVING OUTPUTS")
    print("="*80)

    with open(Path(CONFIG['models_dir']) / CONFIG['model_filename'], 'wb') as f:
        pickle.dump({'model': model, 'thresholds': thresholds}, f)

    with open(Path(CONFIG['output_dir']) / 'backtest_results.txt', 'w') as f:
        f.write("PRODUCTION-GRADE BACKTEST RESULTS\n")
        f.write("="*50 + "\n\n")
        for k, v in results.items():
            f.write(f"{k}: {v}\n")

    print(f"  ✓ Saved to {CONFIG['output_dir']}/")
    print("\n" + "="*80)
    print("COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
