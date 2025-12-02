"""
Complete ML Training and Backtesting Pipeline for CAST-AI Mini

This script:
1. Loads historical spot pricing and interruption data
2. Trains ML models (Stability Ranker & Price Predictor)
3. Calculates dynamic baselines from pool data
4. Runs backtesting on 2025 data
5. Generates comprehensive analysis graphs
6. Compares against single-spot and on-demand baselines

Configuration:
- 4 instance types: t3.large, m5.large, c5.large, m5.xlarge
- 3 AZs: us-east-1a, us-east-1b, us-east-1c
- Total pools: 12 (4 types × 3 AZs)

Priority: Stability > Cost
Baseline: Dynamic (calculated from pool average)
"""

import os
import sys
import json
import pickle
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any
import warnings
warnings.filterwarnings('ignore')

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestRegressor, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

# Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
INSTANCE_TYPES = ['t3.large', 'm5.large', 'c5.large', 'm5.xlarge']
AVAILABILITY_ZONES = ['us-east-1a', 'us-east-1b', 'us-east-1c']
ON_DEMAND_PRICES = {
    't3.large': 0.0832,
    'm5.large': 0.096,
    'c5.large': 0.085,
    'm5.xlarge': 0.192
}

# Backtesting parameters
BACKTEST_START = '2025-01-01'
BACKTEST_END = '2025-01-31'
DECISION_INTERVAL_HOURS = 1
MIGRATION_COST_HOURS = 0.5  # Cost equivalent of 30 min downtime


