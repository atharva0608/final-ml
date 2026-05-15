# Spot Optimizer — Workload Architecture Single Source of Truth

> **Schema Version:** WIE v4.4 | PodPlacementEngine v2.0 (5-layer) | PlacementController §9 | PlacementAdvisor §4.4 | Auto-Rebalancer Pillar-1  
> **Last Audited:** Apr 30 2026 — reflects live codebase state  
> **Purpose:** Authoritative reference for all workload-related engines, API endpoints, data sources, concurrency controls, and known gaps.

---

## Table of Contents

1. [Service Classification](#1-service-classification)
2. [Workload Identification Engine (WIE)](#2-workload-identification-engine-wie)
3. [Workload Classification](#3-workload-classification)
4. [Placement Advisor](#4-placement-advisor)
5. [Placement Controller](#5-placement-controller)
6. [Auto-Rebalancer](#6-auto-rebalancer)
7. [Node Bin Packing / Consolidation](#7-node-bin-packing--consolidation)
8. [AgentAction System](#8-agentaction-system)
9. [Execution Controller](#9-execution-controller)
10. [Full Flow Traces](#10-full-flow-traces)
11. [API Endpoint Mapping — /optimize](#11-api-endpoint-mapping----optimize)
12. [Redis Key Registry](#12-redis-key-registry)
13. [Celery Beat Schedule](#13-celery-beat-schedule)
14. [Concurrency Controls](#14-concurrency-controls)
15. [DB Tables Queried in Optimize APIs](#15-db-tables-queried-in-optimize-apis)
16. [Observability & Audit Coverage](#16-observability--audit-coverage)
17. [Silent Failure Paths](#17-silent-failure-paths)
18. [Environment Variables Affecting Optimization](#18-environment-variables-affecting-optimization)
19. [Performance Risks & N+1 Queries](#19-performance-risks--n1-queries)
20. [Karpenter Integration](#20-karpenter-integration)
21. [Dead / Unconsumed Backend Features](#21-dead--unconsumed-backend-features)
22. [Known Gaps & Inconsistencies](#22-known-gaps--inconsistencies)
23. [Deep Audit — Verified Q&A (45 Questions)](#23-deep-audit--verified-qa-45-questions)

---

## 1. Service Classification

All services in `backend/services/` classified by primary role.

| Service File | Classification | Notes |
|---|---|---|
| `workload_identification_engine.py` | **Execution Engine** | Core scoring pipeline; deterministic; read-only |
| `pod_placement_engine.py` | **Execution Engine** | 5-layer plan materialisation: StateGuard→AnchorPlanner→PodSelector→StabilityOptimizer→AZDistributor→CapacityPlanner→BinPacker→CostProjector→PlanValidator; pure-function; no Redis/DB writes |
| `workload_classifier.py` | **Decision Engine** | App-type detection via label/annotation heuristics |
| `workload_inspector.py` | **Data Aggregator** | Builds `WorkloadInput` from K8s + DB + metrics data |
| `placement_advisor_service.py` | **Decision Engine** | Computes OD/Spot split targets, placement policies |
| `placement_controller_service.py` | **Execution Engine** | Reconciles actual pods against policy; dispatches EVICT_POD |
| `placement_rollout_service.py` | **Execution Engine** | Stateful rollout orchestration for StatefulSets |
| `execution_controller.py` | **Execution Engine** | Multi-step zero-downtime node replacement pipeline |
| `auto_rebalancer.py` (task) | **Execution Engine** | State machine for pool node drain/terminate/replace cycle |
| `optimizer_coordinator.py` | **Decision Engine** | Pool ranking, rotation decisions, spot ML coordination |
| `eviction_safety.py` | **Decision Engine** | Guardrail checks for eviction safety (PDB, freeze, queue) |
| `guardrail_engine.py` | **Decision Engine** | Cluster-wide guardrail enforcement |
| `cooldown_controller.py` | **Utility** | Cooldown state management via Redis |
| `circuit_breaker.py` | **Utility** | Circuit breaker open/close state management |
| `distributed_locks.py` | **Utility** | Redis-based distributed locking primitives |
| `aws_pricing_service.py` | **Data Aggregator** | OD/Spot price lookups from AWS + Redis cache |
| `pool_ranking_service.py` | **Decision Engine** | ML-based spot pool risk/ranking computation |
| `pool_rotation_service.py` | **Execution Engine** | Karpenter nodepool type injection and rotation |
| `karpenter_service.py` | **Execution Engine** | Karpenter NodePool CRUD + type management |
| `keda_service.py` | **Execution Engine** | KEDA install/uninstall + ScaledObject management |
| `substitute_manager.py` | **Execution Engine** | Spot substitute node provisioning + lifecycle |
| `metrics_service.py` | **Data Aggregator** | Aggregates cluster/node/workload metrics |
| `observability_logger.py` | **Utility** | Structured decision audit trail (Redis + DB) |
| `audit_service.py` | **Utility** | General audit log writes to `audit_logs` table |
| `decision_engine_service.py` | **Decision Engine** | Wraps multi-factor optimization decision logic |
| `simulation_engine.py` | **Decision Engine** | What-if simulation for placement policy proposals |
| `pdb_service.py` | **Data Aggregator** | PodDisruptionBudget discovery and validation |
| `rightsizing_service.py` | **Decision Engine** | CPU/memory right-sizing proposals |
| `ml_feature_service.py` | **Data Aggregator** | Feature extraction for ML ranking models |
| `global_ema_service.py` | **Data Aggregator** | Exponential moving average for pool interruption rates |
| `adaptive_itn_service.py` | **Data Aggregator** | Adaptive interruption score with decay |
| `hygiene_service.py` | **Execution Engine** | Cluster hygiene enforcement (labels, taints, cleanup) |
| `blacklist_service.py` | **Utility** | Pool/instance blacklist management |
| `diversity_enforcer.py` | **Decision Engine** | Enforces multi-pool, multi-AZ diversity rules |
| `instance_catalog_service.py` | **Data Aggregator** | Instance type catalog from AWS + cache |
| `emergency_handler.py` | **Execution Engine** | Emergency spot interrupt response trigger |
| `emergency_event_processor.py` | **Execution Engine** | Processes SQS spot interruption events |
| `cluster_service.py` | **Data Aggregator** | Primary cluster CRUD and state aggregation |
| `governance_service.py` | **Utility** | Org-level policy governance enforcement |
| `notification_service.py` | **Utility** | Slack/PagerDuty/webhook notifications |

---

## 2. Workload Identification Engine (WIE) — Full Logic

**File:** `backend/services/workload_identification_engine.py`  
**Schema Version:** 4.4  
**Role:** Read-only, deterministic, confidence-first scoring pipeline. No mutations, no ML, no eBPF.

---

### 2.1 Entry Points

| Invoked By | Mode | Frequency |
|---|---|---|
| `WorkloadIdentificationEngine.slow_loop_classify()` | production | Every 10 min via Celery beat |
| `placement_advisor_task.py` → `run_placement_cycle()` | production | Every 30 min |
| Direct API `/workloads/classify` | simulation | On-demand (never persisted) |

---

### 2.2 WorkloadInput — All Input Fields

`WorkloadInput` is a Python dataclass built by `WorkloadDataCollector` before being passed to `classify_workload()`.

**Identity fields:**

| Field | Type | Source |
|---|---|---|
| `workload_id` | `str` | `"{namespace}/{name}"` — unique within cluster |
| `cluster_id` | `str` | DB cluster UUID |
| `namespace` | `str` | K8s metadata.namespace |
| `name` | `str` | K8s controller name |
| `controller_kind` | `str` | `Deployment / StatefulSet / DaemonSet / Job / CronJob` |

**Scheduling:**

| Field | Type | Notes |
|---|---|---|
| `priority_class` | `Optional[str]` | `pod.spec.priorityClassName`; `None` = unknown |
| `priority_class_value` | `Optional[int]` | Resolved `PriorityClass.value`; `None` = not fetched |

**Replica state:**

| Field | Type | Notes |
|---|---|---|
| `replicas` | `int` | Desired replicas; default 1 |
| `ready_replicas` | `Optional[int]` | `None` = unknown (reduces confidence) |

**Resilience:**

| Field | Type | Notes |
|---|---|---|
| `has_pdb` | `bool` | PodDisruptionBudget exists |
| `pdb_min_available` | `Optional[int]` | Numeric minAvailable |
| `pdb_max_unavailable` | `Optional[int]` | `0` = strict zero-downtime |
| `has_topology_spread` | `bool` | topologySpreadConstraints present |
| `topology_min_domains` | `Optional[int]` | `minDomains` value |
| `has_pod_anti_affinity` | `bool` | podAntiAffinity present |

**Exposure:**

| Field | Type | Notes |
|---|---|---|
| `service_type` | `Optional[str]` | `ClusterIP / NodePort / LoadBalancer` |
| `has_ingress` | `bool` | At least one Ingress routes to this workload |
| `inbound_services` | `int` | Count of distinct Services routing inbound traffic |

**Data safety:**

| Field | Type | Notes |
|---|---|---|
| `data_safety` | `str` | Set by `determine_data_safety()` before scoring — `STATEFUL / CACHE / EPHEMERAL` |
| `has_pvc` | `bool` | At least one PVC attached |

**Age and stability:**

| Field | Type | Notes |
|---|---|---|
| `workload_age_hours` | `float` | Hours since K8s `creationTimestamp` |
| `workload_age_days` | `float` | Same in days |
| `stable_for_minutes` | `int` | Minutes since last restart or replica change |
| `last_restart_reason` | `Optional[str]` | `OOMKilled / CrashLoopBackOff / etc.` |
| `restart_rate_normalized` | `Optional[float]` | vs cluster baseline; `None` = no baseline yet |
| `restart_count_per_hour` | `float` | Absolute fallback when baseline absent |

**Metrics quality:**

| Field | Type | Notes |
|---|---|---|
| `metrics_stale_minutes` | `int` | Default `999` (METRICS_ABSENT_VALUE = no data ever) |

**Readiness:**

| Field | Type | Notes |
|---|---|---|
| `readiness_initial_delay` | `Optional[int]` | `initialDelaySeconds`; `None` = no probe |

**Traffic (service mesh only):**

| Field | Type | Notes |
|---|---|---|
| `outbound_dominant_pct` | `Optional[float]` | % traffic to single upstream; `None` = Istio unavailable → **no signal emitted** |

**Leader election:**

| Field | Type | Notes |
|---|---|---|
| `ready_endpoint_count` | `int` | From EndpointSlice; `1` = likely leader |

**Zone placement:**

| Field | Type | Notes |
|---|---|---|
| `observed_zones` | `List[str]` | Actual node AZ labels where pods run |
| `has_declared_spread` | `bool` | topology spread OR pod anti-affinity |

**Labels / annotations:**

| Field | Type | Notes |
|---|---|---|
| `owner_labels` | `Dict[str,str]` | `metadata.labels` |
| `annotations` | `Dict[str,str]` | `metadata.annotations` — used by override system |

**Classifier bridge (set before scoring):**

| Field | Type | Notes |
|---|---|---|
| `detected_app_type` | `Optional[str]` | e.g. `"postgresql"`, `"celery_worker"`, `"stateless_service"` |
| `classifier_confidence` | `float` | `0.0–1.0` from workload_classifier.py |

---

### 2.3 classify_workload() — 10-Step Pipeline

```
WorkloadInput
    │
    Step 1: validate_no_synthetic_defaults()        ← log zeros that look like collection gaps
    Step 2: determine_role_with_signals()            ← SYSTEM / CONTROL_PLANE / APPLICATION
    Step 3: compute_criticality_with_signals()       ← 0–10 → Tier (Platinum/Gold/Silver/Bronze)
    Step 4: compute_confidence()                     ← 1–10
    Step 4a: apply_staleness_penalty()               ← metrics stale > 60min → penalty
    Step 5: get_confidence_state_with_coldstart()    ← DRAFT / PROVISIONAL / CONFIRMED
    Step 6: compute_spot_score_with_signals()        ← 0–10 + is_spot_friendly()
    Step 5a: validate_signals_completeness()         ← min 3 signals, all groups present
    Step 7: Build WorkloadClassification object      ← with az_spread_required, disruption_safe
    Step 8: apply_overrides()                        ← Redis override → annotation override
    Step 9: enforce_safety_invariants()              ← hard blocks (ALWAYS run, can't be skipped)
    Step 10: enforce_confidence()                    ← no-op currently; hook for future
    │
    WorkloadClassification (output)
```

---

### 2.4 determine_role() — 4 Rules, First Match Wins

```python
1. controller_kind == "DaemonSet"             → SYSTEM
2. namespace in system_namespaces             → SYSTEM
   (kube-system, karpenter, spot-optimizer, cert-manager, monitoring, istio-system, linkerd, …)
3. priority_class in SYSTEM_PRIORITY_CLASSES  → SYSTEM or CONTROL_PLANE
   - name in {kube-controller-manager, kube-scheduler, etcd, kube-apiserver} → CONTROL_PLANE
   - otherwise                                → SYSTEM
4. owner_labels["app.kubernetes.io/component"] in {controller-manager, scheduler, etcd, apiserver}
                                              → CONTROL_PLANE
5. default                                    → APPLICATION
```

Per-cluster override: `spot:wie:system_namespaces:{cluster_id}` Redis key extends the default set.

---

### 2.5 compute_criticality() — Score 0–10

**Baseline:** `5` for APPLICATION role (SYSTEM always returns 10, CONTROL_PLANE always returns 9).

| Condition | Δ Score |
|---|---|
| `priority_class_value >= 10000` | `+3` |
| `priority_class_value >= 1000` | `+2` |
| `priority_class_value >= 100` | `+1` |
| `has_pdb AND pdb_max_unavailable == 0` (strict PDB) | `+2` |
| `has_pdb` (any PDB) | `+1` |
| `service_type == LoadBalancer` OR `has_ingress` | `+2` |
| `service_type == NodePort` | `+1` |
| `inbound_services >= 5` (heavy hub) | `+2` |
| `inbound_services >= 3` (moderate hub) | `+1` |
| `data_safety == STATEFUL` | `+2` |
| `data_safety == CACHE` | `+1` |
| `replicas == 1 AND inbound_services >= 2 AND (LB/NP/Ingress)` (singleton exposed) | `+1` |

→ `criticality_to_tier()`: ≥9 → **Platinum**, ≥6 → **Gold**, ≥3 → **Silver**, else → **Bronze**

---

### 2.6 compute_spot_score() — Score 0–10

**Base by controller kind:**

| Kind | Base |
|---|---|
| `Deployment` | 6 |
| `ReplicaSet` | 6 |
| `Job` | 7 |
| `CronJob` | 7 |
| `StatefulSet` | 1 |
| `DaemonSet` | 0 |
| Unknown | 5 |

**Adjustments:**

| Condition | Δ Score |
|---|---|
| `has_pdb AND replicas >= 2` (resilience gate passed) | `+1` |
| `has_topology_spread OR has_pod_anti_affinity` | `+1` |
| `has_declared_spread AND observed_zones >= 2` (multi-AZ confirmed) | `+1` |
| `readiness_initial_delay > 60s` (very slow cold-start) | `−2` |
| `readiness_initial_delay > 30s` | `−1` |
| `readiness_initial_delay < 30s` (fast readiness) | `+1` |
| `restart_rate_normalized > 2.0x` (much worse than baseline) | `−2` |
| `restart_rate_normalized > 1.5x` | `−1` |
| `restart_count_per_hour > 2.0` (Deployment/RS, no baseline) | `−1` |
| `restart_count_per_hour > 1.0` (StatefulSet, no baseline) | `−1` |
| `outbound_dominant_pct > 0.80` (tightly coupled) | `−2` *(only when not None)* |
| `outbound_dominant_pct > 0.60` | `−1` *(only when not None)* |
| `ready_endpoint_count == 1 AND inbound_services > 0` (leader) | `−2` |
| `CronJob AND current_run_minutes > 120` (long-running) | `−1` |

**Stateful cap (hard):**

```
data_safety == STATEFUL:
  _is_stateful_spot_safe():
    - detected_app_type in QUORUM_TYPES (postgres, kafka, etcd…) AND classifier_confidence >= 0.4 → False (score = 0)
    - replicas >= 3 AND has_pdb AND has_declared_spread AND observed_zones >= 2              → cap at 4
    - otherwise                                                                               → cap at 0
```

**`is_spot_friendly()` — two rules (both return True):**

```
Rule A (Resilient): spot_score >= 4 AND has_pdb AND replicas >= 2
Rule B (Stateless):  spot_score >= 6 AND data_safety == EPHEMERAL
                     AND controller_kind in (Deployment, ReplicaSet)
```

---

### 2.7 compute_confidence() — Score 1–10

**Baseline:** `8`

| Condition | Δ Score |
|---|---|
| `metrics_stale_minutes > 20` (stale) | `−3` |
| `metrics_stale_minutes > 10` | `−2` |
| `conflicting_signals == True` | `−2` |
| `workload_age_hours < 24` (new workload) | `−2` |
| `workload_age_hours < 72` | `−1` |
| `last_restart_reason in (CrashLoopBackOff, OOMKilled)` | `−1` |
| `has_declared_spread AND observed_zones >= 2` | `+1` |

> **Note:** `metrics_stale_minutes == 999` (ABSENT) is treated as neutral — no penalty. Only explicit staleness (value present and above threshold) is penalized.

**apply_staleness_penalty()** — called before cold-start check:

```
metrics_stale_minutes >= METRICS_FORCE_DRAFT_THRESHOLD (999) → no penalty
metrics_stale_minutes >= 60 → penalty = min(3, stale_minutes // 60), cap confidence at 1
```

**Confidence states:**

| Score Range | State | Cold-start override |
|---|---|---|
| `< 5` | `DRAFT` | — |
| `5–7` | `PROVISIONAL` | — |
| `≥ 8` | `CONFIRMED` | → `PROVISIONAL` if engine age < 24h |

**Cold start protection:** `get_confidence_state_with_coldstart()` caps CONFIRMED → PROVISIONAL for the first 24 hours of cluster observation. Tracked via `spot:wie:engine_age:{cluster_id}` Redis key (set once via SETNX, never expires).

---

### 2.8 WIE v4.4 Placement Intent Signals

Two new fields derived in every classification cycle:

**`az_spread_required`** (`bool`):
```python
workload.has_declared_spread AND len(workload.observed_zones) >= 2
```
Both declared spread (topology constraints OR anti-affinity) AND observed pods in ≥2 zones must be true.  
Used by: PlacementAdvisor to build multi-AZ node affinity rules.

**`disruption_safe`** (`bool`):
```python
replicas >= 2
AND stable_for_minutes >= 30
AND ready_replicas is not None
AND (
    (has_pdb → ready_replicas - 1 >= pdb_min_available)
    OR (no PDB → ready_replicas >= 2)
)
```
Used by: PlacementController rollout engine to decide whether to proceed to next pod.

---

### 2.9 enforce_safety_invariants() — Hard Blocks

Runs **after** overrides — **cannot be bypassed by any override**.

| Invariant | Condition | Action |
|---|---|---|
| Stateful without resilience | `data_safety == STATEFUL AND spot_friendly AND NOT _is_stateful_spot_safe()` | Force `spot_friendly = False` |
| Singleton | `replicas == 1 AND spot_friendly` | Force `spot_friendly = False` (guaranteed outage on eviction) |

Signal added when blocked: `"invariant_blocked:singleton_never_spot"` or `"override_blocked:stateful_without_resilience"`.

---

### 2.10 Override System (2-tier, bounded by safety)

**Override load priority:** Redis (API-set) → K8s annotation → none

**Redis override key:** `spot:wie:override:{cluster_id}:{workload_id}`  
Format: `{"spot_override": true|false, "tier_override": "Gold", "reason": "...", "expires_at": "..."}`  
Expiry: field `expires_at` in payload; Redis TTL set externally.

**K8s annotation overrides:**

| Annotation | Values | Effect |
|---|---|---|
| `aura.io/spot-override` | `"true"` / `"false"` | Forces `spot_friendly` |
| `aura.io/tier-override` | `Platinum / Gold / Silver / Bronze` | Forces `tier` |
| `aura.io/role-override` | `APPLICATION` | Only APPLICATION is allowed override |

**`spot-optimizer/tier`** (workload_classifier.py annotation): sets TIER_0–TIER_4 directly, wins immediately.

**Safety validation before applying:**
- Cannot force STATEFUL workload to spot without strong resilience signals
- Cannot force singleton (replicas=1) to spot
- Cannot override tier for SYSTEM role

**In simulation mode:** overrides are skipped entirely (`is_simulation=True` → `apply_overrides()` returns immediately).

---

### 2.11 determine_data_safety() — 3 Outputs

Priority order (first match wins):

```
1. Classifier bridge: detected_app_type in STATEFUL_TYPES AND classifier_confidence >= 0.3
   → STATEFUL (postgresql, mysql, mongodb, elasticsearch, etcd, zookeeper, kafka, …)
2. detected_app_type == "redis" AND NOT has_pvc AND NOT StatefulSet
   → CACHE
3. controller_kind == StatefulSet OR has_pvc
   → STATEFUL
4. workload name OR app.kubernetes.io/name label matches CACHE_IMAGE_PATTERNS
   (redis, memcached, dragonfly, keydb, hazelcast, varnish, …)
   → CACHE
5. default
   → EPHEMERAL
```

---

### 2.12 ClassificationGuard — Consumer API

Every downstream consumer MUST use these methods:

| Method | Gate | Used By |
|---|---|---|
| `is_actionable(c)` | `confidence_state == CONFIRMED` | PlacementController, Advisor (automation) |
| `is_spot_eligible(c)` | `spot_friendly == True` | Placement-detail pod scoring |
| `is_drainable(c)` | CONFIRMED + NOT Platinum + NOT (Gold AND not spot) | Auto-rebalancer |
| `is_visible(c)` | Always `True` | UI — all states shown with indicators |
| `can_act(c)` | CONFIRMED | All automated evictions |
| `can_suggest(c)` | PROVISIONAL or CONFIRMED | UI suggestions |
| `get_consumer_action(c)` | DRAFT→IGNORE, PROVISIONAL→SUGGEST_ONLY, CONFIRMED→ACTIONABLE | Logging/audit |

---

### 2.13 Slow Loop Orchestration

`WorkloadIdentificationEngine.slow_loop_classify(cluster_id)` — runs every 10 min:

```
1. Check EngineCircuitBreaker — if tripped → skip cycle (uses last-known-good Redis)
2. _snapshot_pod_states() — Redis pipeline scan of all spot:wie:pod_state:{cid}:* keys
   → frozen deep-copy snapshot (not affected by fast-loop writes during scoring)
3. get_cluster_engine_age_hours() — cold-start guard
4. get_system_namespaces() — cluster-specific system NS override from Redis
5. _collect_workloads() — DB + K8s agent data → list[WorkloadInput]
6. get_prev_scores() → Redis(900s) → DB fallback → sort by criticality desc
7. For each workload:
   a. detect_missing_critical_fields()
   b. detect_conflicting_signals()
   c. classifier bridge: classify_workload (workload_classifier.py) → detected_app_type + confidence
   d. determine_data_safety()
   e. classify_workload() → WorkloadClassification (10-step pipeline)
   f. EngineCircuitBreaker.check_and_trip() if error
8. GracefulDegradation.handle_partial_k8s_failure() → SKIP_WRITES if >50% errored
9. _write_to_db() — with should_write() suppression
10. _write_to_redis() — serialize_classification() → sanitize_classification_output()
    → pipeline.setex(key, 900, json.dumps(data))
11. Update spot:wie:prev_scores:{cid} (TTL 900s)
12. _cleanup_stale_classifications() — remove DB records for workloads no longer in K8s
13. _collect_and_emit_metrics() → spot:wie:metrics:{cid} Redis hash (TTL 3600s)
```

---

### 2.14 DB Write Suppression — `should_write()`

Only writes to DB when **any** of these are true:
- First classification (no previous record)
- `abs(new.spot_score - prev.spot_score) + abs(new.criticality_score - prev.criticality_score) >= 1`
- `spot_friendly` changed
- `tier` changed
- `confidence_state` changed
- `az_spread_required` changed
- `disruption_safe` changed

Hash-only match (`input_hash == prev.input_hash`) is **not sufficient** to suppress — output fields must also be unchanged.

---

### 2.15 Circuit Breaker

`EngineCircuitBreaker` — per cluster:

| Parameter | Value |
|---|---|
| `TRIP_THRESHOLD_PCT` | `0.20` (>20% errors in a cycle → trip) |
| `TRIP_TTL_SECONDS` | `600` (10 min auto-reset) |
| Redis key | `spot:wie:circuit_breaker:{cluster_id}` |
| Behavior when tripped | Log `wie_circuit_breaker_active`; consumers read last-known-good from Redis |

---

### 2.16 EventDebouncer + ClusterRateLimiter

**EventDebouncer** — per-workload, collapses burst re-classification events:

| Cluster size | Debounce window |
|---|---|
| > 200 workloads | 30 s |
| 50–200 workloads | 20 s |
| < 50 workloads | 15 s |

Redis key: `spot:wie:debounce:{cluster_id}:{workload_id}` — `setex(window, "1")`

**ClusterRateLimiter** — per-cluster aggregate cap:

| Parameter | Value |
|---|---|
| Max tasks/cluster/minute | 200 |
| Redis key | `spot:wie:rate_limit:{cluster_id}` (TTL 60s) |

---

### 2.17 Graceful Degradation

| Failure | Mode | Behavior |
|---|---|---|
| Redis failure | `SKIP_WRITES` | Log, skip cycle |
| DB failure | `db_failure` | Redis writes continue, DB skipped |
| K8s partial failure >50% | `SKIP_WRITES` | Skip all writes, use last-known-good |
| K8s partial failure ≤50% | `CONTINUE` | Write successful results only |
| Corrupted Redis JSON | — | Delete key, return `None` |

---

### 2.18 Redis Keys Summary (WIE)

| Key | TTL | Content |
|---|---|---|
| `spot:wie:classification:{cid}:{ns}/{ctrl}` | 900s | Full serialized `WorkloadClassification` JSON |
| `spot:wie:pod_state:{cid}:{ns}/{ctrl}` | varies | `{restart_count, ready_pods, observed_zones, stable_for_minutes, …}` |
| `spot:wie:override:{cid}:{workload_id}` | custom | Active operator override |
| `spot:wie:circuit_breaker:{cid}` | 600s | Tripped = "1" |
| `spot:wie:engine_age:{cid}` | no TTL | ISO timestamp of first observation |
| `spot:wie:debounce:{cid}:{workload_id}` | 15–30s | Debounce lock |
| `spot:wie:rate_limit:{cid}` | 60s | Running task count |
| `spot:wie:metrics:{cid}` | 3600s | Redis HASH of engine health metrics |
| `spot:wie:prev_scores:{cid}` | 900s | `{workload_id: criticality_score}` map |
| `spot:wie:system_namespaces:{cid}` | custom | Per-cluster override of system namespaces |
| `spot:restart_baseline:{cid}:{kind}` | 3600s | Median restart rate per controller kind |

---

### 2.19 Simulation Isolation Contract

`SimulationIsolationContract.assert_not_simulation()` is called at **every** Redis and DB write path. A simulation-tagged result (`is_simulation=True`) raises `RuntimeError` if it reaches a write path. Overrides are skipped in simulation mode.

---

## 3. Workload Classifier (`workload_classifier.py`) — Full Logic

**File:** `backend/services/workload_classifier.py`  
**Role:** Stateless 8-step classifier called from WIE classifier bridge (step C4 in slow loop). Assigns TIER_0–TIER_4 and `detected_app_type`.

---

### 3.1 Tier Definitions

| Tier | Name | Migration Policy | Examples |
|---|---|---|---|
| `TIER_0` | `NEVER_MIGRATE` | `block` | DaemonSets, kube-system, karpenter NS |
| `TIER_1` | `ANCHORED_MANUAL` | `anchored_only` | PostgreSQL, MySQL, MongoDB, Kafka, Etcd |
| `TIER_2` | `SPOT_WITH_CAUTION` | `spot_with_keda_gate` | KEDA queue workers (RabbitMQ, SQS, Kafka consumers) |
| `TIER_3` | `KEDA_GATED` | `spot_with_keda_gate` | Batch workers (Celery, Sidekiq, Temporal) |
| `TIER_4` | `SPOT_ELIGIBLE` | `spot_eligible` | Stateless web/API services (default) |

---

### 3.2 `classify_workload()` — 8-Step Priority Chain (first match wins)

**Step 1 — Manual annotation override:**
```
pod.annotations["spot-optimizer/tier"] == "0"–"4" → return that tier immediately
signal: annotation_override (confidence = 1.0)
```

**Step 2 — DaemonSet → TIER_0:**
```
controller_kind == "DaemonSet"
signal: controller_kind
```

**Step 3 — System namespace → TIER_0:**
```
namespace in {kube-system, kube-public, kube-node-lease, karpenter, spot-optimizer,
              cert-manager, monitoring, istio-system, linkerd}
signal: namespace_system
```

**Step 4 — StatefulSet + strong stateful signal → TIER_1:**
```
controller_kind in (StatefulSet, OperatorStateful) AND any of:
  a. volumeClaimTemplates present                → immediate TIER_1 (signal: volumeClaimTemplates)
  b. pvc_count > 0                               → signal: pvc_present
  c. env vars match LEADER_ELECTION_ENV_PATTERNS → signal: env_key_match
     (patroni_scope, redis_sentinel, kafka_node_id, etcd_initial_cluster, …)
  d. crd_owner_kind in OPERATOR_DB_OWNER_KINDS   → signal: crd_owner_match
     (Cluster→postgresql, PostgresCluster→postgresql, PerconaServerMongoDB→mongodb,
      Kafka→kafka, RabbitmqCluster→rabbitmq, ElasticsearchCluster→elasticsearch, …)
  e. pod_labels match OPERATOR_LABELS            → signal: label_operator_match
     (cnpg.io/cluster, postgres-operator.crunchydata.com/cluster, strimzi-cluster-operator, …)
```

**Step 5 — StatefulSet + DB image → TIER_1:**
```
controller_kind in (StatefulSet, OperatorStateful) AND images not empty
AND _match_images() returns type in _DB_APP_TYPES
→ TIER_1
signals: controller_kind + image_match
```

**Step 5b — Deployment + DB image + (DB port OR PVC) → TIER_1:**
```
controller_kind == Deployment AND images match DB pattern
AND (db_port_match OR pvc_count > 0)
→ TIER_1
signals: image_match + port_match|pvc_present
```

**Step 5c — CRD operator owner (any controller kind) → TIER_1:**
```
crd_owner_kind in OPERATOR_DB_OWNER_KINDS (without StatefulSet gate)
→ TIER_1
signal: crd_owner_match
```

**Step 6 — KEDA-managed + queue trigger → TIER_2:**
```
keda_managed == True AND trigger_types ∩ {rabbitmq, kafka, sqs, azure-servicebus,
  google-cloud-pubsub, redis, nats-jetstream, activemq} != empty
→ TIER_2
signal: keda_managed
(KEDA with non-queue trigger → TIER_3)
```

**Step 7 — Worker image pattern → TIER_3:**
```
images match _WORKER_APP_TYPES: sidekiq_worker, celery_worker, resque_worker,
  dramatiq_worker, bull_worker, temporal_worker
→ tier = min(current_tier, TIER_3)
signal: image_match
```

**Step 7b — Init container DB migration tool → TIER_1:**
```
init container image matches: flyway, liquibase, alembic, goose, dbmate, prisma*migrat, sqitch
OR init container exposes a DB port
→ TIER_1
signal: init_container_db_migration
(Requires agent >= 1.1.8)
```

**Step 7c — Long readiness delay + stateful signal → TIER_3:**
```
readiness_delay >= 60s AND has_stateful_signal (pvc_present OR pvc_count > 0) AND current tier == TIER_4
→ TIER_3 (pure ML model loading / stateless slow-start stays TIER_4)
```

**Step 8 — Default → TIER_4:**
```
No earlier match → TIER_4 (stateless_service)
Attempt to infer detected_app_type from images (web_proxy, python_web, jvm_web, etc.)
```

---

### 3.3 Image Patterns (`IMAGE_PATTERNS`)

Matched against container image basename (registry prefix stripped). Ordered: most specific first.

| Pattern | App Type |
|---|---|
| `postgres\|postgresql\|patroni\|spilo\|pgbouncer` | `postgresql` |
| `mysql\|mariadb\|percona-server` | `mysql` |
| `mongo\|mongodb` | `mongodb` |
| `redis\|keydb\|dragonfly` | `redis` |
| `cassandra\|scylladb` | `cassandra` |
| `elasticsearch\|opensearch` | `elasticsearch` |
| `influxdb\|prometheus` | `timeseries_db` |
| `neo4j\|dgraph` | `graph_db` |
| `etcd\|consul` | `etcd` |
| `zookeeper\|confluent-zookeeper` | `zookeeper` |
| `rabbitmq` | `rabbitmq` |
| `kafka\|confluent-kafka\|strimzi` | `kafka` |
| `nats-server` | `nats` |
| `sidekiq` | `sidekiq_worker` |
| `celery` | `celery_worker` |
| `temporal-worker` | `temporal_worker` |
| `nginx\|apache\|caddy\|traefik` | `web_proxy` |
| `django\|flask\|fastapi\|gunicorn\|uvicorn` | `python_web` |
| `spring-boot\|quarkus\|micronaut` | `jvm_web` |

Old agents (< 1.2.0): image/port heuristics skipped (agent version checked via `_agent_version_gte()`).

---

### 3.4 Port Patterns (DB indicators)

| Ports | App Type |
|---|---|
| 5432, 5433 | postgresql |
| 3306, 3307 | mysql |
| 27017–27019 | mongodb |
| 6379, 6380 | redis |
| 9200, 9300 | elasticsearch |
| 9042 | cassandra |
| 2181, 2888, 3888 | zookeeper |
| 2379, 2380 | etcd |
| 5672, 15672 | rabbitmq |
| 9092, 9093 | kafka |

---

### 3.5 `compute_classification_confidence()` — Signal Weights

| Signal | Weight |
|---|---|
| `annotation_override` | 1.0 (short-circuit → 1.0) |
| `namespace_system` | 0.50 |
| `crd_owner_match` | 0.40 |
| `label_operator_match` | 0.35 |
| `controller_kind` | 0.30 |
| `keda_managed` | 0.30 |
| `image_match` | 0.30 |
| `pvc_present` | 0.20 |
| `port_match` | 0.15 |
| `env_key_match` | 0.15 |

**Single-signal TIER_1 penalty:** If `tier <= TIER_1 AND signals_count < 2` → multiply confidence by 0.5 (lone StatefulSet signal is easy to get wrong).

---

## 3a. Workload Classification DB Model

**Model:** `backend/models/workload_classification.py` → table `workload_classifications`

### All Columns

| Column | Type | Source | Notes |
|---|---|---|---|
| `id` | `String(36) PK` | DB-generated UUID | |
| `cluster_id` | `String(36) FK` | Input | FK → `clusters.id` CASCADE DELETE |
| `workload_id` | `String(512)` | `{namespace}/{name}` | Unique per cluster |
| `namespace` | `String(253)` | K8s | |
| `name` | `String(253)` | K8s | |
| `controller_kind` | `String(50)` | K8s | Deployment/StatefulSet/DaemonSet/Job/CronJob |
| `role` | `String(20)` | WIE | SYSTEM / CONTROL_PLANE / APPLICATION |
| `criticality_score` | `Integer` | WIE | 0–10 |
| `tier` | `String(20)` | WIE | Platinum / Gold / Silver / Bronze |
| `spot_score` | `Integer` | WIE | 0–10 |
| `spot_friendly` | `Boolean` | WIE | `is_spot_friendly()` result |
| `confidence_score` | `Integer` | WIE | 1–10 |
| `confidence_state` | `String(20)` | WIE | DRAFT / PROVISIONAL / CONFIRMED |
| `data_safety` | `String(20)` | WIE | STATEFUL / CACHE / EPHEMERAL |
| `signals_fired` | `JSONB` | WIE | All signal strings from pipeline |
| `override_active` | `Boolean` | Manual | Annotation/API override active |
| `override_reason` | `String(512)` | Manual | Human reason |
| `input_hash` | `String(100)` | WIE | `"sha256:<hex>"` of slow-changing input fields |
| `az_spread_required` | `Boolean` | WIE v4.4 | Migration 011 — default false |
| `disruption_safe` | `Boolean` | WIE v4.4 | Migration 011 — default false |
| `cpu_cv` | `Float` | `workload_cv_task` | 14-day trimmed CPU coefficient of variation |
| `traffic_skew_detected` | `Boolean` | `workload_cv_task` | `cpu_cv > 0.4` |
| `classified_at` | `DateTime` | WIE | UTC |
| `created_at` | `DateTime` | DB | UTC |
| `updated_at` | `DateTime` | DB | UTC auto-update |
| `schema_version` | `String(10)` | WIE | `"4.4"` |

### Indexes

| Index | Columns | Purpose |
|---|---|---|
| `uq_workload_classification_cluster_workload` | `(cluster_id, workload_id)` UNIQUE | One record per workload per cluster |
| `ix_wc_cluster_tier` | `(cluster_id, tier)` | Bulk tier queries |
| `ix_wc_cluster_confidence` | `(cluster_id, confidence_state)` | CONFIRMED workload filtering |
| `ix_wc_cluster_spot` | `(cluster_id, spot_friendly, confidence_state)` | Spot-eligible lookup |
| `ix_wc_workload_id` | `workload_id` | Single workload lookup |

### CPU CV Task (T-07)

**File:** `backend/workers/tasks/workload_cv_task.py`  
**Schedule:** Every 10 minutes

1. Load all `WorkloadClassificationRecord` rows per cluster
2. Fetch 14-day `pod_metrics.cpu_usage_millicores` per workload
3. Trim top 5%: `samples[:int(len*0.95)]`
4. `cpu_cv = std(trimmed) / mean(trimmed)`
5. Write `cpu_cv` and `traffic_skew_detected = (cpu_cv > 0.4)` back to `workload_classifications`

> `PlacementAdvisorService._compute_cv()` also computes CV live in-cycle. The task value is for stable 14-day UI display; the in-cycle value is used for real-time placement adjustment.

---

## 3b. WIE → Workload Placement — Complete Integration Map

This section documents exactly how every WIE output field flows downstream into the Placement Advisor, Placement Controller, and the Placement UI. This is the connective tissue between scoring and execution.

---

### 3b.1 End-to-End Data Flow

```
K8s Agent heartbeat
  └─ pod_state, labels, PVCs, topology, restarts
       │
       ▼
WorkloadDataCollector → WorkloadInput
       │
       ▼
WorkloadIdentificationEngine.slow_loop_classify()   [every 10 min]
  ├─ workload_classifier.py (classifier bridge)
  ├─ classify_workload() 10-step pipeline
  ├─ Redis write: spot:wie:classification:{cid}:{ns}/{ctrl}  [TTL 900s]
  └─ DB write:   workload_classifications table              [suppressed if no delta]
       │
       ▼
PlacementAdvisor.run_placement_cycle()              [every 30 min]
  ├─ Reads: workload_classifications (DB) or Redis fallback
  ├─ Gates on: confidence_state, spot_friendly, role, tier
  ├─ Uses: az_spread_required, disruption_safe, cpu_cv
  ├─ Writes: placement_policies table
  └─ Writes: spot:placement:policy:{cid}:{wid} Redis
       │
       ▼
PodPlacementEngine.materialize_plan()               [called by placement-detail API + future PlacementController]
  ├─ Input: pods[], nodes[], wie{}, targets{ondemand_target, spot_target}
  ├─ Guard 1: pods==[] OR nodes==[] → _noop_plan(status)
  ├─ Guard 2: post-PodSelector, no moves → status="already_optimal"
  ├─ Phase A: PodSelector → classify + score movement cost
  ├─ Phase B: StabilityOptimizer → disruption_safe / PDB / tier / cooldown gates
  ├─ Phase C: AZDistributor → assign target_az per pod
  ├─ Phase D: CapacityPlanner → keep/provision/drain node_plan
  ├─ Phase E: BinPacker → assign target_node (BFD + multi-factor scoring)
  └─ Output: PlacementPlan{pod_assignment, movement_plan, node_plan, az_distribution, feasibility{status}}
       │
       ▼
PlacementController.run_cycle()                     [every 5 min]
  ├─ Reads: placement_policies (DB)
  ├─ Gates on: disruption_safe, PDB, cooldowns, locks
  ├─ Creates: AgentAction(EVICT_POD)
  └─ Writes: spot:placement_controller:* Redis
       │
       ▼
Placement UI (WorkloadPlacement.jsx)
  ├─ /optimize/workloads/placement             → workload list with spot_friendly, tier, confidence_state
  └─ /optimize/workloads/{id}/placement-detail → pod_plan with recommendation (spot/od/skip)
                                                  + policy, state_locks, controller_logs, az_groups
```

---

### 3b.2 WIE → PlacementAdvisor: Field-by-Field Gates

| WIE Field | Value | Effect in PlacementAdvisor |
|---|---|---|
| `role` | `SYSTEM` or `CONTROL_PLANE` | Hard skip — 100% OD, no spot target ever |
| `confidence_state` | `DRAFT` | 100% OD — advisor ignores spot_friendly entirely |
| `confidence_state` | `PROVISIONAL` | Conservative spot target (reduced from CONFIRMED allocation) |
| `confidence_state` | `CONFIRMED` | Full spot migration permitted per tier rules |
| `spot_friendly` | `False` | 100% OD regardless of confidence |
| `spot_friendly` | `True` AND CONFIRMED | Eligible for spot target assignment |
| `tier` | `Platinum` | OD baseline = 100% (all pods stay OD) |
| `tier` | `Gold` | OD baseline = 50% (strong resilience) or 70%; never 0% OD |
| `tier` | `Silver` | OD baseline = 50% |
| `tier` | `Bronze` | OD baseline = floor (max safe reduction) |
| `az_spread_required` | `True` | Advisor injects multi-AZ affinity rules into NodePool template |
| `disruption_safe` | `True/False` | Advisor uses this to confirm safe eviction window; False → skips workload this cycle |
| `data_safety` | `STATEFUL` | Advisor uses baseline-only logic; never assigns spot_target > 0 unless explicitly overridden |
| `cpu_cv` | `> threshold` | `apply_traffic_skew_adjustment()` → baseline + 1 extra OD pod |
| `traffic_skew_detected` | `True` | Same as cpu_cv trigger |
| `replicas` | — | Feeds `compute_ondemand_baseline()` replica-count formula |
| `pdb_min_available` | — | Lower bound on OD baseline |

**PlacementAdvisor hard gate pseudocode:**
```python
# assign_capacity_types() in placement_advisor_service.py
if role in (SYSTEM, CONTROL_PLANE):         → ondemand_target = replicas, spot_target = 0
if confidence_state != CONFIRMED:           → ondemand_target = replicas, spot_target = 0
if not spot_friendly:                       → ondemand_target = replicas, spot_target = 0
# else: compute baseline + skew + AZ + cluster cap → write PlacementPolicyRecord
```

---

### 3b.3 WIE → PlacementController: Eviction Gates

The controller reads `PlacementPolicyRecord` (written by Advisor) AND the live WIE classification for secondary guards:

| WIE / Derived Field | Controller Check | Block Condition |
|---|---|---|
| `disruption_safe` (WIE v4.4) | `_process_workload()` pre-eviction check | `disruption_safe == False` → skip this cycle |
| `has_pdb + pdb_min_available` | `_pdb_safety_check()` | Eviction would violate PDB → skip |
| `ready_replicas` | last-pod safeguard | `ready_replicas - evicting < 1` → skip |
| `stable_for_minutes` | pod-too-young check | Pod age < MIN_POD_AGE_SECONDS → skip |
| `confidence_state` | `_get_actionable_workloads()` | Non-CONFIRMED workloads excluded from action list |
| `tier == Platinum` | `ClassificationGuard.is_drainable()` | Never drainable |
| `tier == Gold AND NOT spot_friendly` | `ClassificationGuard.is_drainable()` | Needs approval |

---

### 3b.4 WIE → Placement UI: Field Rendering Map

#### Workload List (`/optimize/workloads/placement`)

| WIE Field | UI Element | Rendering |
|---|---|---|
| `confidence_state` | Badge next to workload name | `DRAFT` = gray, `PROVISIONAL` = yellow, `CONFIRMED` = green |
| `spot_friendly` | Spot eligibility indicator | ✓ spot eligible / ✗ OD-only |
| `tier` | Tier badge | Platinum=red, Gold=orange, Silver=blue, Bronze=gray |
| `role` | System workload flag | SYSTEM/CONTROL_PLANE rows shown differently (skip eviction) |
| `ondemand_target` | OD target count | From `PlacementPolicyRecord` |
| `spot_target` | Spot target count | From `PlacementPolicyRecord` |

#### Placement Detail (`/optimize/workloads/{id}/placement-detail`)

**Pod recommendations** are computed using WIE classification + PlacementPolicyRecord:

```python
# pod_plan recommendation logic (optimize_routes.py)
if pod is SYSTEM role (namespace in system_ns) → recommendation = 'skip'
if pod.capacity_type == 'spot' AND within spot_target → recommendation = 'spot'
if pod.capacity_type == 'on-demand' AND within od_target → recommendation = 'od'
if pod exceeds od_target (excess OD) → recommendation = 'spot' (eviction candidate)
if pod skipped (no NodeMetadata / no policy) → recommendation = 'skip'
```

| Pod Recommendation | Meaning | UI Color |
|---|---|---|
| `'spot'` | Pod should run on spot node | Blue |
| `'od'` | Pod should stay on on-demand | Red/orange |
| `'skip'` | System pod or no data — not managed | Gray |

**State Locks section** — WIE fields shown as locks:

| Lock Key | Source | Shown When |
|---|---|---|
| `pdb_min_available` | Redis `spot:workload:state:{cid}:{wid}` | Always if PDB exists |
| `hpa_min_replicas` | Agent heartbeat | HPA configured |
| `topology_spread` | Agent heartbeat | `has_topology_spread == True` |
| `pod_anti_affinity` | Agent heartbeat | `has_pod_anti_affinity == True` |
| Cooldown flag | `spot:placement:cooldown:{cid}:{wid}` | Active eviction cooldown |

**Policy Summary** (from `PlacementPolicyRecord` via Redis → DB fallback):

| Field | Description |
|---|---|
| `observed_replicas` | Replica count at policy computation time |
| `ondemand_target` | How many pods should be OD |
| `spot_target` | How many pods should be spot |
| `pod_cpu_cv` | CPU variability coefficient |
| `traffic_skew_detected` | Whether traffic skew adjustment fired |
| `estimated_monthly_saving_usd` | Projected savings if spot target achieved |

---

### 3b.5 Confidence State → UI Automation Gates

| confidence_state | PlacementAdvisor | PlacementController | UI Action |
|---|---|---|---|
| `DRAFT` | 100% OD — no spot | No eviction dispatched | Shows "Observing" badge; no recommendations |
| `PROVISIONAL` | Conservative spot target | No eviction dispatched | Shows "Suggested" mode; no auto-eviction |
| `CONFIRMED` | Full spot allocation | Evictions dispatched if excess OD | Full automation; pod-level recommendations shown |

---

### 3b.6 WIE Classifier → Pod Recommendation Skipping

`role == SYSTEM` is the primary skip gate in the placement-detail endpoint:

```python
# System namespaces (from WIE)
_SYSTEM_NS = {"kube-system", "karpenter", "spot-optimizer", "cert-manager",
              "monitoring", "istio-system", "linkerd", …}

for pod in pods:
    if pod.namespace in _SYSTEM_NS → recommendation = 'skip'
    # No eviction, no policy, shown as gray in UI
```

This means DaemonSet pods, kube-proxy, coredns, karpenter controllers, and the spot-optimizer agent itself are all shown as "skip" in the pod table — WIE's role classification is the direct gate.

---

### 3b.7 Restart Baseline Loop (feeds WIE → feeds Placement)

`update_restart_baselines()` runs every hour (Celery beat):

```
1. Query pod_metrics: avg(restart_count) per controller per hour
2. Compute median across all controllers of that kind in the cluster
3. Write: spot:restart_baseline:{cid}:{Deployment|StatefulSet|...} (TTL 3600s)
```

WIE `slow_loop_classify()` reads this baseline:
```python
restart_rate_normalized = workload.restart_count_per_hour / baseline_for_kind
```
→ if `> 2.0x` → `spot_score −2` → possible `spot_friendly = False` → Placement Advisor assigns 100% OD.

This creates the full feedback loop:
```
Pod restarts (K8s) → PodMetric (DB) → restart_baseline (Redis) →
restart_rate_normalized (WIE) → spot_score (WIE) → spot_friendly (WIE) →
spot_target = 0 (Advisor) → no evictions (Controller) → all pods stay OD (UI)
```

---

## 4. Placement Advisor

**File:** `backend/services/placement_advisor_service.py`  
**Task:** `backend/workers/tasks/placement_advisor_task.py`  
**Role:** Decision engine — computes OD/Spot split targets and writes `PlacementPolicyRecord`.

### Entry Point

| Invoked By | Function | Frequency |
|---|---|---|
| Celery beat | `run_placement_cycle(cluster_id)` | Every 30 min (not in app.py beat but registered as `placement_advisor_task`) |
| `placement_advisor_task.py` | `run_placement_advisor_cycle` | Dispatched per cluster |

### Core Algorithms

| Step | Function | Logic |
|---|---|---|
| OD baseline | `compute_ondemand_baseline()` | replicas≤4 → max(replicas-1,2); else → max(2, pdb_min, hpa_min, replicas×0.5) |
| Tier override | `compute_ondemand_baseline()` | Platinum→100%, Gold→50%(strong resilience) or 70%, Silver→50%, Bronze→floor |
| Traffic skew | `apply_traffic_skew_adjustment()` | If cpu_cv>threshold or request_cv>threshold AND replicas≥4 → baseline+1 |
| OD/Spot split | `assign_capacity_types()` | Hard gate: SYSTEM/CONTROL_PLANE role OR non-CONFIRMED OR not spot_friendly → 100% OD |
| Availability factor | `compute_spot_availability_factor()` | 3-window smoothed avg from Redis history; AZ spike→0.0 override |
| Scheduling success | `get_spot_scheduling_success_rate_blended()` | 70%×15m rate + 30%×120m rate from Redis; None→1.0 |
| Cluster spot cap | `apply_cluster_spot_cap()` | Enforces global max_ratio; sorts by `spot_score × log(1 + spot_requested)` |

### DB Write — PlacementPolicyRecord

| Column | Source |
|---|---|
| `ondemand_target` | `compute_ondemand_baseline()` after tier/traffic overrides |
| `spot_target` | `assign_capacity_types()` |
| `pod_cpu_cv` | Live `_compute_cv()` or from `workload_classifications.cpu_cv` |
| `traffic_skew_detected` | `apply_traffic_skew_adjustment()` |
| `estimated_monthly_saving_usd` | `AWSPricingService.get_ondemand_price()` − spot price × 730 |

### Redis Keys Used

| Key | TTL | Read/Write | Purpose |
|---|---|---|---|
| `spot:placement:policy:{cluster_id}:{workload_id}` | varies | Write | Policy cache per workload |
| `spot:placement:cluster_state:{cluster_id}` | varies | Write | Cluster-level state snapshot |
| `spot:placement:spot_availability:{region}` | — | Read | Availability history for factor computation |
| `spot:placement:spot_availability_az:{region}:{az}` | — | Read | Per-AZ availability for spike detection |
| `spot:placement:scheduling_success:{instance_type}:{window}` | — | Read | Scheduling success rates |
| `spot:placement:metrics:{cluster_id}` | — | Write | Cycle metrics emission |
| `spot:placement:cycle_lock:{cluster_id}` | — | Lock | Prevents concurrent advisor cycles |

---

## 4b. Pod Placement Engine — 5-Layer Plan Materialization

**Status:** ✅ **IMPLEMENTED — Live v2.0 (5-layer)**  
**File:** `backend/services/pod_placement_engine.py`  
**Schema Version:** `"1.0"` (carried in every `PlacementPlan` output)  
**Position:** Sits between `PlacementAdvisor` (produces counts) and `PlacementController` (executes evictions).  
**Current wiring:** Called by `GET /optimize/workloads/{id}/placement-detail` API endpoint; `PlacementController` integration via Redis anchor key.

**5-Layer flow (plan.md v2 spec):**
```
StateGuard (Layer 1)     → PROCEED | NO_OP | ABORT
AnchorPlanner (Layer 2)  → anchor_nodes[], locked_pods[], anchor_map{}
PodSelector              → classify + score (skips locked/system)
StabilityOptimizer       → cooldown + anchor guard
AZDistributor            → AZ spread enforcement
CapacityPlanner          → keep/provision/drain node_plan
BinPacker (Layer 3)      → BFD + multi-factor scoring (hotspot/anchor penalties)
CostProjector (Layer 4)  → cost_projection pass 1
PlanValidator (Layer 5)  → PDB/IP/max_pods/storage-AZ/AZ-spread
CostProjector (Layer 4)  → cost_projection pass 2 (post-validation)
```

---

### 4b.1 Why This Engine Exists

Before this engine, the system jumped directly from **target counts** to **eviction dispatch**:

```
PlacementAdvisor → ondemand_target=4, spot_target=6   (just numbers)
                            │
                            ▼
PlacementController → "evict any 6 OD pods" (no pod selection logic, no AZ logic)
```

This produced four observable failures, all now addressed:

| Was broken | Now fixed by |
|---|---|
| Controller picked arbitrary pods (most disruptive) | PodSelector ranks by movement cost; cheapest pods move first |
| No CPU/memory sum before eviction | CapacityPlanner pre-computes resource needs per (AZ, capacity_type) bucket |
| Spot pods could collapse to a single AZ | AZDistributor enforces spread when `az_spread_required=true` |
| No bin-packing — Karpenter decided node count | BinPacker pre-computes node count using BFD + multi-factor scoring; emits keep/provision/drain plan |

**Hard architectural rule (enforced in code):**
```
Phase 1 (targets from PlacementAdvisor) MUST NOT know pods.
Phases 2+ (PodSelector onward) MUST NOT change targets.
```

The engine also enforces data-validity guards before running any phase — see §4b.3.

---

### 4b.2 I/O Contract

**Input:**
```json
{
  "pods": [
    { "pod_name": "...", "namespace": "...", "controller": "...",
      "node_name": "...", "az": "...", "capacity_type": "spot|on-demand",
      "cpu_request_millicores": 500, "memory_request_bytes": 536870912,
      "phase": "Running", "age_seconds": 1234, "ready": true }
  ],
  "nodes": [
    { "node_name": "...", "az": "...", "capacity_type": "spot|on-demand",
      "instance_type": "m5.xlarge",
      "allocatable_cpu_millicores": 4000, "allocatable_memory_bytes": 16000000000,
      "used_cpu_millicores": 2000, "used_memory_bytes": 8000000000,
      "pod_count": 8 }
  ],
  "wie": {
    "workload_id": "ns/name",
    "tier": "Gold",
    "spot_friendly": true,
    "confidence_state": "CONFIRMED",
    "az_spread_required": true,
    "disruption_safe": true,
    "data_safety": "EPHEMERAL",
    "has_pdb": true,
    "pdb_min_available": 2,
    "replicas": 6,
    "ready_replicas": 6
  },
  "targets": {
    "ondemand_target": 4,
    "spot_target": 2,
    "observed_replicas": 6
  }
}
```

**Output:**
```json
{
  "pod_assignment": {
    "spot":      [ { "pod_name": "...", "current_node": "...", "target_node": "...", "target_az": "...", "movement_required": true  } ],
    "ondemand":  [ { "pod_name": "...", "current_node": "...", "target_node": "...", "target_az": "...", "movement_required": false } ]
  },
  "movement_plan": [
    { "step": 1, "pod_name": "...", "from_node": "...", "to_capacity_type": "spot",
      "to_az": "us-east-1a", "reason": "spot_target_unmet",
      "movement_cost": 0.2, "blocked_by": null }
  ],
  "node_plan": [
    { "action": "keep",       "node_name": "ip-10-0-1-5",  "capacity_type": "on-demand", "az": "us-east-1a" },
    { "action": "provision",  "instance_type": "m5.large", "capacity_type": "spot",      "az": "us-east-1b",
      "required_cpu_millicores": 1500, "required_memory_bytes": 4000000000 },
    { "action": "drain",      "node_name": "ip-10-0-2-7",  "capacity_type": "on-demand", "az": "us-east-1c",
      "reason": "consolidation_candidate" }
  ],
  "az_distribution": {
    "us-east-1a": { "spot": 1, "ondemand": 2, "total": 3 },
    "us-east-1b": { "spot": 1, "ondemand": 1, "total": 2 },
    "us-east-1c": { "spot": 0, "ondemand": 1, "total": 1 }
  },
  "movement_plan": [
    {
      "step": 1,
      "pod_name": "api-1", "namespace": "production",
      "workload_id": "wl-abc123",
      "from_node": "node-x",  "from_az": "us-east-1b",
      "from_capacity_type": "on-demand",
      "to_capacity_type": "spot",
      "to_az": "us-east-1a",  "to_node": "node-c",
      "reason": "spot_target_unmet",
      "movement_cost": 0.2,
      "cpu_request_millicores": 250,
      "memory_request_bytes": 268435456,
      "blocked_by": null
    }
  ],
  "feasibility": {
    "feasible": true,
    "status": "plan_generated",
    "warnings": [],
    "moves_total": 2,
    "moves_blocked": 0,
    "validator_status": "FEASIBLE",
    "passed_checks": ["PDB", "IP_CAPACITY", "MAX_PODS", "STORAGE_AZ", "AZ_SPREAD"]
  },
  "anchor_plan": {
    "anchor_nodes": ["node-a"],
    "locked_pods": ["redis-0"],
    "anchor_count": 1,
    "anchor_map": { "redis-0": "node-a" }
  },
  "cost_projection": {
    "current_nodes": 10, "projected_nodes": 8,
    "current_monthly_usd": 730, "projected_monthly_usd": 584,
    "saving_usd": 146, "saving_pct": 20, "spot_pct": 62,
    "actuals_updated": false
  },
  "validation_errors": []
}
```

**`feasibility.status` values:**

| Status | Meaning | Trigger |
|---|---|---|
| `"cluster_not_idle"` | StateGuard ABORT — cluster busy | `cluster_state != "idle"` |
| `"stale_data"` | StateGuard ABORT — data too old | `data_age_seconds > 30` |
| `"already_optimal"` | StateGuard NO-OP or post-PodSelector: no moves needed | Hash match or empty move lists |
| `"no_pods_observed"` | No pod data supplied | `pods == []` |
| `"no_node_data"` | No node data supplied | `nodes == []` |
| `"plan_generated"` | Normal success path | PlanValidator FEASIBLE + no capacity blocks |
| `"partial"` | Some pods blocked (capacity or soft validator fail) | `n_blocked > 0` or validator `PARTIAL` |
| `"infeasible"` | Hard validator failure (MAX_PODS/IP_CAPACITY/STORAGE_AZ) | PlanValidator `INFEASIBLE` |

---

### 4b.3 Engine Architecture — 5-Layer Pipeline

```
materialize_plan(pods, nodes, wie, targets,
                 cluster_state="idle", desired_hash=None, ...)
    │
    ▼ Layer 1 — StateGuard
    ├─► cluster_state != idle → ABORT ("cluster_not_idle")
    ├─► data_age_seconds > 30 → ABORT ("stale_data")
    ├─► sha256(pod→node) == desired_hash → NO_OP ("already_optimal")
    ├─► pods == []            → _noop_plan("no_pods_observed")
    ├─► nodes == []           → _noop_plan("no_node_data")
    │
    ▼ Layer 2 — AnchorPlanner
    │  anchor_count = max(min_user, ceil(critical_cpu/avg_cpu), 2_if_ha)
    │  capped at 50% of cluster; selects via AZ-spread quota
    │  produces: anchor_nodes{}, locked_pods{}, anchor_map{pod→node}
    │
    ▼  PodSelector.classify_and_score(..., locked_pods=)
    │  skip: system namespaces, DaemonSet, anchor-locked pods
    ├─► to_move==[] → status="already_optimal" [short-circuit]
    │
    ▼  StabilityOptimizer.filter(..., anchor_nodes=, cooldown_pods=)
    │  skips: in-flight evictions, disruption_unsafe, PDB batch, cooldown, anchors
    ▼  AZDistributor.assign(...)  — per-AZ spread quota
    ▼  CapacityPlanner.plan(..., anchor_nodes=)  — never drains anchor nodes
    │
    ▼ Layer 3 — BinPacker.pack(..., nodes=, anchor_nodes=, anchor_map=,
    │                        node_pod_counts=, node_ds_counts=)
    │  BFD: pods sorted CPU-desc; all feasible nodes scored; min(score) wins
    │  score = cpu_remaining_after/alloc [BFD tightness]
    │        + 150 if util_after > 80%        [hotspot penalty]
    │        + 500 if anchor node, non-critical pod [anchor penalty]
    │  Critical pods in anchor_map → direct preferred-anchor assignment
    │  4 dimensions: cpu_remaining, mem_remaining, pod_remaining, ip_remaining
    │  pod_count + daemonset_count DERIVED from pods list (node dict has pod_count=0)
    │  MAX_MOVES_PER_CYCLE=2 hard cap applied after BinPacker
    │
    ▼ Layer 4 — CostProjector.project() PASS 1 (preliminary)
    │
    ▼ Layer 5 — PlanValidator.validate(movement_plan, nodes, wie)
    │  Check 1 PDB (soft)
    │    pdb_budget = running - pdb_min_available
    │    if budget==0: block all; if plan > budget: block highest-cost excess only
    │  Check 2 IP_CAPACITY (hard) — assigned > node.ip_available
    │  Check 3 MAX_PODS (hard)  — current + incoming > max_pods
    │  Check 4 STORAGE_AZ (hard) — STATEFUL cross-AZ move
    │  Check 5 AZ_SPREAD (soft) — < 2 AZs in plan
    │  removes validator-blocked pods from movement_plan
    │
    ▼ Layer 4 — CostProjector.project() PASS 2 (finalized)
    │
    ▼
PlacementPlan{
  pod_assignment, movement_plan, node_plan, az_distribution,
  feasibility{status, validator_status, passed_checks, ...},
  anchor_plan{anchor_nodes, locked_pods, anchor_map},
  cost_projection{current_monthly_usd, saving_usd, spot_pct, preliminary{...}},
  validation_errors[]
}
```

**Phase data-contract rule (hard, enforced by structure):**
- `PodSelector` receives `targets` read-only; never mutates them.
- `StabilityOptimizer` through `BinPacker` receive the `selected/filtered` dict and `targets` read-only; none may alter target counts.
- `CostProjector` and `PlanValidator` are pure-read — they never modify `movement_plan` except via explicit filtered list after validation.

---

### 4b.4 Submodule A — Pod Selector

**Class:** `PodSelector`  **Method:** `classify_and_score(pods, wie, targets)`

**Responsibility:** Classify each pod and score its movement cost; choose which pods become spot candidates.

**Algorithm (actual implementation):**
```
For each pod:
  1. Skip filter:
     - namespace in DEFAULT_SYSTEM_NAMESPACES OR controller_kind=="DaemonSet"
       → system_skip bucket (never touched)

  2. Score movement_cost (lower = cheaper to move):
     base_cost = 0.0
     + 0.5  if pod.age_seconds < 600              (recently scheduled)
     + 0.3  if pod.ready == False                 (still warming up)
     + 0.2  if WIE.classifier_app_type in DB_RISK_APP_TYPES  (postgresql/mysql/kafka/…)
     + 0.3  if WIE.data_safety == "STATEFUL"       (data flush risk)
     − 0.2  if pod.age_seconds > 86400             (long-running, safe to bounce)
     − 0.05×(wie.spot_score − 5)                  (spot_score=10 → −0.25 bonus)

  3. Bucket by current capacity_type:
     spot_now      ← cap=="spot"
     ondemand_now  ← cap=="on-demand" OR unknown

  4. Compute deltas:
     excess_ondemand = max(0, len(ondemand_now) − ondemand_target)
     excess_spot     = max(0, len(spot_now)     − spot_target)

  5. Sort each list by movement_cost ASC; take head of excess slice:
     to_move_to_spot     = ondemand_now[:excess_ondemand]
     to_move_to_ondemand = spot_now[:excess_spot]
```

**Output → next module:**
```python
{
  "to_move_to_spot": [pod, ...],     # cheapest excess-OD pods
  "to_move_to_ondemand": [pod, ...], # cheapest excess-spot pods
  "stay_put": [pod, ...],            # already at target capacity_type
  "system_skip": [pod, ...]          # never touched
}
```

---

### 4b.5 Submodule B — Stability Optimizer

**Responsibility:** Minimize total movements; protect pods whose disruption would violate WIE invariants.

**Hard rules (cannot be overridden):**
1. `WIE.disruption_safe == False` → emit empty movement_plan; skip workload this cycle.
2. Never move a pod if `ready_replicas - in_flight_evictions ≤ pdb_min_available` (PDB violation).
3. Never move the **last running pod** of a Deployment/StatefulSet.
4. Never move pods on a node that is already cordoned/draining.

**Soft optimizations:**
1. **Movement minimization:** if existing distribution is within ±1 of target, emit empty plan (don't churn for trivial deltas).
2. **Batching:** cap `len(movement_plan) ≤ CLUSTER_BATCH_SIZE` (5 by default) per cycle.
3. **Critical pod protection:** if `WIE.tier == Platinum` → reject all moves; if `WIE.tier == Gold AND !spot_friendly` → reject only spot moves.
4. **Cooldown awareness:** drop pods listed in `spot:placement:cooldown:{cid}:{wid}` from movement_plan.

**Output:** filtered movement_plan with `blocked_by` reason annotated for any rejected pod (never silently drop).

---

### 4b.6 Submodule C — AZ Distributor

**Responsibility:** Ensure target AZ distribution; enforce multi-AZ spread when `WIE.az_spread_required == True`.

**Algorithm:**
```
1. Compute current AZ counts per capacity_type:
   az_distribution_now = { az: { spot: int, ondemand: int } }
   
2. Compute ideal AZ targets:
   - if az_spread_required:
       spread spot_target evenly across observed AZs (≥ 2 AZs minimum)
       spread ondemand_target evenly across observed AZs
   - else:
       prefer the AZ with the most available capacity (least eviction churn)
   
3. For each pod in to_move_to_spot:
   - Pick target_az = AZ with lowest current spot count
   - If az_spread_required AND target_az would create > ⌈spot_target / num_az⌉ → next AZ
   
4. For each pod in to_move_to_ondemand:
   - Same logic for ondemand_target
   
5. Validate:
   - For az_spread_required: at least 2 AZs must end up with ≥ 1 pod
   - If validation fails → emit warning + degrade gracefully (keep current spread)
```

**Output:** every entry in `pod_assignment.spot` and `pod_assignment.ondemand` gets a `target_az`.

---

### 4b.7 Submodule D — Capacity Planner

**Responsibility:** Sum CPU/memory of moved pods per (AZ, capacity_type) bucket; compute how many nodes are required.

**Algorithm:**
```
1. Group movement_plan by (target_az, target_capacity_type):
   bucket = (az, capacity_type) → list[pod]
   
2. For each bucket:
   total_cpu_mc  = sum(pod.cpu_request_millicores)
   total_mem_b   = sum(pod.memory_request_bytes)
   
3. Pick a representative instance_type from NodePool ML rankings for that capacity_type
   (use: spot-general / spot-compute / spot-memory / on-demand-general)
   
4. Compute required nodes:
   nodes_for_cpu = ceil(total_cpu_mc / instance.allocatable_cpu_mc)
   nodes_for_mem = ceil(total_mem_b  / instance.allocatable_mem_b)
   required_nodes = max(nodes_for_cpu, nodes_for_mem)
   
5. Subtract existing nodes in bucket with free capacity:
   for node in nodes_in_bucket:
     if node has slack >= largest_pod → required_nodes -= 1
   
6. Emit node_plan entries:
   - "keep"      for existing nodes that fit some pods
   - "provision" for net-new required nodes (Karpenter will materialize)
   - "drain"     for nodes that become empty after moves
```

**Output:** `node_plan[]` with cumulative resource requirements per bucket.

---

### 4b.8 Submodule E — Bin Packer

**Responsibility:** Assign each moved pod to a specific node (existing or to-be-provisioned), minimizing node count.

**Algorithm — Best-Fit-Decreasing (BFD) with multi-factor scoring:**
```
1. Sort moved pods by cpu_request_millicores DESCENDING (largest first)

2. For each pod:
   - Try to fit into existing nodes in the target (az, capacity_type) bucket
     that have slack >= pod requirements
   - If no existing node fits → assign to next "provision" node from node_plan
   - If no provision node has space → request additional provision node (update node_plan)
   
3. Track per-node load:
   node.cpu_used += pod.cpu_request_millicores
   node.mem_used += pod.memory_request_bytes
   node.pod_count += 1
   
4. Validate: pod_count per node ≤ K8s 110-pod-per-node limit
```

**Output:** every entry in `pod_assignment.spot` and `pod_assignment.ondemand` gets a `target_node` (either existing node name OR placeholder like `"provision-spot-us-east-1a-1"`).

---

### 4b.9 Integration Points

**Upstream callers (current live wiring):**
| Caller | Status | When | Purpose |
|---|---|---|---|
| `GET /optimize/workloads/{id}/placement-detail` | ✅ **Live** | On UI request | Builds `nodes_input` from `NodeMetadata`+`NodeMetric`; calls `materialize_plan()`; returns `placement_plan` in response JSON |
| `PlacementController.run_cycle()` | ⏳ **Planned** | Every 5 min | Materialize plan before dispatching evictions |
| `simulation_engine` | ⏳ **Planned** | What-if API | Dry-run plan without execution |

**API wiring detail (`optimize_routes.py`):**
```python
_plan = PodPlacementEngine.materialize_plan(
    pods=pods,              # list[dict] from pod_metrics JOIN node_metadata
    nodes=nodes_input,      # list[dict] from NodeMetadata + latest NodeMetric
    wie=_wie,               # dict from Redis spot:wie:classification:{cid}:{wid}
    targets=_engine_targets,# {ondemand_target, spot_target, observed_replicas}
    cooldown_pods=_cooldown_pods,  # Redis smembers spot:placement:cooldown:{cid}:{wid}
)
placement_plan = _plan.to_dict()   # returned under "placement_plan" key in response
```

**Downstream consumers (current live wiring):**
| Consumer | Field Used | Purpose |
|---|---|---|
| `WorkloadPlacement.jsx` (UI) | `pod_assignment`, `movement_plan`, `node_plan`, `az_distribution`, `feasibility.status` | Renders movement preview, AZ table, node plan table, and no-op banner |
| `PlacementController._process_workload()` | `movement_plan[]` | ⏳ Planned — iterate to create EVICT_POD AgentActions |
| `KarpenterService.add_allowed_instance_type()` | `node_plan[action="provision"]` | ⏳ Planned — pre-warm NodePool |
| `auto_rebalancer` | `node_plan[action="drain"]` | ⏳ Planned — identify nodes to terminate |

---

### 4b.10 Failure Modes

| Failure | Guard / Phase | Engine Response |
|---|---|---|
| `pods == []` (no pod data) | Pre-phase guard | `_noop_plan("no_pods_observed")` — all fields empty; `moves_total=0` |
| `nodes == []` (no node data) | Pre-phase guard | `_noop_plan("no_node_data")` — all fields empty; `moves_total=0` |
| No movements required (targets met) | Post-Phase-A guard | `status="already_optimal"`; `stay_put` assignments returned; Phases B–E skipped |
| `WIE.disruption_safe == False` | Phase B | All move lists emptied; warning added; `movement_plan=[]` |
| `WIE.tier == Platinum` | Phase B | All moves blocked; warning added |
| `WIE.tier == Gold AND spot_friendly == False` | Phase B | Spot moves blocked; OD moves allowed |
| PDB margin exhausted (`max_concurrent < 1`) | Phase B | `movement_plan=[]`; warning `"PDB margin exhausted"` |
| Pod in cooldown set | Phase B | Pod silently dropped from move list (cooldown is normal) |
| Pod on cordoned source node | Phase B | Pod dropped from move list |
| Batch cap exceeded | Phase B | Move list trimmed to `min(batch_size, max_concurrent)`; warning emitted |
| No AZ data in nodes | Phase C | Warning; `target_az=None` on all pods |
| `az_spread_required` but pods collapse to 1 AZ | Phase C | Warning `"spot pods collapsed to one AZ"`; spread not forced |
| Pod missing CPU/memory requests | Phase D/E | Treated as 0; engine uses node fallback (4000mc CPU, 16GB mem); no crash |
| BinPacker cannot fit a pod | Phase E | `pod.target_node=None`; `pod.blocked_by="no_capacity"`; `feasibility.feasible=False` |
| Engine throws unexpected exception | API caller | Fallback `placement_plan` with `feasibility.feasible=False`, warning `"engine_error: ..."` |

---

### 4b.11 What This Engine Replaced / Improved

| Before | After (live) |
|---|---|
| Controller picked any over-target OD pod (arbitrary) | PodSelector ranks by `movement_cost`; cheapest pods move first |
| No CPU/memory accounting before eviction | CapacityPlanner sums resource needs per (AZ, capacity_type) bucket |
| Spot pods could collapse to single AZ | AZDistributor enforces per-AZ cap when `az_spread_required=true` |
| No bin-packing — Karpenter decided node count | BinPacker pre-computes keep/provision/drain node plan (BFD + scoring) |
| `placement-detail` showed only "spot/od/skip" | Endpoint now returns full `movement_plan` with named nodes/AZs |
| No movement preview in UI | `WorkloadPlacement.jsx` renders movement plan, AZ table, node plan |
| Silent failure on missing data (engine always acted) | Three pre-phase guards prevent invalid plan generation |

---

### 4b.12 Implementation Reference

**File:** `backend/services/pod_placement_engine.py`

**Actual public API:**
```python
class PodPlacementEngine:
    @staticmethod
    def materialize_plan(
        pods: List[Dict[str, Any]],       # pod dicts with pod_name, namespace, capacity_type, node_name, az,
                                           #   cpu_request_millicores, memory_request_bytes, age_seconds, ready
        nodes: List[Dict[str, Any]],       # node dicts with node_name, az, capacity_type, instance_type,
                                           #   allocatable_cpu_millicores, allocatable_memory_bytes,
                                           #   used_cpu_millicores, used_memory_bytes
        wie: Dict[str, Any],               # WIE classification dict (spot_score, tier, disruption_safe,
                                           #   az_spread_required, data_safety, has_pdb, pdb_min_available, ...)
        targets: Dict[str, Any],           # {ondemand_target, spot_target, observed_replicas}
        in_flight_evictions: int = 0,
        cordoned_nodes: Optional[set] = None,
        cooldown_pods: Optional[set] = None,
        batch_size: int = 5,
    ) -> PlacementPlan: ...

    @staticmethod
    def _noop_plan(status: str, warnings: Optional[List[str]] = None) -> PlacementPlan:
        """Returns an empty plan with explanatory status. Never triggers any action."""
```

**Submodule classes (implemented, pure functions):**

| Class | Method | Returns |
|---|---|---|
| `PodSelector` | `classify_and_score(pods, wie, targets)` | `Dict[str, List[pod]]` with 4 buckets |
| `StabilityOptimizer` | `filter(selected, wie, targets, ...)` | `(filtered_dict, warnings[])` |
| `AZDistributor` | `assign(filtered, nodes, wie, targets)` | `(filtered_with_az, az_distribution, warnings[])` |
| `CapacityPlanner` | `plan(filtered, nodes)` | `(node_plan[], warnings[])` |
| `BinPacker` | `pack(filtered, node_plan, nodes=, anchor_nodes=, anchor_map=)` | `(filtered_with_target_node, warnings[])` |

**Key constants:**
```python
SCHEMA_VERSION          = "1.0"
DEFAULT_BATCH_SIZE      = 5
K8S_MAX_PODS_PER_NODE   = 110
DEFAULT_SYSTEM_NAMESPACES = frozenset({"kube-system", "karpenter", "spot-optimizer", ...})
DB_RISK_APP_TYPES         = frozenset({"postgresql", "mysql", "mongodb", "kafka", ...})
```

**PlacementPlan dataclass:**
```python
@dataclass
class PlacementPlan:
    schema_version: str
    pod_assignment: Dict[str, List[Dict]]   # {"spot": [...], "ondemand": [...]}
    movement_plan:  List[Dict]              # step-ordered list of moves
    node_plan:      List[Dict]              # keep/provision/drain entries
    az_distribution: Dict[str, Dict[str, int]]
    feasibility: Dict[str, Any]             # {feasible, status, warnings, moves_total}

    def to_dict(self) -> Dict[str, Any]: ...
```

**Schema versioning:** every `PlacementPlan` carries `schema_version="1.0"`. API consumers must validate before use.

---

## 5. Placement Controller

**File:** `backend/services/placement_controller_service.py`  
**Task:** `backend/workers/tasks/placement_controller_task.py`  
**Role:** Execution engine — reconciles actual pod OD/Spot distribution against PlacementAdvisor targets.

### Entry Point

| Invoked By | Function | Frequency |
|---|---|---|
| Celery beat | `dispatch_placement_controller_cycles` | Every 5 minutes |
| Celery beat | `dispatch_placement_controller_recovery` | Hourly (stale migration recovery) |
| Per-cluster task | `run_placement_controller_cycle(cluster_id)` | Dispatched from dispatcher |

### Cycle Execution Steps (`run_cycle()`)

1. **Circuit Breaker Check** — reads `spot:pc:circuit_breaker:{cluster_id}`; aborts if open
2. **Failure Count Window Check** — counts EVICT_POD FAILED in last `PC_CB_WINDOW_SECS`; trips CB if ≥ `PC_CB_THRESHOLD`
3. **Scaling Guard** — `_scaling_guard_active()` checks Redis for active HPA/KEDA scaling
4. **Cluster Mutex Acquire** — `cluster_mutex(redis, cluster_id, owner="placement_controller", ttl=CLUSTER_MUTEX_TTL_SECS)`
5. **Batch Limit Check** — counts ALL in-flight AgentActions (PENDING + PICKED_UP) across cluster; abort if ≥ `CLUSTER_BATCH_SIZE`
6. **Get Actionable Workloads** — `_get_actionable_workloads()` queries PlacementPolicyRecord for CONFIRMED workloads with OD excess
7. **Build Capacity Map** — `_build_capacity_map()` builds AZ-indexed spot node inventory
8. **Process Each Workload** — `_process_workload()` for each policy:
   - Workload-level lock acquisition
   - Cooldown check
   - PDB safety check
   - Pod-too-young check
   - Last-pod safeguard (min 1 pod)
   - Active action dedup check
   - Node drain guard
   - EVICT_POD AgentAction creation
9. **Emit Cycle Metrics** — writes to Redis hash `spot:placement_controller:metrics:{cluster_id}`

### Key Constants

| Constant | Value | Notes |
|---|---|---|
| `CLUSTER_BATCH_SIZE` | 5 (default) | Max concurrent in-flight actions per cluster |
| `CLUSTER_MUTEX_TTL_SECS` | 60 | Mutex TTL |
| `PC_CB_THRESHOLD` | 5 | Failures to trip circuit breaker |
| `PC_CB_WINDOW_SECS` | 300 | Failure count window |
| `PC_CB_COOLDOWN_SECS` | 600 | CB open duration |
| `POD_AGE_MIN_SECONDS` | configurable | Minimum pod age before eviction eligible |

### Shadow Mode

- Set `spot:placement_controller:shadow_mode:{cluster_id}` = `"1"` in Redis
- Engine runs full evaluation but **does not create AgentActions** — metrics only
- Delete the key to re-enable live evictions

### Retry Logic

- `retry_count` field on `AgentAction` incremented by agent on failure
- `PlacementController._process_workload()` skips actions already at `max_retries`
- `permanent_failures` metric incremented when retry limit reached

### Redis Keys Used

| Key | TTL | Operation | Purpose |
|---|---|---|---|
| `spot:pc:circuit_breaker:{cluster_id}` | `PC_CB_COOLDOWN_SECS` | Read/Write | Circuit breaker open flag |
| `spot:pc:cb_trips_24h:{cluster_id}` | 86400 | Incr | CB trip counter for health UI |
| `spot:placement_controller:metrics:{cluster_id}` | 3600 | HSet | Cycle metrics (evictions, skips, etc.) |
| `spot:pc:workload_log:{cluster_id}:{workload_id}` | 3600 | LPush | Per-workload decision log (last 50) |
| `spot:workload:state:{cluster_id}:{workload_id}` | 300 | Read | Current OD/Spot pod counts, cooldown flags |
| `spot:placement_controller:shadow_mode:{cluster_id}` | manual | Read | Shadow mode flag |
| `spot:cluster:pending_pods:{cluster_id}` | agent-written | Read | Pending pod count for health check |

---

## 6. Auto-Rebalancer

**File:** `backend/workers/tasks/auto_rebalancer.py`  
**Schedule:** Every 15 seconds via Celery beat (`workers.auto_rebalancer`)

### Trigger

- Created by `termination_monitor.py` when a spot interruption notice arrives via SQS
- Two types: **Emergency** (90s SLA) and **Graceful** (10 min SLA)
- Rows inserted into `rebalancing_actions` table with `status='in_progress'`

### State Machine

| State | Transition Trigger | Notes |
|---|---|---|
| `CREATED` | Initial insert | |
| `POOL_SELECTED` | Target pool chosen | Via `pool_ranking_service` |
| `SOURCE_CORDONED` | Node cordoned | AgentAction: `CORDON_NODE` |
| `SOURCE_DRAINED` | Node drained | AgentAction: `DRAIN_NODE` |
| `REPLACEMENT_LAUNCHING` | New node requested | Via Karpenter or SubstituteManager |
| `REPLACEMENT_READY` | New node READY in DB | Poll `Instance` table |
| `SOURCE_TERMINATING` | Old node terminating | AgentAction: `TERMINATE_NODE` |
| `COMPLETED` | All steps done | Duration logged |
| `FAILED` | Any step fails | Error stored in `action_metadata` |
| `DRAIN_TIMEOUT` | Drain exceeds TTL | Node uncordoned as rollback |

### Optimistic Locking

```
UPDATE rebalancing_actions
SET current_state = :to_state
WHERE id = :action_id AND current_state = :from_state
```
- Returns `True` only if `rowcount == 1`
- Retries up to 2× with 100ms/200ms backoff (BUG-8 fix)
- Prevents double-execution by concurrent workers

### Cluster Mutex

- Acquires same `cluster_mutex` as PlacementController
- Prevents race between the two engines modifying node/pod state simultaneously

---

## 7. Node Bin Packing / Consolidation

**File:** `backend/workers/tasks/consolidation_analysis_task.py`  
**Schedule:** Every 10 minutes  
**Redis Key Written:** `spot:consolidation:candidates:{cluster_id}` TTL=600s

### Algorithm — Two Branches

| Branch | Condition | Candidate Rule |
|---|---|---|
| **Branch A — Karpenter** | `node.nodepool_name IS NOT NULL` | `do_not_disrupt=False` AND `is_ready=True` AND `cpu_util < 20%` |
| **Branch B — Non-Karpenter** | `nodepool_name IS NULL` | All pods have no `node_affinity_required` AND pod CPU+mem fits on another ready node with headroom |

### CPU Utilisation (Branch A)

```
cpu_util = SUM(cpu_usage_millicores) / SUM(cpu_request_millicores) × 100
```
- Source: `pod_metrics` last 5 minutes
- Threshold: `_KARPENTER_CPU_THRESHOLD_PCT = 20.0` (hardcoded, not configurable)

### Savings Estimation

- OD price from `AWSPricingService.get_ondemand_price()` or Redis `spot:pricing:ondemand:{instance_type}:{region}`
- Spot price from Redis `spot:pricing:instance:{instance_type}:{region}`
- `savings_per_node = max(0, od_price - spot_price) × 730`
- Returns `None` with `reason="pricing_data_pending"` if either price missing

### API Consumption

- `GET /optimize/nodes/bin-packing` reads `consolidation_candidates` from Redis key above
- `data_ready = (consolidation_candidates is not None) AND NOT freshness.is_stale`

### Overload Threshold

```python
_OVERLOAD_THRESHOLD = 85.0  # defined in optimize_routes.py
```
- Applied per-node in bin-packing API: `cpu_actual_pct > 85 OR mem_actual_pct > 85` → `is_overloaded=True`

---

## 8. AgentAction System

**Model:** `backend/models/agent_action.py` → table `agent_actions`

### Action Types

| Type | Created By | Handled By | Actuator |
|---|---|---|---|
| `EVICT_POD` | PlacementController | Agent poll endpoint | `kubectl evict` |
| `DRAIN_NODE` | ExecutionController, AutoRebalancer | Agent poll endpoint | `kubectl drain` |
| `TERMINATE_NODE` | ExecutionController, AutoRebalancer | Agent poll endpoint | AWS EC2 `TerminateInstances` |
| `CORDON_NODE` | AutoRebalancer | Agent poll endpoint | `kubectl cordon` |
| `UNCORDON_NODE` | AutoRebalancer (rollback), reconciliation | Agent poll endpoint | `kubectl uncordon` |
| `APPLY_LABEL` | HygieneService, KarpenterService | Agent poll endpoint | `kubectl label node` |
| `APPLY_TAINT` | HygieneService | Agent poll endpoint | `kubectl taint node` |

> **Dead Path Check:** All 7 types above are both created and referenced in agent actuator. No dead AgentAction types identified.

### Statuses

| Status | Meaning |
|---|---|
| `PENDING` | Created, waiting for agent to pick up |
| `PICKED_UP` | Agent claimed the action |
| `COMPLETED` | Agent reported success |
| `FAILED` | Agent reported failure |
| `EXPIRED` | Not picked up within TTL (cleaned by `approval_cleanup` task) |

### Priority

- Integer field; higher = processed first by agent
- PlacementController uses `priority=5` (default)
- ExecutionController uses `priority=10` (higher priority)
- Emergency handler uses highest priority

### Payload Schema

```json
{
  "pod_name": "string",
  "node_name": "string",
  "namespace": "string",
  "ignore_daemonsets": true,
  "source": "string"
}
```

### DB Indexes

- `(cluster_id, status, action_type)` — for in-flight query
- `(cluster_id, created_at)` — for cleanup
- `(payload → pod_name)` — JSON index for pod-level dedup

---

## 9. Execution Controller

**File:** `backend/services/execution_controller.py`  
**Role:** Zero-downtime spot node replacement pipeline. Called by emergency handlers and direct callers.

### Pipeline Steps

| Step | Method | Mechanism | Timeout |
|---|---|---|---|
| 1. Capacity Check | `_dry_run_capacity_check()` | `dry_run_pool()` via AWS EC2 RunInstances DryRun; Redis-cached 2min | — |
| 2. Provision Substitute | `_provision_substitute()` | `substitute_manager.create_substitute()` or stub `sub-{id}-pending` | — |
| 3. Wait Substitute Ready | `_wait_substitute_ready()` | Poll `Instance.status IN ('READY','running')` every 10s | 300s |
| 4. Drain Source Node | `_drain_node()` | Creates `DRAIN_NODE` AgentAction; polls for COMPLETED/FAILED | 120s |
| 5. Verify Workload Health | `_verify_workload_health()` | Reads `spot:cluster:pending_pods:{cluster_id}` from Redis; threshold = `PC_PENDING_PODS_THRESHOLD` env var (default 3) | — |
| 6. Terminate Source | `_terminate_node()` | Creates `TERMINATE_NODE` AgentAction; polls for COMPLETED/FAILED | 120s |

### Rollback Logic

- If step 4 (drain) fails or step 5 (health check) fails: `_rollback_drain()` called → `kubectl uncordon` (production stub — comment says "Production: kubectl uncordon")
- Rollback is **logged** but the actual uncordon is not implemented in code (stub comment only)

### Concurrency

- Acquires cluster-level `cluster_mutex` before execution
- Checks `CLUSTER_BATCH_SIZE` enforcement before proceeding

---

## 10. Full Flow Traces

### 10.1 Workload Classification Flow

```
pod_metrics ingestion (agent heartbeat every 60s)
    │
    ▼
pod_metrics table (PostgreSQL)
    │
    ▼
workload_inspector.py — builds WorkloadInput from:
  • K8s API: replicas, PDB, topology spread, priority class, services, ingress
  • pod_metrics table: restart rates, age, metrics_stale_minutes
  • workload_classifier.py: detected_app_type (heuristics on labels/annotations)
    │
    ▼
workload_identification_engine.classify_workload(WorkloadInput)
  • compute_criticality() → criticality_score, tier
  • compute_spot_score() → spot_score, spot_friendly
  • enforce_confidence() → confidence_state (DRAFT/PROVISIONAL/CONFIRMED)
  • v4.4 signals: az_spread_required, disruption_safe
    │
    ▼
WorkloadClassificationRecord write to workload_classifications table
    │
    ▼
API: GET /optimize/workloads/placement/summary
  Joins workload_classifications + placement_policies
  Returns: tier, spot_score, confidence_state, placement_state, savings
    │
    ▼
UI: WorkloadPlacement page reads the summary endpoint
```

### 10.2 Pod Eviction Flow

```
PlacementAdvisor cycle (every 30 min)
  → Writes PlacementPolicyRecord (ondemand_target, spot_target)
    │
    ▼
PodPlacementEngine.materialize_plan()  ── called by /placement-detail API (UI) today;
    │  ── PlacementController integration planned
    ▼
PlacementController cycle (every 5 min via Celery)
  dispatch_placement_controller_cycles → run_placement_controller_cycle(cluster_id)
    │
    ├─ circuit breaker check (Redis)
    ├─ scaling guard check (Redis)
    ├─ cluster_mutex acquire (Redis, TTL=60s)
    ├─ batch limit check (DB count AgentActions IN_FLIGHT)
    └─ _get_actionable_workloads() → PlacementPolicyRecord WHERE od_excess > 0
           │
           ▼
       _process_workload(cluster_id, workload_id, policy)
         ├─ workload_lock acquire (Redis, TTL=30s)
         ├─ cooldown check (Redis)
         ├─ PDB check (pdb_service or Redis state)
         ├─ pod age check (pod_metrics.start_time)
         ├─ last-pod safeguard
         ├─ active action dedup (DB query AgentAction PENDING/PICKED_UP for pod)
         └─ AgentAction.create(type=EVICT_POD, status=PENDING, payload={pod_name, node_name})
               │
               ▼
Agent poll: GET /agent/{cluster_id}/actions (every ~10s)
  Returns PENDING AgentActions ordered by priority
    │
    ▼
Agent actuator: kubectl evict {pod_name} --namespace {namespace}
    │
    ▼
Agent reports result: POST /agent/{cluster_id}/actions/{id}/result
  → AgentAction.status = COMPLETED or FAILED
  → retry_count incremented on FAILED
    │
    ▼
PlacementController next cycle:
  • COMPLETED → spot:workload:state updated (current_od decremented)
  • FAILED with retry_count >= max → permanent_failure metric
```

### 10.3 Node Rebalancing Flow

```
Spot interruption notice arrives in AWS SQS queue
    │
    ▼
SQS Consumer (every 30s Celery) → sqs_consumer.poll_interruption_queues
    │
    ▼
emergency_event_processor.py → creates RebalancingAction(type=EMERGENCY, status=in_progress)
    │
    ▼
auto_rebalancer.py (every 15s Celery) — queries rebalancing_actions WHERE status=in_progress
    │
    ├─ _sm_transition(CREATED → POOL_SELECTED) [optimistic lock]
    ├─ pool_ranking_service → select target pool
    ├─ _sm_transition(POOL_SELECTED → SOURCE_CORDONED)
    ├─ AgentAction(CORDON_NODE) → agent executes kubectl cordon
    ├─ _sm_transition(SOURCE_CORDONED → SOURCE_DRAINED)
    ├─ AgentAction(DRAIN_NODE) → agent executes kubectl drain
    ├─ _sm_transition(SOURCE_DRAINED → REPLACEMENT_LAUNCHING)
    ├─ Karpenter NodePool update OR SubstituteManager.create_substitute()
    ├─ _sm_transition(REPLACEMENT_LAUNCHING → REPLACEMENT_READY)
    │   Poll Instance table until status=READY (timeout → DRAIN_TIMEOUT)
    ├─ _sm_transition(REPLACEMENT_READY → SOURCE_TERMINATING)
    ├─ AgentAction(TERMINATE_NODE) → agent executes AWS EC2 TerminateInstances
    └─ _sm_transition(SOURCE_TERMINATING → COMPLETED)
         → duration logged, RebalancingAction.completed_at = now
```

---

## 11. API Endpoint Mapping — /optimize

All endpoints in `backend/api/optimize_routes.py`.

| Endpoint | Method | Summary | Key Data Sources |
|---|---|---|---|
| `/optimize/workloads/placement-state` | GET | Per-workload placement state + actionability gates | DB: `workload_classifications`, `placement_policies`; Redis: `spot:workload:state:{cid}:{wid}` |
| `/optimize/workloads/actionability-gates` | GET | Gate flags blocking placement actions | Redis: workload state key; DB: workload_classifications |
| `/optimize/workloads/placement/summary` | GET | Aggregated placement summary (savings, drift) | DB: `workload_classifications` JOIN `placement_policies`; Redis: workload state per workload |
| `/optimize/workloads/profiling/summary` | GET | Profiling data: tier, CV, savings | DB: `workload_classifications`, `placement_policies`; Redis: `spot:placement:metrics:{cid}` |
| `/optimize/nodes/bin-packing` | GET | Node utilisation + consolidation candidates | DB: `node_metadata` JOIN `pod_metrics` (aggregated); Redis: `spot:consolidation:candidates:{cid}` |
| `/optimize/workloads/{id}/pods` | GET | Pod list with AZ + capacity_type | DB: `pod_metrics` DISTINCT pod_name JOIN `node_metadata`; AgentAction EVICT_POD in-flight |
| `/optimize/workloads/scaling` | GET | HPA scaling status per workload | DB: `hpa_configs`, `hpa_status_snapshots`, `pod_metrics`; KEDA service |
| `/optimize/nodes/{name}/bin-packing-detail` | GET | Per-node pod list for treemap | DB: `pod_metrics` WHERE node_name AND timestamp > 1h |
| `/optimize/workloads/{id}/profiling-detail` | GET | 14-day CPU timeseries + classification | DB: `pod_metrics` grouped by day, `workload_classifications`, `placement_policies` |
| `/optimize/workloads/placement` | GET | Paginated workload placement list | DB: `workload_classifications`; per-workload: `placement_policies` + Redis state + log |
| `/optimize/workloads/{id}/placement-detail` | GET | Full placement detail for one workload; includes `placement_plan` from `PodPlacementEngine` | Redis: state + log + WIE classification + cooldown set; DB: `pod_metrics` JOIN `node_metadata` JOIN `NodeMetric` |
| `/optimize/workloads/{id}/scaling-detail` | GET | 120-min HPA snapshot timeline | DB: `hpa_configs`, `hpa_status_snapshots`, `pod_metrics`; AgentAction in-flight |
| `/optimize/system/health` | GET | Eviction + placement health metrics | DB: `agent_actions` (24h stats), `workload_classifications`, `placement_policies`; Redis: PC metrics, CB state |

### Response Field Sources (Critical Fields)

| Field | Endpoint | Source | Type |
|---|---|---|---|
| `placement_state` | `/placement` | `compute_placement_state(current_od, ondemand_target, last_action)` | **Computed** |
| `od_excess` | `/placement` | `current_od − ondemand_target` | **Computed** |
| `current_spot_pods` | `/placement` | Redis `spot:workload:state:{cid}:{wid}` → `current_spot_pods` | **Redis** |
| `current_ondemand_pods` | `/placement` | Redis `spot:workload:state:{cid}:{wid}` → `current_ondemand_pods` | **Redis** |
| `placement_plan` | `/workloads/{id}/placement-detail` | `PodPlacementEngine.materialize_plan().to_dict()` | **Computed** |
| `placement_plan.feasibility.status` | `/workloads/{id}/placement-detail` | Engine status enum: `no_pods_observed \| no_node_data \| already_optimal \| plan_generated \| infeasible` | **Computed** |
| `estimated_monthly_saving_usd` | `/placement`, `/profiling-detail` | DB `placement_policies.estimated_monthly_saving_usd` | **DB** |
| `ondemand_target` | `/placement`, `/profiling-detail` | DB `placement_policies.ondemand_target` | **DB** |
| `spot_target` | `/profiling-detail` | DB `placement_policies.spot_target` | **DB** |
| `cpu_cv` | `/profiling-detail` | DB `placement_policies.pod_cpu_cv` | **DB** |
| `traffic_skew_detected` | `/profiling-detail` | DB `placement_policies.traffic_skew_detected` | **DB** |
| `consolidation_candidates` | `/nodes/bin-packing` | Redis `spot:consolidation:candidates:{cid}` | **Redis** |
| `is_overloaded` | `/nodes/bin-packing` | `cpu_actual_pct > 85 OR mem_actual_pct > 85` | **Computed** |
| `lifecycle_state` | `/nodes/bin-packing` | `compute_node_lifecycle(is_ready, do_not_disrupt, has_pending_drain)` | **Computed** |
| `lifecycle_class` | `/workloads/{id}/pods` | `classify_pod_lifecycle(phase, cpu_usage_millicores, has_pending_evict)` | **Computed** |
| `eviction_success_rate_24h` | `/system/health` | DB count AgentAction EVICT_POD 24h | **DB Computed** |
| `drift_resolution_rate` | `/system/health` | Per-workload `compute_placement_state()` loop | **Computed + Redis** |
| `pc_cycle_count` | `/system/health` | Redis `spot:placement_controller:metrics:{cid}` hash | **Redis** |
| `circuit_breaker_active` | `/system/health` | Redis `spot:pc:circuit_breaker:{cid}` | **Redis** |
| `hpa_status` (e.g. AT_MAX) | `/workloads/scaling` | `_classify_hpa_status()` computed from hpa_configs + snapshots | **Computed** |
| `recommendation_basis_label` | `/workloads/scaling` | Hardcoded string constant `_RECOMMENDATION_BASIS_LABEL` | **HARDCODED** |
| `cooldown_assessment` | `/workloads/scaling` | `_cooldown_assessment(scale_up_stabilization_seconds)` | **Computed** |

### Data Freshness

- All node/pod endpoints compute `compute_freshness(MAX(table.timestamp))` and return `is_stale`, `data_age_seconds`, `freshness_label`
- Stale nodes excluded from bin-packing via `stale_node_filter(nodes, "node_updated_at")`
- `data_ready` flag tells UI whether to show spinner or real data

---

## 12. Redis Key Registry

Full registry from `backend/redis_keys.py` + usage across services.

### Placement Controller Keys

| Key Pattern | TTL | Writer | Reader |
|---|---|---|---|
| `spot:pc:circuit_breaker:{cluster_id}` | 600s | PlacementController | PlacementController |
| `spot:pc:cb_trips_24h:{cluster_id}` | 86400s | PlacementController | `/system/health` API |
| `spot:placement_controller:metrics:{cluster_id}` | 3600s | PlacementController | `/system/health` API |
| `spot:pc:workload_log:{cluster_id}:{workload_id}` | 3600s | PlacementController | `/workloads/placement`, `/workloads/{id}/placement-detail` |
| `spot:placement_controller:shadow_mode:{cluster_id}` | manual | Ops | PlacementController |
| `spot:cluster:pending_pods:{cluster_id}` | agent-written | Agent heartbeat | ExecutionController health check |

### Placement Advisor Keys

| Key Pattern | TTL | Writer | Reader |
|---|---|---|---|
| `spot:placement:policy:{cluster_id}:{workload_id}` | varies | PlacementAdvisor | PlacementController |
| `spot:placement:cluster_state:{cluster_id}` | varies | PlacementAdvisor | PlacementAdvisor |
| `spot:placement:availability_history:{region}` | — | Agent/pricing worker | PlacementAdvisor |
| `spot:placement:availability_history_az:{region}` | — | Agent/pricing worker | PlacementAdvisor |
| `spot:placement:scheduling_success:{type}:{window}` | — | Pricing/monitoring worker | PlacementAdvisor |
| `spot:placement:metrics:{cluster_id}` | — | PlacementAdvisor task | Profiling summary API |

### Workload State Keys

| Key Pattern | TTL | Writer | Reader |
|---|---|---|---|
| `spot:workload:state:{cluster_id}:{workload_id}` | 300s | PlacementController (post-eviction) | Placement APIs, `/placement-detail` |
| `spot:workload_tier:{cluster_id}:{ns}/{ctrl}` | 540s | WorkloadInspector | AutoRebalancer, EvictionSafety, OptimizerCoordinator |
| `spot:workload_profile:{cluster_id}:{ns}/{ctrl}` | 540s | WorkloadInspector | Multiple services |

### Consolidation Keys

| Key Pattern | TTL | Writer | Reader |
|---|---|---|---|
| `spot:consolidation:candidates:{cluster_id}` | 600s | `consolidation_analysis_task` | `/nodes/bin-packing` API |

### Pricing Keys

| Key Pattern | TTL | Writer | Reader |
|---|---|---|---|
| `spot:pricing:instance:{type}:{region}` | 3600s | `pricing_worker` | ConsolidationTask, PlacementAdvisor |
| `spot:pricing:ondemand:{type}:{region}` | 43200s | `pricing_worker` | ConsolidationTask, PlacementAdvisor |

### PodPlacementEngine Keys

| Key Pattern | TTL | Writer | Reader |
|---|---|---|---|
| `spot:placement:cooldown:{cluster_id}:{workload_id}` | varies | PlacementController (post-eviction) | `PodPlacementEngine.materialize_plan()` via `/placement-detail` API |

### Cooldown / Lock Keys

| Key Pattern | TTL | Purpose |
|---|---|---|
| `spot:cooldown:cluster:{id}` | 60min | Cluster-level cooldown |
| `spot:cooldown:pool:{pool_id}` | 120min | Pool-level cooldown |
| `spot:cooldown:resize:{id}` | 360min | Resize cooldown |
| `spot:cluster_mutex:{cluster_id}` | 60s | PlacementController + AutoRebalancer mutual exclusion |
| `spot:workload:lock:{cluster_id}:{workload_id}` | 30s | Per-workload eviction lock |

### Observability Keys

| Key Pattern | TTL | Purpose |
|---|---|---|
| `obs:decisions:{cluster_id}` | 86400s | Last 100 optimizer decisions (list) |
| `spot:errors:celery_task_failure:{cluster_id}` | 86400s | Error counter per cluster |

---

## 13. Celery Beat Schedule

All tasks from `backend/workers/app.py`.

### Optimization-Critical Tasks

| Task Name | Schedule | File | Notes |
|---|---|---|---|
| `workload-cv-every-10-mins` | 600s | `workload_cv_task` | Writes cpu_cv to workload_classifications |
| `hpa-recommendation-every-30-mins` | 1800s | `hpa_recommendation_task` | Writes recommended_max/min to hpa_configs |
| `consolidation-analysis-every-10-mins` | 600s | `consolidation_analysis_task` | Writes to Redis consolidation key |
| `placement-controller-dispatch-every-5-mins` | 300s | `placement_controller_task` | Dispatches per-cluster eviction cycles |
| `placement-controller-recovery-dispatch-hourly` | 3600s | `placement_controller_task` | Stale migration recovery |
| `unified-pool-optimization-every-30-mins` | 1800s | `optimizer_coordinator_worker` | Pool ranking + rotation |
| `auto-rebalancer-every-15-secs` | 15s | `auto_rebalancer` | State machine execution |
| `termination-monitor-every-30-secs` | 30s | `termination_monitor` | Spot ITN detection |
| `sqs-interrupt-consumer-every-30-secs` | 30s | `sqs_consumer` | SQS interrupt consumer |
| `control-plane-all-clusters-every-5-mins` | 300s | `control_plane_loop` | 8-step decision cycle |

### Pricing / Data Tasks

| Task Name | Schedule | Notes |
|---|---|---|
| `spot-price-ingest-every-10-mins` | 600s | Spot price refresh |
| `regional-pricing-refresh-every-10-mins` | 600s | Regional pricing freshness |
| `ondemand-price-refresh-12h` | 43200s | OD price refresh |
| `instance-catalog-refresh-daily-3am` | crontab(0,3) | Instance catalog |
| `de-dryrun-refresher-every-5-mins` | 300s | Dry-run capacity cache |
| `spot-advisor-scrape-12h` | 43200s | Spot advisor interruption data |

### Overlaps / Potential Conflicts

| Scenario | Tasks Involved | Risk |
|---|---|---|
| `auto-rebalancer` + `placement-controller` running concurrently | Both use `cluster_mutex` | **MITIGATED** — mutex enforces serialization |
| `control-plane-all-clusters-every-5-mins` + `placement-controller-dispatch-every-5-mins` | Potential double-action on same cluster | **RISK** — `control_plane_loop` must not duplicate PC cycle logic |
| `pool-rotation-check-every-5-mins` + `de-verified-pools-every-5-mins` | Both maintain pool sets | Low risk — different keys |
| PlacementAdvisor has no explicit beat entry | `placement_advisor_task` included in workers but no `beat_schedule` entry visible | **GAP** — advisor may not be auto-scheduled |

---

## 14. Concurrency Controls

| Control | Mechanism | TTL | Scope | Acquirer(s) |
|---|---|---|---|---|
| `cluster_mutex` | Redis SET NX | 60s | Per cluster | PlacementController, AutoRebalancer |
| `workload_lock` | Redis SET NX | 30s | Per workload | PlacementController `_process_workload()` |
| `placement_cycle_lock` | Redis SET NX | varies | Per cluster | PlacementAdvisor task |
| `rebalancing_actions` optimistic lock | DB `UPDATE WHERE current_state=` | DB tx | Per action | AutoRebalancer |
| `CLUSTER_BATCH_SIZE` | DB count IN_FLIGHT | — | Per cluster | PlacementController |
| `hibernation:lock:{sched}:{cluster}` | Redis | 180s | Per cluster | HibernationWorker |
| `spot:stabilization_lock:{cluster_id}` | Redis | 15min | Per cluster | CooldownController |

---

## 15. DB Tables Queried in Optimize APIs

| Table | Queried In | Purpose |
|---|---|---|
| `workload_classifications` | All placement/profiling endpoints | Core workload scoring data |
| `placement_policies` | placement, profiling-detail, profiling-summary, system health | OD/Spot targets, savings |
| `node_metadata` | bin-packing, pods endpoints | Node AZ, capacity_type, utilisation |
| `pod_metrics` | bin-packing, pods, profiling-detail, scaling-detail | Pod-level CPU/mem metrics |
| `agent_actions` | bin-packing (drain check), pods (evict check), system health | In-flight action state |
| `hpa_configs` | scaling, scaling-detail | HPA configuration |
| `hpa_status_snapshots` | scaling, scaling-detail | HPA history snapshots |
| `rebalancing_actions` | AutoRebalancer worker | State machine rows |
| `instances` | ExecutionController `_wait_substitute_ready()` | Substitute node status |
| `clusters` | All endpoints (assert_cluster_access) | Cluster authorization |
| `audit_logs` | ObservabilityLogger | Decision audit trail |

---

## 16. Observability & Audit Coverage

### ObservabilityLogger (`backend/services/observability_logger.py`)

| Method | Used For | Coverage |
|---|---|---|
| `log_decision()` | All optimization decisions | PlacementController, AutoRebalancer, OptimizerCoordinator |
| `log_state_transition()` | Circuit breaker + phase transitions | Circuit breaker trips, phase changes |
| `log_guardrail_block()` | Guardrail violations | GuardrailEngine blocks |
| `log_pool_switch()` | Pool rotation decisions | pool_rotation_service, optimizer_coordinator |
| `log_rightsizing_proposal()` | Rightsizing proposals | rightsizing_service |

### Dual Write

- **Redis** — last 100 decisions per cluster at `obs:decisions:{cluster_id}` (TTL 24h)
- **DB** — `audit_logs` table via `_persist_to_db()` (best-effort, failure silently swallowed)

### Celery Task Failure Logging

All tasks (workload_cv_task, consolidation_analysis_task) on failure:
1. Log exception via `logger.exception()`
2. Write to ObservabilityLogger with `decision_type="TASK_FAILURE"`
3. Increment Redis error counter `spot:errors:celery_task_failure:{cluster_id}`
4. Retry via `self.retry(exc=exc, countdown=60)`

### Coverage Gaps

| Component | Coverage Gap |
|---|---|
| `_rollback_drain()` in ExecutionController | Only logs warning; no audit log entry |
| PlacementController workload-level loop exceptions | Caught, logged via `logger.exception()` only; no ObservabilityLogger call |
| Agent actuator execution errors | Agent-side only; not surfaced to ObservabilityLogger |
| AutoRebalancer `DRAIN_TIMEOUT` state | DB state updated, no ObservabilityLogger entry confirmed |

---

## 17. Silent Failure Paths

Top silent failure or ignored error paths identified in code:

| # | Location | Failure | Handling |
|---|---|---|---|
| 1 | `optimize_routes.py` — all `_safe_fetch()` calls | Any exception in DB/Redis fetch | Returns fallback default; logs nothing |
| 2 | `ExecutionController._rollback_drain()` | Uncordon not implemented | Only logs warning; no actual uncordon action |
| 3 | `ObservabilityLogger._persist_to_db()` | DB write failure | `logger.debug()` only; audit record silently lost |
| 4 | `PlacementController._process_workload()` outer try/except | Workload loop exception | `logger.exception()` only; cycle continues |
| 5 | `_verify_workload_health()` in ExecutionController | Redis unavailable | Returns `(True, "no_redis_data_assume_healthy")` — health assumed OK |
| 6 | `consolidation_analysis_task._analyze_cluster()` | Per-cluster failure | Warning log + ObservabilityLogger; other clusters continue |
| 7 | `placement-detail` API — `state_locks` from Redis | Redis unavailable | `safe_get_json()` returns empty dict; locks show as False (wrongly open) |
| 8 | `compute_spot_availability_factor()` in PlacementAdvisor | `except: pass` in AZ spike loop | AZ spike detection silently skipped |
| 9 | `placement_advisor_task.py` — rollout execution | `PlacementRolloutService` exceptions | Caught per-workload; metrics emitted, cycle continues |
| 10 | `auto_rebalancer.py` `_sm_transition()` after all retries | Lost state transition | Returns False; action stays stuck in previous state indefinitely |

---

## 18. Environment Variables Affecting Optimization

| Variable | Default | Used In | Effect |
|---|---|---|---|
| `PC_PENDING_PODS_THRESHOLD` | `3` | ExecutionController `_verify_workload_health()` | Max pending pods before health check fails |
| `REDIS_URL` | `redis://localhost:6379/0` | All Redis clients | Redis broker + backend |
| `ENABLE_POOL_ROTATION` | `False` | optimizer_coordinator_worker | Gate for pool auto-rotation |
| `ENABLE_SPOT_MIGRATION` | `False` | placement_controller_task (shadow mode default) | Master gate for live evictions |
| `CLUSTER_BATCH_SIZE` | `5` | placement_controller_service | Max in-flight actions per cluster |
| `AWS_REGION` | `us-east-1` | aws_pricing_service, consolidation_task | Default region for pricing lookups |
| `PC_CB_THRESHOLD` | `5` | placement_controller_service | Circuit breaker failure threshold |
| `PC_CB_WINDOW_SECS` | `300` | placement_controller_service | CB failure count window |
| `PC_CB_COOLDOWN_SECS` | `600` | placement_controller_service | CB open duration |
| `COLD_START_HOURS` | `24` | workload_identification_engine | Hours before CONFIRMED allowed |

---

## 19. Performance Risks & N+1 Queries

| # | Location | Risk | Fix Needed |
|---|---|---|---|
| 1 | `_get_placement_workload_rows()` in `optimize_routes.py` | **N+1**: Per-workload `db.query(PlacementPolicyRecord).filter(workload_id==wc.workload_id)` inside loop over all workloads | Batch load all PPRs with `WHERE cluster_id=X`, build dict, look up |
| 2 | `/optimize/workloads/placement/summary` | Per-workload Redis `safe_get_json()` call inside loop | Batch with `mget` or pipeline |
| 3 | `/optimize/system/health` drift_resolution_rate loop | Per-workload `db.query(PlacementPolicyRecord)` + Redis get inside loop over `_wcs` | Batch both queries |
| 4 | `workload_cv_task._compute_for_cluster()` | Single `PodMetric` query fetches ALL 14-day data for cluster at once | Potential memory issue for large clusters |
| 5 | `consolidation_analysis_task._can_drain()` | Per-node `PodMetric` query inside node loop | Batch with single `WHERE node_name IN (...)` query |
| 6 | `placement_controller_service._process_workload()` | Per-pod active-action DB check inside workload loop | Use pre-loaded set from batch query |
| 7 | Missing index on `pod_metrics(cluster_id, controller_name, timestamp)` | High-frequency queries in profiling endpoints | Add composite index |

---

## 20. Karpenter Integration

| Path | Implementation | Status |
|---|---|---|
| Node consolidation candidates (Branch A) | `consolidation_analysis_task` checks `nodepool_name IS NOT NULL` | **Active** |
| Pool rotation injection | `pool_rotation_service` via `karpenter_service.add_allowed_instance_type()` | **Active** |
| NodePool type reconciliation | Celery `reconcile-nodepool-types-every-6h` removes orphaned types | **Active** |
| Node provisioning in AutoRebalancer | Karpenter NodePool update OR `substitute_manager.create_substitute()` fallback | **Dual path** |
| Karpenter detection | `KedaService.get_all_scaled_objects()` used in scaling API | **Active** |
| `nodepool_baseline_key` / `injected_type_key` | Written by karpenter_service; read by reconcile task | **Active** |

### Karpenter vs ASG Fallback

- `ExecutionController._provision_substitute()`: tries `substitute_manager.create_substitute()` first; falls back to stub `sub-{id}-pending`
- `auto_rebalancer` replacement: comment says "via Karpenter" but code path not fully traced — may use `substitute_manager`
- **Risk:** If both `substitute_manager` (ASG path) and Karpenter are active, double provisioning is possible

---

## 21. Dead / Unconsumed Backend Features

| Feature | File | Status | Notes |
|---|---|---|---|
| `W3 — Anchored Node Scheduling` | `redis_keys.py` (keys defined) | **Future/Dead** — marked `[future]` | Keys defined but service not implemented |
| `W5 — KEDA Queue Gate` | `redis_keys.py` (keys defined) | **Future/Dead** — marked `[future]` | Keys defined but service not implemented |
| `W7 — HPA/KEDA Freeze` | `redis_keys.py` (keys defined) | **Future/Dead** — marked `[future]` | Keys defined but cleanup task exists |
| `_rollback_drain()` in ExecutionController | `execution_controller.py:413` | **Stub** — comment "Production: kubectl uncordon" | Actual uncordon not implemented |
| `rps_cv` field in workload_cv_task | `workload_cv_task.py` | **Placeholder** — always null | Comment: "requires Prometheus, out of scope" |
| PlacementAdvisor `beat_schedule` entry | `app.py` | **GAP** — no explicit beat entry for advisor cycle | Advisor task registered in `include=` but no schedule |
| `unified-rightsizing-evaluation-daily` | `app.py` | Scheduled but references `workers.optimizer.rightsizing_evaluation` | Task path may not match registered task name |

---

## 22. Known Gaps & Inconsistencies

| # | Area | Description | Severity |
|---|---|---|---|
| 1 | PlacementAdvisor beat schedule | `placement_advisor_task` included in workers but no entry in `app.conf.beat_schedule` | **HIGH** — Advisor may never auto-run |
| 2 | OD/Spot pod counts source | `spot:workload:state:{cid}:{wid}` Redis key provides `current_spot_pods`/`current_ondemand_pods`, but write path not confirmed — may be populated by PlacementController post-eviction only | **HIGH** — Stale if PlacementController cycle skipped |
| 3 | `_rollback_drain()` stub | ExecutionController rollback only logs; uncordon not executed | **HIGH** — Drained nodes stay cordoned after failure |
| 4 | `rps_cv` always null | `workload_cv_task` explicitly skips RPS CV; UI field will always be null | **MEDIUM** — UI shows null for traffic skew RPS signal |
| 5 | N+1 in placement list | `_get_placement_workload_rows()` queries PlacementPolicyRecord per workload in loop | **MEDIUM** — Performance degrades with many workloads |
| 6 | Consolidation threshold hardcoded | `_KARPENTER_CPU_THRESHOLD_PCT = 20.0` in consolidation task; not configurable | **LOW** — Cannot tune without code change |
| 7 | `_OVERLOAD_THRESHOLD = 85.0` hardcoded | In `optimize_routes.py`; not configurable | **LOW** — Cannot tune threshold |
| 8 | Dual CV computation | `workload_cv_task` (14-day) and `PlacementAdvisorService._compute_cv()` (live) coexist; different values | **LOW** — Different purposes, not a bug |
| 9 | `compute_placement_state()` loop in /system/health | Per-workload Redis + DB query inside loop | **MEDIUM** — Performance risk at scale |
| 10 | PlacementAdvisor savings field | `estimated_monthly_saving_usd` depends on `AWSPricingService`; null if pricing unavailable | **MEDIUM** — Savings show null until pricing is warm |
| 11 | Control plane + PC cycle overlap | Both `control-plane-all-clusters-every-5-mins` and `placement-controller-dispatch` run every 5 min | **MEDIUM** — Potential double-action if CP loop duplicates PC logic |
| 12 | `CONFIRMED` workload filter | PlacementController `_get_actionable_workloads()` should filter `confidence_state=CONFIRMED` only; if not enforced, DRAFT workloads could be evicted | **HIGH** — Verify filter in service code |
| 13 | `PodPlacementEngine` not wired to `PlacementController` | ~~Engine is live and called by the `/placement-detail` UI API, but `PlacementController.run_cycle()` does not yet call `materialize_plan()` before dispatching evictions~~ **RESOLVED** — `PlacementController._select_burst_pods()` now reads `spot:placement:anchor_nodes:{cid}:{wid}` from Redis (written by `/placement-detail` API after engine call) and skips pods on anchor nodes | **RESOLVED** |
| 14 | `placement_plan` error fallback missing `status` field | ~~`feasibility.status` absent in error fallback~~ **RESOLVED** — `optimize_routes.py` fallback now includes `"status": "engine_error"`, `"moves_blocked": 0`, `"anchor_plan": {}`, `"cost_projection": {}` | **RESOLVED** |
| 15 | BinPacker used FFD not BFD | ~~FFD (first fit)~~ **RESOLVED** — BFD with multi-factor scoring: BFD-tightness + hotspot_penalty(150) + anchor_penalty(500). Cursors use real `allocatable - used`. 4 dimensions: cpu, mem, pod, ip | **RESOLVED** |
| 16 | BinPacker cursors used `required * 1.5` | ~~Inflated fake capacity~~ **RESOLVED** — `keep` nodes use `allocatable_cpu - used_cpu`; `provision` nodes use `inst_cpu`/`inst_mem` stored by CapacityPlanner | **RESOLVED** |
| 17 | BinPacker missing ip_remaining + real pod_remaining | **RESOLVED** — `ip_remaining = node.ip_available`; `pod_remaining = max_pods - pod_count - daemonset_count` | **RESOLVED** |
| 18 | CostProjector flat $0.10/hr pricing | ~~All instances cost $0.10/hr~~ **RESOLVED** — Static `INSTANCE_HOURLY_OD_USD` table (~40 types: t3/t3a/m5/m6i/c5/c6i/r5/r6i); `SPOT_DISCOUNT_FACTOR=0.65` | **RESOLVED** |
| 19 | AnchorPlanner locked all pods on anchor nodes | ~~All non-system pods on anchor nodes were frozen~~ **RESOLVED** — Only critical pods (anchor_map keys) are locked; non-critical pods steered off by BinPacker's ANCHOR_PENALTY score | **RESOLVED** |
| 20 | PDB check blocked entire plan on any violation | ~~One PDB trigger killed all movements~~ **RESOLVED** — `pdb_budget = running - pdb_min`; only excess pods blocked (highest movement_cost deferred first) | **RESOLVED** |
| 21 | BinPacker `pod_remaining` always 110 (pod_count=0 in node data) | **RESOLVED** — `materialize_plan()` derives `node_pod_counts` + `node_ds_counts` from the `pods` list; passed as `node_pod_counts=`/`node_ds_counts=` to BinPacker; priority: engine-derived → node dict → 0 | **RESOLVED** |
| 22 | `ip_available` + `max_pods` absent from node dict | **TRACKED** — `ip_remaining` defaults to 999 (check effectively bypassed); `max_pods` defaults to 110. Fix requires adding fields to `NodeMetadata` + query builder | **HIGH** — add to NodeMetadata |
| 23 | `movement_plan` steps missing `workload_id`, `from_az`, resource fields | **RESOLVED** — All four fields (`workload_id`, `from_az`, `cpu_request_millicores`, `memory_request_bytes`) now emitted on every step; required by Distribution Engine WorkloadGrouper + PreconditionSnapshotter | **RESOLVED** |

---

## 23. Deep Audit — Verified Q&A (45 Questions)

All answers verified against actual code in `backend/`. Severity: 🔴 Critical · 🟠 High · 🟡 Medium · 🟢 Low

---

### 23.1 — Workload State Source of Truth

**Q: Is there a single source of truth for workload state (OD/Spot counts), or are DB and Redis diverging?**

**A: Diverging — Redis is the live source, DB is the delayed source.**

- `spot:workload:state:{cluster_id}:{workload_id}` is the runtime source for `current_spot_pods`, `current_ondemand_pods`, `ready_replicas`, `has_pdb`, HPA bounds.
- The DB (`pod_metrics` table) is the archival source used for freshness, profiling, and API responses.
- These diverge by up to the agent heartbeat interval (~60s) plus Redis TTL (300s). If the agent stops reporting, Redis keys expire after 5 min and all state reads fall back to empty defaults.
- **No write-back from PlacementController to Redis state** — the state is purely agent-push.

🟠 **Impact:** UI placement counts and OD-excess calculations can lag 60–360 seconds behind actual cluster state.

---

**Q: Exactly where is `spot:workload:state:{cluster_id}:{workload_id}` written, and is it updated on every placement change?**

**A: Written exclusively by `api/agent_routes.py` during agent heartbeat.**

```python
# agent_routes.py:263-267
_r.setex(
    f"spot:workload:state:{cluster.id}:{_wid}",
    300,
    json.dumps(_state_payload),
)
```

- Payload contains: `pdb_min_available`, `hpa_min_replicas`, `hpa_max_replicas`, `ready_replicas`, `current_spot_pods`, `current_ondemand_pods`, `has_pdb`, `has_topology_spread`, `has_pod_anti_affinity`.
- Written per-workload from `hpa_pdb_data` + `pod_metrics_per_workload` fields in the heartbeat request body.
- **NOT written after each eviction or placement change** — only during the next agent heartbeat cycle (~every 60s).
- TTL = 300s. If heartbeat stops, key expires and all consumers get empty `{}`.

🟠 **Impact:** PlacementController reads this key for last-pod guard, PDB check, and rollout status. Stale data here can both allow unsafe evictions (PDB check fails-open when key absent) and block valid evictions (stale `ready_replicas=1`).

---

**Q: What happens to workload state if PlacementController does not run for a cycle—does UI show stale or incorrect distribution?**

**A: UI shows the last Redis-cached state, which may be up to 300s stale; if the key has expired, all counts show as 0.**

- UI reads `spot:workload:state` via `/optimize/workloads/placement` → `_get_placement_workload_rows()` → `safe_get_json(redis_client, state_key, default={})`.
- If the key is absent (expired), `current_spot=0`, `current_od=0`, `od_excess=None`. Placement state computes as `UNKNOWN`.
- PlacementController not running has no direct effect on Redis state — state is agent-pushed. If agent is alive, state stays fresh regardless of PC running.

🟡 **Impact:** Skipped PC cycles show as `UNKNOWN` placement state in UI, but correct pod counts remain while agent is healthy.

---

### 23.2 — Confidence and Classification Gating

**Q: Does PlacementController strictly filter `confidence_state=CONFIRMED` before eviction, or can DRAFT/PROVISIONAL leak into execution?**

**A: Yes, strictly enforced — two independent gates prevent non-CONFIRMED workloads from being evicted.**

Gate 1 — `placement_advisor_task.py:51-54`:
```python
workloads = db.query(WorkloadClassification).filter(
    WorkloadClassification.cluster_id == cluster_id,
    WorkloadClassification.confidence_state == "CONFIRMED"
).all()
```
Only CONFIRMED workloads receive placement policies.

Gate 2 — `placement_advisor_service.py:735`:
```python
actionable = not obs_mode and not degraded and not guards.blocked and classification.confidence_state == "CONFIRMED"
```
Even if a non-CONFIRMED policy exists in Redis, `actionable=False` prevents PlacementController from including it (PC's `_get_actionable_workloads()` filters `policy.get("actionable")`).

Gate 3 — `placement_advisor_service.py:603`:
```python
if policy.confidence_state != "CONFIRMED" and policy.spot_target > 0:
    _fail("spot_target_non_confirmed", "spot_target must be 0 for non-CONFIRMED")
```

🟢 **No leak path identified.** DRAFT/PROVISIONAL workloads receive `actionable=False` and `spot_target=0`.

---

**Q: Is there any mechanism to invalidate outdated workload classification (confidence decay)?**

**A: No automatic decay. Classification stays CONFIRMED until WIE re-runs.**

- WIE runs only when advisor cycle triggers `workload_inspector` → `classify_workload()`, which happens every ~30 min IF the advisor is scheduled (see §23.9).
- There is no TTL, decay score, or background job that downgrades confidence over time.
- If pod restarts spike or metrics go stale, the NEXT classification run will detect it — not immediately.

🟡 **Impact:** A workload that becomes unstable may continue receiving spot eviction attempts for up to 30 min (or until the next advisor cycle) before confidence drops.

---

### 23.3 — Post-Eviction Behavior

**Q: Can a pod be evicted and then rescheduled back onto an On-Demand node — where is this prevented in code?**

**A: Not fully prevented — the Mutating Webhook injects soft Spot affinity but the scheduler can override it.**

- PlacementController dispatches `EVICT_POD` which triggers `kubectl evict`. The pod is deleted and Kubernetes reschedules it.
- `handle_eviction_result()` in `placement_controller_service.py:1121` calls `get_pod_placement(namespace, pod_name)` via K8s API after eviction.
- If the pod lands on OD (scheduler ignoring the soft Spot affinity): action marked `FAILED`, `retry_count` incremented, cooldown set, next PC cycle detects drift and evicts again.
- The "soft affinity" injected by the Mutating Webhook is not a hard constraint — scheduler can place on OD if Spot capacity is unavailable.

🟠 **Impact:** Perpetual eviction-reschedule loop possible if Spot capacity is insufficient (mitigated by MAX_RETRY_COUNT=3 per action, but new actions are created each cycle).

---

**Q: Is there any verification step after eviction that confirms actual OD→Spot movement, or is success assumed?**

**A: Yes — `handle_eviction_result()` performs real post-eviction placement validation via K8s API.**

```python
placement = get_pod_placement(namespace, pod_name)
```

Outcomes:
- `placement.capacity_type == target_cap` → `COMPLETED` ✅
- `placement.capacity_type != target_cap` → `FAILED`, `retry_count++`, mark for retry via next PC drift cycle
- `placement is None` (pod Pending) → `COMPLETED` with `needs_revalidation=True`, deferred to next cycle
- K8s API error → `COMPLETED` with `placement_check: "api_error:..."`, deferred to next cycle

⚠️ `needs_revalidation=True` flag is stored in `result` JSON but **nothing reads it** to trigger revalidation. It is a dead flag.

🟡 **Residual risk:** API-error and pod-pending paths mark success optimistically; actual placement is only verified on next PC drift cycle.

---

### 23.4 — Concurrency and Race Conditions

**Q: Can PlacementController and AutoRebalancer both act on the same node in overlapping time windows despite cluster_mutex TTL limits?**

**A: Yes — the mutex TTL (60s) is shorter than a full PC cycle duration, creating a real race window.**

- `CLUSTER_MUTEX_TTL_SECS = 60` (hardcoded in `placement_controller_service.py:55`).
- A PC cycle that processes many workloads can exceed 60s, causing the mutex to expire while PC is mid-execution.
- AutoRebalancer polls every 15s. If the mutex expires at second 61, AR can acquire it and begin cordoning/draining nodes that PC is simultaneously trying to evict pods from.

🔴 **No code defense against this.** The mutex is the only cross-engine serialization primitive and its TTL is not dynamically extended mid-cycle.

---

**Q: What happens if cluster_mutex expires mid-cycle — can two controllers overlap execution?**

**A: Yes, confirmed overlap is possible.**

- Redis SET NX TTL-based locks do not auto-renew. If the holder does not re-acquire before expiry, another process wins the next acquisition.
- Neither PlacementController nor AutoRebalancer has a keepalive/heartbeat mechanism on the mutex.
- Worst case: PC is halfway through evicting pods on Node A, AR acquires mutex and begins draining Node A. Two concurrent K8s operations on the same node.

🔴 **Fix needed:** Implement mutex keepalive/renewal during long cycles, or extend TTL to cover worst-case cycle duration.

---

**Q: Is CLUSTER_BATCH_SIZE enforced globally across all action types or only for PlacementController?**

**A: Global across all action types — PC's batch check queries ALL AgentAction statuses.**

```python
# placement_controller_service.py:262-269
running_actions = (
    self.db.query(AgentAction)
    .filter(
        AgentAction.cluster_id == cluster_id,
        AgentAction.status.in_([PENDING, PICKED_UP]),
    )
    .count()
)
cluster_slots_available = CLUSTER_BATCH_SIZE - running_actions
```

Additionally, PC increments `rebalance:active_count:{cluster_id}` Redis semaphore when dispatching so AutoRebalancer's batch guard also sees PC actions.

Note: `CLUSTER_BATCH_SIZE` default is **2** (from env `PC_CLUSTER_BATCH_SIZE`, default `2`) — not 5 as previously documented.

🟢 **Enforcement is global and correct.**

---

### 23.5 — Retry and Oscillation

**Q: Can AgentAction retry_count lead to repeated eviction of same pod without changing outcome (infinite loop scenario)?**

**A: Bounded per-action (MAX_RETRY_COUNT=3), but unbounded across new actions.**

- `MAX_RETRY_COUNT = int(os.getenv("PC_MAX_RETRY_COUNT", 3))` — after 3 retries on one action, it's permanently FAILED and a notification is sent.
- However, `_mark_for_retry()` marks the action FAILED (not re-queued). The **next PC cycle** independently detects drift and creates a **new** AgentAction with `retry_count=0`.
- Net effect: if a pod consistently lands on OD (e.g., no Spot capacity), PC generates a new eviction every 5 minutes indefinitely. Each eviction eventually reaches MAX_RETRY_COUNT=3, but a fresh cycle re-creates it.
- Only stoppers: workload cooldown (10 min between evictions for same workload), circuit breaker (10 failures in 600s window trips CB for 1800s).

🟠 **No true per-workload infinite-loop hard stop.** Circuit breaker is the only cluster-level protection, but it requires 10 failures across all workloads, not just one.

---

**Q: Is there any mechanism that detects oscillation (OD ↔ Spot flip loops) for a workload?**

**A: No dedicated oscillation detector. Only indirect mitigation via cooldowns and circuit breaker.**

- `WORKLOAD_COOLDOWN_MINUTES = 10` — per-workload cooldown is set after each eviction attempt. Prevents immediate re-eviction within 10 min.
- Circuit breaker at cluster level (`PC_CB_THRESHOLD=10` EVICT_POD failures in 600s) trips CB and halts all evictions for 1800s.
- No counter tracking "how many times has workload X been evicted and returned to OD." No Redis key per-workload failure count.
- `spot:pc:workload_log:{cluster_id}:{workload_id}` stores last 10 decisions but nothing reads this log to detect oscillation patterns.

🟠 **Risk:** A workload in a scheduling environment with partial Spot availability can oscillate slowly (evict → OD → evict → OD) staying below the circuit breaker threshold indefinitely.

---

### 23.6 — Placement Advisor Feedback and Staleness

**Q: Does PlacementAdvisor recompute targets based on actual outcomes, or is it stateless and blind to execution results?**

**A: Partially outcome-aware via Redis `spot:workload:state`, but with up to 300s lag.**

- Advisor's `run_placement_cycle()` reads `spot:workload:state:{cluster_id}:{workload_id}` for `current_spot_pods`, `current_ondemand_pods`, `ready_replicas`, `has_pdb`, HPA bounds.
- This state is agent-pushed (not execution-result-pushed), so it reflects actual K8s state as of last heartbeat.
- Advisor computes `input_hash` from workload_state + classification + cluster_state. If nothing changes in inputs, same policy is re-generated each cycle.
- **No feedback loop from AgentAction results** — advisor does not know which evictions succeeded or failed.

🟡 **Impact:** If PC is repeatedly failing to evict a workload (e.g., always lands on OD), advisor continues generating the same `spot_target > 0` policy each cycle.

---

**Q: What happens if placement_policies are stale or missing — does controller still act or skip silently?**

**A: Silently skips — empty actionable workload list means PC processes nothing.**

- `_get_actionable_workloads()` scans Redis keys matching `spot:placement:policy:{cluster_id}:*`.
- If advisor hasn't run (no beat schedule — confirmed gap), these keys don't exist.
- `self.redis.keys(pattern)` returns empty list → `policies = []` → PC loops over zero workloads → no evictions → no log entry explaining why.
- Only evidence: `_emit_cycle_metrics()` shows `evictions_attempted=0` with no `skipped_reason`.

🔴 **Silent skip with no UI visibility.** Combined with the missing advisor beat schedule, this means a fresh cluster may silently never evict any pods.

---

**Q: Is there any guarantee that `ondemand_target + spot_target` equals actual replicas at runtime?**

**A: Guaranteed at policy creation time only — runtime divergence is possible due to HPA scaling.**

At policy write time, `_validate_policy()` enforces:
```python
# placement_advisor_service.py:597-598
if policy.spot_target + policy.ondemand_target != policy.observed_replicas:
    _fail("totals_mismatch", ...)
```

At runtime, if HPA scales replicas from 5→8 between advisor cycles, the stored policy still has `ondemand_target + spot_target = 5`. PC uses `target_od = policy.get("ondemand_target", 1)` — with more OD pods than the old target, it evicts the excess, which may be too aggressive.

🟠 **No runtime re-validation of the invariant** — totals can silently diverge until next advisor cycle (up to 30 min).

---

### 23.7 — Scaling Guard and HPA Race Conditions

**Q: Does workload scaling (HPA/KEDA) invalidate placement targets immediately, or is there a delay window causing incorrect actions?**

**A: Delay window exists — up to 30 min + agent heartbeat lag.**

- When HPA scales a workload, K8s changes `spec.replicas` immediately.
- Agent heartbeat sends new `pod_metrics_per_workload` with updated counts within ~60s → updates `spot:workload:state` TTL-300s.
- PlacementAdvisor runs every 30 min (if scheduled). Next advisor cycle recomputes targets with updated replica count.
- PlacementController's `_scaling_guard_active()` checks pending pods (`spot:cluster:pending_pods`) and recent KEDA events — NOT HPA events.

🟠 **HPA scaling events are NOT caught by the scaling guard.** Only KEDA scaling and pending pods are detected. An HPA scale-up can result in PC evicting newly created OD pods that HPA just launched.

---

**Q: Is scaling guard sufficient to prevent eviction during active scaling, or can race conditions still occur?**

**A: Scaling guard has a race window — key absence fails in different directions depending on context.**

- `_get_pending_pods_count()`: if `spot:cluster:pending_pods:{cluster_id}` key absent → returns `PENDING_PODS_THRESHOLD + 1` → **blocks eviction** (fail-safe).
- `_recent_keda_scaling_event()`: if `spot:keda:last_scale_event:{cluster_id}` key absent → depends on process uptime vs `KEDA_BOOTSTRAP_WINDOW_SECONDS` (300s). After bootstrap window, returns `True` (blocks). During bootstrap window (first 5 min after process start), returns `False` (allows eviction).
- HPA scaling has NO corresponding guard key. HPA-triggered pod creation is invisible to the scaling guard.

🔴 **HPA race condition unmitigated.** PC can evict pods that HPA just scheduled.

---

### 23.8 — Node Capacity Data Sources

**Q: What is the exact source of truth for node capacity — `node_metadata` or live K8s API — and can they diverge?**

**A: Dual source — PlacementController uses Redis (agent-pushed), consolidation uses DB (`node_metadata`).**

- PlacementController `_build_capacity_map()` reads `spot:cluster:spot_nodes:{cluster_id}` from Redis (agent-pushed). Falls back to K8s API client.
- Consolidation task reads `NodeMetadata` from DB (PostgreSQL), filtered by `is_ready=True`.
- `node_metadata` is updated by agent heartbeat → DB write pipeline. Divergence is possible when:
  - New node joins but agent heartbeat hasn't written yet (DB lag ~60s).
  - Node terminates but DB row not yet updated (`is_ready` stays `True`).
  - Redis key expires (TTL varies) before next heartbeat.

🟡 **Expected divergence window: 60–300s.** Capacity decisions may use slightly stale node inventories.

---

### 23.9 — Consolidation Logic Correctness

**Q: Does `consolidation_analysis_task` consider daemonsets and system pods when marking nodes as consolidatable?**

**A: No — DaemonSet pods are NOT filtered. This causes Branch B to incorrectly mark nodes as drainable.**

- `_can_drain()` checks pods via `pod_metrics` WHERE `node_name = X`. It checks `affinity.node_affinity_required` but does NOT filter out `kube-system` namespace, DaemonSet-owned pods, or static pods.
- A node with only DaemonSet pods and no `node_affinity_required` will pass the capacity fit check (DaemonSet pods would re-appear on any replacement node, so "fitting" them is meaningless).
- Branch A (Karpenter) uses `do_not_disrupt=False` and `cpu_util < 20%` — this is correct since Karpenter handles DaemonSet awareness internally.

🟠 **Branch B is incorrect for nodes with only DaemonSet pods.** Such nodes may be marked as consolidatable but cannot actually be drained empty.

---

**Q: Can a node marked as consolidatable still fail Karpenter consolidation due to hidden constraints (PDB, affinity)?**

**A: Yes — backend consolidation analysis is a heuristic, not Karpenter's actual decision.**

- Backend `consolidation_candidates` is computed independently of Karpenter's own disruption budget and consolidation evaluation.
- Karpenter respects PodDisruptionBudgets, `do-not-disrupt` annotations on pods, and scheduling constraints that the backend may not model accurately.
- Backend uses `pod_metadata.affinity.node_affinity_required` field which is populated from agent heartbeat data — may be incomplete or stale.

🟡 **UI may show `consolidation_candidates > 0` while Karpenter actually consolidates nothing.**

---

**Q: Is there any feedback loop that compares predicted consolidation vs actual node termination?**

**A: No. There is no reconciliation between `consolidation_candidates` Redis key and actual node terminations.**

- No task reads both the candidates list and `node_metadata.terminated_at` or AWS EC2 state to compare.
- Candidates key is overwritten every 10 min with fresh analysis regardless of whether previous candidates were acted on.

🟡 **Gap:** Savings estimates in UI are speculative with no actuality tracking.

---

**Q: Can `consolidation_candidates` Redis key become stale and mislead UI if task fails or is delayed?**

**A: Partially protected — key has TTL=600s matching the task interval. But task failure leaves a stale key for up to 10 min.**

- If `consolidation_analysis_task` fails, the existing key survives for 600s with stale data.
- The key payload includes `data_ready=True/False`, so on task failure the key may show stale `data_ready=True` until it expires.
- After expiry, API returns `consolidation_candidates=null` with `data_ready_reason="pricing_data_pending"`.

🟡 **10-min stale window on task failure.** UI may show incorrect candidate counts during this window.

---

### 23.10 — ExecutionController and Node Termination Verification

**Q: Does ExecutionController verify actual node termination from AWS/K8s, or only trust AgentAction COMPLETED status?**

**A: Trusts AgentAction COMPLETED status only — no independent AWS API verification.**

- `_terminate_node()` creates a `TERMINATE_NODE` AgentAction and polls `action_row.status` every 5s for up to 120s.
- Once agent reports `COMPLETED`, ExecutionController proceeds.
- No call to AWS EC2 `describe-instances` or K8s node status check after the action completes.

🟠 **If agent marks COMPLETED due to a K8s success response but AWS termination is still in-flight, ExecutionController treats the node as terminated.**

---

**Q: What happens if agent reports success but node is still alive — is this inconsistency detected?**

**A: Yes, eventually — `reconciliation_worker` (every 5 min) reconciles EC2 vs DB state.**

- `reconciliation_worker` task detects EC2 instances whose state in AWS differs from `Instance.status` in DB.
- If a node was marked terminated in DB but EC2 shows it still `running`, the reconciler should flag it.
- However, the reconciler's behavior on `TERMINATE_NODE` discrepancy is not fully traced — it may only log the inconsistency, not re-trigger termination.

🟡 **Partial protection.** Reconciler detects the gap but may not auto-remediate.

---

**Q: Is `_rollback_drain()` fully implemented or are nodes left cordoned permanently after failure?**

**A: Confirmed stub — nodes ARE left cordoned permanently after drain failure.**

```python
# execution_controller.py:413-416
def _rollback_drain(self, cluster_id: str, node_id: str):
    """Un-cordon the drained node to restore capacity."""
    logger.warning(f"[ExecCtrl] Rolling back drain on {node_id}")
    # Production: kubectl uncordon
```

No `AgentAction(UNCORDON_NODE)` is created. No K8s API call is made. The function only logs a warning.

🔴 **After any drain + health-check failure path in ExecutionController, the source node remains cordoned indefinitely**, removing it from scheduling until manually uncordoned or the reconciler detects and corrects it.

---

### 23.11 — Duplicate Provisioning and Over-Provisioning

**Q: Can `substitute_manager` and Karpenter both provision nodes simultaneously leading to over-provisioning?**

**A: Yes — no cross-engine deduplication exists.**

- `ExecutionController._provision_substitute()` calls `substitute_manager.create_substitute()` which creates an EC2 instance via AWS ASG or direct launch.
- AutoRebalancer concurrently updates Karpenter NodePool `instanceTypes`, which triggers Karpenter to provision a new node to satisfy pending pod scheduling.
- If both paths activate for the same cluster simultaneously (e.g., emergency handler + AutoRebalancer), two nodes can be provisioned where one was needed.

🟠 **No mutex or deduplication key between `substitute_manager` and Karpenter paths.**

---

**Q: Is there any check preventing duplicate node provisioning across AutoRebalancer and ExecutionController?**

**A: No explicit check. cluster_mutex partially prevents it but has the expiry race (§23.4).**

- `cluster_mutex` prevents PC and AR from running simultaneously at the outer dispatch level.
- `ExecutionController` is called from emergency handlers which **do not acquire cluster_mutex** before invoking `execute_replacement()`.
- Emergency rebalancer runs on a separate `emergency` Celery queue with no mutual exclusion with AR.

🔴 **Emergency handler + AR overlap is an unprotected path.**

---

### 23.12 — Redis Unavailability Safety

**Q: What happens if Redis is unavailable — do safety checks fail open (allowing risky actions)?**

**A: Mixed — some checks fail-safe (block), others fail-open (allow). No consistent policy.**

| Check | Redis absent behavior | Direction |
|---|---|---|
| `_get_pending_pods_count()` | Returns `PENDING_PODS_THRESHOLD + 1` → guard triggers | **Fail-safe** ✅ |
| `_would_violate_pdb()` | Returns `False` → eviction allowed | **Fail-open** ⚠️ |
| `_workload_in_cooldown()` | `redis.exists()` returns 0 → no cooldown detected → allows eviction | **Fail-open** ⚠️ |
| `_is_shadow_mode()` | Returns `False` → live mode assumed → evictions proceed | **Fail-open** ⚠️ |
| `_recent_keda_scaling_event()` | Depends on process uptime (bootstrap window logic) | **Mixed** |
| `_build_capacity_map()` | Returns empty map → `_has_spot_capacity_for_target_az()` returns `False` → eviction blocked | **Fail-safe** ✅ |
| Circuit breaker check | `redis.get(cb_key)` returns `None` → CB not open → cycle continues | **Fail-open** ⚠️ |

🔴 **PDB check and cooldown both fail-open on Redis absence.** This means a Redis outage can lead to PDB-violating evictions and no cooldown enforcement.

---

**Q: Does `_verify_workload_health()` incorrectly assume healthy state when Redis data is missing?**

**A: Yes — confirmed by code.**

```python
# execution_controller.py:399-403
raw = _r.get(f"spot:cluster:pending_pods:{cluster_id}")
if raw is None:
    return True, "no_redis_data_assume_healthy"
```

When `spot:cluster:pending_pods:{cluster_id}` key is absent (agent not reporting, Redis restart), the health check returns `(True, healthy)` and ExecutionController proceeds to the terminate step.

🔴 **Node termination can proceed without any cluster health validation if Redis is unavailable or agent is silent.**

---

**Q: Are there any `except: pass` blocks that suppress critical decision failures?**

**A: Yes — several confirmed in key code paths.**

| Location | Code | Risk |
|---|---|---|
| `placement_advisor_service.py:compute_spot_availability_factor()` | `except: pass` inside AZ spike detection loop | AZ failure spike silently ignored; availability factor uses only smoothed average |
| `placement_controller_service.py:_select_burst_pods()` | `except: pass` for node lock lookup failure | Pod on drained node may be included in eviction candidates |
| `placement_controller_service.py:_select_burst_pods()` | `except: pass` for node active action check | Same — lock check silently skipped |
| `placement_advisor_task.py:execute_rollout_task()` | `except: pass` for JSON parse in state read | `current_spot` stays 0; rollout may rerun completed steps |

🔴 **The AZ spike detection suppression is the most dangerous** — it means a region-wide Spot capacity failure in a specific AZ may not be detected, and the advisor continues assigning spot pods to that AZ.

---

### 23.13 — Advisor Beat Schedule Gap

**Q: Is there any guarantee that PlacementAdvisor is actually scheduled (no beat entry gap)?**

**A: No guarantee — `placement_advisor_task` has no entry in `app.conf.beat_schedule`.**

Verified in `backend/workers/app.py`:
- `placement_advisor_task` is in `app.conf.include` (imported for task registration).
- `app.conf.beat_schedule` has NO entry for `run_placement_cycle_task`.
- The task can only be triggered manually via `run_placement_cycle_task.delay(cluster_id)` or from another task.

🔴 **Critical gap.** Without a beat schedule entry, the advisor never auto-runs. PlacementPolicyRecords are never updated, `spot:placement:policy:*` keys are never written, and PlacementController processes no workloads.

---

**Q: What happens if PlacementAdvisor does not run — do `placement_policies` become permanently stale?**

**A: Yes — both Redis and DB copies go stale.**

- Redis keys `spot:placement:policy:{cluster_id}:{workload_id}` expire (TTL is cycle-based, not fixed).
- DB `placement_policies` table rows stay indefinitely but `updated_at` grows stale.
- PC `_get_actionable_workloads()` returns empty → zero evictions.
- API `/profiling-detail` returns `ondemand_target`, `spot_target`, `savings` from DB rows that reflect the last advisor run.

🔴 **Combined with the missing beat schedule, all placement-related UI metrics and automation are permanently frozen after initial data load.**

---

### 23.14 — Pricing and Savings

**Q: Are pricing values always available for savings calculation, or do we show incorrect/null savings?**

**A: Can be null — depends on pricing worker freshness.**

- `estimated_monthly_saving_usd` in `placement_policies` is computed by advisor from `AWSPricingService.get_ondemand_price()` minus spot price.
- If `spot:pricing:instance:{type}:{region}` or `spot:pricing:ondemand:{type}:{region}` Redis keys are absent, returns `0.0` or `None`.
- `consolidation_analysis_task._estimate_savings()` returns `(None, "pricing_data_pending")` if any price is missing.
- API `/profiling-detail` returns `null` if `pp` is None or `pp.estimated_monthly_saving_usd` is None.

🟡 **Savings show null or 0 until pricing worker has populated Redis.** Freshness dependency: `spot-price-ingest-every-10-mins` and `ondemand-price-refresh-12h` Celery tasks.

---

### 23.15 — pod_metrics Lag and WIE Accuracy

**Q: Does `pod_metrics` aggregation reflect real-time state or lag behind causing incorrect decisions?**

**A: Lags by agent heartbeat interval (~60s) plus any DB write latency.**

- `pod_metrics` is populated by agent heartbeat via DB write.
- API freshness is computed from `MAX(pod_metrics.timestamp)`. Stale threshold defined in `compute_freshness()`.
- Consolidation task uses 5-min window (`timedelta(minutes=5)`) for CPU utilisation — data must be fresher than 5 min or `_get_node_cpu_util()` returns `None`.
- Profiling detail uses 14-day window for timeseries.

🟡 **Decisions based on pod_metrics can be up to 60–120s behind live cluster state.** Critical for capacity checks during scaling events.

---

**Q: Can workload classification (WIE) differ from live behavior — is there any correction mechanism?**

**A: Yes, divergence is possible — correction only on next full advisor cycle (~30 min if scheduled).**

- WIE scores based on `WorkloadInput` which includes `metrics_stale_minutes`, `restart_rate_normalized`, `stable_for_minutes`.
- If a workload suddenly experiences pod crashes, the next heartbeat updates `pod_metrics`, but WIE only re-runs on the next advisor cycle.
- `workload_cv_task` updates `cpu_cv` and `traffic_skew_detected` every 10 min — provides faster correction for traffic skew.
- No real-time event hook that re-triggers WIE on crash/OOMKill events.

🟡 **Up to 30 min divergence window between actual workload instability and confidence downgrade.**

---

### 23.16 — Multiple CV Implementations

**Q: Are there multiple implementations of CV causing inconsistency between UI and decision engine?**

**A: Yes — three coexisting CV values with different scopes, storage locations, and consumers.**

| CV Implementation | Location | Period | Stored In | Used By |
|---|---|---|---|---|
| `workload_cv_task._compute_cv()` | `workload_cv_task.py` | 14-day trimmed | `workload_classifications.cpu_cv` | UI display only (no API consumer confirmed) |
| `PlacementAdvisorService._compute_cv()` | `placement_advisor_service.py` | In-cycle window | `placement_policies.pod_cpu_cv` | Advisor's `apply_traffic_skew_adjustment()` |
| `get_spot_scheduling_success_rate_blended()` | `placement_advisor_service.py` | 15m + 120m blended | Redis `spot:placement:scheduling_success:*` | Advisor spot availability factor |

- `/profiling-detail` API reads `pp.pod_cpu_cv` (advisor's live CV) — **NOT** `wc.cpu_cv` (14-day task CV).
- The 14-day `workload_classifications.cpu_cv` has no identified API consumer and is not used in placement decisions.

🟡 **The 14-day CV in `workload_classifications` appears to be a dead field** — computed every 10 min but not consumed by any API or engine path.

---

### 23.17 — Bin-Packing API Accuracy

**Q: Is the node bin-packing API based on actual cluster packing or heuristic estimation?**

**A: Based on real aggregated `pod_metrics` and `node_metadata` DB data — not a heuristic. But it lags by agent heartbeat.**

- `/optimize/nodes/bin-packing` aggregates `SUM(cpu_usage)`, `SUM(mem_usage)` etc. from `pod_metrics` per node via DB GROUP BY.
- `consolidation_candidates` count from Redis (task-computed, every 10 min).
- `lifecycle_state` computed from `is_ready`, `do_not_disrupt`, in-flight `DRAIN_NODE` actions.
- Data is as fresh as `MAX(node_metadata.updated_at)` — stale if agent is silent.

🟢 **Not a heuristic. Real DB aggregation.** Freshness is the main concern.

---

**Q: Can UI show "consolidatable=true" while Karpenter does nothing — how is this explained?**

**A: Yes — backend and Karpenter use independent consolidation evaluation.**

- Backend `consolidation_candidates` is computed by `consolidation_analysis_task` using CPU utilisation thresholds and pod fitting logic.
- Karpenter evaluates consolidation based on its own disruption budgets, `consolidation` policy in `NodePool`, and actual pod scheduling simulation.
- There is zero integration between the two. Backend candidates are a recommendation surface; Karpenter acts autonomously.

🟡 **No tracking of discrepancy.** UI may permanently show candidates that Karpenter never acts on.

---

### 23.18 — Node State Transition Tracking

**Q: Is there state transition tracking for nodes (Prepared → Empty → Consolidated) or only final state?**

**A: Only for AutoRebalancer-initiated rebalances via `rebalancing_actions` state machine. No tracking for consolidation.**

- `rebalancing_actions` table with `current_state` column tracks: `CREATED → POOL_SELECTED → SOURCE_CORDONED → SOURCE_DRAINED → REPLACEMENT_LAUNCHING → REPLACEMENT_READY → SOURCE_TERMINATING → COMPLETED/FAILED`.
- Consolidation candidate nodes have no state machine — only the Redis count is written.
- There is no `node_consolidation_state` table or Redis key tracking individual node consolidation progress.

🟡 **Consolidation is fire-and-forget from the backend perspective.**

---

### 23.19 — Error Surfacing to UI

**Q: Are failure paths (e.g., eviction blocked by PDB) surfaced to UI or silently ignored?**

**A: Yes — surfaced via decision log, but only for workloads with logs, not globally.**

- `_emit_decision_log()` writes `{action: "skip", reason: "pdb_constraint", context: {...}}` to `spot:pc:workload_log:{cluster_id}:{workload_id}` (list, last 10 entries, TTL=3600s).
- API `/workloads/{id}/placement-detail` returns `recent_decisions` from this log.
- API `/workloads/placement` returns `placement_status` = last action from log (e.g., "skip").
- Circuit breaker trips, scaling guard activations, and batch limit hits are captured in `_emit_cycle_metrics()` hash, readable from `/system/health`.

🟢 **PDB blocks, cooldowns, and scaling guards are all surfaced.** What is NOT surfaced: per-pod failure reasons from agent actuator execution, and `needs_revalidation` flag (dead field).

---

### 23.20 — End-to-End Invariant Checks

**Q: Is there any end-to-end invariant check ensuring system correctness (e.g., replicas preserved, no workload loss)?**

**A: Partial — three mechanisms provide invariant checking; no single end-to-end verifier.**

| Mechanism | What it checks | Gap |
|---|---|---|
| `PlacementAdvisor._validate_policy()` | `spot_target + ondemand_target == observed_replicas` at policy write time | Does not re-check at runtime |
| `_process_workload_inner()` last-pod guard | `total_running > 1` before any eviction | Only checks total count, not workload health |
| `handle_eviction_result()` | Verifies pod landed on correct capacity type post-eviction | K8s API errors fall back to optimistic COMPLETED |
| `reconciliation_worker` | EC2 vs DB instance state | Does not check pod-level workload completeness |

**No mechanism verifies that total running replicas = `spec.replicas` after evictions.** If eviction causes a pod to enter `CrashLoopBackOff` instead of successfully rescheduling, this is invisible to all backend components until the next WIE classification cycle.

🟠 **No end-to-end workload health invariant.** Workload loss (pod count drop below desired) is only detectable via K8s events, which the backend does not consume directly.

---

## 24. Workload Placement UI — Current State (April 2026)

> **Last audited against:** `frontend/src/pages/optimize/workloads/WorkloadPlacement.jsx` + `backend/api/optimize_routes.py`

### Page Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LEFT PANEL (52% width)          │  RIGHT DETAIL PANEL (48% width)     │
│  Workload list + header stats    │  Selected workload deep-dive         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 24.1 Left Panel — Workload List

**Data source:** `GET /api/v1/optimize/workloads/placement?cluster_id={cid}&page=1&page_size=50`

**Header stats bar (3 tiles):**

| Tile | Value | Source |
|---|---|---|
| Total Tracked | `total_count` from API | `WorkloadClassificationRecord` count |
| Drifting | Count of rows where `status != 'STABLE' && status != 'UNKNOWN'` | Computed frontend |
| Reconcile % | `(total - drifting) / total × 100` | Computed frontend |

**Cluster selector:** `useClusters()` hook auto-selects `clusters[0].id` on load. Dropdown shows `[health_score] cluster_name`.

**Workload row card** (one per workload, auto-selects first on load):

| Element | Content | Source |
|---|---|---|
| Name badge | `workload_id.split('/').pop()` (controller name) | `workload_classifications.name` |
| State badge | `placement_state` e.g. `UNKNOWN`, `DRIFTING`, `AT_TARGET` | `compute_placement_state()` |
| Namespace | `namespace` | `workload_classifications.namespace` |
| OD delta | `Δ OD: +N` shown in red when `od_excess > 0` | `current_od − ondemand_target` |
| Spot gap | `Spot behind: N/M` shown in amber when spot drift > 0 | `spot_target − current_spot` |
| Spot match | `Spot: N/M ✓` in green when `spot_drift === 0` and target not null | Computed |
| Monthly savings | `$N/mo` in green when > 0 | `placement_policies.estimated_monthly_saving_usd` |
| Bar chart | Flex-grow proportional bar: red=OD excess, gray=OD required, indigo=Spot | Pod counts |
| Bar sub-label | `OD: N/total · Spot target: M` | Computed |

**Bar color meanings:**

- 🔴 Red segment → On-Demand pods exceeding target (excess OD)  
- ⬜ Gray segment → On-Demand pods at target (base)  
- 🔵 Indigo segment → Spot pods  
- Empty bar → `bg-gray-200` placeholder when all counts null (PENDING/no data)

**Placement state badge colors:**

| State | Color |
|---|---|
| STABLE / AT_TARGET | Green |
| CONVERGING / IN_PROGRESS / RECONCILING / SCALING_UP | Blue |
| DRIFTING / DRIFT_DETECTED | Amber |
| EVICTING | Red |
| PENDING / UNKNOWN | Gray |

---

### 24.2 Right Panel — Workload Detail

Loads on workload row click via:
- `GET /api/v1/optimize/workloads/{workload_id}/placement-detail?cluster_id={cid}`
- `GET /api/v1/optimize/workloads/{workload_id}/rebalancing?cluster_id={cid}`

#### Section 1: Header Card

Shows workload name, namespace, placement state badge. If a pod is in `Terminating` phase → red **"Disruption Path Active"** badge (⚠ icon).

#### Section 2: Reconciliation Timeline

6-step linear progress bar:

```
Drift Detected → Action Queued → Eviction Triggered → Spot Scheduled → Node Provisioning → Resolved
```

- `timeline_step` (0–5) from API drives which step is active (spinning ↻) vs done (✓) vs pending (gray)
- Progress bar fills `(timeline_step / 5) × 90%` of width

#### Section 3: Eviction Risk Signal (conditional)

Appears only when a pod in `pods[]` has `phase === 'Terminating'`. Shows:
- Pod name (monospace)
- "Pod Terminating" label (red)
- "Replacement Pending" label (indigo)

#### Section 4: Topology Balance

**Data:** `detail.pods[]` → `buildAzGroups(pods)` groups by `pod.az`.

Grid of AZ cards (up to 3 columns):
- Each card shows AZ name + pod count
- Colored dots per pod: 🔵 indigo = spot, 🔴 red = on-demand, ⬜ gray = unknown
- Special case: `az === 'unknown'` → amber border + "⚠ No AZ data" label + "Node metadata pending" note

**"Rebalance AZ" button:** calls `POST /optimize/workloads/{id}/rebalance-az`. Shows success/error message inline. Disabled when no workload selected or request in-flight.

#### Section 5: Ground Truth (Pod Table)

**Data:** `detail.pods[]` — up to 12 pods shown.

Columns: Pod Name | Node Type | AZ | Status | Age

| Node Type logic | Display |
|---|---|
| `capacity_type === 'spot'` | **Spot** (indigo) |
| `capacity_type === 'on_demand' / 'on-demand' / 'ondemand'` | **On-Demand** (red) |
| `capacity_type === null / ''` | *Unknown* (gray italic) |

Status column: `Running` → green, anything else → amber.  
Age: `formatAge(age_seconds)` → `s / m / h / d / w` suffixes.

**Pod data freshness guard:** Backend only returns pods with `PodMetric.timestamp >= now - 30min`. Stale/terminated pods are excluded. `az` and `capacity_type` come from `NodeMetadata` join (outer join — may be null if node not yet in DB).

#### Section 6: Expected Optimized Placement

**Data:** `detail.pod_plan[]`, `detail.capacity_plan`, `detail.policy`

Header pills:
- **WIE badge**: `WIE: {role} ✓ Spot OK` (green) or `WIE: {role} ✗ OD Only` (red) — shown when `capacity_plan.wie_role` present
- **Simulated badge**: amber "Simulated" shown when `capacity_plan.wie_simulated && !hasPolicy`
- **OD + Spot pills**: `N OD + M Spot = total` — shown when `hasPolicy` (both targets non-null)

Body:
- **When `hasPodData` (pod_plan has entries):** shows AZ topology grid (expected distribution) + pod scoring table
- **AZ topology grid:** calls `buildExpectedAzGroups(pod_plan)` — groups pods by `pod.az`, colors by `pod.recommendation` (blue=spot, red=od, gray=skip)
- **Pod scoring table** (up to 12 rows): Pod Name | Recommendation | AZ | Spot Score | Reason

| Recommendation | Display |
|---|---|
| `'spot'` | **Spot** (indigo) |
| `'od'` | **On-Demand** (red) |
| `'skip'` (SYSTEM/non-scorable) | *Skip* (gray italic) |

Spot score coloring: ≥6 green, ≤3 red, else amber.

- **When no pod data + no policy:** "No placement policy computed yet — run advisor first" (gray italic)
- **When SYSTEM workload (all skip):** WIE badge shows `OD Only` + all pod rows show "Skip"

#### Section 7: Active Operations (conditional)

Appears when `activeOps.length > 0`. Shows active rebalancing operations:
- `current_state` (monospace)
- Scope badge: `pod-level` (indigo) or `node-level` (gray)
- `source_pool → target_pool`
- `source_instance_id` (if present)

#### Section 8: State Locks + Controller Log

Two-column grid:

**State Locks:**
| Lock | Value | Warning |
|---|---|---|
| PDB Blocked | `True` / `False` | Amber if True |
| Action Cooldown | `Active (Ns)` / `None` | Amber if active |
| In-Flight | `N Actions` | Amber if N > 0 |
| KEDA Scaling | `Active` / `None` | Amber if active |
| Rollout Blocked | `Blocked (Ns)` / `None` | Amber if blocked |

All locks read from `detail.state_locks` which is populated from individual Redis keys (NOT from agent heartbeat — see fix WP-12).

**Controller Log:** `detail.recent_decisions[]` — last 10 PlacementController decisions for this workload. Format: `HH:MM:SS — {action}`. Source: Redis `spot:pc:workload_log:{cluster_id}:{workload_id}`.

---

## 25. placement-detail Endpoint — Complete Logic

**Endpoint:** `GET /api/v1/optimize/workloads/{workload_id}/placement-detail?cluster_id={cid}`  
**File:** `backend/api/optimize_routes.py` → `get_workload_placement_detail()`

### Step 1 — Parse workload_id

`workload_id` format: `{namespace}/{controller_name}` (URL-encoded, e.g. `karpenter%2Fkarpenter`).

```python
workload_name = workload_id.split('/')[-1]
workload_namespace = '/'.join(workload_id.split('/')[:-1])
```

### Step 2 — State Locks (7 real Redis checks)

| Lock Field | Redis Key | Logic |
|---|---|---|
| `cooldown_active` | `spot:placement_controller:cooldown:{cid}:{wid}` | TTL exists → True |
| `cooldown_expires_in` | same key | `redis.ttl()` → seconds remaining |
| `rollout_blocked` | `spot:placement:rollout_blocked:{cid}:{wid}` | TTL exists → True |
| `rollout_blocked_expires_in` | same key | `redis.ttl()` → seconds remaining |
| `keda_scaling_active` | `spot:keda:last_scale_event:{cid}` | Timestamp delta < 120s |
| `pdb_active` | `spot:workload:state:{cid}:{wid}` → `has_pdb` | From agent heartbeat |
| `in_flight_actions` | `AgentAction` DB table | Count PENDING/PICKED_UP EVICT_POD for workload |

### Step 3 — Policy (3-tier lookup)

```
1. Redis: spot:placement:policy:{cid}:{wid}  (TTL ~600s, written by PlacementAdvisor)
2. DB fallback: PlacementPolicyRecord WHERE (cluster_id, workload_id)
3. Frontend fallback: policy.ondemand_target ?? w?.od_required (list-row data)
```

Returns: `{ ondemand_target, spot_target, rollout_eligible, actionability_reason, ... }`

### Step 4 — Pod Query (30-min freshness filter)

```python
latest_subq = db.query(
    PodMetric.pod_name, PodMetric.node_name, PodMetric.phase,
    PodMetric.start_time, PodMetric.timestamp,
    PodMetric.cpu_request_millicores, PodMetric.memory_request_bytes,
    PodMetric.namespace, PodMetric.controller_kind,
)
.filter(
    PodMetric.cluster_id == cluster_id,
    PodMetric.controller_name == workload_name,
    PodMetric.timestamp >= utcnow() - timedelta(minutes=30),  # ← freshness guard
)
.distinct(PodMetric.pod_name)
.order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
.subquery()
```

Joined with `NodeMetadata` (outer join) on `(cluster_id, node_name)` to get `az` and `capacity_type`.

Each pod row becomes:
```python
{
    'name': pod_name,
    'node_name': node_name,
    'phase': phase,
    'az': az,                         # from NodeMetadata, may be None
    'capacity_type': capacity_type,   # from NodeMetadata, may be None
    'age_seconds': (now - start_time).total_seconds(),
    'cpu_request_millicores': ...,
    'memory_request_bytes': ...,
    'namespace': namespace,
    'controller_kind': controller_kind,
}
```

### Step 5 — WIE Classification Lookup

```python
_wie_key = f"spot:wie:classification:{cluster_id}:{workload_id}"
_wie = redis.get(_wie_key) → JSON → {
    'role': 'SYSTEM'|'CONTROL_PLANE'|'APPLICATION',
    'spot_friendly': bool,
    'spot_score': 0-10,
    'tier': 'Platinum'|'Gold'|'Silver'|'Bronze',
    'confidence_state': 'DRAFT'|'PROVISIONAL'|'CONFIRMED',
}
```

Fallback: DB `WorkloadClassificationRecord` if Redis miss.

### Step 6 — Effective Spot Target (`_eff_spot_tgt`)

```
Source priority:
  1. policy.spot_target  (from PlacementAdvisor via Redis/DB)
  2. Simulated from WIE:
     - wie.spot_friendly=True  → _eff_spot_tgt = max(0, total_pods - od_floor)
     - wie.spot_friendly=False → _eff_spot_tgt = 0  (all OD)
     - wie not available       → None (handled in scoring)
```

Effective spot count after safety gate:
```python
_eff_spot = min(_eff_spot_tgt, len(_scorable))
# If no policy AND no WIE → simulate conservatively: _eff_spot = max(0, len(_scorable) - 1)
```

### Step 7 — Pod Scoring Loop

For each pod, `_spot_score(pod)` returns `(score: int|None, reason: str)`:

```
None   → pod is SYSTEM/non-scorable (goes to _skipped list)
0–10   → spot eligibility score
```

**Score = 0 baseline, then adjustments:**

| Condition | Δ Score | Tag |
|---|---|---|
| `wie.spot_friendly == False` | → return `None` (skip entirely) | system |
| `capacity_type == 'spot'` (already spot) | `+3` | already_spot |
| `phase == 'Terminating'` | `−3` | terminating |
| `age_seconds > 86400` (>24h old) | `+2` | stable |
| `age_seconds < 300` (<5min old, new pod) | `−2` | new_pod |
| `cpu_request_millicores <= 500` (low CPU) | `+1` | low_cpu |
| `wie.spot_score >= 7` | `+1` | wie_high |
| `wie.spot_score <= 3` | `−1` | wie_low |

**Score = None triggers:** `wie.spot_friendly == False` (role=SYSTEM/CONTROL_PLANE or spot_friendly=False from WIE).

### Step 8 — pod_plan Construction

```python
_scorable.sort(key=lambda x: x['spot_score'], reverse=True)  # highest score → spot first

pod_plan = []
for i, p in enumerate(_scorable):
    pod_plan.append({
        **p,
        'recommendation': 'spot' if i < _eff_spot else 'od'
    })
pod_plan.extend({**p, 'recommendation': 'skip'} for p in _skipped)
```

Result: every pod in `pod_plan` has `recommendation` ∈ `{'spot', 'od', 'skip'}`.

### Step 9 — capacity_plan

Aggregated from `pod_plan`:

```python
capacity_plan = {
    'total_cpu_spot_millicores': sum(spot pods cpu_request),
    'total_memory_spot_bytes':   sum(spot pods memory_request),
    'total_cpu_od_millicores':   sum(od pods cpu_request),
    'total_memory_od_bytes':     sum(od pods memory_request),
    'spot_pod_count':    len(spot pods),
    'od_pod_count':      len(od pods),
    'skipped_pod_count': len(skip pods),
    'wie_simulated':     bool,   # True when spot_target came from WIE simulation not real policy
    'wie_spot_friendly': bool,   # from WIE classification
    'wie_role':          str,    # 'SYSTEM' | 'APPLICATION' | 'CONTROL_PLANE' | None
}
```

### Step 10 — topology_constraints

```python
_active_pods = [p for p in pod_plan if p['recommendation'] != 'skip']
topology_constraints = {
    'distinct_nodes': len({p['node_name'] for p in _active_pods if p.get('node_name')}),
    'distinct_azs':   len({p['az'] for p in _active_pods if p.get('az') and p['az'] != 'unknown'}),
    'min_nodes_ok':   distinct_nodes >= 2,
    'az_spread_ok':   distinct_azs >= 2 or len(_active_pods) <= 1,
    'anti_affinity_ok': distinct_nodes >= 2 or len(_active_pods) <= 1,
}
```

### Full Response Shape

```json
{
  "cluster_id": "...",
  "workload_id": "namespace/controller",
  "state_locks": {
    "cooldown_active": false,
    "cooldown_expires_in": 0,
    "rollout_blocked": false,
    "rollout_blocked_expires_in": 0,
    "keda_scaling_active": false,
    "pdb_active": false,
    "in_flight_actions": 0
  },
  "policy": {
    "ondemand_target": 2,
    "spot_target": 3,
    "rollout_eligible": true,
    "actionability_reason": "..."
  },
  "pods": [
    {
      "name": "pod-abc-xyz",
      "node_name": "ip-10-0-1-5...",
      "phase": "Running",
      "az": "ap-south-1a",
      "capacity_type": "spot",
      "age_seconds": 172800,
      "cpu_request_millicores": 250,
      "memory_request_bytes": 268435456
    }
  ],
  "pod_plan": [
    {
      "name": "pod-abc-xyz",
      "recommendation": "spot",
      "spot_score": 5,
      "reason": "already_spot,stable",
      "az": "ap-south-1a",
      ...
    }
  ],
  "capacity_plan": {
    "spot_pod_count": 3,
    "od_pod_count": 2,
    "skipped_pod_count": 0,
    "wie_simulated": false,
    "wie_spot_friendly": true,
    "wie_role": "APPLICATION"
  },
  "topology_constraints": {
    "distinct_nodes": 3,
    "distinct_azs": 2,
    "min_nodes_ok": true,
    "az_spread_ok": true,
    "anti_affinity_ok": true
  },
  "recent_decisions": [
    { "timestamp": "2026-04-29T10:00:00Z", "action": "skip", "reason": "cooldown_active" }
  ],
  "data_ready": true,
  "data_age_seconds": 45
}
```

---

## 26. placement list Endpoint — Complete Logic

**Endpoint:** `GET /api/v1/optimize/workloads/placement?cluster_id={cid}&page=1&page_size=50`  
**File:** `backend/api/optimize_routes.py` → `get_workloads_placement()` → `_get_placement_workload_rows()`

### Per-Workload Row Construction

For each `WorkloadClassificationRecord` in the cluster:

```
1. Load Redis state:   spot:workload:state:{cid}:{wid}
   → current_spot_pods, current_ondemand_pods, has_pdb
   → DB fallback when key absent: query PodMetric + NodeMetadata

2. Load policy:        spot:placement:policy:{cid}:{wid}
   → ondemand_target, spot_target
   → DB fallback: PlacementPolicyRecord

3. Load decision log:  spot:pc:workload_log:{cid}:{wid}
   → latest entry for timeline_step and placement_status

4. Compute:
   od_excess      = max(0, current_ondemand_pods - ondemand_target)
   od_required    = ondemand_target
   spot_count     = current_spot_pods
   placement_state = compute_placement_state(current_od, ondemand_target, last_action)
   timeline_step  = derive_timeline_step(last_action_type, placement_state)
```

### `compute_placement_state()` Logic

```python
def compute_placement_state(current_od, ondemand_target, last_action):
    if current_od is None or ondemand_target is None:
        return 'UNKNOWN'
    delta = abs(current_od - ondemand_target)
    if delta == 0:
        return 'AT_TARGET'          # perfectly at policy
    if delta <= 1:
        return 'STABLE'             # within tolerance
    if last_action == 'evict':
        return 'EVICTING'           # active eviction
    if current_od > ondemand_target:
        return 'DRIFTING'           # too many OD pods
    return 'CONVERGING'             # moving toward target
```

### Timeline Step Mapping

| `last_action` value | `timeline_step` |
|---|---|
| None / no log | `0` (Drift Detected) |
| `skip` | `0` |
| `queue` | `1` (Action Queued) |
| `evict` | `2` (Eviction Triggered) |
| `completed` | `5` (Resolved) |
| `failed` | `0` (reset) |

---

## 27. Recent Bug Fixes — Current Status

*All fixes applied to `backend/api/optimize_routes.py` and `frontend/src/pages/optimize/workloads/WorkloadPlacement.jsx`*

### WP-9 (Fixed): Stale pods → "unknown" AZ card

**Root cause:** No timestamp filter on `PodMetric` subquery — terminated pods from weeks ago were returned.  
**Fix:** Added `PodMetric.timestamp >= utcnow() - 30min` filter.  
**Frontend:** `unknown` AZ renders amber warning card instead of appearing as a real AZ.

### WP-10 (Fixed): Bar chart rounding gap

**Root cause:** `Math.round(N/total × 100)` per segment → segments summed to 99%.  
**Fix:** Switched to `style={{ flexGrow: podCount }}` — browser distributes proportionally, no rounding.

### WP-11 (Fixed): null `capacity_type` shown as "On-Demand"

**Root cause:** `isOD = !isSpot` treated null as On-Demand.  
**Fix:** Three-way branch: `spot` → Spot (indigo), `on_demand/on-demand` → On-Demand (red), anything else → Unknown (gray).

### WP-12 (Fixed): State Locks always show False

**Root cause:** `placement-detail` read `state_locks` from `spot:workload:state` (agent heartbeat) which never contains lock keys.  
**Fix:** Replaced with 7 individual Redis TTL/value checks matching real lock key patterns. Added `cooldown_expires_in` and `rollout_blocked_expires_in` to response.

### WP-13 (Fixed): Expected Placement blank — "No policy computed"

**Root cause:** Endpoint read `ondemand_target` from agent heartbeat key (which never contains it). Should read from `spot:placement:policy:{cid}:{wid}`.  
**Fix:** 3-tier policy lookup: Redis policy key → DB PlacementPolicyRecord → frontend fallback.

### WP-14 (Fixed): placement-detail 500 — `KeyError: 'recommendation'`

**Root cause:** `_skipped` pods extended into `pod_plan` without `'recommendation'` key. Line 1868 then did `_p['recommendation']` → `KeyError`.  
**Fix:** Changed `pod_plan.extend(_skipped)` to `pod_plan.extend({**_p, 'recommendation': 'skip'} for _p in _skipped)`.  
**Impact:** All 16 workloads now return 200. SYSTEM workloads correctly show all pods as `recommendation: 'skip'` with `capacity_plan.wie_role: 'SYSTEM'`.

### WP-15 (Fixed): Pod scoring ignores WIE — all pods shown as spot-eligible

**Root cause:** `_spot_score()` had no WIE lookup; any pod could score positively regardless of role.  
**Fix:** Added Redis `spot:wie:classification:{cid}:{wid}` lookup at start of `_spot_score()`. `wie.spot_friendly == False` → return `None` (add to `_skipped`, recommendation = `'skip'`). Also gated `_eff_spot_tgt` on WIE eligibility.

### WP-16 (Fixed): `UnboundLocalError: spot_tgt` in pod scoring

**Root cause:** `spot_tgt` used before assignment when `policy_summary` was empty.  
**Fix:** Moved policy lookup block above the pod scoring section so `spot_tgt` is always defined.

### WP-17 (Fixed): New pod false negative on age check

**Root cause:** `age_seconds` could be `None` when `start_time` was null. `age_seconds < 300` on `None` raised TypeError.  
**Fix:** Added null guard: `age_seconds = (now - start_time).total_seconds() if start_time else None`. Scoring skips the age penalty when `age_seconds is None`.

---

## 28. System Data Flow — Current End-to-End (April 2026)

```
K8s Agent DaemonSet (every 60s)
  │  POST /api/v1/agent/{cid}/heartbeat
  │  Writes: pod_metrics, node_metadata, workload state
  ▼
PostgreSQL Tables:
  pod_metrics        → phase, cpu, memory, start_time, controller_name, namespace
  node_metadata      → az, capacity_type, instance_type, nodepool_name
  workload_classifications → tier, spot_score, confidence_state, spot_friendly
  placement_policies → ondemand_target, spot_target, estimated_savings

Redis Keys:
  spot:workload:state:{cid}:{wid}     (TTL 300s) ← agent heartbeat only
  spot:placement:policy:{cid}:{wid}   (TTL 600s) ← PlacementAdvisor
  spot:wie:classification:{cid}:{wid} (TTL 3600s) ← WIE advisor cycle
  spot:pc:workload_log:{cid}:{wid}    (TTL 3600s) ← PlacementController
  spot:placement_controller:cooldown:{cid}:{wid}  ← PC post-eviction
  spot:keda:last_scale_event:{cid}               ← KEDA service

                    │
                    ▼
API Request: GET /optimize/workloads/placement?cluster_id={cid}
  _get_placement_workload_rows():
    For each WorkloadClassificationRecord:
      ├─ Redis: spot:workload:state → current_spot/od (DB fallback if miss)
      ├─ Redis: spot:placement:policy → ondemand_target/spot_target (DB fallback)
      ├─ Redis: spot:pc:workload_log → timeline_step, last_action
      └─ Compute: placement_state, od_excess, spot_drift
  Returns paginated workload list (16 workloads on demo cluster)

                    │
                    ▼ (on workload row click)
API Request: GET /optimize/workloads/{wid}/placement-detail?cluster_id={cid}
  1. State Locks:  7 Redis key TTL checks (real lock state, not agent heartbeat)
  2. Policy:       Redis → DB fallback (ondemand_target, spot_target)
  3. Pod Query:    PodMetric JOIN NodeMetadata (30-min freshness filter)
  4. WIE Lookup:   Redis spot:wie:classification (role, spot_friendly, spot_score)
  5. Pod Scoring:  _spot_score() per pod → (score, reason) or None for SYSTEM
  6. pod_plan:     Sort scorable by score desc → assign 'spot'/'od'/'skip'
  7. capacity_plan: Aggregate CPU/mem by recommendation type
  8. topology_constraints: distinct_nodes, distinct_azs spread checks
  9. recent_decisions: Redis workload log last 10 entries
  Returns full detail JSON

                    │
                    ▼
UI Renders:
  Left:  16 workload cards with state badges + proportional bars
  Right: 8 sections (header, timeline, topology, ground truth, expected,
                      active ops, state locks, controller log)
```

### Current Demo Cluster State (as of April 2026)

| Metric | Value |
|---|---|
| Total workloads tracked | 16 |
| All placement states | UNKNOWN (no agent heartbeat producing live pod counts yet) |
| WIE role of most workloads | SYSTEM (karpenter, argocd, spot-optimizer namespaces) |
| placement-detail | Returns 200 for all 16 workloads |
| pod_plan recommendation for SYSTEM workloads | All `skip` |
| capacity_plan.wie_role | `SYSTEM` for system NS workloads |
| State locks | All showing correct values (cooldown=false, in_flight=0) |
