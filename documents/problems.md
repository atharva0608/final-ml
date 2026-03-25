# Spot Optimizer Platform — Deep Codebase Problem Analysis
**Date**: 2026-03-25 (Updated: 2026-03-26)
**Scope**: auto_rebalancer.py, emergency_rebalancer.py, recovery_monitor.py, cooldown_controller.py, circuit_breaker.py, cluster.py, instance.py, agent_action.py, rebalancing_action.py, app.py, rightsizing_service.py, karpenter_routes.py, pool_ranking_service.py, tag_management_service.py, DB models, Redis patterns, Frontend components
**Categories**: Cluster Size Growth | Failure Rollback | Non-Capacity Node / UI False-Fail | Stale Data | Cycle Check with User Config | Right-Sizing | Pool Rankings | AWS API | DB Schema | Redis Patterns | Frontend

---

## CRITICAL PROBLEMS

---

### P-C1: emergency_rebalancer Creates RebalancingAction with Non-Existent Columns

**Category**: Category 2 — Failure Rollback / Orphan Instances

**File**: `backend/workers/tasks/emergency_rebalancer.py` lines 106–119

**Problem**: The `RebalancingAction` ORM object is constructed with five field names that do not exist in the model. The model (`rebalancing_action.py`) declares: `trigger` (NOT NULL), `source_pool` (NOT NULL), `target_pool` (NOT NULL). The emergency_rebalancer passes: `source_instance_type`, `action_type`, `trigger_reason` (none exist), and omits `source_pool` and `target_pool` entirely. SQLAlchemy raises `InvalidRequestError` or the DB raises `NOT NULL constraint failed` on `db.commit()`, every single time a spot interruption triggers this path.

**Dependency Chain**:
1. AWS spot interruption notice arrives via SQS or agent HTTP call
2. `emergency_rebalancer` Celery task is dispatched (queue: `emergency`)
3. Lines 106–119: `RebalancingAction(... source_instance_type=..., action_type="emergency", trigger_reason=reason ...)` is constructed — but `source_pool` and `target_pool` are NOT NULL in the schema
4. `db.add(action); db.commit()` at line 119 raises `IntegrityError` or `InvalidRequestError`
5. Exception is caught by the outer `except Exception as e` at line 175
6. `db.rollback()` is called; function returns `{"status": "error", ...}`
7. Standby failover, normal emergency flow, Karpenter terminate path — ALL skipped
8. Interrupted node is NOT cordoned, NOT drained
9. AWS terminates the EC2 at T+120s — pods forcibly evicted, NOT gracefully migrated

**Evidence**:
```python
# emergency_rebalancer.py lines 106-119 — fields don't exist in model
action = RebalancingAction(
    id=generate_uuid(),          # model PK is autoincrement Integer, not UUID
    cluster_id=cluster_id,
    source_instance_id=interrupted.instance_id,
    source_instance_type=interrupted.instance_type,  # NOT IN MODEL
    source_az=interrupted.az,                         # NOT IN MODEL
    status="in_progress",
    action_type="emergency",     # NOT IN MODEL (model has: trigger)
    trigger_reason=reason,       # NOT IN MODEL
    created_at=datetime.utcnow(), # NOT IN MODEL (model has: started_at)
    # MISSING: source_pool (NOT NULL), target_pool (NOT NULL), trigger (NOT NULL)
)
db.add(action)
db.commit()   # <-- CRASHES HERE

# rebalancing_action.py lines 23-26 — actual model
trigger = Column(String(20), nullable=False)         # 'emergency' or 'graceful'
source_pool = Column(String(100), nullable=False)    # NOT NULL
target_pool = Column(String(100), nullable=False)    # NOT NULL
```

**Effect**: Every spot interruption handled by this task fails silently. The interrupted node is never cordoned or drained before AWS forcibly terminates it. All running pods on that node are evicted ungracefully (no PDB respect, no pre-migration). The 120-second AWS grace window is wasted. Recovery falls to recovery_monitor's orphan scan (5-minute cycle) — by then the node is already gone.

---

### P-C2: Stale Action Expiry Does Not Terminate Orphan Spot Instances

**Category**: Category 1 — Cluster Size Growth

**File**: `backend/workers/tasks/auto_rebalancer.py` lines 2068–2098

**Problem**: The stale action cleanup loop marks `in_progress` and `waiting_agent` actions as `failed` after 45 minutes but never calls `_do_rollback_terminate_orphan_spot()`. If a spot EC2 was successfully launched during Phase 1 (line 982: `ec2.run_instances`) but the action subsequently got stuck (agent timeout, DB crash, Celery restart), the spot instance remains running indefinitely. The old OD node may also still be running (was never terminated). The cluster grows by one node.

**Dependency Chain**:
1. Phase 1 succeeds: spot EC2 is launched, `action.status = 'waiting_agent'`, `action.action_metadata['replacement_spot_instance_id'] = new_ec2_id`
2. Agent never acknowledges (network split, agent pod restart)
3. `waiting_agent` stuck > 45 minutes — stale expiry loop fires (line 2068)
4. `_stale.status = 'failed'`, `_stale.error_message = "..."` — action marked failed
5. NO call to `_do_rollback_terminate_orphan_spot()` — spot EC2 is NEVER terminated
6. Old OD node: still running (was never cordoned or drained yet — those happen in Phase 2)
7. `RebalancingAction.action_metadata['replacement_spot_instance_id']` contains the orphan EC2 ID but this is not read during expiry
8. Cluster now has: original OD node + orphan spot node = N+1 nodes
9. Discovery worker detects the extra node and adds it to DB — cluster appears larger than intended
10. Auto-rebalancer sees the cluster is now balanced (spot is running), may not flag it for rebalance

**Evidence**:
```python
# auto_rebalancer.py lines 2068-2098 — no orphan termination
_stale_actions = db.query(RebalancingAction).filter(
    RebalancingAction.status.in_(['in_progress', 'waiting_agent']),
    RebalancingAction.started_at < _stale_cutoff,
).all()
for _stale in _stale_actions:
    _stale.status = 'failed'
    _stale.error_message = (
        f"Action timed out after {_REBALANCING_ACTION_TIMEOUT_MIN} minutes — "
        f"marked failed by stale cleanup"
    )
    # action_metadata contains replacement_spot_instance_id — but it's NEVER read here
    # _do_rollback_terminate_orphan_spot() is NEVER called
db.commit()

# Compare: correct rollback path at line 2369 — what should happen:
_do_rollback_terminate_orphan_spot(
    db, redis, cluster, action,
    _wa_meta.get('replacement_spot_instance_id'),
    _wa_meta.get('asg_name_used'),
)
```

**Effect**: Every action that times out (agent unreachable, Celery restart mid-action) leaves a running spot EC2 that is never cleaned up. Clusters grow by 1 node per stale rebalancing cycle. Billing increases. The orphan EC2 is not tagged for recovery_monitor to find (it has `spot-optimizer:status=pending` tag from launch, but `node_joined:{iid}` Redis key may exist from a partial join — see P-M4). If node DID partially join K8s, recovery_monitor's orphan scan won't terminate it (it only terminates nodes where `node_joined` key is ABSENT). The EC2 runs until manual intervention or account cost alert.

---

### P-C3: ASG Suspend Written to action_metadata AFTER Possible Exception Point

**Category**: Category 1 — Cluster Size Growth | Category 2 — Failure Rollback

**File**: `backend/workers/tasks/auto_rebalancer.py` lines ~982–1604

**Problem**: The ASG Launch process lifecycle is: (1) suspend ASG Launch process (EC2 API call, line ~982), (2) launch spot EC2, (3) create pre-registered DB Instance record, (4) set `action.status = 'waiting_agent'`, (5) write `action.action_metadata['asg_suspended'] = True`, (6) `db.commit()`. The commit of `asg_suspended=True` metadata only happens at step 6 (when status moves to `waiting_agent`). If an exception occurs between step 1 (ASG suspend) and step 6 (commit), the exception handler at line ~1616 reads `action.action_metadata` to check `asg_suspended` — but at that point `action_metadata` in the DB still has the OLD value (before the suspend). The handler then does NOT call `ec2.resume_processes(ScalingProcesses=['Launch'])`, leaving the ASG frozen permanently.

**Dependency Chain**:
1. `execute_rebalancing_action()` enters Phase 1 (non-Karpenter direct launch path)
2. Line ~982: `ec2.suspend_processes(ScalingProcesses=['Launch'])` — ASG Launch is frozen
3. Exception fires (e.g., `ec2.run_instances` throws `InsufficientInstanceCapacity`, or DB write for pre-registration fails)
4. Exception handler runs: reads `action_metadata = action.action_metadata or {}`
5. `action_metadata.get('asg_suspended')` → returns `False` (the local dict update happened in-memory but `db.commit()` was never called)
6. Exception handler does NOT call `ec2.resume_processes()` — ASG stays suspended
7. ASG cannot launch new nodes — any scale-out event (CA, manual) is silently blocked
8. Cluster cannot grow beyond current size until operator manually resumes ASG

**Evidence**:
```python
# Approximate line 982 — ASG suspend (before exception risk zone)
ec2.suspend_processes(ScalingProcesses=['Launch'], AutoScalingGroupName=asg_name)

# Approximate line 1580-1604 — ONLY PLACE where asg_suspended is committed:
action.action_metadata = {
    **existing_metadata,
    'asg_suspended': True,
    'asg_name_used': asg_name,
    'replacement_spot_instance_id': new_instance_id,
}
action.status = 'waiting_agent'
db.commit()   # <-- asg_suspended=True reaches DB only HERE

# Exception handler (line ~1616) — reads stale metadata:
except Exception as _phase1_err:
    _meta = action.action_metadata or {}
    if _meta.get('asg_suspended'):          # False (not yet committed)
        try:
            ec2.resume_processes(...)       # NEVER CALLED
        except:
            pass
```

**Effect**: ASG Launch process remains suspended. Cluster auto-scaling is broken. Karpenter / CA scale-out events fail silently. The only recovery is manual ASG console intervention or the next time a DIFFERENT rebalancing action on the same cluster completes and explicitly resumes Launch — which may never happen if the cluster is already at target node count. Operators typically discover this hours later via "cluster not scaling" alert.

