from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

class ResourceType(str, Enum):
    INSTANCE = "INSTANCE"
    VOLUME = "VOLUME"
    SNAPSHOT = "SNAPSHOT"
    ELASTIC_IP = "ELASTIC_IP"
    LOAD_BALANCER = "LOAD_BALANCER"
    NAT_GATEWAY = "NAT_GATEWAY"
    NETWORK_INTERFACE = "NETWORK_INTERFACE"  # ENI
    RDS_DB = "RDS_DB"
    S3_BUCKET = "S3_BUCKET"
    IAM_USER = "IAM_USER"
    IAM_KEY = "IAM_KEY"

class HygieneStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ORPHANED = "ORPHANED"
    TERMINATING = "TERMINATING"
    DELETED = "DELETED"
    STOPPED = "STOPPED"
    UNAUTHORIZED = "UNAUTHORIZED"
    SAFE_TO_DELETE = "SAFE_TO_DELETE"
    RISK = "RISK" # For IAM Keys
    LEGACY_UPGRADE = "LEGACY_UPGRADE"
    NOT_COMPLIANT = "NOT_COMPLIANT"

class ResourceItem(BaseModel):
    id: str
    name: Optional[str] = "Unknown"
    type: ResourceType
    status: HygieneStatus
    region: str
    cost_per_month: float = 0.0
    is_authorized: bool = False
    reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # Tag Compliance
    is_compliant: bool = True
    missing_tags: List[str] = Field(default_factory=list)
    # Dependency Mapping
    blocking_resources: List[Dict[str, str]] = Field(default_factory=list)
    # Approval Status
    pending_approval: bool = False

class HygieneSummary(BaseModel):
    total_potential_savings: float = 0.0
    previous_savings: Optional[float] = None
    savings_trend_percent: Optional[float] = None
    unauthorized_instance_count: int = 0
    orphaned_volume_count: int = 0
    orphaned_snapshot_count: int = 0
    unused_ip_count: int = 0
    idle_lb_count: int = 0
    idle_rds_count: int = 0
    dormant_user_count: int = 0
    untagged_waste_cost: float = 0.0
    resources: List[ResourceItem]
    metadata: Dict[str, Any] = Field(default_factory=dict)

class HygieneActionType(str, Enum):
    AUTHORIZE = "AUTHORIZE"
    UNAUTHORIZE = "UNAUTHORIZE"
    TERMINATE = "TERMINATE"
    DELETE = "DELETE"
    RELEASE = "RELEASE"
    SNAPSHOT_STOP = "SNAPSHOT_STOP"
    DISABLE = "DISABLE"
    NOTIFY = "NOTIFY"

class HygieneAction(BaseModel):
    resource_ids: List[str]
    action_type: HygieneActionType
    region: str
