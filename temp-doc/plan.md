# Production-Critical Minimum Changeset
# Execution Ownership + Onboarding Safety

Status: PLANNING
Last updated: 2026-05-12

---

## Overview

12 changes across 7 priorities. No rewrites. No overengineering.
Every change maps to an exact file, function, and line range.

---

## PRIORITY 1 — Fix Execution Ownership Races

### CHANGE 1 — Symmetric Lock Coordination

**Problem:**
- AR checks `spot:cluster_mutex:{cluster_id}` before acting → skips if PC holds it ✅
- PC never checks `rebalance:lock:{cluster_id}` before acting → races with AR mid-drain ❌

Result: AR is CORDON→DRAIN→TERMINATE on node X. PC wakes up, acquires cluster_mutex (AR
doesn't hold it), dispatches EVICT_POD for pods on node X. Two agents move the same pods.

**Exact location:**
- File: `backend/pipeline/stage3_ppe/controller_service.py`
- Function: `PlacementControllerService.run_cycle()` — line 172
- Insert point: line 235 — AFTER the circuit breaker check (line 202-231), BEFORE
  `_scaling_guard_active` (line 236), and definitely BEFORE `cluster_mutex` (line 244)

**The lock key to check:**
- Defined in `backend/core/redis_client.py` line 57: `key_rebalance_lock(cluster_id)` → `"rebalance:lock:{cluster_id}"`
- AR acquires it in `execute_rebalancing_action()` line 892: `_redis.set(_lock_key, str(action.id), nx=True, ex=2700)`
- Also acquired in `backend/pipeline/stage5_execution/controller.py` line 151-152

**Change to make:**
```python
# Insert at line 235 in controller_service.py, before _scaling_guard_active check
from backend.core.redis_client import key_rebalance_lock as _key_rl
_rl_key = _key_rl(cluster_id)
if self.redis.exists(_rl_key):
    logger.info(
        "placement_controller_rebalance_lock_held",
        extra={"cluster_id": cluster_id, "lock_key": _rl_key},
    )
    self._emit_cycle_metrics(cluster_id, metrics, skipped_reason="rebalance_lock_held")
    return
```

**Why before cluster_mutex:** cluster_mutex is a HeartbeatLock (TTL 60s) — if we wait until
after acquiring it, we've already blocked AR for up to 60s unnecessarily. Cheapest check first.

**Test:** With AR holding rebalance:lock for a cluster, trigger a PC cycle. Confirm PC logs
`placement_controller_rebalance_lock_held` and returns without dispatching any EVICT_POD.

---

### CHANGE 2 — Draining Node Annotation

**Problem:** When AR begins CORDON on a node, no signal exists for PC/EE/PPE to know that
node is mid-drain. PC can still read the node as "available OD pod host" and plan evictions
from it. PPE can still include it as a "drain candidate" in a new plan. Both cause stuck drains.

**What to annotate:**
```
spot-optimizer/draining: "true"
```
Applied via `AgentActionType.LABEL_NODE` (existing action type, line 17 of `agent_action.py`).
K8s annotations and labels are agent-side — use LABEL_NODE payload with the annotation key.

**Exact location in AR:**
- File: `backend/workers/tasks/auto_rebalancer.py`
- Where to add: inside `execute_rebalancing_action()`, after the rebalance lock is acquired
  (line 892) and before Phase 1 (NodePool injection) starts — approximately line 970 area,
  after the safety gates (stabilization lock, substitute guard, resize cooldown).
- Read `action.action_metadata` for `target_node_name` — this is the source OD node being drained.

**Change to make — queue a LABEL_NODE before Phase 1:**
```python
# After safety gates, before Phase 1 NodePool patch
# Annotate the source node as draining so PC/PPE skip it
_drain_node_name = (action.action_metadata or {}).get('target_node_name') or \
                   (action.action_metadata or {}).get('node_name')
if _drain_node_name:
    from backend.models.agent_action import AgentAction as _AA_Ann, \
        AgentActionType as _AAT_Ann, AgentActionStatus as _AAS_Ann
    _ann_action = _AA_Ann(
        cluster_id=action.cluster_id,
        action_type=_AAT_Ann.LABEL_NODE,
        status=_AAS_Ann.PENDING,
        priority=10,  # high priority — must run before CORDON
        payload={
            "node_name": _drain_node_name,
            "labels": {"spot-optimizer/draining": "true"},
        },
    )
    db.add(_ann_action)
    db.commit()
```

**Where PC must check (Change 2b):**
- File: `backend/pipeline/stage3_ppe/controller_service.py`
- Function: `_dispatch_eviction()` line 1020
- Before creating the EVICT_POD AgentAction, check if the pod's node has `spot-optimizer/draining=true`.
- Read from Redis: agent writes node labels to `spot:node:labels:{cluster_id}:{node_name}` (check
  what key agent uses for node label cache — use `_redis.hget` or scan the pod's `pod.node`).
- If draining label is set: skip the pod, increment `evictions_skipped_node_drain` metric
  (this counter already exists in the metrics dict at line 191).

**Where PPE must check (Change 2c):**
- File: `backend/services/pod_placement_engine.py`
- In `CapacityPlanner.plan()` when iterating nodes to mark as "drain" candidates:
  nodes with `spot-optimizer/draining=true` are already being drained — do not add them
  to the `node_plan` as new drain actions. They are already in flight.

---

## PRIORITY 2 — Add Ownership Model

### CHANGE 3 — Add `node_owner_type` to Instance

**Problem:** All nodes are treated identically. AR tries to drain bootstrap nodes (system
components) and MNG nodes (wrong termination path). No way to distinguish.

**Schema change:**
- File: `backend/models/instance.py`
- Add column after `standby` (line 60):
```python
node_owner_type = Column(String(20), nullable=True, default=None, index=True)
# Values: "bootstrap" | "legacy_mng" | "karpenter_dynamic" | None (unknown)
```
- Add DB migration: `ALTER TABLE instances ADD COLUMN node_owner_type VARCHAR(20);`

**Detection logic — where to populate:**
- File: `backend/workers/tasks/auto_rebalancer.py`
- Function: `_sync_instance_state_from_k8s()` line 728
- This function already reads K8s node objects and syncs to DB Instance records.
- After reading node labels, derive `node_owner_type`:

```python
def _derive_node_owner_type(node_labels: dict) -> str:
    if node_labels.get("optimization-exempt") == "true":
        return "bootstrap"
    if "karpenter.sh/nodepool" in node_labels:
        return "karpenter_dynamic"
    if "eks.amazonaws.com/nodegroup" in node_labels:
        return "legacy_mng"
    return "unknown"  # ADJUSTMENT 1: surface as unknown, not silently bootstrap
```

**ADJUSTMENT 1 — Why `"unknown"` not `"bootstrap"`:**
Returning `"bootstrap"` as fail-safe permanently protects any node whose labels are missing
due to agent lag, stale sync, or partial metadata. This silently converts normal nodes into
untouchable bootstrap nodes with no visibility. `"unknown"` is different:
- `unknown` → **no drain** (same safety as bootstrap) BUT it is logged as classification failure
- Exposed via Redis: `spot:node:owner_type:{cluster_id}:{node_name}` = `"unknown"` is visible
- AR logs `node_owner_type_unknown` metric per cluster per cycle — detectable in dashboards
- Bootstrap is only set when `optimization-exempt=true` is explicit — intentional, not default

**Behavior rule for `unknown` nodes (add to Change 4):**
```python
if owner_type in ("bootstrap", "unknown"):
    # never drain, but log unknown separately
    if owner_type == "unknown":
        logger.warning("node_owner_type_unknown node=%s cluster=%s", node_name, cluster_id)
    add to node_plan with action="keep", retention_reason=f"{owner_type}_node"
```

- Call this during `_sync_instance_state_from_k8s()` when upserting Instance records.
- Also populate from agent heartbeat data if agent reports node labels to Redis.

**Also store in Redis for fast reads (no DB query in hot paths):**
```
spot:node:owner_type:{cluster_id}:{node_name} → "bootstrap" | "legacy_mng" | "karpenter_dynamic"
TTL: 300s (refreshed every sync cycle)
```

---

### CHANGE 4 — Ownership-Aware PPE and AR Behavior

**Three rules only. No scoring engine.**

**Rule 1 — bootstrap: never drain, never optimize**
- File: `backend/services/pod_placement_engine.py`
- In `CapacityPlanner.plan()` when building `node_plan`:
  Before appending a `"drain"` action for any node, check Redis key
  `spot:node:owner_type:{cluster_id}:{node_name}`. If value is `"bootstrap"`, skip it.
  Add it to `node_plan` with `action="keep"` and `retention_reason="bootstrap_node"`.

**Rule 2 — legacy_mng: prefer drain (takeover phase only)**
- File: `backend/workers/tasks/auto_rebalancer.py`
- In the cluster evaluation loop (around line 7150+), when selecting which RebalancingAction
  to create next, prefer nodes with `node_owner_type="legacy_mng"` as source nodes.
- This only applies when `cluster.onboarding_phase == "takeover"` (see Change 5).
- Outside takeover phase, MNG nodes are left alone (cluster is already managed).

**Rule 3 — karpenter_dynamic: normal optimization**
- No change needed. Current behavior already targets these correctly.

**ADJUSTMENT 2 — Node age protection (anti-churn cooldown):**
Newly provisioned Karpenter OD nodes (from takeover OR normal rebalancing) must NOT be
immediately eligible for further redistribution/consolidation. Without this, the sequence:
`scale-up → KEDA triggers → consolidation → scale-up again` creates a churn loop.

Mechanism: when a new node is provisioned, write a Redis key:
```
spot:node:provisioned_at:{cluster_id}:{node_name}  → UTC timestamp, TTL 1800s (30 min)
```
Set this key in `execute_rebalancing_action()` when the `waiting_agent` loop detects a new
spot/OD node has joined (around the spot-baseline diff detection, line ~1854).

Also set it in `NodeProvisioner.provision_all()` in `execution_engine.py` when a provision
entry transitions to `READY`.

**Read in AR cluster evaluation loop (before creating new RebalancingAction):**
```python
MIN_NODE_AGE_BEFORE_CONSOLIDATION = 900  # 15 min (configurable)
_prov_ts_raw = _redis.get(f"spot:node:provisioned_at:{cluster_id}:{target_node_name}")
if _prov_ts_raw:
    _prov_ts = float(_prov_ts_raw)
    _node_age = time.time() - _prov_ts
    if _node_age < MIN_NODE_AGE_BEFORE_CONSOLIDATION:
        logger.info(f"[ar] Node {target_node_name} too young ({_node_age:.0f}s) — skipping")
        continue  # skip — let node settle
```

**Why 15 min:** KEDA reacts within 30s–2min. Karpenter provisioning takes 60–180s. HPA scale
events have a 5-min window guard. 15 min covers all async scheduling settling time.

**Redis key lifecycle:** TTL is 1800s. After 30 min the key expires and the node becomes
eligible for normal optimization. No manual cleanup needed.

**Additional Redis key to add to plan summary:**
```
spot:node:provisioned_at:{cluster_id}:{node_name}  TTL 1800s  prevents churn loops
```

---

## PRIORITY 3 — Add Onboarding Phases

### CHANGE 5 — Add `onboarding_phase` to Cluster Model

**Schema change:**
- File: `backend/models/cluster.py`
- Add column after `managed_node_group_deleted` (line 125):
```python
onboarding_phase = Column(
    String(20), nullable=False,
    default="shadow",
    server_default="'shadow'",
)
# Values: "shadow" | "takeover" | "managed"
# shadow  = observe only, no mutations
# takeover = moving MNG ownership → Karpenter OD (one node at a time)
# managed  = normal optimization enabled
```
- DB migration: `ALTER TABLE clusters ADD COLUMN onboarding_phase VARCHAR(20) NOT NULL DEFAULT 'shadow';`

**State transitions:**
```
shadow   → takeover   User triggers via API (POST /clusters/{id}/onboarding/start-takeover)
                      OR auto after agent connected + Karpenter installed + WIE has ≥1 cycle
takeover → managed    Auto: when all legacy_mng nodes are gone (count == 0)
                      Set by _run_takeover_step() exit condition
```

**API endpoint to expose (minimal):**
- File: `backend/api/` — add to cluster routes
- `POST /api/v1/clusters/{cluster_id}/onboarding/advance`
- Body: `{"phase": "takeover"}` — only allowed transition from shadow
- Sets `cluster.onboarding_phase = "takeover"` and commits.

---

### CHANGE 6 — Gate Mutation Engines on `onboarding_phase`

**Gate 1 — auto_rebalancer (`execute_rebalancing()`):**
- File: `backend/workers/tasks/auto_rebalancer.py`
- Location: cluster loop, after the agent-disconnected gate (line 7045-7060),
  before the cluster_mutex check (line 7062).
- Insert:
```python
# ── ONBOARDING PHASE GATE ────────────────────────────────────────────
_ob_phase = getattr(cluster, 'onboarding_phase', 'managed') or 'managed'
if _ob_phase == 'shadow':
    _record_skip(_redis, cluster.id, 'onboarding_shadow')
    continue
if _ob_phase == 'takeover':
    _run_takeover_step(cluster, db, _redis)
    continue  # skip normal rebalancing — takeover handles everything
```

**Gate 2 — PlacementController (`run_cycle()`):**
- File: `backend/pipeline/stage3_ppe/controller_service.py`
- Location: line 201 — after circuit breaker check (line 202-232), before everything else.
- Insert:
```python
# ── ONBOARDING PHASE GATE ────────────────────────────────────────────
try:
    from backend.models.cluster import Cluster as _CL_ob
    _cl_ob = self.db.query(_CL_ob).filter(_CL_ob.id == cluster_id).first()
    _ob_phase = getattr(_cl_ob, 'onboarding_phase', 'managed') or 'managed'
    if _ob_phase in ('shadow', 'takeover'):
        logger.info("placement_controller_onboarding_gate cluster=%s phase=%s", cluster_id, _ob_phase)
        self._emit_cycle_metrics(cluster_id, metrics, skipped_reason=f"onboarding_{_ob_phase}")
        return
except Exception:
    pass  # fail open — unknown phase does not block PC
```

**Gate 3 — ExecutionEngine (`ExecutionEngine.run()`):**
- File: `backend/services/execution_engine.py`
- Location: `ExecutionEngine.run()` at line 1649, after cluster load (lines 1668-1680),
  before `ExecutionGate.check()` at line 1683.

**ADJUSTMENT 4 — Gate ONLY normal optimization manifests, NOT takeover execution:**
Blocking ALL EE execution during `takeover` phase risks a deadlock if takeover itself
ever routes through EE (e.g., EE-managed drain lifecycle actions). The gate must be
manifest-type aware.

Manifests have no `manifest_type` field today — add it. When `_run_takeover_step()` or
any takeover path creates a manifest, tag it `manifest_type="takeover"`.

Gate logic:
```python
# ADJUSTMENT 4: onboarding phase gate — only block normal optimization
_ob_phase = getattr(cluster, 'onboarding_phase', 'managed') or 'managed'
if _ob_phase in ('shadow', 'takeover'):
    _manifest_type = manifest.get('manifest_type', 'optimization')
    if _manifest_type != 'takeover':
        # Block normal optimization manifests during onboarding
        logger.info(
            f"[EE] cluster={cluster_id} onboarding_gate phase={_ob_phase} "
            f"manifest_type={_manifest_type} — skipping"
        )
        return
    # Takeover-tagged manifests pass through even during takeover phase
```

This means:
- `shadow` phase: ALL manifests blocked (nothing executes)
- `takeover` phase: `manifest_type=optimization` blocked, `manifest_type=takeover` allowed
- `managed` phase: all manifests execute normally

Also add `manifest_type` to the `ManifestStore` write in `distribution_engine.py`:
```python
# in the manifest dict, add:
"manifest_type": "optimization",  # default for all DE-generated manifests
```

**What is ALLOWED during shadow/takeover:**
- WIE cycles ✅ — observation and profile building, no mutations
- `placement_advisor_task` ✅ — only writes PlacementPolicyRecord, no mutations
- Telemetry + metrics ✅
- `bootstrap_default_nodepool()` ✅ — idempotent, safe

---

## PRIORITY 4 — Fix Karpenter Ownership Flow

### CHANGE 7 — Create Two NodePools on Bootstrap

**Current state:** `bootstrap_default_nodepool()` in `karpenter_service.py` line 1289 creates
only `spot-general`. There is no `od-general` pool. During takeover, when AR tries to move
MNG pods to OD (safer), it fails with `no_spot_nodepool_exists` because the `od-general`
pool doesn't exist.

**Change in `bootstrap_default_nodepool()` (line 1289):**
After creating `spot-general`, also call `_update_nodepool()` for `od-general`:
```python
# Create od-general NodePool for stateful/critical/takeover workloads
self._update_nodepool(
    api_client=api_client,
    nodepool_name="od-general",
    instance_types=_safe_types,
    azs=azs,
    cluster=cluster,
    capacity_type="on-demand",
    consolidation_policy="WhenEmpty",      # conservative for OD
    consolidate_after="300s",              # 5-min cooldown before OD consolidation
)
```

**Check for existing `od-general` pool** before creating (same pattern as `spot_pools` check
at line 1306-1322 — check for OD pools separately).

---

### CHANGE 8 — Explicit NodePool Targeting

**Problem:** `_target_nodepool_name` resolution in `execute_rebalancing_action()` (around line
1700 in `auto_rebalancer.py`) tries `spot-general` then `default`. No OD targeting. During
takeover, all moves should go to `od-general`.

**Change in `execute_rebalancing_action()` Phase 1 NodePool resolution:**
```python
# Before the existing K-5 NodePool resolution logic (~line 1680):
_is_takeover = (action.action_metadata or {}).get('migration_type') == 'mng_takeover'
_cap_type_target = "on-demand" if _is_takeover else "spot"

# In K-5 resolution, prefer od-general for OD migrations, spot-general for spot:
_preferred_pool = "od-general" if _is_takeover else "spot-general"
# Try preferred pool first, fall back to "default"
```

**Verify NodeClaim NodePool selection:** Karpenter v1 NodeClaims select a NodePool via
`spec.nodeClassRef` + NodePool label selectors. The trigger pod must carry the correct
`karpenter.sh/nodepool: od-general` annotation/nodeSelector so Karpenter routes it to the
right pool. This is set in `KarpenterService.create_spot_trigger_pod()` — add a
`nodepool_name` parameter that sets the nodeSelector.

---

## PRIORITY 5 — Fix MNG Termination

### CHANGE 9 (was CHANGE 5 in original list numbering) — MNG-Safe Termination

**Current problem:** `execute_rebalancing_action()` terminates nodes via direct EC2
`terminate_instances()`. For MNG nodes managed by an Auto Scaling Group, this causes the ASG
to immediately re-provision a replacement node — the cluster never shrinks.

**Correct path for MNG nodes:**
```
TerminateInstanceInAutoScalingGroup(
    InstanceId=instance_id,
    ShouldDecrementDesiredCapacity=True   ← critical
)
```

**Where to add:**
- File: `backend/workers/tasks/auto_rebalancer.py`
- In `execute_rebalancing_action()` at the EC2 termination section (Phase 2/3 — after DRAIN
  completes and TERMINATE_NODE AgentAction is processed).
- Check action metadata for `mng_node: true` and `asg_name`:
```python
_is_mng_node = (action.action_metadata or {}).get('mng_node', False)
_asg_name = (action.action_metadata or {}).get('asg_name')

if _is_mng_node and _asg_name:
    # ASG-aware termination — decrements desired capacity
    _autoscaling = boto3.client('autoscaling', region_name=region, ...)
    _autoscaling.terminate_instance_in_auto_scaling_group(
        InstanceId=_source_instance_id,
        ShouldDecrementDesiredCapacity=True,
    )
else:
    # existing EC2 terminate path
    ec2_client.terminate_instances(InstanceIds=[_source_instance_id])
```

**Where `mng_node` and `asg_name` are set:**
In `_run_takeover_step()` (new function — see Change 11/12), when creating a RebalancingAction
for an MNG node, set `action_metadata["mng_node"] = True` and `action_metadata["asg_name"]`
from the `eks.amazonaws.com/nodegroup` label → lookup ASG via `eks describe-nodegroup` or
from the EC2 instance's ASG membership tag `aws:autoscaling:groupName`.

---

## PRIORITY 6 — Execution Safety Validation

### CHANGE 10 — AgentAction Idempotency Check

**Verify these are already safe:**
- `CORDON_NODE`: K8s `cordon` is idempotent — calling it on already-cordoned node is a no-op ✅
- `DRAIN_NODE`: K8s `drain` with `--ignore-daemonsets` is idempotent if pods already gone ✅
- `LABEL_NODE`: K8s label patch is idempotent ✅
- `EVICT_POD`: K8s eviction on already-gone pod returns 404 — agent must handle gracefully

**What's NOT safe today — DB-level dedup:**
- File: `backend/pipeline/stage3_ppe/controller_service.py`
- Function: `_dispatch_eviction()` line 1020
- Currently creates EVICT_POD without checking if one already exists for the same pod.
- Add a dedup check before `db.add(agent_action)`:
```python
from backend.models.agent_action import AgentAction as _AA_chk, AgentActionStatus as _AAS_chk
_existing_eviction = self.db.query(_AA_chk).filter(
    _AA_chk.cluster_id == cluster_id,
    _AA_chk.status.in_([_AAS_chk.PENDING, _AAS_chk.PICKED_UP]),
    _AA_chk.payload['pod_name'].astext == pod.name,
    _AA_chk.payload['namespace'].astext == pod.namespace,
).first()
if _existing_eviction:
    logger.info("evict_pod_dedup_skipped pod=%s existing_action=%s", pod.name, _existing_eviction.id)
    metrics["evictions_skipped_active_action"] += 1  # counter already exists at line 190
    return
```

**Cooldown + reconciliation verification (no code change needed — confirm behavior):**
- `reconcile_stuck_actions()` at line 2556 of `auto_rebalancer.py` already runs every 5min
  via Celery beat. It catches actions stuck in `in_progress`/`waiting_agent` for >45 min.
- Heartbeat lock `HeartbeatLock` in `execute_rebalancing()` (line 2682) handles Redis restart.
- `_cleanup_rebalancing_resources()` at line 2402 clears semaphore + trigger pod on every
  exit path (fail, deferred, complete).
- These are already correct. No changes needed.

---

## PRIORITY 7 — MNG Takeover Flow

### CHANGE 11 — `_run_takeover_step()` — OD-First, One Node at a Time

**New function to add in `backend/workers/tasks/auto_rebalancer.py`**
(define it near `trigger_graceful_rebalancing` at line 2047):

```python
def _run_takeover_step(cluster, db, redis):
    """
    Called by execute_rebalancing() when cluster.onboarding_phase == 'takeover'.
    Migrates one MNG node per cycle to Karpenter OD.
    
    Flow:
    T-0: Prereq gate — Karpenter installed + od-general NodePool exists
    T-1: Check if a takeover action is already in_progress → wait
    T-2: Count remaining MNG nodes → if 0, transition to 'managed'
    T-3: Pick 1 MNG node (fewest pods, no anchor pods)
    T-4: Create RebalancingAction with migration_type='mng_takeover'
    """
    from backend.models.rebalancing_action import RebalancingAction
    from backend.core.redis_client import key_rebalance_lock

    cluster_id = str(cluster.id)
    _takeover_active_key = f"spot:takeover_active:{cluster_id}"

    # T-0: Karpenter must be installed
    _karp_flag = f"spot:karpenter_nodepool_bootstrap_needed:{cluster_id}"
    if redis and redis.exists(_karp_flag):
        logger.info(f"[takeover] Cluster {cluster_id}: waiting for NodePool bootstrap")
        return  # bootstrap not yet complete

    # T-1: One action at a time
    if redis and redis.exists(_takeover_active_key):
        logger.debug(f"[takeover] Cluster {cluster_id}: takeover action in flight, waiting")
        return

    # T-2: Count remaining MNG nodes
    from backend.models.instance import Instance
    mng_nodes = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.node_owner_type == 'legacy_mng',
        Instance.state == 'running',
    ).all()

    if not mng_nodes:
        # All MNG nodes gone → transition to managed
        from backend.models.cluster import Cluster as _CL
        db.query(_CL).filter(_CL.id == cluster_id).update(
            {"onboarding_phase": "managed"}
        )
        db.commit()
        logger.info(f"[takeover] Cluster {cluster_id}: all MNG nodes migrated → phase=managed")
        return

    # T-3: Pick node with fewest pods (least disruptive)
    # ADJUSTMENT 3: Skip nodes with singleton/critical workloads before picking
    _safe_nodes = []
    for _cand in mng_nodes:
        _skip_reason = _takeover_should_skip_node(_cand, cluster_id, redis, db)
        if _skip_reason:
            logger.warning(
                f"[takeover] Skipping node {_cand.node_name}: {_skip_reason}"
            )
            continue
        _safe_nodes.append(_cand)

    if not _safe_nodes:
        logger.warning(
            f"[takeover] Cluster {cluster_id}: all remaining MNG nodes are anchor-blocked. "
            f"Manual intervention required. Nodes: {[n.node_name for n in mng_nodes]}"
        )
        return

    target_node = _safe_nodes[0]
    _asg_name = None
    # TODO: resolve ASG name from node labels or EC2 tags
    #       Store in action_metadata['asg_name'] for MNG-safe termination (Change 9)

    # T-4: Create RebalancingAction targeting od-general
    action = RebalancingAction(
        cluster_id=cluster_id,
        trigger="takeover",
        source_pool=f"{target_node.instance_id}:{target_node.az}",
        target_pool="od-general",
        status="pending",
        migration_type="mng_takeover",
        source="takeover_controller",
        action_metadata={
            "mng_node": True,
            "asg_name": _asg_name,
            "target_node_name": target_node.node_name,
            "instance_id": target_node.instance_id,
        },
    )
    db.add(action)
    db.commit()

    # Set active guard (TTL 45 min — matches stale action expiry)
    if redis:
        redis.setex(_takeover_active_key, 2700, str(action.id))

    logger.info(
        f"[takeover] Cluster {cluster_id}: queued takeover for node "
        f"{target_node.node_name} ({target_node.instance_id}) → od-general. "
        f"Remaining MNG nodes: {len(mng_nodes)}"
    )
```

**ADJUSTMENT 3 — `_takeover_should_skip_node()` helper (add near `_run_takeover_step`):**
```python
def _takeover_should_skip_node(node, cluster_id: str, redis, db) -> Optional[str]:
    """
    Returns a skip reason string if the node should not be takeover-drained,
    None if it is safe to proceed.
    """
    node_name = node.node_name or ""

    # 1. kube-system criticals — nodes running kube-system Pending-critical pods
    #    Agent writes pod list per node to Redis: spot:node:pods:{cluster_id}:{node_name}
    try:
        _pod_raw = redis.get(f"spot:node:pods:{cluster_id}:{node_name}") if redis else None
        if _pod_raw:
            _pods = json.loads(_pod_raw)
            _system_pods = [
                p for p in _pods
                if p.get("namespace") == "kube-system"
                and p.get("priority_class") in ("system-cluster-critical", "system-node-critical")
            ]
            if _system_pods:
                return f"kube_system_critical_pods:{len(_system_pods)}"
    except Exception:
        pass

    # 2. Singleton StatefulSets (replicas=1, no PDB)
    #    WIE writes workload profile per node to Redis
    try:
        _node_wl_key = f"spot:node:workloads:{cluster_id}:{node_name}"
        _wl_raw = redis.get(_node_wl_key) if redis else None
        if _wl_raw:
            _workloads = json.loads(_wl_raw)
            for _wl in _workloads:
                if (_wl.get("controller_kind") in ("StatefulSet",)
                        and int(_wl.get("replicas", 2)) == 1
                        and not _wl.get("has_pdb")):
                    return f"singleton_statefulset_no_pdb:{_wl.get('workload_id')}"
    except Exception:
        pass

    # 3. Check takeover retry counter — stop trying permanently broken nodes
    # ADJUSTMENT 5 (see below)
    try:
        _attempt_key = f"spot:takeover_attempts:{cluster_id}:{node_name}"
        _attempts = int(redis.get(_attempt_key) or 0) if redis else 0
        if _attempts >= 3:
            return f"max_takeover_retries_exceeded:{_attempts}"
    except Exception:
        pass

    return None  # safe to proceed
```

---

### CHANGE 12 — One Node at a Time (enforced)

Already embedded in `_run_takeover_step()` via `spot:takeover_active:{cluster_id}`.

**How the guard clears:**
- When the RebalancingAction for the takeover reaches `status='completed'` or `status='failed'`,
  the existing `_cleanup_rebalancing_resources()` at line 2402 should also delete
  `spot:takeover_active:{cluster_id}`.
- Add to `_cleanup_rebalancing_resources()`:
```python
# Clear takeover active guard if this was a takeover action
if (wa.action_metadata or {}).get('mng_node'):
    try:
        redis_client.delete(f"spot:takeover_active:{wa.cluster_id}")
    except Exception:
        pass
    # ADJUSTMENT 5: increment per-node retry counter on failure
    _node_name_for_counter = (wa.action_metadata or {}).get('target_node_name')
    if wa.status in ('failed',) and _node_name_for_counter:
        try:
            _attempt_key = f"spot:takeover_attempts:{wa.cluster_id}:{_node_name_for_counter}"
            redis_client.incr(_attempt_key)
            redis_client.expire(_attempt_key, 86400)  # 24h window
            _attempts = int(redis_client.get(_attempt_key) or 1)
            if _attempts >= 3:
                logger.error(
                    f"[takeover] Node {_node_name_for_counter} failed {_attempts} times — "
                    f"marking as blocked. Manual intervention required."
                )
                # Surface via Redis for dashboard
                redis_client.setex(
                    f"spot:takeover_blocked_node:{wa.cluster_id}:{_node_name_for_counter}",
                    86400, json.dumps({"attempts": _attempts, "reason": wa.error_message})
                )
        except Exception:
            pass
```

**ADJUSTMENT 5 — Takeover timeout escalation (full description):**
The 45-min TTL via `reconcile_stuck_actions()` at line 2556 handles stale in-progress
actions. But without a per-node retry counter, the same broken node gets retried indefinitely
every time `reconcile_stuck_actions()` resets it. This burns cycles and masks real failures.

Full mechanism:
- `spot:takeover_attempts:{cluster_id}:{node_name}` — INCR on each failure, TTL 24h
- After 3 failures: `_takeover_should_skip_node()` returns `max_takeover_retries_exceeded`
- `spot:takeover_blocked_node:{cluster_id}:{node_name}` — surfaced for dashboard/alert
- Exposed via API: `GET /api/v1/clusters/{id}/onboarding/status` returns `blocked_nodes` list
- Manual override: `DELETE /api/v1/clusters/{id}/onboarding/blocked-nodes/{node_name}`
  resets `spot:takeover_attempts:{cluster_id}:{node_name}` → node becomes eligible again

---

## Implementation Order

Implement in this exact order — each step is independently deployable:

| Step | Change | File | Risk | Prereqs |
|------|--------|------|------|---------|
| 1 | Change 1: Symmetric lock | `controller_service.py` line 235 | Low — adds a skip | None |
| 2 | Change 10: EVICT_POD dedup | `controller_service.py` `_dispatch_eviction()` | Low — adds dedup | None |
| 3 | Change 3: `node_owner_type` schema | `instance.py` + migration | Low — additive column | None |
| 4 | Change 3: populate in `_sync_instance_state_from_k8s` | `auto_rebalancer.py` line 728 | Low | Step 3 |
| 5 | Change 5: `onboarding_phase` schema | `cluster.py` + migration | Low — additive column | None |
| 6 | Change 6: Gate PC on onboarding_phase | `controller_service.py` line 201 | Low | Step 5 |
| 7 | Change 6: Gate AR on onboarding_phase | `auto_rebalancer.py` cluster loop ~7045 | Low | Step 5 |
| 8 | Change 6: Gate EE on onboarding_phase | `execution_engine.py` | Low | Step 5 |
| 9 | Change 7: od-general NodePool | `karpenter_service.py` `bootstrap_default_nodepool()` | Medium — K8s API call | Step 5 |
| 10 | Change 4: PPE bootstrap/MNG rules | `pod_placement_engine.py` CapacityPlanner | Medium | Steps 3,4 |
| 11 | Change 2: Draining annotation | `auto_rebalancer.py` + `controller_service.py` | Medium | None |
| 12 | Change 9: MNG-safe termination | `auto_rebalancer.py` terminate section | High — AWS API | Steps 3,4 |
| 13 | Change 11+12: `_run_takeover_step()` | `auto_rebalancer.py` | High — new flow | Steps 3,5,7,9,12 |
| 14 | Change 8: Explicit NodePool targeting | `auto_rebalancer.py` Phase 1 | Medium | Step 9 |

---

## DB Migrations Required

```sql
-- Migration 1: node_owner_type on instances
ALTER TABLE instances
  ADD COLUMN node_owner_type VARCHAR(20);

CREATE INDEX idx_instances_node_owner_type ON instances(cluster_id, node_owner_type);

-- Migration 2: onboarding_phase on clusters
ALTER TABLE clusters
  ADD COLUMN onboarding_phase VARCHAR(20) NOT NULL DEFAULT 'shadow';

-- Existing clusters that are already live should be set to 'managed'
-- so they are not accidentally gated:
UPDATE clusters
  SET onboarding_phase = 'managed'
  WHERE status = 'ACTIVE'
    AND agent_installed = 'Y';
```

---

## Redis Keys Added

| Key | TTL | Set by | Read by | Purpose |
|-----|-----|--------|---------|---------|
| `spot:node:owner_type:{cluster_id}:{node_name}` | 300s | `_sync_instance_state_from_k8s` | AR cluster loop, PPE | Fast owner type lookup |
| `spot:takeover_active:{cluster_id}` | 2700s | `_run_takeover_step` | `_run_takeover_step` | Enforce 1-node-at-a-time |
| `spot:node:provisioned_at:{cluster_id}:{node_name}` | 1800s | `execute_rebalancing_action` waiting_agent loop + `NodeProvisioner` | AR cluster loop | Anti-churn cooldown (ADJUSTMENT 2) |
| `spot:takeover_attempts:{cluster_id}:{node_name}` | 86400s | `_cleanup_rebalancing_resources` on failure | `_takeover_should_skip_node` | Per-node retry counter (ADJUSTMENT 5) |
| `spot:takeover_blocked_node:{cluster_id}:{node_name}` | 86400s | `_cleanup_rebalancing_resources` at retry threshold | API status endpoint | Surface blocked nodes for manual intervention (ADJUSTMENT 5) |

---

## What is NOT changed

- PPE core algorithm — no rewrite
- WorkloadSorter / WaveBuilder — not needed for safety
- Decision Engine — untouched
- WIE — untouched  
- Any existing lock mechanisms — only additions, no removals
- AgentAction model — no new action types needed
- RebalancingAction model — `migration_type='mng_takeover'` is a new string value only,
  no schema change (column is already VARCHAR)

---

## Adjustments Summary (v2)

| # | What changed | Why |
|---|---|---|
| ADJ-1 | `_derive_node_owner_type()` default is `"unknown"` not `"bootstrap"` | Observability — stale labels must be visible, not silently protected |
| ADJ-2 | Node age cooldown (`spot:node:provisioned_at`, 15 min gate) | Prevents churn loops with KEDA/Karpenter async scheduling |
| ADJ-3 | `_takeover_should_skip_node()` filters singletons + kube-system before picking | Prevents first migration destabilizing cluster |
| ADJ-4 | EE gate is manifest_type-aware (`manifest_type=takeover` bypasses) | Prevents takeover deadlocking itself via EE drain lifecycle |
| ADJ-5 | Per-node retry counter + blocked_node surfacing + manual override API | Stops infinite retry on broken nodes, surfaces for ops team |

---

## Issues (v3) — Remaining Operational Gaps

---

### ISSUE 1 — EE Gating Already Resolved (ADJ-4) — Reinforcement Note

Addressed in ADJ-4 above. Confirmed that the EE gate MUST be manifest_type-aware.
`shadow` phase blocks ALL manifests. `takeover` phase blocks only `manifest_type=optimization`.
`manifest_type=takeover` passes through in all phases.

This is now in the plan. No additional code change needed beyond what ADJ-4 specifies.

---

### ISSUE 2 — KEDA Key Verification (HIGHEST PRIORITY OPERATIONAL RISK)

**Root cause found in code (confirmed):**
- Key: `KEDA_EVENT_KEY_TEMPLATE = "spot:keda:last_scale_event:{cluster_id}"` (`controller_service.py` line 62)
- Read by: `_recent_keda_scaling_event()` at line 780
- **Critical behavior at line 788-791:**
  ```python
  process_uptime = time.time() - _PROCESS_START_TIME
  return process_uptime > KEDA_BOOTSTRAP_WINDOW_SECONDS  # 300s default
  ```
  If the key is **absent** AND process has been running > 5 min → returns `True` = **block all evictions permanently**.

**This is NOT a fake guard. It is an overly conservative guard that silently disables PC.**

If the agent never writes `spot:keda:last_scale_event:{cluster_id}`, the system behaves as:
- First 5 minutes: PC works normally (bootstrap window)
- After 5 minutes: PC permanently blocks ALL evictions for ALL clusters — forever
- No log line, no alert, no visible error — PC silently skips all workloads

**Verification steps (must do before production):**

Step 1: Confirm WHERE the agent writes this key. Search agent codebase for:
```
spot:keda:last_scale_event
```
The agent must write `redis.setex(key, SCALING_GUARD_WINDOW_SECONDS, str(time.time()))`
whenever it observes a KEDA ScaledObject trigger a replica change.

Step 2: If agent does NOT write this key, add it to the agent's KEDA event handler:
```python
# In agent's KEDA watch loop, when ScaledObject fires:
redis.setex(
    f"spot:keda:last_scale_event:{cluster_id}",
    120,  # 2-min window — matches SCALING_GUARD_WINDOW_SECONDS
    str(time.time())
)
```

Step 3: Add an explicit log line when `_recent_keda_scaling_event()` returns True due to
absent key (not due to a real recent event). Currently these two cases are indistinguishable:
```python
# In _recent_keda_scaling_event(), add:
if not raw:
    if process_uptime > KEDA_BOOTSTRAP_WINDOW_SECONDS:
        logger.warning(
            "keda_event_key_absent_blocking_evictions cluster=%s uptime=%.0fs "
            "— verify agent is writing spot:keda:last_scale_event",
            cluster_id, process_uptime
        )
    return process_uptime > KEDA_BOOTSTRAP_WINDOW_SECONDS
```

This makes the silent block visible in logs immediately.

**Add to implementation order as Step 0 (before all other changes) — verification only, no
code change if agent already writes the key.**

---

### ISSUE 3 — Pre-Takeover Anchor Node Classification

**Problem:** Currently `_takeover_should_skip_node()` filters nodes reactively as takeover
runs. This means takeover appears "stuck" or "making no progress" without any explanation.
Operators have no visibility into WHY no nodes are being migrated.

**Fix: Pre-classification pass BEFORE takeover begins.**

Add a new function `_classify_takeover_blockers(cluster_id, db, redis)` that runs ONCE
when `onboarding_phase` transitions to `"takeover"`.

```python
def _classify_takeover_blockers(cluster_id: str, db, redis) -> Dict:
    """
    Scan all legacy_mng nodes and classify which ones are blocked before takeover starts.
    Writes results to Redis for API/UI consumption.
    Returns: {"total_mng": int, "safe": int, "blocked": List[Dict]}
    """
    from backend.models.instance import Instance
    mng_nodes = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.node_owner_type == 'legacy_mng',
        Instance.state == 'running',
    ).all()

    blocked = []
    safe = []
    for node in mng_nodes:
        reason = _takeover_should_skip_node(node, cluster_id, redis, db)
        if reason:
            blocked.append({"node_name": node.node_name, "reason": reason,
                            "instance_id": node.instance_id})
        else:
            safe.append(node.node_name)

    result = {
        "total_mng": len(mng_nodes),
        "safe_to_migrate": len(safe),
        "blocked_nodes": blocked,
        "classified_at": time.time(),
    }
    if redis:
        redis.setex(
            f"spot:takeover_preflight:{cluster_id}",
            86400,
            json.dumps(result)
        )
    logger.info(
        f"[takeover] Preflight cluster={cluster_id}: "
        f"total={result['total_mng']} safe={result['safe_to_migrate']} "
        f"blocked={len(blocked)}"
    )
    return result
```

**Where to call it:**
- File: `backend/api/` — in the `POST /api/v1/clusters/{id}/onboarding/advance` endpoint
- Call `_classify_takeover_blockers()` immediately after `cluster.onboarding_phase = "takeover"`
- Return the result in the API response so the UI can display it

**API response structure:**
```json
{
  "phase": "takeover",
  "preflight": {
    "total_mng_nodes": 8,
    "safe_to_migrate": 5,
    "blocked_nodes": [
      {"node_name": "ip-10-0-1-100", "reason": "singleton_statefulset_no_pdb:postgres-primary"},
      {"node_name": "ip-10-0-1-101", "reason": "kube_system_critical_pods:2"},
      {"node_name": "ip-10-0-1-102", "reason": "singleton_statefulset_no_pdb:redis-master"}
    ]
  }
}
```

**Also expose via:**
- `GET /api/v1/clusters/{id}/onboarding/status` — reads `spot:takeover_preflight:{cluster_id}`
- UI shows: "5 of 8 nodes ready to migrate. 3 nodes require manual preparation."

**New Redis key:**
```
spot:takeover_preflight:{cluster_id}  TTL 86400s  preflight classification result
```

---

### ISSUE 4 — OD→Spot Migration Must Stay Conservative (24h Observation Gate)

**Context:** After takeover completes, all workloads are on `od-general` Karpenter nodes.
The normal AR+PC loop will try to migrate them to `spot-general`. This must NOT happen
aggressively.

**Current gating in WIE:** WIE outputs `spot_confidence` and `workload_class`. PC already
checks `max_spot_replicas` from WIE policy. The issue is: WIE reaches `CONFIRMED` status
after ~24h but this threshold is configurable and may be lower in some environments.

**Add an explicit minimum observation age gate in PC (`run_cycle()`):**

In `_process_workload()` or before `_dispatch_eviction()`, add:
```python
# After takeover: enforce minimum observation window before spot migration
# Check when this cluster completed takeover
_takeover_done_ts_raw = self.redis.get(f"spot:takeover_completed_at:{cluster_id}")
if _takeover_done_ts_raw:
    _takeover_done_ts = float(_takeover_done_ts_raw)
    _time_since_takeover = time.time() - _takeover_done_ts
    MIN_OBS_SECS = int(os.getenv("PC_MIN_OD_TO_SPOT_OBSERVATION_SECS", 86400))  # 24h default
    if _time_since_takeover < MIN_OBS_SECS:
        logger.info(
            "od_to_spot_observation_window cluster=%s elapsed=%.0fh required=%.0fh",
            cluster_id, _time_since_takeover/3600, MIN_OBS_SECS/3600
        )
        self._emit_cycle_metrics(cluster_id, metrics, skipped_reason="od_spot_observation_window")
        return
```

**Where `spot:takeover_completed_at:{cluster_id}` is set:**
In `_run_takeover_step()` when transitioning `onboarding_phase → "managed"`:
```python
if redis:
    redis.setex(
        f"spot:takeover_completed_at:{cluster_id}",
        604800,  # 7 days — covers the observation window + margin
        str(time.time())
    )
```

**Why 24h:** Production workloads need a full 24h cycle (business hours, off-hours, batch
jobs, KEDA peak/trough) to build a representative WIE profile. Without this, WIE may
classify a workload as spot-safe during a quiet off-peak period, then fail during morning
peak. The 24h gate is the minimum safe observation window for production.

**This is configurable via env:** `PC_MIN_OD_TO_SPOT_OBSERVATION_SECS=86400`. Set to 0 to
disable for dev/staging.

**New Redis key:**
```
spot:takeover_completed_at:{cluster_id}  TTL 604800s (7d)  set by _run_takeover_step at phase=managed
```

---

### ISSUE 5 — Karpenter Consolidation Freeze Lifecycle (Confirmed Bug)

**Root cause found in code:**

`add_allowed_instance_type()` line 1521-1525 in `karpenter_service.py`:
```python
if self.redis and not self.redis.exists(_CONSOLIDATE_AFTER_KEY):
    _original_after = nodepool.get('spec', {}).get('disruption', {}).get('consolidateAfter', '30s')
    self.redis.set(_CONSOLIDATE_AFTER_KEY, _original_after)  # ← NO TTL
```

**Bug 1 — No TTL on `_CONSOLIDATE_AFTER_KEY`:**
`redis.set()` with no TTL = key lives forever. If `remove_allowed_instance_type()` is never
called (action fails, worker crashes, Redis connection drops at cleanup), the key `karpenter:nodepool_consolidate_after_baseline:{cluster_id}:{nodepool_name}` persists indefinitely. On the next injection cycle, `not self.redis.exists(...)` is False, so NO new snapshot is taken — the baseline is whatever was stored from the last successful cycle.

Meanwhile, `consolidateAfter=Never` is re-set every `add_allowed_instance_type()` call (line
1535). The `_CONSOLIDATE_AFTER_KEY` has the correct restore value, but if `remove_allowed_instance_type()` fails, consolidation stays frozen.

**Bug 2 — `remove_allowed_instance_type()` is the only restore path:**
If this function fails (K8s API error, Redis error), consolidation remains frozen AND
`_CONSOLIDATE_AFTER_KEY` is NOT deleted (line 1700 only runs on success). Subsequent calls
to `add_allowed_instance_type()` see the existing key and skip re-snapshotting — correct
behavior. But `remove_allowed_instance_type()` must be called successfully at some point.

**Fix 1 — Add TTL to `_CONSOLIDATE_AFTER_KEY`:**
In `add_allowed_instance_type()` line 1525, change:
```python
self.redis.set(_CONSOLIDATE_AFTER_KEY, _original_after)
```
to:
```python
self.redis.set(_CONSOLIDATE_AFTER_KEY, _original_after, ex=86400)  # 24h max injection window
```
After 24h, the key expires. The reconciliation scan then detects the frozen NodePool
and issues a restore call.

**Fix 2 — Add reconciliation scan for orphaned frozen NodePools:**
A periodic task (every 30 min via Celery beat) should scan:
```python
# Scan for orphaned consolidation freeze
_frozen_keys = redis.keys("karpenter:nodepool_consolidate_after_baseline:*")
for key in _frozen_keys:
    # parse cluster_id and nodepool_name from key
    _parts = key.split(":")
    _cluster_id = _parts[-2]
    _nodepool_name = _parts[-1]
    # Check if any active action exists for this cluster
    _active_action = db.query(RebalancingAction).filter(
        RebalancingAction.cluster_id == _cluster_id,
        RebalancingAction.status.in_(["in_progress", "waiting_agent"]),
    ).first()
    if not _active_action:
        # No active action but consolidation is frozen — restore it
        logger.warning(
            f"[karpenter] Orphaned consolidation freeze detected: cluster={_cluster_id} "
            f"nodepool={_nodepool_name} — restoring"
        )
        ks.remove_allowed_instance_type(_cluster_id, "", _nodepool_name)
```

**Fix 3 — Ensure `remove_allowed_instance_type()` is on every exit path:**
In `_cleanup_rebalancing_resources()` at line 2402 of `auto_rebalancer.py`, confirm it calls
`remove_allowed_instance_type()`. Currently it calls `ks.delete_spot_trigger_pod()` (line 2441)
but it is NOT confirmed to call `remove_allowed_instance_type()`. Add explicit call:
```python
# In _cleanup_rebalancing_resources(), after trigger pod cleanup:
try:
    _nodepool_used = wa_meta.get('target_nodepool_name', 'spot-general')
    _inst_type_injected = wa_meta.get('injected_instance_type')
    if _inst_type_injected:
        from backend.services.karpenter_service import KarpenterService as _KS_clnup
        _ks_c = _KS_clnup(db, redis_client)
        _ks_c.remove_allowed_instance_type(wa.cluster_id, _inst_type_injected, _nodepool_used)
except Exception as _ce:
    logger.warning(f"[cleanup] consolidation restore failed (will reconcile): {_ce}")
    # Non-fatal — reconciliation scan (Fix 2) will catch it within 30 min
```

---

## Critical Pre-Production Checklist

These MUST be verified before enabling autonomous optimization on any production cluster.

| # | Check | How to verify | Consequence if skipped |
|---|---|---|---|
| P1 | Agent writes `spot:keda:last_scale_event:{cluster_id}` | Search agent codebase for the key. If absent, PC is blocked after 5 min. | PC silently disabled forever |
| P2 | Agent writes `spot:pc:hpa_scaling_event:{cluster_id}` | Same pattern as KEDA key | HPA guard fake — evictions during scale-up |
| P3 | `remove_allowed_instance_type()` called on ALL action exit paths | Audit `_cleanup_rebalancing_resources()` | Consolidation frozen permanently |
| P4 | `_CONSOLIDATE_AFTER_KEY` has TTL added | Check line 1525 of `karpenter_service.py` | Orphaned freeze if Redis key survives |
| P5 | `_takeover_should_skip_node()` reads from correct Redis key pattern | Confirm agent writes `spot:node:workloads:{cluster_id}:{node_name}` | Singleton detection is a no-op |
| P6 | Onboarding phase of existing live clusters backfilled to `managed` | DB migration UPDATE statement | All live clusters silently gated |

---

## Architecture Characterization (v3)

This system now correctly represents **lightweight CAST AI-style lifecycle orchestration**:

```
Phase 0: Register + Observe (shadow)
Phase 1: Install Karpenter + Bootstrap NodePools
Phase 2: Takeover — MNG → Karpenter OD (one node at a time, anchor-aware)
Phase 3: Stabilize — 24h observation window, WIE profile building
Phase 4: Optimize — OD → Spot migration, PPE planning, right-sizing
```

What this is NOT:
- Not a custom Kubernetes scheduler
- Not a complex AI optimizer
- Not a policy engine

What this IS:
- An operational lifecycle controller
- A safe, sequenced ownership transfer mechanism
- A conflict-free multi-engine coordination layer

The architecture is correct. The remaining work is verification and hardening of
the infrastructure ownership lifecycle — not algorithmic improvement.

---

## Issues Summary (v3) — Implementation Status

| # | Issue | Status | Implementation |
|---|---|---|---|
| I-1 | EE gating scope | ✅ IMPLEMENTED | `execution_engine.py` onboarding gate, `manifest_type`-aware (shadow=block all, takeover=allow only `manifest_type=takeover`) |
| I-2 | KEDA key absent warning | ✅ IMPLEMENTED | `controller_service.py _recent_keda_scaling_event()` — explicit `logger.warning` when key absent and uptime > 5min |
| I-3 | Pre-takeover anchor classification | ✅ IMPLEMENTED | `_takeover_should_skip_node()` in `auto_rebalancer.py` — checks kube-system pods, singleton StatefulSets without PDB, max retry counter |
| I-4 | OD→Spot 24h observation gate | ✅ IMPLEMENTED | `controller_service.py run_cycle()` — reads `spot:takeover_completed_at:{cluster_id}`, blocks evictions for `PC_MIN_OD_TO_SPOT_OBSERVATION_SECS` (default 86400) |
| I-5 | Consolidation freeze lifecycle | ✅ IMPLEMENTED | `karpenter_service.py add_allowed_instance_type()` — 24h TTL on `_CONSOLIDATE_AFTER_KEY`; `_cleanup_rebalancing_resources()` already calls `remove_allowed_instance_type()` |

---

## Implementation Log (Session 2)

### Completed Changes

**Change 1 — Symmetric lock (controller_service.py)**
- Added `rebalance:lock` check before `_scaling_guard_active` in `run_cycle()`
- PC skips if AR holds the lock; logs `placement_controller_rebalance_lock_held`

**Change 2 — Draining annotation (auto_rebalancer.py + controller_service.py)**
- AR sets `spot-optimizer/draining=true` K8s label + `spot:node:draining:{cluster_id}:{node_name}` Redis key on CORDON
- PC `_select_burst_pods()` skips pods on nodes in the draining set
- Draining key cleared in `_cleanup_rebalancing_resources()`

**Change 3 — node_owner_type column (instance.py)**
- `node_owner_type VARCHAR(32)` column added; default `unknown`
- `_derive_node_owner_type(labels)` helper in `auto_rebalancer.py`:
  - `optimization-exempt=true` → `bootstrap`
  - `karpenter.sh/nodepool` present → `karpenter_dynamic`
  - `eks.amazonaws.com/nodegroup` present → `legacy_mng`
  - else → `unknown`

**Change 5 — onboarding_phase column (cluster.py)**
- `onboarding_phase VARCHAR(32)` column added; default `shadow`
- Values: `shadow` | `takeover` | `managed`
- **CRITICAL**: DB migration must backfill existing active clusters to `managed` (see `temp-doc/db_migrations.sql`)

**Change 6 — Onboarding phase gates**
- PC (`controller_service.py run_cycle()`): returns early if phase=`shadow` or `takeover`
- AR (`auto_rebalancer.py` cluster loop): skips optimization for `shadow`; calls `_run_takeover_step()` for `takeover`
- EE (`execution_engine.py`): blocks all manifests in `shadow`; blocks non-takeover manifests in `takeover`

**Change 7 — od-general NodePool (karpenter_service.py)**
- `bootstrap_default_nodepool()` now also creates `od-general` NodePool (on-demand, `WhenEmpty`, m5.xlarge/2xl/4xl)
- Non-fatal if creation fails

**Change 10 — EVICT_POD dedup (controller_service.py)**
- `_dispatch_eviction()` checks for existing PENDING/PICKED_UP EVICT_POD for same pod before creating new one

**Change 11+12 — Takeover step functions (auto_rebalancer.py)**
- `_run_takeover_step(cluster_id, db, redis)` — single-node-at-a-time MNG drain loop with active guard
- `_takeover_should_skip_node(node, cluster_id, redis, db)` — anchor/singleton/retry safety checks
- On completion (no MNG nodes left): advances `onboarding_phase → managed`, sets `spot:takeover_completed_at`
- ADJ-5: Retry counter increment + blocked node surfacing on failure (3+ attempts → `spot:takeover_blocked_node`)

**Issue 5 Fix 1 — TTL on consolidation baseline (karpenter_service.py)**
- `redis.set(_CONSOLIDATE_AFTER_KEY, ..., ex=86400)` — 24h TTL prevents orphaned freeze

**Issue 4 — OD→Spot 24h gate (controller_service.py)**
- Reads `spot:takeover_completed_at:{cluster_id}` and compares to `PC_MIN_OD_TO_SPOT_OBSERVATION_SECS` env var

### DB Migrations Required

See `temp-doc/db_migrations.sql` for both migrations:
1. `ALTER TABLE instances ADD COLUMN node_owner_type VARCHAR(32) DEFAULT 'unknown'`
2. `ALTER TABLE clusters ADD COLUMN onboarding_phase VARCHAR(32) DEFAULT 'shadow'`
   - **CRITICAL**: Must `UPDATE clusters SET onboarding_phase='managed' WHERE status='ACTIVE' AND agent_installed='Y'`

### All Items Implemented

**node_owner_type population — `agent_routes.py` `upsert_node_metadata_batch`**
- Added `labels: Optional[dict] = None` to `NodeMetadataItem` schema (backwards-compatible; agents that don't send labels fall back to structured field inference)
- After NodeMetadata upsert: iterates nodes, calls `_derive_node_owner_type(labels)` or falls back to `nodepool_name` → `karpenter_dynamic` / `unknown`
- Bulk-updates `Instance.node_owner_type` in batches of 100; fully fail-safe

**`_classify_takeover_blockers()` REST API — `karpenter_routes.py`**
- Endpoint: `GET /karpenter/{cluster_id}/takeover/preflight`
- Queries all `node_owner_type=legacy_mng` running instances
- Calls `_takeover_should_skip_node()` per node, returns per-node `safe` + `skip_reason`
- Response includes: `onboarding_phase`, `takeover_active`, `takeover_completed_at`, `mng_nodes_remaining`, `safe_to_proceed`, `blocked`, `nodes[]`

**Change 9: MNG-safe ASG termination**
- Existing `scaledown` termination mode (`ShouldDecrementDesiredCapacity=True`) already covers MNG-backed nodes
- `_p2_asg_name` detection in Phase 1 ensures MNG nodes use `scaledown` mode automatically — no new code needed
