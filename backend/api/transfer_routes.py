"""
Data Transfer Analysis API Routes
Endpoints for data transfer optimization
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user, RequireRole
from backend.services.transfer_service import get_transfer_service

router = APIRouter(prefix="/transfer", tags=["Data Transfer"])


@router.get("/overview")
def get_transfer_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get Data Transfer optimization overview"""
    service = get_transfer_service(db)
    return service.get_overview(current_user)


@router.post("/analyze")
def analyze_transfer_costs(
    current_user: User = Depends(RequireRole("ORG_ADMIN")),
    db: Session = Depends(get_db)
):
    """Trigger Data Transfer analysis"""
    service = get_transfer_service(db)
    try:
        return service.analyze_all(current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
