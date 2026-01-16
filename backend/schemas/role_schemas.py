"""
Pydantic schemas for Role and Permission management
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class PermissionResponse(BaseModel):
    """Permission response schema"""
    id: str
    slug: str
    name: str
    module: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleBase(BaseModel):
    """Base role schema"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class RoleCreate(RoleBase):
    """Schema for creating a custom role"""
    permission_slugs: List[str] = []


class RoleUpdate(BaseModel):
    """Schema for updating a custom role"""
    name: Optional[str] = None
    description: Optional[str] = None
    permission_slugs: Optional[List[str]] = None


class RoleResponse(BaseModel):
    """Role response schema"""
    id: str
    name: str
    type: str  # SYSTEM or CUSTOM
    description: Optional[str] = None
    organization_id: Optional[str] = None
    permissions: List[PermissionResponse] = []

    class Config:
        from_attributes = True


class RoleListResponse(BaseModel):
    """List of roles response"""
    roles: List[RoleResponse]
    total: int


class PermissionListResponse(BaseModel):
    """List of permissions response"""
    permissions: List[PermissionResponse]


class UserRoleAssignment(BaseModel):
    """Schema for assigning a role to a user"""
    user_id: str
    role_id: str
