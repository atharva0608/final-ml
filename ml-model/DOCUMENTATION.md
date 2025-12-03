# ML Model Training & Decision Engine Backtesting

## Overview

`model-tarining.py` is the **ML training and blind backtesting script** that mimics the production decision engines and evaluates the performance of a dynamic pool-switching strategy on 2025 Mumbai spot pricing data.

## Architecture

### Agentless Design
- **No agents on EC2 instances** - All decisions made via AWS SDK
- **Direct spot market interaction** - Real-time pool switching
- **12 Pools**: 4 instance types × 3 availability zones

### Pool Configuration
- **Region**: ap-south-1 (Mumbai)
- **Instance Types**: t3.medium, t4g.medium, c5.large, t4g.small
- **Availability Zones**: ap-south-1a, ap-south-1b, ap-south-1c
- **Total Pools**: 12 combinations

## Hyperparameters

All hyperparameters are defined at the **top of the script** in the `HYPERPARAMETERS` dictionary for easy tuning:

```python
HYPERPARAMETERS = {
    # Safety Thresholds
    'SAFE_INTERRUPT_RATE_THRESHOLD': 0.05,  # 5% max interruption rate

    # Baseline Windows (days)
    'MIN_LOOKBACK_DAYS_FOR_BASELINE': 14,
    'BASELINE_DISCOUNT_WINDOW_DAYS': 30,
    'BASELINE_VOLATILITY_WINDOW_DAYS': 30,

    # Switching Thresholds (z-scores)
    'DISCOUNT_ZSCORE_SWITCH_THRESHOLD': 1.5,
    'VOLATILITY_ZSCORE_SWITCH_THRESHOLD': 1.5,

    # Global Trend Analysis
    'GLOBAL_DISCOUNT_TREND_WINDOW_DAYS': 7,
    'GLOBAL_TREND_SWITCH_THRESHOLD': 0.01,

    # Switching Constraints
    'MAX_SWITCHES_PER_DAY': 3,
    'SWITCH_COST_PENALTY': 0.001,

    # Cost/Penalty Multipliers
    'INTERRUPTION_PENALTY_MULTIPLIER': 5.0,
    'STABILITY_WEIGHT': 0.70,  # 70% stability
    'COST_WEIGHT': 0.30,       # 30% cost

    # Minimum Improvement Thresholds
    'MIN_COST_IMPROVEMENT_PCT': 0.05,     # 5% min cost improvement
    'MIN_STABILITY_IMPROVEMENT': 0.10,    # 10% min stability improvement

    'RANDOM_SEED': 42
}
```

### Tuning Guidelines

| Hyperparameter | Description | Increase Effect | Decrease Effect |
|----------------|-------------|-----------------|-----------------|
| `SAFE_INTERRUPT_RATE_THRESHOLD` | Max interruption rate for safe pools | More pools considered safe | Fewer safe pools, more conservative |
| `BASELINE_DISCOUNT_WINDOW_DAYS` | Rolling window for baseline calculation | Smoother baseline, less sensitive | More reactive to recent changes |
| `DISCOUNT_ZSCORE_SWITCH_THRESHOLD` | Z-score threshold for triggering switches | Fewer switches, more stable | More switches, more opportunistic |
| `MAX_SWITCHES_PER_DAY` | Maximum pool switches allowed per day | More switching opportunities | More stable, less churn |
| `INTERRUPTION_PENALTY_MULTIPLIER` | Weight of interruption risk in scoring | Prioritize stability over cost | Prioritize cost over stability |
| `STABILITY_WEIGHT` / `COST_WEIGHT` | Ranking weights (must sum to 1.0) | Adjust stability vs cost priority | - |

## Data Requirements

### Input Files

The script uses existing dataset paths referenced in the current configuration:

