from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime

class AccountSummary(BaseModel):
    id: str
    aws_account_id: str
    status: str
    
    class Config:
        from_attributes = True

class TeamMemberResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    status: str
    aws_accounts_count: int = 0  # Computed field
    accounts: List[AccountSummary] = [] # List of connected accounts
    team_member_permissions: dict = {}  # Granular permission overrides

    class Config:
        from_attributes = True

class TeamResponse(BaseModel):
    id: str
    name: str
    organization_id: str
    created_at: datetime
    governance_config: dict = {}
    members: List[TeamMemberResponse] = []

    class Config:
        from_attributes = True

class TeamGovernanceUpdate(BaseModel):
    config: dict = Field(..., description="Governance configuration (key-value pairs)")

class TeamMemberPermissionsUpdate(BaseModel):
    """Schema for updating a team member's granular permissions"""
    permissions: dict = Field(..., description="Key-value pairs for permission overrides (e.g., {'allow_termination': false})")
