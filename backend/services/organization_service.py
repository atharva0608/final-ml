from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from backend.models.user import User, OrgRole, UserRole
from backend.core.exceptions import ValidationError, ResourceNotFoundError, ForbiddenError
from backend.core.crypto import hash_password
from backend.schemas.organization_schemas import MemberResponse, MemberListResponse
import secrets
import string

class OrganizationService:
    def __init__(self, db: Session):
        self.db = db

    def list_members(self, organization_id: str) -> MemberListResponse:
        """List all members of an organization"""
        members = self.db.query(User).filter(
            User.organization_id == organization_id
        ).all()
        
        return MemberListResponse(
            members=[self._map_to_response(u) for u in members],
            total=len(members)
        )

    def create_invitation(self, organization_id: str, email: str, role_str: str, access_level_str: str, requesting_user: User) -> dict:
        """
        Directly add a new member to the organization.
        Creates a user account with default credentials.
        """
        from backend.models.user import AccessLevel, UserRole
        from datetime import datetime
        import uuid

        # 1. Validate Target Role/Access
        try:
            target_role = OrgRole[role_str.upper()]
            target_access = AccessLevel[access_level_str.upper()]
        except KeyError:
            raise ValidationError("Invalid role or access level")

        # 2. Enforce Hierarchy - ONLY ORG_ADMIN can invite
        req_role_val = requesting_user.org_role
        
        if req_role_val != OrgRole.ORG_ADMIN:
            raise ForbiddenError("Only organization administrators can add new members")

        # 3. Check if user already exists
        existing_user = self.db.query(User).filter(User.email == email).first()
        if existing_user:
            raise ValidationError("User with this email already exists")

        # 4. Create User directly
        DEFAULT_PASSWORD = "demo1234"
        hashed_pw = hash_password(DEFAULT_PASSWORD)
        
        # Determine organization_id
        # Explicitly use the passed organization_id
        
        new_user = User(
            email=email,
            password_hash=hashed_pw,
            role=UserRole.CLIENT,
            organization_id=organization_id,
            org_role=target_role,
            access_level=target_access,
            is_active="Y",
            must_reset_password=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)
        
        return {
            "message": "Member added successfully",
            "user": self._map_to_response(new_user),
            "temporary_password": DEFAULT_PASSWORD
        }

    def remove_member(self, organization_id: str, target_user_id: str, requesting_user: User):
        """
        Remove a member from the organization.
        Enforces Hierarchy.
        """
        user = self.db.query(User).filter(
            and_(User.id == target_user_id, User.organization_id == organization_id)
        ).first()

        if not user:
            raise ResourceNotFoundError("User", target_user_id)

        # Cannot remove yourself
        if user.id == requesting_user.id:
            raise ValidationError("Cannot remove yourself")

        # Hierarchy Check
        req_role = requesting_user.org_role
        target_role = user.org_role

        if req_role == OrgRole.ORG_ADMIN:
            # Org Admin can remove anyone (except maybe other Org Admins if policy restricts, but prompt says "can manage all users including other admins")
            pass
        elif req_role == OrgRole.TEAM_LEAD:
            # Team Lead can only remove MEMBERS
            if target_role != OrgRole.MEMBER:
                raise ForbiddenError("Team Leads can only remove Members")
        else:
            raise ForbiddenError("Insufficient permissions to remove members")

        self.db.delete(user)
        self.db.commit()

    def update_member_role(self, organization_id: str, target_user_id: str, new_role_str: Optional[str], new_access_str: Optional[str], requesting_user: User):
        """
        Update a member's role or access level.
        Enforces Hierarchy.
        """
        from backend.models.user import AccessLevel

        user = self.db.query(User).filter(
            and_(User.id == target_user_id, User.organization_id == organization_id)
        ).first()

        if not user:
            raise ResourceNotFoundError("User", target_user_id)

        if user.id == requesting_user.id:
            raise ValidationError("Cannot update your own role/access")

        # Validate New Values
        try:
            new_role_enum = OrgRole[new_role_str.upper()] if new_role_str else user.org_role
            new_access_enum = AccessLevel[new_access_str.upper()] if new_access_str else user.access_level
        except KeyError:
            raise ValidationError("Invalid role or access level")

        # Hierarchy Check
        req_role = requesting_user.org_role
        target_current_role = user.org_role

        if req_role == OrgRole.ORG_ADMIN:
            # Can change anything
            pass
        elif req_role == OrgRole.TEAM_LEAD:
            # Can only manage MEMBERS
            if target_current_role != OrgRole.MEMBER:
                raise ForbiddenError("Team Leads cannot modify non-members")
            
            # Cannot promote TO non-member
            if new_role_enum != OrgRole.MEMBER:
                raise ForbiddenError("Team Leads cannot promote users above Member")
        else:
            raise ForbiddenError("Insufficient permissions")

        user.org_role = new_role_enum
        user.access_level = new_access_enum
        self.db.commit()
        self.db.refresh(user)
        return self._map_to_response(user)

    def accept_invitation(self, token: str) -> dict:
        """
        Accept an organization invitation and create a new user account.
        
        Validates:
        - Token exists and is PENDING
        - Token has not expired
        - Email is not already registered
        
        Creates user with default password (demo1234) and requires password reset.
        """
        from backend.models.invitation import OrganizationInvitation, InvitationStatus
        from backend.models.user import AccessLevel
        from datetime import datetime

        # Default password for invited users
        DEFAULT_PASSWORD = "demo1234"

        # 1. Find invitation by token
        invitation = self.db.query(OrganizationInvitation).filter(
            OrganizationInvitation.token == token
        ).first()
        
        if not invitation:
            raise ResourceNotFoundError("Invitation", token)
        
        # 2. Check status
        if invitation.status != InvitationStatus.PENDING:
            raise ValidationError(f"Invitation has already been {invitation.status.value.lower()}")
        
        # 3. Check expiration
        if invitation.expires_at < datetime.utcnow():
            invitation.status = InvitationStatus.EXPIRED
            self.db.commit()
            raise ValidationError("Invitation has expired")
        
        # 4. Check if user already exists
        existing_user = self.db.query(User).filter(User.email == invitation.email).first()
        if existing_user:
            raise ValidationError("An account with this email already exists")
        
        # 5. Create user with default password and must_reset_password flag
        hashed_pw = hash_password(DEFAULT_PASSWORD)
        new_user = User(
            email=invitation.email,
            password_hash=hashed_pw,
            role=UserRole.CLIENT,
            organization_id=invitation.organization_id,
            org_role=invitation.role,
            access_level=invitation.access_level,
            is_active="Y",
            must_reset_password=True  # Force password reset on first login
        )
        self.db.add(new_user)
        
        # 6. Mark invitation as ACCEPTED (atomic)
        invitation.status = InvitationStatus.ACCEPTED
        
        self.db.commit()
        self.db.refresh(new_user)
        
        return {
            "message": "Invitation accepted successfully. Please reset your password on first login.",
            "user_id": new_user.id,
            "email": new_user.email,
            "organization_id": new_user.organization_id,
            "org_role": new_user.org_role.value,
            "access_level": new_user.access_level.value,
            "must_reset_password": True,
            "temporary_password": DEFAULT_PASSWORD
        }

    def _map_to_response(self, user: User) -> MemberResponse:
        return MemberResponse(
            id=user.id,
            email=user.email,
            org_role=user.org_role.value if user.org_role else "MEMBER",
            access_level=user.access_level.value if user.access_level else "READ_ONLY",
            is_active=user.is_active == "Y",
            created_at=user.created_at
        )

def get_organization_service(db: Session):
    return OrganizationService(db)

