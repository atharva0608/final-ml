# Backend Workers Module - Complete Implementation Reference

## Purpose

Asynchronous background workers for AWS resource discovery, health monitoring, optimization execution, and event processing.

**Last Updated**: 2025-12-25 (Comprehensive Enhancement)
**Authority Level**: CRITICAL
**Total Workers**: 4 files
**Total Lines**: ~1,300

---

## Complete Worker Reference

### 1. discovery_worker.py - AWS RESOURCE DISCOVERY (444 lines) ⭐ CRITICAL

**Purpose**: Scan AWS accounts for EC2 instances and populate database

**Entry Point**: `run_initial_discovery(account_db_id)` (line 229)

**Complete Flow**:
```
1. Triggered by: onboarding_routes.py after connection verification
   ↓
2. Retrieve Account record from database (line 248)
   ↓
3. Get AWS Session based on connection_method (line 269):
   - IAM Role: Call get_assumed_session() → STS AssumeRole with ExternalID
   - Access Keys: Decrypt credentials → Create session with access keys
   ↓
4. Scan EC2 instances via scan_ec2_instances() (line 122):
   - Call AWS EC2 DescribeInstances API
   - Filter: running, pending, stopping, stopped states
   - Extract: instance_id, instance_type, state, lifecycle, tags
   - Identify Kubernetes clusters from tags (line 159-164)
   - Determine auth_status from "ManagedBy" tag
   - UPSERT to instances table (update if exists, insert if new)
   ↓
5. Update Account status (line 306):
   - status: 'connected' → 'active' ⚠️ PROTECTED
   - is_active: True
   - account_metadata: last_scan, instances_discovered, regions_scanned
   ↓
6. Trigger immediate health checks (line 334) ⭐ NEW 2025-12-25
   - Import run_all_health_checks()
   - Non-blocking: errors logged but don't fail discovery
   ↓
7. Commit changes and close session
```

**Key Functions**:

#### get_session_for_account(account) - Lines 67-119
**Purpose**: Get boto3 session supporting dual authentication

**Flow**:
```python
if connection_method == 'access_keys':
    access_key = decrypt_credential(account.aws_access_key_id)
    secret_key = decrypt_credential(account.aws_secret_access_key)
    return boto3.Session(access_key, secret_key, region)
elif connection_method == 'iam_role':
    return get_assumed_session(role_arn, external_id, region)
```

**Encryption**: Uses `utils.crypto.decrypt_credential()` for AES-256 decryption

---

#### scan_ec2_instances(session, account_id, db, region) - Lines 122-227
**Purpose**: Scan single region for EC2 instances

**API Call**:
```python
ec2 = session.client('ec2', region_name=region)
response = ec2.describe_instances(
    Filters=[
        {'Name': 'instance-state-name',
         'Values': ['running', 'pending', 'stopping', 'stopped']}
    ]
)
```

**Kubernetes Detection** (lines 159-164):
```python
cluster_name = (
    tags.get('kubernetes.io/cluster/name') or
    tags.get('eks:cluster-name') or
    tags.get('eks:nodegroup-name') or
    tags.get('aws:autoscaling:groupName')
)
```

**Authorization Detection** (lines 167-168):
```python
managed_by = tags.get('ManagedBy', '').lower()
auth_status = 'authorized' if managed_by == 'spotoptimizer' else 'unauthorized'
```

**Database Operations**:
```
1. Query Instance WHERE instance_id = ec2_instance_id
2. If exists: UPDATE (instance_type, region, state, lifecycle, auth_status, metadata)
3. Else: INSERT new Instance record with all fields
4. Commit after all instances processed
```

---

#### run_initial_discovery(account_db_id) - Lines 229-384 ⭐ MAIN ENTRY
**Purpose**: Main worker function triggered by FastAPI BackgroundTasks

**Execution Context**: FastAPI background task (non-blocking)

**Error Handling**:
- Authentication failure → Account status = 'failed', store error in metadata
- Region scan failure → Log error, continue with other regions
- Worker crash → Fresh DB session, update status to 'failed', store traceback

**Success Criteria**:
- All regions scanned successfully
- Account status transitioned to 'active'
- Health checks triggered (non-blocking)

**System Logging** (lines 254-329):
```python
sys_logger.info("Starting discovery for account...")
sys_logger.info("Scanned region us-east-1: found 23 instances")
sys_logger.success("Discovery completed successfully: 23 instances found")
```

---

#### trigger_rediscovery(account_db_id) - Lines 386-444
**Purpose**: Re-scan existing active account (periodic refresh)