---

### P-C4: Cross-Account Emergency Stall Detection Uses Platform Credentials

**Category**: Category 2 — Failure Rollback / Orphan Instances

**File**: `backend/workers/tasks/recovery_monitor.py` (detect_karpenter_stalls function)

**Problem**: `detect_karpenter_stalls()` calls `boto3.client('ec2', region_name=region)` using the platform's own AWS credentials (NOT the assumed role of the customer account). For all cross-account clusters (which have `cluster.aws_role_arn` set), this call will target the WRONG AWS account. The `describe_instances` call either returns an empty result (instance ID not found) or raises `UnauthorizedAccess`. The `except Exception` handler at the bottom logs at DEBUG level — silently swallowing the error. Stalled Karpenter instances in customer accounts are NEVER detected or terminated by this function.

**Dependency Chain**:
1. Spot instance launched in customer account via assumed role
2. EC2 is running but Karpenter fails to provision the K8s node (stuck NodeClaim)
3. `detect_karpenter_stalls` runs every 60s (recovery_monitor beat)
4. `boto3.client('ec2', region_name=region)` — uses platform creds (no assume_role)
5. `describe_instances(InstanceIds=[...])` → `AccessDenied` (wrong account)
6. `except Exception: logger.debug(...)` — error swallowed
7. Stalled instance never terminated
8. Orphan instance continues billing in customer account
9. Cluster grows by 1 (the launch was tracked, the stall was not detected)

**Evidence**:
```python
# recovery_monitor.py — detect_karpenter_stalls (no assume_role)
ec2 = boto3.client('ec2', region_name=region)   # platform-account credentials only
response = ec2.describe_instances(InstanceIds=[instance_ids_batch])
# For cross-account clusters: AccessDenied → swallowed by except
```

**Effect**: All stall detection for cross-account clusters silently fails. The safety net that should catch "launched but node never joined" scenarios for Karpenter clusters does not work. Orphan EC2s in customer accounts run indefinitely, billed to the customer.

---

## HIGH PROBLEMS

---

### P-H1: Karpenter Non-Direct Timeout Path — OD Drained Without Confirmed Replacement

**Category**: Category 1 — Cluster Size Growth (inverse: cluster SHRINK)

**File**: `backend/workers/tasks/auto_rebalancer.py` lines ~2420–2435

**Problem**: In the Karpenter non-direct launch path (where the NodePool PATCH was issued, then the rebalancer waits for a new spot node to appear), if the timeout fires and `_other_running > 0` (there are other running nodes), the code logs a warning then PROCEEDS to drain and terminate the OD node without confirming that a spot replacement was actually provisioned. It trusts "Karpenter should provision after node removal" — but if Karpenter's NodePool is at capacity, or its webhook is unreachable, or the NodeClaim is stuck, no replacement is ever launched.

**Dependency Chain**:
1. Phase 1: NodePool PATCH issued — weight/limits adjusted to invite Karpenter to provision a spot node
2. Phase 2: `waiting_agent` loop — waits for new spot node to join with matching instance type
3. Timeout fires (default spot_join_timeout_minutes = 30 min): no new spot node detected
4. Check: `_other_running > 0` — other nodes exist, so cluster won't be empty
5. Code proceeds: CORDON_NODE + DRAIN_NODE + TERMINATE_NODE queued for the OD node
6. Agent executes DRAIN → all pods evicted from OD node
7. Agent executes TERMINATE → OD EC2 terminated
8. Karpenter never provisioned replacement (NodeClaim stuck, capacity insufficient)
9. Cluster node count: N-1 (shrunk by 1). Pods are spread to remaining nodes.
10. If remaining nodes are at capacity, pods go Pending — workload degraded

**Evidence**:
```python
# auto_rebalancer.py lines ~2427-2431 — proceeds without replacement
if _other_running > 0:
    logger.warning(
        f"[rebalancer] Spot join timeout for {cluster.name} — "
        f"other nodes running, proceeding to drain OD node "
        f"(Karpenter should provision after removal)"
    )
    # Falls through to: create CORDON_NODE, DRAIN_NODE, TERMINATE_NODE for OD node
    # No check: did a spot node actually join?
    # No check: is there at least 1 spot node for the pods to move to?
```

**Effect**: Cluster can permanently lose a node if Karpenter fails to provision. Worst case: if all remaining nodes are at CPU/memory capacity, newly scheduled pods go Pending until Karpenter eventually provisions or an operator intervenes. This is a silent cluster shrink — the DB shows the OD node as terminated and the spot node as "pending" in Karpenter, but there is no alert or rollback.

---

### P-H2: Stabilization Lock NOT Set After Phase 2 Failure

**Category**: Category 5 — Cycle Check with User Config

**File**: `backend/workers/tasks/auto_rebalancer.py` lines ~2640–2700 (CORDON/DRAIN failure paths)

**Problem**: The 60-second stabilization lock (`spot:stabilization_lock:{cluster_id}`) is only set after SUCCESSFUL completion of a rebalancing action (at line ~3242). When Phase 2 fails (CORDON fails, DRAIN times out, TERMINATE fails), the stabilization lock is NEVER set. Combined with the per-instance cooldown key being deleted on failure (see P-H3), the cluster loop can retry a new rebalancing action on the same cluster within the next 15-second Celery beat cycle — while rollback actions (UNCORDON) are still in-flight or in-queue.

**Dependency Chain**:
1. Phase 2 action fires: CORDON_NODE queued for old OD node
2. Agent fails CORDON (e.g., `kubectl cordon` returns non-zero, node not found)
3. `AgentAction.status = 'FAILED'` — detected in `waiting_agent` loop
4. Rollback initiated: `_do_rollback_uncordon_and_terminate` called
5. `spot:rebalanced:instance:{id}` deleted (cooldown key cleared)
6. NO stabilization lock set
7. Next Celery beat (15s later): cluster loop sees no stabilization lock, no per-instance cooldown
8. New rebalancing action created for SAME OD node
9. New CORDON_NODE queued — potentially while UNCORDON from rollback is still PENDING
10. Agent processes CORDON after UNCORDON — OD node cordoned again before pods fully rescheduled
11. Effectively rapid re-flapping on the same node within 15–30 seconds

**Evidence**:
```python
# auto_rebalancer.py lines ~2655-2661 — CORDON failure: no stab lock
_redis.delete(f"spot:rebalanced:instance:{_wa_instance_id}")  # cooldown DELETED
db.commit()
_do_rollback_uncordon_and_terminate(...)  # rollback started (async, agent)
# No: cooldown_controller.acquire_stabilization_lock(cluster_id)

# Compare: success path at line ~3242 (the ONLY place stab lock is set)
cooldown_controller.acquire_stabilization_lock(cluster.id, reason="rebalance_completed")
```

**Effect**: On any Phase 2 failure, the cluster enters a tight 15-second retry loop. Each retry creates new CORDON/DRAIN/TERMINATE AgentActions while rollback UNCORDON actions from the previous attempt are still queued or in-flight. The agent processes actions in order — UNCORDON from cycle N may arrive AFTER CORDON from cycle N+1, leaving the node in an unpredictable state. Circuit breaker eventually fires (after 2 rollbacks in 1h → CONSERVATIVE, 3 → HALT), but 15 rapid cycles of cordon/uncordon could disrupt pod scheduling before the breaker activates.

---

### P-H3: CORDON/DRAIN Failure Path Deletes Per-Instance Cooldown Key Before Setting Backoff

**Category**: Category 5 — Cycle Check with User Config

**File**: `backend/workers/tasks/auto_rebalancer.py` lines ~2655–2700 and ~2999–3016

**Problem**: When CORDON or DRAIN fails during Phase 2, the code explicitly DELETES the per-instance cooldown key (`spot:rebalanced:instance:{id}`) BEFORE the exponential backoff key is set. There is a window of ~1–2 Celery beats (15–30 seconds) between the delete and the backoff write where the cluster loop can see NO cooldown for this instance and attempt to create a fresh rebalancing action.

**Dependency Chain**:
1. CORDON action reports `FAILED` in the waiting_agent loop (`_wa` variable)
2. Line ~2657: `_redis.delete(f"spot:rebalanced:instance:{_wa_instance_id}")` — cooldown DELETED
3. Line ~2660: `db.commit()` — deletes the `spot:rebalanced:instance:` entry from any future reference
4. Rollback is initiated (UNCORDON + terminate orphan spot)
5. The `_wa` inner loop continues to remaining waiting actions
6. After ALL waiting actions are processed, the outer logic at lines ~2999-3016 runs:
   - `if _failed > 0`: sets exponential backoff: `_redis.setex(f"spot:rebalanced:instance:{_wa_instance_id}", backoff_seconds, "failed")`
7. Between steps 2 and 6, the next Celery beat (15s) can run the cluster loop
8. Cluster loop at line ~3592: checks `spot:rebalanced:instance:{instance.id}` — KEY IS GONE
9. Loop proceeds to create a new RebalancingAction for this same instance
10. New CORDON_NODE queued — possibly before UNCORDON from the previous failure is processed

**Evidence**:
```python
# Phase 2 CORDON failure path — delete BEFORE backoff is set
# Line ~2657:
_redis.delete(f"spot:rebalanced:instance:{_wa_instance_id}")  # key DELETED

# ... (rest of _wa loop processing, rollback dispatch) ...

# Lines ~2999-3016 — backoff set LATER (separate block after _wa loop):
if _failed > 0:
    _backoff = min(_base_backoff * (2 ** (_attempts - 1)), _max_backoff)
    _redis.setex(f"spot:rebalanced:instance:{_wa_instance_id}", _backoff, "failed")
    # Window between delete (step 2657) and this setex:
    # Any Celery fire in this window sees NO cooldown → races to create new action
```

**Effect**: Per-instance retry storm. Every CORDON/DRAIN failure creates a 15–30 second window where the instance appears "safe to rebalance again" to the next Celery beat. A new RebalancingAction is created, new AgentActions queued. If the failure is persistent (node not found, agent offline), this creates a tight burst of 2–4 actions before the backoff finally takes effect. Each burst: creates DB records, queues agent actions, calls rollback. Circuit breaker eventually catches it, but 2–4 rapid retries with concurrent CORDON/UNCORDON is disruptive.

