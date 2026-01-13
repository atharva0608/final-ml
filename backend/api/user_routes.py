from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from backend.models.base import get_db
from backend.core.dependencies import get_current_user
from backend.models.user import User

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
