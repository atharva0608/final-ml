# Manual Replica Mode - Complete Behavior Guide

## Overview

Manual replica mode maintains **exactly 1 replica instance** at all times while the toggle is enabled, ensuring:
- **Total instances**: 1 primary + 1 replica = **2 instances maximum**
- **Continuous availability**: If either instance terminates, a replacement is created automatically
- **User control**: You decide when to switch, not the ML model

---

## Instance Count Rules

### ✅ Normal State (Manual Replica Enabled)
```
Primary Instance (1)  +  Replica Instance (1)  =  2 Total Instances
     ↓                         ↓
   Active                   Standby
   (Running workload)       (Syncing state)
```

### 🔄 After Primary Terminates
```
Primary Dies (0)  →  Replica Promoted (1)  →  New Replica Created (1)  =  2 Total
     ↓                      ↓                         ↓
   Terminated            Becomes Primary          New Standby Created
                        (Runs workload)           (Syncs from new primary)
```

### 🔄 After Replica Terminates
```
Primary (1)  +  Replica Dies (0)  →  New Replica Created (1)  =  2 Total
     ↓                ↓                       ↓
   Active         Terminated            New Standby Created
  (Continues)                          (Syncs from primary)
```

### 🔄 After User Switches to Replica
```
Old Primary (1)  +  Replica (1)
     ↓                  ↓
User clicks "Switch to Replica"
     ↓                  ↓
Replica Promoted   →   New Replica Created  =  2 Total
     ↓                       ↓
Becomes Primary       Standby for new primary
(Runs workload)       (Syncs state)

Old Primary:
- If auto_terminate_enabled = TRUE: Terminated after wait period
- If auto_terminate_enabled = FALSE: Kept alive (user must terminate manually)
```

---

## ReplicaCoordinator Behavior

The `ReplicaCoordinator` background job (runs every 10 seconds) ensures this behavior:

### 1. On Startup / Toggle Enabled
```python
# Check: Does agent have manual_replica_enabled = TRUE?
#   AND  Does agent have 0 active replicas?
# Action: Create 1 replica
```

### 2. Continuous Monitoring (Every 10 seconds)
```python
# Count active replicas for this agent
active_count = COUNT(replica_instances WHERE agent_id = X AND is_active = TRUE)

if active_count == 0:
    # No replica exists - create one
    create_manual_replica(agent)

elif active_count == 1:
    # Perfect state - do nothing
    pass

elif active_count > 1:
    # Too many replicas - keep newest, terminate others
    keep_newest_replica()
    terminate_other_replicas()
```

### 3. After Promotion Detection
```python
# Check: Was a replica promoted in the last 5 minutes?
recently_promoted = replica WHERE status='promoted' AND promoted_at >= NOW() - 5 MIN

if recently_promoted:
    # User just switched - create new replica for new primary
    wait(2 seconds)  # Let promotion complete
    create_manual_replica(new_primary)
```

---

## Lifecycle Examples

### Example 1: Enable Manual Replica Toggle

**Timeline:**
```
T+0s:  User enables manual_replica_enabled toggle
       → Frontend: POST /api/client/agents/<id>/config {"manualReplicaEnabled": true}
       → Backend: UPDATE agents SET manual_replica_enabled = TRUE, auto_switch_enabled = FALSE

T+10s: ReplicaCoordinator detects manual_replica_enabled = TRUE
       → Checks: active_count = 0
       → Creates replica in cheapest available pool
       → INSERT INTO replica_instances (status='launching')

T+30s: Replica instance launches in AWS
       → Agent: POST /api/agents/<id>/replicas/<replica_id> {"instance_id": "i-xyz", "status": "syncing"}
       → Backend: UPDATE replica_instances SET instance_id='i-xyz', status='syncing', launched_at=NOW()

T+2m:  Replica finishes state sync
       → Agent: POST /api/agents/<id>/replicas/<replica_id>/status {"status": "ready"}
       → Backend: UPDATE replica_instances SET status='ready', ready_at=NOW()

Result: 2 instances running (1 primary + 1 replica)
```

