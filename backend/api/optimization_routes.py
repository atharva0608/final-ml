from fastapi import APIRouter, Depends
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
    rightsizer = get_rightsizer(db)
    # Ensure rightsizer module has analyze_resource_usage implemented
    return rightsizer.analyze_resource_usage(cluster_id)