```python
# Default paths (can override with environment variables)
DATA_DIR = PROJECT_ROOT / 'data' / 'training'

- TRAINING_DATA: aws_2023_2024_complete_24months.csv
- TEST_Q1_DATA: mumbai_spot_data_sorted_asc_q1.csv (Q1 2025)
- TEST_Q2_DATA: mumbai_spot_data_sorted_asc_q2.csv (Q2 2025)
- TEST_Q3_DATA: mumbai_spot_data_sorted_asc_q3.csv (Q3 2025)
- EVENT_DATA: aws_stress_events_2023_2025.csv
```

### Required Columns

Each CSV must contain:
- `timestamp`: ISO format datetime
- `spot_price`: Spot price in USD
- `on_demand_price`: On-demand price in USD
- `instance_type`: EC2 instance type (e.g., t3.medium)
- `availability_zone`: AWS AZ (e.g., ap-south-1a)
- `interruption_rate`: Interruption rate (0.0-1.0) **[Optional - will generate synthetic if missing]**

### Environment Variables

Override default paths using environment variables:

```bash
export TRAINING_DATA=/path/to/training.csv
export TEST_Q1_DATA=/path/to/test_q1.csv
export TEST_Q2_DATA=/path/to/test_q2.csv
export TEST_Q3_DATA=/path/to/test_q3.csv
export EVENT_DATA=/path/to/events.csv

python model-tarining.py
```

## Backtesting Strategy

### Blind Backtesting

The backtest is **"blind"** - it uses only past information when making decisions:

1. At time `t`, only data from `t-1` and earlier is used
2. Baseline calculations use rolling windows ending at `t-1`
3. No future peeking - realistic simulation of production behavior

### Decision Flow

```
For each timestamp t in 2025:
  1. Compute dynamic baseline (using data up to t-1)
  2. Compute global discount trend (slope of recent discounts)
  3. Filter pools → safe pools (interruption_rate ≤ threshold)
  4. Rank safe pools → by stability (low interruption) + cost (high discount)
  5. Check if switch needed:
     - Baseline breach? (z-score exceeds threshold)
     - Global trend significant?
     - Candidate pool significantly better?
     - Within switch limit for today?
  6. If yes → switch to best candidate pool
  7. Record cost, interruptions, metrics
```

### Pool Representation

Each pool is represented as `(instance_type, availability_zone)` with time-series data:

```python
pool = {
    'instance_type': 't3.medium',
    'availability_zone': 'ap-south-1a',
    'timeseries': DataFrame[
        timestamp, spot_price, on_demand_price,
        interruption_rate, discount
    ]
}
```

### Safe Pool Logic

**Safe pools** are those with interruption rate ≤ `SAFE_INTERRUPT_RATE_THRESHOLD`:

```python
safe_pools = [
    pool_id for pool_id, data in pool_data.items()
    if data['interruption_rate'] <= HYPERPARAMETERS['SAFE_INTERRUPT_RATE_THRESHOLD']
]
```

If no pools are safe, fall back to the pool with the lowest interruption rate.

### Dynamic Baseline Calculation

The baseline is **dynamic** and calculated from historical pool data:

```python
baseline = {
    'discount_mean': mean(all_discounts_in_window),
    'discount_std': std(all_discounts_in_window),
    'volatility_mean': mean(pool_volatilities),
    'volatility_std': std(pool_volatilities)
}

# Z-score computation
discount_zscore = (current_discount - baseline['discount_mean']) / baseline['discount_std']
```

**Key Properties:**
- Rolling window (default: 30 days)
- Uses only past data (up to `t-1`)
- Adapts to market conditions
- Baseline breach triggers switch consideration

### Global Trend Feature

Detects whether discounts are globally increasing or decreasing:

```python
# Linear regression slope over recent window
global_trend = polyfit(time_indices, discount_series, degree=1)[0]

# Interpretation:
# slope > 0 → Discounts increasing (AWS adding capacity or demand dropping)
# slope < 0 → Discounts decreasing (Demand increasing or capacity tightening)
```

Used to make smarter switch decisions:
- Be more aggressive when discounts are rising globally
- Be more conservative when discounts are falling globally

