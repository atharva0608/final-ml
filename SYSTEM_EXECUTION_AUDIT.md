# SYSTEM EXECUTION AUDIT — Spot Optimizer Platform
**Generated**: 2026-04-27 | **Schema**: v11.0 — T-09→T-24 Spot Optimizer Real Data Integration complete; 3 new DB tables; 3 new Alembic migrations; 2 new Celery tasks; 8 new /optimize API endpoints; 5 validation fixes applied; reliability score 8.5/10

---

# PART A: ANSWERS TO ARCHITECTURE QUESTIONS

## Q1: Agent Capabilities (Ground Truth from `AgentActionType` enum)

**File**: `backend/models/agent_action.py` lines 12-34

The agent currently supports **14 action types** via the `AgentActionType` enum:

| # | Action | Enum Value | Status |
|---|--------|-----------|--------|
| ✅ (a) | Cordon node | `CORDON_NODE` | Active — used by auto_rebalancer state machine |
| ✅ (b) | Drain node | `DRAIN_NODE` | Active — used by auto_rebalancer state machine |
| ✅ (c) | Terminate instance | `TERMINATE_NODE` | Active — "Terminate EC2 instance after drain so Karpenter sees Pending pods" |
| ✅ (d) | Evict specific pod | `EVICT_POD` | Active — used by PlacementController + anchored_node_service |
| ✅ (e) | Scale Deployment/StatefulSet | `UPDATE_DEPLOYMENT` | Active — used for deployment updates |
| ❌ (f) | Query pod placement (AZ, capacity type) | *Not an action type* | Agent reports this via metrics ingestion (`POST /metrics/batch`), NOT via AgentAction |

**Additional agent capabilities NOT in the user's list:**
- `LABEL_NODE` — used by WorkloadInspector and AnchoredNodeService
- `INSTALL_KARPENTER` / `UNINSTALL_KARPENTER` — Karpenter lifecycle
- `INSTALL_KEDA` / `UNINSTALL_KEDA` — KEDA lifecycle via Helm
- `PATCH_CONTAINER_RESOURCES` — rightsizing CPU/memory requests+limits
- `UNCORDON_NODE` — activate standby during emergency
- `FORCE_DELETE_NODE` — ghost/hardware-failed nodes
- `REMOVE_POD_FINALIZERS` — stuck finalizers on Terminating pods
- `ANNOTATE_WORKLOAD` — tier-override annotations
- `PATCH_AFFINITY` — nodeAffinity patch to pod templates

**Agent polling mechanism**: `GET /clusters/{cluster_id}/actions/pending` → returns up to 10 PENDING actions ordered by `priority DESC, created_at ASC`. Agent marks them `PICKED_UP`, executes, then reports via `POST /agents/actions/{id}/result`.

---

## Q2: PlacementController Redis Queue Consumer

**Status: RESOLVED (as of v6.0 / 2026-04-23).**

The dead-letter Redis queue (`spot:placement_controller:action_queue:{cluster_id}`) has been fully replaced. `_create_evict_pod_action()` (Redis `rpush`) was replaced with two DB-write functions:

| Function | File | What It Does |
|----------|------|--------------|
| `_dispatch_eviction()` | `placement_controller_service.py` | Creates `AgentAction(type=EVICT_POD)` + linked `RebalancingAction(source='placement_controller')` in PostgreSQL |
| `_dispatch_stateful_rollout()` | `placement_controller_service.py` | Creates `RebalancingAction(migration_type='stateful_pod')` — auto_rebalancer picks it up |

**Agent visibility is now complete**: The agent polls `GET /clusters/{id}/actions/pending` which queries the `AgentAction` table. `EVICT_POD` records from the PlacementController are now fully visible to, and executed by, the in-cluster agent.

**Visibility chain**: `PlacementController` → `AgentAction` DB record → Agent polls → `agent/actuator.py` calls K8s Eviction API → Reports result via `POST /agents/actions/{id}/result` → `handle_eviction_result()` validates placement.

---

## Q3: Node-Level vs Pod-Level Architecture Decision

**Current state — both engines operational, execution paths unified through `AgentAction` table:**

| Attribute | Engine A (auto_rebalancer) | Engine B (PlacementController) |
|-----------|---------------------------|-------------------------------|
| Granularity | Entire EC2 node replacement | Individual pod eviction |
| Action path | `AgentAction` DB → agent polls → executes ✅ | `AgentAction` DB → agent polls → executes ✅ |
| State tracking | `RebalancingAction` table (6-state machine) | `RebalancingAction(source='placement_controller')` + `AgentAction.retry_count` |
| Karpenter integration | Patches NodePool, terminates old node → Karpenter provisions | Relies on Karpenter to reschedule evicted pods onto Spot |
| Cross-engine safety | `spot:cluster_mutex:{cluster_id}` (Redis SET NX, 60s TTL) | Same key — PC acquires during `run_cycle()`, AR skips cluster if held |
| Batch coordination | Shared `rebalance:active_count:{cluster_id}` Redis semaphore | PC increments on dispatch, decrements on COMPLETED/FAILED |
| Maturity | Production-grade (10,012 lines, full state machine) | Production-ready (v1.4 fully implemented, 17/17 tests pass) |

---

## Q4: Karpenter Configuration

**From `karpenter_service.py` lines 222, 793-812:**

**(a) Consolidation is enabled.** Default policy: `WhenEmptyOrUnderutilized`

**(b) Disruption policies configured:**

| Setting | Default Value | Source |
|---------|-------------|--------|
| `consolidationPolicy` | `WhenEmptyOrUnderutilized` | `_update_nodepool()` line 795 |
| `consolidateAfter` | `30s` | `_update_nodepool()` line 798 |
| `expireAfter` | `720h` (30 days) | `switch_to_ondemand()` line 223 |

**Behavior**: When updating a NodePool, the service **preserves existing disruption settings** if no override is passed. It only falls back to defaults for brand-new NodePools. The `_update_nodepool()` method (line 780-798) explicitly reads the existing NodePool's disruption block before applying changes.

**On-Demand Fallback**: When no safe spot pools exist, `switch_to_ondemand()` sets `capacity-type: on-demand` with a 12-hour Redis TTL (`spot:ondemand_fallback:{cluster_id}`). After TTL expires, `revert_to_spot()` patches back to `capacity-type: spot`.

---

## Q5: ASG vs Karpenter Future

**Current state — Hybrid, with Karpenter as the primary path:**

| Evidence | File | Detail |
|----------|------|--------|
| `karpenter_only_mode` column | `cluster.py` | Boolean toggle on `ClusterOptimizationSettings` |
| ASG suspend/resume logic | `execution_controller.py` lines 182-194 | Rollback restores ASG min_size |
| Karpenter-first provisioning | `emergency_rebalancer.py` line 188 | "Karpenter's `consolidationPolicy: WhenUnderutilized` + NodePool constraints" |
| `SubstituteManager` (ASG-era) | `scheduler.py` line 103 | Still active via APScheduler every 5 min |

**The codebase supports all three modes:**
- **(a) 100% Karpenter**: Set `karpenter_only_mode=True` → skips ASG code paths
- **(b) Hybrid**: Default — ASG manages base capacity, Karpenter handles spot scaling
- **(c) ASG primary**: Legacy path, still functional but not the recommended configuration

**`SubstituteManager`** is a pre-Karpenter construct that still runs every 5 minutes via APScheduler (`job_reconcile_substitutes`). It reconciles "stuck substitutes" — EC2 instances launched as replacements that never completed their lifecycle. This is legacy ASG-era code.

---

## Q6: Agent Communication Model

**The agent uses BOTH paths:**

| Channel | Direction | Protocol | Purpose |
|---------|-----------|----------|---------|
| WebSocket `/ws/cluster/{id}` | Bidirectional | WS | Real-time commands + metrics streaming |
| `POST /metrics/batch` | Agent → Backend | HTTP | Bulk node/pod metrics ingestion |
| `GET /actions/pending` | Agent → Backend | HTTP | Poll for pending `AgentAction` records |
| `POST /agents/actions/{id}/result` | Agent → Backend | HTTP | Report action completion/failure |
| `POST /agents/heartbeat` | Agent → Backend | HTTP | Health + Karpenter status detection |

**The agent does NOT call the Kubernetes API independently for optimization decisions.** It receives instructions via `AgentAction` records and executes them. However, the agent DOES interact with K8s API to:
1. Execute received actions (cordon, drain, evict, label, etc.)
2. Collect metrics (pod states, node capacity, AZ info) and report them back
3. Detect Karpenter presence (reported via heartbeat)

**Key detail from `routers/actions.py`**: The agent polls `GET /clusters/{id}/actions/pending` which returns up to 10 actions ordered by `priority DESC, created_at ASC`. Emergency actions (priority=10) preempt normal actions (priority=0).

---

## Q7: Source of Truth for Cluster Actions

**Answer: (d) Mixed / not unified.**

| Engine | Source of Truth | Storage | Agent Visible? |
|--------|----------------|---------|---------------|
| **Engine A** (auto_rebalancer) | `RebalancingAction` table + `AgentAction` table | PostgreSQL | ✅ Yes — agent polls `AgentAction` |
| **Engine B** (PlacementController) | `AgentAction(type=EVICT_POD)` + `RebalancingAction(source='placement_controller')` | PostgreSQL | ✅ Yes — **FIXED 2026-04-23** |
| **Engine C** (Optimizer) | `RightsizingProposal` table + `AgentAction` for `PATCH_CONTAINER_RESOURCES` | PostgreSQL | ✅ Yes (for approved proposals) |
| **Emergency** | `RebalancingAction` table (trigger='emergency') | PostgreSQL | ✅ Yes |
| **KEDA/Karpenter** | `AgentAction` table (INSTALL_KEDA, etc.) | PostgreSQL | ✅ Yes |

**Status: RESOLVED (v7.0).** Engine B now writes to `AgentAction` DB via `_dispatch_eviction()` in `placement_controller_service.py`. The dead-letter Redis queue `spot:placement_controller:action_queue:{cluster_id}` is fully deprecated. The `AgentAction` table is now the single unified source of truth for all in-flight pod-level and node-level actions.

---

## Q8: Cross-Engine Safeguards (Engine A vs Engine B)

**Status: RESOLVED — shared cluster mutex and unified batch limit implemented as of v6.0.**

| Guard | Scope | Key | TTL | Protects Against |
|-------|-------|-----|-----|------------------|
| `spot:rebalance_lock:{cluster_id}` | Engine A only | Redis SET NX | 600s | Two AR cycles on same cluster |
| `spot:placement_controller:cycle_lock:{cluster_id}` | Engine B only | Redis SET NX | 300s | Two PC cycles on same cluster |
| **`spot:cluster_mutex:{cluster_id}`** (**NEW**) | **Both engines** | **Redis SET NX via `HeartbeatLock`** | **60s + heartbeat** | **PC and AR acting simultaneously on same cluster** |
| `spot:workload_lock:{cluster_id}:{workload_id}` (**NEW**) | Engine B only | Redis SET NX | 30s | Two PC cycles evicting from same workload |
| `_scaling_guard_active()` | Engine B only | Redis + K8s API | — | Skips if pending pods > 3 or recent KEDA event |
| `spot:stabilization:{cluster_id}` | Engine A only | Redis TTL | 60s | Post-action cooldown |
| `rebalance:active_count:{cluster_id}` (**SHARED**) | **Both engines** | Redis INCR/DECR | 300s TTL | Cluster-wide batch limit (default `CLUSTER_BATCH_SIZE=2`) |

**How the cluster mutex works:**
- PlacementController acquires `spot:cluster_mutex:{cluster_id}` at the start of `run_cycle()` via a context manager in `backend/utils/redis_locks.py`.
- auto_rebalancer performs a **read-only check** (`redis.get(mutex_key)`) before processing each cluster in its per-cluster loop. If the key is present, the cluster is skipped for that 15-second cycle and `cluster_mutex_contention` is recorded.
- This is a skip-not-block design: AR cannot be interrupted mid-migration, so it skips the cluster rather than waiting.

**How the unified batch limit works:**
- `run_cycle()` queries `COUNT(*) FROM agent_actions WHERE cluster_id=X AND status IN ('PENDING','PICKED_UP')` — this captures BOTH engines' in-flight actions (PC's `EVICT_POD` + AR's `CORDON_NODE`/`DRAIN_NODE`/`UNCORDON_NODE`).
- PC also increments/decrements `rebalance:active_count:{cluster_id}` so AR's own semaphore guard sees PC's dispatched actions.
- AR's semaphore reconciliation now counts both `RebalancingAction` records and in-flight `AgentAction` records to prevent over-correction.

---

## Q9: PlacementController Retry/Rollback/Failure Handling

**Retry mechanisms:**
| Mechanism | Location | Detail |
|-----------|----------|--------|
| Celery retry | `placement_controller_task.py` | `max_retries=1`, countdown=60s on task failure |
| Workload cooldown | `placement_controller_service.py` | 10-min cooldown after successful eviction, 20-min after stateful rollout |
| Migration cooldown | `placement_rollout_service.py` | 30-min cooldown after failed stateful rollout |
| **Post-eviction retry** | `handle_eviction_result()` | If pod lands on OD after eviction → `_mark_for_retry()` marks FAILED; PlacementController drift detection on next 5-min cycle dispatches fresh action. **NEVER re-queues same action as PENDING** (evicted pod no longer exists — K8s 404). |
| **retry_count field** (**NEW**) | `AgentAction.retry_count` | Persisted `SMALLINT DEFAULT 0`; incremented each retry; visible in DB for monitoring |

**Rollback mechanisms:**
| Mechanism | Location | Detail |
|-----------|----------|--------|
| Stateful rollout scale-back | `placement_rollout_service.py` | On timeout: scale replicas back to original IF original pod still Running |
| Fix 3: OD placement abort | `placement_rollout_service.py` | If new pod lands on OD instead of Spot → scale back + cooldown |
| Stale migration recovery | `placement_controller_task.py` | Hourly scan for orphaned scale-ups where replica was never restored |
| Rollout block flag | `placement_rollout_service.py` | `spot:placement:rollout_blocked:{cluster_id}:{workload_id}` — 4-hour TTL |

**Resolved gaps from prior audit:**
- ✅ Engine B actions now fully visible in DB (`RebalancingAction` + `AgentAction` with `source='placement_controller'`)
- ✅ `retry_count` persisted in `AgentAction` table — visible to monitoring
- ⚠️ No Engine B circuit breaker yet (Engine A has `karpenter_service._check_circuit_breaker`)

---

## Q10: Unified Action Model Decision

**Current state: Actions are unified via `AgentAction` table.**

Three separate tracking mechanisms exist:

```
Engine A:  RebalancingAction (DB) → AgentAction (DB) → Agent executes
Engine B:  RebalancingAction(source='placement_controller') + AgentAction(EVICT_POD) → Agent executes
Engine C:  RightsizingProposal (DB) → AgentAction(PATCH_CONTAINER_RESOURCES) → Agent executes
```

**Recommendation for unification:**

| Approach | Pros | Cons |
|----------|------|------|
| **Extend RebalancingAction** | Already production-proven, has state machine, reconciliation | Would need new `trigger` types ('pod_eviction', 'rightsizing') |
| **New unified `ClusterOperation` table** | Clean design, purpose-built | Migration effort, two systems during transition |
| **Use AgentAction as the sole model** | Agent already polls it, simplest bridge for Engine B | Lacks state machine, no built-in reconciliation |

**Pragmatic recommendation**: Bridge Engine B to write `AgentAction` records instead of Redis lists. This immediately fixes the dead-letter problem (Q2) and gives full visibility. Add a `source` column to `AgentAction` to distinguish `auto_rebalancer` vs `placement_controller` vs `optimizer` origins.

---

# PART B: DETAILED EXECUTION FLOW

## 1. Entry Points

### 1.1 FastAPI Gateway
- `main.py` → `uvicorn` on port 8000
- `startup` event → `start_scheduler()` (APScheduler, 10 in-process jobs)
- 3 routers: `/agents`, `/actions`, `/metrics`
- WebSocket: `/ws/cluster/{cluster_id}`

### 1.2 Celery Workers
- 47 registered task modules, 42 beat schedule entries
- Queues: `default`, `emergency` (c=4), `pricing`, `monitoring`

### 1.3 APScheduler (In-Process)
- 10 jobs inside FastAPI process (NOT Celery)
- 60s delayed start for Uvicorn boot

---

## 2. Engine A: Auto-Rebalancer (Node-Level)

**Task**: `workers.auto_rebalancer` — every 15s
**File**: `auto_rebalancer.py` (623KB)
**State Machine**: `CREATED → POOL_SELECTED → CORDONED → DRAINED → TERMINATING → DONE`
**Gate**: `ClusterOptimizationSettings.auto_rebalance_enabled`

**Tick-by-tick flow:**
1. Query clusters with `auto_rebalance_enabled=True`
2. Per cluster: check cooldown, circuit breaker, stabilization lock
3. Find OD nodes eligible for spot replacement
4. Score candidates via `PoolRankingService`
5. Create `RebalancingAction` DB record
6. Advance state machine via `_sm_transition()` (optimistic locking)
7. Create `AgentAction` records (CORDON → DRAIN → TERMINATE)
8. Agent polls, executes, reports back
9. State machine advances on agent result
10. Reconciliation task (every 5 min) detects stuck actions

---

## 3. Engine B: Placement Controller (Pod-Level)

**Task**: `dispatch_placement_controller_cycles` — every 5 min
**Service**: `PlacementController` in `placement_controller_service.py`
**Gate**: `FEATURE_PLACEMENT_CONTROLLER_ENABLED`
**Modes**: Shadow (metrics-only) or Live (writes to AgentAction DB)

**Tick-by-tick flow:**
1. Enumerate clusters with `agent_installed=True`
2. Dispatch per-cluster `run_placement_controller_task` (Celery)
3. Acquire `spot:cluster_mutex:{cluster_id}` (HeartbeatLock, 60s TTL) — skip if held by AR
4. Batch limit check: `COUNT(*) FROM agent_actions WHERE status IN (PENDING, PICKED_UP)` — skip cluster if ≥ `CLUSTER_BATCH_SIZE=2`
5. Load actionable `PlacementPolicy` from Redis cache
6. Per workload: acquire `spot:workload_lock:{cluster_id}:{workload_id}` (30s TTL)
7. Cooldown check → K8s rolling-update guard (`updatedReplicas == readyReplicas`) → drift threshold
8. Count excess OD pods vs `ondemand_target`; apply drift threshold (1 if `target ≤ 3`, else `max(2, target×20%)`)
9. Select burst pods — newest-first, skip pods younger than `POD_AGE_MIN_SECONDS=120`
10. Capacity check: CPU + memory + ENI/pod-slots per AZ with `SPOT_CAPACITY_BUFFER=0.7`
11. Shadow → increment metrics only; Live → call `_dispatch_eviction()` per pod
12. `_dispatch_eviction()` creates `AgentAction(EVICT_POD)` + `RebalancingAction(source='placement_controller')` in PostgreSQL, increments Redis semaphore
13. Stateful path → `_dispatch_stateful_rollout()` creates `RebalancingAction(migration_type='stateful_pod')`, AR picks it up
14. Emit cycle metrics to Redis HASH `spot:placement_controller:metrics:{cluster_id}` (TTL 3600s)

**Post-execution:**
- Agent polls `GET /clusters/{id}/actions/pending`, executes `EVICT_POD` via K8s Eviction API
- Agent reports result → `handle_eviction_result()` validates pod landed on Spot
- If pod on OD or Pending → `_mark_for_retry()` → re-queues as PENDING (max `MAX_RETRY_COUNT=3`)
- On COMPLETED or permanent FAILED → `_decr_semaphore()` decrements `rebalance:active_count`

---

## 4. Intelligence Pipeline

### WIE (Workload Identification Engine)
| Loop | Cadence | Scheduler |
|------|---------|-----------|
| Fast | 2 min | APScheduler — pod_state cache |
| Slow | 10 min | APScheduler — full classification + DB |

**Output**: `WorkloadClassification` with tier (Platinum/Gold/Silver/Bronze), spot_friendly, confidence_state (DRAFT/PROVISIONAL/CONFIRMED)

### Placement Advisor
| Cadence | 10 min (APScheduler → Celery) |
|---------|-------------------------------|
| Gate | `FEATURE_PLACEMENT_ADVISOR_ENABLED` |
| Lock | Redis SET NX EX 300 per cluster |

**Output**: `PlacementPolicyRecord` with `ondemand_target`, `spot_target`, `actionable`

---

## 5. Safety Architecture

### Concurrency Locks
| Key | TTL | Scope |
|-----|-----|-------|
| `spot:rebalance_lock:{cluster}` | 600s | Engine A (per-task) |
| `spot:placement_controller:cycle_lock:{cluster}` | 300s | Engine B (per-task) |
| `spot:placement:cycle_lock:{cluster}` | 300s | Placement Advisor |
| `spot:stabilization:{cluster}` | 60s | Post-action |
| `emergency:dedup:{instance}` | 300s | SQS/IMDS/EventBridge |
| `emergency:rebalance:{instance}` | 120s | Per-node emergency |
| `spot:active_drains:{cluster}:{ctrl}` | 600s | Cross-drain coord |
| **`spot:cluster_mutex:{cluster}`** | **60s + heartbeat** | **Cross-engine (A+B)** |
| **`spot:workload_lock:{cluster}:{workload}`** | **30s** | **Engine B per-workload** |
| `lock:workers.auto_rebalancer` | 300s + heartbeat | Engine A (global task dedup) |

### Circuit Breakers
| Breaker | Threshold | Cooldown |
|---------|-----------|----------|
| Karpenter execution | 10 fails / 10 min | 30 min |
| Execution-level pool penalty | 2 fails / 1h | 6h blacklist |
| WIE confidence | Engine age < 24h | CONFIRMED blocked |

---

## 6. Orphaned Code

### Dead Tasks (registered, no beat entry)
| File | Size |
|------|------|
| `optimization.py` | 4KB |
| `event_processor.py` | 14KB |
| `report_worker.py` | 22KB |
| `alert_worker.py` | 10KB |
| `tag_automation_tasks.py` | 1.4KB |

### Stubbed Methods (return hardcoded True)
| Method | File |
|--------|------|
| `ExecutionController._wait_substitute_ready` | `execution_controller.py` |
| `ExecutionController._drain_node` | `execution_controller.py` |
| `ExecutionController._verify_workload_health` | `execution_controller.py` |
| `ExecutionController._terminate_node` | `execution_controller.py` |

### TODO Body
| Task | Line |
|------|------|
| `pool_optimization_worker` | line 69 — only records timestamp |

---

## 7. Architectural Gaps

| # | Gap | Status | Impact |
|---|-----|--------|--------|
| 1 | **PlacementController Redis queue has no consumer** | ✅ **FIXED** — replaced with `AgentAction` DB writes | Resolved |
| 2 | **No cross-engine mutex** | ✅ **FIXED** — `spot:cluster_mutex:{cluster_id}` in `redis_locks.py` | Resolved |
| 3 | **ExecutionController is stubbed** | ⚠️ Still stubbed — zero stubs found that needed wiring per audit | Emergency replacements silently "succeed" |
| 4 | **Pool optimization is a no-op** | ⚠️ Still a timestamp-only task | 30-min task records timestamp only |
| 5 | **Shadow mode has no graduation** | ⚠️ Still manual | Manual Redis DEL required |
| 6 | **Engine B actions invisible to monitoring** | ✅ **FIXED** — `RebalancingAction(source='placement_controller')` + `AgentAction.retry_count` | Resolved |
| 7 | **WIE + WorkloadInspector overlap** | ⚠️ Still dual | Dual classification systems |
| 8 | **Import path mismatch in placement_advisor_task** | ✅ **FIXED** — `backend/db/session.py` shim created | Resolved |
| 9 | **Batch limit only counted AR actions** | ✅ **FIXED** — single `AgentAction` DB query captures both engines | Resolved |
| 10 | **Semaphore reconciliation ignored PC actions** | ✅ **FIXED** — AR reconciliation now sums `RebalancingAction + AgentAction` | Resolved |

---

## 8. Refactoring Priorities

| Priority | Action | Status |
|----------|--------|--------|
| **P0** | Bridge Engine B to write `AgentAction` DB records | ✅ **DONE** |
| **P0** | Add cross-engine mutex per cluster | ✅ **DONE** |
| **P0** | Unified batch limit counting both engines | ✅ **DONE** |
| **P0** | Add `migration_type`/`source`/`agent_action_id` to `RebalancingAction` | ✅ **DONE** |
| **P0** | Add `retry_count` to `AgentAction` | ✅ **DONE** |
| **P1** | Wire ExecutionController stubs to real K8s/AWS | ⚠️ Pending |
| **P1** | Implement pool_optimization_worker body | ⚠️ Pending |
| **P2** | Standardize placement_advisor_task imports | ✅ **DONE** (session.py shim) |
| **P2** | Remove 5 dead task files | ⚠️ Pending |
| **P3** | Add shadow mode graduation metrics | ⚠️ Pending |
| **P3** | Deprecate WorkloadInspector in favor of WIE | ⚠️ Pending |

---

## 9. Directory Manifest: `backend/services/`
The `services` folder contains the core business logic of the platform, structured functionally. (Note: Quarantined files like `chaos_testing_service.py` have been removed).

### Core Platform & Gateways
- **`agent_injector.py`**: Manages the automated injection of the in-cluster agent via Helm.
- **`cluster_service.py`**: Primary CRUD and state management for Kubernetes clusters.
- **`hygiene_service.py`**: Executes automated cluster cleanup/hygiene actions (requires approval workflows).
- **`cluster_cleanup_service.py`**: Specific tear-down logic for removing Karpenter/Agents when offboarding a cluster.

### Optimizer & Placement (The Brain)
- **`placement_advisor_service.py`**: Core algorithm that generates `PlacementPolicyRecord`s mapping workloads to Spot/OD targets.
- **`placement_controller_service.py`**: (Engine B) Computes drift and selects specific On-Demand pods for eviction to enforce placement policies.
- **`placement_rollout_service.py`**: Manages stateful "create-before-delete" migrations and adaptive rollout timeouts.
- **`optimizer_coordinator.py`**: (Engine C) Orchestrates rightsizing proposals and evaluates tradeoff options.
- **`rightsizing_service.py`**: Analyzes VPA metrics to propose new CPU/Memory request/limit boundaries.
- **`workload_identification_engine.py` (WIE)**: ML-driven workload classifier (assigns criticality, statefulness, and Spot-friendliness).
- **`workload_inspector.py`**: Legacy workload scanner (scheduled to be deprecated in favor of WIE).
- **`workload_classifier.py`**: Helper logic for workload inspection.

### Execution & Rebalancing
- **`execution_controller.py`**: Base abstractions for direct K8s/AWS node operations (mostly stubbed out in favor of Agent actions).
- **`emergency_handler.py`**: Triggers immediate Spot replacement when an interruption notice (2-minute warning) is received.
- **`eviction_safety.py`**: Validates PDBs, single-replica status, and readiness gates before allowing a node drain.
- **`pool_ranking_service.py`**: ML-based scorer that ranks AWS EC2 instance pools by Spot interruption risk and capacity.
- **`pool_rotation_service.py`**: Manages time-based rotation of NodePools to prevent capacity exhaustion.
- **`pool_reputation_service.py`**: Tracks localized pool failure rates (ICE errors) and temporarily downranks them.
- **`rebalance_tracker.py`**: Lightweight state tracker for `RebalancingAction` transitions.
- **`global_pool_cache_service.py`**: Provides cross-cluster cached AWS capacity data.
- **`global_ema_service.py`**: Exponential Moving Average calculator for global Spot interruption trends.
- **`adaptive_itn_service.py`**: Adaptive Interruption Tolerance Network (modulates risk appetite based on cluster history).

### Provisioning & Infrastructure
- **`karpenter_service.py`**: Core interface for reading and patching Karpenter `NodePool` and `EC2NodeClass` objects in the cluster.
- **`karpenter_metrics_collector.py`**: Scrapes Karpenter Prometheus endpoints to gauge provisioning latency.
- **`nodepool_reconciler_service.py`**: Ensures Karpenter NodePool definitions match backend database configurations.
- **`spot_asg_service.py`**: Legacy interface for managing AWS Auto Scaling Groups.
- **`substitute_manager.py`**: Legacy pre-Karpenter logic for maintaining warm EC2 substitute instances.
- **`dynamic_instance_helpers.py`**: Utilities for parsing EC2 instance types and capabilities.

### Auth, Governance & Users
- **`auth_service.py`**: JWT generation and authentication flows.
- **`account_service.py` / `admin_service.py`**: Tenant and super-admin management.
- **`approval_service.py`**: Multi-party approval workflow engine for risky cluster actions.
- **`governance_service.py`**: Applies organizational guardrails to cluster actions.
- **`organization_service.py` / `team_service.py`**: RBAC grouping structures.
- **`role_service.py` / `permission_service.py`**: Granular RBAC definitions.
- **`policy_service.py`**: General organizational policies.
- **`oidc_federation_service.py`**: AWS IAM Identity Center / OIDC integration.

### Billing & Pricing
- **`aws_pricing_service.py`**: Fetches real-time and historical AWS Spot/OD prices.
- **`resource_pricing_service.py`**: Correlates cluster usage with AWS prices.
- **`resource_cost_service.py`**: Generates cost breakdowns per workload/namespace.
- **`savings_plan_service.py`**: Tracks AWS Savings Plans / RIs to prevent Spot from cannibalizing covered OD capacity.
- **`rds_analysis_service.py` / `ri_analysis_service.py`**: Cost analysis for databases and reserved instances.

### Addons & Utilities
- **`keda_service.py`**: Installs and manages KEDA for cluster auto-scaling.
- **`anchored_node_service.py`**: Logic for pinning specific workloads to dedicated persistent nodes.
- **`hibernation_service.py`**: Pauses dev/staging clusters during off-hours to save cost.
- **`observability_logger.py`**: Structured JSON logging to DataDog/CloudWatch.
- **`metrics_service.py`**: Timeseries ingestion from in-cluster agents.
- **`notification_service.py`**: Slack/Email alerting for optimization events.
- **`audit_service.py`**: Immutable trail of all system actions.
- **`circuit_breaker.py`**: Disables automation when failure thresholds are breached.
- **`cooldown_controller.py`**: Enforces time-based locks (e.g., "no rebalancing for 10m after scale-up").
- **`distributed_locks.py`**: Redis-backed distributed mutexes.
- **`event_monitor.py`**: Monitors global region volatility.
- **`simulation_engine.py`**: Sandbox for running "what-if" rebalancing scenarios without executing them.
- **`tag_management_service.py`** / **`tag_scoring_service.py`** / **`tag_policy_service.py`** / **`tag_compliance_service.py`** / **`tag_suggestion_service.py`** / **`tag_automation_service.py`**: Comprehensive suite for enforcing AWS tagging compliance.

---

## 10. Directory Manifest: `backend/workers/tasks/`
The `tasks` folder contains Celery background workers and APScheduler jobs. (Note: Quarantined files like `alert_worker.py` have been removed).

### Rebalancing & Spot Operations (Engine A & Emergency)
- **`auto_rebalancer.py`**: (Engine A) The 623KB core state machine that cordons, drains, and replaces nodes on a 15-second loop.
- **`emergency_rebalancer.py`**: Bypasses normal queues to instantly replace nodes receiving a 2-minute interruption warning.
- **`termination_monitor.py`**: Polls AWS APIs to confirm EC2 instances have actually terminated after a drain.
- **`sqs_consumer.py`**: Listens to AWS EventBridge/SQS for Spot interruption notices.
- **`standby.py`**: Pre-warms instances for workloads that require zero-downtime migrations.
- **`maintain_warm_spare_worker.py`**: Ensures a buffer of empty Spot nodes exists for rapid failover.

### Placement & Control Plane (Engines B & C)
- **`placement_advisor_task.py`**: Wraps the Placement Advisor algorithm in a Celery task with Redis locking.
- **`placement_controller_task.py`**: Dispatches the Placement Controller eviction cycles and runs the stale migration recovery loop.
- **`control_plane_loop.py`**: An 8-step mega-loop that evaluates macro cluster health and NodePool validity.
- **`optimizer_coordinator_worker.py`**: Evaluates rightsizing proposals and (TODO) pool optimization.

