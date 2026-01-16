from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

class InviteMemberRequest(BaseModel):
    email: EmailStr = Field(..., description="Email of the user to invite")
    role: Optional[str] = Field("MEMBER", description="Role in the organization (ORG_ADMIN, TEAM_LEAD, MEMBER)")
    access_level: Optional[str] = Field("READ_ONLY", description="Access Level (READ_ONLY, EXECUTION, FULL)")

class UpdateMemberRoleRequest(BaseModel):
    role: Optional[str] = Field(None, description="New role for the member")
    access_level: Optional[str] = Field(None, description="New access level")

class MemberResponse(BaseModel):
    id: str
    email: str
    org_role: str
    role: str  # Alias for org_role for frontend compatibility
    access_level: str
    is_active: bool
    status: Optional[str] = "ACTIVE"
    created_at: datetime
    last_login: Optional[datetime] = None
    team_id: Optional[str] = None
    full_name: Optional[str] = None

    class Config:
        from_attributes = True

class MemberListResponse(BaseModel):
    members: List[MemberResponse]
    total: int

class InviteResponse(BaseModel):
    message: str
    invitation: Optional[dict] = None
    # Legacy support if needed, but we are moving to invitations
    temporary_password: Optional[str] = None

class AcceptInvitationRequest(BaseModel):
    """Request to accept an organization invitation - no password needed, default is assigned"""
    pass  # No fields required - default password demo1234 is assigned

class AcceptInvitationResponse(BaseModel):
    """Response after accepting invitation"""
    message: str
    user_id: str
    email: str
    organization_id: str
    org_role: str
    access_level: str
    must_reset_password: bool = True  # Indicates user must reset on first login
    temporary_password: str = "demo1234"  # Default password that must be reset

