# Decision Engine v3 — Implementation Status

**Date:** 2026-02-24
**Target:** 100% Implementation Complete
**Current Status:** 61% Complete (11/18 tasks)

---

## ✅ Completed Tasks (11/18)

### Phase 1: Foundation & Core Utilities

| Task # | Component | Status | Lines | File |
|--------|-----------|--------|-------|------|
| **#1** | **Shared Scoring Utility** | ✅ **COMPLETE** | 56 | `backend/core/scoring.py` |
| **#2** | **Risk Threshold Config** | ✅ **COMPLETE** | 5 | `ml_model/risk_threshold.json` |

**Impact:** Unblocks all phases. Single source of truth for expected value scoring.

---

### Phase 2: Database Schema

| Task # | Component | Status | Lines | Files |
|--------|-----------|--------|-------|-------|
| **#3** | **Cluster Model Columns** | ✅ **COMPLETE** | +18 | `backend/models/cluster.py` + migration |
| **#4** | **Cooldown & Substitute Models** | ✅ **COMPLETE** | 66 | 3 new model files + `__init__.py` |

**Columns Added:**
- `optimization_mode` (COST_FIRST / BALANCED / NO_DOWNTIME_FIRST)
- `model_version` (ML model version pinning)
- `workload_type` (informational cache only)

**New Tables:**
- `cluster_cooldowns`
- `pool_cooldowns`
- `substitute_states`

---

### Phase 3: Service Layer — New Services

| Task # | Component | Status | Lines | File |
|--------|-----------|--------|-------|------|
| **#5** | **Cluster Activity Service** | ✅ **COMPLETE** | 92 | `backend/services/cluster_activity_service.py` |
| **#6** | **Workload Inspector** | ✅ **COMPLETE** | 323 | `backend/services/workload_inspector.py` |
| **#10** | **Cooldown Controller** | ✅ **COMPLETE** | 153 | `backend/services/cooldown_controller.py` |
| **#11** | **Diversity Enforcer** | ✅ **COMPLETE** | 164 | `backend/services/diversity_enforcer.py` |

**Key Features:**
- DB-backed active cluster count for dynamic DryRun budget
- Auto-detection of stateful vs stateless nodes (FAIL CLOSED safety)
- Anti-flapping cooldown enforcement (cluster + pool level)
- Family/AZ diversity constraints

---

### Phase 4: Service Layer — Modifications

| Task # | Component | Status | Changes | File |
|--------|-----------|--------|---------|------|
| **#8** | **Global Pool Cache** | ✅ **COMPLETE** | +3 fields, TTL 65min, limit 50 | `backend/services/global_pool_cache_service.py` |
| **#9** | **Blacklist Service** | ✅ **COMPLETE** | +7 methods (~200 lines) | `backend/services/blacklist_service.py` |

