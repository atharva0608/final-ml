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

class CleanupStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ORPHANED = "ORPHANED"
    TERMINATING = "TERMINATING"
    DELETED = "DELETED"
    STOPPED = "STOPPED"
    UNAUTHORIZED = "UNAUTHORIZED"
    SAFE_TO_DELETE = "SAFE_TO_DELETE"
    RISK = "RISK" # For IAM Keys
    LEGACY_UPGRADE = "LEGACY_UPGRADE" # For Feature 5
    NOT_COMPLIANT = "NOT_COMPLIANT"

class ResourceItem(BaseModel):
    id: str
    name: Optional[str] = "Unknown"
    type: ResourceType
    status: CleanupStatus
    region: str
    cost_per_month: float = 0.0
    is_authorized: bool = False
    reason: Optional[str] = None  # Why this resource is flagged (e.g., "No healthy targets")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # Tag Compliance (Feature 2)
    is_compliant: bool = True
    missing_tags: List[str] = Field(default_factory=list)
    # Dependency Mapping (Feature 1)
    blocking_resources: List[Dict[str, str]] = Field(default_factory=list)  # [{"type": "AMI", "id": "ami-123"}]
    # Approval Status (Feature 3)
    pending_approval: bool = False

class CleanupSummary(BaseModel):
    total_potential_savings: float = 0.0
    unauthorized_instance_count: int = 0
    orphaned_volume_count: int = 0
    orphaned_snapshot_count: int = 0
    unused_ip_count: int = 0
    idle_lb_count: int = 0
    idle_rds_count: int = 0
    dormant_user_count: int = 0
    untagged_waste_cost: float = 0.0  # Feature 2: Total cost of non-compliant resources
    resources: List[ResourceItem]
    metadata: Dict[str, Any] = Field(default_factory=dict)

class CleanupActionType(str, Enum):
    AUTHORIZE = "AUTHORIZE"
    UNAUTHORIZE = "UNAUTHORIZE"
    TERMINATE = "TERMINATE"
    DELETE = "DELETE"
    RELEASE = "RELEASE"
    SNAPSHOT_STOP = "SNAPSHOT_STOP"
    DISABLE = "DISABLE"

class CleanupAction(BaseModel):
    resource_ids: List[str]
    action_type: CleanupActionType
    region: str 
