# Replica Management System - Agent Integration Guide

**Version:** 1.0
**Last Updated:** 2025-11-20
**Status:** Ready for Integration

---

## 📋 Table of Contents

1. [Executive Summary](#executive-summary)
2. [What's Ready in Database & Backend](#whats-ready-in-database--backend)
3. [Agent Requirements](#agent-requirements)
4. [Integration Steps](#integration-steps)
5. [API Reference](#api-reference)
6. [Data Flow Diagrams](#data-flow-diagrams)
7. [Testing Checklist](#testing-checklist)
8. [Troubleshooting](#troubleshooting)

---

## 🎯 Executive Summary

The Replica Management System is **fully implemented** on the server side and ready for agent integration. This system provides:

✅ **Manual Replica Management** - User-controlled replica creation and failover
✅ **Automatic Spot Interruption Defense** - AWS interruption detection and automatic failover
✅ **Data Quality & Deduplication** - Pristine pricing data with intelligent gap-filling
✅ **Switch History with Accurate Pricing** - Historical cost tracking with confidence scores

**Current Status:**
- ✅ Database schema migrated (migration 006)
- ✅ Backend APIs implemented and tested
- ✅ Data processing pipelines ready
- ⏳ Agent integration pending (this document guides you)

---

## 🗄️ What's Ready in Database & Backend

### Database Tables (Schema Migration 006)

#### 1. **replica_instances**
Tracks all replica instances (manual and automatic).

**Key Fields:**
- `id` - Unique replica identifier
- `agent_id` - Parent agent
- `instance_id` - EC2 instance ID (or placeholder)
- `replica_type` - `manual`, `automatic-rebalance`, `automatic-termination`
- `status` - `launching`, `syncing`, `ready`, `promoted`, `terminated`, `failed`
- `sync_status` - `initializing`, `syncing`, `synced`, `out-of-sync`
- `sync_latency_ms` - Current sync latency
- `state_transfer_progress` - 0-100% completion

**Usage:** Agent queries this to find active replicas and update sync status.

#### 2. **pricing_submissions_raw**
Captures EVERY pricing submission for complete audit trail.

**Key Fields:**
- `submission_id` - Unique submission UUID
- `source_instance_id` - Which instance submitted
- `source_type` - `primary`, `replica-manual`, `replica-automatic`, `interpolated`
- `is_duplicate` - Marked by deduplication pipeline
- `spot_price`, `ondemand_price` - Pricing data

**Usage:** Agent submits ALL pricing observations here, including from replicas.

#### 3. **pricing_snapshots_clean**
Deduplicated operational data used by application.

**Key Fields:**
- `pool_id`, `time_bucket` - Unique constraint
- `spot_price` - Authoritative price for this 5-minute window
- `confidence_score` - 0.00 to 1.00 (1.00 = primary source, 0.70 = interpolated)
- `data_source` - `measured` or `interpolated`
- `interpolation_method` - Method used if interpolated

**Usage:** Read-only for agent. Used for displaying accurate historical prices.

#### 4. **pricing_snapshots_interpolated**
Transparent record of all interpolated prices.

**Key Fields:**
- `interpolation_method` - `linear`, `weighted-average`, `cross-pool`
- `confidence_score` - Quality indicator
- `price_before`, `price_after` - Boundary prices used
- `interpolated_price` - Calculated price

**Usage:** Read-only. Shows how gaps were filled.

#### 5. **spot_interruption_events**
Logs all interruption signals and handling.

**Key Fields:**
- `signal_type` - `rebalance-recommendation` or `termination-notice`
- `detected_at`, `termination_time` - Timing information
- `response_action` - What agent did
- `replica_id` - Which replica was used
- `success` - Whether failover succeeded

**Usage:** Agent logs interruption events here.

#### 6. **agents** (Enhanced)
Existing table with new columns:

**New Fields:**
- `auto_replica_enabled` - Boolean flag
- `manual_replica_enabled` - Boolean flag
- `current_replica_id` - Active replica
- `replica_count` - Number of active replicas
- `last_interruption_signal`, `last_failover_at` - Timing

**Usage:** Agent checks these flags to enable features.

#### 7. **instance_switches** (Enhanced)
Enhanced with price tracking:

**New Fields:**
- `old_instance_price`, `new_instance_price` - Prices at switch time
- `price_confidence_old`, `price_confidence_new` - Quality scores
- `price_data_source_old`, `price_data_source_new` - `measured` or `interpolated`
- `estimated_savings` - Calculated savings
- `savings_confidence` - `high`, `medium`, `low`, `unavailable`

**Usage:** Read-only. Used for switch history display.

---

### Backend API Endpoints

#### Manual Replica Management

##### 1. `POST /api/agents/<agent_id>/replicas`
**Create a manual replica.**

**Request Body:**
```json
{
  "pool_id": 123,  // optional - auto-selects cheapest if omitted
  "exclude_zones": ["us-east-1a"],  // optional
  "max_hourly_cost": 0.50,  // optional
  "created_by": "user@example.com",  // optional
  "tags": {"purpose": "testing"}  // optional
}
```

**Response (201):**
```json
{
  "success": true,
  "replica_id": "uuid-xxxx",
  "instance_id": "replica-uuid-xxxx",
  "pool": {
    "id": 123,
    "name": "us-east-1b-t3.medium",
    "instance_type": "t3.medium",
    "region": "us-east-1",
    "az": "us-east-1b"
  },
  "hourly_cost": 0.0416,
  "status": "launching",
  "message": "Replica is launching. Connect your agent to establish sync."
}
```

**Agent Action:** Use `replica_id` to establish connection and begin state sync.

---

##### 2. `GET /api/agents/<agent_id>/replicas`
**List all replicas for an agent.**

**Query Parameters:**
- `include_terminated=true` - Include terminated replicas (default: false)

**Response (200):**
```json
{
  "replicas": [
    {
      "id": "uuid-xxxx",
      "instance_id": "replica-uuid-xxxx",
      "type": "manual",
      "status": "ready",
      "sync_status": "synced",
      "sync_latency_ms": 150,
      "state_transfer_progress": 100.0,
      "pool": {
        "id": 123,
        "name": "us-east-1b-t3.medium",
        "instance_type": "t3.medium",
        "region": "us-east-1",
        "az": "us-east-1b"
      },
      "cost": {
        "hourly": 0.0416,
        "total": 1.25
      },
      "created_by": "user@example.com",
      "created_at": "2025-11-20T10:00:00Z",
      "ready_at": "2025-11-20T10:02:30Z",
      "age_seconds": 3600,
      "is_active": true
    }
  ],
  "total": 1
}
```

---

##### 3. `POST /api/agents/<agent_id>/replicas/<replica_id>/promote`
**Promote replica to primary (manual failover).**

**Request Body:**
```json
{
  "demote_old_primary": true,  // false to terminate old primary
  "wait_for_sync": true  // wait for final state sync
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Replica promoted to primary",
  "new_instance_id": "i-newinstance",
  "old_instance_id": "i-oldinstance",
  "demoted": true,
  "switch_time": "2025-11-20T10:30:00Z"
}
```

---

##### 4. `DELETE /api/agents/<agent_id>/replicas/<replica_id>`
**Gracefully terminate a replica.**

**Response (200):**
```json
{
  "success": true,
  "message": "Replica terminated",
  "replica_id": "uuid-xxxx",
  "terminated_at": "2025-11-20T10:35:00Z"
}
```

---

#### Automatic Spot Interruption Defense

##### 5. `POST /api/agents/<agent_id>/create-emergency-replica`
**Create emergency replica for spot interruption.**

**Request Body:**
```json
{
  "signal_type": "rebalance-recommendation",  // or "termination-notice"
  "termination_time": "2025-11-20T10:47:00Z",  // for termination notice
  "instance_id": "i-1234567890abcdef0",
  "pool_id": 123,  // current pool
  "preferred_zones": ["us-east-1b", "us-east-1c"],
  "exclude_zones": ["us-east-1a"],
  "urgency": "high"  // or "critical"
}
```

**Response (201):**
```json
{
  "success": true,
  "replica_id": "uuid-emergency",
  "instance_id": "emergency-uuid-xxx",
  "pool": {
    "id": 456,
    "name": "us-east-1c-t3.medium",
    "az": "us-east-1c"
  },
  "hourly_cost": 0.0420,
  "message": "Emergency replica created. Connect immediately for state sync.",
  "urgency": "high"
}
```

**Agent Action:** IMMEDIATELY connect to server as replica, establish state sync channel.

---

##### 6. `POST /api/agents/<agent_id>/termination-imminent`
**Handle 2-minute termination notice (CRITICAL).**

**Request Body:**
```json
{
  "instance_id": "i-1234567890abcdef0",
  "termination_time": "2025-11-20T10:47:00Z",
  "replica_id": "uuid-of-ready-replica"  // optional
}
```

**Response (200) - Failover Successful:**
```json
{
  "success": true,
  "message": "Automatic failover completed",
  "new_instance_id": "i-newinstance",
  "replica_id": "uuid-emergency",
  "failover_time_ms": 8543,
  "action": "replica_promoted"
}
```

**Response (500) - No Replica Available:**
```json
{
  "success": false,
  "error": "No replica available",
  "action": "emergency_snapshot_required",
  "message": "Agent should create emergency state snapshot and upload to S3"
}
```

**Agent Action:**
- If successful: Replica is now primary - disconnect old instance, connect as new primary
- If failed: Create state snapshot, upload to S3, terminate gracefully

---

##### 7. `POST /api/agents/<agent_id>/replicas/<replica_id>/sync-status`
**Update replica sync status (called periodically by agent).**

**Request Body:**
```json
{
  "sync_status": "synced",  // or "syncing", "out-of-sync"
  "sync_latency_ms": 150,
  "state_transfer_progress": 100.0,
  "status": "ready"  // optional - update overall status
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Sync status updated"
}
```

**Agent Action:** Call this every 10-30 seconds while replica is active.

---

### Data Processing Pipelines

#### Deduplication Pipeline

**Status:** ✅ Implemented and ready

**Function:** `process_pricing_submission()` in `data_quality_processor.py`

**What it does:**
1. Accepts pricing submission from ANY source (primary, replica, manual)
2. Inserts into `pricing_submissions_raw` for audit trail
3. Checks for duplicates (exact match or time-window collision)
4. Resolves conflicts using source priority: `primary > replica-automatic > replica-manual > interpolated`
5. Creates/updates `pricing_snapshots_clean` with authoritative price
6. Returns acceptance status

**Agent Integration:** Submit ALL pricing data, including from replicas. Pipeline handles deduplication automatically.

---

#### Gap Detection & Filling

**Status:** ✅ Implemented and ready

**Function:** `detect_and_fill_gaps()` in `data_quality_processor.py`

**What it does:**
1. Scans `pricing_snapshots_clean` for missing 5-minute buckets
2. Identifies gap type: `short` (5-10 min), `medium` (15-30 min), `long` (35+ min)
3. Applies appropriate interpolation strategy
4. Creates records in `pricing_snapshots_interpolated`
5. Inserts into `pricing_snapshots_clean` with `data_source='interpolated'`

**Interpolation Methods:**
- **Linear** (short gaps): Simple interpolation between boundary prices
- **Weighted Average** (medium gaps): Considers surrounding prices with decay
- **Cross-Pool** (long gaps): Uses peer pools' price movements
- **No Interpolation** (blackout >4 hours): Leaves gap empty

**Agent Integration:** Agent doesn't need to do anything. Pipeline runs automatically every 15 minutes.

---

#### ML Dataset Refresh

**Status:** ✅ Implemented and ready

**Function:** `refresh_ml_dataset()` in `data_quality_processor.py`

**What it does:**
1. Refreshes `pricing_snapshots_ml` table every 6 hours
2. Includes only high-confidence data (score >= 0.95)
3. Adds ML features:
   - `price_change_1h`, `price_change_24h`
   - `price_volatility_6h`
   - `pool_rank_by_price`
4. Used for model retraining

**Agent Integration:** Agent can use this for improved decision-making (optional).

---

## 🤖 Agent Requirements

### Configuration Flags

Add these configuration options to agent:

```python
# Replica management flags
MANUAL_REPLICA_ENABLED = False  # Allow manual replica creation
AUTO_REPLICA_ENABLED = False  # Enable automatic interruption defense
MAX_REPLICAS = 2  # Maximum concurrent replicas

# Interruption monitoring
INTERRUPTION_CHECK_INTERVAL = 5  # seconds
REBALANCE_PROBABILITY_THRESHOLD = 0.30  # 30%

# State sync
SYNC_STATUS_UPDATE_INTERVAL = 10  # seconds
STATE_TRANSFER_CHUNK_SIZE = 1024 * 1024  # 1MB
```

### Dependencies

Agent needs:
- **AWS SDK**: For interruption metadata polling (`boto3` or equivalent)
- **WebSocket Client**: For replica-to-primary communication (optional - can use HTTP polling)
- **Compression Library**: For efficient state transfer (e.g., `gzip`, `lz4`)

---

## 🔧 Integration Steps

### Step 1: Enable Replica Support in Agent

```python
# In agent initialization
def initialize_agent():
    # ... existing initialization ...

    # Check if replica features are enabled on server
    agent_config = api_client.get_agent_config(agent_id)

    if agent_config.get('manual_replica_enabled'):
        logger.info("Manual replicas enabled")
        # Enable manual replica handling

    if agent_config.get('auto_replica_enabled'):
        logger.info("Automatic replicas enabled")
        # Start interruption monitoring thread
        start_interruption_monitor()
```

---

### Step 2: Implement Interruption Monitoring

```python
import requests
import time
from threading import Thread

METADATA_BASE = "http://169.254.169.254/latest/meta-data"

def monitor_interruptions():
    """Poll AWS metadata for interruption signals"""
    while True:
        try:
            # Check rebalance recommendation
            rebalance_url = f"{METADATA_BASE}/events/recommendations/rebalance"
            response = requests.get(rebalance_url, timeout=2)

            if response.status_code == 200:
                logger.warning("REBALANCE RECOMMENDATION RECEIVED")
                handle_rebalance_recommendation()

            # Check termination notice
            termination_url = f"{METADATA_BASE}/spot/instance-action"
            response = requests.get(termination_url, timeout=2)

            if response.status_code == 200:
                termination_data = response.json()
                logger.critical(f"TERMINATION NOTICE: {termination_data}")
                handle_termination_notice(termination_data)
                break  # Stop monitoring, we're terminating

        except Exception as e:
            # 404 is expected when no signal present
            if "404" not in str(e):
                logger.error(f"Error checking interruption: {e}")

        time.sleep(5)  # Check every 5 seconds

# Start monitoring in background
Thread(target=monitor_interruptions, daemon=True).start()
```

---

### Step 3: Handle Rebalance Recommendation

```python
def handle_rebalance_recommendation():
    """Handle rebalance recommendation (10-15 min warning)"""

    # Calculate interruption probability
    instance_age_hours = calculate_instance_age()
    pool_interruption_rate = get_pool_interruption_rate(current_pool_id)

    probability = estimate_interruption_probability(
        instance_age_hours,
        pool_interruption_rate,
        time.localtime()  # time of day matters
    )

    logger.info(f"Interruption probability: {probability:.2%}")

    # Create replica if probability exceeds threshold
    if probability > REBALANCE_PROBABILITY_THRESHOLD:
        logger.warning("Creating emergency replica due to high interruption risk")

        response = api_client.post(
            f'/api/agents/{agent_id}/create-emergency-replica',
            json={
                'signal_type': 'rebalance-recommendation',
                'instance_id': instance_id,
                'pool_id': current_pool_id,
                'urgency': 'high'
            }
        )

        if response['success']:
            replica_id = response['replica_id']
            logger.info(f"Emergency replica created: {replica_id}")

            # Wait for replica to connect (it should boot and call us)
            # Or we could connect to it proactively
        else:
            logger.error(f"Failed to create replica: {response}")
```

---

### Step 4: Handle Termination Notice (CRITICAL)

```python
def handle_termination_notice(termination_data):
    """Handle 2-minute termination notice - IMMEDIATE ACTION REQUIRED"""

    termination_time = termination_data['time']
    logger.critical(f"TERMINATION AT {termination_time} - INITIATING FAILOVER")

    # Stop all non-critical operations
    stop_non_critical_operations()

    # Check if replica exists
    replicas = api_client.get(f'/api/agents/{agent_id}/replicas')
    ready_replica = next(
        (r for r in replicas['replicas'] if r['status'] == 'ready'),
        None
    )

    if ready_replica:
        # Transfer state to replica
        logger.warning(f"Transferring state to replica {ready_replica['id']}")
        transfer_state_to_replica(ready_replica['id'])

        # Notify server to promote replica
        response = api_client.post(
            f'/api/agents/{agent_id}/termination-imminent',
            json={
                'instance_id': instance_id,
                'termination_time': termination_time,
                'replica_id': ready_replica['id']
            }
        )

        if response['success']:
            logger.info(f"Failover completed in {response['failover_time_ms']}ms")
            # Flush logs and terminate
            flush_final_logs()
            sys.exit(0)
        else:
            logger.error("Failover failed! Creating emergency snapshot")
            create_emergency_snapshot()
    else:
        # No replica available - emergency snapshot
        logger.error("NO REPLICA AVAILABLE - CREATING EMERGENCY SNAPSHOT")
        create_emergency_snapshot()

        # Notify server (this will trigger new instance launch)
        api_client.post(
            f'/api/agents/{agent_id}/termination-imminent',
            json={
                'instance_id': instance_id,
                'termination_time': termination_time
            }
        )
```

---

### Step 5: State Transfer Implementation

```python
def transfer_state_to_replica(replica_id):
    """Transfer agent state to replica quickly"""
    import gzip
    import json

    # Collect critical state
    state = {
        'pricing_observations': get_recent_pricing_data(hours=1),
        'pool_metrics': get_pool_metrics(),
        'switch_history': get_recent_switches(days=1),
        'agent_config': get_current_config(),
        'timestamp': time.time()
    }

    # Compress
    state_json = json.dumps(state)
    compressed = gzip.compress(state_json.encode('utf-8'))

    logger.info(f"State size: {len(state_json)} bytes, compressed: {len(compressed)} bytes")

    # Send to server (server will forward to replica)
    response = api_client.post(
        f'/api/agents/{agent_id}/replicas/{replica_id}/state-transfer',
        data=compressed,
        headers={'Content-Encoding': 'gzip', 'Content-Type': 'application/json'}
    )

    return response['success']
```

---

### Step 6: Replica Sync Status Updates

```python
def update_replica_sync_status():
    """Update replica sync status (run periodically)"""

    if not is_replica:
        return

    # Calculate sync latency
    last_sync_time = get_last_sync_time()
    sync_latency_ms = int((time.time() - last_sync_time) * 1000)

    # Get state transfer progress
    progress = get_state_transfer_progress()  # 0-100

    # Update server
    api_client.post(
        f'/api/agents/{agent_id}/replicas/{replica_id}/sync-status',
        json={
            'sync_status': 'synced' if progress == 100 else 'syncing',
            'sync_latency_ms': sync_latency_ms,
            'state_transfer_progress': progress,
            'status': 'ready' if progress == 100 else 'syncing'
        }
    )
```

---

### Step 7: Pricing Submission with Source Type

```python
def submit_pricing_data(pool_id, spot_price, ondemand_price):
    """Submit pricing data with correct source type"""
    import uuid

    source_type = 'replica-automatic' if is_replica else 'primary'

    submission = {
        'submission_id': str(uuid.uuid4()),
        'source_instance_id': instance_id,
        'source_agent_id': agent_id,
        'source_type': source_type,
        'pool_id': pool_id,
        'instance_type': instance_type,
        'region': region,
        'az': az,
        'spot_price': float(spot_price),
        'ondemand_price': float(ondemand_price) if ondemand_price else None,
        'observed_at': datetime.now().isoformat(),
        'submitted_at': datetime.now().isoformat(),
        'client_id': client_id
    }

    # Submit to server
    # Server's deduplication pipeline will handle it
    response = api_client.post('/api/pricing/submit', json=submission)

    return response['accepted']
```

---

## 📊 Data Flow Diagrams

### Manual Replica Creation Flow

```
User (Frontend) -> Backend -> Database
        |              |
        |              v
        |        replica_instances (created)
        |              |
        v              v
Agent gets notification
        |
        v
Agent connects to replica instance
        |
        v
Agent begins state sync
        |
        v
Agent updates sync_status periodically
        |
        v
Replica status: launching -> syncing -> ready
```

---

### Automatic Interruption Handling Flow

```
AWS Spot Instance -> Interruption Signal
        |
        v
Agent monitors metadata endpoint (every 5s)
        |
        +-- Rebalance Recommendation (10-15 min warning)
        |        |
        |        v
        |   Calculate probability
        |        |
        |        v
        |   If >30%: Create emergency replica
        |        |
        |        v
        |   POST /api/agents/{id}/create-emergency-replica
        |        |
        |        v
        |   Replica boots and syncs in background
        |
        +-- Termination Notice (2 min warning)
                 |
                 v
            Stop non-critical ops
                 |
                 v
            Transfer state to replica
                 |
                 v
            POST /api/agents/{id}/termination-imminent
                 |
                 v
            Server promotes replica instantly
                 |
                 v
            Old instance terminates gracefully
```

---

### Data Quality Pipeline Flow

```
Agent submits pricing data
        |
        v
POST /api/pricing/submit (to be implemented)
        |
        v
process_pricing_submission() in data_quality_processor.py
        |
        +-> Insert into pricing_submissions_raw
        |
        +-> Check for duplicates
        |        |
        |        +-- Exact duplicate -> Mark and skip
        |        +-- Time-window collision -> Check priority
        |                |
        |                +-- Higher priority -> Replace existing
        |                +-- Lower priority -> Mark duplicate, keep existing
        |
        +-> Create/update pricing_snapshots_clean
        |
        v
Authoritative price stored

Background job (every 15 min):
        |
        v
detect_and_fill_gaps()
        |
        +-> Scan for missing 5-min buckets
        |
        +-> For each gap:
                |
                +-> Determine gap type (short/medium/long)
                |
                +-> Apply interpolation strategy
                |
                +-> Insert into pricing_snapshots_interpolated
                |
                +-> Insert into pricing_snapshots_clean (data_source='interpolated')

Background job (every 6 hours):
        |
        v
refresh_ml_dataset()
        |
        +-> Truncate pricing_snapshots_ml
        |
        +-> Insert high-confidence data (score >= 0.95)
        |
        +-> Calculate ML features
        |
        v
ML training dataset ready
```

---

## ✅ Testing Checklist

### Manual Replica Testing

- [ ] Enable `manual_replica_enabled` flag in database for test agent
- [ ] Create replica via API: `POST /api/agents/{id}/replicas`
- [ ] Verify replica record created in `replica_instances` table
- [ ] Connect agent as replica, establish state sync
- [ ] Update sync status: `POST /api/agents/{id}/replicas/{rid}/sync-status`
- [ ] Verify replica status changes: `launching -> syncing -> ready`
- [ ] Promote replica: `POST /api/agents/{id}/replicas/{rid}/promote`
- [ ] Verify new instance created and agent remapped
- [ ] Verify switch recorded in `instance_switches` table
- [ ] Delete replica: `DELETE /api/agents/{id}/replicas/{rid}`
- [ ] Verify replica marked as terminated

---

### Automatic Interruption Testing

**Note:** Requires actual AWS spot instance or mock interruption metadata.

- [ ] Enable `auto_replica_enabled` flag for test agent
- [ ] Trigger rebalance recommendation (mock metadata endpoint)
- [ ] Verify agent creates emergency replica
- [ ] Verify replica syncs in background
- [ ] Trigger termination notice (mock metadata endpoint)
- [ ] Verify agent calls `/termination-imminent` endpoint
- [ ] Verify replica promoted instantly
- [ ] Verify interruption logged in `spot_interruption_events` table
- [ ] Verify failover time < 15 seconds

---

### Data Quality Testing

- [ ] Submit pricing data from primary agent
- [ ] Submit duplicate data -> Verify marked as duplicate
- [ ] Submit data from replica -> Verify accepted with confidence 0.95
- [ ] Create data gap (stop submissions for 15 minutes)
- [ ] Run `detect_and_fill_gaps()` manually
- [ ] Verify gap filled with interpolated price
- [ ] Check `pricing_snapshots_interpolated` for transparency record
- [ ] Verify confidence score set correctly (< 1.00)
- [ ] Run `refresh_ml_dataset()` manually
- [ ] Verify ML table populated with high-confidence data only

---

### Switch History Accuracy

- [ ] Create manual switch between instances
- [ ] Verify `instance_switches` record includes prices
- [ ] Check `old_instance_price` matches actual price at switch time
- [ ] Check `price_confidence_old` and `price_data_source_old`
- [ ] If interpolated, verify confidence < 1.00
- [ ] Query switch history API (to be implemented)
- [ ] Verify UI displays prices with correct indicators

---

## 🐛 Troubleshooting

### Replica Not Syncing

**Symptom:** Replica stuck in `syncing` status, never reaches `ready`.

**Possible Causes:**
1. Agent not updating sync status
2. State transfer failed
3. Network connectivity issues

**Solution:**
```sql
-- Check replica status
SELECT * FROM replica_instances WHERE id = 'replica-id';

-- Check last sync update
SELECT last_sync_at, sync_latency_ms FROM replica_instances WHERE id = 'replica-id';

-- Manual update (testing only)
UPDATE replica_instances
SET status = 'ready', sync_status = 'synced', state_transfer_progress = 100.0
WHERE id = 'replica-id';
```

---

### Duplicate Pricing Data

**Symptom:** Multiple entries in `pricing_snapshots_clean` for same time bucket.

**Possible Causes:**
1. Deduplication pipeline not running
2. Race condition in concurrent submissions

**Solution:**
```sql
-- Find duplicates
SELECT pool_id, time_bucket, COUNT(*) as cnt
FROM pricing_snapshots_clean
GROUP BY pool_id, time_bucket
HAVING cnt > 1;

-- Run manual deduplication
-- (Python)
from data_quality_processor import deduplicate_batch
deduplicate_batch(start_time, end_time)
```

---

### Gaps Not Being Filled

**Symptom:** Gaps remain in pricing data after gap-filling job runs.

**Possible Causes:**
1. Gap too long (>4 hours - intentionally not filled)
2. No boundary prices available
3. Interpolation failed

**Solution:**
```sql
-- Check for gaps
SELECT psc.time_bucket
FROM pricing_snapshots_clean psc
RIGHT JOIN (
    -- Generate all 5-minute buckets in range
    SELECT time_bucket FROM pricing_snapshots_clean
    WHERE pool_id = 123
    AND time_bucket BETWEEN '2025-11-20 00:00:00' AND '2025-11-20 23:59:59'
) all_buckets ON psc.time_bucket = all_buckets.time_bucket
WHERE psc.time_bucket IS NULL;

-- Run manual gap filling
-- (Python)
from data_quality_processor import detect_and_fill_gaps
detect_and_fill_gaps(pool_id=123, start_time=start, end_time=end)
```

---

### Failover Failed During Termination

**Symptom:** Agent terminated without successful failover.

**Possible Causes:**
1. No replica available
2. Replica not ready in time
3. State transfer timeout

**Solution:**
```sql
-- Check interruption event
SELECT * FROM spot_interruption_events
WHERE agent_id = 'agent-id'
ORDER BY detected_at DESC
LIMIT 1;

-- If success = FALSE, check error_message
-- If no replica, check why replica creation failed

-- Check replica status at time of failover
SELECT * FROM replica_instances
WHERE agent_id = 'agent-id'
AND created_at >= (
    SELECT detected_at FROM spot_interruption_events
    WHERE agent_id = 'agent-id'
    ORDER BY detected_at DESC
    LIMIT 1
);
```

---

## 📝 Summary

**What's Ready:**
- ✅ Complete database schema (13 tables)
- ✅ 7 backend API endpoints for replica management
- ✅ Data quality processing pipeline (deduplication, gap-filling, interpolation)
- ✅ ML dataset preparation
- ✅ Switch history price tracking

**What Agent Needs to Implement:**
1. Interruption monitoring (poll AWS metadata every 5s)
2. Emergency replica creation on rebalance recommendation
3. Immediate failover on termination notice
4. State transfer to replicas
5. Periodic sync status updates
6. Pricing submissions with correct source type

**Next Steps:**
1. Review this document with development team
2. Implement agent changes according to Integration Steps
3. Test manually with checklist
4. Deploy to staging environment
5. Monitor interruption handling in production

---

**Questions?** Contact the backend team or file an issue in the repository.

**Last Updated:** 2025-11-20
**Document Version:** 1.0
**Status:** ✅ Ready for Integration
