"""
Family Stress Hardware Contagion System
========================================

CORE PHILOSOPHY:
- Standard models assume instance independence
- This model assumes PHYSICAL DEPENDENCE
- Hypothesis: c5.large and c5.12xlarge compete for same silicon
- When large instances spike, AWS defragments hosts, evicting smaller instances
- Result: "Family Stress" predicts child instance failure even with flat prices

TARGET: Binary Classification - "Is this environment hostile?"
FEATURES: Hardware-aware stress signals (not just volatility)
ALGORITHM: LightGBM Binary Classifier
OPTIMIZED FOR: MacBook Air M4 (16GB RAM, <15min runtime)
"""

import sys
import warnings
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm

from lightgbm import LGBMClassifier
from sklearn.metrics import (
    precision_recall_curve, auc, precision_score, recall_score,
    f1_score, roc_auc_score, confusion_matrix
)

warnings.filterwarnings('ignore')
sns.set_style('whitegrid')

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    # Data paths
    'training_data': '/Users/atharvapudale/Downloads/aws_mumbai_2023_all.csv',
    'test_data': '/Users/atharvapudale/Downloads/aws_mumbai_2024_all.csv',

    # M4 MacBook Air Optimizations
    'use_float32': True,  # Half memory vs float64
    'use_categorical_dtypes': True,
    'chunk_size': 100000,  # Load in chunks
    'max_execution_minutes': 15,

    # Family definitions (hardware dependency groups)
    'families': {
        'c5': {
            'target': 'c5.large',
            'signals': ['c5.xlarge', 'c5.2xlarge', 'c5.4xlarge', 'c5.9xlarge',
                       'c5.12xlarge', 'c5.24xlarge', 'c5.metal']
        },
        't4g': {
            'target': 't4g.small',
            'signals': ['t4g.medium', 't4g.large', 't4g.xlarge', 't4g.2xlarge']
        },
        't3': {
            'target': 't3.medium',
            'signals': ['t3.large', 't3.xlarge', 't3.2xlarge']
        }
    },

    # Static On-Demand prices (AWS Mumbai region)
    # CRITICAL: Do NOT use spot_price * 4 - that makes discount always 75%!
    'on_demand_prices': {
        # C5 family (Compute Optimized)
        'c5.large': 0.096,
        'c5.xlarge': 0.192,
        'c5.2xlarge': 0.384,
        'c5.4xlarge': 0.768,
        'c5.9xlarge': 1.728,
        'c5.12xlarge': 2.304,
        'c5.18xlarge': 3.456,
        'c5.24xlarge': 4.608,
        'c5.metal': 4.608,
        # T4g family (ARM, Burstable)
        't4g.nano': 0.0042,
        't4g.micro': 0.0084,
        't4g.small': 0.0168,
        't4g.medium': 0.0336,
        't4g.large': 0.0672,
        't4g.xlarge': 0.1344,
        't4g.2xlarge': 0.2688,
        # T3 family (Burstable)
        't3.nano': 0.0066,
        't3.micro': 0.0132,
        't3.small': 0.0264,
        't3.medium': 0.0528,
        't3.large': 0.1056,
        't3.xlarge': 0.2112,
        't3.2xlarge': 0.4224,
    },

    # Target definition
    'spike_threshold': 0.01,  # REDUCED: 1% (Mumbai data is very stable!)
    'lookahead_hours': 6,     # Predict 6 hours ahead
    'lookahead_intervals': 36,  # 6 hours / 10 min intervals

    # Feature windows
    'price_position_window_days': 7,  # REDUCED: 7-day (30-day too stable)

    # Model hyperparameters
    'model_params': {
        'objective': 'binary',
        'metric': 'auc',
        'n_estimators': 200,
        'num_leaves': 31,
        'max_depth': 6,
        'learning_rate': 0.05,
        'feature_fraction': 0.8,
        'bagging_fraction': 0.8,
        'bagging_freq': 5,
        'verbose': -1,
        'random_state': 42,
        'n_jobs': -1
    },

    # Decision threshold (optimized for safety over cost)
    'decision_threshold': 0.4,  # Mark as unsafe if P(unstable) > 40%

    # Output
    'output_dir': './training/outputs',
    'plots_dir': './training/plots',
    'model_path': './models/uploaded/family_stress_model.pkl'
}

# Create directories
for dir_path in [CONFIG['output_dir'], CONFIG['plots_dir'], Path(CONFIG['model_path']).parent]:
    Path(dir_path).mkdir(parents=True, exist_ok=True)

print("="*80)
print("FAMILY STRESS HARDWARE CONTAGION SYSTEM")
print("="*80)
print(f"Start Time: {datetime.now()}")
print(f"Platform: MacBook Air M4 (16GB RAM)")
print(f"Target Runtime: <{CONFIG['max_execution_minutes']} minutes")
print(f"Optimization: float32, categorical dtypes, chunked loading")
print("="*80)

# ============================================================================
# 1. MEMORY-EFFICIENT DATA LOADING
# ============================================================================