### Example 2: Primary Instance Gets Interrupted

**Timeline:**
```
T+0s:  AWS sends spot termination notice to primary instance
       → Agent detects: 2-minute warning

T+5s:  Agent promotes replica immediately
       → Agent: POST /api/agents/<id>/replicas/<replica_id>/promote
       → Backend:
           1. UPDATE replica_instances SET status='promoted', promoted_at=NOW()
           2. UPDATE agents SET instance_id=<replica_instance_id>, current_pool_id=<replica_pool>
           3. Replica becomes new primary

T+15s: ReplicaCoordinator detects promotion (promoted_at within 5 minutes)
       → Checks: Replica was promoted
       → Creates NEW replica for the NEW primary
       → New replica starts launching

T+2m:  Old primary terminates (AWS terminates it)
       New replica finishes launching and syncing

Result: 2 instances again (new primary + new replica)
```

### Example 3: Replica Instance Gets Interrupted

**Timeline:**
```
T+0s:  AWS terminates replica instance (spot interruption)
       → Replica dies

T+10s: ReplicaCoordinator runs periodic check
       → Checks: active_count = 0 (replica is gone)
       → Creates new replica immediately
       → New replica starts launching

T+2m:  New replica finishes launching and syncing

Result: 2 instances (primary + new replica)
       Primary was never affected - no downtime!
```

### Example 4: User Manually Switches to Replica

**Timeline:**
```
T+0s:  User clicks "Switch to Replica" button in UI
       → Frontend: POST /api/agents/<id>/replicas/<replica_id>/promote
       → Backend:
           1. UPDATE replica_instances SET status='promoted', promoted_at=NOW()
           2. UPDATE agents SET instance_id=<replica_id>
           3. Replica becomes new primary

T+10s: ReplicaCoordinator detects recent promotion
       → Checks: promoted_at within last 5 minutes
       → Waits 2 seconds (let promotion complete)
       → Creates NEW replica for NEW primary

T+2m:  New replica finishes launching

       Old primary handling depends on auto_terminate_enabled:
       - If TRUE: Backend waits terminate_wait_seconds, then terminates
       - If FALSE: Old primary stays alive (user must terminate manually)

Result: Either 2 instances (if auto_terminate=TRUE) or 3 instances temporarily (if FALSE)
```

### Example 5: Disable Manual Replica Toggle

**Timeline:**
```
T+0s:  User disables manual_replica_enabled toggle
       → Frontend: POST /api/client/agents/<id>/config {"manualReplicaEnabled": false}
       → Backend:
           1. UPDATE agents SET manual_replica_enabled = FALSE
           2. UPDATE replica_instances SET is_active=FALSE, status='terminated', terminated_at=NOW()
              WHERE agent_id = <id> AND is_active = TRUE
           3. Terminates all replicas

T+1m:  Replica instances shut down

Result: 1 instance (primary only)
```

---

## API Enforcement

### Manual Replica Creation Endpoint
```
POST /api/agents/<agent_id>/replicas
```

**Validation:**
```python
# 1. Check manual_replica_enabled
if not agent['manual_replica_enabled']:
    return 400 "Manual replicas not enabled for this agent"

# 2. Check replica count - ENFORCES EXACTLY 1 REPLICA
if agent['replica_count'] >= 1:
    return 400 {
        'error': 'Replica already exists for this agent',
        'current_count': 1,
        'max_allowed': 1,
        'note': 'Manual replica mode maintains exactly 1 replica. Delete existing replica first.'
    }

# 3. Create replica
```

This prevents users from manually creating more than 1 replica via API.

---

## Cost Implications

### Manual Replica Mode Costs
```
Cost = (Primary instance cost) + (Replica instance cost)

Example:
- Primary: t3.medium spot @ $0.0104/hour
- Replica: t3.medium spot @ $0.0098/hour (cheapest pool)
- Total: $0.0202/hour ≈ $14.54/month

vs. On-Demand:
- t3.medium on-demand @ $0.0416/hour
- Total: $0.0416/hour ≈ $29.95/month

Savings: $15.41/month (51.4% cheaper than on-demand)
       BUT: 2x more expensive than single spot instance
```

