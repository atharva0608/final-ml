"""
Admin API Routes

FastAPI endpoints for super admin operations and user management
"""
from fastapi import APIRouter, Depends, status, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user
from backend.services.admin_service import get_admin_service
from backend.schemas.admin_schemas import (
    ClientList,
    ClientFilter,
    UserManagement,
    PlatformStats,
    PasswordReset,
)
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/clients",
    response_model=ClientList,
    summary="List all clients",
    description="Get paginated list of client users (Super admin only)"
)
def list_clients(
    search: Optional[str] = Query(None, description="Search by email or ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    created_after: Optional[datetime] = Query(None, description="Filter by creation date (after)"),
    created_before: Optional[datetime] = Query(None, description="Filter by creation date (before)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ClientList:
    """
    List all client users

    Super admin only endpoint to view all registered clients
    with filtering and pagination.

    Supports filtering by:
    - Search text (email or ID)
    - Active status
    - Creation date range

    Args:
        search: Optional search query
        is_active: Optional active status filter
        created_after: Optional creation date filter (after)
        created_before: Optional creation date filter (before)
        page: Page number (default: 1)
        page_size: Items per page (default: 50, max: 100)
        current_user: Authenticated user (must be super admin)
        db: Database session

    Returns:
        Paginated list of clients with summary stats
    """
    filters = ClientFilter(
        search=search,
        is_active=is_active,
        created_after=created_after,
        created_before=created_before,
        page=page,
        page_size=page_size
    )
    service = get_admin_service(db)
    return service.list_clients(current_user, filters)


@router.get(
    "/clients/{client_id}",
    response_model=UserManagement,
    summary="Get client details",
    description="Get detailed information about a specific client (Super admin only)"
)
def get_client_details(
    client_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> UserManagement:
    """
    Get client details

    Retrieves detailed information about a specific client including:
    - User profile
    - Account statistics
    - Cluster and instance counts
    - Cost metrics

    Args:
        client_id: Client user ID
        current_user: Authenticated user (must be super admin)
        db: Database session

    Returns:
        Full client details with statistics
    """
    service = get_admin_service(db)
    return service.get_client_details(current_user, client_id)


@router.post(
    "/clients/{client_id}/toggle",
    response_model=UserManagement,
    summary="Toggle client active status",
    description="Activate or deactivate a client user (Super admin only)"
)
def toggle_client_status(
    client_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> UserManagement:
    """
    Toggle client active status

    Enable or disable a client account. Disabled accounts
    cannot log in or access the platform.

    Args:
        client_id: Client user ID
        current_user: Authenticated user (must be super admin)
        db: Database session

    Returns:
        Updated client details
    """
    service = get_admin_service(db)
    return service.toggle_client_status(current_user, client_id)


@router.post(
    "/clients/{client_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset client password",
    description="Reset a client's password (Super admin only)"
)
def reset_client_password(
    client_id: str,
    password_data: PasswordReset,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> None:
    """
    Reset client password

    Allows super admin to reset a client's password.
    Useful for account recovery or security purposes.

    The new password must meet strength requirements:
    - At least 8 characters
    - Contains uppercase and lowercase letters
    - Contains at least one digit

    Args:
        client_id: Client user ID
        password_data: New password
        current_user: Authenticated user (must be super admin)
        db: Database session

    Returns:
        None (204 No Content)
    """
    service = get_admin_service(db)
    service.reset_client_password(
        current_user,
        client_id,
        password_data.new_password
    )


@router.get(
    "/stats",
    response_model=PlatformStats,
    summary="Get platform statistics",
    description="Get aggregated platform-wide statistics (Super admin only)"
)
def get_platform_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> PlatformStats:
    """
    Get platform statistics

    Returns aggregated metrics across the entire platform:
    - Total and active users
    - Recent signups (last 30 days)
    - Total clusters and instances
    - Spot vs on-demand split
    - Total platform cost

    Args:
        current_user: Authenticated user (must be super admin)
        db: Database session

    Returns:
        Platform-wide statistics
    """
    service = get_admin_service(db)
    return service.get_platform_stats(current_user)
