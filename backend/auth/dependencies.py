"""
Authentication Dependencies

Role-based access control and rate limiting for API endpoints.
"""

from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import User, UserRole, SandboxSession
from .jwt import get_current_active_user


def require_role(allowed_roles: List[str]):
    """
    Dependency factory for role-based access control

    Args:
        allowed_roles: List of allowed role names

    Returns:
        Dependency function that checks user role

    Example:
        @app.post("/admin/users")
        def create_user(
            user_data: UserCreate,
            current_user: User = Depends(require_role(["admin"]))
        ):
            # Only admins can access this endpoint
    """
    def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(allowed_roles)}"
            )
        return current_user

    return role_checker


def check_rate_limit(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Check rate limiting for sandbox sessions

    Enforces max 5 active sessions per user.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        User if within limits

    Raises:
        HTTPException: If user has exceeded rate limit

    Example:
        @app.post("/sandbox/sessions")
        def create_session(
            request: CreateSessionRequest,
            user: User = Depends(check_rate_limit),
            db: Session = Depends(get_db)
        ):
            # Create sandbox session
    """
    # Count active sandbox sessions for this user
    active_sessions = db.query(SandboxSession).filter(
        SandboxSession.user_id == current_user.id,
        SandboxSession.is_active == True
    ).count()

    MAX_SESSIONS = 5

    if active_sessions >= MAX_SESSIONS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {MAX_SESSIONS} active sessions allowed. "
                   f"Please end an existing session before creating a new one."
        )

    return current_user
