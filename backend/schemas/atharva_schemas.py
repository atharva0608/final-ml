from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


# ─── Existing Enums ───────────────────────────────────────────────────────────

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class PoolType(str, Enum):
    SPOT = "spot"
    ON_DEMAND = "on_demand"

class PoolStatus(str, Enum):
    ACTIVE = "active"
    DRAINING = "draining"
    SUSPENDED = "suspended"


# ─── Existing Models ─────────────────────────────────────────────────────────

class AtharvaStatus(BaseModel):
    risk_score: int
    risk_level: RiskLevel
    savings_rate: float
    active_optimization_count: int
    auto_rebalance_enabled: bool
    manual_mode_expires: Optional[datetime] = None
    current_cluster: Optional[str] = None
    monitored_nodes: int = 0
    active_pools: int = 0
    last_updated: datetime

class InstancePool(BaseModel):
    id: str
    name: str
    instance_type: str
    availability_zone: str
    price: float
    interrupt_risk: int
    risk_level: RiskLevel
    efficiency_score: int
    pool_type: PoolType
    status: PoolStatus

class InstanceRanking(BaseModel):
    top_safe_pools: List[InstancePool]
    top_cheap_pools: List[InstancePool]
    last_updated: datetime

class RecommendationType(str, Enum):
    REBALANCE = "rebalance"
    RIGHTSIZE = "rightsize"
    TYPE_SWITCH = "type_switch"

class RecommendationAction(str, Enum):
    APPLY = "apply"
    DISMISS = "dismiss"
    SCHEDULE = "schedule"

class Recommendation(BaseModel):
    id: str
    type: RecommendationType
    title: str
    description: str
    impact: str
    confidence: int
    risk_level: RiskLevel
    created_at: datetime
    applies_to: str

class RiskEvent(BaseModel):
    id: str
    timestamp: datetime
    level: RiskLevel
    message: str
    source: str
    resolved: bool

class AtharvaSettings(BaseModel):
    auto_rebalance: bool
    risk_threshold: int
    notification_channels: List[str]
    excluded_node_groups: List[str]


# ─── Node Template Schemas ───────────────────────────────────────────────────

class NodeTemplateRules(BaseModel):
    cpu_architecture: List[str] = Field(default=["x64"], description="Allowed architectures: x64, arm64")
    vcpu_min: int = Field(default=1, ge=1, le=96)
    vcpu_max: int = Field(default=96, ge=1, le=96)
    memory_min_gib: int = Field(default=1, ge=1, le=384)
    memory_max_gib: int = Field(default=384, ge=1, le=384)
    memory_to_vcpu_ratio_min: float = Field(default=2.0)
    memory_to_vcpu_ratio_max: float = Field(default=8.0)
    instance_families_allowed: List[str] = Field(default=["m5", "m5a", "m6i", "c5", "c5a", "r5", "t3"])
    instance_families_blocked: List[str] = Field(default=[])
    instance_sizes_allowed: List[str] = Field(default=["large", "xlarge", "2xlarge", "4xlarge"])
    instance_sizes_blocked: List[str] = Field(default=[])
    exclude_burstable: bool = False
    network_performance_min: str = Field(default="moderate")
    storage_type_allowed: List[str] = Field(default=["ebs_only", "instance_store", "both"])
    availability_zones_allowed: List[str] = Field(default=["all"])
    availability_zones_excluded: List[str] = Field(default=[])
    spot_only: bool = True
    max_interruption_rate: float = Field(default=0.25, ge=0.0, le=1.0)

class NodeTemplate(BaseModel):
    id: str
    name: str
    description: str = ""
    active: bool = True
    applied_clusters: List[str] = []
    rules: NodeTemplateRules = NodeTemplateRules()
    created_at: datetime
    updated_at: datetime
    created_by: str = "system"

class NodeTemplateCreate(BaseModel):
    name: str
    description: str = ""
    rules: NodeTemplateRules = NodeTemplateRules()

class NodeTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None
    rules: Optional[NodeTemplateRules] = None


# ─── Pool Rankings Schemas ────────────────────────────────────────────────────

