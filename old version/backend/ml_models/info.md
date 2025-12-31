# Backend ML Models Module

## Purpose

Trained machine learning models for cost prediction and optimization recommendations.

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM

---

## Files

### mumbai_price_predictor.py
**Purpose**: ML model for predicting AWS EC2 instance pricing in Mumbai region
**Lines**: ~1,700
**Key Components**:
- `MumbaiPricePredictor` - Main predictor class
- Feature engineering pipeline
- Model training logic
- Prediction interface

**Model Details**:
- **Algorithm**: Likely regression-based (Random Forest, XGBoost, or similar)
- **Target**: Instance hourly cost prediction
- **Features**: Instance type, region, usage patterns, market trends
- **Training Data**: Historical pricing data from AWS

**Capabilities**:
- Predict instance costs for different configurations
- Compare pricing across instance types
- Cost forecasting for optimization scenarios

**Dependencies**:
- scikit-learn or similar ML library
- pandas, numpy
- backend/ai/feature_engine.py

**Recent Changes**: None recent

### __init__.py
**Purpose**: Package initialization and exports
**Exports**: MumbaiPricePredictor

---

## Model Usage Flow

```
Instance Configuration
   ↓
[Extract Features] (feature_engine.py)
   ↓
[Load Model] (mumbai_price_predictor.py)
   ↓
[Make Prediction]
   ↓
[Return Cost Estimate]
```

---

## Dependencies

### Depends On:
- scikit-learn / ML libraries
- pandas, numpy
- backend/ai/feature_engine.py
- backend/logic/model_registry.py (for versioning)

### Depended By:
- backend/decision_engine/ (cost analysis)
- backend/api/ (cost prediction endpoints)
- Frontend cost estimator

**Impact Radius**: MEDIUM (affects cost predictions)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing ML model
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Usage

### Price Prediction Example
```python
from backend.ml_models.mumbai_price_predictor import MumbaiPricePredictor

predictor = MumbaiPricePredictor()
predictor.load_model()

cost_estimate = predictor.predict({
    "instance_type": "t3.medium",
    "region": "ap-south-1",
    "usage_hours": 730  # monthly
})
```

---

## Model Maintenance

### Model Retraining
- **Frequency**: Monthly or when pricing changes
- **Data Source**: AWS Cost Explorer API
- **Validation**: Compare predictions to actual costs
- **Deployment**: Register new version in ModelRegistry

### Model Files Location
Likely stored in:
- `/backend/ml_models/trained_models/` (not shown, may be in .gitignore)
- Or cloud storage (S3)

---

## Known Issues

### None

ML models module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM - Cost prediction models_
