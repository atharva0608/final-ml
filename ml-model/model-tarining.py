"""
CAST-AI Mini - ML Training & Decision Engine Backtesting
=========================================================

This script:
1. TRAINS ML models on 2023-2024 data to predict next-hour spot prices
2. BACKTESTS the decision engine on 2025 data using those trained models
3. Simulates pool switching based on ML price predictions + baseline monitoring

Architecture: Agentless (no agents on instances, direct AWS SDK)
Region: ap-south-1 (Mumbai)
Instance Types: t3.medium, t4g.medium, c5.large, t4g.small
Pools: Discovered from data (instance_type × availability_zone)

ML Models: Train for EACH pool to predict next-hour prices
Decision Logic: Switch if ML predicts baseline breach + significant improvement
"""

# ============================================================================
# IMPORTS
# ============================================================================

import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
from pathlib import Path
from decimal import Decimal
import warnings
import os
import pickle
from collections import defaultdict
warnings.filterwarnings('ignore')

# ML libraries
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, mean_absolute_percentage_error
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import ElasticNet
import xgboost as xgb

# ============================================================================
# HYPERPARAMETERS - TUNE FROM HERE
# ============================================================================

HYPERPARAMETERS = {
    # Safety Thresholds
    'SAFE_INTERRUPT_RATE_THRESHOLD': 0.05,  # 5% max interruption rate for safe pools

    # Baseline Windows (days)
    'MIN_LOOKBACK_DAYS_FOR_BASELINE': 14,  # Minimum history needed to compute baseline
    'BASELINE_DISCOUNT_WINDOW_DAYS': 30,   # Rolling window for discount baseline
    'BASELINE_VOLATILITY_WINDOW_DAYS': 30, # Rolling window for volatility baseline

    # ML Price Prediction
    'PRICE_PREDICTION_HORIZON_HOURS': 1,    # Predict 1 hour ahead
    'ML_BASELINE_BREACH_THRESHOLD': 0.10,   # 10% predicted price increase triggers consideration

    # Switching Thresholds (z-scores)
    'DISCOUNT_ZSCORE_SWITCH_THRESHOLD': 1.5,    # Z-score threshold for discount deviation
    'VOLATILITY_ZSCORE_SWITCH_THRESHOLD': 1.5,  # Z-score threshold for volatility deviation

    # Global Trend Analysis
    'GLOBAL_DISCOUNT_TREND_WINDOW_DAYS': 7,  # Window for computing global trend slope
    'GLOBAL_TREND_SWITCH_THRESHOLD': 0.01,   # Min slope to consider significant trend

    # Switching Constraints
    'MAX_SWITCHES_PER_DAY': 3,           # Maximum pool switches allowed per day
    'SWITCH_COST_PENALTY': 0.001,        # Cost penalty per switch (as fraction of hourly cost)

    # Cost/Penalty Multipliers
    'INTERRUPTION_PENALTY_MULTIPLIER': 5.0,  # Multiply interruption rate by this in scoring
    'STABILITY_WEIGHT': 0.70,            # 70% weight for stability in ranking
    'COST_WEIGHT': 0.30,                 # 30% weight for cost in ranking

    # Minimum Improvement Thresholds
    'MIN_COST_IMPROVEMENT_PCT': 0.05,    # 5% min cost improvement to justify switch
    'MIN_STABILITY_IMPROVEMENT': 0.10,   # 10% min stability improvement to justify switch

    # Random Seed
    'RANDOM_SEED': 42,

    # Data Sampling (for faster development/testing)
    'SAMPLE_BACKTEST_HOURS': None,  # None = use all data, or int = sample N hours
}

print("="*80)
print("CAST-AI Mini - ML Training & Decision Engine Backtesting")
print("="*80)
print(f"Start Time: {datetime.now()}")
print("="*80)

print("\n🎛️  HYPERPARAMETERS:")
for key, value in HYPERPARAMETERS.items():
    print(f"  {key}: {value}")

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    # Data paths - YOUR ACTUAL LOCAL FILE PATHS
    'training_data': '/Users/atharvapudale/Downloads/aws_2023_2024_complete_24months.csv',
    'test_q1': '/Users/atharvapudale/Downloads/mumbai_spot_data_sorted_asc(1-2-3-25).csv',
    'test_q2': '/Users/atharvapudale/Downloads/mumbai_spot_data_sorted_asc(4-5-6-25).csv',
    'test_q3': '/Users/atharvapudale/Downloads/mumbai_spot_data_sorted_asc(7-8-9-25).csv',
    'event_data': '/Users/atharvapudale/Downloads/aws_stress_events_2023_2025.csv',

    'output_dir': './training/outputs',
    'models_dir': './models/uploaded',

    # Data parameters - AGENTLESS ARCHITECTURE
    'region': 'ap-south-1',  # Mumbai
    'instance_types': ['t3.medium', 't4g.medium', 'c5.large', 't4g.small'],  # 4 instance types
    # Note: availability_zones are auto-discovered from the data
    # Pools are determined by unique (instance_type, availability_zone) combinations in the data

    # Training parameters
    'train_end_date': '2024-12-31',  # Train on 2023-2024 data
    'test_start_date': '2025-01-01',  # Test on 2025 data

    # Feature engineering
    'lookback_periods': {
        '1h': 6,    # 10-min intervals
        '6h': 36,
        '24h': 144,
        '7d': 1008
    },

    # Forecasting
    'forecast_horizon': 6,  # 1 hour ahead (6 × 10 min)

    # Use actual data (set to False to generate sample data)
    'use_actual_data': True
}