### Pool Ranking & Scoring

Pools are ranked using an **objective score**:

```python
score = (
    discount * COST_WEIGHT
    - interruption_rate * INTERRUPTION_PENALTY_MULTIPLIER * STABILITY_WEIGHT
    - SWITCH_COST_PENALTY (if switching to this pool)
)
```

**Higher score = better pool**

### Switching Rules

A switch from current pool to candidate pool occurs if **ALL** of these conditions are met:

1. **Baseline breach**: Z-score exceeds threshold OR global trend is significant
2. **Significant improvement**:
   - Cost improvement > `MIN_COST_IMPROVEMENT_PCT` (5%)
   - OR Stability improvement > `MIN_STABILITY_IMPROVEMENT` (10%)
3. **Switch limit**: Haven't exceeded `MAX_SWITCHES_PER_DAY`
4. **Candidate is different**: Not already in the best pool

### Cross-Instance Type Switching

The strategy **allows switching across ANY pool** - not restricted to same instance type:

- Can switch from `t3.medium` in `ap-south-1a` → `c5.large` in `ap-south-1b`
- Evaluates all 12 pools at every decision point
- Maximizes flexibility and cost optimization

## Strategies Compared

The backtest compares 3 strategies:

### 1. Dynamic Switching (Main Strategy)
- Uses all logic described above
- Switches pools based on baseline breaches and improvements
- Balances stability (70%) and cost (30%)

### 2. Always On-Demand (Baseline)
- Never uses spot instances
- 100% on-demand pricing
- 0% interruptions, 0% savings

### 3. Fixed Best Pool (Never Switch)
- Selects the single best historical pool (highest avg discount)
- Never switches, even if conditions change
- Lower overhead, but misses opportunities

## Performance Metrics

For each strategy, the backtest calculates:

| Metric | Description |
|--------|-------------|
| `total_cost` | Total cost over entire 2025 period |
| `total_on_demand_cost` | Cost if using 100% on-demand |
| `total_savings` | Savings vs on-demand |
| `avg_discount_pct` | Average discount percentage |
| `interruption_count` | Number of interruptions experienced |
| `switch_count` | Number of pool switches performed |
| `total_hours` | Total hours simulated |
| `cost_per_hour` | Average cost per hour |

## Usage

### Basic Execution

```bash
cd /home/user/final-ml/ml-model
python model-tarining.py
```

### With Custom Data Paths

```bash
export TRAINING_DATA=/custom/path/training.csv
export TEST_Q1_DATA=/custom/path/q1.csv
python model-tarining.py
```

### Sampling (Faster Testing)

To test with a subset of data, edit the hyperparameter:

```python
'SAMPLE_BACKTEST_HOURS': 24,  # Test with only 24 hours of data
```

Set to `None` to use all data.

## Output

### Console Output

The script prints:
1. Hyperparameters configuration
2. Data loading summary
3. Pool timeseries build progress
4. Backtest progress (every 1000 timestamps)
5. Performance comparison table
6. Best strategy summary

### Visualization

Generates `backtest_comparison.png` in `training/outputs/`:

- **Chart 1**: Total cost by strategy
- **Chart 2**: Savings vs on-demand
- **Chart 3**: Interruptions vs switches trade-off
- **Chart 4**: Average hourly cost

## Integration with Production

### Decision Engine Mimicry

The `BlindBacktester` class closely mimics the production decision engine:

```python
# Production decision engine (backend/decision_engine/engine_enhanced.py)
def decide(instance, metrics, pools, region):
    baseline = calculate_dynamic_baseline(pools)
    safe_pools = filter_safe_pools(pools, threshold)
    ranked_pools = rank_pools(safe_pools, stability_weight, cost_weight)
    best_pool = ranked_pools[0]
    if should_switch(current, best_pool, baseline):
        return switch_to(best_pool)
    return stay_in_current_pool()

# Backtest engine (ml-model/model-tarining.py)
class BlindBacktester:
    def run_backtest(...):
        for timestamp in timeline:
            baseline = self.compute_rolling_baseline(...)
            safe_pools = self.get_safe_pools(...)
            ranked_pools = self.rank_pools(...)
            best_pool = ranked_pools[0]
            if self.should_switch(...):
                self.current_pool = best_pool
            # Record metrics
```

