# Backend Logic Module

## Purpose

Business logic components including ML model registry and risk management.

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM-HIGH

---

## Files

### model_registry.py
**Purpose**: Central registry for ML models and versioning
**Lines**: ~250
**Key Classes**:
- `ModelRegistry` - Singleton registry for all ML models

**Capabilities**:
- Model registration and versioning
- Model loading/unloading
- Model metadata management
- Performance tracking per model

**Registered Models**:
- Instance optimization model
- Cost prediction model
- Waste detection model
- Risk assessment model

**Model Metadata**:
- Model name and version
- Training date
- Accuracy metrics
- Feature schema
- Model file path

**Dependencies**:
- backend/ai/base_adapter.py
- pickle or joblib (for model serialization)

**Recent Changes**: None recent

### risk_manager.py
**Purpose**: Risk assessment and mitigation logic
**Lines**: ~380
**Key Classes**:
- `RiskManager` - Main risk assessment engine

**Risk Categories**:
1. **Financial Risk** (0-100 scale)
   - Unexpected cost increases
   - Budget overruns
   - Savings estimation errors

2. **Operational Risk** (0-100 scale)
   - Service downtime
   - Performance degradation
   - Failed executions

3. **Security Risk** (0-100 scale)
   - Unencrypted resources
   - Public exposure
   - Compliance violations

4. **Data Risk** (0-100 scale)
   - Data loss potential
   - Backup failures
   - Retention policy violations

**Key Functions**:
- `assess_action_risk(action)` - Evaluate risk of proposed action
- `calculate_risk_score(instance)` - Overall risk score
- `get_mitigation_strategies(risk_type)` - Suggest risk mitigations
- `validate_risk_threshold(action, threshold)` - Check if action exceeds risk threshold

**Risk Calculation**:
```
Overall Risk =
  (Financial × 0.3) +
  (Operational × 0.35) +
  (Security × 0.25) +
  (Data × 0.1)
```

**Dependencies**:
- backend/database/models.py
- numpy (for calculations)

**Recent Changes**: None recent

### __init__.py
**Purpose**: Package initialization and exports
**Exports**: ModelRegistry, RiskManager

---

## Risk Assessment Flow

```
Proposed Action
   ↓
[Identify Risk Factors] (risk_manager.py)
   ↓
[Calculate Category Scores]
   - Financial Risk
   - Operational Risk
   - Security Risk
   - Data Risk
   ↓
[Calculate Overall Risk Score]
   ↓
[Compare to Threshold]
   ↓
[Return Assessment + Mitigations]
```

---

## Risk Thresholds

| Action Type | Max Risk Score | Approval Required |
|-------------|----------------|-------------------|
| Stop Instance | 20 | No |
| Start Instance | 15 | No |
| Resize Instance | 40 | No |
| Terminate Instance | 80 | Yes (explicit confirmation) |
| Delete Volume | 70 | Yes |
| Modify Security Group | 60 | Yes |

---

## Dependencies

### Depends On:
- backend/database/models.py
- backend/ai/base_adapter.py
- numpy
- pickle/joblib

### Depended By:
- backend/decision_engine/ (risk-aware decisions)
- backend/executor/ (risk validation before execution)
- backend/jobs/security_enforcer.py
- API endpoints (risk scoring)

**Impact Radius**: MEDIUM-HIGH (affects decision quality)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing logic components
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Usage

### Risk Assessment Example
```python
from backend.logic.risk_manager import RiskManager

risk_mgr = RiskManager()
risk_score = risk_mgr.assess_action_risk({
    "action": "terminate",
    "instance_id": "i-1234567890abcdef0"
})

if risk_score > 80:
    # Require confirmation
    pass
```

### Model Registry Example
```python
from backend.logic.model_registry import ModelRegistry

registry = ModelRegistry()
model = registry.get_model("instance-optimizer", version="1.2.0")
predictions = model.predict(features)
```

---

## Known Issues

### None

Logic module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM-HIGH - Core business logic_
