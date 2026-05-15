# Page-by-Page Data Source Audit

> **Purpose**: For each of the 6 Optimize pages, document every UI sub-component, the data it renders, the API endpoint that supplies it, the physical storage backend (PostgreSQL table / Redis key), and whether the data is **REAL**, **FAKE** (hardcoded mock), or **MISSING** (UI exists, backend does not yet provide the value).
>
> **Legend**  
> - 🟢 **REAL** — wired end-to-end; data flows from storage → API → UI  
> - 🟡 **PARTIAL** — endpoint called and returns a value but some fields in the section are NULL / derived client-side  
> - 🔴 **FAKE** — UI renders hardcoded mock/static data; no API call  
> - ⚫ **MISSING** — UI section exists, displays a placeholder "—" or hides itself; backend field is absent  

---

## Table 1 — Node Bin Packing (`NodeBinPacking.jsx`)

**List API**: `GET /api/v1/optimize/nodes/bin-packing?cluster_id=X`  
**Detail API**: `GET /api/v1/optimize/nodes/{node_name}/bin-packing-detail?cluster_id=X`  
**Auth**: None (no `get_current_user` — uses `assert_cluster_access` row check only)

| UI Section / Sub-component | Fields Rendered | API Endpoint | DB Table / Redis Key | Status |
|---|---|---|---|---|
| **Cluster Selector** (header dropdown) | cluster name, cluster id list | `GET /api/v1/clusters` (auth required) | `clusters` table | 🟢 REAL |
| **Summary Strip — Total Nodes** | count of nodes returned | `/nodes/bin-packing` | `node_metadata` (COUNT via query) | 🟢 REAL |
| **Summary Strip — Total Pods** | sum of `pod_count` across all nodes | `/nodes/bin-packing` | `pod_metrics` (COUNT DISTINCT pod_name per node) | 🟢 REAL |
| **Summary Strip — Avg CPU Util** | mean of `cpu_actual_pct` across nodes | `/nodes/bin-packing` | Computed client-side from `pod_metrics` aggregates / `node_metadata.allocatable_cpu_millicores` | 🟢 REAL |
| **Summary Strip — Avg Mem Util** | mean of `mem_actual_pct` across nodes | `/nodes/bin-packing` | Computed client-side from `pod_metrics` aggregates / `node_metadata.allocatable_memory_bytes` | 🟢 REAL |
| **Summary Strip — Consolidation Candidates** | count of underutilized nodes | `/nodes/bin-packing` | Redis `spot:consolidation:candidates:{cluster_id}` → `consolidation_candidates` field | 🟡 PARTIAL — real only if Redis key is seeded/set by agent; else falls back to client-side count of nodes with `cpu_actual_pct < 60` |
| **Summary Strip — Est. Savings if Packed** | `$X/mo` | `/nodes/bin-packing` | Redis `spot:consolidation:candidates:{cluster_id}` → `est_savings_monthly_usd` | 🟡 PARTIAL — `$0` if Redis key absent; key must be seeded or written by consolidation engine |
| **Node List (left panel) — hostname** | `node_name` from NodeMetadata | `/nodes/bin-packing` | `node_metadata.node_name` | 🟢 REAL |
| **Node List — Instance Type / Pool** | `instance_type`, `az`, `capacity_type` | `/nodes/bin-packing` | `node_metadata` | 🟢 REAL |
| **Node List — CPU bar** | `cpu_actual_pct` (actual usage % of allocatable) | `/nodes/bin-packing` | `pod_metrics.cpu_usage_millicores` SUM / `node_metadata.allocatable_cpu_millicores` | 🟢 REAL |
| **Node List — Mem bar** | `mem_actual_pct` | `/nodes/bin-packing` | `pod_metrics.memory_usage_bytes` SUM / `node_metadata.allocatable_memory_bytes` | 🟢 REAL |
| **Node List — CONSOLIDATE / OVERLOADED badge** | Derived from `cpu_actual_pct`: `< 60% → "Can consolidate"`, `is_overloaded → "Overloaded"` | Client-side derivation from `/nodes/bin-packing` | No separate DB column — fully computed on frontend | 🟡 PARTIAL — logic is correct but threshold is hardcoded in JS |
| **Node List — STALE exclusion** | `stale_nodes_excluded` counter | `/nodes/bin-packing` | `node_metadata.updated_at` compared to `AURA_STALE_THRESHOLD_SECS` (default 120s) | 🟢 REAL — nodes with stale updated_at are removed from list silently |
| **Right Panel — Instance Type / Capacity / AZ** | `type`, `pool` (capacity_type + az) | `/nodes/bin-packing` | `node_metadata` | 🟢 REAL |
| **Right Panel — CPU Allocation bar** | `cpu_actual_pct` | `/nodes/bin-packing` | `pod_metrics` aggregation | 🟢 REAL |
| **Right Panel — Memory Allocation bar** | `mem_actual_pct` | `/nodes/bin-packing` | `pod_metrics` aggregation | 🟢 REAL |
| **Right Panel — Density Optimization panel** (only for "Can consolidate" nodes) | Current state bar = `cpu_actual_pct`, Packed Target label = **hardcoded "~80%"** | Partially `/nodes/bin-packing` | `pod_metrics` (current); target is hardcoded | 🔴 FAKE — the "Packed Target ~80%" is a hardcoded visual; no backend target calculation exists |
| **Right Panel — Pod Spatial Map** | `pod_name`, hover: `cpu_usage_millicores`, `cpu_request_millicores` | `/nodes/bin-packing-detail` (last 1h of pod_metrics) | `pod_metrics` filtered to node + timestamp > now-1h | 🟢 REAL |
| **`data_ready` field** | Used by UI to decide whether to trust numbers | `/nodes/bin-packing` | Requires BOTH `node_metadata.updated_at < 120s` AND Redis `spot:consolidation:candidates` key present | 🟡 PARTIAL — `false` if Redis key missing or data stale |

