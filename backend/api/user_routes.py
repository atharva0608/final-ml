from fastapi import APIRouter, Depends, Body, status
from sqlalchemy.orm import Session
from typing import List
from backend.models.base import get_db
from backend.core.dependencies import get_current_user, RequireRole
from backend.models.user import User
from backend.services.role_service import RoleService

router = APIRouter(prefix="/users", tags=["User Profile"])

@router.patch("/me")
def update_profile(
    full_name: str = Body(..., embed=True),
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    user.full_name = full_name
    db.commit()
    return {"status": "success", "user": {"id": user.id, "email": user.email, "full_name": user.full_name}}


@router.post("/{user_id}/permissions", status_code=status.HTTP_200_OK)
async def update_user_permissions(
    user_id: str,
    permissions: List[str] = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRole("ORG_ADMIN"))
):
    """
    Update direct/custom permissions for a user.
    """
    service = RoleService(db)
    user = service.update_user_permissions(user_id, permissions)
    return {"status": "success", "message": f"Updated permissions for user {user.email}", "permissions": [p.slug for p in user.custom_permissions]}

