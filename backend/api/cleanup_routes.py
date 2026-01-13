from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.core.dependencies import get_db
from backend.services.cleanup_service import CleanupService
from backend.schemas.cleanup_schemas import CleanupSummary, CleanupAction

router = APIRouter(
    prefix="/cleanup",
    tags=["cleanup"]
)

@router.get("/scan/{account_id}", response_model=CleanupSummary)
def scan_resources(
    account_id: str, 
    regions: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db)
    # user = Depends(get_current_user) # Assuming auth is handled globally or middleware
):
    """
    Scan for orphaned resources.
    Pass regions=['ALL'] to scan all available regions.
    """
    service = CleanupService(db)
    try:
        return service.scan_resources(account_id, regions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/action")
def execute_cleanup_action(
    action: CleanupAction,
    account_id: str = Query(..., description="The account ID to execute action on"),
    db: Session = Depends(get_db)
):
    """
    Execute cleanup actions (Terminate, Delete, Release).
    """
    service = CleanupService(db)
    try:
        return service.execute_action(account_id, action)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
