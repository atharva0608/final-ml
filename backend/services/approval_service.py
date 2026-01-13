"""
Approval Service
Handles creation, listing, and approval/rejection of governance requests.
"""
from sqlalchemy.orm import Session
from backend.models.approval import ApprovalRequest, ApprovalStatus
from backend.models.user import User, UserRole
from backend.models.organization import Organization
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

class ApprovalService:
    def __init__(self, db: Session):
        self.db = db

    def create_request(self, user: User, resource_type: str, action: str, payload: dict) -> ApprovalRequest:
        """
        Create a new approval request
        """
        logger.info(f"Creating approval request for user {user.id}: {action} on {resource_type}")
        req = ApprovalRequest(
            organization_id=user.organization_id,
            requester_id=user.id,
            resource_type=resource_type,
            resource_id=payload.get("resource_id", "BATCH"),
            action=action,
            execution_payload=payload
        )
        self.db.add(req)
        self.db.commit()
        return req

    def get_pending_requests(self, organization_id: str):
        """
        List all pending requests for an organization
        """
        return self.db.query(ApprovalRequest).filter(
            ApprovalRequest.organization_id == organization_id,
            ApprovalRequest.status == ApprovalStatus.PENDING
        ).order_by(ApprovalRequest.created_at.desc()).all()

    def approve_request(self, admin_user: User, request_id: str):
        """
        Approve and Execute a request
        """
        # 1. Verify Permission
        if admin_user.role not in [UserRole.ORG_ADMIN, UserRole.TEAM_LEAD, UserRole.SUPER_ADMIN]:
            raise Exception("Unauthorized: Only Team Leads or Admins can approve.")

        req = self.db.query(ApprovalRequest).filter(
            ApprovalRequest.id == request_id,
            ApprovalRequest.organization_id == admin_user.organization_id
        ).first()

        if not req:
            raise Exception("Request not found")
        
        if req.status != ApprovalStatus.PENDING:
            raise Exception("Request is not pending")

        # 2. Prevent self-approval if strict mode? 
        # (For now allow, but in strict mode ideally requester != approver)
        
        # 3. Execute the Logic (Late Binding)
        try:
            logger.info(f"Executing approved request {req.id} (Action: {req.action})")
            
            if req.action == "CLEANUP_EXECUTE":
                # Dynamic import to avoid circular dependency
                from backend.services.cleanup_service import CleanupService
                from backend.schemas.cleanup_schemas import CleanupAction
                
                svc = CleanupService(self.db)
                payload = req.execution_payload
                
                # Reconstruct action data
                action_data = CleanupAction(**payload['action_data'])
                
                # Execute with approval bypass
                svc.execute_action(
                    account_id=payload['account_id'],
                    action_data=action_data,
                    user=req.requester, # Log original requester? Or Admin? technically admin executed it. 
                    # Actually better to pass admin as actor but note requester. 
                    # For now using admin as the effective actor.
                    bypass_approval=True
                )
            
            req.status = ApprovalStatus.APPROVED
            req.approver_id = admin_user.id
            req.updated_at = datetime.utcnow()
            self.db.commit()
            return {"status": "success", "message": "Request Approved and Executed"}
            
        except Exception as e:
            logger.error(f"Execution failed for request {req.id}: {e}")
            req.status = ApprovalStatus.FAILED
            self.db.commit()
            raise e

    def reject_request(self, admin_user: User, request_id: str):
        """
        Reject a request
        """
        if admin_user.role not in [UserRole.ORG_ADMIN, UserRole.TEAM_LEAD, UserRole.SUPER_ADMIN]:
            raise Exception("Unauthorized")

        req = self.db.query(ApprovalRequest).filter(
            ApprovalRequest.id == request_id,
            ApprovalRequest.organization_id == admin_user.organization_id
        ).first()

        if not req:
            raise Exception("Request not found")
            
        req.status = ApprovalStatus.REJECTED
        req.approver_id = admin_user.id
        req.updated_at = datetime.utcnow()
        self.db.commit()
        return {"status": "success", "message": "Request Rejected"}