class TrendDirection(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"

class PoolMetadata(BaseModel):
    vcpu: int
    memory_gib: float
    network_performance: str
    architecture: str

class RankedPool(BaseModel):
    rank: int
    pool_id: str
    instance_type: str
    instance_family: str
    availability_zone: str
    risk_score: float
    interruption_rate: float
    hourly_cost: float
    combined_score: float
    trend: TrendDirection
    rank_change: int = 0
    current_nodes: int = 0
    is_current: bool = False
    is_blacklisted: bool = False
    blacklist_expires_at: Optional[datetime] = None
    metadata: PoolMetadata

class FilteringStats(BaseModel):
    total_pools_available: int
    after_template_filter: int
    after_interruption_filter: int
    after_blacklist_filter: int
    after_uniqueness_filter: int
    final_top_10: int

class AppliedTemplate(BaseModel):
    id: str
    name: str

class CurrentPool(BaseModel):
    instance_type: str
    availability_zone: str
    rank: Optional[int] = None

class PoolRankingsResponse(BaseModel):
    rankings: List[RankedPool]
    applied_template: Optional[AppliedTemplate] = None
    filtering_stats: FilteringStats
    current_pool: Optional[CurrentPool] = None
    last_updated: datetime


# ─── Pool Details Schemas ─────────────────────────────────────────────────────

class PoolOverview(BaseModel):
    pool_name: str
    instance_type: str
    availability_zone: str
    risk_score: float
    interruption_rate: float
    hourly_cost: float
    spot_price_current: float
    ondemand_price: float
    discount_percentage: float

class PoolSpecifications(BaseModel):
    vcpu: int
    memory_gib: float
    architecture: str
    network_performance: str
    storage: str
    ebs_optimized: bool

class RiskBreakdown(BaseModel):
    overall_risk_score: float
    interruption_probability: float
    regional_capacity_score: float
    historical_interruptions_24h: int
    global_interruptions_1h: int
    last_interruption: Optional[datetime] = None

class SavingsDetail(BaseModel):
    hourly: float
    monthly: float
    percentage: float

class CostAnalysis(BaseModel):
    hourly_cost: float
    daily_cost: float
    monthly_cost_projection: float
    savings_vs_ondemand: SavingsDetail

class CurrentUsage(BaseModel):
    nodes_in_cluster: int
    total_pods: int
    avg_cpu_utilization: float
    avg_memory_utilization: float

class CostImpact(BaseModel):
    hourly_change: float
    monthly_change: float

class RiskImpact(BaseModel):
    current_risk: float
    new_risk: float
    change: str

class SwitchPreview(BaseModel):
    nodes_to_migrate: int
    pods_to_reschedule: int
    estimated_duration: str
    estimated_downtime: str
    cost_impact: CostImpact
    risk_impact: RiskImpact

class PoolDetailsResponse(BaseModel):
    overview: PoolOverview
    specifications: PoolSpecifications
    risk_breakdown: RiskBreakdown
    cost_analysis: CostAnalysis
    current_usage: Optional[CurrentUsage] = None
    switch_preview: Optional[SwitchPreview] = None


# ─── Blacklist Schemas ────────────────────────────────────────────────────────

class BlacklistReason(str, Enum):
    TERMINATION_NOTICE = "termination_notice"
    REBALANCE_NOTICE = "rebalance_notice"
    MANUAL = "manual"

class BlacklistEntry(BaseModel):
    pool_id: str
    instance_type: str
    availability_zone: str
    region: str = "us-east-1"
    blacklisted_at: datetime
    expires_at: datetime
    reason: BlacklistReason
    time_remaining: str = ""

class BlacklistAddRequest(BaseModel):
    region: str = "us-east-1"
    instance_type: str
    availability_zone: str
    reason: BlacklistReason = BlacklistReason.MANUAL
    duration_hours: int = 12

class BlacklistResponse(BaseModel):
    blacklisted_pools: List[BlacklistEntry]


# ─── Pool Switch Schemas ─────────────────────────────────────────────────────

class SafetyCheck(BaseModel):
    check: str
    status: bool
    blocking: bool

class PoolSwitchRequest(BaseModel):
    cluster_id: str
    from_pool_id: str
    to_pool_id: str
    auto_resume_hours: int = 12
    reason: str = ""
    initiated_by: str = "manual"

class PoolSwitchResponse(BaseModel):
    action_id: str
    status: str
    from_pool: str
    to_pool: str
    safety_checks: List[SafetyCheck]
    estimated_duration: str
    initiated_at: datetime


# ─── Activity Feed Schemas ────────────────────────────────────────────────────

class ActivityEventType(str, Enum):
    SYSTEM_DECISION = "system_decision"
    MANUAL_DECISION = "manual_decision"
    REBALANCING_STARTED = "rebalancing_started"
    REBALANCING_COMPLETED = "rebalancing_completed"
    POOL_SWITCHED = "pool_switched"
    POOL_BLACKLISTED = "pool_blacklisted"

class ActivityEvent(BaseModel):
    id: str
    event_type: ActivityEventType
    timestamp: datetime
    cluster_id: str = ""
    description: str
    details: Dict[str, Any] = {}