def standardize_columns(df):
    """Standardize column names across different CSV formats"""
    df.columns = df.columns.str.lower().str.strip()

    # Find the first matching column for each type
    timestamp_col = None
    instance_type_col = None
    az_col = None
    price_col = None

    for col in df.columns:
        col_lower = col.lower()
        if timestamp_col is None and any(x in col_lower for x in ['time', 'date', 'timestamp']):
            timestamp_col = col
        elif instance_type_col is None and any(x in col_lower for x in ['instance', 'type']):
            instance_type_col = col
        elif az_col is None and any(x in col_lower for x in ['availability', 'zone', 'az']):
            az_col = col
        # CRITICAL: Match 'spot' specifically (not just 'price') to avoid OndemandPrice
        elif price_col is None and 'spot' in col_lower:
            price_col = col

    # Build mapping
    col_mapping = {}
    if timestamp_col:
        col_mapping[timestamp_col] = 'timestamp'
    if instance_type_col:
        col_mapping[instance_type_col] = 'instance_type'
    if az_col:
        col_mapping[az_col] = 'availability_zone'
    if price_col:
        col_mapping[price_col] = 'spot_price'

    # Diagnostic output
    print(f"  📋 Column mapping:")
    print(f"    Timestamp: '{timestamp_col}' → 'timestamp'")
    print(f"    Instance: '{instance_type_col}' → 'instance_type'")
    print(f"    AZ: '{az_col}' → 'availability_zone'")
    print(f"    Price: '{price_col}' → 'spot_price'")

    # Warn if reading wrong column
    if price_col and 'ondemand' in price_col.lower():
        print(f"\n  ⚠️  WARNING: Reading '{price_col}' which appears to be ON-DEMAND prices!")
        print(f"     On-demand prices are FIXED (no variance per instance).")
        print(f"     Looking for 'SpotPrice' column instead...")
        # Try to find spot price column
        for col in df.columns:
            if 'spot' in col.lower() and 'price' in col.lower():
                price_col = col
                col_mapping[price_col] = 'spot_price'
                print(f"     ✓ Found and using '{price_col}' instead!")
                break

    # Rename columns
    df = df.rename(columns=col_mapping)

    # Keep ONLY the standardized columns we need (this drops everything else)
    required_cols = ['timestamp', 'instance_type', 'availability_zone', 'spot_price']
    existing_cols = [c for c in required_cols if c in df.columns]

    # Select only these columns (drops all others including any duplicates)
    df = df[existing_cols].copy()

    return df

def load_data_efficient(file_path, families_config, is_training=True):
    """
    M4 OPTIMIZATION: Load only required families, use efficient dtypes
    """
    print(f"\n📂 Loading {'training' if is_training else 'test'} data...")
    print(f"  File: {Path(file_path).name}")

    # Get all instance types we care about
    required_instances = set()
    for family_data in families_config.values():
        required_instances.add(family_data['target'])
        required_instances.update(family_data['signals'])

    print(f"  Required instances: {len(required_instances)}")

    # Load in chunks, filter early
    chunks = []
    total_rows_before = 0
    total_rows_after = 0

    for chunk in tqdm(pd.read_csv(file_path, chunksize=CONFIG['chunk_size']),
                      desc="  Loading chunks"):
        chunk = standardize_columns(chunk)
        total_rows_before += len(chunk)

        # Filter to required instances BEFORE concatenating
        chunk = chunk[chunk['instance_type'].isin(required_instances)]
        total_rows_after += len(chunk)

        if len(chunk) > 0:
            chunks.append(chunk)

    df = pd.concat(chunks, ignore_index=True)

    print(f"  Rows before filter: {total_rows_before:,}")
    print(f"  Rows after filter: {total_rows_after:,} ({total_rows_after/total_rows_before*100:.1f}%)")

    # Quick variance check to confirm we're reading spot prices (not on-demand)
    if 'spot_price' in df.columns:
        price_std = df['spot_price'].std()
        price_range = df['spot_price'].max() - df['spot_price'].min()
        print(f"\n  📊 Spot Price Variance Check:")
        print(f"    Min: ${df['spot_price'].min():.4f}")
        print(f"    Max: ${df['spot_price'].max():.4f}")
        print(f"    Range: ${price_range:.4f}")
        print(f"    Std: ${price_std:.6f}")

        if price_std < 0.001:
            print(f"\n    ⚠️  WARNING: Spot prices have very low variance (std < $0.001)!")
            print(f"       This might indicate on-demand prices were loaded instead of spot prices.")
            print(f"       Check that CSV has a 'SpotPrice' column with varying prices.")
        else:
            print(f"    ✓ Spot prices have reasonable variance!")

    # Remove duplicate columns if they exist (safety check)
    if not df.columns.is_unique:
        print(f"  ⚠️  Found duplicate columns, removing...")
        df = df.loc[:, ~df.columns.duplicated()]
        print(f"  ✓ Columns after dedup: {list(df.columns)}")

    # Optimize dtypes - handle mixed datetime formats
    print(f"  Converting timestamps (handling mixed formats)...")
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', errors='coerce')

    # Check for failed conversions
    failed_timestamps = df['timestamp'].isna().sum()
    if failed_timestamps > 0:
        print(f"  ⚠️  {failed_timestamps:,} timestamps failed to parse (will be dropped)")
        df = df.dropna(subset=['timestamp'])

    print(f"  ✓ Final rows: {len(df):,}")

    if CONFIG['use_float32']:
        df['spot_price'] = df['spot_price'].astype('float32')

    if CONFIG['use_categorical_dtypes']:
        df['instance_type'] = df['instance_type'].astype('category')
        df['availability_zone'] = df['availability_zone'].astype('category')

    # Add on-demand price (STATIC from AWS pricing, NOT spot*4!)
    df['on_demand_price'] = df['instance_type'].map(CONFIG['on_demand_prices'])
    # Fallback for missing types
    missing_mask = df['on_demand_price'].isna()
    if missing_mask.sum() > 0:
        print(f"  ⚠️  {missing_mask.sum()} rows missing on-demand price, using fallback (spot*4)")
        df.loc[missing_mask, 'on_demand_price'] = df.loc[missing_mask, 'spot_price'] * 4.0

    if CONFIG['use_float32']:
        df['on_demand_price'] = df['on_demand_price'].astype('float32')

    print(f"  ✓ Loaded: {len(df):,} rows")
    print(f"  Memory: {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")

    return df