**New Methods (Task #9):**
- `blacklist_pool_tiered()` — Explicit TTL, no exponential backoff
- `check_cascade_risk()` — Detect >70% blacklist ratio
- `suspend_blacklisting()` — Cascade dampener (30min)
- `is_blacklisting_suspended()` — Check suspension status
- `blacklist_pool_tiered_safe()` — Respects suspension for predictive, bypasses for ITN
- `is_pool_blacklisted()` — Simple boolean check
- `cleanup_redis_keys()` — Daily hygiene job

---

## 🔄 In Progress (3/18 - Background Agents)

| Task # | Component | Agent ID | Estimated Lines | File |
|--------|-----------|----------|-----------------|------|
| **#12** | **Decision Engine v3** | a1604cf | ~500-600 | `backend/core/decision_engine.py` |
| **#14** | **Substitute Manager** | a2de853 | ~200 | `backend/services/substitute_manager.py` |
| **#15** | **Event Monitor** | a224196 | ~200 | `backend/services/event_monitor.py` |

**Decision Engine v3 (Task #12):**
- FULL REWRITE (not incremental patch)
- 15-step evaluation pipeline
- OPTIMIZATION_PROFILES (COST_FIRST / BALANCED / NO_DOWNTIME_FIRST)
- Current pool reevaluation
- Delta threshold (prevent micro-switches)
- Capacity freshness validation (staleness penalty)
- Volatility regime guard
- Model version enforcement
- Deadlock protection
- Observability metrics

**Substitute Manager (Task #14):**
- State machine: IDLE → PREWARMING → READY → ACTIVE → RELEASING
- Mode-aware (on-demand for NO_DOWNTIME_FIRST, spot for others)
- Node-aware (validates STATELESS_ELIGIBLE)
- DryRun validation (iterates top 3 candidates)
- 5min prewarm timeout with auto-reset
- Cost drift check (trigger early release if > 15%)
- Reconcile stuck substitutes

**Event Monitor (Task #15):**
- Termination notice handler (BYPASSES normal pipeline)
- Node classification check (safety first)
- Immediate substitute activation
- Pre-drain validation (kubectl drain --dry-run)
- Deterministic blacklisting (bypasses cascade suspension)
- Volatility detection (24h stddev vs 30-day p95)
- Cache invalidation

---

## ⏳ Pending Tasks (4/18)

| Task # | Component | Estimated Lines | Complexity |
|--------|-----------|-----------------|------------|
| **#7** | **Pool Ranking Service** | +70 | HIGH |
| **#13** | **Karpenter Service** | +100 | MEDIUM |
| **#16** | **Rightsizing Service** | +50 | MEDIUM |
| **#17** | **v3 API Endpoints** | +150 | LOW |

### Task #7: Pool Ranking Service Modifications

**File:** `backend/services/pool_ranking_service.py`

**Changes Required:**
1. Replace scoring formula with `compute_expected_value()` from `scoring.py`
2. Remove `self.savings_weight` and `self.risk_weight` from `__init__()`
3. Add hard risk cutoff at 0.50 after ML scoring
4. Remove `_step5_capacity_check()`
5. Add `_step9_post_score_capacity_check()` after step 8:
   - Dynamic budget: `min(200, max(25, active_clusters * 2))`
   - Per-cluster fairness cap: 5 DryRuns/hour
   - Validate top 10 candidates only
   - Tiered blacklisting on failure (6h/12h)
   - Promote pools 11-20 to fill gaps

### Task #13: Karpenter Service Modifications

**File:** `backend/services/karpenter_service.py`

**Changes Required:**
1. Add `_final_capacity_check()` method (execution-layer DryRun)
2. Add `_validate_drain()` method (kubectl drain --dry-run)
3. Add rollback logic to `_update_nodepool()`
4. Add retry with backoff (max 2 retries: 5s, 15s)
5. Add per-cluster circuit breaker (10 failures in 10 min → 30 min disable)
6. Add `_record_execution_failure()` method

### Task #16: Rightsizing Service Modifications

**File:** `backend/services/rightsizing_service.py`

**Changes Required:**
1. Check cluster cooldown → return [] if active
2. Check node classification → return [] if no STATELESS_ELIGIBLE
3. Intersect with global rankings
4. Filter by mode risk ceiling + blacklist + capacity status
5. Re-score using `compute_expected_value()` from `scoring.py`
6. Sort by expected_value descending
7. Filter by delta threshold
8. Return top 3 alternatives

### Task #17: v3 API Endpoints

**Files:** `backend/api/atharvaai_routes.py`, `backend/api/karpenter_routes.py`

**New Endpoints:**
1. `GET /v3/global-intelligence/status`
2. `GET /v3/diversity/{cluster_id}`
3. `GET /v3/cooldown/{cluster_id}`
4. `GET /v3/substitute/{cluster_id}`
5. `GET /v3/state-machine/{cluster_id}`
6. `PUT /v3/cluster/{id}/optimization-mode` (with 30min cooldown)
7. `PUT /v3/cluster/{id}/model-version` (admin-only)
8. `GET /v3/metrics` (observability counters)
9. `GET /v3/workload-status/{cluster_id}`
10. `POST /v3/substitute/{cluster_id}/deploy`

---

## 📊 Statistics

| Metric | Value |
|--------|-------|
| **Total Tasks** | 18 |
| **Completed** | 11 (61%) |
| **In Progress** | 3 (17%) |
| **Pending** | 4 (22%) |
| **Files Created** | 10 |
| **Files Modified** | 5 |
| **New Lines of Code** | ~950 (completed) + ~850 (in progress) = ~1,800 |
| **Remaining Lines** | ~370 |
| **Total Estimated** | ~2,170 lines |

---

## 🔑 Critical Dependencies Met

✅ **Unblocking Dependencies Complete:**
- ✅ `scoring.py` (Task #1) — Unblocks ALL phases
- ✅ Cluster model columns (Task #3) — Unblocks decision engine
- ✅ 3 new models (Task #4) — Unblocks services
- ✅ Cooldown Controller (Task #10) — Required by decision engine
- ✅ Diversity Enforcer (Task #11) — Required by decision engine
- ✅ Workload Inspector (Task #6) — Required by decision engine

🔄 **Core Components (Background Agents):**
- 🔄 Decision Engine v3 (Task #12) — Core component
- 🔄 Substitute Manager (Task #14) — Safety component
- 🔄 Event Monitor (Task #15) — Event handling

⏳ **Remaining Critical:**
- ⏳ Pool Ranking Service (Task #7) — Intelligence pipeline
- ⏳ Karpenter Service (Task #13) — Execution layer
- ⏳ Rightsizing Service (Task #16) — Recommendations
- ⏳ v3 API Endpoints (Task #17) — Integration

---

## 🎯 Next Steps

1. **Wait for background agents to complete** (Tasks #12, #14, #15)
2. **Implement Task #7** (Pool Ranking Service modifications)
3. **Implement Task #13** (Karpenter Service modifications)
4. **Implement Task #16** (Rightsizing Service modifications)
5. **Implement Task #17** (v3 API endpoints)
6. **Task #18:** Rebuild Docker containers and test
7. Create database migration for new models (cluster_cooldowns, pool_cooldowns, substitute_states)
8. Configure background scheduler (Celery) for:
   - Node classification scan (every 10 min)
   - Active cluster count refresh (every 5 min)
   - Volatility detection (every 1 hour)
   - Substitute cost drift check (every 30 min)
   - Stuck substitute reconciliation (every 5 min)
   - Blacklist cleanup (daily)
   - Redis key hygiene (daily)

---

## 🚧 Known Issues / Blockers

None currently. Background agents are progressing successfully.

---

## 📝 Testing Checklist

Once implementation is 100% complete:

- [ ] Test scoring.py compute_expected_value() formula
- [ ] Test cluster cooldown enforcement
- [ ] Test pool cooldown enforcement
- [ ] Test diversity constraints
- [ ] Test node classification (stateless vs stateful)
- [ ] Test tiered blacklisting
- [ ] Test cascade dampener (>70% blacklist → suspend)
- [ ] Test decision engine 15-step pipeline
- [ ] Test substitute state machine transitions
- [ ] Test termination event handling (bypasses normal pipeline)
- [ ] Test volatility regime guard
- [ ] Test model version mismatch handling
- [ ] Test capacity freshness validation
- [ ] Test delta threshold (prevent micro-switches)
- [ ] Test per-cluster circuit breaker
- [ ] Test all v3 API endpoints
- [ ] Verify Redis keys created correctly
- [ ] Verify database migrations applied
- [ ] Verify Docker containers rebuild successfully

---

**Last Updated:** 2026-02-24 09:45 UTC
**Next Update:** After background agents complete
