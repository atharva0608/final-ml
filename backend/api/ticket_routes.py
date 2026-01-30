
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List

from backend.models.user import User
from backend.services.ticket_service import TicketService
from backend.core.dependencies import get_current_user
from backend.models.base import get_db
from sqlalchemy.orm import Session
from backend.schemas.ticket_schemas import TicketCreate, TicketResponse, TicketGrantCreate
from backend.core.exceptions import ResourceNotFoundError, ForbiddenError

router = APIRouter(prefix="/tickets", tags=["tickets"])

def get_ticket_service(db: Session = Depends(get_db)) -> TicketService:
    return TicketService(db)

@router.post("", response_model=TicketResponse)
def create_ticket(
    ticket_data: TicketCreate,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service)
):
    """
    Submit a new access request ticket
    """
    try:
        # Pass data as dict/compatible format to service
        return service.create_ticket(current_user, ticket_data.model_dump())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("", response_model=List[TicketResponse])
def list_tickets(
    status: str = None,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service)
):
    """
    List tickets visible to the current user (Own, Team, or Org based on role)
    """
    return service.list_tickets(current_user, status)

@router.post("/delegate", response_model=List[TicketResponse])
def create_delegated_tickets(
    grant_data: TicketGrantCreate,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service)
):
    """
    Admin: Grant access to multiple users (Delegated Grant)
    """
    try:
        return service.create_delegated_tickets(current_user, grant_data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.get("/active-window")
def get_active_window(
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service)
):
    """
    Check if there's an active execution window for the current user.
    Returns the active ticket with time-limited access if one exists.
    """
    active_ticket = service.get_active_window(current_user.id)
    if active_ticket:
        return {
            "has_active_window": True,
            "ticket_id": str(active_ticket.id),
            "expires_at": active_ticket.expires_at.isoformat() if active_ticket.expires_at else None
        }
    return {"has_active_window": False, "ticket_id": None, "expires_at": None}

