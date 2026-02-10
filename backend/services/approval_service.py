from sqlalchemy.orm import Session
from backend.models.approval import Approval, ApprovalStatus, ApprovalType
from backend.models.user import User, UserRole
from backend.core.exceptions import ForbiddenError, ResourceNotFoundError
from datetime import datetime, timedelta

class ApprovalService:
    def __init__(self, db: Session):
        self.db = db

    def create_approval(self, user: User, data: dict):
        """
        Create a new access request approval.
        """
        approval = Approval(
            user_id=user.id,
            organization_id=user.organization_id,
            type=data.get("type", ApprovalType.ACCESS_WINDOW),
            resource_id=data.get("resource_id"),
            action_type=data.get("action_type"),
            reason_category=data.get("reason_category"),
            reason_text=data.get("reason_text"),
            duration_hours=data.get("duration_hours", 1),
            status=ApprovalStatus.PENDING
        )
        self.db.add(approval)
        self.db.commit()
        self.db.refresh(approval)
        return approval

    def list_approvals(self, user: User, status: str = None):
        """
        List approvals.
        Members see their own.
        Team Leads see approvals for their team.
        Org Admins see all approvals in their org.
        """
        query = self.db.query(Approval).filter(Approval.organization_id == user.organization_id)

        # Role-based filtering
        if user.role == UserRole.MEMBER:
            query = query.filter(Approval.user_id == user.id)
        elif user.role == UserRole.TEAM_LEAD:
            team_member_ids = self.db.query(User.id).filter(User.team_id == user.team_id).all()
            ids = [u.id for u in team_member_ids]
            query = query.filter(Approval.user_id.in_(ids))

        if status:
            query = query.filter(Approval.status == status)

        return query.order_by(Approval.created_at.desc()).all()

    def approve(self, approver: User, approval_id: str):
        """
        Approve an approval request and activate the window.
        """
        approval = self.db.query(Approval).filter(Approval.id == approval_id).first()
        if not approval:
            raise ResourceNotFoundError("Approval", approval_id)

        self._check_approver_auth(approver, approval)

        if approval.status != ApprovalStatus.PENDING:
            raise ForbiddenError("Approval is not pending")

        approval.status = ApprovalStatus.APPROVED_ACTIVE
        approval.approver_id = approver.id
        approval.approved_at = datetime.utcnow()
        approval.expires_at = datetime.utcnow() + timedelta(hours=approval.duration_hours)

        self.db.commit()
        self.db.refresh(approval)

        # Execute System Automation if this was a paused cleanup approval
        if approval.type == ApprovalType.SYSTEM_CLEANUP:
            try:
                metadata = approval.additional_metadata or {}
                region = metadata.get("region")
                resource_ids = metadata.get("resource_ids")
                action_type_str = metadata.get("action_type")

                if region and resource_ids and action_type_str:
                    from backend.services.hygiene_service import HygieneService
                    from backend.schemas.hygiene_schemas import HygieneAction, HygieneActionType

                    try:
                        clean_type = str(action_type_str).replace("HygieneActionType.", "")
                        enum_val = HygieneActionType(clean_type)

                        action_data = HygieneAction(
                            resource_ids=resource_ids,
                            action_type=enum_val,
                            region=region
                        )

                        hygiene_service = HygieneService(self.db)
                        target_account_id = metadata.get("account_id")
                        if not target_account_id:
                            target_account_id = approval.user.accounts[0].id if approval.user.accounts else None

                        hygiene_service.execute_action(
                            account_id=target_account_id,
                            action_data=action_data,
                            user=approver,
                            bypass_approval=True
                        )
                    except Exception as exec_err:
                        print(f"Failed to execute system cleanup after approval: {exec_err}")

            except Exception as e:
                print(f"Error handling system cleanup approval: {e}")

        return approval

    def revoke(self, user: User, approval_id: str):
        """
        Revoke an active approval immediately.
        """
        approval = self.db.query(Approval).filter(Approval.id == approval_id).first()
        if not approval:
            raise ResourceNotFoundError("Approval", approval_id)

        self._check_approver_auth(user, approval)

        approval.status = ApprovalStatus.REVOKED
        approval.expires_at = datetime.utcnow()

        # Cascade Revoke Children
        if approval.children:
            for child in approval.children:
                if child.status in [ApprovalStatus.PENDING_CONSENT, ApprovalStatus.APPROVED_ACTIVE]:
                    child.status = ApprovalStatus.REVOKED
                    child.expires_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(approval)
        return approval

    def get_active_window(self, user_id: str):
        """
        Check if user has a global Active Window.
        """
        now = datetime.utcnow()
        approval = self.db.query(Approval).filter(
            Approval.user_id == user_id,
            Approval.status == ApprovalStatus.APPROVED_ACTIVE,
            Approval.type == ApprovalType.ACCESS_WINDOW,
            Approval.expires_at > now
        ).first()
        return approval

    def check_specific_permission(self, user_id: str, action_type: str, resource_id: str = None):
        """
        Check for specific ACTION approval.
        """
        now = datetime.utcnow()
        query = self.db.query(Approval).filter(
            Approval.user_id == user_id,
            Approval.status == ApprovalStatus.APPROVED_ACTIVE,
            Approval.type == ApprovalType.ACTION,
            Approval.action_type == action_type,
            Approval.expires_at > now
        )
        if resource_id:
            query = query.filter(Approval.resource_id == resource_id)

        return query.first()

    def create_delegated_approvals(self, admin: User, data: dict):
        """
        Admin grants access to multiple recipients.
        """
        recipient_ids = data.get("recipient_ids", [])
        if not recipient_ids:
            raise ValueError("No recipients selected")

        parent_approval = Approval(
            user_id=admin.id,
            organization_id=admin.organization_id,
            approver_id=admin.id,
            type=data.get("type", ApprovalType.ACCESS_WINDOW),
            resource_id=data.get("resource_id"),
            action_type=data.get("action_type"),
            reason_category=data.get("reason_category"),
            reason_text=f"Delegated Grant: {data.get('reason_text', '')}",
            duration_hours=data.get("duration_hours", 1),
            status=ApprovalStatus.APPROVED_ACTIVE,
            approved_at=datetime.utcnow(),
            activated_at=datetime.utcnow()
        )
        self.db.add(parent_approval)
        self.db.flush()

        created_approvals = [parent_approval]

        for recipient_id in recipient_ids:
            is_self_grant = (recipient_id == admin.id)

            child_status = ApprovalStatus.APPROVED_ACTIVE if is_self_grant else ApprovalStatus.PENDING_CONSENT

            expires_at = (datetime.utcnow() + timedelta(hours=data.get("duration_hours", 1))) if is_self_grant else None
            child_activated_at = datetime.utcnow() if is_self_grant else None

            child = Approval(
                user_id=recipient_id,
                organization_id=admin.organization_id,
                approver_id=admin.id,
                parent_id=parent_approval.id,
                type=data.get("type", ApprovalType.ACCESS_WINDOW),
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
            created_approvals.append(child)

        self.db.commit()
        return created_approvals

    def accept_grant(self, user: User, approval_id: str):
        """
        User accepts a delegated grant.
        """
        approval = self.db.query(Approval).filter(Approval.id == approval_id).first()
        if not approval:
            raise ResourceNotFoundError("Approval", approval_id)

        if approval.user_id != user.id:
            raise ForbiddenError("Not your approval")

        if approval.status != ApprovalStatus.PENDING_CONSENT:
            raise ValueError("Approval is not pending consent")

        if approval.parent_id:
            parent = self.db.query(Approval).filter(Approval.id == approval.parent_id).first()
            if parent and parent.status in [ApprovalStatus.REVOKED, ApprovalStatus.EXPIRED]:
                raise ForbiddenError("This offering has expired or been revoked by the admin")

        approval.status = ApprovalStatus.APPROVED_ACTIVE
        approval.activated_at = datetime.utcnow()
        approval.expires_at = datetime.utcnow() + timedelta(hours=approval.duration_hours)

        self.db.commit()
        return approval

    def reject_grant(self, user: User, approval_id: str):
        """
        User declines a delegated grant.
        """
        approval = self.db.query(Approval).filter(Approval.id == approval_id).first()
        if not approval:
            raise ResourceNotFoundError("Approval", approval_id)

        if approval.user_id != user.id:
            raise ForbiddenError("Not your approval")

        if approval.status != ApprovalStatus.PENDING_CONSENT:
            raise ValueError("Approval is not pending consent")

        approval.status = ApprovalStatus.REJECTED
        self.db.commit()
        return approval

    def _check_approver_auth(self, user: User, approval: Approval):
        """Verify user can manage this approval"""
        if user.organization_id != approval.organization_id:
            raise ForbiddenError("Approval belongs to a different organization")

        if user.role in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN, UserRole.CLIENT]:
            return

        if user.role == UserRole.TEAM_LEAD:
            approval_owner = self.db.query(User).filter(User.id == approval.user_id).first()
            if approval_owner and approval_owner.team_id == user.team_id:
                return

        raise ForbiddenError("Not authorized to manage this approval")

    def create_jit_request(self, user: User, data: dict):
        """
        Create a JIT feature access request.
        """
        from backend.core.feature_registry import get_feature

        feature_id = data.get("feature_id")
        feature = get_feature(feature_id)

        if not feature:
            raise ValueError(f"Invalid feature_id: {feature_id}")

        requested_hours = data.get("duration_hours", feature.default_duration_hours)
        if requested_hours > feature.max_duration_hours:
            raise ValueError(
                f"Requested duration {requested_hours}h exceeds maximum {feature.max_duration_hours}h for {feature.name}"
            )

        if feature.min_approver_role == "ORG_ADMIN" and user.role == UserRole.MEMBER:
            pass

        approval = Approval(
            user_id=user.id,
            organization_id=user.organization_id,
            type=ApprovalType.JIT_FEATURE,
            feature_id=feature_id,
            resource_id=data.get("resource_id"),
            reason_category=data.get("reason_category"),
            reason_text=data.get("reason_text"),
            duration_hours=requested_hours,
            jit_scope=data.get("jit_scope", "TEAM"),
            jit_metadata=data.get("jit_metadata", {}),
            status=ApprovalStatus.PENDING
        )

        self.db.add(approval)
        self.db.commit()
        self.db.refresh(approval)

        return approval

    def get_active_jit_approvals(self, user_id: str):
        """
        Get all active JIT approvals for a user.
        """
        now = datetime.utcnow()
        approvals = self.db.query(Approval).filter(
            Approval.user_id == user_id,
            Approval.type == ApprovalType.JIT_FEATURE,
            Approval.status == ApprovalStatus.APPROVED_ACTIVE,
            Approval.expires_at > now
        ).all()

        return approvals