# Create output directories
Path(CONFIG['output_dir']).mkdir(parents=True, exist_ok=True)
Path(CONFIG['models_dir']).mkdir(parents=True, exist_ok=True)

print("\n📁 Configuration:")
for key, value in CONFIG.items():
    if not isinstance(value, dict):
        if isinstance(value, str) and '/' in value:
            print(f"  {key}: {Path(value).name if Path(value).exists() else value}")
        else:
            print(f"  {key}: {value}")

# ============================================================================
# DATA LOADING & PREPARATION
# ============================================================================

print("\n" + "="*80)
print("1. DATA LOADING (Training 2023-2024 + Test 2025)")
print("="*80)

def standardize_columns(df):
    """Standardize column names to expected format"""
    df.columns = df.columns.str.lower().str.strip()

    # Column mapping
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
        elif col in ['az', 'availability_zone']:
            col_map[col] = 'availability_zone'
        elif col in ['region']:
            col_map[col] = 'region'
        elif 'interrupt' in col:
            col_map[col] = 'interruption_rate'

    df = df.rename(columns=col_map)

    # Parse timestamp
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

    # Parse numeric columns
    df['spot_price'] = pd.to_numeric(df['spot_price'], errors='coerce')
    if 'on_demand_price' in df.columns:
        df['on_demand_price'] = pd.to_numeric(df['on_demand_price'], errors='coerce')
    if 'interruption_rate' in df.columns:
        df['interruption_rate'] = pd.to_numeric(df['interruption_rate'], errors='coerce')

    # Infer region from AZ if missing
    if 'region' not in df.columns or df['region'].isna().all():
        if 'availability_zone' in df.columns:
            df['region'] = df['availability_zone'].str.extract(r'^([a-z]+-[a-z]+-\d+)')[0]

    # Drop rows with missing critical data
    df = df.dropna(subset=['spot_price', 'timestamp']).sort_values('timestamp')

    # Calculate discount if not present
    if 'on_demand_price' in df.columns and 'discount' not in df.columns:
        df['discount'] = (df['on_demand_price'] - df['spot_price']) / df['on_demand_price']
        df['discount'] = df['discount'].clip(0, 1)  # Cap between 0 and 1

    # Calculate price ratio
    if 'on_demand_price' in df.columns and 'price_ratio' not in df.columns:
        df['price_ratio'] = (df['spot_price'] / df['on_demand_price']).clip(0, 10)

    return df

def load_all_data():
    """
    Load BOTH training (2023-2024) and test (2025) data
    """
    print("\n📂 Loading training data (2023-2024)...")

    # Load training data
    if Path(CONFIG['training_data']).exists():
        print(f"  Loading training: {Path(CONFIG['training_data']).name}")
        df_train = pd.read_csv(CONFIG['training_data'])
        df_train = standardize_columns(df_train)
    else:
        print(f"  ❌ Training data not found: {CONFIG['training_data']}")
        sys.exit(1)

    print("\n📂 Loading test data (2025 Q1/Q2/Q3)...")

    # Load Q1, Q2, Q3 2025 data
    test_dfs = []
    for quarter, path in [('Q1', CONFIG['test_q1']), ('Q2', CONFIG['test_q2']), ('Q3', CONFIG['test_q3'])]:
        if Path(path).exists():
            print(f"  Loading {quarter} 2025: {Path(path).name}")
            df = pd.read_csv(path)
            df = standardize_columns(df)
            test_dfs.append(df)
        else:
            print(f"  ⚠️  {quarter} data not found: {path}")

    if not test_dfs:
        print("\n❌ ERROR: No 2025 data files found!")
        sys.exit(1)

    df_test = pd.concat(test_dfs, ignore_index=True)
    df_test = df_test.sort_values('timestamp').reset_index(drop=True)

    print(f"\n✓ Loaded {len(df_train):,} training records (2023-2024)")
    print(f"  Date range: {df_train['timestamp'].min()} to {df_train['timestamp'].max()}")

    print(f"\n✓ Loaded {len(df_test):,} test records (2025)")
    print(f"  Date range: {df_test['timestamp'].min()} to {df_test['timestamp'].max()}")

    # Filter both datasets
    print(f"\n📊 Filtering to region={CONFIG['region']} and instance_types={CONFIG['instance_types']}")

    if 'region' in df_train.columns:
        df_train = df_train[df_train['region'] == CONFIG['region']]
    if 'instance_type' in df_train.columns:
        df_train = df_train[df_train['instance_type'].isin(CONFIG['instance_types'])]

    if 'region' in df_test.columns:
        df_test = df_test[df_test['region'] == CONFIG['region']]
    if 'instance_type' in df_test.columns:
        df_test = df_test[df_test['instance_type'].isin(CONFIG['instance_types'])]

    print(f"\n✓ After filtering:")
    print(f"  Training: {len(df_train):,} records")
    print(f"  Test: {len(df_test):,} records")

    if 'availability_zone' in df_train.columns:
        train_pools = df_train.groupby(['instance_type', 'availability_zone']).ngroups
        print(f"  Training pools: {train_pools}")

    if 'availability_zone' in df_test.columns:
        test_pools = df_test.groupby(['instance_type', 'availability_zone']).ngroups
        print(f"  Test pools: {test_pools}")

    # Check for interruption_rate
    if 'interruption_rate' not in df_test.columns:
        print("\n⚠️  WARNING: interruption_rate column not found in test data!")
        print("  Generating synthetic interruption rates for demonstration...")
        np.random.seed(HYPERPARAMETERS['RANDOM_SEED'])
        df_test['interruption_rate'] = np.random.uniform(0.01, 0.15, size=len(df_test))

    return df_train, df_test

