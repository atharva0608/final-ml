"""
Policy API Routes

FastAPI endpoints for cluster optimization policy management
"""
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user
from backend.services.policy_service import get_policy_service
from backend.schemas.policy_schemas import (
    PolicyCreate,
    PolicyUpdate,
    PolicyResponse,
    PolicyList,
    PolicyFilter,
)

router = APIRouter(prefix="/policies", tags=["Policies"])


@router.post(
    "",
    response_model=PolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create optimization policy",
    description="Create a new optimization policy for a cluster"
)
def create_policy(
    policy_data: PolicyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> PolicyResponse:
    """
    Create optimization policy

    Creates a new optimization policy that defines:
    - Spot instance percentage (0-100%)
    - Node template for instance selection
    - Scaling rules (min/max nodes)
    - Target utilization thresholds
    - Fallback and diversification strategies

    Args:
        policy_data: Policy configuration
        current_user: Authenticated user
        db: Database session

    Returns:
        Created policy details
    """
    service = get_policy_service(db)
    return service.create_policy(current_user.id, policy_data)


@router.get(
    "",
    response_model=PolicyList,
    summary="List policies",
    description="Get paginated list of optimization policies with filters"
)
def list_policies(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster ID"),
    template_id: Optional[str] = Query(None, description="Filter by template ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    min_spot_percentage: Optional[int] = Query(None, ge=0, le=100, description="Minimum spot percentage"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> PolicyList:
    """
    List policies with filters

    Supports filtering by:
    - Cluster ID
    - Template ID
    - Active status
    - Minimum spot percentage

    Args:
        cluster_id: Optional cluster filter
        template_id: Optional template filter
        is_active: Optional active status filter
        min_spot_percentage: Optional minimum spot percentage
        page: Page number (default: 1)
        page_size: Items per page (default: 50, max: 100)
        current_user: Authenticated user
        db: Database session

    Returns:
        Paginated list of policies
    """
    filters = PolicyFilter(
        cluster_id=cluster_id,
        template_id=template_id,
        is_active=is_active,
        min_spot_percentage=min_spot_percentage,
        page=page,
        page_size=page_size
    )
    service = get_policy_service(db)
    return service.list_policies(current_user.id, filters)


@router.get(
    "/{policy_id}",
    response_model=PolicyResponse,
    summary="Get policy details",
    description="Get detailed information about a specific policy"
)
def get_policy(
    policy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> PolicyResponse:
    """
    Get policy by ID

    Args:
        policy_id: Policy UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Policy details
    """
    service = get_policy_service(db)
    return service.get_policy(policy_id, current_user.id)


@router.get(
    "/cluster/{cluster_id}",
    response_model=Optional[PolicyResponse],
    summary="Get policy for cluster",
    description="Get the optimization policy for a specific cluster"
)
def get_policy_by_cluster(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Optional[PolicyResponse]:
    """
    Get policy for cluster

    Each cluster can have at most one active optimization policy.
    This endpoint retrieves the current policy for a cluster.

    Args:
        cluster_id: Cluster UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Policy details or null if no policy exists
    """
    service = get_policy_service(db)
    return service.get_policy_by_cluster(cluster_id, current_user.id)


@router.patch(
    "/{policy_id}",
    response_model=PolicyResponse,
    summary="Update policy",
    description="Update optimization policy configuration"
)
def update_policy(
    policy_id: str,
    update_data: PolicyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> PolicyResponse:
    """
    Update policy

    Allows updating any policy configuration including:
    - Spot percentage
    - Node template
    - Scaling parameters
    - Target utilization
    - Diversification settings

    Args:
        policy_id: Policy UUID
        update_data: Fields to update
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated policy details
    """
    service = get_policy_service(db)
    return service.update_policy(policy_id, current_user.id, update_data)


@router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete policy",
    description="Delete an optimization policy"
)
def delete_policy(
    policy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> None:
    """
    Delete policy

    Removes the optimization policy from a cluster.
    The cluster will no longer have automated optimization applied.

    Args:
        policy_id: Policy UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        None (204 No Content)
    """
    service = get_policy_service(db)
    service.delete_policy(policy_id, current_user.id)


@router.post(
    "/{policy_id}/toggle",
    response_model=PolicyResponse,
    summary="Toggle policy active status",
    description="Enable or disable a policy without deleting it"
)
def toggle_policy(
    policy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> PolicyResponse:
    """
    Toggle policy active status

    Temporarily enable or disable a policy without deleting it.
    Disabled policies are not applied during optimization runs.

    Args:
        policy_id: Policy UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated policy with new active status
    """
    service = get_policy_service(db)
    return service.toggle_policy(policy_id, current_user.id)
