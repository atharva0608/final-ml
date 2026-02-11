"""
Permission Service - JIT Feature-Based Access Control

This service enforces Just-In-Time privilege escalation for protected features.
All permission checks go through the feature registry for consistent enforcement.
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import logging

from backend.models.user import User, UserRole
from backend.models.approval import Approval, ApprovalStatus, ApprovalType
from backend.core.feature_registry import get_feature, FEATURE_REGISTRY
from backend.core.exceptions import GovernanceError

logger = logging.getLogger(__name__)


class PermissionService:
    """Central permission gatekeeper using feature-based JIT approvals"""

    def __init__(self, db: Session):
        self.db = db

    def enforce(self, user: User, feature_id: str, resource_id: Optional[str] = None) -> bool:
        """
        Central permission enforcement for feature-based actions.

        Args:
            user: User attempting the action
            feature_id: Feature identifier from registry (e.g., "hygiene:execute")
            resource_id: Optional specific resource being accessed

        Returns:
            True if allowed

        Raises:
            GovernanceError: If permission denied
        """
        feature = get_feature(feature_id)
        if not feature:
            logger.error(f"Unknown feature ID: {feature_id}")
            raise GovernanceError(
                message=f"Invalid feature: {feature_id}",
                details={"feature_id": feature_id}
            )

        # 1. ORG_ADMIN / SUPER_ADMIN -> Automatic bypass for all features
        if user.role in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
            logger.info(f"Admin bypass: {user.email} → {feature_id}")
            return True

        # 2. PRIORITY: Check for active JIT ticket (works for all features)
        active_ticket = self._get_active_jit_ticket(user.id, feature_id, resource_id)
        if active_ticket:
            logger.info(f"JIT ticket granted: {user.email} → {feature_id} (ticket: {active_ticket.id})")
            return True

        # 3. If no JIT ticket, check base RBAC permissions
        if not feature.requires_approval:
            # Feature doesn't need approval - check base permission only
            if self._has_permission(user, feature.permission_slug):
                logger.info(f"Permission granted (no approval needed): {user.email} → {feature_id}")
                return True
            else:
                logger.warning(f"Missing permission: {user.email} → {feature.permission_slug}")
                raise GovernanceError(
                    message=f"Missing permission: {feature.permission_slug}",
                    details={
                        "feature_id": feature_id,
                        "required_permission": feature.permission_slug,
                        "requires_approval": False
                    }
                )

        # 4. Feature requires approval but no active ticket - DENY with actionable error
        logger.warning(f"Permission denied (no JIT ticket): {user.email} → {feature_id}")
        raise GovernanceError(
            message=f"JIT approval required for: {feature.name}",
            details={
                "feature_id": feature_id,
                "feature_name": feature.name,
                "description": feature.description,
                "resource_id": resource_id,
                "required_ticket": True,
                "min_approver_role": feature.min_approver_role,
                "max_duration_hours": feature.max_duration_hours,
                "default_duration_hours": feature.default_duration_hours,
                "risk_level": feature.risk_level
            }
        )

    def check_permission(self, user: User, feature_id: str, resource_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Non-blocking permission check - returns status instead of raising exception.

        Returns:
            {
                "allowed": bool,
                "reason": str,
                "ticket": Ticket or None,
                "feature": Feature metadata
            }
        """
        feature = get_feature(feature_id)
        if not feature:
            return {
                "allowed": False,
                "reason": "Invalid feature ID",
                "ticket": None,
                "feature": None
            }

        # Admin bypass
        if user.role in [UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]:
            return {
                "allowed": True,
                "reason": "Admin privileges",
                "ticket": None,
                "feature": feature.__dict__
            }

        # PRIORITY 1: Check for active JIT ticket first (works for all features)
        active_ticket = self._get_active_jit_ticket(user.id, feature_id, resource_id)
        if active_ticket:
            return {
                "allowed": True,
                "reason": "Active JIT ticket",
                "ticket": active_ticket,
                "feature": feature.__dict__,
                "expires_at": active_ticket.expires_at.isoformat() if active_ticket.expires_at else None
            }

        # PRIORITY 2: Check for pending JIT ticket (show pending state)
        pending_ticket = self._get_pending_jit_ticket(user.id, feature_id, resource_id)
        if pending_ticket:
            return {
                "allowed": False,
                "reason": "Request pending approval",
                "ticket": pending_ticket,
                "feature": feature.__dict__,
                "pending": True
            }

        # PRIORITY 3: If no ticket, check base RBAC permissions
        if not feature.requires_approval:
            has_perm = self._has_permission(user, feature.permission_slug)
            return {
                "allowed": has_perm,
                "reason": "Permission granted" if has_perm else "Missing permission",
                "ticket": None,
                "feature": feature.__dict__,
                "pending": False
            }

        # PRIORITY 4: Feature requires approval but user has no ticket
        return {
            "allowed": False,
            "reason": "JIT ticket required",
            "ticket": None,
            "feature": feature.__dict__,
            "pending": False
        }

    def _get_pending_jit_ticket(self, user_id: str, feature_id: str, resource_id: Optional[str] = None) -> Optional[Approval]:
        """
        Find pending JIT ticket for user + feature combination.
        Used to check if user already has a pending request.
        """
        pending_ticket = self.db.query(Approval).filter(
            and_(
                Approval.user_id == user_id,
                Approval.status == ApprovalStatus.PENDING,
                Approval.type == ApprovalType.JIT_FEATURE,
                Approval.feature_id == feature_id
            )
        ).first()

        return pending_ticket

    def _get_active_jit_ticket(self, user_id: str, feature_id: str, resource_id: Optional[str] = None) -> Optional[Approval]:
        """
        Find active JIT ticket for user + feature + resource combination.

        Checks for:
        1. Feature-specific tickets (exact match)
        2. Global access windows covering this feature
        3. Resource-specific vs global tickets
        """
        now = datetime.now(timezone.utc)

        # Build query for active tickets
        query = self.db.query(Approval).filter(
            and_(
                Approval.user_id == user_id,
                Approval.status == ApprovalStatus.APPROVED_ACTIVE,
                Approval.expires_at > now
            )
        )

        # Check for feature-specific ticket first
        feature_ticket = query.filter(
            Approval.type == ApprovalType.JIT_FEATURE,
            Approval.feature_id == feature_id
        ).first()

        if feature_ticket:
            # Check resource scoping
            if resource_id:
                # Caller specified a resource - check if ticket matches
                if feature_ticket.resource_id == resource_id or not feature_ticket.resource_id:
                    # Ticket matches specific resource OR is a global ticket
                    return feature_ticket
            else:
                # No resource specified by caller - accept any ticket for this feature
                return feature_ticket

        # Check for general ACCESS_WINDOW (legacy broad access)
        access_window = query.filter(
            Approval.type == ApprovalType.ACCESS_WINDOW
        ).first()

        if access_window:
            return access_window

        return None

    def _has_permission(self, user: User, permission_slug: str) -> bool:
        """
        Check if user has required permission (via role or custom permissions).

        This checks the RBAC permission system (backend/models/permission.py).
        """
        from backend.services.role_service import RoleService

        role_service = RoleService(self.db)
        user_permissions = role_service.get_user_permissions(user)
        # user_permissions is already a list of slugs (strings), not objects
        permission_slugs = set(user_permissions) if user_permissions else set()

        return permission_slug in permission_slugs

    def list_user_features(self, user: User) -> Dict[str, Any]:
        """
        Get list of features user can access (immediately or with approval).

        Returns:
            {
                "immediate_access": [features user can use right now],
                "requires_approval": [features user can request],
                "denied": [features user cannot access]
            }
        """
        immediate = []
        requires_approval = []
        denied = []

        for feature_id, feature in FEATURE_REGISTRY.items():
            check = self.check_permission(user, feature_id)

            if check["allowed"]:
                immediate.append({
                    "feature_id": feature_id,
                    "name": feature.name,
                    "ticket": check.get("ticket")
                })
            elif feature.requires_approval:
                requires_approval.append({
                    "feature_id": feature_id,
                    "name": feature.name,
                    "description": feature.description,
                    "risk_level": feature.risk_level,
                    "min_approver_role": feature.min_approver_role
                })
            else:
                # Missing base permission
                denied.append({
                    "feature_id": feature_id,
                    "name": feature.name,
                    "reason": "Missing permission"
                })

        return {
            "immediate_access": immediate,
            "requires_approval": requires_approval,
            "denied": denied
        }

    def revoke_feature_access(self, user_id: str, feature_id: str) -> bool:
        """
        Revoke all active tickets for a specific feature.

        Returns:
            Number of tickets revoked
        """
        now = datetime.now(timezone.utc)

        revoked_count = self.db.query(Approval).filter(
            and_(
                Approval.user_id == user_id,
                Approval.feature_id == feature_id,
                Approval.status == ApprovalStatus.APPROVED_ACTIVE,
                Approval.expires_at > now
            )
        ).update({
            "status": ApprovalStatus.REVOKED,
            "updated_at": now
        })

        self.db.commit()
        logger.info(f"Revoked {revoked_count} tickets for user {user_id} feature {feature_id}")
        return revoked_count > 0
