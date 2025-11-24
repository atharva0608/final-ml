# Modular Migration Progress

## Overview

**Migration Status:** 🟡 IN PROGRESS
**Completion:** 2% (1/63 endpoints)
**Branch:** `claude/fix-replica-agent-reference-01F4nEg8izLHTvWD6cD9eLSM`

---

## Architecture Completed ✅

### Foundation Modules
- ✅ `backend/config.py` - Centralized configuration
- ✅ `backend/database_manager.py` - Database connection pooling
- ✅ `backend/utils.py` - Common utilities (UUID, tokens, notifications)
- ✅ `backend/auth.py` - Authentication middleware
- ✅ `backend/app.py` - New modular entry point

### Directory Structure
- ✅ `backend/api/` - API route blueprints
- ✅ `backend/services/` - Business logic layer
- ✅ `backend/jobs/` - Background jobs
- ✅ `backend/models/` - Data models (optional)

---

## Services Created

### Pricing Service ✅
**File:** `backend/services/pricing_service.py`

**Functions:**
- ✅ `store_pricing_report(agent_id, client_id, data)` - Store pricing from agents
- ✅ `get_pricing_history(agent_id, days)` - Retrieve pricing history

**Used by:**
- Agent pricing-report endpoint

---

## API Routes Migrated

### Agent Routes
**File:** `backend/api/agent_routes.py`
**Progress:** 1/9 endpoints (11%)

| Endpoint | Status | Service | Notes |
|----------|--------|---------|-------|
| POST /<agent_id>/pricing-report | ✅ DONE | pricing_service | Stores agent pricing data |
| POST /<agent_id>/switch-report | ⏳ TODO | switch_service | Record switch events |
| POST /<agent_id>/termination | ⏳ TODO | instance_service | Handle termination |
| POST /<agent_id>/cleanup-report | ⏳ TODO | switch_service | Post-switch cleanup |
| POST /<agent_id>/rebalance-recommendation | ⏳ TODO | replica_service | AWS rebalance notices |
| GET /<agent_id>/replica-config | ⏳ TODO | replica_service | Get replica config |
| POST /<agent_id>/decide | ⏳ TODO | decision_service | ML decision request |
| GET /<agent_id>/switch-recommendation | ⏳ TODO | decision_service | Get recommendation |
| POST /<agent_id>/issue-switch-command | ⏳ TODO | switch_service | Issue switch command |

### Replica Routes
**File:** `backend/api/replica_routes.py` (NOT CREATED YET)
**Progress:** 0/9 endpoints (0%)

| Endpoint | Status | Service | Notes |
|----------|--------|---------|-------|
| POST /<agent_id>/replicas | ⏳ TODO | replica_service | Create replica |
| GET /<agent_id>/replicas | ⏳ TODO | replica_service | List replicas |
| PUT /<agent_id>/replicas/<replica_id> | ⏳ TODO | replica_service | Update replica |
| DELETE /<agent_id>/replicas/<replica_id> | ⏳ TODO | replica_service | Delete replica |
| POST /<agent_id>/replicas/<replica_id>/promote | ⏳ TODO | replica_service | Promote replica |
| POST /<agent_id>/replicas/<replica_id>/status | ⏳ TODO | replica_service | Update status |
| POST /<agent_id>/replicas/<replica_id>/sync-status | ⏳ TODO | replica_service | Sync status |
| POST /<agent_id>/create-emergency-replica | ⏳ TODO | replica_service | Emergency replica |
| POST /<agent_id>/termination-imminent | ⏳ TODO | replica_service | Termination notice |

### Client Routes
**File:** `backend/api/client_routes.py` (NOT CREATED YET)
**Progress:** 0/18 endpoints (0%)

### Admin Routes
**File:** `backend/api/admin_routes.py` (NOT CREATED YET)
**Progress:** 0/11 endpoints (0%)

### Notification Routes
**File:** `backend/api/notification_routes.py` (NOT CREATED YET)
**Progress:** 0/3 endpoints (0%)

---

## Services Needed (Not Yet Created)

### Switch Service
**File:** `backend/services/switch_service.py` ⏳

**Functions needed:**
- `record_switch(agent_id, switch_data)` - Record switch event
- `issue_switch_command(agent_id, target)` - Issue switch command
- `get_switch_history(client_id)` - Get switch history
- `calculate_switch_impact(old, new)` - Calculate savings

**Extracted from lines:** 977-1046, 1580-1774, 3198-3238 in backend.py

### Replica Service
**File:** `backend/services/replica_service.py` ⏳

**Functions needed:**
- `create_replica(agent_id, pool_id)` - Create new replica
- `list_replicas(agent_id)` - List agent replicas
- `promote_replica(agent_id, replica_id)` - Promote to primary
- `delete_replica(agent_id, replica_id)` - Delete replica
- `update_replica_status(replica_id, status)` - Update status
- `create_emergency_replica(agent_id)` - Emergency failover
- `handle_termination_imminent(agent_id)` - Handle termination notice

**Extracted from lines:** 5842-6784 in backend.py

### Decision Service
**File:** `backend/services/decision_service.py` ⏳

**Functions needed:**
- `make_decision(agent_id, instance, pricing)` - ML decision
- `get_switch_recommendation(agent_id)` - Get recommendation
- `load_decision_engine()` - Load ML model

