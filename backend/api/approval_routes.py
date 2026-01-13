from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from typing import List, Dict

from backend.core.dependencies import get_db, get_current_user
from backend.services.approval_service import ApprovalService
from backend.models.user import User

router = APIRouter(
    prefix="/approvals",
    tags=["approvals"]
)

@router.get("/pending", summary="List pending approval requests")
def list_pending_approvals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all pending requests for the current user's organization.
    """
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not part of an organization")
        
    service = ApprovalService(db)
    # Filter? or just return all for the org?
    # Ideally should check if user is allowed to see them (Team Lead+)
    # But for now transparency is fine.
    return service.get_pending_requests(current_user.organization_id)

@router.post("/{request_id}/approve", summary="Approve a request")
def approve_request(
    request_id: str = Path(..., title="The ID of the request to approve"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Approve and execute a pending request.
    """
    service = ApprovalService(db)
    try:
        return service.approve_request(current_user, request_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{request_id}/reject", summary="Reject a request")
def reject_request(
    request_id: str = Path(..., title="The ID of the request to reject"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Reject a pending request.
    """
    service = ApprovalService(db)
    try:
        return service.reject_request(current_user, request_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
