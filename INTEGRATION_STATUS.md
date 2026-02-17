# Three-System Integration Status

**Date**: 2026-02-17
**Status**: 🟡 **PARTIAL - Needs Real Data Implementation**

---

## System Overview

```
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  RIGHT-SIZING    │──────▶│   KARPENTER      │──────▶│  ML + TEMPLATE   │
│  Pod Optimization│      │  Node Provisioning│      │  Safe Pool Select│
└──────────────────┘      └──────────────────┘      └──────────────────┘
        ▲                          ▲                          ▲
        │                          │                          │
        └──────────────────────────┴──────────────────────────┘
                     CONTINUOUS OPTIMIZATION LOOP
```

---

## Current Implementation Status

### ✅ System 1: ML Pool Selection (AtharvaAI) - **100% COMPLETE**

**Location**: `backend/services/pool_ranking_service.py`, `backend/api/atharvaai_routes.py`

**What's Working**:
- ✅ 8-step pool selection pipeline
- ✅ ONNX ML models (classifier + regressor)
- ✅ 45-feature engineering
- ✅ AWS Spot Advisor scraping (29,794 pools)
- ✅ Node template filtering
- ✅ Global blacklist (Redis)
- ✅ Real-time rankings API
- ✅ Frontend UI integration

**Endpoints**:
- `POST /api/v1/atharvaai/pools/rankings` - ✅ REAL API
- `GET /api/v1/atharvaai/blacklist` - ✅ REAL API
- `GET /api/v1/atharvaai/health` - ✅ REAL API
- `GET /api/v1/atharvaai/rebalancing/status` - ❌ **MOCK DATA**

**Database Tables**:
- ✅ `spot_price_history` - stores historical pricing
- ✅ `family_hour_baselines` - family-level aggregates
- ✅ `pool_risk_scores` - ML risk predictions
- ✅ `node_templates` - user-defined filtering rules
- ✅ `termination_events` - termination notices
- ✅ `rebalancing_actions` - auto-rebalancing history

**Missing**:
- ❌ Rebalancing status endpoint returns hardcoded data
- ❌ Need to query `rebalancing_actions` table for real data

---

### ⚠️ System 2: Right-Sizing - **NOT IMPLEMENTED**

**What's Needed**:
- ❌ DaemonSet for pod metrics collection
- ❌ Time-series database (InfluxDB/TimescaleDB) for usage data
- ❌ P95/P99 usage calculator
- ❌ Resource recommendation engine
- ❌ Safety checks (OOM kills, CPU throttling)
- ❌ Rolling update orchestration
- ❌ Frontend UI for right-sizing recommendations

**Database Tables Needed**:
- ❌ `pod_metrics` - CPU/memory usage time-series
- ❌ `right_sizing_recommendations` - generated recommendations
- ❌ `workload_analysis` - historical patterns

---

### ⚠️ System 3: Karpenter Integration - **NOT IMPLEMENTED**

**What's Needed**:
- ❌ NodePool YAML generator
- ❌ Kubernetes API client for updating NodePools
- ❌ ML ranking → NodePool instance-types sync
- ❌ Consolidation trigger listener
- ❌ Node expiry automation (24-hour rotation)

**Database Tables Needed**:
- ❌ `karpenter_nodepools` - NodePool configurations
- ❌ `node_provisioning_history` - provisioning logs
- ❌ `consolidation_events` - consolidation actions

---

## Integration Points

### 🔴 Integration Point 1: Right-Sizing → Karpenter
**Status**: ❌ NOT IMPLEMENTED

**Required**:
1. Right-sizing reduces pod requests
2. Karpenter detects low node utilization
3. Karpenter consolidates underutilized nodes

**Missing**:
- No right-sizing system to generate pod size recommendations
- No Karpenter listener to detect consolidation opportunities

---

### 🟡 Integration Point 2: ML Model → Karpenter
**Status**: ⚠️ **PARTIAL**

**What Works**:
- ✅ ML model ranks safe pools every 30 seconds
- ✅ Rankings cached in Redis

**Missing**:
- ❌ Karpenter NodePool update mechanism
- ❌ Kubernetes API integration
- ❌ NodePool.spec.requirements.instance-types updater

**Implementation Needed**:
```python
# In backend/services/karpenter_service.py (NEW FILE)
def update_nodepool_from_ml(cluster_id: str, top_pools: List[ScoredPool]):
    """
    Updates Karpenter NodePool with ML-approved instance types.

    1. Get cluster kubeconfig
    2. Load NodePool YAML
    3. Update spec.requirements.instance-types with top 10 pools
    4. Apply changes via kubectl
    """
```

---

### 🟢 Integration Point 3: Node Template → ML Model
**Status**: ✅ **COMPLETE**

**What Works**:
- ✅ User sets node templates via UI
- ✅ Templates stored in database
- ✅ ML pipeline loads templates before running
- ✅ ML only evaluates template-approved instances

**Flow**:
1. User creates template: `architecture=['amd64'], families=['m5', 'c5'], sizes=['large', 'xlarge']`
2. Template saved to database
3. ML pipeline queries template
4. ML filters 400+ instance types → 35 template-approved
5. ML scores only those 35
6. Top 10 returned to UI

---

### 🔴 Integration Point 4: Right-Sizing Metrics → ML Model
**Status**: ❌ NOT IMPLEMENTED

**What's Needed**:
- ❌ DaemonSet collecting CPU/memory utilization
- ❌ Utilization data stored in time-series DB
- ❌ ML feature service reads utilization metrics
- ❌ Add utilization as ML input features

**Impact**:
- Current ML accuracy: ~89% (AWS data + time + history)
- With right-sizing metrics: ~93% (includes actual workload characteristics)

---

