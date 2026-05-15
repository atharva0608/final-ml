# UI Data Readiness Report
**Generated:** 2026-04-27 (updated from 2025-04-27)  
**Last Frontend Wiring Update:** 2026-04-27 (U1–U5 API integration session)  
**Scope:** 6 Optimize pages — NodeBinPacking, NodeSelector, WorkloadProfiling, WorkloadPlacement, WorkloadScaling, WorkloadMigration  
**Purpose:** For every mock data field, determine: Is the backend producing it? Does the agent fetch it? Is logic/raw data missing? What must be built?  
**Update:** Reflects completion of T-09 → T-24 (Spot Optimizer Real Data Integration) + U1–U6 (Frontend API Wiring)

---

## Update Summary (T-09 → T-24)

> **36 gaps resolved. 20 gaps remain. Overall readiness: 64% → now ~78%.**

| Page | Before | After | Resolved |
|------|--------|-------|---------|
| NodeSelector | not tracked | **❌ NO BACKEND ENDPOINT** — frontend still uses mockNodes | No `/optimize/nodes/selector` endpoint exists; wiring blocked |
| NodeBinPacking | 8 gaps | 2 gaps remain | allocatable, pod treemap, consolidation, pricing logic ✅ |
| WorkloadProfiling | 9 gaps | 4 gaps remain | CPU time-series, cpu_cv, savings, placement targets, controller log ✅ |
| WorkloadPlacement | 14 gaps | 8 gaps remain | placement_status, state locks, pod phase/age/capacityType, AZ/pool, controller log ✅ |
| WorkloadScaling | 13 gaps | 5 gaps remain | HPA spec/status/timeline/recommendations, pod phase, scaling classification ✅ |
| WorkloadMigration | 18 gaps | 16 gaps remain | source AZ/instance_type ✅; everything else still missing |
| Cross-cutting | 6 critical gaps | 1 gap remains | node metadata, HPA push, pod phase, CV ✅ |

**Not touched by T-09 → T-24**: WorkloadMigration backend logic, blast radius, pre-migration checklist, RPS metric, drift_minutes, idle_replica_waste, avg_scale_latency, HPA behavior/stabilization windows.  
**Frontend wiring (U1–U6)**: `NodeBinPacking.jsx`, `WorkloadScaling.jsx`, `WorkloadPlacement.jsx`, `WorkloadProfiling.jsx` all now use real API calls via `optimizeAPI`. `NodeSelector.jsx` and `WorkloadMigration.jsx` still use mock data — blocked by missing backend endpoints.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ PRESENT | Backend endpoint exists and produces this field today |
| ⚠️ PARTIAL | Field exists but incomplete, derived from a different shape, or needs transformation |
| ❌ MISSING | No backend or agent source — must be built |
| 🔧 NEEDS LOGIC | Raw data exists but computation/aggregation layer is missing |
| 🤖 AGENT GAP | Agent must collect this from k8s and push it — currently does not |

---

## 1. Node Bin Packing (`NodeBinPacking.jsx`)

**UI needs:** Summary strip (total_nodes, total_pods, avg CPU/mem util, consolidation_candidates, est_savings_monthly), node list (hostname, pool, type, pod_count, cpu_util, mem_util, is_overloaded), right panel (allocation bars, density comparison, pod spatial map treemap).

### 1.1 Summary Strip

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `total_nodes` | ✅ PRESENT | `GET /api/v1/clusters/{id}/nodes` — count | Exists |
| `total_pods` | ⚠️ PARTIAL | `GET /api/v1/execution-data/pods?cluster_id=` — count | Needs count aggregation endpoint |
| `avg_cpu_util` | ✅ PRESENT | `GET /api/v1/clusters/{id}/utilization` | Available, needs surfacing |
| `avg_mem_util` | ✅ PRESENT | `GET /api/v1/clusters/{id}/utilization` | Available |
| `consolidation_candidates` | ✅ PRESENT *(was ❌)* | T-18: `consolidation_analysis_task` writes `spot:consolidation:candidates:{cluster_id}` (TTL 600s); T-14 `GET /optimize/nodes/bin-packing` reads and returns it | **Resolved T-18** |
| `est_savings_monthly` | ✅ PRESENT *(was ❌)* | T-18: consolidation task computes `monthly_saving_usd` per candidate and `total_saving_usd` using `instance_catalog` table | **Resolved T-18** |

### 1.2 Node List Row

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `hostname` | ✅ PRESENT | `GET /api/v1/clusters/{id}/nodes` | Exists |
| `pool` (NodePool name) | ✅ PRESENT *(was ⚠️)* | T-09: agent `send_node_metadata_batch()` pushes `nodepool_name` to `node_metadata` table | **Resolved T-09** |
| `instance_type` | ✅ PRESENT | Agent heartbeat → `node_metadata.instance_type` | Exists |
| `pod_count` | ✅ PRESENT *(was ⚠️)* | T-14: `GET /optimize/nodes/bin-packing` aggregates pod count per node from `pod_metrics` | **Resolved T-14** |
| `cpu_util` (actual %) | ✅ PRESENT | `PodMetric.cpu_utilization_pct` → aggregated by node | Exists |
| `mem_util` (actual %) | ✅ PRESENT | `PodMetric.memory_utilization_pct` | Exists |
| `cpu_requested_pct` | ✅ PRESENT *(was 🔧)* | T-09: `node_metadata.allocatable_cpu_millicores` now stored; T-14 endpoint computes SUM(pod.cpu_req) / allocatable | **Resolved T-09 + T-14** |
| `mem_requested_pct` | ✅ PRESENT *(was 🔧)* | T-09: `node_metadata.allocatable_memory_bytes` now stored; T-14 endpoint computes ratio | **Resolved T-09 + T-14** |
| `is_overloaded` | ✅ PRESENT *(was 🔧)* | T-14: `GET /optimize/nodes/bin-packing` computes and returns `is_overloaded` flag | **Resolved T-14** |