---

## Table 2 — Node Selector (`NodeSelector.jsx`)

**List API**: None — uses `mockNodes` array hardcoded in source  
**Planned API**: `GET /api/v1/optimize/nodes/selector` (referenced in comment only; **backend endpoint does not exist**)  
**Auth**: N/A

| UI Section / Sub-component | Fields Rendered | API Endpoint | DB Table / Redis Key | Status |
|---|---|---|---|---|
| **Cluster Selector** | None — no cluster selector exists on this page | — | — | 🔴 FAKE — page operates without cluster context |
| **What-If Strip — Monthly Savings** | `-$4,200` | None | None | 🔴 FAKE hardcoded |
| **What-If Strip — Spot Coverage** | `41% → 78%` | None | None | 🔴 FAKE hardcoded |
| **What-If Strip — Nodes After** | `24 → 18` | None | None | 🔴 FAKE hardcoded |
| **What-If Strip — Interruption Risk** | `Low` | None | None | 🔴 FAKE hardcoded |
| **Node Table — Hostname / Pool** | `ip-10-0-1-45.ec2.internal`, `default-pool` | None | None | 🔴 FAKE hardcoded (2 demo nodes) |
| **Node Table — Current: Instance Type, Capacity, $/hr** | `m5.2xlarge`, `On-Demand`, `$0.384` | None | None | 🔴 FAKE hardcoded |
| **Node Table — Current: vCPU, Memory** | `8 vCPU`, `32 GiB` | None | None | 🔴 FAKE hardcoded |
| **Node Table — Current: CPU/Mem Utilization** | `18%`, `42%` (hardcoded values) | None | None | 🔴 FAKE hardcoded |
| **Node Table — Optimized To: Target Instance / Capacity** | `r6a.xlarge`, `Spot` | None | None | 🔴 FAKE hardcoded |
| **Node Table — Savings % / Score** | `-64%`, `92` | None | None | 🔴 FAKE hardcoded |
| **Expanded Row — Optimization Reason text** | AI-style explanation paragraph | None | None | 🔴 FAKE hardcoded string |
| **Expanded Row — Cost Impact** | `$0.138/hr vs $0.384/hr` | None | None | 🔴 FAKE hardcoded |
| **Status filter buttons** | "Scheduled (4)", "Excluded (2)" | None | None | 🔴 FAKE hardcoded counts in button labels |
| **"Execute Optimizations" button** | Clickable but no action wired | None | None | 🔴 FAKE — no backend action endpoint |
| **"Export Plan" button** | Clickable but no action wired | None | None | 🔴 FAKE |