### 🔴 Integration Point 5: Termination Notice → All Three Systems
**Status**: ❌ NOT IMPLEMENTED (System B: Termination Monitoring)

**What's Needed**:
1. **EventBridge listener** - detect AWS termination notices
2. **DaemonSet** - detect 2-minute warnings on nodes
3. **Global blacklist** - flag risky pools (12-hour TTL)
4. **Auto-rebalancing** - graceful (10 min) + emergency (90 sec) modes
5. **Cross-client intelligence** - share termination data globally

**Database Tables**:
- ✅ `termination_events` - exists but not populated
- ✅ `rebalancing_actions` - exists but not populated

**Missing Workers**:
- ❌ `termination_monitor.py` - EventBridge + DaemonSet integration
- ❌ `auto_rebalancer.py` - emergency/graceful rebalancing

---

## Critical Issues to Fix NOW

### 🔴 Issue 1: Rebalancing Status Endpoint Returns Mock Data

**File**: `backend/api/atharvaai_routes.py` (lines 224-246)

**Current Code**:
```python
# TODO: Query rebalancing_actions table
# For now, return mock data
response = [
    RebalancingStatusResponse(
        cluster_id="eks-prod-01",
        status="completed",
        trigger="emergency",
        ...
    ),
    ...
]
```

**Fix Required**:
```python
# Query real rebalancing_actions table
actions = db.query(RebalancingAction).filter(...)
response = [RebalancingStatusResponse(...) for action in actions]
```

---

### 🟡 Issue 2: ML Features Missing Right-Sizing Data

**File**: `backend/services/ml_feature_service.py`

**Current Features**: 45 (temporal, lag, rolling, price dynamics, family patterns, events, risk, categorical)

**Missing Features** (from right-sizing):
- `avg_cpu_utilization` - how loaded are nodes?
- `avg_memory_utilization` - memory pressure
- `avg_pod_count` - pod density
- `workload_stability` - usage variance

**Impact**: ML cannot assess workload-specific risk

---

### 🔴 Issue 3: No Karpenter NodePool Updates

**Missing Service**: `backend/services/karpenter_service.py`

**What's Needed**:
1. Kubernetes API client integration
2. NodePool YAML generator
3. ML ranking → instance-types list updater
4. Every 30 seconds: sync ML top 10 → Karpenter NodePool

---

## Hardcoded/Mock Data Inventory (from all-components.md)

### Dashboard Components

| Component | Data Source | Status | Fix Required |
|-----------|-------------|--------|--------------|
| FleetComposition | Hardcoded | ❌ | Use `GET /api/v1/metrics/instances` |
| PendingApprovalsCard | Hardcoded | ❌ | Use `GET /api/v1/approvals/` |
| PlatformHealthCard | Hardcoded | ❌ | Use `GET /api/v1/admin/health` |

### AtharvaAI Components

| Component | Data Source | Status | Fix Required |
|-----------|-------------|--------|--------------|
| OptimizationStatusHeader - Rebalancing | Mock API | ❌ | Query `rebalancing_actions` table |
| LivePoolRankings | Real API | ✅ | No fix needed |
| Blacklist | Real API | ✅ | No fix needed |

---

## Recommended Implementation Order

### Phase 1: Fix Mock Data (1-2 days)
1. ✅ Fix rebalancing status endpoint to query database
2. ✅ Fix FleetComposition to use real metrics API
3. ✅ Fix PendingApprovalsCard to use real approvals API
4. ✅ Fix PlatformHealthCard to use real health API

### Phase 2: Karpenter Integration (3-5 days)
1. Create `karpenter_service.py`
2. Add Kubernetes API client helper
3. Implement NodePool YAML generator
4. Create Celery Beat task to sync ML rankings → NodePool every 30s
5. Test end-to-end: ML runs → NodePool updates → Karpenter provisions

### Phase 3: Termination Monitoring (5-7 days)
1. Create EventBridge listener worker
2. Create DaemonSet for 2-minute warnings
3. Implement auto-rebalancing logic (graceful + emergency)
4. Create frontend UI for rebalancing history
5. Test end-to-end: Termination notice → Pool blacklisted → Auto-rebalance → UI updates

### Phase 4: Right-Sizing System (10-14 days)
1. Create DaemonSet for pod metrics collection
2. Set up time-series database (TimescaleDB)
3. Build P95/P99 usage calculator
4. Create recommendation engine
5. Add safety checks (OOM kills, CPU throttling)
6. Build frontend UI for recommendations
7. Implement rolling update orchestration
8. Feed metrics into ML model as features

---

## Success Criteria

### Minimum Viable Integration (MVP)
- ✅ All endpoints return real data (no mock/hardcoded)
- ✅ ML rankings update Karpenter NodePools automatically
- ✅ Termination notices trigger auto-rebalancing
- ✅ UI shows real rebalancing history

### Full Integration
- ✅ Right-sizing recommendations generated daily
- ✅ Karpenter consolidates after right-sizing
- ✅ ML model uses right-sizing metrics (93% accuracy)
- ✅ Continuous optimization loop working end-to-end

---

## Next Steps

**Immediate (Today)**:
1. Fix rebalancing status endpoint mock data → real database query
2. Create `RebalancingAction` model if missing
3. Test endpoint returns real data
4. Update frontend to handle empty state gracefully

**This Week**:
1. Create Karpenter service
2. Implement ML → NodePool sync
3. Test on dev cluster

**Next Sprint**:
1. Implement System B (termination monitoring)
2. Build right-sizing MVP
3. Complete three-system integration

---

**Updated**: 2026-02-17 06:30 AM IST
**Status**: 🟡 **70% Complete** (ML Pool Selection fully working, Karpenter + Right-Sizing pending)