# Load all data
df_train, df_test = load_all_data()

# ============================================================================
# ML MODEL TRAINING (Train on 2023-2024 data)
# ============================================================================

print("\n" + "="*80)
print("2. ML MODEL TRAINING (Per-Pool Price Prediction)")
print("="*80)

def engineer_features(df):
    """Engineer features for price prediction"""
    df = df.copy()

    # Lag features
    for lag in [1, 6, 12, 24, 48, 168]:
        df[f'spot_lag_{lag}h'] = df['spot_price'].shift(lag)
        df[f'ratio_lag_{lag}h'] = df['price_ratio'].shift(lag) if 'price_ratio' in df.columns else 0

    # Rolling statistics
    for window in [6, 12, 24, 168]:
        df[f'spot_mean_{window}h'] = df['spot_price'].rolling(window, min_periods=1).mean()
        df[f'spot_std_{window}h'] = df['spot_price'].rolling(window, min_periods=1).std()

    # Rate of change
    for period in [1, 6, 24]:
        df[f'price_change_{period}h'] = df['spot_price'].pct_change(period) * 100

    # Temporal features
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['month'] = df['timestamp'].dt.month
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
    df['is_business_hours'] = ((df['hour'] >= 9) & (df['hour'] <= 17)).astype(int)

    # Get feature columns
    feature_cols = [col for col in df.columns if
                   ('lag_' in col or 'mean_' in col or 'std_' in col or 'change_' in col or
                    col in ['hour', 'day_of_week', 'month', 'is_weekend', 'is_business_hours'])]

    # Fill NaN
    df[feature_cols] = df[feature_cols].fillna(method='bfill').fillna(0)

    return df, feature_cols

def train_pool_models(df_train):
    """
    Train ML models for each pool on 2023-2024 data
    Returns: dict of {pool_id: {'model': model, 'scaler': scaler, 'features': features}}
    """
    pool_models = {}

    # Discover pools from training data
    if 'availability_zone' not in df_train.columns:
        print("  ⚠️  No AZ column - training by instance_type only")
        pool_groups = df_train.groupby(['instance_type'])
    else:
        pool_groups = df_train.groupby(['instance_type', 'availability_zone'])

    print(f"\n🎓 Training ML models for {pool_groups.ngroups} pools...")

    for name, group in pool_groups:
        if isinstance(name, tuple):
            pool_id = f"{name[0]}_{name[1]}"
        else:
            pool_id = str(name)

        print(f"\n  Training model for {pool_id}...")

        # Engineer features
        pool_df, feature_cols = engineer_features(group)

        # Create target (next hour price)
        pool_df['target'] = pool_df['spot_price'].shift(-1)
        pool_df = pool_df.dropna(subset=['target'])

        if len(pool_df) < 100:
            print(f"    ⚠️  Not enough data ({len(pool_df)} records) - skipping")
            continue

        # Split features and target
        X = pool_df[feature_cols].values
        y = pool_df['target'].values

        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Train Gradient Boosting model
        model = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=5,
            min_samples_split=10,
            subsample=0.8,
            random_state=HYPERPARAMETERS['RANDOM_SEED']
        )
        model.fit(X_scaled, y)

        # Validation on last 10%
        val_size = int(len(X_scaled) * 0.1)
        X_val = X_scaled[-val_size:]
        y_val = y[-val_size:]
        y_pred = model.predict(X_val)

        mae = mean_absolute_error(y_val, y_pred)
        mape = np.mean(np.abs((y_val - y_pred) / y_val)) * 100

        print(f"    ✓ Trained on {len(X):,} samples, MAE=${mae:.6f}, MAPE={mape:.2f}%")

        # Store model
        pool_models[pool_id] = {
            'model': model,
            'scaler': scaler,
            'features': feature_cols,
            'baseline_price': pool_df['spot_price'].mean()
        }

    print(f"\n✓ Trained {len(pool_models)} pool models")

    # Save models
    models_path = Path(CONFIG['models_dir']) / 'pool_price_models.pkl'
    with open(models_path, 'wb') as f:
        pickle.dump(pool_models, f)
    print(f"✓ Saved models to: {models_path}")

    return pool_models

# Train models
pool_models = train_pool_models(df_train)

# ============================================================================
# POOL REPRESENTATION FOR BACKTESTING
# ============================================================================

print("\n" + "="*80)
print("3. POOL REPRESENTATION (Backtest Data with ML Models)")
print("="*80)

