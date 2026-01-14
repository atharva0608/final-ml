"""
Role API Routes - RBAC management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user, RequireRole
from backend.services.role_service import RoleService
from backend.schemas.role_schemas import (
    RoleCreate, RoleUpdate, RoleResponse, RoleListResponse,
    PermissionListResponse, PermissionResponse, UserRoleAssignment
)

router = APIRouter(prefix="/roles", tags=["Roles & Permissions"])


@router.get("/permissions", response_model=PermissionListResponse)
async def list_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all available permissions in the system.
    Used to populate the permission matrix editor.
    """
    service = RoleService(db)
    permissions = service.list_permissions()
    return PermissionListResponse(permissions=permissions)


@router.get("", response_model=RoleListResponse)
async def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all roles visible to the user's organization.
    Returns both system roles (global) and custom roles (org-specific).
    """
    service = RoleService(db)
    roles = service.list_roles(organization_id=current_user.organization_id)
    return RoleListResponse(roles=roles, total=len(roles))


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single role by ID"""
    service = RoleService(db)
    role = service.get_role(role_id)
    return role


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole("ORG_ADMIN"))
):
    """
    Create a custom role for the organization.
    Only ORG_ADMIN can create roles.
    """
    service = RoleService(db)
    role = service.create_custom_role(
        organization_id=current_user.organization_id,
        name=role_data.name,
        description=role_data.description,
        permission_slugs=role_data.permission_slugs
    )
    return role


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: str,
    role_data: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole("ORG_ADMIN"))
):
    """
    Update a custom role.
    Only ORG_ADMIN can update roles. System roles cannot be modified.
    """
    service = RoleService(db)
    role = service.update_role(
        role_id=role_id,
        name=role_data.name,
        description=role_data.description,
        permission_slugs=role_data.permission_slugs
    )
    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole("ORG_ADMIN"))
):
    """
    Delete a custom role.
    Only ORG_ADMIN can delete roles. System roles cannot be deleted.
    """
    service = RoleService(db)
    service.delete_role(role_id)
    return None


@router.post("/assign", response_model=dict)
async def assign_role(
    assignment: UserRoleAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole("ORG_ADMIN"))
):
    """
    Assign a role to a user.
    Only ORG_ADMIN can assign roles.
    """
    service = RoleService(db)
    user = service.assign_role_to_user(assignment.user_id, assignment.role_id)
    return {"message": f"Role assigned successfully to {user.email}"}


@router.post("/seed", response_model=dict)
async def seed_rbac_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole("ORG_ADMIN"))
):
    """
    Seed default permissions and system roles.
    Typically called during initial setup.
    """
    service = RoleService(db)
    perm_count = service.seed_permissions()
    role_count = service.seed_system_roles()
    return {
        "message": "RBAC data seeded",
        "permissions_created": perm_count,
        "roles_created": role_count
    }
