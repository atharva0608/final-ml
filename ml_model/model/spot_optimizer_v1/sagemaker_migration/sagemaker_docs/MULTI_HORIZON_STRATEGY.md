# Multi-Horizon Training Strategy

## Overview
This document describes strategies for training models to predict spot instance savings at multiple time horizons (1-hour, 6-hour, etc.).

---

## The Challenge

**Why you can't use one model for all horizons:**
- Different horizons require different feature weights
- Magnitude of changes varies (1h: ±2%, 6h: ±10%)
- Noise tolerance is different (1h: capture spikes, 6h: smooth trends)

**Example:**
- **1h model**: "If price spiked 5% in last 10min → predict +3% in 1h"
- **6h model**: "If price spiked 5% in last 10min → predict -2% in 6h" (mean reversion)

These are opposite signals! One model can't learn both.

---

## Strategy 1: Feature Importance Transfer (Recommended First Step)

### Concept
Train a baseline model on one horizon, extract feature importance, use insights for other horizons.

### Implementation

#### Step 1: Train 1-Hour Model
```python
from src.model import HybridSpotModel

model_1h = HybridSpotModel(horizon=6)  # 1 hour
model_1h.fit(X_train, X_val, train_df, val_df)

# Get feature importance
feature_imp = model_1h.regressor.feature_importance(importance_type='gain')
features_df = pd.DataFrame({
    'feature': feature_cols,
    'importance': feature_imp
}).sort_values('importance', ascending=False)

print(features_df.head(20))  # Top 20 features
```

#### Step 2: Apply Insights to 6-Hour Model
```python
# Use top 15-20 features only for faster training
top_features = features_df.head(20)['feature'].tolist()

model_6h = HybridSpotModel(horizon=36)  # 6 hours
# Train with reduced feature set
model_6h.fit(X_train[top_features], X_val[top_features], ...)
```

### Benefits
-  Faster 6h training (fewer features)
-  Reduced overfitting risk
-  Insights into what drives predictions

### Limitations
-  Not true transfer learning (no weight reuse)
-  Might miss horizon-specific important features

---

## Strategy 2: Multi-Task Learning (Parallel Training)

### Concept
Train multiple independent models sharing the same preprocessing pipeline.

### Implementation

#### Shared Preprocessing
```python
# Run once, creates features for ALL horizons
python submit_preprocessing_job.py --bucket ... --role ...
# Output: preprocessed_features.parquet (in S3)
```

#### Parallel Training
```python
# Train 1h model
python hpo_submitter.py --horizon 6 --n-trials 100

# Train 6h model (reuses same preprocessed data!)
python hpo_submitter.py --horizon 36 --n-trials 100
```

### Configuration
```yaml
# config.yaml
features:
  horizons: [6, 36]  # Both 1h and 6h targets will be created
  rolling_windows: [72]  # Shared windows (compromise for both)
```

### Benefits
-  Each model optimized for its horizon
-  Shared preprocessing (saves time/cost)
-  Independent hyperparameter tuning
-  Can compare prediction quality across horizons

### Costs
**Preprocessing**: $0.40 (once)
**HPO**: $1.42 × 2 = $2.84 (100 trials each horizon)
**Total**: $3.24

---

## Strategy 3: Hierarchical Predictions (Sequential Dependency)

### Concept
Use short-horizon predictions as features for long-horizon model.

### Implementation

#### Step 1: Train and Deploy 1h Model
```python
model_1h = HybridSpotModel(horizon=6)
model_1h.fit(...)
model_1h.save('models/model_1h.pkl')
```

#### Step 2: Create 1h Predictions as Feature
```python
# Load preprocessed data
df = pd.read_parquet('preprocessed_features.parquet')

# Add 1h predictions as a new feature
model_1h = HybridSpotModel.load('models/model_1h.pkl')
df['predicted_savings_1h'] = model_1h.predict(df[feature_cols])

# Use as feature for 6h model
feature_cols_6h = feature_cols + ['predicted_savings_1h']
model_6h = HybridSpotModel(horizon=36)
model_6h.fit(df[feature_cols_6h], ...)
```

