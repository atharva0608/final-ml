# Pod Distribution, Rebalancing, Cost Selection, Buffering, and Scaling Deep Dive

## 1. Purpose

This document explains, in implementation-level detail, how this platform:

- classifies pods as spot-friendly vs non-spot-friendly (stateful/protected)
- distributes pods to spot and on-demand nodes
- selects node types for best cost while respecting safety constraints
- applies and executes rebalancing actions
- uses buffer capacity
- exposes all of this in UI and API
- stores and tracks data in DB and Redis
- coordinates scaling behavior with Karpenter, KEDA, and other safety systems

This is based on the current code in:

- backend/modules/placement_optimizer.py
- backend/api/ascpai_routes.py
- backend/services/cluster_service.py
- backend/workers/tasks/auto_rebalancer.py
- backend/services/keda_service.py
- backend/workers/tasks/keda_installer.py
- backend/api/karpenter_routes.py
- backend/api/keda_routes.py
- frontend/src/components/clusters/overview/RebalancedDistribution.jsx
- frontend/src/services/api.js
- backend/models/*.py (cluster, instance, pod_metric, rebalancing_action)
- agent/karpenter_watcher.py

---

## 2. End-to-End Architecture (High Level)

1. Agent/metrics ingestion updates pod and node runtime data.
2. backend/services/cluster_service.py builds node+pod detailed view with workload classification.
3. backend/api/ascpai_routes.py get_recommended_config calls placement optimizer.
4. backend/modules/placement_optimizer.py computes recommended OD/Spot/Buffer layout and pod-to-node assignments.
5. Frontend pulls recommended config and renders live pod placement in RebalancedDistribution.
6. If applying config, backend creates RebalancingAction rows (staggered).
7. auto_rebalancer worker executes drain/migrate/terminate flow with safety gates.
8. Karpenter launches replacement capacity and may also act independently (observed via watcher).
9. KEDA/HPA are frozen/restored around sensitive drain windows to avoid autoscaler races.

---

## 3. Workload Identification: How Pod Type Is Determined

### 3.1 Source of truth inputs

From backend/services/cluster_service.py get_cluster_nodes_detailed:

- latest pod metrics (recent 5-minute window)
- pod metadata (including has_pvc when available)
- controller kind (Deployment, StatefulSet, DaemonSet, etc.)
- namespace
- Redis node classification cache (spot:node_classification:{cluster_id})
- Redis workload tier cache (spot:workload_tier:{cluster_id}:{namespace}/{controller})

### 3.2 Stateful/protected decision factors

A pod is treated as stateful/protected by nature if any of these apply:

1. PVC present (has_pvc true, or PVC found in volume spec)
2. controller_kind is StatefulSet
3. system namespace (kube-system, karpenter, monitoring, etc.)
4. controller_kind is DaemonSet
5. workload tier from Redis is critical (tier <= 1)

A pod can also be stateful by placement if:

- node classification indicates protected state, such as STATEFUL_PROTECTED or DRAIN_UNSAFE

The output per pod includes:

- is_stateful (boolean)
- stateful_reason (by_nature or by_placement)

### 3.3 Cluster-level workload type

get_cluster_workload_type classifies cluster as:

- UNKNOWN: no pod data
- STATELESS: no PVC and no StatefulSet indicators
- STATEFUL: all pods indicate stateful pattern
- MIXED: partial stateful indicators

This endpoint also uses Redis cache key spot:workload_type:{cluster_id} when present.

---

## 4. Pod Distribution Logic: Spot-Friendly vs Non-Spot-Friendly

### 4.1 Conversion into optimizer input

backend/modules/placement_optimizer.py pods_from_cluster_detail converts pods into PodSpec with:

- cpu_request_millicores
- memory_request_mb
- is_stateful_by_nature
- controller_kind

Important rule in conversion:

- by_nature stateful pods are OD-only
- by_placement stateful pods are not permanently considered stateful by nature

### 4.2 Hard lifecycle split in optimizer

PlacementOptimizer v3 uses strict two-phase separation:

- Stateful pods: on-demand only (hard constraint)
- Spot-eligible pods: spot preferred; OD overflow allowed if spot full

This behavior is explicitly defined in optimizer class comments and enforcement logic.

---

## 5. Node Selection for Best Cost (Core Optimization)

## 5.1 Inputs used for optimization

- available pools from Redis market rankings (instance type, az, lifecycle, hourly cost, risk)
- live pod requests from cluster detail
- optional user-provided OD/Spot/Buffer counts
- current monthly cost baseline from running instances

### 5.2 Feasibility constraints

Optimizer enforces:

- minimum 2 vCPU
- minimum 4 GiB memory
- minimum pod density threshold (max_pods >= 11)
- AWS ENI max-pods limits by instance type
- when using spot, minimum 3 spot nodes for AZ diversity
- stateful pods must fully fit OD nodes (candidate rejected otherwise)

### 5.3 Packing algorithms used

1. Stateful on OD:
- First-Fit Decreasing (FFD)

2. Spot-friendly on Spot:
- Best-Fit Decreasing with Topology Spread Constraints (BFD-TSC)
- prefers nodes maintaining AZ diversity before relaxing diversity

3. Overflow step:
- unfit spot pods attempt fit on existing OD nodes

4. Buffer nodes:
- optional nodes created as spare capacity

### 5.4 Candidate search strategy

When node counts are not fixed:

- enumerate top OD pools and top Spot pools
- compute minimum OD and Spot counts needed
- search nearby count ranges (O and S combinations)
- keep valid placements with zero hard misplacements
- choose cheapest by monthly cost (tie-break by higher placement_score)

### 5.5 Scoring model

placement_score combines:

- AZ concentration penalty
- family concentration penalty
- average CPU utilization reward
- average interruption probability penalty

Then clamped to [0, 1].

### 5.6 Cost model

- recommended monthly = sum(hourly cost of all selected nodes * 730)
- savings monthly = max(0, current monthly - recommended monthly)
- savings pct = savings monthly / current monthly

---

## 6. Buffer Capacity: How It Is Used

Buffer nodes are represented in optimizer output as role=buffer.

Current behavior:

- buffer count can be computed as adjustable recommendation
- buffer nodes are part of recommended_state and cost calculations
- buffer nodes provide spare headroom and can reduce risk under burst/drain pressure

UI note:

- latest UI hides buffer nodes from the visible node list in RebalancedDistribution by filtering role != buffer
- however, buffer count can still appear in summary badges if present

---

## 7. Rebalancing Execution: How Actions Are Applied

### 7.1 API level

POST /api/v1/ascpai/clusters/{cluster_id}/apply-recommended-config

- creates RebalancingAction rows for OD -> Spot migrations
- supports explicit node assignments or auto-detection of excess OD nodes
- writes action metadata including scheduled_start_at and stagger group
- stagger delay is 30s between groups
- limits parallel starts to max 3 per batch

### 7.2 Worker level

auto_rebalancer task processes in-progress actions and executes steps like:

- select/validate source and target pools
- cordon source node
- drain evictable pods
- trigger/verify replacement capacity
- terminate source node
- cleanup and mark completed/failed

### 7.3 State machine and journaling

RebalancingAction includes:

- current_state (state machine transitions)
- action_step (INJECTED -> WAITING_SPOT -> DRAINING -> TERMINATING -> CLEANUP -> DONE)
- metadata journal and timestamps

This supports crash-safe resume and idempotent progress.

---

## 8. Safety and Guardrails During Drain/Migration

From auto_rebalancer and eviction safety integration:

- tier gate blocks critical workloads (TIER_0 and TIER_1)
- per-controller eviction gate checks drain safety
- single-replica protection can temporarily scale to 2 before eviction
- pod termination grace period respected from pod spec
- DaemonSet and mirror pods skipped for eviction
- blocked controllers are marked and skipped instead of forcefully evicted

---

## 9. KEDA Behavior: What KEDA Does Here

### 9.1 Detection and inventory

KedaService can:

- detect installation (CRD + operator running)
- list and query ScaledObjects
- read ScaledObject metric names

Detection result is cached in Redis key:

- spot:keda_detection:{cluster_id} (TTL 300s)

### 9.2 Pause/restore during rebalancing

KEDA ScaledObjects are paused and restored around drain windows via:

- pause_scaled_object
- restore_scaled_object

Paused state is stored in Redis:

- spot:keda_paused_state:{namespace}/{name} (TTL 600s)

### 9.3 Install/uninstall lifecycle

KEDA install/uninstall is queued as agent actions and monitored by Celery task:

- workers.keda.monitor_install_actions
- timeout defaults to 300s
- install-in-progress flag key: spot:keda_installing:{cluster_id}

### 9.4 Why KEDA is frozen during migration

To avoid autoscaler race conditions while pods are being drained/rescheduled:

- freeze autoscaler state before eviction
- restore autoscaler state after drain completes
- stale freeze cleanup task removes orphaned freeze locks

---

## 10. Karpenter Behavior: What Karpenter Does Here

### 10.1 Karpenter role in node lifecycle

Karpenter is the node provisioning and consolidation engine in actual cluster operations.

The platform:

- computes recommended lifecycle and sizing intent
- emits apply actions and migration plan
- relies on Karpenter to provision/satisfy capacity in-cluster

### 10.2 Karpenter config and mode

Cluster has karpenter_mode:

- dry_run: insights only
- auto: autonomous management

Karpenter config API exposes strategy, family/arch bounds, spot targets, and automation toggles.

### 10.3 Independent Karpenter activity visibility

agent/karpenter_watcher.py streams K8s events and forwards Karpenter-originated events to backend, such as:

- NodeClaimCreated
- NodeClaimDeleted
- Consolidated
- DisruptionBlocked
- InsufficientCapacity

This gives backend visibility even when Karpenter acts independently.

---

## 11. UI Behavior: Exactly What User Sees

### 11.1 Main panel

frontend/src/components/clusters/overview/RebalancedDistribution.jsx

Shows:

- current vs recommended node counts and monthly costs
- pod distribution counters (total, spot-eligible, stateful-by-nature, misplaced)
- live pod placement cards by lifecycle group
- AZ distribution
- warnings
- refresh controls and YAML download

### 11.2 Real-time pod mapping behavior

- API fetch via ascpaiAPI.getRecommendedConfig
- auto-refresh every 60 seconds
- node cards default expanded (pods visible without click)
- pod names shown from recommended_state.node_breakdown[].pod_names
- current UI filters out role=buffer from visible node list

### 11.3 API methods used by UI

From frontend/src/services/api.js:

- getRecommendedConfig
- applyRecommendedConfig
- downloadRecommendedConfigYaml

---

## 12. API Contracts Used in This Flow

### 12.1 Get recommendation

GET /api/v1/ascpai/clusters/{cluster_id}/recommended-config

Returns:

- current_state
- recommended_state
- pod_distribution
- adjustable_params
- warnings

recommended_state includes per-node:

- type, lifecycle, role, az
- vcpu, memory_gb, max_pods
- pods count and pod_names list
- cpu/memory used and capacities
- hourly and monthly cost

### 12.2 Apply recommendation

POST /api/v1/ascpai/clusters/{cluster_id}/apply-recommended-config

Creates staggered migration actions and returns action IDs with estimated timeline.

### 12.3 Download YAML

GET /api/v1/ascpai/clusters/{cluster_id}/recommended-config/yaml

Generates NodePool YAML. Behavior depends on cluster optimization toggles:

- permissive OD-focused mode when automation features are off
- optimized split mode when relevant automation is on

---

## 13. DB Data Model: What Is Persisted

## 13.1 Core tables involved

1. clusters
- cluster identity, region, status, karpenter_mode, aggregate node/cost fields

2. instances
- instance_id, type, lifecycle (spot/on-demand), az, state, util, node_name

3. pod_metrics
- pod identity, node, controller, cpu/memory usage and requests, metadata, timestamp

4. rebalancing_actions
- trigger, source_pool, target_pool, status, timing, metadata, state machine columns, step journal

5. cluster_optimization_settings
- automation toggles and guardrail tuning:
  - auto_rebalance_enabled
  - auto_rightsizing_enabled
  - auto_stateful_rightsizing_enabled
  - diversify_pools
  - cooldown and batch/safety controls

6. stateful_rules and stateless_runtime_rules
- approval/safety behavior and runtime policy constraints

### 13.2 Data freshness behavior

- pod detail pulls recent metrics (5-minute cutoff)
- stale pods on dead nodes are filtered out
- only running instances are considered in current node state
- dedup logic prefers real EC2 instance records over placeholder agent records

---

## 14. Redis Keys Used in This System

Important keys for this topic:

- spot:node_classification:{cluster_id}
- spot:workload_tier:{cluster_id}:{namespace}/{controller}
- spot:keda_detection:{cluster_id}
- spot:keda_paused_state:{namespace}/{name}
- spot:keda_installing:{cluster_id}
- spot:autoscaler_freeze:{namespace}/{controller}
- spot:stabilization_lock:{cluster_id}
- market ranking cache keys used by recommendation loader

These keys coordinate cache, safety, and transient runtime state between API and workers.

---

## 15. How Scaling Happens in Practice (Responsibility Split)

## 15.1 Karpenter

Karpenter handles node-level provisioning and consolidation in the cluster.

In this platform, Karpenter is the execution engine for capacity realization after recommendation/decision.

## 15.2 KEDA

KEDA handles event/queue-driven workload autoscaling at controller level.

During migration windows, KEDA ScaledObjects may be temporarily paused and restored to avoid scaling races.

## 15.3 HPA and internal safety helpers

HPA/KEDA freeze + restore plus single-replica protective scale-out are used to maintain service continuity during drains.

## 15.4 Platform worker orchestration

auto_rebalancer coordinates:

- what to drain
- when to drain
- what to block
- what to restore

Karpenter and KEDA then enact their respective layers (nodes and workload autoscaling).

---

## 16. Practical Example Flow

1. API reads live node+pod details.
2. Pods are classified into stateful/protected and spot-eligible.
3. Optimizer computes cheapest valid OD/Spot/Buffer layout with constraints.
4. UI shows recommended nodes and pod names per node.
5. User (or automation) applies recommendation.
6. Rebalancing actions are queued in staggered groups.
7. Worker cordons and drains selected nodes with policy checks.
8. Autoscalers are frozen/restored around migration for stability.
9. Karpenter provisions replacement capacity and old nodes terminate.
10. UI refresh reflects final pod placement and cost delta.

---

## 17. Key Guarantees and Tradeoffs

### Guarantees

- Stateful-by-nature pods are never intentionally placed on spot by optimizer.
- Spot rollout respects hard fit constraints and max-pods limits.
- Rebalancing is guarded with tier checks and eviction safety gates.
- Autoscaler freeze/restore reduces disruption risk during migration.

### Tradeoffs

- Spot overflow to OD may reduce maximum savings but preserves fitability.
- Buffer capacity increases cost but improves resilience.
- Strong safety gates can delay migrations in constrained clusters.

---

## 18. Operations Checklist

For a healthy recommendation and rebalancing cycle:

1. Ensure recent pod_metrics are arriving.
2. Ensure instances table has correct running lifecycle state.
3. Verify ranking cache is populated for region.
4. Verify Karpenter mode/config as intended.
5. Verify KEDA detect status if workload uses ScaledObjects.
6. Monitor rebalancing_actions status and action_step transitions.
7. Confirm UI refresh shows expected pod_names and lifecycle split.

---

## 19. Summary

This implementation uses a strict safety-first workload split (stateful on OD, stateless mostly on Spot), then optimizes cost through constrained bin-packing and staged migration orchestration. It combines:

- optimizer-level hard placement rules
- worker-level drain safety and autoscaler coordination
- Karpenter node provisioning
- KEDA autoscaling control
- UI transparency with live pod-to-node visibility

The result is a practical and auditable path to cost reduction without ignoring workload safety and migration stability.