**Differences from Initial Discovery**:
- Does NOT change account status (stays 'active')
- Only scans account's configured region
- Updates metadata with last_scan timestamp
- Used for periodic updates, not onboarding

---

**Database Tables**:
- **READ**: `accounts` (verify status, get credentials)
- **WRITE**: `instances` (UPSERT discovered instances)
- **UPDATE**: `accounts` (status transition, metadata update)

**API Trigger Points**:
- `backend/api/onboarding_routes.py:553` (CloudFormation verify)
- `backend/api/onboarding_routes.py:270` (Access keys connect)

**Frontend Components**:
- `ClientSetup.jsx` - startPollingAccountStatus() (line ~162)
- Polls GET /client/onboarding/{id}/discovery every 3 seconds

**Protected Zone**: ⚠️
- Status transition `connected` → `active` MUST NOT change
- See: `/progress/regression_guard.md#discovery-worker-status-transitions`

**Recent Changes**:
- **2025-12-25**: Added immediate health check trigger (lines 334-340)
- **Reason**: Dashboard showed $0 until midnight cron
- **Impact**: Dashboard now populates immediately after discovery
- **Fixed**: P-2025-12-25-002

---

## 2. health_monitor.py - HEALTH MONITORING (146 lines)

**Purpose**: Continuous health monitoring with state transition detection

**Execution Mode**: Background thread (daemon=True, 30-second loop)

**Entry Point**: `start_health_monitor_background()` (line 132)

**Complete Flow**:
```
1. Start background daemon thread on app startup (main.py)
   ↓
2. Run monitor_loop() continuously every 30 seconds (line 33)
   ↓
3. Call run_all_health_checks(db) from utils/ (line 48)
   ↓
4. Compare results with previous_states dict (line 52)
   ↓
5. Detect state transitions:
   - healthy → degraded/critical: Call _handle_degradation()
   - degraded/critical → healthy: Log recovery message
   ↓
6. Store new states, sleep 30 seconds, repeat
```

**State Transition Detection** (lines 51-66):
```python
previous_status = self.previous_states.get(component_name, "healthy")

# Detect degradation
if previous_status == "healthy" and current_status != "healthy":
    self._handle_degradation(db, component_name, current_status, details)

# Detect recovery
elif previous_status != "healthy" and current_status == "healthy":
    logger.info(f"✅ Component recovered: {component_name}")

# Update state
self.previous_states[component_name] = current_status
```

**Auto-Diagnostic Context** (lines 76-124):
```python
def _handle_degradation(self, db, component_name, new_status, details):
    # Fetch last 15 logs for diagnostic context
    recent_logs = db.query(SystemLog).filter(
        SystemLog.component == component_name
    ).order_by(SystemLog.timestamp.desc()).limit(15).all()

    # Create alert with context
    alert = {
        "component": component_name,
        "status": new_status,
        "details": details,
        "diagnostic_logs": log_summary  # Last 15 logs
    }

    # TODO: Send to PagerDuty/Slack
```

**Monitored Components** (from utils/component_health_checks.py):
- Database latency
- Redis queue depth
- K8s watcher heartbeat
- Optimizer last run
- Price scraper freshness
- Risk engine data age
- ML inference model status

**Startup Integration** (line 132):
```python
def start_health_monitor_background():
    import threading

    monitor = HealthMonitor()
    thread = threading.Thread(target=monitor.monitor_loop, daemon=True)
    thread.start()

    return monitor
```

**Database Tables**:
- **READ**: `system_logs` (fetch diagnostic context)
- **DEPENDS ON**: `utils.component_health_checks.run_all_health_checks()`

**Recent Changes**:
- **2025-12-25**: Now triggered immediately after discovery
- **Trigger Point**: discovery_worker.py:334-340
- **Impact**: Faster dashboard data population

---

## 3. optimizer_task.py - PIPELINE ROUTER (308 lines) ⭐ CRITICAL

**Purpose**: Route optimization requests to appropriate pipeline based on instance configuration

**Entry Point**: `run_optimization_cycle(instance_id, db)` (line 171)

**The Fork in the Road** - Pipeline Decision (lines 229-246):
```python
pipeline_mode = instance.pipeline_mode or "LINEAR"

if pipeline_mode == 'LINEAR':
    # Lab Mode: Single-instance atomic switch
    result = run_linear_pipeline(instance, db)

elif pipeline_mode == 'CLUSTER':
    # Production: Batch cluster optimization
    result = run_cluster_pipeline(instance, db)

elif pipeline_mode == 'KUBERNETES':
    # K8s-aware node optimization
    result = run_kubernetes_pipeline(instance, db)
```

