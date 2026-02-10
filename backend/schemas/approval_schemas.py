from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from backend.models.approval import ApprovalType, ApprovalStatus, ReasonCategory, JITScope

class ApprovalCreate(BaseModel):
    type: ApprovalType = ApprovalType.ACCESS_WINDOW
    resource_id: Optional[str] = None
    action_type: Optional[str] = None
    reason_category: ReasonCategory
    reason_text: str
    duration_hours: int = 1


class ApprovalGrantCreate(ApprovalCreate):
    recipient_ids: List[str]


class JITRequestCreate(BaseModel):
    """Schema for requesting JIT feature access"""
    feature_id: str
    reason_category: ReasonCategory
    reason_text: str
    duration_hours: int = 1
    resource_id: Optional[str] = None  # For resource-specific access
    jit_scope: JITScope = JITScope.TEAM
    jit_metadata: Optional[Dict[str, Any]] = None


class PermissionCheckRequest(BaseModel):
    """Schema for checking permission on a feature"""
    feature_id: str
    resource_id: Optional[str] = None


class PermissionCheckResponse(BaseModel):
    """Response for permission check"""
    allowed: bool
    reason: str
    feature: Optional[Dict[str, Any]] = None
    ticket: Optional[Dict[str, Any]] = None
    expires_at: Optional[str] = None


class ApprovalResponse(BaseModel):
    id: str
    parent_id: Optional[str] = None
    user_id: str
    organization_id: str
    approver_id: Optional[str]
    type: ApprovalType
    status: ApprovalStatus
    resource_id: Optional[str]
    action_type: Optional[str]
    reason_category: ReasonCategory
    reason_text: Optional[str]
    duration_hours: int
    expires_at: Optional[datetime]
    approved_at: Optional[datetime]
    activated_at: Optional[datetime]
    created_at: datetime

    # JIT-specific fields
    feature_id: Optional[str] = None
    jit_scope: Optional[JITScope] = None
    jit_metadata: Optional[Dict[str, Any]] = None
    auto_approved: Optional[bool] = False

    class Config:
        from_attributes = True
