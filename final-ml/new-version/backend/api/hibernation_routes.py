"""
Hibernation API Routes

FastAPI endpoints for hibernation schedule management
"""
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user, RequireAccess
from backend.services.hibernation_service import get_hibernation_service
from backend.schemas.hibernation_schemas import (
    HibernationScheduleCreate,
    HibernationScheduleUpdate,
    HibernationScheduleResponse,
    HibernationScheduleList,
    HibernationScheduleFilter,
)

router = APIRouter(prefix="/hibernation", tags=["Hibernation"])


@router.post(
    "",
    response_model=HibernationScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create hibernation schedule",
    description="Create a new weekly hibernation schedule for a cluster"
)
def create_schedule(
    schedule_data: HibernationScheduleCreate,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> HibernationScheduleResponse:
    """
    Create hibernation schedule

    Creates a weekly hibernation schedule that defines:
    - 168-element matrix (7 days × 24 hours)
    - Each element: 0 (hibernate) or 1 (active)
    - Timezone for schedule interpretation
    - Pre-warm minutes before activation

    Example schedule_matrix:
    - [0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0, ...] (168 elements)
    - Index 0 = Monday 00:00, Index 167 = Sunday 23:00

    Args:
        schedule_data: Schedule configuration
        current_user: Authenticated user
        db: Database session

    Returns:
        Created schedule details
    """
    service = get_hibernation_service(db)
    return service.create_schedule(current_user.id, schedule_data)


@router.get(
    "",
    response_model=HibernationScheduleList,
    summary="List hibernation schedules",
    description="Get paginated list of hibernation schedules with filters"
)
def list_schedules(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    timezone: Optional[str] = Query(None, description="Filter by timezone"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> HibernationScheduleList:
    """
    List hibernation schedules with filters

    Supports filtering by:
    - Cluster ID
    - Active status
    - Timezone

    Args:
        cluster_id: Optional cluster filter
        is_active: Optional active status filter
        timezone: Optional timezone filter
        page: Page number (default: 1)
        page_size: Items per page (default: 50, max: 100)
        current_user: Authenticated user
        db: Database session

    Returns:
        Paginated list of schedules
    """
    filters = HibernationScheduleFilter(
        cluster_id=cluster_id,
        is_active=is_active,
        timezone=timezone,
        page=page,
        page_size=page_size
    )
    service = get_hibernation_service(db)
    return service.list_schedules(current_user.id, filters)


@router.get(
    "/{schedule_id}",
    response_model=HibernationScheduleResponse,
    summary="Get schedule details",
    description="Get detailed information about a specific hibernation schedule"
)
def get_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> HibernationScheduleResponse:
    """
    Get schedule by ID

    Args:
        schedule_id: Schedule UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Schedule details
    """
    service = get_hibernation_service(db)
    return service.get_schedule(schedule_id, current_user.id)


@router.get(
    "/cluster/{cluster_id}",
    response_model=Optional[HibernationScheduleResponse],
    summary="Get schedule for cluster",
    description="Get the hibernation schedule for a specific cluster"
)
def get_schedule_by_cluster(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Optional[HibernationScheduleResponse]:
    """
    Get schedule for cluster

    Each cluster can have at most one hibernation schedule.
    This endpoint retrieves the current schedule for a cluster.

    Args:
        cluster_id: Cluster UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Schedule details or null if no schedule exists
    """
    service = get_hibernation_service(db)
    return service.get_schedule_by_cluster(cluster_id, current_user.id)


@router.patch(
    "/{schedule_id}",
    response_model=HibernationScheduleResponse,
    summary="Update schedule",
    description="Update hibernation schedule configuration"
)
def update_schedule(
    schedule_id: str,
    update_data: HibernationScheduleUpdate,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> HibernationScheduleResponse:
    """
    Update schedule

    Allows updating:
    - Schedule matrix (168 elements)
    - Timezone
    - Pre-warm minutes
    - Active status

    Args:
        schedule_id: Schedule UUID
        update_data: Fields to update
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated schedule details
    """
    service = get_hibernation_service(db)
    return service.update_schedule(schedule_id, current_user.id, update_data)


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete schedule",
    description="Delete a hibernation schedule"
)
def delete_schedule(
    schedule_id: str,
    current_user: User = Depends(RequireAccess("FULL")),
    db: Session = Depends(get_db)
) -> None:
    """
    Delete schedule

    Removes the hibernation schedule from a cluster.
    The cluster will remain active 24/7 until a new schedule is created.

    Args:
        schedule_id: Schedule UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        None (204 No Content)
    """
    service = get_hibernation_service(db)
    service.delete_schedule(schedule_id, current_user.id)


@router.post(
    "/{schedule_id}/toggle",
    response_model=HibernationScheduleResponse,
    summary="Toggle schedule active status",
    description="Enable or disable a schedule without deleting it"
)
def toggle_schedule(
    schedule_id: str,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> HibernationScheduleResponse:
    """
    Toggle schedule active status

    Temporarily enable or disable a schedule without deleting it.
    Disabled schedules are not processed during hibernation checks.

    Args:
        schedule_id: Schedule UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated schedule with new active status
    """
    service = get_hibernation_service(db)
    return service.toggle_schedule(schedule_id, current_user.id)
