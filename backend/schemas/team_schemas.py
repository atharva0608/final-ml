from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime

class TeamMemberResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    status: str
    aws_accounts_count: int = 0  # Computed field

    class Config:
        from_attributes = True

class TeamResponse(BaseModel):
    id: str
    name: str
    organization_id: str
    created_at: datetime
    members: List[TeamMemberResponse] = []

    class Config:
        from_attributes = True