---

### P-H4: Last-Node Guard Spot Launch — No DB Pre-Registration, No Assertion Guard

**Category**: Category 4 — Stale Data | Category 1 — Cluster Size Growth

**File**: `backend/workers/tasks/auto_rebalancer.py` lines ~3710–3766

**Problem**: The "last-node guard" code path (triggered when the cluster has only 1 node and that node has a termination notice) calls `_launch_spot_instance_direct()` to launch a replacement spot instance. However, unlike the main rebalancing path, this launch does NOT: (a) create a pre-registered `Instance` DB record, (b) set the `spot:asserted_spot:{iid}` Redis guard key, (c) create a `RebalancingAction` record for tracking. The discovery worker, running every 5 minutes, will see the new EC2 instance and classify it. Without the assertion guard, `_sync_instance_state_from_aws` (RC3) can classify the new spot instance as `ON_DEMAND` if the spot tag is not yet propagated — triggering another rebalancing action on the new node before it's even fully joined.

**Dependency Chain**:
1. Cluster has 1 running node (OD or spot), receives termination notice
2. Last-node guard fires: `_launch_spot_instance_direct()` called at line ~3740
3. New spot EC2 launched — no DB `Instance` record pre-created, no `spot:asserted_spot:` key set
4. No `RebalancingAction` created — no tracking in UI, no stale cleanup safety net
5. Discovery worker runs (every 5 min): sees new EC2, creates Instance record
6. `_sync_instance_state_from_aws` runs: checks `spot:asserted_spot:{iid}` — KEY ABSENT
7. If AWS lifecycle tag not yet propagated: instance classified as `ON_DEMAND`
8. Auto-rebalancer sees the "new OD node" and creates a rebalancing action to convert it to spot
9. But it IS already spot — rebalancing creates a spurious action that will fail when CORDON fires on a just-joined node
10. Alternatively: recovery_monitor's `scan_orphans` sees the instance with `spot-optimizer:status=pending` tag and NO `node_joined` key — if 15+ minutes pass, scan_orphans terminates the EC2 as orphan

**Evidence**:
```python
# auto_rebalancer.py lines ~3710-3766 — last-node guard launch
_new_ec2 = _launch_spot_instance_direct(...)
if _new_ec2:
    logger.info(f"Last-node guard: launched {_new_ec2} as emergency replacement")
    # No: pre-register Instance in DB
    # No: redis.setex(f"spot:asserted_spot:{_new_ec2}", 300, "1")
    # No: RebalancingAction record
    # No: node_joined key — scan_orphans will find this after 15 min

# Compare: main path at lines ~1580-1604 — correct pre-registration:
_instance_record = Instance(instance_id=new_ec2_id, lifecycle=SPOT, state='pending', ...)
db.add(_instance_record)
redis.setex(f"spot:asserted_spot:{new_ec2_id}", 300, "1")
action.action_metadata['replacement_spot_instance_id'] = new_ec2_id
action.status = 'waiting_agent'
db.commit()
```

**Effect**: Emergency last-node replacements have no tracking, no stale cleanup, no assertion guard. Depending on timing relative to discovery and recovery_monitor, the new EC2 may be: (a) reclassified as OD and re-queued for rebalancing (spurious churn), (b) terminated as orphan by scan_orphans after 15 minutes (cluster loses its last node), or (c) correctly picked up by discovery and tracked (lucky timing). Outcome is non-deterministic.

---

## MEDIUM PROBLEMS

---

### P-M1: `node_count` on Cluster Table Not Updated by sync_instance_state_from_aws

**Category**: Category 4 — Stale Data

**File**: `backend/workers/tasks/auto_rebalancer.py` (`_sync_instance_state_from_aws` function)

**Problem**: `_sync_instance_state_from_aws()` updates `cluster.spot_count` and `cluster.on_demand_node_count` but does NOT update `cluster.node_count`. The `node_count` column is only updated by the discovery worker (every 5 minutes). During active rebalancing, `node_count` can lag behind reality by up to 5 minutes, showing the pre-rebalance count. API consumers (cluster details endpoint, overview cards) read `cluster.node_count` for display — showing stale values during rebalancing windows.

**Dependency Chain**:
1. Rebalancing action completes: 1 OD terminated, 1 spot launched → net change 0
2. But during the window: 2 nodes exist (old OD + new spot) → `node_count` should be N+1
3. `_sync_instance_state_from_aws` updates `spot_count += 1` and `on_demand_node_count -= 0`
4. `cluster.node_count` stays at old value — not touched
5. API returns stale `node_count` until discovery worker runs (0–5 min lag)
6. Frontend shows wrong node count during active rebalancing

**Evidence**:
```python
# _sync_instance_state_from_aws — updates spot/od counts but NOT node_count
cluster.spot_count = _computed_spot_count
cluster.on_demand_node_count = _computed_od_count
# cluster.node_count = ??? — NEVER SET HERE
db.commit()

# cluster.py — separate column not updated here:
node_count = Column(Integer, default=0)     # updated by discovery only
spot_count = Column(Integer, default=0)     # updated by sync
on_demand_node_count = Column(Integer, default=0)  # updated by sync
```

**Effect**: UI shows inconsistent node counts during rebalancing. Frontend may show `node_count=5` while `spot_count=3, on_demand_node_count=3` (sum=6). Minor display bug, but can confuse operators checking cluster health during active migrations.

---

### P-M2: EC2 Terminate Failure Cooldown Only 90 Minutes — Allows Early Retry

**Category**: Category 2 — Failure Rollback / Orphan Instances

**File**: `backend/workers/tasks/auto_rebalancer.py` lines ~2917–2931

**Problem**: When Phase 2 `TERMINATE_NODE` action fails (agent cannot terminate the EC2), the code sets a 90-minute cooldown: `redis.set(f"spot:term_failed:{instance_id}", "1", ex=5400)`. The per-instance backoff (`spot:rebalanced:instance:{id}`) is ALSO deleted at CORDON failure time (see P-H3), meaning the same node could be re-targeted for rebalancing after 90 minutes with both the OD node AND the new spot node still running (double billing). The 90-minute cooldown is shorter than the minimum review window needed for operators to investigate terminated-EC2 failures.

**Dependency Chain**:
1. Phase 2 TERMINATE_NODE action reports FAILED
2. Code sets `spot:term_failed:{instance_id}` with 90-min (5400s) TTL
3. Spot orphan termination is attempted via `_do_rollback_terminate_orphan_spot` — may also fail
4. After 90 min: both cooldowns expire
5. Auto-rebalancer sees the OD node again (still running, state='running' in DB)
6. New rebalancing action created — attempts CORDON/DRAIN/TERMINATE again
7. Meanwhile: orphan spot instance is still running (not terminated) → cluster at N+1

**Evidence**:
```python
# auto_rebalancer.py lines ~2917-2931
except Exception as _term_err:
    _wa_meta['ec2_terminate_failed'] = True
    logger.error(f"[rebalancer] EC2 terminate failed for {_wa_instance_id}: {_term_err}")
    try:
        _redis.set(f"spot:term_failed:{_wa_instance_id}", "1", ex=5400)  # 90-min only
    except Exception:
        pass
```

**Effect**: 90-minute retry window is insufficient for operator review. After expiry, rebalancer fires again — trying to CORDON a node that AWS may have already terminated (orphan), or re-cordoning a node that had a successful CORDON but failed TERMINATE. In the latter case: node is cordoned (no new pods scheduled), DRAINED (pods evicted), but not terminated — pods are homeless. Second rebalance attempt then fires 90 min later and tries CORDON on an already-cordoned node.

---

### P-M3: RC3 Streak Key 5-Minute TTL — Redis Restart Resets SPOT→OD Downgrade Protection

**Category**: Category 4 — Stale Data

**File**: `backend/workers/tasks/auto_rebalancer.py` (`_sync_instance_state_from_aws` function, RC3 guard)

**Problem**: The RC3 guard prevents a SPOT instance from being downgraded to ON_DEMAND classification unless AWS reports it as OD for 3 consecutive 5-minute observations. The streak counter is stored in Redis as `rc3:sync_od_streak:{aws_iid}` with a 5-minute TTL. If Redis restarts (or the key is evicted under memory pressure) during the observation window, the streak resets to 0 — requiring 3 NEW consecutive observations. This is the intended safety behavior. However, the inverse is the problem: if the key expires (5-min TTL, renewed each observation), and the discovery worker runs its next cycle at T+4:59 (just before expiry), the key is refreshed. But if the Celery beat for discovery runs even 1 second late (T+5:01), the key expires and the count resets at exactly the boundary — potentially allowing an OD classification after only 1–2 observations instead of 3.

**Dependency Chain**:
1. Spot instance launches (T=0): `spot:asserted_spot:{iid}` set (TTL=300s)
2. Discovery runs at T=3 min: AWS reports as OD (billing model propagation lag is normal for first 5 min)
3. RC3 check: `rc3:sync_od_streak:{iid}` = 1 (with 5-min TTL starting T=3)
4. Discovery runs at T=8 min: streak key TTL = 5 - (8-3) = 0 min → KEY EXPIRED
5. Streak resets to 0 (not 2 as expected)
6. Next 3 observations (T=8, T=13, T=18): streak count = 1, 2, 3 → LIFECYCLE CHANGED TO OD at T=18
7. But with correct behavior it should have taken until T=13 (3 observations from T=3)
8. Net effect: OD downgrade happens at T=18 instead of T=13 — 5 minutes late, not critical

**Evidence**:
```python
# RC3 guard in _sync_instance_state_from_aws
_rc3_key = f"rc3:sync_od_streak:{aws_iid}"
_streak = int(_redis.get(_rc3_key) or 0)
_streak += 1
_redis.setex(_rc3_key, 300, str(_streak))  # 5-min TTL resets each observation
if _streak >= 3:
    # allow OD lifecycle change
    instance.lifecycle = InstanceLifecycle.ON_DEMAND
    _redis.delete(_rc3_key)
```