**Complete Flow**:
```
1. API calls run_optimization_cycle(instance_uuid, db)
   ↓
2. Fetch Instance from database (line 205)
   ↓
3. Read pipeline_mode field from instance record
   ↓
4. Route to appropriate pipeline:

   LINEAR (Lab Mode):
   ├─ Scraper: Fetch real-time spot prices
   ├─ Safe Filter: Filter historic interrupt rate < 20%
   ├─ ML Inference: Predict crash probability
   ├─ Decision: Select best candidate
   └─ Atomic Switch: Direct instance replacement

   CLUSTER (Production):
   ├─ Fetch all instances in ASG
   ├─ Batch optimization analysis
   ├─ Apply optimizations with parallelization
   └─ Track global risk contagion

   KUBERNETES:
   ├─ Cordon node (mark unschedulable)
   ├─ Drain pods respecting PodDisruptionBudgets
   ├─ Atomic EC2 switch
   ├─ Wait for new node to join cluster
   └─ Uncordon and verify pod rescheduling
   ↓
5. Return execution summary with decision, timing, metadata
```

**Pipeline Functions**:

#### run_linear_pipeline(instance, db) - Lines 88-125
**Purpose**: Simplified Lab Mode single-instance optimization

**Pipeline Stages**:
1. Scraper: Fetch real-time spot prices
2. Safe Filter: Historic interrupt rate < 20%
3. ML Inference: Assigned model prediction
4. Decision: Select best candidate
5. Atomic Switch: Direct instance replacement

**BYPASSED in Linear Mode**:
- Bin Packing (no waste cost calculation)
- Right Sizing (no upsizing/downsizing)
- Global risk contagion (Lab Mode only)

**Import**: `from pipelines.linear_optimizer import LinearPipeline`

---

#### run_cluster_pipeline(instance, db) - Lines 37-85
**Purpose**: Batch cluster optimization for Auto Scaling Groups

**ASG Detection** (lines 65-76):
```python
asg_name = instance.metadata.get('asg_name') if instance.metadata else None

if not asg_name:
    # Fall back to single-instance optimization
    result = cluster_pipeline.execute(target_instance_id=instance.instance_id)
else:
    # Batch optimize entire ASG
    result = cluster_pipeline.execute(asg_name=asg_name)
```

**Import**: `from pipelines.cluster_optimizer import ClusterPipeline`

---

#### run_kubernetes_pipeline(instance, db) - Lines 128-168
**Purpose**: Kubernetes-aware node optimization with graceful drain

**Cluster Validation** (lines 152-160):
```python
if not instance.cluster_membership:
    return {
        "status": "error",
        "error": "Instance is in KUBERNETES mode but has no cluster_membership data"
    }
```

**Import**: `from pipelines.kubernetes_optimizer import KubernetesPipeline`

---

**Execution Summary** (lines 260-280):
```json
{
  "instance_id": "uuid",
  "ec2_instance_id": "i-xxxxx",
  "pipeline_mode": "LINEAR",
  "execution_time_ms": 1234.56,
  "timestamp": "2025-12-25T10:30:00Z",
  "result": {...},
  "decision": "SWITCH",
  "reason": "Cost savings: $0.012/hr",
  "selected_candidate": {
    "instance_type": "c5.large",
    "availability_zone": "us-east-1b",
    "spot_price": 0.034,
    "crash_probability": 0.08
  }
}
```

**Database Tables**:
- **READ**: `instances` (fetch configuration and metadata)
- **JOIN**: `accounts` (get region, credentials)

**API Trigger Point**:
- `backend/api/lab.py` - POST /lab/instances/{id}/evaluate
- FastAPI BackgroundTasks execution

**Frontend Components**:
- `LabInstanceDetails.jsx` - "Run Evaluation" button
- `ModelExperiments.jsx` - Batch evaluation

---

## 4. event_processor.py - SPOT INTERRUPTION HANDLER (446 lines) ⭐ CRITICAL

**Purpose**: Zero-downtime safety net for AWS spot instance interruptions

**Entry Point**: `process_aws_event(event)` (line 419)

**Three Scenarios**:

### Scenario A: Rebalance Notice (2hr warning) - Lines 36-153

**AWS Event**: `EC2 Spot Instance Rebalance Recommendation`

