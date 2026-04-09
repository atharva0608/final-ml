# Auto-Rebalancing System — Complete Deep Dive

> **Last updated:** 6 April 2026  
> **Scope:** End-to-end documentation of the OD→Spot auto-rebalancing system including user settings, pool selection, AWS logic, Kubernetes logic, all phases, cooldowns, locks, UI, backend, DB, and Redis.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [User-Configurable Settings](#2-user-configurable-settings)
3. [Database Models](#3-database-models)
4. [Redis Keys Reference](#4-redis-keys-reference)
5. [Pool Selection & Ranking (System A)](#5-pool-selection--ranking-system-a)
6. [Celery Task Scheduling](#6-celery-task-scheduling)
7. [Auto-Rebalancer Core Loop](#7-auto-rebalancer-core-loop)
8. [Phase 1 — Provisioning Replacement Spot](#8-phase-1--provisioning-replacement-spot)
9. [Phase 2 — Cordon, Drain, Terminate](#9-phase-2--cordon-drain-terminate)
10. [Ghost Node Fast-Path](#10-ghost-node-fast-path)
11. [Agent Execution (In-Cluster)](#11-agent-execution-in-cluster)
12. [Backend EC2 Terminate Logic](#12-backend-ec2-terminate-logic)
13. [Rollback & Recovery](#13-rollback--recovery)
14. [Cooldowns & Locks](#14-cooldowns--locks)
15. [Stale Action Monitor](#15-stale-action-monitor)
16. [Savings Calculation](#16-savings-calculation)
17. [UI & API Endpoints](#17-ui--api-endpoints)
18. [Karpenter Service (K8s NodePool Management)](#18-karpenter-service-k8s-nodepool-management)
19. [WorkloadInspector (Node Classification)](#19-workloadinspector-node-classification)
20. [Spot-to-Spot Rebalancing](#20-spot-to-spot-rebalancing)
21. [End-to-End Flow Diagram](#21-end-to-end-flow-diagram)
22. [Known Issues & Edge Cases](#22-known-issues--edge-cases)
23. [Bug Fixes & Improvements Log](#23-bug-fixes--improvements-log)

---

## 1. System Overview

The auto-rebalancing system replaces On-Demand (OD) EC2 instances with cheaper Spot instances in EKS clusters. It operates as a continuous control loop that:

1. **Detects** OD instances running in EKS clusters
2. **Ranks** alternative Spot instance pools using ML models + AWS Spot Advisor
3. **Provisions** a replacement Spot node via Karpenter
4. **Migrates** workloads (cordon → drain) from OD to Spot
5. **Terminates** the OD instance (with ASG decrement if applicable)

### Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                      │
│  ClusterDetails │ PoolRankings │ AutoRebalanceAuditModal      │
├─────────────────────────────────────────────────────────────┤
│                     BACKEND (FastAPI + Celery)                │
│  Routers: cluster_routes, ascpai_routes, agents, actions     │
│  Workers: auto_rebalancer, ascpai_worker, control_plane      │
│  Services: KarpenterService, PoolRankingService, CooldownCtl │
├─────────────────────────────────────────────────────────────┤
│              AGENT (In-Cluster Python DaemonSet)             │
│  Actuator │ Collector │ Heartbeat │ Poller │ PodMetrics      │
├──────────────┬──────────────┬───────────────────────────────┤
│   PostgreSQL │    Redis     │  AWS (EC2, ASG, STS, Pricing)  │
│ + TimescaleDB│              │  Kubernetes API (via EKS token) │
└──────────────┴──────────────┴───────────────────────────────┘
```

### Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `backend/workers/tasks/auto_rebalancer.py` | ~7504 | Core rebalancing loop — `execute_rebalancing()` (L2101), `execute_rebalancing_action()` (L696), stale monitor, Phase 1 + Phase 2 |
| `backend/workers/tasks/ascpai_worker.py` | ~431 | `execute_pool_ranking_pipeline` (L23), `collect_spot_prices` (L100), `sync_karpenter_nodepools` (L244) |
| `backend/services/pool_ranking_service.py` | ~2885 | Class `PoolRankingService` (L84) — 8-step ML pipeline, `rank_pools()` (L232), `rank_pools_for_node()` (L2181) |
| `backend/services/karpenter_service.py` | ~1408 | Class `KarpenterService` (L37) — NodePool CRUD, `create_spot_trigger_pod()` (L1236), `_get_k8s_client()` (L577) |
| `backend/services/cooldown_controller.py` | ~490 | Class `CooldownController` — multi-layer cooldown with DB write-through to `system_configs` |
| `backend/models/rebalancing_action.py` | | Class `RebalancingAction` — table `rebalancing_actions`, state machine, optimistic locking via `lock_version` |
| `backend/models/agent_action.py` | | Class `AgentAction` — table `agent_actions`, enums `AgentActionType` (L13), `AgentActionStatus` (L31) |
| `backend/models/cluster.py` | | `ClusterOptimizationSettings` (L~155), `OptimizationStrategy` (L~218), `StatelessRuntimeRules` (L~229), `StatefulRules` (L~242), `NodeAlternativeCache` (L~250), `ClusterCooldownState` (L~309) |
| `agent/actuator.py` | ~1941 | Class `ActionActuator` (L41) — `cordon_node()` (L210), `drain_node()` (L357), `_terminate_node()` (L1220), `install_karpenter()` (L812) |
| `agent/poller.py` | | Class `SpotPoller` (L11) — IMDS spot interruption detection, 5-second poll interval |
| `agent/main.py` | | Class `Agent` — 6 component threads + health server + watchdog monitor |
| `backend/services/workload_inspector.py` | | Class `WorkloadInspector` (L29) — `scan_cluster()` node classification, 540s TTL |
| `backend/services/substitute_manager.py` | | Class `SubstituteManager` — state machine: IDLE → PREWARMING → READY → ACTIVE → RELEASING → IDLE |
| `backend/services/metrics_service.py` | ~1608 | Class `MetricsService` (L31) — `_calculate_hibernation_savings()` (L844), `_get_accessible_clusters()` (L819) |
| `backend/services/resource_pricing_service.py` | ~673 | Class `ResourcePricingService` (L36) — `get_instance_price()` (L116) wraps `calculate_instance_cost(hours=1)` |
| `backend/services/hygiene_service.py` | | Class `HygieneService` — IAM scan calls `classify_iam_user()` at L1201 |
| `backend/Resource_rules/identity_rules.py` | | `classify_iam_user()` (L18) — DORMANT_USER_DAYS=90 threshold |
| `backend/redis_keys.py` | | Centralized Redis key pattern documentation |
| `backend/scheduler.py` | | APScheduler `BackgroundScheduler` — `WorkloadInspector` scan (10min), substitute reconciliation (5min), volatility detection (1h) |
| `backend/api/ascpai_routes.py` | | ASCPAi router — `/ascpai/rebalancing/status` (L523), approve (L598), deny (L624) |
| `backend/routers/actions.py` | | Agent action router — `/api/v1/actions/poll` (L23), result (L73) |
| `frontend/src/components/ascpai/RebalancingTimeline.jsx` | | 6-step rebalance visualization with live countdown |
| `frontend/src/hooks/useAdaptivePolling.js` | | Fast (5s) / slow (30s) adaptive polling hook |

---

## 2. User-Configurable Settings

All settings are per-cluster, stored in 4 related DB tables (all defined in `backend/models/cluster.py`) and managed through a unified API via `UnifiedOptimizationSettings` schema (`backend/schemas/cluster_schemas.py` L424).

### 2.1 Automation Controls (`cluster_optimization_settings` table, `ClusterOptimizationSettings` class, L~155)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `auto_rebalance_enabled` | bool | `false` | **Master toggle** — entire system is OFF until this is true |
| `target_spot_exposure_pct` | int | `100` | Max % of nodes that should be Spot. 80 = keep 20% OD |
| `max_concurrent_rebalance_actions` | int | `1` | How many OD nodes to replace simultaneously |
| `rebalance_batch_percent` | int | auto | Max % of OD nodes to target per cycle |
| `check_interval_seconds` | int | `15` | How often the rebalancer evaluates this cluster |
| `cooldown_override_minutes` | int | `null` (=60) | Override default 60-min cluster cooldown |
| `failure_cooldown_minutes` | int | `30` | Wait time after a failed action before retry |
| `manual_approval_required` | bool | `false` | If true, actions enter `pending_approval` state |
| `architecture_preference` | str | `"both"` | `"amd64"`, `"arm64"`, or `"both"` — filters pool selection |
| `drain_timeout_minutes` | int | `15` | Max time to wait for pod eviction during drain |
| `maintain_standby` | bool | `false` | Keep a hot standby Spot node ready |
| `diversify_pools` | bool | `false` | Enforce instance type diversity across Spot fleet |
| `max_family_diversification_cap_pct` | int | `40` | Max % of fleet that can be same instance family |
| `instance_type_diversification_pct` | int | `100` | 100% = every node uses a different type |
| `min_node_count` | int | `1` | Hard floor — never scale below this |
| `scale_down_threshold_pct` | int | `20` | CPU+mem below which node is considered idle |
| `scale_down_stabilization_minutes` | int | `15` | How long util must be below threshold |
| `enable_ascp_auto_scaler` | bool | `false` | Built-in auto-scaler (separate from rebalancing) |
| `karpenter_only_mode` | bool | `false` | Skip all ASG detection code paths |
| `min_topology_spread` | int | `1` | Min AZ spread during consolidation |

### 2.2 Optimization Strategy (`optimization_strategy` table, `OptimizationStrategy` class, L~218)

Controls the risk/savings tradeoff in pool selection:

| Setting | Default | Description |
|---------|---------|-------------|
| `strategy_type` | `"BALANCED"` | `"COST_FIRST"` / `"BALANCED"` / `"NO_DOWNTIME_FIRST"` / `"CUSTOM"` |
| `risk_ceiling_percent` | `25` | Maximum acceptable interruption risk % |
| `min_savings_percent` | `15` | Minimum savings to justify migration |
| `volatility_tolerance_percent` | `20` | Acceptable spot price volatility |
| `migration_penalty_multiplier` | `1.5` | Penalty for migration overhead in scoring |
| `diversity_strictness_level` | `"Medium"` | Pool diversity enforcement level |
| `risk_savings_tradeoff_pct` | `20` | Accept X% more expensive if X% safer |

### 2.3 Stateless Runtime Rules (`stateless_runtime_rules` table, `StatelessRuntimeRules` class, L~229)

| Setting | Default | Description |
|---------|---------|-------------|
| `max_rebalances_per_24h` | `5` | **Daily rebalance cap** — prevents runaway cycles |
| `respect_pdb_enabled` | `true` | Honor PodDisruptionBudgets during drain |
| `prewarm_minutes` | `0` | Pre-warm time for substitute nodes |
| `substitute_strategy` | `"PREWARMED"` | `"PREWARMED"` or `"ON_DEMAND"` |
| `resize_cooldown_minutes` | `120` | Cooldown after right-sizing operation |
| `resize_headroom_multiplier` | `1.2` | Extra capacity margin for resize |
| `volatility_safety_multiplier` | `1.35` | Safety margin for volatile pools |
| `fresh_cluster_stabilization_minutes` | `1440` | 24h stabilization for newly added clusters |

### 2.4 Stateful Rules (`stateful_rules` table, `StatefulRules` class, L~242)

| Setting | Default | Description |
|---------|---------|-------------|
| `manual_resize_allowed` | `true` | Allow manual resize of stateful nodes |
| `require_approval` | `true` | Require human approval for stateful changes |
| `block_spot_for_stateful` | `true` | Prevent spot migration for stateful workloads |
| `max_downscale_percent` | `25` | Max downscale per operation |

### 2.5 Cluster-Level Settings (`clusters` table, `Cluster` class)

| Field | Description |
|-------|-------------|
| `auto_rebalance_enabled` | `Boolean` default False (L108) — Legacy toggle (also in settings table; both must be true) |
| `karpenter_mode` | `Enum(KarpenterMode)` nullable (L97) — `DRY_RUN` / `AUTO` (enum at L24) |
| `optimization_mode` | `String(20)` default `"BALANCED"` (L100) — `COST_FIRST` / `BALANCED` / `NO_DOWNTIME_FIRST` |
| `model_version` | `String(10)` default `"6"` (L105) — ML model version selector |

### 2.6 API for Settings

| Method | Endpoint | Router File | Description |
|--------|----------|-------------|-------------|
| `PATCH` | `/api/v1/clusters/{id}/auto-rebalance?enabled=true` | `backend/routers/cluster_routes.py` | Simple ON/OFF toggle |
| `GET` | `/api/v1/ascpai/clusters/{id}/effective-configuration` | `backend/api/ascpai_routes.py` L121 | Returns computed config including auto_rebalance ON/OFF |
| `PUT` | `/api/v1/clusters/{id}/optimization-settings` | `backend/routers/cluster_routes.py` | Partial update via `UnifiedOptimizationSettings` (`backend/schemas/cluster_schemas.py` L424) |
| `POST` | `/api/v1/clusters/{id}/start-migration` | `backend/routers/cluster_routes.py` | Full migration mode (enables everything) |

---

## 3. Database Models

### 3.1 `rebalancing_actions` — Action State Machine

> **Source:** `backend/models/rebalancing_action.py` — Class `RebalancingAction`

Each rebalancing operation is tracked as a row in this table.

| Column | Type | Line | Description |
|--------|------|------|-------------|
| `id` | `Integer` PK | L22 | Auto-increment |
| `cluster_id` | `String(100)` FK→clusters.id | L23 | Indexed with status via `idx_rebalancing_cluster_status` |
| `trigger` | `String(20)` | L24 | `"emergency"` / `"graceful"` / `"auto_rebalance"` |
| `source_pool` | `String(100)` | L25 | `"instance_type:az"` format, e.g. `"t3.medium:ap-south-1a"` |
| `target_pool` | `String(100)` | L26 | Target spot pool |
| `status` | `String(20)` | L27 | `"in_progress"` / `"completed"` / `"failed"` / `"deferred"` / `"waiting_agent"` / `"pending_approval"` |
| `current_state` | `String(30)` indexed | L59 | State machine: see below |
| `state_entered_at` | `DateTime` | L62 | Timestamp when current state entered |
| `nodes_affected` | `Integer` | L28 | Count of nodes affected |
| `pods_migrated` | `Integer` | L29 | Count of pods migrated |
| `started_at` | `DateTime` | L30 | Action creation timestamp |
| `completed_at` | `DateTime` | L31 | Completion timestamp |
| `duration_seconds` | `Integer` | L32 | Total elapsed time |
| `error_message` | `Text` | L33 | Failure details |
| `action_metadata` | `JSONB` (DB col: `metadata`) | L34 | Rich context (see below) |
| `source_od_price_hr` | `Float` | L39 | OD hourly price at decision time |
| `target_spot_price_hr` | `Float` | L40 | Spot hourly price at decision time |
| `estimated_savings_hr` / `_mo` | `Float` | L41–42 | Projected savings |
| `actual_instance_type` | `String(50)` | L45 | What was actually provisioned |
| `actual_az` | `String(50)` | L46 | What AZ the spot landed in |
| `actual_spot_price_hr` | `Float` | L47 | Actual spot price |
| `realized_savings_hr` / `_mo` / `_pct` | `Float` | L48–50 | Calculated after completion |
| `savings_gap_hr` | `Float` | L51 | estimated vs actual gap |
| `source_instance_id` | `String(50)` indexed | L65 | EC2 instance being replaced |
| `lock_version` | `Integer` default=0 | L64 | Optimistic locking counter |
| `state_history` | `JSONB` | L63 | `[{state, entered_at, exited_at}]` |
| `created_at` | `DateTime` server_default=now() | L53 | Row creation time |

**State Machine (`current_state`)** — defined at L55–58 of `rebalancing_action.py`, constants at L35–45 of `auto_rebalancer.py`:

```
Constants (auto_rebalancer.py L35–45):
SM_CREATED = 'CREATED'
SM_POOL_SELECTED = 'POOL_SELECTED'
SM_SOURCE_CORDONED = 'SOURCE_CORDONED'
SM_SOURCE_DRAINED = 'SOURCE_DRAINED'
SM_REPLACEMENT_LAUNCHING = 'REPLACEMENT_LAUNCHING'
SM_REPLACEMENT_READY = 'REPLACEMENT_READY'
SM_SOURCE_TERMINATING = 'SOURCE_TERMINATING'
SM_COMPLETED = 'COMPLETED'
SM_FAILED = 'FAILED'
SM_DRAIN_TIMEOUT = 'DRAIN_TIMEOUT'

Flow:
CREATED → POOL_SELECTED → SOURCE_CORDONED → SOURCE_DRAINED
    → REPLACEMENT_LAUNCHING → REPLACEMENT_READY → SOURCE_TERMINATING
    → COMPLETED
    → FAILED (from any state)
    → DRAIN_TIMEOUT
```

> **Note:** In practice, the actual flow mainly uses `action.status` (`in_progress`, `waiting_agent`, `deferred`, `failed`, `completed`, `pending_approval`) and `action_metadata['current_step']` strings rather than the SM_* constants. `_sm_transition()` (L48) and `_sm_set_state()` (L98) exist but are primarily called to set `WAITING_FOR_KARPENTER` in Phase 1.

Transitions use optimistic locking via `_sm_transition()` (L48) — `UPDATE WHERE lock_version = N AND current_state = from_state`, incrementing `lock_version`. Failed transitions retry 2x with 100ms/200ms backoff.

**`metadata` JSONB structure** (key fields):

```json
{
  "instance_id": "i-0cde42e5f90ba7271",
  "asg_name_used": "eks-standard-workers-xxx",
  "asg_min_at_start": 0,
  "asg_desired_at_start": 1,
  "replacement_spot_instance_id": "i-0abc...",
  "replacement_spot_node_name": "ip-10-0-1-234.ec2.internal",
  "ranked_alternatives": ["c7g.medium", "m7g.medium", ...],
  "karpenter_nodepool_updated": true,
  "karpenter_nodepool_name": "stateless-spot",
  "karpenter_patched_nodepools": ["stateless-spot", "default"],
  "karpenter_target_types": ["c7g.medium", "m7g.medium", ...],
  "phase1_completed_at": "2026-04-06T10:38:22Z",
  "phase2_created_at": "2026-04-06T10:42:15Z",
  "phase2_params": {"instance_id": "...", "instance_type": "...", "az": "..."},
  "spot_baseline_count": 3,
  "baseline_spot_instance_ids": ["i-0aaa...", "i-0bbb...", "i-0ccc..."],
  "provisioner_type": "karpenter",
  "trigger_pod_name": "spot-trigger-261",
  "trigger_pod_created": true,
  "trigger_pod_instance_type": "c7g.medium",
  "trigger_cpu": "550m",
  "trigger_mem": "508Mi",
  "current_step": "waiting_for_spot_node",
  "termination_mode": "scaledown",
  "ghost_terminate": true,
  "esc_alt1_done": true,
  "esc_alt2_done": false,
  "esc_broad_done": false,
  "step_1_spot_provisioning": "2026-04-06T10:38:22Z",
  "step_2_cordon": "2026-04-06T10:42:30Z",
  "step_3_draining_pods": "2026-04-06T10:43:15Z",
  "step_4_new_node_joined": "2026-04-06T10:41:00Z",
  "readiness_verified": true,
  "target_node_name": "ip-192-168-39-125.ap-south-1.compute.internal"
}
```

### 3.2 `agent_actions` — Agent Command Queue

> **Source:** `backend/models/agent_action.py` — Class `AgentAction`

The backend creates agent action rows; the in-cluster agent polls and executes them.

| Column | Type | Line | Description |
|--------|------|------|-------------|
| `id` | `String(36)` PK (UUID) | L50 | |
| `cluster_id` | `String(36)` FK→clusters.id | L53 | |
| `action_type` | `SQLEnum(AgentActionType)` | L56 | See below |
| `payload` | `JSONB` | L64 | Action-specific params (includes `rebalancing_action_id` to link back) |
| `status` | `SQLEnum(AgentActionStatus)` default PENDING | L67 | `PENDING` → `PICKED_UP` → `COMPLETED` / `FAILED` / `EXPIRED` |
| `priority` | `Integer` default=0 | L80 | 0=normal, 10=emergency |
| `created_at` / `expires_at` / `picked_up_at` / `completed_at` | `DateTime` | L70–74 | Lifecycle timestamps |
| `result` | `JSONB` | L77 | Agent-reported execution result |
| `error_message` | `String(1024)` | L78 | Error details |

**`AgentActionType` enum (L13–28):**

| Value | Description |
|-------|-------------|
| `EVICT_POD` | Evict a pod |
| `CORDON_NODE` | Cordon a node |
| `DRAIN_NODE` | Drain a node |
| `LABEL_NODE` | Label a node |
| `UPDATE_DEPLOYMENT` | Update deployment |
| `INSTALL_KARPENTER` | Install Karpenter |
| `UNINSTALL_KARPENTER` | Uninstall Karpenter |
| `PATCH_CONTAINER_RESOURCES` | Right-sizing: update CPU/memory |
| `TERMINATE_NODE` | Terminate EC2 instance after drain |
| `UNCORDON_NODE` | Uncordon a node |
| `FORCE_DELETE_NODE` | Force-delete K8s Node object |
| `REMOVE_POD_FINALIZERS` | Remove stuck finalizers |

**`AgentActionStatus` enum (L31–37):** `PENDING`, `PICKED_UP`, `COMPLETED`, `FAILED`, `EXPIRED`

**Payload examples for rebalancing**:

```json
// CORDON_NODE
{"instance_id": "i-xxx", "node_name": "ip-xxx", "rebalancing_action_id": "261", "zero_downtime_step": 2}

// DRAIN_NODE
{"instance_id": "i-xxx", "node_name": "ip-xxx", "ignore_daemonsets": true, "grace_period_seconds": 60,
 "force": false, "rebalancing_action_id": "261", "zero_downtime_step": 3}

// TERMINATE_NODE
{"instance_id": "i-xxx", "node_name": null, "rebalancing_action_id": "261", "zero_downtime_step": 4,
 "termination_mode": "scaledown", "asg_name": "eks-xxx", "ghost_node": false}
```

### 3.3 `instances` — EC2 Instance Registry

> **Source:** `backend/models/instance.py` — Class `Instance`

| Column | Type | Description |
|--------|------|-------------|
| `instance_id` | `String(20)` unique | AWS EC2 ID (`i-xxx`) or K8s placeholder (`ip-xxx`) |
| `cluster_id` | FK→clusters | |
| `instance_type` | varchar | `c7g.medium`, `t3.medium`, etc. |
| `lifecycle` | `Enum(InstanceLifecycle)` | `SPOT` (`"spot"`) or `ON_DEMAND` (`"on-demand"`) |
| `az` | varchar | `ap-south-1a` |
| `state` | varchar default `"running"` | `running` / `terminated` |
| `status` | varchar | `READY` / `CALIBRATING` / `UNKNOWN` / `TERMINATED`. Fleet view filters to `READY` or `CALIBRATING` only (whitelist) |
| `node_name` | varchar | K8s node name |
| `architecture` | varchar | `arm64` / `x86_64` |
| `launched_by` | varchar | `"platform"` for platform-launched nodes |
| `standby` | `Boolean` | Hot standby flag |
| `price` | float | Instance hourly price |

### 3.4 Supporting Models

> **All defined in `backend/models/cluster.py`** unless noted otherwise.

| Model | Table | Line | Purpose |
|-------|-------|------|---------|
| `Cluster` | `clusters` | L~60 | EKS cluster metadata + feature flags. `ClusterStatus` enum (L8): PENDING, DISCOVERED, ACTIVE, INACTIVE, ERROR, TERMINATED, DISCONNECTED, DEGRADED, DELETED |
| `NodeAlternativeCache` | `node_alternative_cache` | L~250 | Per-node ranked alternative pools with `coverage_status`: `COVERED`/`AT_RISK`/`STRANDED`/`IMMOVABLE` |
| `ClusterBaseline` | `cluster_baselines` | L~273 | Cost baseline for savings delta |
| `ClusterCooldownState` | `cluster_cooldown_states` | L~309 | DB-backed cooldown: `stabilization_until`, `last_action_at` (survives Redis restarts) |
| `CircuitBreakerState` | `circuit_breaker_state` | `backend/models/circuit_breaker_state.py` | States: CLOSED/OPEN/HALF_OPEN, failure_count, trip_count |
| `PoolCooldown` | `pool_cooldowns` | `backend/models/pool_cooldown.py` | Per-pool failure tracking: `pool_id` (instance_type:az), `last_failure_timestamp` |
| `ExecutionState` | `execution_states` | `backend/models/execution_state.py` | States: PENDING → VALIDATING → PREWARMING → DRAINING → PROVISIONING → READY → COMPLETED / FAILED / ARCHIVED / PDB_BLOCKED / CIRCUIT_OPEN / ROLLBACK |
| `SubstituteState` | `substitute_states` | `backend/models/substitute_state.py` | `cluster_id`, `substitute_type`, status: active/releasing/released |
| `LaunchOutcome` | `launch_outcomes` | `backend/models/launch_outcome.py` | Pool reputation: `pool_key`, outcomes: success/failed/interrupted |
| `OptimizerState` | `optimizer_states` | `backend/models/optimizer_state.py` | Phases: INITIAL_POOL_OPTIMIZATION → STABILIZATION → RIGHTSIZING_EVALUATION → COMBINED_EXECUTION → COOLDOWN |

---

## 4. Redis Keys Reference

> **Centralized documentation:** `backend/redis_keys.py`
> **Inline usage:** Redis key strings appear directly in `auto_rebalancer.py`, `cooldown_controller.py`, `pool_ranking_service.py`, `karpenter_service.py`, and `workload_inspector.py`.

### 4.1 Cooldown Keys

| Key Pattern | TTL | Owner |
|-------------|-----|-------|
| `spot:cooldown:cluster:{cluster_id}` | 60 min (configurable) | `CooldownController` |
| `spot:cooldown:pool:{pool_id}` | 120 min | `CooldownController` |
| `spot:cooldown:pool_switch:{id}` | 30 min | `CooldownController` |
| `spot:cooldown:substitute:{id}` | 120 min | `CooldownController` |
| `spot:cooldown:action:resize:{cluster_id}` | 21600s (6h) | `CooldownController` |
| `spot:rebalanced:instance:{instance_id}` | 86400s (24h) success / backoff on failure | `auto_rebalancer.py` |
| `spot:stabilization_lock:{cluster_id}` | 60s | `CooldownController` |
| `spot:term_failed:{instance_id}` | 14400s (4h) | `auto_rebalancer.py` |
| `spot:launch_blocked:{cluster_id}:{type}:{az}` | 1800s (30 min) | `auto_rebalancer.py` |
| `spot:post_launch_cooldown:{instance_id}` | 60s | `auto_rebalancer.py` |
| `spot:stateful:resize:instance:{id}` | 172800s (48h) | `auto_rebalancer.py` |
| `spot:stateful:resize:cluster:{id}` | 172800s (48h) | `auto_rebalancer.py` |
| `spot:karpenter:nodepool_updated:{cluster_id}` | 1800s (30 min) | `auto_rebalancer.py` |
| `spot:karpenter:provision_requested:{cluster_id}` | 900s (15 min) | `auto_rebalancer.py` |
| `s2s_migration:{cluster_id}:{src}:{tgt}` | 7200s (2h) | `auto_rebalancer.py` |

### 4.2 Lock Keys

| Key Pattern | TTL | Owner |
|-------------|-----|-------|
| `lock:workers.auto_rebalancer` | 300s (renewed 150s) | `HeartbeatLock` in `auto_rebalancer.py` |
| `spot:rebalance_lock:{cluster_id}` | 2700s (renewed 60s) | `auto_rebalancer.py` Phase 1 |
| `lock:node_action:{cluster_id}` | 1200s (20 min) | `auto_rebalancer.py` distributed drain lock |
| `spot:node_active_action:{instance_id}` | 86400s (24h) | `auto_rebalancer.py` |
| `spot:replacement_claimed:{instance_id}` | 3600s (1h) | `auto_rebalancer.py` atomic claim |
| `rebalance:active_count:{cluster_id}` | 300s safety | `auto_rebalancer.py` distributed semaphore |
| `hibernation:lock:{sched}:{cluster}` | 180s | `HibernationWorker` |

### 4.3 State / Tracking Keys

| Key Pattern | TTL | Owner |
|-------------|-----|-------|
| `action_heartbeat:{action_id}` | 120s | Agent + rebalancer |
| `spot:last_check:{cluster_id}` | interval-14s | `auto_rebalancer.py` |
| `spot:last_run_ts:{cluster_id}` | 3× interval | `auto_rebalancer.py` |
| `spot:skip_streak:{cluster_id}` | 300s | `auto_rebalancer.py` — `_record_skip()` (L2072) |
| `spot:daily_count:{cluster_id}` | 86400s | `auto_rebalancer.py` |
| `rebalance_failures:{instance_id}` | 86400s | `auto_rebalancer.py` failure counter |
| `rebalance_last_failure:{instance_id}` | 86400s | `auto_rebalancer.py` backoff reset window |
| `rebalance_daily_count:{instance_id}:{date}` | end-of-day | `auto_rebalancer.py` |
| `spot:node_classification:{cluster_id}` | 540s (9 min) | `WorkloadInspector` |
| `spot:node_arch_constraints:{cluster_id}` | varies | `WorkloadInspector` |
| `class_miss_streak:{cluster_id}` | 90s | `auto_rebalancer.py` |
| `node_joined:{instance_id}` | — | `auto_rebalancer.py` |
| `spot:substitute:state:{cluster_id}` | — | `SubstituteManager` |
| `spot:ondemand_fallback:{cluster_id}` | 12h | `KarpenterService` |
| `spot:nodes_labelled:{cluster_id}` | 3600s | `auto_rebalancer.py` label cache |
| `spot:asserted_spot:{instance_id}` | — | `auto_rebalancer.py` |
| `spot:s2s_suppressed:{instance_id}` | — | `auto_rebalancer.py` |
| `aws_sync:empty_streak:{cluster_id}` | 600s | `_sync_instance_state_from_aws()` (L316) |
| `rc3:sync_od_streak:{instance_id}` | 600s | SPOT→OD confirmation streak |
| `spot:karpenter:installed:{cluster_id}` | — | Karpenter live detection |
| `spot:cluster_mode:{id}` | 300s | `DecisionEngine` |

### 4.4 Caching Keys

| Key Pattern | TTL | Owner |
|-------------|-----|-------|
| `global_pool_rankings:{region}` | 65 min | `PoolRankingService._get_or_compute_global_rankings()` (L559) |
| `ranking_stale_warned:{region}` | 3600s | `auto_rebalancer.py` |
| `ranking_refresh_pending:{region}` | 60s | `auto_rebalancer.py` |
| `instance_type_arch:{type}` | 604800s (7 days) | `_get_instance_arch()` (L110) |
| `dry_run:{type}:{az}` | — | `_final_capacity_check()` |
| `pricing:od:{region}:{type}` | — | OD price cache |
| `cluster_coverage:{cluster_id}` | — | Coverage cache |
| `spot:cluster_circuit_breaker:{cluster_id}` | 30 min | `KarpenterService._check_circuit_breaker()` (L479) |
| `spot:exec_fail_window:{cluster_id}` | 600s (10 min) | `KarpenterService._record_execution_failure()` (L500) |
| `spot:execution_fail:{pool_id}` | 1h | `_final_capacity_check()` per-pool failure |
| `spot:dryrun_count:{region}` | 1h | `PoolRankingService` |
| `spot:dryrun_failures_24h:{pool}` | 24h | `PoolRankingService` |
| `ascpai:ml_fail_count` | 10 min | `PoolRankingService` ML circuit breaker |
| `ascpai:ml_degraded` | 10 min | `PoolRankingService` ML degraded flag |
| `volatility_regime:{region}` | — | `EventMonitor` |
| `market_factor:{region}` | — | Regional market factor |
| `spot:rejection_counter:{id}:{reason}` | 24h | `DecisionEngine` |
| `spot:execution_plan:{cluster_id}` | 1h | `control_plane_loop.py` |

---

## 5. Pool Selection & Ranking (System A)

> **Source:** `backend/services/pool_ranking_service.py` — Class `PoolRankingService` (L84)
> **Dataclasses:** `NodeTemplate` (L41), `InstancePool` (L53), `ScoredPool` (L67)

### 5.1 Overview

Pool ranking runs as a scheduled pipeline (hourly via `execute_pool_ranking_pipeline` in `ascpai_worker.py` L23) and on-demand for per-node decisions. It produces an ordered list of Spot instance pools (type + AZ combinations) scored by an ML model.

### 5.2 The Pipeline (`PoolRankingService.rank_pools()`, L232)

**Signature:** `rank_pools(node_template: NodeTemplate, region: str = "ap-south-1", limit: int = 10, node_id: Optional[str] = None) → List[ScoredPool]`

**Two-tier execution:**
- **Tier 1:** `_get_or_compute_global_rankings()` (L559) — Redis-cached, with lock + fencing token to prevent stampede
- **Tier 2:** `_apply_client_filters()` (L649) — In-memory template filtering

**Global pipeline (`_run_global_pipeline()`, L371):**

```
Step 1: Build ALL catalog instances × region AZs

Step 2: Tiered Spot Advisor Filtering (5 passes, stops when GLOBAL_CACHE_LIMIT met)
  → Pass 0: max_rank=0 (<5% interruption)
  → Pass 1: max_rank=1 (≤10%)
  → Pass 2: max_rank=2 (≤15%)
  → Pass 3: max_rank=3 (≤20%)
  → Pass 4: max_rank=4 (≤25%)

Step 3: Global Blacklist Check
  → Redis-based risky_pools:{region} set; hard-reject at ≥3 failures

Step 4: Capacity Check
  → RunInstances --dry-run (parallelized, 15-min cache)

Step 5: Price Fetch
  → Spot + OD prices from AWS API + Redis cache

Step 6: ML Model Scoring via _step7_ml_scoring() (L1145)
  → Engineers 45 features via MLFeatureService
  → ONNX classifier (classifier_6.onnx → risk_probability)
  → ONNX regressor (regressor_6.onnx → predicted_savings)
  → Spot Advisor savings override when regressor saturates (≥0.99)
  → 4-signal blended risk (compute_blended_risk(), L1398):
    ONNX (0.40) + Price pressure (0.35) + Spot Advisor (0.25) + optional EMA
  → Hard overrides: blacklisted → max(0.75, risk), dryrun failed → max(0.65, risk)
  → Unified score (compute_unified_score(), L1374):
    (savings × 0.8) × (1 - risk) × reputation_mult × capacity_mult
  → Reputation multipliers batch-prefetched via PoolReputationService.bulk_get_multipliers()
  → Circuit breaker: ascpai:ml_fail_count > 5 in 10 min → fallback scoring

Step 7: Post-Score Capacity Check (_step9_post_score_capacity_check(), L1480)
  → DescribeInstanceTypeOfferings on top 10

Step 8: Final Ranking & Caching
  → Dedup by instance type, sort by ml_score DESC
  → Cache: global_pool_rankings:{region} (65-min TTL, top 1500 pools/region)
```

### 5.3 Two-Tier Caching

- **Tier 1 (global):** `global_pool_rankings:{region}` — refreshed hourly by `execute_pool_ranking_pipeline` celery task. Stores top 1500 pools per region.
- **Tier 2 (per-request):** In-memory filtering from Tier 1 cache using cluster-specific template constraints (architecture, families, sizes, AZ preferences).

### 5.4 Per-Node Pool Selection in Rebalancer

When the rebalancer needs to select a target pool for a specific OD node, it uses a **multi-tier hierarchy**:

1. **`rank_pools_for_node()`** (L2181) — Primary: per-node ranking with dynamic filters (pod resource floor, node-specific constraints). Returns pools marked `would_be_launched` or `rebalancer_eligible`.
   - **Signature:** `(node_info: dict, cluster_id: str, region: str, include_dynamic_filters: bool = True, force_type: Optional[str] = None) → List[dict]`
   - Loads cluster settings (risk_ceiling, tradeoff_pct, arch_pref, diversify, min_savings)
   - Applies market factor to risk ceiling
   - Floor enforcement: refuses to rank if `min_vcpu=0` (prevents undersized replacement)
   - Reads from `market_view_cache:{region}` or `global_pool_rankings:{region}`

2. **4-Pass Rebalancer Gate** (inside `rank_pools_for_node()`):
   - Pass 1: Cheaper AND risk < ceiling
   - Pass 2: Tradeoff — allow up to X% savings loss for lower risk
   - Pass 3: Risk override — any safer pool
   - Pass 4: OD→Spot last-resort fallback (any cheaper pool)

3. **`rank_pools_for_size()`** (L2051) — Size-based fallback if per-node returns nothing:
   - **Signature:** `(vcpu: int, memory_gb: float, region, allowed_families, architecture, limit) → List[ScoredPool]`
   - Creates size-constrained NodeTemplate (±1 vCPU, ±2 GB flexibility)
   - Uses `rank_pools()` internally, sorts by closeness to target size

4. **`rank_pools_for_node()` retry** — If double-gate returns same type or null.

### 5.5 Scheduled Tasks (`backend/workers/tasks/ascpai_worker.py`, ~431 lines)

| Task | Line | Interval | Purpose |
|------|------|----------|---------|
| `execute_pool_ranking_pipeline` | L23 | 1 hour | Refreshes global pool rankings cache |
| `collect_spot_prices` | L100 | 10 min | Stores real-time spot prices in `spot_price_history` |
| `sync_karpenter_nodepools` | L244 | 1 hour (after ranking) | Syncs ML-ranked instance types to Karpenter NodePools. **Guards:** skips clusters without agent, without karpenter_mode, with stale heartbeat (>30 min), or with active rebalancing action (`status IN ('in_progress', 'waiting_agent')`) |
| `cleanup_old_spot_prices` | L196 | (helper) | Deletes entries older than 24h |

### 5.6 Architecture-Aware Ranking

The `architecture_preference` setting filters pools (in `_apply_client_filters()`, normalizes `x86_64 ↔ amd64` as aliases):
- `"arm64"`: Only ARM64 families (m7g, c7g, r7g, m6g, c6g, r6g, t4g)
- `"amd64"`: Only x86_64 families (m5, m6i, c5, c6i, r5, r6i, etc.)
- `"both"`: All families allowed
- Auto-detection: `_get_instance_arch()` (L110 in `auto_rebalancer.py`) uses `DescribeInstanceTypes` API (7-day Redis cache `instance_type_arch:{type}`) + static ARM family fallback
- Pod-request-based floor via `node_resource_profile:{node_id}` (10% headroom)
- Source OD price gate: `source_od_price > 0 → skip if spot ≥ source_od_price`

### 5.7 Additional Module-Level Functions (`pool_ranking_service.py`)

| Function | Line | Purpose |
|----------|------|---------|
| `estimate_az_interruption()` | L2586 | 3-layer model: AWS base + AZ price adjustment + historical EMA |
| `record_interruption_event()` | L2665 | Updates EMA in Redis (7-day TTL) |
| `assign_risk_tier()` | L2722 | Risk tier classification |
| `compute_capacity_score()` | L2731 | Capacity availability score |
| `report_launch_attempt()` | L2737 | Pool reputation tracking |
| `report_launch_failure()` | L2749 | Pool reputation tracking |
| `report_launch_success()` | L2775 | Pool reputation tracking |
| `get_pool_reputation()` | L2809 | reputation_multiplier 0.5–1.2 |
| `blacklist_pool_temporary()` | L2852 | Temporary pool blacklist |
| `filter_pools_with_dry_run()` | L2863 | DryRun capacity filter |

---

## 6. Task Scheduling

> **Note:** The codebase uses **two scheduling systems**: Celery tasks (for the main rebalancer and workers) and APScheduler `BackgroundScheduler` (`backend/scheduler.py`) for services.

### 6.1 Celery Tasks (Key Entries)

| Task | Interval | Name | File |
|------|----------|------|------|
| `workers.auto_rebalancer` | **15 seconds** | Main rebalancer loop | `auto_rebalancer.py` L2101 |
| `workers.ascpai.execute_pool_ranking_pipeline` | 1 hour | Pool rankings | `ascpai_worker.py` L23 |
| `workers.ascpai.sync_karpenter_nodepools` | 1 hour | NodePool sync | `ascpai_worker.py` L244 |
| `workers.ascpai.collect_spot_prices` | 10 minutes | Spot prices | `ascpai_worker.py` L100 |
| `workers.termination_monitor` | 30 seconds | Spot termination notices | `termination_monitor.py` |
| `workers.sqs_consumer.poll_interruption_queues` | 30 seconds | SQS spot interruptions | `sqs_consumer.py` |
| `warm_spare.maintain_all_clusters` | 5 minutes | Standby node maintenance | `maintain_warm_spare_worker.py` |
| `health.cleanup_zombie_nodes` | 2 minutes | Zombie node cleanup | `health.py` |
| `health.reset_stale_agents` | 60 seconds | Agent stale detection | `health.py` |
| `dry_run_refresher` | 5 minutes | Capacity dry-run refresh | `dry_run_refresher.py` |
| `workers.control_plane.run_all_clusters_decision_cycle` | 5 minutes | 8-step control plane | `control_plane_loop.py` |

### 6.2 APScheduler Jobs (`backend/scheduler.py`)

| Job ID | Interval | Function | Purpose |
|--------|----------|----------|---------|
| `refresh_active_count` | 5 min | `job_refresh_active_count` | Refresh active cluster count for DryRun budgets |
| `reconcile_substitutes` | 5 min | `job_reconcile_substitutes` | Reconcile stuck substitutes via `SubstituteManager` |
| `scan_clusters` | 10 min | `job_scan_clusters` | Node classification via `WorkloadInspector` |
| `check_cost_drift` | 30 min | `job_check_cost_drift` | Cost drift detection via `SubstituteManager` |
| `detect_volatility` | 1 hour | `job_detect_volatility` | Volatility regime detection via `EventMonitor` |
| `cleanup_blacklist` | Daily 2 AM | `job_cleanup_blacklist` | Blacklist + Redis hygiene |

All APScheduler jobs have a 60-second startup delay.

### 6.3 Task Concurrency

The rebalancer uses `HeartbeatLock("lock:workers.auto_rebalancer")` (300s TTL, renewed every 150s) to ensure only ONE celery worker executes the main loop at a time. All other workers that pick up the task see the lock and skip.

---

## 7. Auto-Rebalancer Core Loop

> **Source:** `backend/workers/tasks/auto_rebalancer.py` (~7504 lines)

### 7.1 Entry Point

`execute_rebalancing()` (L2101) — Celery task `@app.task(name='workers.auto_rebalancer')` running every 15 seconds.

### 7.2 Key Functions Index

| Function | Line | Description |
|----------|------|-------------|
| `_sm_transition()` | L48 | Atomic state machine transition (optimistic lock) |
| `_sm_set_state()` | L98 | Force-set state w/o optimistic check |
| `_get_instance_arch()` | L110 | Arch detection via DescribeInstanceTypes + 7-day cache |
| `_extract_k8s_minor_version()` | L148 | EKS version extraction |
| `_resolve_arch_compatible_ami()` | L163 | AMI resolution for cross-arch rebalancing |
| `_validate_rebalancing_action_schema()` | L260 | Pillar 6 data contract validation |
| `_sync_instance_state_from_aws()` | L316 | AWS→DB lifecycle sync (RC3, empty-streak guard) |
| `execute_rebalancing_action()` | L696 | **Phase 1 logic** — single action execution |
| `trigger_graceful_rebalancing()` | L1598 | API-callable trigger for manual/scheduled rebalance |
| `_seed_instances_from_redis()` | L1652 | Create Instance rows from Redis telemetry |
| `_do_rollback_uncordon_and_terminate()` | L1786 | Rollback: uncordon + terminate orphan spot |
| `_do_rollback_terminate_orphan_spot()` | L1820 | Terminate orphaned replacement spot EC2 |
| `_cleanup_rebalancing_resources()` | L1964 | Idempotent cleanup (Redis keys, trigger pods, agent actions, NodePool rollback) |
| `_record_skip()` | L2072 | Skip streak tracking |
| `_record_active()` | L2093 | Clear skip streak |
| `execute_rebalancing()` | L2101 | **Main Celery task entry point** |

### 7.3 Loop Structure

```python
@app.task(name='workers.auto_rebalancer')  # L2101
def execute_rebalancing():
    # 1. Acquire HeartbeatLock (global singleton, 300s TTL, 150s heartbeat)
    
    # 2. STALE ACTION MONITOR (~L2222)
    #    - Expire actions older than 45 minutes
    #    - Per-state timeouts (_STATE_TIMEOUTS_MIN dict, L~2232)
    #    - Action heartbeat check (>2min stale)
    #    - Terminate orphan spot EC2s for stale actions
    
    # 3. STALE-RESOURCE SWEEPER (~L2321)
    #    - Clean leaked spot:node_active_action locks
    
    # 4. STEP 0: RESOLVE waiting_agent ACTIONS (~L2330)
    #    - Update action heartbeat
    #    - Track step timestamps (step_1 through step_6)
    #    - Karpenter detection via karpenter_nodepool_updated metadata flag
    #    - Standby fast-path (Enhancement 9, find_ready_standby())
    #    - Spot join detection: Pinned ID → Count fallback → Time-based → K8s direct
    #    - Readiness gate (Enhancement 4): node_name + 10s floor + READY/CALIBRATING + live K8s check
    #    - Atomic claim via spot:replacement_claimed:{id} (Redis NX)
    #    - Ghost node fast-path: ASG-backed but not in K8s → TERMINATE-only
    #    - Trigger pod creation (after 10s): workload-aware sizing, node labelling
    #    - Escalation: ESC_ALT1 (5 min), ESC_ALT2 (10 min), ESC_BROAD (15 min)
    #    - Phase 2 creation (CORDON → DRAIN → TERMINATE agent actions)
    #    - Fast-recovery: expired Phase 2 + source EC2 check → auto-complete or re-queue
    #    - Readiness verification (20s grace + stuck pod check + drain timeout)
    #    - Backend EC2 terminate (ASG path vs direct EC2, STS 5x retry)
    #    - Failure handling: CORDON/DRAIN rollback, zombie EC2 terminate (Z4)
    #    - Post-success: remove do-not-disrupt, standby launch, savings recalc
    #    - Post-failure: exponential backoff, pool ranking refresh
    
    # 5. STEP 1: CLUSTER LOOP (~L4900)
    #    For each cluster with auto_rebalance_enabled=True:
    #      a. Hibernation gate
    #      b. Per-cluster interval gate (check_interval_seconds)
    #      c. Stabilization lock gate (60s post-action)
    #      d. Pool rankings freshness check + stale abort
    #      e. AWS instance state sync (_sync_instance_state_from_aws, L316)
    #      f. Karpenter NodePool refresh (30-min cooldown)
    #      g. Ghost/stale instance cleanup
    #      h. OptimizerCoordinator phase gate (RC-5)
    #      i. Daily rebalance limit check (with OD→Spot bypass)
    #      j. One-at-a-time guardrail (agent actions)
    #      k. Proactive warm standby, last-node safety guard
    #      l. Karpenter provisioning cooldown (configurable, default 60 min)
    #      m. Deferred action re-queue
    #      n. Find ON_DEMAND instances (with Redis seeding fallback)
    #      o. Per-instance cooldown filter
    #      p. WorkloadInspector classification filter
    #      q. Target spot exposure enforcement
    #      r. S2S rebalancing (when no OD left): diversify, risk-threshold, opportunistic
    #      s. Per-instance action creation: ML ranking (4-pass gate), diversify filter
    
    # 6. STEP 2: EXECUTE in_progress ACTIONS (~L7410)
    #    For each new action → execute_rebalancing_action()
    
    # 7. AUTO-STATEFUL RIGHTSIZING PHASE (~L7435)
    #    Separate phase with 48h cooldowns
```

### 7.4 Gate Sequence (Per Cluster)

Before any OD node targeting, every cluster passes through these gates in order (Step 1, ~L4900):

```
1. auto_rebalance_enabled = True              → skip cluster if false
2. Cluster not hibernating                    → skip if is_hibernating
3. Per-cluster interval gate                  → skip if checked < interval ago
4. Stabilization lock not held                → skip if lock exists (60s post-action)
5. Pool rankings cache is fresh               → warn if stale (>65min), trigger refresh
6. AWS instance sync completed                → _sync_instance_state_from_aws() (L316)
7. Karpenter NodePool refreshed               → 30-min cooldown between syncs
8. Ghost instance cleanup done                → removes stale ip- placeholders
9. OptimizerCoordinator phase safety gate     → blocks during active optimizer phases (RC-5)
10. Daily rebalance limit not exceeded        → max_rebalances_per_24h check (OD→Spot bypass)
11. One-at-a-time guardrail                   → blocks if PENDING/PICKED_UP agent actions exist
12. OD instances found                        → skip if no running OD instances
13. Per-instance cooldown check               → skip instances done in last 24h
14. WorkloadInspector classification           → skip STATEFUL or unclassified nodes
15. Target exposure enforcement               → only target enough to reach target_spot_exposure_pct
```

---

## 8. Phase 1 — Provisioning Replacement Spot

> **Source:** `execute_rebalancing_action()` at L696 of `auto_rebalancer.py`

### 8.1 Trigger

Phase 1 runs inside `execute_rebalancing_action()` (L696) when a new `RebalancingAction` is created with `status='in_progress'`.

### 8.2 Safety Gates (Before Phase 1)

```
1. Cluster cooldown guard                     → key_cluster_cooldown
2. Concurrency lock (Redis NX, 2700s TTL)     → spot:rebalance_lock:{cluster_id} (heartbeat thread every 60s)
3. Cross-system gates:
   a. Stabilization lock                      → blocks if cluster just had an action
   b. Substitute mutual exclusion             → blocks if SubstituteManager in PREWARMING/RELEASING
   c. Resize cooldown                         → blocks if resize in progress
4. Double-launch guard                        → checks replacement_spot_instance_id in metadata
5. Distributed lock (1200s TTL)               → lock:node_action:{cluster_id}
6. Per-node active action lock                → spot:node_active_action:{instance_id}
7. Concurrent action semaphore                → rebalance:active_count:{cluster_id} INCR/DECR
```

### 8.3 Phase 1 Steps

> Implemented in `execute_rebalancing_action()` (L696–L1596)

```
Step 1: Instance ID Resolution
  → Resolve K8s hostname placeholders (ip-xxx) to real EC2 IDs
  → Query: Instance WHERE node_name LIKE instance_id

Step 2: ASG Detection
  → Call get_asg_for_instance(instance_id, region, creds)
  → Store asg_name_used, asg_min_at_start, asg_desired_at_start in metadata
  → Skip if karpenter_only_mode = True

Step 3: Pre-computed Ranked Alternatives
  → Uses ranked_alternatives from metadata if pre-computed in Step 1
  → Fallback re-ranking via PoolRankingService.rank_pools_for_node() (L2181)

Step 4: No-Join Block Filter
  → Check spot:launch_blocked:{cluster_id}:{type}:{az} Redis keys
  → Skip pools that previously failed to join K8s

Step 5: Architecture Filtering
  → Determine source node architecture via _get_instance_arch() (L110)
  → Filter ML-ranked alternatives by architecture_preference
  → ARM64 families: m7g, m6g, c7g, c6g, r7g, r6g, t4g
  → AMD64 families: m5, m6i, c5, c6i, r5, r6i

Step 6: Karpenter Installation Verification
  → Check DB + Redis spot:karpenter:installed:{cluster_id} + in-flight

Step 7: Dry-Run Capacity Validation
  → KarpenterService._final_capacity_check() (L329 of karpenter_service.py)
  → ARM64-aware: resolves EKS-optimized AMI via SSM parameter
    (/aws/service/eks/optimized-ami/{version}/amazon-linux-2-arm64/recommended)
  → Fallback to DescribeImages with architecture filter
  → Cache results in Redis
  → Layer isolation: only updates spot:execution_fail:{pool_id} (1h TTL)
  → Escalates to 6h blacklist after ≥2 failures via BlacklistService

Step 8: Karpenter NodePool Patch
  → KarpenterService.add_allowed_instance_type_all_spot() (L948 of karpenter_service.py)
  → Returns (bool, list[str]) — success flag + list of patched NodePool names
  → Adds target types to ALL spot-capable NodePools
  → Up to 8 types from ranked_alternatives
  → Read-back verification after patch
  → Auto-syncs kubernetes.io/arch label based on types in NodePool
  → Stores karpenter_nodepool_name (first patched) and
    karpenter_patched_nodepools (all patched) in metadata

Step 9: Record Phase 1 Completion
  → Set state: WAITING_FOR_KARPENTER via _sm_set_state() (L98)
  → Set metadata: karpenter_nodepool_updated=True
  → Set metadata: phase1_completed_at = now()
  → Set metadata: spot_baseline_count = current running spot count
  → Set metadata: baseline_spot_instance_ids = [s.instance_id for all running spots]
    (enables ID-set-diff detection when baseline=0)
  → Set status: waiting_agent
```

### 8.4 Trigger Pod Creation (10 seconds after Phase 1)

> Trigger pod creation happens in TWO places: at the end of Phase 1 in `execute_rebalancing_action()` (Enhancement 3, ~L1440) AND in the spot-wait loop inside Step 0 (~L3060). The first is eager, the second is the fallback.

If `spot_count <= spot_baseline` after 10 seconds (`_SPOT_STABILIZE_FLOOR_S`), Karpenter hasn't provisioned a node because there's no pending pod to schedule. The rebalancer creates a **trigger pod**:

```
Step 1: Workload-Aware Sizing
  → Query PodMetric table for all pods on source OD node
  → Sum CPU millicores and memory bytes (exclude DaemonSet pods)
  → Apply 10% safety margin
  → Example: 500m CPU + 462Mi memory → 550m CPU + 508Mi memory

Step 2: Label Existing Nodes
  → Label ALL existing K8s nodes with spot-optimizer.io/existing-node=true
  → Cache in Redis set spot:nodes_labelled:{cluster_id} (1h TTL)
  → This ensures trigger pod can't schedule on existing nodes

Step 3: Create Trigger Pod
  → KarpenterService.create_spot_trigger_pod() (L1236 of karpenter_service.py)
  → Creates busybox pod in 'default' namespace
  → nodeSelector:
      karpenter.sh/capacity-type: spot
      karpenter.sh/nodepool: <from metadata karpenter_nodepool_name, default "default">
      node.kubernetes.io/instance-type: c7g.medium  (target type)
  → nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        - key: spot-optimizer.io/existing-node
          operator: DoesNotExist
  → podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        - labelSelector: {app: spot-trigger}
          topologyKey: kubernetes.io/hostname
  → resources: {requests: {cpu: 550m, memory: 508Mi}}
  → command: ["sleep", "3600"]
  → toleration: {operator: Exists}
  → Returns True on 409 (already exists), False on other failures

Step 4: Karpenter Provisions
  → Karpenter sees Pending pod that can't fit existing nodes
  → Launches new c7g.medium spot instance
  → Node joins K8s, gets Ready status
```

### 8.5 Spot Wait Gate

> Runs in Step 0 of `execute_rebalancing()` (~L2330), on every 15-second cycle.

After Phase 1, every 15-second cycle checks if a new spot node joined:

```
Detection priority:
  1. Standby Fast-Path (Enhancement 9)
     → find_ready_standby() — checks for pre-warmed standby node
     → If found, claims immediately (skips trigger pod)

  2. ID-First (replacement_spot_instance_id pinned)
     → Direct DB lookup by instance_id
     → Proactive polling: node_name + node_joined:{id} Redis key
  
  3. Count Fallback with ID-Set-Diff (legacy — no pinned ID)
     → spot_count > spot_baseline
     → Filtered by expected_instance_type
     → Uses baseline_spot_instance_ids set-diff:
       Query spots NOT IN baseline IDs + matching target type
       → More reliable than pure count, especially when baseline=0
  
  4. Time-Based Stagnation
     → Spot created_at > action.started_at
     → Net count didn't increase (old spot died simultaneously)
  
  5. K8s Direct Detection
     → Query K8s API directly for node list

Readiness gate (Enhancement 4):
  → Age >= 10 seconds (_SPOT_STABILIZE_FLOOR_S)
  → node_name must be set (kubelet joined K8s)
  → status must be READY or CALIBRATING (not UNKNOWN)
  → Live K8s node check

Timeout: 30 minutes (_SPOT_WAIT_TIMEOUT_S = 1800s)
  → Direct launch: terminate orphan EC2, fail action
  → Karpenter: fail action (check NodeClaim status)

Log severity (progressive):
  → < 5 min: INFO
  → 5-20 min: WARNING
  → > 20 min: ERROR
```

### 8.6 Spot Wait Escalation (baseline=0 Stall Recovery)

When `spot_count=0` and `baseline=0`, the trigger pod may be Pending because
Karpenter can't get spot capacity for the target instance type.  The system
progressively tries alternative types from `ranked_alternatives` in metadata:

```
Escalation timeline (after trigger pod created):

  5 min (_ESC_ALT1_S):  ESCALATION — switch to 2nd alternative type
     → Delete current trigger pod
     → Recreate targeting ranked_alternatives[1] (e.g. m7g.medium)
     → Re-label existing nodes
     → Set metadata: esc_alt1_done=True

  10 min (_ESC_ALT2_S): ESCALATION — switch to 3rd alternative type
     → Delete current trigger pod
     → Recreate targeting ranked_alternatives[2] (e.g. r7g.medium)
     → Set metadata: esc_alt2_done=True

  15 min (_ESC_BROAD_S): ESCALATION — broaden to any NodePool type
     → Delete current trigger pod
     → Recreate with NO instance-type constraint
     → Karpenter chooses freely from all types in NodePool
     → Set metadata: esc_broad_done=True

  30 min: TIMEOUT — fail action (existing behavior)
     → Cleanup trigger pod, NodePool types, Redis locks
```

Escalation flags are one-shot (each step runs at most once per action).
The trigger pod sizing (`trigger_cpu`, `trigger_mem`) is preserved from
the original workload-aware calculation.

**Example action 262 timeline:**
```
  T+0:00   Phase 1 done, waiting for spot (baseline=0)
  T+1:00   Trigger pod created: spot-trigger-262 (type=c7g.medium)
  T+5:00   ESC_ALT1: delete & recreate targeting m7g.medium
  T+10:00  ESC_ALT2: delete & recreate targeting r7g.medium
  T+15:00  ESC_BROAD: delete & recreate with NO type constraint
  T+30:00  TIMEOUT: fail action, full cleanup
```

---

## 9. Phase 2 — Cordon, Drain, Terminate

### 9.1 Trigger

Phase 2 is created when the spot wait gate confirms a new spot node has joined K8s and is Ready.

### 9.2 Pre-Phase-2 Actions

```
1. Atomic Claim
   → Redis SET NX on spot:replacement_claimed:{instance_id}
   → Prevents two actions from sharing one replacement spot

2. Trigger Pod Cleanup
   → Delete spot-trigger-{action_id} pod from K8s
   → Karpenter will NOT terminate the new spot (node already has workloads)

3. Do-Not-Disrupt Annotation
   → Set karpenter.sh/do-not-disrupt=true on new spot node
   → Prevents Karpenter consolidation from terminating replacement during drain
```

### 9.3 K8s Node Verification

Before creating agent actions, verify the OD node is registered in K8s:

```
if node_name NOT in K8s nodes:
    if asg_name_used exists:
        → Ghost node (EC2 running but not in K8s)
        → Skip cordon/drain → TERMINATE-only path (see §10)
    else:
        → Not ASG-backed and not in K8s → nothing to do
        → Mark action FAILED
```

### 9.4 Agent Action Creation

If the node IS in K8s, create 3 agent actions:

```
1. CORDON_NODE  (zero_downtime_step: 2)
   → Marks node unschedulable
   → payload: {instance_id, node_name, rebalancing_action_id}

2. DRAIN_NODE   (zero_downtime_step: 3)
   → Evicts all pods (except DaemonSets, mirrors)
   → payload: {instance_id, node_name, ignore_daemonsets: true,
               grace_period_seconds: 60, force: <from respect_pdb_enabled>}

3. TERMINATE_NODE (zero_downtime_step: 4)
   → Backend handles actual EC2 termination (not agent)
   → payload: {instance_id, termination_mode: "scaledown"/"karpenter",
               asg_name, asg_min_at_start, asg_desired_at_start}
```

### 9.5 Readiness Verification (Post-Drain)

After drain completes, the rebalancer waits for evicted pods to reschedule:

```
1. Grace period: 20 seconds minimum (_READINESS_GRACE_S)
2. Readiness check: All evicted pods Running on new nodes?
3. Drain timeout: configurable (_READINESS_MAX_S = drain_timeout_minutes * 60, default 900s = 15 min)
4. Pod stuck check: If pods still Pending after timeout → log warning, proceed
5. Max wait: 5 minutes for readiness verification
```

### 9.6 `termination_mode` Routing

> **Note:** 4 modes exist in the agent's `_terminate_node()` (L1220 of `actuator.py`). For rebalancing, the backend determines the mode.

| Mode | When Used | AWS API Call |
|------|-----------|-------------|
| `scaledown` | OD node is ASG-backed | `terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=True)` |
| `asg_no_decrement` | ASG attach mode | `terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=False)` |
| `karpenter` | Karpenter-managed (no ASG) | `ec2.terminate_instances(InstanceIds=[id])` |
| `replacement` | Standard detach | Detach from ASG (no decrement) + EC2 terminate |

---

## 10. Ghost Node Fast-Path

### 10.1 What Is a Ghost Node?

An EC2 instance that is:
- Running in AWS
- InService in an ASG
- **NOT registered as a K8s node** (kubelet never started or crashed)

This causes the standard rebalancer to fail: Phase 2 tries to CORDON/DRAIN but the node doesn't exist in K8s → "not registered in Kubernetes. Cannot cordon/drain."

### 10.2 Ghost Detection

**Two detection points:**

1. **Early fast-path** (before spot-wait) — `auto_rebalancer.py` spot-wait block:
   ```
   IF asg_name_used exists
   AND ghost_terminate NOT already set
   AND phase2_created_at NOT already set
   THEN:
     → K8s list_node() check
     → IF target_node_name NOT in K8s nodes → ghost confirmed
   ```

2. **Phase 2 verification** (after spot joins) — in Phase 2 creation:
   ```
   IF node_name NOT found in K8s node list
   AND asg_name_used exists
   THEN: _p2_skip_cordon_drain = True
   ```

### 10.3 Ghost Terminate Flow

```
1. Ghost detected → skip cordon/drain entirely
2. Delete trigger pod (not needed — no workloads to migrate)
3. Create TERMINATE-only AgentAction:
   → termination_mode: "scaledown"
   → ghost_node: true
   → No CORDON or DRAIN actions created
4. Set metadata: ghost_terminate=True
5. Next cycle: ghost_terminate bypass
   → Immediately set readiness_verified=True
   → Skip drain wait, pod readiness check
   → Proceed to backend EC2 terminate
6. Backend terminate:
   → Pre-decrement ASG MinSize by 1
   → terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=True)
   → ASG desired capacity decremented by AWS
   → Result: ASG desired goes to 0, no replacement launched
```

---

## 11. Agent Execution (In-Cluster)

> **Source:** `agent/main.py` — Class `Agent`, `agent/actuator.py` — Class `ActionActuator` (L41)

### 11.1 Agent Architecture

The agent runs as a DaemonSet in the EKS cluster with **6 component threads** + 1 health server + 1 monitor watchdog (started in `Agent.start_components()`, L302–360 of `agent/main.py`):

| Thread Name | Class | File | Purpose |
|-------------|-------|------|---------|
| `MetricsCollector` | `MetricsCollector` | `agent/collector.py` | Node/pod CPU/memory via psutil (priority 1) or K8s metrics-server (priority 2) |
| `ActionActuator` | `ActionActuator` | `agent/actuator.py` L41 | HTTP poll `/api/v1/actions/poll` every 10s + execute K8s operations |
| `HeartbeatSender` | `HeartbeatSender` | `agent/heartbeat.py` L121 | 30s heartbeat to backend + Karpenter live detection + health server |
| `WebSocketClient` | `WebSocketClient` | `agent/websocket_client.py` | Real-time action push. BUG-1/N6 fix: dual queue (critical unbounded + metrics ring buffer maxlen=200) |
| `SpotPoller` | `SpotPoller` | `agent/poller.py` L11 | IMDS spot interruption/rebalance-recommendation polling every 5s |
| `PodMetricsCollector` | `PodMetricsCollector` | `agent/pod_metrics_collector.py` | Pod-level CPU/memory for right-sizing, 60s interval |

**Additional threads:**
- `/healthz` HTTP server on port 8080 (`_HealthHandler`, in `Agent.run()`)
- `monitor_components()` — watchdog loop every 30s, restarts dead threads with exponential backoff (max 10 restarts, capped at 60s)

### 11.2 Action Polling & Execution

> **Source:** `ActionActuator.run()` (L1775) and `execute_action_v2()` (L1586)

```
Agent Actuator Loop (every 10s, L1775–1840):
  1. GET /api/v1/actions/poll?cluster_id=X (poll_actions(), L1724)
  2. Sort by zero_downtime_step (Bug #11 defense-in-depth)
  3. Execute ONE step per rebalancing_action_id per cycle
  4. Spawn _action_heartbeat_loop thread (N5 fix, L1577 — POST heartbeat every 30s)
  5. Execute via execute_action_v2() (L1586, UPPERCASE enum normalization):
     → CORDON_NODE: cordon_node() (L210)
     → DRAIN_NODE: drain_node() (L357)
     → TERMINATE_NODE: _terminate_node() (L1220) — 4 modes
     → LABEL_NODE: label_node() (L518)
     → PATCH_CONTAINER_RESOURCES: _patch_container_resources() (L1022)
     → etc.
  6. POST /api/v1/actions/{id}/result (report_action_result(), L1748)
```

**WebSocket fallback (BUG-1):** If WebSocket send fails, HTTP fallback for action result delivery (L387–396 of `websocket_client.py`).

### 11.3 Cordon Details (`actuator.cordon_node()`, L210–289)

- Patches `node.spec.unschedulable = True`
- Read-back verification (L248–257) to confirm state persisted
- **Z3 self-cordon guard** (L222–229): Reads `NODE_NAME` env var. If `not uncordon` and `node_name == _my_node`, returns `SELF_CORDON_ATTEMPT` error immediately.
- Result: `{verified: true/false, node_name, was_already_cordoned}`

### 11.4 Drain Details (`actuator.drain_node()`, L357–502)

```
1. Z3 self-drain guard (L371–377): blocks SELF_DRAIN_ATTEMPT
2. Cordon first (if not already cordoned)
3. List all pods on node
4. Skip: DaemonSet pods (_is_daemonset_pod, L722), mirror pods (_is_mirror_pod, L729)
5. Skip: pods with no controller if force=False (_has_controller, L734)
6. For each pod:
   a. Check PDB violation (check_pdb_violation(), L99–126)
      → Lists PDBs in namespace, matches pod labels against selectors
      → If disruptions_allowed < 1 → violation
      → ISSUE-13 FIX: On error, returns False (fail-open, matches kubectl drain)
   b. If PDB blocks AND force=True: force-delete pod (grace_period_seconds=0)
   c. If PDB blocks AND force=False: append to failed list
   d. Normal: evict_pod() (L128) — 5 retries on 429 with 10s delay
7. Wait for pod termination (grace period check)
8. Post-drain verification (L441–451): count remaining non-DS pods
9. Clear stuck VolumeAttachments (clear_stuck_volume_attachments(), L576) — best-effort
10. Result: {verified: true, pods_evicted, pods_remaining, remaining_non_ds_pods}
```

### 11.5 Terminate (`_terminate_node()`, L1220 — 4 Modes)

| Mode | When Used | AWS API Call |
|------|-----------|-------------|
| `scaledown` | OD node is ASG-backed | `terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=True)` |
| `asg_no_decrement` | ASG attach mode | `terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=False)` |
| `karpenter` | Karpenter-managed (no ASG) | `ec2.terminate_instances(InstanceIds=[id])` |
| `replacement` | Standard detach | Detach from ASG (no decrement) + EC2 terminate |

> **Note:** The TERMINATE_NODE agent action for rebalancing is primarily a state marker. The backend's Step 0 in `execute_rebalancing()` handles actual EC2 termination directly (see §12). The agent's `_terminate_node()` is used for direct agent-initiated terminations.

### 11.6 Spot Interruption Handling (`agent/poller.py` — `SpotPoller`, L11)

Separate from rebalancing — handles AWS spot termination notices:

```
IMDS URLs:
  spot/instance-action: http://169.254.169.254/latest/meta-data/spot/instance-action
  rebalance:            http://169.254.169.254/latest/meta-data/events/recommendations/rebalance

1. IMDSv2 token management (_get_imds_token, L49) — 6h TTL, v1 fallback
2. Poll every 5 seconds (run(), L114):
   a. check_termination_notice() (L82) — checks spot/instance-action
   b. check_rebalance_recommendation() (L102) — checks events/recommendations/rebalance
3. On termination notice:
   → _notify_backend() (L133) — POST /api/v1/worker/spot-interruption
   → handle_termination() (L174):
     - Primary: actuator.handle_spot_interruption() (L1843)
     - Fallback: _emergency_self_cordon_drain() (L1862) — BUG-13: bypasses Z3 self-cordon guard
4. On rebalance recommendation:
   → _notify_rebalance() (L157) — POST /api/v1/worker/rebalance-recommendation
```

---

## 12. Backend EC2 Terminate Logic

> **Source:** Step 0 of `execute_rebalancing()` in `auto_rebalancer.py`, after all Phase 2 agent actions complete.

### 12.1 When

Runs in `execute_rebalancing()` Step 0 (~L2330), after all Phase 2 agent actions (CORDON + DRAIN) complete and readiness verification passes.

### 12.2 Pre-Checks

```
1. Replacement spot alive: verify replacement instance state != terminated/shutting-down
2. Source OD still running: verify source instance state still running
3. Readiness verified: all evicted pods rescheduled on new nodes
```

### 12.3 Credential Resolution

```
1. Load platform AWS credentials from SystemConfig
2. STS AssumeRole into cluster's aws_role_arn (5 retries, exponential backoff)
3. Fallback: direct platform credentials if STS fails
4. All calls use the assumed-role credentials
```

### 12.4 ASG Path (`termination_mode = "scaledown"`)

```
1. Pre-decrement MinSize by 1
   → describe_auto_scaling_group() to get current Min
   → update_auto_scaling_group(MinSize = current_min - 1)
   → This prevents ASG from blocking terminate when desired == min

2. terminate_instance_in_auto_scaling_group(
       InstanceId = "i-xxx",
       ShouldDecrementDesiredCapacity = True
   )
   → AWS simultaneously: terminates EC2 + decrements ASG desired by 1
   → Example: Desired 1 → 0, Min 0 → instance terminated, no replacement

3. Retry: 3 attempts on throttling with 2s backoff
   → STS AssumeRole: 5 retries with exponential backoff

4. Fallback: On ValidationError (instance already removed from ASG)
   → Direct ec2.terminate_instances(InstanceIds=["i-xxx"])
```

### 12.5 Direct EC2 Path (`termination_mode = "karpenter"`)

```
1. ec2.terminate_instances(InstanceIds=["i-xxx"])
2. Karpenter detects NodeClaim gone → no replacement (consolidation)
```

### 12.6 Post-Terminate

```
1. Verification: 2s sleep → describe_instances → check state = terminated/shutting-down
2. DB Update: Instance.state = 'terminated' (with row lock)
3. DB Update: RebalancingAction.status = 'completed', duration_seconds calculated
4. Savings: Write realized_savings_hourly_usd, realized_savings_monthly_usd directly on action
5. Trigger: calculate_real_savings.delay() for cluster-wide recalculation
6. Cleanup: _cleanup_rebalancing_resources() (L1964)
7. Post-success: remove do-not-disrupt annotation, launch standby if configured
8. Invalidate: cluster_coverage:{cluster_id} cache
9. Record: pool reputation (success via report_launch_success())
```

---

## 13. Rollback & Recovery

> **Key functions:** `_do_rollback_uncordon_and_terminate()` (L1786), `_do_rollback_terminate_orphan_spot()` (L1820), `_cleanup_rebalancing_resources()` (L1964)

### 13.1 CORDON Failure Rollback

```
1. Queue UNCORDON_NODE agent action (restore node to schedulable)
2. Terminate orphan spot via _do_rollback_terminate_orphan_spot() (L1820)
3. Set failure backoff: min(300 × 2^n, 3600) seconds
4. Acquire stabilization lock (60s — prevents immediate retry)
5. Mark action FAILED
```

### 13.2 DRAIN Failure Rollback

```
1. Guard: If TERMINATE already completed (parallel agent race), treat as partial success
2. Call _do_rollback_uncordon_and_terminate() (L1786): UNCORDON + terminate orphan spot
3. Same backoff + stabilization lock
4. Mark action FAILED or DRAIN_TIMEOUT
```

### 13.3 Replacement Dead

```
If replacement spot instance dies before OD can be terminated:
  1. Detect: replacement instance state = terminated/shutting-down
  2. ABORT the action
  3. Queue UNCORDON for OD node (restore service)
  4. _cleanup_rebalancing_resources() (L1964)
  5. Mark action FAILED
```

### 13.4 Zombie EC2 (Z4)

```
CORDON failed with NOT_FOUND (K8s node gone, EC2 still running):
  1. Terminate zombie EC2 directly via ec2.terminate_instances
  2. Terminate orphan replacement spot
  3. _cleanup_rebalancing_resources()
```

### 13.5 Phase 2 Expired (Agent Restarted)

```
All CORDON/DRAIN/TERMINATE agent actions expired (agent pod restarted mid-action):
  1. Check source EC2 state in AWS
  2. If terminated: auto-complete (migration succeeded in real world)
  3. If still running: delete expired actions, re-queue Phase 2 fresh
```

### 13.6 Stale Action Recovery

```
Action stuck > 45 minutes:
  1. Mark FAILED
  2. Terminate orphan spot EC2
  3. Clear spot:node_active_action lock
  4. Cleanup all resources
```

---

## 14. Cooldowns & Locks

### 14.1 Cooldown Hierarchy

```
Layer 1: Cluster-level (60 min default, configurable)
  → After any action completes, entire cluster cooling

Layer 2: Per-instance (24h success, exponential failure)
  → 24h after successful replacement
  → min(300 × 2^n, 3600)s after failure (5min → 10min → 20min → ... → 1hr)

Layer 3: Pool-level (2h after pool failure)
  → Prevents reusing known-bad pools

Layer 4: Stabilization (60s)
  → Short pause after action for cluster to settle

Layer 5: Daily cap (max_rebalances_per_24h, default 5)
  → Prevents runaway replacement cycles

Layer 6: Node pool sync cooldown (30 min)
  → Prevents Karpenter NodePool churn

Layer 7: Launch block (30 min)
  → Blocks specific instance_type:az combos that failed to join K8s
```

### 14.2 Lock Hierarchy

```
Global:
  HeartbeatLock("lock:workers.auto_rebalancer") — 300s, 150s heartbeat
  → Only 1 celery worker runs the rebalancer at a time

Per-Cluster:
  spot:rebalance_lock:{cluster_id} — 2700s, 60s heartbeat
  → Only 1 action executing per cluster

  lock:node_action:{cluster_id} — 1200s
  → Only 1 drain operation per cluster

Per-Node:
  spot:node_active_action:{instance_id} — 86400s
  → Only 1 action targeting a specific node

Per-Replacement:
  spot:replacement_claimed:{instance_id} — 3600s
  → Only 1 action can claim a specific spot node as replacement

Concurrency Semaphore:
  rebalance:active_count:{cluster_id} — INCR/DECR, 300s safety TTL
  → Limits parallel actions to max_concurrent_rebalance_actions
```

### 14.3 CooldownController Service

> **Source:** `backend/services/cooldown_controller.py` (~490 lines) — Class `CooldownController`

**Constants:**
| Name | Value |
|------|-------|
| `DEFAULT_CLUSTER_COOLDOWN_MIN` | 60 (1 hour) |
| `DEFAULT_POOL_COOLDOWN_MIN` | 120 (2 hours) |
| `COOLDOWN_POOL_SWITCH_MIN` | 30 |
| `COOLDOWN_RESIZE_MIN` | 360 (6 hours) |
| `COOLDOWN_SUBSTITUTE_MIN` | 120 (2 hours) |
| `STABILIZATION_LOCK_TTL` | 60 (1 minute) |

Three backed storage layers:
1. **Redis** — primary (fast reads)
2. **DB `system_configs`** — write-through via `_persist_cooldown()` (survives Redis restart)
3. **Re-hydration** — `_rehydrate_from_db()` on cache miss. Also persists to `ClusterCooldownState` table

**Key methods:**
| Method | Purpose |
|--------|---------|
| `can_switch()` | Cluster cooldown check (with DB rehydration) |
| `can_reuse_pool()` | Pool failure cooldown check |
| `record_switch()` | Set cluster cooldown (with DB write-through) |
| `record_pool_failure()` | Set pool cooldown |
| `override_for_emergency()` | Delete cluster cooldown |
| `get_cluster_cooldown_status()` | UI status dict |
| `can_resize()` | 6h resize cooldown check |
| `record_resize_action()` | Set resize cooldown |
| `record_pool_switch_action()` | Set pool switch cooldown |
| `record_substitute_action()` | Set substitute cooldown |
| `get_action_cooldown_status()` | Comprehensive action status dict |
| `acquire_stabilization_lock()` | 60s lock with DB persistence to `ClusterCooldownState` |
| `is_stabilization_locked()` | Check stabilization lock |
| `release_stabilization_lock()` | Early release |

Types managed:
- `CLUSTER`: 60 min default
- `POOL`: 120 min default
- `POOL_SWITCH`: 30 min
- `RESIZE`: 360 min (6 hours)
- `SUBSTITUTE`: 120 min (2 hours)

---

## 15. Stale Action Monitor

> **Source:** Runs at the start of `execute_rebalancing()` (~L2222), every 15-second cycle.

### 15.1 Global Timeout

```
Query: RebalancingAction WHERE status IN (in_progress, waiting_agent)
       AND started_at < NOW() - 45 minutes
Action: Mark FAILED, terminate orphan spot, cleanup
```

### 15.2 Per-State Timeouts

```python
# auto_rebalancer.py ~L2232
_STATE_TIMEOUTS_MIN = {
    'in_progress':              45,
    'waiting_agent':            10,
    'waiting_for_spot_node':    28,
    'cordoning_node':           10,
    'draining_pods':            20,
    'verifying_pod_readiness':  20,
    'terminating_source':       10,
}
```

For actions within the 45-min window, checks `current_step` against these limits.

### 15.3 Action Heartbeat

```
Redis key: action_heartbeat:{action_id} (TTL 120s)
Set by: Agent during action execution (every 30s)
Set by: Rebalancer during Phase 1 (every 15s cycle)
Check: If heartbeat key expired (>2 min since last), action considered stale
```

### 15.4 Resource Cleanup on Stale

> **Source:** `_cleanup_rebalancing_resources()` (L1964)

```
1. Delete trigger pod (if exists) via KarpenterService.delete_spot_trigger_pod() (L1383)
2. Cancel PENDING agent actions (prevent agent from picking up stale work)
3. Release spot:replacement_claimed lock
4. Release spot:node_active_action lock
5. DECR rebalance:active_count semaphore
6. Remove Phase-1 injected types from ALL patched NodePools
   (iterates karpenter_patched_nodepools list from metadata)
7. Clear NodePool sync cooldown (spot:karpenter:nodepool_updated) so background sync resumes
8. Terminate orphan spot EC2 (if replacement was launched) via _do_rollback_terminate_orphan_spot() (L1820)
```

---

## 16. Savings Calculation

### 16.1 At Decision Time

```python
source_od_price_hr = pricing_helper.get_ec2_price(region, source_type)
target_spot_price_hr = pricing_helper.get_spot_price(region, target_type, target_az)
estimated_savings_hr = max(od_price - spot_price, 0.0)
estimated_savings_mo = estimated_savings_hr * 730  # hours/month
```

### 16.2 At Completion

```python
actual_spot_price_hr = pricing_helper.get_spot_price(region, actual_type, actual_az)
realized_savings_hr = max(source_od_price_hr - actual_spot_price_hr, 0.0)
realized_savings_mo = realized_savings_hr * 730
realized_savings_pct = (realized_savings_hr / source_od_price_hr) * 100
savings_gap_hr = estimated_savings_hr - realized_savings_hr  # positive = less than expected
```

### 16.3 Post-Action

Triggers `calculate_real_savings.delay()` Celery task for cluster-wide recalculation. Invalidates `cluster_coverage:{cluster_id}` cache.

---

## 17. UI & API Endpoints

### 17.1 Rebalancing API

> **Source:** `backend/api/ascpai_routes.py` — prefix `/ascpai`

| Method | Endpoint | Line | Description |
|--------|----------|------|-------------|
| `GET` | `/ascpai/rebalancing/status` | L523 | List rebalancing actions with full step timeline |
| `POST` | `/ascpai/rebalancing-actions/{id}/approve` | L598 | Approve pending_approval → in_progress |
| `POST` | `/ascpai/rebalancing-actions/{id}/deny` | L624 | Deny action → failed |
| `GET` | `/ascpai/clusters/{id}/effective-configuration` | L121 | Computed config including auto_rebalance ON/OFF |
| `POST` | `/ascpai/pools/rankings` | L197 | Trigger pool ranking |
| `GET` | `/ascpai/blacklist` | L407 | List blacklisted pools |
| `GET` | `/ascpai/v3/cooldown/{cluster_id}` | L1199 | Cooldown status |
| `GET` | `/ascpai/v3/diversity/{cluster_id}` | L951 | Fleet diversity metrics |
| `GET` | `/ascpai/v3/state-machine/{cluster_id}` | L975 | State machine status |
| `GET` | `/ascpai/v3/workload-status/{cluster_id}` | L1225 | WorkloadInspector classification |
| `GET` | `/ascpai/v3/substitute/{cluster_id}` | L1266 | Substitute manager status |
| `GET` | `/ascpai/clusters/{id}/node-recommendations` | L1387 | Per-node alternative pools |
| `GET` | `/ascpai/volatility/status` | L1320 | Market volatility regime |
| `GET` | `/ascpai/interruption-heatmap` | L661 | Interruption heatmap |
| `GET` | `/ascpai/savings-velocity` | L762 | Savings velocity metrics |

### 17.2 Agent Action API

> **Source:** `backend/routers/actions.py` — prefix `/api/v1/actions`

| Method | Endpoint | Line | Description |
|--------|----------|------|-------------|
| `GET` | `/api/v1/actions/poll?cluster_id=` | L23 | Agent polls for PENDING actions → marks PICKED_UP |
| `POST` | `/api/v1/actions/{action_id}/result` | L73 | Agent reports completion result |
| `POST` | `/api/v1/actions/` | L118 | Create new action |
| `GET` | `/api/v1/actions/{action_id}` | L170 | Get action by ID |

### 17.3 Rebalancing Status Response

```json
{
  "id": 261,
  "cluster_id": "4fab64...",
  "status": "waiting_agent",
  "trigger": "auto_rebalance",
  "source_pool": "t3.medium:ap-south-1a",
  "target_pool": "c7g.medium:ap-south-1c",
  "started_at": "2026-04-06T10:38:20Z",
  "completed_at": null,
  "duration_seconds": null,
  "current_step": "waiting_for_spot_node",
  "instance_id": "i-0cde42e5f90ba7271",
  "provisioner_type": "karpenter",
  "replacement_spot_instance_id": null,
  "actual_instance_type": null,
  "actual_az": null,
  "step_1": "2026-04-06T10:38:22Z",
  "step_1_verified": true,
  "step_2": null,
  "step_3": null,
  "step_4": null,
  "step_5": null,
  "step_6": null,
  "realized_savings_hr": null,
  "realized_savings_mo": null,
  "error_message": null
}
```

### 17.4 Frontend Components

| Component | File | Function |
|-----------|------|----------|
| `ClusterDetails` | `frontend/src/components/clusters/ClusterDetails.jsx` | Main cluster view with rebalancing toggle, `NodeConditionBadge` sub-component (conditions: `REBALANCING`, `AWAITING_SPOT`, `REBALANCE:RISK_HIGH`, `REBALANCE:BETTER_POOL`, `STABLE`), tracks in-flight node instance IDs |
| `PoolRankings` | `frontend/src/components/ascpai/PoolRankings.jsx` | Two tabs: per-node and cluster-wide. Shows ML-scored pools with family distribution, blacklist, coverage data. Calls `ascpaiAPI.getRankings()` |
| `AutoRebalanceAuditCard` | `frontend/src/components/ascpai/AutoRebalanceAuditCard.jsx` | Toggle for `auto_rebalance_enabled`, circuit breaker state, approve/deny pending actions, opens `AutoRebalanceAuditModal` |
| `AutoRebalanceAuditModal` | `frontend/src/components/ascpai/AutoRebalanceAuditModal.jsx` | Full execution history with status badges (`completed`, `failed`, `in_progress`, `pending_approval`, `deferred`, `waiting_agent`) and trigger badges (`emergency`, `auto`) |
| `RebalancingTimeline` | `frontend/src/components/ascpai/RebalancingTimeline.jsx` | 6-step pipeline visualization with live countdown timers, cooldown tracking, daily limit info. Reused in 3 places: `ASCPAiPage`, `RightSizingDashboard`, `RightSizingKarpenterTab` |
| `RightSizingDashboard` | `frontend/src/components/right-sizing/RightSizingDashboard.jsx` | `<AutoModeBanner>` sub-component showing toggle state, renders `<RebalancingTimeline actions={rebalancingActions} />` |
| `RightSizingKarpenterTab` | `frontend/src/components/right-sizing/RightSizingKarpenterTab.jsx` | Karpenter-specific view with `StatelessDetailedDrawer` and `StatefulProposalModal` sub-components |

### 17.5 Adaptive Polling

> **Source:** `frontend/src/hooks/useAdaptivePolling.js`

The frontend uses `useAdaptivePolling` hook:
- **Params:** `{ fetchFn, isActive, fastMs=5000, slowMs=30000 }`
- When `isActive=true` (action is `in_progress` or `waiting_agent`): polls at `fastMs` (5s)
- When `isActive=false`: reverts to `slowMs` (30s)
- Cleans up timer on unmount; uses refs to avoid re-scheduling on every render

### 17.6 Frontend API Service

> **Source:** `frontend/src/services/api.js` — `ascpaiAPI` and `clusterAPI` objects

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `ascpaiAPI.getRankings()` | `POST /api/v1/ascpai/pools/rankings` | ML-scored pool recommendations |
| `ascpaiAPI.getRebalancingStatus()` | `GET /api/v1/ascpai/rebalancing/status` | Rebalancing action list |
| `ascpaiAPI.approveRebalancingAction()` | `POST /api/v1/ascpai/rebalancing-actions/{id}/approve` | Approve pending action |
| `ascpaiAPI.denyRebalancingAction()` | `POST /api/v1/ascpai/rebalancing-actions/{id}/deny` | Deny pending action |
| `ascpaiAPI.getRebalancingContext()` | `GET /api/v1/ascpai/v3/rebalancing-context/{clusterId}` | Cooldown + next target data |
| `clusterAPI.toggleAutoRebalance()` | `PATCH /api/v1/clusters/{id}/auto-rebalance` | Enable/disable auto-rebalancing |

### 17.7 Step Timeline in UI

```
Step 1: NodePool Updated       → Karpenter NodePool patched, trigger pod created
Step 2: New Node Joined        → Replacement spot Ready in K8s  
Step 3: Node Cordoned          → Node marked unschedulable
Step 4: Pods Drained           → Pods evicted and rescheduled
Step 5: Old Node Terminated    → OD instance terminated, ASG decremented
Step 6: Complete               → Savings calculated, cleanup done
```

> Maps step keys to backend `current_step` values via `STEP_CURRENT_MAP` in `RebalancingTimeline.jsx`

Each step has a timestamp and verified flag (agent confirmed the operation).

---

## 18. Karpenter Service (K8s NodePool Management)

> **Source:** `backend/services/karpenter_service.py` (~1408 lines) — Class `KarpenterService` (L37)
> **Constants:** `FALLBACK_TTL_SECONDS = 43200`, `MAX_PATCH_RETRIES = 2`, `RETRY_DELAYS = [5, 15]`

### 18.1 Key Methods

| Method | Line | Return | Purpose |
|--------|------|--------|---------|
| `add_allowed_instance_type_all_spot()` | L948 | `(bool, list[str])` | Phase 1: Add target type to ALL spot-capable NodePools |
| `add_allowed_instance_type()` | L981 | `bool` | Add type to specific NodePool |
| `remove_allowed_instance_type()` | L1141 | `bool` | Remove type from specific NodePool |
| `sync_ml_rankings_to_nodepool()` | L47 | `Dict` | Background: write ML-ranked types |
| `switch_to_ondemand()` | L102 | `Dict` | Emergency fallback: spot → on-demand (12h auto-revert) |
| `revert_to_spot()` | L249 | `Dict` | Revert from on-demand back to spot |
| `is_in_fallback_mode()` | L316 | `bool` | Check `spot:ondemand_fallback:{cluster_id}` |
| `create_spot_trigger_pod()` | L1236 | `bool` | Create trigger pod for Karpenter provisioning |
| `delete_spot_trigger_pod()` | L1383 | `bool` | Cleanup trigger pod |
| `_get_k8s_client()` | L577 | K8s client | STS AssumeRole → EKS token (SigV4 presigned URL) → K8s API client |
| `_final_capacity_check()` | L329 | `Optional[Dict]` | DryRun per-pool capacity validation (ARM64-aware AMI lookup via SSM) |
| `_check_circuit_breaker()` | L479 | `bool` | Per-cluster failure circuit breaker (10 failures in 10 min → 30 min trip) |
| `_record_execution_failure()` | L500 | - | Increment `spot:exec_fail_window:{cluster_id}` |
| `_get_nodepool_state()` | L514 | `Optional[Dict]` | Snapshot NodePool spec for rollback |
| `_restore_nodepool_state()` | L537 | - | Rollback NodePool to snapshot (logs CRITICAL on failure) |
| `detect_karpenter_in_cluster()` | L833 | `dict` | K8s detection of Karpenter pods |
| `get_nodepool_status()` | L793 | `Dict` | Get NodePool details |
| `_update_nodepool()` | L676 | `bool` | Internal: full NodePool CRUD with circuit breaker + rollback |
| `_get_eks_token()` | L647 | `str` | SigV4 presigned URL to STS GetCallerIdentity |
| `patch_node_pool_allowed_types()` | L1213 | `dict` | Batch-update NodePool allowed types |

### 18.2 NodePool Patch Flow (`_update_nodepool()`, L676)

```
1. Check circuit breaker (_check_circuit_breaker(), L479) → raise if active
2. Derive architecture list from instance type families
3. Build NodePool spec (apiVersion: karpenter.sh/v1)
4. Snapshot current state: _get_nodepool_state() (L514)
5. GET existing NodePool via CustomObjectsApi.get_cluster_custom_object()
6. If exists → PATCH. On failure: _restore_nodepool_state() (L537) + _record_execution_failure() (L500) + re-raise
7. If 404 → CREATE new NodePool → return False
8. Non-blocking retries: attempt once, raise on failure (Enhancement 8 — caller retries next cycle)
```

### 18.3 `_get_k8s_client()` Details (L577)

```
1. Fetch Account for the cluster
2. Get platform credentials via _get_backend_credentials() (L636)
3. Generate EKS token via _get_eks_token() (L647) — SigV4 presigned URL to STS GetCallerIdentity
4. Configure client.Configuration() with bearer token
5. Handle CA cert: base64 decode cluster.ca_data, write to temp file
6. Fallback: verify_ssl = False if CA decode fails or ca_data is null
```

### 18.4 NodePool Structure

Created by `ActionActuator.install_karpenter()` (L812) → `_create_default_karpenter_resources()` (L888):

| NodePool | Capacity Type | Weight | Consolidation |
|----------|--------------|--------|---------------|
| `stateless-spot` | spot | 10 (preferred) | WhenEmptyOrUnderutilized |
| `stateful-od` | on-demand | 5 | WhenEmpty |
| `default` | spot + on-demand | 1 (fallback) | WhenEmptyOrUnderutilized |

### 18.5 NodePool Sync Protection

During active rebalancing (`sync_karpenter_nodepools` in `ascpai_worker.py` L244):
```
Guards (checked in order):
  1. cluster_type='EKS', status='ACTIVE'
  2. agent_installed == 'Y'
  3. cluster.karpenter_mode is set
  4. last_heartbeat < 30 min ago
  5. IF active rebalancing action exists (status IN ('in_progress', 'waiting_agent')):
     → SKIP sync (log: "Skipping NodePool sync — active rebalance action #X")
     → This prevents overwriting the rebalancer's Phase 1 NodePool patch
```

After action completes:
```
_cleanup_rebalancing_resources() (L1964):
  → Remove Phase-1 injected types from ALL patched NodePools
    (iterates karpenter_patched_nodepools list from metadata)
  → Clear spot:karpenter:nodepool_updated cooldown
  → Background sync will restore ML-ranked types on next cycle
```

---

## 19. WorkloadInspector (Node Classification)

> **Source:** `backend/services/workload_inspector.py` — Class `WorkloadInspector` (L29)
> **Also:** Copied in `ml_model/decision_engine/04_workload_classifier.py` (L113) for inline decision engine use.

### 19.1 Purpose

Classifies each node using `NodeStatus` enum with 4 states:
- `STATELESS_ELIGIBLE` — safe for spot migration
- `STATEFUL_PROTECTED` — StatefulSet/PV-backed pods (blocked)
- `DRAIN_UNSAFE` — host networking/host PID pods
- `SYSTEM_PROTECTED` — system-level pods

Prevents the rebalancer from targeting nodes with StatefulSet pods, PersistentVolume-backed pods, or pods with host networking / host PID.

### 19.2 Cache

```
Key: spot:node_classification:{cluster_id}
TTL: 540s (9 min — Issue 3a fix)
Value: JSON map of {node_name: "STATELESS_ELIGIBLE" | "STATEFUL_PROTECTED" | "DRAIN_UNSAFE" | "SYSTEM_PROTECTED"}
Source: WorkloadInspector.scan_cluster() — scheduled by APScheduler job_scan_clusters() every 10 min
```

### 19.3 Inline Fallback

> **Source:** `auto_rebalancer.py` ~L5760

```
If cache absent (TTL expired or worker restart):
  1. Obtain K8s client: KarpenterService._get_k8s_client(cluster) (L577)
  2. Run WorkloadInspector(redis=redis, k8s_client=_wi_k8s).scan_cluster(cluster_id) inline
  3. If scan returns results: cache and proceed
  4. If scan fails (K8s unreachable):
     → Treat ALL OD nodes as STATELESS_ELIGIBLE (safe default)
     → Cache this default for 300s
     → Log warning: "Treating all OD nodes as STATELESS_ELIGIBLE"
```

### 19.4 Node Filtering

```
For each OD instance (in auto_rebalancer.py Step 1):
  classification = cache.get(instance.node_name)
  if classification in ("STATEFUL_PROTECTED", "DRAIN_UNSAFE", "SYSTEM_PROTECTED"):
    → Skip (do not target for spot migration)
  if classification is None (not in cache):
    → Skip (newly joined node, wait for classification)
  if classification == "STATELESS_ELIGIBLE":
    → Eligible for rebalancing
```

---

## 20. Spot-to-Spot Rebalancing

> **Source:** Step 1 of `execute_rebalancing()` (~L5900+ in `auto_rebalancer.py`), runs when no OD instances remain.

### 20.1 Purpose

Beyond OD→Spot, the system also migrates between Spot pools for:
- **Diversity violations**: Too many nodes of same family/type
- **Risk threshold**: Current pool interruption risk > ceiling
- **Opportunistic**: Better-scored pool available at lower cost

### 20.2 Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `_S2S_OPP_RISK_DELTA` | `0.05` | S2S opportunistic risk threshold (base) |
| `_S2S_OPP_SAV_DELTA` | `0.01` | S2S opportunistic savings threshold (base) |
| `_MAX_AZ_SHARE` | `0.50` | Max 50% of nodes in one AZ |

### 20.2 Triggers

```
1. Diversity Violation:
   → family_pct > max_family_diversification_cap_pct (default 40%)
   → instance_type_count < required by instance_type_diversification_pct

2. Risk Threshold:
   → Current pool risk > risk_ceiling_percent from strategy
   → ML score indicates elevated interruption probability

3. Opportunistic:
   → New pool scored significantly better by ML model
   → Cost savings > min_savings_percent threshold
```

### 20.3 S2S Dedup

```
Key: s2s_migration:{cluster_id}:{src_type}:{tgt_type}
TTL: 7200s (2h)
Purpose: Prevent infinite migration loop (A→B→A→B...)
```

### 20.4 Target Selection (3-Pass)

```
Pass 1: Different family, cheaper, lower risk
Pass 2: Different type (same family OK), cheaper
Pass 3: Any cheaper pool with capacity
```

---

## 21. End-to-End Flow Diagram

```
                    ┌──────────────────────────────┐
                    │   USER: Enable auto-rebalance │
                    │   PUT /optimization-settings  │
                    └──────────────┬───────────────┘
                                   ▼
              ┌─────────────────────────────────────────────┐
              │         Celery Beat: every 15 seconds        │
              │         execute_rebalancing()                 │
              └──────────────────┬──────────────────────────┘
                                 ▼
              ┌─────────────────────────────────────────────┐
              │  STALE MONITOR: Expire stuck actions (45min) │
              └──────────────────┬──────────────────────────┘
                                 ▼
              ┌─────────────────────────────────────────────┐
              │  STEP 0: Resolve waiting_agent actions       │
              │  ├─ Check agent action completion             │
              │  ├─ Wait for spot to join K8s                 │
              │  ├─ Ghost fast-path detection                 │
              │  ├─ Create Phase 2 (CORDON→DRAIN→TERMINATE)   │
              │  ├─ Readiness verification post-drain         │
              │  ├─ Backend EC2 terminate                     │
              │  └─ Savings calculation + cleanup             │
              └──────────────────┬──────────────────────────┘
                                 ▼
              ┌─────────────────────────────────────────────┐
              │  STEP 1: Cluster loop                        │
              │  For each cluster:                           │
              │  ├─ Gates: hibernation, interval, cooldown    │
              │  ├─ AWS sync (instance state from EC2 API)   │
              │  ├─ Find ON_DEMAND instances                  │
              │  ├─ Filter: cooldown, classification, exposure│
              │  ├─ Pool selection (ML rank → 3-pass gate)   │
              │  └─ Create RebalancingAction (in_progress)   │
              └──────────────────┬──────────────────────────┘
                                 ▼
              ┌─────────────────────────────────────────────┐
              │  STEP 2: Execute new in_progress actions     │
              │  execute_rebalancing_action()                 │
              │  ├─ Safety gates (cooldown, lock, semaphore)  │
              │  ├─ ASG detection                             │
              │  ├─ Architecture filtering                    │
              │  ├─ Dry-run capacity check                    │
              │  ├─ PHASE 1: Karpenter NodePool patch         │
              │  ├─ Set status = waiting_agent                │
              │  └─ Next cycle handles Phase 2 →              │
              └──────────────────┬──────────────────────────┘
                                 ▼
         ┌─────────────────────────────────────────────────────┐
         │  PHASE 1 WAITING (every 15s cycle in Step 0):       │
         │  ├─ 60s: Create trigger pod (workload-aware sizing) │
         │  ├─ Karpenter sees Pending pod → launches spot EC2   │
         │  ├─ ESCALATION (baseline=0 stall):                  │
         │  │  ├─ 5min: switch to 2nd alternative type          │
         │  │  ├─ 10min: switch to 3rd alternative type         │
         │  │  └─ 15min: broaden to any NodePool type           │
         │  ├─ Node joins K8s → status READY → spot_count++     │
         │  ├─ ID-first, ID-set-diff, or count-based detection  │
         │  └─ Timeout: 30 min → fail action                   │
         └───────────────────────┬─────────────────────────────┘
                                 ▼
         ┌─────────────────────────────────────────────────────┐
         │  PHASE 2 CREATION (in Step 0):                       │
         │  ├─ Atomic claim on replacement spot                 │
         │  ├─ Delete trigger pod                               │
         │  ├─ Annotate replacement: do-not-disrupt=true        │
         │  ├─ K8s node verification (ghost detection)          │
         │  └─ Create AgentActions: CORDON → DRAIN → TERMINATE  │
         └───────────────────────┬─────────────────────────────┘
                                 ▼
         ┌─────────────────────────────────────────────────────┐
         │  AGENT EXECUTION (in-cluster):                       │
         │  ├─ Poll /actions/pending every 10s                  │
         │  ├─ Sort by zero_downtime_step                       │
         │  ├─ CORDON: kubectl cordon + verify                  │
         │  ├─ DRAIN: evict pods (PDB retry) + verify           │
         │  └─ Report results to backend API                    │
         └───────────────────────┬─────────────────────────────┘
                                 ▼
         ┌─────────────────────────────────────────────────────┐
         │  BACKEND TERMINATE (in Step 0, next cycle):          │
         │  ├─ Readiness check (evicted pods Running?)          │
         │  ├─ STS AssumeRole → cluster credentials             │
         │  ├─ ASG: pre-decrement Min, terminate w/ decrement   │
         │  │  OR Direct: ec2.terminate_instances               │
         │  ├─ Verify: EC2 state = terminated                   │
         │  ├─ DB: Instance.state = terminated                  │
         │  └─ Savings calc + cleanup + stabilization lock      │
         └───────────────────────┬─────────────────────────────┘
                                 ▼
         ┌─────────────────────────────────────────────────────┐
         │  POST-ACTION:                                        │
         │  ├─ Set 24h per-instance cooldown                    │
         │  ├─ Increment daily count                            │
         │  ├─ Record pool reputation (success/failure)         │
         │  ├─ Set 60s stabilization lock                       │
         │  ├─ Remove do-not-disrupt annotation                 │
         │  ├─ Remove Phase-1 types from NodePool               │
         │  ├─ Invalidate coverage cache                        │
         │  └─ UI refreshes via adaptive polling                │
         └─────────────────────────────────────────────────────┘
```

---

## 22. Known Issues & Edge Cases

### 22.1 Ghost Node Loop

**Problem:** OD instance running in ASG but not in K8s. Phase 2 fails ("not registered"), ASG auto-replaces with new OD, loop repeats.

**Fix:** Ghost fast-path skips Phase 1 entirely for ASG-backed ghosts. Creates TERMINATE-only action with `ShouldDecrementDesiredCapacity=True`. No replacement spot needed (no workloads to migrate).

### 22.2 Trigger Pod Not Provisioning (Spot Capacity Exhaustion)

**Problem:** Trigger pod stays Pending because Karpenter can't get spot capacity for the target instance type in the selected AZ.

**Possible causes:**
- Spot capacity unavailable for target type in target AZ
- NodePool limits exceeded
- Karpenter controller restarting (leader election)
- EC2 fleet quota exhausted

**Fix (Escalation Logic — see §8.6):** Progressive instance type retry:
- 5 min → switch trigger pod to 2nd ranked alternative type
- 10 min → switch to 3rd alternative type
- 15 min → remove instance-type constraint entirely (Karpenter chooses freely)
- 30 min → timeout and fail (existing behavior)

### 22.3 NodePool Sync Race

**Problem:** `sync_karpenter_nodepools` (every 30s) can overwrite rebalancer's NodePool patch after action completes.

**Mitigation:** Sync is blocked during active `waiting_agent` actions. After completion, `_cleanup_rebalancing_resources()` removes injected types from ALL patched NodePools (iterated from `karpenter_patched_nodepools` metadata) before sync resumes.

### 22.4 Per-State Timeout vs Spot Wait Timeout

**Problem:** `waiting_agent` per-state timeout (10 min) < spot wait timeout (30 min).

**Mitigation:** Per-state timeout only fires if `step_entered_waiting_agent` metadata key exists. Currently not always set, so the 45-min global timeout is the effective limit.

### 22.5 WorkloadInspector Failure

**Problem:** K8s API unreachable → `scan_cluster` returns empty → all nodes classified as `STATELESS_ELIGIBLE`.

**Risk:** Stateful nodes could be targeted for spot migration.

**Mitigation:** This is a conscious safe-default — PDB and drain timeout provide secondary protection for stateful workloads. The inline fallback now obtains a K8s client via `KarpenterService._get_k8s_client(cluster)` and passes it to `WorkloadInspector(k8s_client=...)`.

### 22.6 Concurrent Action Claims

**Problem:** Two actions created simultaneously for different OD nodes but same replacement spot joins.

**Mitigation:** Atomic claim via `Redis SET NX` on `spot:replacement_claimed:{instance_id}`. Second action waits for another spot node.

---

## 23. Bug Fixes & Improvements Log

All fixes implemented and deployed as of 6 April 2026.

### Fix #1: Trigger Pod Wrong NodePool

**Problem:** Trigger pod hardcoded `nodepool_name="default"` instead of targeting the NodePool that Phase 1 actually patched (e.g. `stateless-spot`). Result: trigger pod stuck Pending because `default` NodePool didn't have the target types.

**Root cause:** `add_allowed_instance_type_all_spot()` returned only `bool`; caller had no way to know which NodePools were patched.

**Fix:**
- Changed `add_allowed_instance_type_all_spot()` (L948 of `karpenter_service.py`) to return `(bool, list[str])` — success + names of patched NodePools
- Stores `karpenter_nodepool_name` (first patched) and `karpenter_patched_nodepools` (all) in action metadata
- Trigger pod reads `karpenter_nodepool_name` from metadata instead of hardcoded `"default"`
- `create_spot_trigger_pod()` (L1236) accepts `nodepool_name` parameter
- Cleanup in `_cleanup_rebalancing_resources()` (L1964) iterates `karpenter_patched_nodepools` to remove types from all patched NodePools
- **Files:** `backend/services/karpenter_service.py`, `backend/workers/tasks/auto_rebalancer.py`

### Fix #2: baseline=0 Ambiguity (ID-Set-Diff + Escalation)

**Problem:** When spot_baseline=0, the count-based gate `spot_count > 0` can't distinguish a new replacement spot from a pre-existing spot that appeared via concurrent activity. Also, trigger pod sits Pending for 30 minutes with no retry when target type has no capacity.

**Fix (two parts):**

**Part A — ID-set-diff detection:**
- Phase 1 now stores `baseline_spot_instance_ids` — full list of spot instance IDs at action start
- Count-based fallback queries spots NOT IN baseline ID set, filtered by expected target type
- Works even when baseline=0: any spot not in the empty set is a new spot

**Part B — Escalation logic (§8.6):**
- 5 min: recreate trigger pod targeting 2nd alternative type
- 10 min: recreate targeting 3rd alternative type
- 15 min: recreate with NO type constraint — Karpenter picks any available type
- Progressive log severity: INFO → WARNING (5min) → ERROR (20min)
- **Files:** `auto_rebalancer.py`

### Fix #3: DELETED Enum Crash

**Problem:** `health_monitor.py` queried `Cluster.status != 'DELETED'` but `DELETED` was not a valid value in the `ClusterStatus` Python enum or PostgreSQL `clusterstatus` type, causing crashes.

**Fix:**
- Added `DELETED = "DELETED"` to `ClusterStatus` enum in `backend/models/cluster.py`
- Changed health_monitor query to `Cluster.status.notin_([ClusterStatus.DELETED, ClusterStatus.TERMINATED])`
- Ran `ALTER TYPE clusterstatus ADD VALUE IF NOT EXISTS 'DELETED'` on live DB
- Created migration `backend/migrations/008_add_deleted_to_clusterstatus.py`
- **Files:** `cluster.py`, `health_monitor.py`

### Fix #4: NULL cluster_id Metrics Guard

**Problem:** Agent `/metrics` endpoint could submit metrics batches with `cluster_id=None` when agent starts before cluster registration completes.

**Fix:**
- Added `and cluster_id` guard to the metrics batch insert condition in `backend/routers/metrics.py`
- Guard: `if (pod_metrics or node_metrics or event_metrics) and cluster_id:`
- **Files:** `metrics.py`

### Fix #5: Orphaned Nodes in Fleet View

**Problem:** Fleet view showed orphaned/terminated nodes because filter used `Instance.status.notin_(['UNKNOWN'])` — a blacklist approach that allowed `TERMINATED`, `DELETING`, etc.

**Fix:**
- Changed to whitelist: `Instance.status.in_(['READY', 'CALIBRATING'])` (or `status IS NULL` for newly discovered nodes)
- **Files:** `ascpai_routes.py`

### Fix #6: get_instance_price Missing

**Problem:** `ResourcePricingService` lacked a `get_instance_price()` method that other services expected.

**Fix:**
- Added `get_instance_price(instance_type, region, lifecycle, availability_zone) -> float`
- Wraps existing `calculate_instance_cost(hours=1)` with proper parameter mapping
- **Files:** `resource_pricing_service.py`

### Fix #7: _get_accessible_clusters Missing

**Problem:** `MetricsService._calculate_hibernation_savings()` called `self._get_accessible_clusters(user_id, cluster_id, team_id)` but the method didn't exist.

**Fix:**
- Implemented `_get_accessible_clusters()` using same org-based access pattern as rest of MetricsService:
  - Look up user → organization_id
  - Query Account IDs for that org
  - Query Clusters with `account_id IN (org_accounts)`
  - Optional filter by `cluster_id` parameter
  - `team_id` reserved for future use
- **Files:** `metrics_service.py`

### Fix #8: IAM Scan NoneType Crash

**Problem:** `classify_iam_user(days_inactive=None)` crashed with `TypeError: '<=' not supported between NoneType and int` when a newly created IAM user had no console login AND was created recently (neither `if` branch set `days_inactive`).

**Fix (defense in depth):**
- Caller (`hygiene_service.py`): `if days_inactive is None: continue` — skip new users with no activity
- Callee (`identity_rules.py`): `if days_inactive is None or days_inactive <= DORMANT_USER_DAYS:` — return ACTIVE on None
- **Files:** `hygiene_service.py`, `identity_rules.py`

### Fix #9: ARM64 Dry-Run AMI Mismatch

**Problem:** `_final_capacity_check()` dry-run used the default x86_64 AMI for ARM64 instance types (c7g, m7g, etc.), causing `InvalidParameterCombination` errors from EC2.

**Fix:**
- Added ARM64 family detection (graviton families: m7g, c7g, r7g, m6g, c6g, r6g, t4g, etc.)
- SSM parameter lookup for EKS-optimized AMI: `/aws/service/eks/optimized-ami/{version}/amazon-linux-2-arm64/recommended/image_id`
- Fallback to `DescribeImages` with `architecture=arm64` filter
- Passes resolved `ImageId` to `run_instances` dry-run call
- **Files:** `karpenter_service.py`

### Fix #10: WorkloadInspector No K8s Client

**Problem:** Auto-rebalancer's inline WorkloadInspector call didn't pass K8s credentials, causing `scan_cluster()` to fail with "no K8s client" when the classification cache was cold.

**Fix:**
- Added `KarpenterService._get_k8s_client(cluster)` call before creating WorkloadInspector
- Passes `k8s_client=_wi_k8s` to `WorkloadInspector` constructor
- **Files:** `auto_rebalancer.py`

---

*This document reflects the codebase as of 6 April 2026. All line numbers reference the current version of the files.*
