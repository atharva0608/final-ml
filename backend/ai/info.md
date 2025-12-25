# Backend AI Module

## Purpose

AI/ML integration layer including feature engineering and ML model adapters.

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM

---

## Files

### base_adapter.py
**Purpose**: Base class for ML model adapters
**Lines**: ~100
**Key Classes**:
- `BaseModelAdapter` - Abstract base class for all ML model integrations

**Responsibilities**:
- Define standard interface for ML models
- Handle model loading/unloading
- Provide prediction interface
- Error handling for model failures

**Dependencies**: abc (Abstract Base Classes)
**Recent Changes**: None recent

### feature_engine.py
**Purpose**: Feature extraction and transformation for ML models
**Lines**: ~250
**Key Classes/Functions**:
- `FeatureEngine` - Main feature engineering class
- `extract_instance_features()` - Extract features from EC2 instance data
- `transform_features()` - Apply transformations
- `normalize_features()` - Feature normalization

**Features Extracted**:
- Instance type metrics (CPU, memory, storage)
- Usage patterns (CPU utilization, network I/O)
- Cost metrics
- Time-based features
- Regional features

**Dependencies**:
- pandas
- numpy
- scikit-learn (for transformations)
- backend/database/models.py (Instance model)

**Recent Changes**: None recent

### __init__.py
**Purpose**: Package initialization and exports
**Exports**: BaseModelAdapter, FeatureEngine

---

## AI/ML Pipeline

```
Instance Data (from database)
   ↓
[Feature Extraction] (feature_engine.py)
   ↓
[Feature Transformation]
   ↓
[Normalization]
   ↓
[ML Model Prediction] (via adapter)
   ↓
[Results/Recommendations]
```

---

## Dependencies

### Depends On:
- pandas, numpy, scikit-learn
- backend/database/models.py
- Python abc module

### Depended By:
- backend/decision_engine/ (uses feature engineering)
- backend/ml_models/ (model implementations)
- API routes that serve ML predictions

**Impact Radius**: MEDIUM (affects ML-powered features)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing AI utilities
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Usage

### Feature Extraction Example
```python
from backend.ai.feature_engine import FeatureEngine
from backend.database.models import Instance

engine = FeatureEngine()
instance = db.query(Instance).first()
features = engine.extract_instance_features(instance)
```

### Creating Model Adapter
```python
from backend.ai.base_adapter import BaseModelAdapter

class MyModelAdapter(BaseModelAdapter):
    def load_model(self):
        # Load your model
        pass

    def predict(self, features):
        # Make predictions
        pass
```

---

## Known Issues

### None

AI module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM - ML utilities_