**Complete Flow**:
```
1. AWS sends rebalance notice via EventBridge
   ↓
2. Extract: instance_id, instance_type, availability_zone
   → pool_id = "us-east-1a:c5.large"
   ↓
3. Flag global risk (line 78):
   RiskManager.register_risk_event(
       pool_id=pool_id,
       event_type='rebalance_notice'
   )
   ↓
4. Find safe alternative pool (lines 93-112):
   - Different AZ in same region
   - Check if pool is poisoned (15-day cooldown)
   - Fall back to different instance type if needed
   ↓
5. Launch replica with 6hr expiry timer (lines 114-132):
   - Create Instance record with is_replica=True
   - Set replica_of_id to primary instance_id
   - Set replica_expiry = now + 6 hours
   ↓
6. Wait for termination notice or 6hr expiry
   (40% of rebalances are false alarms - no termination)
```

**Replica Record** (lines 117-129):
```python
replica = Instance(
    instance_id=f"replica-{instance_id}-{timestamp}",
    is_replica=True,
    replica_of_id=instance_id,
    replica_expiry=datetime.utcnow() + timedelta(hours=6),
    assigned_model_version=instance.assigned_model_version,
    pipeline_mode=instance.pipeline_mode
)
```

---

### Scenario B: Termination Notice (2min warning) - Lines 155-323

**AWS Event**: `EC2 Spot Instance Interruption Warning`

**Complete Flow**:
```
1. AWS will terminate instance in ~2 minutes
   ↓
2. Flag global risk (line 198)
   ↓
3. Check for replica (lines 212-216):
   Query Instance WHERE:
     - replica_of_id = instance_id
     - is_replica = True
     - is_active = True
   ↓
4A. IF REPLICA READY (lines 218-247):
    → ZERO DOWNTIME SWITCH ✅
    - Promote replica: is_replica=False, replica_of_id=NULL
    - Mark primary: is_active=False, termination metadata
    - Return: downtime_seconds = 0

4B. IF NO REPLICA (lines 249-316):
    → EMERGENCY LAUNCH ⚠️
    - Launch new instance in safe pool
    - Calculate downtime: end - start
    - Log to DowntimeLog table with exact seconds
    - Our responsibility: SLA impact tracked
```

**Zero Downtime Switch** (lines 224-228):
```python
# Promote replica
replica.is_replica = False
replica.replica_of_id = None
replica.replica_expiry = None

downtime_seconds = 0  # Zero downtime!
```

**Emergency Launch Downtime Logging** (lines 289-303):
```python
downtime_log = DowntimeLog(
    client_id=instance.account.user_id,
    instance_id=instance_id,
    start_time=downtime_start,
    end_time=downtime_end,
    duration_seconds=downtime_seconds,
    cause='no_replica',
    cause_details='Emergency launch required, replica not ready',
    downtime_metadata={'pool_id': pool_id}
)
```

---

### Scenario C: Cleanup Job (every 1hr) - Lines 326-415

**Purpose**: Remove false alarm replicas to save costs

**Complete Flow**:
```
1. Find all replicas WHERE:
   - is_replica = True
   - replica_expiry < now
   - is_active = True
   ↓
2. For each expired replica:
   Query primary instance by replica_of_id
   ↓
3A. IF PRIMARY STILL ALIVE:
    → False alarm detected!
    - Terminate replica
    - Log: "false_rebalance_cleanup"
    - Cost saved: ~$0.30 per replica

3B. IF PRIMARY WAS TERMINATED:
    → Replica served its purpose
    - Leave as-is (already promoted)
```

**Cost Savings** (lines 385-387):
```python
# Estimate: $0.05/hr * 6hrs = $0.30 saved per replica
cost_saved += 0.30
```

**Stats** (lines 403-408):
```json
{
  "status": "success",
  "replicas_cleaned": 5,
  "cost_saved_usd": 1.50,
  "message": "Removed 5 false alarm replicas"
}
```

---

**Database Tables**:
- **READ**: `instances` (find primaries, replicas)
- **WRITE**: `instances` (create replicas, update metadata)
- **WRITE**: `global_risk_events` (flag poisoned pools)
- **WRITE**: `downtime_logs` (track emergency launch downtime)

**AWS Integration**:
- EventBridge triggers Lambda → Lambda calls process_aws_event()
- Event types: Rebalance Recommendation, Interruption Warning

**SLA Impact**:
- Zero downtime: Not logged (no SLA impact)
- Emergency launch: Logged to DowntimeLog (counts against < 60s/month target)

**Dependencies**:
- `logic.risk_manager.RiskManager` (global risk tracking)
- `utils.system_logger.SystemLogger` (event logging)