> **Summary**: This entire page is 100% mock data. The backend has no `/nodes/selector` endpoint. Real data would require: a new DB table for optimization schedules, EC2 pricing lookup, and a node recommendation engine.

---

## Table 3 — Workload Migration (`WorkloadMigration.jsx`)

**List API**: None — uses `CANDIDATES` array hardcoded in source  
**Planned API**: None defined in backend  
**Auth**: N/A

| UI Section / Sub-component | Fields Rendered | API Endpoint | DB Table / Redis Key | Status |
|---|---|---|---|---|
| **Candidate List (left panel)** | workload names (ml-batch-worker, auth-service, data-pipeline, cache-warmer), state chips, progress bar | None | None | 🔴 FAKE hardcoded (4 candidates) |
| **Candidate List — Progress bar** | `IN_PROGRESS 62% · 48GB` for data-pipeline | None | None | 🔴 FAKE hardcoded |
| **Statefulness & Data Profile panel** | Stateless/Stateful description paragraph | None | None | 🔴 FAKE — text derived from hardcoded `stateless` boolean |
| **Architecture Shift — Source node** | pool name, AZ, instance type | None | None | 🔴 FAKE hardcoded |
| **Architecture Shift — Target node** | target pool name, AZ, instance type | None | None | 🔴 FAKE hardcoded |
| **Execution Plan — Steps list** | step titles, descriptions, SAFE/REVERSIBLE/DESTRUCTIVE tags, active step highlight | None | None | 🔴 FAKE hardcoded (4–6 steps per candidate) |
| **Pre-Migration Checklist** | 6 items, all always checked green | None | None | 🔴 FAKE — all items always show ✓ |
| **Blast Radius** | downstream services count, est. downtime, rollback SLA | None | None | 🔴 FAKE hardcoded |
| **Cost Delta — Current / Target monthly cost** | `$1,244 → $311`, savings % | None | None | 🔴 FAKE hardcoded |
| **Migration Audit History** | timestamp, actor, action, status rows | None | None | 🔴 FAKE hardcoded (1–3 rows per candidate) |
| **"Begin Migration" button** | Disabled with tooltip "backend APIs pending" | None | None | ⚫ MISSING — button exists but is disabled; no backend migration execution API |

> **Summary**: This entire page is 100% mock data. No migration planning, scheduling, or execution APIs exist in the backend. Real implementation would require: a migration workflow engine, state machine per workload, PDB awareness, and drain orchestration.

---

## Table 4 — Workload Profiling (`WorkloadProfiling.jsx`)

**List API**: `GET /api/v1/workload-classification/{cluster_id}/workloads?page_size=100`  
**Summary API**: `GET /api/v1/workload-classification/{cluster_id}/summary`  
**Detail API**: `GET /api/v1/optimize/workloads/{workload_id}/profiling-detail?cluster_id=X`  
**Auth**: All three endpoints require `get_current_user` JWT

