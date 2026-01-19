"""
RDS Analysis API Routes
Endpoints for RDS cost optimization
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user, RequireRole
from backend.services.rds_analysis_service import get_rds_analysis_service

router = APIRouter(prefix="/rds", tags=["RDS Database"])


@router.get("/overview")
def get_rds_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get RDS optimization overview"""
    service = get_rds_analysis_service(db)
    return service.get_overview(current_user)


@router.post("/analyze")
def analyze_rds_instances(
    current_user: User = Depends(RequireRole("ORG_ADMIN")),
    db: Session = Depends(get_db)
):
    """Trigger RDS Multi-AZ analysis"""
    service = get_rds_analysis_service(db)
    try:
        return service.analyze_all(current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
