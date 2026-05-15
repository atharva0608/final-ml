# Workload Inventory + Workload Identification Engine (WIE v4.3) — End-to-End Deep Dive

This document explains **how the Workload Inventory UI** and the **Workload Identification Engine (WIE v4.3)** work end-to-end: logic, inputs, sources, outputs, algorithms, DB operations, Redis operations, and exactly how data flows to/from the UI.

Primary code references:
- **UI**: [`WorkloadInventoryDashboard.jsx`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/frontend/src/components/right-sizing/WorkloadInventoryDashboard.jsx) (1033 lines)
- **Frontend API client**: [`api.js`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/frontend/src/services/api.js#L677-L740) (`workloadClassificationAPI`, lines 677–740)
- **API routes**: [`workload_classification_routes.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py) (715 lines)
- **Engine**: [`workload_identification_engine.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py) (2732 lines)
- **DB model**: [`workload_classification.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/models/workload_classification.py) (116 lines)
- **Pydantic schemas**: [`workload_classification_schemas.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/schemas/workload_classification_schemas.py) (231 lines)
- **Pod metric model**: [`pod_metric.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/models/pod_metric.py) (124 lines)
- **Node/workload inspector**: [`workload_inspector.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_inspector.py) (separate tier system)
- **Classifier**: [`workload_classifier.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_classifier.py) (separate tier system)
- **Scheduler**: [`scheduler.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/scheduler.py) (272 lines)

---

## Logic (what it does)

### What the "Workload Inventory" section is
- **Workload Inventory** is the UI surface that shows **per-workload classification records** produced by **WIE v4.3**.
- WIE produces (defined in [`WorkloadClassification` dataclass, line 199](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L199-L236)):
  - **role**: `SYSTEM | CONTROL_PLANE | APPLICATION`
  - **tier**: `Platinum | Gold | Silver | Bronze` (derived from criticality score via [`criticality_to_tier()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L242-L254))
  - **criticality_score**: 0–10
  - **spot_score**: 0–10
  - **spot_friendly**: boolean (computed via [`is_spot_friendly()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L720-L732): `spot_score >= 4 AND has_pdb AND replicas >= 2`)
  - **confidence_score**: 1–10 and **confidence_state**: `DRAFT | PROVISIONAL | CONFIRMED`
  - **data_safety**: `STATEFUL | CACHE | EPHEMERAL` (computed via [`determine_data_safety()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L261-L289))
  - **signals_fired**: `List[str]` explaining why the scores are what they are
  - **input_hash**: `sha256:<hex>` content fingerprint for change detection / write suppression (via [`compute_input_hash()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L377-L400))

### WIE execution model (two loops)
WIE is a deterministic, non-ML scoring engine that runs continuously in two loops:

- **Fast loop (every 2 minutes)**: updates *pod state cache* in Redis (no scoring, no DB writes).
  - Scheduler entry: [`job_wie_fast_loop()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/scheduler.py#L163-L182)
  - Engine entry: [`WorkloadIdentificationEngine.fast_loop_update(cluster_id)`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L2650-L2716)
  - Queries `PodMetric` rows from the last 5 minutes (cutoff at line 2659)
  - Groups by `{namespace}/{controller_name}` and computes per-workload: `ready_count`, `pending_count`, `total_count`, `zones` (derived from `node_name`)
  - Output: Redis keys `spot:wie:pod_state:{cluster_id}:{ns}/{controller}` (TTL 300s)

- **Slow loop (every 10 minutes)**: full classification cycle for all workloads in a cluster.
  - Scheduler entry: [`job_scan_clusters()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/scheduler.py#L57-L94) (lines 78–89)
  - Engine entry: [`WorkloadIdentificationEngine.slow_loop_classify(cluster_id)`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L2114-L2231)
  - Steps:
    1. Circuit breaker check ([`EngineCircuitBreaker.is_tripped()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1458-L1459))
    2. Snapshot pod_state from Redis ([`_snapshot_pod_states()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1965-L1996))
    3. Load engine age + system namespaces
    4. Collect workloads ([`_collect_workloads()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L2409-L2646))
    5. Load prev scores for evaluation order ([`get_prev_scores()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L831-L867))
    6. Classify each workload ([`classify_workload()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1724-L1827))
    7. Write to DB ([`_write_to_db()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L2254-L2367)) + Redis ([`_write_to_redis()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L2233-L2252))
    8. Cleanup stale classifications ([`_cleanup_stale_classifications()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L2369-L2407))
    9. Emit metrics ([`_collect_and_emit_metrics()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L2032-L2094))

---

## Inputs (what WIE needs) and where they come from

WIE's scoring is driven by a [`WorkloadInput` dataclass](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L109-L193) (46 fields).

### Primary data source: Pod metrics stored in Postgres
WIE slow loop collects workloads from the `pod_metrics` table via [`PodMetric` ORM model](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/models/pod_metric.py#L19-L82):
- [`_collect_workloads()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L2409-L2646) queries `PodMetric` rows from the last 10 minutes (cutoff at line 2423).
- If no fresh data exists (line 2436), it falls back to the most recent window around `max(PodMetric.timestamp)`.

The engine aggregates `PodMetric` fields per controller (namespace + controller_kind + controller_name). From `PodMetric` it extracts:
- **Identity**: `namespace`, `controller_kind`, `controller_name` (→ `workload_id = "{ns}/{name}"`)
- **Replicas**: count of distinct `pod_name` records (line 2560)
- **Ready count**: from pod_state cache or by counting pods with `phase == "Running"` in `pod_metadata` (lines 2561–2568)
- **pod_metadata** (JSONB column, line 64 of `pod_metric.py`), parsed for:
  - `labels` → `owner_labels`
  - `has_pvc` → persistent volume attachment
  - `has_pdb` → PDB presence (any pod reporting `has_pdb = True` means workload has PDB, line 2534)
  - `readiness_initial_delay_s` → readiness probe delay
  - `__scheduling` nested map → `has_topology_spread`, `has_pod_anti_affinity`
  - `affinity.podAntiAffinity` → is also checked for anti-affinity (line 2547–2550)
  - `phase` → pod phase for ready count
- **Workload age**: computed from `min(PodMetric.timestamp)` for this workload (lines 2593–2605)
- **Metrics staleness**: `datetime.now(UTC) - latest_ts` in minutes (lines 2608–2612)

**Where `pod_metrics` comes from**
- The Kubernetes agent scrapes node/pod stats and POSTs batches to backend ingestion endpoints (not part of WIE itself).
- WIE is *downstream* from the ingestion path: it relies on `pod_metrics` being populated.
- `PodMetric` table has indexes at [`__table_args__`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/models/pod_metric.py#L70-L82): `idx_pod_metric_cluster_time`, `idx_pod_metric_controller`, `idx_pod_metric_node_time`, `idx_pod_metric_pod_time`.

### Secondary data source: pod_state cache in Redis
WIE fast loop builds a lightweight per-workload "pod state" document (lines 2699–2706):
```json
{
  "restart_count": 0,
  "ready_count": 3,
  "pending_count": 0,
  "total_count": 3,
  "zones": ["ip-10-0-1-42.ec2.internal", "ip-10-0-2-15.ec2.internal"],
  "last_updated": "2026-04-21T09:15:00+00:00"
}
```

The slow loop snapshots these keys at the start of a cycle using:
- [`_snapshot_pod_states(cluster_id, redis)`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1965-L1996)
  - Reads all `spot:wie:pod_state:{cluster_id}:*` keys in a single pipeline call
  - Validates schema via [`validate_pod_state()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1706-L1717), deep-copies values for cycle consistency

### Overrides input (operator intent)
Overrides can come from:
- **Redis override** (set via API; highest priority):
  - Key: `spot:wie:override:{cluster_id}:{workload_id}` (via [`wie_override_key()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L442-L443))
  - Written by API endpoint: `POST /api/v1/workload-classification/{cluster_id}/workloads/{workload_id}/override` ([line 460](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L460-L584))
  - Loaded by: [`_load_override()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L939-L960) — includes `expires_at` TTL check
- **Kubernetes annotations** (lower priority):
  - Keys defined in [`OVERRIDE_ANNOTATIONS`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L932-L936):
    - `aura.io/spot-override` → `"true" | "false"`
    - `aura.io/tier-override` → `Platinum | Gold | Silver | Bronze`
    - `aura.io/role-override` → `APPLICATION` (only allowed override)

Overrides are applied **inside the classification pipeline** via [`apply_overrides()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L990-L1056), but only in `mode="production"` (simulation explicitly skips overrides at line 1003).

### System namespace overrides (classification boundary)
The API supports per-cluster system namespace override:
- `PUT /api/v1/workload-classification/{cluster_id}/system-namespaces` ([line 624](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L624-L679))
- Stored in Redis at `spot:wie:system_namespaces:{cluster_id}` (TTL 3600s, line 662)
- The engine reads system namespace set via [`get_system_namespaces(cluster_id, redis)`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L474-L486)
- Default system namespaces ([`DEFAULT_SYSTEM_NAMESPACES`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L59-L63)): `kube-system, kube-public, kube-node-lease, karpenter, spot-optimizer, cert-manager, monitoring, istio-system, linkerd`
- The GET endpoint at line 682 has a **slightly different** default list that adds `ingress-nginx, logging, flux-system, argocd` — this is the route-level default, while the engine uses the frozenset above.

---

## Outputs (what it produces) and where they go

### 1) Postgres (persistent truth for the UI)
Table: `workload_classifications` (model: [`WorkloadClassificationRecord`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/models/workload_classification.py#L32-L115))

Stored per workload (unique on `(cluster_id, workload_id)` via [`uq_workload_classification_cluster_workload`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/models/workload_classification.py#L93-L96)):

| Column | Type | Description |
|--------|------|-------------|
| `id` | `String(36)` | UUID primary key |
| `cluster_id` | `String(36)` | FK → `clusters.id` (CASCADE delete) |
| `workload_id` | `String(512)` | `"namespace/name"` |
| `namespace` | `String(253)` | K8s namespace |
| `name` | `String(253)` | Controller name |
| `controller_kind` | `String(50)` | Deployment / StatefulSet / DaemonSet / Job / CronJob |
| `role` | `String(20)` | `SYSTEM / CONTROL_PLANE / APPLICATION` |
| `criticality_score` | `Integer` | 0–10 |
| `tier` | `String(20)` | `Platinum / Gold / Silver / Bronze` |
| `spot_score` | `Integer` | 0–10 |
| `spot_friendly` | `Boolean` | Computed suitability |
| `confidence_score` | `Integer` | 1–10 |
| `confidence_state` | `String(20)` | `DRAFT / PROVISIONAL / CONFIRMED` |
| `data_safety` | `String(20)` | `STATEFUL / CACHE / EPHEMERAL` |
| `signals_fired` | `JSONB` | List of signal strings |
| `override_active` | `Boolean` | Whether an override is applied |
| `override_reason` | `String(512)` | Nullable override reason |
| `input_hash` | `String(100)` | `sha256:<hex>` fingerprint |
| `schema_version` | `String(10)` | Always `"4.3"` |
| `classified_at` | `DateTime` | UTC timestamp of classification |
| `created_at` | `DateTime` | Record creation time |
| `updated_at` | `DateTime` | Last update (auto via `onupdate`) |

**Indexes** (lines 91–105):
- `ix_wc_cluster_tier` — `(cluster_id, tier)`
- `ix_wc_cluster_confidence` — `(cluster_id, confidence_state)`
- `ix_wc_cluster_spot` — `(cluster_id, spot_friendly, confidence_state)`
- `ix_wc_workload_id` — `(workload_id)`

### 2) Redis (fast-read cache + engine health)
WIE writes several Redis keys (key helpers at [lines 434–468](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L434-L468)):

| Key Pattern | TTL | Written By | Purpose |
|-------------|-----|------------|---------|
| `spot:wie:classification:{cluster_id}:{ns}/{ctrl}` | 900s | `_write_to_redis()` | Per-workload classification cache |
| `spot:wie:pod_state:{cluster_id}:{ns}/{ctrl}` | 300s | `fast_loop_update()` | Pod state (ready/pending/zones) |
| `spot:wie:metrics:{cluster_id}` | 3600s | `_collect_and_emit_metrics()` | Engine health HASH |
| `spot:wie:override:{cluster_id}:{workload_id}` | Optional | API route `POST /override` | Operator override JSON |
| `spot:wie:engine_age:{cluster_id}` | None | `get_cluster_engine_age_hours()` (SETNX) | First-observation timestamp |
| `spot:wie:prev_scores:{cluster_id}` | 900s | `slow_loop_classify()` | Previous criticality scores for ordering |
| `spot:wie:circuit_breaker:{cluster_id}` | 600s | `EngineCircuitBreaker.check_and_trip()` | Circuit breaker flag |
| `spot:wie:debounce:{cluster_id}:{workload_id}` | 15–30s | `EventDebouncer.should_process()` | Per-workload debounce window |
| `spot:wie:rate_limit:{cluster_id}` | 60s | `ClusterRateLimiter.is_allowed()` | Per-cluster task rate cap |
| `spot:wie:system_namespaces:{cluster_id}` | 3600s | API route `PUT /system-namespaces` | Per-cluster namespace override |
| `spot:wie:metrics:{cluster_id}:scan_total` | None | `_collect_and_emit_metrics()` (INCR) | Cumulative scan counter |
| `spot:restart_baseline:{cluster_id}:{kind}` | 3600s | `update_restart_baselines()` | Restart rate baseline per controller kind |

### 3) API responses (what the UI consumes)
Endpoints (prefix: `/api/v1/workload-classification`, router at [line 49](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L49-L52)):

#### `GET /{cluster_id}/summary` ([line 129](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L129-L198))
- Response model: [`ClusterClassificationSummary`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/schemas/workload_classification_schemas.py#L69-L92)
- Aggregates counts by tier/confidence/role from **Postgres** (`db.query(WorkloadClassificationRecord).filter_by(cluster_id=...)`)
- Computes `spot_friendly_count`, `spot_friendly_pct`, `spot_ready_count` (CONFIRMED + spot_friendly)
- Pulls `last_scan_at` and `engine_age_hours` from Redis HASH `spot:wie:metrics:{cluster_id}`

#### `GET /{cluster_id}/workloads` ([line 205](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L205-L270))
- Response model: [`WorkloadClassificationListResponse`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/schemas/workload_classification_schemas.py#L57-L62)
- Filters: `namespace`, `tier`, `confidence_state`, `spot_friendly`, `role`, `search` (ILIKE on name and namespace)
- Pagination: `page` + `page_size` (max 200 per request, default 50)
- Order: `criticality_score DESC`
- Each record → `_classification_to_response()` → `sanitize_classification_output()` → `WorkloadClassificationResponse`

#### `GET /{cluster_id}/workloads/{workload_id}` ([line 277](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L277-L312))
- Response model: [`WorkloadClassificationDetail`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/schemas/workload_classification_schemas.py#L112-L115) — includes `classification` + `scoring_breakdown`
- `scoring_breakdown` is reconstructed from `signals_fired` via [`_build_scoring_breakdown()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L91-L122) — partitions signals into: `role_signals`, `criticality_signals`, `spot_signals`, `confidence_signals`, `override_signals`

#### `GET /{cluster_id}/spot-candidates` ([line 319](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L319-L387))
- Response model: [`SpotCandidatesResponse`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/schemas/workload_classification_schemas.py#L221-L231)
- Returns **two sets** (plus defense-in-depth re-sanitization):
  - `safe_candidates`: `confidence_state="CONFIRMED"` and `spot_friendly=True` (automation-allowed set)
  - `potential_candidates`: `confidence_state="PROVISIONAL"` and `spot_friendly=True` (visibility-only set)
- Each candidate goes through `sanitize_classification_output()` and is re-validated post-sanitization (lines 355–376)

#### `GET /{cluster_id}/metrics` ([line 394](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L394-L453))
- Response model: [`EngineMetricsResponse`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/schemas/workload_classification_schemas.py#L122-L145)
- Reads Redis HASH `spot:wie:metrics:{cluster_id}` and returns: `scan_count`, `last_scan_at`, `last_scan_duration_ms`, `total_workloads`, `confirmed_count`, `provisional_count`, `draft_count`, `spot_friendly_count`, `spot_friendly_pct`, `db_writes`, `db_suppressed`, `suppress_rate`, `debounce_drops`, `rate_limit_drops`, `error_count`, `signal_freq`, `engine_age_hours`, `enforcement_enabled`

#### `POST /{cluster_id}/workloads/{workload_id}/override` ([line 460](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L460-L584))
- Request model: [`OverrideRequest`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/schemas/workload_classification_schemas.py#L152-L181) — fields: `spot_override` (bool), `tier_override` (string, validated: Platinum/Gold/Silver/Bronze), `reason` (max 512 chars), `expires_hours` (1–720)
- Pre-validates safety via [`_validate_override_safety()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L963-L987) — returns 422 with `rejection_reason` if unsafe
- Stores override JSON in Redis via `setex()` (if `expires_hours`) or `set()` (permanent)
- Takes effect on next slow loop cycle (up to ~10 minutes)

#### `DELETE /{cluster_id}/workloads/{workload_id}/override` ([line 591](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L591-L614))
- Deletes Redis override key; effect on next slow loop cycle

#### `PUT /{cluster_id}/system-namespaces` ([line 624](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L624-L679))
- Request: `{ "add": [...], "remove": [...] }`
- Merges with existing override in Redis, validates no conflicts (cannot add+remove same namespace)
- Best-effort persistence to `ClusterOptimizationSettings.system_namespace_overrides` in DB

#### `GET /{cluster_id}/system-namespaces` ([line 682](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/api/workload_classification_routes.py#L682-L714))
- Returns `{ defaults, override, effective }` — effective is defaults + adds - removes

---

## Scheduling (where/when it runs)

### Background scheduler integration

The platform runs WIE from the [`BackgroundScheduler`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/scheduler.py#L20) in `backend/scheduler.py`. All jobs are delayed 60s after startup (line 198).

#### Every 10 minutes: `job_scan_clusters()` ([line 57](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/scheduler.py#L57-L94))
For each active cluster (with random 0–10s jitter per cluster):
1. `WorkloadInspector.scan_cluster(cluster.id)` — node-level stateful/stateless classification
2. `WorkloadInspector.build_all_profiles_for_cluster(cluster.id)` — per-controller profile + misconfig recs
3. **WIE slow loop** (lines 78–89):
   ```python
   engine = WorkloadIdentificationEngine(redis=redis_client, db=db, k8s_client=None)
   engine.slow_loop_classify(cluster_id=cluster.id)
   ```
   - Registered as scheduler job `"scan_clusters"` with `IntervalTrigger(minutes=10)` (line 219)
   - First run at `startup + 60s + 10s` (line 224)

#### Every 2 minutes: `job_wie_fast_loop()` ([line 163](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/scheduler.py#L163-L182))
For each active cluster:
```python
engine = WorkloadIdentificationEngine(redis=redis_client, db=db, k8s_client=None)
engine.fast_loop_update(cluster_id=cluster.id)
```
- Registered as job `"wie_fast_loop"` with `IntervalTrigger(minutes=2)`, `max_instances=1` (lines 254–261)
- First run at `startup + 60s + 40s` (line 260)

**Key operational note**: In the scheduler, `k8s_client=None` is always passed (lines 83, 174). WIE therefore operates exclusively from **pod_metrics DB** and **pod_state Redis** data. The [`_fetch_pod_state_direct()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L2718-L2732) live K8s fallback is a TODO stub (line 2729).

---

## UI behavior (inputs → API calls → rendered output)

### Where the Workload Inventory screen is mounted
- `RightSizingDashboard.jsx` imports `WorkloadInventoryDashboard` at [line 7](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/frontend/src/components/right-sizing/RightSizingDashboard.jsx#L7)
- Renders `<WorkloadInventoryDashboard clusterId={selectedClusterId} />` when `activeTab === 'workload'` at [line 1384–1385](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/frontend/src/components/right-sizing/RightSizingDashboard.jsx#L1384-L1385)

### Main component structure ([`WorkloadInventoryDashboard`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/frontend/src/components/right-sizing/WorkloadInventoryDashboard.jsx#L928-L1032))
- Root component manages `activeView` state: `"inventory"` or `"detail"`
- Shows "WIE v4.3" badge (line 972)
- **Observation Mode Banner** (lines 977–1021): displayed when `enforcement_enabled === false` — shows engine age, classifier disagreements, CONFIRMED rate

### What the UI calls (and how often)
[`InventoryView`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/frontend/src/components/right-sizing/WorkloadInventoryDashboard.jsx#L477-L855) runs a **polling** data loader:

- **Every 60 seconds** (and on first mount / filter changes, line 537) it calls, in parallel:
  ```javascript
  const [sumRes, wlRes, metricsRes] = await Promise.all([
      workloadClassificationAPI.getSummary(clusterId),
      workloadClassificationAPI.getWorkloads(clusterId, params),
      workloadClassificationAPI.getMetrics(clusterId),
  ]);
  ```

The UI supports:
- **Pagination**: `page`, `page_size` (default `PAGE_SIZE = 50`, line 489)
- **Filtering**: `namespace` (dropdown from loaded data), `tier`, `confidence_state`, `spot_friendly`, `search` (300ms debounced, lines 546–553)
- **Detail drill-down**: click a row → calls `workloadClassificationAPI.getWorkloadDetail(clusterId, workloadId)` (line 185)

### Frontend API client ([`workloadClassificationAPI`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/frontend/src/services/api.js#L677-L740))

| Method | HTTP | Path |
|--------|------|------|
| `getSummary(clusterId)` | GET | `/api/v1/workload-classification/{clusterId}/summary` |
| `getWorkloads(clusterId, params)` | GET | `/api/v1/workload-classification/{clusterId}/workloads` |
| `getWorkloadDetail(clusterId, workloadId)` | GET | `/api/v1/workload-classification/{clusterId}/workloads/{encodeURIComponent(workloadId)}` |
| `getSpotCandidates(clusterId)` | GET | `/api/v1/workload-classification/{clusterId}/spot-candidates` |
| `getMetrics(clusterId)` | GET | `/api/v1/workload-classification/{clusterId}/metrics` |
| `setOverride(clusterId, workloadId, payload)` | POST | `/api/v1/workload-classification/{clusterId}/workloads/{encodeURIComponent(workloadId)}/override` |
| `deleteOverride(clusterId, workloadId)` | DELETE | `/api/v1/workload-classification/{clusterId}/workloads/{encodeURIComponent(workloadId)}/override` |

### Override actions from UI
The [detail view](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/frontend/src/components/right-sizing/WorkloadInventoryDashboard.jsx#L168-L473) has an "Override" panel (line 354):
- Override form fields: `tier_override` (select), `spot_override` (select: force_spot/force_ondemand), `duration` (1h/6h/24h/7d/permanent), `reason` (text input)
- **Reason must be at least 10 characters** (line 205–207)
- Override form is **disabled** unless `confidence_state === "CONFIRMED"` (line 198, 431)
- `handleOverrideSubmit()` (line 203): converts `spot_override` string to boolean, sends to `setOverride()`
- `handleDeleteOverride()` (line 232): calls `deleteOverride()`

Important: overrides do **not** instantly mutate the DB row; they are stored in Redis and applied in the next slow loop cycle.

### UI table columns (workload list)
The [inventory table](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/frontend/src/components/right-sizing/WorkloadInventoryDashboard.jsx#L716-L800) shows:
| Column | Source |
|--------|--------|
| Name / Namespace | `w.name`, `w.namespace` |
| Kind | `w.controller_kind` (badge) |
| Tier | `w.tier` (colored badge: Platinum=red, Gold=amber, Silver=blue, Bronze=green) |
| Spot | `w.spot_friendly` (✓ green / ✗ red) |
| Confidence | `w.confidence_state` (colored badge: CONFIRMED=green, PROVISIONAL=amber, DRAFT=grey) |
| Crit. | `w.criticality_score` |
| Spot Score | `w.spot_score` |
| Signals | First 3 from `w.signals_fired` (prefix before `:` shown as badges) |

### Engine Health footer (lines 828–852)
Shows: Last Scan, Engine Age, Scans/min, DB Writes Suppressed %, Debounce Drops, Rate Limit Drops + stale warning if `last_scan_seconds > 600`.

---

## Algorithms (how WIE computes scores)

Everything below is implemented in [`workload_identification_engine.py`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py).

### Classification pipeline (per workload)
The single entry point is [`classify_workload()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1724-L1827):

```
classify_workload(workload, system_namespaces, cluster_engine_age_hours, redis, mode)
```

Pipeline steps (as implemented):

| Step | Function | Line | Description |
|------|----------|------|-------------|
| 1 | `validate_no_synthetic_defaults()` | 1751 | Log warning for suspicious zero-valued fields |
| 2 | `determine_role_with_signals()` | 1754 | Role: SYSTEM / CONTROL_PLANE / APPLICATION |
| 3 | `compute_criticality_with_signals()` + `criticality_to_tier()` | 1757–1758 | Criticality 0–10 → tier mapping |
| 4 | `compute_confidence()` | 1761 | Confidence 1–10 |
| 4a | `apply_staleness_penalty()` | 1764 | Metrics staleness adjustment (before cold start) |
| 5 | `get_confidence_state_with_coldstart()` | 1770 | State mapping + 24h cold start cap |
| 5a | `validate_signals_completeness()` | 1791 | Ensure ≥3 signals + role/tier/spot groups present |
| 6 | `compute_spot_score_with_signals()` + `is_spot_friendly()` | 1775–1776 | Spot 0–10 + boolean eligibility |
| 7 | Build `WorkloadClassification` | 1794–1815 | Assemble output dataclass |
| 8 | `apply_overrides()` | 1819 | Production mode only; Redis > K8s annotations |
| 9 | `enforce_safety_invariants()` | 1822 | Hard safety gate (stateful without resilience) |
| 10 | `enforce_confidence()` | 1825 | Global confidence enforcement (currently pass-through) |

### Role determination ([`determine_role()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L489-L529))
```
SYSTEM:        DaemonSet || system namespace || system priority class
CONTROL_PLANE: system priority class + name in {kube-controller-manager, kube-scheduler, etcd, kube-apiserver, cloud-controller-manager}
               OR labels app.kubernetes.io/component in {controller-manager, scheduler, etcd, apiserver}
APPLICATION:   Everything else
```

### Criticality scoring ([`compute_criticality()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L532-L603))
- SYSTEM → 10, CONTROL_PLANE → 9 (hardcoded)
- APPLICATION base: **5**, then adjustments:

| Signal | Condition | Effect |
|--------|-----------|--------|
| Priority class | value ≥ 10000 / ≥ 1000 / ≥ 100 | +3 / +2 / +1 |
| PDB strictness | `pdb_max_unavailable == 0` / exists | +2 / +1 |
| External exposure | LoadBalancer/Ingress / NodePort | +2 / +1 |
| Hub detection | `inbound_services >= 5` / `>= 3` | +2 / +1 |
| Stateful | STATEFUL / CACHE | +2 / +1 |
| Singleton exposed | replicas==1 + inbound≥2 + external | +1 |

Clamped to [0, 10].

### Tier mapping ([`criticality_to_tier()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L242-L254))
```
≥ 9 → Platinum    ≥ 6 → Gold    ≥ 3 → Silver    < 3 → Bronze
```

### Spot scoring ([`compute_spot_score()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L625-L717))
- SYSTEM/CONTROL_PLANE → **0** always
- Base scores by kind: `Deployment=6, ReplicaSet=6, StatefulSet=1, DaemonSet=0, Job=7, CronJob=7`

| Signal | Condition | Effect |
|--------|-----------|--------|
| Resilience gate | has_pdb AND replicas ≥ 2 | +1 |
| Topology spread | has_topology_spread OR has_pod_anti_affinity | +1 |
| Multi-AZ | declared_spread AND ≥ 2 observed_zones | +1 |
| Fast readiness | `readiness_initial_delay < 30s` | +1 |
| Slow readiness | `> 60s` / `> 30s` | -2 / -1 |
| High restart rate | normalized `> 2.0x` / `> 1.5x` | -2 / -1 |
| Absolute restart fallback | StatefulSet `> 1.0/hr` or Deploy `> 2.0/hr` | -1 |
| Outbound concentrated | `> 80%` / `> 60%` (only when not None) | -2 / -1 |
| Leader election | `ready_endpoint_count == 1` AND inbound > 0 | -2 |
| Long CronJob | `current_run_minutes > 120` | -1 |
| **Stateful cap** | _is_stateful_spot_safe() = True → cap at **4**; else → **0** | min cap |

Clamped to [0, 10].

### Spot-friendly eligibility ([`is_spot_friendly()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L720-L732))
```python
spot_score >= 4 AND has_pdb AND replicas >= 2
```

### Stateful spot safety ([`_is_stateful_spot_safe()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L606-L622))
All four conditions must hold:
1. `replicas >= 3` (quorum survives 1 eviction)
2. `has_pdb` (disruption budget exists)
3. `has_declared_spread` (topology spread OR pod anti-affinity present)
4. `len(observed_zones) >= 2` (pods actually running in ≥ 2 zones)

### Confidence scoring ([`compute_confidence()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L735-L782))
- Base: **8**

| Signal | Condition | Effect |
|--------|-----------|--------|
| Metrics staleness | stale > 20 min / > 10 min (only when value < ABSENT) | -3 / -2 |
| Conflicting signals | 2+ detected contradictions | -2 |
| New workload | < 24h / < 72h old | -2 / -1 |
| Instability | last_restart_reason in {CrashLoopBackOff, OOMKilled} | -1 |
| Multi-AZ boost | declared_spread AND ≥ 2 observed_zones | +1 |

Missing metrics (value == 999 sentinel) are treated as **neutral** — no penalty.

Clamped to [1, 10].

### Confidence state mapping ([`compute_confidence_state()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L785-L797))
```
< 5 → DRAFT    5–7 → PROVISIONAL    ≥ 8 → CONFIRMED
```

### Cold start enforcement ([`get_confidence_state_with_coldstart()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L800-L813))
If engine has been running for < 24h (`COLD_START_HOURS = 24`), cap at PROVISIONAL even if score would give CONFIRMED.

### Confidence gating model (what it means)
WIE explicitly separates:
- **Eligibility**: "is it spot-suitable?" → `spot_friendly` only
- **Automation allowance**: "can we act automatically?" → confidence gate

Consumers should use [`ClassificationGuard`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1361-L1404):

| Method | Returns True When |
|--------|-------------------|
| `is_actionable()` | `confidence_state == "CONFIRMED"` |
| `is_visible()` | Always `True` |
| `is_spot_eligible()` | `spot_friendly == True` |
| `is_drainable()` | CONFIRMED + not Platinum + (not Gold or spot_friendly) |
| `get_consumer_action()` | DRAFT→"IGNORE", PROVISIONAL→"SUGGEST_ONLY", CONFIRMED→"ACTIONABLE" |

---

## DB operations (what gets written, and why)

### Write suppression ("don't spam Postgres")
The slow loop writes via [`_write_to_db()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L2254-L2367) using [`should_write(new, prev)`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L403-L426).

Logic:
1. If `prev is None` → always write (first time)
2. If `new.input_hash == prev.input_hash` → return `False` (nothing material changed in inputs)
3. Otherwise: write if `score_delta >= 1` OR `spot_friendly changed` OR `tier changed` OR `confidence_state changed`

For new records (no previous): creates `WorkloadClassificationRecord` with `uuid.uuid4()` (line 2329).
For existing records: updates all scoring/metadata fields in-place (lines 2313–2326).
All records are committed in a single `db.commit()` (line 2362) with rollback on failure.

### Stale cleanup (deleted workloads)
At the end of each slow loop:
- [`_cleanup_stale_classifications(cluster_id, active_ids)`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L2369-L2407) deletes DB records for workloads no longer present.
- Deletes in chunks of 100 (line 2377) to avoid huge IN clauses.
- Redis classification keys expire by TTL (900s) — no explicit Redis cleanup needed.

---

## Redis operations (keys, TTLs, and why they exist)

### Snapshot consistency
- Slow loop snapshots pod_state with [`_snapshot_pod_states()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1965-L1996) — single pipeline call + `copy.deepcopy()` per entry + schema validation.
- Slow loop writes classifications with [`_write_to_redis()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L2233-L2252) — single pipeline call, 900s TTL per key.
- Each classification goes through `serialize_classification()` → `sanitize_classification_output()` → `json.dumps()` before write.
- Simulation results are explicitly blocked via [`SimulationIsolationContract.assert_not_simulation()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1417-L1424) (line 2241, 2270).

### Circuit breaker ([`EngineCircuitBreaker`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1443-L1481))
- Trip threshold: >20% errors in a cycle (`TRIP_THRESHOLD_PCT = 0.20`)
- TTL: 600s (auto-reset after 10 min)
- Key: `spot:wie:circuit_breaker:{cluster_id}`
- When tripped: slow loop skips entirely, consumers continue reading last-known-good Redis data

### Event debouncing ([`EventDebouncer`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1907-L1932))
- Cluster-size-aware window: > 200 workloads→30s, ≥ 50→20s, < 50→15s
- Key: `spot:wie:debounce:{cluster_id}:{workload_id}`

### Rate limiting ([`ClusterRateLimiter`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1935-L1958))
- Cap: 200 recompute tasks per cluster per minute
- Key: `spot:wie:rate_limit:{cluster_id}` with 60s expire

---

## Reaction to UI (what happens after user actions)

### When UI applies an override
1. UI calls `POST /workload-classification/{cluster}/workloads/{workload}/override`
2. Backend loads current DB record (lines 489–499)
3. Backend pre-validates safety via `_validate_override_safety()` against a conservative mini-workload (singleton, no PDB — line 513)
4. If unsafe: returns `OverrideResponse(applied=False, rejection_reason=...)` (line 541–547)
5. If safe: stores override JSON in Redis (optional TTL via `setex` or permanent via `set`, lines 563–568)
6. Next WIE slow loop applies it via `apply_overrides()` → then `enforce_safety_invariants()`
7. Result is persisted to DB (subject to `should_write()` suppression) and Redis caches
8. UI poll (60s) sees updated record and shows "Override Active" badge

### When UI removes an override
1. UI calls `DELETE /.../override`
2. Redis key is deleted (line 604)
3. Next slow loop recomputes classification without override
4. Response message (line 613): "Takes effect on next classification cycle (up to 10 min)."

---

## Cautions / correctness rules

### Never automate on DRAFT / PROVISIONAL
- Use `ClassificationGuard.is_actionable(...)` as the automation gate.
- For candidate discovery:
  - automation: use `safe_candidates` (CONFIRMED + spot_friendly)
  - visibility: use `potential_candidates` (PROVISIONAL + spot_friendly)

### Overrides are bounded (can be rejected)
Unsafe overrides are rejected by [`_validate_override_safety()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L963-L987):
- Cannot force `STATEFUL` to spot **without strong resilience signals** (replicas ≥ 3 + PDB + multi-AZ declared+observed)
- Cannot force singleton without PDB to spot — "guaranteed outage risk"
- Cannot override tier for `SYSTEM` role workloads

### "spot_friendly" vs "actionable"
- `spot_friendly` is a suitability signal (preserved even for DRAFT/PROVISIONAL at API boundary since [`enforce_confidence()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1091-L1097) is now a pass-through).
- **Actionability** must be gated by `confidence_state == CONFIRMED` in consumers.
- [`sanitize_classification_output()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1630-L1660) clears `placement_plan` for DRAFT/PROVISIONAL but preserves `spot_friendly`.

### Schema version enforcement
- [`sanitize_classification_output()`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1641-L1652): if `schema_version != "4.3"`, forces `confidence_state = "DRAFT"`, `spot_friendly = False`, adds `_schema_warning`.

### Graceful degradation ([`GracefulDegradation`](file:///Users/atharvapudale/Desktop/backend-ecc/Atharva%20Repo/github/final-ml/backend/services/workload_identification_engine.py#L1548-L1588))
- Redis failure → skip cycle
- DB failure → Redis writes continue, DB writes skipped
- > 50% workloads failed collection → skip all writes for this cycle

---

## Full end-to-end flow (single cluster)

1. **Agent → backend ingestion**: pod stats + metadata are stored in `pod_metrics` (Postgres).
2. **Fast loop (2 min)**: WIE builds pod_state from `pod_metrics` (last 5 min) and writes Redis `spot:wie:pod_state:*` (TTL 300s).
3. **Slow loop (10 min)**:
   - Circuit breaker check
   - Snapshot pod_state (Redis pipeline + deep copy)
   - Query `pod_metrics` (last 10 min or fallback) → aggregate per-controller → `WorkloadInput`
   - Pre-compute: `detect_missing_critical_fields()`, `detect_conflicting_signals()`, `determine_data_safety()`
   - Classify via `classify_workload()` (10-step pipeline: role/criticality/confidence/spot + overrides + invariants)
   - Write to `workload_classifications` (Postgres) with suppression via `should_write()`
   - Write to `spot:wie:classification:*` (Redis, TTL 900s) with `sanitize_classification_output()`
   - Cleanup stale DB records for deleted workloads
   - Update `spot:wie:metrics:*` (Redis HASH, TTL 3600s)
4. **UI polling (60s)**: calls summary/list/metrics and renders inventory + health.
5. **User drill-down + overrides**: detail endpoint + override endpoints feed back into next slow loop.

---

## Appendix: Related "workload engines" in this repo (not the same as WIE)

This repo contains more than one "workload classification" concept:

- **WIE v4.3 (this document)**:
  - Workload-level classification for UI + safe automation gating
  - DB table: `workload_classifications`
  - Engine: `backend/services/workload_identification_engine.py` (2732 lines)
  - API: `/api/v1/workload-classification/*` (10 endpoints)
  - Key classes: `WorkloadInput`, `WorkloadClassification`, `WorkloadIdentificationEngine`, `ClassificationGuard`, `EngineCircuitBreaker`, `EventDebouncer`, `ClusterRateLimiter`, `GracefulDegradation`, `SimulationIsolationContract`

- **WorkloadInspector / `workload_classifier.py`**:
  - Node-level classification (stateful vs stateless nodes) and a separate tier system (`TIER_0..TIER_4`)
  - Redis keys like `spot:node_classification:*`, `spot:workload_profile:*`, `spot:workload_tier:*`
  - Used by other automation systems (rebalancer / eviction safety), not the Workload Inventory DB table directly
  - Called from the same scheduler job (`job_scan_clusters()`) but runs *before* WIE

---

## Appendix: Constants reference

| Constant | Value | Location (line) |
|----------|-------|-----------------|
| `DEFAULT_SYSTEM_NAMESPACES` | `{kube-system, kube-public, kube-node-lease, karpenter, spot-optimizer, cert-manager, monitoring, istio-system, linkerd}` | 59–63 |
| `SYSTEM_PRIORITY_CLASSES` | `{system-node-critical, system-cluster-critical}` | 66–69 |
| `SIDECAR_CONTAINERS` | `{istio-proxy, istio-init, vault-agent, filebeat, datadog-agent, ...}` | 72–76 |
| `CACHE_IMAGE_PATTERNS` | `{redis, memcached, dragonfly, keydb, hazelcast, varnish, twemproxy, mcrouter}` | 79–82 |
| `METRICS_ABSENT_VALUE` | `999` | 85 |
| `METRICS_STALE_THRESHOLD_MINUTES` | `60` | 88 |
| `SCHEMA_VERSION` | `"4.3"` | 92 |
| `MIN_EXPECTED_SIGNALS` | `3` | 95 |
| `CONFIDENCE_THRESHOLD_DRAFT` | `5` | 98 |
| `CONFIDENCE_THRESHOLD_PROVISIONAL` | `8` | 99 |
| `COLD_START_HOURS` | `24` | 102 |
| `POD_STATE_SCHEMA_VERSION` | `1` | 1697 |
| `TRIP_THRESHOLD_PCT` | `0.20` (20%) | 1450 |
| `TRIP_TTL_SECONDS` | `600` (10 min) | 1451 |
| `MAX_RECOMPUTE_TASKS_PER_CLUSTER_PER_MINUTE` | `200` | 1941 |
