from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.models.base import get_db
from backend.core.dependencies import get_current_user
from backend.models.user import User, UserRole
from backend.services.ticket_service import TicketService
from backend.schemas.ticket_schemas import TicketCreate, TicketResponse, TicketGrantCreate

router = APIRouter(prefix="/tickets", tags=["JIT Tickets"])

def get_service(db: Session = Depends(get_db)):
    return TicketService(db)

@router.post("/", response_model=TicketResponse)
def create_ticket(
    ticket: TicketCreate,
    service: TicketService = Depends(get_service),
    user: User = Depends(get_current_user)
):
    """Create a new JIT access request"""
    return service.create_ticket(user, ticket.dict())

@router.get("/", response_model=List[TicketResponse])
def list_tickets(
    status: Optional[str] = None,
    service: TicketService = Depends(get_service),
    user: User = Depends(get_current_user)
):
    """List tickets (scoped to user/team/org based on role)"""
    return service.list_tickets(user, status)

@router.get("/active-window", response_model=Optional[TicketResponse])
def get_active_window(
    service: TicketService = Depends(get_service),
    user: User = Depends(get_current_user)
):
    """Check if current user has an active access window"""
    return service.get_active_window(user.id)

@router.post("/{ticket_id}/approve", response_model=TicketResponse)
def approve_ticket(
    ticket_id: str,
    service: TicketService = Depends(get_service),
    user: User = Depends(get_current_user)
):
    """Approve a ticket (Team Lead or Admin only)"""
    return service.approve_ticket(user, ticket_id)

@router.post("/{ticket_id}/revoke", response_model=TicketResponse)
def revoke_ticket(
    ticket_id: str,
    service: TicketService = Depends(get_service),
    user: User = Depends(get_current_user)
):
    """Revoke/Reject a ticket"""
    return service.revoke_ticket(user, ticket_id)

@router.post("/grant", response_model=List[TicketResponse])
def grant_access(
    grant_data: TicketGrantCreate,
    service: TicketService = Depends(get_service),
    user: User = Depends(get_current_user)
):
    """Admin grants access to multiple users"""
    return service.create_delegated_tickets(user, grant_data.dict())

@router.post("/{ticket_id}/accept", response_model=TicketResponse)
def accept_grant(
    ticket_id: str,
    service: TicketService = Depends(get_service),
    user: User = Depends(get_current_user)
):
    """User accepts a delegated grant"""
    return service.accept_grant(user, ticket_id)

@router.post("/{ticket_id}/reject", response_model=TicketResponse)
def reject_grant(
    ticket_id: str,
    service: TicketService = Depends(get_service),
    user: User = Depends(get_current_user)
):
    """User rejects a delegated grant"""
    return service.reject_grant(user, ticket_id)
