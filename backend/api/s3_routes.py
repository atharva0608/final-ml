"""
S3 Analysis API Routes
Endpoints for S3 storage optimization
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user, RequireRole
from backend.services.s3_tiering_service import get_s3_tiering_service

router = APIRouter(prefix="/s3", tags=["S3 Storage"])


@router.get("/overview")
def get_s3_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get S3 storage optimization overview"""
    service = get_s3_tiering_service(db)
    return service.get_overview(current_user)


@router.post("/analyze")
def analyze_s3_buckets(
    current_user: User = Depends(RequireRole("ORG_ADMIN")),
    db: Session = Depends(get_db)
):
    """Trigger S3 tiering analysis"""
    service = get_s3_tiering_service(db)
    try:
        return service.analyze_all_buckets(current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
