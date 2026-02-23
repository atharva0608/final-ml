# Decision Engine Architecture & Logic Plan

**Document Version:** 1.0
**Last Updated:** 2026-02-23
**Purpose:** Define isolated decision engine with fixed inputs/outputs and logical decision trees
**Audience:** Backend developers, architects, product managers

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Design Principles](#design-principles)
3. [Decision Engine Interface](#decision-engine-interface)
4. [Binary Decision Trees](#binary-decision-trees)
5. [Implementation Architecture](#implementation-architecture)
6. [Logic Flow Diagrams](#logic-flow-diagrams)
7. [Configuration & Tunability](#configuration--tunability)
8. [Error Handling & Fallbacks](#error-handling--fallbacks)
9. [Testing Strategy](#testing-strategy)
10. [Migration & Deployment](#migration--deployment)

---

## Executive Summary

### The Problem

Current ML integration is **tightly coupled** to backend services:
- Hard to test ML logic independently
- Difficult to swap models or change ranking algorithms
- Business logic mixed with ML inference code
- No clear interface for A/B testing or experimentation

### The Solution

Build an **isolated Decision Engine** with:

```
┌─────────────────────────────────────────────┐
│          DECISION ENGINE                    │
│                                             │
│  Input: Standardized pool data (JSON/dict) │
│  ↓                                          │
│  Logic: Binary decision trees              │
│  ↓                                          │
│  Output: Ranked pools with scores          │
└─────────────────────────────────────────────┘
```

**Benefits:**
- ✅ Isolated, testable, swappable
- ✅ Fixed input/output contracts
- ✅ Human-readable decision logic
- ✅ Easy to A/B test alternative strategies
- ✅ No backend code changes for ML updates

---

## Design Principles

### 1. Separation of Concerns

```
┌────────────────────┐
│  Data Collection   │ ← Backend responsibility
│  (API calls, DB)   │
└──────────┬─────────┘
           │
           ▼
┌────────────────────┐
│  Decision Engine   │ ← Pure logic, no I/O
│  (This component)  │
└──────────┬─────────┘
           │
           ▼
┌────────────────────┐
│  Result Handling   │ ← Backend responsibility
│  (Cache, API resp) │
└────────────────────┘
```

**Decision Engine should:**
- ✅ Accept standardized input
- ✅ Contain only decision logic
- ✅ Return standardized output
- ❌ NOT fetch data from databases
- ❌ NOT call external APIs
- ❌ NOT manage caching

### 2. Immutability

```python
# ✅ Good: Pure function
def score_pool(pool_data: dict, config: dict) -> float:
    return (pool_data['savings'] * 100) - (pool_data['cost'] * 0.1)

# ❌ Bad: Mutates input
def score_pool(pool_data: dict):
    pool_data['score'] = ...  # Don't modify input!
```

### 3. Testability

Every decision should be unit-testable:

```python
def test_blacklist_penalty():
    pool = {'savings': 0.93, 'is_flagged': True}
    result = apply_blacklist_penalty(pool, penalty=0.50)
    assert result['adjusted_savings'] == 0.43

def test_risk_categorization():
    assert categorize_risk(0.95) == "SAFE"
    assert categorize_risk(0.75) == "MODERATE"
    assert categorize_risk(0.40) == "RISKY"
```

### 4. Configuration-Driven

All thresholds, weights, and rules should be configurable:

```yaml
# decision_engine_config.yaml
scoring:
  savings_weight: 100
  cost_weight: 0.1
  blacklist_penalty: 0.50

risk_thresholds:
  safe_min: 0.90
  moderate_min: 0.70
  risky_max: 0.70

filtering:
  max_interruption_index: 1  # 0-1 = <10%
  min_savings_percentage: 50
  max_cost_usd: 100
```

---

## Decision Engine Interface

### Input Contract

```python
@dataclass
class PoolInput:
    """
    Standardized input for Decision Engine.
    Backend is responsible for preparing this data.
    """
    # Identity
    instance_type: str         # "m5.xlarge"
    availability_zone: str     # "us-east-1a"
    region: str               # "us-east-1"

    # Pricing (from AWS Pricing API)
    spot_price: float         # 0.045 (USD/hour)
    ondemand_price: float     # 0.096 (USD/hour)
    current_savings: float    # 0.53 (53% savings)

    # Spot Advisor (from Web Scraper)
    interruption_index: int   # 0-4 (from Spot Advisor)
    advisor_savings_pct: int  # 0-100 (from Spot Advisor)

    # ML Features (engineered by backend)
    features: np.ndarray      # Shape (1, 45) - ready for inference

    # Status Flags (from Redis/DB)
    is_blacklisted: bool      # True if flagged by System B
    blacklist_score: int      # Interruption count (0-10)

    # Historical Context (optional)
    pool_historical_risk: float  # 0.0-1.0 (from pool_risk_scores table)
    last_interruption: Optional[datetime]

    # Metadata
    timestamp: datetime
    cluster_id: str
    template_id: Optional[str]


# Example JSON representation
pool_input_json = {
    "instance_type": "m5.xlarge",
    "availability_zone": "us-east-1a",
    "region": "us-east-1",
    "spot_price": 0.045,
    "ondemand_price": 0.096,
    "current_savings": 0.53,
    "interruption_index": 1,
    "advisor_savings_pct": 70,
    "features": [...],  # 45-element list
    "is_blacklisted": false,
    "blacklist_score": 0,
    "pool_historical_risk": 0.01,
    "last_interruption": null,
    "timestamp": "2026-02-23T10:30:00Z",
    "cluster_id": "cluster-123",
    "template_id": null
}
```

### Output Contract

```python
@dataclass
class PoolScore:
    """
    Standardized output from Decision Engine.
    Backend uses this to sort and present results.
    """
    # Identity (passthrough)
    instance_type: str
    availability_zone: str

    # ML Predictions
    ml_savings_pct: float     # 0.0-1.0 (from classifier)
    ml_cost_estimate: float   # USD (from regressor)

    # Adjusted Scores
    adjusted_savings: float   # After blacklist penalty
    final_score: float        # Combined metric for ranking

    # Risk Assessment
    risk_category: str        # "SAFE", "MODERATE", "RISKY"
    risk_score: float         # 0.0-1.0 (0=safe, 1=risky)

    # Decision Flags
    is_recommended: bool      # True if passes all filters
    rejection_reason: Optional[str]  # Why pool was rejected

    # Metadata
    decision_timestamp: datetime
    engine_version: str       # "v1.0.0"
    model_version: str        # "classifier_6, regressor_6"


# Example JSON representation
pool_score_json = {
    "instance_type": "m5.xlarge",
    "availability_zone": "us-east-1a",
    "ml_savings_pct": 0.93,
    "ml_cost_estimate": 14.07,
    "adjusted_savings": 0.93,
    "final_score": 91.6,
    "risk_category": "SAFE",
    "risk_score": 0.07,
    "is_recommended": true,
    "rejection_reason": null,
    "decision_timestamp": "2026-02-23T10:30:00Z",
    "engine_version": "v1.0.0",
    "model_version": "classifier_6, regressor_6"
}
```

### Main Function Signature

```python
def rank_pools(
    pools: List[PoolInput],
    config: DecisionEngineConfig
) -> List[PoolScore]:
    """
    Main entry point for Decision Engine.

    Args:
        pools: List of standardized pool inputs
        config: Configuration object with thresholds and weights

    Returns:
        List of scored pools, sorted by final_score (descending)

    Raises:
        ValueError: If input validation fails
        ModelInferenceError: If ML models fail to load/run
    """
    # Step 1: Validate inputs
    validated_pools = validate_inputs(pools)

    # Step 2: Filter pools (decision tree 1)
    filtered_pools = apply_filtering_rules(validated_pools, config)

    # Step 3: Score pools (decision tree 2)
    scored_pools = apply_scoring_logic(filtered_pools, config)

    # Step 4: Categorize risk (decision tree 3)
    categorized_pools = apply_risk_categorization(scored_pools, config)

    # Step 5: Sort and return
    return sort_by_final_score(categorized_pools)
```

---

## Binary Decision Trees

### Decision Tree 1: Filtering Rules

**Purpose:** Remove pools that don't meet minimum requirements

```
START: Pool candidates
│
├─ Q1: Is interruption_index > max_interruption_index?
│  ├─ YES → REJECT (reason: "high_interruption_rate")
│  └─ NO → Continue to Q2
│
├─ Q2: Is advisor_savings_pct < min_savings_percentage?
│  ├─ YES → REJECT (reason: "low_savings_potential")
│  └─ NO → Continue to Q3
│
├─ Q3: Is is_blacklisted == True AND blacklist_score >= blacklist_threshold?
│  ├─ YES → REJECT (reason: "globally_blacklisted")
│  └─ NO → Continue to Q4
│
├─ Q4: Is ml_cost_estimate > max_cost_usd?
│  ├─ YES → REJECT (reason: "cost_exceeds_budget")
│  └─ NO → Continue to Q5
│
├─ Q5: Is pool_historical_risk > max_historical_risk?
│  ├─ YES → REJECT (reason: "poor_historical_performance")
│  └─ NO → PASS (is_recommended = True)
│
END: Filtered pool list
```

**Implementation:**

```python
def apply_filtering_rules(
    pools: List[PoolInput],
    config: DecisionEngineConfig
) -> List[PoolInput]:
    """Apply filtering rules via binary decision tree."""
    filtered = []

    for pool in pools:
        # Q1: Interruption frequency check
        if pool.interruption_index > config.max_interruption_index:
            pool.rejection_reason = "high_interruption_rate"
            continue

        # Q2: Savings potential check
        if pool.advisor_savings_pct < config.min_savings_percentage:
            pool.rejection_reason = "low_savings_potential"
            continue

        # Q3: Blacklist check
        if pool.is_blacklisted and pool.blacklist_score >= config.blacklist_threshold:
            pool.rejection_reason = "globally_blacklisted"
            continue

        # Q4: Cost check (requires ML inference first)
        # Note: This step is performed AFTER scoring in actual flow
        # Shown here for logical completeness

        # Q5: Historical risk check
        if pool.pool_historical_risk > config.max_historical_risk:
            pool.rejection_reason = "poor_historical_performance"
            continue

        # Passed all filters
        filtered.append(pool)

    return filtered
```

**Configuration:**

```yaml
filtering:
  max_interruption_index: 1     # 0-1 = <10% interruption
  min_savings_percentage: 50    # Must save at least 50%
  blacklist_threshold: 3        # Allow up to 2 recent interruptions
  max_cost_usd: 100             # Budget constraint
  max_historical_risk: 0.15     # Max 15% historical failure rate
```

---

### Decision Tree 2: ML Scoring & Penalty Application

**Purpose:** Calculate scores using ML models and apply penalties

```
START: Filtered pool
│
├─ STEP 1: Run ML Inference
│  ├─ Run classifier_6.onnx → ml_savings_pct (0.0-1.0)
│  └─ Run regressor_6.onnx → ml_cost_estimate (USD)
│
├─ STEP 2: Apply Blacklist Penalty (if flagged)
│  ├─ Q1: Is is_blacklisted == True?
│  │  ├─ YES → adjusted_savings = ml_savings_pct - blacklist_penalty
│  │  └─ NO → adjusted_savings = ml_savings_pct
│
├─ STEP 3: Apply Historical Risk Adjustment
│  ├─ Q2: Is pool_historical_risk > historical_risk_threshold?
│  │  ├─ YES → adjusted_savings -= (pool_historical_risk × risk_penalty_factor)
│  │  └─ NO → No adjustment
│
├─ STEP 4: Calculate Final Score
│  └─ final_score = (adjusted_savings × savings_weight) - (ml_cost_estimate × cost_weight)
│
END: Scored pool
```

**Implementation:**

```python
def apply_scoring_logic(
    pools: List[PoolInput],
    config: DecisionEngineConfig
) -> List[PoolScore]:
    """Apply ML scoring and penalty logic."""
    scored_pools = []

    # Load ML models (singleton pattern)
    classifier = load_onnx_model(config.classifier_path)
    regressor = load_onnx_model(config.regressor_path)

    for pool in pools:
        # STEP 1: ML Inference
        ml_savings_pct = run_classifier(classifier, pool.features)
        ml_cost_estimate = run_regressor(regressor, pool.features)

        # STEP 2: Blacklist penalty
        adjusted_savings = ml_savings_pct
        if pool.is_blacklisted:
            adjusted_savings -= config.blacklist_penalty

        # STEP 3: Historical risk adjustment
        if pool.pool_historical_risk > config.historical_risk_threshold:
            risk_adjustment = pool.pool_historical_risk * config.risk_penalty_factor
            adjusted_savings -= risk_adjustment

        # STEP 4: Final score calculation
        final_score = (
            (adjusted_savings * config.savings_weight) -
            (ml_cost_estimate * config.cost_weight)
        )

        scored_pools.append(PoolScore(
            instance_type=pool.instance_type,
            availability_zone=pool.availability_zone,
            ml_savings_pct=ml_savings_pct,
            ml_cost_estimate=ml_cost_estimate,
            adjusted_savings=adjusted_savings,
            final_score=final_score,
            decision_timestamp=datetime.utcnow(),
            engine_version=config.version,
            model_version=config.model_version
        ))

    return scored_pools
```

**Configuration:**

```yaml
scoring:
  savings_weight: 100           # Weight for savings percentage
  cost_weight: 0.1              # Weight for cost (inverse)
  blacklist_penalty: 0.50       # -50% penalty for blacklisted pools
  historical_risk_threshold: 0.10  # 10% historical risk triggers adjustment
  risk_penalty_factor: 0.5      # Penalty = risk × 0.5
```

**Example Calculation:**

```python
# Pool A: High savings, not blacklisted
ml_savings_pct = 0.93
ml_cost_estimate = 14.07
is_blacklisted = False
pool_historical_risk = 0.05  # 5% (below threshold)

adjusted_savings = 0.93  # No penalties
final_score = (0.93 × 100) - (14.07 × 0.1)
            = 93.0 - 1.407
            = 91.593

# Pool B: Medium savings, blacklisted
ml_savings_pct = 0.85
ml_cost_estimate = 10.50
is_blacklisted = True
pool_historical_risk = 0.12  # 12% (above threshold)

adjusted_savings = 0.85 - 0.50  # Blacklist penalty
                 = 0.35
adjusted_savings -= (0.12 × 0.5)  # Historical risk penalty
                 = 0.35 - 0.06
                 = 0.29

final_score = (0.29 × 100) - (10.50 × 0.1)
            = 29.0 - 1.05
            = 27.95

# Pool A ranks much higher (91.6 vs 28.0)
```

---

### Decision Tree 3: Risk Categorization

**Purpose:** Assign human-readable risk categories

```
START: Scored pool
│
├─ Q1: Is adjusted_savings >= safe_min_threshold?
│  ├─ YES → AND Q2: Is is_blacklisted == False?
│  │  ├─ YES → CATEGORY: "SAFE"
│  │  └─ NO → CATEGORY: "MODERATE" (high savings but flagged)
│  └─ NO → Continue to Q3
│
├─ Q3: Is adjusted_savings >= moderate_min_threshold?
│  ├─ YES → CATEGORY: "MODERATE"
│  └─ NO → CATEGORY: "RISKY"
│
├─ STEP 2: Calculate risk_score (inverse of adjusted_savings)
│  └─ risk_score = 1.0 - adjusted_savings
│
END: Categorized pool
```

**Implementation:**

```python
def apply_risk_categorization(
    pools: List[PoolScore],
    config: DecisionEngineConfig
) -> List[PoolScore]:
    """Assign risk categories and scores."""

    for pool in pools:
        # Q1 + Q2: Safe category (high savings + not blacklisted)
        if (pool.adjusted_savings >= config.safe_min_threshold and
            not pool.is_blacklisted):
            pool.risk_category = "SAFE"
            pool.risk_score = 1.0 - pool.adjusted_savings  # Lower is better

        # Q3: Moderate category (decent savings)
        elif pool.adjusted_savings >= config.moderate_min_threshold:
            pool.risk_category = "MODERATE"
            pool.risk_score = 1.0 - pool.adjusted_savings

        # Otherwise: Risky category
        else:
            pool.risk_category = "RISKY"
            pool.risk_score = 1.0 - pool.adjusted_savings

    return pools
```

**Configuration:**

```yaml
risk_categorization:
  safe_min_threshold: 0.90      # 90%+ savings = SAFE
  moderate_min_threshold: 0.70  # 70-90% savings = MODERATE
  # Below 70% = RISKY
```

**Example Categorizations:**

| Adjusted Savings | Is Blacklisted | Category | Risk Score |
|-----------------|----------------|----------|------------|
| 0.95 | False | SAFE | 0.05 |
| 0.92 | True | MODERATE | 0.08 |
| 0.75 | False | MODERATE | 0.25 |
| 0.65 | False | RISKY | 0.35 |
| 0.40 | True | RISKY | 0.60 |

---

## Implementation Architecture

### File Structure

```
ml_model/
└── decision_engine/
    ├── __init__.py
    ├── core.py                 # Main DecisionEngine class
    ├── models.py               # PoolInput, PoolScore dataclasses
    ├── filters.py              # Filtering logic (Tree 1)
    ├── scorers.py              # Scoring logic (Tree 2)
    ├── categorizers.py         # Risk categorization (Tree 3)
    ├── ml_inference.py         # ONNX model loading & inference
    ├── config.py               # Configuration management
    └── utils.py                # Validation, sorting utilities

backend/
├── services/
│   └── decision_engine_service.py  # Backend wrapper
└── api/
    └── atharvaai_routes.py    # API endpoint integration
```

### Core Class Design

```python
# ml_model/decision_engine/core.py

class DecisionEngine:
    """
    Main Decision Engine class.
    Orchestrates filtering, scoring, and categorization.
    """

    def __init__(self, config: DecisionEngineConfig):
        self.config = config
        self.classifier = None
        self.regressor = None
        self.version = "v1.0.0"

    def load_models(self):
        """Load ONNX models (call once at startup)."""
        self.classifier = load_onnx_model(self.config.classifier_path)
        self.regressor = load_onnx_model(self.config.regressor_path)

    def rank_pools(self, pools: List[PoolInput]) -> List[PoolScore]:
        """Main ranking pipeline."""
        # Validate
        self._validate_inputs(pools)

        # Filter (Tree 1)
        filtered = apply_filtering_rules(pools, self.config)

        # Score (Tree 2)
        scored = apply_scoring_logic(
            filtered,
            self.config,
            self.classifier,
            self.regressor
        )

        # Categorize (Tree 3)
        categorized = apply_risk_categorization(scored, self.config)

        # Sort
        ranked = sorted(categorized, key=lambda p: p.final_score, reverse=True)

        return ranked

    def _validate_inputs(self, pools: List[PoolInput]):
        """Validate input data structure."""
        for pool in pools:
            if not (0 <= pool.interruption_index <= 4):
                raise ValueError(f"Invalid interruption_index: {pool.interruption_index}")
            if pool.features.shape != (1, 45):
                raise ValueError(f"Invalid features shape: {pool.features.shape}")
            # Additional validations...
```

### Backend Integration

```python
# backend/services/decision_engine_service.py

from ml_model.decision_engine import DecisionEngine, PoolInput
from ml_model.decision_engine.config import load_config

class DecisionEngineService:
    """
    Backend service wrapper for Decision Engine.
    Handles data preparation and result formatting.
    """

    def __init__(self):
        config = load_config("ml_model/decision_engine/config.yaml")
        self.engine = DecisionEngine(config)
        self.engine.load_models()

    def rank_pools_for_cluster(
        self,
        cluster_id: str,
        template_id: Optional[str] = None
    ) -> List[dict]:
        """
        Main entry point called by backend.

        1. Fetch pool data from database/APIs
        2. Prepare PoolInput objects
        3. Call Decision Engine
        4. Convert results to JSON
        5. Return to API layer
        """

        # Step 1: Fetch data (backend responsibility)
        raw_pools = self._fetch_pool_data(cluster_id, template_id)

        # Step 2: Prepare inputs for Decision Engine
        pool_inputs = []
        for raw_pool in raw_pools:
            pool_input = PoolInput(
                instance_type=raw_pool['instance_type'],
                availability_zone=raw_pool['az'],
                region=raw_pool['region'],
                spot_price=raw_pool['spot_price'],
                ondemand_price=raw_pool['ondemand_price'],
                current_savings=raw_pool['savings'],
                interruption_index=raw_pool['spot_advisor_rank'],
                advisor_savings_pct=raw_pool['advisor_savings'],
                features=self._engineer_features(raw_pool),
                is_blacklisted=self._check_blacklist(raw_pool),
                blacklist_score=self._get_blacklist_score(raw_pool),
                pool_historical_risk=self._get_historical_risk(raw_pool),
                timestamp=datetime.utcnow(),
                cluster_id=cluster_id,
                template_id=template_id
            )
            pool_inputs.append(pool_input)

        # Step 3: Call Decision Engine (pure logic, no I/O)
        ranked_pools = self.engine.rank_pools(pool_inputs)

        # Step 4: Convert to JSON
        results = [self._to_dict(pool) for pool in ranked_pools]

        # Step 5: Cache results (backend responsibility)
        self._cache_results(cluster_id, results, ttl=30)

        return results

    def _fetch_pool_data(self, cluster_id, template_id):
        """Fetch pool data from Step 1-6 of ranking pipeline."""
        # Implementation omitted - calls existing backend methods
        pass

    def _engineer_features(self, raw_pool):
        """Engineer 45 features for ML models."""
        # Implementation omitted - calls ml_feature_service
        pass

    # Other helper methods...
```

---

## Logic Flow Diagrams

### Complete Ranking Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND LAYER                                │
│                                                                 │
│  1. API Request: GET /api/v1/atharvaai/pools/rankings           │
│  2. Fetch pool candidates (Steps 1-6 of existing pipeline)     │
│  3. Engineer features (45 features per pool)                   │
│  4. Prepare PoolInput objects                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  DECISION ENGINE LAYER                          │
│                  (Isolated, Pure Logic)                         │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  TREE 1: Filtering Rules                               │  │
│  │  ├─ Q1: Interruption check                             │  │
│  │  ├─ Q2: Savings check                                  │  │
│  │  ├─ Q3: Blacklist check                                │  │
│  │  ├─ Q4: Historical risk check                          │  │
│  │  └─ Output: Filtered pools                             │  │
│  └─────────────────────────────────────────────────────────┘  │
│                         │                                       │
│                         ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  TREE 2: ML Scoring & Penalties                        │  │
│  │  ├─ Run classifier (savings predictor)                 │  │
│  │  ├─ Run regressor (cost predictor)                     │  │
│  │  ├─ Apply blacklist penalty (if flagged)               │  │
│  │  ├─ Apply historical risk adjustment                   │  │
│  │  ├─ Calculate final_score                              │  │
│  │  └─ Output: Scored pools                               │  │
│  └─────────────────────────────────────────────────────────┘  │
│                         │                                       │
│                         ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  TREE 3: Risk Categorization                           │  │
│  │  ├─ Q1: Adjusted savings >= 0.90?                      │  │
│  │  ├─ Q2: Adjusted savings >= 0.70?                      │  │
│  │  ├─ Assign category (SAFE/MODERATE/RISKY)              │  │
│  │  ├─ Calculate risk_score                               │  │
│  │  └─ Output: Categorized pools                          │  │
│  └─────────────────────────────────────────────────────────┘  │
│                         │                                       │
│                         ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  SORTING & OUTPUT                                       │  │
│  │  ├─ Sort by final_score (descending)                   │  │
│  │  └─ Return List[PoolScore]                             │  │
│  └─────────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND LAYER                                │
│                                                                 │
│  5. Convert PoolScore objects to JSON                          │
│  6. Cache results in Redis (30-second TTL)                     │
│  7. Return API response                                        │
└─────────────────────────────────────────────────────────────────┘
```

### Penalty Application Flow

```
Input: Pool with ML predictions
│
├─ ml_savings_pct = 0.93 (from classifier)
├─ is_blacklisted = True
├─ pool_historical_risk = 0.12
│
▼
Step 1: Apply blacklist penalty
│
├─ IF is_blacklisted:
│  └─ adjusted_savings = 0.93 - 0.50 = 0.43
│
▼
Step 2: Apply historical risk adjustment
│
├─ IF pool_historical_risk > 0.10:
│  └─ adjusted_savings = 0.43 - (0.12 × 0.5) = 0.43 - 0.06 = 0.37
│
▼
Step 3: Calculate final score
│
└─ final_score = (0.37 × 100) - (14.07 × 0.1)
             = 37.0 - 1.407
             = 35.593
│
▼
Output: Scored pool with penalties applied
```

---

## Configuration & Tunability

### Configuration File Structure

```yaml
# ml_model/decision_engine/config.yaml

version: "v1.0.0"
model_version: "classifier_6, regressor_6"

# Model paths
models:
  classifier_path: "ml_model/model/classifier_6.onnx"
  regressor_path: "ml_model/model/regressor_6.onnx"
  category_mapping_path: "ml_model/model/category_mapping.json"

# Filtering rules (Decision Tree 1)
filtering:
  max_interruption_index: 1      # 0-1 = <10% interruption
  min_savings_percentage: 50     # Minimum 50% savings
  blacklist_threshold: 3         # Allow up to 2 recent interruptions
  max_cost_usd: 100              # Budget constraint
  max_historical_risk: 0.15      # Max 15% historical failure rate

# Scoring weights (Decision Tree 2)
scoring:
  savings_weight: 100
  cost_weight: 0.1
  blacklist_penalty: 0.50
  historical_risk_threshold: 0.10
  risk_penalty_factor: 0.5

# Risk categorization (Decision Tree 3)
risk_categorization:
  safe_min_threshold: 0.90       # 90%+ savings = SAFE
  moderate_min_threshold: 0.70   # 70-90% savings = MODERATE

# Feature engineering (if done by engine)
features:
  use_minimum_viable_set: false  # Use 15 features or full 39?
  feature_defaults:
    lag_default: 0.0
    rolling_default: 0.0
    stress_default: 0.0
```

### A/B Testing Configuration

```yaml
# Enable A/B testing with multiple engine configurations
ab_testing:
  enabled: true
  variant_distribution:
    control: 0.50   # 50% of traffic uses v1.0.0 config
    variant_a: 0.25  # 25% uses aggressive filtering
    variant_b: 0.25  # 25% uses conservative scoring

variants:
  control:
    # Same as default config above
    ...

  variant_a:  # Aggressive filtering
    filtering:
      max_interruption_index: 0  # Only <5% interruption
      min_savings_percentage: 70
      blacklist_threshold: 1     # Zero tolerance

  variant_b:  # Conservative scoring
    scoring:
      savings_weight: 80         # Less weight on savings
      cost_weight: 0.2           # More weight on cost
      blacklist_penalty: 0.30    # Smaller penalty
```

---

## Error Handling & Fallbacks

### Error Categories

#### 1. Input Validation Errors

```python
class InputValidationError(Exception):
    """Raised when input data is invalid."""
    pass

def validate_pool_input(pool: PoolInput):
    """Validate pool input before processing."""
    errors = []

    if not (0 <= pool.interruption_index <= 4):
        errors.append(f"Invalid interruption_index: {pool.interruption_index}")

    if pool.spot_price <= 0:
        errors.append(f"Invalid spot_price: {pool.spot_price}")

    if pool.features.shape != (1, 45):
        errors.append(f"Invalid features shape: {pool.features.shape}")

    if errors:
        raise InputValidationError("; ".join(errors))
```

#### 2. Model Inference Errors

```python
class ModelInferenceError(Exception):
    """Raised when ML model inference fails."""
    pass

def run_classifier_safe(model, features: np.ndarray) -> float:
    """Run classifier with fallback logic."""
    try:
        output = model.run(None, {"input": features})
        return float(output[0][0][0])
    except Exception as e:
        logger.error(f"Classifier inference failed: {e}")

        # Fallback 1: Use Spot Advisor savings estimate
        logger.warning("Using Spot Advisor fallback")
        return pool.advisor_savings_pct / 100.0

        # Fallback 2: Use historical average
        # return pool.pool_historical_savings

        # Fallback 3: Conservative default
        # return 0.70  # Assume 70% savings
```

#### 3. Configuration Errors

```python
class ConfigurationError(Exception):
    """Raised when configuration is invalid."""
    pass

def validate_config(config: DecisionEngineConfig):
    """Validate configuration values."""
    if config.savings_weight < 0:
        raise ConfigurationError("savings_weight must be >= 0")

    if not (0.0 <= config.blacklist_penalty <= 1.0):
        raise ConfigurationError("blacklist_penalty must be 0.0-1.0")

    if config.safe_min_threshold <= config.moderate_min_threshold:
        raise ConfigurationError(
            "safe_min_threshold must be > moderate_min_threshold"
        )
```

### Graceful Degradation Strategy

```python
def rank_pools_with_fallbacks(
    pools: List[PoolInput],
    config: DecisionEngineConfig
) -> List[PoolScore]:
    """
    Ranking with multi-level fallback logic.

    Fallback Hierarchy:
    1. Full ML scoring (45 features)
    2. Minimum viable ML (15 features)
    3. Spot Advisor only (no ML)
    4. Static heuristics (last resort)
    """

    try:
        # Level 1: Full ML scoring
        return rank_pools_full_ml(pools, config)

    except ModelInferenceError as e:
        logger.warning(f"ML inference failed: {e}. Using minimum viable features.")

        try:
            # Level 2: Minimum viable ML
            return rank_pools_minimum_ml(pools, config)

        except ModelInferenceError as e2:
            logger.error(f"Minimum ML failed: {e2}. Using Spot Advisor only.")

            try:
                # Level 3: Spot Advisor only
                return rank_pools_spot_advisor_only(pools, config)

            except Exception as e3:
                logger.critical(f"Spot Advisor failed: {e3}. Using static heuristics.")

                # Level 4: Static heuristics (last resort)
                return rank_pools_static_heuristics(pools, config)
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_filtering.py

def test_interruption_filter():
    """Test interruption frequency filtering."""
    config = DecisionEngineConfig(max_interruption_index=1)

    pool_safe = PoolInput(interruption_index=0, ...)
    pool_moderate = PoolInput(interruption_index=1, ...)
    pool_risky = PoolInput(interruption_index=3, ...)

    filtered = apply_filtering_rules([pool_safe, pool_moderate, pool_risky], config)

    assert len(filtered) == 2  # Only safe and moderate pass
    assert pool_safe in filtered
    assert pool_moderate in filtered
    assert pool_risky not in filtered


def test_blacklist_penalty():
    """Test blacklist penalty calculation."""
    config = DecisionEngineConfig(blacklist_penalty=0.50)

    pool = PoolInput(
        ml_savings_pct=0.93,
        is_blacklisted=True,
        ...
    )

    scored = apply_scoring_logic([pool], config)

    assert scored[0].ml_savings_pct == 0.93  # Original unchanged
    assert scored[0].adjusted_savings == 0.43  # After penalty


def test_risk_categorization():
    """Test risk category assignment."""
    config = DecisionEngineConfig(
        safe_min_threshold=0.90,
        moderate_min_threshold=0.70
    )

    pool_safe = PoolScore(adjusted_savings=0.95, is_blacklisted=False, ...)
    pool_moderate = PoolScore(adjusted_savings=0.75, is_blacklisted=False, ...)
    pool_risky = PoolScore(adjusted_savings=0.60, is_blacklisted=False, ...)

    categorized = apply_risk_categorization(
        [pool_safe, pool_moderate, pool_risky],
        config
    )

    assert categorized[0].risk_category == "SAFE"
    assert categorized[1].risk_category == "MODERATE"
    assert categorized[2].risk_category == "RISKY"
```

### Integration Tests

```python
# tests/test_integration.py

def test_end_to_end_ranking():
    """Test complete ranking pipeline."""
    # Setup
    config = load_config("ml_model/decision_engine/config.yaml")
    engine = DecisionEngine(config)
    engine.load_models()

    # Prepare test data
    pools = [
        create_test_pool("m5.xlarge", savings=0.93, is_blacklisted=False),
        create_test_pool("c5.large", savings=0.85, is_blacklisted=True),
        create_test_pool("t3.medium", savings=0.60, is_blacklisted=False),
    ]

    # Execute
    ranked = engine.rank_pools(pools)

    # Assertions
    assert len(ranked) == 3
    assert ranked[0].instance_type == "m5.xlarge"  # Highest score
    assert ranked[0].risk_category == "SAFE"
    assert ranked[1].instance_type == "c5.large"   # Penalized but still good
    assert ranked[2].instance_type == "t3.medium"  # Lowest savings


def test_fallback_behavior():
    """Test graceful degradation when ML fails."""
    config = load_config("ml_model/decision_engine/config.yaml")
    config.classifier_path = "invalid_path.onnx"  # Force failure

    engine = DecisionEngine(config)

    pools = [create_test_pool("m5.xlarge")]

    # Should fall back to Spot Advisor only
    ranked = engine.rank_pools_with_fallbacks(pools)

    assert len(ranked) > 0  # Still returns results
    assert ranked[0].fallback_method == "spot_advisor"
```

---

## Migration & Deployment

### Phase 1: Parallel Deployment (Week 1-2)

**Goal:** Run Decision Engine alongside existing logic

```python
# backend/services/pool_ranking_service.py

def rank_pools(cluster_id, template_id):
    # Existing logic
    old_results = rank_pools_old_logic(cluster_id, template_id)

    # New Decision Engine (parallel)
    try:
        new_results = decision_engine_service.rank_pools_for_cluster(
            cluster_id,
            template_id
        )

        # Log differences for comparison
        compare_and_log_results(old_results, new_results)

    except Exception as e:
        logger.error(f"Decision Engine failed: {e}")

    # Return old results (safe)
    return old_results
```

### Phase 2: Shadow Mode (Week 3-4)

**Goal:** Validate Decision Engine accuracy

```python
def rank_pools(cluster_id, template_id):
    # Run both
    old_results = rank_pools_old_logic(cluster_id, template_id)
    new_results = decision_engine_service.rank_pools_for_cluster(
        cluster_id,
        template_id
    )

    # Track agreement metrics
    agreement_pct = calculate_agreement(old_results, new_results)
    metrics.track("decision_engine_agreement", agreement_pct)

    # A/B test: 10% traffic uses new engine
    if random.random() < 0.10:
        return new_results
    else:
        return old_results
```

### Phase 3: Full Cutover (Week 5-6)

**Goal:** Switch to Decision Engine with fallback

```python
def rank_pools(cluster_id, template_id):
    try:
        # Primary: Decision Engine
        return decision_engine_service.rank_pools_for_cluster(
            cluster_id,
            template_id
        )
    except Exception as e:
        logger.error(f"Decision Engine failed: {e}")

        # Fallback: Old logic
        logger.warning("Falling back to old ranking logic")
        return rank_pools_old_logic(cluster_id, template_id)
```

### Phase 4: Cleanup (Week 7+)

**Goal:** Remove old logic

```python
def rank_pools(cluster_id, template_id):
    # Only Decision Engine
    return decision_engine_service.rank_pools_for_cluster(
        cluster_id,
        template_id
    )
```

---

## Summary

### Key Benefits

✅ **Isolated Logic:** Pure decision logic separated from I/O
✅ **Testable:** Every decision tree node is unit-testable
✅ **Configurable:** All thresholds and weights in YAML
✅ **Swappable:** Easy to replace ML models or ranking algorithms
✅ **Observable:** Clear decision points for debugging
✅ **Maintainable:** Human-readable logic, well-documented

### Fixed Contracts

**Input:** `PoolInput` (standardized pool data)
**Output:** `PoolScore` (ranked pools with scores)
**Configuration:** `DecisionEngineConfig` (YAML-based)

### Binary Decision Trees

1. **Filtering Rules:** Remove unqualified pools (5 binary checks)
2. **ML Scoring:** Apply ML predictions and penalties (4 steps)
3. **Risk Categorization:** Assign risk levels (3 thresholds)

### Next Steps

1. ✅ Review this architecture plan
2. ⬜ Implement `DecisionEngine` class skeleton
3. ⬜ Write unit tests for each decision tree
4. ⬜ Create YAML configuration file
5. ⬜ Integrate with backend (shadow mode)
6. ⬜ Run A/B test (10% traffic)
7. ⬜ Full deployment + monitoring

---

**Document Status:** ✅ Complete
**Version:** 1.0
**Next Review:** 2026-03-23
**Contact:** AtharvaAi ML Team