def build_pool_timeseries(df, pool_models):
    """
    Build per-pool time series with ML prediction capability
    """
    pools = {}

    # Discover pools from test data
    if 'availability_zone' not in df.columns:
        print("  ⚠️  WARNING: No availability_zone column - creating pools by instance_type only")
        for instance_type in df['instance_type'].unique():
            pool_id = f"{instance_type}"
            pool_data = df[df['instance_type'] == instance_type].copy()

            if len(pool_data) == 0:
                continue

            # Engineer features for prediction
            pool_data, _ = engineer_features(pool_data)
            pool_data = pool_data.sort_values('timestamp').reset_index(drop=True)

            pools[pool_id] = {
                'instance_type': instance_type,
                'availability_zone': None,
                'timeseries': pool_data[['timestamp', 'spot_price', 'on_demand_price', 'interruption_rate', 'discount']].copy(),
                'full_data': pool_data,  # Keep full data with features for predictions
                'has_model': pool_id in pool_models
            }
    else:
        # Group by (instance_type, availability_zone)
        pool_groups = df.groupby(['instance_type', 'availability_zone'])

        for (instance_type, az), group_df in pool_groups:
            pool_id = f"{instance_type}_{az}"

            # Engineer features
            pool_data, _ = engineer_features(group_df)
            pool_data = pool_data.sort_values('timestamp').reset_index(drop=True)

            pools[pool_id] = {
                'instance_type': instance_type,
                'availability_zone': az,
                'timeseries': pool_data[['timestamp', 'spot_price', 'on_demand_price', 'interruption_rate', 'discount']].copy(),
                'full_data': pool_data,  # Keep full data with features for predictions
                'has_model': pool_id in pool_models
            }

    return pools

# Build pools with ML capability
pools = build_pool_timeseries(df_test, pool_models)

print(f"\n✓ Built timeseries for {len(pools)} pools:")
for pool_id, pool in pools.items():
    ts_len = len(pool['timeseries'])
    avg_discount = pool['timeseries']['discount'].mean() * 100
    avg_interrupt = pool['timeseries']['interruption_rate'].mean() * 100
    has_model = "✓" if pool['has_model'] else "✗"
    print(f"  {pool_id}: {ts_len:,} records, {avg_discount:.1f}% avg discount, {avg_interrupt:.1f}% interrupt, ML model: {has_model}")

if len(pools) == 0:
    print(f"\n❌ ERROR: No pools discovered!")
    sys.exit(1)

# ============================================================================
# ML-ENHANCED BACKTESTING ENGINE
# ============================================================================

print("\n" + "="*80)
print("4. ML-ENHANCED BLIND BACKTESTING ENGINE")
print("="*80)
print("Using ML price predictions to forecast baseline breaches")

