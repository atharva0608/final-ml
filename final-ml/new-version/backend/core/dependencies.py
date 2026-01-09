"""
FastAPI Dependencies

Dependency injection functions for authentication, authorization, and database access
"""
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from backend.models.base import get_db
from backend.models.user import User
from backend.core.crypto import decode_token
from backend.core.exceptions import (
    AuthenticationError,
    InvalidTokenError,
    TokenExpiredError,
    AuthorizationError,
    InsufficientPermissionsError
)
from backend.schemas.auth_schemas import UserContext


# HTTP Bearer token security
security = HTTPBearer()


def get_current_user_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> UserContext:
    """
    Extract and validate user context from JWT token

    Args:
        request: FastAPI request
        credentials: HTTP Bearer credentials
        db: Database session

    Returns:
        UserContext with user information

    Raises:
        AuthenticationError: If token is invalid or expired
    """
    token = credentials.credentials

    # Decode token
    payload = decode_token(token)
    if not payload:
        raise InvalidTokenError()

    # Extract user ID
    user_id: str = payload.get("sub")
    if not user_id:
        raise InvalidTokenError("Token missing user ID")

    # Verify user exists in database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AuthenticationError("User not found")

    # Return user context
    ctx = UserContext(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        organization_id=user.organization_id,
        org_role=user.org_role.value if user.org_role else None,
        access_level=user.access_level.value if user.access_level else None
    )
    
    # Store in request state for logging
    request.state.user_context = ctx
    
    return ctx