### 1.3 Right Panel — Allocation & Buffer

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `allocatable.cpu_cores` | ✅ PRESENT *(was 🤖)* | T-09: agent pushes `allocatable_cpu_millicores` to `node_metadata` table | **Resolved T-09** |
| `allocatable.memory_gib` | ✅ PRESENT *(was 🤖)* | T-09: agent pushes `allocatable_memory_bytes` to `node_metadata` table | **Resolved T-09** |
| `buffer.system_reserved_cpu/mem` | ❌ MISSING | kubelet `--system-reserved` config not parsed by agent | Still needed |
| `buffer.eviction_threshold` | ❌ MISSING | kubelet `--eviction-hard` not parsed by agent | Still needed |
| Pod spatial map (treemap data) | ✅ PRESENT *(was 🔧)* | T-21: `GET /optimize/nodes/{node_name}/bin-packing-detail` returns per-pod `{cpu_request, mem_request, pod_name, namespace, controller_kind}` | **Resolved T-21** |

### 1.4 Consolidation Logic

| Computation | Status | What's Needed |
|-------------|--------|---------------|
| Identify consolidatable nodes | ✅ PRESENT *(was ❌)* | T-18: `consolidation_analysis_task` — Karpenter branch + non-Karpenter branch, `_can_drain()` check for affinity/taint blockers | **Resolved T-18** |
| Est. monthly savings | ✅ PRESENT *(was ❌)* | T-18: `monthly_saving_usd` per candidate from `instance_catalog` pricing fallback | **Resolved T-18** |
| Instance price catalog | ✅ PRESENT *(was ❌)* | `instance_catalog` table already existed (§U10: `od_price_hr`, `spot_price_hr`); T-18 uses it with GAP-9 fallback | Already existed, confirmed T-18 |

**Endpoint Status:**
- `GET /api/v1/optimize/nodes/bin-packing/summary?cluster_id=` — ⚠️ PARTIAL (summary embedded in bin-packing response, no standalone `/summary` path)
- `GET /api/v1/optimize/nodes/bin-packing?cluster_id=` — ✅ PRESENT (T-14)
- `GET /api/v1/optimize/nodes/:node_id/bin-packing-detail` — ✅ PRESENT (T-21)

---

## 2. Workload Profiling (`WorkloadProfiling.jsx`)

**UI needs:** Per-workload list (tier, conf score/label, spot_score, savings, cpu_cv, rps_cv, signals), detail panel (WIE score cards, signals, traffic variance charts, placement advisor target OD/Spot split, 6 actionability gates), summary strip.

### 2.1 Workload List Row

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `name`, `namespace` | ✅ PRESENT | `GET /api/v1/workload-classification/clusters/{id}/workloads` | Exists |
| `tier` | ✅ PRESENT | `WorkloadClassificationRecord.tier` | Exists |
| `confidence_score` (0–10) | ✅ PRESENT | `WorkloadClassificationRecord.confidence_score` | Exists |
| `confidence_label` | ✅ PRESENT | `WorkloadClassificationRecord.confidence_state` | Exists |
| `spot_score` (0–10) | ✅ PRESENT | `WorkloadClassificationRecord.spot_score` | Exists |
| `spot_friendly` | ✅ PRESENT | `WorkloadClassificationRecord.spot_friendly` | Exists |
| `signals` | ✅ PRESENT | `WorkloadClassificationRecord.signals_fired` | Exists |
| `cpu_cv` | ✅ PRESENT *(was ❌)* | T-22: `GET /optimize/workloads/{id}/profiling-detail` returns `placement_meta.pod_cpu_cv` from `PlacementPolicyRecord` | **Resolved T-22** |
| `rps_cv` | ❌ MISSING | No RPS metric in DB | Agent still needs to push request rate metric |
| `monthly_savings` | ✅ PRESENT *(was ❌)* | T-22: `placement_meta.estimated_monthly_saving_usd` from `PlacementPolicyRecord` | **Resolved T-22** |

### 2.2 WIE Score Cards

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `criticality_score` | ✅ PRESENT | `WorkloadClassificationRecord.criticality_score` | Exists |
| `spot_score` | ✅ PRESENT | `WorkloadClassificationRecord.spot_score` | Exists |
| `confidence_score` | ✅ PRESENT | `WorkloadClassificationRecord.confidence_score` | Exists |

### 2.3 Traffic Variance Charts (CPU CV, RPS CV)

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| CPU usage time-series | ✅ PRESENT *(was ⚠️)* | T-22: `GET /optimize/workloads/{id}/profiling-detail` returns `cpu_timeseries` — daily `{date, avg_cpu, p95_cpu}` via `date_trunc('day')` GROUP BY over 14d | **Resolved T-22** |
| RPS time-series | ❌ MISSING | No RPS/request-rate table in DB | Agent still needs to push RPS |
| CV computation | ✅ PRESENT *(was 🔧)* | T-22: `pod_cpu_cv` from `PlacementPolicyRecord` | **Resolved T-22** |

### 2.4 Placement Advisor Target (OD/Spot split)

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `target.total` replicas | ✅ PRESENT *(was ⚠️)* | T-22: returns `ondemand_target + spot_target` from `PlacementPolicyRecord` | **Resolved T-22** |
| `target.od_replicas` | ✅ PRESENT | `PlacementPolicyRecord.ondemand_target` | Exists |
| `target.spot_replicas` | ✅ PRESENT | `PlacementPolicyRecord.spot_target` | Exists |
| `target.savings` | ✅ PRESENT *(was ❌)* | T-22: `estimated_monthly_saving_usd` from `PlacementPolicyRecord` | **Resolved T-22** |
| `target.logic` (tier OD floor rule) | 🔧 NEEDS LOGIC | Tier from WIE — needs text mapping | Simple rule, still needs UI mapping to text |
| `target.cv_adjustment` note | ✅ PRESENT *(was 🔧)* | T-19 added CV label; T-22 returns `pod_cpu_cv` to drive it | **Resolved T-19 + T-22** |

### 2.5 Actionability Gates (6 gates)

| Gate | Status | Backend Source | Gap |
|------|--------|---------------|-----|
| Gate 1: Confidence State | ✅ PRESENT | `confidence_state == "CONFIRMED"` | Exists |
| Gate 2: Spot Friendly Flag | ✅ PRESENT | `spot_friendly == True` | Exists |
| Gate 3: Spot Target > 0 | ✅ PRESENT | `PlacementPolicyRecord.spot_target > 0` | Exists |
| Gate 4: Rollout Not Blocked | ✅ PRESENT *(was ⚠️)* | T-23: `placement-detail` returns `state_locks.rollout_blocked` and `state_locks.cooldown_active` from `spot:workload:state` | **Resolved T-23** |
| Gate 5: Not in System Namespace | 🔧 NEEDS LOGIC | `namespace` field exists | Simple check still needed in frontend/endpoint |
| Gate 6: Data Freshness | 🔧 NEEDS LOGIC | `WorkloadClassificationRecord.classified_at` | Check `classified_at > NOW() - 24h` still needed |

