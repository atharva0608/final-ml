# AWS Spot Optimizer V1

> **Production-ready LightGBM system for AWS spot instance price forecasting and Risk Score prediction**

## Quick Start

```bash
# 1. Create conda environment
conda create -n lightgbm python=3.11 -y
conda activate lightgbm

# 2. Install dependencies
pip install -r requirements.txt

# 3. Train baseline models
python scripts/train.py

# 4. Run backtesting (optional)
python scripts/backtest.py
```

## Project Structure

```
spot_optimizer_v1/
├── config/config.yaml      # All configuration
├── scripts/
│   ├── train.py            # Training pipeline
│   └── backtest.py         # Walk-forward backtesting
├── src/
│   ├── __init__.py         # Package exports
│   ├── data.py             # Data loading + feature engineering
│   ├── model.py            # LightGBM hybrid model
│   └── backtest.py         # Backtesting module
├── models/                 # Saved models (generated)
├── reports/                # Metrics & plots (generated)
├── docs/                   # Detailed documentation
└── requirements.txt
```

## Features

### Core Capabilities
- **Single-horizon forecasting**: 6h ahead predictions
- **Dual model**: Regressor (savings%) + Classifier (Risk Score)
- **Risk Score output**: Calibrated probability (0.0 = Safe, 1.0 = High Risk)
- **Z-score risk zones**: Safe → Moderate → Warning → Danger

### Why 6-Hour Horizon?

The **6-hour horizon (36 steps)** is the "sweet spot" for AWS Spot instances:

| Aspect | Reasoning |
|--------|-----------|
| **Focus vs. Breadth** | Single-horizon models optimize loss solely for that timeframe, improving accuracy |
| **Actionable Window** | Provides enough time to finish most batch jobs or migrate workloads before price changes |
| **Lower Uncertainty** | More accurate than 24-hour forecasts where market dynamics are harder to predict |
| **Use Case** | Ideal for immediate instance management (e.g., "Should I launch this 4-hour job now?") |

> **Note:** If you need a 24-hour outlook for job scheduling, train a separate simpler model for that horizon rather than forcing one model to do everything. See [Technical Docs](docs/TECHNICAL_DOCS.md) for multi-horizon configuration.

### Key Innovations
| Feature | Description |
|---------|-------------|
| **Family Stress Index** | Detects cross-instance contagion within families |
| **Family-Time Patterns** | Learns instance-family specific time patterns from data |
| **Walk-Forward Backtesting** | Time-series validation across multiple periods |

### 39 Engineered Features
- 10 Temporal (hour, day, cyclical encoding)
- 3 Lag features (1h, 4h, 24h lookback)
- 8 Rolling stats (4h, 24h windows: mean, std, min, max each)
- 5 Price dynamics (velocity, volatility, headroom, pool_saturation, consecutive_stable_hours)
- 6 Family-Time patterns (learned from data)
- 3 Family Stress features
- 3 Event features
- 1 Pool Risk (historical zero-rate)

### Memory Optimization Strategy (Polars-First)
To handle 210M+ rows on limited-memory instances, the pipeline uses a **"Polars-First Split"** strategy:
1.  **Fast Loading:** Data loaded and preprocessed in Polars (`pl.DataFrame`).
2.  **In-Memory Split:** Training/Validation/Test splits are created in Polars (Zero-Copy views) to avoid 2x duplication.
3.  **JIT Conversion:** Data is converted to Pandas *Just-In-Time* for `model.fit()`, and deleted immediately after use.
4.  **Result:** Reduces peak memory usage by ~40-60%, enabling full training on `ml.r5.8xlarge`.

## Usage

### Local Testing (Limited RAM)
```bash
# 1. Edit config.yaml to filter to 2-3 families:
#    sample_families: ['c6i', 'm6i']

# 2. Run training
python scripts/train.py
```

### Full Training (Cloud/High RAM)
```bash
# 1. Edit config.yaml to load ALL families:
#    sample_families: []

# 2. Run training
python scripts/train.py
```


**Outputs:**
- `models/regressor_{horizon}.onnx` - ONNX Optimized Model (Verified)
- `models/classifier_{horizon}.onnx` - ONNX Optimized Model (Verified)
- `models/category_mapping.json` - Required for inference
- `models/pool_baselines.json` - Per-pool statistics
- `reports/training_results.json` - Metrics

### Backtesting
```bash
python scripts/backtest.py
```

**Outputs:**
- `reports/backtest_{horizon}.json` - Per-horizon results
- `reports/backtest_combined.json` - Aggregated metrics

## Configuration

Edit `config/config.yaml`:

```yaml
data:
  parquet_files:
    - "../Data/aws_mumbai_2023_lgbm.parquet"
    - "../Data/aws_mumbai_2024_lgbm.parquet"
    - "../Data/aws_mumbai_2025_lgbm.parquet"
  sample_families: []  # Empty = ALL families. Use ['c6i', 'm6i'] for local test.

features:
  horizons: [6]  # Single horizon: 1h (6 x 10-min intervals)
  lag_intervals: [6, 24, 144]  # 1h, 4h, 24h
  rolling_windows: [24, 144]  # 4h, 24h

model:
  n_jobs: 8
  early_stopping_rounds: 100
```

## Success Criteria

| Model | Metric | Target |
|-------|--------|--------|
| Regressor | MAPE | < 5% |
| Classifier | F1 | > 80% |

## Hardware Requirements

| Mode | RAM | Instance |
|------|-----|----------|
| Local Test (2 families) | 4-8 GB | Laptop (M1/M2/M4) |
| Full data (Legacy) | >400 GB | ml.r5.24xlarge |
| Full data (Polars Optimized) | ~200 GB | ml.r5.8xlarge |

## Documentation

- [Technical Documentation](docs/TECHNICAL_DOCS.md) - Detailed architecture and API reference

## License

MIT