### Infrastructure Sync
- **`discovery.py`**: Scans AWS accounts to ingest newly created EKS clusters automatically.
- **`ascpai_worker.py`**: Syncs ML rankings directly into Karpenter NodePool YAMLs inside the cluster.
- **`reconciliation_worker.py`**: Detects drift between the Backend DB state and the actual AWS EC2 state.
- **`recovery_monitor.py`**: Scans for "orphaned" nodes (instances running in AWS that aren't tracked in the DB).

### Pricing & Intelligence Cache
- **`cache_builder.py`**: Pre-computes global Spot instance interruption risks and prices.
- **`cache_warmer.py`**: Loads pre-computed caches into Redis fast-memory.
- **`pricing_worker.py`**: Fetches the latest Spot pricing from AWS APIs.
- **`resource_pricing_worker.py`**: Updates DB pricing models.
- **`instance_catalog_worker.py`**: Ingests new EC2 instance types and their capabilities (CPU/Mem/ENI) when AWS releases them.
- **`global_ema_tasks.py`**: Triggers the exponential decay of global interruption risk scores.
- **`adaptive_itn_tasks.py`**: Persists and decays localized cluster interruption risk tolerances.
- **`pool_rotation_worker.py`**: Flips active/standby NodePools to maintain instance diversity.

### Autoscaling & Addons
- **`auto_scaler.py`**: A custom pending-pod autoscaler (active only if `enable_ascp_auto_scaler` is True).
- **`keda_installer.py`**: Monitors the rollout of KEDA ScaledObjects in user clusters.
- **`hibernation_worker.py`**: Executes scheduled cron jobs to scale down clusters at night and wake them in the morning.
- **`resize_guard_worker.py`**: Protects clusters from being rebalanced immediately after a major scale-up event.

### Cost & Analytics
- **`cost_calculator.py`**: Aggregates hourly compute costs.
- **`cost_explorer.py`**: Syncs with AWS Cost Explorer for precise billing data.
- **`savings_calculator.py`**: Computes the exact dollar amount saved by using Spot vs On-Demand.
- **`daily_stats_aggregator.py`**: Rolls up daily cluster metrics for the UI dashboard.
- **`report_worker.py`**: (Skipped Quarantine) Generates PDF/CSV monthly cost savings reports.

### Health & Cleanup
- **`health.py`**: Cleans up zombie nodes, stuck agents, and stale Redis keys.
- **`health_monitor.py`**: Computes macro "Health Scores" (A/B/C/D) for clusters.
- **`cleanup_tasks.py`**: Removes old migration events and terminated EC2 DB records.
- **`approval_cleanup.py`**: Expires pending admin approval requests that timed out.
- **`dry_run_refresher.py`**: Keeps the "Dry Run" simulation cache up to date.
- **`pod_metrics_cleanup.py`**: Truncates massive timeseries pod metric tables to save DB space.
- **`optimization.py`** / **`event_processor.py`**: (Skipped Quarantine) Zombie tasks imported by `__init__.py` but unused in the execution schedule.

---

## 11. Directory Manifest: `backend/api/`
The `api` folder contains the FastAPI endpoints serving the REST and WebSocket interfaces for the platform. (Note: Quarantined files like `ai_agent_routes.py` have been removed).

### Core Operations & Ingestion
- **`cluster_routes.py`**: CRUD operations for cluster configurations and optimizations.
- **`agent_routes.py`**: Ingestion endpoints for in-cluster agents (metrics, heartbeat, action polling).
- **`websocket_routes.py`**: Real-time bidirectional WebSocket handlers for the agents.
- **`worker_routes.py`**: Endpoints for triggering and monitoring background Celery worker tasks manually.
- **`onboarding_routes.py` / `installer_routes.py`**: Self-service onboarding and agent installation scripts.
- **`multi_cluster_routes.py`**: Fleet-wide views and aggregations.

### Optimizer & Placement API
- **`ascpai_routes.py`**: The main ASCP (Automated Spot Capacity Provisioning) AI endpoints for dashboard interaction.
- **`karpenter_routes.py`**: Endpoints to inspect Karpenter definitions, NodePools, and generated ML templates.
- **`optimization_routes.py`**: Legacy triggers for manual optimization cycles.
- **`optimizer_coordinator_routes.py`**: Views for Engine C rightsizing proposals and tradeoff options.
- **`placement_policy_routes.py`**: Exposes the `PlacementPolicyRecord` outputs from the Advisor.
- **`placement_webhook_routes.py`**: Webhook receivers for Placement Controller events.
- **`workload_classification_routes.py`**: Displays the WIE outputs (Tiering, Statefulness, Spot-readiness).

### Auth, Users & Governance
- **`auth_routes.py` / `user_routes.py`**: Authentication, login, and profile management.
- **`account_routes.py`**: Tenant lifecycle management.
- **`admin_routes.py`**: Super-admin override endpoints.
- **`approval_routes.py`**: UI endpoints for accepting/rejecting high-risk administrative requests.
- **`governance_routes.py` / `policy_routes.py`**: Organization-wide guardrail configurations.
- **`organization_routes.py` / `team_routes.py` / `role_routes.py` / `permission_routes.py`**: RBAC endpoints.

### Financial & Analytics
- **`billing_routes.py`**: AWS Cost Explorer sync endpoints and financial rollups.
- **`audit_routes.py`**: System-wide immutable action logs.
- **`health_routes.py`**: Quick uptime and readiness probes.
- **`metrics_routes.py`**: Aggregated cluster savings and performance graphs for the UI.
- **`pod_metrics_routes.py`**: Detailed VPA/HPA utilization timeseries data.

### Addons, Tags & Utilities
- **`hibernation_routes.py`**: Endpoints to schedule cluster sleep/wake cycles.
- **`hygiene_routes.py`**: Manual triggers for cleanup scripts.
- **`keda_routes.py`**: Management views for KEDA ScaledObjects.
- **`tag_*_routes.py`**: Six files dedicated to configuring, scoring, and enforcing AWS Tagging policies.
- **`node_template_routes.py` / `pool_rotation_routes.py`**: Specialized configuration for NodePool attributes.
- **`decision_routes.py`**: Exposes "Why did the engine do X?" debug decisions.
- **`integrations_routes.py` / `transfer_routes.py`**: 3rd party tool bindings.
- **`rds_routes.py` / `ri_routes.py` / `s3_routes.py`**: Storage and database specialized views.

---

## 12. Directory Manifest: `agent/`
The `agent` folder contains the Python code that runs *inside* the customer's Kubernetes clusters. It communicates with the `backend/api/` via HTTP and WebSockets.

### Core Entry & Connectivity
- **`main.py`**: The process entry point. Bootstraps connections, loads config, and initializes sub-components.
- **`config.py`**: Loads environment variables (Cluster ID, API Keys, Backend URL) provided by the Helm chart.
- **`websocket_client.py`**: Maintains a persistent, real-time bidirectional connection to the backend. Used for streaming logs and receiving immediate Action commands.
- **`poller.py`**: A fallback HTTP polling mechanism that calls `GET /actions/pending` if the WebSocket disconnects.
- **`heartbeat.py`**: Periodically sends `POST /agents/heartbeat` to signal the agent is alive and reports basic cluster presence (like if Karpenter CRDs exist).

### Data Collection (Read-Only)
- **`collector.py`**: The primary state scraper. Queries K8s API for Node allocatable capacity, Pod statuses, and cluster-wide events. Formats and sends via `POST /metrics/batch`.
- **`pod_metrics_collector.py`**: Specialized scraper for Kubernetes Metrics Server (`metrics.k8s.io`). Captures CPU/Memory utilization per pod for rightsizing calculations.
- **`karpenter_watcher.py`**: Specialized watcher that tracks `NodeClaim` state changes (e.g., from Provisioning to Registered) to provide exact timing metrics to the backend.

### Execution (Write)
- **`actuator.py`**: The execution engine that performs K8s mutations requested by the backend. It maps `AgentActionType` enum values to K8s API calls. 
  - *Examples*: Calling `cordon` and `drain` on a node, `evicting` a pod via the Eviction API, scaling a Deployment replica count, or patching a NodePool.

---

## 13. Deep-Dive: Workload Identification to Execution Pipeline
The lifecycle from analyzing a workload to physically executing a migration follows a strict, multi-stage pipeline across three distinct microservices. 

### Phase 1: Workload Identification Engine (WIE)
**File**: `backend/services/workload_identification_engine.py`
The WIE is a read-only, deterministic scoring engine (no ML, no mutations). It operates on strict confidence thresholds to prevent dangerous automation.
1. **Filtering**: Explicitly ignores system namespaces (`kube-system`, `karpenter`, `cert-manager`) and critical priority classes (`system-node-critical`).
2. **Scoring**: Computes three core dimensions:
   - `criticality (0-10)`: Based on replicas, ingress, PDBs, and traffic.
   - `spot_score (0-10)`: Based on statefulness, topology spread, and traffic variance.
   - `confidence (1-10)`: Based on data freshness and cluster cold-start time (requires 24h of data).
3. **State Gates**: Outputs are grouped by confidence:
   - **DRAFT (<5)**: Engine is observing, no actions permitted.
   - **PROVISIONAL (5-7)**: Generates UI suggestions, but automation is blocked.
   - **CONFIRMED (≥8)**: Full automation permitted. Outputs are passed to the Advisor.

### Phase 2: Placement Intelligence (Advisor)
**File**: `backend/services/placement_advisor_service.py`
Once WIE confirms a workload is "Spot-friendly", the Advisor calculates the exact mathematical floor for On-Demand pods to guarantee availability.
1. **Coefficient of Variation (CV)**: Calculates traffic skew (CPU and Request variance). If CV > 40%, the baseline is adjusted upwards to prevent cascading failures.
2. **Tier Logic**: Computes the `ondemand_target`:
   - **Platinum**: 100% On-Demand (No Spot).
   - **Gold**: 70% On-Demand (drops to 50% if PDBs and Anti-Affinity are present).
   - **Silver**: 50% On-Demand.
   - **Bronze**: Mathematical minimum only (max of `replicas * 0.5` or `pdb_min_available`).
3. **Output**: Writes a `PlacementPolicyRecord` to the DB.

### Phase 3: Drift Detection (Controller)
**File**: `backend/services/placement_controller_service.py`
Runs every 5 minutes to compare the cluster's *actual* pod placement against the Advisor's *intended* `PlacementPolicyRecord`.
1. **Guards**: Aborts if scaling guards are active (>3 pending pods cluster-wide) or if the target pod is too young (<120 seconds old) to prevent fighting the native K8s scheduler.
2. **Drift Calculation**: If there are more On-Demand pods running than the `ondemand_target` allows (exceeding a 20% drift threshold), it queues an eviction.
3. **Routing**: 
   - **Stateless**: Emits an `EVICT_POD` action to forcefully kill the On-Demand pod, trusting Karpenter to spin up a Spot node.
   - **Stateful**: Delegates to `placement_rollout_service.py` for a safe, stateful "create-before-delete" rolling migration.

### Phase 4: Execution (RESOLVED as of v6.0)
**Actual Flow (current)**: The Controller writes directly to the `AgentAction` PostgreSQL table. The Redis dead-letter queue is no longer used.

**Execution path for stateless EVICT_POD:**
1. `_dispatch_eviction()` creates `AgentAction(type=EVICT_POD, status=PENDING)` + `RebalancingAction(source='placement_controller', migration_type='pod_level')`
2. Agent polls `GET /clusters/{id}/actions/pending` → receives `EVICT_POD` record
3. `agent/actuator.py` calls `kubernetes.client.CoreV1Api().create_namespaced_pod_eviction()`
4. Agent reports result → `POST /agents/actions/{id}/result`
5. Backend calls `handle_eviction_result()` — checks `get_pod_placement()` to validate pod landed on Spot
6. If pod is on OD or still Pending → `_mark_for_retry()` increments `retry_count`, re-queues as PENDING
7. At `retry_count >= MAX_RETRY_COUNT (3)` → marks FAILED, decrements semaphore, PlacementController re-evaluates on next 5-min cycle
8. On SUCCESS → marks COMPLETED, decrements semaphore, workload cooldown set

**Execution path for stateful rollout:**
1. `_dispatch_stateful_rollout()` creates `RebalancingAction(migration_type='stateful_pod', source='placement_controller')`
2. auto_rebalancer picks up the record on next 15-second cycle
3. auto_rebalancer executes create-before-delete: scale up → wait for new pod Ready → evict old OD pod → scale down → remove `karpenter.sh/do-not-disrupt` annotation
4. Rollback if timeout: scale back to `original_replicas` (only if original pod still Running)

---

## 14. PlacementController v1.4 — Full Logic Reference

### 14.1 Configuration Constants
| Constant | Default | Env Var | Purpose |
|----------|---------|---------|---------|
| `CLUSTER_BATCH_SIZE` | `2` | `PC_CLUSTER_BATCH_SIZE` | Max concurrent in-flight actions per cluster across both engines |
| `MAX_RETRY_COUNT` | `3` | `PC_MAX_RETRY_COUNT` | Max post-eviction retries before permanent FAILED |
| `CLUSTER_MUTEX_TTL_SECS` | `60` | — | HeartbeatLock TTL for cross-engine mutex |
| `WORKLOAD_LOCK_TTL_SECS` | `30` | — | Per-workload Redis lock TTL |
| `MAX_EVICTIONS_PER_CYCLE` | `3` | `PC_MAX_EVICTIONS_PER_CYCLE` | Max pods to evict per workload per cycle |
| `SPOT_CAPACITY_BUFFER` | `0.7` | `PC_SPOT_CAPACITY_BUFFER` | Fraction of allocatable capacity to use |
| `WORKLOAD_COOLDOWN_MINUTES` | `10` | `PC_WORKLOAD_COOLDOWN_MINUTES` | Cooldown after successful eviction |
| `SCALING_GUARD_WINDOW_SECONDS` | `120` | `PC_SCALING_GUARD_WINDOW_SECONDS` | Post-KEDA scaling inhibit window |
| `PENDING_PODS_THRESHOLD` | `3` | `PC_PENDING_PODS_THRESHOLD` | Max pending pods before skipping cycle |
| `MIGRATION_TIMEOUT_MINUTES` | `20` | `PC_MIGRATION_TIMEOUT_MINUTES` | Max stateful rollout wait time |
| `POD_AGE_MIN_SECONDS` | `120` | `PC_POD_AGE_MIN_SECONDS` | Skip pods younger than this (Fix 4: anti-scheduler-fight) |

### 14.2 Per-Cycle Decision Tree
```
run_cycle(cluster_id)
  ├── Acquire spot:cluster_mutex:{cluster_id}  → skip if held by AR
  ├── Count ALL AgentAction(PENDING|PICKED_UP) → skip if ≥ CLUSTER_BATCH_SIZE
  ├── Load PlacementPolicy from Redis
  └── For each actionable workload:
        ├── Acquire spot:workload_lock:{cluster_id}:{workload_id}
        ├── Check workload cooldown
        ├── K8s rollout guard: updatedReplicas == readyReplicas?
        ├── Count excess OD pods (current_od - ondemand_target)
        ├── Drift threshold: skip if excess < threshold
        │     (threshold = 1 if target≤3, else max(2, target×0.2))
        ├── Rate limit: excess_od = min(excess_od, MAX_EVICTIONS_PER_CYCLE)
        ├── Select pods (newest-first, skip age < POD_AGE_MIN_SECONDS)
        ├── Compute desired AZ per pod (capacity-biased scoring)
        ├── Capacity check: CPU + memory + ENI slots per AZ × SPOT_CAPACITY_BUFFER
        │     → skip if insufficient (evictions_skipped_capacity++)
        │     → skip if no spot nodes at all (evictions_failed_due_to_no_replacement++)
        └── Act:
              disruption_safe=True  → _dispatch_eviction() per pod
              disruption_safe=False → _dispatch_stateful_rollout()
```

### 14.3 Metrics Emitted (Redis HASH per cycle)
Key: `spot:placement_controller:metrics:{cluster_id}` | TTL: 3600s

| Counter | Meaning |
|---------|---------|
| `evictions_attempted` | Pods for which EVICT_POD was dispatched |
| `evictions_skipped_capacity` | Pods skipped due to insufficient Spot capacity |
| `evictions_skipped_cooldown` | Workloads skipped due to active cooldown |
| `evictions_skipped_scaling_guard` | Workloads skipped (rolling update in progress or KEDA scaling) |
| `evictions_skipped_lock_contention` | Workloads skipped (per-workload Redis lock held) |
| `evictions_skipped_batch_limit` | Cycles skipped (cluster batch limit reached) |
| `evictions_failed_due_to_no_replacement` | Pods with no eligible Spot nodes in any AZ |
| `stateful_rollout_started` | Stateful create-before-delete migrations initiated |
| `stateful_rollout_completed` | Stateful migrations successfully completed |
| `stateful_rollout_failed` | Stateful migrations aborted (capacity pre-check failed) |
| `stateful_rollout_timeout` | Stateful migrations timed out and rolled back |
| `retry_incremented` | Post-eviction validations that triggered a retry |
| `permanent_failures` | Actions that hit MAX_RETRY_COUNT and were marked FAILED |

### 14.4 Mutating Webhook (v1.4)
**File**: `backend/api/placement_webhook_routes.py`
**Framework**: FastAPI (`APIRouter`, async handlers)
**Endpoint**: `POST /placement/mutate` (registered in `backend/api/__init__.py`)

**Responsibility**: Structure-only injection. Does NOT decide Spot vs On-Demand.

| Injection | Condition | Result |
|-----------|-----------|--------|
| Topology Spread `ScheduleAnyway` | `policy.az_spread_required == True` | Adds `topologySpreadConstraints` to pod spec |
| Spot Preference (`weight: 80`) | Always when policy is actionable | Adds `nodeAffinity.preferredDuringScheduling` for `karpenter.sh/capacity-type: spot` |
| Idempotency | Both: check existing constraints before injecting | No duplicate constraints |

---

## 15. Execution Engine v1.1 — Changes Summary

### 15.1 New Files
| File | Purpose |
|------|---------|
| `backend/utils/redis_locks.py` | `cluster_mutex(redis, cluster_id, owner, ttl)` and `workload_lock(redis, cluster_id, workload_id, ttl)` context managers |
| `backend/db/session.py` | Shim re-exporting `SessionLocal` from `backend.models.base` |
| `backend/db/__init__.py` | Package init |
| `migrations/versions/20260423_pod_level_cols.py` | Alembic migration (revision `20260423_pod_level_cols`) adding all 4 new columns; applied to live DB 2026-04-23 |

### 15.2 DB Schema Changes Applied
| Table | Column | Type | Default | Purpose |
|-------|--------|------|---------|---------|
| `rebalancing_actions` | `migration_type` | `VARCHAR(20) NOT NULL` | `'node_level'` | Distinguishes node vs pod-level migrations |
| `rebalancing_actions` | `source` | `VARCHAR(30) NOT NULL` | `'auto_rebalancer'` | Which engine created the record |
| `rebalancing_actions` | `agent_action_id` | `VARCHAR(36) FK` | `NULL` | Links PC's AgentAction to its tracking RebalancingAction |
| `agent_actions` | `retry_count` | `SMALLINT NOT NULL` | `0` | Post-eviction retry counter |

### 15.3 auto_rebalancer.py Changes
| Location | Change |
|----------|--------|
| `~line 6951` (per-cluster loop) | Cross-engine mutex check: `redis.get('spot:cluster_mutex:{cluster_id}')` → skip cluster if key present |
| `~line 8517` (semaphore reconciliation) | Now counts `RebalancingAction(in_progress/pending/waiting_agent)` + `AgentAction(PENDING/PICKED_UP)` to get true `_actual_active` |

---

## 16. UI Automation Toggle Behavior

### 16.1 Toggle Location and State Persistence
**File**: `frontend/src/components/clusters/ClusterDetails.jsx`
**Tab**: "Optimization Settings" within the Cluster Detail view
**API**: `GET/PUT /api/v1/clusters/{id}/optimization-settings` → `ClusterOptimizationSettings` DB table
**State fields**: `automation_controls.auto_rebalance_enabled` and `automation_controls.auto_rightsizing_enabled`

**Pre-condition guard** (both toggles): If Karpenter is NOT installed (`karpenterInstallStatus.karpenter_installed === false`), enabling either toggle triggers a `KarpenterRequiredModal` instead of activating the toggle. The modal offers to install Karpenter first.

```javascript
// ClusterDetails.jsx handleOptConfigChange()
if (key === 'auto_rebalance_enabled' || key === 'auto_rightsizing_enabled') {
  if (value === true && !karpenterInstallStatus?.karpenter_installed) {
    setShowKarpenterRequiredModal(true);  // blocks toggle activation
    return;
  }
}
```

---

### 16.2 Auto-Rebalance Toggle (`auto_rebalance_enabled`)

#### When TURNED ON:
**UI changes (immediate — before save):**
- Status banner at top of Optimization Settings tab: turns green with pulsing dot → "ENABLED — Auto-rebalancer is active — ML engine monitors and moves nodes to optimal spot pools"
- Mode badge in card header: turns green → "REBALANCE ACTIVE" (or "FULL AUTO" if rightsizing is also on)
- Sub-settings appear below the toggle:
  - **Maintain Warm Standby** toggle (teal) — pre-warms 1 spot node for instant failover
  - **Failure Cooldown** input (default 30 min) — after a failed migration
  - **Post-Rebalance Cooldown** input (default 60 min) — after a successful migration
- In Right-Sizing Dashboard: **StatelessSection** shows "AUTO ENABLED" badge; the manual "Apply" button is hidden (automation handles it)
- **Optimization Target** dropdown: if both toggles ON → locked to "Spot" with "Locked" badge

**Backend effect (after clicking Save):**
1. `PUT /api/v1/clusters/{id}/optimization-settings` with `automation_controls.auto_rebalance_enabled: true`
2. `ClusterOptimizationSettings.auto_rebalance_enabled` set to `True` in DB
3. Next `execute_rebalancing()` Celery beat (15s): cluster passes the `auto_rebalance_enabled` gate at line ~6908
4. auto_rebalancer begins its full cycle: AWS sync → K8s sync → candidate scoring → RebalancingAction creation → AgentAction dispatch
5. PlacementController's `dispatch_placement_controller_cycles` also uses this cluster (if `FEATURE_PLACEMENT_CONTROLLER_ENABLED=True`)
6. `AutoModeBanner` in RightSizingDashboard turns to active state

**Backend effect (when TURNED OFF):**
1. `auto_rebalance_enabled` set to `False`
2. auto_rebalancer skips the cluster at the `auto_rebalance_enabled` gate — no new RebalancingActions created
3. In-progress actions continue to completion (no abort)
4. Status banner turns gray → "DISABLED — All automation paused — manual mode only"
5. Mode badge turns gray → "DISABLED"

---

### 16.3 Auto-Right-Sizing Toggle (`auto_rightsizing_enabled`)

#### When TURNED ON:
**UI changes (immediate — before save):**
- In RightSizingDashboard (`RightSizingDashboard.jsx`): `AutoModeBanner` shows active state
- **Min Topology Spread** slider appears below the toggle (1–5, default 1, teal gradient card):
  - Controls the minimum number of nodes across different AZs during rightsizing consolidation
  - Higher = more HA, fewer savings
- In `KarpenterConfigPanel` on the "config" tab: `auto_rightsizing_enabled` also visible and synced
- **Optimization Target**: if both toggles ON → locked to "Spot" (synergy mode)
- `RightSizingRecommendationsTable` becomes visible with "Active — Auto-Applying" badge (green) instead of "Recommendations Only" (amber)
- StatelessSection's Apply button for manual spot migration is hidden

**Backend effect (after clicking Save):**
1. `PUT /api/v1/clusters/{id}/optimization-settings` with `automation_controls.auto_rightsizing_enabled: true`
2. `ClusterOptimizationSettings.auto_rightsizing_enabled` set to `True`
3. `optimizer_coordinator_worker.py` evaluates rightsizing proposals and auto-approves them (no manual approval gate when `auto_rightsizing_enabled=True`)
4. Approved `RightsizingProposal` records generate `AgentAction(type=PATCH_CONTAINER_RESOURCES)` records
5. Agent polls and applies new CPU/memory requests+limits to Deployments/StatefulSets
6. Karpenter re-evaluates node sizing after resource changes → may consolidate underutilized nodes

**Backend effect (when TURNED OFF):**
1. `auto_rightsizing_enabled` set to `False`
2. `optimizer_coordinator_worker.py` stops auto-approving proposals — they remain in `PENDING` state requiring manual approval
3. `RightSizingRecommendationsTable` badge changes to "Recommendations Only" (amber)
4. The manual Approve/Reject buttons reappear in the Execution Plan table

---

### 16.4 Synergy Mode (Both Toggles ON)
When both `auto_rebalance_enabled=True` AND `auto_rightsizing_enabled=True`:
- Mode badge: "FULL AUTO"
- **Optimization Target** locked to "Spot" — cannot be changed to "On-Demand"
- `RightSizingRecommendationsTable` shows "Active — Auto-Applying" badge
- The platform operates in full autonomous mode:
  1. WIE classifies workloads continuously
  2. PlacementAdvisor sets `ondemand_target` per workload
  3. PlacementController evicts excess OD pods to Spot
  4. auto_rebalancer replaces OD nodes with Spot nodes at the node level
  5. Optimizer applies rightsizing patches to over-provisioned workloads
  6. Karpenter consolidates the resulting smaller/cheaper nodes

---

## 17. UI Sections Reference

### 17.1 ClusterDetails.jsx — "Optimization Settings" Tab
**Route**: `/clusters/{id}` → Tab: "Optimization Settings"
**Data source**: `GET /api/v1/clusters/{id}/optimization-settings`

| Section | What It Shows | Visible When |
|---------|--------------|--------------|
| **Status Banner** | Green/gray pill: "ENABLED/DISABLED" with description | Always |
| **Mode Badge** | "FULL AUTO" / "REBALANCE ACTIVE" / "DISABLED" | Always (top-right of card) |
| **CPU Architecture** | Dropdown: "Both / AMD64 / ARM64" — controls pool selection | Always |
| **Diversify Spot Pools** toggle | Spread across multiple instance pools | Always |
| → Max Family Diversification Cap (slider 10–100%) | Cap on same instance family % | Only when Diversify ON |
| → Instance Type Diversification (slider 0–100%) | Strict vs relaxed uniqueness | Only when Diversify ON |
| **Auto Rebalance** toggle (blue) | Enable/disable node-level Spot migration | Always |
| → Maintain Warm Standby | Pre-warm 1 Spot node for instant failover | Only when Auto Rebalance ON |
| → Failure Cooldown (min) | Post-failure inhibit window | Only when Auto Rebalance ON |
| → Post-Rebalance Cooldown (min) | Post-success inhibit window | Only when Auto Rebalance ON |
| **Check Cycle Interval** (min 15s) | How often auto_rebalancer evaluates the cluster | Always |
| **Auto Right-Sizing** toggle (blue) | Enable/disable automated CPU/mem rightsizing | Always |
| → Min Topology Spread (slider 1–5) | Min AZ diversity during consolidation | Only when Rightsizing ON |
| **Optimization Target** dropdown | Spot / On-Demand billing model for replacements | Always (locked to Spot in synergy mode) |
| **Conservative Mode** toggle (green) | Limits aggressive replacements in first 24h | Always |
| **Manual Approval Required** toggle (dark) | Routes changes to Team Lead before execution | Always |

### 17.2 RightSizingDashboard.jsx — Main Dashboard
**Route**: `/right-sizing`
**Data source**: `GET /api/v1/clusters/{id}/optimization-settings` + `GET /api/v1/karpenter/{id}/recommendations`

#### Top-level tabs:
| Tab | Shows | Logic |
|-----|-------|-------|
| **karpenter** (default) | Node recommendations, migration timeline, pod rightsizing table | Active polling every 15s |
| **history** | Node-by-node execution plan + Approve/Reject buttons | `optimizerCoordinatorAPI.listProposals()` |
| **config** | KarpenterConfigPanel (strategy, instance families, stateful policy) | `karpenterAPI.getConfig()` |
| **savings** | KPIs (resizes this month, net savings, success rate) + action history table | `karpenterAPI.getHistory()` |
| **workload** | WorkloadInventoryDashboard | WIE classification outputs |

#### AutoModeBanner (top of karpenter tab):
| State | Banner Content |
|-------|---------------|
| Both OFF | Gray — manual mode, recommendations only |
| Rebalance ON only | Blue — auto-rebalancer active, rightsizing manual |
| Rightsizing ON only | Teal — rightsizing active, rebalancing manual |
| Both ON | Green — full auto mode, all optimizations active |

#### StatelessSection (Spot Node Recommendations):
| State | UI Change |
|-------|----------|
| `auto_rebalance_enabled=False` | Shows "Apply" button per node — manual trigger |
| `auto_rebalance_enabled=True` | "AUTO ENABLED" badge, Apply button hidden — handled by agent |

#### RightSizingRecommendationsTable (Pod CPU/Memory Recommendations):
- Only visible when `auto_rightsizing_enabled=True` AND `rsRecs.length > 0`
- Badge: "Active — Auto-Applying" (green) when both toggles on; "Recommendations Only" (amber) otherwise
- Columns: Workload, Namespace, Current CPU/Mem, Recommended CPU/Mem, Monthly Savings, Action (REDUCE/INCREASE/NO_CHANGE)

#### RebalancingTimeline:
- Polls `ascpaiAPI.getRebalancingStatus(clusterId, 5)` every 15s
- Shows active node migrations in progress: draining pods → new node up → old node terminating → done
- Always visible on karpenter tab regardless of toggle state

### 17.3 KarpenterConfigPanel (config tab)
Manages deep Karpenter settings. Key state from toggles:
| Field | Effect |
|-------|--------|
| `auto_rebalancing_enabled` | Same as `auto_rebalance_enabled` in ClusterDetails (synced via `karpenterAPI.updateConfig()`) |
| `auto_rightsizing_enabled` | Same as `auto_rightsizing_enabled` in ClusterDetails |
| `optimization_target` | Locked to "Spot" when both toggles ON ("synergy mode" label shown) |
| `consolidation_enabled` | Karpenter-native `WhenEmptyOrUnderutilized` consolidation |
| `consolidation_threshold` | % utilization threshold to trigger consolidation (default 80%) |
| `stateful_require_approval` | When OFF, stateful node resizes execute immediately |
| `auto_stateful_rightsizing_enabled` | Auto-resize stateful OD nodes (max 1 per cluster per 48h, downsizes only); shows ⚠️ warning when ON |
| `instance_families` | Chip picker — toggle which EC2 families are allowed for bin-packing |
| `diversify_pools` | Spread Spot across multiple pools to reduce interruption risk |
| `strategy` | "balanced" / "cost-first" / "performance-first" |
| `spot_target_pct` | % of nodes targeting Spot (slider 0–100%) |
| `buffer_pct` | Safety headroom above P95 usage during bin-packing (default 30%) |

### 17.4 API Endpoints Backing the Toggles
| Action | Frontend Call | Backend Route | DB Effect |
|--------|--------------|---------------|-----------|
| Read settings | `clusterAPI.getOptimizationSettings(id)` | `GET /api/v1/clusters/{id}/optimization-settings` | Read `ClusterOptimizationSettings` |
| Save settings | `clusterAPI.updateOptimizationSettings(id, data)` | `PUT /api/v1/clusters/{id}/optimization-settings` | Update `ClusterOptimizationSettings` |
| Toggle rebalance only | `clusterAPI.toggleAutoRebalance(id, enabled)` | `PATCH /api/v1/clusters/{id}/auto-rebalance?enabled=true` | Set `auto_rebalance_enabled` only |
| Save Karpenter config | `karpenterAPI.updateConfig(id, form)` | *(karpenter config endpoint)* | Syncs both toggles + Karpenter mode |

---

## 18. UI Section: Placement Intelligence Advisor

**Route**: `/placement-advisor` (standalone page) or right-side panel in cluster context
**Files**: `frontend/src/pages/PlacementAdvisorPage.jsx` + `frontend/src/components/placement/PlacementAdvisorDashboard.jsx`
**Hooks**: `usePlacementPolicies`, `usePlacementPolicySummary` in `frontend/src/hooks/usePlacementPolicies.js`

### 18.1 What This Section Does

The Placement Intelligence Advisor is the **AI decision layer** between raw workload analysis (WIE) and execution (PlacementController). It shows per-workload placement decisions and lets operators trigger a new advisor cycle.

| Component | Purpose |
|-----------|---------|
| **Summary bar** (4 stat cards) | Cluster-wide totals: estimated savings, Spot/OD target split, actionable workload count, rollout-ready count |
| **Policy table** | One row per workload: tier badge, confidence state, current replicas, OD/Spot targets, savings %, status badges |
| **Search + filters** | Filter by workload name, criticality tier (Platinum→Bronze), actionable status |
| **"Run Advisor Cycle" button** | Triggers `placementPolicyAPI.generate(clusterId)` → Celery task `run_placement_cycle_task` |
| **"Details" → per-workload** | Navigates to `/clusters/{id}/placement-policies/{workload_id}` → `PlacementPolicyDetail.jsx` |

### 18.2 Data Flow

```
WIE (workload_classification_service.py)
  └─→ WorkloadClassificationRecord (PostgreSQL)
        └─→ PlacementAdvisorService.run_cycle()  [Celery task every 10min]
              └─→ PlacementPolicyRecord (PostgreSQL)  ← source of truth
                    └─→ GET /api/v1/placement-policy/{cluster_id}/placement-policies
                          └─→ PlacementAdvisorDashboard.jsx (policy table)
```

### 18.3 API Endpoints

| Endpoint | Method | Auth | Feature Flag | Returns |
|----------|--------|------|--------------|---------|
| `/api/v1/placement-policy/{cluster_id}/placement-policies` | GET | JWT | `FEATURE_PLACEMENT_ADVISOR_ENABLED=true` | Paginated `PlacementPolicyRecord` list |
| `/api/v1/placement-policy/{cluster_id}/placement-policies/summary` | GET | JWT | same | Aggregated counts + savings totals |
| `/api/v1/placement-policy/{cluster_id}/placement-policies/{workload_id}` | GET | JWT | same | Single policy detail |
| `/api/v1/placement-policy/{cluster_id}/placement-policies/generate` | POST | JWT | same | Triggers `run_placement_cycle_task.delay(cluster_id)` |

**Feature gate**: All routes call `_check_feature_flag()` which raises `HTTP 404` if `settings.FEATURE_PLACEMENT_ADVISOR_ENABLED=False`. Set `FEATURE_PLACEMENT_ADVISOR_ENABLED=true` in environment to enable (set in `docker-compose.yml` for all services).

### 18.4 Key DB Table: `placement_policies` (`PlacementPolicyRecord`)

**Actual table**: `placement_policies` (`__tablename__ = "placement_policies"` in `backend/models/placement_policy.py`)

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(36) UUID PK | Row identifier |
| `cluster_id` | VARCHAR(36) FK→clusters | Owning cluster |
| `workload_id` | VARCHAR(512) | `namespace/name` (unique per cluster) |
| `namespace` | VARCHAR(253) | K8s namespace |
| `name` | VARCHAR(253) | Workload name |
| `criticality_tier` | VARCHAR(20) | Platinum / Gold / Silver / Bronze |
| `confidence_state` | VARCHAR(20) | CONFIRMED / PROVISIONAL |
| `spot_friendly` | BOOL | WIE-owned flag — API must not override |
| `observed_replicas` | INT | Current replica count at policy generation time |
| `ondemand_target` | INT | Recommended On-Demand replica count |
| `spot_target` | INT | Recommended Spot replica count |
| `spot_target_raw` | INT | Spot target before safety clamping |
| `traffic_skew_detected` | BOOL | True if CPU/request-rate CV exceeds threshold |
| `assigned_nodepool_class` | VARCHAR(50) | NodePool class label for Spot placement |
| `spot_instance_families` | JSONB | Allowed EC2 instance families |
| `spot_instance_types` | JSONB | Specific instance types for placement |
| `baseline_affinity` | JSONB | nodeAffinity patch for OD baseline pods |
| `burst_affinity` | JSONB | nodeAffinity patch for Spot burst pods |
| `topology_spread` | JSONB | TopologySpreadConstraints if applicable |
| `keda_min_replicas` | INT | KEDA ScaledObject min (if KEDA present) |
| `keda_max_replicas` | INT | KEDA ScaledObject max (if KEDA present) |
| `rollout_eligible` | BOOL | Subset of actionable — safe to start rollout now |
| `rollout_blocked_reason` | VARCHAR(512) | Why rollout is blocked (if not eligible) |
| `estimated_savings_pct` | FLOAT | % savings vs current OD baseline |
| `estimated_monthly_saving_usd` | FLOAT | Monthly $ savings if targets met |
| `actionable` | BOOL | True iff CONFIRMED + spot_target > 0 |
| `actionable_blocked_reason` | VARCHAR(512) | Why not actionable (if false) |
| `signals_used` | JSONB | List of WIE signal names used in this decision |
| `schema_version` | VARCHAR(10) | Policy schema version (current: `5.10`) |
| `input_hash` | VARCHAR(64) | SHA-256 of inputs — used for write suppression |
| `generated_at` / `created_at` / `updated_at` | DateTime | Timestamps |

### 18.5 Tier & Confidence Logic

The PlacementController does **not** branch on tier name directly. It reads `policy.get("disruption_safe", True)` from the policy dict. The Advisor sets `disruption_safe=False` for stateful/critical workloads. Conceptual mapping:

| Tier | Typical `disruption_safe` | PlacementController path |
|------|--------------------------|-------------------------|
| Platinum | `False` | `_dispatch_stateful_rollout()` — auto_rebalancer handles node-level migration |
| Gold | `False` | `_dispatch_stateful_rollout()` |
| Silver | `True` | `_dispatch_eviction()` — direct pod eviction to Spot |
| Bronze | `True` | `_dispatch_eviction()` |

| `confidence_state` | Meaning |
|-------------------|---------|
| `CONFIRMED` | WIE has seen consistent signal across ≥3 cycles — safe to act |
| `PROVISIONAL` | WIE has initial signal — advisor shows it but PC skips it |

### 18.6 Redis Keys Used by PlacementAdvisor

Key patterns are defined in `backend/redis_keys.py` and used by `placement_advisor_task.py`:

| Key (actual from `redis_keys.py`) | TTL | Purpose |
|-----------------------------------|-----|---------|
| `spot:placement:cycle_lock:{cluster_id}` | 300s | Prevents concurrent advisor Celery tasks for same cluster (`placement_cycle_lock_key()`) |
| `spot:placement:metrics:{cluster_id}` | 86400s | Cycle metrics HASH: `placement_policy_changed`, `placement_cycle_timeout_count`, write_suppressed counts, etc. (`placement_metrics_key()`) |
| `spot:placement:stability:{cluster_id}:{workload_id}` | variable | Stability signal per workload (`placement_stability_key()`) |
| `spot:placement:rollout_blocked:{cluster_id}:{workload_id}` | 14400s (4h) | Rollout block flag set by `placement_advisor_task.py` and `placement_rollout_service.py` |

---

## 19. UI Section: Workload Inventory Dashboard

**Route**: `RightSizingDashboard.jsx` → tab `workload` → renders `WorkloadInventoryDashboard`
**File**: `frontend/src/components/right-sizing/WorkloadInventoryDashboard.jsx`

### 19.1 What This Section Does

The Workload Inventory is the **real-time operational view** of all workloads in a cluster. It merges three data sources into one derived UI state:

| Data Source | What It Provides | API Call |
|-------------|-----------------|---------|
| WIE classifications | Workload names, confidence state, tier | `GET /api/v1/workload-classification/{cluster_id}/workloads` |
| Placement policies | OD/Spot targets | `GET /api/v1/placement-policy/{cluster_id}/placement-policies` |
| Pod metrics | Live pod state (capacity_type, status, CPU%) | `GET /api/v1/pods?cluster_id=...` |
| Agent actions | Recent eviction/drain/cordon events | `GET /api/v1/agent-actions?cluster_id=...` |
| NodeClaims | Karpenter-provisioned nodes | `GET /api/v1/nodeclaims?cluster_id=...` |

### 19.2 Tabs

| Tab | Shows | Data |
|-----|-------|------|
| **Workloads** | Table of all workloads with derived status, drift, progress, confidence | Merged WIE + policy + pod metrics |
| **Live Activity** | Real-time feed of agent actions, deduped by pod+action_type | `agent-actions` endpoint, polled every 3s |
| **System Insights** | Skip reason charts, rollout success gauge, timeout tracking, NodeClaims table | Mixed: metrics Redis + agent-actions + nodeclaims |

### 19.3 Workload Row Derivation Logic (Frontend)

```
For each WorkloadClassificationRecord:
  policy = PlacementPolicyRecord matching workload_id
  wPods  = PodMetric records matching workload_id

  current_spot = wPods.filter(capacity_type == 'spot').length
  current_od   = wPods.filter(capacity_type == 'on-demand').length
  target_spot  = policy.spot_target
  target_od    = policy.ondemand_target
  drift        = |current_od - target_od|
  driftLevel   = drift==0 → Low | drift<=2 → Medium | else → High
  progress     = target_spot==0 ? 100 : min(100, current_spot/target_spot * 100)

  STATUS (priority order):
    BLOCKED     if confidence_state != 'CONFIRMED'
    SCALING     if pending_pods / total > 20%
    THROTTLING  if cpu_usage_pct > 90% for > 50% of pods
    REBALANCING if drift > 1
    STABLE      otherwise
```

### 19.4 Summary Bar (Optimization Summary)

| Metric | Derivation |
|--------|-----------|
| Cluster Status | `activeActionsCount > 0` → "Optimizing" else "Stable" |
| Active Actions | `agentActionsData.filter(type === 'RUNNING').length` |
| Drift Level | Fixed label "Tracking" (future: aggregate drift across workloads) |
| Savings | Currently static placeholder — future: sum `estimated_monthly_saving_usd` from policies |

### 19.5 Search and Namespace Filter

**Search**: Client-side filter on `workload_id.toLowerCase().includes(searchTerm)` — no backend call.

**Namespaces filter**: UI button present but not yet wired. To implement:
1. Extract unique namespaces from `wItems` array: `[...new Set(wItems.map(w => w.namespace))]`
2. Pass `namespace` query param to `workloadClassificationAPI.getWorkloads(clusterId, { namespace: selectedNs })`
3. Backend route (`workload_classification_routes.py`) already accepts `namespace` filter param

**Status filter**: UI button present but not wired. To implement: Pass `confidence_state` or custom `status` filter to the API.

### 19.6 Backend Routes Serving Workload Inventory

| Route file | Path | DB Table | Auth |
|------------|------|----------|------|
| `workload_classification_routes.py` | `GET /api/v1/workload-classification/{cluster_id}/workloads` | `workload_classifications` | JWT |
| `placement_policy_routes.py` | `GET /api/v1/placement-policy/{cluster_id}/placement-policies` | `placement_policy_records` | JWT + feature flag |
| `execution_data_routes.py` | `GET /api/v1/pods?cluster_id=...` | `pod_metrics` (latest per pod via subquery) | JWT |
| `execution_data_routes.py` | `GET /api/v1/agent-actions?cluster_id=...` | `agent_actions` (last 20, newest first) | JWT |
| `execution_data_routes.py` | `GET /api/v1/nodeclaims?cluster_id=...` | *(placeholder — returns `[]`)* | JWT |

### 19.7 Live Activity Feed — Agent Action Mapping

| `AgentAction.status` DB value | UI `type` label | Icon |
|-------------------------------|----------------|------|
| `PENDING` | `RUNNING` | Blue spinning Loader2 |
| `PICKED_UP` | `RUNNING` | Blue spinning Loader2 |
| `COMPLETED` | `SUCCESS` | Green CheckCircle2 |
| `FAILED` | `RETRY` | Red AlertCircle |

**Deduplication**: Actions are keyed by `${pod_name}-${action_type}`. If two EVICT_POD actions for the same pod exist (retry pattern), only the most recent is shown.

---

## 20. Session Fix Log (2026-04-23)

All fixes applied in the 2026-04-23 session. Each entry lists: root cause → fix → file(s) changed.

### Fix 1 — `_mark_for_retry()` re-queued evicted pod as PENDING
**Root cause**: After eviction, the original pod no longer exists. Re-queuing the same `AgentAction` as `PENDING` caused the agent to receive a K8s 404 on the next poll cycle.
**Fix**: Always set `action.status = FAILED` in `_mark_for_retry()`. Also call `_decr_semaphore()` and sync `RebalancingAction` to `"failed"` for both the max-retry and sub-max-retry branches.
**File**: `backend/services/placement_controller_service.py` — `_mark_for_retry()`

### Fix 2 — `_scale_workload()` wrote to dead Redis queue
**Root cause**: `PlacementRolloutService._scale_workload()` used `redis.rpush(action_key, ...)` to a queue that nothing consumed.
**Fix**: Replaced with `AgentAction(type=UPDATE_DEPLOYMENT, status=PENDING)` DB write via `self.db.add()`.
**File**: `backend/services/placement_rollout_service.py` — `_scale_workload()`

### Fix 3 — `_evict_pod()` wrote to dead Redis queue
**Root cause**: Same as Fix 2 for `_evict_pod()`.
**Fix**: Replaced with `AgentAction(type=EVICT_POD, status=PENDING)` DB write.
**File**: `backend/services/placement_rollout_service.py` — `_evict_pod()`

### Fix 4 — No StatefulSet guard in `execute_stateful_rollout()`
**Root cause**: `execute_stateful_rollout()` used scale +1 for all workloads. For StatefulSets, adding +1 replica creates pod-N with a new PVC — it does NOT migrate the existing OD pod. StatefulSets need node-level migration.
**Fix**: Added early `return False` guard: `if workload.get("kind") == "StatefulSet": log warning + return False`.
**Note**: Not counted as `stateful_rollout_failed` — it's a routing decision, not a failure.
**File**: `backend/services/placement_rollout_service.py` — `execute_stateful_rollout()`

### Fix 5 — `submit_action_result()` never called `handle_eviction_result()`
**Root cause**: The post-eviction placement validation (did pod land on Spot?) was never triggered. `handle_eviction_result()` existed but was dead code.
**Fix**: Added call `handle_eviction_result(action, db, get_redis_client())` after `db.commit()` in `submit_action_result()`, guarded by `request.success and action.action_type.value == "EVICT_POD"`.
**File**: `backend/api/agent_routes.py` — `submit_action_result()`

### Fix 6 — Execution controller stubs returned `(True, ...)` silently
**Root cause**: `_wait_substitute_ready`, `_drain_node`, `_verify_workload_health`, `_terminate_node` all returned `(True, ...)` — faking success without executing anything. Emergency operations appeared to succeed but nothing happened.
**Fix**: Changed all stubs to return `(False, "stub: not wired to K8s/AWS API")` so the pipeline fails loudly instead of silently.
**File**: `backend/services/execution_controller.py`

### Fix 7 — `placement is None` (Pending pod) incorrectly marked FAILED
**Root cause**: `handle_eviction_result()` called `_mark_for_retry()` when `get_pod_placement()` returned None (pod still scheduling). But eviction succeeded — pod is being scheduled and may land on Spot.
**Fix**: When `placement is None` → mark `COMPLETED` + set `placement_check: pod_pending_at_validation_time` in `result`. PlacementController drift detection handles re-evaluation on next cycle.
**File**: `backend/services/placement_controller_service.py` — `handle_eviction_result()`

### Fix 8 — K8s API error during placement check marked action FAILED
**Root cause**: Exception in `get_pod_placement()` → `_mark_for_retry()` → FAILED. But eviction succeeded; we just can't check placement.
**Fix**: On API error → mark `COMPLETED` + set `placement_check: api_error:...` + `needs_revalidation: True`. PC drift detection handles it.
**File**: `backend/services/placement_controller_service.py` — `handle_eviction_result()`

### Fix 9 — Dead import of `cluster_mutex` in auto_rebalancer
**Root cause**: `from backend.utils.redis_locks import cluster_mutex as _cluster_mutex` was imported but `_cluster_mutex` was never used — raw `redis.get()` was used instead. This gave a false impression the HeartbeatLock context manager was being used.
**Fix**: Removed dead import. Added comment clarifying the direct `redis.get()` is intentional — AR must not acquire the mutex (only observe it).
**File**: `backend/workers/tasks/auto_rebalancer.py`

### Fix 10 — `placement_policy_routes.py` imported non-existent `backend.api.dependencies`
**Root cause**: `from backend.api.dependencies import get_db, get_current_user` — the module `backend.api.dependencies` does not exist. `get_db` lives in `backend.models.base`, `get_current_user` in `backend.core.dependencies`.
**Fix**: Split into two correct imports.
**File**: `backend/api/placement_policy_routes.py`

### Fix 11 — `placement_advisor_task.py` imported non-existent `backend.redis_client`
**Root cause**: `from backend.redis_client import redis_client` — no such module. Correct path is `backend.core.redis_client.get_redis_client()`.
**Fix**: Replaced with `from backend.core.redis_client import get_redis_client; redis_client = get_redis_client()`.
**Files**: `backend/workers/tasks/placement_advisor_task.py`, `backend/workers/tasks/placement_controller_task.py`

### Fix 12 — `WorkloadClassification` model name wrong in placement_advisor_task
**Root cause**: `from backend.models.workload_classification import WorkloadClassification` — the class is `WorkloadClassificationRecord`.
**Fix**: Aliased: `from backend.models.workload_classification import WorkloadClassificationRecord as WorkloadClassification`.
**File**: `backend/workers/tasks/placement_advisor_task.py`

### Fix 13 — `FEATURE_PLACEMENT_ADVISOR_ENABLED` defaulted to `False` → 404 on all routes
**Root cause**: `_check_feature_flag()` in `placement_policy_routes.py` raised `HTTP 404` because `settings.FEATURE_PLACEMENT_ADVISOR_ENABLED` defaults to `False`.
**Fix**: Added `FEATURE_PLACEMENT_ADVISOR_ENABLED: "true"` to backend, celery-worker, and celery-beat services in `docker/docker-compose.yml`.
**File**: `docker/docker-compose.yml`

### Fix 14 — `placementPolicyAPI.list()` used wrong URL (missing prefix)
**Root cause**: `api.js` line 209: `api.get('/api/v1/${clusterId}/placement-policies')` — missing the `/placement-policy/` router prefix that the backend uses.
**Fix**: Corrected to `api.get('/api/v1/placement-policy/${clusterId}/placement-policies')`.
**File**: `frontend/src/services/api.js`

### Fix 15 — `clustersAPI.getPods/getAgentActions` called wrong backend endpoints
**Root cause**: `getPods` called `getNodesDetailed` → 403; `getAgentActions` called `pending-commands` → 422. New `execution_data_routes.py` endpoints existed but weren't being called.
**Fix**: Rewired all three methods to use the new execution data endpoints.
**File**: `frontend/src/services/api.js`

### Fix 16 — `execution_data_routes.py` not mounted in `api_gateway.py`
**Root cause**: Router was added to `api_router` in `backend/api/__init__.py` but `api_gateway.py` registers routers directly — `api_router` aggregation is not used for new routers added to `__init__.py`.
**Fix**: Added `app.include_router(execution_data_router, prefix="/api/v1")` directly in `api_gateway.py`.
**File**: `backend/core/api_gateway.py`

### Fix 17 — `WorkloadInventoryDashboard` catch block never called `setLoading(false)`
**Root cause**: Any JavaScript exception in the try block after `Promise.allSettled` left `loading=true` forever — component showed "Loading real data..." indefinitely.
**Fix**: Added `if (mounted) setLoading(false)` to the catch block.
**File**: `frontend/src/components/right-sizing/WorkloadInventoryDashboard.jsx`

### Fix 18 — Placement Intelligence Advisor in dark theme
**Root cause**: `PlacementAdvisorDashboard.jsx` used `bg-gray-900`, `text-white`, `border-gray-800` throughout — dark mode hardcoded. `PlacementAdvisorPage.jsx` additionally wrapped it in `bg-gray-900 rounded-xl`.
**Fix**: Full light-theme rewrite matching the app design system (`bg-white`, `border-gray-200`, `text-gray-900`, `shadow-sm`, `bg-gray-50` table headers).
**Files**: `frontend/src/components/placement/PlacementAdvisorDashboard.jsx`, `frontend/src/pages/PlacementAdvisorPage.jsx`

---

## 21. Complete Redis Key Map

All active Redis keys in the system as of v7.0:

| Key Pattern | Owner | TTL | Type | Purpose |
|-------------|-------|-----|------|---------|
| `spot:cluster_mutex:{cluster_id}` | PlacementController | 60s + heartbeat | STRING | Cross-engine mutex — PC writes, AR reads-only |
| `spot:placement_controller:cycle_lock:{cluster_id}` | PlacementController Celery task | 300s | STRING | Prevents concurrent PC Celery tasks for same cluster |
| `spot:rebalance_lock:{cluster_id}` | auto_rebalancer | 600s | STRING | Prevents concurrent AR cycles for same cluster |
| `rebalance:active_count:{cluster_id}` | Both engines (PC + AR) | 300s | STRING (counter) | Shared batch semaphore — PC INCR/DECR, AR INCR/DECR, reconciled each AR cycle |
| `lock:workload:{cluster_id}:{workload_id}` | PlacementController | 30s | STRING | Prevents two PC cycles evicting from same workload simultaneously (`WORKLOAD_LOCK_KEY` in `backend/utils/redis_locks.py`) |
| `spot:placement_controller:cooldown:{cluster_id}:{workload_id}` | PlacementController | variable | STRING | Workload cooldown after eviction (10min success, 30min failure) |
| `spot:stabilization_lock:{cluster_id}` | auto_rebalancer | 60s | STRING | Post-action stabilization window |
| `spot:last_check:{cluster_id}` | auto_rebalancer | `check_interval - 14` s | STRING | Per-cluster interval gate (NX) |
| `spot:last_run_ts:{cluster_id}` | auto_rebalancer | `check_interval * 3` s | STRING | Timestamp of last AR run (for frontend countdown) |
| `spot:node_active_action:{node_id}` | auto_rebalancer | 86400s | STRING | Per-node lock preventing two migrations on same node |
| `spot:ondemand_fallback:{cluster_id}` | karpenter_service | 43200s (12h) | STRING | OD fallback active indicator |
| `spot:karpenter:installed:{cluster_id}` | Karpenter detection | 3600s | STRING | Karpenter installed flag |
| `spot:placement:metrics:{cluster_id}` | PlacementAdvisorService | 86400s | HASH | Advisor cycle metrics (`placement_metrics_key()` in `redis_keys.py`) |
| `spot:placement:cycle_lock:{cluster_id}` | placement_advisor_task | 300s | STRING | Celery task-level lock for advisor cycle (`placement_cycle_lock_key()` in `redis_keys.py`) |
| `spot:placement:stability:{cluster_id}:{workload_id}` | PlacementAdvisorService | variable | STRING | Per-workload stability signal (`placement_stability_key()` in `redis_keys.py`) |
| `spot:placement_controller:metrics:{cluster_id}` | PlacementController | 3600s | HASH | PC cycle metrics — `METRICS_KEY_TEMPLATE` in `placement_controller_service.py` line 57 |
| `spot:placement:rollout_blocked:{cluster_id}:{workload_id}` | PlacementRolloutService | 14400s (4h) | STRING | Rollout block flag — set by `placement_advisor_task.py` and `placement_rollout_service.py` |
| `spot:cluster:{cluster_id}:metrics` | auto_rebalancer | variable | HASH | AR metrics per cluster |
| `spot:skip_reasons:{cluster_id}` | auto_rebalancer | variable | HASH | AR skip reason tracking (mutex_contention, batch_limit, etc.) |
| `spot:stabilization_lock:{cluster_id}` (DB re-hydration) | auto_rebalancer | from DB | STRING | Re-created from `ClusterCooldownState` if Redis restarts |

---

## 22. Frontend API Route Map (v7.0)

Complete map of all `api.js` client calls → backend routes → DB tables:

### Cluster APIs (`clusterAPI` / `clustersAPI`)
| Frontend Call | HTTP | Backend Route | Returns |
|---------------|------|---------------|---------|
| `clusterAPI.list()` | GET | `/api/v1/clusters` | Cluster list |
| `clusterAPI.getCluster(id)` | GET | `/api/v1/clusters/{id}` | Cluster detail |
| `clusterAPI.getNodes(id)` | GET | `/api/v1/clusters/{id}/nodes` | Node list |
| `clusterAPI.getNodesDetailed(id)` | GET | `/api/v1/clusters/{id}/nodes/detailed` | Nodes with pod details |
| `clusterAPI.getOptimizationSettings(id)` | GET | `/api/v1/clusters/{id}/optimization-settings` | `ClusterOptimizationSettings` |
| `clusterAPI.updateOptimizationSettings(id, d)` | PUT | `/api/v1/clusters/{id}/optimization-settings` | Updates settings |
| `clusterAPI.toggleAutoRebalance(id, bool)` | PATCH | `/api/v1/clusters/{id}/auto-rebalance` | Toggles rebalance flag |
| **`clusterAPI.getPods(id, limit)`** | GET | `/api/v1/pods?cluster_id=...` | Latest `PodMetric` per pod |
| **`clusterAPI.getAgentActions(id, limit)`** | GET | `/api/v1/agent-actions?cluster_id=...` | Recent `AgentAction` records |
| **`clusterAPI.getNodeClaims(id)`** | GET | `/api/v1/nodeclaims?cluster_id=...` | Karpenter NodeClaims (stub: `[]`) |

*(Bold = new routes via `execution_data_routes.py`, registered in `api_gateway.py`)*

### Placement Policy APIs (`placementPolicyAPI`)
| Frontend Call | HTTP | Backend Route | Auth |
|---------------|------|---------------|------|
| `placementPolicyAPI.list(clusterId, params)` | GET | `/api/v1/placement-policy/{id}/placement-policies` | JWT + feature flag |
| `placementPolicyAPI.getSummary(clusterId)` | GET | `/api/v1/placement-policy/{id}/placement-policies/summary` | JWT + feature flag |
| `placementPolicyAPI.getDetail(clusterId, wId)` | GET | `/api/v1/placement-policy/{id}/placement-policies/{wId}` | JWT + feature flag |
| `placementPolicyAPI.generate(clusterId)` | POST | `/api/v1/placement-policy/{id}/placement-policies/generate` | JWT + feature flag |

### Workload Classification APIs (`workloadClassificationAPI`)
| Frontend Call | HTTP | Backend Route | DB Table |
|---------------|------|---------------|----------|
| `workloadClassificationAPI.getWorkloads(id, params)` | GET | `/api/v1/workload-classification/{id}/workloads` | `workload_classifications` |
| `workloadClassificationAPI.getSummary(id)` | GET | `/api/v1/workload-classification/{id}/summary` | Aggregated |
| `workloadClassificationAPI.getSpotCandidates(id)` | GET | `/api/v1/workload-classification/{id}/spot-candidates` | Filtered |
| `workloadClassificationAPI.getMetrics(id)` | GET | `/api/v1/workload-classification/{id}/metrics` | Redis metrics |

### Workload Classification Query Params (for Search + Namespace Filter)
| Param | Type | Backend Filter |
|-------|------|---------------|
| `namespace` | string | `WHERE namespace = ?` |
| `tier` | string | `WHERE criticality_tier = ?` |
| `confidence_state` | string | `WHERE confidence_state = ?` |
| `spot_friendly` | bool | `WHERE spot_friendly = ?` |
| `search` | string | `WHERE workload_id ILIKE ?` |
| `page` | int | Pagination offset |
| `page_size` | int | Pagination limit |

**Note**: Search and Namespace filters in `WorkloadInventoryDashboard.jsx` are currently client-side only. The backend routes accept these params — wire the UI inputs to `workloadClassificationAPI.getWorkloads(clusterId, { namespace, search })` to enable server-side filtering.

---

## 23. Placement Advisor UI — Button Behaviour (v8.0)

**File**: `frontend/src/components/placement/PlacementAdvisorDashboard.jsx`
**Hooks**: `frontend/src/hooks/usePlacementPolicies.js`

### 23a. "Refresh" Button

```
onClick → handleRefresh()
  └─ Promise.all([
       refreshSummary()  → GET /api/v1/placement-policy/{id}/placement-policies/summary
       refreshPolicies() → GET /api/v1/placement-policy/{id}/placement-policies
     ])
```

- Both requests run in parallel.
- Button shows a spinner (`isLoading={summaryLoading || policiesLoading}`) while either is in-flight.
- Outcome: re-renders the summary stats cards and the policy table with latest DB data.

### 23b. "Run Advisor Cycle" Button

```
onClick → handleGenerate()
  └─ setIsGenerating(true)
  └─ generatePolicies()
       └─ POST /api/v1/placement-policy/{id}/placement-policies/generate
            → 202 Accepted — triggers PlacementAdvisorService Celery task
  └─ setInterval(handleRefresh, 3000)  [polls every 3 s for 15 s / 5 attempts]
       └─ refreshSummary() + refreshPolicies() on each tick
  └─ after 5 attempts → clearInterval + setIsGenerating(false)
```

- The `generate` POST is fire-and-forget (returns 202). The UI does not wait for task completion synchronously.
- The 5-tick polling window (3 s × 5 = 15 s) catches the new `PlacementPolicy` DB rows that the Celery task writes.
- Button shows spinner (`isLoading={isGenerating}`) for the full 15-second polling window.
- Backend task: `placement_advisor_task.py` → `PlacementAdvisorService.run_advisor_cycle()` → writes/updates `placement_policies` table rows.

---

## 24. WorkloadInventoryDashboard — Real Data Fetching & Mock Removal (v8.0)

**File**: `frontend/src/components/right-sizing/WorkloadInventoryDashboard.jsx`

### 24a. Data Sources

All data is fetched via `Promise.allSettled` in a `useEffect` that polls every **3 seconds**:

| State Variable | API Call | Backend Route | Returns |
|---|---|---|---|
| `workloadsData` | `workloadClassificationAPI.getWorkloads(clusterId)` | `GET /api/v1/workload-classification/{id}/workloads` | WIE classification records |
| `policiesData` | `placementPolicyAPI.list(clusterId)` | `GET /api/v1/placement-policy/{id}/placement-policies` | Placement policies with `spot_target`, `ondemand_target` |
| `podsData` | `clustersAPI.getPods(clusterId)` | `GET /api/v1/pods?cluster_id=...` | Latest `PodMetric` per pod with `capacity_type` |
| `agentActionsData` | `clustersAPI.getAgentActions(clusterId)` | `GET /api/v1/agent-actions?cluster_id=...` | Recent `AgentAction` rows ordered newest-first |
| `nodeClaimsData` | `clustersAPI.getNodeClaims(clusterId)` | `GET /api/v1/nodeclaims?cluster_id=...` | Karpenter NodeClaims (stub `[]` until agent syncs CRDs) |
| `placementMetrics` | `clustersAPI.getPlacementMetrics(clusterId)` | `GET /api/v1/placement-metrics?cluster_id=...` | Redis `HGETALL spot:placement_controller:metrics:{id}` |
| `rolloutStatus` | `clustersAPI.getRolloutStatus(clusterId)` | `GET /api/v1/rollout-status?cluster_id=...` | Success rate from `AgentAction` table; pending timeouts |

### 24b. `enrichedWorkloads` useMemo

Combines three raw state arrays into the shape `WorkloadsTable` expects:

```
workloadsData (WIE)  +  policiesData  +  podsData
        ↓
enrichedWorkloads[]:
  uid          = w.workload_id
  name         = "${namespace}/${name}"
  current      = "${odPods} OD / ${spotPods} Spot"    (counted from podsData.capacity_type)
  target       = "${odTarget} OD / ${spotTarget} Spot" (from policy.ondemand_target / spot_target)
  driftValue   = |spotPods - spotTarget| + |odPods - odTarget|
  driftLevel   = High (>3) | Medium (>0) | Low (0)
  progress     = Math.round(w.spot_score * 100)        (0-1 fraction normalized to 0-100)
  confidence   = Math.round(w.confidence_score * 100)
  status       = BLOCKED (DRAFT) | SCALING (PROVISIONAL) | REBALANCING (drift>1) | THROTTLING (cpu>85%) | STABLE
```

### 24c. `mappedActions` useMemo

Transforms raw `AgentAction` DB records into the shape `LiveActivityFeed` expects:

```
agentActionsData[]
        ↓
mappedActions[]:
  type    = RUNNING (PENDING/PICKED_UP) | SUCCESS (COMPLETED) | RETRY (FAILED/EXPIRED)
  text    = "${ACTION_TYPE.replace(/_/g,' ')} on ${pod_name|workload_id|node_name|cluster:short_id}"
  time    = relative: Xd ago | Xh ago | Xm ago | Xs ago | Just now
  reason  = payload.reason || error_message || 'Queued by controller'
  target  = payload.target_node || payload.node_name || payload.pod_name || 'N/A'
  source  = KarpenterController (KARPENTER actions) | KedaController (KEDA) | PlacementController (default)
```

### 24d. Mock Data Removed

| Location | What Was Hardcoded | Replacement |
|---|---|---|
| `WorkloadsTable` | Passed raw WIE records (wrong shape) | Now receives `enrichedWorkloads` (computed via `useMemo`) |
| `LiveActivityFeed` | Passed raw `AgentAction` records (wrong fields) | Now receives `mappedActions` (computed via `useMemo`) |
| Optimization Summary Bar — Savings | `₹12,400/mo (approx)` | `enrichedWorkloads.filter(w => w.status !== 'BLOCKED').length` + "workloads active" |
| Optimization Summary Bar — Drift Level | `Tracking` (hardcoded yellow badge) | `overallDrift` useMemo — High/Medium/Low derived from `enrichedWorkloads` with matching color badge |
| SystemInsights — Rollout Success circle | `strokeDashoffset="27.1"` (always 91%) | `strokeDashoffset={301.5 * (1 - (rolloutStatus?.success_rate \|\| 0) / 100)}` |
| SystemInsights — Skip Reasons | `PDB Constraint 42% / Resource Starvation 28% / Topology Skew 15%` (fake) | `placementMetrics.skip_reasons[]` from Redis `spot:placement_controller:metrics:{id}` |
| SystemInsights — Timeout Tracking | `db-shard-01 9m/10m, frontend-web 1m/5m` (fake) | `rolloutStatus.active_timeouts[]` — PENDING `AgentAction` rows older than 10 min from DB |
| SystemInsights — Active NodeClaims | Hardcoded action rows | `nodeClaimsData[]` from `/api/v1/nodeclaims` (live stub, will populate when agent syncs Karpenter CRDs) |

---

# DEEP CODE AUDIT — v9.0 (Source-of-Truth: Live Code Only)

> **Methodology**: All claims verified from `.py` / `.jsx` / `.js` source files only.
> No `.md` or README files were used as evidence.
> Every finding includes `file:line` reference.
> Unverified items are explicitly marked **UNKNOWN**.

---

## §A. CONFLICT_HANDLING_REALITY

### A1. Cluster-Level Mutual Exclusion

**Implementation**: `backend/utils/redis_locks.py:24` — `cluster_mutex()` context manager.

```
Redis key: spot:cluster_mutex:{cluster_id}
SET NX EX {ttl}   (ttl = CLUSTER_MUTEX_TTL_SECS = 60 s)
```

**PlacementController acquires it** (`placement_controller_service.py:167`):
```python
with cluster_mutex(self.redis, cluster_id, owner="placement_controller", ttl=CLUSTER_MUTEX_TTL_SECS) as acquired:
    if not acquired:
        return   # skip cycle silently
```

**auto_rebalancer does NOT acquire it** (`auto_rebalancer.py:6957-6968`). It performs a **read-only GET**:
```python
_mutex_key = f"spot:cluster_mutex:{cluster.id}"
_mutex_holder = _redis.get(_mutex_key) if _redis else None
if _mutex_holder:
    _record_skip(_redis, cluster.id, "cluster_mutex_contention")
    continue
```

**Conflict handling type**: `IMPLICIT` — the mutex is best-effort. If PC crashes mid-cycle (before TTL expires), the key expires in 60 s and AR resumes. No deadlock protection beyond TTL.

### A2. KEDA Scaling Guard — PlacementController

**Implementation**: `placement_controller_service.py:512`

```python
def _scaling_guard_active(self, cluster_id: str) -> bool:
    pending = self._get_pending_pods_count(cluster_id)   # reads spot:cluster:pending_pods:{cluster_id}
    if pending > PENDING_PODS_THRESHOLD:                  # PENDING_PODS_THRESHOLD = 3
        return True
    return self._recent_keda_scaling_event(cluster_id)   # reads spot:keda:last_scale_event:{cluster_id}
```

**⚠️ VERIFIED GAP — NO WRITER EXISTS for either key:**

| Redis Key | Read By | Writer | Status |
|---|---|---|---|
| `spot:keda:last_scale_event:{cluster_id}` | `placement_controller_service.py:519` | **None found in entire codebase** | **DEAD — guard always returns False** |
| `spot:cluster:pending_pods:{cluster_id}` | `placement_controller_service.py:530` | **None found in entire codebase** | **DEAD — guard always returns 0** |

Search exhausted: `grep -r "keda:last_scale_event" --include="*.py"` returns only the read location. `grep -r "cluster:pending_pods" --include="*.py"` returns only the read location. No agent heartbeat, no webhook, no task writes these keys.

**Consequence**: PC's KEDA scaling guard is permanently disabled at runtime. PlacementController will evict pods even when KEDA is actively scaling a workload up.

### A3. Shared Batch Semaphore (Cross-Engine)

Both engines share `rebalance:active_count:{cluster_id}` (Redis INCR/DECR):

- **PC increments** on eviction dispatch (`placement_controller_service.py:764`)
- **PC decrements** on completion/failure (`placement_controller_service.py:991`)
- **AR increments** before creating new RebalancingAction (`auto_rebalancer.py:8962`)
- **AR decrements** in `_cleanup_rebalancing_resources()` (`auto_rebalancer.py:2395`)
- **AR reconciles** Redis counter vs actual DB count every 15 s (`auto_rebalancer.py:8517`)

**Conflict handling type**: `EXPLICIT` — atomic INCR/DECR prevents both engines from exceeding `max_concurrent_rebalance_actions` (default 1 per cluster).

### A4. Rolling-Update Guard (Per-Workload)

`placement_controller_service.py:298`:
```python
rollout = self._get_rollout_status(cluster_id, workload_id)
if rollout and rollout.updated_replicas != rollout.ready_replicas:
    metrics["evictions_skipped_scaling_guard"] += 1
    return
```
Source: live K8s API call (cached `ROLLOUT_STATUS_CACHE_TTL=30` s). **VERIFIED active.**

### A5. Conflict Resolution Summary

| Guard | Mechanism | Status |
|---|---|---|
| PC vs AR cluster-level | Redis mutex (SET NX EX 60) + AR read-only GET | ACTIVE — best-effort |
| PC eviction batch limit | `rebalance:active_count` shared INCR/DECR semaphore | ACTIVE — atomic |
| PC vs KEDA (scaling events) | `spot:keda:last_scale_event` read — **NO WRITER** | **DEAD CODE** |
| PC vs KEDA (pending pods) | `spot:cluster:pending_pods` read — **NO WRITER** | **DEAD CODE** |
| PC per-workload rolling update | K8s rollout status live check | ACTIVE |

**Overall**: Conflict resolution is **partially implicit / partially missing**. No centralized conflict arbiter exists. The most critical guard (KEDA scaling coexistence) is non-functional.

---

## §B. WORKLOAD_CLASSIFICATION_DUPLICATION

### B1. Three Coexisting Classification Systems

**System 1: `WorkloadInspector`** (`services/workload_inspector.py`)
- **Classifies**: Nodes into `NodeStatus` enum (STATELESS_ELIGIBLE, STATEFUL_PROTECTED, STATEFUL_ELIGIBLE, UNKNOWN)
- **Storage**: Redis cache per cluster
- **Callers**: `decision_engine.py:256`, `optimizer_coordinator.py:175`, `substitute_manager.py:374`, `rightsizing_service.py:131`, `event_monitor.py:139`, `scheduler.py:12`, `auto_rebalancer.py:7715`, `control_plane_loop.py:223`, `ascpai_routes.py:1303,1473`, `karpenter_routes.py:2096`
- **Status**: **ACTIVE** — primary safety gate for node-level operations

**System 2: `WorkloadIdentificationEngine` (WIE)** (`services/workload_identification_engine.py`)
- **Classifies**: Workloads (Deployments/StatefulSets) into tiers, confidence states, `spot_friendly` flags
- **Storage**: `workload_classifications` DB table + Redis
- **Callers**: `scheduler.py:82,173` (slow_loop + fast_loop), `workload_classification_routes.py:37`
- **Status**: **ACTIVE** — feeds Placement Advisor + frontend WorkloadInventoryDashboard

**System 3: `WorkloadClassifier`** (`services/workload_classifier.py`)
- **Classifies**: Pod-level workload type (helper)
- **Storage**: None (stateless function calls)
- **Callers**: `workload_inspector.py:26` (imports `OPERATOR_DB_OWNER_KINDS`), `workload_inspector.py:906` (calls `classify_workload()` inline during node scan)
- **Status**: **ACTIVE** — sub-component of WorkloadInspector, not standalone

### B2. Active vs Dead

| System | Dead? | Risk |
|---|---|---|
| `WorkloadInspector` | NO — 10+ active callers | None |
| `WorkloadIdentificationEngine` | NO — scheduled in `scheduler.py`, serves API | None |
| `WorkloadClassifier` | NO — called by WI internally | None |

### B3. Duplication Risk

WI classifies **nodes**; WIE classifies **workloads**. Conceptual overlap in answering "is this stateless?" but from different perspectives. **They do not share results.** If WI and WIE disagree on a workload's stateless status, node-level decisions (ExecutionController, SubstituteManager) use WI; Placement Advisor uses WIE. No synchronization between the two.

**Risk level**: `MEDIUM` — divergent classifications can cause PC to treat a node as safe to drain while WIE marks the workload as DRAFT/PROVISIONAL, leading to eviction of a workload that hasn't stabilized its placement policy yet.

---

## §C. DEPRECATED AND STUBBED CODE

### C1. ExecutionController Stubs (Confirmed via Code)

**File**: `services/execution_controller.py`

| Method | Line | Returns | Comment in code |
|---|---|---|---|
| `_wait_substitute_ready()` | 341 | `False, "stub: _wait_substitute_ready not wired to K8s API"` | "Not yet implemented — return False so callers fail loudly" |
| `_drain_node()` | 351 | `False, "stub: _drain_node not wired to K8s API"` | "Not yet implemented — use auto_rebalancer.create_pool_switch_actions() path" |
| `_verify_workload_health()` | 361 | `False, "stub: _verify_workload_health not wired to metrics API"` | "Not yet implemented — return False so post-drain verification fails loudly" |
| `_terminate_node()` | 376 | `False, "stub: _terminate_node not wired to AWS EC2 API"` | "Not yet implemented — the real path uses TERMINATE_NODE AgentAction" |

**Runtime effect**: `execute_replacement()` (`execution_controller.py:114`) calls all four stubs in sequence. Since `_wait_substitute_ready()` returns `False`, the execution pipeline fails at Step 3 (substitute ready check) every time, triggering `rollback()`. `execute_pool_switch()` (`execution_controller.py:211`) is separate and not affected.

### C2. ExecutionController Actual Usage

**Only caller**: `emergency_handler.py:70`:
```python
controller = ExecutionController(cluster_id=cluster_id, region=region)
result = controller.execute_replacement(bypass_double_gate=True, db=db)
```
No `substitute_manager` injected → `self.substitute_manager = None` → `_provision_substitute()` returns a placeholder ID → `_wait_substitute_ready()` returns `False` → pipeline fails → `rollback()` called → `circuit_breaker` is also `None` so no circuit breaker recording.

**Conclusion**: `ExecutionController.execute_replacement()` **always fails silently during emergency handling**. The emergency handler falls back to On-Demand (`emergency_handler.py:77`: "On-demand last resort").

### C3. Circuit Breaker

`services/circuit_breaker.py` exists. Referenced in `execution_controller.py:292`. But **never injected** at the only call site (`emergency_handler.py:71`). Circuit breaker is effectively dead in the emergency path.

### C4. Feature Flag Status

Both major features are **disabled by default** in production (`core/config.py`):

| Feature | Flag | Default |
|---|---|---|
| Placement Advisor | `FEATURE_PLACEMENT_ADVISOR_ENABLED` | `False` |
| Placement Controller | `FEATURE_PLACEMENT_CONTROLLER_ENABLED` | `False` |

`run_placement_controller_task` (`placement_controller_task.py:133`) checks `getattr(settings, "FEATURE_PLACEMENT_CONTROLLER_ENABLED", False)` — returns `"skipped - feature disabled"` unless explicitly enabled via env var.

### C5. SpotASGService

**Not deprecated**. Active routes in `karpenter_routes.py:2176,2245,2309,2497,2543,2597`. Used for non-Karpenter EKS managed nodegroups. Separate execution path from Karpenter/PC.

---

## §D. RETRY AND FAILURE BEHAVIOR

### D1. PlacementController Retry Flow

**Trigger**: `POST /api/v1/agents/actions/{action_id}/result` (`agent_routes.py:330`) with `success=True` + `action_type=EVICT_POD`

**Handler**: `handle_eviction_result()` (`placement_controller_service.py:877`) called from `agent_routes.py:386`

**Retry path** (`placement_controller_service.py:954`):
```
Pod found on wrong capacity type
    → _mark_for_retry(action, workload_id, db, redis)
        → action.retry_count += 1
        → action.status = FAILED        ← NOT re-queued as PENDING
        → error_message = "pod_evicted_but_not_on_spot (attempt N/3)"
        → _update_rebalancing_action(status='failed')
        → _decr_semaphore(cluster_id, redis)
        → if retry_count >= MAX_RETRY_COUNT (3):
              log WARNING "hit MAX_RETRY_COUNT — Marking FAILED permanently"
              (no further action, no alert)
```

**Key behavior**: On retry, the action is marked `FAILED`, not re-queued. PlacementController detects the drift again on the next 5-minute cycle and creates a **fresh** `AgentAction` for the new pod. This means retry is not per-action but per-cycle.

**Circuit breaker for PC**: None. `PlacementController` has no circuit breaker integration.

**Failure escalation**: None. Max retries hit → silent log warning only. No `notification_service` call, no alert, no operator escalation.

**Idempotency**: `_mark_for_retry()` is called at most once per result report (guarded by the API endpoint logic). But if the agent crashes after eviction and before reporting, the action stays `PICKED_UP` indefinitely — recovered by `drift_detector` task (stuck actions > 30 min check).

### D2. auto_rebalancer Retry / Failure

- `_cleanup_rebalancing_resources()` (`auto_rebalancer.py:2370`) — called on every exit path (success, fail, defer)
- DECR semaphore, delete Redis node lock, cancel orphan trigger pods, cancel orphan PENDING agent actions
- **Semaphore self-heal**: AR reconciles `rebalance:active_count` vs actual DB count every 15-second beat (`auto_rebalancer.py:8513`)

### D3. Risk Analysis

| Scenario | Behavior | Risk |
|---|---|---|
| Pod evicted, lands on OD (not Spot) | Action FAILED, next PC cycle creates new EVICT_POD for new pod | LOW — self-correcting every 5 min |
| Max retries reached (3×) | Permanent FAILED, no alert | MEDIUM — operator unaware |
| Agent crash after eviction, before report | Action stuck PICKED_UP until `drift_detector` 30-min check | MEDIUM — delayed recovery |
| EC2 replacement fails in ExecutionController | Always fails (stubs), falls back to OD | HIGH — emergency spot replacement is broken |
| Redis crash during DECR | Semaphore stuck, reconciler fixes within 15 s | LOW |

---

## §E. DRIFT DETECTION REALITY

### E1. Mechanisms Found in Code

**Mechanism 1: PlacementController 5-minute cycle** (`placement_controller_service.py:135`)
- Compares actual pod `capacity_type` (from DB/K8s) vs `PlacementPolicy.spot_target/ondemand_target`
- If drift found → dispatches `EVICT_POD` AgentAction
- **Drift persisted?** Yes — via `AgentAction` and `RebalancingAction` DB rows
- **Reacts to manual changes?** Only if pod capacityType changes in K8s (detected via next agent heartbeat push to `pod_metrics` table)

**Mechanism 2: `drift_detector` Celery task** (`health_monitor.py:207`) — every 15 min
- Checks: stuck `ExecutionState` rows > 30 min, stale `spot:advisor:last_scraped:{region}` data, empty pool caches, savings accuracy degradation
- **Does NOT compare desired vs actual pod placement state**
- Writes alerts to `drift_alerts:latest` Redis key (TTL 1800 s)
- **No corrective action taken** — monitoring only

**Mechanism 3: Cost drift check** (`scheduler.py:122`) — `SubstituteManager.check_cost_drift()`
- Compares current cluster cost vs baseline
- Logs warning, no corrective action

**Mechanism 4: Karpenter `drift_enabled`** (`schemas/policy_schemas.py:48`)
- Schema field `drift_enabled: bool = True` in `KarpenterConfig`
- Delegates actual NodePool drift handling to Karpenter itself (not backend code)

### E2. Gaps

| Gap | Detail |
|---|---|
| NodePool spec vs status comparison | **Not implemented** — no code in backend compares `NodePool.spec.limits` vs `NodePool.status.resources` |
| ScaledObject desired vs actual | **Not implemented** — KEDA ScaledObject state not tracked in backend DB |
| Manual cluster changes | **Not detected** — no watch/event loop on K8s API for out-of-band changes. Only the next agent heartbeat push reflects them |
| Drift persistence | PC drift correction creates `AgentAction` rows (persisted), but alerts are Redis-only (TTL 30 min) |

**drift_detection_present**: `YES` (pod-placement drift via PC) / `PARTIAL` (infrastructure drift)

---

## §F. SOURCE OF TRUTH VALIDATION

### F1. Full Eviction Lifecycle Trace (PlacementController Path)

```
1. CREATION
   placement_controller_service.py:711  _dispatch_eviction()
     → db.add(AgentAction(type=EVICT_POD, status=PENDING, retry_count=0))
     → db.add(RebalancingAction(source='placement_controller', agent_action_id=action.id))
     → redis.incr("rebalance:active_count:{cluster_id}")    [shared semaphore]
     → redis.incr("spot:placement_controller:metrics:{cluster_id}", "evictions_attempted")

2. AGENT PICKUP
   agent_routes.py (GET /clusters/{id}/actions/pending)
     → AgentAction.status = PICKED_UP

3. EXECUTION
   Agent K8s Eviction API call (in-cluster agent/actuator.py)

4. RESULT REPORTING
   agent_routes.py:330  POST /api/v1/agents/actions/{action_id}/result
     → AgentAction.status = COMPLETED (if success=True)
     → handle_eviction_result() called
         → Pod found on Spot → action.status = COMPLETED
                               _update_rebalancing_action('completed')
                               _decr_semaphore()
         → Pod found on OD  → _mark_for_retry()
                               action.status = FAILED
                               action.retry_count += 1
                               _update_rebalancing_action('failed')
                               _decr_semaphore()
         → K8s unreachable  → action.status = COMPLETED (benefit of doubt)
                               _decr_semaphore()
         → Pod Pending       → action.status = COMPLETED
                               _decr_semaphore()
```

### F2. Authoritative Table

**`AgentAction`** (`models/agent_action.py`) is the **primary source of truth** for eviction state.

**`RebalancingAction`** (`models/rebalancing_action.py`) is a **visibility mirror** — synchronized by `_update_rebalancing_action()` (`placement_controller_service.py:999`).

```python
def _update_rebalancing_action(agent_action_id: str, status: str, db) -> None:
    try:
        db.query(RebalancingAction).filter(
            RebalancingAction.agent_action_id == agent_action_id
        ).update({"status": status})
        db.commit()
    except Exception as e:
        logger.warning(...)   # ← silently swallowed — tables can diverge
```

**Consistency risk**: `_update_rebalancing_action()` wraps its DB write in `try/except` without re-raising. If the DB commit fails, `AgentAction` is `COMPLETED` but `RebalancingAction` stays `pending/in_progress`. The semaphore reconciler (`auto_rebalancer.py:8517`) counts both tables — a stale `RebalancingAction` inflates the active count, blocking new AR migrations until the next reconciliation.

---

## §G. KEDA INTERACTION VALIDATION

### G1. Integration Type: INDIRECT

PlacementController has **no direct KEDA API calls**. Interaction is entirely via Redis keys written externally:

| Integration Point | Code | Status |
|---|---|---|
| KEDA scale event detection | `placement_controller_service.py:518` reads `spot:keda:last_scale_event:{cluster_id}` | **DEAD — key never written** |
| Pending pods detection | `placement_controller_service.py:529` reads `spot:cluster:pending_pods:{cluster_id}` | **DEAD — key never written** |
| Pod scheduling preference | `placement_webhook_routes.py:77` injects soft Spot affinity at pod creation | **ACTIVE** |
| Autoscaler freeze during drain | `eviction_safety.py:981` — `freeze_autoscaler()` pauses HPA/ScaledObject during drain | **ACTIVE** — but only called from auto_rebalancer drain path, not PC |

### G2. Can PlacementController Fight KEDA?

**Yes — confirmed conflict scenario:**

```
T=0:   KEDA detects CPU spike → scales Deployment from 3→5 replicas
T=0:   2 new pods created → pod scheduling prefers Spot (webhook)
T=0:   Pods become Pending (awaiting Spot node)
T=5m:  PlacementController cycle runs
T=5m:  PC reads spot:cluster:pending_pods → 0 (key never written)
T=5m:  PC reads spot:keda:last_scale_event → nil (key never written)
T=5m:  _scaling_guard_active() returns False → guard bypassed
T=5m:  PC finds OD pods on workload → evicts them
T=5m:  Cluster temporarily under-capacity during KEDA scale-up + PC eviction
```

**Conflict risk**: `HIGH` — both KEDA and PC can reduce available pod capacity simultaneously.

### G3. KEDA Service Integration

`services/keda_service.py` — manages KEDA installation/uninstallation. No runtime interaction with PlacementController. `eviction_safety.py` can freeze ScaledObjects during auto_rebalancer drain operations (`services/eviction_safety.py:981`), but this path is NOT triggered by PlacementController evictions.

---

## §H. RECOMMENDED FIXES (Code-Reality Based)

### H1. CRITICAL — Wire KEDA Scaling Guard Keys

**Problem**: `spot:keda:last_scale_event:{cluster_id}` and `spot:cluster:pending_pods:{cluster_id}` are never written.

**Fix**: In `agent_routes.py` (agent heartbeat handler), after updating pod metrics:
```python
pending_count = db.query(PodMetric).filter(
    PodMetric.cluster_id == cluster_id,
    PodMetric.phase == "Pending"
).count()
redis.setex(f"spot:cluster:pending_pods:{cluster_id}", 120, str(pending_count))
```
For KEDA events: in `placement_webhook_routes.py` mutate-pods handler, detect KEDA-generated pods (label `app.kubernetes.io/managed-by=keda`) and write:
```python
redis.setex(f"spot:keda:last_scale_event:{cluster_id}", 300, str(time.time()))
```

### H2. HIGH — Wire ExecutionController Stubs to Real Paths

`execution_controller.py:330-376` — four methods return `False` with stub messages. Must be wired to:
- `_wait_substitute_ready()` → K8s `CoreV1Api.read_node_status()` polling loop
- `_drain_node()` → Create `CORDON_NODE + DRAIN_NODE` AgentAction records (as noted in the stub comments)
- `_verify_workload_health()` → Query `pod_metrics` table for pod readiness
- `_terminate_node()` → Create `TERMINATE_NODE` AgentAction or direct boto3 call

### H3. HIGH — Inject CircuitBreaker in EmergencyHandler

`emergency_handler.py:71` instantiates `ExecutionController` without `circuit_breaker`. Import and inject:
```python
from backend.services.circuit_breaker import CircuitBreaker
cb = CircuitBreaker(redis_client=redis)
controller = ExecutionController(cluster_id=cluster_id, region=region, circuit_breaker=cb)
```

### H4. MEDIUM — Escalate PlacementController Permanent Failures

`placement_controller_service.py:972` — `MAX_RETRY_COUNT` hit logs a WARNING but sends no alert. Wire `notification_service.send_alert()` to notify on permanent eviction failure.

### H5. MEDIUM — Make `_update_rebalancing_action()` Re-raise on Failure

`placement_controller_service.py:999` — silent `try/except` risks `AgentAction`/`RebalancingAction` divergence. Either re-raise (let caller handle) or add a dead-letter queue for failed sync writes.

### H6. LOW — Enable Feature Flags in Staging

`FEATURE_PLACEMENT_CONTROLLER_ENABLED` and `FEATURE_PLACEMENT_ADVISOR_ENABLED` default to `False` in `core/config.py:102,108`. Verify env vars are set in staging before any live validation.

---

## §I. VERIFIED vs UNKNOWN SUMMARY

| Claim | Status | Evidence |
|---|---|---|
| PC acquires cluster mutex before eviction | **VERIFIED** | `placement_controller_service.py:167` |
| AR skips cluster when PC holds mutex | **VERIFIED** | `auto_rebalancer.py:6958` |
| KEDA scaling guard reads key that is never written | **VERIFIED GAP** | `placement_controller_service.py:519` — no writer found in full codebase scan |
| Pending pods guard reads key that is never written | **VERIFIED GAP** | `placement_controller_service.py:530` — no writer found |
| ExecutionController stubs always return False | **VERIFIED** | `execution_controller.py:341,351,361,376` |
| ExecutionController used without SubstituteManager/CircuitBreaker | **VERIFIED** | `emergency_handler.py:71` |
| PlacementController disabled by default | **VERIFIED** | `core/config.py:108` — `default=False` |
| WI and WIE are separate non-overlapping systems | **VERIFIED** | WI=node-level Redis cache; WIE=workload-level DB |
| RebalancingAction can silently diverge from AgentAction | **VERIFIED** | `placement_controller_service.py:999` — silent except |
| drift_detector does NOT compare desired vs actual pod state | **VERIFIED** | `health_monitor.py:207-331` — checks only stuck actions/stale data |
| Who writes `spot:cluster:pending_pods` | **UNKNOWN** — agent heartbeat code not found in backend scan |
| Karpenter NodePool drift_enabled effect | **UNKNOWN** — delegated to Karpenter (out of backend code) |

---

# DELTA AUDIT — v10.0 (Gap-Fill Only, Code-Only Source)

> **Mode**: DELTA — does NOT re-audit §A–§I. Only adds missing sections, corrects PARTIAL claims, and raises new contradictions found in live code.
> Every statement includes `file:line` reference. No assumptions.

---

## §J. CORRECTIONS TO PREVIOUS AUDIT CLAIMS

| Previous Claim | Status | Correction |
|---|---|---|
| "AR skips cluster when PC holds mutex" | **PARTIAL** | AR skips the cluster for ONE 15-second beat only. If PC holds mutex for up to 60 s and AR runs every 15 s, AR may fire 3 more times before mutex expires. Each beat re-checks GET on the mutex key (`auto_rebalancer.py:6959`), so all 3 skips correctly. **VERIFIED CORRECT** |
| "PR's `_wait_for_new_pod_ready()` polls `spot:workload:state`" | **NEW CRITICAL** — see §K.3 | Key is NEVER WRITTEN — rollout wait always times out |
| "PDB enforced at eviction time" | **INVALID** | PC has no PDB check in `_process_workload_inner()`. PDB info is only used in WIE's `derive_disruption_safe()` at classification time. Eviction time has zero PDB guard. |
| "disruption_safe=False blocks eviction" | **PARTIAL** | Default is `policy.get("disruption_safe", True)` — `placement_controller_service.py:366`. Cache miss → defaults to True (stateless path) regardless of actual workload type. |
| "WorkloadState provides HPA/PDB to PlacementAdvisor at runtime" | **INVALID** | `spot:workload:state:{cluster_id}:{workload_id}` is never written anywhere. PlacementAdvisor always operates with `pdb_min_available=None`, `hpa_min_replicas=None`, `current_spot_pods=0`. |

---

## §K. EXECUTION_REALITY_CHECK

### K1. What Actually Runs in Production (Default Config)

With all defaults (`FEATURE_PLACEMENT_CONTROLLER_ENABLED=False`, `FEATURE_PLACEMENT_ADVISOR_ENABLED=False`, `PLACEMENT_ADVISOR_OBSERVATION_MODE=True`):

| Component | Runs? | Reason |
|---|---|---|
| `dispatch_placement_controller_cycles` beat task | YES — dispatches | Task fires every 5 min (`app.py:336`) but each per-cluster task returns `"skipped - feature disabled"` (`placement_controller_task.py:133`) |
| `PlacementController.run_cycle()` | **NO** | `FEATURE_PLACEMENT_CONTROLLER_ENABLED=False` by default |
| `run_placement_cycle_task` (PlacementAdvisor) | **NO** | `FEATURE_PLACEMENT_ADVISOR_ENABLED=False` by default (`placement_advisor_task.py:27`) |
| `auto_rebalancer` every 15 s | YES | No feature flag — always active (`app.py:156`) |
| `drift_detector` every 15 min | YES | No feature flag |
| `health_monitor` every 5 min | YES | No feature flag |
| `workers.control_plane.run_all_clusters_decision_cycle` | YES | No feature flag |
| `warm_spare.maintain_all_clusters` | YES | No feature flag |
| `workers.sqs_consumer.poll_interruption_queues` | YES — emergency queue | No feature flag |
| `workers.keda.monitor_install_actions` | YES | No feature flag |

**Net effect**: PlacementController and PlacementAdvisor produce zero production behaviour until env vars are set. All other subsystems run regardless.

### K2. Execution Paths That Never Reach AgentAction

| Path | File | Reason Never Reaches AgentAction |
|---|---|---|
| `ExecutionController.execute_replacement()` | `execution_controller.py:114` | All 4 internal steps return `(False, "stub")` — pipeline aborts at step 3 (`_wait_substitute_ready`) and calls `rollback()` |
| `PlacementController` stateless eviction | `placement_controller_service.py:368` | Never fires: `FEATURE_PLACEMENT_CONTROLLER_ENABLED=False` by default |
| `PlacementRolloutService._wait_for_new_pod_ready()` | `placement_rollout_service.py:307` | Polls `spot:workload:state` (never written) → always times out → rollout aborts |
| `recover_stale_stateful_migrations` | `placement_controller_task.py:249` | Reads `spot:workload:state` (never written) → `if not state_raw: continue` → always skips every workload |

### K3. `spot:workload:state` — Third Confirmed Dead Key

**Reads**:
- `placement_advisor_service.py:982` — reads `hpa_min_replicas`, `pdb_min_available`, `current_spot_pods`
- `placement_rollout_service.py:63, 100, 310` — polls for `ready_replicas` during rollout
- `placement_advisor_task.py:132` — checks `current_spot` post-rollout
- `placement_controller_task.py:249` — reads `original_replicas` for stale migration recovery

**Writer**: **NONE** found in full codebase scan. Not in `redis_keys.py` registry.

**Agent heartbeat** (`agent_routes.py:202–206`) writes THREE different keys:
```
spot:placement:agent_data:{cluster_id}:pod_metrics        TTL=120s
spot:placement:agent_data:{cluster_id}:cluster_spot_summary TTL=120s
spot:placement:agent_data:{cluster_id}:hpa_pdb            TTL=300s
```

None of these match `spot:workload:state:{cluster_id}:{workload_id}`. No translation layer exists between the cluster-level agent data and the per-workload state key.

**Runtime consequences**:

| Consumer | Expected | Actual (key missing) |
|---|---|---|
| `PlacementAdvisorService.compute_ondemand_baseline()` | Uses `pdb_min_available` as a floor factor | `pdb_min_available=None` → PDB floor NEVER applied |
| `PlacementAdvisorService` Gold-tier PDB gate | `has_pdb=True` enables 50% Spot | `has_pdb=False` always → Gold treated as 70% Spot tier |
| `PlacementRolloutService._wait_for_new_pod_ready()` | Polls until `ready_replicas > original` | Returns `False` immediately (loop exits timeout with no data) |
| `recover_stale_stateful_migrations` | Checks `original_replicas` for stale detection | Always `continue` → recovery task is a no-op |

---

## §L. REDIS_BEHAVIOR_ANALYSIS

### L1. Complete Dead-Key Map (No Writers Found)

| Redis Key | Template File | Read By | Writer | Risk |
|---|---|---|---|---|
| `spot:keda:last_scale_event:{cluster_id}` | `placement_controller_service.py:61` | `placement_controller_service.py:519` | **NONE** | HIGH — KEDA guard always bypassed |
| `spot:cluster:pending_pods:{cluster_id}` | `placement_controller_service.py:62` | `placement_controller_service.py:530` | **NONE** | HIGH — pending pods guard always 0 |
| `spot:workload:state:{cluster_id}:{workload_id}` | (not in registry) | `placement_advisor_service.py:982`, `placement_rollout_service.py:63` | **NONE** | HIGH — PDB/HPA/replica state always empty |

### L2. Keys With No TTL (Persistent, Can Grow)

From `redis_keys.py:23-29`:

| Key | TTL | Risk |
|---|---|---|
| `spot:cluster_state:{cluster_id}` | NONE | Grows indefinitely; never auto-expires if cluster deleted |
| `spot:rankings_version:{region}` | NONE | Version counter; safe but never cleaned |
| `spot:config:org_velocity_threshold` | NONE | Manual config key; no cleanup path |
| `lock:workload:{cluster_id}:{workload_id}` (on crash) | 30 s TTL via SET NX EX | If PC crashes between SET and DELETE, next cycle blocked for 30 s — acceptable |
| `spot:workload_tier:{cluster_id}:*` (override) | `api/cluster_routes.py:1468` — "TTL=None — override persists until cleared" | Manual tier override leaks permanently on cluster deletion |

### L3. TTL Inconsistency: `spot:node_active_action`

**Code**: `auto_rebalancer.py:9740` — `redis.setex(..., 1800, ...)` → **30 minutes**

**Comment**: `auto_rebalancer.py:2374` — `"spot:node_active_action stuck for 24h"` → **stale comment, 24 h is wrong**

`health.py:323` skips node termination if `spot:node_active_action` exists — if comment is trusted instead of code, operations engineers may wait 24h before manually clearing stuck locks when the actual TTL is 30 min.

### L4. Lock Safety Analysis

| Lock | Key | TTL | Crash Safety |
|---|---|---|---|
| Cluster mutex (PC) | `spot:cluster_mutex:{cluster_id}` | 60 s | Safe — AR retries after TTL |
| Workload lock (PC) | `lock:workload:{cluster_id}:{workload_id}` | 30 s | Safe — TTL self-heals |
| Cycle lock (PC task) | `spot:placement_controller:cycle_lock:{cluster_id}` | 300 s | Safe — prevents overlap |
| Node active action (AR) | `spot:node_active_action:{instance_id}` | 1800 s | Safe — sweeper clears at 45 min |
| AR heartbeat lock | 2700 s TTL + 60 s heartbeat | `auto_rebalancer.py:874` | Safe — heartbeat stops on crash, key expires |
| Autoscaler freeze | `spot:autoscaler_freeze:{ns}/{ctrl}` | 180 s | **RISK** — `cleanup_stale_autoscaler_freezes` runs every 5 min; 5 min window where HPA is frozen and AR is dead |

### L5. Orphaned Key Risk After Cluster Deletion

`cluster_service.py:797` — cluster deletion deletes `RebalancingAction` rows. But NO Redis key cleanup on cluster deletion is present. After deletion:
- `spot:cluster_mutex:{cluster_id}` — expires in 60 s (safe)
- `spot:workload_tier:{cluster_id}:*` manual overrides — **NEVER cleaned** (TTL=None)
- `spot:placement_controller:metrics:{cluster_id}` — expires in 3600 s (safe)
- `spot:node_classification:{cluster_id}` — expires in 10 min (safe)

---

## §M. AGENT_EXECUTION_TRUTH

### M1. Full AgentAction Lifecycle

```
PENDING
  ↓ GET /agents/actions/pending — agent picks up (agent_routes.py:229)
PICKED_UP
  ↓ Agent executes (K8s API call in-cluster)
  ↓ POST /agents/actions/{id}/result (agent_routes.py:330)
COMPLETED  ←── success=True, pod on correct capacity_type
FAILED     ←── success=True but pod on wrong capacity_type (handle_eviction_result)
FAILED     ←── success=False (agent reported failure)
EXPIRED    ←── drift_detector or health_monitor timeout cleanup
```

### M2. Stuck-State Recovery Paths

| Stuck State | Detected By | Timeout | Action |
|---|---|---|---|
| `PICKED_UP` AgentAction (agent crash) | `drift_detector` (`health_monitor.py:207`) | ~30 min (stuck > 30 min check) | Alert only — no status change in AgentAction |
| `in_progress` RebalancingAction | `auto_rebalancer.py:2685` stale expiry | 45 min | Status → `failed`, orphan EC2 terminated |
| `waiting_agent` RebalancingAction | `auto_rebalancer.py:2685` | 45 min | Status → `failed` |
| `terminating_source` RebalancingAction | Per-state timeout `auto_rebalancer.py:2682` | 10 min | Status → `failed` |
| Per-state heartbeat stop | `auto_rebalancer.py:2699` | 2 min since last heartbeat | Added to stale list |

**Gap**: The `drift_detector` fires an ALERT for stuck AgentActions (`health_monitor.py:246-252`) but does NOT change `action.status`. A PICKED_UP AgentAction that is stuck stays PICKED_UP forever until manual intervention or cluster deletion.

### M3. Consistency Gap: AgentAction vs Actual Cluster State

- No reconciliation between `pod_metrics` DB table and K8s live pod state
- Agent pushes pod metrics every heartbeat (TTL 120 s) — stale window = up to 2 min
- If agent is disconnected, PC reads stale pod data from DB and may evict pods that no longer exist (K8s 404 handled gracefully in agent)
- No watch/informer loop on K8s API in backend — fully agent-push-dependent

---

## §N. RACE_CONDITIONS_AND_CONCURRENCY

### N1. PC + AR Same-Workload Race (UNPROTECTED)

**Scenario** (occurs between PC 5-minute cycles):

```
T=0s    AR beat: selects node X (hosts workload W, 3 OD pods)
T=0s    AR: INCR rebalance:active_count  → 1
T=0s    AR: sets spot:node_active_action:{X} (TTL 1800s)
T=0s    AR: begins draining node X (cordon + evict 3 pods)
T=60s   AR: node X cordon complete, pods evicting
T=300s  PC: acquires cluster_mutex, acquires lock:workload:W
T=300s  PC: _get_od_pods() reads pod_metrics — sees 2 OD pods remaining on workload W (on node Y)
T=300s  PC: INCR rebalance:active_count  → 2
T=300s  PC: dispatches EVICT_POD for pods on node Y
T=310s  Agent evicts pods on Y. Workload W now has 0 pods.
```

**PC does not check `spot:node_active_action`** (`placement_controller_service.py:284-380` — no such check).
**AR does not check `lock:workload`** (`auto_rebalancer.py:6957-6970` — cluster mutex GET only).

**Combined effect**: Both engines reduce workload W's pod count. If W has `pdb_min_available=1`, and total pods were 3 → combined action brings it to 0 — PDB violated.

**Risk**: `HIGH` when both engines are active simultaneously on the same cluster.

### N2. Non-Locked Critical Section: `handle_eviction_result()`

`agent_routes.py:382-388` — `handle_eviction_result()` is called from a FastAPI route handler without any lock. Two concurrent agent callbacks for different pods of the same workload can call it simultaneously:

```python
# Thread 1: action_A → _mark_for_retry() → action_A.retry_count += 1
# Thread 2: action_B → _mark_for_retry() → action_B.retry_count += 1
# Both: _decr_semaphore() → redis.decr() (atomic — safe)
# Both: _update_rebalancing_action() → db.commit() (separate transactions — safe)
```

The DB transactions are per-action (separate rows), so this is effectively safe. The semaphore DECR is atomic. **Risk: LOW**.

### N3. `disruption_safe` Default Overrides DB Value

`placement_controller_service.py:366`:
```python
disruption_safe = policy.get("disruption_safe", True)
```

`_get_actionable_workloads()` reads policy from Redis (`POLICY_KEY_TEMPLATE`). If Redis key expired (TTL not set for policy cache — see `redis_keys.py:111`, no TTL in `placement_policy_key()`), the policy is fetched from DB and re-serialised. If the DB fetch path fails silently, `policy` dict is empty → `disruption_safe=True` regardless.

**VERIFY**: `services/placement_advisor_service.py:844` — `_write_policy()` writes to DB. Policy Redis cache is written by `_write_policy()` via:
```python
self.redis.setex(placement_policy_key(cluster_id, workload_id), POLICY_CACHE_TTL, json.dumps(...))
```
Need to confirm `POLICY_CACHE_TTL` value and whether it's set.
<br>→ `POLICY_CACHE_TTL` not found via search — **UNKNOWN** — if no TTL, key is permanent; if TTL expires between advisor cycles, PC reads stale/empty policy.

### N4. Workload Lock TTL vs Workload Processing Time

`WORKLOAD_LOCK_TTL_SECS = 30` (`placement_controller_service.py:55`).

For stateful workloads, `_dispatch_stateful_rollout()` creates a `RebalancingAction` record and waits:
- `placement_rollout_service._wait_for_new_pod_ready()` → up to `ROLLOUT_TIMEOUT_SECONDS` (unknown TTL)

If the rollout wait exceeds 30 s, the workload lock expires while `_process_workload_inner()` is still executing. A second PC cycle (unlikely given 5-min interval) could acquire the lock and dispatch a duplicate rollout.

**Risk**: LOW in practice (5-min cycle interval > 30 s lock), but the lock duration is insufficient if PC takes >30 s per workload.

---

## §O. CONFIG_VS_RUNTIME_BEHAVIOR

### O1. Double-Default-Off Creates Silent Zero-Output

```
FEATURE_PLACEMENT_ADVISOR_ENABLED=False  →  No policies written
FEATURE_PLACEMENT_CONTROLLER_ENABLED=False  →  No evictions
PLACEMENT_ADVISOR_OBSERVATION_MODE=True  →  All policies have actionable=False
```

If only `FEATURE_PLACEMENT_CONTROLLER_ENABLED=True` is set but `FEATURE_PLACEMENT_ADVISOR_ENABLED` remains `False`:
- No PlacementPolicies are ever written to Redis
- `_get_actionable_workloads()` scans Redis pattern and finds zero keys
- PC runs its full cycle, acquires mutex, finds no workloads, does nothing
- **No error or warning is logged** — silent no-op

**Reference**: `placement_controller_service.py:225` — `actionable_workloads = self._get_actionable_workloads(cluster_id)` with empty result → for loop doesn't execute.

### O2. `PLACEMENT_ADVISOR_OBSERVATION_MODE` Double-Enforced

Observation mode is enforced in two places:

1. `placement_advisor_service.py:734` — `actionable = not obs_mode and ...` → `policy.actionable=False`
2. `placement_advisor_service.py:600` — `_validate_prewrite()` raises if `observation_mode and policy.actionable` → write rejected

This means even if a caller manually sets `policy.actionable=True` before calling `_write_policy()`, the validator rejects it. **Double enforcement is correct** but adds complexity. Reference: `placement_advisor_service.py:589-601`.

### O3. Hardcoded Env-Var Defaults With No Runtime Override Path

| Variable | Default | Hardcoded In | Override Via |
|---|---|---|---|
| `PC_CLUSTER_BATCH_SIZE` | `2` | `placement_controller_service.py:52` | Env var only |
| `PC_MAX_RETRY_COUNT` | `3` | `placement_controller_service.py:53` | Env var only |
| `PC_SCALING_GUARD_WINDOW_SECS` | `120` | `placement_controller_service.py:47` | Env var only |
| `PC_PENDING_PODS_THRESHOLD` | `3` | `placement_controller_service.py:48` | Env var only |
| `WORKLOAD_LOCK_TTL_SECS` | `30` | `placement_controller_service.py:55` | **No env var — hardcoded** |
| `CLUSTER_MUTEX_TTL_SECS` | `60` | `placement_controller_service.py:54` | **No env var — hardcoded** |
| `POD_AGE_MIN_SECONDS` | `120` | `placement_controller_service.py:50` | **No env var — hardcoded** |

`WORKLOAD_LOCK_TTL_SECS`, `CLUSTER_MUTEX_TTL_SECS`, and `POD_AGE_MIN_SECONDS` cannot be changed without code change.

### O4. `POLICY_CACHE_TTL` — Unresolved

`placement_advisor_service.py` writes the policy Redis key via `placement_policy_key()`. The TTL value used for the `setex` call could not be confirmed in this search pass. **UNKNOWN** — if TTL is missing, policy keys persist indefinitely; if TTL is too short, PC reads stale data.

---

## §P. OBSERVABILITY_AND_DEBUGGING_GAPS

### P1. Silent Failure Inventory

| Failure | Location | Logging | Alerting |
|---|---|---|---|
| PC max retries hit | `placement_controller_service.py:972` | `logger.warning(...)` | **None** |
| `_update_rebalancing_action()` DB failure | `placement_controller_service.py:999` | `logger.warning(...)` | **None** |
| `handle_eviction_result()` exception | `agent_routes.py:387-390` | `logger.warning(...)` | **None** |
| `spot:workload:state` always empty | All callers check `if state_raw:` and silently use defaults | **None** | **None** |
| PC skips cluster (feature disabled) | `placement_controller_task.py:133` | `logger.debug(...)` | **None** |
| Stale AgentAction (PICKED_UP > 30 min) | `health_monitor.py:246` | `logger.warning(...)` | Redis `drift_alerts:latest` only |

### P2. Metrics Emitted vs Actionable

PC emits cycle metrics to `spot:placement_controller:metrics:{cluster_id}` (TTL 3600 s). Fields include:
- `evictions_attempted`, `evictions_skipped_cooldown`, `evictions_skipped_scaling_guard`
- `evictions_skipped_capacity`, `evictions_failed_due_to_no_replacement`

**Gap**: `evictions_skipped_scaling_guard` will always be 0 because `_scaling_guard_active()` always returns `False` (dead keys). This metric cannot be trusted to indicate KEDA conflicts.

### P3. Execution Reconstructability

| Question | Answer |
|---|---|
| Can an AgentAction be traced to its dispatching PC cycle? | **PARTIAL** — `RebalancingAction.source='placement_controller'` exists but no cycle_id FK |
| Can we know which workload triggered an eviction? | YES — `AgentAction.payload.workload_id` |
| Can we know why a policy changed? | YES — diff logged in `placement_advisor_service.py:804` |
| Can we know why PC skipped a workload? | PARTIAL — `evictions_skipped_*` counters, but no per-workload reason log |
| Can we detect if `spot:workload:state` is missing? | **NO** — all callers silently default to empty state |

---

## §Q. SAFETY_GUARD_VALIDATION

### Q1. PDB Check — NOT Present at Eviction Time

PC's `_process_workload_inner()` (`placement_controller_service.py:284`):

```
Step 1: Cooldown check
Step 2: Rolling-update guard (K8s rollout status)
Step 3: Get OD pods
Step 4: Compute excess_od
Step 5: Rate limit
Step 6: Select pods (youngest-first)
Step 7: Capacity check
Step 8: Shadow mode check
Step 9: disruption_safe → stateless or stateful path
```

**No PDB validation at any step.** The `disruption_safe` flag (Step 9) is computed by WIE at classification time (periodic, up to WIE cycle interval stale). If a PDB is added to a workload after the last WIE cycle, PC does not see it until the next classification run.

**Risk level**: `HIGH` — eviction can violate PDB if cluster state changes between WIE cycles.

### Q2. Last-Replica Eviction Risk

Scenario: `target_od=0`, workload has 1 OD pod, `disruption_safe=True`:
- `excess_od = max(0, 1 - 0) = 1`
- `pods_to_evict = [last_pod]`
- No minimum-survivor check
- `EVICT_POD` dispatched → workload has 0 pods

**No minimum-replicas guard in PC's stateless path.** The only protection is `disruption_safe=False` (which would route to stateful path), but `disruption_safe` defaults to `True` on cache miss.

**Reference**: `placement_controller_service.py:309, 321-326, 368-371` — no `len(remaining_pods) >= 1` check.

**Risk level**: `CRITICAL` — can evict the last pod of a workload.

### Q3. Safety Guards — Summary Table

| Guard | Mechanism | Enforced At | Status |
|---|---|---|---|
| PDB min_available | WIE `derive_disruption_safe()` (pre-computed) + **live `_would_violate_pdb()` check at dispatch** (P2-A) | Classification time + **Per-pod dispatch** | **ACTIVE** ✅ *(fixed 2026-04-24)* |
| Minimum replicas / last-pod guard | P0-B: reads `spot:workload:state.ready_replicas`; blocks if total running ≤ 1 | Per-cycle | **ACTIVE** ✅ *(fixed 2026-04-24)* |
| Active AgentAction coordination (workload) | P2-B L1: JSONB query — blocks workload if EVICT_POD PENDING/PICKED_UP exists | Per-workload | **ACTIVE** ✅ *(added 2026-04-24)* |
| Node migration lock (spot:node_active_action) | P2-B L2: node_name→instance_id batch lookup then Redis check | Per-pod selection | **ACTIVE** ✅ *(fixed 2026-04-24 — was using wrong key format)* |
| Rolling update in progress | `placement_controller_service.py:300` — live K8s rollout status | Per-cycle | ACTIVE |
| Per-workload cooldown (10 min) | `placement_controller_service.py:294` | Per-cycle | ACTIVE |
| KEDA scaling guard | `placement_controller_service.py:512` — reads `spot:keda:last_scale_event` | Per-cycle | **ACTIVE** ✅ *(fixed 2026-04-24 — key now written by P1-A)* |
| Spot capacity check | `placement_controller_service.py:336` | Per-cycle | ACTIVE |
| Pod age minimum (2 min) | `placement_controller_service.py:50, 324` | Per-cycle | ACTIVE |
| Shadow mode | `placement_controller_service.py:352` | Per-cycle | ACTIVE (when set) |
| Cluster batch limit (2/cycle) | `placement_controller_service.py:230` | Per-cycle | ACTIVE |

**Safety score for PlacementController (post-hardening)**: 10/10 guards active. *(Was 5/9 before 2026-04-24 hardening.)*

---

## §R. SYSTEM RELIABILITY SCORE

> **Pre-hardening (2026-04-23): 4.5 / 10** | **Post-hardening (2026-04-24): 7.5 / 10**

### Post-hardening score breakdown

| Dimension | Old | New | Reasoning |
|---|---|---|---|
| Execution correctness | 3/10 | 8/10 | Redis keys all written; ExecutionController wired to AgentAction dispatch; last-replica guard fixed |
| Conflict handling | 5/10 | 8/10 | KEDA guard now live; workload-level EVICT_POD coordination active; node lock cross-system resolved |
| Recovery / resilience | 6/10 | 8/10 | PICKED_UP auto-expire added (P3-B); semaphore decrement on expiry; CircuitBreaker injected in emergency path |
| Safety guards | 4/10 | 9/10 | All 10 guards now active; live PDB check added; last-pod guard fixed; node lock key format corrected |
| Observability | 4/10 | 7/10 | 4 new skip counters; send_alert on permanent failure; _update_rebalancing_action upgraded to logger.error |
| Feature flag correctness | 7/10 | 7/10 | Unchanged |
| Data consistency | 3/10 | 7/10 | All 4 dead Redis keys now written; spot:workload:pods still unwritten (P0-B migrated to workload:state) |

---

## §S. TOP 10 IMMEDIATE FIX RECOMMENDATIONS (Code-Reality Based)

> **Status as of 2026-04-24: ALL 10 ITEMS RESOLVED** — see §T for implementation details.

| Priority | Fix | File | Status |
|---|---|---|---|
| **P0** | Write `spot:workload:state:{cluster_id}:{workload_id}` from agent heartbeat | `agent_routes.py` | ✅ DONE — P0-A |
| **P0** | Add minimum-survivor guard in PC | `placement_controller_service.py` | ✅ DONE — P0-B (also fixed BUG-7) |
| **P1** | Write `spot:keda:last_scale_event` from webhook | `placement_webhook_routes.py` | ✅ DONE — P1-A |
| **P1** | Write `spot:cluster:pending_pods` from heartbeat | `agent_routes.py` | ✅ DONE — P1-B |
| **P1** | Wire `ExecutionController` stubs to real AgentAction dispatch | `execution_controller.py` | ✅ DONE — P1-C |
| **P1** | Inject `CircuitBreaker` in `emergency_handler.py` | `emergency_handler.py` | ✅ DONE — P1-D |
| **P2** | Add live PDB check in PC before dispatching EVICT_POD | `placement_controller_service.py` | ✅ DONE — P2-A (also fixed BUG-8) |
| **P2** | Have PC check `spot:node_active_action` before evicting | `placement_controller_service.py` | ✅ DONE — P2-B (also fixed BUG-9) |
| **P2** | Fix TTL comment on `spot:node_active_action` | `auto_rebalancer.py` | ✅ DONE — P2-C |
| **P3** | Alert when PC hits `MAX_RETRY_COUNT` permanently | `placement_controller_service.py` | ✅ DONE — P3-A |

---

## §T. BACKEND HARDENING EXECUTION REPORT (2026-04-24)

**Scope**: plan.md P0–P4 full implementation + VERIFY_AND_COMPLETE_HARDENING_PLAN audit pass.
**Result**: All 10 §S recommendations resolved; 3 additional bugs (BUG-7/8/9) found and fixed during audit.

---

### §T-1. Redis Key Writers Added

Four Redis keys were being read by guards but never written. All four are now written:

| Key | TTL | Writer | Reader |
|---|---|---|---|
| `spot:workload:state:{cluster_id}:{workload_id}` | 300s | `agent_routes.py` — per heartbeat, per workload from `hpa_pdb_data` | `placement_controller_service.py` `_would_violate_pdb()`, P0-B guard, `placement_rollout_service.py`, `placement_advisor_service.py` |
| `spot:cluster:pending_pods:{cluster_id}` | 120s | `agent_routes.py` — from `cluster_spot_summary.unhealthy_pending_pods` | `execution_controller.py` `_verify_workload_health()` |
| `spot:keda:last_scale_event:{cluster_id}` | 300s | `placement_webhook_routes.py` — when KEDA-managed pod is admitted | `placement_controller_service.py` KEDA scaling guard |
| `spot:workload:state.ready_replicas` field | (within above) | `agent_routes.py` — `spot_pods + od_pods` from `pod_metrics_per_workload` | `_would_violate_pdb()`, P0-B last-pod guard |

**Key confirmed never written** (documented, not fixed): `spot:workload:pods` — P0-B guard was migrated away from this key to `spot:workload:state.ready_replicas`.

---

### §T-2. Safety Guards Added/Fixed

#### P0-B — Last-Pod Eviction Guard (`placement_controller_service.py`)

- **Implementation**: Before computing excess OD pods, reads `spot:workload:state.ready_replicas` (total spot+od running). If `total_running <= 1`, skips with counter `evictions_skipped_last_pod`.
- **BUG-7 fixed**: Original implementation read `spot:workload:pods` (never written). Fallback used only `len(current_od_pods)` → incorrectly blocked eviction when Spot pods existed. Migrated to `spot:workload:state.ready_replicas`.
- **Fail-safe**: Falls back to `len(current_od_pods)` if state key absent.

#### P2-A — Live PDB Check (`placement_controller_service.py`)

- **New method**: `_would_violate_pdb(cluster_id, workload_id) -> bool` reads `spot:workload:state`. Returns `True` (block) if `(ready_replicas - 1) < pdb_min_available`.
- **Called**: Per-pod in the disruption-safe eviction loop, before `_dispatch_eviction()`. Skips with counter `evictions_skipped_pdb`.
- **BUG-8 fixed**: `ready_replicas` was sourced from `hpa_pdb_data` which never contains it. Agent's `pod_metrics_per_workload` provides `spot_pods` + `od_pods` — now used as `ready_replicas` source in the state writer.
- **Fail-safe**: Returns `False` (allow) if state key absent or `pdb_min_available` is None.

#### P2-B L1 — Workload-Level AgentAction Coordination (`placement_controller_service.py`)

- **Implementation**: In `_process_workload_inner()`, before pod distribution, opens a short-lived DB session and queries:
  ```python
  AgentAction.cluster_id == cluster_id
  AgentAction.action_type == EVICT_POD
  AgentAction.status.in_([PENDING, PICKED_UP])
  AgentAction.payload.op("->>")( "workload_id") == workload_id
  ```
- **Key decision**: `AgentAction` has no `workload_id` column — value is in JSONB `payload`. Uses SQLAlchemy `op("->>")(...)` for PostgreSQL JSONB text extraction.
- **Counter**: `evictions_skipped_active_action`

#### P2-B L2 — Node-Level Lock Coordination (`placement_controller_service.py`)

- **Implementation**: In `_select_burst_pods()`, pre-builds `node_name→instance_id` map via single batch `Instance` table query. Checks `redis.exists(f"spot:node_active_action:{instance_id}")` per pod.
- **BUG-9 fixed**: Original used `pod.node` (K8s node name, e.g. `ip-10-0-1-234.ec2.internal`). `auto_rebalancer` sets key with `instance.instance_id` (e.g. `i-1234567890abcdef0`). These never matched — lock check was a no-op.
- **Fix**: Single `Instance.node_name.in_(...)` batch query before the filter loop builds the mapping. Zero extra queries per pod.
- **Counter**: `evictions_skipped_node_locked`

---

### §T-3. ExecutionController Stub Methods Wired (P1-C)

**File**: `backend/services/execution_controller.py`

| Method | Was | Now |
|---|---|---|
| `_wait_substitute_ready()` | `return False, "stub"` | Polls `Instance` table by `instance_id` until `status in ("READY", "running")`. 10s intervals, respects `timeout_seconds`. |
| `_drain_node()` | `return False, "stub"` | Creates `AgentAction(DRAIN_NODE, priority=10)` via DB session. Returns `True` = dispatched. |
| `_verify_workload_health()` | `return False, "stub"` | Reads `spot:cluster:pending_pods:{cluster_id}` from Redis. Blocks if `pending > PC_PENDING_PODS_THRESHOLD` (env var, default 3). |
| `_terminate_node()` | `return False, "stub"` | Creates `AgentAction(TERMINATE_NODE, priority=10)` via DB session. Returns `True` = dispatched. |

**NR-1 (known risk)**: `_drain_node` dispatches async and returns immediately — `execute_pool_switch` treats dispatch=success. Node termination may race with agent drain completion.

---

### §T-4. CircuitBreaker Injection (P1-D)

**File**: `backend/services/emergency_handler.py`

Before constructing `ExecutionController`, now instantiates `CircuitBreaker(redis_client=_r)` and passes it as `circuit_breaker=_cb`. Guarded with `if _cb_redis else None` so Redis unavailability does not crash the emergency path.

---

### §T-5. Alerting and Observability (P3-A, P3-B, P3-C)

#### P3-A — Alert on Permanent Eviction Failure

- **File**: `backend/services/placement_controller_service.py` `_mark_for_retry()`
- When `retry_count >= MAX_RETRY_COUNT`, calls `asyncio.run(NotificationService(db).send_alert(alert_type=AlertType.EXECUTION_FAILED, ...))`.
- `organization_id` looked up from `Cluster` model. Fully wrapped in `try/except` — failure logs a warning, never disrupts retry logic.
- **NR-3**: `asyncio.run()` raises `RuntimeError` if Celery worker has a live event loop. Alert is best-effort; exception is caught.

#### P3-B — Auto-Expire Stuck PICKED_UP AgentActions

- **File**: `backend/workers/tasks/health_monitor.py` `run_drift_detector()`
- Added "Check 1b" after existing stuck-RebalancingAction check.
- Queries `AgentAction(status=PICKED_UP, picked_up_at <= now-30min)`. Sets each to `EXPIRED`, appends `EXPIRED_ACTION` alert string, decrements `rebalance:active_count:{cluster_id}` semaphore.
- Single `db.commit()` after all updates to minimise round trips.

#### P3-C — Upgrade Error Logging in `_update_rebalancing_action`

- **File**: `backend/services/placement_controller_service.py`
- `logger.warning(...)` → `logger.error(..., exc_info=True)` with full context (agent_action_id, target_status, exception).

---

### §T-6. New Metric Counters

All four counters are initialised in `run_cycle()` and emitted in `_emit_metrics()` Redis payload:

| Counter | Trigger |
|---|---|
| `evictions_skipped_last_pod` | P0-B guard fires (total running ≤ 1) |
| `evictions_skipped_pdb` | P2-A `_would_violate_pdb()` returns True |
| `evictions_skipped_active_action` | P2-B L1 finds PENDING/PICKED_UP EVICT_POD for workload |
| `evictions_skipped_node_locked` | P2-B L2 finds `spot:node_active_action` for node's instance |

---

### §T-7. Dead Code Removed (P4)

Three Celery task files confirmed unscheduled in `app.py` beat schedule were moved to `temp-bin/` with `DEPRECATED_` prefix:

| Source | Destination |
|---|---|
| `backend/workers/tasks/optimization.py` | `temp-bin/DEPRECATED_optimization.py` |
| `backend/workers/tasks/event_processor.py` | `temp-bin/DEPRECATED_event_processor.py` |
| `backend/workers/tasks/report_worker.py` | `temp-bin/DEPRECATED_report_worker.py` |

`backend/workers/tasks/__init__.py` imports and `__all__` entries cleaned. **Note**: `backend/services/emergency_event_processor.py` is a different file — NOT moved, still active.

---

### §T-8. TTL Comment Fixes (P2-C)

**File**: `backend/workers/tasks/auto_rebalancer.py`

| Line | Was | Now |
|---|---|---|
| L2374 | `spot:node_active_action stuck for 24h` | `stuck for 30 min` |
| L8928 | `(10-min TTL)` | `(30-min TTL, 1800s)` |

Actual `setex` at L9741–9743 uses `1800` (30 min). Comments now match code.

---

### §T-9. Bugs Found During Audit

| Bug | Location | Problem | Fix |
|---|---|---|---|
| **BUG-7** | `placement_controller_service.py` P0-B | Read `spot:workload:pods` (never written anywhere in codebase). Fallback to OD-only count incorrectly blocked eviction when Spot pods running. | Replaced with `spot:workload:state.ready_replicas` (P0-A key). |
| **BUG-8** | `agent_routes.py` `spot:workload:state` writer | `ready_replicas` sourced from `hpa_pdb_data` which never contains it → always `None` → `_would_violate_pdb()` always returned `False`. | Source from `pod_metrics_per_workload[wid].spot_pods + od_pods`. |
| **BUG-9** | `placement_controller_service.py` `_select_burst_pods()` | Node lock checked `spot:node_active_action:{pod.node}` (node_name) but key is set by `auto_rebalancer` using `instance.instance_id`. Format mismatch → check was dead. | Pre-build `node_name→instance_id` map via single batch `Instance` table query. |

---

### §T-10. Remaining Risks (Accepted, Documented)

| ID | Risk | Mitigation |
|---|---|---|
| NR-1 | `_drain_node` dispatches async — `execute_pool_switch` treats dispatch=success; node may be terminated before agent drain completes | Monitor `DRAIN_NODE` action completion time; add wait-for-completion loop in future |
| NR-3 | `asyncio.run()` in P3-A alert fails if Celery worker runs with live event loop | Alert is best-effort; `try/except` catches and logs; retry logic unaffected |
| NR-4 | `spot:workload:state` TTL=300s matches PC 5-min cycle; if agent down >5 min, state expires and P0-B/P2-A fail open | Acceptable — rolling-update, cooldown, and semaphore guards still protect |

---

### §T-11. Full File Change Log

| File | Changes |
|---|---|
| `backend/api/agent_routes.py` | P0-A: writes `spot:workload:state` per workload; P1-B: writes `spot:cluster:pending_pods`; BUG-8 fix: `ready_replicas` from `pod_metrics_per_workload` |
| `backend/api/placement_webhook_routes.py` | P1-A: writes `spot:keda:last_scale_event` when KEDA-managed pod admitted |
| `backend/services/placement_controller_service.py` | P0-B: last-pod guard (BUG-7 fix); P2-A: `_would_violate_pdb()` + per-pod check; P2-B L1: JSONB AgentAction coordination; P2-B L2: node lock with instance_id (BUG-9 fix); P3-A: `send_alert` on max retries; P3-C: `logger.error(exc_info=True)`; 4 new metric counters |
| `backend/services/execution_controller.py` | P1-C: all 4 stubs wired to real AgentAction dispatch or Redis check |
| `backend/services/emergency_handler.py` | P1-D: `CircuitBreaker` instantiated and injected |
| `backend/workers/tasks/auto_rebalancer.py` | P2-C: TTL comment fixes (2 lines) |
| `backend/workers/tasks/health_monitor.py` | P3-B: PICKED_UP auto-expiry in `run_drift_detector()` |
| `backend/workers/tasks/__init__.py` | P4: removed imports of 3 dead task files |
| `temp-bin/DEPRECATED_optimization.py` | P4: moved from workers/tasks/optimization.py |
| `temp-bin/DEPRECATED_event_processor.py` | P4: moved from workers/tasks/event_processor.py |
| `temp-bin/DEPRECATED_report_worker.py` | P4: moved from workers/tasks/report_worker.py |

---

# §U. COMPLETE DATABASE SCHEMA REFERENCE

> **Source**: `backend/models/*.py` — verified from live code only. All tables use PostgreSQL.

## U1. `clusters` (`models/cluster.py`)

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `id` | VARCHAR(36) PK | UUID | |
| `cluster_uid` | VARCHAR(8) UNIQUE INDEX | hex[:8] | Short human-readable display ID |
| `name` / `arn` / `region` | VARCHAR | — | `arn` is UNIQUE INDEX |
| `account_id` | VARCHAR FK→accounts | — | Owning AWS account |
| `cluster_type` | ENUM(EKS,ECS,GKE,AKS) | EKS | |
| `status` | ENUM(PENDING,DISCOVERED,ACTIVE,INACTIVE,ERROR,TERMINATED,DISCONNECTED,DEGRADED,DELETED) | DISCOVERED | |
| `agent_installed` / `is_agentless` | VARCHAR | 'N'/'Y' | 'Y' or 'N' strings |
| `api_key` | VARCHAR | NULL | Auto-generated for agent auth |
| `aws_role_arn` / `aws_external_id` | VARCHAR | NULL | Cross-account IAM role + STS |
| `last_heartbeat` | DATETIME | NULL | Last agent push timestamp |
| `monthly_cost` / `estimated_savings` | INTEGER | 0 | USD |
| `potential_savings_monthly` / `realized_savings_monthly` | FLOAT | 0.0 | Teaser savings data |
| `node_count` / `spot_count` / `cpu_total` / `mem_total` | INTEGER | 0 | Updated by discovery/agent |
| `cpu_usage_pct` / `mem_usage_pct` | FLOAT | 0.0 | |
| `inventory_summary` | JSON | {} | `{total, on_demand, spot}` |
| `karpenter_mode` | ENUM(dry_run,auto) | NULL | NULL = not installed |
| `optimization_mode` | VARCHAR(20) | 'BALANCED' | COST_FIRST / BALANCED / NO_DOWNTIME_FIRST |
| `model_version` | VARCHAR(10) | '6' | ASCP.AI pinned model version |
| `workload_type` | VARCHAR(10) | 'STATELESS' | Display cache only — NOT used for decisions |
| `auto_rebalance_enabled` / `rightsizing_enabled` | BOOLEAN | False | Legacy column — settings table is source of truth |
| `is_hibernating` | BOOLEAN | False | True when hibernated |
| `hibernation_state` | JSON | NULL | Saved replica counts for wake |
| `hibernation_lock` / `hibernation_lock_acquired_at` | VARCHAR / DATETIME | NULL | Worker UUID + acquisition time |
| `is_dismissed` | BOOLEAN | False | Prevents re-discovery |
| `managed_node_group_deleted` | BOOLEAN | False | Original MNG removed flag |
| `created_at` / `updated_at` | DATETIME | utcnow | `updated_at` auto-refreshes |

**Cascade relationships**: `agent_actions`, `pod_metrics`, `rightsizing_proposals`, `optimization_settings`, `stateless_rules`, `stateful_rules`, `optimization_strategy_profile`

---

## U2. `cluster_optimization_settings` (`models/cluster.py`)

One-to-one with `clusters`. Written by `PUT /clusters/{id}/optimization-settings`.

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `cluster_id` | VARCHAR FK→clusters PK | — | |
| `auto_rebalance_enabled` / `auto_rightsizing_enabled` / `auto_stateful_rightsizing_enabled` | BOOLEAN | False | Engine activation toggles |
| `manual_approval_required` | BOOLEAN | False | Routes changes to team lead |
| `target_spot_exposure_pct` | INTEGER | 100 | % of nodes targeting Spot |
| `maintain_standby` / `diversify_pools` | BOOLEAN | False | Warm standby / pool spread |
| `max_family_diversification_cap_pct` | INTEGER | 40 | Max same-family % |
| `instance_type_diversification_pct` | INTEGER | 100 | Uniqueness strictness |
| `failure_cooldown_minutes` | INTEGER | 30 | Post-failure inhibit window |
| `instance_aware_rightsizing` | BOOLEAN | False | Double gate: only resize if better pool exists |
| `min_node_count` | INTEGER | 1 | Scale-down hard floor |
| `scale_down_threshold_pct` | INTEGER | 20 | Idle threshold % |
| `scale_down_stabilization_minutes` | INTEGER | 15 | Anti-thrash stabilization window |
| `enable_ascp_auto_scaler` | BOOLEAN | False | ASCP built-in ASG scaler |
| `check_interval_seconds` | INTEGER | 15 | AR eval frequency (min 15s) |
| `architecture_preference` | VARCHAR(10) | 'both' | both / amd64 / arm64 |
| `drain_timeout_minutes` | INTEGER | 15 | Graceful pod termination wait |
| `max_concurrent_rebalance_actions` | INTEGER | NULL | NULL = 1 (one-at-a-time) |
| `rebalance_batch_percent` | INTEGER | NULL | Max % of nodes per cycle |
| `min_topology_spread` | INTEGER | 1 | Min AZs during consolidation |
| `karpenter_only_mode` | BOOLEAN | False | Skip all ASG code paths |

**Related tables**: `optimization_strategy` (strategy_type, risk_ceiling_percent, volatility_tolerance_percent), `stateless_runtime_rules` (pdb_enabled, substitute_strategy, max_rebalances_per_24h), `stateful_rules` (require_approval, block_spot_for_stateful, max_downscale_percent) — all PK = `cluster_id`.

---

## U3. `agent_actions` (`models/agent_action.py`) — PRIMARY EXECUTION QUEUE

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `id` | VARCHAR(36) PK INDEX | UUID | |
| `cluster_id` | VARCHAR(36) FK→clusters CASCADE INDEX | — | |
| `action_type` | ENUM INDEX | — | See enum below |
| `payload` | JSONB | {} | Action-specific params (pod_name, node_name, etc.) |
| `status` | ENUM INDEX | PENDING | PENDING → PICKED_UP → COMPLETED\|FAILED\|EXPIRED |
| `created_at` | DATETIME INDEX | utcnow | |
| `expires_at` | DATETIME INDEX | utcnow+1h | Cleanup TTL |
| `picked_up_at` / `completed_at` | DATETIME | NULL | Lifecycle timestamps |
| `result` | JSONB | NULL | Success detail (e.g., `placement_check: spot`) |
| `error_message` | VARCHAR(1024) | NULL | |
| `priority` | INTEGER INDEX | 0 | 10 = emergency, 0 = normal. ORDER BY priority DESC, created_at ASC |
| `retry_count` | SMALLINT | 0 | Post-eviction PC retry counter (max = `PC_MAX_RETRY_COUNT=3`) |

**`action_type` values**: `EVICT_POD`, `CORDON_NODE`, `DRAIN_NODE`, `LABEL_NODE`, `UPDATE_DEPLOYMENT`, `INSTALL_KARPENTER`, `UNINSTALL_KARPENTER`, `PATCH_CONTAINER_RESOURCES`, `TERMINATE_NODE`, `UNCORDON_NODE`, `FORCE_DELETE_NODE`, `REMOVE_POD_FINALIZERS`, `INSTALL_KEDA`, `UNINSTALL_KEDA`, `ANNOTATE_WORKLOAD`, `PATCH_AFFINITY`

**Compound indexes**: `(cluster_id, status)` — agent polling; `(expires_at)` — cleanup sweep; `(created_at)` — ordering. **Constraint**: `expires_at > created_at`.

**Payload shape per type**:

| `action_type` | Key `payload` fields |
|---------------|---------------------|
| `EVICT_POD` | `pod_name`, `namespace`, `grace_period`, `workload_id` |
| `CORDON_NODE` / `DRAIN_NODE` | `node_name` (+ `ignore_daemonsets` for drain) |
| `PATCH_CONTAINER_RESOURCES` | `namespace`, `name`, `kind`, `container`, `requests {cpu,memory}`, `limits {cpu,memory}` |
| `TERMINATE_NODE` / `UNCORDON_NODE` / `FORCE_DELETE_NODE` | `node_name`, `instance_id` |
| `UPDATE_DEPLOYMENT` | `namespace`, `name`, `replicas` |
| `PATCH_AFFINITY` | `namespace`, `name`, `kind`, `affinity_patch` |
| `ANNOTATE_WORKLOAD` | `namespace`, `name`, `kind`, `annotations {}` |

---

## U4. `rebalancing_actions` (`models/rebalancing_action.py`) — EXECUTION VISIBILITY MIRROR

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK autoincrement | |
| `cluster_id` | VARCHAR FK→clusters CASCADE INDEX | |
| `trigger` | VARCHAR(20) | `'emergency'` or `'graceful'` |
| `source_pool` / `target_pool` | VARCHAR(100) | `'instance_type:az'` format |
| `status` | VARCHAR(20) INDEX | `in_progress` / `completed` / `failed` |
| `nodes_affected` / `pods_migrated` / `duration_seconds` | INTEGER | Outcome metrics |
| `started_at` INDEX / `completed_at` | DATETIME | |
| `error_message` | TEXT | |
| `metadata` | JSONB | Context (termination notice details) |
| `source_od_price_hr` / `target_spot_price_hr` / `estimated_savings_hr/mo` | FLOAT | Written at creation (decision time) |
| `actual_instance_type` / `actual_az` / `actual_spot_price_hr` | VARCHAR/FLOAT | Written at completion (actual outcome) |
| `realized_savings_hr/mo/pct` / `savings_gap_hr` | FLOAT | Estimated vs actual gap |
| `current_state` | VARCHAR(30) INDEX | State machine: CREATED→POOL_SELECTED→SOURCE_CORDONED→SOURCE_DRAINED→REPLACEMENT_LAUNCHING→REPLACEMENT_READY→SOURCE_TERMINATING→COMPLETED\|FAILED\|DRAIN_TIMEOUT |
| `state_entered_at` / `state_history` JSONB / `lock_version` INTEGER | | State machine tracking |
| `source_instance_id` | VARCHAR(50) INDEX | EC2 instance ID of replaced node |
| `action_step` | VARCHAR(20) INDEX | Karpenter journal: INJECTED / WAITING_SPOT / DRAINING / TERMINATING / CLEANUP / DONE |
| `migration_type` | VARCHAR(20) | `'node_level'` (AR) / `'pod_level'` / `'stateful_pod'` (PC) |
| `source` | VARCHAR(30) | `'auto_rebalancer'` or `'placement_controller'` |
| `agent_action_id` | VARCHAR(36) FK→agent_actions SET NULL INDEX | Links PC's AgentAction to its tracking row |

**Index**: `(cluster_id, status)`. **Note**: `AgentAction` is the authoritative state; `RebalancingAction` is a visibility mirror updated by `_update_rebalancing_action()`.

---

## U5. `workload_classifications` (`models/workload_classification.py`)

WIE output. One record per workload per cluster. Written every scheduler cycle with write-suppression (only updates when score_delta ≥ 1 or tier/confidence/spot_friendly changes).

| Column | Type | Notes |
|--------|------|-------|
| `id` | VARCHAR(36) PK | UUID |
| `cluster_id` | VARCHAR FK→clusters CASCADE INDEX | |
| `workload_id` | VARCHAR(512) | `namespace/name` |
| `namespace` / `name` / `controller_kind` | VARCHAR | |
| `role` | VARCHAR(20) | SYSTEM / CONTROL_PLANE / APPLICATION |
| `criticality_score` | INTEGER | 0–10 |
| `tier` | VARCHAR(20) | Platinum / Gold / Silver / Bronze |
| `spot_score` | INTEGER | 0–10 |
| `spot_friendly` | BOOLEAN | WIE output — API must NOT override |
| `confidence_score` | INTEGER | 0–10 |
| `confidence_state` | VARCHAR(20) | DRAFT(<5) / PROVISIONAL(5-7) / CONFIRMED(≥8) |
| `data_safety` | VARCHAR(20) | STATEFUL / CACHE / EPHEMERAL |
| `signals_fired` | JSONB | List of signal names used in scoring |
| `override_active` / `override_reason` | BOOLEAN / VARCHAR | Manual tier override metadata |
| `input_hash` | VARCHAR(100) | SHA fingerprint for write suppression |
| `az_spread_required` / `disruption_safe` | BOOLEAN | False | v4.4 placement intent signals |
| `schema_version` | VARCHAR(10) | '4.4' |
| `classified_at` / `created_at` / `updated_at` | DATETIME | |

**Unique constraint**: `(cluster_id, workload_id)`. **Indexes**: `(cluster_id, tier)`, `(cluster_id, confidence_state)`, `(cluster_id, spot_friendly, confidence_state)`, `(workload_id)`.

---

## U6. `placement_policies` (`models/placement_policy.py`)

PlacementAdvisor output. Written by `PlacementAdvisorService.run_advisor_cycle()` (Celery task every 10 min).

| Column | Type | Notes |
|--------|------|-------|
| `id` | VARCHAR(36) UUID PK | |
| `cluster_id` | VARCHAR FK→clusters | |
| `workload_id` | VARCHAR(512) | `namespace/name` |
| `criticality_tier` / `confidence_state` | VARCHAR | Platinum/Gold/Silver/Bronze; CONFIRMED/PROVISIONAL |
| `spot_friendly` | BOOLEAN | WIE-owned — must not be API-overridden |
| `observed_replicas` / `ondemand_target` / `spot_target` / `spot_target_raw` | INTEGER | Core placement math output |
| `traffic_skew_detected` | BOOLEAN | CV > 40% threshold |
| `baseline_affinity` / `burst_affinity` / `topology_spread` | JSONB | K8s affinity/spread patches |
| `keda_min_replicas` / `keda_max_replicas` | INTEGER | KEDA ScaledObject bounds |
| `rollout_eligible` / `rollout_blocked_reason` | BOOLEAN / VARCHAR | Safe to start rollout now |
| `estimated_savings_pct` / `estimated_monthly_saving_usd` | FLOAT | Financial output |
| `actionable` / `actionable_blocked_reason` | BOOLEAN / VARCHAR | CONFIRMED + spot_target > 0 |
| `signals_used` | JSONB | WIE signal names used in this decision |
| `schema_version` | VARCHAR(10) | '5.10' |
| `input_hash` | VARCHAR(64) | SHA-256 write suppression |
| `generated_at` / `created_at` / `updated_at` | DATETIME | |

---

## U7. `rightsizing_proposals` (`models/rightsizing_proposal.py`)

Created by rightsizing service; evaluated by optimizer coordinator.

| Column | Type | Notes |
|--------|------|-------|
| `id` | VARCHAR PK | `rsprop_{timestamp}` prefix |
| `cluster_id` | VARCHAR FK→clusters INDEX | |
| `current_instance_type` / `current_vcpu` / `current_memory_gb` / `current_pool` / `current_hourly_cost` | mixed | Current node state |
| `proposed_instance_type` / `proposed_vcpu` / `proposed_memory_gb` / `proposed_hourly_cost` | mixed | Proposed new state |
| `estimated_hourly_savings` / `estimated_monthly_savings` / `savings_percentage` | FLOAT | |
| `avg_cpu_utilization_pct` / `p95_cpu_utilization_pct` / `avg_memory_utilization_pct` / `p95_memory_utilization_pct` | FLOAT | 14-day metric window |
| `metric_sample_count` / `metric_window_hours` | INTEGER / FLOAT | |
| `status` | ENUM(PENDING,APPROVED,REJECTED,EXECUTED,FAILED,ROLLED_BACK) | |
| `created_at` / `evaluated_at` / `executed_at` | DATETIME | |
| `combined_ev_option_a/b/c` | FLOAT | EV: current+new_pool / new_size+best_pool / do_nothing |
| `selected_option` | VARCHAR | 'A' / 'B' / 'C' / NULL |
| `best_pool_for_new_size` / `best_pool_hourly_cost` / `best_pool_risk_score` | VARCHAR / FLOAT | Post-reoptimization best pool |
| `rejection_reason` | TEXT | |
| `ev_breakdown` | JSON | Full economic EV computation |
| `net_ev` | FLOAT | |

**Index**: `(cluster_id, status)`.

---

## U8. `pod_metrics` (`models/pod_metric.py`) — TIME-SERIES DATA

Collection frequency: every 5 minutes. Retention: 7 days.

| Column | Type | Notes |
|--------|------|-------|
| `id` | VARCHAR(36) PK | UUID |
| `cluster_id` | VARCHAR FK→clusters CASCADE INDEX | |
| `namespace` / `pod_name` / `node_name` | VARCHAR(253) INDEX | K8s identity |
| `controller_kind` / `controller_name` | VARCHAR INDEX | Deployment / StatefulSet / DaemonSet / Job |
| `cpu_usage_millicores` | INTEGER | Current CPU (millicores) |
| `cpu_request_millicores` / `cpu_limit_millicores` | INTEGER | May be NULL if unset |
| `memory_usage_bytes` | BIGINT | |
| `memory_request_bytes` / `memory_limit_bytes` | BIGINT | May be NULL |
| `cpu_utilization_pct` / `memory_utilization_pct` | FLOAT | usage/request × 100 |
| `container_count` | INTEGER | Default 1 |
| `timestamp` | DATETIME INDEX | |
| `pod_metadata` | JSONB | Labels, annotations |

**Indexes**: `(cluster_id, timestamp)`, `(cluster_id, namespace, controller_kind, controller_name, timestamp)`, `(cluster_id, node_name, timestamp)`, `(cluster_id, namespace, pod_name, timestamp)`.

---

## U9. Governance, Auth & RBAC Tables (Summary)

| Table | Key Columns | Purpose |
|-------|------------|---------|
| `users` | `id`, `email` UNIQUE, `hashed_password`, `role` ENUM, `organization_id` FK, `is_active`, `is_verified` | User accounts |
| `organizations` | `id`, `name`, `slug` UNIQUE, `plan` ENUM, `max_clusters` | Multi-tenant root |
| `accounts` | `id`, `org_id` FK, `aws_account_id`, `aws_role_arn`, `status` | AWS account link |
| `api_keys` | `id`, `cluster_id` FK, `key_hash`, `is_active`, `expires_at` | Agent auth keys |
| `approvals` | `id`, `user_id` FK, `organization_id` FK, `approver_id` FK, `type` ENUM, `feature_id`, `jit_scope` ENUM, `status` ENUM, `expires_at` | JIT access + approval workflow |
| `audit_logs` | `id`, `org_id` FK, `user_id`, `action`, `resource_type`, `resource_id`, `payload` JSONB, `created_at` | Immutable action log |
| `teams` / `roles` / `permissions` | standard RBAC structure | Org-level RBAC |

## U10. Infrastructure, Cost & Tag Tables (Summary)

| Table | Key Columns | Purpose |
|-------|------------|---------|
| `instances` | `cluster_id` FK, `instance_id` (EC2), `instance_type`, `az`, `capacity_type` (SPOT/ON_DEMAND), `status`, `node_name`, `price_hr` | Live node inventory |
| `hibernation_schedules` | `id`, `org_id` FK, `cron_wake`, `cron_sleep`, `timezone`, `enabled` | Schedule-based hibernation (many-to-many with clusters) |
| `karpenter_events` | `cluster_id` FK, `event_type`, `node_name`, `instance_type`, `az`, `timestamp` | Karpenter provisioning events |
| `node_alternative_cache` | `cluster_id` FK, `node_name`, `alternative_pools` JSONB, `coverage_status` (COVERED/AT_RISK/STRANDED/IMMOVABLE) | Per-node Spot alternative pool cache |
| `cluster_baselines` | `cluster_id` PK FK, `primary_node_type`, `baseline_monthly_cost` | Cost delta baseline |
| `cluster_cooldown_states` | `cluster_id` PK FK, `stabilization_until`, `last_action_at` | DB-backed Redis re-hydration on crash |
| `daily_cluster_stats` | `cluster_id` FK, `date`, `total_savings_usd`, `spot_pct`, `node_count` | Daily billing rollup |
| `ri_utilization` | `account_id` FK, `ri_id`, `instance_type`, `utilization_pct`, `savings` | Reserved Instance tracking |
| `s3_analysis` / `rds_analysis` / `transfer_analysis` | `account_id` FK, resource attrs, `cost_usd` | AWS cost analysis |
| `tag_policies` / `tag_templates` / `tag_compliance_scores` / `tag_automation_rules` / `tag_automation_logs` / `tag_scoring_config` | org/resource FKs, JSONB tag definitions | Full tag governance suite |
| `instance_catalog` | `instance_type` PK, `vcpu`, `memory_gb`, `arch`, `od_price_hr`, `spot_price_hr` | EC2 instance type catalog |
| `pricing` | `instance_type`, `region`, `az`, `capacity_type`, `price_hr` | Live pricing from AWS |

---

# §V. MASTER REDIS KEY CATALOG

> **Sources**: `backend/redis_keys.py`, §21, §L, §T-1. All keys verified from live code.
> TTL = time-to-live; NONE = key persists indefinitely (no expiry set).

## V1. Concurrency & Locking

| Key Pattern | TTL | Owner | Purpose |
|-------------|-----|-------|---------|
| `spot:cluster_mutex:{cluster_id}` | 60s + heartbeat | PlacementController | Cross-engine mutex. PC writes with SET NX EX. AR reads-only via GET — never acquires. |
| `spot:placement_controller:cycle_lock:{cluster_id}` | 300s | placement_controller_task | Prevents concurrent PC Celery tasks per cluster |
| `spot:rebalance_lock:{cluster_id}` | 600s | auto_rebalancer | Prevents concurrent AR cycles per cluster |
| `lock:workload:{cluster_id}:{workload_id}` | 30s | PlacementController | Per-workload lock — prevents dual-eviction in overlapping cycles (`WORKLOAD_LOCK_KEY` in `redis_locks.py`) |
| `spot:stabilization_lock:{cluster_id}` | 60s | auto_rebalancer | Post-action stabilization window; re-hydrated from `cluster_cooldown_states` DB after Redis restart |
| `spot:node_active_action:{instance_id}` | 1800s (30 min) | auto_rebalancer | Per-node migration lock. Uses EC2 `instance_id` (e.g. `i-0abc`), NOT K8s node name. BUG-9 fix: PC now maps node_name→instance_id before checking. |
| `hibernation:lock:{schedule_id}:{cluster_id}` | 180s | HibernationWorker | Per-schedule hibernation execution lock |
| `spot:autoscaler_freeze:{ns}/{ctrl}` | 180s | eviction_safety | HPA/KEDA freeze during AR drain. Risk: 5-min window if AR crashes. |

## V2. Cooldowns

| Key Pattern | TTL | Owner |
|-------------|-----|-------|
| `spot:cooldown:cluster:{cluster_id}` | 60 min | CooldownController |
| `spot:cooldown:pool:{pool_id}` | 120 min | CooldownController |
| `spot:cooldown:resize:{instance_id}` | 360 min | CooldownController |
| `spot:cooldown:pool_switch:{instance_id}` | 30 min | CooldownController |
| `spot:cooldown:substitute:{instance_id}` | 120 min | CooldownController |
| `spot:placement_controller:cooldown:{cluster_id}:{workload_id}` | 10 min (success) / 30 min (failure) | PlacementController | Per-workload eviction cooldown |

## V3. Workload & Placement State

| Key Pattern | TTL | Writer | Readers | Notes |
|-------------|-----|--------|---------|-------|
| `spot:workload:state:{cluster_id}:{workload_id}` | 300s | `agent_routes.py` heartbeat (P0-A) | PC `_would_violate_pdb()`, P0-B guard, PlacementRolloutService, PlacementAdvisorService | HASH: `ready_replicas`, `spot_pods`, `od_pods`, `pdb_min_available`, `hpa_min_replicas` |
| `spot:workload_tier:{cluster_id}:{ns}/{ctrl}` | 540s | WorkloadInspector | DecisionEngine, SubstituteManager, auto_rebalancer | Node-level classification cache |
| `spot:workload_profile:{cluster_id}:{ns}/{ctrl}` | 540s | WorkloadInspector | Multiple callers | Extended workload profile with tier fields |
| `spot:placement:stability:{cluster_id}:{workload_id}` | variable | PlacementAdvisorService | PlacementAdvisorService | Per-workload stability signal |
| `spot:placement:rollout_blocked:{cluster_id}:{workload_id}` | 14400s (4h) | PlacementRolloutService | PlacementAdvisorTask | Rollout block flag |
| `spot:placement:policy:{cluster_id}:{workload_id}` | POLICY_CACHE_TTL (unconfirmed) | PlacementAdvisorService `_write_policy()` | PlacementController `_get_actionable_workloads()` | Serialized PlacementPolicyRecord; PC reads this to find workloads to act on |

## V4. Shared Semaphore (Cross-Engine)

| Key | TTL | Type | Owners |
|-----|-----|------|--------|
| `rebalance:active_count:{cluster_id}` | 300s | STRING (integer counter) | PC increments on eviction dispatch, decrements on completion/failure. AR increments before RebalancingAction, decrements in cleanup. AR reconciles vs DB count every 15s. Enforces `max_concurrent_rebalance_actions`. |

## V5. KEDA & Pending Pod Guards

| Key Pattern | TTL | Writer | Reader | Status |
|-------------|-----|--------|--------|--------|
| `spot:keda:last_scale_event:{cluster_id}` | 300s | `placement_webhook_routes.py` when KEDA-managed pod admitted (P1-A) | `placement_controller_service.py:519` KEDA scaling guard | **ACTIVE** post-hardening |
| `spot:cluster:pending_pods:{cluster_id}` | 120s | `agent_routes.py` heartbeat from `cluster_spot_summary.unhealthy_pending_pods` (P1-B) | PC scaling guard + `execution_controller._verify_workload_health()` | **ACTIVE** post-hardening |
| `spot:keda_detection:{cluster_id}` | 300s | keda_service | keda_routes | KEDA installation detection result |
| `spot:keda_paused_state:{ns}/{name}` | 600s | keda_service | keda_service restore | Paused ScaledObject state snapshot |
| `spot:keda_installing:{cluster_id}` | 300s | keda_service | keda_routes | Install in-progress gate |

## V6. Metrics Hashes

| Key Pattern | TTL | Type | Counter Fields |
|-------------|-----|------|----------------|
| `spot:placement_controller:metrics:{cluster_id}` | 3600s | HASH | `evictions_attempted`, `evictions_skipped_cooldown`, `evictions_skipped_scaling_guard`, `evictions_skipped_capacity`, `evictions_skipped_lock_contention`, `evictions_skipped_batch_limit`, `evictions_skipped_last_pod`, `evictions_skipped_pdb`, `evictions_skipped_active_action`, `evictions_skipped_node_locked`, `stateful_rollout_started/completed/failed/timeout`, `retry_incremented`, `permanent_failures` |
| `spot:placement:metrics:{cluster_id}` | 86400s | HASH | `placement_policy_changed`, `write_suppressed`, `placement_cycle_timeout_count` |
| `spot:cluster:{cluster_id}:metrics` | variable | HASH | AR cycle metrics per cluster |
| `spot:skip_reasons:{cluster_id}` | variable | HASH | AR skip reasons (mutex_contention, batch_limit, etc.) |
| `drift_alerts:latest` | 1800s | STRING/LIST | Latest drift detection alerts from health_monitor |

## V7. Cache & Rate-Control

| Key Pattern | TTL | Owner |
|-------------|-----|-------|
| `spot:last_check:{cluster_id}` | check_interval−14s | auto_rebalancer — per-cluster interval gate (SET NX) |
| `spot:last_run_ts:{cluster_id}` | check_interval×3 | auto_rebalancer — last run timestamp (frontend countdown) |
| `spot:global_rankings:{region}` | 65 min | GlobalPoolCacheService — ranked Spot pool list |
| `spot:volatility_regime:{region}` | 2h | EventMonitor — market volatility regime |
| `spot:node_classification:{cluster_id}` | 10 min | WorkloadInspector — node status cache |
| `spot:ondemand_fallback:{cluster_id}` | 12h | karpenter_service — OD fallback active |
| `spot:karpenter:installed:{cluster_id}` | 3600s | Karpenter detection — installed flag |
| `spot:cluster_state:{cluster_id}` | **NONE** | risk_engine — **persistent, no cluster-deletion cleanup** |
| `spot:rankings_version:{region}` | **NONE** | multiple — version counter, safe but never cleaned |
| `spot:config:org_velocity_threshold` | **NONE** | config (manual) — org velocity threshold |
| `spot:rejection_counter:{id}:{reason}` | 24h | decision_engine — pool rejection reason counter |
| `ascpai:ml_fail_count` / `ascpai:ml_degraded` | 10 min | PoolRankingService — ML degraded mode |

## V8. Agent Push Data (Cluster-Level)

| Key Pattern | TTL | Written By | Used By |
|-------------|-----|-----------|---------|
| `spot:placement:agent_data:{cluster_id}:pod_metrics` | 120s | agent heartbeat | PlacementAdvisorService |
| `spot:placement:agent_data:{cluster_id}:cluster_spot_summary` | 120s | agent heartbeat | PlacementAdvisorService |
| `spot:placement:agent_data:{cluster_id}:hpa_pdb` | 300s | agent heartbeat | PlacementAdvisorService |

## V9. Karpenter NodePool Type Keys

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `karpenter:nodepool_baseline:{cluster_id}:{nodepool}` | 86400s | Baseline allowed instance types for NodePool |
| `spot:injected_type:{cluster_id}:{nodepool}:{type}` | 7200s | Temporarily injected instance type for diversification |

## V10. Dead Keys Confirmed (Historic — Now Fixed)

| Key | Was Dead? | Fixed By |
|-----|-----------|---------|
| `spot:keda:last_scale_event:{cluster_id}` | YES (pre-hardening) | P1-A: now written by placement_webhook_routes.py |
| `spot:cluster:pending_pods:{cluster_id}` | YES (pre-hardening) | P1-B: now written by agent_routes.py heartbeat |
| `spot:workload:state:{cluster_id}:{workload_id}` | YES (pre-hardening) | P0-A: now written by agent_routes.py heartbeat |
| `spot:workload:pods:{cluster_id}:{workload_id}` | YES — still dead | P0-B guard migrated to use `spot:workload:state.ready_replicas` instead |

---

# §W. COMPLETE API ENDPOINT REFERENCE

> **Base prefix**: All routes under `/api/v1/` (registered in `backend/core/api_gateway.py`).
> **Auth default**: JWT Bearer (`Authorization: Bearer <token>`) unless stated otherwise.
> Agent-facing routes use cluster `X-Api-Key` header.

## W1. Auth & User (`/auth`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/signup` | None | Register new user + org. Returns JWT pair. |
| POST | `/auth/login` | None | Login. Returns `{access_token, refresh_token, user}`. |
| POST | `/auth/refresh` | Refresh JWT | Rotate access token. |
| GET | `/auth/me` | JWT | Current user profile + role + org. |
| POST | `/auth/change-password` | JWT | Body: `{current_password, new_password}`. |
| PUT | `/auth/profile` | JWT | Update display name, avatar. |
| POST | `/auth/logout` | JWT | Invalidate session. |
| POST | `/auth/invitation-response` | None | Accept/decline org invite. Body: `{token, action}`. |

## W2. Cluster CRUD & Settings (`/clusters`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/clusters` | List clusters for org. Includes status, cost, savings summary. |
| POST | `/clusters` | Register cluster. Body: `{name, region, arn, account_id}`. |
| GET | `/clusters/{id}` | Full cluster detail (nodes, settings, health). |
| PUT | `/clusters/{id}` | Update cluster metadata. |
| DELETE | `/clusters/{id}` | Delete + cascade all records. Admin only. |
| GET | `/clusters/{id}/nodes` | Node list with capacity type + utilization. |
| GET | `/clusters/{id}/nodes/detailed` | Nodes with running pod details. |
| GET | `/clusters/{id}/optimization-settings` | Read `ClusterOptimizationSettings` + `OptimizationStrategy` + `StatelessRuntimeRules` + `StatefulRules`. |
| PUT | `/clusters/{id}/optimization-settings` | Update all four settings tables in one request. |
| PATCH | `/clusters/{id}/auto-rebalance` | Toggle `auto_rebalance_enabled`. Query: `?enabled=true\|false`. |
| GET | `/clusters/{id}/coverage` | Node alternative pool coverage (COVERED / AT_RISK / STRANDED). |
| POST | `/clusters/{id}/refresh` | Trigger immediate cluster state refresh. |
| POST | `/clusters/{id}/dismiss` | Mark as dismissed — prevents re-discovery. |

## W3. Agent Endpoints (`/agents`) — API Key Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/agents/register` | Agent registers. Returns `cluster_id`, config, poll interval. |
| POST | `/agents/deregister` | Agent graceful shutdown. Marks cluster DISCONNECTED. |
| POST | `/agents/heartbeat` | Primary agent→backend data push. Writes: `pod_metrics` rows, `spot:workload:state` per workload, `spot:cluster:pending_pods`, `spot:placement:agent_data:*`. Updates `cluster.last_heartbeat`. |
| GET | `/agents/actions/pending` | Poll queue. Returns PENDING `AgentAction` rows ordered by `priority DESC, created_at ASC`. Sets status = PICKED_UP. |
| POST | `/agents/actions/{id}/result` | Report result. Body: `{success, result, error_message}`. On EVICT_POD + success: calls `handle_eviction_result()`. |
| POST | `/agents/spot-interruption` | Forward IMDS interruption notice → emergency rebalancing. |
| POST | `/agents/rebalance-recommendation` | Forward EC2 rebalance recommendation event. |

## W4. Execution Data (registered directly in `api_gateway.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/pods` | Latest `PodMetric` per pod. Query: `cluster_id`, `limit` (default 100). Subquery: max timestamp per `(cluster_id, namespace, pod_name)`. |
| GET | `/agent-actions` | Recent `AgentAction` rows. Query: `cluster_id`, `limit` (default 20). Ordered newest-first. |
| GET | `/nodeclaims` | Karpenter NodeClaims. Returns `[]` until agent syncs K8s CRDs. Query: `cluster_id`. |
| GET | `/placement-metrics` | `HGETALL spot:placement_controller:metrics:{cluster_id}` from Redis. All PC cycle counters. |
| GET | `/rollout-status` | From `AgentAction` table: `success_rate` (COMPLETED/FAILED last 24h), `active_timeouts` (PENDING rows older than 10 min). |

## W5. Placement Intelligence (`/placement-policy`, `/placement`) — Feature-gated

Requires `FEATURE_PLACEMENT_ADVISOR_ENABLED=true`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/placement-policy/{cluster_id}/placement-policies` | Paginated `PlacementPolicyRecord` list. Filters: `tier`, `confidence_state`, `actionable`. |
| GET | `/placement-policy/{cluster_id}/placement-policies/summary` | Aggregated counts + savings totals. |
| GET | `/placement-policy/{cluster_id}/placement-policies/{workload_id}` | Single policy with affinity patches, signals, EV. |
| POST | `/placement-policy/{cluster_id}/placement-policies/generate` | Trigger `run_placement_cycle_task.delay(cluster_id)`. Returns 202 Accepted. UI polls every 3s for 15s after. |
| POST | `/placement/mutate` | Webhook (no JWT). K8s Mutating Admission Webhook — injects Spot affinity into pod spec. Writes `spot:keda:last_scale_event` if KEDA-managed pod. |

## W6. Workload Classification (`/workload-classification`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/workload-classification/{cluster_id}/workloads` | Paginated `WorkloadClassificationRecord`. Filters: `namespace`, `tier`, `confidence_state`, `spot_friendly`, `search`, `page`, `page_size`. |
| GET | `/workload-classification/{cluster_id}/summary` | Aggregated tier counts, confidence breakdown, spot-eligible total. |
| GET | `/workload-classification/{cluster_id}/spot-candidates` | `CONFIRMED + spot_friendly=True` records only. |
| GET | `/workload-classification/{cluster_id}/metrics` | WIE cycle metrics from Redis. |

## W7. Optimization & Rightsizing (`/optimization`, `/optimizer-coordinator`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/optimization/recommendations` | `RightsizingProposal` list for cluster. Query: `cluster_id`. |
| POST | `/optimization/apply/{proposal_id}` | Approve proposal → creates `PATCH_CONTAINER_RESOURCES` AgentAction. |
| POST | `/optimization/reject/{proposal_id}` | Sets `status=REJECTED`. |
| GET | `/optimization/history` | Historical proposals with outcomes. |
| GET | `/optimizer-coordinator/proposals` | All proposals with EV breakdown. |
| POST | `/optimizer-coordinator/evaluate` | Trigger coordinator evaluation cycle. Query: `cluster_id`. |
| GET | `/optimizer-coordinator/status` | Last run, pending proposals, approved this cycle. |

## W8. Karpenter & KEDA (`/karpenter`, `/keda`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/karpenter/{cluster_id}/config` | Read Karpenter config (mode, families, consolidation). |
| PUT | `/karpenter/{cluster_id}/config` | Update Karpenter config. Syncs `ClusterOptimizationSettings`. |
| GET | `/karpenter/{cluster_id}/status` | Installation status, mode, NodePool count, active NodeClaims. |
| POST | `/karpenter/{cluster_id}/dry-run` | Simulate consolidation without executing. |
| GET | `/karpenter/{cluster_id}/node-pools` | List NodePool objects pushed by agent. |
| PUT | `/karpenter/{cluster_id}/node-pools/{name}` | Patch NodePool spec. Creates `PATCH_AFFINITY` AgentAction. |
| GET | `/keda/{cluster_id}/status` | KEDA installation status. Reads `spot:keda_detection:{cluster_id}` (TTL 300s). |
| POST | `/keda/{cluster_id}/install` | Install KEDA via Helm. Creates `INSTALL_KEDA` AgentAction. |
| POST | `/keda/{cluster_id}/uninstall` | Creates `UNINSTALL_KEDA` AgentAction. |
| GET | `/keda/{cluster_id}/scaled-objects` | List KEDA ScaledObjects pushed by agent. |
| POST | `/keda/{cluster_id}/pause/{ns}/{name}` | Pause ScaledObject. Writes `spot:keda_paused_state:{ns}/{name}` (TTL 600s). |
| POST | `/keda/{cluster_id}/restore/{ns}/{name}` | Restore paused ScaledObject from Redis snapshot. |

## W9. Hibernation (`/hibernation`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/hibernation/schedules` | List org hibernation schedules. |
| POST | `/hibernation/schedules` | Create schedule. Body: `{name, cron_wake, cron_sleep, timezone, cluster_ids}`. |
| PUT/DELETE | `/hibernation/schedules/{id}` | Update / delete schedule. |
| POST | `/hibernation/{cluster_id}/sleep` | Immediate hibernate: scale all Deployments to 0, save `hibernation_state` JSONB to `clusters` table. |
| POST | `/hibernation/{cluster_id}/wake` | Restore from `hibernation_state`: re-scale to saved replica counts. |
| GET | `/hibernation/{cluster_id}/state` | Current state (`is_hibernating`, saved replicas, lock holder). |

## W10. Governance & Approvals (`/approvals`, `/policies`, `/governance`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/approvals` | Create approval request. Body: `{type, feature_id, reason_category, reason_text, duration_hours}`. |
| GET | `/approvals` | List approvals filtered by `status`. Admin sees all; user sees own. |
| POST | `/approvals/delegate` | Admin: create delegated approval grants. |
| GET | `/approvals/active-window` | Check if current user has active approval window. Returns `{has_active_window, approval_id, expires_at}`. |
| POST | `/approvals/jit-request` | JIT feature access request. Body: `{feature_id, jit_scope, reason_text, duration_hours}`. |
| GET | `/approvals/my-jit-approvals` | Current user's JIT approvals list. |
| POST | `/approvals/{id}/approve` | Approve pending request (Admin). |
| POST | `/approvals/{id}/reject` | Reject request with reason (Admin). |
| POST | `/approvals/{id}/revoke` | Revoke active approval (Admin). |
| GET/POST/PUT/DELETE | `/policies` + `/policies/{id}` | Governance policy CRUD. |

## W11. Hygiene (`/hygiene`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/hygiene/scan/{account_id}` | Scan for orphaned/idle resources. Query: `regions[]`. Returns `HygieneSummary` with categorized waste. |
| GET | `/hygiene/check-dependencies` | Pre-flight check before cleanup. Query: `account_id`, `resource_type`. |
| POST | `/hygiene/action` | Execute cleanup (delete/stop/resize). Requires `hygiene:execute` JIT approval if governance enforced. |
| GET | `/hygiene/discover` | Discover resources by type. Query: `account_id`, `resource_type`. |
| GET | `/hygiene/total-cost` | Total wasted USD across all idle resources. |
| GET | `/hygiene/scan-history` | Historical scans. Query: `account_id`, `days` (1–30). |

## W12. Metrics & Billing (`/metrics`, `/billing`, `/ri`, `/s3`, `/rds`, `/transfer`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/metrics/cluster/{cluster_id}` | Cluster timeseries (CPU, memory, spot%, savings). Params: `period`, `resolution`. |
| GET | `/metrics/savings` | Aggregated savings across all clusters. |
| GET | `/metrics/fleet` | Fleet-wide dashboard summary. |
| POST | `/metrics/batch` | Agent batch push of cluster metrics. Writes to `cluster_metrics` table. |
| GET | `/billing/summary` | Monthly cost: spot%, OD%, savings, forecast. Source: `billing` table + AWS Cost Explorer. |
| GET | `/billing/history` | 12-month billing history. |
| POST | `/billing/sync` | Trigger AWS Cost Explorer sync (Celery task). |
| GET | `/ri/analysis` | RI utilization by instance type/region. Source: `ri_utilization`. |
| GET | `/ri/recommendations` | RI purchase recommendations. |
| GET | `/s3/analysis` / `/rds/analysis` / `/transfer/analysis` | AWS cost analysis per service. |

## W13. RBAC (`/teams`, `/roles`, `/permissions`)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/teams` | List / create teams. |
| GET/PUT/DELETE | `/teams/{id}` | Team detail / update / delete. |
| POST/DELETE | `/teams/{id}/members` + `/teams/{id}/members/{user_id}` | Add / remove team members. |
| GET/POST/PUT/DELETE | `/roles` + `/roles/{id}` | Custom role CRUD. |
| GET | `/permissions` | Effective permissions for current user. |
| POST | `/permissions/check` | Body: `{resource_type, action, scope}`. Returns `{allowed: bool}`. |

## W14. Tag Management (`/tag-policies`, `/tag-management`, `/tag-compliance`, `/tag-automation`, `/tag-scoring`)

| Domain | Endpoints | Summary |
|--------|-----------|---------|
| `/tag-policies` | CRUD + `/rules` sub-resource | Tag governance policy definitions |
| `/tag-management/resources` | GET (browse), POST `/apply` | Browse AWS resources with tag state; apply tags |
| `/tag-compliance/scores` + `/summary` | GET | Per-resource compliance scores + org-wide % |
| `/tag-automation` | GET/POST + `/logs` | Auto-tagging rules + execution history |
| `/tag-scoring/config` | GET/PUT | Tag score weight configuration |

## W15. Admin & Health (`/admin`, `/health`, `/onboarding`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Readiness probe. Returns `{status, version, db, redis}`. |
| GET | `/health/detailed` | JWT | DB pool, Redis latency, Celery queue depths. |
| POST | `/onboarding/aws-connect` | JWT | Connect AWS account. Body: `{role_arn, external_id, account_id}`. Validates STS assume-role. |
| GET | `/onboarding/status` | JWT | Onboarding checklist (account connected, agent installed, first metric). |
| POST | `/onboarding/discover-clusters` | JWT | Trigger EKS cluster discovery. |
| GET | `/onboarding/agent-install-command` | JWT | Returns pre-filled Helm install command with cluster ID + API key. |
| GET | `/admin/clusters` | SuperAdmin | All clusters across all orgs. |
| GET | `/admin/organizations` | SuperAdmin | All organizations. |
| POST | `/admin/workers/trigger/{task}` | SuperAdmin | Manually trigger Celery task by name. |
| GET/DELETE | `/admin/redis/keys` + `/admin/redis/key` | SuperAdmin | Browse / delete Redis keys. |
| GET/PUT | `/admin/system/config` | SuperAdmin | Read / update platform-wide feature flags and config. |

## W16. Cross-Engine Data Flow Summary

```
Agent Heartbeat (POST /agents/heartbeat)
  │
  ├─► pod_metrics table (time-series, 7-day retention)
  ├─► spot:workload:state:{cluster_id}:{workload_id}  TTL=300s  (P0-A)
  ├─► spot:cluster:pending_pods:{cluster_id}           TTL=120s  (P1-B)
  ├─► spot:placement:agent_data:{cluster_id}:*         TTL=120-300s
  └─► cluster.last_heartbeat (UPDATE)

Placement Advisor Cycle (POST /placement-policy/{id}/generate → Celery)
  │
  ├─► placement_policies table (UPSERT with write-suppression)
  └─► spot:placement:policy:{cluster_id}:{workload_id} (cache)

PlacementController Cycle (Celery beat, every 5 min, feature-gated)
  │
  ├─► Reads spot:placement:policy:* (actionable workloads)
  ├─► Reads spot:workload:state:* (PDB/replica guard)
  ├─► Reads spot:keda:last_scale_event:* (KEDA guard)
  ├─► Reads spot:cluster:pending_pods:* (pending pod guard)
  ├─► Writes agent_actions (EVICT_POD, status=PENDING)
  ├─► Writes rebalancing_actions (visibility mirror)
  └─► INCR rebalance:active_count:{cluster_id}

Agent Action Execution (GET /agents/actions/pending → POST /agents/actions/{id}/result)
  │
  ├─► agent_actions.status PENDING → PICKED_UP → COMPLETED|FAILED
  ├─► handle_eviction_result() → verifies pod landed on Spot
  ├─► _update_rebalancing_action() → syncs rebalancing_actions (best-effort)
  └─► DECR rebalance:active_count:{cluster_id}
```

---

# DELTA AUDIT — v11.0 (Spot Optimizer Real Data Integration: T-09 → T-24)

> **Mode**: DELTA — Covers only T-09 through T-24 (new tables, new Celery tasks, new API endpoints, agent changes, UI changes, and all inline fixes from the 2026-04-27 validation pass).
> All prior sections (§A–§W) remain authoritative for pre-existing code.
> Every claim includes file reference.

---

## §X. NEW AGENT DATA COLLECTION CAPABILITIES

### X1. Node Metadata Batch Push (T-09)

**Files changed**: `agent/heartbeat.py` (lines 180–192, 490–564), `agent/main.py` (lines 370–393)

Added `set_metrics_collector()` and `send_node_metadata_batch()` to `HeartbeatSender`. The `run()` loop now calls `send_node_metadata_batch()` on each heartbeat tick when a `metrics_collector` is linked. In `main.py`, `set_metrics_collector()` is wired after both the `pod_metrics_collector` and `HeartbeatSender` are initialised.

**Data pushed**: per-node metadata (instance type, AZ, allocatable CPU/mem, nodepool name, is_ready) to `POST /agents/heartbeat` payload.

---

### X2. KarpenterNodeClaim Polling (T-11)

**Files changed**: `agent/karpenter_watcher.py` (lines 76–213), `backend/models/karpenter_node_claims.py` (new), `backend/api/agent_routes.py` (lines 628–740), `migrations/versions/20260427_karpenter_node_claims.py` (new)

| Component | Detail |
|-----------|--------|
| Agent: `KarpenterWatcher.run()` | Spawns a NodeClaims polling thread (`_poll_nodeclaims()`) alongside the existing event-watch loop |
| `_detect_crd_version()` | Probes K8s API for `karpenter.sh/v1` then falls back to `karpenter.sh/v1beta1` |
| `_poll_nodeclaims()` | Fetches all `NodeClaim` CRD objects every 60s, batches them, calls `POST /agents/nodeclaims/batch` |
| Backend: `POST /agents/nodeclaims/batch` | Upserts into `karpenter_node_claims` table using PostgreSQL `ON CONFLICT (cluster_id, node_name) DO UPDATE` |
| Model: `KarpenterNodeClaim` | New table — see §Z1 |
| Migration: `20260427_karpenter_node_claims` | Alembic migration creates `karpenter_node_claims` table |

**Why /nodeclaims endpoint returns `[]` before this**: `execution_data_routes.py` `GET /nodeclaims` was a stub. Now populated once the `KarpenterWatcher` agent thread runs.

---

### X3. Pod Phase + Start Time (T-12)

**Files changed**: `backend/models/pod_metric.py` (lines 47–98), `backend/schemas/pod_metric_schemas.py` (lines 26–105), `backend/api/pod_metrics_routes.py` (line 117–121), `agent/pod_metrics_collector.py` (lines 566–588), `migrations/versions/20260427_pod_metrics_phase_starttime.py` (new)

| Addition | Detail |
|----------|--------|
| `PodMetric.phase` | `VARCHAR(20)` nullable, indexed (`idx_pod_metric_phase`). Values: Running / Pending / Succeeded / Failed / Unknown |
| `PodMetric.start_time` | `DATETIME` nullable. K8s pod `status.startTime`. |
| Schema: `PodMetricCreate` + `PodMetricResponse` | Both extended with `phase: Optional[str]` and `start_time: Optional[datetime]` |
| Agent: `pod_metrics_collector.py` | Extracts `pod.status.phase` and `pod.status.start_time` and includes them in the metric dict |
| Use: `consolidation_analysis_task.py` | Queries `PodMetric.phase` to detect unschedulable Pending pods when evaluating drain-ability of candidate nodes (T-18) |

---

### X4. HPA Config + Status Snapshot Collection (T-13)

**Files changed**: `agent/pod_metrics_collector.py` (lines 690–800), `backend/models/hpa_configs.py` (new), `backend/models/hpa_status_snapshots.py` (new), `backend/api/agent_routes.py` (lines 638–740), `backend/workers/tasks/pod_metrics_cleanup.py` (lines 14–65), `migrations/versions/20260427_hpa_tables.py` (new)

| Component | Detail |
|-----------|--------|
| Agent: `collect_hpa_configs()` | Lists all `HorizontalPodAutoscaler` objects via K8s `autoscaling/v2` API. Extracts `min_replicas`, `max_replicas`, target CPU/memory thresholds. |
| Agent: `send_hpa_configs_batch()` | POSTs batch to `POST /agents/hpa-configs/batch` |
| Agent: collect loop | `collect_and_send()` calls `collect_hpa_configs()` + `send_hpa_configs_batch()` on each scrape cycle |
| Backend: `POST /agents/hpa-configs/batch` | Upserts into `hpa_configs` AND inserts snapshot row into `hpa_status_snapshots` per record |
| Cleanup: `pod_metrics_cleanup.py` | Extended to delete `hpa_status_snapshots` rows older than retention window |
| Models: `HpaConfig`, `HpaStatusSnapshot` | See §Z2 and §Z3 |

---

## §Y. NEW CELERY WORKERS

### Y1. HPA Recommendation Task (T-16)

**File**: `backend/workers/tasks/hpa_recommendation_task.py` (new, 159 lines)
**Beat schedule**: every 30 minutes (`app.py`)
**Soft time limit**: 300s (5 min)

**Algorithm**:
1. Query all clusters with `agent_installed='Y'`.
2. For each cluster → query all `HpaConfig` records.
3. For each HPA → fetch last 14 days of `HpaStatusSnapshot` records.
4. **Data guard**: if snapshot window < 7 days → skip (insufficient data).
5. Compute **P95** of `current_replicas` using index `floor(ceil(0.95 × N) - 1)`.
6. `recommended_max = ceil(p95 × 1.2)` (20% safety margin).
7. `recommended_min = min(current_min_replicas, recommended_max)`.
8. Upsert `HpaConfig.recommended_max_replicas` and `HpaConfig.recommended_min_replicas`.

**Import fix applied**: `from backend.models.base import SessionLocal` (not `backend.core.database` which does not exist).

---

### Y2. Consolidation Analysis Task (T-18)

**File**: `backend/workers/tasks/consolidation_analysis_task.py` (new, 209 lines)
**Beat schedule**: every 10 minutes (`app.py`)
**Soft time limit**: 240s

**Two-branch algorithm**:

| Branch | Trigger | Logic |
|--------|---------|-------|
| **Karpenter branch** | Cluster has rows in `karpenter_node_claims` | Query `NodeMetadata` for nodes with `do_not_disrupt=False`. For each: compute pod-level CPU/mem occupancy from `PodMetric`. Node is "candidate" if occupancy < 20% of allocatable. Call `_can_drain()` to check for affinity/taint blockers. |
| **Non-Karpenter branch** | No `karpenter_node_claims` rows | Query `NodeMetadata` for non-Karpenter nodes. Same utilisation threshold. |

**`_can_drain(node_name, db)` logic**:
- Fetches `pod_metadata` JSONB from `PodMetric` for all pods on the node.
- Returns `False` if any pod has `node_affinity_required`, `has_host_port`, or `toleration_not_schedulable_elsewhere`.

**GAP-9 pricing fallback**: if `NodeMetadata.instance_type` price is unavailable, falls back to `instance_catalog` table lookup, then to `0.0` — never raises.

**Output**: writes JSON summary to Redis key `spot:consolidation:candidates:{cluster_id}` (TTL 600s). Shape: `{karpenter_mode, candidates: [{node_name, instance_type, cpu_pct, mem_pct, pod_count, monthly_saving_usd}], total_saving_usd}`.

**Import fix applied**: `from backend.models.base import SessionLocal`.

---

## §Z. NEW AND MODIFIED DATABASE TABLES

### Z1. `karpenter_node_claims` (T-11)

**File**: `backend/models/karpenter_node_claims.py`
**Migration**: `migrations/versions/20260427_karpenter_node_claims.py`

| Column | Type | Notes |
|--------|------|-------|
| `id` | VARCHAR(36) PK | UUID |
| `cluster_id` | VARCHAR(36) FK→clusters CASCADE INDEX | |
| `node_name` | VARCHAR(253) | K8s NodeClaim `.metadata.name` |
| `instance_type` | VARCHAR(100) | From NodeClaim `.spec.requirements[instance-type]` |
| `capacity_type` | VARCHAR(20) | spot / on-demand |
| `az` | VARCHAR(50) | Availability zone |
| `state` | VARCHAR(50) | Karpenter NodeClaim state: Pending / Registered / Launched / Initialized / Ready / Terminating |
| `crd_version` | VARCHAR(20) | `v1` or `v1beta1` (auto-detected by agent) |
| `created_at` / `updated_at` | DATETIME | |

**Unique constraint**: `(cluster_id, node_name)` — `ON CONFLICT DO UPDATE` on batch upsert.

---

### Z2. `hpa_configs` (T-13)

**File**: `backend/models/hpa_configs.py`
**Migration**: `migrations/versions/20260427_hpa_tables.py`

| Column | Type | Notes |
|--------|------|-------|
| `id` | VARCHAR(36) PK | UUID |
| `cluster_id` | VARCHAR(36) FK→clusters INDEX | |
| `namespace` | VARCHAR(253) | |
| `name` | VARCHAR(253) | HPA object name |
| `target_kind` / `target_name` | VARCHAR | e.g. Deployment / my-service |
| `min_replicas` / `max_replicas` | INTEGER | Current HPA spec values |
| `desired_replicas` / `current_replicas` | INTEGER | Runtime values from `.status` |
| `target_cpu_pct` / `target_memory_pct` | INTEGER nullable | HPA target metric thresholds |
| `recommended_min_replicas` / `recommended_max_replicas` | INTEGER nullable | Written by T-16 `hpa_recommendation_task` |
| `collected_at` / `created_at` / `updated_at` | DATETIME | |

**Unique constraint**: `(cluster_id, namespace, name)`.

---

### Z3. `hpa_status_snapshots` (T-13)

**File**: `backend/models/hpa_status_snapshots.py`
**Migration**: same as Z2

| Column | Type | Notes |
|--------|------|-------|
| `id` | VARCHAR(36) PK | UUID |
| `cluster_id` | VARCHAR(36) FK→clusters INDEX | |
| `hpa_config_id` | VARCHAR(36) FK→hpa_configs | |
| `namespace` / `hpa_name` | VARCHAR INDEX | Denormalised for direct query |
| `current_replicas` / `desired_replicas` | INTEGER | Point-in-time snapshot values |
| `snapshot_at` | DATETIME INDEX | When snapshot was taken |

**Retention**: cleaned by `pod_metrics_cleanup.py` (same retention window as `pod_metrics`).
**Use**: T-16 P95 calculation reads last 14 days of snapshots ordered by `snapshot_at` per HPA.

---

### Z4. `pod_metrics` Schema Additions (T-12)

**File**: `backend/models/pod_metric.py`

| New Column | Type | Notes |
|------------|------|-------|
| `phase` | VARCHAR(20) nullable | Pod phase: Running / Pending / Succeeded / Failed / Unknown. Index: `idx_pod_metric_phase`. |
| `start_time` | DATETIME nullable | `pod.status.startTime` from K8s API. |

**Migration**: `migrations/versions/20260427_pod_metrics_phase_starttime.py`

---

## §AA. NEW AND UPDATED REDIS KEYS

### AA1. Consolidation Candidates Cache (T-18)

| Key | TTL | Writer | Reader |
|-----|-----|--------|--------|
| `spot:consolidation:candidates:{cluster_id}` | 600s | `consolidation_analysis_task.py` | `GET /optimize/nodes/bin-packing` endpoint (T-14) |

**Shape** (JSON string, `decode_responses=True` required):
```json
{
  "karpenter_mode": true,
  "candidates": [
    {"node_name": "...", "instance_type": "...", "cpu_pct": 12.4, "mem_pct": 8.1, "pod_count": 3, "monthly_saving_usd": 42.00}
  ],
  "total_saving_usd": 42.00
}
```

**Access pattern**: `redis_client.get(key)` → `json.loads()`. Uses `get_redis_client()` (decode_responses=True) — NOT raw `redis.from_url()`.

### AA2. Workload Log (Pre-existing, Corrected Usage)

| Key | TTL | Type | Writer | Reader |
|-----|-----|------|--------|--------|
| `spot:pc:workload_log:{cluster_id}:{workload_id}` | variable | **LIST** (RPUSH) | `PlacementController` | T-23 `_get_placement_workload_rows()` and `placement-detail` endpoint |

**Critical**: This is a Redis **LIST** (written via `rpush`), NOT a STRING. T-23 endpoints were corrected to use `lrange(key, 0, 0)` (latest entry) and `lrange(key, 0, 9)` (last 10 entries). `get()` returns an error on LIST types.

---

## §AB. NEW API ENDPOINTS — /optimize ROUTER (T-14 through T-24)

**File**: `backend/api/optimize_routes.py`
**Router prefix**: `/api/v1/optimize`
**Auth**: JWT (inherits from parent router)
**All endpoints require `cluster_id` query param unless stated otherwise.**

### AB1. Bin-Packing & Node Endpoints (T-14, T-15, T-21)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/optimize/nodes/bin-packing` | Node-level CPU/mem utilisation with overload flags. Reads `NodeMetadata` + latest `PodMetric` per node. Appends consolidation candidates from Redis `spot:consolidation:candidates:{cluster_id}` (TTL 600s). Returns `{nodes, data_ready, consolidation_candidates}`. |
| GET | `/optimize/nodes/{node_name}/workload-pods` | All pods running on a specific node (by `node_name`). Returns `{node_name, pods}`. |
| GET | `/optimize/nodes/{node_name}/bin-packing-detail` | Pod treemap list for a single node. Returns per-pod `{pod_name, namespace, controller_kind, controller_name, cpu_request_millicores, mem_request_bytes, cpu_usage_millicores, mem_usage_bytes}`. |

---

### AB2. Workload Scaling Endpoint (T-17)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/optimize/workloads/scaling` | Paginated HPA status list with scaling classification per workload. |

**Classification logic** (`_classify_hpa_status(cfg, snapshots_30m, snapshots_24h, has_pending_pods)`):

| Status | Condition |
|--------|-----------|
| `AT_MAX` | `current_replicas >= max_replicas` AND `has_pending_pods` |
| `SCALING_UP` | `desired_replicas > current_replicas` |
| `THRASHING` | ≥ 4 snapshots in last 30 min AND direction changes > 3 |
| `OVERPROVISIONED` | `current_replicas > recommended_max_replicas + 2` (T-16 field) |
| `OPTIMAL` | None of the above |

**KEDA bypass**: workloads with a matching `ScaledObject` in the KEDA tables are tagged `keda_managed=True` and returned with `status="KEDA_MANAGED"` — classification skipped.

**Response extras per row**: `has_warning` (bool), `cooldown_assessment` (string), `scale_events_24h` (int = direction changes in 24h snapshots), `recommended_max` (from `hpa_configs.recommended_max_replicas`).

**Summary sub-object**: `{total, at_max, scaling_up, thrashing, overprovisioned, optimal, keda_managed}`.

---

### AB3. Workload Profiling Endpoint (T-22)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/optimize/workloads/{workload_id}/profiling-detail` | 14-day CPU time-series + workload classification metadata. |

**Returns**:
- `cpu_timeseries`: daily `{date, avg_cpu, p95_cpu}` via `date_trunc('day', timestamp)` GROUP BY.
- `workload_meta`: from `WorkloadClassificationRecord` — `tier`, `confidence_state`, `spot_score`, `criticality_score`, `spot_friendly`.
- `placement_meta`: from `PlacementPolicyRecord` — `pod_cpu_cv`, `traffic_skew_detected`, `estimated_monthly_saving_usd`, `ondemand_target`, `spot_target`.

---

### AB4. Placement List & Detail (T-23)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/optimize/workloads/placement` | Paginated placement workload list. Params: `cluster_id`, `page` (ge=1), `page_size` (ge=1, le=100). |
| GET | `/optimize/workloads/{workload_id}/placement-detail` | Full placement state for one workload. |

**Shared helper `_get_placement_workload_rows(cluster_id, db, redis_client)`**:
- Queries `WorkloadClassificationRecord` (all workloads for cluster).
- Joins `PlacementPolicyRecord` per workload (single query per workload).
- Reads `spot:pc:workload_log:{cluster_id}:{workload_id}` via `lrange(key, 0, 0)` → extracts latest `action` field as `placement_status`.
- Returns list of dicts with: `workload_id`, `namespace`, `tier`, `confidence_state`, `spot_score`, `spot_friendly`, `ondemand_target`, `spot_target`, `estimated_monthly_saving_usd`, `placement_status`, `pod_cpu_cv`, `traffic_skew_detected`.

**`placement-detail` endpoint additional fields**:
- `state_locks`: reads `spot:workload:state:{cluster_id}:{workload_id}` → `cooldown_active`, `rollout_blocked`, `keda_scaling_active`, `pdb_active`.
- `recent_decisions`: `lrange(spot:pc:workload_log:{cluster_id}:{workload_id}, 0, 9)` → last 10 placement log entries parsed as JSON.

---

### AB5. Scaling Detail Endpoint (T-24)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/optimize/workloads/{workload_id}/scaling-detail` | 120-minute HPA snapshot timeline + scale event count. |

**Returns**:
- `hpa_timeline`: `HpaStatusSnapshot` rows from the last 120 minutes ordered by `snapshot_at` ASC. Each row: `{snapshot_at, current_replicas, desired_replicas}`.
- `scale_events_120m`: count of direction changes in the last 120 minutes (consecutive `desired_replicas` differs from previous).
- `hpa_config`: from `HpaConfig` — `min_replicas`, `max_replicas`, `recommended_min_replicas`, `recommended_max_replicas`, `target_cpu_pct`.

---

## §AC. UI CHANGES (T-19, T-20)

### AC1. WorkloadProfiling.jsx — CV Label (T-19)

**File**: `frontend/src/pages/optimize/workloads/WorkloadProfiling.jsx` (line 290–294)

Added a contextual label below the sparkline chart grid:
> *"Variability measured over 14-day window. CV > 0.4 raises OD baseline."*

This explains the Coefficient of Variation metric to operators without requiring them to navigate docs.

---

### AC2. WorkloadScaling.jsx — KEDA Integration UI (T-20)

**File**: `frontend/src/pages/optimize/workloads/WorkloadScaling.jsx`

| Change | Location | Detail |
|--------|----------|--------|
| `isKedaManaged` state | line 1 / 102–112 | `useState(false)` + `useEffect` that calls `/api/v1/keda/{cluster_id}/scaled-objects`, checks if workload name appears in the ScaledObjects list, sets `isKedaManaged=true` if found |
| KEDA badge | line 175–187 | Shows `"KEDA MANAGED"` badge in the forensics panel header when `isKedaManaged === true` |
| HPA recommendation label | line 192–197 | Displays `"Based on P95 of current_replicas × 1.2 (14-day window)"` sub-label beneath the HPA recommendation table |
| Scale event history | line 220–225, 237–239 | Replaced hardcoded mock SVG timeline with `"Scale event history coming soon"` placeholder |

---

## §AD. SESSION FIX LOG (2026-04-27 Validation Pass)

All fixes identified and applied during post-implementation validation sweep.

| # | Fix | File | Root Cause | Status |
|---|-----|------|-----------|--------|
| 1 | `SessionLocal` import path | `hpa_recommendation_task.py`, `consolidation_analysis_task.py` | Both files imported from `backend.core.database` — module does not exist. Correct path: `backend.models.base`. | **RESOLVED** |
| 2 | Missing `import redis` | `optimize_routes.py` | `redis.from_url()` called in T-14/T-23 endpoints but `redis` not in top-level imports → `NameError` at runtime. | **RESOLVED** |
| 3 | Redis LIST read with wrong command | `optimize_routes.py` (T-23) | `spot:pc:workload_log` is written via `rpush` (LIST type). T-23 used `get()` which returns an error on LIST keys. Corrected to `lrange(key, 0, 0)` (single latest) and `lrange(key, 0, 9)` (last 10). | **RESOLVED** |
| 4 | `decode_responses=False` on Redis client | `optimize_routes.py` (T-14, T-23) | Used `redis.from_url(settings.REDIS_URL)` without `decode_responses=True`. Returns bytes — `json.loads()` may fail or produce incorrect output on Python 3.9+. Replaced with `get_redis_client()` which sets `decode_responses=True`. | **RESOLVED** |
| 5 | Dead `active_evictions` DB query | `optimize_routes.py` `_get_placement_workload_rows()` | `AgentAction` query result was assigned to `active_evictions` but the variable was never used — unnecessary DB round-trip per placement list request. Removed. | **RESOLVED** |

---

## §AE. COMPLETE NEW FILE MANIFEST (T-09 through T-24)

| File | Type | Task | Purpose |
|------|------|------|---------|
| `backend/models/karpenter_node_claims.py` | New Model | T-11 | KarpenterNodeClaim SQLAlchemy model |
| `backend/models/hpa_configs.py` | New Model | T-13 | HpaConfig SQLAlchemy model |
| `backend/models/hpa_status_snapshots.py` | New Model | T-13 | HpaStatusSnapshot SQLAlchemy model |
| `backend/workers/tasks/hpa_recommendation_task.py` | New Task | T-16 | P95×1.2 HPA replica recommendation |
| `backend/workers/tasks/consolidation_analysis_task.py` | New Task | T-18 | Karpenter + non-Karpenter consolidation candidate analysis |
| `migrations/versions/20260427_karpenter_node_claims.py` | New Migration | T-11 | Creates `karpenter_node_claims` table |
| `migrations/versions/20260427_pod_metrics_phase_starttime.py` | New Migration | T-12 | Adds `phase`, `start_time` to `pod_metrics` |
| `migrations/versions/20260427_hpa_tables.py` | New Migration | T-13 | Creates `hpa_configs` and `hpa_status_snapshots` tables |

### Modified Files Summary

| File | Tasks | Key Changes |
|------|-------|-------------|
| `agent/heartbeat.py` | T-09 | Added `set_metrics_collector()`, `send_node_metadata_batch()`, integrated into `run()` loop |
| `agent/main.py` | T-09 | Wired `set_metrics_collector()` to link node metadata to `HeartbeatSender` |
| `agent/karpenter_watcher.py` | T-11 | Added NodeClaims polling thread + `_detect_crd_version()` + `_poll_nodeclaims()` |
| `agent/pod_metrics_collector.py` | T-12, T-13 | Added `phase` + `start_time` collection; added `collect_hpa_configs()` + `send_hpa_configs_batch()` |
| `backend/models/pod_metric.py` | T-12 | Added `phase` (indexed) + `start_time` columns |
| `backend/schemas/pod_metric_schemas.py` | T-12 | Extended `PodMetricCreate` + `PodMetricResponse` with `phase`, `start_time` |
| `backend/api/pod_metrics_routes.py` | T-12 | Added `phase`, `start_time` to `PodMetric` constructor |
| `backend/api/agent_routes.py` | T-11, T-13 | Added `POST /agents/nodeclaims/batch` (T-11) + `POST /agents/hpa-configs/batch` (T-13) |
| `backend/api/optimize_routes.py` | T-14–T-24 | Added 8 new endpoints under `/optimize/`; fixed `import redis`, `lrange` bug, `decode_responses` bug, removed dead query |
| `backend/workers/tasks/pod_metrics_cleanup.py` | T-13 | Extended cleanup to include `hpa_status_snapshots` retention |
| `backend/workers/app.py` | T-16, T-18 | Registered `hpa_recommendation_task` (every 30 min) and `consolidation_analysis_task` (every 10 min) in `include` list and `beat_schedule` |
| `frontend/src/pages/optimize/workloads/WorkloadProfiling.jsx` | T-19 | CV label below sparkline grid |
| `frontend/src/pages/optimize/workloads/WorkloadScaling.jsx` | T-20 | KEDA detection state/effect, KEDA badge, HPA recommendation label, scale event placeholder |

---

## §AF. UPDATED RELIABILITY SCORE (Post v11.0)

> **v11.0 score: 8.5 / 10** (up from 7.5 / 10 post v10.0 hardening)

---

# PART C: REAL OPERATIONAL STATE AUDIT
**Source**: All findings derived from live code — `scheduler.py`, `workers/app.py`, `services/`, `api/`, `docker/docker-compose.yml`, `migrations/`, `agent/`. No .md files used as source of truth.

---

## C.1 Deployment & Environment

### Deployment Topology
The platform runs as a single-tenant, multi-cluster system — not SaaS. There is one FastAPI process (`uvicorn`, port 8000), one PostgreSQL instance, one Redis instance, and one Celery worker container, all in a single Docker Compose stack (`docker/docker-compose.yml`). Multiple EKS clusters (currently three registered: `seed0003`, `spot-demo-1`, `spot-demo-2`) are monitored and managed by this single backend. Each cluster runs its own agent DaemonSet + orchestrator Deployment installed via Helm (`charts/spot-optimizer-agent`). The backend has no per-tenant isolation — a single DB and Redis instance serves all clusters.

### Environment Isolation
There is exactly one running environment. No dev/stage/prod separation exists at the infrastructure level. The `.env.example` file contains a single set of credentials. No feature-flag matrix, no separate DB per environment, no namespace-level separation. The "seed" cluster (`seed0003`) exists purely as demo data seeded via `scripts/seed_demo_data.py`, not as a functional separate environment.

### Backend Runtime Architecture
The backend is a monolith FastAPI application. One `uvicorn` process handles all API routes, WebSocket connections, and 10 in-process APScheduler background jobs. Celery workers run in separate Docker containers for async task processing. All shared state — cluster metadata, action queues, placement policies, circuit breaker state — goes through the same PostgreSQL and Redis instances. There is no microservice split; `placement_controller_service.py`, `workload_identification_engine.py`, `pool_ranking_service.py`, `karpenter_service.py` are all imported into the same process or the same Celery worker.

---

## C.2 Database & Schema

### DB Schema Version and Migration Consistency
The highest Alembic migration in `backend/migrations/` is `013_agent_actions_retry_fields` (down_revision `012_rebalancing_actions_pod_level`). The chain is: `001 → 002 → ... → 013`. However, several schema changes were applied manually via raw `ALTER TABLE` SQL outside of Alembic (columns `cpu_cv`, `traffic_skew_detected` on `workload_classifications`; `phase`, `start_time` on `pod_metrics`). These were later captured in migration files `20260427_pod_metrics_phase_starttime.py` and related. This means the Alembic revision head and the actual deployed schema can diverge on a freshly initialized DB if the early raw ALTER TABLEs are not replayed. The `_ensure_tables()` function in `seed_demo_data.py` was added to compensate. Risk: any fresh DB provisioned from `alembic upgrade head` alone may be missing columns that existed only as raw SQL.

### Celery Workers and Queue Coverage
The Celery worker in `docker-compose.yml` runs with `--concurrency=4 -Q celery,pricing`. There is only one worker container. The `beat_schedule` in `workers/app.py` defines 42+ scheduled tasks. Queues consumed: `celery` (default) and `pricing`. The PART B section of this document references four queues (`default`, `emergency`, `pricing`, `monitoring`) but the docker-compose worker command only binds to two. Emergency and monitoring tasks exist in the task registry but the worker is not explicitly routing them to a separate high-priority queue unless the Celery broker default routing applies them to `celery`. Actual queue lag is not observable without Flower or a Redis `LLEN` query. There is no Flower deployment in docker-compose.

---

## C.3 Redis Architecture and Key Health

### Redis Topology and Eviction Policy
Redis runs as a single standalone node (`redis:6-alpine`) with `--appendonly yes` (AOF persistence). No cluster mode, no Sentinel, no replica. The docker-compose `command` passes only `--appendonly yes` — no `--maxmemory` or `--maxmemory-policy` directive. This means Redis is running with the default `noeviction` policy: when memory is exhausted, Redis returns errors on write commands rather than evicting keys. There is no memory ceiling defined, so growth is unbounded until the host runs out of RAM. This is the single biggest silent operational risk in the system.

### Redis Memory Utilization and Key TTL Health
Redis DB 0 is used for application state (placement metrics, locks, cluster state, workload classification cache). DB 1 is the Celery broker. DB 2 is the Celery result backend. Key TTL coverage is mixed: cycle locks (300–600s) and workload locks (30s) and mutex (60s) all have TTLs. However, cluster state hashes (`spot:cluster_state:{cluster_id}`) are explicitly set with no TTL per `risk_engine.py`: `"Do NOT set a TTL on this key — permanent for cluster's lifetime."` Circuit breaker keys (`cb:state:{cluster_id}`, `cb:rollbacks:{cluster_id}`) have no TTL. Over time these accumulate indefinitely. The daily `job_cleanup_blacklist()` (2 AM cron) only cleans blacklist-category keys via `BlacklistService.cleanup_redis_keys()`.

### Stale and Orphaned Redis Keys
The `RedisCacheManager` explicitly prohibits `SCAN` operations to avoid performance issues. This means orphan detection relies entirely on TTL expiry. Keys without TTLs (cluster state, circuit breaker state, shadow mode keys) accumulate permanently. The `BlacklistService` cleanup handles a specific namespace. No general-purpose Redis key audit runs. Orphaned keys from deleted clusters (cluster state, placement metrics, workload locks) remain in Redis indefinitely after a cluster is removed from the DB.

---

## C.4 Concurrency, Locks, and Cycle Execution

### Cluster Mutex Starvation Risk
The `spot:cluster_mutex:{cluster_id}` is a 60-second heartbeat lock (`HeartbeatLock` in `backend/utils/redis_locks.py`). PlacementController acquires it for the full duration of `run_cycle()`. auto_rebalancer performs a read-only skip-check: if the key exists, AR skips that cluster for its 15-second tick. If a PC cycle takes longer than expected (e.g., a slow Karpenter API call), the heartbeat renewal prevents expiry. If the PC worker crashes mid-cycle, the lock expires in 60 seconds and AR resumes. There is no starvation in the classic sense — AR simply comes back on the next 15s tick. However, if PC cycles consistently take >10 seconds and AR runs every 15 seconds, AR effectively gets one opportunity per two PC cycles for any given cluster.

### Real Concurrency Per Cluster
`CLUSTER_BATCH_SIZE=2` (env `PC_CLUSTER_BATCH_SIZE`). This limits the maximum number of concurrent `PENDING` or `PICKED_UP` `AgentAction` records per cluster to 2, across both Engine A and Engine B. This is a hard gate enforced by a `COUNT(*)` query on `agent_actions` at the start of each PC cycle. Engine A (auto_rebalancer) enforces its own semaphore separately via `rebalance:active_count:{cluster_id}`. In practice, at most 2 concurrent pod evictions or 2 node drain operations run per cluster at any time.

### AgentAction Failure Rate
Tracked structurally: every `AgentAction` record has `status` (PENDING → PICKED_UP → COMPLETED or FAILED) and `retry_count SMALLINT DEFAULT 0`. The `permanent_failures` counter in the PC metrics Redis hash (`spot:placement_controller:metrics:{cluster_id}`) counts actions that exhausted `MAX_RETRY_COUNT=3`. No alert fires when failures spike. The only visibility is direct DB query or reading the Redis metrics hash (TTL 3600s, reset each cycle). No historical failure rate trend is stored beyond 1 hour.

### Action Creation-to-Completion Latency
No end-to-end latency measurement is instrumented. The timestamps `created_at` and a completion timestamp exist on `AgentAction` but no Celery task or background job computes percentiles. From architecture: agent polls actions every ~15 seconds (auto_rebalancer beat), so minimum pickup latency is 0–15 seconds from creation. Execution time depends on the action type: cordon is near-instant, drain waits for pod termination grace periods (typically 30–60s), and stateful rollout waits up to `MIGRATION_TIMEOUT_MINUTES=20`.

---

## C.5 Agent Health and Heartbeat

### Agent Heartbeat Reliability
The agent sends `POST /agents/heartbeat` from `agent/heartbeat.py`. The Celery task `reset_stale_agents` (`backend.workers.tasks.health.reset_stale_agents`) runs every 60 seconds and sets `agent_installed='N'` and `status=DISCONNECTED` for clusters whose `last_heartbeat` is older than 5 minutes. This means the maximum undetected agent downtime window is approximately 5 minutes. After that, the cluster is correctly flagged as disconnected. No alert (Slack/email) is triggered when this happens — the state change is purely a DB update.

### Clusters Without Agents Still Marked Active
Within the 5-minute detection window, a cluster can be marked ACTIVE with `agent_installed='Y'` even though the agent is down. After `reset_stale_agents` fires, the cluster transitions to DISCONNECTED. PlacementController skips clusters with `agent_installed != 'Y'` (it filters on this flag in the task dispatch loop `dispatch_placement_controller_cycles`), so at most one or two 5-minute PC cycles could run against a "ghost ACTIVE" cluster before the stale agent is detected.

### Agent Version Distribution
Agent version is not persisted in the DB. The `AgentRegisterRequest` schema includes a `version` field (default `"1.0.0"`) which is logged but not stored in the `clusters` table. All currently deployed agents are on version `1.1.8` (set by `AGENT_IMAGE=atharva608/spot-optimizer-agent:1.1.8` in `update-tunnel.sh`). The Helm chart `values.yaml` previously defaulted to `1.1.6` — this has been corrected. There is no version drift detection or enforcement mechanism.

### WebSocket vs HTTP Polling
Both channels are implemented. From `agent/` directory manifest: `websocket_client.py` maintains a persistent WS connection to `/ws/cluster/{id}`. `poller.py` is an explicit HTTP polling fallback for when WebSocket disconnects. `collector.py` always uses `POST /metrics/batch` over HTTP for metrics ingestion — this is never over WebSocket. The heartbeat always uses `POST /agents/heartbeat` over HTTP. In practice, action receipt happens via both paths simultaneously: WS push triggers immediate actuator execution, and the HTTP poller provides resilience if WS drops. Whether WS or HTTP polling dominates in practice depends on network stability between the Cloudflare tunnel and the agent.

### Metrics Ingestion Delay
Agent logs confirm `POST /metrics/batch` is called approximately every 20 seconds per agent pod (observed from live agent logs: `"Successfully sent 17 metrics to backend"`, `"Successfully sent 20 metrics to backend"`, cycle complete). This means node and pod state data in the DB is at most ~20 seconds stale under normal operation. The `data_freshness.py` util uses `STALE_THRESHOLD_SECONDS=120` as the staleness gate — well within the 20s actual cadence.

---

## C.6 PlacementController Cycle Behavior

### PlacementController Scaling Guard Skip Rate
When cluster-level pending pods exceed `PENDING_PODS_THRESHOLD=3` (env `PC_PENDING_PODS_THRESHOLD`), or when a KEDA scale event occurred within `SCALING_GUARD_WINDOW_SECONDS=120s`, `run_cycle()` returns early after incrementing `evictions_skipped_scaling_guard`. This counter is stored in the per-cluster Redis metrics hash (TTL 3600s). The frequency depends entirely on cluster activity — it spikes during deployments or after KEDA-triggered scale events and is effectively zero on idle clusters. No historical trend exists beyond the 1-hour metrics window.

### PlacementController Capacity Check Skip Rate
When the Spot capacity check (CPU + memory + ENI slots per AZ at `SPOT_CAPACITY_BUFFER=0.7`) fails, `evictions_skipped_capacity` is incremented. If no Spot node exists at all in any AZ, `evictions_failed_due_to_no_replacement` is incremented additionally. Both counters reside in the same Redis hash with 3600s TTL. This is the second most common skip reason after cooldown on small clusters where Spot node count is low. On the demo cluster (`spot-demo-2` with 4 nodes, all provisioned as standard workers), Spot availability depends on Karpenter provisioning new Spot nodes after evictions.

### Percentage of Evicted Pods That Land Back on On-Demand
Tracked via `handle_eviction_result()` in `placement_controller_service.py`. After each eviction, the backend queries the pod's current node's `capacity_type` from `NodeMetadata`. If `capacity_type == 'on-demand'`, `_mark_for_retry()` fires, incrementing both `retry_count` on `AgentAction` and the `retry_incremented` counter in the metrics hash. The actual percentage is not aggregated over time — only the last PC cycle's metrics are visible in the TTL 3600s Redis hash. The `permanent_failures` counter represents pods that exceeded `MAX_RETRY_COUNT=3` without landing on Spot.

---

## C.7 AgentAction Retry Mechanics

### Retry Count Distribution and MAX_RETRY_COUNT Behavior
`retry_count` is a `SMALLINT DEFAULT 0` column on `agent_actions` (added in migration `013_agent_actions_retry_fields`). `MAX_RETRY_COUNT=3` (env `PC_MAX_RETRY_COUNT`). Each time `_mark_for_retry()` is called, `retry_count` is incremented and the action is re-queued as `PENDING`. At `retry_count >= 3`, the action is moved to `FAILED` permanently and `_decr_semaphore()` is called to release the cluster batch slot. No escalation or alert fires. The workload is re-evaluated on the next 5-minute PC cycle, which may dispatch a new `AgentAction` for a different pod. This means the same workload can generate repeated waves of actions if Spot capacity is persistently insufficient.

---

## C.8 Stateful Rollout Mechanics

### Stateful Rollout Success Rate and Timeout
`stateful_rollout_started`, `stateful_rollout_completed`, `stateful_rollout_failed`, and `stateful_rollout_timeout` counters are all tracked in the Redis metrics hash per cluster per cycle. `MIGRATION_TIMEOUT_MINUTES=20` is the default wait. On timeout, `placement_rollout_service.py` scales replicas back to `original_replicas` only if the original pod is still `Running` — this prevents double-kill on already-gone pods. A 30-minute failed-migration cooldown (`MIGRATION_FAILED_COOLDOWN_MINUTES=30`) prevents immediate re-attempt. The actual success rate is not aggregated in DB — only the last cycle's Redis hash is available. An hourly stale migration recovery scan in `placement_controller_task.py` catches orphaned scale-ups where a replica was scale-up but the original pod was never removed.

### Rollback Trigger Frequency
The `CircuitBreaker` service (`circuit_breaker.py`) tracks rollbacks per cluster in `cb:rollbacks:{cluster_id}` (no TTL). The rollback window counter is a sliding 1-hour count. `NORMAL → CONSERVATIVE` threshold is 2 rollbacks/hour. `CONSERVATIVE → HALT` threshold is 3 rollbacks/hour from CONSERVATIVE state. Recovery: `HALT → CONSERVATIVE` after 30 minutes with no failures; `CONSERVATIVE → NORMAL` after 2 hours stable. Emergency actions (priority=10) and gate rejections do NOT count toward this counter (per comment in `circuit_breaker.py` line 100). Frequency is unknown without querying Redis directly.

### Workload Drift Frequency
Drift is computed every 5 minutes per workload that has a `PlacementPolicy`. The drift threshold is adaptive: `1` if `ondemand_target ≤ 3`, else `max(2, int(ondemand_target × 0.2))`. If `excess_od < threshold`, the cycle is a no-op for that workload. On freshly onboarded clusters where pods naturally land on OD (before Spot is established), nearly every 5-minute cycle will show drift above threshold until the fleet stabilizes.

---

## C.9 Workload Intelligence

### Percentage of Workloads With Placement Policies Generated
`PlacementPolicyRecord` rows are created by `PlacementAdvisorService` in `placement_advisor_service.py` only for workloads that pass two gates: (a) `WorkloadClassificationRecord.confidence_state == 'CONFIRMED'` and (b) `WIE` has completed at least one scan (checked via Redis key `spot:wie:metrics:{cluster_id}` in `scheduler.py`). On a fresh cluster, no policies exist until WIE runs the slow loop (10 min after boot) and the placement advisor cycle runs (10 min after WIE). The proportion depends on how many workloads reach CONFIRMED state vs remaining in DRAFT/PROVISIONAL.

### Percentage of Workloads Actionable vs Blocked by WIE Confidence
`WorkloadClassificationRecord.confidence_state` has three states: `DRAFT` (<5 confidence), `PROVISIONAL` (5–7), `CONFIRMED` (≥8). Only CONFIRMED workloads get `PlacementPolicyRecord` generated. Only workloads with `actionable=True` in their policy get picked up by PlacementController. A workload can have a policy but still be non-actionable if WIE marks `spot_friendly=False` or if the tier is Platinum (100% OD). The exact cross-cluster percentage is available via the `/workload-classification/{id}/summary` API per cluster but not aggregated globally.

### WIE Confidence Distribution
WIE (`workload_identification_engine.py`) requires 24 hours of data before confidence can reach CONFIRMED (`WIE_COLD_START_HOURS=24`). On clusters younger than 24 hours, all workloads are capped at PROVISIONAL regardless of scoring. After 24h, confidence is driven by data freshness (recent pod state cache), restart rate stability, and observation count. No cross-cluster confidence histogram exists. The `/workload-classification/{id}/summary` endpoint returns tier distribution per cluster.

### Duration in DRAFT or PROVISIONAL
WIE does not store state transition timestamps. `WorkloadClassificationRecord.updated_at` tracks the last classification update but not when the confidence state changed. A workload that has been in DRAFT for 72 hours is indistinguishable from one that entered DRAFT 2 minutes ago from the DB schema alone. This is a gap: there is no visibility into classification age by confidence tier.

---

## C.10 Placement Advisor

### Placement Advisor Execution Success Rate
The placement advisor task (`run_placement_cycle_task` in `placement_advisor_task.py`) is a Celery task dispatched from the APScheduler `job_run_placement_cycle()` every 10 minutes. It has its own Redis lock (`spot:placement:cycle_lock:{cluster_id}`, 300s TTL) to prevent concurrent cycles. Task success/failure is logged to Celery's result backend (Redis DB 2) but no dedicated metrics counter or alert exists. If the task throws an exception, Celery marks it FAILURE and logs it. The next 10-minute cycle simply retries.

### Placement Advisor ondemand_target Consistency
`ondemand_target` is a deterministic function of `tier` + `cv_adjustment` + `pdb_min_available`. Given the same workload state (same tier, same CPU CV, same replica count), the output is identical every cycle. Oscillation can only occur if (a) the workload flips between tiers due to WIE re-classification, or (b) CPU CV straddles the 40% threshold between cycles (possible if the metric is computed on a rolling window that changes significantly cycle-to-cycle). On stable workloads, `ondemand_target` should remain constant.

---

## C.11 Cost Savings and Accuracy

### Actual Cost Savings vs Estimated Accuracy
`PlacementPolicyRecord.estimated_monthly_saving_usd` is a forward estimate computed from the difference in cost between `current_od_pods × od_price` and `ondemand_target × od_price + (current_pods - ondemand_target) × spot_price`. This uses real-time pricing from `aws_pricing_service.py`. However, this estimate is never reconciled against actual AWS billing. The `cost-explorer-sync-daily` task (`workers.cost.sync_cost_explorer`) fetches actual Cost Explorer data independently. The two datasets — estimated savings (from Placement Advisor) and actual spend delta (from Cost Explorer) — exist in separate DB tables with no join query or reconciliation job. Savings accuracy is therefore unknown.

### Spot vs On-Demand Ratio Across Clusters
Available as a computable metric: `node_metadata.capacity_type` records `'spot'` or `'on-demand'` per node per cluster. The agent pushes this via `POST /node-metadata/batch`. The `/api/v1/optimize/nodes/bin-packing` endpoint aggregates this into `node_count`, `total_cpu_allocatable`, and utilization per cluster. A live Spot/OD ratio query is possible but no scheduled job computes or reports it as a time series. The UI shows it per-cluster in the Bin Packing view.

---

## C.12 Interruption Prediction and Karpenter

### Interruption Rate Observed vs Predicted
The `adaptive_itn_service.py` tracks actual interruptions per cluster via events processed through `POST /agents/spot-interruption`. The `PoolRankingService` uses a `GlobalEMAService` that maintains exponential moving average interruption rates per `(region, AZ, instance_type)` tuple in Redis (`spot:pool:ema:{region}:{az}:{itype}`). The `AdaptiveITN` service computes per-cluster risk tolerance based on accumulated node-hours and actual interruption events. The `adaptive-itn-decay-hourly` Celery task decays scores and flushes to Postgres. The accuracy of predicted vs observed interruption rate is maintained by this feedback loop but is not exposed as a dashboard metric.

### Karpenter Provisioning Latency
`KarpenterMetricsCollector` (`karpenter_metrics_collector.py`) collects metrics from Karpenter's Prometheus endpoint every 2 minutes (APScheduler job `karpenter_metrics_collection`). It captures provisioning latency P50/P90/P95 and provision success rates per cluster. Results are stored in Redis. No UI component currently renders these values. The data is available but not surfaced.

### Karpenter Provisioning Failures and OD Fallback
The Karpenter circuit breaker in `karpenter_service.py` trips at 10 consecutive failures within a 10-minute window, entering a 30-minute halt. When no safe Spot pools exist, `switch_to_ondemand()` sets `capacity-type: on-demand` with a 12-hour Redis TTL (`spot:ondemand_fallback:{cluster_id}`). After TTL expiry, the `check_reversion_opportunities` task (hourly) calls `revert_to_spot()` to patch the NodePool back to `capacity-type: spot`. Reversion is automatic as long as Celery beat is running. There is no mechanism to force-stay in OD fallback longer than 12 hours without manually setting the Redis key again.

---

## C.13 Node Lifecycle and Ghost Nodes

### Node Churn Rate
Not tracked as an explicit metric. Node terminations are recorded via `AgentAction(type=TERMINATE_NODE, status=COMPLETED)` records. A churn rate (terminations/hour) could be computed by querying `agent_actions WHERE type='TERMINATE_NODE' AND status='COMPLETED' AND created_at > NOW() - INTERVAL '1h'` but no scheduled job does this. Node lifecycle events are also visible in `NodeMetadata.updated_at` but deletions are not tombstoned with a timestamp.

### Stuck Nodes Not Terminated After Drain
The `reconciliation_worker` (every 5 minutes) detects `AgentAction` records in `PENDING` or `PICKED_UP` state for longer than expected. The `termination_monitor.py` Celery task (`zombie-cleanup-every-2-mins`) specifically cleans up zombie nodes. Additionally, `cleanup_zombie_od_instances` (hourly) terminates On-Demand EC2 instances with no corresponding K8s node after 10 minutes. This three-layer approach (reconciliation + termination monitor + zombie OD cleanup) should catch most stuck nodes.

### Ghost Nodes (AWS But Not DB) and Orphaned DB Records
Ghost nodes (running in AWS but absent from the DB) are detected by `recovery_monitor.py` via `scan_orphans` (every 5 minutes). The `reconciliation_worker` handles drift between EC2 state and DB state (Issue #34 fix). DB records for nodes not present in the cluster are cleaned by `cleanup_tasks.py` (removes old migration events and terminated EC2 records). The `reconcile_nodepool_classes_task` ensures Karpenter NodePool definitions match DB configs. This is a reasonably comprehensive reconciliation layer for a single-region deployment.

---

## C.14 Execution Controller and Stubbed Code

### ExecutionController Stub Status in Production Path
`ExecutionController` in `execution_controller.py` documents a direct (non-agent) node replacement pipeline. Four methods remain stubbed: `_wait_substitute_ready`, `_drain_node`, `_verify_workload_health`, and `_terminate_node` — each returns `True` without doing real work. However, this is NOT the primary execution path. The actual production path for both Engine A and Engine B routes all K8s mutations through `AgentAction` DB records picked up by the in-cluster agent (`agent/actuator.py`). `ExecutionController.execute_replacement()` is a legacy direct-execution fallback that predates the agent model. Any code that still calls it directly would silently "succeed" without performing real K8s operations — a correctness risk if the call path is ever exercised.

### Which Stubbed Methods Are Called in Production
`auto_rebalancer.py` — the primary Engine A — creates `AgentAction` records (CORDON_NODE → DRAIN_NODE → TERMINATE_NODE) and does NOT call `ExecutionController.execute_replacement()` directly. `emergency_rebalancer.py` uses `AgentAction` dispatch as well. A codebase search confirms `ExecutionController` is imported and instantiated in certain service files but the `execute_replacement()` entry point is not in any active Celery task or beat schedule path. The stubs are dormant in the current production flow but remain a risk if future code inadvertently invokes the direct path.

### ASG Legacy Code Dependency
`SubstituteManager` (`substitute_manager.py`, 60KB) still runs every 5 minutes via APScheduler (`job_reconcile_substitutes`). It reconciles "stuck substitutes" — EC2 instances launched as replacements in the pre-Karpenter era. `spot_asg_service.py` exists and is importable. The `karpenter_only_mode` boolean flag on `ClusterOptimizationSettings` is the intended gate to skip ASG paths entirely, but the APScheduler jobs for `SubstituteManager` and `job_check_cost_drift` run unconditionally regardless of this flag. Legacy ASG code continues to execute on every cluster every 5 minutes.

---

## C.15 Pool Services

### Pool Rotation Effectiveness
`pool_rotation_service.py` + `pool_rotation_worker.py` manage time-based rotation of NodePools to prevent capacity exhaustion in a single Spot pool. The `pool-rotation-check-every-5-mins` task scans all clusters for NodePools that have been active beyond a rotation threshold and swaps to a standby pool. The `pool-cache-refresh-every-15-mins` task pre-warms fresh pool data. The underlying pool ranking is maintained by `GlobalEMAService` and `AdaptiveITN`. Effectiveness (reduction in actual interruption rate post-rotation) is tracked indirectly by the EMA decay; no direct before/after metric is computed.

---

## C.16 Circuit Breakers

### Circuit Breaker Trigger Frequency and Downtime
The `CircuitBreaker` service operates per-cluster with three states: `NORMAL → CONSERVATIVE → HALT`. State is stored in Redis keys `cb:state:{cluster_id}` and `cb:rollbacks:{cluster_id}` with no TTL (permanent). Transition thresholds: 2 rollbacks/1h → CONSERVATIVE; 3 rollbacks/1h from CONSERVATIVE → HALT. Recovery: 30 min stable → back to CONSERVATIVE; 2h stable → back to NORMAL. In CONSERVATIVE mode, the `risk_multiplier` increases up to 1.3x, making the pool scoring engine prefer lower-risk pools. In HALT, `automation_allowed = False` blocks all placement and rebalancing automation. There is no automatic circuit breaker reset after a fixed wall-clock timeout — only the rollback-count-decay path triggers recovery. A cluster could theoretically stay in HALT indefinitely if the rollback window counter never clears.

### Separate Karpenter Circuit Breaker
Independent of the above, `karpenter_service.py` has a separate circuit breaker: 10 provisioning failures within 10 minutes triggers a 30-minute automation halt specific to Karpenter operations. This is tracked in Redis and resolves automatically after 30 minutes without manual intervention.

---

## C.17 API Security and Auth Gaps

### JWT Coverage Across Endpoints
Most user-facing routes (cluster, account, hygiene, keda, billing, audit, onboarding) require `Depends(get_current_user)` which validates a JWT token. Agent-facing routes (`agent_routes.py`) use `Depends(validate_api_key)` which validates `cluster.api_key` from the DB. **The gap**: all `/api/v1/optimize/*` endpoints in `optimize_routes.py` use only `assert_cluster_access(cluster_id, db)` — a DB row existence check — without `Depends(get_current_user)`. This means anyone who knows a valid `cluster_id` UUID (which is a UUID4, so not easily guessable, but potentially leaked via logs or responses) can read all placement, scaling, profiling, and bin-packing data without authentication.

### Unauthenticated Endpoints
Three endpoints have zero authentication:
- `POST /agents/spot-interruption` — accepts spot interruption events with no credential check. Any internet-accessible caller can inject fake interruption events.
- `POST /agents/rebalance-recommendation` — same: no auth.
- `GET /api/v1/agents/discover-url` — intentionally public; returns the backend tunnel URL. Used by agents before they have credentials.
- `GET /api/installer/linux` — intentionally public; generates installer scripts. Accepts `cluster_id` and `api_key` as query params — the api_key is exposed in the URL.

### RBAC Consistency
RBAC (`role_service.py`, `permission_service.py`) is implemented for user-facing operations via `RequireRole` and `RequireAccess` dependencies. However, the optimization pipeline endpoints (`optimize_routes.py`, `workload_classification_routes.py`) bypass RBAC entirely — they rely only on `assert_cluster_access` which checks cluster DB row existence, not organizational or role-level permissions.

---

## C.18 UI Component Status

### Percentage of UI Components With Real vs Fake Data
Based on code audit of all six optimize pages:
- **Node Bin Packing**: 14 of 17 UI fields backed by real DB/Redis data. 3 fields are hardcoded (packed target label, recommendation text, node card background color logic).
- **Node Selector**: 100% hardcoded mock data. No backend endpoint exists (`GET /api/v1/optimize/nodes/selector` is referenced in the component but not implemented). This is an active UI placeholder with no backend.
- **Workload Migration**: 100% hardcoded mock data. No migration planning, execution, or audit API exists. This is a UI prototype only.
- **Workload Profiling**: Real list and summary from WIE APIs. CPU timeseries chart real from `pod_metrics`. Savings column always shows $0 (bug). RPS data completely absent.
- **Workload Placement**: All list/detail endpoints real. Pod table often empty on fresh clusters because `pod_metrics.phase` and `start_time` were only recently added.
- **Workload Scaling**: HPA config and snapshot timeline real. Three summary strip items (`latency`, `idle_waste`, `vpa_recommendation`) always render `—` because no backend populates these fields.

### Node Selector and Workload Migration Pages
Node Selector is a complete placeholder — mock data, no routing to a backend, no known backend implementation plan in any service file. Workload Migration similarly has no backend service, no data model, no Celery task. Both are UI wireframes awaiting backend implementation. They are not "abandoned" — they exist intentionally as forward-planning scaffolding — but they deliver no real value in the current running system.

---

## C.19 Decision Explainability and Audit Logging

### Decision Logs
`PlacementController` emits per-workload decision logs via `_emit_decision_log()`. Each log entry includes `DecisionAction` (SKIP/EVICT/DEFER/REBALANCE) and `DecisionReason` (AT_TARGET, COOLDOWN_ACTIVE, ROLLOUT_BLOCKED, etc.) and is appended to the Redis list `spot:pc:workload_log:{cluster_id}:{workload_id}` (accessible via the placement detail API endpoint). The last 10 entries per workload are returned by `/optimize/workloads/{id}/placement-detail`. This is the closest the system comes to "why did the engine take this action" — it is queryable per workload but not searchable across workloads or time-ranges from the UI.

### Audit Log Completeness and Immutability
`AuditService.create_audit_log()` records user-initiated events (cluster create/update, policy changes, approval decisions) with a SHA256 checksum (`hashlib`) over the event fields for tamper-evidence. The checksum prevents easy record modification but is not cryptographically signed — a DB admin with write access could recompute the hash after modifying a record. Automated system actions (AgentAction evictions, auto-rebalancer node drains, PC evictions) are NOT automatically fed through `AuditService`. They are tracked in `AgentAction` and `RebalancingAction` tables which have no tamper-evidence checksum. Audit coverage is therefore comprehensive for user actions and absent for autonomous system actions.

---

## C.20 Observability and Alerting

### Observability Stack
`observability_logger.py` provides structured JSON logging targeting DataDog and CloudWatch. There is no Prometheus metrics endpoint (`/metrics`) in the FastAPI app. No Grafana deployment. No self-hosted alerting stack. `notification_service.py` supports Slack and Email notifications via SendGrid/AWS SES. No Datadog agent container is in docker-compose. In practice, the current observability is: application logs (stdout/Docker logs), Redis metrics hashes (TTL 3600s), and DB record state. There are no dashboards.

### Alerts for Critical Failures
`notification_service.py` is implemented and can send Slack/Email. However, no hardwired alert triggers are connected to: agent heartbeat loss, high retry rate in `agent_actions`, circuit breaker state transitions, or drift spike events. Alert emission requires explicit calls to `NotificationService.send_*` which are not present in `circuit_breaker.py`, `placement_controller_service.py`, or `health.py` (stale agent reset). The notification infrastructure exists but is not wired to operational triggers.

---

## C.21 SLA, Data Retention, and DB Health

### SLA Definition and Adherence
No SLA document exists in the codebase. No SLO metrics (availability %, latency P99, etc.) are defined or measured. No SLI recording rules exist. The reliability score (8.5/10) in `§AF` is an engineering self-assessment, not a contractual or measured commitment.

### Data Retention Policy
- `pod_metrics` table: 7 days (`cleanup_old_pod_metrics(retention_days=7)` in `pod_metrics_cleanup.py`, runs daily at 2 AM UTC via `pod-metrics-cleanup-daily` beat entry).
- `hpa_status_snapshots`: extended by the same cleanup task (added in T-13).
- AWS Cost Explorer data: 90 days (`cost-explorer-cleanup-weekly`).
- `AgentAction` records: no retention policy. They accumulate indefinitely. COMPLETED and FAILED records are never pruned.
- `RebalancingAction` records: no retention policy. Indefinite accumulation.
- `audit_logs` records: no retention policy.

### pod_metrics Table Bounded Growth
The daily cleanup task (`cleanup_old_pod_metrics`) ensures `pod_metrics` rows older than 7 days are deleted. With 4 nodes and ~20-second collection cadence, daily volume per cluster is roughly `4 nodes × (86400/20) × avg pods per node`. For a 100-pod cluster, this is approximately 432,000 rows/day, which the daily cleanup keeps bounded. Growth rate scales linearly with cluster size and pod count.

### DB Slow Queries and Index Coverage
No `pg_stat_statements` or slow query log is configured in the docker-compose Postgres service. High-frequency queries that lack verified indexes include: `AgentAction` filtered by `cluster_id + status` (critical for CLUSTER_BATCH_SIZE gate), `pod_metrics` filtered by `cluster_id + node_name + timestamp` (critical for bin-packing detail), and `WorkloadClassificationRecord` filtered by `cluster_id`. Migration files `009–013` add columns but no explicit index creation was found in the reviewed migrations. The `pod_metric.py` model shows `phase` is indexed (noted in `§AE` modified files table) but cross-column composite indexes for the hot query patterns are not confirmed.

---

## C.22 Scalability and Backpressure

### Horizontal Scalability Limit
The current architecture has a hard scalability ceiling at the single-process boundaries: one Celery worker with `--concurrency=4`, one APScheduler running in the FastAPI uvicorn thread (10 in-process jobs), one Redis instance, one Postgres instance. The bottleneck order at 10x cluster scale: (1) APScheduler in-process jobs — `job_wie_fast_loop` and `job_scan_clusters` iterate over all clusters serially with random jitter; at 30+ clusters these loops take longer than their 2–10 minute schedules; (2) Celery concurrency=4 — tasks queue behind 4 worker slots; high-priority emergency tasks may wait behind pricing tasks in the shared `celery` queue; (3) Redis single node — no eviction policy means memory fills under high load; (4) Postgres — unbounded `agent_actions` and `rebalancing_actions` tables with growing scan costs on status queries.

### Backpressure and Rate Limiting
No explicit backpressure signal exists. Celery queues absorb unlimited tasks. `RedisCacheManager` implements an atomic rate limiter (Lua script) but it is not applied to agent data ingestion endpoints (`POST /metrics/batch`, `POST /node-metadata/batch`). An agent sending metrics at 1-second intervals instead of 20-second intervals would not be throttled. There is no circuit breaker on the ingestion path that would shed load.

---

## C.23 Shadow Mode, Manual Ops, and Known Risks

### Shadow Mode Governance
PlacementController shadow mode is controlled by the Redis key `spot:placement_controller:shadow_mode:{cluster_id}` (key template defined in `placement_controller_service.py`). If the key exists, all cycles are metrics-only (no `AgentAction` writes). If the key is absent, the controller is in live mode. Setting/deleting this key requires direct Redis access — there is no API endpoint or UI control. Shadow-to-live graduation is manual: `redis-cli DEL spot:placement_controller:shadow_mode:{cluster_id}`. No graduation metrics (e.g., shadow cycle count, false-positive rate) gate the promotion.

### Manual Operations Required for System Functioning
The following operational steps require human intervention today:
1. **Tunnel URL rotation** — when the Cloudflare tunnel expires, `update-tunnel.sh` must be run manually (or with `--new-tunnel` flag).
2. **Agent initial install** — partially automated with the `update-tunnel.sh` self-install fix from this session, but still requires the script to be invoked.
3. **Shadow → Live graduation** — requires direct Redis key deletion.
4. **DB schema migrations** — `alembic upgrade head` must be run manually on each deployment.
5. **Circuit breaker recovery** — if a cluster is stuck in HALT and the rollback count window hasn't cleared naturally, a manual Redis key delete (`DEL cb:state:{cluster_id}`) is required.
6. **Demo data seeding** — `python scripts/seed_demo_data.py` (or `--refresh`) must be run manually to populate demo clusters.
7. **Karpenter install** — via UI "Activate Optimization" flow or manual Helm command.

### Top Known Failure Modes Not Yet Solved
1. **Redis no eviction policy**: with `noeviction`, any Redis OOM event causes all lock acquisitions and metric writes to fail simultaneously, crashing placement controller cycles, auto-rebalancer, and WIE simultaneously. No monitoring, no alert.
2. **ExecutionController stubs silently succeed**: if any code path calls `execute_replacement()` directly (possible via future changes), it will return success without performing real K8s operations.
3. **No alert on agent heartbeat loss**: a cluster can be offline for up to 5 minutes before DB state reflects it. No Slack/email fires.
4. **Celery emergency queue not isolated**: emergency tasks share the default `celery` queue with pricing, cost, and discovery tasks. A backlog of pricing tasks can delay emergency rebalancing.
5. **Audit gap for autonomous actions**: evictions, drains, and terminations by the agent are not recorded through `AuditService`. Only user-initiated events have tamper-evident audit records.

### Biggest Architectural Risk
The single Redis node with no eviction policy and no persistence replication. Redis is the locking backbone of the entire system: all cross-engine mutexes, workload cooldowns, placement policy caches, circuit breaker state, and WIE classification cache live here. An OOM event or Redis crash while the platform is managing active Spot replacements would simultaneously release all locks, invalidate all cached policies, and corrupt in-flight action state. Recovery requires manual cache warm-up and risk of double-eviction or duplicate action dispatch.

### Biggest Scalability Bottleneck
APScheduler running 10 in-process jobs inside the FastAPI uvicorn process. `job_wie_fast_loop` and `job_scan_clusters` iterate serially over all clusters with a short jitter. At current scale (3 clusters) this is fine. At 20+ clusters, these jobs will routinely overlap their schedule intervals. The fix requires moving all scheduled work to Celery beat tasks (as the newer tasks like `workload_cv_task`, `hpa_recommendation_task`, `consolidation_analysis_task` already do), but the older APScheduler jobs (WIE fast/slow loop, karpenter metrics collection, placement advisor cycle) are still in-process.

### Biggest Correctness Risk
The unauthenticated `POST /agents/spot-interruption` and `POST /agents/rebalance-recommendation` endpoints. An adversarial or misconfigured caller can inject fake spot interruption events for any cluster, triggering emergency rebalancing (cordon, drain, terminate) on healthy nodes. The `EmergencyEventProcessor` deduplicates by `instance_id` with a 300s TTL, but a fresh `instance_id` per call bypasses deduplication entirely. The consequence is uncontrolled node eviction triggered by an unauthenticated HTTP POST.

### Biggest Cost Leak
Workload savings estimates (`placement_policies.estimated_monthly_saving_usd`) are never validated against actual AWS Cost Explorer data. The savings calculator (`workers.savings.calculate_real_savings`, every 30 min) computes realized savings from OD→Spot conversions using `aws_pricing_service.py` prices but does not reconcile against the placement advisor's forward estimates. If the advisor's price data is stale or the spot price assumptions are off, the savings figures shown in the UI may significantly overstate actual savings without any alert. There is no nightly or weekly reconciliation job that compares estimated vs actual spend delta.

---

## C.24 WIE Fast Loop vs Slow Loop

### Fast Loop Mechanics (Every 2 Minutes)
`job_wie_fast_loop()` in `scheduler.py` runs every 2 minutes. It calls `engine.fast_loop_update(cluster_id)`. The fast loop's sole job is to refresh the per-workload pod state cache in Redis (`spot:wie:pod_state:{cluster_id}:{ns}/{ctrl}`). It captures: restart counts, ready replica count, zone distribution, and recent pod-level events. It does NOT recompute classification scores or write to the `workload_classifications` DB table. It exists purely so that the slow loop operates on fresh data even though the slow loop runs less frequently.

### Slow Loop Mechanics (Every 10 Minutes)
`job_scan_clusters()` in `scheduler.py` runs every 10 minutes. It calls `engine.slow_loop_classify(cluster_id)`. The slow loop reads the pod state cache from Redis (populated by the fast loop), runs all 15 scoring functions (`compute_criticality`, `compute_spot_score`, `compute_confidence`, etc.), applies `enforce_confidence()` for cold start gating, and — if `should_write()` returns True — upserts the result into the `workload_classifications` DB table. The split exists to avoid heavy DB writes every 2 minutes while still keeping classification state responsive to recent cluster changes.

### WIE DB Write Suppression via Input Hashing
Every classification output includes an `input_hash` (SHA256 of slow-changing workload fields: `controller_kind`, `namespace`, `has_pdb`, `has_pvc`, `priority_class_value`, etc.). The `should_write()` function compares the new hash against the previous classification's hash. If they match AND no meaningful score delta occurred, the DB write is suppressed. The metrics hash `spot:wie:metrics:{cluster_id}` tracks `db_writes` vs `db_suppressed` per cycle. On stable clusters, suppression rates can exceed 90% — preventing unnecessary DB churn for unchanged workloads.

### WIE Debounce and Rate Limiting
The `EventDebouncer` class prevents burst recomputation. Each workload has a per-workload Redis key `spot:wie:debounce:{cluster_id}:{workload_id}` with a cluster-size-aware TTL (15s for >20 nodes, shorter for smaller clusters). If a second recompute request arrives within the debounce window, it is dropped. The `RateLimiter` class enforces `MAX_RECOMPUTE_TASKS_PER_CLUSTER_PER_MINUTE = 60` (a per-minute cap per cluster). Both `debounce_drops` and `rate_limit_drops` are tracked in the metrics hash per cycle.

### WIE Circuit Breaker
`EngineCircuitBreaker` in `workload_identification_engine.py` monitors the WIE error rate within a slow loop cycle. If the error rate exceeds `TRIP_THRESHOLD_PCT` within the cycle window, it sets `spot:wie:circuit_breaker:{cluster_id}` with a `TRIP_TTL_SECONDS` TTL. All subsequent slow loop calls for that cluster skip classification until the key expires naturally. This prevents a broken Kubernetes API (e.g., Metrics Server outage) from flooding logs with repeated failures.

### WIE Cold Start Protection
`COLD_START_HOURS = 24` in `workload_identification_engine.py`. `enforce_confidence()` checks `cluster_engine_age_hours` against this threshold. Even if a workload's raw confidence score is ≥8 (CONFIRMED), if the cluster WIE engine has been running for less than 24 hours, the state is capped at PROVISIONAL. The engine age is tracked in Redis key `spot:wie:engine_age:{cluster_id}`. This prevents the automation from acting on insufficiently observed workloads on new or recently reset clusters.

### WIE Priority Class and System Namespace Handling
WIE explicitly excludes system workloads from automation. Namespaces in `DEFAULT_SYSTEM_NAMESPACES` (`kube-system`, `karpenter`, `cert-manager`, `istio-system`, `linkerd`, etc.) are given `role=SYSTEM` and `criticality=10`. Priority classes `system-node-critical` and `system-cluster-critical` also force `role=SYSTEM`. These workloads get `spot_friendly=False` and `confidence_state=CONFIRMED` for exclusion (not for action). Control plane components (`kube-controller-manager`, `kube-scheduler`, `etcd`) are separately identified as `role=CONTROL_PLANE`.

---

## C.25 Emergency Rebalancer

### Emergency Rebalancer Trigger Path
`emergency_rebalancer` is a Celery task (`queue="emergency"`) registered in `workers/tasks/emergency_rebalancer.py`. It is triggered by `POST /agents/spot-interruption` which processes AWS Spot interruption notices (2-minute warnings from the EC2 Instance Metadata Service or SQS/EventBridge). The handler immediately dispatches `emergency_rebalancer.apply_async(...)`. It runs `_execute_karpenter_emergency()` — direct EC2 terminate + NodeClaim cleanup — bypassing all normal queues and batch limits. `EMERGENCY_COOLDOWN_MINUTES` prevents the same instance from triggering multiple emergency cycles (deduplication by `instance_id`).

### Emergency vs Normal Rebalancer Difference
The emergency rebalancer skips: circuit breaker state check, cluster batch limit, workload cooldown, PDB checks, scaling guards, and the normal 15-second AR polling cycle. It is the only code path that directly calls EC2 terminate without an intermediate `AgentAction` PENDING/PICKED_UP cycle. The trade-off: speed over safety. This path has `max_retries=1` meaning if the Celery task fails, it retries once and gives up. There is no fallback to normal AR if emergency rebalancer fails — the 2-minute interruption window is simply lost.

---

## C.26 Health Scoring

### Cluster Health Score Computation
`health_monitor.py` (`run_health_monitor` task, every 5 min) computes a composite health score for each active cluster and stores it at `cluster_health:{cluster_id}` in Redis (TTL 600s). The score is computed by `_compute_cluster_health()` from: `RebalancingAction` success/failure ratios, recent `AgentAction` FAILED count, active `spot:ondemand_fallback` key presence, pending pods count, and circuit breaker state. The result is an A/B/C/D grade plus a numeric score used by the `health_routes.py` endpoint. A separate `run_drift_detector` task (every 15 min) computes placement drift signals for the same health view.

---

## C.27 Dry Run Mechanism

### How Dry Run Works
`dry_run_refresher.py` maintains a `verified_pools` Redis ZSET per cluster (`spot:verified_pools:{cluster_id}`). The refresher (`maintain_all_verified_pool_sets`, every 5 min via beat) runs capacity checks against the top Spot pool candidates without creating real `AgentAction` records. The `run_dry_run_checks` task validates pool viability (CPU/memory/ENI headroom) and marks pools as verified or rejected. The `_VERIFIED_SET_TTL = 3600s`. The PC capacity check path queries this ZSET to fast-path pool selection without re-running full capacity math. The dry run is effectively a pre-validated pool whitelist cache.

---

## C.28 Resize Guard

### Rightsizing Rollback and Stability Window
`resize_guard_worker.py` runs `resize_guard_worker` task every 5 minutes. After a `RightsizingProposal` is applied (via `AgentAction(PATCH_CONTAINER_RESOURCES)`), the guard monitors the target workload for 2 hours for: CPU stress (`cpu_usage > cpu_request × 0.95`), restart spike (above `pod_restart_baseline`), and memory pressure. If any signal triggers, it writes to `resize:rollback_needed:{cluster_id}` Redis key. The `resize_rollback_consumer` task picks this up and dispatches a rollback `AgentAction` to revert the container resources to the previous values. The `update_pod_restart_baseline` task (hourly) maintains the 24-hour rolling restart average that the guard compares against.

---

## C.29 Feature Flags

### Feature Flag Governance
Feature flags are a mix of environment variables and DB columns:
- `FEATURE_PLACEMENT_CONTROLLER_ENABLED` — env var checked in `dispatch_placement_controller_cycles()`. Must be set at container start. No runtime toggle.
- `FEATURE_PLACEMENT_ADVISOR_ENABLED` — env var checked in `job_run_placement_cycle()`. Same: container restart required to change.
- `cluster.auto_rebalance_enabled` — DB column on `ClusterOptimizationSettings`. Toggle-able at runtime via UI.
- `cluster.auto_rightsizing_enabled` — DB column. Toggle-able at runtime via UI.
- `cluster.enable_ascp_auto_scaler` — DB column. Checked by `auto_scaler.py`.
- Shadow mode — Redis key `spot:placement_controller:shadow_mode:{cluster_id}`. Toggle-able via direct Redis access only.

There is no feature flag management dashboard or audit trail for flag changes. Environment variable flags require container restart to take effect.

---

## C.30 Approval Workflow

### High-Risk Action Approval Gate
`ApprovalService` (`approval_service.py`) and `approval_routes.py` implement an approval gate for high-risk administrative actions (e.g., bulk node termination, governance policy changes). When an action is flagged as `requires_approval=True`, an `ApprovalRequest` record is created with `status=PENDING` and an email/Slack notification is sent via `notification_service.py`. The requesting operation is held until an admin approves or rejects via `POST /api/v1/approvals/{id}/approve`. `approval_cleanup.py` (`approval-cleanup-every-15-mins` beat task) expires stale requests after a configurable timeout. Auto-rebalancer evictions and placement controller evictions do NOT go through this approval gate — they act autonomously.

---

## C.31 JWT Token Lifecycle

### JWT Authentication Flow
`auth_routes.py` handles `POST /api/v1/auth/login`. On success, it returns a JWT signed with `JWT_SECRET_KEY` (from env). Token claims include `user_id`, `email`, `role`, `exp` (expiration). The `get_current_user` FastAPI dependency decodes and validates the token on every protected request. There is no refresh token mechanism in the codebase — when a JWT expires, the user must re-login. Token expiry is configured via `ACCESS_TOKEN_EXPIRE_MINUTES` in `config.py`. No token revocation list (blacklist) exists — a stolen JWT is valid until expiry.

---

## C.32 Cluster Discovery

### Automatic EKS Cluster Discovery
`discovery.py` (`workers.discovery.scan_aws_clusters`, `auto-discovery-every-5-mins` beat task) polls AWS for new EKS clusters in the configured region using the `eks.list_clusters()` API. Newly discovered clusters are upserted into the `clusters` DB table with `status=DISCOVERED` and `agent_installed='N'`. No automatic Helm install happens at discovery time — the cluster waits for the user to trigger onboarding or for `update-tunnel.sh` to run. The discovery worker is what drives the "Your new cluster appears in the dashboard" experience without manual cluster registration.

---

## C.33 Warm Spare Standby

### Warm Standby Mechanics
`maintain_warm_spare_worker.py` (`workers.maintain_warm_spare`, schedule every 5 min) monitors clusters where `maintain_warm_standby=True` (set via UI toggle in Optimization Settings). When enabled, it ensures at least one empty or lightly-loaded Spot node exists as a "spare". It does this by checking current allocatable capacity headroom and, if below threshold, dispatching a `ScaleNodePool` action to provision one extra node. This reduces pod scheduling latency from ~3 minutes (Karpenter provisioning) to ~0 for the first pod to land after a Spot interruption.

---

## C.34 KEDA Integration

### KEDA ScaledObject Monitoring
`keda_installer.py` (`keda-installer-every-5-mins` beat task) monitors KEDA `ScaledObject` and `TriggerAuthentication` resources in customer clusters. It tracks rollout state and reports back to the DB whether KEDA is installed and which workloads have KEDA-managed HPA. The placement controller reads KEDA event timestamps from `spot:keda:last_scale_event:{cluster_id}` (written by the agent's `pod_metrics_collector.py` which watches for KEDA-driven replica changes) to implement the `SCALING_GUARD_WINDOW_SECONDS=120` inhibit window. This prevents PC from evicting pods immediately after KEDA scales a workload up, which would cause the freshly added replicas to be immediately evicted.

---

## C.35 NodePool Reconciliation

### NodePool Class Reconciler
`job_reconcile_nodepool_classes()` runs every 10 minutes (APScheduler). It calls `reconcile_nodepool_classes_task` which compares `node_pool_configs` DB records against actual Karpenter NodePool CRD definitions in the cluster. If a NodePool definition drifts from DB (e.g., instance types changed, capacity type patched manually), it re-applies the DB definition via `PATCH_NODE_POOL` `AgentAction`. The `ascpai_worker.py` (`workers.ascpai.sync_pools`, `pool-sync-every-10-mins` beat task) additionally syncs ML-ranked instance type lists directly into Karpenter NodePool YAML, ensuring pool diversity reflects the latest `pool_rankings` table.

---

## C.36 Consolidation Analysis

### Consolidation Candidate Computation
`consolidation_analysis_task.py` (`workers.consolidation_analysis.run_consolidation_analysis`, every 10 min via beat) identifies nodes that are candidates for bin-packing consolidation. For clusters with Karpenter (`karpenter_installed=True`), it computes consolidatable nodes using `NodeMetadata.cpu_allocatable` vs `PodMetric.cpu_request_millicores` sum per node. For non-Karpenter clusters, it checks `standard_consolidation_candidates`. Results are written to Redis list `spot:consolidation_candidates:{cluster_id}` (TTL 600s). The `/api/v1/optimize/nodes/bin-packing` endpoint reads this key to populate the "Consolidation Candidates" section of the Node Bin Packing UI.

---

## C.37 Right-Sizing Proposal Lifecycle

### Proposal Creation to Execution
`optimizer_coordinator_worker.py` (`workers.optimizer_coordinator.run_all_clusters`, every 15 min via beat) is Engine C. For each cluster with `auto_rightsizing_enabled=True`, it: (1) computes CPU P90 and memory P90 from recent `pod_metrics`, (2) compares against current container requests, (3) if delta exceeds threshold, creates a `RightsizingProposal` record with `status=PENDING` and `target_requests`, `target_limits` computed values. If `auto_rightsizing_enabled=True`, the proposal is immediately auto-approved (status set to `APPROVED`). If `False`, it stays PENDING until a user approves via the UI `RightSizingRecommendationsTable`. An approved proposal generates `AgentAction(type=PATCH_CONTAINER_RESOURCES)`. The resize guard then monitors the workload post-apply for 2 hours.

---

## C.38 APScheduler vs Celery Beat Coexistence

### Why Both Schedulers Exist
The system runs two parallel scheduling systems: APScheduler (in-process, 10 jobs in the FastAPI uvicorn thread) and Celery beat (separate container, 42+ tasks). This is an architectural evolution artifact. Original infrastructure used APScheduler exclusively. As the system grew, Celery beat was introduced for horizontal scalability and task isolation. Newer tasks (T-16, T-18, WIE cv_task, HPA recommendation) are registered as Celery beat tasks. Older core jobs (WIE fast/slow loop, scan clusters, placement cycle, karpenter metrics, NodePool reconciler) still live in APScheduler. The risk: APScheduler runs inside the same process as the API. If the uvicorn process crashes, all 10 APScheduler jobs stop. The Celery beat container keeps running independently.

---

## C.39 Scheduler Job Full Reference

### APScheduler Jobs (in-process, `scheduler.py`)
| Job | Interval | Function |
|-----|----------|----------|
| `refresh_active_count` | 5 min | Updates active cluster count cache |
| `reconcile_substitutes` | 5 min | Cleans up pre-Karpenter stuck substitute EC2 instances |
| `scan_clusters` | 10 min | WIE slow loop — full classification cycle |
| `check_cost_drift` | 30 min | Checks whether node costs have drifted from last optimization |
| `detect_volatility` | 1 hour | Detects pricing volatility regimes across pools |
| `cleanup_blacklist` | Daily 2 AM | Redis key cleanup for blacklisted pools |
| `wie_fast_loop` | 2 min | Updates pod state cache (restarts, ready count, AZ distribution) |
| `karpenter_metrics_collection` | 2 min | Fetches Karpenter provisioning latency/success from Prometheus |
| `run_placement_cycle` | 10 min | Triggers placement advisor Celery task per cluster |
| `reconcile_nodepool_classes` | 10 min | Ensures Karpenter NodePool CRDs match DB configurations |

### Celery Beat Schedule Summary (Selected Key Tasks, `workers/app.py`)
| Task Name | Schedule | Purpose |
|-----------|----------|---------|
| `auto-rebalancer-every-15-secs` | 15s | Engine A: node-level Spot replacement loop |
| `control-plane-all-clusters-every-5-mins` | 5 min | Control plane loop: 8-step macro health cycle |
| `placement-controller-every-5-mins` | 5 min | Engine B: pod placement drift correction |
| `pool-rotation-check-every-5-mins` | 5 min | NodePool rotation for capacity diversity |
| `hpa-recommendation-every-30-mins` | 30 min | P95×1.2 HPA replica recommendation per workload |
| `consolidation-analysis-every-10-mins` | 10 min | Bin-packing consolidation candidate analysis |
| `pod-metrics-cleanup-daily` | Daily | Prune `pod_metrics` older than 7 days |
| `cost-explorer-sync-daily` | Daily | Fetch AWS Cost Explorer billing data |
| `adaptive-itn-decay-hourly` | 1 hour | Decay interruption risk EMA scores |
| `zombie-cleanup-every-2-mins` | 2 min | Detect and clean zombie EC2 nodes |

---

## C.40 Data Flow: Metrics Collection to PlacementController Action

### End-to-End Latency Budget
The full pipeline from Kubernetes state change to PlacementController acting has these latency components:
1. **K8s state change → agent collector** — ~20 seconds (agent poll interval)
2. **Agent → backend `POST /metrics/batch`** — near-instant (<1s)
3. **backend → PostgreSQL write** — near-instant (<100ms per batch)
4. **WIE fast loop refresh** — up to 2 minutes (next scheduled run)
5. **WIE slow loop classification** — up to 10 minutes (next scheduled run)
6. **Placement Advisor cycle** — up to 10 minutes after WIE write
7. **PlacementController cycle** — up to 5 minutes after policy is ready
8. **Agent pickup of `AgentAction`** — up to 15 seconds (AR polling frequency)
9. **Agent executes eviction** — near-instant (~1s for pod eviction API call)

**Worst-case latency from node provisioning to first placement action: ~27 minutes** (WIE cold start excluded). After the first cycle, subsequent drift corrections happen within 5 minutes (PC cycle).

---

## C.41 Known Open Issues and Technical Debt

### Confirmed Open Issues From Code
1. **`workload_savings_usd` always $0 in Workload Profiling UI**: `optimize_routes.py` `_get_profiling_workload_rows()` returns `saving_usd=0.0` hardcoded. Backend does not join `placement_policies.estimated_monthly_saving_usd` to the workload list query.
2. **Node Selector page 100% mock**: `NodeSelector.jsx` uses `const nodes = [...mockData]` with no API call. Backend endpoint does not exist.
3. **Workload Migration page 100% mock**: `WorkloadMigration.jsx` is a UI prototype. No backend.
4. **RPS timeseries absent**: `WorkloadProfiling.jsx` placeholder `rpsData = []` — no backend endpoint for request-per-second data.
5. **HPA summary strip always `—`**: `latency_p99`, `idle_waste_pct`, `vpa_recommendation` fields always null from backend; no task populates them.
6. **ASG jobs run unconditionally**: `job_reconcile_substitutes` and `job_check_cost_drift` run for all clusters regardless of `karpenter_only_mode` flag.
7. **`agent_actions` and `rebalancing_actions` have no retention policy**: These tables grow indefinitely.
8. **No composite DB indexes on hot query paths**: `(cluster_id, status)` on `agent_actions` and `(cluster_id, node_name, timestamp)` on `pod_metrics` lack confirmed composite indexes.
9. **Shadow mode has no UI toggle**: Requires direct Redis access. Not accessible to end users.
10. **Circuit breaker stuck in HALT**: If rollback counter is somehow never decremented below threshold, the cluster stays in HALT permanently with no automatic reset mechanism independent of rollback count decay.

---

## C.42 AgentAction State Transition Rates

### COMPLETED vs FAILED — What the Code Can Tell Us
`AgentAction.status` transitions from `PENDING → PICKED_UP → COMPLETED or FAILED`. The `completed_at` timestamp is set in `agent_routes.py` `submit_action_result()`: `action.completed_at = datetime.utcnow()` on both success and failure paths. `action.error_message` is populated on FAILED. This means the data to compute COMPLETED vs FAILED ratios exists in the DB — the query is `SELECT status, COUNT(*) FROM agent_actions GROUP BY status` — but no scheduled job runs this query or surfaces it. The actual current ratio is unknown without a live DB query. Architecturally, from the retry design: any EVICT_POD action can appear COMPLETED in DB but then be overridden back to retry by `handle_eviction_result()` if the pod landed on OD, so raw COMPLETED count overstates true success.

### Stale PICKED_UP Actions
The `GET /agents/actions/pending` endpoint includes a stale PICKED_UP reset: actions that remain `PICKED_UP` without an agent result report are reset to `PENDING` with a log message `"Resetting stale PICKED_UP action... to PENDING — agent likely crashed"`. This reset TTL is implicit (based on `picked_up_at` age check in the polling handler). No counter tracks how often this fires. The `reconciliation_worker` also detects stuck PICKED_UP actions independently every 5 minutes. Percentage of actions stuck in PICKED_UP is not aggregated — it is a reactive reset, not a monitored metric.

---

## C.43 Execution Latency by Action Type

### Architectural Latency Estimates (No Measurement Exists)
`AgentAction` has both `created_at` and `completed_at` fields, so per-action latency is computable via `completed_at - created_at`. No task or scheduled job computes this. From the agent and K8s behavior, expected latencies by type are:

| Action Type | Estimated Latency | Bottleneck |
|-------------|------------------|-----------|
| `EVICT_POD` | 1–5 seconds | K8s eviction API + pod termination grace period |
| `CORDON_NODE` | <1 second | K8s node taint patch |
| `DRAIN_NODE` | 30–120 seconds | Pod graceful termination (default grace 30s × multiple pods) |
| `TERMINATE_NODE` | 5–15 seconds | AWS EC2 terminate API call |
| `PATCH_CONTAINER_RESOURCES` | 1–3 seconds | K8s deployment patch |
| `PATCH_NODE_POOL` | 2–5 seconds | K8s CRD patch for Karpenter NodePool |

A full node replacement (CORDON → DRAIN → TERMINATE sequence) takes **60–150 seconds** under normal conditions, bounded at `MIGRATION_TIMEOUT_MINUTES=20` for stateful rollouts. These are architectural estimates, not measured P50/P95 values.

---

## C.44 Node Replacement Cycle Duration

### CREATED to DONE — Full Lifecycle
A complete node replacement cycle for auto_rebalancer Engine A follows: `RebalancingAction CREATED` → `CORDON_NODE AgentAction PENDING` → agent picks up in 0–15s → CORDON executes (<1s) → `DRAIN_NODE AgentAction PENDING` → agent picks up in 0–15s → DRAIN executes (30–120s, waiting for all pods to terminate) → `TERMINATE_NODE AgentAction PENDING` → agent picks up in 0–15s → TERMINATE executes (5–15s). Total wall-clock: **1–3 minutes** for healthy clusters. The zero-downtime step ordering is enforced: `agent_routes.py` checks that step N-1 is `COMPLETED` before releasing step N to the agent. A stuck or failed intermediate step blocks the entire chain.

---

## C.45 Queue Depth and PENDING Backlog

### Whether Queue Buildup Is Observable
The PENDING backlog is the count of `AgentAction` records with `status=PENDING` in the DB. No scheduled job monitors this count over time. No Redis queue is involved for the current flow (the dead-letter Redis queue was removed in v6). The only queue depth signal is the `CLUSTER_BATCH_SIZE=2` gate: if this gate consistently fires (`evictions_skipped_batch_limit` non-zero), it is an indirect signal of backlog. With BATCH_SIZE=2 per cluster, maximum PENDING+PICKED_UP at any time is 2 per cluster. For 3 clusters, max in-flight queue depth is 6. There is no observable "backlog growing over time" signal in the current architecture.

---

## C.46 Eviction Outcome: Spot vs On-Demand Landing

### What % of Evicted Pods Land on Spot
After each `EVICT_POD` action completes successfully, `handle_eviction_result()` checks the pod's new node's `capacity_type` in `NodeMetadata`. If `capacity_type == 'on-demand'`: `retry_incremented` counter fires and `retry_count` on `AgentAction` increments. If `capacity_type == 'spot'`: action is marked `COMPLETED` cleanly and workload cooldown is set. The per-cycle `retry_incremented` vs `evictions_attempted` ratio in the Redis metrics hash gives a proxy for OD landing rate — but only for the last cycle (TTL 3600s). Historically, this is not aggregated. The rate is expected to be higher immediately after a fresh cluster onboarding (before Karpenter has established Spot nodes) and near-zero on a healthy cluster with established Spot pools.

### Oscillation: Pod Returning to On-Demand After Eviction
Oscillation happens when: (1) pod is evicted from OD node, (2) no Spot capacity exists in the AZ, (3) K8s scheduler places the pod back onto an existing OD node or a freshly provisioned OD Karpenter node. This is the `retry_incremented` case. At `retry_count >= MAX_RETRY_COUNT=3`, the action is permanently FAILED and the workload is re-evaluated on the next 5-minute PC cycle. If Spot capacity genuinely doesn't exist, the workload oscillates across multiple PC cycles indefinitely — each cycle creating a new `AgentAction` wave that hits MAX_RETRY_COUNT. This is the "no Spot pool available" failure mode.

---

## C.47 Retry Mechanics and Effectiveness

### Average Retries Per Eviction and MAX_RETRY_COUNT Hit Rate
`retry_count` field on `agent_actions` stores the retry count per action. Average retries is computable: `SELECT AVG(retry_count) FROM agent_actions WHERE action_type='EVICT_POD'`. Hit rate at MAX_RETRY_COUNT: `SELECT COUNT(*) FROM agent_actions WHERE retry_count >= 3 AND action_type='EVICT_POD'`. Neither query runs on a schedule. The `permanent_failures` counter in the per-cluster Redis metrics hash (TTL 3600s) is the only near-real-time signal. Whether retries improve success rate is not measured — but architecturally, retries help when: the first eviction races with Karpenter provisioning (pod lands on OD before the Spot node is ready), and retry 1 or 2 catches the pod after the Spot node is registered. They do not help when there are genuinely no Spot pools available (pool exhaustion or Karpenter CB tripped).

---

## C.48 PlacementController Cycle Metrics

### Cycle Duration and Skip Frequency
No timer wraps `run_cycle()`. PC cycle duration is not measured or stored. From architecture: the cycle iterates over all actionable workloads for a cluster, doing Redis reads, DB queries, and Kubernetes-state-derived capacity checks per workload. On a cluster with 20 workloads, this is approximately 20 × (Redis GET + DB COUNT + capacity math) = ~200ms–1s per cluster. This is well within the 5-minute schedule. Skip reasons and their frequencies are all in the Redis metrics hash `spot:placement_controller:metrics:{cluster_id}` (TTL 3600s):

| Skip Counter | Meaning |
|-------------|---------|
| `evictions_skipped_batch_limit` | Cluster hit CLUSTER_BATCH_SIZE=2 cap |
| `evictions_skipped_scaling_guard` | Cluster-wide pending pods >3 or KEDA active |
| `evictions_skipped_cooldown` | Per-workload 10-min cooldown active |
| `evictions_skipped_capacity` | Spot capacity insufficient (SPOT_CAPACITY_BUFFER check) |
| `evictions_skipped_lock_contention` | Per-workload Redis lock held |
| `evictions_skipped_pdb_violation` | Eviction would violate PDB |
| `evictions_skipped_pod_too_young` | Pod age < POD_AGE_MIN_SECONDS=120 |
| `evictions_skipped_last_pod` | Would evict the last running pod |
| `evictions_skipped_active_action` | In-flight AgentAction already exists for workload |
| `evictions_skipped_node_drain` | Node being drained |

All visible per-cycle only. No historical trend.

### Actions Per Hour and Peak Concurrent Count
Actions per hour is bounded by the hard gate: `CLUSTER_BATCH_SIZE=2`, PC runs every 5 minutes with `MAX_EVICTIONS_PER_CYCLE=3` per workload per cycle. Theoretical max: `(60/5) × CLUSTER_BATCH_SIZE × workload_count` but in practice CLUSTER_BATCH_SIZE=2 is the binding constraint. For 3 clusters with ~10 actionable workloads each: max ~72 EVICT_POD actions per hour across all clusters. Peak concurrent actions per cluster is always ≤ `CLUSTER_BATCH_SIZE=2`.

---

## C.49 Failure Categorization

### Top Reasons for AgentAction FAILED
`AgentAction.error_message` captures the raw error string from the agent (`ActionResultRequest.error`). The field is unstructured — no error type enum. From the codebase, the five most likely failure causes in order:
1. **Pod landed on On-Demand after eviction** — `handle_eviction_result()` overrides COMPLETED to retry; at `retry_count=3` the action is FAILED. This is the most common failure on clusters where Spot capacity is thin.
2. **K8s eviction API returned 429 (PDB protected)** — `evictions_skipped_pdb_violation` counter; if the eviction is attempted despite PC's PDB check being stale, the agent gets a 429 back.
3. **Drain timeout** — agent waits for all pods to terminate within the drain grace period; if a pod hangs, the drain times out and DRAIN_NODE is FAILED.
4. **Node already gone** — AWS terminated the node between cordon and drain (Spot interruption race); `CORDON_NODE` succeeds but `DRAIN_NODE` finds no node to drain.
5. **Agent process crash** — `PICKED_UP` action with no result report; reset to `PENDING` by the stale action cleanup, but if max retries already hit, counted as FAILED.

### K8s API vs AWS Failure Split
The error split is not categorized. `error_message` is a free-text string. A K8s API error would contain `"ApiException"` or HTTP status codes (409, 404, 429). An AWS error would contain `"ClientError"` or `"BotoCore"`. Without a structured error type field, the only way to compute this ratio is a `LIKE` query on `error_message`. No such query is scheduled.

---

## C.50 Spot Capacity Availability

### How Often Capacity Check Fails and No Spot Pool Exists
Both tracked in the Redis metrics hash per cycle:
- `evictions_skipped_capacity`: insufficient capacity in the AZ that the capacity scorer prefers (using `SPOT_CAPACITY_BUFFER=0.7` of allocatable CPU/memory/ENI)
- `evictions_failed_due_to_no_replacement`: zero Spot nodes exist in any AZ for the cluster

On a cluster where Karpenter has not yet provisioned any Spot nodes (e.g., fresh cluster or after a full interruption wave), `evictions_failed_due_to_no_replacement` fires on every eviction attempt until Karpenter provisions a new Spot node. Once at least one Spot node is available, the `verified_pools` ZSET (from dry_run_refresher) provides a pre-validated fast-path. The Karpenter OD fallback (`spot:ondemand_fallback:{cluster_id}`, 12h TTL) is set when `switch_to_ondemand()` fires — this is the system's recognition that no safe Spot pools exist at all.

---

## C.51 Concurrency, Contention, and Mutex Behavior

### cluster_mutex: Skip-Not-Block Pattern
`spot:cluster_mutex:{cluster_id}` is a HeartbeatLock with 60s TTL. When PlacementController holds it, auto_rebalancer does a read-only `redis.get()` check and skips the cluster for the current 15-second tick. It does NOT wait — there is no blocking queue. The next AR tick (15 seconds later) checks again. If PC holds the mutex for a full 5-minute cycle, AR skips that cluster for up to 20 ticks. This is by design: prevent concurrent AR + PC mutations on the same cluster. The trade-off is AR could miss a narrow window for urgent node replacement. In practice, PC cycles are <1 second per cluster, so AR typically misses only 1 tick.

### Redis Lock Contention
`evictions_skipped_lock_contention` in the metrics hash counts per-workload Redis lock (`spot:workload_lock:{cluster_id}:{workload_id}`, TTL 30s) contention within a PC cycle. This fires when two concurrent PC cycle dispatches (theoretically possible if Celery beat dispatches faster than lock TTL) try to process the same workload simultaneously. With PC running every 5 minutes and lock TTL 30 seconds, genuine contention is extremely rare. Observed frequency: near-zero under normal operation.

### DB Contention on agent_actions Table
The `agent_actions` table is the hottest table in the system: AR reads it every 15 seconds (semaphore reconciliation), PC reads it every 5 minutes (CLUSTER_BATCH_SIZE COUNT query), agent writes it via `submit_action_result` on every action completion, and the stale PICKED_UP reset reads it on every `GET /agents/actions/pending` call. Without a composite index on `(cluster_id, status)`, all of these are sequential scans after filtering by cluster_id. With a growing unbounded table (no retention policy), scan latency grows linearly with table size. This is the most likely DB performance issue at scale.

---

## C.52 Scalability Numbers and Limits

### Max Clusters Without APScheduler Degradation
APScheduler's `job_scan_clusters` (WIE slow loop, 10-min schedule) iterates all active clusters serially. Each cluster's WIE slow loop takes ~100–500ms (Redis reads + classification math + potential DB write). At 20 clusters: 20 × 500ms = 10 seconds per run, which fits within 10 minutes. At 50 clusters: 50 × 500ms = 25 seconds, still fits. The real constraint is `job_wie_fast_loop` (2-min schedule). At 50 clusters: 50 × 200ms = 10 seconds per run, fits within 2 minutes. APScheduler's `max_instances=1` prevents overlaps. **Safe estimate: ~40–50 clusters before APScheduler jobs risk overlapping.** The actual limit also depends on Kubernetes API latency per cluster (each cluster requires a separate K8s client connection).

### Max Safe CLUSTER_BATCH_SIZE
`CLUSTER_BATCH_SIZE=2` is conservative. The COUNT gate at cycle start queries `agent_actions WHERE status IN ('PENDING','PICKED_UP') AND cluster_id=X`. Increasing to 4 doubles the concurrent evictions per cluster. This is safe if: (1) the cluster has sufficient Spot capacity headroom for 4 simultaneous pod migrations, and (2) workloads have PDBs that tolerate 4 concurrent disruptions. Without PDB checks, increasing BATCH_SIZE to 4 on a 2-replica workload would violate disruption budget. The safe maximum depends on the cluster's average `pdb_min_available` across workloads. There is no automated sizing logic — it is a static env var.

### What Breaks First at Scale
In order of failure probability:
1. **APScheduler overlapping** (first hits at ~50 clusters if WIE is slow)
2. **Celery worker concurrency=4 exhausted** — at high task frequency, emergency tasks wait behind pricing/discovery tasks
3. **Redis memory exhaustion** — `noeviction` policy means OOM crashes write path
4. **DB `agent_actions` scan latency** — unbounded table growth, no composite indexes confirmed
5. **Celery beat dispatch lag** — single beat container dispatching 42+ tasks; at high frequency, beat → broker → worker delay grows

---

## C.53 Cost Accuracy and Billing Reality

### Reported Savings vs Actual AWS Billing
`PlacementPolicyRecord.estimated_monthly_saving_usd` is computed by `placement_advisor_service.py` using `aws_pricing_service.py` spot and OD prices at policy-generation time. `workers.savings.calculate_real_savings` (every 30 min) computes realized savings from actual Spot-vs-OD node usage tracked in `NodeMetadata.capacity_type`. AWS Cost Explorer data (fetched daily via `cost-explorer-sync-daily`) contains actual billing. These three numbers live in three different tables/Redis keys with no reconciliation query. The gap between "estimated savings" and "actual billing delta" is unknown. Common sources of divergence: (a) Savings Plans covering OD instances at discounted rates that the platform doesn't know about — making OD appear cheaper than predicted; (b) Spot price volatility between advisor cycle and billing cycle; (c) overhead of Karpenter node provisioning delay (minutes of OD billing before Spot is ready).

### Savings Plans Interference
The platform has no code that checks whether an EC2 instance is covered by an AWS Savings Plan or Reserved Instance. `aws_pricing_service.py` uses on-demand list prices for OD cost estimates. If a cluster's OD instances are partially covered by Savings Plans (effectively 30–40% cheaper), the reported savings from switching to Spot are overstated by that same 30–40%. There is no API call to `DescribeSavingsPlansCoverage` or `DescribeReservedInstancesOfferings` in the codebase.

### Workloads Achieving Target Spot Ratio and Oscillation
Whether a workload "meets `ondemand_target` exactly" is detectable per PC cycle (drift=0 means target met), but not stored historically. Oscillation (OD ↔ Spot flipping) is indirectly visible via the `retry_incremented` pattern: a workload that gets evicted, lands OD, gets retried, lands Spot, then gets interrupted and lands OD again generates `retry_incremented` repeatedly in successive cycles. No oscillation counter exists. A workload stuck in oscillation will continuously generate `AgentAction` waves without ever settling, which is visible only by querying `agent_actions` for repeated EVICT_POD records for the same workload.

---

## C.54 WIE Classification Accuracy

### How Accurate WIE Classification Is vs Real Workload Behavior
WIE classifies based on structural K8s signals: `controller_kind`, `has_pdb`, `topology_spread_constraints`, `priority_class`, `has_pvc`, `restart_rate`, `ready_replicas`. It does NOT use actual runtime performance (latency, error rate, business impact). A Deployment with `replicas=2`, `topologySpreadConstraints`, and no PVC would score spot-friendly. If that Deployment is actually latency-sensitive and degrades under any disruption, WIE would still classify it as spot-friendly. There is no feedback loop comparing WIE classification outcomes to real workload health degradation post-eviction. The `adaptive_itn_service.py` tracks pool-level interruption risk (not workload-level). This is a structural gap in the classification accuracy model.

### Workloads Incorrectly Marked Spot-Friendly
Not tracked. WIE `is_spot_friendly()` requires `spot_score >= 4 AND has_resilience_signal`. The `has_resilience_signal` check requires at least one of: topology spread constraints, multiple replicas, `karpenter.sh/do-not-disrupt` annotation, or `disruption_safe=True` signal. A workload with `replicas=3` but no actual disruption tolerance (no graceful shutdown, sticky sessions, long init containers) would pass this check. Since no post-eviction workload health metrics are collected, false positives in spot-friendly classification accumulate silently.

### Cost Drift Between Expected and Actual
Expected cost per workload = `ondemand_target × od_price + (replicas - ondemand_target) × spot_price`. Actual cost = what AWS bills. The drift sources are identical to the savings gap issue in C.53. Not monitored. No reconciliation job.

---

## C.55 User Behavior and UI Trust

### Feature Usage Tracking
There is no analytics or event tracking in the frontend. No `analytics.track()` calls in any React component. No backend endpoint records which pages users visit, which buttons they click, or whether they accept/reject optimization recommendations. Whether users are actively using the Node Bin Packing, Workload Profiling, or Workload Scaling pages — or ignoring them — is completely unknown.

### Automation Toggle Frequency
`PUT /api/v1/clusters/{id}/optimization-settings` is called when `auto_rebalance_enabled` or `auto_rightsizing_enabled` is toggled. No audit log entry is created for this change (it is not routed through `AuditService`). The DB record `ClusterOptimizationSettings.updated_at` tracks when it last changed but not the history of values. Whether users frequently flip automation on and off is not observable without DB diff queries.

### User Trust in FULL AUTO Mode
No data. The UI provides the "FULL AUTO" mode badge when both toggles are on, but whether users leave it in FULL AUTO or revert to manual is only inferable from the current DB state. The platform has no "override" action type — users who distrust automation simply turn off the toggles, not override individual decisions. The approval workflow (`ApprovalService`) exists for high-risk actions but auto-rebalancer and PC evictions bypass it entirely, meaning users who want control must disable automation globally rather than selectively.

### Placement Advisor Recommendations: Acted Upon or Ignored
`PlacementPolicyRecord` records are created by the advisor. PlacementController automatically acts on them every 5 minutes — there is no "accept recommendation" step for end users in the automation path. Users can only influence this by: (a) turning off `auto_rebalance_enabled`, (b) enabling shadow mode (Redis key), or (c) adjusting placement policy via `placement_policy_routes.py`. Whether users are actively managing their policies or just using defaults is not tracked.

### Misleading or Effectively Unused Dashboard Metrics
From code audit, metrics that display but carry no real information:
1. **Workload Profiling `saving_usd` column** — always `$0.00` due to hardcoded `saving_usd=0.0` in backend
2. **Workload Scaling `latency_p99`, `idle_waste_pct`, `vpa_recommendation`** — always `—` (null from backend, no task populates these fields)
3. **Workload Profiling RPS chart** — always empty (`rpsData = []` in JSX, no backend endpoint)
4. **Node Selector page** — 100% mock; all node data is hardcoded static arrays
5. **Workload Migration page** — 100% mock; all migration candidate data is hardcoded
6. **Karpenter provisioning P50/P95 latency** — collected by `KarpenterMetricsCollector` and stored in Redis every 2 min, but no UI component renders it
7. **Cluster health score `A/B/C/D`** — computed by `health_monitor.py` every 5 min and stored in Redis, but not surfaced on the main cluster list view