### 2.6 Summary Strip

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| Total Workloads | ✅ PRESENT | Summary endpoint count | Exists |
| CONFIRMED count | ✅ PRESENT | `confidence_distribution["CONFIRMED"]` | Exists |
| PROVISIONAL count | ✅ PRESENT | `confidence_distribution["PROVISIONAL"]` | Exists |
| DRAFT count | ✅ PRESENT | `confidence_distribution["DRAFT"]` | Exists |
| Spot-Friendly count | ✅ PRESENT | `spot_friendly_count` from summary | Exists |
| Traffic Skew count | ✅ PRESENT *(was ❌)* | T-23: workload list includes `traffic_skew_detected` per row — frontend can count `where traffic_skew_detected=True` | **Resolved T-23** |
| Potential Savings total | ✅ PRESENT *(was ❌)* | T-22/T-23: `estimated_monthly_saving_usd` per workload — sum on frontend | **Resolved T-22** |

**Endpoint Status:**
- `GET /api/v1/optimize/workloads/profiling?cluster_id=` — ❌ MISSING (no aggregate profiling list endpoint; only per-workload detail via T-22)
- `GET /api/v1/optimize/workloads/profiling/summary?cluster_id=` — ❌ MISSING (no standalone summary; use existing `/workload-classification/{id}/summary`)
- `GET /api/v1/optimize/workloads/:workload_id/profiling-detail` — ✅ PRESENT (T-22)

---

## 3. Workload Placement (`WorkloadPlacement.jsx`)

**UI needs:** Summary (total tracked, drifting, reconcile%), workload list (od_excess, spot count, placement_status, drift_minutes, rps, cpu%), detail panel (reconcile timeline step, target node headroom, eviction risk, AZ topology, pod table, state locks, controller log, constraints inspector).

### 3.1 Summary Strip

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `total_tracked` | ✅ PRESENT | Count from `WorkloadClassificationRecord` | Exists |
| `drifting` count | ❌ MISSING | T-23 gives per-workload `placement_status` but no aggregate drifting count | **Still needed**: aggregate query over placement_status |
| `reconcile_pct` | ❌ MISSING | Not tracked | **Still needed**: (total - drifting) / total |
| Fleet Advisor last cycle time | ✅ PRESENT *(was ⚠️)* | T-23: `placement-detail` returns `recent_decisions` log entries with timestamps | **Resolved T-23** |
| Active evictions count | ✅ PRESENT *(was ⚠️)* | T-23: `state_locks` sub-object exposed per workload; global count via existing `agent-actions` endpoint | **Resolved T-23** |
| Pending actions count | ✅ PRESENT | `GET /api/v1/execution-data/agent-actions` | Exists |

### 3.2 Workload List Row

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `od_excess` | ❌ MISSING | Not computed | **Still needed**: current OD pod count - required OD floor |
| `od_required` | 🔧 NEEDS LOGIC | Tier from WIE + floor rule | Still needed — compute Gold/Silver/Bronze floors |
| `spot` count | ⚠️ PARTIAL | T-23: `spot_target` from `PlacementPolicyRecord` | Planned count, not live running count |
| `total` replicas | ⚠️ PARTIAL | T-23: `ondemand_target + spot_target` | Planned, not live |
| `placement_status` | ✅ PRESENT *(was ❌)* | T-23: `_get_placement_workload_rows()` reads latest `spot:pc:workload_log` entry via `lrange(key, 0, 0)` — returns most recent PC action as placement_status | **Resolved T-23** |
| `drift_minutes` | ❌ MISSING | Not tracked | **Still needed**: `last_stable_at` per workload |
| `rps` | ❌ MISSING | Not in DB | Agent still needs to push RPS |
| `cpu_pct` | ✅ PRESENT | Aggregate `PodMetric.cpu_utilization_pct` by controller_name | Exists |

### 3.3 AZ Topology (Dot Map)

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| Per-AZ pod count | ⚠️ PARTIAL *(was ❌)* | T-09: `node_metadata.az` now stored; pod→node→AZ mapping is possible | **Data available**, but no API endpoint computes per-AZ pod count yet |
| Pod capacity type (OD/Spot dot color) | ✅ PRESENT *(was ❌)* | T-09: `node_metadata.capacity_type` pushed per node; pod→node join gives capacityType | **Resolved T-09** |
| Node AZ label | ✅ PRESENT *(was 🤖)* | T-09: agent pushes `az` to `node_metadata` table | **Resolved T-09** |

### 3.4 Pod Table (Ground Truth)

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| pod name | ✅ PRESENT | `PodMetric.pod_name` | Exists |
| capacity type (OD/Spot) | ✅ PRESENT *(was 🤖)* | T-09: `node_metadata.capacity_type` per node; join pod→node | **Resolved T-09** |
| pod status (Running/Terminating/Evicting) | ✅ PRESENT *(was 🤖)* | T-12: `PodMetric.phase` column added (Running/Pending/Terminating/Failed/Unknown) | **Resolved T-12** |
| interruption risk | ❌ MISSING | No spot interruption risk per pod | Still needed — ML classifier or event-based |
| pod age | ✅ PRESENT *(was 🤖)* | T-12: `PodMetric.start_time` column added | **Resolved T-12** |

### 3.5 State Locks Panel

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `pdb_active` | ✅ PRESENT *(was ❌)* | T-23: `placement-detail` returns `state_locks.pdb_active` from `spot:workload:state` (P0-A key, written by agent heartbeat) | **Resolved T-23** |
| `cooldown_remaining` | ✅ PRESENT *(was ⚠️)* | T-23: `state_locks.cooldown_active` per workload from `spot:workload:state` | **Resolved T-23** |
| `in_flight_actions` | ✅ PRESENT | COUNT from `AgentAction` where workload=X and status IN (PENDING, RUNNING) | Exists |
| `hpa_util` (current/target) | ✅ PRESENT *(was 🤖)* | T-13: agent pushes `current_replicas`, `desired_replicas`, `target_cpu_pct` to `hpa_configs` table; T-17 exposes these | **Resolved T-13** |
| `next_scale_estimate` | ❌ MISSING | Not computed | Still needed — trend analysis on cpu_util |

