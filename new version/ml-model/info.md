# ML Model Training Module

## Purpose

ML model training scripts and data diagnostic tools (root-level training code).

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM

---

## Files

### family_stress_model.py
**Purpose**: ML model for predicting EC2 instance family stress/load patterns
**Lines**: ~1,300
**Key Components**:
- Feature engineering for instance families (t3, m5, c5, etc.)
- Training pipeline for stress prediction
- Model evaluation metrics
- Export trained model

**Model Type**: Likely classification or regression
**Target**: Instance stress level or load prediction

**Features**:
- Instance family characteristics
- Historical load patterns
- Resource utilization trends
- Regional factors

**Dependencies**:
- pandas, numpy
- scikit-learn or similar ML library
- Training data (from database or CSV)

**Recent Changes**: None recent

### hierarchical_spot_stability_model_v2.py
**Purpose**: Advanced ML model for predicting AWS Spot instance stability
**Lines**: ~2,000
**Key Components**:
- Hierarchical model architecture
- Spot instance interruption prediction
- Stability scoring
- Version 2 (improved from v1)

**Model Type**: Hierarchical classification/regression
**Target**: Spot instance stability score (0-1 or 0-100)

**Features**:
- Spot pricing history
- Availability zone characteristics
- Instance type popularity
- Time-based patterns
- Regional factors

**Use Case**:
Predict which spot instances are safe to use vs high-risk for interruption.

**Dependencies**:
- pandas, numpy
- Advanced ML libraries (XGBoost, LightGBM, or TensorFlow)
- AWS pricing data

**Recent Changes**: None recent

### zone_v2_fixed.py
**Purpose**: Availability zone analysis and optimization model (fixed version)
**Lines**: ~1,000
**Key Components**:
- Zone-specific feature engineering
- Optimization across availability zones
- Version 2 (fixed bugs from v1)

**Model Type**: Optimization model
**Target**: Optimal availability zone selection

**Features**:
- AZ pricing differences
- AZ capacity patterns
- Network latency between AZs
- Disaster recovery considerations

**Use Case**:
Recommend optimal availability zone for instance placement.

**Dependencies**:
- pandas, numpy
- Optimization libraries (scipy.optimize, PuLP)
- AWS data

**Recent Changes**: Bug fixes (v2)

### diagnose_data.py
**Purpose**: Data diagnostic tool for ML training datasets
**Lines**: ~230
**Key Functions**:
- Data quality checks
- Missing value analysis
- Outlier detection
- Feature distribution analysis
- Correlation analysis

**Use Cases**:
- Pre-training data validation
- Feature engineering insights
- Data quality assurance

**Dependencies**:
- pandas, numpy
- matplotlib/seaborn (for visualizations)

**Recent Changes**: None recent

---

## Training Workflow

```
Raw Data (from database/AWS)
   ↓
[Data Diagnostic] (diagnose_data.py)
   ↓
[Feature Engineering]
   ↓
[Model Training]
   ├─ family_stress_model.py
   ├─ hierarchical_spot_stability_model_v2.py
   └─ zone_v2_fixed.py
   ↓
[Model Evaluation]
   ↓
[Export Trained Model]
   ↓
[Register in ModelRegistry] (backend/logic/model_registry.py)
   ↓
[Deploy to backend/ml_models/]
```

---

## Model Training Commands

### Training Family Stress Model
```bash
python ml-model/family_stress_model.py \
  --data data/training_data.csv \
  --output models/family_stress_v1.pkl
```

### Training Spot Stability Model
```bash
python ml-model/hierarchical_spot_stability_model_v2.py \
  --data data/spot_history.csv \
  --output models/spot_stability_v2.pkl
```

### Data Diagnostics
```bash
python ml-model/diagnose_data.py \
  --input data/raw_data.csv \
  --report diagnostics/report.html
```

---

## Dependencies

### Depends On:
- pandas, numpy
- scikit-learn / XGBoost / LightGBM
- matplotlib, seaborn
- scipy (for optimization)
- Training data (from database or external sources)

### Depended By:
- backend/ml_models/ (deployed models)
- backend/logic/model_registry.py
- ML experiments and evaluations

**Impact Radius**: MEDIUM (affects ML model quality)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing training scripts
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Training Data Sources

### Internal Data
- Database tables (instances, accounts, experiment_logs)
- Historical metrics from CloudWatch

### External Data
- AWS Spot pricing history
- AWS Service Quotas
- Public AWS datasets

---

## Model Versioning

### Current Versions
- Family Stress Model: v1 (in family_stress_model.py)
- Spot Stability Model: v2 (hierarchical_spot_stability_model_v2.py)
- Zone Optimizer: v2 (zone_v2_fixed.py)

### Version Control
- Training scripts in Git
- Trained model files: Store in S3 or external storage
- Model registry tracks versions

---

## Known Issues

### None

ML training module is stable as of 2025-12-25.

---

## TODO / Improvements

1. **Automated Retraining**: Schedule monthly retraining
2. **Hyperparameter Tuning**: Add automated hyperparameter search
3. **Model Comparison**: A/B testing framework
4. **Data Pipeline**: Automate data collection and preprocessing

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM - ML model training_
