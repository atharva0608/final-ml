"""
Unified Spot Instance Optimization System
==========================================

Combines:
- Hierarchical stability prediction (percentile-based target)
- Zone-based risk assessment (Green/Yellow/Orange/Red/Purple)
- Smart switching with abnormality detection
- Comprehensive backtesting and visualization

Architecture:
1. Train on 2023-24 data (zones + hierarchical features + stability model)
2. Backtest on 2025 Q1/Q2/Q3 (walk-forward validation)
3. Smart switching with 3 triggers: zone exit, purple entry, abnormality
4. Comprehensive metrics: savings, MAE, R², precision, switching costs

Reference: AWS Spot Best Practices + Cast.AI Optimization
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

    # Output directories
    'output_dir': './training/outputs',
    'models_dir': './models/uploaded',
    'plots_dir': './training/plots',
    'zone_plots_dir': './training/plots/zones',

    # Zone configuration (AWS-aligned percentiles)
    'zone_percentiles': {
        'green': 70,   # P70 - AWS <5% interruption rate
        'yellow': 90,  # P90 - 95% CI lower bound
        'orange': 95,  # P95 - 95% CI upper bound
        'red_buffer': 0.10  # Max + 10% engineering margin
    },

    # Purple zone (volatility) - Cast.AI quarterly rebalancing
    'volatility_window': 6,  # 6-hour rolling window
    'quarterly_baseline': True,  # Seasonal patterns (not annual)
    'purple_threshold_multiplier': 2.0,  # 2x quarterly baseline

    # Switching configuration
    'switching_cost': 0.01,  # $0.01 per switch (API overhead)
    'prediction_horizon': 6,  # Predict 6 hours ahead

    # Model configuration
    'model_filename': 'unified_spot_model.pkl',
    'random_seed': 42,

    # Optimization
    'testing_mode': False,  # Set True for fast testing (10% data)
    'sample_rate': 0.1,
}

# LightGBM hyperparameters
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
for dir_path in [CONFIG['output_dir'], CONFIG['models_dir'], CONFIG['plots_dir'], CONFIG['zone_plots_dir']]:
    Path(dir_path).mkdir(parents=True, exist_ok=True)

print("="*80)
print("UNIFIED SPOT INSTANCE OPTIMIZATION SYSTEM")
print("="*80)
print(f"Start Time: {datetime.now()}")
print(f"Region: {CONFIG['region']}")
print(f"Instance Types: {', '.join(CONFIG['instance_types'])}")
print("="*80)

# ============================================================================
# 1. DATA LOADING & PREPROCESSING
# ============================================================================

def standardize_columns(df):
    """Standardize column names across different CSV formats"""
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
        elif 'discount' in col:
            col_mapping[col] = 'discount_pct'
        elif 'volatility' in col:
            col_mapping[col] = 'volatility_24h'
        elif 'velocity' in col:
            if '1h' in col or '1_h' in col:
                col_mapping[col] = 'price_velocity_1h'
            elif '6h' in col or '6_h' in col:
                col_mapping[col] = 'price_velocity_6h'
        elif 'spike' in col:
            col_mapping[col] = 'spike_count_24h'

    df = df.rename(columns=col_mapping)
    return df

def calculate_basic_features(df):
    """Calculate basic price-derived features"""
    df = df.copy()

    # On-demand price estimation if missing
    if 'on_demand_price' not in df.columns:
        df['on_demand_price'] = df['spot_price'] * 4.0
        print(f"    ⚠️  Estimated on_demand_price (spot_price × 4)")

    # Discount percentage
    if 'discount_pct' not in df.columns:
        df['discount_pct'] = ((df['on_demand_price'] - df['spot_price']) / df['on_demand_price']) * 100
        print(f"    ✓ Calculated discount_pct")

    df = df.sort_values(['instance_type', 'availability_zone', 'timestamp'])

    # Volatility (24-hour rolling std)
    if 'volatility_24h' not in df.columns:
        df['volatility_24h'] = df.groupby(['instance_type', 'availability_zone'])['spot_price'].transform(
            lambda x: x.rolling(window=24, min_periods=1).std()
        )
        print(f"    ✓ Calculated volatility_24h")

    # Price velocity
    if 'price_velocity_1h' not in df.columns:
        df['price_velocity_1h'] = df.groupby(['instance_type', 'availability_zone'])['spot_price'].transform(
            lambda x: x.pct_change()
        ).fillna(0)
        print(f"    ✓ Calculated price_velocity_1h")

    if 'price_velocity_6h' not in df.columns:
        df['price_velocity_6h'] = df.groupby(['instance_type', 'availability_zone'])['spot_price'].transform(
            lambda x: x.pct_change(periods=6)
        ).fillna(0)
        print(f"    ✓ Calculated price_velocity_6h")

    # Spike count
    if 'spike_count_24h' not in df.columns:
        df['_temp_spike'] = (df.groupby(['instance_type', 'availability_zone'])['spot_price'].transform(
            lambda x: x.pct_change()
        ).fillna(0) > 0.5).astype(int)

        df['spike_count_24h'] = df.groupby(['instance_type', 'availability_zone'])['_temp_spike'].transform(
            lambda x: x.rolling(window=24, min_periods=1).sum()
        )
        df = df.drop(columns=['_temp_spike'])
        print(f"    ✓ Calculated spike_count_24h")

    # Additional features for stability prediction
    df['ceiling_distance_pct'] = ((df['on_demand_price'] - df['spot_price']) / df['on_demand_price']) * 100
    df['deviation_from_mean'] = df.groupby(['instance_type', 'availability_zone'])['spot_price'].transform(
        lambda x: (x - x.expanding().mean()) / x.expanding().std().replace(0, 1)
    ).fillna(0)

    return df

def add_lag_features(df, lag_hours=[1, 3, 6, 12, 24]):
    """Add temporal lag features for pattern learning"""
    print(f"  📈 Adding lag features ({lag_hours})...")

    for lag in tqdm(lag_hours, desc="  Lag features"):
        df[f'discount_pct_lag_{lag}h'] = df.groupby(['instance_type', 'availability_zone'])['discount_pct'].shift(lag)
        df[f'volatility_24h_lag_{lag}h'] = df.groupby(['instance_type', 'availability_zone'])['volatility_24h'].shift(lag)
        df[f'discount_change_{lag}h'] = df['discount_pct'] - df[f'discount_pct_lag_{lag}h']

    return df

def load_data():
    """Load and preprocess training (2023-24) and test (2025) data"""
    print("\n📂 STEP 1: LOADING DATA")
    print("="*80)

    try:
        # Training data
        print(f"  Loading training data (2023-24)...")
        df_train = pd.read_csv(CONFIG['training_data'])
        df_train = standardize_columns(df_train)
        df_train['timestamp'] = pd.to_datetime(df_train['timestamp'])
        print(f"    ✓ Training: {len(df_train):,} rows")

        # Test data (Q1/Q2/Q3 2025)
        print(f"  Loading test data (2025 Q1/Q2/Q3)...")
        df_test_q1 = pd.read_csv(CONFIG['test_q1'])
        df_test_q1 = standardize_columns(df_test_q1)
        df_test_q1['timestamp'] = pd.to_datetime(df_test_q1['timestamp'])

        df_test_q2 = pd.read_csv(CONFIG['test_q2'])
        df_test_q2 = standardize_columns(df_test_q2)
        df_test_q2['timestamp'] = pd.to_datetime(df_test_q2['timestamp'])

        df_test_q3 = pd.read_csv(CONFIG['test_q3'])
        df_test_q3 = standardize_columns(df_test_q3)
        df_test_q3['timestamp'] = pd.to_datetime(df_test_q3['timestamp'])

        df_test = pd.concat([df_test_q1, df_test_q2, df_test_q3], ignore_index=True)
        df_test = df_test.sort_values('timestamp').reset_index(drop=True)

        print(f"    ✓ Test Q1: {len(df_test_q1):,} rows")
        print(f"    ✓ Test Q2: {len(df_test_q2):,} rows")
        print(f"    ✓ Test Q3: {len(df_test_q3):,} rows")
        print(f"    ✓ Total Test: {len(df_test):,} rows")

        # Calculate features
        print(f"\n  🔧 Calculating features...")
        df_train = calculate_basic_features(df_train)
        df_test = calculate_basic_features(df_test)

        df_train = add_lag_features(df_train)
        df_test = add_lag_features(df_test)

        # Drop NaN from lag features
        df_train = df_train.dropna()
        df_test = df_test.dropna()

        print(f"\n  ✓ Training: {len(df_train):,} rows (after feature engineering)")
        print(f"  ✓ Test: {len(df_test):,} rows (after feature engineering)")

        # Optional sampling for testing
        if CONFIG['testing_mode']:
            sample_rate = CONFIG['sample_rate']
            df_train = df_train.sample(frac=sample_rate, random_state=CONFIG['random_seed']).sort_values('timestamp')
            df_test = df_test.sample(frac=sample_rate, random_state=CONFIG['random_seed']).sort_values('timestamp')
            print(f"\n  ⚠️  Testing mode: Sampled {sample_rate*100}% of data")

        return df_train, df_test, df_test_q1, df_test_q2, df_test_q3

    except Exception as e:
        print(f"    ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# ============================================================================
# 2. ZONE CALCULATION (Pool-Specific + Quarterly Purple)
# ============================================================================

def calculate_pool_zones(df):
    """
    Calculate pool-specific risk zones based on AWS best practices

    Zones (Pool-Relative Percentiles):
    - Green (P70):  Normal operations, AWS <5% interruption
    - Yellow (P90): Elevated risk, Cast.AI manageable range
    - Orange (P95): High risk, statistical outlier threshold
    - Red (Max+10%): Critical capacity crunch + safety margin
    """
    print("\n📊 STEP 2: CALCULATING RISK ZONES")
    print("="*80)
    print(f"  Zone Methodology: Pool-relative percentiles (AWS-aligned)")
    print(f"  - Green (P70):  <5% AWS interruption rate")
    print(f"  - Yellow (P90): 95% CI lower bound")
    print(f"  - Orange (P95): Statistical outlier threshold")
    print(f"  - Red (Max+10%): Black swan event margin")

    zones = []

    for (inst_type, az), group in tqdm(df.groupby(['instance_type', 'availability_zone']),
                                        desc="  Calculating zones"):
        pool_id = f"{inst_type}_{az}"
        prices = group['spot_price']

        p70 = np.percentile(prices, CONFIG['zone_percentiles']['green'])
        p90 = np.percentile(prices, CONFIG['zone_percentiles']['yellow'])
        p95 = np.percentile(prices, CONFIG['zone_percentiles']['orange'])
        red = prices.max() * (1 + CONFIG['zone_percentiles']['red_buffer'])

        zones.append({
            'pool_id': pool_id,
            'instance_type': inst_type,
            'availability_zone': az,
            'green_max': p70,
            'yellow_max': p90,
            'orange_max': p95,
            'red_max': red,
            'mean_price': prices.mean(),
            'std_price': prices.std()
        })

    zones_df = pd.DataFrame(zones)
    print(f"\n  ✓ Calculated zones for {len(zones_df)} pools")

    return zones_df

def calculate_quarterly_purple_zones(df):
    """
    Calculate purple zones (volatility spikes) quarterly

    Cast.AI Insight: Quarterly baseline captures seasonal patterns
    - Q1: Post-holiday normalization
    - Q2: Tax season, spring traffic
    - Q3: Summer peak, infrastructure changes
    - Q4: Holiday surge, capacity pressure
    """
    print(f"\n  🟣 Calculating purple zones (quarterly volatility)...")
    print(f"     Window: {CONFIG['volatility_window']}-hour rolling volatility")
    print(f"     Threshold: {CONFIG['purple_threshold_multiplier']}x quarterly median")

    df = df.copy()
    df['quarter'] = df['timestamp'].dt.to_period('Q')

    purple_zones = []

    for (inst_type, az), group in tqdm(df.groupby(['instance_type', 'availability_zone']),
                                        desc="  Purple zones"):
        pool_id = f"{inst_type}_{az}"
        group = group.sort_values('timestamp').reset_index(drop=True)

        # 6-hour rolling volatility
        group['volatility_6h'] = group['spot_price'].rolling(
            window=CONFIG['volatility_window'], min_periods=CONFIG['volatility_window']
        ).std()

        # Quarterly baseline
        for quarter, qgroup in group.groupby('quarter'):
            baseline = qgroup['volatility_6h'].median()
            threshold = baseline * CONFIG['purple_threshold_multiplier']

            purple_mask = (group['quarter'] == quarter) & (group['volatility_6h'] > threshold)

            if purple_mask.sum() > 0:
                indices = group[purple_mask].index.tolist()

                # Group consecutive indices
                if indices:
                    start = indices[0]
                    prev = indices[0]

                    for idx in indices[1:] + [None]:
                        if idx is None or idx != prev + 1:
                            purple_zones.append({
                                'pool_id': pool_id,
                                'quarter': str(quarter),
                                'start_time': group.loc[start, 'timestamp'],
                                'end_time': group.loc[prev, 'timestamp'],
                                'duration_hours': prev - start + 1,
                                'max_volatility': group.loc[start:prev, 'volatility_6h'].max()
                            })
                            if idx is not None:
                                start = idx
                        prev = idx

    purple_df = pd.DataFrame(purple_zones)

    if len(purple_df) > 0:
        print(f"     ✓ Found {len(purple_df)} purple zones")
        print(f"     Duration: {purple_df['duration_hours'].mean():.1f}h avg, {purple_df['duration_hours'].max():.0f}h max")
    else:
        print(f"     ⚠️  No purple zones found (data very stable)")

    return purple_df

def assign_zones_to_data(df, zones_df, purple_df=None):
    """Assign zone labels to each row"""
    df = df.copy()
    df['pool_id'] = df['instance_type'] + '_' + df['availability_zone']
    df['zone'] = 'unknown'
    df['is_purple'] = False

    df = df.merge(zones_df[['pool_id', 'green_max', 'yellow_max', 'orange_max', 'red_max']],
                  on='pool_id', how='left')

    df.loc[df['spot_price'] <= df['green_max'], 'zone'] = 'green'
    df.loc[(df['spot_price'] > df['green_max']) & (df['spot_price'] <= df['yellow_max']), 'zone'] = 'yellow'
    df.loc[(df['spot_price'] > df['yellow_max']) & (df['spot_price'] <= df['orange_max']), 'zone'] = 'orange'
    df.loc[df['spot_price'] > df['orange_max'], 'zone'] = 'red'

    # Mark purple zones
    if purple_df is not None and len(purple_df) > 0:
        for _, prow in purple_df.iterrows():
            mask = (df['pool_id'] == prow['pool_id']) & \
                   (df['timestamp'] >= prow['start_time']) & \
                   (df['timestamp'] <= prow['end_time'])
            df.loc[mask, 'is_purple'] = True

    return df

# ============================================================================
# 3. HIERARCHICAL FEATURES (Per-Timestamp Relative Rankings)
# ============================================================================

def calculate_hierarchical_features(df):
    """
    Calculate 4-level hierarchical features per timestamp

    Levels:
    - L1 Global: All pools at this timestamp
    - L2 Family: Same instance family (t3, t4g, c5)
    - L3 AZ: Same availability zone
    - L4 Peer: Same family AND same AZ

    AWS Insight: Relative rankings avoid lookahead bias
    """
    print("\n🌲 STEP 3: CALCULATING HIERARCHICAL FEATURES")
    print("="*80)

    df = df.copy()

    # Extract instance family
    df['instance_family'] = df['instance_type'].str.extract(r'([a-z]+\d+[a-z]*)')[0]

    # Instance characteristics
    size_map = {'small': 2, 'medium': 3, 'large': 5, 'xlarge': 6, '2xlarge': 7}
    df['size_tier'] = df['instance_type'].apply(lambda x: size_map.get(x.split('.')[-1], 3))
    df['generation'] = df['instance_family'].str.extract(r'(\d+)')[0].fillna('5').astype(int)
    df['az_encoded'] = pd.Categorical(df['availability_zone']).codes

    # Time features
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['is_business_hours'] = ((df['hour'] >= 10) & (df['hour'] <= 18)).astype(int)

    print(f"  Vectorized calculation (fast)...")

    # L1: Global rankings (all pools at timestamp)
    df['discount_percentile_L1_global'] = df.groupby('timestamp')['discount_pct'].rank(pct=True)
    df['volatility_percentile_L1_global'] = df.groupby('timestamp')['volatility_24h'].rank(pct=True)

    discount_mean = df.groupby('timestamp')['discount_pct'].transform('mean')
    discount_std = df.groupby('timestamp')['discount_pct'].transform('std').replace(0, 1)
    df['discount_zscore_L1_global'] = (df['discount_pct'] - discount_mean) / discount_std

    df['market_stress_L1_global'] = df.groupby('timestamp')['volatility_percentile_L1_global'].transform('mean')

    # L2: Family rankings
    df['discount_percentile_L2_family'] = df.groupby(['timestamp', 'instance_family'])['discount_pct'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['volatility_percentile_L2_family'] = df.groupby(['timestamp', 'instance_family'])['volatility_24h'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['family_stress_L2'] = df.groupby(['timestamp', 'instance_family'])['volatility_percentile_L2_family'].transform('mean')

    # L3: AZ rankings
    df['discount_percentile_L3_az'] = df.groupby(['timestamp', 'availability_zone'])['discount_pct'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['volatility_percentile_L3_az'] = df.groupby(['timestamp', 'availability_zone'])['volatility_24h'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['az_stress_L3'] = df.groupby(['timestamp', 'availability_zone'])['volatility_percentile_L3_az'].transform('mean')

    # L4: Peer rankings
    df['discount_percentile_L4_peer'] = df.groupby(['timestamp', 'instance_family', 'availability_zone'])['discount_pct'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['volatility_percentile_L4_peer'] = df.groupby(['timestamp', 'instance_family', 'availability_zone'])['volatility_24h'].transform(
        lambda x: x.rank(pct=True) if len(x) > 1 else 0.5
    )
    df['peer_pool_count'] = df.groupby(['timestamp', 'instance_family', 'availability_zone'])['instance_type'].transform('count')

    # Cross-level features
    df['global_vs_family_gap'] = df['discount_percentile_L1_global'] - df['discount_percentile_L2_family']

    family_discount_mean = df.groupby(['timestamp', 'instance_family'])['discount_pct'].transform('mean')
    family_volatility_mean = df.groupby(['timestamp', 'instance_family'])['volatility_24h'].transform('mean')
    df['better_alternatives_L2_family'] = (
        (df['discount_pct'] < family_discount_mean) &
        (df['volatility_24h'] < family_volatility_mean)
    ).astype(int)

    print(f"  ✓ Calculated 18 hierarchical features (4 levels)")

    return df

# ============================================================================
# 4. PERCENTILE-BASED STABILITY TARGET
# ============================================================================

def calculate_stability_score_percentile_based(df, lookahead_hours=6):
    """
    Calculate stability score using percentile-based penalties

    Two-pass approach:
    1. Calculate raw future metrics (discount, volatility, spikes, etc.)
    2. Convert to percentiles (worst 5%, 10%, 20%, etc.)
    3. Apply graduated penalties based on distribution

    Guarantees variance even in stable data
    """
    print("\n🎯 STEP 4: CALCULATING PERCENTILE-BASED STABILITY SCORES")
    print("="*80)
    print(f"  Lookahead: {lookahead_hours} hours (future-based target)")
    print(f"  Method: Distribution-based percentiles (not absolute thresholds)")

    df = df.copy().sort_values(['instance_type', 'availability_zone', 'timestamp'])
    df['stability_score'] = np.nan

    # Initialize metric columns
    metrics = ['future_min_discount', 'future_vol_ratio', 'future_spikes',
               'future_discount_drop', 'future_mean_price_ratio']
    for metric in metrics:
        df[metric] = np.nan

    rows_before = len(df)

    # Pass 1: Calculate raw future metrics
    for (inst_type, az), group in tqdm(df.groupby(['instance_type', 'availability_zone']),
                                        desc="  Pass 1: Future metrics"):
        indices = group.index.tolist()

        for i, idx in enumerate(indices):
            future_start = i + 1
            future_end = i + 1 + lookahead_hours

            if future_end > len(indices):
                continue

            future_indices = indices[future_start:future_end]
            future_data = df.loc[future_indices]

            df.loc[idx, 'future_min_discount'] = future_data['discount_pct'].min()

            future_vol = future_data['spot_price'].std()
            df.loc[idx, 'future_vol_ratio'] = future_vol / df.loc[idx, 'on_demand_price']

            future_changes = future_data['spot_price'].pct_change().fillna(0)
            df.loc[idx, 'future_spikes'] = (future_changes > 0.5).sum()

            current_discount = df.loc[idx, 'discount_pct']
            df.loc[idx, 'future_discount_drop'] = max(0, current_discount - future_data['discount_pct'].min())

            current_price = df.loc[idx, 'spot_price']
            df.loc[idx, 'future_mean_price_ratio'] = future_data['spot_price'].mean() / current_price if current_price > 0 else 1.0

    # Pass 2: Calculate percentiles
    print(f"  Pass 2: Converting to percentiles...")
    valid_mask = df['future_min_discount'].notna()
    valid_df = df[valid_mask]

    df.loc[valid_mask, 'pct_min_discount'] = valid_df['future_min_discount'].rank(pct=True) * 100
    df.loc[valid_mask, 'pct_vol_ratio'] = (1 - valid_df['future_vol_ratio'].rank(pct=True)) * 100
    df.loc[valid_mask, 'pct_spikes'] = (1 - valid_df['future_spikes'].rank(pct=True)) * 100
    df.loc[valid_mask, 'pct_discount_drop'] = (1 - valid_df['future_discount_drop'].rank(pct=True)) * 100
    df.loc[valid_mask, 'pct_price_ratio'] = (1 - valid_df['future_mean_price_ratio'].rank(pct=True)) * 100

    # Pass 3: Apply percentile-based penalties
    print(f"  Pass 3: Applying graduated penalties...")
    for idx in tqdm(valid_df.index, desc="  Stability scores"):
        stability = 100.0

        # Priority 1: Discount proximity (strongest)
        pct = df.loc[idx, 'pct_min_discount']
        if pct <= 5:
            stability -= 90
        elif pct <= 10:
            stability -= 80
        elif pct <= 20:
            stability -= 70
        elif pct <= 30:
            stability -= 55
        elif pct <= 50:
            stability -= 25

        # Priority 2: Volatility
        pct = df.loc[idx, 'pct_vol_ratio']
        if pct <= 5:
            stability -= 75
        elif pct <= 10:
            stability -= 65
        elif pct <= 20:
            stability -= 55
        elif pct <= 30:
            stability -= 40
        elif pct <= 50:
            stability -= 25

        # Priority 3: Spikes
        pct = df.loc[idx, 'pct_spikes']
        if pct <= 5:
            stability -= 70
        elif pct <= 10:
            stability -= 55
        elif pct <= 20:
            stability -= 40
        elif pct <= 30:
            stability -= 30
        elif pct <= 50:
            stability -= 15

        # Priority 4: Discount drop
        pct = df.loc[idx, 'pct_discount_drop']
        if pct <= 5:
            stability -= 65
        elif pct <= 10:
            stability -= 55
        elif pct <= 20:
            stability -= 45
        elif pct <= 30:
            stability -= 35
        elif pct <= 50:
            stability -= 20

        # Priority 5: Price trend
        pct = df.loc[idx, 'pct_price_ratio']
        if pct <= 5:
            stability -= 60
        elif pct <= 10:
            stability -= 50
        elif pct <= 20:
            stability -= 40
        elif pct <= 30:
            stability -= 30
        elif pct <= 50:
            stability -= 15

        stability = max(0, min(100, stability))
        df.loc[idx, 'stability_score'] = stability

    # Remove rows without target
    df = df[df['stability_score'].notna()].copy()

    rows_dropped = rows_before - len(df)
    avg = df['stability_score'].mean()
    std = df['stability_score'].std()

    print(f"\n  ✓ Dropped {rows_dropped:,} rows (last {lookahead_hours}h per pool)")
    print(f"  ✓ Remaining: {len(df):,} rows")
    print(f"  ✓ Stability score: {avg:.1f} ± {std:.1f}")
    print(f"  Distribution:")
    for low, high in [(0,20), (20,40), (40,60), (60,80), (80,100)]:
        count = ((df['stability_score'] > low) & (df['stability_score'] <= high)).sum()
        pct = count / len(df) * 100
        print(f"    {low:3d}-{high:3d}: {count:6,} rows ({pct:5.1f}%)")

    return df

# ============================================================================
# 5. MODEL TRAINING (LightGBM Regressor)
# ============================================================================

FEATURE_LIST = [
    # Basic features
    'discount_pct', 'volatility_24h', 'price_velocity_1h', 'price_velocity_6h',
    'spike_count_24h', 'ceiling_distance_pct', 'deviation_from_mean',

    # Lag features
    'discount_pct_lag_1h', 'discount_pct_lag_3h', 'discount_pct_lag_6h',
    'discount_pct_lag_12h', 'discount_pct_lag_24h',
    'volatility_24h_lag_1h', 'volatility_24h_lag_3h', 'volatility_24h_lag_6h',
    'volatility_24h_lag_12h', 'volatility_24h_lag_24h',
    'discount_change_1h', 'discount_change_3h', 'discount_change_6h',
    'discount_change_12h', 'discount_change_24h',

    # Hierarchical features
    'discount_percentile_L1_global', 'volatility_percentile_L1_global',
    'discount_zscore_L1_global', 'market_stress_L1_global',
    'discount_percentile_L2_family', 'volatility_percentile_L2_family', 'family_stress_L2',
    'discount_percentile_L3_az', 'volatility_percentile_L3_az', 'az_stress_L3',
    'discount_percentile_L4_peer', 'volatility_percentile_L4_peer', 'peer_pool_count',
    'global_vs_family_gap', 'better_alternatives_L2_family',

    # Instance characteristics
    'size_tier', 'generation', 'az_encoded', 'hour', 'day_of_week', 'is_business_hours'
]

def train_stability_model(df_train):
    """Train LightGBM model to predict stability scores"""
    print("\n🤖 STEP 5: TRAINING STABILITY PREDICTION MODEL")
    print("="*80)

    X_train = df_train[FEATURE_LIST]
    y_train = df_train['stability_score']

    print(f"  Training samples: {len(X_train):,}")
    print(f"  Features: {len(FEATURE_LIST)}")
    print(f"  Target range: [{y_train.min():.1f}, {y_train.max():.1f}]")

    model = LGBMRegressor(**HYPERPARAMETERS)
    model.fit(X_train, y_train)

    # Training metrics
    train_pred = model.predict(X_train)
    train_mae = mean_absolute_error(y_train, train_pred)
    train_rmse = np.sqrt(mean_squared_error(y_train, train_pred))
    train_r2 = r2_score(y_train, train_pred)

    print(f"\n  Training Metrics:")
    print(f"    MAE:  {train_mae:.2f}")
    print(f"    RMSE: {train_rmse:.2f}")
    print(f"    R²:   {train_r2:.3f}")

    return model

# ============================================================================
# 6. POOL RANKING
# ============================================================================

def rank_pools(df):
    """Rank pools by safety (60%) + discount (30%) + stability (10%)"""
    print("\n🏆 STEP 6: RANKING POOLS")
    print("="*80)

    rankings = []

    for pool_id, group in df.groupby('pool_id'):
        green_pct = (group['zone'] == 'green').sum() / len(group) * 100
        avg_discount = group['discount_pct'].mean()
        cv = group['spot_price'].std() / group['spot_price'].mean()
        stability = 1 / (1 + cv)
        purple_pct = group['is_purple'].sum() / len(group) * 100

        score = green_pct * 0.60 + avg_discount * 0.30 + stability * 100 * 0.10 - purple_pct * 2

        rankings.append({
            'pool_id': pool_id,
            'green_pct': green_pct,
            'avg_discount': avg_discount,
            'stability': stability,
            'purple_pct': purple_pct,
            'composite_score': score,
            'avg_price': group['spot_price'].mean()
        })

    rankings_df = pd.DataFrame(rankings).sort_values('composite_score', ascending=False).reset_index(drop=True)
    rankings_df['rank'] = range(1, len(rankings_df) + 1)

    print(f"  Top 5 pools:")
    for _, row in rankings_df.head(5).iterrows():
        print(f"    #{row['rank']}: {row['pool_id']}")
        print(f"        Score: {row['composite_score']:.1f} | Green: {row['green_pct']:.1f}% | Discount: {row['avg_discount']:.1f}%")

    return rankings_df

# ============================================================================
# 7. ABNORMALITY DETECTION
# ============================================================================

def train_abnormality_detector(df):
    """Train Isolation Forest for anomaly detection"""
    print("\n🔮 STEP 7: TRAINING ABNORMALITY DETECTOR")
    print("="*80)

    df_model = df.copy()
    df_model['zone_encoded'] = pd.Categorical(df_model['zone'], categories=['green', 'yellow', 'orange', 'red']).codes

    features = ['spot_price', 'discount_pct', 'volatility_24h', 'zone_encoded',
                'price_velocity_1h', 'spike_count_24h']

    df_model[features] = df_model[features].fillna(df_model[features].median())
    X = df_model[features].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    iso_forest = IsolationForest(contamination=0.05, random_state=CONFIG['random_seed'], n_jobs=-1)
    iso_forest.fit(X_scaled)

    predictions = iso_forest.predict(X_scaled)
    anomaly_count = (predictions == -1).sum()

    print(f"  ✓ Detected {anomaly_count:,} anomalies ({anomaly_count/len(df)*100:.2f}%)")

    return iso_forest, scaler, features

# ============================================================================
# 8. SMART SWITCHING BACKTEST
# ============================================================================

def backtest_smart_switching(df_test_quarters, zones_df, rankings_df, model, iso_forest, scaler, features):
    """Backtest smart switching strategy on 2025 Q1/Q2/Q3"""
    print("\n🔄 STEP 8: BACKTESTING SMART SWITCHING")
    print("="*80)

    results = {}

    for quarter_name, df_test in df_test_quarters.items():
        print(f"\n  {quarter_name}:")

        df = assign_zones_to_data(df_test, zones_df)

        # Predict stability scores
        X_test = df[FEATURE_LIST]
        df['predicted_stability'] = model.predict(X_test)

        # Predict anomalies
        df['zone_encoded'] = pd.Categorical(df['zone'], categories=['green', 'yellow', 'orange', 'red']).codes
        df[features] = df[features].fillna(df[features].median())
        X_anom = scaler.transform(df[features].values)
        df['predicted_anomaly'] = (iso_forest.predict(X_anom) == -1)

        # Simulate switching
        timestamps = sorted(df['timestamp'].unique())
        current_pool = rankings_df.iloc[0]['pool_id']

        switches = []
        costs = []

        for ts in timestamps:
            current_data = df[(df['timestamp'] == ts) & (df['pool_id'] == current_pool)]

            if len(current_data) == 0:
                continue

            current_row = current_data.iloc[0]

            should_switch = False
            reason = None

            if current_row['zone'] != 'green':
                should_switch = True
                reason = f"exit_green_{current_row['zone']}"
            elif current_row['is_purple']:
                should_switch = True
                reason = "purple_zone"
            elif current_row['predicted_anomaly']:
                should_switch = True
                reason = "predicted_abnormality"

            if should_switch:
                alternatives = df[df['timestamp'] == ts].merge(
                    rankings_df[['pool_id', 'composite_score']], on='pool_id'
                )
                alternatives = alternatives[alternatives['zone'] == 'green'].sort_values('composite_score', ascending=False)

                if len(alternatives) > 0:
                    new_pool = alternatives.iloc[0]['pool_id']
                    if new_pool != current_pool:
                        switches.append({
                            'timestamp': ts,
                            'from_pool': current_pool,
                            'to_pool': new_pool,
                            'reason': reason
                        })
                        costs.append(CONFIG['switching_cost'])
                        current_pool = new_pool

            hourly_data = df[(df['timestamp'] == ts) & (df['pool_id'] == current_pool)]
            if len(hourly_data) > 0:
                costs.append(hourly_data.iloc[0]['spot_price'])

        # Calculate metrics
        baseline_pool = rankings_df.iloc[0]['pool_id']
        baseline_costs = df[df['pool_id'] == baseline_pool].groupby('timestamp')['spot_price'].first()

        actual_cost = sum(costs)
        baseline_cost = baseline_costs.sum()
        savings = baseline_cost - actual_cost
        savings_pct = (savings / baseline_cost) * 100

        # ML metrics
        y_true = df['stability_score']
        y_pred = df['predicted_stability']
        mae = mean_absolute_error(y_true, y_pred)
        r2 = r2_score(y_true, y_pred)

        results[quarter_name] = {
            'switches': len(switches),
            'actual_cost': actual_cost,
            'baseline_cost': baseline_cost,
            'savings': savings,
            'savings_pct': savings_pct,
            'mae': mae,
            'r2': r2
        }

        print(f"    Switches: {len(switches)}")
        print(f"    Baseline cost: ${baseline_cost:.2f}")
        print(f"    Actual cost: ${actual_cost:.2f}")
        print(f"    Savings: ${savings:.2f} ({savings_pct:.2f}%)")
        print(f"    MAE: {mae:.2f} | R²: {r2:.3f}")

    return results

# ============================================================================
# 9. VISUALIZATION
# ============================================================================

def create_visualizations(df_train, df_test_quarters, zones_df, model, results):
    """Create comprehensive visualization suite"""
    print("\n📊 STEP 9: CREATING VISUALIZATIONS")
    print("="*80)

    # 1. Feature Importance
    fig, ax = plt.subplots(figsize=(10, 8))
    importance = pd.DataFrame({
        'feature': FEATURE_LIST,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False).head(20)

    ax.barh(range(len(importance)), importance['importance'])
    ax.set_yticks(range(len(importance)))
    ax.set_yticklabels(importance['feature'])
    ax.set_xlabel('Importance')
    ax.set_title('Top 20 Feature Importance')
    plt.tight_layout()
    plt.savefig(Path(CONFIG['plots_dir']) / 'feature_importance.png', dpi=150)
    plt.close()

    # 2. Backtest Results
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    quarters = list(results.keys())
    savings_pcts = [results[q]['savings_pct'] for q in quarters]
    maes = [results[q]['mae'] for q in quarters]
    r2s = [results[q]['r2'] for q in quarters]
    switches = [results[q]['switches'] for q in quarters]

    axes[0, 0].bar(quarters, savings_pcts, color='green')
    axes[0, 0].set_title('Cost Savings (%)')
    axes[0, 0].set_ylabel('Savings %')

    axes[0, 1].bar(quarters, maes, color='blue')
    axes[0, 1].set_title('Prediction Error (MAE)')
    axes[0, 1].set_ylabel('MAE')

    axes[1, 0].bar(quarters, r2s, color='purple')
    axes[1, 0].set_title('Model Performance (R²)')
    axes[1, 0].set_ylabel('R²')

    axes[1, 1].bar(quarters, switches, color='orange')
    axes[1, 1].set_title('Number of Switches')
    axes[1, 1].set_ylabel('Switches')

    plt.tight_layout()
    plt.savefig(Path(CONFIG['plots_dir']) / 'backtest_results.png', dpi=150)
    plt.close()

    print(f"  ✓ Saved visualizations to {CONFIG['plots_dir']}/")

# ============================================================================
# 10. MAIN EXECUTION
# ============================================================================

def main():
    # Load data
    df_train, df_test, df_q1, df_q2, df_q3 = load_data()

    # Calculate zones (on training data only)
    zones_df = calculate_pool_zones(df_train)
    purple_df = calculate_quarterly_purple_zones(df_train)

    # Assign zones
    df_train = assign_zones_to_data(df_train, zones_df, purple_df)

    # Add hierarchical features
    df_train = calculate_hierarchical_features(df_train)
    df_test = calculate_hierarchical_features(df_test)
    df_q1 = calculate_hierarchical_features(df_q1)
    df_q2 = calculate_hierarchical_features(df_q2)
    df_q3 = calculate_hierarchical_features(df_q3)

    # Calculate stability scores
    df_train = calculate_stability_score_percentile_based(df_train, CONFIG['prediction_horizon'])
    df_test = calculate_stability_score_percentile_based(df_test, CONFIG['prediction_horizon'])
    df_q1 = calculate_stability_score_percentile_based(df_q1, CONFIG['prediction_horizon'])
    df_q2 = calculate_stability_score_percentile_based(df_q2, CONFIG['prediction_horizon'])
    df_q3 = calculate_stability_score_percentile_based(df_q3, CONFIG['prediction_horizon'])

    # Train model
    model = train_stability_model(df_train)

    # Rank pools
    rankings_df = rank_pools(df_train)

    # Train abnormality detector
    iso_forest, scaler, features = train_abnormality_detector(df_train)

    # Backtest
    df_test_quarters = {
        'Q1 2025': df_q1,
        'Q2 2025': df_q2,
        'Q3 2025': df_q3
    }
    results = backtest_smart_switching(df_test_quarters, zones_df, rankings_df, model, iso_forest, scaler, features)

    # Visualize
    create_visualizations(df_train, df_test_quarters, zones_df, model, results)

    # Save outputs
    print("\n💾 STEP 10: SAVING OUTPUTS")
    print("="*80)
    zones_df.to_csv(Path(CONFIG['output_dir']) / 'pool_zones.csv', index=False)
    purple_df.to_csv(Path(CONFIG['output_dir']) / 'purple_zones.csv', index=False)
    rankings_df.to_csv(Path(CONFIG['output_dir']) / 'pool_rankings.csv', index=False)

    with open(Path(CONFIG['models_dir']) / CONFIG['model_filename'], 'wb') as f:
        pickle.dump({'model': model, 'iso_forest': iso_forest, 'scaler': scaler, 'features': features}, f)

    with open(Path(CONFIG['output_dir']) / 'backtest_results.txt', 'w') as f:
        f.write("UNIFIED SPOT OPTIMIZATION - BACKTEST RESULTS\n")
        f.write("="*50 + "\n\n")
        for quarter, metrics in results.items():
            f.write(f"{quarter}:\n")
            f.write(f"  Switches: {metrics['switches']}\n")
            f.write(f"  Savings: ${metrics['savings']:.2f} ({metrics['savings_pct']:.2f}%)\n")
            f.write(f"  MAE: {metrics['mae']:.2f} | R²: {metrics['r2']:.3f}\n\n")

    print(f"  ✓ Saved to {CONFIG['output_dir']}/")

    print("\n" + "="*80)
    print("UNIFIED SPOT OPTIMIZATION COMPLETE")
    print("="*80)
    print(f"End Time: {datetime.now()}")

    # Summary
    total_savings = sum(r['savings'] for r in results.values())
    avg_savings_pct = np.mean([r['savings_pct'] for r in results.values()])
    avg_r2 = np.mean([r['r2'] for r in results.values()])

    print(f"\n📊 SUMMARY:")
    print(f"  Total Savings (2025): ${total_savings:.2f}")
    print(f"  Average Savings: {avg_savings_pct:.2f}%")
    print(f"  Average R²: {avg_r2:.3f}")
    print(f"  Pools Ranked: {len(rankings_df)}")
    print(f"  Visualizations: {CONFIG['plots_dir']}/")
    print("="*80)

if __name__ == "__main__":
    main()