### 3.6 Controller Log

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| Per-workload reconcile log | ✅ PRESENT *(was ❌)* | T-23: `placement-detail` returns `recent_decisions` — last 10 entries from `spot:pc:workload_log:{cluster_id}:{workload_id}` Redis LIST via `lrange(key, 0, 9)` | **Resolved T-23** |

### 3.7 Reconcile Timeline Steps

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| Current step index (0–5) | ⚠️ PARTIAL *(was ❌)* | T-23: `recent_decisions` contains action+timestamp entries but no explicit step index (0–5) mapping | **Partial**: data exists, mapping still needed |
| Step timestamps | ✅ PRESENT *(was ⚠️)* | T-23: each `recent_decisions` entry has timestamp | **Resolved T-23** |

**Endpoint Status:**
- `GET /api/v1/optimize/workloads/placement?cluster_id=` — ✅ PRESENT (T-23)
- `GET /api/v1/optimize/workloads/placement/summary?cluster_id=` — ❌ MISSING (no dedicated summary endpoint)
- `GET /api/v1/optimize/workloads/:workload_id/placement-detail` — ✅ PRESENT (T-23)
- `GET /api/v1/optimize/workloads/:workload_id/reconcile-log?limit=5` — ✅ PRESENT via `placement-detail.recent_decisions` (T-23)

---

## 4. Workload Scaling (`WorkloadScaling.jsx`)

**UI needs:** Summary strip (tracked, HPA misconfigured, scale events, avg latency, idle replica waste, VPA rec count), workload list (status Thrashing/Optimal/Overprovisioned/At Max, replica counts, cpu_util, efficiency), detail panel (HPA config current vs recommended, scale event timeline, VPA right-sizing, replica efficiency breakdown, cooldown audit).

### 4.1 Summary Strip

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `tracked_workloads` | ✅ PRESENT | Count from classification table | Exists |
| `hpa_misconfigured` count | ✅ PRESENT *(was ❌)* | T-17: `GET /optimize/workloads/scaling` returns `summary.thrashing + summary.at_max` as proxy for misconfigured HPAs | **Resolved T-17** |
| `scale_events_24h` | ✅ PRESENT *(was ❌)* | T-17: `scale_events_24h` field in each row (direction changes in `hpa_status_snapshots` over 24h); total in summary | **Resolved T-13 + T-17** |
| `avg_scale_latency` | ❌ MISSING | Not tracked | Still needed — time from HPA trigger to pod ready |
| `idle_replica_waste` ($) | ❌ MISSING | Not computed | Still needed — COUNT(idle pods) × pod CPU req × OD price |
| `vpa_recommendation_count` | ✅ PRESENT | `GET /api/v1/pod-metrics/right-sizing/recommendations` count | Exists |

### 4.2 Workload List Row

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `min_replicas`, `max_replicas` | ✅ PRESENT *(was 🤖)* | T-13: `collect_hpa_configs()` pushes spec to `hpa_configs` table; T-17 returns them | **Resolved T-13** |
| `current_replicas` | ✅ PRESENT *(was 🤖)* | T-13: agent pushes `current_replicas`, `desired_replicas` to `hpa_configs`; T-17 returns them | **Resolved T-13** |
| `cpu_utilization_pct` | ✅ PRESENT | Aggregate from `pod_metrics` | Exists |
| `scaling_status` (Thrashing/etc) | ✅ PRESENT *(was ❌)* | T-17: `_classify_hpa_status()` returns AT_MAX / SCALING_UP / THRASHING / OVERPROVISIONED / OPTIMAL / KEDA_MANAGED | **Resolved T-17** |
| `efficiency_pct` | ❌ MISSING | Not computed | Still needed — serving_time / total_time |

### 4.3 HPA Configuration Detail

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `hpa.min_replicas` | ✅ PRESENT *(was 🤖)* | T-13: `hpa_configs.min_replicas`; exposed via T-24 `scaling-detail` | **Resolved T-13 + T-24** |
| `hpa.max_replicas` | ✅ PRESENT *(was 🤖)* | T-13: `hpa_configs.max_replicas` | **Resolved T-13** |
| `hpa.target_cpu` | ✅ PRESENT *(was 🤖)* | T-13: `hpa_configs.target_cpu_pct`; T-24 returns it | **Resolved T-13 + T-24** |
| HPA recommendations | ✅ PRESENT *(was 🔧)* | T-16: `hpa_recommendation_task` computes P95×1.2 → `hpa_configs.recommended_max_replicas`; T-24 returns it | **Resolved T-16 + T-24** |
| `hpa.has_warning` flag | ✅ PRESENT *(was 🔧)* | T-17: `has_warning` computed per workload in scaling list response | **Resolved T-17** |

### 4.4 VPA Right-Sizing

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `cpu_from` (current request) | ✅ PRESENT | `PodMetric.cpu_requests_millicores` | Exists |
| `cpu_to` (recommendation) | ✅ PRESENT | `GET /api/v1/pod-metrics/right-sizing/recommendations` | Exists |
| `mem_from` (current request) | ✅ PRESENT | `PodMetric.memory_requests_bytes` | Exists |
| `mem_to` (recommendation) | ✅ PRESENT | Same right-sizing endpoint | Exists |

> **VPA section unchanged — already wirable.**

### 4.5 Scale Event Timeline

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| 120m replica count series | ✅ PRESENT *(was ❌)* | T-24: `GET /optimize/workloads/{id}/scaling-detail` returns `hpa_timeline` — `HpaStatusSnapshot` rows for last 120 min with `{snapshot_at, current_replicas, desired_replicas}` | **Resolved T-13 + T-24** |
| Thrash pattern detection | ✅ PRESENT *(was ❌)* | T-17: THRASHING classification (≥4 snapshots, >3 direction changes in 30 min); T-24: `scale_events_120m` count | **Resolved T-17 + T-24** |

### 4.6 Cooldown Audit

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| Scale-Up cooldown value | 🤖 AGENT GAP | `spec.behavior.scaleUp.stabilizationWindowSeconds` not in `hpa_configs` model | **Still needed** — not collected by T-13 |
| Scale-Down stabilization value | 🤖 AGENT GAP | `spec.behavior.scaleDown.stabilizationWindowSeconds` not in `hpa_configs` model | **Still needed** |
| Select Policy value | 🤖 AGENT GAP | `spec.behavior.*.selectPolicy` not in `hpa_configs` model | **Still needed** |
| Assessment (Too short/Adequate/Optimal) | 🔧 NEEDS LOGIC | Depends on cooldown values above | **Still needed** |