---

## Worker Execution Models

### FastAPI BackgroundTasks (Non-blocking)
**Workers**: discovery_worker, optimizer_task

**Usage**:
```python
from fastapi import BackgroundTasks
from workers.discovery_worker import run_initial_discovery

@router.post("/connect")
async def connect(background_tasks: BackgroundTasks):
    # ... validate connection ...
    background_tasks.add_task(run_initial_discovery, account.id)
    return {"status": "connected"}
```

**Characteristics**:
- Non-blocking: API returns immediately
- Runs in FastAPI's thread pool
- No retry on failure (manual retry needed)

---

### Background Thread (Daemon)
**Workers**: health_monitor

**Usage**:
```python
# In main.py on startup
from workers.health_monitor import start_health_monitor_background

monitor = start_health_monitor_background()
```

**Characteristics**:
- Continuous loop (30-second interval)
- Daemon thread: Dies when main process exits
- Auto-restarts on app restart

---

### Event-Driven (AWS EventBridge)
**Workers**: event_processor

**Usage**:
```python
# AWS Lambda handler
from workers.event_processor import process_aws_event

def lambda_handler(event, context):
    result = process_aws_event(event)
    return result
```

**Characteristics**:
- Triggered by AWS events
- Serverless execution
- Stateless (uses database for state)

---

## Error Handling Patterns

### Discovery Worker Pattern (lines 342-375):
```python
try:
    # Main worker logic
    pass
except Exception as e:
    logger.error(f"Worker failed: {e}", exc_info=True)
    db.rollback()

    # Fresh session for error logging
    error_db = SessionLocal()
    try:
        account = error_db.query(Account).filter(...).first()
        account.status = 'failed'
        account.account_metadata['last_error'] = str(e)
        error_db.commit()
    except Exception as commit_error:
        logger.error(f"Failed to update status: {commit_error}")
    finally:
        error_db.close()
finally:
    db.close()
```

---

## Recent Changes Summary

### 2025-12-25: Health Check Integration
**Files Changed**: discovery_worker.py:334-340

**Change**:
```python
# Trigger immediate health checks after discovery
try:
    from utils.component_health_checks import run_all_health_checks
    health_results = run_all_health_checks(db)
except Exception as health_error:
    logger.warning(f"Health check failed (non-critical): {health_error}")
```

**Reason**: Dashboard showed "$0 Cost" until midnight cron job
**Impact**: Dashboard now populates immediately after discovery
**Fixed**: P-2025-12-25-002

---

## Dependencies

**Requires**:
- Database connection (SessionLocal)
- AWS credentials (boto3)
- System logger
- Background task execution environment

**Required By**:
- Onboarding APIs (discovery trigger)
- Lab APIs (optimizer trigger)
- Dashboard (consumes discovered data)
- AWS EventBridge (event processing)

---

## Monitoring

### Worker Health Checks

**Discovery Worker Status**:
```sql
SELECT account_id, status, updated_at, account_metadata->>'last_scan'
FROM accounts
WHERE status IN ('connected', 'active', 'failed')
ORDER BY updated_at DESC;
```

**Health Monitor Logs**:
```sql
SELECT timestamp, log_level, message, component
FROM system_logs
WHERE component = 'health_monitor'
ORDER BY timestamp DESC LIMIT 20;
```

**Optimizer Execution Logs**:
```sql
SELECT instance_id, decision, execution_time_ms, created_at
FROM experiment_logs
ORDER BY created_at DESC LIMIT 20;
```

**Spot Interruption Events**:
```sql
SELECT pool_id, event_type, reported_at, client_id
FROM global_risk_events
WHERE event_type IN ('rebalance_notice', 'termination_notice')
ORDER BY reported_at DESC;
```

**Downtime Tracking (SLA)**:
```sql
SELECT client_id, SUM(duration_seconds) as total_downtime_seconds
FROM downtime_logs
WHERE start_time >= date_trunc('month', CURRENT_DATE)
GROUP BY client_id;
```

---

## Performance Benchmarks

- **Discovery**: 30-60 seconds for typical AWS account (100 instances)
- **Health Checks**: < 1 second per check
- **Optimizer (LINEAR)**: 2-5 seconds per instance
- **Optimizer (CLUSTER)**: 10-30 seconds per ASG
- **Event Processing**: < 500ms per event

---

_Last Updated: 2025-12-25 (Complete 4-Worker Documentation)_
_Authority: CRITICAL - Background workers are core to system functionality_
