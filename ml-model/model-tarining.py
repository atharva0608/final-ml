"""
CAST-AI Mini - ML Training & Decision Engine Backtesting
=========================================================

This script trains ML models and runs comprehensive backtesting that mimics
the real production decision engines on blind 2025 data.

Architecture: Agentless (no agents on instances, direct AWS SDK)
Region: ap-south-1 (Mumbai)
Instance Types: t3.medium, t4g.medium, c5.large, t4g.small
Availability Zones: ap-south-1a, ap-south-1b, ap-south-1c
Total Pools: 12 (4 instance types × 3 AZs)

Backtesting Strategy:
- Dynamic baseline (calculated from pool averages, not fixed)
- Blind backtesting (uses only past information)
- Pool switching across ANY instance type and AZ
- Global trend analysis (demand vs capacity signals)
- Mimics production decision engine logic
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
from collections import defaultdict
warnings.filterwarnings('ignore')

# ML libraries
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, mean_absolute_percentage_error
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
    # Data paths - YOUR ACTUAL LOCAL FILE PATHS (same as original script)
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
    'availability_zones': ['ap-south-1a', 'ap-south-1b', 'ap-south-1c'],  # 3 AZs
    # Total pools: 4 instance types × 3 AZs = 12 pools

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
print("1. DATA LOADING")
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

    return df

def load_mumbai_2025_data():
    """
    Load Mumbai 2025 spot price data for backtesting
    """
    print("\n📂 Loading 2025 Mumbai Spot price data for backtesting...")

    # Load Q1, Q2, Q3 2025 data
    dataframes = []
    for quarter, path in [('Q1', CONFIG['test_q1']), ('Q2', CONFIG['test_q2']), ('Q3', CONFIG['test_q3'])]:
        if Path(path).exists():
            print(f"  Loading {quarter} 2025: {Path(path).name}")
            df = pd.read_csv(path)
            df = standardize_columns(df)
            dataframes.append(df)
        else:
            print(f"  ⚠️  {quarter} data not found: {path}")

    if not dataframes:
        print("\n❌ ERROR: No 2025 data files found!")
        print("  Please ensure the following files exist:")
        print(f"    - {CONFIG['test_q1']}")
        print(f"    - {CONFIG['test_q2']}")
        print(f"    - {CONFIG['test_q3']}")
        sys.exit(1)

    # Concatenate all quarters
    df_2025 = pd.concat(dataframes, ignore_index=True)
    df_2025 = df_2025.sort_values('timestamp').reset_index(drop=True)

    # Filter to configured region, instance types, and AZs
    df_2025 = df_2025[
        (df_2025['region'] == CONFIG['region']) &
        (df_2025['instance_type'].isin(CONFIG['instance_types'])) &
        (df_2025['availability_zone'].isin(CONFIG['availability_zones']))
    ]

    print(f"\n✓ Loaded {len(df_2025):,} records from 2025")
    print(f"  Date range: {df_2025['timestamp'].min()} to {df_2025['timestamp'].max()}")
    print(f"  Instance types: {sorted(df_2025['instance_type'].unique())}")
    print(f"  Availability zones: {sorted(df_2025['availability_zone'].unique())}")

    # Check for interruption_rate column
    if 'interruption_rate' not in df_2025.columns:
        print("\n⚠️  WARNING: interruption_rate column not found in data!")
        print("  Generating synthetic interruption rates for demonstration...")
        # TODO: Replace with real interruption rates from spot advisor web scraper
        np.random.seed(HYPERPARAMETERS['RANDOM_SEED'])
        df_2025['interruption_rate'] = np.random.uniform(0.01, 0.15, size=len(df_2025))

    return df_2025

# Load 2025 data
df_2025 = load_mumbai_2025_data()

# ============================================================================
# POOL REPRESENTATION
# ============================================================================

print("\n" + "="*80)
print("2. POOL REPRESENTATION (12 Pools = 4 Instance Types × 3 AZs)")
print("="*80)

def build_pool_timeseries(df):
    """
    Build per-pool time series for each (instance_type, availability_zone) combination

    Returns: Dictionary with pool_id as key, containing:
      - instance_type
      - availability_zone
      - timeseries (DataFrame with columns: timestamp, spot_price, on_demand_price, interruption_rate, discount)
    """
    pools = {}

    for instance_type in CONFIG['instance_types']:
        for az in CONFIG['availability_zones']:
            pool_id = f"{instance_type}_{az}"

            # Filter data for this pool
            pool_data = df[
                (df['instance_type'] == instance_type) &
                (df['availability_zone'] == az)
            ].copy()

            if len(pool_data) == 0:
                print(f"  ⚠️  No data for pool {pool_id}")
                continue

            # Sort by timestamp
            pool_data = pool_data.sort_values('timestamp').reset_index(drop=True)

            pools[pool_id] = {
                'instance_type': instance_type,
                'availability_zone': az,
                'timeseries': pool_data[['timestamp', 'spot_price', 'on_demand_price', 'interruption_rate', 'discount']].copy()
            }

    return pools

# Build pool timeseries
pools = build_pool_timeseries(df_2025)

print(f"\n✓ Built timeseries for {len(pools)} pools:")
for pool_id, pool in pools.items():
    ts_len = len(pool['timeseries'])
    ts_start = pool['timeseries']['timestamp'].min()
    ts_end = pool['timeseries']['timestamp'].max()
    avg_discount = pool['timeseries']['discount'].mean() * 100
    avg_interrupt = pool['timeseries']['interruption_rate'].mean() * 100
    print(f"  {pool_id}: {ts_len:,} records, {avg_discount:.1f}% avg discount, {avg_interrupt:.1f}% avg interrupt rate")

if len(pools) != 12:
    print(f"\n⚠️  WARNING: Expected 12 pools but got {len(pools)}")

# ============================================================================
# BLIND BACKTESTING ENGINE
# ============================================================================

print("\n" + "="*80)
print("3. BLIND BACKTESTING ENGINE (Mimics Production Decision Engine)")
print("="*80)

class BlindBacktester:
    """
    Blind backtesting engine that mimics the production decision engine.
    Uses only past information to make decisions at each timestep.
    """

    def __init__(self, pools, hyperparameters):
        self.pools = pools
        self.hp = hyperparameters

        # Build unified timeline (all timestamps across all pools)
        all_timestamps = set()
        for pool in pools.values():
            all_timestamps.update(pool['timeseries']['timestamp'])
        self.timeline = sorted(all_timestamps)

        # Pool price/interruption lookup by timestamp
        self.pool_data_by_time = self._build_pool_lookup()

        # Historical state
        self.current_pool = None
        self.switches_today = 0
        self.last_switch_date = None
        self.switch_count = 0

        # Metrics tracking
        self.history = []

        print(f"\n📅 Backtest timeline: {len(self.timeline):,} unique timestamps")
        print(f"   Start: {self.timeline[0]}")
        print(f"   End: {self.timeline[-1]}")

    def _build_pool_lookup(self):
        """Build lookup dict: {timestamp: {pool_id: {spot_price, on_demand_price, interruption_rate, discount}}}"""
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

    def get_safe_pools(self, timestamp):
        """Determine which pools are safe at given timestamp"""
        pool_data = self.pool_data_by_time.get(timestamp, {})
        safe_pools = []

        for pool_id, data in pool_data.items():
            if data['interruption_rate'] <= self.hp['SAFE_INTERRUPT_RATE_THRESHOLD']:
                safe_pools.append(pool_id)

        return safe_pools

    def compute_rolling_baseline(self, current_idx):
        """
        Compute dynamic baseline using only data UP TO current_idx-1 (blind backtest)
        Returns: {
            'discount_mean': float,
            'discount_std': float,
            'volatility_mean': float,
            'volatility_std': float
        }
        """
        # Need minimum lookback
        lookback_days = self.hp['BASELINE_DISCOUNT_WINDOW_DAYS']
        lookback_cutoff = self.timeline[current_idx] - timedelta(days=lookback_days)
        min_lookback_cutoff = self.timeline[current_idx] - timedelta(days=self.hp['MIN_LOOKBACK_DAYS_FOR_BASELINE'])

        if current_idx == 0 or self.timeline[current_idx] < min_lookback_cutoff:
            # Not enough history
            return None

        # Collect all discounts across all pools within window (using only past data)
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

        # Compute volatility as rolling std of discounts per pool
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
        """
        Compute global discount trend (slope) using only past data
        Returns: slope (positive = discounts increasing, negative = decreasing)
        """
        trend_days = self.hp['GLOBAL_DISCOUNT_TREND_WINDOW_DAYS']
        lookback_cutoff = self.timeline[current_idx] - timedelta(days=trend_days)

        # Collect global mean discount per timestamp
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

    def rank_pools(self, safe_pools, timestamp, baseline):
        """
        Rank safe pools by stability (interruption rate) and cost (discount)
        Returns: list of (pool_id, score) tuples, sorted best to worst
        """
        pool_scores = []
        pool_data = self.pool_data_by_time.get(timestamp, {})

        for pool_id in safe_pools:
            data = pool_data.get(pool_id)
            if not data:
                continue

            # Objective score: maximize discount, minimize interruption, penalize switching
            interruption_penalty = data['interruption_rate'] * self.hp['INTERRUPTION_PENALTY_MULTIPLIER']
            switch_penalty = self.hp['SWITCH_COST_PENALTY'] if pool_id != self.current_pool else 0.0

            score = (
                data['discount'] * self.hp['COST_WEIGHT']
                - interruption_penalty * self.hp['STABILITY_WEIGHT']
                - switch_penalty
            )

            pool_scores.append((pool_id, score, data))

        # Sort by score descending (higher is better)
        pool_scores.sort(key=lambda x: x[1], reverse=True)

        return pool_scores

    def should_switch(self, current_pool, candidate_pool, timestamp, baseline, global_trend):
        """
        Decide if we should switch from current_pool to candidate_pool
        Returns: (bool, reason)
        """
        if current_pool is None:
            return True, "Initial pool selection"

        if candidate_pool == current_pool:
            return False, "Already in best pool"

        # Check switch limit per day
        current_date = timestamp.date()
        if self.last_switch_date == current_date and self.switches_today >= self.hp['MAX_SWITCHES_PER_DAY']:
            return False, f"Hit max switches per day ({self.hp['MAX_SWITCHES_PER_DAY']})"

        # Get current and candidate pool data
        pool_data = self.pool_data_by_time.get(timestamp, {})
        current_data = pool_data.get(current_pool)
        candidate_data = pool_data.get(candidate_pool)

        if not current_data or not candidate_data:
            return False, "Missing pool data"

        # Check if baseline breach occurred
        if baseline:
            current_discount_global = np.mean([d['discount'] for d in pool_data.values()])
            discount_zscore = (current_discount_global - baseline['discount_mean']) / baseline['discount_std']

            baseline_breach = (
                abs(discount_zscore) > self.hp['DISCOUNT_ZSCORE_SWITCH_THRESHOLD'] or
                abs(global_trend) > self.hp['GLOBAL_TREND_SWITCH_THRESHOLD']
            )
        else:
            baseline_breach = True  # No baseline yet, allow switches

        # Calculate improvements
        cost_improvement = candidate_data['discount'] - current_data['discount']
        stability_improvement = current_data['interruption_rate'] - candidate_data['interruption_rate']

        cost_improvement_pct = cost_improvement / (current_data['discount'] + 0.01)
        stability_improvement_pct = stability_improvement / (current_data['interruption_rate'] + 0.01)

        # Switch if significant improvement in cost OR stability
        if baseline_breach:
            if cost_improvement_pct > self.hp['MIN_COST_IMPROVEMENT_PCT']:
                return True, f"Cost improvement: {cost_improvement_pct*100:.1f}%"
            if stability_improvement_pct > self.hp['MIN_STABILITY_IMPROVEMENT']:
                return True, f"Stability improvement: {stability_improvement_pct*100:.1f}%"

        return False, "No significant improvement"

    def run_backtest(self, strategy_name="Dynamic Switching"):
        """
        Run the blind backtest strategy
        Returns: performance metrics
        """
        print(f"\n🚀 Running backtest: {strategy_name}")

        total_cost = 0.0
        total_on_demand_cost = 0.0
        interruption_count = 0

        # Sample if requested
        timeline = self.timeline
        if self.hp['SAMPLE_BACKTEST_HOURS']:
            sample_size = self.hp['SAMPLE_BACKTEST_HOURS'] * 6  # 10-min intervals
            timeline = timeline[:min(sample_size, len(timeline))]

        for idx, timestamp in enumerate(timeline):
            if idx % 1000 == 0:
                print(f"  Progress: {idx}/{len(timeline)} ({idx/len(timeline)*100:.1f}%)")

            # Compute baseline (using only past data)
            baseline = self.compute_rolling_baseline(idx)

            # Compute global trend
            global_trend = self.compute_global_trend(idx)

            # Get safe pools at current timestamp
            safe_pools = self.get_safe_pools(timestamp)

            if not safe_pools:
                # No safe pools - fall back to least risky pool
                pool_data = self.pool_data_by_time.get(timestamp, {})
                if pool_data:
                    safe_pools = [min(pool_data.keys(), key=lambda p: pool_data[p]['interruption_rate'])]
                else:
                    # No data at all - skip this timestamp
                    continue

            # Rank pools
            ranked_pools = self.rank_pools(safe_pools, timestamp, baseline)

            if not ranked_pools:
                continue

            best_pool_id, best_score, best_data = ranked_pools[0]

            # Decide if we should switch
            if self.current_pool is None:
                should_switch_flag, reason = True, "Initial selection"
            else:
                should_switch_flag, reason = self.should_switch(
                    self.current_pool, best_pool_id, timestamp, baseline, global_trend
                )

            # Execute switch if needed
            if should_switch_flag and best_pool_id != self.current_pool:
                old_pool = self.current_pool
                self.current_pool = best_pool_id
                self.switch_count += 1

                current_date = timestamp.date()
                if self.last_switch_date != current_date:
                    self.switches_today = 0
                self.switches_today += 1
                self.last_switch_date = current_date

            # Get current pool data
            pool_data = self.pool_data_by_time.get(timestamp, {})
            current_data = pool_data.get(self.current_pool)

            if not current_data:
                continue

            # Track costs (assume 10-minute interval = 1/6 hour)
            interval_hours = 1/6
            spot_cost = current_data['spot_price'] * interval_hours
            on_demand_cost = current_data['on_demand_price'] * interval_hours

            total_cost += spot_cost
            total_on_demand_cost += on_demand_cost

            # Track interruptions (probabilistically)
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
                'global_trend': global_trend
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
            'cost_per_hour': total_cost / total_hours if total_hours > 0 else 0
        }

        return metrics

# ============================================================================
# RUN BACKTESTS
# ============================================================================

print("\n" + "="*80)
print("4. RUNNING BACKTESTS (Comparing Strategies)")
print("="*80)

def run_baseline_strategies(pools, hyperparameters):
    """Run baseline strategies for comparison"""

    strategies = []

    # Strategy 1: Dynamic Switching (main strategy)
    print("\n📊 Strategy 1: Dynamic Switching with Baseline Monitoring")
    backtester = BlindBacktester(pools, hyperparameters)
    metrics = backtester.run_backtest("Dynamic Switching")
    strategies.append(metrics)

    # Strategy 2: Always On-Demand
    print("\n📊 Strategy 2: Always On-Demand (Baseline)")
    # Just use on-demand prices
    total_on_demand = 0
    timeline = sorted(set().union(*[set(p['timeseries']['timestamp']) for p in pools.values()]))
    for ts in timeline:
        for pool_id, pool in pools.items():
            pool_ts = pool['timeseries']
            matching = pool_ts[pool_ts['timestamp'] == ts]
            if len(matching) > 0:
                total_on_demand += matching.iloc[0]['on_demand_price'] / 6  # 10-min interval
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
        'cost_per_hour': total_on_demand / (len(timeline) / 6)
    })

    # Strategy 3: Fixed Best Pool (historical best)
    print("\n📊 Strategy 3: Fixed Best Pool (Never Switch)")
    # Find pool with best historical discount
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
        'cost_per_hour': total_cost_fixed / (len(pools[best_pool_id]['timeseries']) / 6)
    })

    return strategies

# Run all strategies
all_strategies = run_baseline_strategies(pools, HYPERPARAMETERS)

# ============================================================================
# PERFORMANCE COMPARISON
# ============================================================================

print("\n" + "="*80)
print("5. PERFORMANCE COMPARISON")
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

# Find best strategy
best_strategy = comparison_df.loc[comparison_df['total_savings'].idxmax()]
print(f"\n🏆 BEST STRATEGY: {best_strategy['strategy_name']}")
print(f"  Total Savings: ${best_strategy['total_savings']:.2f}")
print(f"  Average Discount: {best_strategy['avg_discount_pct']:.1f}%")

# ============================================================================
# VISUALIZATION
# ============================================================================

print("\n" + "="*80)
print("6. GENERATING VISUALIZATIONS")
print("="*80)

# Create comparison chart
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle('Backtest Performance Comparison - 2025 Mumbai Data', fontsize=16, fontweight='bold')

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

# Chart 4: Cost per Hour
ax4 = axes[1, 1]
strategies_sorted = comparison_df.sort_values('cost_per_hour')
colors = ['green' if s == best_strategy['strategy_name'] else 'gray' for s in strategies_sorted['strategy_name']]
ax4.barh(range(len(strategies_sorted)), strategies_sorted['cost_per_hour'], color=colors, alpha=0.7)
ax4.set_yticks(range(len(strategies_sorted)))
ax4.set_yticklabels(strategies_sorted['strategy_name'])
ax4.set_xlabel('Cost per Hour ($)', fontweight='bold')
ax4.set_title('Average Hourly Cost (Lower is Better)', fontweight='bold')
ax4.grid(axis='x', alpha=0.3)

plt.tight_layout()
output_path = Path(CONFIG['output_dir']) / 'backtest_comparison.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight')
print(f"\n✓ Saved visualization: {output_path}")

# ============================================================================
# SUMMARY & NEXT STEPS
# ============================================================================

print("\n" + "="*80)
print("✅ BACKTESTING COMPLETE!")
print("="*80)

print(f"\n📈 Summary:")
print(f"  Pools analyzed: {len(pools)}")
print(f"  Strategies compared: {len(all_strategies)}")
print(f"  Best strategy: {best_strategy['strategy_name']}")
print(f"  Total savings: ${best_strategy['total_savings']:.2f}")
print(f"  Average discount: {best_strategy['avg_discount_pct']:.1f}%")

print(f"\n🎯 Next Steps:")
print(f"  1. Review visualization: {output_path}")
print(f"  2. Fine-tune HYPERPARAMETERS at top of script")
print(f"  3. Integrate spot advisor web scraper for real-time interruption rates")
print(f"  4. Deploy decision engine with validated thresholds")

print(f"\n💡 TODO: Integrate Spot Advisor Web Scraper")
print(f"  - Replace synthetic interruption rates with real data")
print(f"  - Update pool list dynamically from AWS API")
print(f"  - Monitor for new instance types and AZs")

print("\n" + "="*80)
print(f"End Time: {datetime.now()}")
print("="*80)