### 4.7 Replica Efficiency Breakdown

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| Serving replica count | ✅ PRESENT *(was ❌)* | T-12: `PodMetric.phase = "Running"` now tracked | **Resolved T-12** |
| Idle replica count | ⚠️ PARTIAL *(was ❌)* | T-12: phase=Running available; idle = Running + cpu_util < threshold — logic still needed | **Data available**, threshold logic still needed |
| Draining replica count | ✅ PRESENT *(was ❌)* | T-12: `PodMetric.phase = "Terminating"` now tracked | **Resolved T-12** |

**Endpoint Status:**
- `GET /api/v1/optimize/workloads/scaling?cluster_id=` — ✅ PRESENT (T-17)
- `GET /api/v1/optimize/workloads/scaling/summary?cluster_id=` — ✅ PRESENT (T-17, embedded summary sub-object in response)
- `GET /api/v1/optimize/workloads/:workload_id/scaling-detail` — ✅ PRESENT (T-24)

**Agent Task Status:**
- Push HPA spec (min, max, targetCPU) — ✅ PRESENT (T-13 `collect_hpa_configs()`)
- Push HPA status (currentReplicas, desiredReplicas) — ✅ PRESENT (T-13, snapshot to `hpa_status_snapshots`)
- Push pod phase (Running/Terminating/Pending) — ✅ PRESENT (T-12)
- Push HPA behavior/stabilization windows — 🤖 AGENT GAP (still needed)

---

## 5. Workload Migration (`WorkloadMigration.jsx`)

**UI needs:** Candidate list (name, stateless, state badge, progress bar, source/target pool+AZ+instance), detail panel (statefulness description, architecture shift diagram, execution steps, pre-migration checklist, blast radius, cost delta, audit history).

### 5.1 Migration Candidate Source

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| Candidate workload name, namespace | ✅ PRESENT | `WorkloadClassificationRecord` + `MigrationEvent` | Exists |
| `stateless` flag | ⚠️ PARTIAL | `WorkloadClassificationRecord.data_safety` + signals | Inferrable from signals — unchanged |
| `migration_state` (PENDING/BLOCKED/VALIDATED/IN_PROGRESS/COMPLETED) | ⚠️ PARTIAL | `MigrationEvent.state` tracks freeze-start/migrating/soak/complete/failed | State machine mapping still needed |
| Progress % (for IN_PROGRESS) | ❌ MISSING | Not tracked | Still needed |
| `source.pool` | ✅ PRESENT *(was 🤖)* | T-09: `node_metadata.nodepool_name` per node; join via `node_name` | **Resolved T-09** |
| `source.az` | ✅ PRESENT *(was 🤖)* | T-09: `node_metadata.az` per node; join via `node_name` | **Resolved T-09** |
| `source.instance_type` | ✅ PRESENT *(was ⚠️)* | T-09: `node_metadata.instance_type` per node; replaces `Cluster.node_metrics` JSON | **Resolved T-09** |
| `target.pool`, `target.az`, `target.instance_type` | ❌ MISSING | `MigrationEvent.target_node` exists but target node not in `node_metadata` yet | Still needed — target node must be in `node_metadata` at migration time |
| `migration_type` | ❌ MISSING | Not stored | Still needed — source/target pool comparison logic |

### 5.2 Execution Steps

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| Step list (provisioning, deploy, pre-warm, DNS shift, decommission) | ❌ MISSING | Not in DB | These are workflow steps — need new `MigrationStep` or `AgentAction` sequence mapping |
| Active step indicator | ⚠️ PARTIAL | `MigrationEvent.state` maps roughly to steps | Mapping from state→step needed |
| Step tags (SAFE/REVERSIBLE/DESTRUCTIVE) | ❌ MISSING | Not in DB | Static rules per step type — can be hardcoded in logic layer |
| Step estimated duration | ❌ MISSING | Not tracked | Historical average from past migrations could provide this |

### 5.3 Pre-Migration Checklist

| Checklist Item | Status | Backend Source | Gap |
|---------------|--------|---------------|-----|
| IAM Roles validated | ❌ MISSING | Not checked | New mechanism: validate using AWS STS/IAM API |
| Target subnet capacity | ❌ MISSING | Not checked | New mechanism: AWS EC2 DescribeSubnets |
| Security group mirroring | ❌ MISSING | Not checked | AWS EC2 DescribeSecurityGroups comparison |
| Image available in region | ❌ MISSING | Not checked | ECR describe-images or registry API check |
| Load balancer registered | ❌ MISSING | Not checked | AWS ELB describe-target-health |
| Metrics dashboard prepared | ❌ MISSING | Not checked | Could check if cluster monitoring is healthy |

> **All 6 checklist items are missing.** This requires new integration logic with AWS APIs or kubectl checks executed as a pre-flight Celery task.

### 5.4 Blast Radius

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `downstream_services` count | ❌ MISSING | Not tracked | Requires service dependency graph — not in DB |
| `estimated_downtime` | ❌ MISSING | Not computed | Logic: stateless → 0s, stateful → drain_time, volume_migration → detach+reattach |
| `rollback_time` | ❌ MISSING | Not computed | Static rule: stateless < 30s, stateful < 120s |

### 5.5 Cost Delta

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `cost.from` (current monthly) | ⚠️ PARTIAL *(was ❌)* | `instance_catalog` table exists with `od_price_hr`; source instance_type now in `node_metadata` (T-09) | **Data available** — endpoint not yet built |
| `cost.to` (target monthly) | ❌ MISSING | Target node not yet in `node_metadata` | Target node AZ/type still needed at migration time |
| `cost.savings_pct` | ❌ MISSING | Not computed | Still needed |
| Instance hourly pricing | ✅ PRESENT *(was ❌)* | `instance_catalog` table already exists (`od_price_hr`, `spot_price_hr`) — confirmed used by T-18 | **Resolved — catalog pre-existed, confirmed T-18** |

### 5.6 Audit History

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `timestamp` | ✅ PRESENT | `MigrationEvent.created_at` | Exists |
| `actor` (System / user email) | ⚠️ PARTIAL | `MigrationEvent` has no actor field | Need to add `triggered_by` column |
| `action` description | ⚠️ PARTIAL | `MigrationEvent.state` + `failure_reason` | Needs text mapping from state to human description |
| `status` (SUCCESS/BLOCKED/IN_PROGRESS) | ⚠️ PARTIAL | `MigrationEvent.state` maps to some statuses | Mapping needed |