**Effect**: The TTL boundary race is minor (5-minute timing gap). The larger concern is Redis restart: if Redis restarts between observations 2 and 3, the streak resets, delaying OD classification by 15 minutes (3 full new observations). During that window, a spot instance that AWS has actually converted to OD billing is still shown as SPOT in the platform — savings estimates are inflated. Not a critical correctness bug but a known data quality issue.

---

### P-M4: Global Pool Rankings Cache Miss — Falls Through to Expensive DB Pipeline Every 15s

**Category**: Category 4 — Stale Data

**File**: `backend/workers/tasks/auto_rebalancer.py` (cluster loop, pool rankings fetch)

**Problem**: When `global_pool_rankings:{region}` is absent from Redis (cache cold, Redis restart, or TTL expiry between hourly rebuilds), the auto_rebalancer logs a CRITICAL warning but does NOT abort the cycle. Instead, it falls through to `PoolRankingService.rank_pools_for_size()` which performs a full DB query + scoring computation. Since the auto_rebalancer runs every 15 seconds, a cold cache triggers a full DB pipeline call every 15 seconds until the hourly cache rebuild runs. This can cause DB connection pool exhaustion and worker thread contention during Redis restarts.

**Dependency Chain**:
1. Redis restart at T=0: all keys evicted, including `global_pool_rankings:{region}`
2. Auto-rebalancer fires at T=15s (Celery beat): `_redis.get('global_pool_rankings:{region}')` → None
3. Logs CRITICAL warning: "Pool rankings cache empty — falling back to DB pipeline"
4. Calls `PoolRankingService.rank_pools_for_size()` — full DB pipeline (heavy)
5. Returns results for this cycle
6. At T=30s: same path repeated — another full DB pipeline
7. Continues every 15s until T=3600s when `build_global_pool_cache` beat task fires
8. 240 full DB pipeline calls in 1 hour — each: JOIN on spot_prices, instance_catalog, spot_advisor tables

**Evidence**:
```python
# auto_rebalancer.py — cache miss path
_rankings = _redis.get(f'global_pool_rankings:{region}')
if not _rankings:
    logger.critical(
        f"[rebalancer] Pool rankings cache empty for {region} — "
        f"falling back to DB pipeline (expensive)"
    )
    # Falls through to rank_pools_for_size() — does NOT return/continue
    _rankings = PoolRankingService(db, redis).rank_pools_for_size(...)
```

**Effect**: DB overload during Redis restarts. If the DB pool is configured for 10–20 connections and 10+ clusters each trigger full pipeline calls every 15s, connection exhaustion occurs. Workers queue on DB connection acquire → Celery task processing slows → SLA violations for emergency rebalancing tasks. The `emergency` queue (separate worker) is isolated and unaffected, but all standard queue tasks stall.

---

### P-M5: scan_orphans Pass 1 Scans Platform AWS Account — Never Finds Customer Instances

**Category**: Category 3 — Non-Capacity Node Launched but UI Shows Failed

**File**: `backend/workers/tasks/recovery_monitor.py` (scan_orphans function)

**Problem**: `scan_orphans()` has two passes: Pass 1 uses the platform's own AWS credentials (boto3 default), Pass 2 uses assumed-role credentials per cluster. Pass 1 scans the platform's own AWS account for instances tagged `spot-optimizer:status=pending`. Since ALL customer clusters are cross-account (they have `aws_role_arn`), the platform's own account never has any instances tagged this way. Pass 1 always returns 0 results and wastes a `describe_instances` API call every 5 minutes. Pass 2 correctly uses assumed role — but only processes clusters where `aws_role_arn` is set.

**Dependency Chain**:
1. Spot instance launched in customer account (cross-account, via assumed role)
2. EC2 tagged `spot-optimizer:status=pending` during launch
3. `scan_orphans` runs (every 5 min)
4. Pass 1: `boto3.client('ec2')` with platform creds → scans WRONG account → 0 results
5. Pass 2: correctly uses assumed role for each cluster → finds pending instances
6. Checks `node_joined:{iid}` Redis key — if absent AND > 15 min old → terminates
7. Pass 1 API call: wastes 1 AWS API quota unit every 5 min (minor)

**Evidence**:
```python
# recovery_monitor.py scan_orphans — Pass 1 uses wrong credentials
# Pass 1: platform account
ec2_platform = boto3.client('ec2', region_name=region)  # platform creds only
response = ec2_platform.describe_instances(
    Filters=[{'Name': 'tag:spot-optimizer:status', 'Values': ['pending']}]
)
# Result: always empty (no customer instances in platform account)

# Pass 2: correct (assumed role)
for cluster in clusters_with_role:
    creds = assume_role(cluster.aws_role_arn, ...)
    ec2_customer = boto3.client('ec2', ..., **creds)
    # This correctly scans customer account
```

**Effect**: Pass 1 is dead code for all cross-account deployments. Minor: wastes API calls. More importantly, if a single-account deployment exists (platform-hosted clusters), Pass 2 might not process them (depends on whether `aws_role_arn` is set). The orphan cleanup for single-account clusters might fall through entirely if Pass 2 only iterates `clusters WHERE aws_role_arn IS NOT NULL`.

---

### P-M6: Interval Gate at Default 15s Never Activates — No Redis Last-Check Key Written

**Category**: Category 5 — Cycle Check with User Config

**File**: `backend/workers/tasks/auto_rebalancer.py` lines ~3285–3296

**Problem**: The per-cluster interval gate (`spot:last_check:{cluster_id}`) is designed to skip a cluster if its configured `check_interval_seconds` hasn't elapsed. However, the gate condition is `if _check_interval > 15`. The default value is 15 seconds (matching the Celery beat). At the default, the condition is `15 > 15 = False` — the key is never written to Redis. The cluster loop relies entirely on Celery beat timing (external, not per-cluster). If Celery workers pile up (backpressure), multiple beats may queue — and ALL of them will run for EVERY cluster since the key-based gate never fires at default config.

**Dependency Chain**:
1. `check_interval_seconds = 15` (default for all clusters)
2. Auto-rebalancer Celery beat fires every 15s
3. Cluster loop iterates all active clusters
4. Line ~3287: `if _check_interval > 15 and redis.exists(_last_check_key)` → `15 > 15` → False
5. No skip, no key set
6. Celery backpressure: 3 pending beats in queue (heavy load period)
7. All 3 fire within 5 seconds (backpressure releases)
8. All 3 iterate all clusters — no gate key exists → all process all clusters
9. 3× RebalancingAction creation risk for clusters that are "ready to rebalance"
10. `spot:rebalanced:instance:{id}` key prevents duplicate actions for the SAME instance
11. BUT: if the per-instance key was deleted (P-H3 scenario), duplicate actions CAN be created

**Evidence**:
```python
# auto_rebalancer.py lines ~3285-3296
_check_interval = max(15, int(getattr(_opt_settings, 'check_interval_seconds', 15) or 15))
_last_check_key = f"spot:last_check:{cluster.id}"
try:
    if _redis and _check_interval > 15 and _redis.exists(_last_check_key):
        continue   # skip this cluster
except Exception:
    pass
try:
    if _redis and _check_interval > 15:     # False at default → key NEVER WRITTEN
        _redis.setex(_last_check_key, _check_interval, "1")
except Exception:
    pass
```

**Effect**: At default config, per-cluster rate limiting is entirely absent. Protection against Celery backpressure burst relies solely on `spot:rebalanced:instance:{id}` per-instance keys. If those keys are absent (P-H3 scenario, first run, Redis restart), a burst of 2–3 simultaneous beats can create 2–3 concurrent RebalancingActions for the same cluster, potentially targeting the same instances — creating duplicate CORDON/DRAIN/TERMINATE sequences in the AgentAction queue.

---

## SUMMARY TABLE

| ID | Severity | Category | File | Problem | Effect |
|----|----------|----------|------|---------|--------|
| P-C1 | CRITICAL | Cat 2 — Rollback | emergency_rebalancer.py:106–119 | RebalancingAction created with non-existent columns + missing NOT NULL fields | Every spot interruption fails silently; interrupted node never drained; pods forcibly evicted |
| P-C2 | CRITICAL | Cat 1 — Cluster Growth | auto_rebalancer.py:2068–2098 | Stale action expiry marks `waiting_agent` as failed but never terminates orphan spot EC2 | Cluster grows by 1 per timed-out action; orphan EC2 runs indefinitely; billing leak |
| P-C3 | CRITICAL | Cat 1 + Cat 2 | auto_rebalancer.py:~982–1604 | ASG `asg_suspended=True` only committed at `waiting_agent`; exception before commit → ASG stays frozen | ASG Launch permanently suspended; cluster cannot auto-scale; manual recovery required |
| P-C4 | CRITICAL | Cat 2 — Rollback | recovery_monitor.py | detect_karpenter_stalls uses platform creds for cross-account EC2 operations | Stall detection silently fails for all cross-account clusters; orphan EC2s never terminated |
| P-H1 | HIGH | Cat 1 — Cluster Shrink | auto_rebalancer.py:~2420–2435 | Karpenter timeout path drains OD node without confirmed spot replacement | Cluster shrinks by 1 if Karpenter fails to provision; pods go Pending |
| P-H2 | HIGH | Cat 5 — Cycle Check | auto_rebalancer.py:~2640–3242 | Stabilization lock NOT set after Phase 2 failure | 15-second re-flap loop on same node; CORDON/UNCORDON churn before circuit breaker fires |
| P-H3 | HIGH | Cat 5 — Cycle Check | auto_rebalancer.py:~2655–3016 | CORDON/DRAIN failure deletes per-instance cooldown key before backoff is set | 15–30 second window with no protection → duplicate RebalancingAction creation |
| P-H4 | HIGH | Cat 4 + Cat 1 | auto_rebalancer.py:~3710–3766 | Last-node guard spot launch: no DB pre-registration, no assertion guard | New EC2 classified as OD → spurious rebalance, OR terminated by scan_orphans as orphan |
| P-M1 | MEDIUM | Cat 4 — Stale Data | auto_rebalancer.py | `node_count` not updated by sync_instance_state_from_aws (discovery-only) | UI shows wrong node count during rebalancing windows (0–5 min lag) |
| P-M2 | MEDIUM | Cat 2 — Rollback | auto_rebalancer.py:~2917–2931 | EC2 terminate failure cooldown only 90 min; allows retry with cluster at N+1 | Early retry with both OD + orphan spot running; double billing; operator review window too short |
| P-M3 | MEDIUM | Cat 4 — Stale Data | auto_rebalancer.py | RC3 streak key 5-min TTL can expire at Celery beat boundary; Redis restart resets streak | OD classification delayed by up to 15 min after Redis restart; savings estimates inflated |
| P-M4 | MEDIUM | Cat 4 — Stale Data | auto_rebalancer.py | Pool rankings cache miss falls through to full DB pipeline every 15s | 240 DB pipeline calls/hour during Redis restart; DB connection pool exhaustion |
| P-M5 | MEDIUM | Cat 3 — UI False Fail | recovery_monitor.py | scan_orphans Pass 1 scans platform account — never finds customer instances | Pass 1 is dead code; minor API waste; single-account cluster orphans may not be cleaned |
| P-M6 | MEDIUM | Cat 5 — Cycle Check | auto_rebalancer.py:~3285–3296 | Interval gate `_check_interval > 15` never fires at default 15s; no `spot:last_check` key written | Celery backpressure burst → multiple concurrent beats process all clusters simultaneously |