| UI Section / Sub-component | Fields Rendered | API Endpoint | DB Table / Redis Key | Status |
|---|---|---|---|---|
| **Cluster Selector** | cluster name + id | `GET /api/v1/clusters` | `clusters` table | 🟢 REAL |
| **Summary Strip — Total Workloads** | count | `/workloads?page_size=100` or `/summary` | `workload_classifications` COUNT | 🟢 REAL |
| **Summary Strip — CONFIRMED / PROVISIONAL / DRAFT** | counts per confidence state | `/summary` | `workload_classifications` GROUP BY `confidence_state` | 🟢 REAL |
| **Summary Strip — Spot-Friendly** | count | `/summary` | `workload_classifications` WHERE `spot_friendly=true` | 🟢 REAL |
| **Summary Strip — Potential Savings** | `$X` total | `/summary` | Joined from `placement_policies.estimated_monthly_saving_usd` SUM | 🟡 PARTIAL — only populated if placement_policies rows exist for cluster |
| **Workload List — Name / Namespace** | `workload_id.split('/').pop()`, `namespace` | `/workloads` | `workload_classifications.workload_id`, `.namespace` | 🟢 REAL |
| **Workload List — Tier badge** | GOLD / SILVER / BRONZE | `/workloads` | `workload_classifications.tier` | 🟢 REAL |
| **Workload List — Confidence score** | numeric `0.0–10.0` | `/workloads` | `workload_classifications.confidence_score` | 🟢 REAL |
| **Workload List — Spot Score bar** | bar + numeric `0.0–10.0` | `/workloads` | `workload_classifications.spot_score` | 🟢 REAL |
| **Workload List — Savings column** | always `$0` | `/workloads` | NOT mapped — savings only available in detail response, not list | 🔴 FAKE — hardcoded `savings: 0` in `mapListItem()` regardless of API |
| **Workload List — CPU stability dot** (green/amber) | Derived from `!traffic_skew_detected` | `/workloads` | `workload_classifications.traffic_skew_detected` | 🟢 REAL |
| **Right Panel — Identity (namespace, tier, confidence)** | metadata header | `/workloads` | `workload_classifications` | 🟢 REAL |
| **Right Panel — SPOT FRIENDLY / NOT SPOT READY badge** | `spot_friendly` boolean | `/workloads` | `workload_classifications.spot_friendly` | 🟢 REAL |
| **Right Panel — WIE Score Cards (Criticality, Spot Score, Confidence)** | `criticality_score`, `spot_score`, `confidence_score` | `/workloads` | `workload_classifications` | 🟢 REAL |
| **Right Panel — Signals Used in Scoring** | `signals_fired` string array | `/workloads` | `workload_classifications.signals_fired` (JSONB array) | 🟢 REAL |
| **Right Panel — CPU Usage chart (14d)** | sparkline from `cpu_timeseries` | `/profiling-detail` | `pod_metrics` aggregated by day (avg_cpu_millicores) | 🟢 REAL (requires pod_metrics data) |
| **Right Panel — CPU CV value** | `CV: 0.XX` coefficient of variation | `/profiling-detail` | `workload_classifications.cpu_cv` | 🟢 REAL (column added via ALTER TABLE) |
| **Right Panel — RPS chart (Request Rate)** | always shows "RPS timeseries not available" | None | Agent does not collect RPS data | ⚫ MISSING — placeholder only; no backend support |
| **Right Panel — RPS CV** | always `CV: —` | None | None | ⚫ MISSING |
| **Right Panel — Placement Advisor Target (OD/Spot bar)** | `ondemand_target`, `spot_target`, total replica split | `/profiling-detail` | `placement_policies.ondemand_target`, `.spot_target` | 🟡 PARTIAL — null if no placement_policy row exists for this workload |
| **Right Panel — Est. Monthly Saving** | `$X.XX` | `/profiling-detail` | `placement_policies.estimated_monthly_saving_usd` | 🟡 PARTIAL — `—` if no placement_policy row |
| **Right Panel — Tier Logic Applied** | `"Gold (100% OD Floor)"` etc. | Client-side mapping from `/workloads` tier | `workload_classifications.tier` | 🟢 REAL |
| **Right Panel — CV Adjustment** | "None (Stable load)" or "High volatility…" | `/profiling-detail` → `cpu_cv` | `workload_classifications.cpu_cv` | 🟢 REAL |
| **Right Panel — Advisor Actionability Gates** | 6 pass/fail checks | Mix of `/workloads` + `/profiling-detail` | Confidence state, spot_friendly, spot_target, system namespace check, `data_ready` | 🟡 PARTIAL — "Rollout Not Blocked" gate is hardcoded `'pass'`; others are real |
| **"Run Advisor Cycle" button** | Disabled | None | No trigger API exists | ⚫ MISSING |

