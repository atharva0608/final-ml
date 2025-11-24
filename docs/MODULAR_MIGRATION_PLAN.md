# Modular Refactor Migration Plan

## Overview
Migrate all functionality from the monolithic backend (7,297 lines) to a clean modular architecture.

**Current Progress:** 13/63 endpoints (21%)
**Remaining Work:** 50 endpoints + background jobs
**Estimated Time:** 2-3 weeks

---

## Architecture Overview

### Target Structure
```
backend/
├── app.py (Main entry point - replaces backend_new.py)
├── config.py ✅ (Already exists)
├── database_manager.py ✅ (Already exists)
├── utils.py ✅ (Already exists)
│
├── api/ (API Routes - Blueprints)
│   ├── __init__.py ✅
│   ├── agent_routes.py ✅ (5/14 endpoints - 36% complete)
│   ├── client_admin_routes.py ✅ (8/21 endpoints - 38% complete)
│   ├── replica_routes.py ❌ NEW (0/9 endpoints)
│   ├── admin_routes.py ❌ NEW (0/15 endpoints)
│   └── notification_routes.py ❌ NEW (0/3 endpoints)
│
├── services/ (Business Logic)
│   ├── __init__.py ✅
│   ├── decision_engine.py ✅ (Partial)
│   ├── replica_coordinator.py ✅ (Partial)
│   ├── pricing_service.py ❌ NEW
│   ├── switch_service.py ❌ NEW
│   ├── notification_service.py ❌ NEW
│   └── ml_service.py ❌ NEW
│
├── jobs/ (Background Jobs)
│   ├── __init__.py ❌ NEW
│   ├── health_monitor.py ❌ NEW
│   ├── pricing_aggregator.py ❌ NEW
│   ├── data_cleaner.py ❌ NEW
│   └── snapshot_jobs.py ❌ NEW
│
└── models/ (Optional - Data Models)
    ├── __init__.py ❌ NEW
    ├── agent.py ❌ NEW
    ├── instance.py ❌ NEW
    └── replica.py ❌ NEW
```

---

## Migration Priorities

### ⭐ Priority 1: Agent Core (CRITICAL - Week 1)
**Why:** Agents depend on these for basic operation

#### Endpoints to Migrate (13)
- [ ] `POST /api/agents/<agent_id>/pricing-report` (Line 900-975 in main)
- [ ] `POST /api/agents/<agent_id>/switch-report` (Line 977-1046)
- [ ] `POST /api/agents/<agent_id>/termination` (Line 1048-1079)
- [ ] `POST /api/agents/<agent_id>/cleanup-report` (Line 1081-1118)
- [ ] `POST /api/agents/<agent_id>/rebalance-recommendation` (Line 1250-1291)
- [ ] `GET /api/agents/<agent_id>/replica-config` (Line 1293-1307)
- [ ] `POST /api/agents/<agent_id>/decide` (Line 1309-1433)
- [ ] `GET /api/agents/<agent_id>/switch-recommendation` (Line 1435-1578)
- [ ] `POST /api/agents/<agent_id>/issue-switch-command` (Line 1580-1774)

**Target File:** `backend/api/agent_routes.py`
**Estimated Time:** 2-3 days
**Dependencies:** None (can start immediately)

---

### ⭐⭐ Priority 2: Replica Management (CRITICAL - Week 1)
**Why:** Essential for manual replica mode and failover

