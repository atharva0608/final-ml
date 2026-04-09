# Auto-Rebalancer: End-to-End Flow Documentation

> **System B — Automatic Node Migration**
> Source: `backend/workers/tasks/auto_rebalancer.py` + `agent/actuator.py` + `backend/services/karpenter_service.py`

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Component Map](#2-component-map)
3. [Celery Task Entry Point](#3-celery-task-entry-point)
4. [Safety Gates (Pre-Execution)](#4-safety-gates-pre-execution)
5. [Phase 1 — Provision Spot Node via Karpenter](#5-phase-1--provision-spot-node-via-karpenter)
6. [Spot Wait Loop (WAITING_FOR_KARPENTER)](#6-spot-wait-loop-waiting_for_karpenter)
7. [Phase 2 — CORDON → DRAIN → TERMINATE](#7-phase-2--cordon--drain--terminate)
8. [Agent-Side Execution](#8-agent-side-execution)
9. [Post-Drain Readiness Verification](#9-post-drain-readiness-verification)
10. [EC2 Termination](#10-ec2-termination)
11. [Completion & Cleanup](#11-completion--cleanup)
12. [Failure Recovery & Rollback](#12-failure-recovery--rollback)
13. [Escalation Logic](#13-escalation-logic)
14. [State Machine](#14-state-machine)
15. [Redis Key Reference](#15-redis-key-reference)

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                       BACKEND (Celery Worker)                        │
│                                                                      │
│  ┌────────────────────────┐    ┌─────────────────────────────────┐   │
│  │  execute_rebalancing() │───▶│ execute_rebalancing_action()    │   │
│  │  (every 15s via Beat)  │    │ - Safety gates (5 checks)       │   │
│  │  - Stale action expiry │    │ - Phase 1: NodePool PATCH       │   │
│  │  - HeartbeatLock       │    │ - Trigger pod creation          │   │
│  └────────────────────────┘    │ - Phase 2: Agent action creation│   │
│                                └───────────┬─────────────────────┘   │
│                                            │                         │
│  ┌─────────────────────┐    ┌──────────────▼───────────────────┐    │
│  │ KarpenterService    │    │ RebalancingAction (DB)            │    │
│  │ - add_allowed_type  │    │ - status: in_progress →           │    │
│  │ - create_trigger_pod│    │   waiting_agent → completed       │    │
│  │ - delete_trigger_pod│    │ - action_metadata: JSON blob      │    │
│  │ - remove_type (GC)  │    │ - AgentAction: CORDON/DRAIN/TERM │    │
│  └─────────────────────┘    └──────────────────────────────────┘    │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                     WEBSOCKET / HTTP                                  │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    AGENT (in-cluster)                           │  │
│  │                                                                │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐    │  │
│  │  │ heartbeat.py │  │ websocket_   │  │ actuator.py       │    │  │
│  │  │ - Karpenter  │  │ client.py    │  │ - cordon_node()   │    │  │
│  │  │   detection  │  │ - Action     │  │ - drain_node()    │    │  │
│  │  │ - Node Ready │  │   dispatch   │  │ - _terminate_node │    │  │
│  │  │   reporting  │  │ - Critical Q │  │ - PDB-aware evict │    │  │
│  │  └──────────────┘  └──────────────┘  └───────────────────┘    │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Map

| Component | File | Role |
|-----------|------|------|
| **Celery Task** | `backend/workers/tasks/auto_rebalancer.py` | Main orchestrator — runs every 15s, processes `RebalancingAction` records |
| **Karpenter Service** | `backend/services/karpenter_service.py` | Patches NodePool CRDs via K8s API, creates/deletes trigger pods |
| **Agent Actuator** | `agent/actuator.py` | Executes K8s operations: cordon, drain (PDB-aware), terminate EC2 |
| **WebSocket Client** | `agent/websocket_client.py` | Bidirectional communication, critical message queue for action results |
| **Heartbeat** | `agent/heartbeat.py` | Reports node readiness, Karpenter controller health to backend |
| **Termination Monitor** | `backend/workers/tasks/termination_monitor.py` | Creates `RebalancingAction` records on spot interruption/risk detection |
| **Rebalance Tracker** | `backend/services/rebalance_tracker.py` | Pool blacklisting with tiered TTLs to prevent flapping |
| **Distributed Locks** | `backend/services/distributed_locks.py` | `HeartbeatLock` and `distributed_lock` for concurrency safety |

---

## 3. Celery Task Entry Point

**File:** `auto_rebalancer.py:2105-2140`

```python
@app.task(name='workers.auto_rebalancer')
def execute_rebalancing():
    """Runs every 15 seconds via Celery Beat."""

    # 1. Acquire HeartbeatLock (prevents concurrent task execution)
    #    - Lock key: "lock:workers.auto_rebalancer"
    #    - TTL: 300s, heartbeat renews every 150s
    _heartbeat_lock = HeartbeatLock(
        _redis, "lock:workers.auto_rebalancer",
        timeout=300, stop_event=_hb_stop_event,
    )
    if not _heartbeat_lock.acquire(blocking=False):
        return  # Another worker is already running

    # 2. Stale Action Expiry — fail orphaned actions
    #    Per-state timeouts (minutes):
    #      in_progress: 45, waiting_agent: 10,
    #      waiting_for_spot_node: 28, cordoning_node: 10,
    #      draining_pods: 20, verifying_pod_readiness: 20,
    #      terminating_source: 10

    # 3. Process in_progress actions → execute_rebalancing_action()
    # 4. Process waiting_agent actions → Phase 2 wait loop
```

### Stale Action Expiry Logic

```python
# auto_rebalancer.py:2142-2200
_STATE_TIMEOUTS_MIN = {
    'in_progress': 45,
    'waiting_agent': 10,
    'waiting_for_spot_node': 28,   # ≤ spot_join_timeout_minutes (30 min)
    'cordoning_node': 10,
    'draining_pods': 20,
    'verifying_pod_readiness': 20,
    'terminating_source': 10,
}

# Also checks action_heartbeat Redis key — if heartbeat stopped >2 min ago,
# the action is considered stale regardless of elapsed time.
_hb_age = datetime.utcnow().timestamp() - _hb_ts
if _hb_age > 120:  # heartbeat stopped >2 min ago
    _stale_actions.append(_ra_check)
```

---

## 4. Safety Gates (Pre-Execution)

**File:** `auto_rebalancer.py:667-798`

Before ANY work begins, `execute_rebalancing_action()` enforces 5 sequential safety gates:

### Gate 1: Cluster Cooldown
```python
# auto_rebalancer.py:688-698
_cooldown_key = key_cluster_cooldown(action.cluster_id)
if _redis.exists(_cooldown_key):
    action.status = 'deferred'  # Retry next cycle
    return
```

### Gate 2: Concurrency Lock (Per-Cluster)
```python
# auto_rebalancer.py:706-741
_lock_key = key_rebalance_lock(action.cluster_id)  # "rebalance:lock:{cluster_id}"
_lock_acquired = _redis.set(_lock_key, str(action.id), nx=True, ex=2700)  # 45-min TTL

# Background heartbeat thread renews lock every 60s:
def _heartbeat_cluster_lock(_r, _k, _stop, _aid):
    while not _stop.wait(60):
        _cur = _r.get(_k)
        if _cur == str(_aid):
            _r.expire(_k, 2700)
        else:
            break  # Lock stolen by another action
```

### Gate 3: Stabilization Lock
```python
# auto_rebalancer.py:745-756
is_locked, remaining = _cooldown.is_stabilization_locked(action.cluster_id)
if is_locked:
    action.status = 'deferred'
    return
```

### Gate 4: Substitute Mutual Exclusion
```python
# auto_rebalancer.py:758-771
sub_state = _redis.get(f"spot:substitute:state:{action.cluster_id}")
if sub_state in ("PREWARMING", "RELEASING"):
    action.status = 'deferred'  # Don't drain while substitute is mid-flight
    return
```

### Gate 5: Resize Cooldown
```python
# auto_rebalancer.py:773-783
if _redis.exists(f"spot:cooldown:action:resize:{action.cluster_id}"):
    action.status = 'deferred'  # Right-sizing just executed
    return
```

### Double-Launch Guard
```python
# auto_rebalancer.py:785-798
_existing_replacement = metadata.get('replacement_spot_instance_id')
if _existing_replacement:
    action.status = 'waiting_agent'  # Phase 1 already ran
    return
```

---

## 5. Phase 1 — Provision Spot Node via Karpenter

> Phase 1 ensures a replacement spot node exists BEFORE draining the source node.
> This prevents the "blast-radius" problem of removing capacity without a replacement.

### Step 5.1: Candidate Instance Type Selection

**File:** `auto_rebalancer.py:950-1067`

```python
# Use pre-computed ranked_alternatives from action metadata (set by termination_monitor)
_pre_ranked = metadata.get('ranked_alternatives', [])
ml_instance_types = list(_pre_ranked)[:8]

# Fallback: re-rank via PoolRankingService if no pre-computed list
_ranked_ml = PoolRankingService(db, _redis).rank_pools_for_node(
    node_info={
        'instance_type': source_instance_type,
        'az': target_az,
        'od_price': _od_price_rb,
        'resource_profile': {
            'min_vcpu_required': _specs_rb[0],
            'min_memory_required': float(_specs_rb[1]),
            'architecture': _src_arch_rb,
        },
    },
    cluster_id=action.cluster_id,
    region=cluster.region,
    include_dynamic_filters=True,
)
```

### Step 5.2: No-Join Block Filter

```python
# auto_rebalancer.py:1035-1062
# Removes instance types that previously failed to join K8s
ml_instance_types = [
    t for t in ml_instance_types
    if not _blk_redis.get(f"spot:launch_blocked:{action.cluster_id}:{t}:{target_az}")
]
```

### Step 5.3: Architecture Filter

```python
# auto_rebalancer.py:1084-1176
_ARM64_FAMILIES = {'t4g', 'c6g', 'c7g', 'c8g', 'm6g', 'm7g', ...}

# 3-tier arch detection:
# 1. EC2 DescribeInstanceTypes API (7-day Redis cache)
# 2. ClusterOptimizationSettings.architecture_preference
# 3. Node template constraints
_source_arch = _get_instance_arch(_ec2, source_instance_type, _ARM64_FAMILIES, _region)
```

### Step 5.4: ASG Detection (Pre-Step)

```python
# auto_rebalancer.py:859-938
# Detect whether the source OD node belongs to an Auto Scaling Group
_asg_name = get_asg_for_instance(instance_id, _region, _asg_creds)

if _asg_name:
    metadata['asg_name_used'] = _asg_name
    # Phase 2 will use "scaledown" termination mode:
    #   terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=True)
    # This prevents ASG from auto-healing (launching a new OD to replace terminated one)
```

### Step 5.5: Dry-Run Capacity Validation

```python
# auto_rebalancer.py:1227-1286
# Parallel dry-runs: cached hits + uncached checks via ThreadPoolExecutor
def _dr_check(itype):
    return itype, dry_run_pool(region, instance_type=itype, az=target_az, redis=_redis)

with ThreadPoolExecutor(max_workers=5) as _dr_executor:
    _dr_futures = [_dr_executor.submit(_dr_check, t) for t in _dr_uncached]
    for _dr_f in as_completed(_dr_futures):
        _dr_t, _dr_ok = _dr_f.result()
        if _dr_ok:
            _verified_types.append(_dr_t)

if not _verified_types:
    action.status = 'failed'
    action.error_message = f"Dry run: no capacity in {target_az}"
    return
```

### Step 5.6: Karpenter NodePool Patch

**File:** `karpenter_service.py:999-1137`

```python
# auto_rebalancer.py:1288-1342
for _kp_itype in ml_instance_types[:8]:
    _kp_result, _kp_np_names = _karp_svc.add_allowed_instance_type_all_spot(
        cluster_id=action.cluster_id,
        instance_type=_kp_itype,
    )
    if _kp_result:
        _nodepool_updated = True
        break

# NodePool PATCH retries (up to 3 attempts with defer between cycles):
if not _nodepool_updated:
    if _np_retry < 3:
        action.status = 'deferred'  # Retry next Celery cycle
        return
    action.status = 'failed'
    return
```

#### How `add_allowed_instance_type` works:

```python
# karpenter_service.py:999-1137
def add_allowed_instance_type(self, cluster_id, instance_type, nodepool_name="default"):
    # 1. Read current NodePool via K8s API
    nodepool = custom_api.get_cluster_custom_object(
        group="karpenter.sh", version="v1", plural="nodepools", name=nodepool_name
    )

    # 2. Find instance-type requirement in spec.template.spec.requirements
    for req in requirements:
        if req.get('key') == 'node.kubernetes.io/instance-type':
            values = set(req.get('values', []))
            if instance_type in values:
                return True  # Already present — idempotent
            values.add(instance_type)
            req['values'] = sorted(values)
            break

    # 3. Sync kubernetes.io/arch with derived architectures
    # (prevents arm64 types in amd64-only NodePools)

    # 4. PATCH the NodePool
    custom_api.patch_cluster_custom_object(
        group="karpenter.sh", version="v1", plural="nodepools",
        name=nodepool_name, body=patch_body,
    )

    # 5. Read-back verification — confirm patch took effect
    verified_np = custom_api.get_cluster_custom_object(...)
    if instance_type not in _verified_types:
        return False  # VERIFICATION FAILED
    return True
```

### Step 5.7: Trigger Pod Creation

**File:** `karpenter_service.py:1259-1383`

The trigger pod is a lightweight `busybox:sleep` pod that forces Karpenter to provision a new node:

```python
# karpenter_service.py:1259-1383
def create_spot_trigger_pod(self, cluster_id, pod_name, target_instance_type, ...):
    node_selector = {
        "karpenter.sh/capacity-type": "spot",
        "karpenter.sh/nodepool": nodepool_name,
    }
    if target_instance_type:
        node_selector["node.kubernetes.io/instance-type"] = target_instance_type

    # Anti-affinity: exclude existing nodes (label spot-optimizer.io/existing-node=true)
    node_affinity = V1NodeAffinity(
        required_during_scheduling_ignored_during_execution=V1NodeSelector(
            node_selector_terms=[V1NodeSelectorTerm(
                match_expressions=[V1NodeSelectorRequirement(
                    key="spot-optimizer.io/existing-node",
                    operator="DoesNotExist",
                )],
            )],
        ),
    )

    pod = V1Pod(
        spec=V1PodSpec(
            node_selector=node_selector,
            containers=[V1Container(
                name="trigger",
                image="public.ecr.aws/docker/library/busybox:latest",
                command=["sleep", "3600"],
                resources=V1ResourceRequirements(
                    requests={"cpu": cpu_request, "memory": memory_request},
                ),
            )],
        ),
    )
    v1.create_namespaced_pod(namespace="default", body=pod)
```

### Step 5.8: Record Spot Baseline

```python
# auto_rebalancer.py:1407-1422
# Record spot count BEFORE Phase 1 so Phase 2 can detect NEW spot nodes
_baseline_spots = db.query(Instance).filter(
    Instance.cluster_id == action.cluster_id,
    Instance.lifecycle == InstanceLifecycle.SPOT,
    Instance.state == 'running',
).all()
_meta_update['spot_baseline_count'] = len(_baseline_spots)
_meta_update['baseline_spot_instance_ids'] = [s.instance_id for s in _baseline_spots]

# Action status → waiting_agent
action.status = 'waiting_agent'
action.current_state = 'WAITING_FOR_KARPENTER'
```

---

## 6. Spot Wait Loop (WAITING_FOR_KARPENTER)

> After Phase 1, the rebalancer enters a polling loop (every 15s Celery cycle)
> waiting for a new spot node to appear in the cluster.

**File:** `auto_rebalancer.py:2800-3578` (Step 0 of the waiting_agent processing loop)

### Detection: New Spot Node Joined

```python
# The rebalancer compares current spot count against the Phase 1 baseline:
_spot_count = db.query(Instance).filter(
    Instance.cluster_id == _wa.cluster_id,
    Instance.lifecycle == InstanceLifecycle.SPOT,
    Instance.state == 'running',
).count()

_spot_baseline = _wa_meta.get('spot_baseline_count', 0)

# New spot detected via either:
# 1. Count increased: spot_count > spot_baseline
# 2. Set-diff: new instance_id not in baseline_spot_instance_ids (for baseline=0)
_new_spot_joined = (_spot_count > _spot_baseline) or _set_diff_detected
```

### Readiness Gate (Post-Join)

```python
# 10-second minimum floor after new node detected
# Multi-condition check:
#   1. Node has a K8s node_name (joined the cluster)
#   2. 10-second floor timer elapsed
#   3. Node status is Ready
#   4. Instance lifecycle confirmed as SPOT in AWS
```

### Trigger Pod Health Monitoring

```python
# auto_rebalancer.py:3165-3222
# During the wait loop, the rebalancer monitors trigger pod health:
# - Missing → recreate immediately
# - Failed → delete and recreate
# - Pending > 5 min → re-verify NodePool has target type
```

### Atomic Replacement Claim

```python
# auto_rebalancer.py:3380-3403
# Prevent two actions from sharing one replacement node:
_claim_key = f"spot:replacement_claimed:{_claim_inst_id}"
_claimed = _redis.set(_claim_key, str(_wa.id), nx=True, ex=3600)
if not _claimed:
    # Another action already claimed this node → keep waiting
    _new_spot_joined = False
    continue
```

### Timeout Handling

```python
# auto_rebalancer.py:3462-3578
_SPOT_WAIT_TIMEOUT_S = 1800  # 30 minutes default

if _spot_wait_elapsed >= _SPOT_WAIT_TIMEOUT_S:
    # Karpenter timeout — check safety before proceeding:
    
    if _other_running == 0:
        # REFUSE to drain last node without replacement
        action.status = 'failed'
        action.error_message = "No replacement AND no other nodes — abort"
        return
    
    # Even with other nodes: FAIL the action (don't risk cluster shrink)
    action.status = 'failed'
    action.error_message = "Karpenter spot provisioning timed out — investigate NodeClaim"
    return
```

---

## 7. Phase 2 — CORDON → DRAIN → TERMINATE

> Once a new spot node is confirmed, Phase 2 creates three sequential `AgentAction` records.

**File:** `auto_rebalancer.py:3580-3772`

### Pre-Flight Checks

```python
# 1. Determine termination mode:
if _p2_asg_name:
    _p2_term_mode = "scaledown"  # ASG-backed: terminate_in_asg(DecrementDesired=True)
else:
    _p2_term_mode = "karpenter"  # Karpenter-managed: standard EC2 terminate

# 2. Verify source node exists in K8s:
_k8s_nodes = _core_v1.list_node()
if _p2_node_name not in {n.metadata.name for n in _k8s_nodes.items}:
    if _p2_asg_for_ghost:
        _p2_skip_cordon_drain = True  # "Ghost node" — skip to terminate
    else:
        action.status = 'failed'
        return

# 3. Protect replacement node from Karpenter consolidation:
#    Apply karpenter.sh/do-not-disrupt=true annotation
_kp_annotate = AgentAction(
    action_type=AgentActionType.LABEL_NODE,
    payload={
        "node_name": _newest_spot.node_name,
        "annotations": {"karpenter.sh/do-not-disrupt": "true"},
    },
)
```

### Phase 2 Agent Action Creation

```python
# auto_rebalancer.py:3716-3771

# PDB respect check:
_srr = db.query(StatelessRuntimeRules).filter_by(cluster_id=_wa.cluster_id).first()
_n1_force_drain = not getattr(_srr, 'respect_pdb_enabled', False)

# Step 2: CORDON_NODE
cordon_p2 = AgentAction(
    cluster_id=_wa.cluster_id,
    action_type=AgentActionType.CORDON_NODE,
    payload={
        "instance_id": _p2_instance_id,
        "node_name": _p2_node_name,
        "rebalancing_action_id": str(_wa.id),
        "zero_downtime_step": 2,
    }
)

# Step 3: DRAIN_NODE
drain_p2 = AgentAction(
    cluster_id=_wa.cluster_id,
    action_type=AgentActionType.DRAIN_NODE,
    payload={
        "instance_id": _p2_instance_id,
        "node_name": _p2_node_name,
        "ignore_daemonsets": True,
        "grace_period_seconds": 60,
        "force": _n1_force_drain,  # True = ignore PDB (legacy), False = respect PDB
        "rebalancing_action_id": str(_wa.id),
        "zero_downtime_step": 3,
    }
)

# Step 4: TERMINATE_NODE
terminate_p2 = AgentAction(
    cluster_id=_wa.cluster_id,
    action_type=AgentActionType.TERMINATE_NODE,
    payload={
        "instance_id": _p2_instance_id,
        "termination_mode": _p2_term_mode,  # "scaledown" or "karpenter"
        "asg_name": _wa_meta.get("asg_name_used"),
        "rebalancing_action_id": str(_wa.id),
        "zero_downtime_step": 4,
    }
)

db.add(cordon_p2)
db.add(drain_p2)
db.add(terminate_p2)
```

### Ghost Node Fast-Path

```python
# auto_rebalancer.py:3670-3702
# When the source node is NOT in K8s but EC2 is still running (zombie):
# Skip CORDON/DRAIN → create TERMINATE-only action
if _p2_skip_cordon_drain:
    terminate_ghost = AgentAction(
        action_type=AgentActionType.TERMINATE_NODE,
        payload={
            "instance_id": _p2_instance_id,
            "termination_mode": "scaledown",
            "ghost_node": True,
        }
    )
```

---

## 8. Agent-Side Execution

### 8.1 Action Dispatch (WebSocket)

**File:** `agent/websocket_client.py`

```python
# The backend sends AgentActions via WebSocket as JSON messages.
# The agent's websocket_client receives them and dispatches to actuator:

async def _handle_action(self, action_data):
    action_type = action_data['action_type']
    if action_type == 'CORDON_NODE':
        result = await self.actuator.cordon_node(action_data['payload'])
    elif action_type == 'DRAIN_NODE':
        result = await self.actuator.drain_node(action_data['payload'])
    elif action_type == 'TERMINATE_NODE':
        result = await self.actuator._terminate_node(action_data['payload'])

    # Results go into the CRITICAL message queue (unbounded, never dropped):
    self._critical_queue.put_nowait(result)
```

### 8.2 cordon_node()

**File:** `agent/actuator.py`

```python
async def cordon_node(self, payload):
    node_name = payload.get('node_name')

    # Self-cordon detection: if this agent is running ON the target node,
    # cordon would kill the agent → abort with SELF_CORDON_ATTEMPT
    if node_name == self._self_node_name:
        return {"success": False, "error": "SELF_CORDON_ATTEMPT"}

    # Cordon via K8s API:
    body = {"spec": {"unschedulable": True}}
    v1.patch_node(node_name, body)
    return {"success": True, "node_name": node_name}
```

### 8.3 drain_node() — PDB-Aware

**File:** `agent/actuator.py`

```python
async def drain_node(self, payload):
    node_name = payload['node_name']
    force = payload.get('force', True)
    grace_period = payload.get('grace_period_seconds', 60)
    ignore_daemonsets = payload.get('ignore_daemonsets', True)

    # 1. Get all pods on the node
    pods = v1.list_pod_for_all_namespaces(
        field_selector=f"spec.nodeName={node_name}"
    )

    # 2. Filter: skip DaemonSet pods, mirror pods, completed pods
    evictable = [
        p for p in pods.items
        if not _is_daemonset(p) and not _is_mirror(p) and not _is_completed(p)
    ]

    # 3. Evict each pod (PDB-aware eviction API):
    for pod in evictable:
        eviction = V1Eviction(
            metadata=V1ObjectMeta(name=pod.metadata.name, namespace=pod.metadata.namespace),
            delete_options=V1DeleteOptions(grace_period_seconds=grace_period),
        )
        try:
            v1.create_namespaced_pod_eviction(
                name=pod.metadata.name,
                namespace=pod.metadata.namespace,
                body=eviction,
            )
        except ApiException as e:
            if e.status == 429:  # PDB violation
                if force:
                    v1.delete_namespaced_pod(pod.metadata.name, pod.metadata.namespace)
                else:
                    raise  # Respect PDB — abort drain

    # 4. Wait for pods to terminate (with timeout)
    # 5. Clean up stuck VolumeAttachments
    _cleanup_volume_attachments(node_name)

    return {"success": True, "pods_evicted": len(evictable)}
```

### 8.4 _terminate_node()

**File:** `agent/actuator.py`

```python
async def _terminate_node(self, payload):
    instance_id = payload['instance_id']
    mode = payload.get('termination_mode', 'karpenter')

    if mode == 'scaledown':
        # ASG-backed node: terminate + decrement desired capacity
        asg_client.terminate_instance_in_auto_scaling_group(
            InstanceId=instance_id,
            ShouldDecrementDesiredCapacity=True,
        )
    elif mode == 'karpenter':
        # Karpenter-managed: delete K8s Node object → Karpenter handles EC2
        try:
            v1.delete_node(name=node_name)
        except ApiException:
            pass
        # Also directly terminate EC2 as safety net:
        ec2.terminate_instances(InstanceIds=[instance_id])
    elif mode == 'replacement':
        # Detach from ASG (no decrement) + terminate EC2
        asg_client.detach_instances(
            AutoScalingGroupName=asg_name,
            InstanceIds=[instance_id],
            ShouldDecrementDesiredCapacity=False,
        )
        ec2.terminate_instances(InstanceIds=[instance_id])
```

---

## 9. Post-Drain Readiness Verification

**File:** `auto_rebalancer.py:3797-3876`

After drain completes, the rebalancer enforces a grace period before EC2 termination:

```python
# 20-second minimum grace period (spot stabilization wait already happened)
_READINESS_GRACE_S = 20

# Configurable max wait (default 15 min, per ClusterOptimizationSettings):
_drain_timeout_min = _cos_dt.drain_timeout_minutes  # default: 15
_READINESS_MAX_S = _drain_timeout_min * 60

# Check: are any pods still on the old node?
_pods_stuck = db.query(PodMetric).filter(
    PodMetric.cluster_id == _wa.cluster_id,
    PodMetric.node_name == _drained_inst_rd,
    PodMetric.timestamp >= datetime.utcnow() - timedelta(minutes=2),
).count() > 0

if _pods_stuck and _post_drain_elapsed < _READINESS_MAX_S:
    continue  # Keep waiting
elif _pods_stuck and _post_drain_elapsed >= _READINESS_MAX_S:
    # Timeout: K8s node already deleted; can't uncordon → proceed to EC2 terminate
    logger.warning("Pod readiness timeout — proceeding to EC2 terminate")

# Mark readiness verified:
_wa_meta['readiness_verified'] = True
```

---

## 10. EC2 Termination

EC2 termination is handled by the agent via the `TERMINATE_NODE` agent action (see [Section 8.4](#84-_terminate_node)).

The backend monitors the `TERMINATE_NODE` action status:

```python
# When all Phase 2 actions (CORDON + DRAIN + TERMINATE) are COMPLETED:
_completed = db.query(AgentAction).filter(
    AgentAction.payload.contains({"rebalancing_action_id": _wa.id}),
    AgentAction.status == AgentActionStatus.COMPLETED,
).count()

if _completed >= 3:  # All steps done
    _wa.status = 'completed'
    _wa.completed_at = datetime.utcnow()
    _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
```

---

## 11. Completion & Cleanup

**File:** `auto_rebalancer.py:1958-2066`

`_cleanup_rebalancing_resources()` is called on EVERY exit path (success, failure, defer):

```python
def _cleanup_rebalancing_resources(wa, wa_meta, redis_client, db, *, decr_semaphore=True):
    # 1. Delete per-node active action lock
    redis_client.delete(f"spot:node_active_action:{_inst_id}")

    # 2. DECR concurrent action semaphore (floor at 0)
    _new_val = redis_client.decr(f"rebalance:active_count:{wa.cluster_id}")
    if _new_val < 0:
        redis_client.set(_sem_key, 0, ex=300)

    # 3. Delete trigger pod from K8s
    _ks.delete_spot_trigger_pod(cluster_id=wa.cluster_id, pod_name=_trig_name)

    # 4. Cancel orphaned PENDING agent actions
    db.query(AgentAction).filter(
        AgentAction.payload.contains({"rebalancing_action_id": wa.id}),
        AgentAction.status == AgentActionStatus.PENDING,
    ).update({"status": "FAILED", "error_message": "Cancelled: parent action failed"})

    # 5. Release replacement-instance claim
    redis_client.delete(f"spot:replacement_claimed:{_repl_inst}")

    # 6. NodePool rollback: remove Phase-1-injected instance types
    for _rm_type in _kp_target_types:
        for _rm_np in _kp_patched_nps:
            _ks.remove_allowed_instance_type(
                cluster_id=wa.cluster_id,
                instance_type=_rm_type,
                nodepool_name=_rm_np,
            )

    # 7. Clear NodePool sync cooldown
    redis_client.delete(f"spot:karpenter:nodepool_updated:{wa.cluster_id}")
```

---

## 12. Failure Recovery & Rollback

### CORDON Failure → Full Rollback

```python
# auto_rebalancer.py:3938-3965
# If CORDON failed and DRAIN never ran:
if _cordon_node_failed and not _drain_attempted:
    _do_rollback_uncordon_and_terminate(wa, wa_meta, db)
    # → Queue UNCORDON_NODE to restore schedulability
    # → Terminate orphan spot instance

    # Special case: CORDON_NODE returned NOT_FOUND (404)
    # → K8s node is gone, EC2 is a zombie → terminate directly
```

### DRAIN Failure → Partial Rollback

```python
# If DRAIN failed but CORDON succeeded:
# → Queue UNCORDON_NODE on the source node
# → Terminate the orphan spot replacement
# → Source node restored to schedulable state
```

### TERMINATE Already Completed (Parallel Agent)

```python
# auto_rebalancer.py:3906-3936
# Edge case: agent executed TERMINATE before DRAIN completed (parallel execution)
if _term_already_done:
    # OD node is GONE — no rollback possible
    _wa.status = 'completed'  # Mark as partial success
    _wa.error_message = f"{_failed} steps failed but TERMINATE succeeded"
```

### Self-Cordon Attempt

```python
# auto_rebalancer.py:3955-3965
# Agent is running ON the node being drained → forced cordon-only rollback
if 'SELF_CORDON_ATTEMPT' in _cordon_err:
    _drain_attempted = False  # Override: treat as cordon-only failure
```

### Orphan Spot Termination

**File:** `auto_rebalancer.py:1856-1951`

```python
def _do_rollback_terminate_orphan_spot(wa, wa_meta, db):
    # 1. Find orphan by explicit ID or newest SPOT since action started
    _orphan_id = wa_meta.get('replacement_spot_instance_id')

    # 2. Terminate via EC2 API using assumed credentials
    _spot_ec2.terminate_instances(InstanceIds=[_terminate_id])

    # 3. Clear associated Redis keys
    _redis.delete(f"spot:asserted_spot:{_terminate_id}")
    _redis.delete(f"spot:node_active_action:{_terminate_id}")
```

---

## 13. Escalation Logic

**File:** `auto_rebalancer.py:3244-3355`

When `spot_count=0` and `baseline=0` (no spot nodes exist), the trigger pod may be stuck Pending because Karpenter can't get capacity. Progressive escalation:

```
Timeline:
  0 min  → Initial trigger pod created with ML-ranked #1 type
  5 min  → ESCALATION ALT1: Switch to #2 ranked alternative type
  10 min → ESCALATION ALT2: Switch to #3 ranked alternative type
  15 min → ESCALATION BROAD: Remove instance-type constraint entirely
                              (let Karpenter choose from entire NodePool)
  30 min → TIMEOUT: Fail the action
```

```python
_ESC_ALT1_S = 300   # 5 min
_ESC_ALT2_S = 600   # 10 min
_ESC_BROAD_S = 900  # 15 min

if _esc_action_needed == 'broad':
    _esc_type = ''  # No constraint — Karpenter picks ANY type
elif _esc_action_needed == 'alt2':
    _esc_type = _ranked_alts[2]
else:
    _esc_type = _ranked_alts[1]

# Delete current trigger pod and create new one with escalated type:
_core_esc.delete_namespaced_pod(_trig_del_name, 'default')
_ks_esc.create_spot_trigger_pod(
    cluster_id=_wa.cluster_id,
    pod_name=_trig_del_name,
    target_instance_type=_esc_type,
    nodepool_name=_trig_nodepool_esc,
    exclude_nodes=_existing_esc,
)
```

---

## 14. State Machine

**File:** `auto_rebalancer.py:33-98`

```python
SM_CREATED               = 'CREATED'
SM_POOL_SELECTED         = 'POOL_SELECTED'
SM_SOURCE_CORDONED       = 'SOURCE_CORDONED'
SM_SOURCE_DRAINED        = 'SOURCE_DRAINED'
SM_REPLACEMENT_LAUNCHING = 'REPLACEMENT_LAUNCHING'
SM_REPLACEMENT_READY     = 'REPLACEMENT_READY'
SM_SOURCE_TERMINATING    = 'SOURCE_TERMINATING'
SM_COMPLETED             = 'COMPLETED'
SM_FAILED                = 'FAILED'
SM_DRAIN_TIMEOUT         = 'DRAIN_TIMEOUT'
```

### Optimistic Locking Transitions

```python
def _sm_transition(db, action_id, from_state, to_state, max_retries=2):
    """Atomic state transition using UPDATE ... WHERE current_state = from_state"""
    result = db.execute(text(
        "UPDATE rebalancing_actions SET current_state = :to_state "
        "WHERE id = :action_id AND current_state = :from_state"
    ))
    if result.rowcount == 1:
        return True   # Transition succeeded
    # Retry with backoff (100ms, 200ms):
    # If another worker already advanced past from_state → return False
```

### Lifecycle Flow

```
┌─────────┐     ┌──────────────────┐     ┌─────────────────────┐
│ CREATED │────▶│ POOL_SELECTED    │────▶│ REPLACEMENT_LAUNCHING│
└─────────┘     └──────────────────┘     └──────────┬──────────┘
                                                     │
                              ┌───────────────────────┘
                              ▼
                    ┌──────────────────┐
                    │ REPLACEMENT_READY│ (spot node joined K8s)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ SOURCE_CORDONED  │ (CORDON_NODE completed)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ SOURCE_DRAINED   │ (DRAIN_NODE completed)
                    └────────┬─────────┘
                             │
                    ┌────────▼──────────┐
                    │ SOURCE_TERMINATING│ (TERMINATE_NODE sent)
                    └────────┬──────────┘
                             │
                    ┌────────▼────────┐
                    │ COMPLETED       │
                    └─────────────────┘

         Any state ──── error ────▶ FAILED
```

---

## 15. Redis Key Reference

| Key Pattern | TTL | Purpose |
|------------|-----|---------|
| `lock:workers.auto_rebalancer` | 300s (heartbeat) | Global Celery task lock |
| `rebalance:lock:{cluster_id}` | 2700s (heartbeat) | Per-cluster concurrency lock |
| `spot:node_active_action:{instance_id}` | 24h | Per-node lock (prevents parallel actions on same node) |
| `rebalance:active_count:{cluster_id}` | 300s | Concurrent action semaphore |
| `spot:replacement_claimed:{instance_id}` | 3600s | Atomic claim on replacement node |
| `spot:launch_blocked:{cluster_id}:{type}:{az}` | 1800s | No-join timeout block |
| `spot:cooldown:action:resize:{cluster_id}` | varies | Resize cooldown |
| `spot:substitute:state:{cluster_id}` | varies | Substitute manager state |
| `karpenter:live_status:{cluster_id}` | 120s | Agent-reported Karpenter health |
| `spot:karpenter:installed:{cluster_id}` | 3600s | Cached Karpenter detection |
| `karpenter:detected:{cluster_id}` | 120s | Short-term detection cache |
| `spot:karpenter:nodepool_updated:{cluster_id}` | varies | NodePool sync cooldown |
| `dry_run:{type}:{az}` | varies | Dry-run capacity cache |
| `instance_type_arch:{type}` | 7 days | Architecture detection cache |
| `action_heartbeat:{action_id}` | varies | Action liveness heartbeat |
| `spot:skip_streak:{cluster_id}` | 300s | Skip streak counter |

---

## Summary: End-to-End Timeline

```
T+0s     │ Celery Beat fires execute_rebalancing()
         │ → Acquires HeartbeatLock
         │ → Checks stale actions
         │ → Picks up in_progress RebalancingAction
         │
T+0.1s   │ Safety Gates (5 checks)
         │ ├── Cluster cooldown?
         │ ├── Concurrency lock?
         │ ├── Stabilization lock?
         │ ├── Substitute in-flight?
         │ └── Resize cooldown?
         │
T+0.5s   │ Phase 1: Candidate selection
         │ ├── ML-ranked instance types
         │ ├── No-join block filter
         │ ├── Architecture filter
         │ └── Dry-run capacity validation
         │
T+2s     │ ASG Detection (source node)
         │
T+5s     │ NodePool PATCH (add target type)
         │ + Read-back verification
         │
T+8s     │ Trigger Pod Created
         │ ├── nodeSelector: karpenter.sh/capacity-type=spot
         │ ├── nodeSelector: node.kubernetes.io/instance-type=<target>
         │ └── Anti-affinity: exclude existing nodes
         │
T+8s     │ → Action status = waiting_agent
         │ → State = WAITING_FOR_KARPENTER
         │
T+15s+   │ Spot Wait Loop (every 15s Celery cycle)
         │ ├── Check: spot_count > baseline?
         │ ├── Check: trigger pod healthy?
         │ ├── Escalation at 5/10/15 min
         │ └── Timeout at 30 min
         │
T+~3min  │ New spot node joins K8s
         │ ├── Readiness gate (10s floor)
         │ ├── Atomic replacement claim (Redis SET NX)
         │ ├── Protect replacement: do-not-disrupt=true
         │ └── Delete trigger pod
         │
T+~3.5m  │ Phase 2: Create CORDON → DRAIN → TERMINATE actions
         │
T+~4min  │ Agent executes CORDON_NODE
         │ └── node.spec.unschedulable = true
         │
T+~4.5m  │ Agent executes DRAIN_NODE
         │ ├── PDB-aware pod eviction
         │ ├── DaemonSet pods skipped
         │ └── VolumeAttachment cleanup
         │
T+~5min  │ Post-drain readiness verification (20s grace)
         │ └── Check: pods still on old node?
         │
T+~5.5m  │ Agent executes TERMINATE_NODE
         │ ├── scaledown: terminate_in_asg(DecrementDesired=True)
         │ └── karpenter: delete K8s node + EC2 terminate
         │
T+~6min  │ Completion & Cleanup
         │ ├── Delete per-node lock
         │ ├── DECR semaphore
         │ ├── Remove Phase-1 types from NodePool
         │ ├── Clear sync cooldown
         │ └── Release replacement claim
         │
         ▼ ACTION STATUS = COMPLETED
```

---

## Appendix: Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Provision-then-drain** (not drain-then-provision) | Prevents blast-radius: never remove capacity without confirmed replacement |
| **45-min lock TTL + heartbeat** | Actions can take 30+ min; fixed TTL caused lock expiry & races |
| **Trigger pod with anti-affinity** | Forces Karpenter to provision a NEW node, not reuse existing |
| **Atomic replacement claim** | Prevents two concurrent actions from "sharing" one spot node |
| **ASG scaledown mode** | When source is ASG-backed, decrement desired count to prevent auto-heal |
| **NodePool rollback on failure** | Prevents Karpenter from provisioning orphan types during normal scaling |
| **3-observation RC3 guard** | Prevents false SPOT→OD lifecycle flips on transient AWS API gaps |
| **Progressive escalation** | 5→10→15 min alternative types when primary capacity unavailable |
| **Ghost node fast-path** | Skip cordon/drain for nodes not in K8s but EC2 still running |