---

## APPENDIX: Cooldown / Lock Key Reference

| Redis Key | TTL | Written By | Read By | Purpose |
|-----------|-----|-----------|---------|---------|
| `spot:stabilization_lock:{cluster_id}` | 60s | CooldownController.acquire_stabilization_lock (after success only) | auto_rebalancer cluster loop | Prevent rebalancing immediately after completed action |
| `spot:cooldown:cluster:{cluster_id}` | 60 min (default) | CooldownController.record_switch | CooldownController.can_switch | Anti-flapping cluster-level cooldown |
| `spot:rebalanced:instance:{instance_db_id}` | 5 min–1 hour (exp backoff) | auto_rebalancer Phase 1 entry | auto_rebalancer cluster loop | Per-instance dedupe guard |
| `spot:term_failed:{instance_db_id}` | 90 min (5400s) | auto_rebalancer Phase 2 term failure | auto_rebalancer cluster loop | Prevents retry after terminate EC2 failure |
| `spot:asserted_spot:{aws_instance_id}` | 300s | auto_rebalancer Phase 1 pre-register | discovery `_sync_instance_state_from_aws` | Prevents RC3 from downgrading newly-launched spot to OD |
| `spot:last_check:{cluster_id}` | check_interval_seconds | auto_rebalancer cluster loop | auto_rebalancer cluster loop | Per-cluster rate limiting (ONLY active when interval > 15s) |
| `node_joined:{aws_instance_id}` | 2h | POST /node-joined API endpoint | recovery_monitor scan_orphans | Marks that K8s kubelet joined; prevents orphan termination |
| `rc3:sync_od_streak:{aws_instance_id}` | 300s | `_sync_instance_state_from_aws` | `_sync_instance_state_from_aws` | Streak counter: require 3 consecutive OD observations before lifecycle downgrade |
| `spot:karpenter:installed:{cluster_id}` | indefinite | Karpenter detection at cluster setup | emergency_rebalancer, auto_rebalancer | Routes to Karpenter-specific code path |
| `spot:rebalance_lock:{cluster_id}` | short TTL | auto_rebalancer | auto_rebalancer | Distributed mutex (prevent concurrent actions on same cluster) |
| `cb:state:{cluster_id}` | indefinite | circuit_breaker.py | circuit_breaker.py | Circuit breaker state (NORMAL/CONSERVATIVE/HALT) |

Based on the analysis of `problems.md` against the current documentation (`logic.md`, `all-components.md`, `main-2-updated.md`), I’ve identified which issues remain unfixed, why they matter, and what additional information is required to address them.

---

## 1. Critical Problems (Still Present)

### P-C1: `emergency_rebalancer` Creates RebalancingAction with Non‑Existent Columns

**Status:** Unfixed – the documentation shows the correct model schema but does not mention any fix for the emergency rebalancer’s object construction.

**Why it’s a problem:** Every spot interruption that triggers the emergency rebalancer will fail with a database integrity error. The interrupted node is never cordoned or drained, and pods are forcibly evicted when AWS terminates the instance. This breaks the emergency handling and can lead to data loss.

**Additional info needed:** Verify the exact column mapping in the `RebalancingAction` model and update the emergency rebalancer to use the correct field names and provide the mandatory `source_pool` and `target_pool`.

---

### P-C2: Stale Action Expiry Does Not Terminate Orphan Spot Instances

**Status:** Unfixed – the stale‑action cleanup loop marks actions as failed but never reads `action_metadata` to terminate the launched spot EC2.

**Why it’s a problem:** Clusters accumulate running spot instances that were launched but never joined (orphans). The cluster size grows, incurring unnecessary cost. There is no automated cleanup.

**Additional info needed:** Determine whether the stale‑action loop should call the same rollback termination function used in the normal failure path. Also check if the orphan EC2’s tags (`spot-optimizer:status=pending`) and the absence of `node_joined` Redis key are reliable for cleanup.

---

### P-C3: ASG Suspend Written to `action_metadata` AFTER Possible Exception Point

**Status:** Unfixed – the ASG suspend operation is committed only after the risky EC2 launch and DB updates. An exception before that commit leaves the ASG Launch process suspended permanently.

**Why it’s a problem:** The ASG can no longer launch new nodes, breaking auto‑scaling. The cluster cannot grow, and manual intervention is required to resume the Launch process.

**Additional info needed:** Identify all code paths that can raise an exception after `suspend_processes` but before the metadata commit. Ensure that in every such case the ASG is resumed, even if the action is rolled back.

---

### P-C4: Cross‑Account Emergency Stall Detection Uses Platform Credentials

**Status:** Unfixed – `detect_karpenter_stalls` in `recovery_monitor.py` uses the platform’s own `boto3.client('ec2')` without assuming the customer’s role, so it cannot see EC2 instances in cross‑account clusters.

**Why it’s a problem:** Stalled Karpenter instances (nodes that were launched but never joined) are never detected or terminated. Orphan EC2s run indefinitely, causing cost leakage and potentially confusing node counts.

**Additional info needed:** The function needs to be refactored to use the same assumed‑role mechanism that `scan_orphans` uses (Pass 2). Alternatively, the entire stall detection should be moved into the per‑cluster loop with assumed credentials.

---

## 2. High Problems (Still Present)

### P-H1: Karpenter Non‑Direct Timeout Path Drains OD Node Without Confirmed Replacement

**Status:** Unfixed – when the spot node does not join within the timeout, the code proceeds to drain and terminate the old OD node if other nodes are running, trusting Karpenter to provision later.

**Why it’s a problem:** The cluster can shrink by one node if Karpenter fails to provision the replacement. Pods may become pending or unschedulable if the remaining nodes are at capacity.

**Additional info needed:** The timeout path should be changed to **not** drain the OD node unless a replacement spot node has actually joined. A rollback that leaves the OD node running and terminates the (non‑joined) spot EC2 would be safer.

---

### P-H2: Stabilization Lock NOT Set After Phase 2 Failure

**Status:** Unfixed – the stabilization lock (`spot:stabilization_lock:{cluster_id}`) is only set on success. After a failure (e.g., cordon fails), the lock is not set, allowing a new action to start almost immediately while rollback operations are still pending.

**Why it’s a problem:** This creates a tight 15‑second retry loop, causing churn with cordon/uncordon operations that can disrupt pod scheduling and lead to circuit breaker trips.

**Additional info needed:** Determine the correct place to set a stabilization lock after any failure that required a rollback. A short lock (e.g., 30 seconds) would give the cluster time to stabilise.

---

### P-H3: CORDON/DRAIN Failure Path Deletes Per‑Instance Cooldown Key Before Setting Backoff

**Status:** Unfixed – the per‑instance cooldown key (`spot:rebalanced:instance:{id}`) is deleted before the exponential backoff is written, creating a window where the instance appears eligible for immediate rebalancing.

**Why it’s a problem:** Duplicate actions can be created for the same instance within seconds, causing rapid cordon/drain attempts that may fail again and waste resources.

**Additional info needed:** The order of operations should be reversed: first set the backoff, then delete the old key (or better, just set the backoff and let it expire naturally). Also ensure that the backoff is applied consistently across all failure paths.

---

### P-H4: Last‑Node Guard Spot Launch — No DB Pre‑registration, No Assertion Guard

**Status:** Unfixed – the emergency last‑node path launches a spot EC2 but does not pre‑register it in the DB or set the `spot:asserted_spot` key.

**Why it’s a problem:** The discovery worker may later see the EC2, classify it as OD (due to missing spot label propagation), and then create a spurious rebalancing action. Worse, if the node never joins, it may be terminated by `scan_orphans` after 15 minutes, leaving the cluster empty.

**Additional info needed:** The last‑node guard should reuse the same pre‑registration and assertion logic as the main rebalancing path. This ensures proper lifecycle tracking and prevents misclassification.

---

## 3. Medium Problems (Still Present)

### P-M1: `node_count` on Cluster Table Not Updated by `sync_instance_state_from_aws`

**Status:** Unfixed – the function updates `spot_count` and `on_demand_node_count` but not `node_count`, so the UI shows stale values during active rebalancing.

**Why it’s a problem:** Minor display bug, but can confuse operators who expect the node count to reflect the current state.

**Additional info needed:** Add a line to compute `node_count = spot_count + on_demand_node_count` and update the column. Ensure the change does not conflict with the discovery worker’s later update.

---

### P-M2: EC2 Terminate Failure Cooldown Only 90 Minutes

**Status:** Unfixed – the cooldown after a failed termination is only 90 minutes, which may be too short for operator review and can lead to early retries with both old and new nodes running.

**Why it’s a problem:** If a termination fails because of a persistent AWS issue, retrying after 90 minutes is likely to fail again, and the cluster remains with an extra node. A longer cooldown (e.g., 6 hours) would reduce wasted cycles.

