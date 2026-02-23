# ML Model Documentation

**Purpose:** Complete technical documentation for the Spot Optimizer ML models, web scraper, and decision engine architecture.

**Last Updated:** 2026-02-23

---

## 📚 Documentation Files

### 1. [SUMMARY.md](./SUMMARY.md)
**Comprehensive technical summary of all ML system components**

**Contents:**
- Executive Summary
- System Architecture Overview
- Component 1: Web Scraper (AWS Spot Advisor)
- Component 2: ML Models (LightGBM Dual System)
- Component 3: Feature Engineering Pipeline (45 features)
- Component 4: Decision Engine Integration
- Data Flow & Dependencies
- Model Performance & Metrics
- Production Deployment
- Technical Specifications

**Target Audience:** Backend developers, ML engineers, system architects

**Use When:** You need to understand how the ML system works end-to-end

---

### 2. [PLAN.md](./PLAN.md)
**Decision engine architecture with binary decision trees and logical flows**

**Contents:**
- Design Principles (Separation of Concerns, Immutability, Testability)
- Decision Engine Interface (Fixed Input/Output Contracts)
- Binary Decision Trees (3 decision trees with detailed logic)
  - Tree 1: Filtering Rules (5 binary checks)
  - Tree 2: ML Scoring & Penalty Application (4 steps)
  - Tree 3: Risk Categorization (3 thresholds)
- Implementation Architecture (File structure, core classes)
- Logic Flow Diagrams (Visual decision flows)
- Configuration & Tunability (YAML-based config)
- Error Handling & Fallbacks (4-level graceful degradation)
- Testing Strategy (Unit + integration tests)
- Migration & Deployment (4-phase rollout plan)

**Target Audience:** Backend developers, architects, product managers

**Use When:** You need to build or modify the decision engine logic

---

## 🎯 Quick Reference

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    AtharvaAi Pool Selection System              │
│                     (8-Step Ranking Pipeline)                    │
└─────────────────────────────────────────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐      ┌──────────────────┐     ┌────────────────┐
│  Web Scraper  │      │   ML Models      │     │ Decision Engine│
│  (Step 3)     │      │   (Step 7)       │     │ (Orchestrator) │
│               │      │                  │     │                │
│ - Spot Advisor│      │ - Classifier     │     │ - Filtering    │
│ - 1-hour cache│      │ - Regressor      │     │ - Scoring      │
│ - 12K pools   │      │ - 45 features    │     │ - Ranking      │
└───────────────┘      └──────────────────┘     └────────────────┘
```

### Model Files

| File | Size | Purpose |
|------|------|---------|
| `classifier_6.onnx` | 1.06 MB | Predicts spot savings % (0-1) |
| `regressor_6.onnx` | 1.07 MB | Predicts cost in USD |
| `category_mapping.json` | 1.3 KB | Categorical encodings |
| `pool_baselines.json` | ~50 KB | Per-pool statistics |

**Location:** `/ml_model/model/`

### Feature Engineering

**Total Features:** 45 (39 numerical + 6 categorical)

| Category | Count | Requires Historical Data? |
|----------|-------|--------------------------|
| Temporal | 10 | ❌ No (always available) |
| Lag | 3 | ✅ Yes (24-hour history) |
| Rolling Window | 8 | ✅ Yes (24-hour history) |
| Price Dynamics | 5 | ✅ Yes (price history) |
| Family-Time Patterns | 6 | ✅ Yes (pre-computed baselines) |
| Family Stress | 3 | ✅ Yes (cross-instance data) |
| Events | 3 | ❌ No (calendar lookup) |
| Pool Risk | 1 | ✅ Yes (historical interruptions) |
| Categorical | 6 | ❌ No (instance metadata) |

**Minimum Viable:** 15 features (75% accuracy)
**Full Production:** 39 features (95% accuracy)

### Binary Decision Trees

#### Tree 1: Filtering Rules
```
Pool Candidates
  │
  ├─ Q1: interruption_index > 1? → REJECT
  ├─ Q2: advisor_savings < 50%? → REJECT
  ├─ Q3: blacklisted? → REJECT
  ├─ Q4: cost > $100? → REJECT
  └─ Q5: historical_risk > 15%? → REJECT
  │
  ▼