class MLEnhancedBacktester:
    """
    Blind backtesting engine with ML price prediction
    Uses trained models to predict future prices and decide switches
    """

    def __init__(self, pools, pool_models, hyperparameters):
        self.pools = pools
        self.pool_models = pool_models
        self.hp = hyperparameters

        # Build unified timeline
        all_timestamps = set()
        for pool in pools.values():
            all_timestamps.update(pool['timeseries']['timestamp'])
        self.timeline = sorted(all_timestamps)

        # Pool data lookup
        self.pool_data_by_time = self._build_pool_lookup()

        # State
        self.current_pool = None
        self.switches_today = 0
        self.last_switch_date = None
        self.switch_count = 0
        self.history = []

        if len(self.timeline) == 0:
            print(f"\n❌ ERROR: No timestamps found!")
            raise ValueError("Empty timeline")

        print(f"\n📅 Backtest timeline: {len(self.timeline):,} unique timestamps")
        print(f"   Start: {self.timeline[0]}")
        print(f"   End: {self.timeline[-1]}")
        print(f"   ML models available: {len(self.pool_models)}")

    def _build_pool_lookup(self):
        """Build timestamp lookup"""
        lookup = defaultdict(dict)

        for pool_id, pool in self.pools.items():
            for _, row in pool['timeseries'].iterrows():
                ts = row['timestamp']
                lookup[ts][pool_id] = {
                    'spot_price': row['spot_price'],
                    'on_demand_price': row['on_demand_price'],
                    'interruption_rate': row['interruption_rate'],
                    'discount': row['discount']
                }

        return lookup

    def predict_future_price(self, pool_id, current_timestamp):
        """
        Use ML model to predict next-hour price for a pool
        Returns: (predicted_price, confidence) or (None, 0) if no model
        """
        if pool_id not in self.pool_models:
            return None, 0.0

        if pool_id not in self.pools or not self.pools[pool_id]['has_model']:
            return None, 0.0

        # Get model and recent data
        model_data = self.pool_models[pool_id]
        model = model_data['model']
        scaler = model_data['scaler']
        features = model_data['features']

        # Get recent data for this pool up to current_timestamp
        pool_full_data = self.pools[pool_id]['full_data']
        recent_data = pool_full_data[pool_full_data['timestamp'] <= current_timestamp]

        if len(recent_data) < 24:  # Need at least 24 hours of history
            return None, 0.0

        # Get latest features
        try:
            X_current = recent_data[features].tail(1).values
            X_scaled = scaler.transform(X_current)
            predicted_price = model.predict(X_scaled)[0]
            confidence = 0.8  # Simple confidence measure

            return predicted_price, confidence
        except:
            return None, 0.0

    def get_safe_pools(self, timestamp):
        """Filter safe pools"""
        pool_data = self.pool_data_by_time.get(timestamp, {})
        safe_pools = []

        for pool_id, data in pool_data.items():
            if data['interruption_rate'] <= self.hp['SAFE_INTERRUPT_RATE_THRESHOLD']:
                safe_pools.append(pool_id)

        return safe_pools

    def compute_rolling_baseline(self, current_idx):
        """Compute dynamic baseline using only past data"""
        lookback_days = self.hp['BASELINE_DISCOUNT_WINDOW_DAYS']
        lookback_cutoff = self.timeline[current_idx] - timedelta(days=lookback_days)
        min_lookback_cutoff = self.timeline[current_idx] - timedelta(days=self.hp['MIN_LOOKBACK_DAYS_FOR_BASELINE'])

        if current_idx == 0 or self.timeline[current_idx] < min_lookback_cutoff:
            return None

        all_discounts = []
        all_volatilities = []

        for i in range(current_idx):
            ts = self.timeline[i]
            if ts < lookback_cutoff:
                continue

            pool_data = self.pool_data_by_time.get(ts, {})
            for pool_id, data in pool_data.items():
                all_discounts.append(data['discount'])

        if len(all_discounts) < 10:
            return None

        # Compute volatility per pool
        for pool_id in self.pools.keys():
            pool_discounts = []
            for i in range(current_idx):
                ts = self.timeline[i]
                if ts < lookback_cutoff:
                    continue
                data = self.pool_data_by_time.get(ts, {}).get(pool_id)
                if data:
                    pool_discounts.append(data['discount'])
            if len(pool_discounts) > 1:
                all_volatilities.append(np.std(pool_discounts))

        baseline = {
            'discount_mean': np.mean(all_discounts),
            'discount_std': np.std(all_discounts) if np.std(all_discounts) > 0 else 0.01,
            'volatility_mean': np.mean(all_volatilities) if all_volatilities else 0.05,
            'volatility_std': np.std(all_volatilities) if len(all_volatilities) > 1 else 0.01
        }

        return baseline

    def compute_global_trend(self, current_idx):
        """Compute global discount trend using only past data"""
        trend_days = self.hp['GLOBAL_DISCOUNT_TREND_WINDOW_DAYS']
        lookback_cutoff = self.timeline[current_idx] - timedelta(days=trend_days)

        discount_series = []
        time_indices = []

        for i in range(current_idx):
            ts = self.timeline[i]
            if ts < lookback_cutoff:
                continue

            pool_data = self.pool_data_by_time.get(ts, {})
            discounts_at_t = [data['discount'] for data in pool_data.values()]
            if discounts_at_t:
                discount_series.append(np.mean(discounts_at_t))
                time_indices.append(i)

        if len(discount_series) < 2:
            return 0.0

        # Linear regression slope
        x = np.array(time_indices)
        y = np.array(discount_series)
        slope = np.polyfit(x, y, 1)[0]

        return slope

    def rank_pools_with_ml(self, safe_pools, timestamp, baseline):
        """
        Rank pools using current prices + ML predictions
        """
        pool_scores = []
        pool_data = self.pool_data_by_time.get(timestamp, {})

        for pool_id in safe_pools:
            data = pool_data.get(pool_id)
            if not data:
                continue

            # Get ML prediction for future price
            predicted_price, confidence = self.predict_future_price(pool_id, timestamp)

            # Calculate predicted discount if we have ML prediction
            if predicted_price is not None and confidence > 0:
                predicted_discount = (data['on_demand_price'] - predicted_price) / data['on_demand_price']
                predicted_discount = max(0, min(1, predicted_discount))

                # Weight current and predicted discount
                effective_discount = data['discount'] * 0.5 + predicted_discount * 0.5
            else:
                effective_discount = data['discount']

            # Objective score
            interruption_penalty = data['interruption_rate'] * self.hp['INTERRUPTION_PENALTY_MULTIPLIER']
            switch_penalty = self.hp['SWITCH_COST_PENALTY'] if pool_id != self.current_pool else 0.0

            score = (
                effective_discount * self.hp['COST_WEIGHT']
                - interruption_penalty * self.hp['STABILITY_WEIGHT']
                - switch_penalty
            )

            pool_scores.append((pool_id, score, data, predicted_price, confidence))

        # Sort by score descending
        pool_scores.sort(key=lambda x: x[1], reverse=True)

        return pool_scores

    def should_switch_with_ml(self, current_pool, candidate_pool, timestamp, baseline, global_trend):
        """
        Decide if we should switch using ML prediction
        """
        if current_pool is None:
            return True, "Initial pool selection"

        if candidate_pool == current_pool:
            return False, "Already in best pool"

        # Check switch limit
        current_date = timestamp.date()
        if self.last_switch_date == current_date and self.switches_today >= self.hp['MAX_SWITCHES_PER_DAY']:
            return False, f"Hit max switches per day ({self.hp['MAX_SWITCHES_PER_DAY']})"

        # Get pool data
        pool_data = self.pool_data_by_time.get(timestamp, {})
        current_data = pool_data.get(current_pool)
        candidate_data = pool_data.get(candidate_pool)

        if not current_data or not candidate_data:
            return False, "Missing pool data"

        # ML prediction for current pool - will it breach baseline?
        current_predicted, current_conf = self.predict_future_price(current_pool, timestamp)

        # Check baseline breach using ML prediction
        baseline_breach = False
        if baseline:
            current_discount_global = np.mean([d['discount'] for d in pool_data.values()])
            discount_zscore = (current_discount_global - baseline['discount_mean']) / baseline['discount_std']

            # Also check if ML predicts price increase
            ml_breach = False
            if current_predicted is not None and current_conf > 0.5:
                price_increase_pct = (current_predicted - current_data['spot_price']) / current_data['spot_price']
                if price_increase_pct > self.hp['ML_BASELINE_BREACH_THRESHOLD']:
                    ml_breach = True

            baseline_breach = (
                abs(discount_zscore) > self.hp['DISCOUNT_ZSCORE_SWITCH_THRESHOLD'] or
                abs(global_trend) > self.hp['GLOBAL_TREND_SWITCH_THRESHOLD'] or
                ml_breach
            )
        else:
            baseline_breach = True

        # Calculate improvements
        cost_improvement = candidate_data['discount'] - current_data['discount']
        stability_improvement = current_data['interruption_rate'] - candidate_data['interruption_rate']

        cost_improvement_pct = cost_improvement / (current_data['discount'] + 0.01)
        stability_improvement_pct = stability_improvement / (current_data['interruption_rate'] + 0.01)

        # Switch if baseline breach + significant improvement
        if baseline_breach:
            if cost_improvement_pct > self.hp['MIN_COST_IMPROVEMENT_PCT']:
                return True, f"ML/Cost improvement: {cost_improvement_pct*100:.1f}%"
            if stability_improvement_pct > self.hp['MIN_STABILITY_IMPROVEMENT']:
                return True, f"Stability improvement: {stability_improvement_pct*100:.1f}%"

        return False, "No significant improvement"

    def run_backtest(self, strategy_name="ML-Enhanced Dynamic Switching"):
        """Run ML-enhanced backtest"""
        print(f"\n🚀 Running backtest: {strategy_name}")

        total_cost = 0.0
        total_on_demand_cost = 0.0
        interruption_count = 0
        ml_predictions_used = 0

        # Sample if requested
        timeline = self.timeline
        if self.hp['SAMPLE_BACKTEST_HOURS']:
            sample_size = self.hp['SAMPLE_BACKTEST_HOURS'] * 6
            timeline = timeline[:min(sample_size, len(timeline))]

        for idx, timestamp in enumerate(timeline):
            if idx % 1000 == 0:
                print(f"  Progress: {idx}/{len(timeline)} ({idx/len(timeline)*100:.1f}%)")

            # Compute baseline
            baseline = self.compute_rolling_baseline(idx)

            # Compute global trend
            global_trend = self.compute_global_trend(idx)

            # Get safe pools
            safe_pools = self.get_safe_pools(timestamp)

            if not safe_pools:
                pool_data = self.pool_data_by_time.get(timestamp, {})
                if pool_data:
                    safe_pools = [min(pool_data.keys(), key=lambda p: pool_data[p]['interruption_rate'])]
                else:
                    continue

            # Rank pools with ML
            ranked_pools = self.rank_pools_with_ml(safe_pools, timestamp, baseline)

            if not ranked_pools:
                continue

            best_pool_id, best_score, best_data, predicted_price, confidence = ranked_pools[0]

            if predicted_price is not None:
                ml_predictions_used += 1

            # Decide switch with ML
            if self.current_pool is None:
                should_switch_flag, reason = True, "Initial selection"
            else:
                should_switch_flag, reason = self.should_switch_with_ml(
                    self.current_pool, best_pool_id, timestamp, baseline, global_trend
                )

            # Execute switch
            if should_switch_flag and best_pool_id != self.current_pool:
                self.current_pool = best_pool_id
                self.switch_count += 1

                current_date = timestamp.date()
                if self.last_switch_date != current_date:
                    self.switches_today = 0
                self.switches_today += 1
                self.last_switch_date = current_date

            # Track costs
            pool_data = self.pool_data_by_time.get(timestamp, {})
            current_data = pool_data.get(self.current_pool)

            if not current_data:
                continue

            interval_hours = 1/6
            spot_cost = current_data['spot_price'] * interval_hours
            on_demand_cost = current_data['on_demand_price'] * interval_hours

            total_cost += spot_cost
            total_on_demand_cost += on_demand_cost

            # Track interruptions
            if np.random.random() < current_data['interruption_rate'] * interval_hours:
                interruption_count += 1

            # Record history
            self.history.append({
                'timestamp': timestamp,
                'pool_id': self.current_pool,
                'spot_price': current_data['spot_price'],
                'on_demand_price': current_data['on_demand_price'],
                'interruption_rate': current_data['interruption_rate'],
                'discount': current_data['discount'],
                'cost_incurred': spot_cost,
                'baseline_discount': baseline['discount_mean'] if baseline else None,
                'global_trend': global_trend,
                'ml_prediction_used': predicted_price is not None
            })

        # Calculate metrics
        total_hours = len(timeline) / 6
        avg_discount = (1 - total_cost / total_on_demand_cost) if total_on_demand_cost > 0 else 0

        metrics = {
            'strategy_name': strategy_name,
            'total_cost': total_cost,
            'total_on_demand_cost': total_on_demand_cost,
            'total_savings': total_on_demand_cost - total_cost,
            'avg_discount_pct': avg_discount * 100,
            'interruption_count': interruption_count,
            'switch_count': self.switch_count,
            'total_hours': total_hours,
            'cost_per_hour': total_cost / total_hours if total_hours > 0 else 0,
            'ml_predictions_used': ml_predictions_used,
            'ml_usage_pct': (ml_predictions_used / len(timeline) * 100) if len(timeline) > 0 else 0
        }

        print(f"\n✓ Backtest complete")
        print(f"  ML predictions used: {ml_predictions_used:,} ({metrics['ml_usage_pct']:.1f}%)")

        return metrics

