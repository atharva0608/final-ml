from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

class ResourceType(str, Enum):
    INSTANCE = "INSTANCE"
    VOLUME = "VOLUME"
    SNAPSHOT = "SNAPSHOT"
    ELASTIC_IP = "ELASTIC_IP"

class CleanupStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ORPHANED = "ORPHANED"
    TERMINATING = "TERMINATING"
    DELETED = "DELETED"
    STOPPED = "STOPPED"
    UNAUTHORIZED = "UNAUTHORIZED"
    SAFE_TO_DELETE = "SAFE_TO_DELETE"

class ResourceItem(BaseModel):
    id: str
    name: Optional[str] = "Unknown"
    type: ResourceType
    status: CleanupStatus
    region: str
    cost_per_month: float = 0.0
    is_authorized: bool = False
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
    untagged_waste_cost: float = 0.0  # Feature 2: Total cost of non-compliant resources
    resources: List[ResourceItem]

class CleanupActionType(str, Enum):
    AUTHORIZE = "AUTHORIZE"
    UNAUTHORIZE = "UNAUTHORIZE"
    TERMINATE = "TERMINATE"
    DELETE = "DELETE"
    RELEASE = "RELEASE"

class CleanupAction(BaseModel):
    resource_ids: List[str]
    action_type: CleanupActionType
    region: str 