Filtered Pools (is_recommended = True)
```

#### Tree 2: ML Scoring
```
Filtered Pool
  │
  ├─ Run classifier → savings_pct
  ├─ Run regressor → cost_estimate
  ├─ Apply blacklist penalty → adjusted_savings
  └─ Calculate final_score = (savings × 100) - (cost × 0.1)
  │
  ▼
Scored Pool
```

#### Tree 3: Risk Categorization
```
Scored Pool
  │
  ├─ adjusted_savings >= 0.90? → SAFE
  ├─ adjusted_savings >= 0.70? → MODERATE
  └─ Otherwise → RISKY
  │
  ▼
Categorized Pool
```

### Performance Metrics

| Metric | Value |
|--------|-------|
| **Model Accuracy** | 95% (full features) |
| **Inference Speed** | <50ms per pool |
| **Ranking Frequency** | Every 30 seconds |
| **Cache Hit Rate** | 99.5% (Redis) |
| **API Response Time** | <100ms (cached) |

### API Endpoints

```
GET  /api/v1/atharvaai/pools/rankings
     → Returns ranked pools with ML scores

GET  /api/v1/atharvaai/blacklist
     → Returns globally flagged pools

GET  /api/v1/atharvaai/rebalancing/status
     → Returns current rebalancing actions
```

---

## 🔧 Development Workflow

### For Backend Developers

**Task:** Integrate Decision Engine into backend

**Steps:**
1. Read [PLAN.md](./PLAN.md) - Section: "Implementation Architecture"
2. Review input/output contracts (PoolInput, PoolScore)
3. Implement `DecisionEngineService` wrapper
4. Write integration tests
5. Deploy in shadow mode (parallel to existing logic)

**Key Files to Create:**
- `ml_model/decision_engine/core.py`
- `backend/services/decision_engine_service.py`
- `tests/test_decision_engine.py`

---

### For ML Engineers

**Task:** Update ML models or features

**Steps:**
1. Read [SUMMARY.md](./SUMMARY.md) - Section: "Component 2: ML Models"
2. Review feature engineering pipeline (45 features)
3. Train new models using `ml_model/model/spot_optimizer_v1/scripts/train.py`
4. Export to ONNX format
5. Update `category_mapping.json` if needed
6. Test inference with `scripts/verify_onnx_local.py`
7. Update `model_version` in config

**Key Files to Modify:**
- `ml_model/model/classifier_6.onnx` (replace)
- `ml_model/model/regressor_6.onnx` (replace)
- `ml_model/model/category_mapping.json` (if categories changed)
- `ml_model/decision_engine/config.yaml` (update model_version)

---

### For Product Managers

**Task:** Tune ranking algorithm

**Steps:**
1. Read [PLAN.md](./PLAN.md) - Section: "Configuration & Tunability"
2. Review binary decision trees (understand filtering logic)
3. Modify `ml_model/decision_engine/config.yaml`
4. Test with sample data
5. Deploy via A/B testing (see Migration & Deployment section)

**Tunable Parameters:**
```yaml
filtering:
  max_interruption_index: 1    # 0-1 = <10% interruption
  min_savings_percentage: 50   # Minimum savings threshold

scoring:
  savings_weight: 100          # How much to value savings
  cost_weight: 0.1             # How much to penalize cost
  blacklist_penalty: 0.50      # Penalty for flagged pools

risk_categorization:
  safe_min_threshold: 0.90     # 90%+ savings = SAFE
  moderate_min_threshold: 0.70 # 70-90% = MODERATE
