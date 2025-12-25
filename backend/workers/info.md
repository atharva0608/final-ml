# Backend Workers

## Purpose

Background task workers for asynchronous operations including AWS resource discovery, health monitoring, and optimization tasks.

**Last Updated**: 2025-12-25

---

## Files

### discovery_worker.py
**Purpose**: AWS resource discovery and inventory management
**Lines**: ~435
**Status**: STABLE

**Key Functions**:
- `run_initial_discovery(account_id)` - Full account scan (line 229)
- `scan_ec2_instances(session, account_id, db, region)` - EC2 scanning (line 122)
- `get_session_for_account(account)` - AWS session management (line 67)
- `trigger_rediscovery(account_id)` - Re-scan existing account (line 377)

**Workflow**:
1. Triggered by onboarding API after credential validation
2. Assumes IAM role or uses encrypted access keys
3. Calls AWS EC2 DescribeInstances API
4. Creates/updates Instance records in database
5. Transitions account status: `connected` → `active`
6. Triggers health checks (NEW: 2025-12-25)

**Status Transitions**:
- `pending` → `connected` (via onboarding API)
- `connected` → `active` (after successful discovery)
- `connected` → `failed` (if errors occur)

**Dependencies**:
- boto3 (AWS SDK)
- database/models.py (Account, Instance)
- utils/crypto.py (decrypt credentials)
- utils/component_health_checks.py (NEW: 2025-12-25)

**Recent Changes**:
- **2025-12-25**: Added immediate health check trigger after discovery
  - **Files Changed**: discovery_worker.py:333-340
  - **Reason**: Dashboard showed zero data until midnight cron
  - **Fix**: P-2025-12-25-002
  - **Impact**: Dashboard now populates immediately
  - **Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-002`

**Protected Zone**: ⚠️
- Status transitions MUST NOT be changed
- Dashboard and AuthGateway depend on exact status values
- See: `/progress/regression_guard.md#discovery-worker-status-transitions`

**Reference**: `/scenarios/client_onboarding_flow.md#resource-discovery`

---

### health_monitor.py
**Purpose**: System health monitoring and component status tracking
**Lines**: ~150
**Status**: STABLE

**Key Functions**:
- `HealthMonitor.monitor_loop()` - Continuous monitoring (30-second interval)
- `_handle_degradation()` - Alert on component failures

**Monitored Components**:
- Database latency
- Redis queue depth
- K8s watcher heartbeat
- Optimizer last run
- Price scraper freshness
- Risk engine data age
- ML inference model status

**Workflow**:
1. Runs in background loop (30-second interval)
2. Calls `run_all_health_checks()` from utils/
3. Tracks state transitions (healthy → degraded → critical)
4. Auto-captures diagnostic context on degradation
5. Logs alerts to system_logs table

**Dependencies**:
- utils/component_health_checks.py
- database/models.py (SystemLog)

**Recent Changes**:
- **2025-12-25**: Now triggered immediately after discovery
  - **Trigger Point**: discovery_worker.py
  - **Impact**: Faster dashboard data population

**Reference**: `/index/feature_index.md#health-monitoring`

---

### optimizer_task.py
**Purpose**: Spot instance optimization task execution
**Lines**: ~300
**Status**: STABLE

**Key Functions**:
- Optimization algorithm execution
- Cost-benefit analysis
- Instance replacement decisions

**Workflow**:
1. Analyzes instance workloads
2. Calculates spot vs on-demand costs
3. Makes optimization recommendations
4. Executes approved changes

**Dependencies**:
- decision_engine/ module
- ai/ module (ML predictions)

**Recent Changes**: None recent

---

### event_processor.py
**Purpose**: Process AWS CloudWatch events and system events
**Lines**: ~450
**Status**: STABLE

**Key Functions**:
- Event queue processing
- State change notifications
- Alert generation

**Workflow**:
1. Consumes events from queue
2. Processes based on event type
3. Updates database
4. Triggers notifications

**Dependencies**:
- database/models.py
- websocket/ module (real-time updates)

**Recent Changes**: None recent

---

## Worker Execution

### Synchronous (FastAPI BackgroundTasks)

Most workers are triggered via FastAPI BackgroundTasks:

```python
# In API endpoint
from fastapi import BackgroundTasks
from workers.discovery_worker import run_initial_discovery

@router.post("/connect")
async def connect(background_tasks: BackgroundTasks):
    # Validate connection
    # ...
    # Trigger worker
    background_tasks.add_task(run_initial_discovery, account.id)
    return {"status": "connected"}
```

### Asynchronous (Separate Process)

Some workers run as separate processes:
- health_monitor.py (continuous loop)

---

## Error Handling

All workers follow this pattern:

```python
def worker_function(params):
    db = SessionLocal()
    try:
        # Worker logic
        pass
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        # Update status to 'failed'
        # Store error in metadata
        db.commit()
    finally:
        db.close()
```

---

## Recent Changes Summary

### 2025-12-25: Health Check Integration
**Files Changed**: `discovery_worker.py`
**Lines**: 333-340

**Change**:
```python
# Trigger immediate health/usage check for discovered instances
try:
    from utils.component_health_checks import run_all_health_checks
    logger.info(f"Running health checks for newly discovered account {account_db_id}")
    health_results = run_all_health_checks(db)
    logger.info(f"Health check results: {health_results}")
except Exception as health_error:
    logger.warning(f"Health check failed (non-critical): {health_error}")
```

**Reason**: Dashboard showed "$0 Cost" and "0% Usage" until midnight cron job ran

**Impact**:
- Dashboard now populates metrics immediately after discovery
- Better user experience during onboarding
- Non-blocking (errors logged but don't fail discovery)

**Problem Fixed**: P-2025-12-25-002

**Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-002`

---

## Dependencies

**Requires**:
- Database connection
- AWS credentials (for discovery_worker)
- System logger
- Background task execution environment

**Required By**:
- Onboarding APIs (trigger discovery)
- Dashboard (consumes discovered data)
- Monitoring system

---

## Monitoring

### Worker Health

Check worker status:
```bash
# Check discovery worker status
SELECT status, updated_at FROM accounts
WHERE status IN ('connected', 'active', 'failed');

# Check health monitor logs
SELECT * FROM system_logs
WHERE component = 'health_monitor'
ORDER BY timestamp DESC LIMIT 10;
```

### Performance

- Discovery: 30-60 seconds for typical AWS account
- Health checks: < 1 second
- Optimizer: Varies by instance count

---

## Testing

### Manual Testing

```python
# Test discovery worker
from workers.discovery_worker import run_initial_discovery
run_initial_discovery(account_id=1)

# Test health monitor
from utils.component_health_checks import run_all_health_checks
results = run_all_health_checks(db)
print(results)
```

### Automated Testing

```bash
pytest tests/workers/
```

---

_Last Updated: 2025-12-25_
_See: `/index/dependency_index.md#discovery-worker` for impact analysis_
