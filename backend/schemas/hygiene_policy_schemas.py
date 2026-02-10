from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

from backend.schemas.hygiene_schemas import ResourceType, HygieneActionType

class HygieneConditionRule(BaseModel):
    field: str  # e.g., "age_days", "tag:Environment", "status"
    op: str     # e.g., "eq", "gt", "lt", "contains", "missing"
    value: Optional[Any] = None

class HygieneConditions(BaseModel):
    operator: str = "AND" # "AND", "OR"
    rules: List[HygieneConditionRule]

class HygienePolicyBase(BaseModel):
    name: str
    description: Optional[str] = None
    resource_type: ResourceType
    region: Optional[str] = "global"
    conditions: HygieneConditions
    action: HygieneActionType = HygieneActionType.NOTIFY
    priority: int = 100
    is_active: bool = True
    organization_id: Optional[str] = None

class HygienePolicyCreate(HygienePolicyBase):
    pass

class HygienePolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    conditions: Optional[HygieneConditions] = None
    action: Optional[HygieneActionType] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    region: Optional[str] = None

class HygienePolicyResponse(HygienePolicyBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
