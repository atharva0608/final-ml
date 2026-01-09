from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.models.base import get_db
from backend.core.health_service import get_health_service
from backend.models.user import User
from backend.core.dependencies import require_super_admin

router = APIRouter(prefix="/health", tags=["System"])

@router.get("/system", summary="Get detailed system health")
def get_system_health(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    service = get_health_service(db)
    return service.check_overall_health()