**Additional info needed:** Evaluate whether a longer cooldown is safe and whether a separate alert should be raised after the first failure to prompt manual investigation.

---

### P-M3: RC3 Streak Key 5‑Minute TTL — Redis Restart Resets SPOT→OD Downgrade Protection

**Status:** Unfixed – the streak counter is stored only in Redis with a 5‑minute TTL. A Redis restart resets the streak, allowing a spot instance to be downgraded to OD after only 1 or 2 observations instead of the required 3.

**Why it’s a problem:** This is a data quality issue: during the window after a Redis restart, spot instances may be incorrectly classified as OD, inflating savings estimates. The impact is temporary but could affect decision making.

**Additional info needed:** Consider whether the streak should be persisted to DB or the Redis key TTL should be extended beyond 5 minutes to survive short outages. However, this is a low‑severity issue.

---

### P-M4: Global Pool Rankings Cache Miss Falls Through to Expensive DB Pipeline Every 15s

**Status:** Unfixed – when `global_pool_rankings:{region}` is absent, the auto‑rebalancer logs a CRITICAL warning but still calls the full DB pipeline (`PoolRankingService.rank_pools_for_size()`). This happens every 15 seconds until the cache is rebuilt.

**Why it’s a problem:** During Redis downtime or after a restart, the system can overload the database with heavy queries, causing connection pool exhaustion and delaying other tasks.

**Additional info needed:** The fallback should be rate‑limited (e.g., only once per 5 minutes) or should return a cached result from the last successful computation (if available). The DB pipeline should be avoided in the 15s loop.

---

### P-M5: `scan_orphans` Pass 1 Scans Platform AWS Account — Never Finds Customer Instances

**Status:** Unfixed – the first pass of `scan_orphans` uses the platform’s own credentials, which never see customer‑account instances. It wastes an AWS API call every 5 minutes.

**Why it’s a problem:** Minor waste, but also a potential risk if the platform has its own clusters (they would be scanned, but most customers are cross‑account). The real orphan detection works in Pass 2.

**Additional info needed:** The first pass could be removed entirely, or it could be enhanced to also use assumed‑role credentials for clusters that have an `aws_role_arn`. For now, it’s a low‑priority cleanup.

---

### P-M6: Interval Gate at Default 15s Never Activates — No Redis Last‑Check Key Written

**Status:** Unfixed – the per‑cluster rate‑limiting gate (`spot:last_check:{cluster_id}`) only writes the key when `check_interval_seconds > 15`. With the default 15, the key is never written, so the gate never skips a cluster.

**Why it’s a problem:** During Celery backpressure, multiple beats can process the same cluster simultaneously, potentially creating duplicate actions (if per‑instance cooldown keys are absent). The intended rate limiting is effectively disabled.

**Additional info needed:** The condition should be changed to `>= 15` or the key should always be written, with the skip logic checking its presence. However, note that the default behaviour (no key) is what users expect when they set the interval to 15 seconds. The issue is that the gate is not working as a safeguard against burst executions when the beat schedule is delayed.

---

## Summary of Original Issues (P-C1 through P-M6)

All 14 problems listed above appear to be **still present** in the current codebase. The earlier "14 fixes" (from the previous plan) addressed a different set of issues (stabilization lock, daily limit, TTL mismatches, etc.). The problems documented above represent additional, often more serious, gaps that need attention.

---
---

# ADDITIONAL PROBLEMS — Deep Audit (2026-03-26)

**Scope**: Right-sizing pipeline, ASCP pool rankings, AWS boto3 API correctness, auto-rebalancer (new findings), frontend UI logic, DB model schema, Redis key patterns

---

## AUTO-REBALANCER — NEW FINDINGS

---

### P-C5: Pool String Split Unpacking Crash on Malformed Pool Names

**Category**: Logic Error — ValueError Crash

**File**: `backend/workers/tasks/auto_rebalancer.py` lines 885–886, 1025–1026

**Problem**: The code assumes `action.source_pool` and `action.target_pool` contain exactly one colon delimiter (`instance_type:az`). If the pool string contains multiple colons (e.g. `"m5.large:ap-south-1a:extra"`), Python's `split(':')` returns 3+ elements and the two-variable unpack raises `ValueError: too many values to unpack`.

**Evidence**:
```python
source_instance_type, source_az = action.source_pool.split(':') if ':' in action.source_pool else (action.source_pool, '')
target_instance_type, target_az = action.target_pool.split(':') if ':' in action.target_pool else (action.target_pool, '')
```

**Effect**: Entire rebalancing action crashes. The action is marked failed. The node scheduled for replacement remains on the old instance type.

---

### P-H5: Diversification Guard Ineffective When target_az Is Empty

**Category**: Logic Error — Silent Safety Bypass

**File**: `backend/workers/tasks/auto_rebalancer.py` lines 1305–1333

**Problem**: The diversification guard builds a set of occupied `(instance_type, az)` pairs, but the filter `if i.instance_type and i.az` excludes instances without AZ values. When `target_az` is `None` or `""`, the tuple `(t, target_az)` will never match any entry in the set, so the diversification check passes for ALL candidate types — it never rejects any.

**Evidence**:
```python
_occupied_exec = set(
    (i.instance_type, i.az or '')
    for i in db.query(Instance).filter(
        Instance.cluster_id == action.cluster_id,
        Instance.state.in_(['running', 'pending']),
        Instance.instance_id.like('i-%'),
    ).all()
    if i.instance_type and i.az   # ← Drops instances where az is None
)
# ...
_diversified_types = [
    t for t in _all_candidate_types
    if (t, target_az) not in _occupied_exec  # ← target_az=None/'' never matches
]
```

**Effect**: Cluster accumulates duplicate instance types in the same AZ, violating the intended pool diversification constraint.

---

### P-M7: ASG DesiredCapacity Snapshot Stale Under Concurrent Scaling

**Category**: Concurrency — Read-Modify-Write Race

**File**: `backend/workers/tasks/auto_rebalancer.py` lines 2954–2962

**Problem**: The code reads current `DesiredCapacity` via `describe_auto_scaling_groups`, then blindly sets `DesiredCapacity = max(0, current - 1)`. If Cluster Autoscaler or another process changes DesiredCapacity between the read and the write, the unconditional SET overwrites their change.

**Evidence**:
```python
_cur_desired = _asg_groups[0]['DesiredCapacity'] if _asg_groups else 1
_new_desired = max(0, _cur_desired - 1)
_asg_wa.update_auto_scaling_group(
    AutoScalingGroupName=_stored_asg_for_term,
    MinSize=_new_min,
    DesiredCapacity=_new_desired,
)
```

**Effect**: Under concurrent scaling, cluster ends up with wrong DesiredCapacity (off by 1 or more). CA-added nodes could be silently rolled back.

---

## RIGHT-SIZING PIPELINE — CRITICAL

---

### P-C6: Pod Metrics Query Missing ORDER BY — `metrics[-1]` Returns Random Row

**Category**: Query Bug — Stale/Random Data

**File**: `backend/services/rightsizing_service.py` lines 332–354

**Problem**: The query fetches all PodMetric records for a controller within a time range, but has no `order_by(PodMetric.timestamp)`. The code then accesses `metrics[-1]` as "latest metric" to get current CPU/memory requests. Without ORDER BY, the last element is whichever row the DB returns last — potentially the oldest record.

**Evidence**:
```python
metrics = self.db.query(PodMetric).filter(
    PodMetric.cluster_id == cluster_id,
    PodMetric.namespace == namespace,
    PodMetric.controller_kind == controller_kind,
    PodMetric.controller_name == controller_name,
    PodMetric.timestamp >= start_time,
    PodMetric.timestamp <= end_time
).all()   # ← NO ORDER BY!
# ...
latest_metric = metrics[-1]  # Assuming ordered by timestamp — WRONG
current_cpu_request = latest_metric.cpu_request_millicores
current_memory_request_bytes = latest_metric.memory_request_bytes
```

**Effect**: "Current" resource requests are from an arbitrary point in the time window. If a workload was recently scaled up from 500m→2000m CPU, the recommendation might base its comparison on the old 500m value, producing an incorrect downsize recommendation.

---

### P-C7: Volatility Flag Check Compares Wrong Value — Dead Code

**Category**: Logic Error — Safety Feature Disabled

**File**: `backend/services/rightsizing_service.py` lines 377–378

**Problem**: The code checks `is_volatile == b"true"`, but the volatility key is set to `"active"` by `event_monitor.py` line 289 (`self.redis.setex(volatility_key, ttl_seconds, "active")`). The comparison never matches, so the safety buffer increase (from 20% to 35%) never triggers during high-volatility regimes.

**Evidence**:
```python
# rightsizing_service.py line 377-378:
is_volatile = self.redis.get(f"spot:volatility_regime:{region}")
if is_volatile == b"true":     # ← NEVER MATCHES — key value is b"active"
    safety_buffer = max(safety_buffer, 35)

# event_monitor.py line 289:
self.redis.setex(volatility_key, ttl_seconds, "active")  # Stores "active", not "true"
```

**Effect**: During spot price volatility spikes, the right-sizing safety buffer stays at 20% instead of increasing to 35%. Recommendations are undersized, leading to potential OOMKills or CPU throttling after applying the recommendation.

---

### P-C8: Hardcoded ap-south-1 Pricing in Karpenter Routes — Wrong Costs for All Other Regions

**Category**: Data Error — Region-Locked Pricing

**File**: `backend/api/karpenter_routes.py` lines 28–55

**Problem**: The `INSTANCE_SPECS` dictionary hardcodes hourly on-demand prices for ap-south-1 region only. If the cluster is in us-east-1, eu-west-1, or any other region, all cost calculations and savings estimates are based on the wrong prices (can differ by 20-40% between regions).