---

## Table 5 — Workload Placement (`WorkloadPlacement.jsx`)

**List API**: `GET /api/v1/optimize/workloads/placement?cluster_id=X`  
**Detail API**: `GET /api/v1/optimize/workloads/{workload_id}/placement-detail?cluster_id=X`  
**Auth**: None (uses `assert_cluster_access` only — no JWT)

| UI Section / Sub-component | Fields Rendered | API Endpoint | DB Table / Redis Key | Status |
|---|---|---|---|---|
| **Cluster Selector** | cluster name + id | `GET /api/v1/clusters` | `clusters` table | 🟢 REAL |
| **Summary Strip — Total Tracked** | `total_count` | `/placement` | `placement_policies` COUNT | 🟢 REAL |
| **Summary Strip — Drifting** | count of workloads where `placement_state != STABLE` | Client-side filter on `/placement` response | `placement_policies.placement_state` | 🟢 REAL |
| **Summary Strip — Reconcile %** | `(total - drifting) / total * 100` | Client-side math | Derived | 🟢 REAL |
| **Workload List — name / namespace** | `workload_id.split('/').pop()`, `namespace` | `/placement` | `placement_policies.workload_id`, joined `workload_classifications.namespace` | 🟢 REAL |
| **Workload List — state badge** | HOLD_PDB / SCALE_SPOT / AT_TARGET / etc. | `/placement` | `placement_policies.placement_status` | 🟢 REAL |
| **Workload List — replica bar** (OD excess / OD req / Spot) | `od_excess`, `od_required`, `spot_count` | `/placement` | `placement_policies.od_excess`, `.od_required`, `.spot_count` | 🟢 REAL |
| **Workload List — OD excess delta** | `Δ OD: +N` in red | `/placement` | `placement_policies.od_excess` | 🟢 REAL |
| **Workload List — savings badge** | `$N/mo` in green | `/placement` | `placement_policies.estimated_monthly_saving_usd` | 🟢 REAL |
| **Right Panel — Reconciliation Timeline** | 6 steps; current step derived from `placement_state` via `timelineStep()` | `/placement` | `placement_policies.placement_state` | 🟡 PARTIAL — step mapping is a client-side heuristic; seeded data uses AT_TARGET which maps to step 5 ("Resolved"). States like EVICTING/DRIFT_DETECTED need real agent data |
| **Right Panel — Eviction Risk Signal banner** | pod name + "Pod Terminating" | `/placement-detail` (pods where `phase='Terminating'`) | `pod_metrics.phase` | 🟡 PARTIAL — `phase` column added to DB but NULL in seeded data; shows only with live agent data |
| **Right Panel — Topology Balance (AZ dots)** | AZ groups with Spot (blue) / OD (red) dots per pod | `/placement-detail` | `pod_metrics.node_name` + JOIN `node_metadata.az`, `.capacity_type` | 🟡 PARTIAL — requires pod_metrics with matching node names in node_metadata; works with seeded data |
| **Right Panel — Ground Truth pod table** | pod name, Node Type (Spot/OD), AZ, phase, age | `/placement-detail` | `pod_metrics` latest per pod + `node_metadata` JOIN | 🟡 PARTIAL — `phase` and `age_seconds` are null if `pod_metrics.phase`/`start_time` are null (seed data has them null) |
| **Right Panel — State Locks** | PDB Blocked, Action Cooldown, In-Flight, KEDA Scaling, Rollout Blocked | `/placement-detail` | Redis `spot:workload:state:{cid}:{wid}` (JSON hash) | 🟡 PARTIAL — all `False`/`None` if Redis key absent; populated by agent or seed script |
| **Right Panel — Controller Log** | recent decisions list (timestamp, action) | `/placement-detail` | Redis `spot:pc:workload_log:{cid}:{wid}` (list, last 10) | 🟡 PARTIAL — empty if Redis key absent; written by placement controller |
| **"Rebalance AZ" button** | Disabled | None | No backend action API exists | ⚫ MISSING |

