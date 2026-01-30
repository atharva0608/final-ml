
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from backend.models.base import get_db
from backend.models.user import User
from backend.services.smart_tag_service import SmartTagService
from backend.core.dependencies import get_current_user
from pydantic import BaseModel

router = APIRouter(prefix="/tags/smart", tags=["smart-tags"])

class SmartTagRunRequest(BaseModel):
    account_id: str
    region: str = 'us-east-1'
    dry_run: bool = True

@router.post("/run")
def run_smart_tags(
    request: SmartTagRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Trigger smart tag processing (TTL and Schedule) for a specific account/region.
    """
    service = SmartTagService(db)
    try:
        results = service.process_smart_tags(
            account_id=request.account_id,
            region=request.region,
            dry_run=request.dry_run
        )
        return {"status": "success", "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