### Benefits
-  6h model "learns from" 1h model's insights
-  Can capture multi-scale temporal patterns
-  Potentially better accuracy for long horizons

### Limitations
-  6h model depends on 1h model at inference
-  Deployment complexity (must run both models)
-  If 1h model is wrong, 6h model inherits the error

---

## Recommended Workflow

### Phase 1: Baseline (Current)
```yaml
horizons: [6]  # 1-hour only
rolling_windows: [72]  # 12-hour window
```
1. Complete preprocessing successfully (fits in 256GB)
2. Run HPO for 1h model
3. Validate accuracy and deployment

**Timeline**: 1-2 days
**Cost**: ~$2.00

---

### Phase 2: Feature Analysis
1. Extract feature importance from 1h model
2. Analyze which features matter most
3. Document insights for 6h model design

**Timeline**: Half day
**Cost**: $0 (analysis only)

---

### Phase 3: Add 6h Model
**Option A (Independent - Recommended):**
```yaml
horizons: [6, 36]
rolling_windows: [72, 144]  # Compromise: 12h + 24h
```
- Run preprocessing again with updated config
- Train 2 independent models
- Deploy both for different use cases

**Option B (Hierarchical - Advanced):**
- Keep 1h model as-is
- Add 1h predictions as feature for 6h model
- More complex deployment

**Timeline**: 2-3 days
**Cost**: ~$3.50

---

## Feature Configuration Trade-offs

### For 1-Hour Predictions
| Rolling Window | Memory | Accuracy | Notes |
|----------------|--------|----------|-------|
| [72] (12h) | 30-40GB | Good | **Current** - Safe for 256GB |
| [24, 72] (4h+12h) | 50-60GB | Better | Captures recent + half-day |
| [24, 144] (4h+24h) | 80-100GB | Best | **Risky** - May OOM |

### For 6-Hour Predictions
| Rolling Window | Memory | Accuracy | Notes |
|----------------|--------|----------|-------|
| [144] (24h) | 40GB | Good | Daily cycle, safe |
| [72, 288] (12h+48h) | 60-70GB | Better | Half-day + 2-day pattern |
| [144, 288] (24h+48h) | 90-110GB | Best | **Risky** - May OOM |

### Universal Compromise (Both Horizons)
```yaml
rolling_windows: [72]  # 12 hours
```
- **For 1h**: Excellent (12× horizon)
- **For 6h**: Acceptable (2× horizon, slightly short)
- **Memory**: Safe

---

## Decision Matrix

| Your Goal | Strategy | Config | Effort | Cost |
|-----------|----------|--------|--------|------|
| **Quick MVP** | Single 1h model | `horizons: [6], rolling: [72]` | Low | $2 |
| **Best 1h accuracy** | Single 1h model | `horizons: [6], rolling: [24,72]` | Low | $3 |
| **Support both horizons** | Multi-task | `horizons: [6,36], rolling: [72]` | Medium | $3.5 |
| **Maximum accuracy** | Multi-task + tuning | `horizons: [6,36], rolling: custom per model` | High | $5+ |

---

## Current Status (2026-01-12)

**Active Configuration:**
```yaml
horizons: [6]  # 1-hour predictions
rolling_windows: [72]  # 12-hour rolling window
```

**Reason**: Memory constraints (ml.r5.8xlarge with 256GB RAM)

**Next Steps:**
1. Complete preprocessing with reduced window config
2. Run HPO for 1h model
3. Evaluate accuracy before expanding to 6h

---

## References
- Feature importance: `src/model.py:HybridSpotModel.get_feature_importance()`
- Multi-horizon targets: `src/data.py:prepare_targets()`
- Config: `config/config.yaml`
