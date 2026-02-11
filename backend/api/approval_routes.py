
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List

from backend.models.user import User
from backend.services.approval_service import ApprovalService
from backend.core.dependencies import get_current_user
from backend.models.base import get_db
from sqlalchemy.orm import Session
from backend.schemas.approval_schemas import ApprovalCreate, ApprovalResponse, ApprovalGrantCreate, JITRequestCreate
from backend.core.exceptions import ResourceNotFoundError, ForbiddenError

router = APIRouter(prefix="/approvals", tags=["approvals"])

def get_approval_service(db: Session = Depends(get_db)) -> ApprovalService:
    return ApprovalService(db)

@router.post("", response_model=ApprovalResponse)
def create_approval(
    approval_data: ApprovalCreate,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Submit a new access request approval
    """
    try:
        return service.create_approval(current_user, approval_data.model_dump())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("", response_model=List[ApprovalResponse])
def list_approvals(
    status: str = None,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    List approvals visible to the current user (Own, Team, or Org based on role)
    """
    return service.list_approvals(current_user, status)

@router.post("/delegate", response_model=List[ApprovalResponse])
def create_delegated_approvals(
    grant_data: ApprovalGrantCreate,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Admin: Grant access to multiple users (Delegated Grant)
    """
    try:
        return service.create_delegated_approvals(current_user, grant_data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.get("/active-window")
def get_active_window(
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Check if there's an active execution window for the current user.
    """
    active_approval = service.get_active_window(current_user.id)
    if active_approval:
        return {
            "has_active_window": True,
            "approval_id": str(active_approval.id),
            "expires_at": active_approval.expires_at.isoformat() if active_approval.expires_at else None
        }
    return {"has_active_window": False, "approval_id": None, "expires_at": None}


@router.post("/jit-request", response_model=ApprovalResponse)
def create_jit_request(
    request_data: JITRequestCreate,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Submit a JIT (Just-In-Time) feature access request.

    This creates a time-bound approval for a specific protected feature.
    The request will be routed to appropriate approvers (Team Lead or Org Admin).

    Example:
        POST /api/v1/approvals/jit-request
        {
            "feature_id": "hygiene:execute",
            "reason_category": "MAINTENANCE",
            "reason_text": "Need to cleanup orphaned EBS volumes in us-east-1",
            "duration_hours": 2,
            "jit_scope": "TEAM"
        }
    """
    try:
        approval = service.create_jit_request(current_user, request_data.model_dump())
        return approval
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/my-jit-approvals", response_model=List[ApprovalResponse])
def get_my_jit_approvals(
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Get all active JIT approvals for the current user.
    """
    approvals = service.get_active_jit_approvals(current_user.id)
    return approvals


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
def approve_request(
    approval_id: str,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Approve a JIT access request (Team Lead or Org Admin only).
    """
    try:
        approval = service.approve(current_user, approval_id)
        return approval
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
def reject_request(
    approval_id: str,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Reject a pending JIT access request (Team Lead or Org Admin only).
    """
    try:
        approval = service.reject(current_user, approval_id)
        return approval
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{approval_id}/revoke", response_model=ApprovalResponse)
def revoke_request(
    approval_id: str,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Revoke an active approval immediately (Team Lead or Org Admin only).
    """
    try:
        approval = service.revoke(current_user, approval_id)
        return approval
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{approval_id}/accept", response_model=ApprovalResponse)
def accept_grant(
    approval_id: str,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    User: Accept a delegated grant offering
    """
    try:
        return service.accept_grant(current_user, approval_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
def reject_grant(
    approval_id: str,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    User: Reject a delegated grant offering
    """
    try:
        return service.reject_grant(current_user, approval_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