**Evidence**:
```python
# ─── Instance Specs: (vcpu, memory_gb, hourly_od_ap-south-1) ─────────────────
INSTANCE_SPECS: Dict[str, tuple] = {
    "t3.nano":    (2, 0.5,  0.0058),   # ap-south-1 price
    "m5.large":   (2, 8.0,  0.096),    # ap-south-1: $0.096, us-east-1: $0.096, eu-west-1: $0.107
    "r5.large":   (2, 16.0, 0.126),    # ap-south-1: $0.126, us-east-1: $0.126, eu-west-1: $0.146
    # ...
}
```

**Effect**: Bin-packing recommendations show wrong monthly savings/cost deltas for non-ap-south-1 clusters. A "save $50/month" recommendation might actually save $30 or $70 depending on region.

---

### P-H6: Percentile Calculation Off-By-One — P95 Returns P100 (Max)

**Category**: Math Error — Oversized Recommendations

**File**: `backend/services/rightsizing_service.py` lines 507–525

**Problem**: For P95 with 20 data points: `index = int(0.95 * 20) = 19`. `sorted_values[19]` is the last element (the maximum), so P95 actually returns P100. The correct formula is `index = int((percentile / 100) * (len - 1))` → `int(0.95 * 19) = 18`.

**Evidence**:
```python
def _percentile(self, sorted_values: List[float], percentile: float) -> float:
    if not sorted_values:
        return 0
    index = int((percentile / 100) * len(sorted_values))       # ← Off by one
    index = min(index, len(sorted_values) - 1)
    return sorted_values[index]
```

**Effect**: Recommendations use the maximum observed value instead of the 95th percentile for both CPU and memory. This produces oversized recommendations, wasting resources. The safety buffer compounds on top of the already-too-high P95 value.

---

### P-H7: Null CPU/Memory Request Causes TypeError Crash

**Category**: Missing Null Check

**File**: `backend/services/rightsizing_service.py` lines 354–358

**Problem**: Schema defines `cpu_request_millicores` and `memory_request_bytes` as `Optional[int]`. The code divides `current_memory_request_bytes / (1024 * 1024)` without checking for None first. Pods without resource requests (common in dev/staging namespaces) will crash the recommendation pipeline.

**Evidence**:
```python
current_cpu_request = latest_metric.cpu_request_millicores          # Could be None
current_memory_request_bytes = latest_metric.memory_request_bytes   # Could be None
current_memory_request_mb = int(current_memory_request_bytes / (1024 * 1024))  # ← TypeError if None
```

**Effect**: TypeError crash for any controller whose pods don't have resource requests set. The entire right-sizing pipeline aborts for that controller.

---

### P-M8: Integer Truncation Loses Memory Precision — Undersized Recommendations

**Category**: Precision Loss

**File**: `backend/services/rightsizing_service.py` lines 338–340

**Problem**: Double `int()` truncation: first from float to bytes, then bytes to MB. For P95 memory of 512.9 MB (537,919,283 bytes), the result is `int(537919283 / 1048576) = 512 MB` instead of 513 MB. Combined with the P95→P100 bug, this partially compensates but for normal workloads causes systematic under-recommendation.

**Effect**: Recommended memory is consistently 1-2 MB lower than the true percentile, which may cause OOMKill for workloads running right at the recommendation boundary.

---

## ASCP POOL RANKINGS — FINDINGS

---

### P-H8: Division by Zero in Price Headroom When On-Demand Price Is Zero

**Category**: Math Error — NaN Poisoning

**File**: `backend/services/pool_ranking_service.py` lines 1193–1195

**Problem**: The code checks `pool.ondemand_price > 0` before dividing, but the fallback chain can set `ondemand_price = 0.0`: if `spot_price >= ondemand_price`, the code sets `spot_price = ondemand_price * 0.70`. If ondemand was already 0 (from missing pricing data), both prices become 0. Later code paths can still reach the division.

**Evidence**:
```python
elif pool.ondemand_price > 0:
    price_headroom = (pool.ondemand_price - pool.spot_price) / pool.ondemand_price
```

**Effect**: NaN propagates into the ML scoring pipeline. Affected pools get undefined scores and may appear at random positions in the ranking, or be silently dropped.

---

### P-H9: Spot Advisor Rank Unbounded at Line 1224 — Risk Score Exceeds 1.0

**Category**: Data Validation — ML Assumption Violation

**File**: `backend/services/pool_ranking_service.py` line 1224

**Problem**: Line 1224 divides `pool.spot_advisor_rank / 5.0` without bounds checking. The field allows values 0–5 (and potentially higher from scraper bugs). If rank=6, `sa_risk = 1.2`, and `risk_probability` exceeds the assumed [0, 1] range. Note: line 1498 has proper bounds checking (`if pool.spot_advisor_rank <= 5 else 0.5`), but line 1224 does not.

**Evidence**:
```python
# Line 1224 — NO bounds check:
sa_risk = pool.spot_advisor_rank / 5.0
risk_probability = min(1.0, 0.5 * risk_probability + 0.5 * sa_risk)

# Line 1498 — HAS bounds check:
risk_probability = pool.spot_advisor_rank / 5.0 if pool.spot_advisor_rank <= 5 else 0.5
```

**Effect**: Pools with spot_advisor_rank > 5 get inflated risk scores. The `min(1.0, ...)` clamp catches the final value but the individual `sa_risk` component is wrong, skewing the 50/50 blend.

---

### P-H10: DryRun Budget Starvation — No Backpressure Under Load

**Category**: Resource Management — Capacity Validation Failure

**File**: `backend/services/pool_ranking_service.py` lines 1314–1330

**Problem**: The DryRun budget is capped at `min(200, active_clusters * 2)` per hour. With 100 active clusters requesting rankings 5x/hour, demand = 500 but budget = 200. After ~40 requests exhaust the budget, remaining requests get `capacity_status = "unvalidated"` with no retry mechanism and no UI distinction.

**Evidence**:
```python
active_clusters = int(self.redis.get("spot:active_cluster_count") or 1)
MAX_DRYRUN_PER_HOUR = min(200, max(25, active_clusters * 2))
# ...
if remaining_budget <= 0:
    for p in scored_pools[:TARGET_VALID]:
        p.capacity_status = "unvalidated"
    return scored_pools[:TARGET_VALID]
```

**Effect**: Under load, most ranking requests return unvalidated pools. UI cannot distinguish "validated and available" from "budget exhausted, untested." Users may switch to pools that have no actual EC2 capacity.

---

### P-M9: Global Rankings Cache Race — Concurrent Pipeline Runs

**Category**: Concurrency — Duplicate Work

**File**: `backend/services/pool_ranking_service.py` lines 571–590

**Problem**: On cache miss, the code runs the full global pipeline (5–10s) then writes to Redis. Two concurrent requests that both see MISS will both run the expensive pipeline. No distributed lock protects against this.

**Evidence**:
```python
cached = self.redis.get(cache_key)
if cached:
    return [self._pool_from_dict(d) for d in json.loads(cached)]

# Cache miss — run full global pipeline (SLOW)
global_pools = self._run_global_pipeline(region, global_limit)

if global_pools:
    self.redis.setex(cache_key, GLOBAL_CACHE_TTL, json.dumps(cache_data))
```

**Effect**: Under high concurrency (10+ requests/sec on cache miss), the pipeline runs multiple times simultaneously, wasting compute and potentially causing timeouts on other requests.

---

## AWS BOTO3 API CORRECTNESS

---

### P-H11: Missing ExternalId in STS AssumeRole — Cross-Account Tagging Fails

**Category**: AWS API — Authentication Failure

**File**: `backend/services/tag_management_service.py` line 45

**Problem**: The `assume_role()` call does not pass `ExternalId` even when the account has one configured (`account.external_id`). If the cross-account role's trust policy requires ExternalId, the call fails with `AccessDenied`.

**Evidence**:
```python
assumed_role = sts.assume_role(
    RoleArn=account.role_arn,
    RoleSessionName=f"TagManagement-{service}-{account_id[:8]}"
    # ← Missing: ExternalId=account.external_id
)
```

**Effect**: Cross-account tagging operations fail for any account whose IAM role trust policy requires ExternalId. Users see cryptic STS access denied errors.

---

### P-M10: Invalid PropagateAtLaunch on ASG Tags — API Contract Violation

**Category**: AWS API — Invalid Parameter

**File**: `backend/services/spot_asg_service.py` line 270

**Problem**: `PropagateAtLaunch` is only valid for LaunchConfiguration tags (deprecated), not Auto Scaling Group tags via `create_or_update_tags`. AWS silently ignores the parameter today but this violates the API contract.

**Evidence**:
```python
asg.create_or_update_tags(Tags=[
    {"ResourceId": asg_name, "ResourceType": "auto-scaling-group",
     "Key": "spot-optimizer/managed", "Value": "true", "PropagateAtLaunch": False},
])
```

**Effect**: Currently harmless (AWS ignores the parameter), but creates technical debt. If AWS enforces parameter validation in future API versions, the call would fail.

---

## DATABASE SCHEMA ISSUES

---

### P-C9: 19 Foreign Keys Missing CASCADE Delete — Orphan Record Accumulation

**Category**: DB Schema — Data Integrity

**Files**: Multiple models — `substitute_state.py`, `billing.py`, `cluster_cooldown.py`, `optimizer_state.py`, `cluster.py`, `user.py`, `invitation.py`, `hibernation_schedule_clusters.py`, `chaos_experiment.py`, `rightsizing_proposal.py`

**Problem**: 19 foreign key columns across the codebase have no `ondelete` behavior specified. When parent records (clusters, accounts, users, organizations) are deleted, child records remain as orphans. This causes: dangling references, constraint violations when trying to re-use IDs, and unbounded table growth.

**Key examples**:
```python
# cluster.py — ClusterOptimizationSettings, ClusterCooldown, PoolCooldown, ExecutionState:
cluster_id = Column(String, ForeignKey("clusters.id"))     # No ondelete

# user.py:
organization_id = Column(String(36), ForeignKey("organizations.id"))  # No ondelete
team_id = Column(String(36), ForeignKey("teams.id"))                  # No ondelete

# hibernation_schedule_clusters.py (M2M junction):
schedule_id = Column(String(36), ForeignKey("hibernation_schedules.id"))  # No ondelete
cluster_id = Column(String(36), ForeignKey("clusters.id"))                # No ondelete
```