def get_current_user(
    user_context: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from database
    """
    user = db.query(User).filter(User.id == user_context.user_id).first()
    if not user:
        raise AuthenticationError("User not found")

    return user


def require_super_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Require super admin role
    """
    if current_user.role.value != "SUPER_ADMIN":
        raise InsufficientPermissionsError("This operation requires super admin privileges")

    return current_user


class RequireRole:
    """
    Dependency to require a minimum Organization Role
    Hierarchy: ORG_ADMIN > TEAM_LEAD > MEMBER
    """
    def __init__(self, min_role: str):
        self.min_role = min_role
        # Define hierarchy
        self.hierarchy = {
            "MEMBER": 0,
            "TEAM_LEAD": 1,
            "ORG_ADMIN": 2
        }

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        # Super admins always have access
        if current_user.role.value == "SUPER_ADMIN":
            return current_user

        if not current_user.organization_id:
            raise AuthorizationError("User does not belong to an organization")

        # Get values
        user_role_str = current_user.org_role.value if current_user.org_role else "MEMBER"
        
        user_level = self.hierarchy.get(user_role_str, 0)
        required_level = self.hierarchy.get(self.min_role, 0)

        if user_level < required_level:
            raise InsufficientPermissionsError(f"Role {self.min_role} or higher required")
            
        return current_user


class RequireAccess:
    """
    Dependency to require a minimum Access Level
    Hierarchy: READ_ONLY < EXECUTION < FULL
    """
    def __init__(self, min_level: str):
        self.min_level = min_level
        self.hierarchy = {
            "READ_ONLY": 0,
            "EXECUTION": 1,
            "FULL": 2
        }

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        # Super admins always have access
        if current_user.role.value == "SUPER_ADMIN":
            return current_user

        if not current_user.organization_id:
            raise AuthorizationError("User does not belong to an organization")

        # Get values
        user_access_str = current_user.access_level.value if current_user.access_level else "READ_ONLY"
        
        user_level = self.hierarchy.get(user_access_str, 0)
        required_level = self.hierarchy.get(self.min_level, 0)

        if user_level < required_level:
            raise InsufficientPermissionsError(f"Access Level {self.min_level} or higher required")
            
        return current_user


# Backward compatibility alias - requires ORG_ADMIN role
require_org_admin = RequireRole("ORG_ADMIN")


def verify_cluster_ownership(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> bool:
    """
    Verify user owns or has access to a cluster

    Args:
        cluster_id: Cluster UUID
        current_user: Current authenticated user
        db: Database session

    Returns:
        True if user has access

    Raises:
        AuthorizationError: If user doesn't have access
    """
    from backend.models.cluster import Cluster
    from backend.models.account import Account

    # Super admins have access to all clusters
    if current_user.role.value == "SUPER_ADMIN":
        return True

    # Check if user owns the cluster through their account
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise AuthorizationError("Cluster not found or access denied")

    # Check if cluster belongs to user's account
    account = db.query(Account).filter(
        Account.id == cluster.account_id,
        Account.organization_id == current_user.organization_id
    ).first()

    if not account:
        raise AuthorizationError("Access denied to this cluster")

    return True


def verify_template_ownership(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> bool:
    """
    Verify user owns a node template

    Args:
        template_id: Template UUID
        current_user: Current authenticated user
        db: Database session

    Returns:
        True if user owns template

    Raises:
        AuthorizationError: If user doesn't own template
    """
    from backend.models.node_template import NodeTemplate

    # Super admins have access to all templates
    if current_user.role.value == "SUPER_ADMIN":
        return True

    # Check if user owns the template
    template = db.query(NodeTemplate).filter(
        NodeTemplate.id == template_id,
        # Templates likely owned by Org too? Or User? For now keeping User but ideally Org
        # Assuming NodeTemplate will be migrated to Org later, leaving as is for now or updating if I updated model
        NodeTemplate.user_id == current_user.id
    ).first()

    if not template:
        raise AuthorizationError("Template not found or access denied")

    return True


def get_api_key_cluster(
    api_key: str,
    db: Session = Depends(get_db)
) -> str:
    """
    Validate API key and return associated cluster ID

    Used for Kubernetes Agent authentication

    Args:
        api_key: API key from Agent
        db: Database session

    Returns:
        Cluster ID associated with API key

    Raises:
        AuthenticationError: If API key is invalid
    """
    from backend.models.api_key import APIKey
    from backend.core.crypto import hash_api_key
    from datetime import datetime

    # Hash the provided API key
    key_hash = hash_api_key(api_key)

    # Look up API key in database
    api_key_record = db.query(APIKey).filter(
        APIKey.key_hash == key_hash
    ).first()

    if not api_key_record:
        raise AuthenticationError("Invalid API key")

    # Check if key is expired
    if api_key_record.expires_at and api_key_record.expires_at < datetime.utcnow():
        raise TokenExpiredError("API key has expired")

    # Update last used timestamp
    api_key_record.last_used_at = datetime.utcnow()
    db.commit()

    return api_key_record.cluster_id


async def verify_rate_limit(
    user_context: UserContext = Depends(get_current_user_context)
) -> bool:
    """
    Verify rate limit for user

    Args:
        user_context: User context from token

    Returns:
        True if within rate limit

    Raises:
        RateLimitError: If rate limit exceeded

    Note:
        This is a placeholder. Actual implementation should use Redis
        for distributed rate limiting.
    """
    # TODO: Implement Redis-based rate limiting
    # For now, always return True
    return True


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get current user if authenticated, None otherwise

    Useful for endpoints that work for both authenticated and anonymous users

    Args:
        credentials: Optional HTTP Bearer credentials
        db: Database session

    Returns:
        User if authenticated, None otherwise
    """
    if not credentials:
        return None

    try:
        user_context = get_current_user_context(credentials, db)
        return get_current_user(user_context, db)
    except Exception:
        # If authentication fails, return None instead of raising
        return None


def verify_account_ownership(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> bool:
    """
    Verify user owns an AWS account

    Args:
        account_id: Account UUID
        current_user: Current authenticated user
        db: Database session

    Returns:
        True if user owns account

    Raises:
        AuthorizationError: If user doesn't own account
    """
    from backend.models.account import Account

    # Super admins have access to all accounts
    if current_user.role.value == "SUPER_ADMIN":
        return True

    # Check if user owns the account
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.organization_id == current_user.organization_id
    ).first()

    if not account:
        raise AuthorizationError("Account not found or access denied")

    return True


def get_database_session() -> Session:
    """
    Get database session

    Yields:
        Database session
    """
    return get_db()