# ============================================================================
# 2. TIME SYNCHRONIZATION (Fix async updates)
# ============================================================================

def create_market_snapshots(df, freq='10T'):
    """
    Create synchronized market state matrix
    - Every row = timestamp
    - Columns = features for all pools
    - Forward fill missing values (flat lines are valid)
    """
    print(f"\n🔄 Creating market snapshots ({freq} intervals)...")

    df = df.sort_values(['instance_type', 'availability_zone', 'timestamp'])
    df['pool_id'] = df['instance_type'].astype(str) + '_' + df['availability_zone'].astype(str)

    # Resample each pool
    resampled = []
    for pool_id, group in tqdm(df.groupby('pool_id'), desc="  Resampling pools"):
        group = group.set_index('timestamp')
        group_resampled = group.resample(freq).ffill()  # Forward fill
        group_resampled['pool_id'] = pool_id
        group_resampled['instance_type'] = group['instance_type'].iloc[0]
        group_resampled['availability_zone'] = group['availability_zone'].iloc[0]
        resampled.append(group_resampled)

    df_sync = pd.concat(resampled).reset_index()

    print(f"  Before: {len(df):,} rows (event-driven)")
    print(f"  After: {len(df_sync):,} rows (time-synchronized)")

    return df_sync

# ============================================================================
# 3. TARGET VARIABLE: Is_Unstable_Next_6H
# ============================================================================

def create_target_variable(df, spike_threshold=0.10, lookahead=36):
    """
    Binary target: Is_Unstable_Next_6H (VECTORIZED VERSION)

    Y_t = 1 if:
        max(Price_{t+1...t+36}) > (1 + threshold) * Price_t

    Uses rolling().max() with shift - NO LOOPS!
    """
    print(f"\n🎯 Creating target variable (VECTORIZED)...")
    print(f"  Spike threshold: {spike_threshold*100}%")
    print(f"  Lookahead: {lookahead} intervals (6 hours)")

    df = df.sort_values(['pool_id', 'timestamp']).copy()

    # VECTORIZED: Calculate future max for every row instantly
    # Step 1: Shift forward by 1 (skip current), then rolling max over lookahead window
    df['future_max_price'] = (
        df.groupby('pool_id')['spot_price']
        .shift(-1)  # Start from next timestamp
        .rolling(window=lookahead, min_periods=1)
        .max()
        .shift(lookahead - 1)  # Align back to current row
    )

    # Step 2: Compare current price vs future max
    df['is_unstable_next_6h'] = (
        df['future_max_price'] > df['spot_price'] * (1 + spike_threshold)
    ).astype(int)

    # Step 3: Remove rows where we don't have future data
    rows_before = len(df)
    df = df.dropna(subset=['future_max_price'])
    rows_dropped = rows_before - len(df)

    positive_count = df['is_unstable_next_6h'].sum()
    positive_pct = positive_count / len(df) * 100 if len(df) > 0 else 0

    print(f"  ✓ Target created (dropped {rows_dropped:,} rows without future)")
    print(f"  Unstable samples: {positive_count:,} ({positive_pct:.2f}%)")
    print(f"  Stable samples: {len(df) - positive_count:,} ({100-positive_pct:.2f}%)")

    # Calculate scale_pos_weight for imbalanced data
    scale_pos_weight = (len(df) - positive_count) / positive_count if positive_count > 0 else 1.0
    print(f"  Recommended scale_pos_weight: {scale_pos_weight:.2f}")

    # Clean up temporary column
    df = df.drop(columns=['future_max_price'])

    return df, scale_pos_weight

# ============================================================================
# 4. FEATURE ENGINEERING: Hardware-Aware Stress Signals
# ============================================================================

