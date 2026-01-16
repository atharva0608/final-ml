from sqlalchemy.orm import Session
from backend.models.user import User, UserRole
from backend.services.ticket_service import TicketService
from backend.core.exceptions import GovernanceError
from typing import Optional

class PermissionService:
    def __init__(self, db: Session):
        self.db = db
        self.ticket_service = TicketService(db)

    def enforce(self, user: User, action: str, resource_id: Optional[str] = None):
        """
        The central gatekeeper.
        Raises GovernanceError if action is not allowed.
        """
        
        # 1. ORG_ADMIN / SUPER_ADMIN -> bypass
        if user.role in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN, UserRole.CLIENT]:
            return True

        # 2. Check Static Role Permissions (Optional - if we had a RolePermissions table)
        # For now, MEMBER is blocked from "high risk" actions by default unless they have a ticket.
        
        # 3. Check JIT Tickets (The "Interception")
        
        # A. Check Active Window (Time-based global access)
        active_window = self.ticket_service.get_active_window(user.id)
        if active_window:
            return True # Allowed by Access Window

        # B. Check Specific Action Ticket
        specific_ticket = self.ticket_service.check_specific_permission(user.id, action, resource_id)
        if specific_ticket:
            # Mark action ticket as completed? (Optional logic: one-time use)
            # For now, we just allow it. Detailed logic can come later.
            return True

        # 4. If we haven't returned True yet, DENY.
        raise GovernanceError(
            message=f"Permission denied for action: {action}",
            details={
                "action": action,
                "resource_id": resource_id,
                "required_ticket": True
            }
        )
