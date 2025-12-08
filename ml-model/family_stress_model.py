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

    # Target definition
    'spike_threshold': 0.10,  # 10% price increase = unstable
    'lookahead_hours': 6,     # Predict 6 hours ahead
    'lookahead_intervals': 36,  # 6 hours / 10 min intervals

    # Feature windows
    'price_position_window_days': 30,  # 30-day min/max

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
        if timestamp_col is None and any(x in col for x in ['time', 'date', 'timestamp']):
            timestamp_col = col
        elif instance_type_col is None and any(x in col for x in ['instance', 'type']):
            instance_type_col = col
        elif az_col is None and any(x in col for x in ['availability', 'zone', 'az']):
            az_col = col
        elif price_col is None and (any(x in col for x in ['spot', 'price']) or col == 'price'):
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

    # Add on-demand price (estimated as 4x spot for simplicity)
    df['on_demand_price'] = (df['spot_price'] * 4.0).astype('float32' if CONFIG['use_float32'] else 'float64')

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
    Binary target: Is_Unstable_Next_6H

    Y_t = 1 if:
        max(Price_{t+1...t+36}) > 1.10 * Price_t

    Logic: If price spikes >10% in next 6 hours, current state was "unstable"
    """
    print(f"\n🎯 Creating target variable...")
    print(f"  Spike threshold: {spike_threshold*100}%")
    print(f"  Lookahead: {lookahead} intervals (6 hours)")

    df = df.sort_values(['pool_id', 'timestamp']).copy()
    df['is_unstable_next_6h'] = 0

    for pool_id, group in tqdm(df.groupby('pool_id'), desc="  Calculating targets"):
        indices = group.index.tolist()

        for i, idx in enumerate(indices):
            # Look ahead 36 intervals (6 hours)
            future_end = min(i + lookahead + 1, len(indices))
            if future_end <= i + 1:
                continue

            current_price = df.loc[idx, 'spot_price']
            future_indices = indices[i+1:future_end]
            future_prices = df.loc[future_indices, 'spot_price']

            max_future_price = future_prices.max()

            # Check if future price spikes >10%
            if max_future_price > current_price * (1 + spike_threshold):
                df.loc[idx, 'is_unstable_next_6h'] = 1

    # Remove rows without future data
    df = df[df.index.isin([idx for i, idx in enumerate(df.index) if i < len(df) - lookahead])]

    positive_count = df['is_unstable_next_6h'].sum()
    positive_pct = positive_count / len(df) * 100

    print(f"  ✓ Target created")
    print(f"  Unstable samples: {positive_count:,} ({positive_pct:.2f}%)")
    print(f"  Stable samples: {len(df) - positive_count:,} ({100-positive_pct:.2f}%)")

    # Calculate scale_pos_weight for imbalanced data
    scale_pos_weight = (len(df) - positive_count) / positive_count if positive_count > 0 else 1.0
    print(f"  Recommended scale_pos_weight: {scale_pos_weight:.2f}")

    return df, scale_pos_weight

# ============================================================================
# 4. FEATURE ENGINEERING: Hardware-Aware Stress Signals
# ============================================================================

def calculate_price_position(df, window_days=30):
    """
    A. Price Position (Normalized Pressure)

    P_pos = (P_current - P_min_30d) / (P_max_30d - P_min_30d + ε)

    Interpretation:
    - 0.0 = Cheapest price recently (safe)
    - 1.0 = Most expensive price recently (dangerous)
    """
    print(f"\n📊 Calculating Price Position ({window_days}-day window)...")

    df = df.sort_values(['pool_id', 'timestamp']).copy()
    window = window_days * 24 * 6  # Convert to 10-min intervals

    df['price_min_30d'] = df.groupby('pool_id')['spot_price'].transform(
        lambda x: x.rolling(window=window, min_periods=1).min()
    )
    df['price_max_30d'] = df.groupby('pool_id')['spot_price'].transform(
        lambda x: x.rolling(window=window, min_periods=1).max()
    )

    epsilon = 1e-9
    df['price_position'] = (
        (df['spot_price'] - df['price_min_30d']) /
        (df['price_max_30d'] - df['price_min_30d'] + epsilon)
    )

    # Clip to [0, 1]
    df['price_position'] = df['price_position'].clip(0, 1).astype('float32' if CONFIG['use_float32'] else 'float64')

    print(f"  ✓ Price Position calculated")
    print(f"  Mean: {df['price_position'].mean():.3f}")
    print(f"  Std: {df['price_position'].std():.3f}")

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
    C. Family Stress Index (Hardware Contagion) - THE KEY INNOVATION

    S_family = (1/|F|) * Σ P_pos(i) for i in Family F

    Logic:
    - If c5.large has P_pos=0.1 (low) but c5.metal has P_pos=0.9 (high)
    - The average S_family will be high (~0.5)
    - This marks c5.large as risky due to "Big Brother" stress

    This is the HARDWARE CONTAGION mechanism
    """
    print(f"\n🔥 Calculating Family Stress Index (Hardware Contagion)...")

    df['family_stress'] = 0.0

    for family_name, family_data in families_config.items():
        target = family_data['target']
        signal_instances = family_data['signals']

        print(f"  Processing {family_name} family...")
        print(f"    Target: {target}")
        print(f"    Signals: {len(signal_instances)} instances")

        # For each timestamp, calculate average price_position across ALL family members
        for az in df['availability_zone'].unique():
            # Get all family members in this AZ
            family_pools = [f"{inst}_{az}" for inst in [target] + signal_instances]

            # For each timestamp
            for ts in tqdm(df['timestamp'].unique(), desc=f"    {family_name}/{az}", leave=False):
                # Get price positions of all family members at this timestamp
                family_data_at_ts = df[
                    (df['timestamp'] == ts) &
                    (df['pool_id'].isin(family_pools))
                ]

                if len(family_data_at_ts) > 0:
                    avg_stress = family_data_at_ts['price_position'].mean()

                    # Assign this stress to the TARGET instance
                    target_mask = (
                        (df['timestamp'] == ts) &
                        (df['pool_id'] == f"{target}_{az}")
                    )
                    df.loc[target_mask, 'family_stress'] = avg_stress

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
    'price_position',      # A. Normalized price pressure
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

    # Calculate metrics
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    auc_score = roc_auc_score(y_test, y_pred_proba)

    print(f"\n  Test Metrics:")
    print(f"    Precision: {precision:.3f}")
    print(f"    Recall: {recall:.3f}")
    print(f"    F1 Score: {f1:.3f}")
    print(f"    AUC: {auc_score:.3f}")

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    print(f"\n  Confusion Matrix:")
    print(f"    TN: {cm[0,0]:,} | FP: {cm[0,1]:,}")
    print(f"    FN: {cm[1,0]:,} | TP: {cm[1,1]:,}")

    # ========== GRAPH 1: Precision-Recall Curve ==========
    print(f"\n  Creating Graph 1: Precision-Recall Curve...")

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

    # ========== GRAPH 2: Feature Importance ==========
    print(f"  Creating Graph 2: Feature Importance...")

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
    if feature_importance_df.iloc[0]['feature'] == 'family_stress':
        ax.text(0.95, 0.95, '✓ Hardware Contagion\nSignal Validated!',
                transform=ax.transAxes, fontsize=10, verticalalignment='top',
                horizontalalignment='right', bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))

    plt.tight_layout()
    plt.savefig(Path(plots_dir) / 'feature_importance_bar_chart.png', dpi=150)
    plt.close()

    # ========== GRAPH 3: Prediction Timeline Overlay ==========
    print(f"  Creating Graph 3: Prediction Timeline Overlay...")

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

    print(f"\n  ✓ All graphs saved to {plots_dir}/")

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
    df_train = calculate_discount_depth(df_train)
    df_train = calculate_family_stress_index(df_train, CONFIG['families'])
    df_train = calculate_time_embeddings(df_train)

    df_test = calculate_price_position(df_test, CONFIG['price_position_window_days'])
    df_test = calculate_discount_depth(df_test)
    df_test = calculate_family_stress_index(df_test, CONFIG['families'])
    df_test = calculate_time_embeddings(df_test)

    # Drop rows with missing features
    df_train = df_train.dropna(subset=FEATURE_COLUMNS + ['is_unstable_next_6h'])
    df_test = df_test.dropna(subset=FEATURE_COLUMNS + ['is_unstable_next_6h'])

    print(f"\n✓ Final dataset sizes:")
    print(f"  Training: {len(df_train):,} rows")
    print(f"  Test: {len(df_test):,} rows")

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