#### Endpoints to Migrate (9)
- [ ] `POST /api/agents/<agent_id>/replicas` - Create replica (Line 5842-5989)
- [ ] `GET /api/agents/<agent_id>/replicas` - List replicas (Line 5995-6060)
- [ ] `PUT /api/agents/<agent_id>/replicas/<replica_id>` - Update instance_id (Line 6261-6312)
- [ ] `DELETE /api/agents/<agent_id>/replicas/<replica_id>` - Delete replica (Line 6204-6258)
- [ ] `POST /api/agents/<agent_id>/replicas/<replica_id>/promote` - Promote (Line 6063-6199)
- [ ] `POST /api/agents/<agent_id>/replicas/<replica_id>/status` - Update status (Line 6315-6389)
- [ ] `POST /api/agents/<agent_id>/replicas/<replica_id>/sync-status` - Sync status (Line 6721-6784)
- [ ] `POST /api/agents/<agent_id>/create-emergency-replica` - Emergency (Line 6397-6556)
- [ ] `POST /api/agents/<agent_id>/termination-imminent` - Termination notice (Line 6558-6718)

**Target File:** `backend/api/replica_routes.py` (NEW)
**Estimated Time:** 3-4 days
**Dependencies:** Agent core endpoints

---

### ⭐⭐⭐ Priority 3: Client Features (HIGH - Week 2)
**Why:** Frontend depends on these for user features

#### Instance Management (5 endpoints)
- [ ] `GET /api/client/instances/<instance_id>/pricing` (Line 2791-2857)
- [ ] `GET /api/client/instances/<instance_id>/metrics` (Line 2859-2911)
- [ ] `GET /api/client/instances/<instance_id>/price-history` (Line 2938-3035)
- [ ] `GET /api/client/instances/<instance_id>/available-options` (Line 3037-3098)
- [ ] `POST /api/client/instances/<instance_id>/force-switch` (Line 3100-3196)

#### Agent Management (8 endpoints)
- [ ] `GET /api/client/<client_id>/agents/decisions` (Line 2231-2284)
- [ ] `GET /api/client/<client_id>/agents/history` (Line 2583-2646)
- [ ] `GET /api/client/<client_id>/instances` (Line 2648-2691)
- [ ] `GET /api/client/<client_id>/replicas` (Line 2693-2788)
- [ ] `GET /api/client/<client_id>/stats/charts` (Line 2333-2420)
- [ ] `GET /api/client/<client_id>/switch-history` (Line 3198-3238)
- [ ] `GET /api/client/agents/<agent_id>` (Line 2520-2581)
- [ ] `POST /api/client/agents/<agent_id>/config` (Line 2395-2511)
- [ ] `POST /api/client/agents/<agent_id>/toggle-enabled` (Line 2286-2331)

#### Pricing History (1 endpoint)
- [ ] `GET /api/client/pricing-history` (Line 3037-3169) ✅ **ALREADY ADDED**

#### Notifications (3 endpoints)
- [ ] `GET /api/notifications` (Line 3240-3265)
- [ ] `POST /api/notifications/<notif_id>/mark-read` (Line 3267-3282)
- [ ] `POST /api/notifications/mark-all-read` (Line 3284-3298)

**Target Files:**
- `backend/api/client_routes.py` (instance + agent management)
- `backend/api/notification_routes.py` (NEW - notifications)

**Estimated Time:** 4-5 days
**Dependencies:** Replica management

---

### ⭐⭐⭐⭐ Priority 4: Admin Operations (MEDIUM - Week 2-3)
**Why:** Needed for system management

#### Client Management (7 endpoints)
- [ ] `POST /api/admin/clients/create` (Line 1776-1832)
- [ ] `GET /api/admin/clients` (Line 1966-2009)
- [ ] `GET /api/admin/clients/<client_id>` (Line 2011-2036)
- [ ] `DELETE /api/admin/clients/<client_id>` (Line 1834-1863)
- [ ] `POST /api/admin/clients/<client_id>/regenerate-token` (Line 1865-1902)
- [ ] `GET /api/admin/clients/<client_id>/token` (Line 1904-1920)
- [ ] `GET /api/admin/clients/growth` (Line 3873-3909)

#### ML Model Management (4 endpoints)
- [ ] `POST /api/admin/ml-models/upload` (Line 3425-3563)
- [ ] `POST /api/admin/ml-models/activate` (Line 3565-3632)
- [ ] `POST /api/admin/ml-models/fallback` (Line 3634-3690)
- [ ] `GET /api/admin/ml-models/sessions` (Line 3392-3423)

