"""
Pipeline Contracts — cross-component data boundaries.
======================================================
Documentation artifact. No runtime logic here.

Each constant below describes the exact payload that crosses a pipeline stage boundary.
Callers and callees must agree on these fields. Updating a field name in one service
without updating the counterpart causes silent data bugs.

Import this module in tests to get a single source of truth for integration assertions.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Step 1 → Step 2 (WIE → PPE)
# ---------------------------------------------------------------------------

WIE_TO_PPE: str = """
Input to PodPlacementEngine.materialize_plan():
  pods: List[Dict]
    pod_name: str
    namespace: str
    node_name: str
    capacity_type: "spot" | "on-demand"
    az: str
    cpu_request_millicores: int
    memory_request_bytes: int
    controller_kind: str
    has_pvc: bool
    labels: Dict[str, str]
    restart_count: int

  wie: Dict  — single WIE profile (one call per workload)
    workload_id: str
    namespace: str
    controller_name: str
    controller_kind: str
    workload_class: "db" | "stateful" | "stateless" | "mixed"
    min_on_demand_replicas: int
    max_spot_replicas: int
    tier: "Platinum" | "Gold" | "Silver" | "Bronze"
    spot_score: float
    disruption_safe: bool
    has_pvc: bool
    pdb_min_available: int | None
    az_spread_required: bool
    inbound_services: List[str]   # workload_ids that call this workload
    data_safety: "STATEFUL" | "STATELESS" | None
    pod_names: List[str]          # all pod names belonging to this workload
"""

# ---------------------------------------------------------------------------
# Step 2 → Step 3 (PPE → DE)
# ---------------------------------------------------------------------------

PPE_TO_DE: str = """
Input to DistributionEngine.build():
  plan: PlacementPlan (returned by PPE.materialize_plan(), dict form)
    schema_version: str
    movement_plan: List[Dict]
      step: int
      pod_name: str
      namespace: str
      workload_id: str
      from_node: str
      to_node: str | None           — None if blocked_by=no_capacity
      blocked_by: str | None
      from_capacity_type: str
      to_capacity_type: str
      cpu_request_millicores: int
      memory_request_bytes: int

    node_plan: List[Dict]
      action: "provision" | "keep" | "drain"
      node_name: str
      capacity_type: str
      az: str
      instance_type: str | None     — None until ISS resolves
      required_cpu_millicores: int
      required_memory_bytes: int
      pod_count: int
      packed_pods: List[Dict]       — REQUIRED on provision entries
        pod_name: str
        cpu_request_millicores: int
        memory_request_bytes: int
      retention_reason: str | None  — on keep entries:
        "anchor_node" | "fits_pods" | "drain_reuse" | "min_od_baseline"
      retained_workload_classes: List[str] | None  — on keep entries

    node_layout: Dict
    anchor_plan: Dict
    feasibility: Dict
      feasible: bool
      status: str
      plan_id: str
      cluster_id: str
      warnings: List[str]
    cost_projection: Dict
    validation_errors: List[Dict]

  wie_profiles: Dict[str, Dict]  — all WIE profiles keyed by workload_id
  nodes: List[Dict]
  pods: List[Dict]
"""

# ---------------------------------------------------------------------------
# Step 3 → Step 5 (DE → EE)
# Note: Step 4 (ISS) runs INSIDE Step 3 — instance_type is resolved
#       before DE.build() returns. EE never sees unresolved instance_types.
# ---------------------------------------------------------------------------

DE_TO_EE: str = """
Input to ExecutionEngine.run():
  manifest: Dict — produced by DistributionEngine.build()
    manifest_id: str              — "mfst-{sha256[:12]}"
    plan_id: str
    schema_version: str
    status: "READY"
    plan_status: "resolved" | "partial" | "draft" | "no_action"
    generated_at: str             — ISO timestamp
    expires_in_seconds: int
    workload_priority_order: List[str]
    migration_groups: List[Dict]
      group_id: str
      workload_id: str
      type: "BLUE_GREEN" | "BATCH" | "SERIAL" | "ROLLING"
      strategy: Dict
      steps: List[Dict]           — per-pod steps
      batches: List[Dict]         — for BATCH/ROLLING only

    parallel_waves: List[Dict]
      wave_index: int
      workload_class: str
      group_ids: List[str]
      max_concurrent: int
      barrier_after: bool

    classification_errors: List[Dict]   — DB workloads that leaked into movement_plan
    blocked_workloads: List[Dict]
    budget_consumed: Dict
    budget_remaining: Dict
    precondition_snapshot: Dict
    node_plan: List[Dict]         — from PPE, instance_type resolved by ISS
    node_layout: Dict
    anchor_plan: Dict
    cost_projection: Dict

KEYS THAT DO NOT EXIST in the manifest (common source of bugs):
  provision_nodes  — does not exist; use node_plan[action=provision]
  drain_nodes      — does not exist; use node_plan[action=drain]
  keep_nodes       — does not exist; use node_plan[action=keep]
"""