def calculate_price_position(df, window_days=7):
    """
    A. Price Position (Normalized Pressure)

    P_pos = (P_current - P_min_7d) / (P_max_7d - P_min_7d + ε)

    Interpretation:
    - 0.0 = Cheapest price recently (safe)
    - 1.0 = Most expensive price recently (dangerous)
    """
    print(f"\n📊 Calculating Price Position ({window_days}-day window)...")

    df = df.sort_values(['pool_id', 'timestamp']).copy()
    window = window_days * 24 * 6  # Convert to 10-min intervals

    # Diagnostic: Check actual price ranges
    print(f"  Diagnostic: Checking price volatility...")
    for pool_id in df['pool_id'].unique()[:3]:  # Check first 3 pools
        pool_prices = df[df['pool_id'] == pool_id]['spot_price']
        print(f"    {pool_id}: min=${pool_prices.min():.4f}, max=${pool_prices.max():.4f}, range=${pool_prices.max()-pool_prices.min():.4f}")

    df['price_min_7d'] = df.groupby('pool_id')['spot_price'].transform(
        lambda x: x.rolling(window=window, min_periods=max(1, window//10)).min()
    )
    df['price_max_7d'] = df.groupby('pool_id')['spot_price'].transform(
        lambda x: x.rolling(window=window, min_periods=max(1, window//10)).max()
    )

    # Calculate range
    df['price_range'] = df['price_max_7d'] - df['price_min_7d']

    # Use adaptive epsilon based on price magnitude
    epsilon = df['spot_price'].median() * 0.001  # 0.1% of median price
    print(f"  Using epsilon: {epsilon:.6f}")

    df['price_position'] = (
        (df['spot_price'] - df['price_min_7d']) /
        (df['price_range'] + epsilon)
    )

    # Clip to [0, 1]
    df['price_position'] = df['price_position'].clip(0, 1).astype('float32' if CONFIG['use_float32'] else 'float64')

    # Diagnostic output
    zero_range_count = (df['price_range'] < epsilon).sum()
    if zero_range_count > 0:
        print(f"  ⚠️  {zero_range_count:,} rows ({zero_range_count/len(df)*100:.1f}%) have near-zero price range (very stable)")

    print(f"  ✓ Price Position calculated")
    print(f"  Mean: {df['price_position'].mean():.3f}")
    print(f"  Std: {df['price_position'].std():.3f}")
    print(f"  Min: {df['price_position'].min():.3f}, Max: {df['price_position'].max():.3f}")

    # Clean up temp columns
    df = df.drop(columns=['price_min_7d', 'price_max_7d', 'price_range'])

    return df

def calculate_price_velocity(df):
    """
    Price Velocity (Rate of Change) - Alternative for stable markets

    Captures small price movements that position might miss.

    velocity = (P_current - P_1h_ago) / P_1h_ago
    volatility = rolling std dev over 6 hours
    """
    print(f"\n📈 Calculating Price Velocity & Volatility (backup features)...")

    df = df.sort_values(['pool_id', 'timestamp']).copy()

    # Price velocity: % change over last hour (6 intervals)
    df['price_velocity_1h'] = df.groupby('pool_id')['spot_price'].transform(
        lambda x: x.pct_change(periods=6).fillna(0)
    )

    # Rolling volatility: std dev over 6 hours (36 intervals)
    df['price_volatility_6h'] = df.groupby('pool_id')['spot_price'].transform(
        lambda x: x.rolling(window=36, min_periods=6).std().fillna(0)
    )

    # Normalize volatility by current price (coefficient of variation)
    df['price_cv_6h'] = (df['price_volatility_6h'] / (df['spot_price'] + 1e-8)).fillna(0)

    # Convert to float32
    if CONFIG['use_float32']:
        df['price_velocity_1h'] = df['price_velocity_1h'].astype('float32')
        df['price_volatility_6h'] = df['price_volatility_6h'].astype('float32')
        df['price_cv_6h'] = df['price_cv_6h'].astype('float32')

    print(f"  ✓ Price Velocity calculated")
    print(f"  Velocity Mean: {df['price_velocity_1h'].mean():.6f}, Std: {df['price_velocity_1h'].std():.6f}")
    print(f"  Volatility Mean: {df['price_volatility_6h'].mean():.6f}, Std: {df['price_volatility_6h'].std():.6f}")
    print(f"  CV Mean: {df['price_cv_6h'].mean():.6f}, Std: {df['price_cv_6h'].std():.6f}")

    return df

def calculate_discount_depth(df):
    """
    B. Discount Depth (Economic Buffer)

    D_depth = 1 - (P_spot / P_on_demand)

    Interpretation:
    - 0.05 = Only 5% savings (extreme risk)
    - 0.70 = 70% savings (high safety)
    """
    print(f"\n💰 Calculating Discount Depth...")

    df['discount_depth'] = (1 - (df['spot_price'] / df['on_demand_price'])).astype('float32' if CONFIG['use_float32'] else 'float64')
    df['discount_depth'] = df['discount_depth'].clip(0, 1)

    print(f"  ✓ Discount Depth calculated")
    print(f"  Mean: {df['discount_depth'].mean():.3f}")
    print(f"  Std: {df['discount_depth'].std():.3f}")

    return df

def calculate_family_stress_index(df, families_config):
    """
    C. Family Stress Index (Hardware Contagion) - VECTORIZED VERSION

    S_family = (1/|F|) * Σ P_pos(i) for i in Family F

    Uses pivot_table - aligns timestamps instantly without loops!
    100-1000x faster than nested loops.
    """
    print(f"\n🔥 Calculating Family Stress Index (VECTORIZED - Pivot Table)...")

    df['family_stress'] = 0.0

    # Create a wide pivot table: Index=(timestamp, AZ), Columns=instance_type, Values=price_position
    # This aligns all instances at each timestamp instantly
    print(f"  Creating pivot table...")
    pivot = df.pivot_table(
        index=['timestamp', 'availability_zone'],
        columns='instance_type',
        values='price_position',
        aggfunc='mean'  # In case of duplicates
    )

    for family_name, family_data in families_config.items():
        target = family_data['target']
        signal_instances = family_data['signals']
        all_members = [target] + signal_instances

        print(f"  Processing {family_name} family...")
        print(f"    Target: {target}")
        print(f"    Signals: {len(signal_instances)} instances")

        # Filter pivot to only columns in this family (handle missing cols)
        valid_cols = [c for c in all_members if c in pivot.columns]

        if not valid_cols:
            print(f"    ⚠️  No valid columns found for {family_name}")
            continue

        # Calculate row-wise mean (the Family Stress Index)
        # This is instant - one calculation for all timestamps!
        family_stress_series = pivot[valid_cols].mean(axis=1)
        family_stress_series.name = 'family_stress_temp'

        # Reset index to make merging easier
        stress_df = family_stress_series.reset_index()

        # Merge back to original dataframe (only for target rows)
        mask = df['instance_type'] == target

        # Create temporary merge on target rows
        df_target = df[mask].merge(
            stress_df,
            on=['timestamp', 'availability_zone'],
            how='left',
            suffixes=('', '_new')
        )

        # Update family_stress for target rows
        if 'family_stress_temp' in df_target.columns:
            df.loc[mask, 'family_stress'] = df_target['family_stress_temp'].fillna(0).values

        print(f"    ✓ Updated {mask.sum():,} rows for {target}")

    df['family_stress'] = df['family_stress'].astype('float32' if CONFIG['use_float32'] else 'float64')

    print(f"  ✓ Family Stress Index calculated")
    print(f"  Mean: {df['family_stress'].mean():.3f}")
    print(f"  Std: {df['family_stress'].std():.3f}")

    return df

def calculate_time_embeddings(df):
    """
    D. Time Embeddings (Seasonality)

    T_hour_x = sin(2π * Hour / 24)
    T_hour_y = cos(2π * Hour / 24)

    Captures cyclical patterns (9 AM login storms, midnight batch jobs)
    """
    print(f"\n⏰ Calculating Time Embeddings...")

    df['hour'] = df['timestamp'].dt.hour
    df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24).astype('float32' if CONFIG['use_float32'] else 'float64')
    df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24).astype('float32' if CONFIG['use_float32'] else 'float64')

    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['is_weekend'] = (df['day_of_week'] >= 5).astype('int8')
    df['is_business_hours'] = ((df['hour'] >= 9) & (df['hour'] <= 17)).astype('int8')

    print(f"  ✓ Time Embeddings calculated")

    return df

# ============================================================================
# 5. MODEL TRAINING
# ============================================================================

FEATURE_COLUMNS = [
    'price_position',      # A. Normalized price pressure (7-day range)
    'price_velocity_1h',   # A2. Rate of change (backup for stable markets)
    'price_volatility_6h', # A3. Rolling std dev (backup for stable markets)
    'price_cv_6h',         # A4. Coefficient of variation (backup for stable markets)
    'discount_depth',      # B. Economic buffer
    'family_stress',       # C. Hardware contagion (KEY FEATURE)
    'hour_sin',            # D. Time embeddings
    'hour_cos',
    'is_weekend',
    'is_business_hours'
]

def train_model(df_train, scale_pos_weight):
    """
    Train LightGBM Binary Classifier
    """
    print(f"\n🤖 Training LightGBM Binary Classifier...")
    print(f"  Features: {len(FEATURE_COLUMNS)}")
    print(f"  Samples: {len(df_train):,}")

    X_train = df_train[FEATURE_COLUMNS]
    y_train = df_train['is_unstable_next_6h']

    # Add scale_pos_weight to handle imbalance
    model_params = CONFIG['model_params'].copy()
    model_params['scale_pos_weight'] = scale_pos_weight

    print(f"  Hyperparameters:")
    for k, v in model_params.items():
        print(f"    {k}: {v}")

    model = LGBMClassifier(**model_params)
    model.fit(X_train, y_train)

    # Training metrics
    y_pred_proba = model.predict_proba(X_train)[:, 1]
    y_pred = (y_pred_proba > CONFIG['decision_threshold']).astype(int)

    precision = precision_score(y_train, y_pred)
    recall = recall_score(y_train, y_pred)
    f1 = f1_score(y_train, y_pred)
    auc_score = roc_auc_score(y_train, y_pred_proba)

    print(f"\n  Training Metrics:")
    print(f"    Precision: {precision:.3f}")
    print(f"    Recall: {recall:.3f}")
    print(f"    F1 Score: {f1:.3f}")
    print(f"    AUC: {auc_score:.3f}")

    return model

# ============================================================================
# 6. EVALUATION & VISUALIZATION
# ============================================================================

def evaluate_and_visualize(model, df_test, output_dir, plots_dir):
    """
    Generate the 3 required graphs + metrics
    """
    print(f"\n📊 Evaluation & Visualization...")

    X_test = df_test[FEATURE_COLUMNS]
    y_test = df_test['is_unstable_next_6h']

    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_pred_proba > CONFIG['decision_threshold']).astype(int)

    # Prediction diagnostics
    print(f"\n  🔍 Prediction Diagnostics:")
    print(f"    Unique predictions: {len(np.unique(y_pred))}")
    print(f"    Predicted positive: {y_pred.sum():,} ({y_pred.sum()/len(y_pred)*100:.2f}%)")
    print(f"    Actual positive: {y_test.sum():,} ({y_test.sum()/len(y_test)*100:.2f}%)")
    print(f"    Pred proba range: [{y_pred_proba.min():.6f}, {y_pred_proba.max():.6f}]")

    # Check if model is making diverse predictions
    if len(np.unique(y_pred)) == 1:
        print(f"\n  ❌ CRITICAL: Model only predicts ONE class ({np.unique(y_pred)[0]})!")
        print(f"     This happens when features have zero variance.")
        print(f"     Model cannot distinguish between stable and unstable periods.")
        print(f"\n  🔧 Solutions:")
        print(f"     1. Use data period with actual price movement")
        print(f"     2. Lower decision threshold (try 0.01 instead of 0.5)")
        print(f"     3. Check raw CSV - prices may be aggregated/filtered incorrectly")

        # Try different threshold
        print(f"\n  Attempting with threshold=0.01...")
        y_pred_low = (y_pred_proba > 0.01).astype(int)
        print(f"    Predicted positive with 0.01 threshold: {y_pred_low.sum():,}")
        if y_pred_low.sum() > 0:
            y_pred = y_pred_low
            print(f"    ✓ Using lower threshold")
        else:
            print(f"    ❌ Still no positive predictions - model is broken")

    # Calculate metrics with zero_division handling
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)

    # AUC requires at least some variance in predictions
    try:
        auc_score = roc_auc_score(y_test, y_pred_proba)
    except ValueError:
        auc_score = 0.5  # Random guessing
        print(f"    ⚠️  Cannot calculate AUC (no variance in predictions)")

    print(f"\n  Test Metrics:")
    print(f"    Precision: {precision:.3f}")
    print(f"    Recall: {recall:.3f}")
    print(f"    F1 Score: {f1:.3f}")
    print(f"    AUC: {auc_score:.3f}")

    # Confusion matrix with error handling
    cm = confusion_matrix(y_test, y_pred)
    print(f"\n  Confusion Matrix:")
    if cm.shape == (2, 2):
        print(f"    TN: {cm[0,0]:,} | FP: {cm[0,1]:,}")
        print(f"    FN: {cm[1,0]:,} | TP: {cm[1,1]:,}")
    elif cm.shape == (1, 1):
        print(f"    ❌ Only one class predicted")
        print(f"    All predictions: {np.unique(y_pred)[0]} (count: {cm[0,0]:,})")
    else:
        print(f"    Shape: {cm.shape}")
        print(f"    {cm}")

    # Skip graph generation if predictions are broken
    if len(np.unique(y_pred)) == 1 or precision == 0:
        print(f"\n  ⚠️  Skipping graph generation (predictions are broken)")
        print(f"     Model only predicts one class - graphs would be meaningless")
        return {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'auc': auc_score
        }

    # ========== GRAPH 1: Precision-Recall Curve ==========
    print(f"\n  Creating Graph 1: Precision-Recall Curve...")

    try:
        precisions, recalls, thresholds = precision_recall_curve(y_test, y_pred_proba)
        pr_auc = auc(recalls, precisions)

        fig, ax = plt.subplots(figsize=(10, 8))
        ax.plot(recalls, precisions, linewidth=2, label=f'PR Curve (AUC = {pr_auc:.3f})')
        ax.axhline(y=precision, color='r', linestyle='--', alpha=0.5, label=f'Operating Point (P={precision:.3f}, R={recall:.3f})')
        ax.axvline(x=recall, color='r', linestyle='--', alpha=0.5)
        ax.scatter([recall], [precision], color='red', s=100, zorder=5)

        ax.set_xlabel('Recall', fontsize=12)
        ax.set_ylabel('Precision', fontsize=12)
        ax.set_title('Precision-Recall Curve\n(Goal: Top-Right Corner)', fontsize=14, fontweight='bold')
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(Path(plots_dir) / 'precision_recall_curve.png', dpi=150)
        plt.close()
        print(f"    ✓ Saved to {Path(plots_dir) / 'precision_recall_curve.png'}")
    except Exception as e:
        print(f"    ⚠️  Failed to create PR curve: {e}")

    # ========== GRAPH 2: Feature Importance ==========
    print(f"  Creating Graph 2: Feature Importance...")

    try:
        importances = model.feature_importances_
        feature_importance_df = pd.DataFrame({
            'feature': FEATURE_COLUMNS,
            'importance': importances
        }).sort_values('importance', ascending=False)

        fig, ax = plt.subplots(figsize=(10, 6))
        colors = ['red' if feat == 'family_stress' else 'steelblue' for feat in feature_importance_df['feature']]
        ax.barh(range(len(feature_importance_df)), feature_importance_df['importance'], color=colors)
        ax.set_yticks(range(len(feature_importance_df)))
        ax.set_yticklabels(feature_importance_df['feature'])
        ax.set_xlabel('Importance', fontsize=12)
        ax.set_title('Feature Importance\n(Red = Family Stress Index)', fontsize=14, fontweight='bold')
        ax.grid(axis='x', alpha=0.3)

        # Add annotation if family_stress is top
        if 'family_stress' in feature_importance_df['feature'].values:
            if feature_importance_df.iloc[0]['feature'] == 'family_stress':
                ax.text(0.95, 0.95, '✓ Hardware Contagion\nSignal Validated!',
                        transform=ax.transAxes, fontsize=10, verticalalignment='top',
                        horizontalalignment='right', bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))

        plt.tight_layout()
        plt.savefig(Path(plots_dir) / 'feature_importance_bar_chart.png', dpi=150)
        plt.close()
        print(f"    ✓ Saved to {Path(plots_dir) / 'feature_importance_bar_chart.png'}")
    except Exception as e:
        print(f"    ⚠️  Failed to create feature importance: {e}")

    # ========== GRAPH 3: Prediction Timeline Overlay ==========
    print(f"  Creating Graph 3: Prediction Timeline Overlay...")

    try:
        # Sample a pool for visualization
        sample_pool = df_test['pool_id'].value_counts().index[0]
        df_sample = df_test[df_test['pool_id'] == sample_pool].copy()
        df_sample = df_sample.sort_values('timestamp').head(500)  # First 500 points

        if len(df_sample) > 0:
            X_sample = df_sample[FEATURE_COLUMNS]
            y_sample_true = df_sample['is_unstable_next_6h']
            y_sample_pred = model.predict_proba(X_sample)[:, 1]

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

            # Top panel: Price with true instability markers
            ax1.plot(df_sample['timestamp'], df_sample['spot_price'], linewidth=1, color='black', label='Spot Price')
            unstable_mask = y_sample_true == 1
            if unstable_mask.sum() > 0:
                ax1.scatter(df_sample.loc[unstable_mask, 'timestamp'],
                           df_sample.loc[unstable_mask, 'spot_price'],
                           color='red', s=30, alpha=0.6, label='True Unstable', zorder=5)

            ax1.set_ylabel('Spot Price ($)', fontsize=12)
            ax1.set_title(f'Prediction Timeline: {sample_pool}\n(Top: Price + True Labels | Bottom: Model Predictions)',
                         fontsize=14, fontweight='bold')
            ax1.legend()
            ax1.grid(True, alpha=0.3)

            # Bottom panel: Predicted probability
            ax2.plot(df_sample['timestamp'], y_sample_pred, linewidth=2, color='blue', label='P(Unstable)')
            ax2.axhline(y=CONFIG['decision_threshold'], color='red', linestyle='--',
                       linewidth=1, label=f'Threshold ({CONFIG["decision_threshold"]})')
            ax2.fill_between(df_sample['timestamp'], CONFIG['decision_threshold'], 1.0,
                            alpha=0.2, color='red', label='Red Zone (Unsafe)')
            ax2.fill_between(df_sample['timestamp'], 0, CONFIG['decision_threshold'],
                            alpha=0.2, color='green', label='Green Zone (Safe)')

            ax2.set_xlabel('Timestamp', fontsize=12)
            ax2.set_ylabel('Probability', fontsize=12)
            ax2.set_ylim(0, 1)
            ax2.legend(loc='upper right')
            ax2.grid(True, alpha=0.3)

            plt.tight_layout()
            plt.savefig(Path(plots_dir) / 'prediction_timeline_overlay.png', dpi=150)
            plt.close()
            print(f"    ✓ Saved to {Path(plots_dir) / 'prediction_timeline_overlay.png'}")
    except Exception as e:
        print(f"    ⚠️  Failed to create timeline: {e}")

    print(f"\n  ✓ Graph generation complete")

    # Save metrics to file
    metrics_file = Path(output_dir) / 'evaluation_metrics.txt'
    with open(metrics_file, 'w') as f:
        f.write("FAMILY STRESS MODEL - EVALUATION METRICS\n")
        f.write("="*50 + "\n\n")
        f.write(f"Precision: {precision:.4f}\n")
        f.write(f"Recall: {recall:.4f}\n")
        f.write(f"F1 Score: {f1:.4f}\n")
        f.write(f"AUC: {auc_score:.4f}\n\n")
        f.write("Confusion Matrix:\n")
        f.write(f"  TN: {cm[0,0]:,} | FP: {cm[0,1]:,}\n")
        f.write(f"  FN: {cm[1,0]:,} | TP: {cm[1,1]:,}\n\n")
        f.write("Feature Importance:\n")
        for _, row in feature_importance_df.iterrows():
            f.write(f"  {row['feature']}: {row['importance']:.4f}\n")

    print(f"  ✓ Metrics saved to {metrics_file}")

    return {
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'auc': auc_score
    }