#### System Monitoring (4 endpoints)
- [ ] `GET /api/admin/instances` (Line 2038-2084)
- [ ] `GET /api/admin/agents` (Line 2086-2127)
- [ ] `GET /api/admin/activity` (Line 2129-2179)
- [ ] `POST /api/admin/decision-engine/upload` (Line 3713-3871)

**Target File:** `backend/api/admin_routes.py` (NEW)
**Estimated Time:** 3-4 days
**Dependencies:** None (independent)

---

### ⭐⭐⭐⭐⭐ Priority 5: Background Jobs (LOW - Week 3)
**Why:** Can run from monolithic backend initially

#### Jobs to Migrate
1. **Agent Health Monitor** (Line 4200-4223)
   - Runs every 5 minutes
   - Marks stale agents as offline
   - Target: `backend/jobs/health_monitor.py`

2. **Pricing Deduplication** (Line 4225-4261)
   - Runs hourly
   - Deduplicates pricing submissions
   - Target: `backend/jobs/pricing_aggregator.py`

3. **Gap Filling** (Line 4263-4282)
   - Runs daily
   - Fills gaps in pricing data
   - Target: `backend/jobs/pricing_aggregator.py`

4. **Client Snapshots** (Line 4027-4055)
   - Runs daily at 12:05 AM
   - Captures client growth data
   - Target: `backend/jobs/snapshot_jobs.py`

5. **Monthly Savings** (Line 4057-4083)
   - Runs monthly
   - Calculates monthly savings
   - Target: `backend/jobs/snapshot_jobs.py`

6. **Data Cleanup** (Line 4085-4116)
   - Runs daily
   - Cleans old data
   - Target: `backend/jobs/data_cleaner.py`

**Estimated Time:** 2-3 days
**Dependencies:** All endpoints migrated

---

## Services to Extract

### 1. Pricing Service
**File:** `backend/services/pricing_service.py`

**Functions:**
- `store_pricing_report(agent_id, data)` - Store pricing from agent
- `get_pricing_history(agent_id, days)` - Get historical pricing
- `aggregate_pricing_data()` - Hourly aggregation
- `fill_pricing_gaps()` - Gap filling
- `deduplicate_pricing()` - Remove duplicates

**Lines in Main:** 900-975, 2938-3169, 4225-4282

---

### 2. Switch Service
**File:** `backend/services/switch_service.py`

**Functions:**
- `record_switch(agent_id, switch_data)` - Record switch event
- `issue_switch_command(agent_id, target)` - Issue switch command
- `get_switch_history(client_id)` - Get switch history
- `calculate_switch_impact(old, new)` - Calculate savings

**Lines in Main:** 977-1046, 1580-1774, 3198-3238

---

### 3. Notification Service
**File:** `backend/services/notification_service.py`

**Functions:**
- `create_notification(client_id, message)` - Create notification
- `get_notifications(client_id)` - Get user notifications
- `mark_as_read(notification_id)` - Mark notification read
- `mark_all_read(client_id)` - Mark all read

**Lines in Main:** 3240-3298

---

### 4. ML Model Service
**File:** `backend/services/ml_service.py`

**Functions:**
- `upload_model(files)` - Upload ML model
- `activate_model(session_id)` - Activate model
- `set_fallback(session_id)` - Set fallback model
- `get_sessions()` - Get model sessions
- `load_decision_engine()` - Load decision engine

**Lines in Main:** 3392-3690

---

## Migration Steps (Per Endpoint)

### Template Process
1. **Copy endpoint code** from `main/backend/backend.py`
2. **Extract to appropriate blueprint** in modular structure
3. **Extract business logic** to service layer
4. **Update imports** and dependencies
5. **Test endpoint** works correctly
6. **Update documentation**

