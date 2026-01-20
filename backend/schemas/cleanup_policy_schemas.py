from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

from backend.schemas.cleanup_schemas import ResourceType, CleanupActionType

class CleanupConditionRule(BaseModel):
    field: str  # e.g., "age_days", "tag:Environment", "status"
    op: str     # e.g., "eq", "gt", "lt", "contains", "missing"
    value: Optional[Any] = None

class CleanupConditions(BaseModel):
    operator: str = "AND" # "AND", "OR"
    rules: List[CleanupConditionRule]

class CleanupPolicyBase(BaseModel):
    name: str
    description: Optional[str] = None
    resource_type: ResourceType
    region: Optional[str] = "global"
    conditions: CleanupConditions
    action: CleanupActionType = CleanupActionType.NOTIFY
    priority: int = 100
    is_active: bool = True
    organization_id: Optional[str] = None

class CleanupPolicyCreate(CleanupPolicyBase):
    pass

class CleanupPolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    conditions: Optional[CleanupConditions] = None
    action: Optional[CleanupActionType] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    region: Optional[str] = None

class CleanupPolicyResponse(CleanupPolicyBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