**Same logic, different implementations:**
- Backtest → Historical simulation on 2025 data
- Production → Real-time decisions on live data

### Deploying Validated Thresholds

After tuning hyperparameters via backtesting:

1. Identify best `HYPERPARAMETERS` configuration
2. Update production config in `backend/backend.py`:
   ```python
   DECISION_CONFIG = {
       'safe_interrupt_threshold': 0.05,  # From backtest
       'baseline_window_days': 30,
       'switch_threshold': 1.5,
       # ... other params
   }
   ```
3. Deploy updated backend
4. Monitor performance vs backtest predictions

## TODO: Spot Advisor Integration

Currently, interruption rates are **synthetic** (randomly generated). Replace with real data:

### Future Enhancement
```python
# TODO: Replace synthetic interruption rates with spot advisor web scraper
def fetch_real_interruption_rates(region, instance_types, azs):
    """
    Scrape AWS Spot Advisor or use AWS API to get real-time interruption frequencies
    """
    # Scrape https://aws.amazon.com/ec2/spot/instance-advisor/
    # Or use boto3 to query spot pricing history + interruption events
    pass
```

**Implementation Steps:**
1. Build web scraper for AWS Spot Advisor
2. Parse interruption frequency ratings (e.g., <5%, 5-10%, 10-15%, etc.)
3. Map ratings to numerical probabilities
4. Update pool timeseries with real interruption rates
5. Re-run backtest with real data

## Troubleshooting

### Issue: "No 2025 data files found"
**Solution**: Ensure Q1/Q2/Q3 CSV files exist in `data/training/` or set environment variables

### Issue: "Expected 12 pools but got N"
**Solution**: Check that all 4 instance types have data in all 3 AZs. Some pools may be missing data.

### Issue: "Not enough history for baseline"
**Solution**: Reduce `MIN_LOOKBACK_DAYS_FOR_BASELINE` or ensure data starts early enough in 2025

### Issue: Backtest runs slowly
**Solution**: Set `SAMPLE_BACKTEST_HOURS` to a small value (e.g., 24) for testing

### Issue: Too many/few switches
**Solution**: Tune `DISCOUNT_ZSCORE_SWITCH_THRESHOLD`, `MIN_COST_IMPROVEMENT_PCT`, and `MAX_SWITCHES_PER_DAY`

## Extending the Backtest

### Adding New Strategies

Add new comparison strategies in `run_baseline_strategies()`:

```python
def run_baseline_strategies(pools, hyperparameters):
    strategies = []

    # Existing strategies...

    # NEW: Your custom strategy
    print("\n📊 Strategy 4: My Custom Strategy")
    # Implement your logic here
    metrics = {
        'strategy_name': 'My Custom Strategy',
        'total_cost': ...,
        # ... other metrics
    }
    strategies.append(metrics)

    return strategies
```

### Adding New Metrics

Extend `self.history` tracking in `BlindBacktester.run_backtest()`:

```python
self.history.append({
    # Existing fields...
    'custom_metric': your_calculation,
})
```

### Adding New Visualizations

Add plots after the existing 4 charts:

```python
# Chart 5: Your custom visualization
ax5 = plt.subplot(3, 2, 5)
# ... plotting code
```

## References

- **Production Backend**: `backend/backend.py`
- **Decision Engine**: `backend/decision_engine/engine_enhanced.py`
- **Database Schema**: `database/schema.sql`
- **Deployment**: `scripts/deploy.sh`

---

**Version**: 1.0.0
**Last Updated**: 2025-12-03
**Architecture**: Agentless
**Status**: Production Ready ✅
