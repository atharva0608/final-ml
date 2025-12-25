# Backend Decision Engine Module

## Purpose

Decision-making logic for instance optimization, filtering, and scoring recommendations.

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM-HIGH

---

## Files

### engine.py
**Purpose**: Core decision engine implementation
**Lines**: ~150
**Key Classes**:
- `DecisionEngine` - Main decision-making class
- Decision rules and policies

**Responsibilities**:
- Evaluate instance optimization opportunities
- Apply business rules
- Generate recommendations

**Dependencies**: backend/ai/feature_engine.py
**Recent Changes**: None recent

### engine_enhanced.py
**Purpose**: Enhanced decision engine with advanced features
**Lines**: ~450
**Key Enhancements**:
- Multi-criteria decision making
- Cost-benefit analysis
- Risk assessment integration
- Confidence scoring

**Key Functions**:
- `evaluate_optimization()` - Comprehensive evaluation
- `calculate_savings()` - Projected cost savings
- `assess_risk()` - Risk analysis for changes

**Dependencies**:
- engine.py (base engine)
- backend/logic/risk_manager.py
- backend/ai/feature_engine.py

**Recent Changes**: None recent

### filtering.py
**Purpose**: Instance filtering logic based on criteria
**Lines**: ~300
**Key Functions**:
- `filter_by_usage()` - Filter by CPU/memory utilization
- `filter_by_cost()` - Cost-based filtering
- `filter_by_region()` - Regional filtering
- `filter_by_tags()` - Tag-based filtering
- `apply_exclusions()` - Apply exclusion rules

**Use Cases**:
- Pre-filtering instances for optimization
- User-defined filter criteria
- Compliance filtering

**Dependencies**: backend/database/models.py

**Recent Changes**: None recent

### scoring.py
**Purpose**: Scoring algorithms for ranking optimization opportunities
**Lines**: ~330
**Key Functions**:
- `calculate_optimization_score()` - Overall optimization score (0-100)
- `calculate_urgency_score()` - Urgency ranking
- `calculate_impact_score()` - Potential impact
- `calculate_confidence_score()` - Recommendation confidence

**Scoring Factors**:
- Potential cost savings (40% weight)
- Resource waste level (30% weight)
- Risk level (15% weight)
- Urgency (15% weight)

**Dependencies**:
- numpy (for calculations)
- backend/logic/risk_manager.py

**Recent Changes**: None recent

### __init__.py
**Purpose**: Package initialization and exports
**Exports**: DecisionEngine, filtering functions, scoring functions

---

## Decision Flow

```
Instance Set
   ↓
[Apply Filters] (filtering.py)
   ↓
[Extract Features] (AI module)
   ↓
[Calculate Scores] (scoring.py)
   ↓
[Apply Decision Rules] (engine.py)
   ↓
[Risk Assessment] (engine_enhanced.py)
   ↓
[Ranked Recommendations]
```

---

## Scoring Algorithm

```
Optimization Score =
  (Cost Savings × 0.4) +
  (Waste Level × 0.3) +
  (Risk Inverse × 0.15) +
  (Urgency × 0.15)

Range: 0-100 (higher = better opportunity)
```

---

## Dependencies

### Depends On:
- backend/ai/feature_engine.py
- backend/logic/risk_manager.py
- backend/database/models.py
- numpy

### Depended By:
- backend/api/ (recommendation endpoints)
- backend/jobs/waste_scanner.py
- Frontend dashboard (displays recommendations)

**Impact Radius**: MEDIUM-HIGH (affects all optimization features)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing decision engine
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Usage

### Basic Decision Engine
```python
from backend.decision_engine import DecisionEngine

engine = DecisionEngine()
recommendations = engine.evaluate_instances(instances)
```

### Advanced Filtering
```python
from backend.decision_engine.filtering import filter_by_usage

high_usage_instances = filter_by_usage(
    instances,
    min_cpu=80,  # 80% CPU
    min_memory=75  # 75% memory
)
```

### Scoring Example
```python
from backend.decision_engine.scoring import calculate_optimization_score

score = calculate_optimization_score(
    instance,
    cost_savings=100,  # $100/month
    waste_level=0.6,   # 60% waste
    risk_level=0.2     # 20% risk
)
```

---

## Known Issues

### None

Decision engine is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM-HIGH - Core optimization logic_
