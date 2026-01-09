"""
Optimization Routes - Rightsizing and optimization endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user
from backend.modules.rightsizer import get_rightsizer

router = APIRouter(prefix="/optimization", tags=["Optimization"])


@router.get("/rightsizing/{cluster_id}", summary="Get resize recommendations")
def get_rightsizing_recommendations(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Analyze cluster workloads and return rightsizing recommendations.
    
    Returns:
    - overprovisioned_instances: List of instances that can be downsized
    - total_potential_savings: Estimated monthly savings
    - recommendations: Specific actions to take
    """
    try:
        rightsizer = get_rightsizer(db)
        analysis = rightsizer.analyze_resource_usage(cluster_id)
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