```

---

## 📊 Visual Reference: Complete Data Flow

```
┌───────────────────────────────────────────────────────────────┐
│                     USER REQUEST                              │
│     GET /api/v1/atharvaai/pools/rankings?cluster_id=123       │
└─────────────────────────┬─────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────────┐
│              BACKEND: Data Collection (Steps 1-6)             │
│                                                               │
│  1. Filter by Template (instance families, architectures)    │
│  2. Filter by AZ (user preferences)                          │
│  3. Spot Advisor Filter ← [WEB SCRAPER]                      │
│  4. Global Blacklist Check (Redis)                           │
│  5. Capacity Check (AWS API)                                 │
│  6. Pricing Fetch (AWS Pricing API)                          │
│                                                               │
│  Output: 50-200 candidate pools with metadata                │
└─────────────────────────┬─────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────────┐
│           BACKEND: Feature Engineering (ml_feature_service)   │
│                                                               │
│  For each pool:                                              │
│    - Fetch 24-hour price history (spot_price_history table)  │
│    - Fetch family baselines (family_hour_baselines table)    │
│    - Calculate 45 features (temporal, lag, rolling, etc.)    │
│    - Create PoolInput object                                 │
│                                                               │
│  Output: List[PoolInput] (ready for decision engine)         │
└─────────────────────────┬─────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────────┐
│                 DECISION ENGINE: Ranking Logic                │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  TREE 1: Filtering                                      │ │
│  │  Remove pools that don't meet requirements              │ │
│  └─────────────────────────────────────────────────────────┘ │
│                          │                                    │
│                          ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  TREE 2: ML Scoring ← [ML MODELS: ONNX Inference]      │ │
│  │  - Run classifier_6.onnx → savings_pct                 │ │
│  │  - Run regressor_6.onnx → cost_estimate                │ │
│  │  - Apply penalties → adjusted_savings                   │ │
│  │  - Calculate final_score                                │ │
│  └─────────────────────────────────────────────────────────┘ │
│                          │                                    │
│                          ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  TREE 3: Risk Categorization                           │ │
│  │  Assign SAFE / MODERATE / RISKY categories             │ │
│  └─────────────────────────────────────────────────────────┘ │
│                          │                                    │
│  Output: List[PoolScore] (sorted by final_score DESC)        │
└─────────────────────────┬─────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────────┐
│                BACKEND: Result Handling                       │
│                                                               │
│  - Convert PoolScore to JSON                                 │
│  - Cache in Redis (30-second TTL)                            │
│  - Return API response                                       │
└─────────────────────────┬─────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────────┐
│                      USER RESPONSE                            │
│  {                                                            │
│    "pools": [                                                 │
│      {                                                        │
│        "instance_type": "m5.xlarge",                          │
│        "az": "us-east-1a",                                    │
│        "savings_pct": 0.93,                                   │
│        "cost_estimate": 14.07,                                │
│        "final_score": 91.6,                                   │
│        "rank": 1,                                             │
│        "risk_category": "SAFE"                                │
│      },                                                       │
│      ...                                                      │
│    ]                                                          │
│  }                                                            │
└───────────────────────────────────────────────────────────────┘
```

---

## 🔍 Troubleshooting

### Issue: ML models not loading

**Solution:**
1. Check file paths in `ml_model/decision_engine/config.yaml`
2. Verify ONNX runtime installed: `pip install onnxruntime`
3. Test model loading: `python ml_model/model/spot_optimizer_v1/scripts/verify_onnx_local.py`

### Issue: Feature engineering fails (missing data)

**Solution:**
1. Check if `spot_price_history` table has 24-hour data
2. Enable minimum viable feature set: `use_minimum_viable_set: true` in config
3. Check family_hour_baselines table populated
4. Review backend logs for specific missing features

### Issue: Rankings seem wrong

**Solution:**
1. Enable debug logging in Decision Engine
2. Check configuration thresholds (`config.yaml`)
3. Verify blacklist flags in Redis: `redis-cli SMEMBERS risky_pools`
4. Compare ML predictions with Spot Advisor data
5. Run unit tests: `pytest tests/test_decision_engine.py`

---

## 📞 Contact & Support

**ML Team:** AtharvaAi ML Engineering
**Documentation Owner:** ML Team
**Last Review:** 2026-02-23
**Next Review:** 2026-03-23

**For Questions:**
- Backend Integration: See [PLAN.md](./PLAN.md)
- Model Details: See [SUMMARY.md](./SUMMARY.md)
- Feature Engineering: See SUMMARY.md - Section "Component 3"
- Decision Logic: See PLAN.md - Section "Binary Decision Trees"

---

**Status:** ✅ Documentation Complete
**Version:** 1.0