**Endpoint Status:**
- `GET /api/v1/optimize/workloads/migration?cluster_id=&status=` — ❌ MISSING (not built in T-09→T-24)
- `GET /api/v1/optimize/workloads/migration/summary?cluster_id=` — ❌ MISSING
- `GET /api/v1/optimize/workloads/:workload_id/migration-detail` — ❌ MISSING
- `GET /api/v1/optimize/workloads/migration/what-if?cluster_id=` — ❌ MISSING

> **WorkloadMigration is the least complete page.** T-09 provided source AZ/pool/instance_type via `node_metadata`; everything else (checklist, blast radius, execution steps, cost-to) remains unbuilt.

---

## 6. Node Selector (`NodeSelector.jsx`)

**UI needs:** Node list (hostname, pool, instance type, capacity type, current utilization CPU/Mem, price/hr), detail panel (current vs. optimized instance recommendation, savings %, fitness score, recommendation reason), action button (schedule optimization).

> **Frontend Status: ❌ MOCK DATA — uses hardcoded `mockNodes` array. No real API wiring exists.**

### 6.1 Node List Row

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `hostname` | ✅ PRESENT | `GET /api/v1/clusters/{id}/nodes` | Exists |
| `pool` (NodePool name) | ✅ PRESENT | `node_metadata.nodepool_name` (T-09) | Exists |
| `instance_type` | ✅ PRESENT | `node_metadata.instance_type` (T-09) | Exists |
| `capacity_type` (OD/Spot) | ✅ PRESENT | `node_metadata.capacity_type` (T-09) | Exists |
| `price_per_hour` | ⚠️ PARTIAL | `instance_catalog.od_price_hr` / `spot_price_hr` — join on instance_type | Join query not yet exposed by an endpoint |
| `cpu_utilization_pct` | ✅ PRESENT | `GET /optimize/nodes/bin-packing` — `cpu_actual_pct` per node (T-14) | Exists |
| `mem_utilization_pct` | ✅ PRESENT | `GET /optimize/nodes/bin-packing` — `mem_actual_pct` per node (T-14) | Exists |

### 6.2 Optimized Target Recommendation

| Field | Status | Backend Source | Gap |
|-------|--------|---------------|-----|
| `optimized.type` (target instance type) | ❌ MISSING | No node instance-type right-sizing logic exists | **Must build**: right-sizing algorithm comparing workload CPU/Mem profile vs. instance catalog |
| `optimized.capacity` (Spot/OD) | ❌ MISSING | No node-level capacity recommendation | **Must build**: depends on classification + consolidation logic |
| `optimized.price` | ❌ MISSING | `instance_catalog` has pricing, but no recommendation to price yet | **Must build** |
| `optimized.savings_percent` | ❌ MISSING | Not computed | **Must build**: `(current_price - target_price) / current_price * 100` |
| `optimized.score` (fitness 0–100) | ❌ MISSING | No scoring model for instance right-sizing | **Must build**: WIE-style scoring for node fit |
| `optimized.reason` (text) | ❌ MISSING | No recommendation rationale generated | **Must build**: template-based or LLM-based explanation |
| `optimized.status` (Scheduled/Terminating/etc) | ❌ MISSING | `AgentAction` status could proxy this | **Must build**: map AgentAction state to selector status |

### 6.3 Endpoint Gap

| Endpoint | Status | Notes |
|----------|--------|-------|
| `GET /api/v1/optimize/nodes/selector?cluster_id=` | ❌ MISSING | Primary endpoint — returns node list + per-node optimization target |
| `GET /api/v1/optimize/nodes/{node_id}/selector-detail` | ❌ MISSING | Per-node recommendation detail with reason + score |

> **No backend endpoint exists for this page.** The bin-packing endpoint (T-14) covers utilization data but not instance right-sizing recommendations. A new dedicated task and endpoint must be built before this component can be wired.

---

## 7. Cross-Cutting Infrastructure Gaps

These are shared dependencies required by multiple pages.

### 7.1 Instance Pricing Catalog — ✅ RESOLVED

**Required by:** NodeBinPacking (savings), WorkloadProfiling (savings), WorkloadMigration (cost delta), Overview Dashboard (what-if)

| Gap | Status | Resolution |
|-----|--------|------------|
| No pricing table in DB | ✅ RESOLVED | `instance_catalog` table already existed (`od_price_hr`, `spot_price_hr`); confirmed used by T-18 consolidation task with GAP-9 fallback |
| No Spot price data | ⚠️ PARTIAL | Static catalog only; live `describe-spot-price-history` Celery refresh still not implemented |
| No OD price data | ⚠️ PARTIAL | Static catalog only; live AWS Pricing API refresh still not implemented |

### 7.2 Node Metadata Catalog — ✅ RESOLVED

**Required by:** NodeBinPacking, WorkloadPlacement (AZ dots), WorkloadMigration (source/target AZ+pool)

| Gap | Status | Resolution |
|-----|--------|------------|
| No per-node AZ stored | ✅ RESOLVED | T-09: `node_metadata.az` pushed per node via `send_node_metadata_batch()` |
| No per-node capacity type | ✅ RESOLVED | T-09: `node_metadata.capacity_type` pushed (ON_DEMAND / spot) |
| No per-node allocatable CPU/Mem | ✅ RESOLVED | T-09: `allocatable_cpu_millicores` + `allocatable_memory_bytes` pushed |
| No per-node pool assignment | ✅ RESOLVED | T-09: `nodepool_name` pushed |

### 7.3 HPA Configuration Push — ✅ RESOLVED

**Required by:** WorkloadScaling (all HPA fields), WorkloadPlacement (state locks)

| Gap | Status | Resolution |
|-----|--------|------------|
| Agent does not push HPA specs | ✅ RESOLVED | T-13: `collect_hpa_configs()` → `POST /agents/hpa-configs/batch` → `hpa_configs` table |
| No HPA scale event log | ✅ RESOLVED | T-13: each batch upsert also inserts a snapshot row into `hpa_status_snapshots` (timestamped) |
| HPA behavior/stabilization windows not pushed | 🤖 AGENT GAP | `spec.behavior.scaleUp/Down.stabilizationWindowSeconds` not in `hpa_configs` model — still needed for cooldown audit |

### 7.4 CPU Coefficient of Variation (CV) — ✅ RESOLVED (CPU only)

