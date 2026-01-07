# ML Training and Backtesting Guide

Complete pipeline for training ML models and backtesting the decision engine.

## Overview

This script performs:
1. **Data Generation**: Creates realistic spot pricing and interruption data
2. **Feature Engineering**: Prepares features for ML models
3. **Model Training**: Trains Price Predictor and Stability Ranker
4. **Backtesting**: Simulates decision engine on 2025 data
5. **Analysis**: Generates comprehensive graphs and metrics

## Configuration

### Pools
- **Instance Types**: t3.large, m5.large, c5.large, m5.xlarge (4 types)
- **Availability Zones**: us-east-1a, us-east-1b, us-east-1c (3 AZs)
- **Total Pools**: 12 (4 × 3)

### Decision Logic
- **Priority**: Stability (70%) > Cost (30%)
- **Baseline**: Dynamic - calculated as average discount across all pools
- **Migration Threshold**:
  - Stability improvement > 10 points, OR
  - Stability improvement > 5 points AND cost savings > 5%

### Backtesting Period
- **Training Data**: 2024-01-01 to 2024-12-31 (12 months)
- **Backtesting Data**: 2025-01-01 to 2025-01-31 (1 month)
- **Decision Interval**: 1 hour

## Installation

```bash
cd scripts/
pip install -r requirements_ml.txt
```

## Usage

### Run Complete Pipeline

```bash
python train_and_backtest.py
```

This will:
1. Generate 13 months of synthetic data (Jan 2024 - Jan 2025)
2. Train both ML models
3. Run backtest on January 2025
4. Generate all graphs and reports

### Expected Runtime

- **Data Generation**: ~2 minutes
- **Feature Engineering**: ~1 minute
- **Model Training**: ~3 minutes
- **Backtesting**: ~2 minutes
- **Visualization**: ~1 minute
- **Total**: ~10 minutes

## Outputs

### 1. Data Files (`data/`)

- `spot_prices.csv`: Historical spot prices for all 12 pools
  - Columns: timestamp, pool_id, instance_type, az, spot_price, on_demand_price, discount_percent
  - Records: ~2.8 million (13 months × 12 pools × 288 samples/day)

- `interruptions.csv`: Spot interruption events
  - Columns: timestamp, pool_id, instance_type, az, spot_price, discount_percent
  - Records: Varies based on interruption rate (~10k events)

### 2. Trained Models (`models/`)

- `price_predictor.pkl`: Random Forest price prediction model
  - Input: Time features, lag features, rolling statistics
  - Output: Predicted spot price 1 hour ahead
  - Metrics: MAE, RMSE, R² score

- `stability_ranker.pkl`: Gradient Boosting stability classifier
  - Input: Price volatility, interruption history, time features
  - Output: Probability of interruption in next hour
  - Metrics: ROC-AUC score

- `backtest_results.json`: Complete backtesting results
  - Our strategy cost, migrations, savings
  - Baseline comparisons
  - All decisions made during backtest

### 3. Visualizations (`analysis_graphs/`)

#### `1_price_distribution.png`
- Spot price distribution by instance type and AZ
- Discount distribution
- Price time series

#### `2_stability_analysis.png`
- Interruptions by instance type
- Interruption rate over time
- Price volatility analysis
- Interruptions vs discount correlation

#### `3_model_performance.png`
- Price predictor: MAE, RMSE (train vs test)
- Stability ranker: AUC score (train vs test)

#### `4_backtest_results.png`
- **Cost Comparison**: Our strategy vs single spot vs on-demand
- **Savings Percentage**: How much we save
- **Migration Count**: Number of pool switches
- **Stability Timeline**: Stability scores over time with migration markers

#### `5_decision_distribution.png`
- Action distribution (STAY vs MIGRATE)
- Instance type preferences
- Stability improvement distribution
- Expected savings distribution

## Interpreting Results

### Model Performance

**Good Performance Indicators**:
- Price Predictor:
  - MAE < 0.01 (within 1 cent)
  - RMSE < 0.015
  - R² > 0.7

- Stability Ranker:
  - AUC > 0.75
  - Better than random (0.5)

### Backtesting Metrics

