"""
Data Transfer Analysis API Routes
Endpoints for data transfer optimization
"""
from fastapi import APIRouter, Depends, HTTPException, Query
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
    lookback_days: int = Query(30, description="Analysis period in days (7, 30, or 90)", ge=7, le=90),
    current_user: User = Depends(RequireRole("ORG_ADMIN")),
    db: Session = Depends(get_db)
):
    """
    Trigger Data Transfer analysis with configurable lookback period.
    
    Lookback periods:
    - 7 days: Quick recent snapshot
    - 30 days: Standard monthly analysis (default)
    - 90 days: Quarterly trend analysis (more reliable for recommendations)
    """
    service = get_transfer_service(db)
    try:
        return service.analyze_all(current_user, lookback_days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