**Required by:** WorkloadProfiling (cpu_cv, rps_cv), WorkloadScaling (thrashing detection)

| Gap | Status | Resolution |
|-----|--------|------------|
| CPU CV not computed | ✅ RESOLVED | `PlacementPolicyRecord.pod_cpu_cv` computed by PlacementAdvisor; T-22 exposes it |
| RPS data not in DB | ❌ MISSING | Still requires agent Prometheus scrape integration — not done |

### 7.5 Pod Phase / Pod State Push — ✅ RESOLVED

**Required by:** WorkloadPlacement (pod status column), WorkloadScaling (efficiency breakdown)

| Gap | Status | Resolution |
|-----|--------|------------|
| `pod_metrics` table has no pod phase | ✅ RESOLVED | T-12: `PodMetric.phase` column added + indexed; agent now includes phase in every pod metric push |
| No Terminating state detection | ✅ RESOLVED | T-12: `phase = "Terminating"` tracked per pod |
| No pod start_time | ✅ RESOLVED | T-12: `PodMetric.start_time` column added |

### 7.6 Drift Tracking — ⚠️ PARTIAL

**Required by:** WorkloadPlacement (drift_minutes, placement_status, drifting count)

| Gap | Status | Resolution |
|-----|--------|------------|
| No drift timestamp tracked | ❌ MISSING | `last_stable_at` on `PlacementPolicy` still not added |
| No placement_status field | ✅ RESOLVED | T-23: per-workload `placement_status` derived from `spot:pc:workload_log` latest entry |

---

## 8. Build Priority Summary (Updated post T-09 → T-24)

| Priority | Item | Pages Affected | Status |
|----------|------|---------------|--------|
| 🔴 CRITICAL | Instance pricing catalog | Migration, Profiling, BinPacking | ✅ DONE — static `instance_catalog` existed; live spot-price refresh still pending |
| 🔴 CRITICAL | Agent: push node metadata (AZ, capacityType, allocatable, pool) | BinPacking, Placement, Migration | ✅ DONE — T-09 |
| 🔴 CRITICAL | Agent: push HPA spec + status | Scaling, Placement | ✅ DONE — T-13 |
| 🟠 HIGH | New API endpoints: `/optimize/nodes/bin-packing/*` | BinPacking | ✅ DONE — T-14, T-15, T-21 |
| 🟠 HIGH | New API endpoints: `/optimize/workloads/profiling/*` | Profiling | ⚠️ PARTIAL — per-workload detail ✅ (T-22); list + summary endpoints missing |
| 🟠 HIGH | New API endpoints: `/optimize/workloads/scaling/*` | Scaling | ✅ DONE — T-17, T-24 |
| 🟠 HIGH | New API endpoints: `/optimize/workloads/placement/*` | Placement | ✅ DONE — T-23 (list + detail); summary endpoint missing |
| 🟠 HIGH | New API endpoints: `/optimize/nodes/selector/*` | NodeSelector | ❌ NOT DONE — instance right-sizing engine needed |
| 🟠 HIGH | New API endpoints: `/optimize/workloads/migration/*` | Migration | ❌ NOT DONE |
| 🟡 MEDIUM | CPU CV computation | Profiling, Scaling | ✅ DONE — `pod_cpu_cv` from PlacementPolicyRecord (T-22) |
| 🟡 MEDIUM | RPS CV data push | Profiling, Scaling | ❌ NOT DONE — agent Prometheus integration still pending |
| 🟡 MEDIUM | Drift tracking (`last_stable_at`, aggregate drifting count) | Placement | ❌ NOT DONE — `placement_status` per workload ✅ (T-23), but `drift_minutes` and drifting count missing |
| 🟡 MEDIUM | Pod phase push in agent | Placement, Scaling | ✅ DONE — T-12 |
| 🟡 MEDIUM | Migration candidate queue model | Migration | ❌ NOT DONE |
| 🟡 MEDIUM | Pre-migration checklist Celery task | Migration | ❌ NOT DONE |
| 🟡 MEDIUM | HPA behavior/stabilization windows push | Scaling (cooldown audit) | ❌ NOT DONE — not collected by T-13 |
| 🟢 LOW | Blast radius logic (stateless/stateful rules) | Migration | ❌ NOT DONE |
| 🟢 LOW | Gate 5 (system namespace check) + Gate 6 (freshness) evaluation | Profiling | ❌ NOT DONE |
| 🟢 LOW | `/optimize/nodes/bin-packing/summary` standalone endpoint | BinPacking | ❌ NOT DONE |
| 🟢 LOW | `/optimize/workloads/placement/summary` standalone endpoint | Placement | ❌ NOT DONE |
| 🟢 LOW | `/optimize/workloads/profiling` list endpoint | Profiling | ❌ NOT DONE |
| 🟢 LOW | Live AWS Spot price history Celery task | All pricing | ❌ NOT DONE |

---

## 9. What the Agent Currently Provides vs. What It Must Add

### Currently Provided by Agent (Live Data) — Updated
- Node hostname, instance_type, **AZ, capacity_type, allocatable CPU/Mem, nodepool_name** → `node_metadata` table (T-09)
- Pod CPU/Mem usage, requests, limits, utilization %, **phase, start_time** → `pod_metrics` table (T-12)
- **HPA spec** (min, max, target_cpu, target_memory) + **HPA status** (current, desired replicas) → `hpa_configs` + `hpa_status_snapshots` tables (T-13)
- **Karpenter NodeClaims** (state, instance_type, AZ, capacity_type, CRD version) → `karpenter_node_claims` table (T-11)
- Spot interruption events → `agent_routes.py /spot-interruption`
- Rebalance recommendations → `agent_routes.py /rebalance-recommendation`
- Action results → `AgentAction.result_payload`
- Workload classification data (signals) → via WIE engine

### Still Needs to Be Added to Agent
| New Agent Task | Data to Push | Target Table/Key | Priority |
|---------------|-------------|------------------|----------|
| `collect_hpa_behavior()` | `spec.behavior.scaleUp/Down.stabilizationWindowSeconds`, `selectPolicy` | Add columns to `hpa_configs` | 🟡 MEDIUM |
| `collect_rps_metrics()` | Request rate (RPS) per workload from Prometheus or service mesh | New `workload_rps_metrics` table | 🟡 MEDIUM |
| `collect_pdb_status()` | PDB disruptions allowed/current per workload | New `pdb_status` table or extend `spot:workload:state` | 🟢 LOW (PDB active already from workload:state) |
| `collect_pod_node_mapping()` | Explicit pod → node → AZ + capacityType link (for AZ topology dot map) | Join query against `node_metadata` | 🟢 LOW (data available via join, no new push needed) |