**Effect**: When a cluster is deleted, its cooldowns, optimization settings, execution states, substitute states, proposals, and chaos experiments all remain in the database forever. Over time this causes table bloat and query slowdowns on these tables.

---

### P-H12: Monetary Values Stored as Integer — Fractional Dollars Lost

**Category**: DB Schema — Data Precision

**File**: `backend/models/cluster.py` lines 52–53

**Problem**: `monthly_cost` and `estimated_savings` are `Column(Integer, default=0)`. Fractional dollar amounts are truncated (e.g., $123.45 stored as $123). Nearby fields `potential_savings_monthly` and `realized_savings_monthly` correctly use `Float`.

**Evidence**:
```python
monthly_cost = Column(Integer, default=0)          # ← Truncates $123.45 → $123
estimated_savings = Column(Integer, default=0)     # ← Same issue
potential_savings_monthly = Column(Float, default=0.0)  # ← Correct
realized_savings_monthly = Column(Float, default=0.0)   # ← Correct
```

**Effect**: Monthly cost reports understate actual costs. Small optimizations (< $1/month savings) are reported as $0 savings.

---

### P-H13: Missing Indexes on Frequently Queried Columns

**Category**: DB Schema — Performance

**Files**: `substitute_state.py`, `rebalancing_action.py`, `termination_event.py`

**Problem**: Several columns used in WHERE clauses lack indexes:
- `substitute_state.(cluster_id, status)` — no composite index despite `WHERE cluster_id=X AND status=Y`
- `rebalancing_action.cluster_id` — no index despite cluster-scoped queries
- `termination_event.cluster_id` — no index despite cluster-scoped queries

**Effect**: Full table scans on these tables as data grows. With thousands of rebalancing actions, queries degrade from milliseconds to seconds.

---

### P-M11: No Foreign Key Constraint on RebalancingAction.cluster_id

**Category**: DB Schema — Data Integrity

**File**: `backend/models/rebalancing_action.py` line 20

**Problem**: `cluster_id` is a plain `String(100)` column with no `ForeignKey` reference to the clusters table. Records can reference non-existent clusters, and cluster deletion doesn't cascade.

**Evidence**:
```python
cluster_id = Column(String(100), nullable=False, index=True)  # ← No FK to clusters table
```

**Effect**: Rebalancing actions accumulate for deleted clusters. No referential integrity at the DB level.

---

## REDIS KEY PATTERN ISSUES

---

### P-C10: Redis Keys Without TTL — Unbounded Memory Growth

**Category**: Redis — Memory Leak

**Files**: `backend/redis_keys.py`, `backend/services/substitute_manager.py`, `backend/services/chaos_testing_service.py`

**Problem**: Multiple Redis keys are set with `redis.set()` (no TTL) and never explicitly deleted:
- `spot:cluster_state:{cluster_id}` — cluster state blob, no TTL
- `spot:rankings_version:{region}` — ranking version, no TTL
- `spot:substitute:state:{cluster_id}` — substitute manager state, no TTL (in `substitute_manager.py` line 268)

**Evidence**:
```python
# substitute_manager.py line 268:
self.redis.set(state_key, state.value)  # ← No TTL

# chaos_testing_service.py line 349:
self.redis.set(stale_key, int(time.time()) - 3600)  # ← No TTL
```

**Effect**: Redis memory grows linearly with the number of clusters ever registered. Deleted clusters' keys remain forever. On a long-running system with cluster churn, Redis OOM crash is inevitable.

---

### P-H14: INCR + EXPIRE Race Condition — Counter Keys Can Lose TTL

**Category**: Redis — Atomicity Bug

**Files**: `backend/ml_model/decision_engine/pipeline.py` lines 495–496, `backend/services/optimizer_coordinator.py` lines 569–571

**Problem**: The pattern `redis.incr(key)` followed by `redis.expire(key, TTL)` is not atomic. If the worker crashes between the two calls, the key persists forever with no TTL. The optimizer_coordinator is worse: it only sets TTL when `count == 1`, so if the key already existed without TTL (from a crash), it never gets one.

**Evidence**:
```python
# pipeline.py:
self.redis.incr(f"spot:metrics:{metric_name}")
self.redis.expire(f"spot:metrics:{metric_name}", 86400)  # ← Crash between = key leaks

# optimizer_coordinator.py:
count = self.redis.incr(failure_key)
if count == 1:
    self.redis.expire(failure_key, 86400)  # ← Only on first incr — crash = permanent key
```

**Effect**: Leaked counter keys accumulate in Redis. Failure counts persist indefinitely, potentially causing permanent circuit-breaker trips.

---

### P-M12: Orphan Redis Keys After Cluster Deletion

**Category**: Redis — Stale Data

**Problem**: When a cluster is deleted from the database, no cleanup routine removes its Redis keys. Keys like `spot:cooldown:cluster:{id}`, `spot:node_classification:{node_id}`, `spot:substitute:state:{id}`, and `hibernation:lock:{schedule}:{id}` remain indefinitely.

**Effect**: Redis accumulates stale data proportional to cluster churn. If a cluster ID were reused (unlikely but possible), old cooldowns/locks would incorrectly affect the new cluster.

---

### P-M13: Non-Atomic State Transition in Substitute Manager

**Category**: Redis — Atomicity Bug

**File**: `backend/services/substitute_manager.py` lines 268–277

**Problem**: State and metadata are written in separate `redis.set()` calls without a pipeline/transaction. If the worker crashes between setting state and metadata, the two keys are inconsistent.

**Evidence**:
```python
self.redis.set(state_key, state.value)           # Step 1
self.redis.set(meta_key, json.dumps(metadata))   # Step 2 — crash here = inconsistent
if ttl_seconds:
    self.redis.expire(state_key, ttl_seconds)    # Step 3
    self.redis.expire(meta_key, ttl_seconds)     # Step 4
```

**Effect**: State key shows substitute is "active" but metadata key is missing/stale, causing the substitute manager to take incorrect action or crash on the next read.

---

## FRONTEND UI ISSUES

---

### P-H15: GlobalSavingsPage Uses Math.random() in Render — Chart Flickers

**Category**: UI — Data Integrity

**File**: `frontend/src/pages/GlobalSavingsPage.jsx` lines 19–21

**Problem**: Chart data uses `Math.random()` to generate supposed savings values. This produces different values on every render, causing visual flickering and making the chart useless for actual analysis.

**Evidence**:
```javascript
savings: monthTotal * (0.8 + Math.random() * 0.4),
```

**Effect**: Chart shows different data on every render. Users cannot trust the savings visualization.

---

### P-M14: Falsy Zero Check on Spot Price — Valid $0 Prices Show as "N/A"

**Category**: UI — Display Error

**Files**: `frontend/src/pages/AllInstancesPage.jsx` lines 105–108, `frontend/src/components/details/tabs/ClientInstancesTab.jsx` lines 158–162

**Problem**: Uses JavaScript's `&&` operator to check prices, which treats `0` as falsy. A spot price of `$0.00` (valid for some instance types in certain AZs) causes the savings calculation to show "N/A" instead of "100%".

**Evidence**:
```javascript
{inst.spotPrice && inst.ondemandPrice ?
  (((inst.ondemandPrice - inst.spotPrice) / inst.ondemandPrice) * 100).toFixed(1) + '%' :
  'N/A'}   // ← Shows 'N/A' when spotPrice === 0
```

**Effect**: Savings percentage incorrectly shows "N/A" for any instance where spot price is exactly $0.

---

### P-M15: ClientDetailView Has No Error State — Stuck "Loading..." Forever

**Category**: UI — Error Handling

**File**: `frontend/src/components/details/ClientDetailView.jsx` lines 16–30

**Problem**: No error state exists. If `getClientDetails()` API call fails, the component remains in `loading=true` state forever with no retry option.

**Evidence**:
```javascript
const [client, setClient] = useState(null);
const [loading, setLoading] = useState(true);
// ← No error state

// JSX:
<h2>{loading ? 'Loading...' : client?.name}</h2>  // ← Stuck forever on error
```

**Effect**: After a network error, the page is permanently stuck on "Loading..." with no way for the user to retry or understand what happened.

---

### P-M16: Array Mutation in AdminOverview Client Sorting

**Category**: UI — React Anti-Pattern

**File**: `frontend/src/pages/AdminOverview.jsx` lines 89–91

**Problem**: `.sort()` mutates the original `clients` array in place. In React, this violates the immutability principle and can cause missed re-renders or stale data.

**Evidence**:
```javascript
const topClients = clients
  .sort((a, b) => b.totalSavings - a.totalSavings)  // ← Mutates original array
  .slice(0, 5);
```

**Effect**: Potential rendering bugs where the component doesn't detect state changes because the array reference hasn't changed despite its contents being reordered.

---

## UPDATED SUMMARY

| Category | Count | IDs |
|----------|-------|-----|
| **CRITICAL** | 10 | P-C1 through P-C4 (original), P-C5 (pool split crash), P-C6 (missing ORDER BY), P-C7 (volatility dead code), P-C8 (hardcoded pricing), P-C9 (missing CASCADE), P-C10 (Redis no TTL) |
| **HIGH** | 15 | P-H1 through P-H4 (original), P-H5 (diversification bypass), P-H6 (percentile off-by-one), P-H7 (null TypeError), P-H8 (division by zero), P-H9 (unbounded risk), P-H10 (DryRun starvation), P-H11 (missing ExternalId), P-H12 (Integer monetary), P-H13 (missing indexes), P-H14 (INCR/EXPIRE race), P-H15 (chart random) |
| **MEDIUM** | 16 | P-M1 through P-M6 (original), P-M7 (ASG race), P-M8 (truncation), P-M9 (cache race), P-M10 (PropagateAtLaunch), P-M11 (no FK on rebalancing), P-M12 (orphan Redis), P-M13 (non-atomic state), P-M14 (falsy zero), P-M15 (stuck loading), P-M16 (array mutation) |
| **TOTAL** | **41** | |

For each problem, I’ve indicated why it matters and what additional information is required to fix it. The next step would be to examine the actual source files to confirm the exact code locations and to design the fixes accordingly.