**Success Criteria**:
- Savings vs Single Spot: > 0% (we're better than staying put)
- Savings vs On-Demand: > 50% (significant cost reduction)
- Migration Count: 10-30 per month (not too frequent)
- Migration Cost: < 20% of total savings

### Expected Results (Typical Run)

```
Our Strategy:
  Total Cost: $45-55
  Migrations: 15-25
  Migration Cost: $2-4

Baselines:
  Single Spot (best pool): $50-60
  On-Demand: $70-75

Savings:
  vs Single Spot: 5-15%
  vs On-Demand: 30-40%
```

## Customization

### Change Backtesting Period

Edit constants in `train_and_backtest.py`:

```python
BACKTEST_START = '2025-01-01'
BACKTEST_END = '2025-02-28'  # 2 months instead
```

### Add More Instance Types

```python
INSTANCE_TYPES = ['t3.large', 'm5.large', 'c5.large', 'm5.xlarge', 'r5.large']
ON_DEMAND_PRICES = {
    # ... existing ...
    'r5.large': 0.126
}
```

### Adjust Decision Thresholds

In `Backtester._make_decision()`:

```python
# Current: stability > 10 OR (stability > 5 AND cost > 5%)
if stability_improvement > 15:  # More conservative
    should_migrate = True
```

### Change Priority Weights

In `Backtester._make_decision()`:

```python
# Current: Stability 70%, Cost 30%
pools['composite_score'] = (
    pools['stability_rank'] * 0.80 +  # More stability focus
    pools['cost_rank'] * 0.20
)
```

## Troubleshooting

### Issue: Low AUC Score (<0.6)

**Cause**: Not enough interruption events in training data

**Solution**: Increase interruption rates in `DataGenerator.generate_interruption_events()`:

```python
interruption_rates = {
    't3.large': 0.030,  # Increased from 0.020
    # ...
}
```

### Issue: High MAE (>0.02)

**Cause**: Price volatility too high or model underfitting

**Solution**: Add more features or increase model complexity:

```python
model = RandomForestRegressor(
    n_estimators=200,  # Increased from 100
    max_depth=20,      # Increased from 15
    # ...
)
```

### Issue: Too Many Migrations

**Cause**: Thresholds too low

**Solution**: Increase migration thresholds in decision logic

### Issue: No Savings vs Single Spot

**Cause**: Best pool is too stable, no benefit to switching

**Solution**: This is actually good! It means single spot is optimal. Try:
- More volatile pricing data
- Different instance types
- Longer backtesting period

## Advanced Usage

### Use Real AWS Data

Replace `DataGenerator` with real spot price history:

```python
# Instead of generator.generate_spot_prices()
price_df = pd.read_csv('aws_spot_history.csv')
```

### Export Trained Models

Models are already saved as `.pkl` files. To use in production:

```python
import pickle

with open('models/price_predictor.pkl', 'rb') as f:
    model_data = pickle.load(f)

price_model = model_data['model']
scaler = model_data['scaler']
feature_cols = model_data['feature_cols']

# Make prediction
features = # ... extract features ...
scaled_features = scaler.transform(features)
predicted_price = price_model.predict(scaled_features)
```

### Parallel Processing

For faster training on large datasets:

```python
model = RandomForestRegressor(
    n_jobs=-1,  # Use all CPU cores
    # ...
)
```

## Next Steps

1. **Review Graphs**: Check `analysis_graphs/` for visual insights
2. **Tune Models**: Adjust hyperparameters based on performance
3. **Validate Logic**: Review backtest decisions in `backtest_results.json`
4. **Production Deployment**: Copy trained models to backend/models/
5. **Continuous Training**: Re-run monthly with new data

## Architecture Integration

These trained models integrate with the decision engine:

```
train_and_backtest.py
    ↓
models/price_predictor.pkl → backend/ml_models/price_predictor.py
models/stability_ranker.pkl → backend/ml_models/stability_ranker.py
    ↓
backend/decision_engine/engine_enhanced.py
    ↓
backend/decision_api.py
```

Replace placeholder ML models with these trained ones for production use.

## Support

For issues or questions:
1. Check logs in console output
2. Review generated graphs for anomalies
3. Inspect `data/*.csv` files for data quality
4. Validate `models/backtest_results.json` for decision logic

---

**Version**: 3.0.0
**Last Updated**: 2025-12-02
**Status**: Production Ready ✅
