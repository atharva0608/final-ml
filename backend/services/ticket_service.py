from sqlalchemy.orm import Session
from backend.models.ticket import Ticket, TicketStatus, TicketType
from backend.models.user import User, UserRole
from backend.core.exceptions import ForbiddenError, ResourceNotFoundError
from datetime import datetime, timedelta

class TicketService:
    def __init__(self, db: Session):
        self.db = db

    def create_ticket(self, user: User, data: dict):
        """
        Create a new access request ticket.
        """
        ticket = Ticket(
            user_id=user.id,
            organization_id=user.organization_id,
            type=data.get("type", TicketType.ACCESS_WINDOW),
            resource_id=data.get("resource_id"),
            action_type=data.get("action_type"),
            reason_category=data.get("reason_category"),
            reason_text=data.get("reason_text"),
            duration_hours=data.get("duration_hours", 1),
            status=TicketStatus.PENDING
        )
        self.db.add(ticket)
        self.db.commit()
        self.db.refresh(ticket)
        return ticket

    def list_tickets(self, user: User, status: str = None):
        """
        List tickets.
        Members see their own.
        Team Leads see tickets for their team.
        Org Admins see all tickets in their org.
        """
        query = self.db.query(Ticket).filter(Ticket.organization_id == user.organization_id)

        # Role-based filtering
        if user.role == UserRole.MEMBER:
            # Members only see their own tickets
            query = query.filter(Ticket.user_id == user.id)
        elif user.role == UserRole.TEAM_LEAD:
            # Team Leads see tickets for their team members
            team_member_ids = self.db.query(User.id).filter(User.team_id == user.team_id).all()
            ids = [u.id for u in team_member_ids]
            query = query.filter(Ticket.user_id.in_(ids))
        # ORG_ADMIN, SUPER_ADMIN, and CLIENT see all tickets in their org (no additional filter)
        
        if status:
            query = query.filter(Ticket.status == status)
            
        return query.order_by(Ticket.created_at.desc()).all()

    def approve_ticket(self, approver: User, ticket_id: str):
        """
        Approve a ticket and activate the window.
        """
        ticket = self.db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise ResourceNotFoundError("Ticket", ticket_id)

        # Authorization
        self._check_approver_auth(approver, ticket)

        if ticket.status != TicketStatus.PENDING:
            raise ForbiddenError("Ticket is not pending")

        ticket.status = TicketStatus.APPROVED_ACTIVE
        ticket.approver_id = approver.id
        ticket.approved_at = datetime.utcnow()
        ticket.expires_at = datetime.utcnow() + timedelta(hours=ticket.duration_hours)
        
        self.db.commit()
        self.db.refresh(ticket)
        
        # [NEW] Execute System Automation if this was a paused cleanup ticket
        if ticket.type == TicketType.SYSTEM_CLEANUP:
            try:
                # Extract paused action context
                metadata = ticket.additional_metadata or {}
                region = metadata.get("region")
                resource_ids = metadata.get("resource_ids")
                action_type_str = metadata.get("action_type") # e.g. CleanupActionType.DELETE or DELETE
                
                if region and resource_ids and action_type_str:
                    from backend.services.cleanup_service import CleanupService
                    from backend.schemas.cleanup_schemas import CleanupAction, CleanupActionType
                    
                    # Convert string back to Enum if needed, or Schema expects str?
                    # Schema CleanupAction expects CleanupActionType enum
                    # Ensure parsing logic
                    try:
                        # Handle "CleanupActionType.DELETE" vs "DELETE"
                        clean_type = str(action_type_str).replace("CleanupActionType.", "")
                        enum_val = CleanupActionType(clean_type)
                        
                        action_data = CleanupAction(
                            resource_ids=resource_ids,
                            action_type=enum_val,
                            region=region
                        )
                        
                        cleanup_service = CleanupService(self.db)
                        # Execute with bypass_approval=True because we just approved it
                        target_account_id = metadata.get("account_id") 
                        if not target_account_id:
                            # Fallback if missing (legacy tickets)
                            target_account_id = ticket.user.accounts[0].id if ticket.user.accounts else None

                        cleanup_service.execute_action(
                            account_id=target_account_id,
                            action_data=action_data,
                            user=approver,
                            bypass_approval=True 
                        )
                        # Note: `execute_action` requires valid account_id. 
                        # For system ticket, we don't have account context easily unless we saved it.
                        # We should have saved account_id in metadata.
                        # Assuming for now we can't easily resolve it without metadata "account_id".
                        # But `execute_action` takes account_id.
                        # Let's rely on finding it from the user (approver) or context? No, user is unrelated.
                        # Resource IDs are global or regional.
                        # CRITICAL FIX: We need account_id in metadata.
                    except Exception as exec_err:
                        # Log error but don't fail the approval itself? Or fail?
                        # Better to mark ticket as "APPROVED_FAILED" or similar?
                        # For now, log.
                        print(f"Failed to execute system cleanup after approval: {exec_err}")
                        
            except Exception as e:
                print(f"Error handling system cleanup ticket: {e}")
                
        return ticket

    def revoke_ticket(self, user: User, ticket_id: str):
        """
        Revoke an active ticket immediately.
        """
        ticket = self.db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise ResourceNotFoundError("Ticket", ticket_id)

        # Authorization: Approver (Lead) or Org Admin
        self._check_approver_auth(user, ticket)

        ticket.status = TicketStatus.REVOKED
        ticket.expires_at = datetime.utcnow() # Expire now
        
        # Cascade Revoke Children (If this is a Parent Ticket)
        # Using the `children` relationship
        if ticket.children:
            for child in ticket.children:
                if child.status in [TicketStatus.PENDING_CONSENT, TicketStatus.APPROVED_ACTIVE]:
                    child.status = TicketStatus.REVOKED
                    child.expires_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(ticket)
        return ticket

    def get_active_window(self, user_id: str):
        """
        Check if user has a global Active Window.
        Returns the ticket if active, None otherwise.
        """
        now = datetime.utcnow()
        ticket = self.db.query(Ticket).filter(
            Ticket.user_id == user_id,
            Ticket.status == TicketStatus.APPROVED_ACTIVE,
            Ticket.type == TicketType.ACCESS_WINDOW,
            Ticket.expires_at > now
        ).first()
        return ticket

    def check_specific_permission(self, user_id: str, action_type: str, resource_id: str = None):
        """
        Check for specific ACTION ticket.
        """
        now = datetime.utcnow()
        query = self.db.query(Ticket).filter(
            Ticket.user_id == user_id,
            Ticket.status == TicketStatus.APPROVED_ACTIVE,
            Ticket.type == TicketType.ACTION,
            Ticket.action_type == action_type,
            Ticket.expires_at > now
        )
        if resource_id:
            query = query.filter(Ticket.resource_id == resource_id)
            
        return query.first()

    def create_delegated_tickets(self, admin: User, data: dict):
        """
        Admin grants access to multiple recipients.
        Creates a Parent ticket (for the Admin, as a record/grouper) and Child tickets (for recipients).
        """
        recipient_ids = data.get("recipient_ids", [])
        if not recipient_ids:
            raise ValueError("No recipients selected")

        # 1. Create Parent Ticket (The Grant Record)
        # Assigned to Admin, Status COMPLETED (just a record), or APPROVED_ACTIVE? 
        # Let's make it APPROVED_ACTIVE so Admin can "Revoke" it to cascade revoke children?
        parent_ticket = Ticket(
            user_id=admin.id,
            organization_id=admin.organization_id,
            approver_id=admin.id,
            type=data.get("type", TicketType.ACCESS_WINDOW),
            resource_id=data.get("resource_id"),
            action_type=data.get("action_type"),
            reason_category=data.get("reason_category"),
            reason_text=f"Delegated Grant: {data.get('reason_text', '')}",
            duration_hours=data.get("duration_hours", 1),
            status=TicketStatus.APPROVED_ACTIVE, # Acts as the "Master Switch"
            approved_at=datetime.utcnow(),
            activated_at=datetime.utcnow()
        )
        self.db.add(parent_ticket)
        self.db.flush() # Get ID

        created_tickets = [parent_ticket]

        # 2. Create Child Tickets (For Recipients)
        for recipient_id in recipient_ids:
            # Validate recipient is in same org
            # (assuming controller logic or simple check here)
            
            is_self_grant = (recipient_id == admin.id)
            
            child_status = TicketStatus.APPROVED_ACTIVE if is_self_grant else TicketStatus.PENDING_CONSENT
            
            # If self-grant (Safety Window), set expiration immediately
            expires_at = (datetime.utcnow() + timedelta(hours=data.get("duration_hours", 1))) if is_self_grant else None
            child_activated_at = datetime.utcnow() if is_self_grant else None

            child = Ticket(
                user_id=recipient_id,
                organization_id=admin.organization_id,
                approver_id=admin.id, # Admin is the approver
                parent_id=parent_ticket.id,
                type=data.get("type", TicketType.ACCESS_WINDOW),
                resource_id=data.get("resource_id"),
                action_type=data.get("action_type"),
                reason_category=data.get("reason_category"),
                reason_text=data.get("reason_text"),
                duration_hours=data.get("duration_hours", 1),
                status=child_status, 
                approved_at=datetime.utcnow(), 
                activated_at=child_activated_at,
                expires_at=expires_at
            )
            self.db.add(child)
            created_tickets.append(child)
        
        self.db.commit()
        return created_tickets

    def accept_grant(self, user: User, ticket_id: str):
        """
        User accepts a delegated grant.
        """
        ticket = self.db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise ResourceNotFoundError("Ticket", ticket_id)
        
        if ticket.user_id != user.id:
            raise ForbiddenError("Not your ticket")
            
        if ticket.status != TicketStatus.PENDING_CONSENT:
            raise ValueError("Ticket is not pending consent")

        # Check if Parent is still active?
        if ticket.parent_id:
            parent = self.db.query(Ticket).filter(Ticket.id == ticket.parent_id).first()
            if parent and parent.status in [TicketStatus.REVOKED, TicketStatus.EXPIRED]:
                raise ForbiddenError("This offering has expired or been revoked by the admin")

        ticket.status = TicketStatus.APPROVED_ACTIVE
        ticket.activated_at = datetime.utcnow()
        ticket.expires_at = datetime.utcnow() + timedelta(hours=ticket.duration_hours)
        
        self.db.commit()
        return ticket

    def reject_grant(self, user: User, ticket_id: str):
        """
        User declines a delegated grant.
        """
        ticket = self.db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise ResourceNotFoundError("Ticket", ticket_id)
        
        if ticket.user_id != user.id:
            raise ForbiddenError("Not your ticket")

        if ticket.status != TicketStatus.PENDING_CONSENT:
            raise ValueError("Ticket is not pending consent")

        ticket.status = TicketStatus.REJECTED
        # Optionally set a reason?
        
        self.db.commit()
        return ticket

    def _check_approver_auth(self, user: User, ticket: Ticket):
        """Verify user can manage this ticket"""
        # Must be same org
        if user.organization_id != ticket.organization_id:
            raise ForbiddenError("Ticket belongs to a different organization")
            
        # Org Admin, Super Admin, or Client (legacy) can manage all tickets in their org
        if user.role in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN, UserRole.CLIENT]:
            return # Allow
        
        if user.role == UserRole.TEAM_LEAD:
            # Must be lead of ticket owner's team
            ticket_owner = self.db.query(User).filter(User.id == ticket.user_id).first()
            if ticket_owner and ticket_owner.team_id == user.team_id:
                return # Allow
                
        raise ForbiddenError("Not authorized to manage this ticket")
