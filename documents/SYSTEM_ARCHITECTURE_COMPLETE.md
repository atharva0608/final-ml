# ASCP.AI Spot Optimizer — Complete System Architecture

> **Source:** All data in this document is derived exclusively from real code files. No `.md` or `.txt` files were used as sources.

---

## Table of Contents

1. [Cluster Model & Data Schema](#1-cluster-model--data-schema)
2. [Cluster Optimization Settings](#2-cluster-optimization-settings)
3. [Optimization Strategy & Runtime Rules](#3-optimization-strategy--runtime-rules)
4. [Instance Model & Lifecycle](#4-instance-model--lifecycle)
5. [Agent System](#5-agent-system)
6. [Agent Actions — Types & Execution](#6-agent-actions--types--execution)
7. [Karpenter Management](#7-karpenter-management)
8. [Auto-Rebalancer — Complete Flow](#8-auto-rebalancer--complete-flow)
9. [Safety Gates & Locks](#9-safety-gates--locks)
10. [Pool Selection Algorithm (4-Pass)](#10-pool-selection-algorithm-4-pass)
10b. [Karpenter Simulation Engine v2](#10b-karpenter-simulation-engine-v2)
11. [AWS & EKS Operations](#11-aws--eks-operations)
12. [State Management — Database](#12-state-management--database)
13. [State Management — Redis](#13-state-management--redis)
14. [DB ↔ Redis Synchronization](#14-db--redis-synchronization)
15. [Error Handling & Rollback](#15-error-handling--rollback)
16. [Emergency Rebalancer & Spot Interruptions](#16-emergency-rebalancer--spot-interruptions)
17. [Recovery Monitor & Orphan Cleanup](#17-recovery-monitor--orphan-cleanup)
18. [Celery Scheduled Tasks](#18-celery-scheduled-tasks)
19. [UI Components — What Shows Where](#19-ui-components--what-shows-where)
20. [Cost & Savings Calculation](#20-cost--savings-calculation)
21. [Cross-Account AWS Credential Flow](#21-cross-account-aws-credential-flow)

---

## 1. Cluster Model & Data Schema

**Source:** `backend/models/cluster.py` (Lines 27–135)  
**Table:** `clusters`

### Cluster Status Enum

| Value | Description |
|-------|-------------|
| `PENDING` | Awaiting agent connection verification |
| `DISCOVERED` | Found via AWS EKS scan, agent not installed |
| `ACTIVE` | Agent connected and sending heartbeats |
| `INACTIVE` | Agent stopped responding |
| `ERROR` | Fatal configuration/connection error |
| `TERMINATED` | Cluster deleted in AWS |
| `DISCONNECTED` | Agent manually disconnected |
| `DEGRADED` | Agent installed but cluster no longer found in AWS |

### Karpenter Mode Enum

| Value | Description |
|-------|-------------|
| `NULL` | Karpenter not installed/configured |
| `dry_run` | Insights only — ML rankings computed but NodePool NOT patched |
| `auto` | Full autonomous — NodePool updated every hour with ML rankings |

### Cluster Model Fields

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `id` | String(36), PK | UUID | Primary key |
| `name` | String, indexed | — | Cluster name |
| `account_id` | String, FK(accounts.id) | — | Parent account |
| `arn` | String, unique | — | AWS ARN |
| `region` | String | — | AWS region |
| `cluster_type` | Enum(EKS/ECS/GKE/AKS) | `EKS` | Provider type |
| `version` | String | NULL | K8s version |
| `endpoint` | String | NULL | API endpoint URL |
| `ca_data` | Text | NULL | Base64 CA cert for K8s API auth |
| `status` | Enum(ClusterStatus) | `DISCOVERED` | Current status |
| `agent_installed` | String | `"N"` | Y/N flag |
| `is_agentless` | String | `"Y"` | Y/N flag |
| `api_key` | String | NULL | Auto-generated for agent auth |
| `aws_role_arn` | String | NULL | Cross-account IAM role ARN |
| `aws_external_id` | String | NULL | STS external ID |
| `last_heartbeat` | DateTime | NULL | Last agent heartbeat timestamp |
| `monthly_cost` | Integer | `0` | Current monthly cost (USD) |
| `estimated_savings` | Integer | `0` | Estimated cost savings |
| `potential_savings_monthly` | Float | `0.0` | Savings if all OD nodes moved to spot |
| `realized_savings_monthly` | Float | `0.0` | Currently realized savings from spot |
| `on_demand_node_count` | Integer | `0` | On-demand node count |
| `node_count` | Integer | `0` | Total node count |
| `spot_count` | Integer | `0` | Spot node count |
| `cpu_total` | Integer | `0` | Total CPU cores |
| `mem_total` | Integer | `0` | Total memory (GiB) |
| `cpu_usage_pct` | Float | `0.0` | CPU usage % |
| `mem_usage_pct` | Float | `0.0` | Memory usage % |
| `karpenter_mode` | Enum(KarpenterMode) | NULL | Karpenter operating mode |
| `optimization_mode` | String(20) | `"BALANCED"` | COST_FIRST / BALANCED / NO_DOWNTIME_FIRST |
| `model_version` | String(10) | `"6"` | Pinned ML model version |
| `auto_rebalance_enabled` | Boolean | `False` | Master switch for auto rebalancing |
| `rightsizing_enabled` | Boolean | `False` | Master switch for right-sizing |
| `is_hibernating` | Boolean | `False` | Currently in hibernation |
| `is_dismissed` | Boolean | `False` | Prevents re-discovery after user removal |
| `managed_node_group_deleted` | Boolean | `False` | True once EKS managed node group is deleted during Karpenter migration |
| `tags` | JSON | `{}` | Resource tags |
| `inventory_summary` | JSON | `{}` | e.g. `{"total":20,"on_demand":10,"spot":10}` |
| `created_at` | DateTime | `utcnow` | Creation timestamp |
| `updated_at` | DateTime | `utcnow` | Last update |

### Key Relationships

| Relationship | Target | Cardinality |
|-------------|--------|-------------|
| `instances` | Instance | 1-to-many |
| `optimization_settings` | ClusterOptimizationSettings | 1-to-1 |
| `optimization_strategy_profile` | OptimizationStrategy | 1-to-1 |
| `stateless_rules` | StatelessRuntimeRules | 1-to-1 |
| `stateful_rules` | StatefulRules | 1-to-1 |
| `agent_actions` | AgentAction | 1-to-many |
| `pod_metrics` | PodMetric | 1-to-many |
| `rightsizing_proposals` | RightsizingProposal | 1-to-many |
| `template_mappings` | ClusterTemplateMapping | 1-to-many |

---

## 2. Cluster Optimization Settings

**Source:** `backend/models/cluster.py` (Lines 138–228)  
**Table:** `cluster_optimization_settings`

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `cluster_id` | String, PK/FK | — | Cluster reference |
| `auto_rebalance_enabled` | Boolean | `False` | Enable automatic OD→spot migration |
| `auto_rightsizing_enabled` | Boolean | `False` | Enable right-sizing recommendations |
| `auto_stateful_rightsizing_enabled` | Boolean | `False` | Enable stateful node right-sizing |
| `cooldown_override_minutes` | Integer | NULL | Override default cooldown period |
| ~~`spot_join_timeout_minutes`~~ | ~~Integer~~ | ~~NULL~~ | **Removed** — hardcoded to 30 min (Karpenter-only) |
| `manual_approval_required` | Boolean | `False` | Require manual approval for actions |
| `target_spot_exposure_pct` | Integer | `100` | Target % of instances as spot; auto-rebalancer caps OD→Spot conversions to reach but not exceed this target |
| `maintain_standby` | Boolean | `False` | Keep warm standby nodes ready |
| `diversify_pools` | Boolean | `False` | Enforce family/AZ diversification |
| `max_family_diversification_cap_pct` | Integer | `40` | Max % of nodes from same family |
| `instance_type_diversification_pct` | Integer | `100` | Instance type diversification target |
| `failure_cooldown_minutes` | Integer | `30` | Cooldown after failure |
| `instance_aware_rightsizing` | Boolean | `False` | Only recommend if better spot pool exists |
| ~~`max_instance_type_attempts`~~ | ~~Integer~~ | ~~`6`~~ | **Removed** — Karpenter handles instance type selection |
| `min_node_count` | Integer | `1` | Hard floor — never scale below this |
| `scale_down_threshold_pct` | Integer | `20` | Avg utilization below which node is idle |
| `scale_down_stabilization_minutes` | Integer | `15` | Time utilization must stay low before scale-down |
| `enable_ascp_auto_scaler` | Boolean | `False` | Enable built-in auto-scaler |
| `check_interval_seconds` | Integer | `15` | Per-cluster rebalance check interval |
| `architecture_preference` | String(10) | `"both"` | "both" / "amd64" / "arm64" |
| `drain_timeout_minutes` | Integer | `15` | Graceful pod eviction timeout per node |
| `max_concurrent_rebalance_actions` | Integer | NULL | Max parallel rebalances (NULL = 1) |
| `rebalance_batch_percent` | Integer | NULL | Max % of OD nodes to rebalance per cycle (NULL = auto: PDB-safe or 15%) |
| ~~`attach_to_asg_enabled`~~ | ~~Boolean~~ | ~~`False`~~ | **Removed** — ASG attachment not needed with Karpenter |
| `karpenter_only_mode` | Boolean | `False` | When True, all ASG API calls are skipped cluster-wide (Phase 1 ASG detection + Phase 2 termination) |

### API Response-Only Fields (not persisted)

The `GET /clusters/{id}/optimization-settings` endpoint returns these additional computed fields via `UnifiedOptimizationSettings`:

| Field | Type | Purpose |
|-------|------|---------|
| `pdb_safe_percent` | Optional[int] | Max safe batch % based on PodDisruptionBudgets — computed dynamically by `pdb_service.py`, cached in Redis 5 min |

---

## 3. Optimization Strategy & Runtime Rules

### OptimizationStrategy

**Source:** `backend/models/cluster.py` (Lines 230–246)  
**Table:** `optimization_strategy`

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `strategy_type` | String | `"BALANCED"` | COST_FIRST / BALANCED / NO_DOWNTIME_FIRST / CUSTOM |
| `risk_ceiling_percent` | Integer | `25` | Max acceptable interruption risk % |
| `min_savings_percent` | Integer | `15` | Minimum savings % to trigger action |
| `volatility_tolerance_percent` | Integer | `20` | Volatility tolerance |
| `migration_penalty_multiplier` | Float | `1.5` | Migration cost multiplier |
| `diversity_strictness_level` | String | `"Medium"` | Diversity constraint level |
| `risk_savings_tradeoff_pct` | Integer | `20` | Accept pool X% costlier if safer |

### StatelessRuntimeRules

**Source:** `backend/models/cluster.py` (Lines 248–267)  
**Table:** `stateless_runtime_rules`

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `instance_diversification_enabled` | Boolean | `True` | Enable type diversification |
| `respect_pdb_enabled` | Boolean | `True` | Respect Pod Disruption Budgets |
| `prewarm_minutes` | Integer | `0` | Pre-warming time |
| `substitute_strategy` | String | `"PREWARMED"` | PREWARMED or ON_DEMAND substitute |
| `max_rebalances_per_24h` | Integer | `5` | Daily rebalance cap |
| `resize_cooldown_minutes` | Integer | `120` | Cooldown between resizes |
| `resize_headroom_multiplier` | Float | `1.2` | Headroom for sizing |
| `volatility_safety_multiplier` | Float | `1.35` | Safety multiplier for volatile pools |
| `fresh_cluster_stabilization_minutes` | Integer | `1440` | 24h stabilization for new clusters |

### StatefulRules

**Source:** `backend/models/cluster.py` (Lines 269–279)  
**Table:** `stateful_rules`

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `manual_resize_allowed` | Boolean | `True` | Allow manual resizing |
| `require_approval` | Boolean | `True` | Require approval |
| `block_spot_for_stateful` | Boolean | `True` | Block spot for stateful workloads |
| `max_downscale_percent` | Integer | `25` | Max downscale % allowed |

---

## 4. Instance Model & Lifecycle

**Source:** `backend/models/instance.py` (Lines 15–95)  
**Table:** `instances`

### InstanceLifecycle Enum

| Value | Description |
|-------|-------------|
| `SPOT` | `"spot"` — AWS spot instance |
| `ON_DEMAND` | `"on-demand"` — AWS on-demand instance |

### Instance Model Fields

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `id` | String(36), PK | UUID | Internal ID |
| `cluster_id` | String(36), FK | NULL | Cluster reference |
| `account_id` | String(36), FK | NULL | Account reference |
| `instance_id` | String(20), unique | — | AWS instance ID (e.g. i-0abc123) |
| `instance_type` | String(50), indexed | — | EC2 type (e.g. m5.large) |
| `lifecycle` | Enum(InstanceLifecycle) | — | SPOT or ON_DEMAND |
| `az` | String(50), indexed | — | Availability zone |
| `price` | Float | NULL | Hourly price (USD) |
| `cpu_util` | Float | NULL | CPU utilization % |
| `memory_util` | Float | NULL | Memory utilization % |
| `state` | String(20), indexed | `"running"` | Instance state |
| `status` | String(20) | `"READY"` | READY / CALIBRATING / UNKNOWN / TERMINATED |
| `architecture` | String(20) | `"amd64"` | CPU architecture |
| `node_name` | String(255), indexed | NULL | K8s node name |
| `launched_by` | String(50), indexed | NULL | Platform-launched identifier |
| `standby` | Boolean | `False` | Hot standby node (cordoned) |
| `last_heartbeat` | DateTime | NULL | Zombie detection timestamp |

---

## 5. Agent System

### Agent Lifecycle

**Source:** `agent/main.py`, `agent/heartbeat.py`, `agent/websocket_client.py`

| Phase | Action | Endpoint / Mechanism | Source File |
|-------|--------|---------------------|-------------|
| 1. Register | HTTP POST with cluster_id, agent_id, capabilities | `POST /api/v1/agents/register` | `agent/main.py` |
| 2. Initialize | Start 6 components in daemon threads | MetricsCollector, ActionActuator, HeartbeatSender, WebSocketClient, SpotPoller, PodMetricsCollector | `agent/main.py` L216–286 |
| 3. Connect WS | Establish bidirectional WebSocket | `ws://<backend>/ws/cluster/{cluster_id}` | `agent/websocket_client.py` L81–130 |
| 4. Heartbeat | Every 30s health report | `POST /api/v1/agents/heartbeat` | `agent/heartbeat.py` L310–375 |
| 5. Receive Actions | WebSocket push (primary) / HTTP poll (fallback) | WS message or `GET /api/v1/actions/poll` | `agent/actuator.py` L1772–1794 |
| 6. Execute Action | Run action handler (cordon, drain, etc.) | See Section 6 | `agent/actuator.py` L1651–1748 |
| 7. Report Result | Send result via WS or HTTP POST | `POST /api/v1/agents/actions/{id}/result` | `agent/actuator.py` L1796–1821 |
| 8. Monitor | Check thread health every 30s, restart dead threads | Exponential backoff: 2s→4s→8s→16s→32s→60s cap, max 5 restarts | `agent/main.py` L418–454 |
| 9. Shutdown | Stop components, HTTP POST deregister | `POST /api/v1/agents/deregister` | `agent/main.py` L376–416 |

### Agent Health Endpoints

| Endpoint | Port | Purpose |
|----------|------|---------|
| `GET /healthz` | 8080 | Liveness probe |
| `GET /readyz` | 8080 | Readiness probe |
| `GET /metrics` | 8080 | Agent system metrics |

### WebSocket Message Buffering

| Message Type | Queue | Behavior |
|-------------|-------|----------|
| `action_result`, `action_heartbeat`, `action_still_running` | Unbounded (critical) | Never dropped |
| `heartbeat`, `metrics` | Ring buffer (200 max) | Oldest dropped when full |

**Reconnection:** Exponential backoff 1s → 2s → 4s → 8s → max 60s, max 10 attempts

---

## 6. Agent Actions — Types & Execution

**Source:** `backend/models/agent_action.py`, `agent/actuator.py`

### AgentAction Status Enum

| Status | Description |
|--------|-------------|
| `PENDING` | Waiting to be picked up by agent |
| `PICKED_UP` | Agent retrieved but not yet executed |
| `COMPLETED` | Executed successfully |
| `FAILED` | Execution failed |
| `EXPIRED` | Action expired without execution |

### AgentAction Types

| Type | Agent Handler | Purpose | Source Lines |
|------|--------------|---------|-------------|
| `EVICT_POD` | `evict_pod()` | Graceful pod eviction with PDB checks, 5 retries | `agent/actuator.py` L90–211 |
| `CORDON_NODE` | `cordon_node()` | Mark node unschedulable | L213–270 |
| `UNCORDON_NODE` | `cordon_node(uncordon=True)` | Mark node schedulable (rollback) | L1689–1691 |
| `DRAIN_NODE` | `drain_node()` | Cordon → evict all pods (skip DaemonSets) | L334–533 |
| `LABEL_NODE` | `label_node()` | Add/remove K8s node labels; also used by WorkloadInspector to apply `workload=stateless`/`stateful` classification labels | L536–605 |
| `TERMINATE_NODE` | `_terminate_node()` | Terminate EC2 instance (3 modes) | L1051–1394 |
| `FORCE_DELETE_NODE` | `force_delete_node()` | Delete K8s Node object + clear stuck finalizers | L272–332 |
| `UPDATE_DEPLOYMENT` | `update_deployment()` | Update replicas or container image | L608–672 |
| `PATCH_CONTAINER_RESOURCES` | `_patch_container_resources()` | Right-sizing: patch CPU/memory requests+limits | L1057–1137 |
| ~~`PATCH_KARPENTER_NODEPOOL`~~ | — | **Removed** — NodePool is now patched directly via K8s API in `KarpenterService.add_allowed_instance_type()` | — |
| `INSTALL_KARPENTER` | `install_karpenter()` | Helm install + create NodePool/EC2NodeClass | L829–956 |
| `UNINSTALL_KARPENTER` | `uninstall_karpenter()` | Helm uninstall + namespace cleanup | L1396–1433 |
| `REMOVE_POD_FINALIZERS` | (in force_delete_node) | Remove stuck finalizers from Terminating pods | L310–331 |

### TERMINATE_NODE Modes

| Mode | Behavior |
|------|----------|
| `karpenter` | Karpenter-friendly: delete K8s Node object → Karpenter handles EC2 |
| `replacement` | Direct EC2 terminate (for platform-launched instances) |
| `scaledown` | Terminate + decrement ASG desired capacity |
| `asg_no_decrement` | Terminate without changing ASG capacity |

### AgentAction Model Fields

| Field | Type | Purpose |
|-------|------|---------|
| `id` | String(36), PK | UUID |
| `cluster_id` | String(36), FK | Cluster reference |
| `action_type` | Enum(AgentActionType) | Action to execute |
| `payload` | JSONB | Action-specific parameters |
| `status` | Enum(AgentActionStatus) | Current status |
| `priority` | Integer | 0=normal, 10=emergency |
| `created_at` | DateTime | Created timestamp |
| `expires_at` | DateTime | Default +1 hour |
| `picked_up_at` | DateTime | When agent picked up |
| `completed_at` | DateTime | When completed |
| `result` | JSONB | Success result details |
| `error_message` | String(1024) | Failure message |

---

## 7. Karpenter Management

**Source:** `backend/services/karpenter_service.py`, `backend/api/karpenter_routes.py`, `agent/actuator.py`

### Karpenter API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/karpenter/status` | GET | Overall Karpenter deployment status |
| `/karpenter/config` | GET | Get cluster Karpenter config |
| `/karpenter/config` | POST | Save Karpenter config |
| `/karpenter/config/{cluster_id}` | PATCH | Update config + sync toggles to DB |
| `/karpenter/deploy` | POST | Deploy Karpenter to clusters |
| `/karpenter/toggle/{cluster_id}` | POST | Pause/resume Karpenter |
| `/karpenter/activity` | GET | Recent optimization events |
| `/karpenter/stats` | GET | Weekly/monthly performance KPIs |
| `/karpenter/recommendations` | GET | Pending dry-run recommendations |

### KarpenterService Methods

| Method | Purpose | Redis Keys | Source Lines |
|--------|---------|-----------|-------------|
| `sync_ml_rankings_to_nodepool()` | Sync ML-ranked types to NodePool CRD | — | L53–113 |
| `switch_to_ondemand()` | Force NodePool to on-demand (no safe spot pools) | `spot:ondemand_fallback:{cid}` (12h TTL) | L115–250 |
| `revert_to_spot()` | Revert from on-demand back to spot | Deletes `spot:ondemand_fallback:{cid}` | L252–331 |
| `is_in_fallback_mode()` | Check if cluster is in OD fallback | Check `spot:ondemand_fallback:{cid}` | L333–337 |
| `detect_karpenter_in_cluster()` | Detect Karpenter installation (NodePool CRD check) | `karpenter:detected:{cid}` (300s), `spot:karpenter:installed:{cid}` (3600s) | L818–863 |
| `patch_node_pool_allowed_types()` | Direct K8s API NodePool patch (no agent action) | — | L943+ |
| `add_allowed_instance_type()` | Add single instance type to NodePool via K8s CustomObjectsApi | — | L865–941 |
| `get_nodepool_status()` | Get current NodePool instance types, capacity, AZs | — | L769–816 |
| `_update_nodepool()` | Internal: actually patch/create NodePool | Circuit breaker keys | L663–767 |

### Karpenter Installation — 6 Steps

**Source:** `agent/actuator.py` L829–956

| Step | Action | Detail |
|------|--------|--------|
| 1 | Helm Chart Install | `helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter --wait --timeout 5m` |
| 2 | SQS Queue Config | `KarpenterInterruptionQueue-{cluster_name}` for spot interruption handling |
| 3 | IRSA Setup | ServiceAccount annotation `eks.amazonaws.com/role-arn={iam_role_arn}` |
| 4 | Access Entry | Register `KarpenterNodeRole-{cluster_name}` as EC2_LINUX access entry |
| 5 | EC2NodeClass | Create default with AL2023 amiFamily (dual-arch, auto-resolves amd64/arm64) |
| 6 | Dual NodePools | Creates 3 NodePools: `stateless-spot` (spot-only, weight=10, label workload=stateless), `stateful-od` (on-demand-only, weight=5, label workload=stateful), `default` (both types, weight=1, fallback) |

### Karpenter Uninstallation — 2 Steps

**Source:** `agent/actuator.py` L1396–1433

| Step | Action |
|------|--------|
| 1 | `helm uninstall {release_name} --namespace {namespace} --wait --timeout 3m` |
| 2 | Delete karpenter namespace (best-effort) |

### What Happens When Karpenter is Installed

| Event | System Behavior | Source |
|-------|----------------|--------|
| ML rankings computed (every 30 min) | Top 10 pools cached in Redis `global_pool_rankings:{region}` | `pool_ranking_service.py` |
| Hourly sync task fires | `sync_ml_rankings_to_nodepool()` patches NodePool CRD with top ML types | `karpenter_service.py` L48–105 |
| Auto-rebalancer selects target | Directly updates NodePool via `KarpenterService.add_allowed_instance_type()` — no agent action needed | `auto_rebalancer.py` |
| Karpenter controller sees NodePool update | Provisions new spot instance from ML-approved type list | Kubernetes-native |
| Emergency spot interruption | Clear cooldowns → blacklist pool → CORDON source → Karpenter auto-provisions replacement | `emergency_rebalancer.py` L95–102 |
| No safe spot pools exist | `switch_to_ondemand()` patches NodePool capacity-type to on-demand, auto-reverts after 12h | `karpenter_service.py` L108–202 |

### NodePool CRD Patching — Retry & Rollback

| Parameter | Value |
|-----------|-------|
| Max Patch Retries | 2 |
| Retry Delays | 5s, 15s |
| Circuit Breaker Threshold | 10 execution failures / 10 min |
| Circuit Breaker Disable Window | 30 min |
| Rollback | Captures previous NodePool state → restores on patch failure |

### Karpenter Migration — Hybrid-to-Karpenter Workflow

**Source:** `backend/api/cluster_routes.py`, `backend/workers/tasks/auto_rebalancer.py`, `backend/workers/tasks/cleanup_tasks.py`, `backend/services/workload_inspector.py`

The migration workflow moves a cluster from EKS Managed Node Groups to Karpenter-only:

| Phase | Trigger | What Happens |
|-------|---------|-------------|
| **Start** | `POST /clusters/{id}/start-migration` | Sets `auto_rebalance_enabled=True`, `target_spot_exposure_pct=100`, `karpenter_mode=AUTO` |
| **In Progress** | Auto-rebalancer runs | OD instances are drained one-by-one and replaced with Karpenter-provisioned spot instances |
| **Workload Labels** | `WorkloadInspector.scan_cluster()` | Classifies nodes as stateless/stateful → queues `LABEL_NODE` agent actions to apply `workload=stateless`/`stateful` labels → dual NodePools schedule accordingly |
| **Completing** | All OD instances drained (CHECKPOINT-E) | Auto-rebalancer triggers `cleanup_managed_node_group.delay(cluster_id)` |
| **Cleanup** | `cleanup_managed_node_group` Celery task | Verifies 0 OD nodes → lists EKS node groups → checks desiredSize=0 → calls `delete_nodegroup()` → sets `managed_node_group_deleted=True` + `karpenter_only_mode=True` |
| **Completed** | Both flags set | ASG APIs are permanently skipped; cluster runs on Karpenter NodePools only |
| **Force Complete** | `POST /clusters/{id}/force-complete-migration` | Admin safety hatch — sets both flags immediately |

#### Migration API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/clusters/{id}/start-migration` | POST | Starts migration (checks Karpenter installed) |
| `/clusters/{id}/migration-status` | GET | Returns phase, node counts, spot %, flag states |
| `/clusters/{id}/force-complete-migration` | POST | Force-sets both migration flags |

---

## 8. Auto-Rebalancer — Complete Flow

**Source:** `backend/workers/tasks/auto_rebalancer.py` (~4300 lines)

### Main Entry: `execute_rebalancing()` Celery Task

**Runs every:** 15 seconds (configurable via `check_interval_seconds`)

### Execution Phases

```
Stale Cleanup → Safety Gates → Spot Exposure Limiting → Batch Selection (PDB-aware) → Phase 1 (Provision) → Phase 2 (Drain & Replace)
```

### Spot Exposure Limiting

After safety gates pass and the OD candidate list is filtered (cooldown + WorkloadInspector classification), the rebalancer enforces `target_spot_exposure_pct`:

1. Read `target_spot_exposure_pct` from `ClusterOptimizationSettings` (default **100**).
2. If target == 100 → no limiting; all OD nodes remain eligible (full migration mode).
3. If target < 100:
   - Count total running instances and spot instances for the cluster.
   - Compute `current_spot_pct = spot_running / total_running × 100`.
   - If `current_spot_pct ≥ target` → empty the OD list, skip OD→Spot rebalancing entirely.
   - Else → compute `od_to_convert = max(1, floor((target − current_spot_pct) / 100 × total_running))` and trim the OD batch.

**Source:** `auto_rebalancer.py`, inserted between Classification Guard and CHECKPOINT-E.

### Batch Selection (PDB-Aware)

Before iterating target nodes, the rebalancer computes a batch size:

1. If `rebalance_batch_percent` is set → use that value.
2. Else if `respect_pdb_enabled` → compute PDB-safe % via `pdb_service.get_pdb_safe_percent_for_cluster()` (cached 5 min).
3. Else → default 15%.
4. If `respect_pdb_enabled`, always cap to PDB-safe limit regardless of user setting.
5. `batch_size = max(1, floor(len(od_nodes) × batch_percent / 100))`.

**PDB Computation** (`backend/services/pdb_service.py`): Queries all PodDisruptionBudgets via K8s `PolicyV1Api`, finds the strictest `maxUnavailable` or `(total - minAvailable)` across all PDBs, converts to percentage of total nodes.

**Source:** `backend/services/pdb_service.py` + `auto_rebalancer.py` batch selection block.

### Phase 1: Provision Replacement (Lines 1355–1855)

| Step | Action | Source |
|------|--------|--------|
| 1 | Load pre-computed ranked alternatives from `action.metadata['ranked_alternatives']` | L1351–1370 |
| 2 | If no metadata: call `PoolRankingService.rank_pools_for_node()` | L1360–1419 |
| 3 | Filter out pools with `spot:launch_blocked:{cid}:{type}:{az}` Redis key | L1500–1521 |
| 4 | Detect source architecture via `DescribeInstanceTypes` (7-day Redis cache) | L1527–1600 |
| 5 | Apply architecture preference filter (arm64/amd64/both) | L1527–1600 |
| 6 | **Karpenter-only:** Validate capacity via dry-run → `KarpenterService.add_allowed_instance_type()` to update NodePool directly via K8s API | Phase 1 code |
| 7 | Store `karpenter_nodepool_updated`, `phase1_completed_at`, `phase2_params` in action_metadata | Phase 1 code |
| 8 | Set `current_state = 'WAITING_FOR_KARPENTER'` — Karpenter provisions replacement automatically | Phase 1 code |
| 9 | Set 24h instance cooldown: `spot:rebalanced:instance:{id}` | Phase 1 code |

### Phase 2: Drain & Replace (Lines 2816–3700)

**Trigger conditions (all must pass):**

| Condition | Check |
|-----------|-------|
| All Phase 1 AgentActions COMPLETED | No PENDING/PICKED_UP actions remaining |
| Replacement instance exists in DB as running SPOT | `metadata['replacement_spot_instance_id']` found |
| Instance age ≥ 90 seconds | Stabilization window |
| K8s node status = READY | From collector heartbeat |

| Step | AgentAction Created | Purpose |
|------|-------------------|---------|
| 1 | `LABEL_NODE` | Add `karpenter.sh/do-not-disrupt=true` on replacement |
| 2 | `CORDON_NODE` | Mark source node unschedulable |
| 3 | `DRAIN_NODE` | Evict pods (grace_period=60s, force=configurable) |
| 4 | `TERMINATE_NODE` | Backend terminates source EC2 instance |
| 5 | `LABEL_NODE` | Remove do-not-disrupt label from replacement |

### Timeout Configuration

| Phase | Default | Configurable Via |
|-------|---------|-----------------|
| Spot join timeout | 30 min | Hardcoded (previously `spot_join_timeout_minutes`) |
| Drain timeout | 15 min | `drain_timeout_minutes` setting |
| Readiness grace | 20s–15 min | Wait for pods to reschedule after drain |

### State Machine Transitions

```
CREATED → POOL_SELECTED → SOURCE_CORDONED → SOURCE_DRAINED
→ REPLACEMENT_LAUNCHING → REPLACEMENT_READY → SOURCE_TERMINATING
→ COMPLETED / FAILED
```

**Implementation:** Optimistic locking via SQL `UPDATE ... WHERE current_state = ?` with 2 retries and exponential backoff (100ms, 200ms).  
**Source:** `auto_rebalancer.py` L41–77

### Stale Action Cleanup — Per-Step Timeouts

| State | Timeout |
|-------|---------|
| `in_progress` | 45 min |
| `waiting_agent` | 10 min |
| `waiting_for_spot_node` | 28 min |
| `cordoning_node` | 10 min |
| `draining_pods` | 20 min |
| `verifying_pod_readiness` | 20 min |
| `terminating_source` | 10 min |

**On expiry:** Mark `status='failed'` → terminate orphan spot EC2 → clear `spot:node_active_action:{source_id}`  
**Source:** `auto_rebalancer.py` L2630–2700

### Failure Backoff Formula

```
failure_count = redis.incr(f"rebalance_failures:{instance_id}")   # 24h TTL
backoff_seconds = min(300 × 2^(failure_count - 1), 3600)

Sequence: 300s (5 min) → 600s (10 min) → 1200s (20 min) → 2400s (40 min) → 3600s (1 hr max)
```

**Sliding window:** If >24h since last failure → reset counter to 0  
**Cleared on success:** Delete `rebalance_failures:{instance_id}` and `rebalance_last_failure:{instance_id}`  
**Source:** `auto_rebalancer.py` L3703–3729

---

## 9. Safety Gates & Locks

**Source:** `auto_rebalancer.py` L1121–1208

All gates must pass. If ANY blocks → action status set to `deferred`.

| Gate | Redis Key / Check | TTL | Purpose |
|------|-------------------|-----|---------|
| Cluster Cooldown | `spot:cluster_cooldown:{cluster_id}` | Dynamic | Recent action or emergency hold |
| Concurrency Lock | `rebalance_lock:{cluster_id}` | 2700s (45 min) | One cycle at a time (heartbeat renews every 60s) |
| Stabilization Lock | CooldownController `.is_stabilization_locked()` | Dynamic | Blocks cross-system operations |
| Substitute State | `spot:substitute:state:{cluster_id}` | Varies | Block if PREWARMING/RELEASING (READY is OK) |
| Resize Cooldown | `spot:cooldown:action:resize:{cluster_id}` | Dynamic | Right-sizing in progress |
| Double-Launch Guard | `action.metadata['replacement_spot_instance_id']` already set | N/A | Skip Phase 1, go straight to waiting_agent |
| Per-Node Lock | `spot:node_active_action:{instance_id}` | 600s | Prevent overlapping drains on same node |
| Concurrency Semaphore | `rebalance:active_count:{cluster_id}` | 300s | Max concurrent actions (default 1) |
| PDB-Safe Batch Cache | `pdb:safe_percent:{cluster_id}` | 300s | Cached PDB-safe % for batch limiting |
| Spot Exposure Cap | `target_spot_exposure_pct` (DB setting) | N/A | If current spot % ≥ target, skip OD→Spot; else trim batch to gap |
| Karpenter-Only Mode | `karpenter_only_mode` (DB setting) | N/A | When True: Phase 1 skips `get_asg_for_instance()` entirely; Phase 2 forces direct EC2 terminate path |

---

## 10. Pool Selection Algorithm (4-Pass)

**Source:** `auto_rebalancer.py` L1351–1600 → `pool_ranking_service.py`

### Pass 1 — Primary (VALUE + SAFETY)

| Filter | Condition |
|--------|-----------|
| Price | `spot_price < OD_price` |
| Risk | `risk < risk_ceiling` (default 25%) |

→ Most common path: best savings with acceptable risk

### Pass 2 — Tradeoff (slightly worse pool)

**Triggered:** Only if Pass 1 returns 0 results

| Filter | Condition |
|--------|-----------|
| Price | `spot_price ≤ cheapest_spot + tradeoff_pct × (OD - cheapest)` |
| Risk | `risk < risk_ceiling` |

→ Up to X% more expensive if safer (default 20%)

### Pass 3 — Risk Override (current node already risky)

**Triggered:** Only if Pass 1+2 empty AND `node_risk > risk_ceiling`

| Filter | Condition |
|--------|-----------|
| Risk | `pool_risk < node_risk` |

→ Any pool safer than current is acceptable

### Pass 4 — Final Fallback (anything cheaper)

**Triggered:** Only if Pass 1+2+3 empty

| Filter | Condition |
|--------|-----------|
| Price | `spot_price < OD_price` |

→ Last resort, ignores risk ceiling entirely

### Diversification Filters (applied after ML ranking)

| Filter | Condition | When |
|--------|-----------|------|
| Pool Uniqueness | `pool_counts[pool] == 0` | Always |
| AZ Cap | `az_counts[az] / total ≤ 50%` | Always |
| Family Cap | `fam_counts[fam] < ceil(40% × total_nodes)` | Only if `diversify_pools=ON` |
| Launch Block | No `spot:launch_blocked:{cid}:{type}:{az}` key | Always |

---

## 10b. Karpenter Simulation Engine v2

**Source:** `backend/services/simulation_engine.py` (engine) + `backend/api/ascpai_routes.py` (integration)  
**Version:** `v2-convergence`  
**Replaces:** Single-pass FFD bin-packing (removed)

The node-recommendations endpoint (`GET /api/clusters/{id}/ascpai/node-recommendations`) now uses a multi-cycle convergence simulation that models real Karpenter + auto-rebalancer behavior instead of a globally-optimal First-Fit Decreasing (FFD) bin-packing algorithm.

### Why FFD Was Replaced

| Problem | Impact |
|---------|--------|
| FFD is globally optimal → real Karpenter is greedy (1 pod at a time) | Savings over-estimated by 15-30% |
| No temporal model → drain/provision/stabilize happen in zero time | Missed convergence delays |
| No Redis constraint replay → used pools that are launch_blocked | Recommended unavailable pools |
| Shared regional pool cache → included pools from wrong AZs | Invalid pool selections |
| No fragmentation modeling → 100% packing efficiency assumed | Unrealistic node counts |
| No stateful/stateless separation → mixed workload types on same nodes | Violated Karpenter NodePool boundaries |

### Architecture Overview (9 Stages)

```
Stage 1: Consistent Snapshot     → SimulationSnapshot (frozen timestamp)
Stage 2: Virtual Cluster State   → VirtualClusterState (node/pod state machine)
Stage 3: Multi-Cycle Loop        → max 10 convergence cycles
Stage 4: Greedy Scheduler        → arrival-order placement (NOT FFD)
Stage 5: Real Karpenter Behavior → 4-pass pool selection with ML scoring
Stage 6: Constraint Replay       → launch_blocked, blacklist, risky_pools from Redis
Stage 7: Per-Cluster Isolation   → cluster-scoped AZ/arch filtering
Stage 8: Time-Based State Machine→ PROVISIONING(3 ticks) → STABILIZING(3 ticks) → READY
Stage 9: Calibration & Accuracy  → confidence scoring based on failures + convergence speed
```

### Stage 1: Simulation Snapshot

All inputs are frozen at the same logical timestamp (`snapshot_frozen_at`).

**Dataclasses:**

| Dataclass | Key Fields |
|-----------|------------|
| `SimNode` | instance_id, instance_type, lifecycle, az, architecture, vcpu, memory_gb, price_hourly, workload_class (stateless/stateful/system) |
| `SimPod` | pod_name, namespace, controller_name, cpu_millicores, memory_bytes, is_stateful, is_daemonset |
| `SimPool` | instance_type, az, architecture, vcpu, memory_gb, spot_price, od_price, risk_probability, ml_score |
| `SimRedisState` | launch_blocked (Set), blacklisted_pools (Set), risky_pools (Set), pdb_safe_percent |
| `SimClusterSettings` | target_spot_exposure_pct, diversify_pools, architecture_preference, risk_ceiling_percent, risk_savings_tradeoff_pct |
| `SimulationSnapshot` | snapshot_id, frozen_at, cluster_id, nodes, pods, redis_state, cluster_settings, candidate_pools, ds_cpu/mem_overhead |

**Data Sources (from ascpai_routes.py):**

| Snapshot Field | Source Variable | Origin |
|----------------|----------------|--------|
| `nodes` | `_node_list` + `node_classification` | `instance_cache:{cluster_id}` Redis + WorkloadInspector |
| `pods` | `PodMetric` query (latest 10min) | PostgreSQL `pod_metrics` table |
| `candidate_pools` | `top_pools` (_ScoredPoolWrapper) | `market_view_cache:{region}` Redis |
| `redis_state` | `spot:launch_blocked:*`, `risky_pools` | Redis keys |
| `cluster_settings` | `cluster.optimization_settings` + `optimization_strategy_profile` | PostgreSQL |
| `ds_cpu/mem_overhead` | DaemonSet pod separation | PodMetric query |

### Stage 2: Virtual Cluster State

`VirtualClusterState` tracks all nodes and pods with state transitions:

**Node States:**
```
READY → CORDONED → DRAINING → TERMINATED
                                    ↑
PROVISIONING → STABILIZING → READY  (new nodes)
```

**Pod States:**
```
RUNNING → PENDING (when node drained)
PENDING → RUNNING (when placed on new node)
PENDING → FAILED  (when no node can fit)
```

**Key Methods:**
- `drain_node(node_id)` → marks node DRAINING, moves pods to PENDING
- `provision_node(pool, ds_cpu, ds_mem)` → creates new node in PROVISIONING state
- `place_pod(pod_id, node_id)` → assigns pod to node, updates resource consumption
- `tick_provisioning_nodes()` → advances PROVISIONING → STABILIZING → READY timers
- `check_convergence()` → true when no PENDING pods AND no PROVISIONING nodes

### Stage 3: Multi-Cycle Convergence Loop

```python
for cycle in range(MAX_CYCLES):     # MAX_CYCLES = 10
    candidates = select_candidates()  # stateless OD nodes → drain
    drain(candidates)                 # evict pods → PENDING
    provision(pending_pods)           # Karpenter creates new spot nodes
    tick(PROVISIONING + STABILIZATION)  # ~6 ticks × 30s = 180s
    scheduler_place(pending)          # greedy placement on READY nodes
    if converged:
        break
```

**Tick Model:** `TICK_SECONDS = 30`, `PROVISIONING_TICKS = 3`, `STABILIZATION_TICKS = 3`, `MAX_SIMULATION_TICKS = 30` (15-minute wall-clock cap)

### Stage 4: Greedy Scheduler

Unlike FFD which sorts pods largest-first for optimal packing, the greedy scheduler processes pods in **arrival order** (as real kube-scheduler does):

1. For each PENDING pod, iterate READY nodes sorted by remaining CPU (most-available first)
2. If pod fits AND node allows pod (stateful/stateless constraint), place it
3. If no existing node fits, try newly provisioned READY nodes
4. If still unplaceable → mark as FAILED (unschedulable)

**Workload Isolation:**
- Stateful pods only placed on `stateful` or `system` workload-class nodes
- Stateless pods only placed on `stateless` workload-class nodes
- This mirrors Karpenter NodePool `karpenter.sh/nodepool` label selectors

### Stage 5: 4-Pass Pool Selection

When pending pods need new nodes, `select_pool_for_pending()` uses 4 passes:

| Pass | Criteria | Constraint |
|------|----------|------------|
| 1: VALUE+SAFETY | `risk < ceiling` AND `price < OD` AND diversification ok | Strictest |
| 2: Tradeoff | `risk < ceiling` AND `price ≤ cheapest + tradeoff% × (OD - cheapest)` | Allows costlier |
| 3: Risk Override | `risk < ceiling` AND fits resource needs | Drops diversification |
| 4: Final Fallback | `price < OD` AND fits resource needs | Drops risk ceiling |

### Stage 6: Constraint Replay Engine

Before pool selection, `build_cluster_pool_view()` filters the global candidate list:

| Constraint | Redis Key Pattern | Effect |
|------------|-------------------|--------|
| Launch Blocked | `spot:launch_blocked:{cid}:{type}:{az}` | Pool removed from eligible set |
| Globally Blacklisted | `risky_pools` (set members) | Pool removed from eligible set |
| PDB Safe Percent | `pdb:safe_percent:{cid}` | Limits batch size |

### Stage 7: Per-Cluster Pool View

Instead of using the full regional pool cache, the simulation filters to:
- Only AZs where the cluster currently has nodes (`cluster_azs`)
- Only architectures matching `architecture_preference` setting (amd64/arm64/both)
- Removes pools failing constraint replay (Stage 6)
- Result: `eligible_pools` — cluster-scoped, constraint-filtered, sorted by `(spot_price, -ml_score)`

### Stage 8: Time-Based State Machine

Each provisioning event takes real time modeled as ticks:

| Phase | Ticks | Wall-Clock | What Happens |
|-------|-------|------------|--------------|
| PROVISIONING | 3 | ~90s | EC2 instance launching, joining EKS |
| STABILIZING | 3 | ~90s | Node taints removed, DaemonSets scheduled |
| READY | — | — | Pods can be placed |

If `total_ticks ≥ MAX_SIMULATION_TICKS (30)`, the simulation times out and reports partial results with lower confidence.

### Stage 9: Confidence Scoring

`_compute_confidence()` produces a 0.0-1.0 score:

| Factor | Penalty |
|--------|---------|
| Each provisioning failure | −0.05 |
| Unschedulable pods (% of total) | −0.20 × (failed/total) |
| Slow convergence (>6 cycles) | −0.10 |

### Post-Convergence Corrections

**Fragmentation Correction:** If CPU utilization across stateless READY nodes exceeds `(1 - FRAGMENTATION_PCT)` (92%), an extra node of the most common type is added. This corrects for the simulation's greedy scheduler being slightly more efficient than real-world pod scheduling with node affinity/anti-affinity.

**HA Minimum:** At least 2 stateless spot nodes are enforced (or `min_node_count` from settings) to survive a single spot interruption.

### Two-Pool Cost Calculation

Costs are computed separately for stateless (spot) and stateful (on-demand) pools:

```
stateless_monthly = Σ(stateless spot node prices) × 730 hours
stateful_monthly  = Σ(stateful OD node prices) × 730 hours
total_monthly     = stateless_monthly + stateful_monthly
monthly_savings   = current_monthly_cost - total_monthly
```

### Candidate Selection Logic

`_select_candidates()` identifies nodes to consolidate:
1. Only stateless nodes (skip stateful/system)
2. Only on-demand nodes (they're the ones being replaced with spot)
3. Apply `target_spot_exposure_pct` cap — stop converting if spot% would exceed target
4. Apply `rebalance_batch_percent` (default 15%) — limit how many nodes per cycle

### Enhanced Output Schema

The simulation output includes all previous fields plus:

| Field | Type | Description |
|-------|------|-------------|
| `stateless_node_count` | int | Nodes for stateless workloads |
| `stateless_spot_count` | int | Spot instances in stateless pool |
| `stateless_monthly_cost` | float | Monthly cost of stateless pool |
| `stateless_consolidated_nodes` | list | Per-type breakdown for stateless |
| `stateless_nodes_eliminated` | int | Current stateless − simulated stateless |
| `stateless_monthly_savings` | float | Stateless cost reduction |
| `stateful_node_count` | int | Nodes for stateful workloads |
| `stateful_monthly_cost` | float | Monthly cost of stateful pool |
| `stateful_consolidated_nodes` | list | Per-type breakdown for stateful |
| `stateful_monthly_savings` | float | Stateful cost reduction |
| `simulated_spot_node_count` | int | Total spot nodes across both pools |
| `simulated_od_node_count` | int | Total OD nodes across both pools |
| `simulated_spot_pct` | float | Spot percentage after simulation |
| `cycles_to_converge` | int | Number of convergence cycles used |
| `converged` | bool | Whether simulation fully converged |
| `timed_out` | bool | Whether simulation hit MAX_SIMULATION_TICKS |
| `pending_pods_peak` | int | Maximum pending pods at any point |
| `provisioning_failures` | int | Pools that couldn't provision |
| `scheduler_fragmentation_pct` | float | Wasted capacity percentage |
| `pools_skipped_launch_blocked` | int | Pools excluded by launch_blocked |
| `pools_skipped_blacklisted` | int | Pools excluded by blacklist |
| `confidence_score` | float | 0.0-1.0 quality score |
| `snapshot_frozen_at` | str | ISO timestamp of snapshot |
| `simulation_engine_version` | str | "v2-convergence" |

### Integration in ascpai_routes.py

The endpoint builds a `SimulationSnapshot` from existing route variables:

```
_node_list + node_classification → List[SimNode]
PodMetric query (10min window)   → List[SimPod]
top_pools (_ScoredPoolWrapper)   → List[SimPool]
Redis keys                       → SimRedisState
cluster.optimization_settings    → SimClusterSettings
```

Then calls:
```python
result = run_simulation(snapshot)
output = build_simulation_output(result, snapshot, current_node_count, current_monthly_cost)
```

The output dict is set as `_karpenter_simulation` in the response payload.

### Simulation Accuracy Audit

#### What's Correct & Well-Implemented

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-cycle convergence loop | ✅ | Models iterative drain+provision cycles, not global optimum |
| Greedy scheduler (arrival order) | ✅ | Matches kube-scheduler's FIFO pod queue |
| Time-based state machine (PROVISIONING → STABILIZING → READY) | ✅ | Realistic node join delays |
| Constraint replay (launch_blocked, blacklist, PDB) | ✅ | Respects Redis runtime state |
| Per-cluster AZ/arch filtering | ✅ | Avoids pools from irrelevant zones |
| Workload isolation (stateless vs stateful) | ✅ | Uses Karpenter NodePool labels |
| 4-pass pool selection | ✅ | Aligns with auto-rebalancer logic |
| Fragmentation correction + HA min nodes | ✅ | Addresses greedy scheduler inefficiency |

#### Known Limitations (Accepted Simplifications)

These are scheduling constraints that real Kubernetes and Karpenter enforce but the simulation currently **does not model**. The simulation intentionally simplifies these to keep execution fast (~1-2s) while still producing directionally accurate cost/node estimates.

| Gap | Impact on Simulation | Real Karpenter / K8s Behavior | Severity |
|-----|---------------------|-------------------------------|----------|
| **Node selectors** | Pods may be placed on nodes that violate `nodeSelector` — simulation treats all non-stateful pods as interchangeable | Karpenter inspects `nodeSelector` when provisioning and only launches instance types that satisfy all selectors (e.g. `kubernetes.io/arch`, `node.kubernetes.io/instance-type`) | Medium |
| **Taints & tolerations** | GPU / dedicated workloads with tolerations could be placed on generic nodes | Karpenter creates nodes with taints matching NodePool config; scheduler only places pods with matching tolerations | Medium |
| **Pod affinity / anti-affinity** | Co-located or separated workloads may be placed incorrectly, under-counting required nodes | `podAffinity` and `podAntiAffinity` with `requiredDuringScheduling` are hard constraints — scheduler rejects violations, Karpenter may provision additional nodes to satisfy them | High |
| **Topology spread constraints** | HA spread across nodes/AZs may be violated, simulation may over-consolidate | `topologySpreadConstraints` with `whenUnsatisfiable: DoNotSchedule` forces the scheduler to spread pods, preventing tight bin-packing on fewer nodes | High |
| **PDB enforcement during placement** | PDB is used only for drain batch sizing (`pdb:safe_percent`), not for validating final placement feasibility | A real migration could violate PDB if too many pods from the same controller land on one node that later gets interrupted — kube-scheduler and Karpenter's disruption controller respect PDB when evicting | Low |
| **Resource limits (not just requests)** | Pods with limits >> requests may OOM on tightly packed nodes | Scheduler uses `requests` for placement; simulation correctly uses requests too, but doesn't account for limit-based headroom — in practice, Karpenter's `memory-headroom` consolidation setting handles this | Low |
| **StatefulSet pod identity** | Stateful pods are isolated to stateful nodes (correct) but don't model volume zone affinity | StatefulSet pods with PVCs are AZ-constrained to where their EBS volumes reside — Karpenter provisions nodes in the correct AZ automatically | Low |

**Net effect:** The simulation may **under-count** required nodes by 5-15% for clusters with heavy affinity/anti-affinity or topology spread rules. The `confidence_score` and `fragmentation_correction` partially compensate but do not fully account for these constraints.

**Mitigation strategy (current):**
- Fragmentation correction adds an extra node when utilization exceeds 92%
- HA minimum enforces ≥2 stateless spot nodes
- Confidence score penalizes unschedulable pods and slow convergence
- Savings estimates use conservative pool pricing (not best-case)

**Future improvements (not yet implemented):**
- Parse `nodeSelector` from `SimPod` and filter `SimPool` candidates by matching labels
- Model `topologySpreadConstraints` by tracking per-AZ pod counts and enforcing `maxSkew`
- Track pod affinity groups and provision co-located pods onto the same node

---

## 11. AWS & EKS Operations

**Source:** `backend/workers/tasks/discovery.py`, `backend/utils/aws/asg.py`, `backend/utils/aws/dry_run.py`

### All AWS API Calls

#### Discovery Worker (every 5 minutes)

| AWS API | Service | Purpose | Source |
|---------|---------|---------|--------|
| `AssumeRole` | STS | Cross-account access | `asg.py` L49–65 |
| `ListClusters` (paginated) | EKS | Find all EKS clusters | `discovery.py` L441 |
| `DescribeCluster` | EKS | Get endpoints, version, ARN, CA data | `discovery.py` L450 |
| `DescribeInstances` (paginated) | EC2 | Get EKS nodes with cluster tag | `discovery.py` L44 |
| `DescribeSpotPriceHistory` | EC2 | Real-time spot prices (last 1h) | `discovery.py` L92 |
| `GetCostAndUsage` | Cost Explorer | Monthly cluster costs (24h cache) | `discovery.py` L487 |

#### Auto-Rebalancer Worker

| AWS API | Service | Purpose | Source |
|---------|---------|---------|--------|
| `DescribeInstances` | EC2 | Get source instance config (AMI, subnet, SGs) | `auto_rebalancer.py` L690 |
| `DescribeInstanceAttribute` | EC2 | Fetch user-data from running instance | L751 |
| `DescribeLaunchTemplateVersions` | EC2 | Get user-data from EKS managed LT | L769 |
| `ListNodegroups` + `DescribeNodegroup` | EKS | Get authoritative user-data from nodegroup LT | L797 |
| `DescribeImages` | EC2 | Resolve architecture-compatible AMI | L228–270 |
| `DescribeInstanceTypes` | EC2 | Detect instance architecture (7-day Redis cache) | L115–145 |
| `RunInstances (DryRun=True)` | EC2 | Spot capacity pre-check (validates before NodePool update) | `dry_run.py` L209 |
| ~~`RunInstances` (spot)~~ | ~~EC2~~ | **Removed** — Karpenter handles instance provisioning | — |
| ~~`CreateFleet` (instant)~~ | ~~EC2~~ | **Removed** — `fleet.py` deleted, Karpenter handles provisioning | — |
| `TerminateInstances` | EC2 | Terminate source OD / orphan spot | `auto_rebalancer.py` L2477 |

#### ASG Operations

| AWS API | Service | Purpose | Source |
|---------|---------|---------|--------|
| `DescribeAutoScalingInstances` | AutoScaling | Resolve ASG for instance | `asg.py` L103 |
| `DescribeAutoScalingGroups` | AutoScaling | Get ASG config (Min/Desired/Max) | L119 |
| `SuspendProcesses` | AutoScaling | Pause ReplaceUnhealthy, AZRebalance, Launch | L141 |
| `ResumeProcesses` | AutoScaling | Resume ASG processes after rebalance | L163 |
| `UpdateAutoScalingGroup` | AutoScaling | Lower MinSize for last-OD detach | L180 |
| `DetachInstances` | AutoScaling | Remove node from ASG (decrement desired) | L199 |

### ASG Last-OD-Node Replacement Sequence

| Step | Action | Source |
|------|--------|--------|
| 1 | Resolve ASG via `DescribeAutoScalingInstances` | `asg.py` L103–111 |
| 2 | Suspend `ReplaceUnhealthy`, `AZRebalance`, `Launch` | L138–150 |
| 3 | Lower MinSize if `MinSize > (DesiredCapacity - 1)` | L176–194 |
| 4 | `DetachInstances(ShouldDecrementDesiredCapacity=True)` | L196–214 |
| 5 | Resume all suspended processes | L155–167 |

### Spot Capacity Dry-Run Validation

**Source:** `backend/utils/aws/dry_run.py` L209–225

```
ec2.run_instances(DryRun=True, ImageId=ami, InstanceType=type, 
                  Placement={AZ}, InstanceMarketOptions={spot})
```

| Response | Meaning | Cache TTL |
|----------|---------|-----------|
| `DryRunOperation` error | Capacity AVAILABLE | 900s (15 min) |
| `InsufficientInstanceCapacity` | No capacity | 60s (1 min) |
| Other error | Conservative FAIL | 60s |

### User-Data Resolution (3-Tier Fallback)

| Attempt | Method | Source |
|---------|--------|--------|
| 1 | `DescribeInstanceAttribute` on source instance | `auto_rebalancer.py` L751 |
| 2 | `DescribeLaunchTemplateVersions` from EKS managed LT | L769 |
| 3 | `ListNodegroups` → `DescribeNodegroup` → LT user-data (most reliable) | L797 |
| 4 | Generate from template via `backend/utils/aws/user_data.py` | Fallback |

---

## 12. State Management — Database

### Core Tables & What They Track

| Table | Model | State Tracked | Update Frequency |
|-------|-------|--------------|-----------------|
| `clusters` | Cluster | Name, status, node counts, costs, karpenter_mode | Every discovery cycle (5 min) |
| `instances` | Instance | Per-node: type, lifecycle, state, AZ, price, utilization | Discovery (5 min) + rebalancer |
| `cluster_optimization_settings` | ClusterOptimizationSettings | All automation toggles/thresholds | User-triggered (UI save) |
| `optimization_strategy` | OptimizationStrategy | Risk/savings profile | User-triggered |
| `agent_actions` | AgentAction | Per-action: type, status, payload, result | Agent execution lifecycle |
| `rebalancing_actions` | RebalancingAction | Per-rebalance: source/target pool, state, savings | Rebalancer state machine |
| `pod_metrics` | PodMetric | Per-pod CPU/memory usage | Agent push (continuous) |
| `rightsizing_proposals` | RightsizingProposal | Per-node right-sizing recommendations | Celery task (periodic) |

### RebalancingAction State Machine (DB)

| Field | Purpose |
|-------|---------|
| `status` | Overall status: in_progress, waiting_agent, completed, failed, deferred |
| `current_state` | Fine-grained phase: POOL_SELECTED, SOURCE_CORDONED, etc. |
| `source_pool` | `{instance_type}:{az}` of source node |
| `target_pool` | `{instance_type}:{az}` of replacement |
| `started_at` | Phase 1 start timestamp |
| `completed_at` | Final completion or failure timestamp |
| `actual_spot_price_hr` | Realized spot price |
| `realized_savings_hr` | OD price minus spot price |
| `realized_savings_mo` | Monthly savings (×730) |
| `metadata` | JSON: replacement_spot_instance_id, ranked_alternatives, pool_change_reason |
| `error_message` | Failure reason text |

---

## 13. State Management — Redis

### All Redis Key Patterns

#### Locks & Concurrency

| Key Pattern | TTL | Purpose |
|------------|-----|---------|
| `rebalance_lock:{cluster_id}` | 2700s (45 min) | One rebalance cycle at a time (heartbeat renews 60s) |
| `action_heartbeat:{action_id}` | 120s | Updated every cycle; stale = action stuck |
| `lock:workers.auto_rebalancer` | 300s | Main task lock |
| `lock:node_action:{cluster_id}` | 1200s | Drain operations lock |

#### Per-Instance Cooldowns

| Key Pattern | TTL | Purpose |
|------------|-----|---------|
| `spot:rebalanced:instance:{iid}` | 24h (normal) / backoff (failure) | Don't re-target this instance |
| `spot:post_launch_cooldown:{iid}` | 60s | Post-launch S2S suppression |
| `spot:s2s_suppressed:{iid}` | 180s | S2S suppression after fallback |
| `spot:term_failed:{iid}` | 14400s (4h) | EC2 terminate failure cooldown |
| `spot:asserted_spot:{iid}` | 600s | Prevent discovery false OD downgrade |
| `spot:node_active_action:{iid}` | 600s | Active rebalance marker for this node |

#### Per-Cluster Blocks

| Key Pattern | TTL | Purpose |
|------------|-----|---------|
| `spot:cluster_cooldown:{cluster_id}` | Dynamic | General cooldown |
| `spot:launch_blocked:{cid}:{type}:{az}` | 1800s (30 min) | Capacity failures (3 attempts) |
| `spot:cooldown:action:resize:{cid}` | Dynamic | Right-sizing in progress |
| `spot:substitute:state:{cid}` | Varies | IDLE/PREWARMING/READY/RELEASING |

#### Failure Tracking

| Key Pattern | TTL | Purpose |
|------------|-----|---------|
| `rebalance_failures:{iid}` | 86400s (24h) | Failure count for backoff |
| `rebalance_last_failure:{iid}` | 86400s | Timestamp for sliding window |

#### Karpenter State

| Key Pattern | TTL | Purpose |
|------------|-----|---------|
| `spot:karpenter:installed:{cid}` | 3600s (1h) | Live detection marker |
| `karpenter:detected:{cid}` | 300s (5 min) | Cached detection result |
| `spot:ondemand_fallback:{cid}` | 43200s (12h) | On-demand fallback mode active |
| `karpenter_config:{cid}` | 86400s (24h) | Persisted UI config |

#### Pool Rankings & Blacklist

| Key Pattern | TTL | Purpose |
|------------|-----|---------|
| `global_pool_rankings:{region}` | 3900s (65 min) | ML-ranked pool cache |
| `market_view_cache:{region}` | 3600s (60 min) | Market view data |
| `blacklist:global:{pool_key}` | 86400s (24h) / 900s (15 min) | Terminated/interrupted pool |
| `risky_pools:{region}` | With metadata | Risky pool SET |

#### Emergency & Dedup

| Key Pattern | TTL | Purpose |
|------------|-----|---------|
| `emergency:seen:{iid}` | 300s (5 min) | Dedup spot interruption events |
| `emergency:rebalance:{iid}` | 120s (2 min) | Per-node emergency lock |
| `cluster:{cid}:emergency_in_progress` | Varies | Emergency rebalance flag |

#### Discovery & Sync

| Key Pattern | TTL | Purpose |
|------------|-----|---------|
| `spot:discovery_last_updated:{cid}` | 600s | Discovery freshness marker |
| `rc3:sync_od_streak:{iid}` | 600s | SPOT→OD downgrade confirmation counter |
| `aws_sync:empty_streak:{cid}` | 600s | Guard against false empty scans |
| `instance_type_arch:{type}` | 604800s (7 days) | DescribeInstanceTypes cache |
| `node_joined:{iid}` | Session | K8s join confirmation |

#### Caches

| Key Pattern | TTL | Purpose |
|------------|-----|---------|
| `dry_run:{type}:{az}` | 900s (pass) / 60s (fail) | Capacity check cache |
| `dry_run:ami:{region}:{arch}` | 86400s (24h) | AMI resolution cache |
| `cluster_coverage:{cid}` | Dynamic | UI data cache (invalidated post-rebalance) |
| `credential_cache:{account_id}` | Varies | Cross-account STS creds |
| `pdb:safe_percent:{cluster_id}` | 300s (5 min) | PDB-safe batch % — max nodes rebalanceable without violating PodDisruptionBudgets (`pdb_service.py`) |

---

## 14. DB ↔ Redis Synchronization

### How State Is Kept In Sync

| Data | DB (PostgreSQL) | Redis | Sync Direction | Mechanism |
|------|-----------------|-------|---------------|-----------|
| Instance lifecycle | `instances.lifecycle` | `spot:asserted_spot:{iid}` | DB ← AWS, Redis guards downgrades | RC3: 3 consecutive OD observations required before SPOT→OD change |
| Rebalancing state | `rebalancing_actions.status` | Lock/cooldown keys | DB is source of truth, Redis gates execution | State machine writes DB; Redis locks prevent concurrent access |
| Cluster node counts | `clusters.node_count/spot_count` | — | DB ← AWS sync | `_sync_instance_state_from_aws()` updates after each scan |
| Pool rankings | — | `global_pool_rankings:{region}` (65 min TTL) | Redis-only cache, rebuilt by Celery task | Execution reads from Redis; never from DB |
| Karpenter status | `clusters.karpenter_mode` (DB column) | `spot:karpenter:installed:{cid}` (1h TTL) | Dual-write: DB for persistence, Redis for fast lookup | `detect_karpenter_in_cluster()` checks DB → sets Redis |
| Agent heartbeat | `clusters.last_heartbeat` | — | DB ← Agent HTTP POST | Agent sends every 30s; backend writes to DB |
| Blacklist | — | `blacklist:global:{pool_key}`, `risky_pools` SET | Redis-only (TTL-based expiry) | Written by termination_monitor & emergency_rebalancer |
| Action status | `agent_actions.status` | `action_heartbeat:{id}` | DB is truth; Redis tracks liveness | Agent updates DB; rebalancer checks heartbeat freshness |

### RC3 Lifecycle Downgrade Guard

**Problem:** AWS API sometimes omits `InstanceLifecycle='spot'` transiently  
**Solution:** Require 3 consecutive OD observations before downgrading SPOT→OD in DB

| Counter Key | TTL | Threshold | Source |
|------------|-----|-----------|--------|
| `rc3:sync_od_streak:{instance_id}` | 600s | 3 consecutive | `discovery.py` L875–905, `auto_rebalancer.py` L481–510 |
| `rc3_od_consecutive:{instance_id}` | 1800s | 3 consecutive | `discovery.py` L875 (legacy key) |

### Conflict Resolution

| Scenario | Resolution |
|----------|-----------|
| Discovery overwrites in-progress rebalance state | Discovery checks for active `RebalancingAction` before setting state |
| Redis key expires during operation | Rebalancer refreshes lock heartbeat every 60s; stale cleanup catches timeouts |
| Two workers pick same cluster | `rebalance_lock:{cid}` with `nx=True` — only first writer wins |
| Emergency + normal rebalance collide | Emergency clears cooldown+lock → takes priority |

---

## 15. Error Handling & Rollback

**Source:** `auto_rebalancer.py`

### Rollback Functions

| Function | When Triggered | What It Does | Source Lines |
|----------|---------------|-------------|-------------|
| `_do_rollback_terminate_orphan_spot()` | Phase 1 failure, drain timeout, stale cleanup | Terminates replacement spot EC2 via `ec2.terminate_instances()`, clears `spot:asserted_spot:{iid}`, removes `replacement_spot_instance_id` from metadata | L2418–2546 |
| `_do_rollback_uncordon_and_terminate()` | CORDON/DRAIN failure | Queues `UNCORDON_NODE` AgentAction → then calls `_do_rollback_terminate_orphan_spot()` | L2385–2413 |

### Phase Failure → Rollback Mapping

| Phase | Failure | Rollback Action |
|-------|---------|----------------|
| Pool Selection | No eligible pools found | No rollback needed (no resources created) |
| Cordon Source | kubectl error | `UNCORDON_NODE` + terminate orphan spot |
| Drain Source | PDB violation / timeout | `UNCORDON_NODE` + terminate orphan spot |
| Launch Replacement | `InsufficientInstanceCapacity` | Try next pool in cascade (up to 6 attempts) |
| Launch Replacement | All attempts exhausted | Mark action failed, set `spot:launch_blocked:{cid}:{type}:{az}` (30 min) |
| Wait for spot join | Timeout (30 min) | Terminate orphan spot, mark action failed |
| Terminate Source | EC2 API error | Set `spot:term_failed:{iid}` (4h), mark action failed, orphan spot stays running |
| Any phase | Stale action (>45 min) | Terminate orphan spot, clear per-node lock |

### Error Handling Patterns

| Pattern | Implementation |
|---------|---------------|
| Launch idempotency | SHA256(`{source_iid}:{target_type}`) as ClientToken — same source+type always returns existing instance | 
| Optimistic state locking | SQL `UPDATE ... WHERE current_state = ?` with 2 retries + backoff |
| Never-raise rollback | All rollback steps in try/except — continues to next step on any failure |
| Circuit breaker | 10 execution failures in 10 min → disable execution for 30 min |
| Exponential backoff | Per-node: 5 min → 10 min → 20 min → 40 min → 1 hr (max), 24h sliding window |
| 3-observation guard | Empty AWS scan results → require 3 consecutive empty before mass-terminate |

---

## 16. Emergency Rebalancer & Spot Interruptions

**Source:** `backend/workers/tasks/emergency_rebalancer.py`, `backend/workers/tasks/termination_monitor.py`

### Spot Interruption Detection

| Source | Detection Method |
|--------|-----------------|
| AWS EventBridge | Spot termination 2-min notice |
| Agent DaemonSet | Node-level metadata endpoint polling |
| Manual API | Admin-triggered endpoint |

### Deduplication Guards

| Guard | Key | TTL | Purpose |
|-------|-----|-----|---------|
| Event dedup | `emergency:dedup:{iid}` | 300s (5 min) | Only process first notice |
| Per-node lock | `emergency:rebalance:{iid}` | 120s (2 min) | Prevent repeated emergency for same node |
| Active action check | DB query for in_progress/waiting_agent | — | Skip if rebalance already running |

### Emergency Flow

| Step | Action | Source |
|------|--------|--------|
| 1 | Clear cluster cooldown + rebalance lock | L36–37 |
| 2 | Blacklist pool for 24h: `blacklist:global:{pool_key}` | L53–59 |
| 3 | Update interruption EMA (cross-cluster tracking) | L61–67 |
| 4 | Debounced cache refresh: `ranking_refresh_pending:{region}` (60s) | L69–84 |
| 5 | Create `RebalancingAction(trigger='emergency')` | L86–93 |
| 6 | **Karpenter-only:** CORDON → DRAIN → TERMINATE_NODE (mode=karpenter), Karpenter auto-provisions replacement | Karpenter emergency path |
| — | ~~Non-Karpenter path~~ | **Removed** — standby failover and normal emergency paths removed |
| 7 | Set 2-hour emergency cooldown | After execution |

---

## 17. Recovery Monitor & Orphan Cleanup

**Source:** `backend/workers/tasks/recovery_monitor.py`

### Task 1: `sync_instance_states()` — Every 5 min

| Step | Action |
|------|--------|
| 1 | Query all `Instance(state='running')` per cluster |
| 2 | `ec2.describe_instances(InstanceIds=[...])` in batches of 200 |
| 3 | Update DB where AWS state ∈ {terminated, shutting-down} |
| 4 | Handle `InvalidInstanceID` by re-querying individually |

### Task 2: `scan_orphans()` — Every 5 min

**Detection criteria:**
- Tag: `spot-optimizer:status=pending`
- State: `running`
- Age: > 15 min
- Redis: NO `node_joined:{iid}`, NO `spot:prevent_orphan_termination:{iid}`

**Double-check before termination:**

| Check | If True |
|-------|---------|
| `spot:prevent_orphan_termination:{iid}` exists | SKIP (manual override) |
| `Instance.node_name` is set in DB | SKIP (agent confirmed K8s join) |
| `Instance.last_heartbeat` < 5 min old | SKIP (agent recently alive) |
| All checks fail | TERMINATE orphan |

**Two-pass scan:**
- Pass 1: Platform credentials (same-account clusters)
- Pass 2: Per-cluster assumed-role (cross-account)

### Task 3: `detect_karpenter_stalls()` — Every 5 min

**Problem:** Karpenter NodeClaim reconciler loses track after control-plane restart  
**Detection:** AgentAction(type=TERMINATE_NODE, status=COMPLETED, completed > 15 min ago, mode=karpenter)  
**Fix:** Direct `ec2.terminate_instances()` as fallback

---

## 18. Celery Scheduled Tasks

**Source:** `backend/scheduler.py` L80–151, `backend/workers/app.py`

### Background Jobs

| Task | Interval | Purpose | Source |
|------|----------|---------|--------|
| `execute_rebalancing` | 15s (configurable) | Main auto-rebalancer loop | `auto_rebalancer.py` |
| `execute_pool_ranking_pipeline` | 30 min | Regenerate ML-ranked global pool list | `pool_ranking_service.py` |
| `collect_spot_prices` | 30 min | Refresh AWS spot prices in Redis | Pricing worker |
| `sync_karpenter_nodepools` | 1 hour | Patch Karpenter NodePool with top 10 ML pools | `karpenter_service.py` |
| `sync_instance_states` | 5 min | Sync AWS EC2 states to DB | `recovery_monitor.py` |
| `scan_orphans` | 5 min | Detect + terminate orphan EC2 | `recovery_monitor.py` |
| `detect_karpenter_stalls` | 5 min | Catch stalled Karpenter terminations | `recovery_monitor.py` |
| `job_scan_clusters` | 10 min | Node classification (with jitter) | `scheduler.py` L101 |
| `job_refresh_active_count` | 5 min | DryRun budget tracking | `scheduler.py` L83 |
| `job_reconcile_substitutes` | 5 min | Stuck substitute recovery | `scheduler.py` L92 |
| `job_check_cost_drift` | 30 min | Detect unexpected cost changes | `scheduler.py` L110 |
| `job_detect_volatility` | 1 hour | Spot volatility regime per region | `scheduler.py` L119 |
| `job_cleanup_blacklist` | Daily 2 AM | Expire stale blacklist entries | `scheduler.py` L128 |
| `global_ema.persist` | Nightly | Persist Redis EMA → PostgreSQL | EMA worker |
| `global_ema.decay` | Nightly | Apply 30-day half-life to EMA | EMA worker |
| `cleanup_managed_node_group` | On-demand | Delete EKS managed node group after all OD instances drained; sets `managed_node_group_deleted` + `karpenter_only_mode` flags | `cleanup_tasks.py` |
| Discovery scan | 5 min | Scan AWS for clusters/instances | `discovery.py` |

### Task Queue Routing

| Task Pattern | Queue | Priority |
|-------------|-------|----------|
| `emergency_rebalancer` | `emergency` | High |
| `recovery_monitor.*` | `monitoring` | Low |
| All others | `default` | Normal |

---

## 19. UI Components — What Shows Where

**Source:** `frontend/src/components/`, `frontend/src/pages/`

### ClusterDetails Page — Tabs

| Tab | Component | Data Shown | API Calls |
|-----|----------|------------|-----------|
| **Overview** | `OverviewTab.jsx` | Agent status, cost/savings donut, node composition ring, pod distribution, current vs. optimized config, cost trend chart, Karpenter panel | `getCluster`, `getClusterMetrics`, `getNodesDetailed`, `getNodeRecommendations`, `getCostTimeSeries` |
| **Optimization Settings** | (in ClusterDetails) | Architecture pref, pool diversification, scaling controls, cooldowns, automation toggles, risk strategy | `getOptimizationSettings` |
| **Node Template** | (in ClusterDetails) | vCPU range, memory range, allowed families, architecture, excluded types | `getActiveMapping` |
| **Activity Log** | (in ClusterDetails) | Historical rebalancing actions and cluster events | `getRebalancingStatus` |

### ASCPAiPage — Tabs

| Tab | Components | Data Shown |
|-----|-----------|------------|
| **Dashboard** | AutoRebalanceAuditCard + InterruptionHeatmap + RebalancingTimeline + PoolRankings | All-in-one ASCP.ai overview |
| **Rankings** | PoolRankings.jsx | Per-node ranked alternative pools, pool audit funnel, diversity metrics |
| **Heatmap** | InterruptionHeatmap.jsx | 7-day × 24-hour interruption risk grid |
| **Rebalancing** | AutoRebalanceAuditCard + RebalancingTimeline | Audit log + live timeline |
| **Decision Engine V3** | DecisionEngineV3Dashboard.jsx | State machine, ML model metrics, rejection counters, substitute status |

### RebalancingTimeline — 6 Visual Steps

| Step | Label | Meaning |
|------|-------|---------|
| 1 | New Pool Provisioned | Replacement spot EC2 launched |
| 2 | New Node Joined | Replacement node Ready in K8s |
| 3 | Node Cordoned | Source marked unschedulable |
| 4 | Pods Draining | Pods gracefully evicted from source |
| 5 | Old Node Terminated | Source EC2 terminated |
| 6 | Complete | Migration finished |

### Real-Time Status Panels (RebalancingTimeline)

| Panel | Content |
|-------|---------|
| Next Target Node | Which node will be optimized next + estimated savings |
| Cooldown Timer | Countdown to when next rebalancing can start |
| In-Progress Status | 🔄 Active / ⏳ Cooldown / ⚠️ Daily limit / ✅ Ready |
| Daily Limit | X/5 rebalances used today |

### PoolRankings — Node View vs Cluster View

| View | Displays |
|------|----------|
| **Node View (Fleet View)** | Per-node recommendations table (current type, target pool, status, cost, savings), summary cards (total nodes, eligible pools, at-risk, projected savings), savings velocity chart, instance pool distribution bar, per-node alternative pools panel |
| **Cluster View** | Coverage % across all nodes + family distribution heatmap |

### AutoRebalanceAuditCard

| Item | Content |
|------|---------|
| Toggle Switch | Auto Rebalancing ON/OFF |
| Circuit Breaker State | OPEN/CLOSED/HALF_OPEN |
| Latest 5 Decisions | Trigger, node, source/target type, status badge, timestamp |

### ClusterList — Per-Cluster Card

| Data | Source |
|------|--------|
| Cluster name, region, K8s version | `getCluster` |
| Status indicator (active/inactive/degraded) | `status` field |
| Spot ratio % gauge | `spot_count / node_count` |
| Settings toggles (auto-rebalance, rightsizing, arch, diversify, etc.) | `getOptimizationSettings` |
| Karpenter Migration card (Start / Progress / Force Complete) | `getMigrationStatus`, `startMigration`, `forceCompleteMigration` |

### Polling Strategy

| Component | Interval | Data |
|----------|----------|------|
| ClusterDetails (light) | 30s | Node state, rebalancing status, recommendations |
| ClusterDetails (heavy) | 60s | Cluster metrics, cost trends, right-sizing |
| PoolRankings | 30s | ML-ranked pool list |
| RebalancingTimeline | ~7.5s (half of check_interval) | Active rebalancing actions + cooldown state |
| VolatilityMonitor | 10 min | Market volatility regime |
| InterruptionHeatmap | 5 min | Historical interruption events |
| Karpenter status (ClusterList) | 4s | Install status per cluster |

---

## 20. Cost & Savings Calculation

**Source:** `backend/workers/tasks/cost_calculator.py`, `backend/workers/tasks/savings_calculator.py`

### Monthly Cost

```
cluster_monthly_cost = SUM(instance.price_hourly × 730)
```

- Prices from Discovery worker (AWS API)
- Only updates if cost change > $1
- Stored in `clusters.monthly_cost`

### Realized Savings (Anchored to Baseline)

```
baseline_monthly_cost = baseline_od_price_hr × node_count × 730
current_monthly_cost = SUM(current_spot_price × 730) for platform spots
realized_savings = baseline_monthly_cost - current_monthly_cost
```

### Per-Action Savings

| Field | Calculation | Source |
|-------|------------|--------|
| `actual_spot_price_hr` | From `rebalancing_action` record | `savings_calculator.py` |
| `realized_savings_hr` | `source_od_price_hr - actual_spot_price_hr` | Computed on completion |
| `realized_savings_mo` | `realized_savings_hr × 730` | Computed on completion |
| `realized_savings_pct` | `(od - spot) / od × 100` | Computed on completion |

**Rule:** Only **realized** savings (from completed actions). Never estimated.

---

## 21. Cross-Account AWS Credential Flow

**Source:** `backend/utils/aws/asg.py`, `backend/workers/tasks/discovery.py`

### Architecture

```
Platform Account (Spot Optimizer Backend)
    │
    │ SystemConfig DB:
    │   PLATFORM_AWS_ACCESS_KEY
    │   PLATFORM_AWS_SECRET
    │   PLATFORM_AWS_REGION
    │
    ▼ STS AssumeRole(customer_role_arn, external_id)
    │
Customer AWS Account (EKS Cluster)
    │
    ├── EKS: ListClusters, DescribeCluster
    ├── EC2: DescribeInstances, RunInstances (DryRun only), TerminateInstances
    ├── AutoScaling: Describe/Suspend/Resume/Detach
    └── Cost Explorer: GetCostAndUsage
```

### Credential Resolution Order

| Priority | Source | When Used |
|----------|--------|-----------|
| 1 | `Account.role_arn` + `Account.external_id` | Primary cross-account |
| 2 | `Cluster.aws_role_arn` + `Cluster.aws_external_id` | Per-cluster override |
| 3 | Environment/instance profile | Same-account fallback |

### STS AssumeRole Details

| Parameter | Value |
|-----------|-------|
| Endpoint | Regional: `https://sts.{region}.amazonaws.com` |
| Session Name | `SpotOptimizer-...` |
| External ID | From Account/Cluster model (if required by trust policy) |
| Retry | 3 attempts with exponential backoff (2^attempt seconds) |
| Same-account fallback | If AssumeRole fails + caller account == role ARN account → use env creds |

---

## Appendix: Complete File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `backend/models/cluster.py` | ~280 | Cluster, Settings, Strategy, Rules models |
| `backend/models/instance.py` | ~95 | Instance model with lifecycle enum |
| `backend/models/agent_action.py` | ~113 | AgentAction model, status/type enums |
| `backend/models/agent_identity.py` | ~85 | Agent OIDC identity model |
| `backend/workers/tasks/auto_rebalancer.py` | ~4300 | Main rebalancer: state machine, AWS sync, launch, drain |
| `backend/workers/tasks/discovery.py` | ~1050 | Discovery: EKS scan, EC2 scan, cost fetch |
| `backend/workers/tasks/emergency_rebalancer.py` | ~127 | Emergency spot interruption handler |
| `backend/workers/tasks/termination_monitor.py` | ~200 | Spot termination detection + dedup |
| `backend/workers/tasks/recovery_monitor.py` | ~400 | State sync, orphan scan, karpenter stall detect |
| `backend/workers/tasks/cost_calculator.py` | ~70 | Monthly cost aggregation |
| `backend/workers/tasks/savings_calculator.py` | ~100 | Realized savings tracking |
| `backend/services/karpenter_service.py` | ~1000 | Karpenter NodePool management, K8s client, EC2 checks |
| `backend/services/metrics_service.py` | ~120 | Organization-scoped metric aggregation |
| `backend/api/karpenter_routes.py` | ~1100 | Karpenter API endpoints + config sync |
| `backend/routers/agents.py` | ~200 | Agent register/heartbeat/result endpoints |
| `backend/routers/actions.py` | ~275 | Action CRUD + polling endpoints |
| `backend/core/api_gateway.py` | ~685 | WebSocket server for agent communication |
| `backend/core/redis_client.py` | ~37 | Redis key helper functions |
| `backend/redis_keys.py` | ~24 | Redis key pattern definitions |
| `backend/utils/aws/asg.py` | ~310 | ASG operations, STS cross-account |
| `backend/utils/aws/dry_run.py` | ~300 | Spot capacity DryRun validation |
| `backend/utils/aws/user_data.py` | ~85 | EKS bootstrap script generation |
| ~~`backend/utils/aws/fleet.py`~~ | — | **Deleted** — Karpenter handles all instance provisioning |
| `backend/scheduler.py` | ~151 | Celery beat scheduled tasks |
| `backend/services/pdb_service.py` | ~80 | PDB-safe batch % computation with Redis caching |
| `backend/schemas/cluster_schemas.py` | ~430 | Pydantic request/response schemas (incl. `pdb_safe_percent` computed field, `karpenter_only_mode`, `managed_node_group_deleted`) |
| `agent/main.py` | ~475 | Agent entry point, component lifecycle |
| `agent/actuator.py` | ~1900 | Action execution (cordon, drain, terminate, karpenter) |
| `agent/heartbeat.py` | ~380 | Heartbeat sender + health server |
| `agent/websocket_client.py` | ~320 | WebSocket client with message buffering |
| `frontend/src/components/clusters/ClusterDetails.jsx` | — | Main cluster management UI |
| `frontend/src/components/clusters/ClusterList.jsx` | — | Cluster dashboard with settings |
| `frontend/src/components/clusters/overview/OverviewTab.jsx` | — | Cluster overview with costs/nodes |
| `frontend/src/components/ascpai/RebalancingTimeline.jsx` | — | 6-step rebalancing visualizer |
| `frontend/src/components/ascpai/PoolRankings.jsx` | — | ML pool ranking tables |
| `frontend/src/components/ascpai/AutoRebalanceAuditCard.jsx` | — | Automation audit log |
| `frontend/src/components/ascpai/InterruptionHeatmap.jsx` | — | Spot interruption risk heatmap |
| `frontend/src/components/ascpai/DecisionEngineV3Dashboard.jsx` | — | Decision engine control panel |
| `frontend/src/pages/ASCPAiPage.jsx` | — | Central ASCP.ai hub page |
| `backend/workers/tasks/cleanup_tasks.py` | ~80 | Celery task to delete EKS managed node group after migration |
| `backend/services/workload_inspector.py` | ~350 | Node classification (stateless/stateful) + workload label queuing via LABEL_NODE agent actions |
