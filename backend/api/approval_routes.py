
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.models.user import User
from backend.services.ticket_service import TicketService
from backend.core.dependencies import get_current_user
from backend.models.base import get_db
from backend.schemas.ticket_schemas import TicketResponse
from backend.core.exceptions import ResourceNotFoundError, ForbiddenError

router = APIRouter(prefix="/approvals", tags=["approvals"])

def get_ticket_service(db: Session = Depends(get_db)) -> TicketService:
    return TicketService(db)

@router.post("/{ticket_id}/approve", response_model=TicketResponse)
def approve_ticket(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service)
):
    """
    Approve a pending ticket (Team Lead / Admin)
    """
    try:
        return service.approve_ticket(current_user, ticket_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{ticket_id}/revoke", response_model=TicketResponse)
def revoke_ticket(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service)
):
    """
    Revoke an active ticket immediately
    """
    try:
        return service.revoke_ticket(current_user, ticket_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.post("/{ticket_id}/accept", response_model=TicketResponse)
def accept_grant(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service)
):
    """
    User: Accept a delegated grant offering
    """
    try:
        return service.accept_grant(current_user, ticket_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{ticket_id}/reject", response_model=TicketResponse)
def reject_grant(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service)
):
    """
    User: Reject a delegated grant offering
    """
    try:
        return service.reject_grant(current_user, ticket_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