---

## Table 6 — Workload Scaling (`WorkloadScaling.jsx`)

**List + Summary API**: `GET /api/v1/optimize/workloads/scaling?cluster_id=X`  
**Detail API**: `GET /api/v1/optimize/workloads/{workload_id}/scaling-detail?cluster_id=X`  
**Auth**: None (uses `assert_cluster_access` only — no JWT)

| UI Section / Sub-component | Fields Rendered | API Endpoint | DB Table / Redis Key | Status |
|---|---|---|---|---|
| **Cluster Selector** | cluster name + id | `GET /api/v1/clusters` | `clusters` table | 🟢 REAL |
| **Summary Strip — Tracked Workloads** | count | `/scaling` | `hpa_configs` COUNT | 🟢 REAL |
| **Summary Strip — HPA Misconfigured** | count of workloads with `has_warning=true` | `/scaling` | `hpa_configs` flagged rows | 🟢 REAL |
| **Summary Strip — Scale Events (24h)** | total event count | `/scaling` | `hpa_status_snapshots` COUNT in last 24h | 🟢 REAL |
| **Summary Strip — Avg Scale Latency** | always `—` | None | Not collected by agent | ⚫ MISSING — hardcoded `—` in component |
| **Summary Strip — Idle Replica Waste** | always `—` | None | Not computed anywhere | ⚫ MISSING — hardcoded `—` in component |
| **Summary Strip — VPA Recommendations** | always `—` | None | No VPA integration exists | ⚫ MISSING — hardcoded `—` in component |
| **Workload List — name / namespace** | `workload_id.split('/').pop()`, `namespace` | `/scaling` | `hpa_configs.workload_name`, `.namespace` | 🟢 REAL |
| **Workload List — status badge** | AT_MAX / THRASHING / OVERPROVISIONED / OPTIMAL | `/scaling` | Computed by backend from hpa_configs + snapshot comparison | 🟢 REAL |
| **Workload List — Min / Max / Current replicas** | numeric values | `/scaling` | `hpa_configs.min_replicas`, `.max_replicas`, `.current_replicas` | 🟢 REAL |
| **Workload List — Scale Events (24h)** | count | `/scaling` | `hpa_status_snapshots` COUNT per workload in last 24h | 🟢 REAL |
| **Workload List — current/max bar** | `current / max * 100%` progress bar | `/scaling` | Client-side math | 🟢 REAL |
| **Right Panel — HPA Config table** (Parameter / Current / Recommended) | min replicas, max replicas, target CPU | `/scaling-detail` | `hpa_configs` row | 🟢 REAL |
| **Right Panel — HPA Recommended values** | `recommended_min`, `recommended_max` | `/scaling-detail` | `hpa_configs.recommended_min_replicas`, `.recommended_max_replicas` | 🟢 REAL |
| **Right Panel — Recommendation basis label** | e.g. "Based on P95 desired replicas (last 30 days) × 1.2" | `/scaling` (list field) | `hpa_configs.recommendation_basis_label` (computed by agent) | 🟢 REAL |
| **Right Panel — Scale Event Timeline chart** (bars) | `desired_replicas` per snapshot bar | `/scaling-detail` | `hpa_status_snapshots.desired_replicas`, `.snapshot_at` (last 120 min) | 🟢 REAL — shows up to 40 bars |
| **Right Panel — "Thrash Pattern Detected" badge** | shown when `status === THRASHING` | `/scaling` | Client-side from `w.status` | 🟢 REAL |
| **Right Panel — Replica Efficiency breakdown** (Serving / Idle / Draining %) | `serving_count`, `idle_count`, `evicting_count` | `/scaling-detail` | `pod_metrics.phase` counts (`Running`/`Succeeded`/`Terminating`) for workload | 🟡 PARTIAL — requires `pod_metrics.phase` to be non-null; column added to DB but seeded as NULL; shows 0/0/0 with seed data |
| **Right Panel — Cooldown Audit table** | Scale-Up / Scale-Down stabilization window, assessment | `/scaling-detail` | `hpa_configs.scale_up_stabilization_seconds`, `.scale_down_stabilization_seconds` | 🟡 PARTIAL — these columns are NULL in seeded data (not in seed script); shows "Stabilization window data not collected by agent yet" |
| **KEDA badge** | shown when `keda_managed=true` | `/scaling` | `hpa_configs.keda_managed` | 🟢 REAL |