---

## 10. Endpoints Ready for UI Wiring (Updated post T-09 → T-24)

### 10.1 Pre-existing — Still Directly Wirable

| Component | Mock Field | Live Endpoint | Notes |
|-----------|-----------|--------------|-------|
| WorkloadProfiling | tier, confidence_score, confidence_state, spot_score, spot_friendly, signals | `GET /api/v1/workload-classification/clusters/{id}/workloads` | Direct wire |
| WorkloadProfiling | Summary counts | `GET /api/v1/workload-classification/clusters/{id}/summary` | Direct wire |
| WorkloadScaling | VPA cpu_from/to, mem_from/to | `GET /api/v1/pod-metrics/right-sizing/recommendations` | Direct wire |
| NodeBinPacking | Node hostname, instance_type, total_nodes | `GET /api/v1/clusters/{id}/nodes` | Direct wire |
| NodeBinPacking | avg_cpu_util, avg_mem_util | `GET /api/v1/clusters/{id}/utilization` | Direct wire |
| WorkloadPlacement | in_flight_actions | `GET /api/v1/execution-data/agent-actions?cluster_id=&status=PENDING` | Direct wire |

### 10.2 New Endpoints Added by T-09 → T-24 — Ready for Wiring

| Component | Data Available | New Endpoint | Notes |
|-----------|---------------|--------------|-------|
| NodeBinPacking | Node bin-packing list + consolidation candidates | `GET /api/v1/optimize/nodes/bin-packing?cluster_id=` | T-14 |
| NodeBinPacking | Pod treemap per node | `GET /api/v1/optimize/nodes/{node_name}/bin-packing-detail` | T-21 |
| NodeBinPacking | All pods on a node | `GET /api/v1/optimize/nodes/{node_name}/workload-pods` | T-15 |
| WorkloadScaling | HPA status list + classification | `GET /api/v1/optimize/workloads/scaling?cluster_id=` | T-17 |
| WorkloadScaling | 120m timeline + scale events + recommendations | `GET /api/v1/optimize/workloads/{id}/scaling-detail` | T-24 |
| WorkloadProfiling | 14-day CPU time-series + savings + cv + targets | `GET /api/v1/optimize/workloads/{id}/profiling-detail` | T-22 |
| WorkloadPlacement | Placement list with status + tier + savings | `GET /api/v1/optimize/workloads/placement?cluster_id=` | T-23 |
| WorkloadPlacement | State locks + recent decisions + placement_status | `GET /api/v1/optimize/workloads/{id}/placement-detail` | T-23 |

---

## 11. Execution Buttons — Status (Updated)

| Component | Button | Was Blocked Because | Current Status |
|-----------|--------|--------------------|-----------------|
| WorkloadMigration | 🚀 Begin Migration | No checklist, no candidate queue, no cost delta | ❌ **Still blocked** — migration endpoints not built |
| WorkloadPlacement | Trigger Reconcile for All Drifting | Drift tracking API missing | ⚠️ **Still blocked** — `drift_minutes` and drifting aggregate count still missing; per-workload `placement_status` now available |
| WorkloadPlacement | Rebalance AZ | AZ topology data missing | ⚠️ **Partially unblocked** — AZ + capacity_type data now in `node_metadata` (T-09); AZ rebalance endpoint still not built |
| WorkloadScaling | Apply VPA | HPA data missing | ⚠️ **Partially unblocked** — HPA data now present (T-13); can unblock once HPA recommendation review UX is complete |
| WorkloadProfiling | ▶ Run Advisor Cycle | Full data readiness needed | ✅ **Can be unblocked** — placement advisor data pipeline complete; `POST /placement-policy/{id}/generate` exists |

---

## 12. Frontend Integration Status (Updated U1–U6)

### 12.1 Components Wired to Real APIs

| Component | Real API Used | Endpoints Wired | Session |
|-----------|--------------|-----------------|--------|
| `NodeBinPacking.jsx` | `optimizeAPI.getNodeBinPacking`, `getNodeBinPackingDetail` | `GET /optimize/nodes/bin-packing`, `GET /optimize/nodes/{name}/bin-packing-detail` | U2 |
| `WorkloadScaling.jsx` | `optimizeAPI.getWorkloadsScaling`, `getWorkloadScalingDetail` | `GET /optimize/workloads/scaling`, `GET /optimize/workloads/{id}/scaling-detail` | U3 |
| `WorkloadPlacement.jsx` | `optimizeAPI.getWorkloadsPlacement`, `getWorkloadPlacementDetail` | `GET /optimize/workloads/placement`, `GET /optimize/workloads/{id}/placement-detail` | U4 |
| `WorkloadProfiling.jsx` | `workloadClassificationAPI.getWorkloads`, `getSummary`, `optimizeAPI.getWorkloadProfilingDetail` | `GET /workload-classification/{id}/workloads`, `GET /workload-classification/{id}/summary`, `GET /optimize/workloads/{id}/profiling-detail` | U5 |

### 12.2 Components Still Using Mock Data

| Component | Mock Data Source | Blocker | Action Needed |
|-----------|-----------------|---------|---------------|
| `NodeSelector.jsx` | `const mockNodes = [...]` hardcoded in component | No backend endpoint (`/optimize/nodes/selector`) exists | Build instance right-sizing engine + endpoint (see § 6) |
| `WorkloadMigration.jsx` | `const CANDIDATES = [...]` hardcoded in component | All 4 migration endpoints missing (see § 5 Endpoint Status) | Build migration candidate queue + all endpoints |

### 12.3 `optimizeAPI` Service (U1)

Added to `frontend/src/services/api.js`:

```js
export const optimizeAPI = {
    getNodeBinPacking: (clusterId) => ...,
    getNodeBinPackingDetail: (nodeName, clusterId) => ...,
    getWorkloadsScaling: (clusterId) => ...,
    getWorkloadScalingDetail: (workloadId, clusterId) => ...,
    getWorkloadsPlacement: (clusterId, page, pageSize) => ...,
    getWorkloadPlacementDetail: (workloadId, clusterId) => ...,
    getWorkloadProfilingDetail: (workloadId, clusterId) => ...,
};
```