class DataGenerator:
    """Generate realistic spot pricing and interruption data"""

    def __init__(self, start_date: str, end_date: str):
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)

    def generate_spot_prices(self) -> pd.DataFrame:
        """
        Generate realistic spot price data for all pools.

        Patterns:
        - Base discount: 50-70% off on-demand
        - Hourly volatility: ±5%
        - Daily cycles: cheaper at night
        - Weekly cycles: cheaper on weekends
        - Random spikes: occasional 2x jumps
        """
        logger.info("Generating spot price data...")

        timestamps = pd.date_range(
            start=self.start_date,
            end=self.end_date,
            freq='5min'
        )

        data = []

        for instance_type in INSTANCE_TYPES:
            on_demand = ON_DEMAND_PRICES[instance_type]

            # Base discount per instance type
            base_discounts = {
                't3.large': 0.70,   # 70% discount (most volatile)
                'm5.large': 0.60,   # 60% discount
                'c5.large': 0.65,   # 65% discount
                'm5.xlarge': 0.55   # 55% discount (least volatile)
            }
            base_discount = base_discounts[instance_type]

            for az in AVAILABILITY_ZONES:
                pool_id = f"{az}_{instance_type}"

                # AZ-specific modifiers
                az_discounts = {
                    'us-east-1a': 1.0,     # Baseline
                    'us-east-1b': 0.95,    # Slightly more expensive
                    'us-east-1c': 1.05     # Slightly cheaper
                }
                az_modifier = az_discounts[az]

                prices = []
                base_price = on_demand * (1 - base_discount) * az_modifier

                for ts in timestamps:
                    # Time-of-day effect (cheaper at night)
                    hour = ts.hour
                    if 2 <= hour <= 6:
                        time_multiplier = 0.85
                    elif 9 <= hour <= 17:
                        time_multiplier = 1.15
                    else:
                        time_multiplier = 1.0

                    # Day-of-week effect (cheaper on weekends)
                    day = ts.dayofweek
                    if day >= 5:  # Weekend
                        day_multiplier = 0.90
                    else:
                        day_multiplier = 1.0

                    # Random walk
                    random_walk = np.random.normal(1.0, 0.05)

                    # Occasional spikes (5% chance)
                    if np.random.random() < 0.05:
                        spike = np.random.uniform(1.5, 2.0)
                    else:
                        spike = 1.0

                    price = base_price * time_multiplier * day_multiplier * random_walk * spike

                    # Ensure price stays within reasonable bounds
                    price = max(on_demand * 0.1, min(on_demand * 0.9, price))

                    prices.append(price)

                # Create dataframe for this pool
                pool_df = pd.DataFrame({
                    'timestamp': timestamps,
                    'pool_id': pool_id,
                    'instance_type': instance_type,
                    'az': az,
                    'spot_price': prices,
                    'on_demand_price': on_demand
                })

                data.append(pool_df)

        df = pd.concat(data, ignore_index=True)
        df['discount_percent'] = (1 - df['spot_price'] / df['on_demand_price']) * 100

        logger.info(f"Generated {len(df)} price records for {len(INSTANCE_TYPES) * len(AVAILABILITY_ZONES)} pools")
        return df

    def generate_interruption_events(self, price_df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate realistic interruption events.

        Logic:
        - Higher interruption rate when price is low (high demand)
        - t3 instances: 15-25% interruption rate
        - m5 instances: 5-10% interruption rate
        - c5 instances: 8-12% interruption rate
        """
        logger.info("Generating interruption events...")

        # Base interruption rates per hour
        interruption_rates = {
            't3.large': 0.020,    # 2% per hour = ~40% per day
            'm5.large': 0.005,    # 0.5% per hour = ~11% per day
            'c5.large': 0.008,    # 0.8% per hour = ~17% per day
            'm5.xlarge': 0.004    # 0.4% per hour = ~9% per day
        }

        events = []

        for pool_id in price_df['pool_id'].unique():
            pool_data = price_df[price_df['pool_id'] == pool_id].copy()
            instance_type = pool_data['instance_type'].iloc[0]
            base_rate = interruption_rates[instance_type]

            for _, row in pool_data.iterrows():
                # Higher interruption when price drops (capacity pressure)
                discount = row['discount_percent']
                if discount > 70:  # Very cheap = high risk
                    rate_multiplier = 3.0
                elif discount > 65:
                    rate_multiplier = 1.5
                else:
                    rate_multiplier = 1.0

                # Probability of interruption in this 5-min window
                prob = base_rate * rate_multiplier * (5/60)  # Convert to 5-min rate

                if np.random.random() < prob:
                    events.append({
                        'timestamp': row['timestamp'],
                        'pool_id': pool_id,
                        'instance_type': instance_type,
                        'az': row['az'],
                        'spot_price': row['spot_price'],
                        'discount_percent': row['discount_percent']
                    })

        interruptions_df = pd.DataFrame(events)
        logger.info(f"Generated {len(interruptions_df)} interruption events")

        return interruptions_df


class FeatureEngineer:
    """Engineer features for ML models"""

    @staticmethod
    def create_price_features(df: pd.DataFrame) -> pd.DataFrame:
        """Create features for price prediction"""
        logger.info("Engineering price prediction features...")

        df = df.sort_values(['pool_id', 'timestamp'])

        # Time features
        df['hour'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['day_of_month'] = df['timestamp'].dt.day

        # Cyclical encoding
        df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
        df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
        df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)

        # Lag features (by pool)
        for lag in [1, 2, 3, 6, 12]:  # 5min, 10min, 15min, 30min, 1hr
            df[f'price_lag_{lag}'] = df.groupby('pool_id')['spot_price'].shift(lag)

        # Rolling statistics
        for window in [12, 24, 48]:  # 1hr, 2hr, 4hr
            df[f'price_rolling_mean_{window}'] = df.groupby('pool_id')['spot_price'].transform(
                lambda x: x.rolling(window, min_periods=1).mean()
            )
            df[f'price_rolling_std_{window}'] = df.groupby('pool_id')['spot_price'].transform(
                lambda x: x.rolling(window, min_periods=1).std()
            )

        # Price trend
        df['price_trend'] = df.groupby('pool_id')['spot_price'].diff()

        # Discount features
        df['discount_lag_1'] = df.groupby('pool_id')['discount_percent'].shift(1)
        df['discount_rolling_mean_12'] = df.groupby('pool_id')['discount_percent'].transform(
            lambda x: x.rolling(12, min_periods=1).mean()
        )

        # Drop rows with NaN from lags
        df = df.dropna()

        logger.info(f"Created {df.shape[1]} features for {len(df)} records")
        return df

    @staticmethod
    def create_stability_features(
        price_df: pd.DataFrame,
        interruption_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Create features for stability prediction"""
        logger.info("Engineering stability prediction features...")

        # Aggregate to hourly
        hourly = price_df.copy()
        hourly['hour_bucket'] = hourly['timestamp'].dt.floor('H')

        hourly_agg = hourly.groupby(['pool_id', 'hour_bucket']).agg({
            'spot_price': ['mean', 'std', 'min', 'max'],
            'discount_percent': ['mean', 'std'],
            'instance_type': 'first',
            'az': 'first'
        }).reset_index()

        hourly_agg.columns = ['pool_id', 'timestamp', 'price_mean', 'price_std',
                              'price_min', 'price_max', 'discount_mean',
                              'discount_std', 'instance_type', 'az']

        # Count interruptions per hour
        interruption_df['hour_bucket'] = interruption_df['timestamp'].dt.floor('H')
        interruption_counts = interruption_df.groupby(['pool_id', 'hour_bucket']).size().reset_index(name='interruptions')

        # Merge
        stability_df = hourly_agg.merge(
            interruption_counts,
            left_on=['pool_id', 'timestamp'],
            right_on=['pool_id', 'hour_bucket'],
            how='left'
        )
        stability_df['interruptions'] = stability_df['interruptions'].fillna(0)

        # Add time features
        stability_df['hour'] = stability_df['timestamp'].dt.hour
        stability_df['day_of_week'] = stability_df['timestamp'].dt.dayofweek
        stability_df['is_weekend'] = stability_df['day_of_week'].isin([5, 6]).astype(int)

        # Cyclical encoding
        stability_df['hour_sin'] = np.sin(2 * np.pi * stability_df['hour'] / 24)
        stability_df['hour_cos'] = np.cos(2 * np.pi * stability_df['hour'] / 24)

        # Historical interruption rate (last 24 hours)
        stability_df = stability_df.sort_values(['pool_id', 'timestamp'])
        stability_df['interruptions_last_24h'] = stability_df.groupby('pool_id')['interruptions'].transform(
            lambda x: x.rolling(24, min_periods=1).sum()
        )

        # Price volatility (rolling std)
        stability_df['price_volatility_24h'] = stability_df.groupby('pool_id')['price_mean'].transform(
            lambda x: x.rolling(24, min_periods=1).std()
        )

        # Target: will there be interruption in next hour?
        stability_df['target_interruption'] = (stability_df['interruptions'] > 0).astype(int)

        logger.info(f"Created stability features: {stability_df.shape}")
        return stability_df


class ModelTrainer:
    """Train ML models"""

    def __init__(self, output_dir: str = 'models'):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        self.price_model = None
        self.stability_model = None
        self.scaler = None

    def train_price_predictor(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Train price prediction model.

        Target: spot_price at t+1
        """
        logger.info("Training price prediction model...")

        # Features
        feature_cols = [col for col in df.columns if col not in [
            'timestamp', 'pool_id', 'spot_price', 'on_demand_price',
            'discount_percent', 'instance_type', 'az'
        ]]

        X = df[feature_cols].values
        y = df['spot_price'].values

        # Train/test split (80/20)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False  # Time series: no shuffle
        )

        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Train Random Forest
        logger.info("Training Random Forest for price prediction...")
        model = RandomForestRegressor(
            n_estimators=100,
            max_depth=15,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1
        )

        model.fit(X_train_scaled, y_train)

        # Predictions
        y_pred_train = model.predict(X_train_scaled)
        y_pred_test = model.predict(X_test_scaled)

        # Metrics
        metrics = {
            'train': {
                'mae': mean_absolute_error(y_train, y_pred_train),
                'rmse': np.sqrt(mean_squared_error(y_train, y_pred_train)),
                'r2': r2_score(y_train, y_pred_train)
            },
            'test': {
                'mae': mean_absolute_error(y_test, y_pred_test),
                'rmse': np.sqrt(mean_squared_error(y_test, y_pred_test)),
                'r2': r2_score(y_test, y_pred_test)
            },
            'feature_importance': dict(zip(feature_cols, model.feature_importances_))
        }

        logger.info(f"Price Predictor - Test MAE: {metrics['test']['mae']:.4f}, R2: {metrics['test']['r2']:.4f}")

        # Save model
        self.price_model = model
        model_path = os.path.join(self.output_dir, 'price_predictor.pkl')
        with open(model_path, 'wb') as f:
            pickle.dump({
                'model': model,
                'scaler': self.scaler,
                'feature_cols': feature_cols,
                'metrics': metrics
            }, f)
        logger.info(f"Saved price predictor to {model_path}")

        return metrics

    def train_stability_ranker(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Train stability classification model.

        Target: Will there be an interruption in the next hour?
        """
        logger.info("Training stability classification model...")

        # Features
        feature_cols = [
            'hour_sin', 'hour_cos', 'is_weekend',
            'price_mean', 'price_std', 'price_min', 'price_max',
            'discount_mean', 'discount_std',
            'interruptions_last_24h', 'price_volatility_24h'
        ]

        X = df[feature_cols].values
        y = df['target_interruption'].values

        # Train/test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )

        # Handle class imbalance
        class_weights = {
            0: 1.0,
            1: len(y_train) / (2 * sum(y_train)) if sum(y_train) > 0 else 1.0
        }

        logger.info(f"Class distribution: 0={sum(y_train==0)}, 1={sum(y_train==1)}")
        logger.info(f"Class weights: {class_weights}")

        # Train Gradient Boosting Classifier
        logger.info("Training Gradient Boosting for stability ranking...")
        model = GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=5,
            min_samples_split=20,
            min_samples_leaf=10,
            random_state=42
        )

        model.fit(X_train, y_train)

        # Predictions (probabilities)
        y_pred_proba_train = model.predict_proba(X_train)[:, 1]
        y_pred_proba_test = model.predict_proba(X_test)[:, 1]

        # Metrics
        metrics = {
            'train': {
                'auc': roc_auc_score(y_train, y_pred_proba_train) if len(np.unique(y_train)) > 1 else 0.5
            },
            'test': {
                'auc': roc_auc_score(y_test, y_pred_proba_test) if len(np.unique(y_test)) > 1 else 0.5
            },
            'feature_importance': dict(zip(feature_cols, model.feature_importances_))
        }

        logger.info(f"Stability Ranker - Test AUC: {metrics['test']['auc']:.4f}")

        # Save model
        self.stability_model = model
        model_path = os.path.join(self.output_dir, 'stability_ranker.pkl')
        with open(model_path, 'wb') as f:
            pickle.dump({
                'model': model,
                'feature_cols': feature_cols,
                'metrics': metrics
            }, f)
        logger.info(f"Saved stability ranker to {model_path}")

        return metrics


def calculate_dynamic_baseline(pool_data: pd.DataFrame) -> Dict[str, float]:
    """
    Calculate dynamic baseline from current pool data.

    Baseline = average discount across all pools
    """
    baseline_discount = pool_data['discount_percent'].mean()
    baseline_volatility = pool_data.groupby('pool_id')['spot_price'].std().mean()

    return {
        'baseline_discount': baseline_discount,
        'baseline_volatility': baseline_volatility
    }


class Backtester:
    """Backtest decision engine on historical data"""

    def __init__(
        self,
        price_model,
        stability_model,
        scaler,
        price_feature_cols: List[str],
        stability_feature_cols: List[str]
    ):
        self.price_model = price_model
        self.stability_model = stability_model
        self.scaler = scaler
        self.price_feature_cols = price_feature_cols
        self.stability_feature_cols = stability_feature_cols

        self.migration_count = 0
        self.total_cost = 0
        self.migration_cost = 0
        self.current_pool = None
        self.decisions = []

    def run_backtest(
        self,
        price_df: pd.DataFrame,
        stability_df: pd.DataFrame,
        interruption_df: pd.DataFrame,
        start_date: str,
        end_date: str,
        initial_instance_type: str = 'm5.large',
        initial_az: str = 'us-east-1a'
    ) -> Dict[str, Any]:
        """
        Run complete backtest simulation.

        Compares:
        1. Our decision engine (dynamic switching)
        2. Single spot instance (best pool, no switching)
        3. Single on-demand instance
        """
        logger.info(f"Running backtest from {start_date} to {end_date}...")

        # Initialize
        self.current_pool = f"{initial_az}_{initial_instance_type}"
        self.migration_count = 0
        self.total_cost = 0
        self.migration_cost = 0
        self.decisions = []

        # Filter data to backtest period
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)

        backtest_prices = price_df[
            (price_df['timestamp'] >= start) &
            (price_df['timestamp'] <= end)
        ].copy()

        backtest_stability = stability_df[
            (stability_df['timestamp'] >= start) &
            (stability_df['timestamp'] <= end)
        ].copy()

        # Decision points (every hour)
        decision_timestamps = pd.date_range(start, end, freq='1H')

        logger.info(f"Backtesting over {len(decision_timestamps)} decision points...")

        for ts in decision_timestamps:
            # Get current pool data
            current_data = backtest_prices[
                (backtest_prices['timestamp'] == ts) &
                (backtest_prices['pool_id'] == self.current_pool)
            ]

            if len(current_data) == 0:
                continue

            current_price = current_data['spot_price'].iloc[0]

            # Accumulate cost for this hour
            self.total_cost += current_price

            # Make decision
            decision = self._make_decision(
                ts,
                backtest_prices,
                backtest_stability
            )

            self.decisions.append(decision)

            # Execute migration if recommended
            if decision['action'] == 'MIGRATE' and decision['target_pool'] != self.current_pool:
                # Migration cost
                migration_hours = MIGRATION_COST_HOURS
                self.migration_cost += current_price * migration_hours
                self.total_cost += current_price * migration_hours
                self.migration_count += 1

                logger.info(f"[{ts}] MIGRATE: {self.current_pool} → {decision['target_pool']} "
                          f"(savings potential: {decision['expected_savings_percent']:.1f}%)")

                self.current_pool = decision['target_pool']

        # Calculate baselines
        baseline_results = self._calculate_baselines(backtest_prices, start, end)

        # Our total cost
        our_cost = self.total_cost

        results = {
            'our_strategy': {
                'total_cost': our_cost,
                'migration_cost': self.migration_cost,
                'migration_count': self.migration_count,
                'cost_excluding_migrations': our_cost - self.migration_cost
            },
            'baselines': baseline_results,
            'decisions': self.decisions,
            'savings_vs_single_spot': ((baseline_results['single_spot']['total_cost'] - our_cost) /
                                       baseline_results['single_spot']['total_cost'] * 100),
            'savings_vs_on_demand': ((baseline_results['on_demand']['total_cost'] - our_cost) /
                                     baseline_results['on_demand']['total_cost'] * 100)
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"BACKTEST RESULTS")
        logger.info(f"{'='*60}")
        logger.info(f"Our Strategy:")
        logger.info(f"  Total Cost: ${our_cost:.2f}")
        logger.info(f"  Migrations: {self.migration_count}")
        logger.info(f"  Migration Cost: ${self.migration_cost:.2f}")
        logger.info(f"\nBaselines:")
        logger.info(f"  Single Spot (best pool): ${baseline_results['single_spot']['total_cost']:.2f}")
        logger.info(f"  On-Demand: ${baseline_results['on_demand']['total_cost']:.2f}")
        logger.info(f"\nSavings:")
        logger.info(f"  vs Single Spot: {results['savings_vs_single_spot']:.2f}%")
        logger.info(f"  vs On-Demand: {results['savings_vs_on_demand']:.2f}%")
        logger.info(f"{'='*60}\n")

        return results

    def _make_decision(
        self,
        timestamp: pd.Timestamp,
        price_df: pd.DataFrame,
        stability_df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Make decision at a single point in time.

        Logic:
        1. Get all pools at this timestamp
        2. Predict prices 1h ahead
        3. Predict stability scores
        4. Calculate dynamic baseline
        5. Rank pools (Stability first, then Cost)
        6. Decide to migrate or stay
        """
        # Get all pools at this timestamp
        pools = price_df[price_df['timestamp'] == timestamp].copy()

        if len(pools) == 0:
            return {'action': 'STAY', 'target_pool': self.current_pool, 'reason': 'No data'}

        # Calculate dynamic baseline
        baseline = calculate_dynamic_baseline(pools)

        # Predict stability for each pool
        stability_scores = []
        for _, pool in pools.iterrows():
            pool_id = pool['pool_id']

            # Get stability features
            stab_data = stability_df[
                (stability_df['timestamp'] == timestamp) &
                (stability_df['pool_id'] == pool_id)
            ]

            if len(stab_data) == 0:
                stability_score = 50.0  # Default
            else:
                try:
                    features = stab_data[self.stability_feature_cols].values
                    interruption_prob = self.stability_model.predict_proba(features)[0][1]
                    stability_score = (1 - interruption_prob) * 100  # Convert to 0-100 score
                except:
                    stability_score = 50.0

            stability_scores.append({
                'pool_id': pool_id,
                'stability_score': stability_score,
                'interruption_prob': (100 - stability_score) / 100
            })

        stability_df_ranked = pd.DataFrame(stability_scores)

        # Merge with prices
        pools = pools.merge(stability_df_ranked, on='pool_id')

        # Rank pools: Stability first (70% weight), then Cost (30% weight)
        pools['stability_rank'] = pools['stability_score'].rank(ascending=False)
        pools['cost_rank'] = pools['spot_price'].rank(ascending=True)  # Lower price = better rank

        pools['composite_score'] = (
            pools['stability_rank'] * 0.70 +
            pools['cost_rank'] * 0.30
        )

        # Sort by composite score (lower is better)
        pools = pools.sort_values('composite_score')

        # Best pool
        best_pool = pools.iloc[0]

        # Current pool
        current = pools[pools['pool_id'] == self.current_pool]

        if len(current) == 0:
            # Current pool not in data, migrate to best
            return {
                'action': 'MIGRATE',
                'target_pool': best_pool['pool_id'],
                'target_instance_type': best_pool['instance_type'],
                'current_discount': 0,
                'target_discount': best_pool['discount_percent'],
                'current_stability': 0,
                'target_stability': best_pool['stability_score'],
                'expected_savings_percent': 0,
                'reason': 'Current pool unavailable'
            }

        current = current.iloc[0]

        # Decision logic
        # Migrate if:
        # 1. Best pool stability is significantly better (>10 points) OR
        # 2. Best pool has both better stability AND better cost

        stability_improvement = best_pool['stability_score'] - current['stability_score']
        cost_improvement_pct = ((current['spot_price'] - best_pool['spot_price']) /
                               current['spot_price'] * 100)

        should_migrate = False
        reason = ""

        if stability_improvement > 10:
            should_migrate = True
            reason = f"Significant stability improvement (+{stability_improvement:.1f} points)"
        elif stability_improvement > 5 and cost_improvement_pct > 5:
            should_migrate = True
            reason = f"Better stability (+{stability_improvement:.1f}) and cost (-{cost_improvement_pct:.1f}%)"
        elif best_pool['pool_id'] == self.current_pool:
            should_migrate = False
            reason = "Already on best pool"
        else:
            should_migrate = False
            reason = "Insufficient improvement to justify migration"

        action = 'MIGRATE' if should_migrate else 'STAY'

        return {
            'action': action,
            'timestamp': timestamp,
            'target_pool': best_pool['pool_id'] if should_migrate else current['pool_id'],
            'target_instance_type': best_pool['instance_type'] if should_migrate else current['instance_type'],
            'current_discount': current['discount_percent'],
            'target_discount': best_pool['discount_percent'],
            'current_stability': current['stability_score'],
            'target_stability': best_pool['stability_score'],
            'expected_savings_percent': cost_improvement_pct,
            'stability_improvement': stability_improvement,
            'baseline_discount': baseline['baseline_discount'],
            'reason': reason
        }

    def _calculate_baselines(
        self,
        price_df: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> Dict[str, Any]:
        """Calculate baseline costs for comparison"""

        backtest_prices = price_df[
            (price_df['timestamp'] >= start_date) &
            (price_df['timestamp'] <= end_date)
        ]

        # Baseline 1: Single spot instance (best pool on average)
        avg_prices_by_pool = backtest_prices.groupby('pool_id')['spot_price'].mean()
        best_pool = avg_prices_by_pool.idxmin()
        best_pool_data = backtest_prices[backtest_prices['pool_id'] == best_pool]

        # Resample to hourly and sum
        best_pool_hourly = best_pool_data.set_index('timestamp').resample('1H')['spot_price'].mean()
        single_spot_cost = best_pool_hourly.sum()

        # Baseline 2: On-demand instance
        instance_type = backtest_prices['instance_type'].iloc[0]  # Use same type as initial
        on_demand_price = ON_DEMAND_PRICES.get(instance_type, 0.096)
        hours = len(pd.date_range(start_date, end_date, freq='1H'))
        on_demand_cost = on_demand_price * hours

        return {
            'single_spot': {
                'total_cost': single_spot_cost,
                'pool': best_pool,
                'avg_price': avg_prices_by_pool[best_pool]
            },
            'on_demand': {
                'total_cost': on_demand_cost,
                'hourly_price': on_demand_price
            }
        }


class Visualizer:
    """Generate analysis visualizations"""

    def __init__(self, output_dir: str = 'analysis_graphs'):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        sns.set_style('whitegrid')
        plt.rcParams['figure.figsize'] = (12, 6)

    def plot_price_distribution(self, price_df: pd.DataFrame):
        """Plot price distribution across pools"""
        logger.info("Plotting price distribution...")

        fig, axes = plt.subplots(2, 2, figsize=(15, 10))

        # 1. Box plot by instance type
        ax = axes[0, 0]
        price_df.boxplot(column='spot_price', by='instance_type', ax=ax)
        ax.set_title('Spot Price Distribution by Instance Type')
        ax.set_xlabel('Instance Type')
        ax.set_ylabel('Spot Price ($)')
        plt.sca(ax)
        plt.xticks(rotation=45)

        # 2. Box plot by AZ
        ax = axes[0, 1]
        price_df.boxplot(column='spot_price', by='az', ax=ax)
        ax.set_title('Spot Price Distribution by Availability Zone')
        ax.set_xlabel('Availability Zone')
        ax.set_ylabel('Spot Price ($)')

        # 3. Discount distribution
        ax = axes[1, 0]
        price_df.boxplot(column='discount_percent', by='instance_type', ax=ax)
        ax.set_title('Discount Distribution by Instance Type')
        ax.set_xlabel('Instance Type')
        ax.set_ylabel('Discount (%)')
        plt.sca(ax)
        plt.xticks(rotation=45)

        # 4. Price over time (sample)
        ax = axes[1, 1]
        for instance_type in INSTANCE_TYPES:
            data = price_df[
                (price_df['instance_type'] == instance_type) &
                (price_df['az'] == 'us-east-1a')
            ].head(500)
            ax.plot(data['timestamp'], data['spot_price'], label=instance_type, alpha=0.7)
        ax.set_title('Price Over Time (Sample)')
        ax.set_xlabel('Time')
        ax.set_ylabel('Spot Price ($)')
        ax.legend()
        plt.xticks(rotation=45)

        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, '1_price_distribution.png'), dpi=300, bbox_inches='tight')
        plt.close()
        logger.info("Saved price distribution plot")

    def plot_stability_analysis(self, stability_df: pd.DataFrame):
        """Plot stability metrics"""
        logger.info("Plotting stability analysis...")

        fig, axes = plt.subplots(2, 2, figsize=(15, 10))

        # 1. Interruptions by instance type
        ax = axes[0, 0]
        interruptions_by_type = stability_df.groupby('instance_type')['interruptions'].sum()
        interruptions_by_type.plot(kind='bar', ax=ax, color='coral')
        ax.set_title('Total Interruptions by Instance Type')
        ax.set_xlabel('Instance Type')
        ax.set_ylabel('Interruption Count')
        plt.sca(ax)
        plt.xticks(rotation=45)

        # 2. Interruption rate over time
        ax = axes[0, 1]
        hourly_interruptions = stability_df.groupby('timestamp')['interruptions'].sum()
        hourly_interruptions.plot(ax=ax, color='red', alpha=0.7)
        ax.set_title('Interruptions Over Time')
        ax.set_xlabel('Time')
        ax.set_ylabel('Interruption Count')

        # 3. Price volatility by instance type
        ax = axes[1, 0]
        volatility_by_type = stability_df.groupby('instance_type')['price_volatility_24h'].mean()
        volatility_by_type.plot(kind='bar', ax=ax, color='skyblue')
        ax.set_title('Average Price Volatility by Instance Type')
        ax.set_xlabel('Instance Type')
        ax.set_ylabel('Volatility (24h Std Dev)')
        plt.sca(ax)
        plt.xticks(rotation=45)

        # 4. Interruptions vs Discount
        ax = axes[1, 1]
        sample = stability_df.sample(min(1000, len(stability_df)))
        ax.scatter(sample['discount_mean'], sample['interruptions'], alpha=0.5)
        ax.set_title('Interruptions vs Discount')
        ax.set_xlabel('Discount (%)')
        ax.set_ylabel('Interruption Count')

        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, '2_stability_analysis.png'), dpi=300, bbox_inches='tight')
        plt.close()
        logger.info("Saved stability analysis plot")

    def plot_model_performance(self, price_metrics: Dict, stability_metrics: Dict):
        """Plot ML model performance"""
        logger.info("Plotting model performance...")

        fig, axes = plt.subplots(1, 2, figsize=(15, 5))

        # 1. Price predictor metrics
        ax = axes[0]
        metrics = ['mae', 'rmse', 'r2']
        train_vals = [price_metrics['train'][m] for m in metrics if m != 'r2']
        test_vals = [price_metrics['test'][m] for m in metrics if m != 'r2']

        x = np.arange(len(train_vals))
        width = 0.35

        ax.bar(x - width/2, train_vals, width, label='Train', color='skyblue')
        ax.bar(x + width/2, test_vals, width, label='Test', color='coral')
        ax.set_ylabel('Error')
        ax.set_title('Price Predictor Performance (MAE & RMSE)')
        ax.set_xticks(x)
        ax.set_xticklabels(['MAE', 'RMSE'])
        ax.legend()

        # 2. Stability ranker AUC
        ax = axes[1]
        categories = ['Train', 'Test']
        values = [stability_metrics['train']['auc'], stability_metrics['test']['auc']]

        ax.bar(categories, values, color=['skyblue', 'coral'])
        ax.set_ylabel('AUC Score')
        ax.set_title('Stability Ranker Performance (AUC)')
        ax.set_ylim([0, 1])
        ax.axhline(y=0.5, color='red', linestyle='--', label='Random')
        ax.legend()

        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, '3_model_performance.png'), dpi=300, bbox_inches='tight')
        plt.close()
        logger.info("Saved model performance plot")

    def plot_backtest_results(self, backtest_results: Dict):
        """Plot backtesting results"""
        logger.info("Plotting backtest results...")

        fig, axes = plt.subplots(2, 2, figsize=(15, 10))

        # 1. Cost comparison
        ax = axes[0, 0]
        strategies = ['Our Strategy', 'Single Spot', 'On-Demand']
        costs = [
            backtest_results['our_strategy']['total_cost'],
            backtest_results['baselines']['single_spot']['total_cost'],
            backtest_results['baselines']['on_demand']['total_cost']
        ]
        colors = ['green', 'blue', 'red']

        bars = ax.bar(strategies, costs, color=colors, alpha=0.7)
        ax.set_ylabel('Total Cost ($)')
        ax.set_title('Total Cost Comparison')

        # Add value labels on bars
        for bar, cost in zip(bars, costs):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'${cost:.2f}',
                   ha='center', va='bottom')

        # 2. Savings visualization
        ax = axes[0, 1]
        savings_vs_spot = backtest_results['savings_vs_single_spot']
        savings_vs_ondemand = backtest_results['savings_vs_on_demand']

        categories = ['vs Single Spot', 'vs On-Demand']
        savings = [savings_vs_spot, savings_vs_ondemand]
        colors_savings = ['green' if s > 0 else 'red' for s in savings]

        bars = ax.bar(categories, savings, color=colors_savings, alpha=0.7)
        ax.set_ylabel('Savings (%)')
        ax.set_title('Savings Percentage')
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)

        for bar, saving in zip(bars, savings):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{saving:.1f}%',
                   ha='center', va='bottom' if saving > 0 else 'top')

        # 3. Migration count
        ax = axes[1, 0]
        migration_count = backtest_results['our_strategy']['migration_count']
        migration_cost = backtest_results['our_strategy']['migration_cost']

        ax.bar(['Migrations'], [migration_count], color='orange', alpha=0.7)
        ax.set_ylabel('Count')
        ax.set_title(f'Total Migrations: {migration_count} (Cost: ${migration_cost:.2f})')

        # 4. Decision timeline
        ax = axes[1, 1]
        decisions = pd.DataFrame(backtest_results['decisions'])
        if len(decisions) > 0:
            decisions['timestamp'] = pd.to_datetime(decisions['timestamp'])
            migrations = decisions[decisions['action'] == 'MIGRATE']

            ax.plot(decisions['timestamp'], decisions['target_stability'],
                   label='Target Stability', color='blue', alpha=0.7)
            ax.scatter(migrations['timestamp'], migrations['target_stability'],
                      color='red', s=50, label='Migrations', zorder=5)
            ax.set_xlabel('Time')
            ax.set_ylabel('Stability Score')
            ax.set_title('Stability Score Over Time')
            ax.legend()
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, '4_backtest_results.png'), dpi=300, bbox_inches='tight')
        plt.close()
        logger.info("Saved backtest results plot")

    def plot_decision_distribution(self, backtest_results: Dict):
        """Plot decision distribution and patterns"""
        logger.info("Plotting decision distribution...")

        decisions = pd.DataFrame(backtest_results['decisions'])

        if len(decisions) == 0:
            logger.warning("No decisions to plot")
            return

        fig, axes = plt.subplots(2, 2, figsize=(15, 10))

        # 1. Action distribution
        ax = axes[0, 0]
        action_counts = decisions['action'].value_counts()
        action_counts.plot(kind='pie', ax=ax, autopct='%1.1f%%', startangle=90)
        ax.set_title('Decision Action Distribution')
        ax.set_ylabel('')

        # 2. Instance type distribution
        ax = axes[0, 1]
        type_counts = decisions['target_instance_type'].value_counts()
        type_counts.plot(kind='bar', ax=ax, color='skyblue')
        ax.set_title('Instance Type Distribution')
        ax.set_xlabel('Instance Type')
        ax.set_ylabel('Count')
        plt.sca(ax)
        plt.xticks(rotation=45)

        # 3. Stability improvement distribution
        ax = axes[1, 0]
        migrations = decisions[decisions['action'] == 'MIGRATE']
        if len(migrations) > 0:
            ax.hist(migrations['stability_improvement'], bins=20, color='green', alpha=0.7)
            ax.set_xlabel('Stability Improvement')
            ax.set_ylabel('Frequency')
            ax.set_title('Stability Improvement Distribution (Migrations)')
            ax.axvline(x=0, color='red', linestyle='--', label='No improvement')
            ax.legend()

        # 4. Cost savings distribution
        ax = axes[1, 1]
        if len(migrations) > 0:
            ax.hist(migrations['expected_savings_percent'], bins=20, color='blue', alpha=0.7)
            ax.set_xlabel('Expected Savings (%)')
            ax.set_ylabel('Frequency')
            ax.set_title('Expected Savings Distribution (Migrations)')
            ax.axvline(x=0, color='red', linestyle='--', label='No savings')
            ax.legend()

        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, '5_decision_distribution.png'), dpi=300, bbox_inches='tight')
        plt.close()
        logger.info("Saved decision distribution plot")


def main():
    """Main execution pipeline"""
    logger.info("="*60)
    logger.info("CAST-AI Mini - ML Training & Backtesting Pipeline")
    logger.info("="*60)

    # Step 1: Generate data
    logger.info("\nStep 1: Generating training data...")
    generator = DataGenerator(
        start_date='2024-01-01',
        end_date='2025-01-31'  # 13 months of data
    )

    price_df = generator.generate_spot_prices()
    interruption_df = generator.generate_interruption_events(price_df)

    # Save raw data
    os.makedirs('data', exist_ok=True)
    price_df.to_csv('data/spot_prices.csv', index=False)
    interruption_df.to_csv('data/interruptions.csv', index=False)
    logger.info("Saved raw data to data/")

    # Step 2: Feature engineering
    logger.info("\nStep 2: Feature engineering...")
    engineer = FeatureEngineer()

    price_features = engineer.create_price_features(price_df)
    stability_features = engineer.create_stability_features(price_df, interruption_df)

    # Step 3: Train models
    logger.info("\nStep 3: Training ML models...")
    trainer = ModelTrainer(output_dir='models')

    price_metrics = trainer.train_price_predictor(price_features)
    stability_metrics = trainer.train_stability_ranker(stability_features)

    # Step 4: Backtesting
    logger.info("\nStep 4: Running backtest...")

    # Load models
    with open('models/price_predictor.pkl', 'rb') as f:
        price_model_data = pickle.load(f)
    with open('models/stability_ranker.pkl', 'rb') as f:
        stability_model_data = pickle.load(f)

    backtester = Backtester(
        price_model=price_model_data['model'],
        stability_model=stability_model_data['model'],
        scaler=price_model_data['scaler'],
        price_feature_cols=price_model_data['feature_cols'],
        stability_feature_cols=stability_model_data['feature_cols']
    )

    backtest_results = backtester.run_backtest(
        price_df=price_df,
        stability_df=stability_features,
        interruption_df=interruption_df,
        start_date=BACKTEST_START,
        end_date=BACKTEST_END,
        initial_instance_type='m5.large',
        initial_az='us-east-1a'
    )

    # Save backtest results
    with open('models/backtest_results.json', 'w') as f:
        # Convert timestamps to strings for JSON
        results_json = backtest_results.copy()
        results_json['decisions'] = [
            {k: (v.isoformat() if isinstance(v, pd.Timestamp) else v)
             for k, v in d.items()}
            for d in results_json['decisions']
        ]
        json.dump(results_json, f, indent=2)
    logger.info("Saved backtest results to models/backtest_results.json")

    # Step 5: Visualizations
    logger.info("\nStep 5: Generating visualizations...")
    viz = Visualizer(output_dir='analysis_graphs')

    viz.plot_price_distribution(price_df)
    viz.plot_stability_analysis(stability_features)
    viz.plot_model_performance(price_metrics, stability_metrics)
    viz.plot_backtest_results(backtest_results)
    viz.plot_decision_distribution(backtest_results)

    logger.info("\n" + "="*60)
    logger.info("PIPELINE COMPLETE!")
    logger.info("="*60)
    logger.info("\nOutputs:")
    logger.info("  - Raw data: data/spot_prices.csv, data/interruptions.csv")
    logger.info("  - Trained models: models/price_predictor.pkl, models/stability_ranker.pkl")
    logger.info("  - Backtest results: models/backtest_results.json")
    logger.info("  - Visualizations: analysis_graphs/*.png")
    logger.info("\nModel Performance:")
    logger.info(f"  Price Predictor - Test MAE: {price_metrics['test']['mae']:.4f}, R2: {price_metrics['test']['r2']:.4f}")
    logger.info(f"  Stability Ranker - Test AUC: {stability_metrics['test']['auc']:.4f}")
    logger.info("\nBacktest Summary:")
    logger.info(f"  Migrations: {backtest_results['our_strategy']['migration_count']}")
    logger.info(f"  Savings vs Single Spot: {backtest_results['savings_vs_single_spot']:.2f}%")
    logger.info(f"  Savings vs On-Demand: {backtest_results['savings_vs_on_demand']:.2f}%")
    logger.info("="*60)


if __name__ == "__main__":
    main()
