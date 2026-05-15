# Frontend Missing Data Report

This file tracks UI sections that still show placeholder / N/A values because no
backend API exists to supply the required data.  Each entry records the page,
the missing field(s), a proposed endpoint, and the data source that would back it.

---

## Node Selection page (`/optimize/nodes/selector`)

### Missing: Per-node optimization recommendation

**UI section:** "Optimization Target" right panel in the expanded row view  
**Currently shows:** Amber warning banner with "Missing data" message

| Field | Description | Proposed endpoint |
|---|---|---|
| `target_instance_type` | Recommended replacement instance type | `GET /optimize/nodes/{node_name}/recommendation?cluster_id=` |
| `target_capacity_type` | Spot / On-Demand for the target | same |
| `target_vcpu` | vCPU count of target instance | same |
| `target_memory_gib` | Memory of target instance | same |
| `savings_percent` | Estimated % hourly cost reduction | same |
| `optimization_score` | 0-100 fit score | same |
| `rationale` | Human-readable explanation of recommendation | same |

**Proposed data source:**  
The `consolidation_analysis_task` identifies `candidate_nodes` and picks replacement
pools. Exposing per-node replacement info from that analysis (or from
`RebalancingAction.target_pool` for in-flight migrations) would satisfy this.

**Priority:** Medium — the table rows and summary strip are fully real-data now.
The detail panel is the only remaining placeholder.

---

### Missing: Pool / node-group label per node

**UI section:** Node row sub-label (currently shows AZ)  
**Currently shows:** AZ instead of node-pool name  
**Source needed:** `NodeMetadata` doesn't have a pool/group column.  
Karpenter `NodePool` name is available in node labels (`karpenter.sh/nodepool`)
via the agent but is not currently stored in `node_metadata`.  

**Proposed fix:** Store the label value in a new `NodeMetadata.nodepool_name`
column and return it from the bin-packing endpoint.

---

## Summary of real data now wired (Node Selection)

| Field | Source |
|---|---|
| `node_name` | `GET /optimize/nodes/bin-packing` → `NodeMetadata` |
| `instance_type` | same |
| `capacity_type` | same |
| `az` | same |
| `pod_count` | same — aggregated from `PodMetric` |
| `cpu_actual_pct` / `cpu_requested_pct` | same |
| `mem_actual_pct` / `mem_requested_pct` | same |
| `cpu_buffer_pct` / `mem_buffer_pct` | same |
| `is_overloaded` | same |
| `lifecycle_state` (running/cordoned/draining) | same |
| `vcpu_count` | derived: `allocatable_cpu_millicores / 1000` (added this session) |
| `memory_gib` | derived: `allocatable_memory_bytes / GiB` (added this session) |
| `hourly_price_usd` | joined from `OnDemandPricing` / `SpotPriceHistory` (added this session) |
| `consolidation_candidates` count | `spot:consolidation:candidates:{cluster_id}` Redis key |
| `est_savings_monthly_usd` | same Redis key |

---

*Last updated: 2026-04-28*