### Example: Migrating pricing-report endpoint

**Before (main/backend/backend.py:900-975):**
```python
@app.route('/api/agents/<agent_id>/pricing-report', methods=['POST'])
@require_client_token
def pricing_report(agent_id: str):
    data = request.json
    # ... 75 lines of logic ...
    return jsonify({'success': True})
```

**After (modular):**

**api/agent_routes.py:**
```python
@agent_bp.route('/<agent_id>/pricing-report', methods=['POST'])
def pricing_report(agent_id: str):
    from backend.services.pricing_service import store_pricing_report
    data = request.json
    result = store_pricing_report(agent_id, data)
    return jsonify(result)
```

**services/pricing_service.py:**
```python
def store_pricing_report(agent_id: str, data: dict) -> dict:
    """Store pricing report from agent"""
    instance = data.get('instance', {})
    pricing = data.get('pricing', {})

    # ... business logic ...

    return {'success': True}
```

---

## Testing Strategy

### Unit Tests
- [ ] Test each service function independently
- [ ] Mock database calls
- [ ] Test edge cases and error handling

### Integration Tests
- [ ] Test each endpoint with real database
- [ ] Verify responses match original backend
- [ ] Test authentication and authorization

### Regression Tests
- [ ] Compare responses between old and new backends
- [ ] Ensure all agent operations still work
- [ ] Verify frontend compatibility

---

## Migration Tracking

### Week 1 Goals
- ✅ Priority 1: Agent Core (13 endpoints)
- ✅ Priority 2: Replica Management (9 endpoints)
- **Total:** 22 endpoints migrated (35% progress)

### Week 2 Goals
- ✅ Priority 3: Client Features (18 endpoints)
- ✅ Priority 4 (Partial): Admin Operations (7 endpoints)
- **Total:** 47 endpoints migrated (75% progress)

### Week 3 Goals
- ✅ Priority 4 (Complete): Admin Operations (4 endpoints)
- ✅ Priority 5: Background Jobs (6 jobs)
- ✅ Testing and documentation
- **Total:** 100% complete

---

## Rollout Strategy

### Phase 1: Development (Weeks 1-2)
- Migrate all endpoints to modular structure
- Test each endpoint as it's migrated
- Keep old backend.py as reference

### Phase 2: Testing (Week 3)
- Run both backends side-by-side
- Compare responses for consistency
- Fix any discrepancies

### Phase 3: Deployment
- Deploy modular backend to staging
- Test with real agents
- Monitor for issues

### Phase 4: Cleanup
- Remove old backend.py
- Update documentation
- Archive migration materials

---

## Risk Mitigation

### Risks
1. **Breaking changes** - New backend doesn't match old behavior
2. **Missing functionality** - Forgot to migrate something
3. **Performance issues** - Modular structure slower
4. **Integration issues** - Services don't communicate properly

### Mitigations
1. **Side-by-side testing** - Run both backends in parallel
2. **Comprehensive checklist** - Track every endpoint
3. **Performance benchmarks** - Measure response times
4. **Gradual rollout** - Deploy to subset of agents first

---

## Success Criteria

### Must Have
- ✅ All 63 endpoints working
- ✅ All background jobs running
- ✅ Response times within 10% of original
- ✅ Zero breaking changes for agents
- ✅ Zero breaking changes for frontend

### Nice to Have
- ✅ Better test coverage
- ✅ Improved performance
- ✅ Better error handling
- ✅ Comprehensive documentation

---

## Next Steps

1. **Review this plan** - Confirm priorities and timeline
2. **Set up modular branch** - Merge latest fixes from main
3. **Start with Priority 1** - Migrate agent core endpoints
4. **Track progress** - Update checklist daily
5. **Test continuously** - Don't wait until the end

---

**Created:** November 23, 2025
**Author:** Claude
**Status:** 📝 Ready for Review
**Next Action:** Begin Priority 1 migration
