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

class ResourceItem(BaseModel):
    id: str
    name: Optional[str] = "Unknown"
    type: ResourceType
    status: CleanupStatus
    region: str
    cost_per_month: float = 0.0
    is_authorized: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

class CleanupSummary(BaseModel):
    total_potential_savings: float = 0.0
    unauthorized_instance_count: int = 0
    orphaned_volume_count: int = 0
    orphaned_snapshot_count: int = 0
    unused_ip_count: int = 0
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