### Auto-Switch Mode Costs (Emergency Replicas Only)
```
Normal State: 1 instance only
Emergency State (rare): 2 instances temporarily

Example:
- 99% of month: 1 instance @ $0.0104/hour = $7.49/month
- 1% of month: 2 instances @ $0.0202/hour = $0.15/month
- Total: ~$7.64/month

vs. Manual Replica:
- 100% of month: 2 instances @ $0.0202/hour = $14.54/month

Savings: Manual costs ~2x more than auto-switch
```

**Choose based on requirements:**
- **Manual Replica**: Zero-downtime failover, instant switches, user control → Higher cost
- **Auto-Switch**: Cost optimization, ML-driven switches, emergency-only replicas → Lower cost

---

## Troubleshooting

### Issue: "I see 3 instances instead of 2"

**Cause:** Old primary not terminated after promotion

**Solution:**
```bash
# Check auto_terminate_enabled
curl http://backend/api/client/<client_id>/agents | jq '.[0].autoTerminateEnabled'

# If false, old instances are kept alive
# Enable auto-terminate:
POST /api/client/agents/<id>/config
{
  "autoTerminateEnabled": true,
  "terminateWaitMinutes": 30
}
```

### Issue: "Replica keeps getting recreated"

**Cause:** This is normal behavior

**Explanation:**
```
Manual replica mode CONTINUOUSLY maintains 1 replica.
If replica terminates for any reason, a new one is created within 10 seconds.
This is intentional - ensures continuous failover readiness.
```

### Issue: "I only see 1 instance (no replica)"

**Possible Causes:**
1. **Manual replica toggle is OFF**
   ```bash
   # Check status
   curl http://backend/api/client/<client_id>/agents | jq '.[0].manualReplicaEnabled'
   # Should be: true
   ```

2. **Replica creation failed**
   ```bash
   # Check backend logs
   grep "Manual mode: Creating replica" /var/log/backend.log
   grep "ERROR.*replica" /var/log/backend.log
   ```

3. **ReplicaCoordinator not running**
   ```bash
   # Check coordinator status
   grep "ReplicaCoordinator started" /var/log/backend.log
   # Should see: "ReplicaCoordinator started successfully"
   ```

### Issue: "Multiple replicas exist (more than 1)"

**This should auto-resolve within 10 seconds**

**How ReplicaCoordinator handles this:**
```python
# Every 10 seconds:
if active_count > 1:
    # Keep newest replica
    newest_replica = active_replicas[0]

    # Terminate all others
    for replica in active_replicas[1:]:
        UPDATE replica_instances
        SET is_active=FALSE, status='terminated', terminated_at=NOW()
        WHERE id = replica_id
```

**Manual fix (if needed):**
```bash
# List all replicas
curl http://backend/api/agents/<agent_id>/replicas

# Delete extra replicas
curl -X DELETE http://backend/api/agents/<agent_id>/replicas/<replica_id>
```

---

## Summary

| Aspect | Behavior |
|--------|----------|
| **Target replica count** | Exactly 1 |
| **Total instances** | 2 (1 primary + 1 replica) |
| **If primary dies** | Replica promoted → New replica created |
| **If replica dies** | New replica created immediately |
| **After user switches** | New replica created for new primary |
| **Toggle disabled** | All replicas terminated → Back to 1 instance |
| **Enforcement** | ReplicaCoordinator (every 10s) + API validation |
| **Cost** | ~2x single instance, but ~50% cheaper than on-demand |

---

**Last Updated:** November 23, 2025
**Related Docs:**
- `docs/REPLICA_MODES_EXPLAINED.md` - Auto-Switch vs Manual comparison
- `docs/SESSION_FIXES_2025-11-23.md` - Implementation fixes
- `docs/DATABASE_SCHEMA.md` - replica_instances table schema