# ============================================================================
# RUN BACKTESTS
# ============================================================================

print("\n" + "="*80)
print("5. RUNNING ML-ENHANCED BACKTESTS")
print("="*80)

def run_all_strategies(pools, pool_models, hyperparameters):
    """Run all strategies"""
    strategies = []

    # Strategy 1: ML-Enhanced Dynamic Switching
    print("\n📊 Strategy 1: ML-Enhanced Dynamic Switching")
    backtester = MLEnhancedBacktester(pools, pool_models, hyperparameters)
    metrics = backtester.run_backtest("ML-Enhanced Dynamic Switching")
    strategies.append(metrics)

    # Strategy 2: Always On-Demand
    print("\n📊 Strategy 2: Always On-Demand (Baseline)")
    total_on_demand = 0
    timeline = sorted(set().union(*[set(p['timeseries']['timestamp']) for p in pools.values()]))
    for ts in timeline:
        for pool_id, pool in pools.items():
            pool_ts = pool['timeseries']
            matching = pool_ts[pool_ts['timestamp'] == ts]
            if len(matching) > 0:
                total_on_demand += matching.iloc[0]['on_demand_price'] / 6
                break

    strategies.append({
        'strategy_name': 'Always On-Demand',
        'total_cost': total_on_demand,
        'total_on_demand_cost': total_on_demand,
        'total_savings': 0,
        'avg_discount_pct': 0,
        'interruption_count': 0,
        'switch_count': 0,
        'total_hours': len(timeline) / 6,
        'cost_per_hour': total_on_demand / (len(timeline) / 6),
        'ml_predictions_used': 0,
        'ml_usage_pct': 0
    })

    # Strategy 3: Fixed Best Pool
    print("\n📊 Strategy 3: Fixed Best Pool (Never Switch)")
    best_pool_id = max(pools.keys(), key=lambda pid: pools[pid]['timeseries']['discount'].mean())
    print(f"  Best historical pool: {best_pool_id}")

    total_cost_fixed = 0
    total_on_demand_fixed = 0
    interruptions_fixed = 0

    for _, row in pools[best_pool_id]['timeseries'].iterrows():
        interval_hours = 1/6
        total_cost_fixed += row['spot_price'] * interval_hours
        total_on_demand_fixed += row['on_demand_price'] * interval_hours
        if np.random.random() < row['interruption_rate'] * interval_hours:
            interruptions_fixed += 1

    strategies.append({
        'strategy_name': f'Fixed Best Pool ({best_pool_id})',
        'total_cost': total_cost_fixed,
        'total_on_demand_cost': total_on_demand_fixed,
        'total_savings': total_on_demand_fixed - total_cost_fixed,
        'avg_discount_pct': (1 - total_cost_fixed / total_on_demand_fixed) * 100,
        'interruption_count': interruptions_fixed,
        'switch_count': 0,
        'total_hours': len(pools[best_pool_id]['timeseries']) / 6,
        'cost_per_hour': total_cost_fixed / (len(pools[best_pool_id]['timeseries']) / 6),
        'ml_predictions_used': 0,
        'ml_usage_pct': 0
    })

    return strategies

