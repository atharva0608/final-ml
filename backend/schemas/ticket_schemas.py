from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from backend.models.ticket import TicketType, TicketStatus, ReasonCategory

class TicketCreate(BaseModel):
    type: TicketType = TicketType.ACCESS_WINDOW
    resource_id: Optional[str] = None
    action_type: Optional[str] = None
    reason_category: ReasonCategory
    reason_text: str
    duration_hours: int = 1


class TicketGrantCreate(TicketCreate):
    recipient_ids: List[str]

class TicketResponse(BaseModel):
    id: str
    parent_id: Optional[str] = None
    user_id: str
    organization_id: str
    approver_id: Optional[str]
    type: TicketType
    status: TicketStatus
    resource_id: Optional[str]
    action_type: Optional[str]
    reason_category: ReasonCategory
    reason_text: Optional[str]
    duration_hours: int
    expires_at: Optional[datetime]
    approved_at: Optional[datetime]
    activated_at: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True