**Extracted from lines:** 1309-1578 in backend.py

### Notification Service
**File:** `backend/services/notification_service.py` ⏳

**Functions needed:**
- `get_notifications(client_id)` - Get user notifications
- `mark_as_read(notification_id)` - Mark notification read
- `mark_all_read(client_id)` - Mark all read

**Extracted from lines:** 3240-3298 in backend.py

### ML Service
**File:** `backend/services/ml_service.py` ⏳

**Functions needed:**
- `upload_model(files)` - Upload ML model
- `activate_model(session_id)` - Activate model
- `set_fallback(session_id)` - Set fallback model
- `get_sessions()` - Get model sessions

**Extracted from lines:** 3392-3690 in backend.py

---

## Background Jobs (Not Migrated)

### Health Monitor
**File:** `backend/jobs/health_monitor.py` ⏳
**Schedule:** Every 5 minutes
**Purpose:** Mark stale agents as offline
**Extracted from lines:** 4200-4223 in backend.py

### Pricing Aggregator
**File:** `backend/jobs/pricing_aggregator.py` ⏳
**Schedule:** Hourly + Daily
**Purpose:** Deduplicate pricing, fill gaps
**Extracted from lines:** 4225-4282 in backend.py

### Data Cleaner
**File:** `backend/jobs/data_cleaner.py` ⏳
**Schedule:** Daily
**Purpose:** Clean old data
**Extracted from lines:** 4085-4116 in backend.py

### Snapshot Jobs
**File:** `backend/jobs/snapshot_jobs.py` ⏳
**Schedule:** Daily + Monthly
**Purpose:** Client growth snapshots, monthly savings
**Extracted from lines:** 4027-4083 in backend.py

---

## Testing Status

### Unit Tests
- ⏳ pricing_service tests
- ⏳ switch_service tests
- ⏳ replica_service tests
- ⏳ decision_service tests

### Integration Tests
- ⏳ Agent endpoints
- ⏳ Client endpoints
- ⏳ Admin endpoints
- ⏳ Replica endpoints

### Regression Tests
- ⏳ Compare modular vs monolithic responses
- ⏳ Agent compatibility check
- ⏳ Frontend compatibility check

---

## Next Steps

### Immediate (Current Session)
1. ✅ Create foundation modules
2. ✅ Create pricing service
3. ✅ Migrate first endpoint (pricing-report)
4. ⏳ Continue migrating Priority 1 endpoints

### Priority 1 - Agent Core (Week 1)
- [ ] Migrate switch-report endpoint
- [ ] Migrate termination endpoint
- [ ] Migrate cleanup-report endpoint
- [ ] Migrate rebalance-recommendation endpoint
- [ ] Migrate replica-config endpoint
- [ ] Migrate decide endpoint
- [ ] Migrate switch-recommendation endpoint
- [ ] Migrate issue-switch-command endpoint

### Priority 2 - Replica Management (Week 1)
- [ ] Create replica_routes.py
- [ ] Create replica_service.py
- [ ] Migrate all 9 replica endpoints

### Priority 3 - Client Features (Week 2)
- [ ] Create client_routes.py
- [ ] Migrate instance management endpoints (5)
- [ ] Migrate agent management endpoints (8)
- [ ] Migrate pricing history endpoint (1)
- [ ] Migrate notification endpoints (3)

### Priority 4 - Admin Operations (Week 2-3)
- [ ] Create admin_routes.py
- [ ] Migrate client management (7)
- [ ] Migrate ML model management (4)
- [ ] Migrate system monitoring (4)

### Priority 5 - Background Jobs (Week 3)
- [ ] Create all job files
- [ ] Test job scheduling
- [ ] Verify data quality jobs work

---

## Timeline

### Week 1 (Current)
- **Goal:** Complete Priority 1 + Priority 2 (22 endpoints)
- **Status:** 1/22 endpoints complete (5%)

### Week 2
- **Goal:** Complete Priority 3 + Priority 4 (partial)
- **Target:** 47/63 endpoints (75%)

### Week 3
- **Goal:** Complete Priority 4 + Priority 5 + Testing
- **Target:** 63/63 endpoints (100%)

---

## How to Continue Migration

### Pattern for Migrating an Endpoint

1. **Read endpoint from backend.py**
   ```bash
   # Find endpoint line number
   grep -n "endpoint_name" backend/backend.py
   ```

2. **Extract business logic to service**
   ```python
   # backend/services/example_service.py
   def example_function(arg1, arg2):
       """Docstring explaining what this does"""
       # Business logic here
       return result
   ```

3. **Create route in blueprint**
   ```python
   # backend/api/example_routes.py
   @example_bp.route('/<id>/action', methods=['POST'])
   @require_client_token
   def action(id: str):
       from backend.services.example_service import example_function
       result = example_function(id, request.json)
       return jsonify(result), 200
   ```

4. **Register blueprint in app.py**
   ```python
   from backend.api.example_routes import example_bp
   app.register_blueprint(example_bp)
   ```

5. **Test endpoint**
   ```bash
   curl -X POST http://localhost:5000/api/example/123/action \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"key": "value"}'
   ```

---

**Last Updated:** 2025-11-24
**Current Branch:** claude/fix-replica-agent-reference-01F4nEg8izLHTvWD6cD9eLSM
**Next Endpoint to Migrate:** POST /api/agents/<agent_id>/switch-report
