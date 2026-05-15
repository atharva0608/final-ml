from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class PlacementPolicyBase(BaseModel):
    # Identity
    workload_id: str
    cluster_id: str
    namespace: str
    name: str

    # Phase 1 Inputs
    criticality_tier: str
    confidence_state: str
    spot_friendly: bool

    # Distribution
    observed_replicas: int
    ondemand_target: int
    spot_target: int
    spot_target_raw: int

    # Traffic skew
    traffic_skew_detected: bool
    skew_signal_source: Optional[str] = None
    pod_cpu_cv: Optional[float] = None
    pod_request_rate_cv: Optional[float] = None

    # NodePool
    assigned_nodepool_class: str
    spot_instance_families: List[str]
    spot_instance_types: List[str]

    # Constraints
    baseline_affinity: Dict[str, Any]
    burst_affinity: Dict[str, Any]
    topology_spread: Optional[Dict[str, Any]] = None
    spread_relaxation_tier: int

    # KEDA
    keda_min_replicas: Optional[int] = None
    keda_max_replicas: Optional[int] = None

    # Rollout
    rollout_eligible: bool
    rollout_blocked_reason: Optional[str] = None

    # Cost
    estimated_savings_pct: float
    estimated_monthly_saving_usd: float

    # Actionability
    actionable: bool
    actionable_blocked_reason: Optional[str] = None

    # Audit
    signals_used: List[str]
    schema_version: str
    input_hash: Optional[str] = None


class PlacementPolicyResponse(PlacementPolicyBase):
    id: str
    generated_at: datetime
    created_at: datetime
    updated_at: datetime
    schema_warning: Optional[bool] = False

    class Config:
        from_attributes = True


class PlacementPolicySummaryResponse(BaseModel):
    total_workloads: int = 0
    spot_workload_count: int = 0
    od_workload_count: int = 0
    total_spot_target: int = 0
    total_od_target: int = 0
    total_estimated_savings_usd: float = 0.0
    actionable_count: int = 0
    rollout_eligible_count: int = 0
    observation_mode: bool = False


class PlacementPolicyListResponse(BaseModel):
    items: List[PlacementPolicyResponse]
    total: int
    page: int
    page_size: int


class PlacementPolicyGenerateRequest(BaseModel):
    workload_ids: Optional[List[str]] = Field(
        default=None, 
        description="Optional list of workload_ids to generate policies for. If empty, generates for all."
    )
    force_regenerate: bool = Field(
        default=False, 
        description="If true, bypasses the write suppression and forces a generation."
    )
