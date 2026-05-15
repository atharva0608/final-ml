# ASCP.AI Spot Optimizer — Complete Platform Reference

> **Generated**: 19 April 2026  
> **Source**: 100% verified against live codebase (`backend/`, `agent/`, `frontend/`, `ml_model/`)  
> **Scope**: ML pipeline, rebalancing, right-sizing, pod classification, EKS logic, database operations, UI components, user-configurable settings

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [ML Pipeline — ONNX Pool Ranking](#2-ml-pipeline--onnx-pool-ranking)
3. [Auto-Rebalancing System](#3-auto-rebalancing-system)
4. [Right-Sizing System](#4-right-sizing-system)
5. [Pod Classification System](#5-pod-classification-system)
6. [EKS-Related Logic](#6-eks-related-logic)
7. [Database Operations & Schema](#7-database-operations--schema)
8. [User-Configurable Settings](#8-user-configurable-settings)
9. [UI Components & API Map](#9-ui-components--api-map)
10. [Redis Key Reference](#10-redis-key-reference)
11. [Background Schedules (Celery Beat)](#11-background-schedules-celery-beat)
12. [Cross-Account AWS Credentials](#12-cross-account-aws-credentials)

---

## 1. System Architecture Overview

**Core Stack**

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API | FastAPI + Uvicorn | REST + WebSocket serving |
| Auth | JWT (HS256) + API keys | User auth + agent auth |
| DB | PostgreSQL via SQLAlchemy | Persistent state |
| Cache / State | Redis | Ephemeral state, locks, caches |
| Workers | Celery (Redis broker) | Async background tasks |
| Scheduler | APScheduler (in-process) | Lightweight recurring jobs |
| Cloud | AWS (EC2, EKS, STS, Cost Explorer) | Infrastructure management |
| K8s autoscaling | Karpenter v1 | Node provisioning |
| Frontend | React (CRA) | User interface |

**Middleware Chain** (in `backend/core/api_gateway.py`)

1. CORS (configurable origins)
2. Request timing header (`X-Process-Time`)
3. Rate limiter (Redis-backed, per-IP)
4. JWT token validation
5. Global exception handlers

**Key Files**

| File | Lines | Role |
|------|-------|------|
| `backend/workers/tasks/auto_rebalancer.py` | ~7504 | Core rebalancing loop |
| `backend/workers/tasks/ascpai_worker.py` | ~431 | ML pipeline tasks |
| `backend/services/pool_ranking_service.py` | ~2886 | ML scoring + pool ranking |
| `backend/services/karpenter_service.py` | ~1408 | NodePool CRUD |
| `backend/services/rightsizing_service.py` | ~700 | Pod resource analysis |
| `backend/services/workload_inspector.py` | ~500 | Node-level classification |
| `backend/services/workload_classifier.py` | ~600 | Controller-level classification |
| `backend/services/ml_feature_service.py` | ~800 | 45-feature ONNX input engineering |
| `agent/main.py` | ~530 | 6-component agent orchestrator |
| `agent/actuator.py` | ~1941 | K8s action executor |

---

## 2. ML Pipeline — ONNX Pool Ranking

**Source**: `backend/services/pool_ranking_service.py`, `backend/services/ml_feature_service.py`  
**Schedule**: Every 30 minutes via Celery beat (`execute_pool_ranking_pipeline`)

### 2.1 Model Files

| File | Purpose |
|------|---------|
| `ml_model/model/classifier_6.onnx` | Predicts interruption risk (0.0–1.0) per spot pool |
| `ml_model/model/regressor_6.onnx` | Predicts % savings vs on-demand (0.0–1.0) |
| `ml_model/risk_threshold.json` | `optimal_threshold: 0.35` — hard gate for pool rejection |
| `ml_model/model/category_mapping.json` | Family / size / AZ categorical encoding map |

**Model version**: `6` (stored in `clusters.model_version`)  
**Provider**: `CPUExecutionProvider` (ONNX Runtime)  
**Fallback**: If either session is `None`, pools get `risk = 0.20` (conservative default)

### 2.2 8-Step Ranking Pipeline

```
Step 1  Load all (instance_type × AZ) pool combinations from region pricing data
Step 2  Global blacklist filter — remove pools in risky_pools:{region} Redis SET
Step 3  Spot Advisor annotation — attach SA rank as ONNX feature (no gate here)
Step 4  Price fetch — drop pools with no spot or on-demand price available
Step 5  DescribeInstanceTypeOfferings capacity verification — drop unavailable
Step 6  Spot price + on-demand price fetch; estimate price where missing
Step 7  ML ONNX scoring (classifier + regressor) → blended risk + savings → unified score
Step 8  Cache top 1500 pools in global_pool_rankings:{region} (TTL 65 min)
```

### 2.3 45-Feature Input Contract

| Group | Features | Count |
|-------|----------|-------|
| Temporal | hour, day-of-week, day-of-month, month, weekend flag, business-hours flag, hour sine, hour cosine, day sine, day cosine | 10 |
| Lag | savings 1h ago, 4h ago, 24h ago | 3 |
| Rolling-window (4h + 24h) | mean, std, min, max per window | 8 |
| Price dynamics | velocity, volatility, headroom to OD, pool saturation, consecutive stable hours | 5 |
| Family-time patterns | hour avg, hour std, day-of-week avg, hour-deviation, hour z-score, weekend avg | 6 |
| Family stress | stress index, avg savings, savings std | 3 |
| Event | holiday flag, stress-event flag, days-to-nearest-event | 3 |
| Pool risk | Spot Advisor interruption index | 1 |
| Categorical encoding | family, size, AZ, 3× padding slots | 6 |
| **Total** | | **45** |

If history is insufficient, `_engineer_minimum_features()` fills historical features with zeros while preserving temporal, event, and categorical features — the input shape (1, 45) is always maintained.

### 2.4 Blended Risk Formula

```
headroom = (od_price - spot_price) / od_price
base_pressure = max(0, 1 - headroom / 0.40)
velocity_factor = 1 + max(0, price_velocity_1h × 0.5)
price_pressure = min(1.0, base_pressure × velocity_factor)

existing_normalized = (0.40 × onnx_risk + 0.35 × price_pressure) / 0.75
adaptive_weight = adaptive_confidence × 0.25

final_risk = (1 - adaptive_weight) × existing_normalized + adaptive_weight × adaptive_risk
```

**Hard overrides** (applied after blending):
- Blacklisted pool (interruption in last 24h) → `risk ≥ 0.75`
- Dry-run capacity check failed → `risk ≥ 0.65`

### 2.5 Savings Calculation

1. Raw `predicted_savings` from regressor clipped to `[0.0, 1.0]`
2. If `predicted_savings ≥ 0.99` (saturation): replace with Spot Advisor savings for the type, or fall back to direct headroom `(od - spot) / od`
3. If pool is globally flagged: effective savings reduced by `0.20`

### 2.6 Unified Scoring Formula

```
unified_score = (savings × 0.8) × (1 - risk) × reputation_multiplier × capacity_factor
```

### 2.7 Risk Gates (multi-layer filtering)

| Gate | Threshold | Source |
|------|-----------|--------|
| ONNX Hard Gate | risk > 0.35 → rejected | `risk_threshold.json` |
| Safety Net | risk > 0.50 → rejected (fallback scoring only) | `pool_ranking_service.py` |
| Circuit Breaker | >5 ONNX failures in 10 min → fallback risk = 0.20 | Redis `ascpai:ml_fail_count` |
| Fallback trigger | < 10 pools after ONNX gate → loosen to safety net | `pool_ranking_service.py` |

### 2.8 Pool Universe (counts)

| Stage | Pools Remaining |
|-------|----------------|
| Raw universe (offerings backfill) | ~600+ |
| After SA annotation | ~600+ (no gate) |
| After global blacklist | ~580–600 |
| After price fetch | ~560–590 |
| After ONNX hard gate (≤ 0.35) | ~50–200 |
| After safety net (≤ 0.50) | ~35–150 |
| Final global cache (top 1500) | 35–150 or up to 1500 |

---

## 3. Auto-Rebalancing System

**Source**: `backend/workers/tasks/auto_rebalancer.py` (~7504 lines)  
**Schedule**: Every 15 seconds (configurable via `check_interval_seconds`)

### 3.1 What It Does

Replaces On-Demand (OD) EC2 instances with cheaper Spot instances inside EKS clusters.  
Also performs Spot-to-Spot (S2S) rebalancing when a safer or cheaper pool is found.

### 3.2 Full Execution Sequence

```
1.  Stale action cleanup (PENDING/PICKED_UP > 15 min → expire)
2.  Load active clusters with auto_rebalance_enabled = True
3.  Per-cluster distributed lock (Redis SET NX, 45 min TTL + heartbeat renewal)
4.  Cross-system safety gates (circuit breakers, volatility, approval locks)
5.  AWS state sync: DescribeInstances → DB sync (lifecycle corrections, placeholder merge)
6.  WorkloadInspector classification gate: only STATELESS_ELIGIBLE nodes targeted
7.  Spot exposure limiting (target_spot_exposure_pct)
8.  PDB-aware batch size calculation
9.  OD→Spot: Phase 1 — provision replacement spot via Karpenter NodePool patch
10. Phase 2 — CORDON → DRAIN → TERMINATE old OD node
11. S2S rebalancing check (if enabled and safer pool found)
12. Cool-down writes on success / exponential backoff on failure
```

### 3.3 AWS State Sync (`_sync_instance_state_from_aws`)

- Calls `DescribeInstances` via STS assumed-role credentials
- Derives K8s node name: `ip-{private_ip}.{region}.compute.internal`
- Lifecycle corrections: requires 3 consecutive observations (RC3 guard, 600s Redis TTL)
- Empty-result protection: 3-consecutive-empty-streak guard prevents false mass-termination
- Placeholder merge: deletes `ip-xxx` placeholder rows, transfers utilization to real `i-xxx` records

### 3.4 Phase 1 — Provision Replacement Spot

| Step | Action |
|------|--------|
| 1 | Load pre-ranked alternatives from `action.metadata` |
| 2 | If none: call `PoolRankingService.rank_pools_for_node()` |
| 3 | Filter out pools with `spot:launch_blocked:{cid}:{type}:{az}` Redis key |
| 4 | Detect source architecture via `DescribeInstanceTypes` (7-day Redis cache) |
| 5 | Apply `architecture_preference` filter (amd64 / arm64 / both) |
| 6 | Validate capacity via EC2 DryRun |
| 7 | Call `KarpenterService.add_allowed_instance_type()` → patches NodePool CRD via K8s API |
| 8 | Store `phase2_params` in action metadata |
| 9 | Set `current_state = WAITING_FOR_KARPENTER` |
| 10 | Write 24h instance cooldown: `spot:rebalanced:instance:{id}` |

### 3.5 Phase 2 — Cordon, Drain, Terminate

| Step | Agent Action | Detail |
|------|-------------|--------|
| 1 | `CORDON_NODE` | Mark old node unschedulable |
| 2 | Pre-eviction delay | 2s per pod for endpoint controller propagation |
| 3 | EndpointSlice gate (E2/P2) | Verify new pod IPs in EndpointSlice with 10s kube-proxy soak |
| 4 | `DRAIN_NODE` | Evict all pods (skip DaemonSets), PDB-aware retries |
| 5 | `TERMINATE_NODE` | EC2 terminate (karpenter mode: delete K8s node → Karpenter handles EC2) |
| 6 | Post-drain verify | K8s API confirms pods vacated the drained node |

### 3.6 Spot-to-Spot (S2S) Rebalancing

Triggered when the current spot pool has deteriorated significantly but a safer/cheaper pool exists.

**Checks before triggering S2S:**
- `Δrisk ≥ 5pp` (base, +2pp HIGH vol, +4pp CRITICAL vol)
- `Δsavings ≥ 1pp` (base, +1pp HIGH vol, +2pp CRITICAL vol)
- `risk_savings_tradeoff_pct` threshold respected
- Redis key `s2s_migration:{cluster_id}:{source_pool}:{target_pool}` with 2h TTL prevents loop re-triggering

### 3.7 Safety Gates

| Gate | Redis Key / Mechanism | Block Condition |
|------|----------------------|----------------|
| Cluster cooldown | `cooldown:{cluster_id}` | Recent action completed (60 min default) |
| Circuit breaker | `spot:cluster_circuit_breaker:{cid}` | >10 failures in 10 min → 30 min block |
| Distributed action lock | `lock:node_action:{cluster_id}` (20 min TTL) | Another action in progress |
| Rebalance lock | `lock:rebalance:{cluster_id}` (45 min TTL + heartbeat) | Prevents concurrent rebalance |
| Volatility regime | `volatility_regime:{region}` | CRITICAL regime blocks new migrations |
| Manual approval | `requires_approval` setting | Action enters `pending_approval` state |
| WorkloadInspector | Redis `spot:node_classification:{cid}` | Non-STATELESS_ELIGIBLE nodes skipped |

### 3.8 Cooldowns & Backoff

| Cooldown | Key | TTL | Trigger |
|----------|-----|-----|---------|
| Instance-level (success) | `spot:rebalanced:instance:{id}` | 24h | Successful migration |
| Instance-level (failure) | `rebalance_failures:{instance_id}` | `min(300 × 2^failures, 3600)` | Each failure |
| Per-instance daily cap | `rebalance_daily_count:{instance_id}:{date}` | End of day | Max 10 retries/day |
| Action failure cooldown | Per-cluster `failure_cooldown_minutes` setting | Configurable (default 30 min) | Failed action |

### 3.9 Architecture-Aware AMI Resolution

When migrating across architectures (x86 ↔ arm64):
1. `_get_instance_arch()`: API call `DescribeInstanceTypes` with 7-day Redis cache; fallback to static ARM family set
2. `_resolve_arch_compatible_ami()`: 3-strategy resolution:
   - Exact source-name architecture swap (e.g. `amazon-eks-node` → `amazon-eks-arm64-node`)
   - Version-aware wildcard search across EKS naming schemes
   - Generic architecture wildcard as last resort

### 3.10 Rebalancing Action State Machine

States in `rebalancing_actions.current_state`:

```
CREATED → PROVISIONING → WAITING_FOR_KARPENTER → SPOT_NODE_JOINING → 
ENDPOINTS_VERIFIED → CORDONING → DRAINING → TERMINATING → COMPLETED / FAILED
```

---

## 4. Right-Sizing System

**Source**: `backend/services/rightsizing_service.py`, `backend/services/simulation_engine.py`

### 4.1 Overview

Analyzes historical pod CPU/memory metrics (P95/P99) to recommend reduced resource requests.  
Integrates with Karpenter simulation to show the projected post-resize node layout.

### 4.2 Analysis Pipeline

```
1. Metric freshness check (reject if latest metrics > 5 min old)
2. Cluster cooldown check (CooldownController)
3. Node classification filter (only STATELESS_ELIGIBLE nodes analyzed)
4. Per-controller metric aggregation over analysis_window_hours (default 168h = 7 days)
5. P95 CPU and P99 memory calculation
6. Apply SAFETY_BUFFER_PCT (20%) above P95/P99
7. Flag OVERSIZED (actual < 50% of request) or UNDERSIZED (P99 > request)
8. Optional: instance-aware check (_check_better_pool_exists)
9. Return RightSizingRecommendation list
```

### 4.3 Configuration Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `SAFETY_BUFFER_PCT` | 20% | Buffer added above P95 usage |
| `OVERSIZED_THRESHOLD_PCT` | 50% | Flag oversized if usage < 50% of request |
| `UNDERSIZED_THRESHOLD_PCT` | 95% | Flag undersized if P99 > request |
| Analysis window | 168h (7 days) | Default look-back period |
| Min data points | 100 | Minimum metrics for recommendation |

### 4.4 Instance-Aware Mode

When `instance_aware_rightsizing = True` in `ClusterOptimizationSettings`:
- After generating CPU/memory recommendation, checks if a better spot pool exists for the reduced resource footprint
- If no better pool found → recommendation is marked `is_actionable = False` and skipped
- Result: recommendations only surface when applying them would land on a cheaper spot pool

### 4.5 Karpenter Simulation Engine

**5-Pass Pool Selection:**

| Pass | Purpose |
|------|---------|
| Pass 0 | Total cost optimization — bin-pack all pods on fewest / cheapest nodes |
| Pass 1 | Exact AZ match — place pods in their current AZ if possible |
| Pass 2 | Family-first relaxation — same family, different size |
| Pass 3 | Cross-family optimization — different instance family if cheaper |
| Pass 4 | VM-only fallback — any available instance that fits pod requests |

**Additional corrections:**
- Fragmentation correction: re-allocates pods from partially-used nodes to fill fuller nodes
- Empty node cleanup: removes nodes with zero pod assignments
- Capacity-aware pod batching: batches pods to simulate Karpenter's real scheduling

### 4.6 Optimizer Coordinator

Prevents oscillation between pool optimization and right-sizing.  
Phased execution: rightsizing completes before pool rebalancing is allowed, and vice versa.

Redis lock: `optimizer:running:{cluster_id}` with TTL = `max_concurrent_rebalance_actions × 45 min`

### 4.7 Action Execution

When applied: creates `PATCH_CONTAINER_RESOURCES` AgentAction with  
`{namespace, deployment_name, container_name, cpu_request_m, memory_request_mb, cpu_limit_m, memory_limit_mb}`

Agent patches the pod spec via `apps/v1 Deployment` API; no pod restart required in most cases (rolling update).

### 4.8 Synergy Mode

When both `auto_rebalance_enabled` AND `auto_rightsizing_enabled` are ON:
- Optimization target locks to `"spot"`
- UI shows "Locked to Spot — synergy mode active" badge
- Bin-pack first → ML spot pool selection → Karpenter provisions right-sized spot node → agent migrates workloads

---

## 5. Pod Classification System

**Source**: `backend/services/workload_inspector.py`, `backend/services/workload_classifier.py`, `backend/services/cluster_service.py`  
**Schedule**: Every 9 minutes via APScheduler

### 5.1 Three-Layer Architecture

```
Layer 1: WorkloadInspector  — Node-level scan → STATELESS_ELIGIBLE / STATEFUL_PROTECTED / DRAIN_UNSAFE / SYSTEM_PROTECTED
Layer 2: WorkloadClassifier — Controller-level scan → TIER 0–4 + migration policy
Layer 3: cluster_service.py — Per-pod is_stateful determination at API request time
```

### 5.2 Layer 1 — WorkloadInspector (Node-level)

**Redis key**: `spot:node_classification:{cluster_id}` (TTL = 540s)

Evaluated in priority order:

| Priority | Condition | Classification |
|----------|-----------|---------------|
| 1 | Node is control plane or kube-system | `SYSTEM_PROTECTED` |
| 2 | Any pod has PDB with `maxUnavailable = 0` | `DRAIN_UNSAFE` |
| 3 | Any pod has PVC or is StatefulSet member | `STATEFUL_PROTECTED` |
| 4 | Any pod has `hostPath` volume | `STATEFUL_PROTECTED` |
| 5 | No pods (empty node) | `STATELESS_ELIGIBLE` |
| 6 | None of the above | `STATELESS_ELIGIBLE` |

Only `STATELESS_ELIGIBLE` nodes are candidates for auto-rebalancing.

### 5.3 Layer 2 — SmartWorkloadClassifier (Controller-level)

**Redis key**: `spot:workload_tier:{cluster_id}:{ns}/{controller_name}` (TTL = 540s)

8-step pipeline (stops at first match):

| Step | Condition | Tier | Migration Policy |
|------|-----------|------|-----------------|
| 1 | DaemonSet OR system namespace | TIER_0 | `block` — NEVER_MIGRATE |
| 2 | StatefulSet OR active PVC | TIER_1 | `anchored_only` — ANCHORED_MANUAL |
| 3 | Operator-managed DB (Postgres, MySQL, Redis, Kafka CRDs) | TIER_1 | `anchored_only` |
| 4 | KEDA queue consumer (ScaledObject managed) | TIER_2 | `spot_with_keda_gate` — SPOT_WITH_CAUTION |
| 5 | Batch/worker (celery, sidekiq, resque, dramatiq, etc.) | TIER_3 | `spot_with_keda_gate` — KEDA_GATED |
| 6 | `initialDelaySeconds > 60s` heuristic → may promote to TIER_1 | Varies | — |
| 7 | Confidence scoring (PVC count, image match, replicas, PDB, hostNetwork, readiness delay, mesh sidecar) | Validates | — |
| 8 | Fallback | TIER_4 | `spot_eligible` — SPOT_ELIGIBLE |

**Spot-friendly** = TIER_2, TIER_3, TIER_4  
**Not spot-friendly** = TIER_0, TIER_1

### 5.4 Layer 3 — Per-Pod `is_stateful` (API request time)

Five combined factors (in `cluster_service.py`):

| Factor | Logic |
|--------|-------|
| PVC / StatefulSet owner | `has_pvc OR pod.owner_kind == "StatefulSet"` → is_stateful = True |
| Node classification (Redis) | Node in STATEFUL_PROTECTED or DRAIN_UNSAFE → is_stateful = True |
| System namespace | `kube-system`, `kube-public`, `karpenter`, `monitoring`, `istio-system`, etc. → is_stateful = True |
| DaemonSet owner | `pod.owner_kind == "DaemonSet"` → is_stateful = True |
| Workload tier (Redis) | tier ≤ 1 (TIER_0 or TIER_1) → is_stateful = True |

`is_spot_friendly = NOT is_stateful`

### 5.5 Workload Labels Applied

When `WorkloadInspector.scan_cluster()` runs, it queues `LABEL_NODE` AgentActions to apply:
- `workload=stateless` on STATELESS_ELIGIBLE nodes
- `workload=stateful` on STATEFUL_PROTECTED nodes

Karpenter's dual NodePools use these labels:
- `stateless-spot` NodePool selects `workload=stateless` nodes (spot-only, weight=10)
- `stateful-od` NodePool selects `workload=stateful` nodes (on-demand-only, weight=5)
- `default` NodePool is a fallback (both capacity types, weight=1)

---

## 6. EKS-Related Logic

### 6.1 Cluster Discovery

**Source**: `backend/workers/tasks/discovery_worker.py`

- AWS `list_clusters()` + `describe_cluster()` per account
- Creates/updates `clusters` table rows with status `DISCOVERED`
- Sets `endpoint`, `ca_data`, K8s version, region
- Skips clusters flagged `is_dismissed = True`
- Runs every 10 minutes via Celery beat

### 6.2 Karpenter Installation (Per-Cluster)

Triggered by `POST /karpenter/deploy`.  
Creates `INSTALL_KARPENTER` AgentAction → agent runs via `agent/actuator.py:install_karpenter()`.

**6 steps:**

| Step | Action |
|------|--------|
| 1 | `helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter --wait --timeout 5m` |
| 2 | Configure SQS interruption queue (`KarpenterInterruptionQueue-{cluster_name}`) |
| 3 | IRSA setup: annotate ServiceAccount `eks.amazonaws.com/role-arn={iam_role_arn}` |
| 4 | Register `KarpenterNodeRole-{cluster_name}` as EKS Access Entry (EC2_LINUX type) |
| 5 | Create EC2NodeClass with AL2023 amiFamily (auto-resolves amd64/arm64) |
| 6 | Create 3 NodePools: `stateless-spot`, `stateful-od`, `default` |

### 6.3 Managed Node Group Migration & Cleanup

When all OD nodes have been drained (CHECKPOINT-E):
1. `cleanup_managed_node_group.delay(cluster_id)` Celery task fires
2. Verifies 0 OD nodes remain
3. Lists EKS node groups via `list_nodegroups()`
4. Confirms `desiredSize = 0` for all groups
5. Calls `delete_nodegroup()` per group
6. Sets `managed_node_group_deleted = True` and `karpenter_only_mode = True` on cluster
7. All subsequent rebalancing skips ASG API calls permanently

**Migration API Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /clusters/{id}/start-migration` | POST | Start managed node group → Karpenter migration |
| `GET /clusters/{id}/migration-status` | GET | Phase, node counts, spot %, flag states |
| `POST /clusters/{id}/force-complete-migration` | POST | Admin force-set both migration flags |

### 6.4 Cluster Cleanup (DELETE `/clusters/{id}`)

**Source**: `backend/services/cluster_cleanup_service.py`  
All steps are best-effort (failures logged, do not block DB deletion).

| Resource | Action |
|----------|--------|
| K8s (via agent) | Queue `UNINSTALL_KARPENTER` action (helm uninstall + namespace cleanup) |
| IAM | Delete `KarpenterControllerRole-{name}`, `KarpenterNodeRole-{name}`, instance profile |
| SQS | Delete `KarpenterInterruptionQueue-{name}` |
| EventBridge | Delete `KarpenterRule-{name}-*` rules |
| OIDC | Delete IAM OIDC identity provider (unique per cluster, derived from `describe_cluster`) |
| Redis | Flush all per-cluster cache keys |

### 6.5 EKS Access Entry Management

When creating Karpenter node role:
- Registers `KarpenterNodeRole-{cluster_name}` as EKS access entry type `EC2_LINUX`
- This allows Karpenter-provisioned nodes to join the cluster automatically without `aws-auth` ConfigMap

### 6.6 Architecture-Aware Node Provisioning

Karpenter EC2NodeClass uses `amiFamily: AL2023` which auto-selects the correct AMI for both `amd64` and `arm64`.

When the backend triggers a cross-architecture migration (via `_resolve_arch_compatible_ami()`):
1. First tries to find an exact AMI name swap (e.g. `amazon-eks-node` → `amazon-eks-arm64-node`)
2. Falls back to version-aware wildcard SSM lookups
3. Falls back to generic architecture wildcard

### 6.7 Karpenter NodePool Patching

**Source**: `backend/services/karpenter_service.py`  
ML rankings → NodePool CRD → Karpenter provisions from ML-approved types only.

| Method | Purpose |
|--------|---------|
| `sync_ml_rankings_to_nodepool()` | Push top-10 ML-ranked instance types to NodePool every hour |
| `add_allowed_instance_type()` | Add single instance type to NodePool (used by auto-rebalancer, Phase 1) |
| `patch_node_pool_allowed_types()` | Batch patch NodePool requirements |
| `switch_to_ondemand()` | Force capacity-type=on-demand; auto-revert after 12h TTL |
| `revert_to_spot()` | Revert from OD fallback |

Retry: up to 2 retries with delays [5s, 15s]; rollback restores previous NodePool state on failure.

### 6.8 OIDC Federation

**Source**: `backend/services/oidc_federation_service.py`

Manages IAM OIDC identity providers for EKS clusters to enable IRSA (IAM Roles for Service Accounts).  
Used during Karpenter setup and cleanup.

### 6.9 Agent DaemonSet Networking

DaemonSet config:
- `hostNetwork: true` — uses node network namespace for IMDS access and host metrics
- `dnsPolicy: ClusterFirstWithHostNet` (explicitly set, E11 fix)
- Tolerates all taints (`operator: Exists`)
- Mounts `/host/proc` for psutil-based CPU/memory collection

---

## 7. Database Operations & Schema

**DB**: PostgreSQL via SQLAlchemy ORM  
**Migrations**: Alembic

### 7.1 Key Tables

| Table | Model File | Purpose |
|-------|-----------|---------|
| `clusters` | `models/cluster.py` | Cluster registry |
| `instances` | `models/instance.py` | EC2 instance tracking |
| `rebalancing_actions` | `models/rebalancing_action.py` | Action state machine |
| `agent_actions` | `models/agent_action.py` | In-cluster K8s actions |
| `pod_metrics` | `models/pod_metric.py` | Pod CPU/memory time-series |
| `rightsizing_proposals` | `models/rightsizing_proposal.py` | Right-sizing recommendations |
| `spot_price_history` | `models/spot_price.py` | Rolling 24h spot price data |
| `on_demand_pricing` | `models/pricing.py` | On-demand price catalog |
| `cluster_optimization_settings` | `models/cluster.py` | Per-cluster automation settings |
| `optimization_strategy` | `models/cluster.py` | Risk/savings tradeoff profile |
| `stateless_runtime_rules` | `models/cluster.py` | Rebalancing runtime rules |
| `stateful_rules` | `models/cluster.py` | Stateful workload rules |
| `accounts` | `models/account.py` | AWS account registry |
| `organizations` | `models/organization.py` | Multi-tenant organizations |
| `users` | `models/user.py` | User accounts + auth |
| `onboarding_state` | `models/onboarding.py` | AWS setup wizard state |
| `system_configs` | `models/system_config.py` | Platform-wide key-value settings |

### 7.2 `clusters` — Field Reference

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `id` | String(36) PK | UUID | Primary key |
| `name` | String(indexed) | — | Cluster name |
| `account_id` | String FK | — | Parent account |
| `arn` | String unique | — | AWS ARN |
| `region` | String | — | AWS region |
| `status` | Enum | `DISCOVERED` | PENDING / DISCOVERED / ACTIVE / INACTIVE / ERROR / TERMINATED / DISCONNECTED / DEGRADED |
| `karpenter_mode` | Enum | NULL | NULL / dry_run / auto |
| `optimization_mode` | String(20) | `BALANCED` | COST_FIRST / BALANCED / NO_DOWNTIME_FIRST |
| `model_version` | String(10) | `6` | Pinned ML model version |
| `auto_rebalance_enabled` | Boolean | False | Master rebalance switch |
| `rightsizing_enabled` | Boolean | False | Master rightsizing switch |
| `managed_node_group_deleted` | Boolean | False | True after EKS nodegroup deleted |
| `karpenter_only_mode` | Boolean (via settings) | False | Skip all ASG API code paths |
| `api_key` | String | NULL | Agent auth token (auto-generated) |
| `aws_role_arn` | String | NULL | Cross-account IAM role ARN |
| `ca_data` | Text | NULL | Base64 cluster CA cert |

### 7.3 `rebalancing_actions` — State Machine

| Status | Meaning |
|--------|---------|
| `in_progress` | Actively being executed |
| `waiting_agent` | Waiting for agent to execute K8s actions |
| `pending_approval` | Awaiting manual approval |
| `completed` | Finished successfully |
| `failed` | Execution failed |
| `deferred` | Delayed by safety gate |

State machine path: `CREATED → PROVISIONING → WAITING_FOR_KARPENTER → SPOT_NODE_JOINING → ENDPOINTS_VERIFIED → CORDONING → DRAINING → TERMINATING → COMPLETED / FAILED`

Optimistic locking via `lock_version` field prevents concurrent writes.

### 7.4 `agent_actions` — Types

| Type | Purpose |
|------|---------|
| `EVICT_POD` | Graceful pod eviction with PDB checks |
| `CORDON_NODE` | Mark unschedulable |
| `UNCORDON_NODE` | Mark schedulable (rollback) |
| `DRAIN_NODE` | Evict all pods |
| `LABEL_NODE` | Apply/remove node labels |
| `TERMINATE_NODE` | EC2 terminate (4 modes: karpenter, replacement, scaledown, asg_no_decrement) |
| `FORCE_DELETE_NODE` | Delete K8s Node object + clear finalizers |
| `UPDATE_DEPLOYMENT` | Update replicas or image |
| `PATCH_CONTAINER_RESOURCES` | Right-sizing CPU/memory patch |
| `INSTALL_KARPENTER` | Helm install + NodePool creation |
| `UNINSTALL_KARPENTER` | Helm uninstall + namespace cleanup |
| `REMOVE_POD_FINALIZERS` | Clear stuck finalizers |

AgentAction expires after 1 hour (`expires_at = created_at + 1h`).  
PENDING/PICKED_UP stale cutoff = 15 minutes.  
Action heartbeat TTL = 120 seconds.

### 7.5 `pod_metrics` — Time-Series Data

Collected every **60 seconds** by agent's `PodMetricsCollector`.  
Fields: `pod_name`, `namespace`, `controller_name`, `controller_kind`, `node_name`, `cpu_millicores`, `memory_mb`, `cpu_request_m`, `memory_request_mb`, `cpu_limit_m`, `memory_limit_mb`, `timestamp`.

Used by `RightSizingService` over a 7-day window for P95/P99 analysis.

### 7.6 `spot_price_history` — Rolling 24h Retention

Collected every 10 minutes by `pricing_collector.py` via `describe_spot_price_history` (6h lookback).  
Fields: `instance_type`, `az`, `region`, `price`, `timestamp`.

Used by `MLFeatureService` for lag features, rolling stats, and price dynamics.

### 7.7 `system_configs` — Key-Value Store

Used for:
- `PLATFORM_AWS_ACCESS_KEY` / `PLATFORM_AWS_SECRET` / `PLATFORM_AWS_REGION` — platform identity
- `PLATFORM_AWS_ACCOUNT_ID` — used in CloudFormation deep-link
- Per-cluster cooldown state (`ClusterCooldownState` model)
- DB write-through for cooldown values (via `CooldownController`)

---

## 8. User-Configurable Settings

All settings are per-cluster and stored across four related DB tables.  
Managed via `PUT /api/v1/clusters/{id}/optimization-settings` using the `UnifiedOptimizationSettings` Pydantic schema.

### 8.1 Automation Controls (`cluster_optimization_settings`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `auto_rebalance_enabled` | bool | false | Master toggle — entire rebalancing system is OFF until true |
| `auto_rightsizing_enabled` | bool | false | Master toggle for right-sizing |
| `auto_stateful_rightsizing_enabled` | bool | false | Enable stateful node right-sizing |
| `target_spot_exposure_pct` | int | 100 | Max % of nodes that should be Spot (80 = keep 20% OD) |
| `max_concurrent_rebalance_actions` | int | 1 | How many OD nodes to replace simultaneously |
| `rebalance_batch_percent` | int | auto | Max % of OD nodes to target per cycle |
| `check_interval_seconds` | int | 15 | How often the rebalancer evaluates this cluster |
| `cooldown_override_minutes` | int | null (=60) | Override default 60-min cluster cooldown |
| `failure_cooldown_minutes` | int | 30 | Wait time after a failed action before retry |
| `manual_approval_required` | bool | false | If true, actions enter `pending_approval` state |
| `architecture_preference` | str | `"both"` | `"amd64"` / `"arm64"` / `"both"` — filters pool selection |
| `drain_timeout_minutes` | int | 15 | Max time to wait for pod eviction during drain |
| `maintain_standby` | bool | false | Keep a hot standby Spot node ready |
| `diversify_pools` | bool | false | Enforce instance type diversity across Spot fleet |
| `max_family_diversification_cap_pct` | int | 40 | Max % of fleet that can be same instance family |
| `instance_type_diversification_pct` | int | 100 | 100% = every node uses a different type |
| `min_node_count` | int | 1 | Hard floor — never scale below this |
| `scale_down_threshold_pct` | int | 20 | CPU + mem below which node is considered idle |
| `scale_down_stabilization_minutes` | int | 15 | How long util must stay below threshold |
| `enable_ascp_auto_scaler` | bool | false | Built-in auto-scaler (separate from rebalancing) |
| `karpenter_only_mode` | bool | false | Skip all ASG detection code paths |
| `instance_aware_rightsizing` | bool | false | Only recommend resize if a better spot pool exists |
| `min_topology_spread` | int | 1 | Minimum AZ spread during consolidation |

### 8.2 Optimization Strategy (`optimization_strategy`)

| Setting | Default | Description |
|---------|---------|-------------|
| `strategy_type` | `BALANCED` | `COST_FIRST` / `BALANCED` / `NO_DOWNTIME_FIRST` / `CUSTOM` |
| `risk_ceiling_percent` | 25 | Maximum acceptable interruption risk % |
| `min_savings_percent` | 15 | Minimum savings % to justify migration |
| `volatility_tolerance_percent` | 20 | Acceptable spot price volatility |
| `migration_penalty_multiplier` | 1.5 | Penalty for migration overhead in scoring |
| `diversity_strictness_level` | `Medium` | Pool diversity enforcement level |
| `risk_savings_tradeoff_pct` | 20 | Accept X% more expensive if X% safer (S2S) |

**Strategy presets and their DE V3 risk ceilings:**

| Strategy | DE V3 Ceiling | Volatile Adjustment |
|----------|--------------|----------------------|
| `COST_FIRST` | 25% | -5% |
| `BALANCED` | 20% | -5% |
| `NO_DOWNTIME_FIRST` | 10% | -5% |

### 8.3 Stateless Runtime Rules (`stateless_runtime_rules`)

| Setting | Default | Description |
|---------|---------|-------------|
| `max_rebalances_per_24h` | 5 | Daily hard cap — prevents runaway cycles |
| `respect_pdb_enabled` | true | Honor PodDisruptionBudgets during drain |
| `prewarm_minutes` | 0 | Pre-warm time for substitute nodes |
| `substitute_strategy` | `PREWARMED` | `PREWARMED` or `ON_DEMAND` |
| `resize_cooldown_minutes` | 120 | Cooldown after right-sizing operation |
| `resize_headroom_multiplier` | 1.2 | Extra capacity margin for resize |
| `volatility_safety_multiplier` | 1.35 | Safety margin for volatile pools |
| `fresh_cluster_stabilization_minutes` | 1440 | 24h stabilization for newly added clusters |

### 8.4 Stateful Rules (`stateful_rules`)

| Setting | Default | Description |
|---------|---------|-------------|
| `manual_resize_allowed` | true | Allow manual resize of stateful nodes |
| `require_approval` | true | Require human approval for stateful changes |
| `block_spot_for_stateful` | true | Prevent spot migration for stateful workloads |
| `max_downscale_percent` | 25 | Max downscale per operation |

### 8.5 Cluster-Level Flags (`clusters` table)

| Field | Description |
|-------|-------------|
| `karpenter_mode` | `NULL` (not installed) / `dry_run` (insights only, NodePool NOT patched) / `auto` (full autonomous) |
| `optimization_mode` | `COST_FIRST` / `BALANCED` / `NO_DOWNTIME_FIRST` |
| `model_version` | ML model version selector (default `"6"`) |

### 8.6 Settings API

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/clusters/{id}/optimization-settings` | Get current settings + computed `pdb_safe_percent` |
| PUT | `/api/v1/clusters/{id}/optimization-settings` | Partial update via `UnifiedOptimizationSettings` |
| PATCH | `/api/v1/clusters/{id}/auto-rebalance?enabled=true` | Simple ON/OFF toggle |
| POST | `/api/v1/clusters/{id}/start-migration` | Enable everything + start migration mode |
| GET | `/api/v1/ascpai/clusters/{id}/effective-configuration` | Returns computed runtime config |

---

## 9. UI Components & API Map

### 9.1 Frontend Structure

```
frontend/src/
├── App.js                        # 30+ routes
├── services/api.js               # 47 API modules (Axios)
├── store/                        # 3 Zustand stores (useStore, useASCPStore, useHibernationStore)
├── hooks/                        # useAdaptivePolling (5s active / 30s idle), useDashboard, usePermission, useAuth
└── components/
    ├── dashboard/                # Fleet overview + widgets
    ├── clusters/                 # Cluster management (ClusterList, ClusterDetails, OverviewTab)
    ├── ascpai/                   # ML Engine UI (PoolRankings, RebalancingTimeline)
    ├── right-sizing/             # Rightsizing dashboard + Karpenter tab
    ├── hibernation/              # Schedule management
    ├── cleanup/                  # Resource hygiene
    ├── onboarding/               # AWS setup wizard
    ├── governance/               # Permission gates & JIT
    ├── approvals/                # Ticket & access modals
    └── admin/                    # Super-admin panel
```

### 9.2 Dashboard Widgets

| Widget | API Endpoint | Purpose |
|--------|-------------|---------|
| Cost KPI card | GET `/api/v1/metrics/dashboard` | Total monthly cost |
| Savings KPI card | GET `/api/v1/metrics/dashboard` | Total savings |
| Savings bar chart | GET `/api/v1/metrics/dashboard` | Savings by category |
| Fleet composition pie | GET `/api/v1/clusters` | Instance type mix |
| Activity feed | GET `/api/v1/audit/logs` | Recent events |
| Cluster health cards | GET `/api/v1/clusters` | Cluster status overview |
| Agent status | GET `/api/v1/admin/agent-fleet` | DaemonSet health |
| Spend forecast | GET `/api/v1/metrics/cost/timeseries` | Predicted future costs |
| Trends chart | GET `/api/v1/multi-cluster/trends` | 30-day savings + spot trends |
| Pending approvals | GET `/api/v1/approvals/` | Actions awaiting approval |

### 9.3 Cluster Details — Tabs

| Tab | Component | Key Endpoints |
|-----|-----------|--------------|
| Overview | `OverviewTab.jsx` | `GET /clusters/{id}` + rebalancing status |
| Nodes | `NodeList.jsx` | `GET /clusters/{id}/nodes/detailed` |
| ML Engine | `ascpai/PoolRankings.jsx` | `POST /ascpai/pools/rankings` |
| Node Templates | `NodeTemplateTab.jsx` | `GET /clusters/{id}/node-template/active` |
| Right-Sizing | `RightSizingKarpenterTab.jsx` | `GET /clusters/{id}/rightsizing/recommendations` |
| Settings | `ClusterDetails.jsx` | `PUT /clusters/{id}/optimization-settings` |

### 9.4 ML Engine / ASCP.AI UI

| Element | Endpoint | Purpose |
|---------|----------|---------|
| Pool rankings table | `POST /ascpai/pools/rankings` | Show ML-ranked spot pools |
| Rebalancing timeline | `GET /ascpai/rebalancing/status` | 6-step live visualization |
| Approve/Deny buttons | `POST /ascpai/rebalancing/approve` / `deny` | Manual approval flow |
| Node recommendations | `GET /ascpai/clusters/{id}/node-recommendations` | Risk bar per node |

### 9.5 Right-Sizing UI

**Stateless Nodes Table Columns:**

| Column | Content | Notes |
|--------|---------|-------|
| Node | Node name | Plain text |
| Current Type | e.g. `m5.xlarge` | Current instance type |
| CPU / Mem | e.g. `72% / 58%` | Red if >80% |
| Bin-Packed Size | e.g. `m5.large` | Recommended instance size |
| Optimal Action | `⚠ Scale Up` / `✦ Resize + Spot` / `↓ Resize Only` / `⟳ Spot Pool` / `✓ No Change` | Strategy badge |
| Best Spot Pool | `instance_type`, `az`, `risk_score`, `predicted_savings_pct` | Hidden when auto-mode ON |
| Savings | `$XX/mo` | Green (savings) or red (cost increase) |
| EV | `XX%` | Expected Value percentage |
| Actionable | ✓ Actionable / No Better Pool / — | Instance-aware check result |
| Action | Button (manual) or "Auto-managed" (greyed, auto ON) | |

### 9.6 Onboarding Wizard

| Step | Component | Action |
|------|-----------|--------|
| Welcome | `WelcomeStep.jsx` | Navigation |
| Connect | `ConnectStep.jsx` | CloudFormation deep-link or role ARN input |
| Verify | `VerifyStep.jsx` | `POST /api/v1/onboarding/verify` (STS assume-role) |
| Success | `SuccessStep.jsx` | Navigate to dashboard |

---

## 10. Redis Key Reference

### ML / Pool Ranking

| Key | TTL | Written By | Purpose |
|-----|-----|-----------|---------|
| `global_pool_rankings:{region}` | 3900s (65 min) | pool_ranking_service | Global ranked pool cache |
| `spot_price:{region}:{az}:{type}` | 600s (real) / 3600s (estimated) | pricing_collector | Latest spot price |
| `od_price:{region}:{type}` | varies | pricing scraper | On-demand price |
| `spot_advisor:{region}:{type}:Linux` | 90000s (25h) | spot_advisor_scraper | Interruption index + savings |
| `risky_pools:{region}` | varies | pool_ranking_service | Global SET of failed pool keys |
| `ascpai:ml_fail_count` | 600s | pool_ranking_service | Circuit breaker failure counter |
| `spot:validated:{region}:{type}:{az}` | 1800s | DryRun step | Capacity validation cache |
| `spot:dryrun_count:{region}` | 3600s | DryRun step | Budget enforcement |

### Rebalancing

| Key | TTL | Written By | Purpose |
|-----|-----|-----------|---------|
| `spot:rebalanced:instance:{id}` | 24h | auto_rebalancer | Per-instance migration cooldown |
| `rebalance_failures:{instance_id}` | exponential | auto_rebalancer | Failure backoff counter |
| `rebalance_daily_count:{instance_id}:{date}` | end-of-day | auto_rebalancer | Per-instance daily cap (max 10) |
| `s2s_migration:{cluster_id}:{src}:{tgt}` | 2h | auto_rebalancer | Prevents S2S loop re-trigger |
| `spot:launch_blocked:{cid}:{type}:{az}` | 1h | auto_rebalancer | Block pool after 1 failure |
| `lock:rebalance:{cluster_id}` | 2700s (45 min) + heartbeat | auto_rebalancer | Distributed rebalance lock |
| `lock:node_action:{cluster_id}` | 1200s (20 min) | auto_rebalancer | Per-cluster action lock |
| `blacklist_failures:{pool_key}` | 86400s (24h) | auto_rebalancer | Per-cluster pool rejection counter |
| `cooldown:{cluster_id}` | configurable | cooldown_controller | Cluster-level cooldown |

### Karpenter

| Key | TTL | Purpose |
|-----|-----|---------|
| `spot:ondemand_fallback:{cid}` | 43200s (12h) | OD fallback mode flag |
| `karpenter:detected:{cid}` | 300s | Karpenter installation detection cache |
| `spot:karpenter:installed:{cid}` | 3600s | Karpenter installed flag |
| `spot:cluster_circuit_breaker:{cid}` | 1800s (30 min) | Execution circuit breaker |
| `spot:exec_fail_window:{cid}` | 600s (10 min) | Failure count window |

### Workload Classification

| Key | TTL | Purpose |
|-----|-----|---------|
| `spot:node_classification:{cluster_id}` | 540s | Node-level classification (Layer 1) |
| `spot:workload_tier:{cluster_id}:{ns}/{ctrl}` | 540s | Controller-level tier (Layer 2) |
| `node_resource_profile:{node_id}` | varies | Pod-request floor for rightsizing |

### Volatility & Market

| Key | TTL | Purpose |
|-----|-----|---------|
| `volatility_regime:{region}` | varies | NORMAL / HIGH / CRITICAL |
| `market_factor:{region}` | varies | 0.80–1.20× risk ceiling multiplier |

---

## 11. Background Schedules (Celery Beat)

| Task | Interval | Purpose |
|------|----------|---------|
| `execute_rebalancing` | Every 15s | Auto-rebalancing core loop |
| `execute_pool_ranking_pipeline` | Every 30 min | ML ONNX pool ranking |
| `sync_karpenter_nodepools` | Every 60 min | Push ML rankings to NodePool CRDs |
| `collect_spot_prices` | Every 10 min | Spot price collection |
| `scrape_spot_advisor` | Every 25h | AWS Spot Advisor data refresh |
| `discovery_worker` | Every 10 min | EKS cluster discovery |
| WorkloadInspector scan (APScheduler) | Every 9 min | Node + controller classification |
| Substitute reconciliation (APScheduler) | Every 5 min | Substitute node state machine |
| Volatility detection (APScheduler) | Every 1h | Update `volatility_regime` |
| Stale action monitor | Periodic | Expire stuck PENDING actions |
| Recovery monitor | Periodic | Detect and recover stuck rebalancing |
| Cleanup managed node group | Triggered | Post-migration EKS nodegroup deletion |

---

## 12. Cross-Account AWS Credentials

**Source**: `backend/services/sts_credential_broker.py`

**Flow:**
1. User provides an IAM Role ARN during onboarding (CloudFormation template creates the role)
2. Backend calls `sts.assume_role(RoleArn=..., ExternalId=..., RoleSessionName=...)` using platform credentials from `SystemConfig` table
3. Temporary credentials (`access_key`, `secret_key`, `session_token`) are cached in Redis (TTL = STS credential expiry - 5 min)
4. All AWS API calls (EC2, EKS, STS, Cost Explorer, Pricing) use these assumed-role credentials

**Platform identity** (set in Super Admin → Platform Identity):
- `PLATFORM_AWS_ACCESS_KEY`
- `PLATFORM_AWS_SECRET`  
- `PLATFORM_AWS_REGION`
- `PLATFORM_AWS_ACCOUNT_ID`

**Security**: External ID (unique UUID per customer) prevents confused-deputy attacks.

---

## Appendix: All Risk Thresholds Quick Reference

| Threshold | Value | Source | Purpose |
|-----------|-------|--------|---------|
| ONNX Hard Gate | 0.35 | `risk_threshold.json` | Reject pools from ML pipeline |
| Safety Net | 0.50 | `pool_ranking_service.py` | Absolute max (fallback scoring) |
| ONNX Fallback | 0.20 | `pool_ranking_service.py` | Default when circuit breaker trips |
| Risk Ceiling (user) | 25% default | `optimization_strategy` | Per-cluster configurable ceiling |
| Market Factor | 0.80–1.20× | `market_factor:{region}` Redis | Multiplied into risk ceiling |
| S2S Opportunistic Δrisk | ≥5pp base | `auto_rebalancer.py` | Must be this much safer |
| S2S Opportunistic Δsavings | ≥1pp base | `auto_rebalancer.py` | Must also be cheaper |
| HIGH vol boost | +2pp risk, +1pp savings | `auto_rebalancer.py` | Widens S2S thresholds |
| CRITICAL vol boost | +4pp risk, +2pp savings | `auto_rebalancer.py` | Widens even more |
| Blacklist floor | 0.75 | `compute_blended_risk()` | Pool with ITN in last 24h |
| Dry-run fail floor | 0.65 | `compute_blended_risk()` | Pool failed capacity check |
| At-Risk UI badge | >60% | `PoolRankings.jsx` | Counts nodes in summary card |
| UI Warning bar | ≥75% of ceiling | `PoolRankings.jsx` | Amber "Approaching" label |
| UI Breach bar | >100% of ceiling | `PoolRankings.jsx` | Red glow + "⚠ S2S next cycle" |
| DE V3 COST_FIRST | 25% | `05_risk_filter.py` | Strategy-based ceiling |
| DE V3 BALANCED | 20% | `05_risk_filter.py` | Strategy-based ceiling |
| DE V3 NO_DOWNTIME | 10% | `05_risk_filter.py` | Strategy-based ceiling |
| Trust Phase 0 | force 15% | `05_risk_filter.py` | First 30 min of cluster life |
| Trust Phase 1 | force 20% | `05_risk_filter.py` | 30 min – 2h of cluster life |
