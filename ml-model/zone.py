"""
Zone-Based Spot Instance Risk Prediction and Smart Switching System
===================================================================

Purpose:
- Calculate pool-specific risk zones (Green/Yellow/Orange/Red/Purple)
- Train on 2023-24 data, backtest on 2025 data
- Predict abnormalities and rank pools by safety + discount
- Perform smart switches when crossing zones
- Show actual vs predicted savings

Zone Definitions (Pool-Specific Percentiles):
- Green:  P70  (70th percentile - safe zone, normal operations)
- Yellow: P90  (90th percentile - elevated risk, manageable)
- Orange: P95  (95th percentile - high risk, outlier threshold)
- Red:    Max+10% (critical - capacity crunch with safety margin)
- Purple: Volatility spikes (6-hour windows exceeding quarterly baseline)

Key Innovation:
- Quarterly volatility calculation (captures seasonal patterns)
- Pool-relative zones (t3.medium vs c5.large have different baselines)
- Switching triggers: Zone crossing, purple zones, abnormality prediction

Author: Zone-Based Switching System
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

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix

warnings.filterwarnings('ignore')
sns.set_style('whitegrid')

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    # Data paths (same as hierarchical model)
    'training_data': '/Users/atharvapudale/Downloads/aws_2023_2024_complete_24months.csv',
    'test_q1': '/Users/atharvapudale/Downloads/mumbai_spot_data_sorted_asc(1-2-3-25).csv',
    'test_q2': '/Users/atharvapudale/Downloads/mumbai_spot_data_sorted_asc(4-5-6-25).csv',
    'test_q3': '/Users/atharvapudale/Downloads/mumbai_spot_data_sorted_asc(7-8-9-25).csv',

    # Scope
    'region': 'ap-south-1',
    'instance_types': ['t3.medium', 't4g.medium', 'c5.large', 't4g.small'],

    # Output
    'output_dir': './training/outputs',
    'plots_dir': './training/plots',
    'zone_plots_dir': './training/plots/zones',

    # Zone configuration
    'zone_percentiles': {
        'green': 70,   # P70 - safe operations (<5% interruption)
        'yellow': 90,  # P90 - elevated risk (manageable with automation)
        'orange': 95,  # P95 - high risk (outlier threshold)
        'red_buffer': 0.10  # Max + 10% safety margin
    },

    # Purple zone (volatility) configuration
    'volatility_window': 6,  # 6-hour rolling window
    'quarterly_baseline': True,  # Calculate volatility per quarter (not annual)
    'purple_threshold_multiplier': 2.0,  # 2x quarterly baseline = purple

    # Switching configuration
    'switching_cost': 0.01,  # $0.01 per switch (API overhead)
    'prediction_horizon': 1,  # Predict 1 hour ahead for switching

    'random_seed': 42,
}

# Create output directories
for dir_path in [CONFIG['output_dir'], CONFIG['plots_dir'], CONFIG['zone_plots_dir']]:
    Path(dir_path).mkdir(parents=True, exist_ok=True)

print("="*80)
print("ZONE-BASED SPOT INSTANCE RISK PREDICTION & SMART SWITCHING")
print("="*80)
print(f"Start Time: {datetime.now()}")
print("="*80)

# ============================================================================
# 1. DATA LOADING
# ============================================================================

def standardize_columns(df):
    """Standardize column names across different CSV formats"""
    # Convert all columns to lowercase
    df.columns = df.columns.str.lower().str.strip()

    # Create mapping for common variations
    col_mapping = {}
    for col in df.columns:
        # Timestamp variations
        if 'time' in col or 'date' in col:
            col_mapping[col] = 'timestamp'
        # Instance type variations
        elif 'instance' in col and 'type' in col:
            col_mapping[col] = 'instance_type'
        # Availability zone variations
        elif ('availability' in col and 'zone' in col) or col in ['az', 'zone']:
            col_mapping[col] = 'availability_zone'
        # Spot price variations
        elif 'spot' in col and 'price' in col:
            col_mapping[col] = 'spot_price'
        elif col == 'price':
            col_mapping[col] = 'spot_price'
        # On-demand price variations
        elif 'ondemand' in col or 'on_demand' in col:
            col_mapping[col] = 'on_demand_price'
        # Discount percentage
        elif 'discount' in col:
            col_mapping[col] = 'discount_pct'
        # Volatility
        elif 'volatility' in col:
            col_mapping[col] = 'volatility_24h'
        # Price velocity
        elif 'velocity' in col:
            if '1h' in col or '1_h' in col:
                col_mapping[col] = 'price_velocity_1h'
            elif '6h' in col or '6_h' in col:
                col_mapping[col] = 'price_velocity_6h'
        # Spike count
        elif 'spike' in col:
            col_mapping[col] = 'spike_count_24h'

    df = df.rename(columns=col_mapping)
    return df

def calculate_missing_features(df):
    """Calculate missing features from basic spot price data"""
    df = df.copy()

    # Calculate on-demand price if missing (using a fixed ratio or lookup)
    if 'on_demand_price' not in df.columns:
        # Estimate: on-demand is typically 3-5x spot price for stable instances
        # Use a conservative multiplier
        df['on_demand_price'] = df['spot_price'] * 4.0
        print(f"    ⚠️  Estimated on_demand_price (spot_price × 4)")

    # Calculate discount percentage if missing
    if 'discount_pct' not in df.columns:
        df['discount_pct'] = ((df['on_demand_price'] - df['spot_price']) / df['on_demand_price']) * 100
        print(f"    ✓ Calculated discount_pct")

    # Sort by pool and timestamp for rolling calculations
    df = df.sort_values(['instance_type', 'availability_zone', 'timestamp'])

    # Calculate volatility (24-hour rolling std) if missing
    if 'volatility_24h' not in df.columns:
        df['volatility_24h'] = df.groupby(['instance_type', 'availability_zone'])['spot_price'].transform(
            lambda x: x.rolling(window=24, min_periods=1).std()
        )
        print(f"    ✓ Calculated volatility_24h")

    # Calculate price velocity (hourly change) if missing
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

    # Calculate spike count (24-hour window) if missing
    if 'spike_count_24h' not in df.columns:
        # Define spike as >50% price jump
        df['_temp_spike'] = (df.groupby(['instance_type', 'availability_zone'])['spot_price'].transform(
            lambda x: x.pct_change()
        ).fillna(0) > 0.5).astype(int)

        df['spike_count_24h'] = df.groupby(['instance_type', 'availability_zone'])['_temp_spike'].transform(
            lambda x: x.rolling(window=24, min_periods=1).sum()
        )
        df = df.drop(columns=['_temp_spike'])
        print(f"    ✓ Calculated spike_count_24h")

    return df

def load_data():
    """Load training (2023-24) and test (2025 Q1/Q2/Q3) data"""
    print("\n📂 Loading data...")

    try:
        # Training data (2023-24)
        print(f"  Loading training data (2023-24)...")
        df_train = pd.read_csv(CONFIG['training_data'])
        df_train = standardize_columns(df_train)

        if 'timestamp' not in df_train.columns:
            print(f"    ⚠️  Available columns: {list(df_train.columns)}")
            raise ValueError("No timestamp column found in training data")

        df_train['timestamp'] = pd.to_datetime(df_train['timestamp'])
        print(f"    ✓ Training: {len(df_train):,} rows")

        # Test data (2025 Q1/Q2/Q3)
        print(f"  Loading test data (2025)...")

        df_test_q1 = pd.read_csv(CONFIG['test_q1'])
        df_test_q1 = standardize_columns(df_test_q1)

        if 'timestamp' not in df_test_q1.columns:
            print(f"    ⚠️  Q1 columns: {list(df_test_q1.columns)}")
            raise ValueError("No timestamp column found in Q1 test data")

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

        # Calculate missing features if needed
        print(f"  🔧 Calculating missing features...")
        df_train = calculate_missing_features(df_train)
        df_test = calculate_missing_features(df_test)

        # Verify required columns are present
        required_cols = ['timestamp', 'instance_type', 'availability_zone', 'spot_price']
        missing_train = [col for col in required_cols if col not in df_train.columns]
        missing_test = [col for col in required_cols if col not in df_test.columns]

        if missing_train:
            print(f"    ⚠️  Training data missing: {missing_train}")
            print(f"    ⚠️  Available: {list(df_train.columns)}")
            raise ValueError(f"Required columns missing from training data: {missing_train}")
        if missing_test:
            print(f"    ⚠️  Test data missing: {missing_test}")
            print(f"    ⚠️  Available: {list(df_test.columns)}")
            raise ValueError(f"Required columns missing from test data: {missing_test}")

        print(f"  ✓ All required features present")

        return df_train, df_test

    except Exception as e:
        print(f"    ❌ Error loading data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# ============================================================================
# 2. ZONE CALCULATION (Pool-Specific, Quarterly for Purple)
# ============================================================================

def calculate_pool_zones(df):
    """
    Calculate pool-specific price zones based on historical percentiles

    Zones are RELATIVE to each pool's own price history:
    - Green: P70 (normal operations)
    - Yellow: P90 (elevated but manageable)
    - Orange: P95 (high risk)
    - Red: Max+10% (critical with safety buffer)

    Returns: DataFrame with zone thresholds for each pool
    """
    print("\n🎯 Calculating pool-specific price zones...")
    print(f"  📊 Zone methodology: Pool-relative percentiles (P70/P90/P95/Max+10%)")
    print(f"  📊 Why these percentiles?")
    print(f"     - P70: Statistical 'normal range' (AWS <5% interruption)")
    print(f"     - P90: 95% CI lower bound (industry standard)")
    print(f"     - P95: 95% CI upper bound (outlier threshold)")
    print(f"     - Max+10%: Engineering margin for black swan events")

    zone_thresholds = []

    for (inst_type, az), group in tqdm(df.groupby(['instance_type', 'availability_zone']),
                                        desc="  Calculating zones"):
        pool_id = f"{inst_type}_{az}"
        prices = group['spot_price']

        # Calculate percentile thresholds
        p70 = np.percentile(prices, CONFIG['zone_percentiles']['green'])
        p90 = np.percentile(prices, CONFIG['zone_percentiles']['yellow'])
        p95 = np.percentile(prices, CONFIG['zone_percentiles']['orange'])
        max_price = prices.max()
        red_threshold = max_price * (1 + CONFIG['zone_percentiles']['red_buffer'])

        zone_thresholds.append({
            'pool_id': pool_id,
            'instance_type': inst_type,
            'availability_zone': az,
            'green_max': p70,
            'yellow_max': p90,
            'orange_max': p95,
            'red_max': red_threshold,
            'historical_max': max_price,
            'mean_price': prices.mean(),
            'std_price': prices.std()
        })

    zones_df = pd.DataFrame(zone_thresholds)

    print(f"\n  ✓ Calculated zones for {len(zones_df)} pools")
    print(f"\n  📊 Zone thresholds (example: first pool):")
    first_pool = zones_df.iloc[0]
    print(f"     Pool: {first_pool['pool_id']}")
    print(f"     Green:  ≤ ${first_pool['green_max']:.4f}")
    print(f"     Yellow: ≤ ${first_pool['yellow_max']:.4f}")
    print(f"     Orange: ≤ ${first_pool['orange_max']:.4f}")
    print(f"     Red:    ≤ ${first_pool['red_max']:.4f}")

    return zones_df

def calculate_quarterly_purple_zones(df):
    """
    Calculate purple zones (volatility spikes) on QUARTERLY basis

    CRITICAL: Quarterly calculation captures seasonal patterns:
    - Q1: Jan-Mar (post-holiday normalization)
    - Q2: Apr-Jun (tax season, spring traffic)
    - Q3: Jul-Sep (summer peak, infrastructure changes)
    - Q4: Oct-Dec (holiday surge, capacity pressure)

    Purple zone = 6-hour volatility > 2x quarterly baseline
    """
    print("\n🟣 Calculating purple zones (quarterly volatility spikes)...")
    print(f"  📊 Window: {CONFIG['volatility_window']}-hour rolling volatility")
    print(f"  📊 Baseline: Quarterly (every 3 months) NOT annual")
    print(f"  📊 Threshold: {CONFIG['purple_threshold_multiplier']}x quarterly baseline")
    print(f"  📊 Why quarterly? Captures seasonal AWS pricing patterns")

    df = df.copy()
    df['quarter'] = df['timestamp'].dt.to_period('Q')

    purple_zones = []

    for (inst_type, az), group in tqdm(df.groupby(['instance_type', 'availability_zone']),
                                        desc="  Calculating purple zones"):
        pool_id = f"{inst_type}_{az}"
        group = group.sort_values('timestamp').reset_index(drop=True)

        # Calculate 6-hour rolling volatility
        group['volatility_6h'] = group['spot_price'].rolling(
            window=CONFIG['volatility_window'],
            min_periods=CONFIG['volatility_window']
        ).std()

        # Calculate quarterly baseline volatility
        for quarter, quarter_group in group.groupby('quarter'):
            quarter_baseline = quarter_group['volatility_6h'].median()
            purple_threshold = quarter_baseline * CONFIG['purple_threshold_multiplier']

            # Mark purple zones (volatility exceeds 2x quarterly baseline)
            quarter_mask = group['quarter'] == quarter
            purple_mask = (group['volatility_6h'] > purple_threshold) & quarter_mask

            if purple_mask.sum() > 0:
                # Find continuous purple regions
                purple_indices = group[purple_mask].index.tolist()

                # Group consecutive indices
                purple_regions = []
                if purple_indices:
                    start_idx = purple_indices[0]
                    prev_idx = purple_indices[0]

                    for idx in purple_indices[1:]:
                        if idx != prev_idx + 1:
                            # End of region
                            purple_regions.append({
                                'pool_id': pool_id,
                                'instance_type': inst_type,
                                'availability_zone': az,
                                'quarter': str(quarter),
                                'start_time': group.loc[start_idx, 'timestamp'],
                                'end_time': group.loc[prev_idx, 'timestamp'],
                                'duration_hours': prev_idx - start_idx + 1,
                                'max_volatility': group.loc[start_idx:prev_idx, 'volatility_6h'].max(),
                                'baseline': quarter_baseline,
                                'threshold': purple_threshold
                            })
                            start_idx = idx
                        prev_idx = idx

                    # Add final region
                    purple_regions.append({
                        'pool_id': pool_id,
                        'instance_type': inst_type,
                        'availability_zone': az,
                        'quarter': str(quarter),
                        'start_time': group.loc[start_idx, 'timestamp'],
                        'end_time': group.loc[prev_idx, 'timestamp'],
                        'duration_hours': prev_idx - start_idx + 1,
                        'max_volatility': group.loc[start_idx:prev_idx, 'volatility_6h'].max(),
                        'baseline': quarter_baseline,
                        'threshold': purple_threshold
                    })

                purple_zones.extend(purple_regions)

    purple_df = pd.DataFrame(purple_zones)

    if len(purple_df) > 0:
        print(f"\n  ✓ Found {len(purple_df)} purple zones (volatility spikes)")
        print(f"  📊 Purple zone statistics:")
        print(f"     Average duration: {purple_df['duration_hours'].mean():.1f} hours")
        print(f"     Max duration: {purple_df['duration_hours'].max():.0f} hours")
        print(f"     Total purple hours: {purple_df['duration_hours'].sum():.0f}")
    else:
        print(f"\n  ⚠️  No purple zones found (data may be very stable)")
        purple_df = pd.DataFrame(columns=['pool_id', 'start_time', 'end_time', 'duration_hours'])

    return purple_df

# ============================================================================
# 3. ASSIGN ZONES TO DATA
# ============================================================================

def assign_zones_to_data(df, zones_df, purple_df=None):
    """
    Assign zone labels (green/yellow/orange/red/purple) to each row
    """
    print("\n🏷️  Assigning zones to data...")

    df = df.copy()
    df['pool_id'] = df['instance_type'] + '_' + df['availability_zone']
    df['zone'] = 'unknown'
    df['is_purple'] = False

    # Merge zone thresholds
    df = df.merge(zones_df[['pool_id', 'green_max', 'yellow_max', 'orange_max', 'red_max']],
                  on='pool_id', how='left')

    # Assign color zones based on spot price
    df.loc[df['spot_price'] <= df['green_max'], 'zone'] = 'green'
    df.loc[(df['spot_price'] > df['green_max']) & (df['spot_price'] <= df['yellow_max']), 'zone'] = 'yellow'
    df.loc[(df['spot_price'] > df['yellow_max']) & (df['spot_price'] <= df['orange_max']), 'zone'] = 'orange'
    df.loc[df['spot_price'] > df['orange_max'], 'zone'] = 'red'

    # Mark purple zones (volatility spikes)
    if purple_df is not None and len(purple_df) > 0:
        for _, purple_row in purple_df.iterrows():
            purple_mask = (
                (df['pool_id'] == purple_row['pool_id']) &
                (df['timestamp'] >= purple_row['start_time']) &
                (df['timestamp'] <= purple_row['end_time'])
            )
            df.loc[purple_mask, 'is_purple'] = True

    # Calculate zone distribution
    zone_dist = df['zone'].value_counts()
    purple_count = df['is_purple'].sum()

    print(f"  ✓ Zone distribution:")
    print(f"     Green:  {zone_dist.get('green', 0):,} rows ({zone_dist.get('green', 0)/len(df)*100:.1f}%)")
    print(f"     Yellow: {zone_dist.get('yellow', 0):,} rows ({zone_dist.get('yellow', 0)/len(df)*100:.1f}%)")
    print(f"     Orange: {zone_dist.get('orange', 0):,} rows ({zone_dist.get('orange', 0)/len(df)*100:.1f}%)")
    print(f"     Red:    {zone_dist.get('red', 0):,} rows ({zone_dist.get('red', 0)/len(df)*100:.1f}%)")
    print(f"     Purple: {purple_count:,} rows ({purple_count/len(df)*100:.1f}%) [volatility spikes]")

    return df

# ============================================================================
# 4. POOL RANKING (Green Time + Discount + Stability)
# ============================================================================

def rank_pools_by_safety_and_discount(df):
    """
    Rank pools by:
    1. Time spent in green zone (60% weight)
    2. Average discount percentage (30% weight)
    3. Price stability (10% weight)

    Returns: DataFrame with pool rankings and scores
    """
    print("\n🏆 Ranking pools by safety + discount + stability...")
    print(f"  📊 Weighting: 60% green time, 30% discount, 10% stability")

    pool_rankings = []

    for pool_id, group in df.groupby('pool_id'):
        # Metric 1: Green zone time (percentage)
        green_pct = (group['zone'] == 'green').sum() / len(group) * 100

        # Metric 2: Average discount
        avg_discount = group['discount_pct'].mean()

        # Metric 3: Price stability (inverse of coefficient of variation)
        cv = group['spot_price'].std() / group['spot_price'].mean()
        stability = 1 / (1 + cv)  # Normalize to 0-1, higher = more stable

        # Purple zone penalty (reduce score if many volatility spikes)
        purple_pct = group['is_purple'].sum() / len(group) * 100
        purple_penalty = purple_pct * 2  # 2% penalty per 1% purple time

        # Composite score (0-100)
        score = (
            green_pct * 0.60 +           # 60% weight on green time
            avg_discount * 0.30 +        # 30% weight on discount
            stability * 100 * 0.10       # 10% weight on stability
            - purple_penalty             # Penalty for volatility
        )

        pool_rankings.append({
            'pool_id': pool_id,
            'instance_type': pool_id.split('_')[0],
            'availability_zone': pool_id.split('_')[1],
            'green_pct': green_pct,
            'avg_discount': avg_discount,
            'stability': stability,
            'purple_pct': purple_pct,
            'composite_score': score,
            'avg_price': group['spot_price'].mean(),
            'total_hours': len(group)
        })

    rankings_df = pd.DataFrame(pool_rankings)
    rankings_df = rankings_df.sort_values('composite_score', ascending=False).reset_index(drop=True)
    rankings_df['rank'] = range(1, len(rankings_df) + 1)

    print(f"\n  ✓ Pool rankings (Top 5):")
    for i, row in rankings_df.head(5).iterrows():
        print(f"     #{row['rank']}: {row['pool_id']}")
        print(f"         Score: {row['composite_score']:.1f}/100")
        print(f"         Green: {row['green_pct']:.1f}% | Discount: {row['avg_discount']:.1f}% | Stability: {row['stability']:.3f}")
        print(f"         Purple: {row['purple_pct']:.1f}% | Avg Price: ${row['avg_price']:.4f}")

    return rankings_df

# ============================================================================
# 5. ABNORMALITY DETECTION (Isolation Forest)
# ============================================================================

def train_abnormality_detector(df):
    """
    Train Isolation Forest to detect price/volatility anomalies
    Features: spot_price, discount_pct, volatility_24h, zone
    """
    print("\n🔮 Training abnormality detection model...")

    # Prepare features
    df_model = df.copy()
    df_model['zone_encoded'] = pd.Categorical(df_model['zone'],
                                               categories=['green', 'yellow', 'orange', 'red']).codes

    features = ['spot_price', 'discount_pct', 'volatility_24h', 'zone_encoded',
                'price_velocity_1h', 'spike_count_24h']

    # Handle missing values
    df_model[features] = df_model[features].fillna(df_model[features].median())

    X = df_model[features].values

    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train Isolation Forest
    iso_forest = IsolationForest(
        contamination=0.05,  # Expect 5% anomalies
        random_state=CONFIG['random_seed'],
        n_jobs=-1
    )
    iso_forest.fit(X_scaled)

    # Predict anomalies
    predictions = iso_forest.predict(X_scaled)
    anomaly_scores = iso_forest.score_samples(X_scaled)

    df_model['is_anomaly'] = (predictions == -1)
    df_model['anomaly_score'] = anomaly_scores

    anomaly_count = df_model['is_anomaly'].sum()
    print(f"  ✓ Detected {anomaly_count:,} anomalies ({anomaly_count/len(df_model)*100:.2f}%)")

    return iso_forest, scaler, features

# ============================================================================
# 6. SMART SWITCHING (Zone-Based + Abnormality Prediction)
# ============================================================================

def backtest_smart_switching(df_test, zones_df, rankings_df, iso_forest, scaler, features):
    """
    Backtest smart switching strategy on 2025 data

    Switching triggers:
    1. Current pool exits green zone
    2. Current pool enters purple zone (volatility spike)
    3. Abnormality predicted in next hour

    Switch to: Highest-ranked pool currently in green zone
    """
    print("\n🔄 Backtesting smart switching strategy on 2025 data...")
    print(f"  🎯 Switching triggers:")
    print(f"     1. Exit green zone")
    print(f"     2. Enter purple zone (volatility spike)")
    print(f"     3. Abnormality predicted (next hour)")
    print(f"  💰 Switching cost: ${CONFIG['switching_cost']:.2f} per switch")

    df = df_test.copy()

    # Assign zones to test data
    df = assign_zones_to_data(df, zones_df)

    # Predict abnormalities
    df['zone_encoded'] = pd.Categorical(df['zone'],
                                         categories=['green', 'yellow', 'orange', 'red']).codes
    df[features] = df[features].fillna(df[features].median())
    X_test = df[features].values
    X_test_scaled = scaler.transform(X_test)
    df['predicted_anomaly'] = (iso_forest.predict(X_test_scaled) == -1)

    # Initialize switching simulation
    timestamps = sorted(df['timestamp'].unique())
    current_pool = rankings_df.iloc[0]['pool_id']  # Start with top-ranked pool

    switches = []
    costs = []

    for i, ts in enumerate(tqdm(timestamps[:-1], desc="  Simulating switches")):
        current_data = df[(df['timestamp'] == ts) & (df['pool_id'] == current_pool)]

        if len(current_data) == 0:
            continue

        current_row = current_data.iloc[0]

        # Check switching triggers
        should_switch = False
        switch_reason = None

        # Trigger 1: Exit green zone
        if current_row['zone'] != 'green':
            should_switch = True
            switch_reason = f"exit_green_{current_row['zone']}"

        # Trigger 2: Purple zone (volatility spike)
        if current_row['is_purple']:
            should_switch = True
            switch_reason = "purple_zone"

        # Trigger 3: Predicted abnormality
        if current_row['predicted_anomaly']:
            should_switch = True
            switch_reason = "predicted_abnormaly"

        if should_switch:
            # Find best alternative pool (highest-ranked, currently in green)
            alternative_pools = df[df['timestamp'] == ts].copy()
            alternative_pools = alternative_pools.merge(
                rankings_df[['pool_id', 'composite_score']],
                on='pool_id',
                how='left'
            )
            alternative_pools = alternative_pools[alternative_pools['zone'] == 'green']
            alternative_pools = alternative_pools.sort_values('composite_score', ascending=False)

            if len(alternative_pools) > 0:
                new_pool = alternative_pools.iloc[0]['pool_id']

                if new_pool != current_pool:
                    switches.append({
                        'timestamp': ts,
                        'from_pool': current_pool,
                        'to_pool': new_pool,
                        'reason': switch_reason,
                        'from_price': current_row['spot_price'],
                        'to_price': alternative_pools.iloc[0]['spot_price'],
                        'from_zone': current_row['zone'],
                        'to_zone': alternative_pools.iloc[0]['zone']
                    })

                    costs.append(CONFIG['switching_cost'])
                    current_pool = new_pool

        # Track hourly cost
        hourly_data = df[(df['timestamp'] == ts) & (df['pool_id'] == current_pool)]
        if len(hourly_data) > 0:
            costs.append(hourly_data.iloc[0]['spot_price'])

    switches_df = pd.DataFrame(switches)

    print(f"\n  ✓ Backtesting complete:")
    print(f"     Total switches: {len(switches_df)}")
    if len(switches_df) > 0:
        print(f"     Switch reasons:")
        for reason, count in switches_df['reason'].value_counts().items():
            print(f"       - {reason}: {count}")
        print(f"     Total switching cost: ${len(switches_df) * CONFIG['switching_cost']:.2f}")

    # Calculate baseline (no switching - stay on initial pool)
    baseline_pool = rankings_df.iloc[0]['pool_id']
    baseline_costs = df[df['pool_id'] == baseline_pool].groupby('timestamp')['spot_price'].first()

    # Calculate actual costs with switching
    actual_cost_total = sum(costs)
    baseline_cost_total = baseline_costs.sum()
    savings = baseline_cost_total - actual_cost_total
    savings_pct = (savings / baseline_cost_total) * 100

    print(f"\n  💰 Cost comparison:")
    print(f"     Baseline (no switching): ${baseline_cost_total:.2f}")
    print(f"     With smart switching:    ${actual_cost_total:.2f}")
    print(f"     Savings:                 ${savings:.2f} ({savings_pct:.2f}%)")

    return switches_df, {
        'actual_cost': actual_cost_total,
        'baseline_cost': baseline_cost_total,
        'savings': savings,
        'savings_pct': savings_pct,
        'total_switches': len(switches_df)
    }

# ============================================================================
# 7. VISUALIZATION
# ============================================================================

def plot_zone_timeline(df, pool_id, zones_df, purple_df, save_path):
    """Plot price timeline with colored zones for a specific pool"""

    pool_data = df[df['pool_id'] == pool_id].sort_values('timestamp')
    zone_thresholds = zones_df[zones_df['pool_id'] == pool_id].iloc[0]

    fig, ax = plt.subplots(figsize=(16, 6))

    # Plot price line
    ax.plot(pool_data['timestamp'], pool_data['spot_price'],
            color='black', linewidth=1, label='Spot Price', zorder=5)

    # Fill zone areas
    ax.axhspan(0, zone_thresholds['green_max'],
               color='green', alpha=0.2, label='Green Zone (P70)')
    ax.axhspan(zone_thresholds['green_max'], zone_thresholds['yellow_max'],
               color='yellow', alpha=0.2, label='Yellow Zone (P90)')
    ax.axhspan(zone_thresholds['yellow_max'], zone_thresholds['orange_max'],
               color='orange', alpha=0.2, label='Orange Zone (P95)')
    ax.axhspan(zone_thresholds['orange_max'], zone_thresholds['red_max'],
               color='red', alpha=0.2, label='Red Zone (Max+10%)')

    # Mark purple zones (volatility spikes)
    if purple_df is not None and len(purple_df) > 0:
        pool_purple = purple_df[purple_df['pool_id'] == pool_id]
        for _, purple_row in pool_purple.iterrows():
            ax.axvspan(purple_row['start_time'], purple_row['end_time'],
                      color='purple', alpha=0.3, zorder=3)

    ax.set_xlabel('Timestamp', fontsize=12)
    ax.set_ylabel('Spot Price ($)', fontsize=12)
    ax.set_title(f'Zone Timeline: {pool_id}', fontsize=14, fontweight='bold')
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()

def create_zone_visualizations(df_train, df_test, zones_df, purple_df, rankings_df):
    """Create comprehensive zone visualizations"""
    print("\n📊 Creating zone visualizations...")

    # 1. Plot top 3 pools zone timelines (training data)
    for i, row in rankings_df.head(3).iterrows():
        pool_id = row['pool_id']
        save_path = Path(CONFIG['zone_plots_dir']) / f'zone_timeline_{pool_id}_train.png'
        plot_zone_timeline(df_train, pool_id, zones_df, purple_df, save_path)

    print(f"  ✓ Created zone timeline plots in {CONFIG['zone_plots_dir']}/")

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print("\n" + "="*80)
    print("STARTING ZONE-BASED RISK PREDICTION AND SWITCHING ANALYSIS")
    print("="*80)

    # 1. Load data
    df_train, df_test = load_data()

    # 2. Calculate zones (only on training data 2023-24)
    zones_df = calculate_pool_zones(df_train)
    purple_df = calculate_quarterly_purple_zones(df_train)

    # 3. Assign zones to training data
    df_train = assign_zones_to_data(df_train, zones_df, purple_df)

    # 4. Rank pools
    rankings_df = rank_pools_by_safety_and_discount(df_train)

    # 5. Train abnormality detector
    iso_forest, scaler, features = train_abnormality_detector(df_train)

    # 6. Backtest on 2025 data
    switches_df, metrics = backtest_smart_switching(
        df_test, zones_df, rankings_df, iso_forest, scaler, features
    )

    # 7. Create visualizations
    create_zone_visualizations(df_train, df_test, zones_df, purple_df, rankings_df)

    # 8. Save results
    print("\n💾 Saving results...")
    zones_df.to_csv(Path(CONFIG['output_dir']) / 'pool_zones.csv', index=False)
    purple_df.to_csv(Path(CONFIG['output_dir']) / 'purple_zones.csv', index=False)
    rankings_df.to_csv(Path(CONFIG['output_dir']) / 'pool_rankings.csv', index=False)
    switches_df.to_csv(Path(CONFIG['output_dir']) / 'switching_decisions.csv', index=False)

    with open(Path(CONFIG['output_dir']) / 'switching_metrics.txt', 'w') as f:
        f.write("SMART SWITCHING METRICS (2025 Backtest)\n")
        f.write("="*50 + "\n\n")
        f.write(f"Baseline Cost (no switching): ${metrics['baseline_cost']:.2f}\n")
        f.write(f"Actual Cost (with switching): ${metrics['actual_cost']:.2f}\n")
        f.write(f"Total Savings:                ${metrics['savings']:.2f}\n")
        f.write(f"Savings Percentage:           {metrics['savings_pct']:.2f}%\n")
        f.write(f"Total Switches:               {metrics['total_switches']}\n")

    print(f"  ✓ Saved results to {CONFIG['output_dir']}/")

    print("\n" + "="*80)
    print("ZONE-BASED ANALYSIS COMPLETE")
    print("="*80)
    print(f"End Time: {datetime.now()}")
    print(f"\n📊 Summary:")
    print(f"  - Calculated zones for {len(zones_df)} pools")
    print(f"  - Found {len(purple_df)} purple zones (volatility spikes)")
    print(f"  - Performed {metrics['total_switches']} smart switches")
    print(f"  - Achieved {metrics['savings_pct']:.2f}% cost savings")
    print(f"\n📁 Results saved to: {CONFIG['output_dir']}/")
    print("="*80)

if __name__ == "__main__":
    main()
