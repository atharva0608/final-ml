from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.core.dependencies import get_db, get_current_user, verify_tenant_action
from backend.services.cleanup_service import CleanupService
from backend.schemas.cleanup_schemas import CleanupSummary, CleanupAction
from backend.models.user import User

router = APIRouter(
    prefix="/cleanup",
    tags=["cleanup"]
)

@router.get("/scan/{account_id}", response_model=CleanupSummary)
def scan_resources(
    account_id: str, 
    regions: Optional[List[str]] = Query(None),
    force_refresh: bool = Query(False, description="Bypass cache and fetch fresh data from AWS"),
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_tenant_action)
):
    """
    Scan for orphaned resources.
    Pass regions=['ALL'] to scan all available regions.
    Pass force_refresh=true to bypass cache (use after cleanup actions).
    """
    service = CleanupService(db)
    try:
        return service.scan_resources(account_id, regions, organization=current_user.organization, force_refresh=force_refresh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/check-dependencies")
def check_dependencies(
    account_id: str = Query(...),
    resource_type: str = Query(...),
    resource_id: str = Query(...),
    region: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_tenant_action)
):
    """
    Feature 1: Deep Dependency Mapping
    Pre-flight check before deletion to verify no blocking resources.
    """
    service = CleanupService(db)
    try:
        result = service.check_dependencies(account_id, resource_type, resource_id, region)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/action")
def execute_cleanup_action(
    action: CleanupAction,
    account_id: str = Query(..., description="The account ID to execute action on"),
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_tenant_action)
):
    """
    Execute cleanup actions (Terminate, Delete, Release).
    Supports RBAC - Members require approval.
    """
    service = CleanupService(db)
    try:
        result = service.execute_action(account_id, action, user=current_user)
        # Return 202 Accepted if pending approval
        if result.get("status") == "pending_approval":
            return Response(status_code=202, content=result, media_type="application/json")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