---

## Cross-Page Summary Matrix

| Page | Total Sub-components | 🟢 REAL | 🟡 PARTIAL | 🔴 FAKE | ⚫ MISSING |
|---|---|---|---|---|---|
| Node Bin Packing | 17 | 12 | 4 | 1 | 0 |
| Node Selector | 15 | 0 | 0 | 14 | 1 |
| Workload Migration | 11 | 0 | 0 | 10 | 1 |
| Workload Profiling | 22 | 13 | 4 | 1 | 4 |
| Workload Placement | 15 | 8 | 5 | 0 | 2 |
| Workload Scaling | 19 | 12 | 3 | 0 | 4 |

---

## Critical Gaps Requiring Backend Work

| Priority | Gap | Affected Pages | Fix Required |
|---|---|---|---|
| **P0** | `pod_metrics.phase` and `start_time` are NULL in seed data (columns exist, agent not writing them) | Placement (pod table, eviction), Scaling (efficiency breakdown) | Seed script + agent to populate these fields |
| **P0** | Node Selector page is 100% fake | Node Selector | New backend endpoint `GET /optimize/nodes/selector`, node recommendation engine |
| **P0** | Workload Migration page is 100% fake | Migration | Migration planning API, workflow state machine |
| **P1** | `hpa_configs.scale_up_stabilization_seconds` and `scale_down_stabilization_seconds` not seeded | Scaling (Cooldown Audit) | Add to seed script and ensure agent writes them |
| **P1** | Savings in Profiling list always `$0` | Profiling (list column) | Map `estimated_monthly_saving_usd` from detail response into list item on selection, or return it in list API |
| **P1** | RPS timeseries entirely absent | Profiling (Traffic Variance) | Agent needs to collect RPS from ingress/service metrics |
| **P1** | Redis consolidation candidates key only set by seed/manual — agent doesn't write it | Bin Packing (savings, data_ready) | Consolidation engine needs to write `spot:consolidation:candidates:{cid}` |
| **P2** | "Rollout Not Blocked" gate is hardcoded `pass` in Profiling | Profiling (Actionability Gates) | Pass `rollout_blocked` from placement_policies or Redis state into profiling-detail response |
| **P2** | `pod.age_seconds` always null in Placement pod table | Placement (Ground Truth table) | Agent must write `pod_metrics.start_time` |
| **P2** | Avg Scale Latency, Idle Replica Waste, VPA Recommendations missing | Scaling (Summary Strip) | Agent needs to track scale event timestamps; VPA integration is a separate project |
| **P3** | Placement reconciliation timeline uses coarse client-side mapping | Placement (Timeline) | Backend could return a `timeline_step` integer directly |