# Run all strategies
all_strategies = run_all_strategies(pools, pool_models, HYPERPARAMETERS)

# ============================================================================
# PERFORMANCE COMPARISON
# ============================================================================

print("\n" + "="*80)
print("6. PERFORMANCE COMPARISON")
print("="*80)

comparison_df = pd.DataFrame(all_strategies)

print("\n📊 Strategy Comparison:")
print("="*80)
for _, row in comparison_df.iterrows():
    print(f"\n🎯 {row['strategy_name']}")
    print(f"  Total Cost: ${row['total_cost']:.2f}")
    print(f"  Savings vs On-Demand: ${row['total_savings']:.2f} ({row['avg_discount_pct']:.1f}%)")
    print(f"  Cost per Hour: ${row['cost_per_hour']:.4f}")
    print(f"  Interruptions: {row['interruption_count']}")
    print(f"  Switches: {row['switch_count']}")
    print(f"  Total Hours: {row['total_hours']:.1f}")
    if row['ml_predictions_used'] > 0:
        print(f"  ML Predictions: {row['ml_predictions_used']:,} ({row['ml_usage_pct']:.1f}%)")

# Find best strategy
best_strategy = comparison_df.loc[comparison_df['total_savings'].idxmax()]
print(f"\n🏆 BEST STRATEGY: {best_strategy['strategy_name']}")
print(f"  Total Savings: ${best_strategy['total_savings']:.2f}")
print(f"  Average Discount: {best_strategy['avg_discount_pct']:.1f}%")