# ============================================================================
# 7. MAIN EXECUTION
# ============================================================================

def main():
    start_time = datetime.now()

    print("\n🚀 Starting Family Stress Model Pipeline...\n")

    # 1. Load data
    df_train = load_data_efficient(CONFIG['training_data'], CONFIG['families'], is_training=True)
    df_test = load_data_efficient(CONFIG['test_data'], CONFIG['families'], is_training=False)

    # 2. Time synchronization
    df_train = create_market_snapshots(df_train, freq='10T')
    df_test = create_market_snapshots(df_test, freq='10T')

    # 3. Create target variable
    df_train, scale_pos_weight = create_target_variable(
        df_train,
        CONFIG['spike_threshold'],
        CONFIG['lookahead_intervals']
    )
    df_test, _ = create_target_variable(
        df_test,
        CONFIG['spike_threshold'],
        CONFIG['lookahead_intervals']
    )

    # 4. Feature engineering
    print("\n" + "="*80)
    print("FEATURE ENGINEERING: Hardware-Aware Stress Signals")
    print("="*80)

    df_train = calculate_price_position(df_train, CONFIG['price_position_window_days'])
    df_train = calculate_price_velocity(df_train)  # Backup features for stable markets
    df_train = calculate_discount_depth(df_train)
    df_train = calculate_family_stress_index(df_train, CONFIG['families'])
    df_train = calculate_time_embeddings(df_train)

    df_test = calculate_price_position(df_test, CONFIG['price_position_window_days'])
    df_test = calculate_price_velocity(df_test)  # Backup features for stable markets
    df_test = calculate_discount_depth(df_test)
    df_test = calculate_family_stress_index(df_test, CONFIG['families'])
    df_test = calculate_time_embeddings(df_test)

    # Drop rows with missing features
    df_train = df_train.dropna(subset=FEATURE_COLUMNS + ['is_unstable_next_6h'])
    df_test = df_test.dropna(subset=FEATURE_COLUMNS + ['is_unstable_next_6h'])

    print(f"\n✓ Final dataset sizes:")
    print(f"  Training: {len(df_train):,} rows")
    print(f"  Test: {len(df_test):,} rows")

    # Data quality validation
    print(f"\n🔍 Data Quality Validation...")
    print("="*80)
    zero_variance_features = []
    for feature in FEATURE_COLUMNS:
        std = df_train[feature].std()
        mean = df_train[feature].mean()
        print(f"  {feature:20s}: Mean={mean:8.6f}, Std={std:8.6f}", end="")
        if std < 1e-6:
            print("  ⚠️  ZERO VARIANCE - Feature may not be useful!")
            zero_variance_features.append(feature)
        else:
            print("  ✓")

    if zero_variance_features:
        print(f"\n⚠️  WARNING: {len(zero_variance_features)} features have zero variance!")
        print(f"  Features: {', '.join(zero_variance_features)}")
        print(f"\n  Possible causes:")
        print(f"  1. Data is EXTREMELY stable (prices barely move)")
        print(f"  2. Window size too large for stable market")
        print(f"  3. Data quality issues (all prices same)")
        print(f"\n  🔧 AUTO-FIX: Removing zero-variance features from training...")

        # Create new feature list without zero-variance features
        active_features = [f for f in FEATURE_COLUMNS if f not in zero_variance_features]

        if len(active_features) < 2:
            print(f"\n  ❌ CRITICAL: Only {len(active_features)} usable features!")
            print(f"     Cannot train model with so few features.")
            print(f"\n  ACTION REQUIRED:")
            print(f"     1. Run diagnostic tool: python ml-model/diagnose_data.py")
            print(f"     2. Check raw CSV data for price variance")
            print(f"     3. Use different time period with actual market activity")
            print(f"\n  Exiting...")
            return
        else:
            print(f"  ✓ Removed {len(zero_variance_features)} features")
            print(f"  ✓ Training with {len(active_features)} features: {active_features}")
            # Update feature columns for training
            FEATURE_COLUMNS.clear()
            FEATURE_COLUMNS.extend(active_features)
    else:
        active_features = FEATURE_COLUMNS

    print("="*80)

    # Final check: Do we have ANY variance in target variable?
    train_pos = df_train['is_unstable_next_6h'].sum()
    train_total = len(df_train)
    test_pos = df_test['is_unstable_next_6h'].sum()

    if train_pos < 10:
        print(f"\n❌ CRITICAL: Only {train_pos} unstable samples in training data!")
        print(f"   Model cannot learn from <10 positive samples.")
        print(f"\n  ACTION REQUIRED:")
        print(f"     1. Lower spike_threshold (current: {CONFIG['spike_threshold']*100}%)")
        print(f"        Try: 'spike_threshold': 0.001 (0.1%)")
        print(f"     2. Or use different time period with more volatility")
        print(f"\n  Exiting...")
        return

    print(f"\n✓ Ready to train:")
    print(f"  Features: {len(active_features)}")
    print(f"  Training samples: {train_total:,} ({train_pos} unstable = {train_pos/train_total*100:.3f}%)")
    print(f"  Test samples: {len(df_test):,} ({test_pos} unstable = {test_pos/len(df_test)*100:.3f}%)")

    # 5. Train model
    model = train_model(df_train, scale_pos_weight)

    # 6. Evaluate and visualize
    metrics = evaluate_and_visualize(model, df_test, CONFIG['output_dir'], CONFIG['plots_dir'])

    # 7. Save model
    print(f"\n💾 Saving model...")
    import pickle
    with open(CONFIG['model_path'], 'wb') as f:
        pickle.dump(model, f)
    print(f"  ✓ Model saved to {CONFIG['model_path']}")

    # Final summary
    elapsed = datetime.now() - start_time
    print("\n" + "="*80)
    print("✅ PIPELINE COMPLETE")
    print("="*80)
    print(f"Elapsed Time: {elapsed.total_seconds() / 60:.1f} minutes")
    print(f"\n📊 Final Metrics:")
    print(f"  Precision: {metrics['precision']:.3f}")
    print(f"  Recall: {metrics['recall']:.3f}")
    print(f"  F1 Score: {metrics['f1']:.3f}")
    print(f"  AUC: {metrics['auc']:.3f}")
    print(f"\n📁 Outputs:")
    print(f"  Graphs: {CONFIG['plots_dir']}/")
    print(f"  Metrics: {CONFIG['output_dir']}/evaluation_metrics.txt")
    print(f"  Model: {CONFIG['model_path']}")
    print("="*80)

    # Interpretation guide
    print(f"\n📖 HOW TO INTERPRET THE RESULTS:")
    print(f"\n1. Precision-Recall Curve:")
    print(f"   - Goal: Line in top-right corner")
    print(f"   - AUC 0.80-1.0 = Excellent (Family Stress signal is highly predictive)")
    print(f"   - AUC 0.50-0.70 = Weak (Model struggling, prices may be too stable)")

    print(f"\n2. Feature Importance:")
    print(f"   - Look for 'family_stress' bar (highlighted in red)")
    print(f"   - If tallest = Hypothesis validated! Parent instances predict child failure")
    print(f"   - If short = Hardware contagion signal is weak in this data")

    print(f"\n3. Prediction Timeline:")
    print(f"   - Top: Actual prices with red dots = true instability")
    print(f"   - Bottom: Model's probability predictions")
    print(f"   - Good model: High probability BEFORE red dots appear")
    print("="*80)

if __name__ == "__main__":
    main()