# ============================================================================
# VISUALIZATION
# ============================================================================

print("\n" + "="*80)
print("7. GENERATING VISUALIZATIONS")
print("="*80)

# Create comparison chart
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle('ML-Enhanced Backtest Performance - 2025 Mumbai Data', fontsize=16, fontweight='bold')

# Chart 1: Total Cost Comparison
ax1 = axes[0, 0]
strategies_sorted = comparison_df.sort_values('total_cost')
colors = ['green' if s == best_strategy['strategy_name'] else 'gray' for s in strategies_sorted['strategy_name']]
ax1.barh(range(len(strategies_sorted)), strategies_sorted['total_cost'], color=colors, alpha=0.7)
ax1.set_yticks(range(len(strategies_sorted)))
ax1.set_yticklabels(strategies_sorted['strategy_name'])
ax1.set_xlabel('Total Cost ($)', fontweight='bold')
ax1.set_title('Total Cost by Strategy (Lower is Better)', fontweight='bold')
ax1.grid(axis='x', alpha=0.3)

# Chart 2: Savings vs On-Demand
ax2 = axes[0, 1]
strategies_sorted = comparison_df.sort_values('total_savings', ascending=False)
colors = ['green' if s == best_strategy['strategy_name'] else 'gray' for s in strategies_sorted['strategy_name']]
ax2.barh(range(len(strategies_sorted)), strategies_sorted['total_savings'], color=colors, alpha=0.7)
ax2.set_yticks(range(len(strategies_sorted)))
ax2.set_yticklabels(strategies_sorted['strategy_name'])
ax2.set_xlabel('Savings vs On-Demand ($)', fontweight='bold')
ax2.set_title('Total Savings (Higher is Better)', fontweight='bold')
ax2.grid(axis='x', alpha=0.3)

# Chart 3: Interruptions vs Switches
ax3 = axes[1, 0]
for _, row in comparison_df.iterrows():
    color = 'green' if row['strategy_name'] == best_strategy['strategy_name'] else 'gray'
    ax3.scatter(row['switch_count'], row['interruption_count'],
               s=200, alpha=0.6, color=color, edgecolors='black')
    ax3.annotate(row['strategy_name'],
                (row['switch_count'], row['interruption_count']),
                xytext=(5, 5), textcoords='offset points', fontsize=9)
ax3.set_xlabel('Number of Switches', fontweight='bold')
ax3.set_ylabel('Number of Interruptions', fontweight='bold')
ax3.set_title('Interruptions vs Switches Trade-off', fontweight='bold')
ax3.grid(alpha=0.3)

# Chart 4: ML Usage
ax4 = axes[1, 1]
ml_strategies = comparison_df[comparison_df['ml_predictions_used'] > 0]
if len(ml_strategies) > 0:
    ax4.bar(range(len(ml_strategies)), ml_strategies['ml_usage_pct'], color='steelblue', alpha=0.7)
    ax4.set_xticks(range(len(ml_strategies)))
    ax4.set_xticklabels(ml_strategies['strategy_name'], rotation=15, ha='right')
    ax4.set_ylabel('ML Predictions Used (%)', fontweight='bold')
    ax4.set_title('ML Model Usage by Strategy', fontweight='bold')
    ax4.grid(axis='y', alpha=0.3)
else:
    ax4.text(0.5, 0.5, 'No ML strategies used', ha='center', va='center', fontsize=14)
    ax4.axis('off')

plt.tight_layout()
output_path = Path(CONFIG['output_dir']) / 'ml_enhanced_backtest_comparison.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight')
print(f"\n✓ Saved visualization: {output_path}")
plt.close()

# ============================================================================
# SUMMARY & NEXT STEPS
# ============================================================================

print("\n" + "="*80)
print("✅ ML-ENHANCED BACKTESTING COMPLETE!")
print("="*80)

print(f"\n📈 Summary:")
print(f"  Training data: 2023-2024")
print(f"  Test data: 2025")
print(f"  ML models trained: {len(pool_models)}")
print(f"  Pools analyzed: {len(pools)}")
print(f"  Strategies compared: {len(all_strategies)}")
print(f"  Best strategy: {best_strategy['strategy_name']}")
print(f"  Total savings: ${best_strategy['total_savings']:.2f}")
print(f"  Average discount: {best_strategy['avg_discount_pct']:.1f}%")
if best_strategy['ml_predictions_used'] > 0:
    print(f"  ML predictions used: {best_strategy['ml_predictions_used']:,} ({best_strategy['ml_usage_pct']:.1f}%)")

print(f"\n🎯 Next Steps:")
print(f"  1. Review visualization: {output_path}")
print(f"  2. Fine-tune HYPERPARAMETERS at top of script")
print(f"  3. Integrate spot advisor web scraper for real interruption rates")
print(f"  4. Deploy ML models and decision engine to production")

print(f"\n💡 ML Model Integration:")
print(f"  - Trained models saved to: {Path(CONFIG['models_dir']) / 'pool_price_models.pkl'}")
print(f"  - Load in production: pickle.load(open('pool_price_models.pkl', 'rb'))")
print(f"  - Predict: model['pool_id']['model'].predict(scaler.transform(features))")

print("\n" + "="*80)
print(f"End Time: {datetime.now()}")
print("="*80)
