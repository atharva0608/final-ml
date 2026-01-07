"""
Cluster API Routes

FastAPI endpoints for cluster discovery and management
"""
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user
from backend.services.cluster_service import get_cluster_service
from backend.schemas.cluster_schemas import (
    ClusterCreate,
    ClusterUpdate,
    ClusterResponse,
    ClusterList,
    ClusterFilter,
    ClusterFilter,
    AgentInstallCommand,
    AWSConnectRequest,
)

router = APIRouter(prefix="/clusters", tags=["Clusters"])


@router.post(
    "/discover",
    response_model=list[ClusterResponse],
    status_code=status.HTTP_200_OK,
    summary="Discover clusters in AWS account",
    description="Automatically discover EKS and self-managed Kubernetes clusters"
)
def discover_clusters(
    account_id: str = Query(..., description="AWS Account ID to discover clusters in"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> list[ClusterResponse]:
    """
    Discover clusters in AWS account

    Automatically discovers:
    - Amazon EKS clusters
    - Self-managed Kubernetes clusters with specific tags

    Args:
        account_id: Account UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        List of discovered clusters
    """
    service = get_cluster_service(db)
    return service.discover_clusters(account_id, current_user.id)


@router.post(
    "",
    response_model=ClusterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a cluster",
    description="Manually register a Kubernetes cluster"
)
def register_cluster(
    cluster_data: ClusterCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ClusterResponse:
    """
    Register a new cluster

    Manually register a Kubernetes cluster that wasn't auto-discovered
    or to add additional metadata.

    Args:
        cluster_data: Cluster creation data
        current_user: Authenticated user
        db: Database session

    Returns:
        Registered cluster details
    """
    service = get_cluster_service(db)
    return service.register_cluster(current_user.id, cluster_data)


@router.post(
    "/connect-aws",
    response_model=ClusterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Connect AWS cluster",
    description="Connect an AWS EKS cluster using IAM Role (Agentless)"
)
def connect_aws_cluster(
    connect_data: AWSConnectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ClusterResponse:
    """
    Connect AWS EKS cluster using STS Assume Role

    Args:
        connect_data: Connection details (ARN, External ID)
        current_user: Authenticated user
        db: Database session

    Returns:
        Connected cluster details
    """
    service = get_cluster_service(db)
    return service.connect_aws_cluster(current_user.id, connect_data)


@router.get(
    "",
    response_model=ClusterList,
    summary="List clusters",
    description="Get paginated list of clusters with filters"
)
def list_clusters(
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    region: Optional[str] = Query(None, description="Filter by AWS region"),
    cluster_type: Optional[str] = Query(None, description="Filter by cluster type (EKS/SELF_MANAGED)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by name or ARN"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ClusterList:
    """
    List clusters with filters

    Supports filtering by:
    - Account ID
    - AWS region
    - Cluster type (EKS or self-managed)
    - Status (DISCOVERED, ACTIVE, INACTIVE, ERROR)
    - Search text (matches name or ARN)

    Args:
        account_id: Optional account filter
        region: Optional region filter
        cluster_type: Optional type filter
        status: Optional status filter
        search: Optional search query
        page: Page number (default: 1)
        page_size: Items per page (default: 50, max: 100)
        current_user: Authenticated user
        db: Database session

    Returns:
        Paginated list of clusters
    """
    filters = ClusterFilter(
        account_id=account_id,
        region=region,
        cluster_type=cluster_type,
        status=status,
        search=search,
        page=page,
        page_size=page_size
    )
    service = get_cluster_service(db)
    return service.list_clusters(current_user.id, filters)


@router.get(
    "/{cluster_id}",
    response_model=ClusterResponse,
    summary="Get cluster details",
    description="Get detailed information about a specific cluster"
)
def get_cluster(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ClusterResponse:
    """
    Get cluster by ID

    Args:
        cluster_id: Cluster UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Cluster details
    """
    service = get_cluster_service(db)
    return service.get_cluster(cluster_id, current_user.id)


@router.patch(
    "/{cluster_id}",
    response_model=ClusterResponse,
    summary="Update cluster",
    description="Update cluster details"
)
def update_cluster(
    cluster_id: str,
    update_data: ClusterUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ClusterResponse:
    """
    Update cluster

    Allows updating:
    - Version
    - Endpoint
    - Tags
    - Status

    Args:
        cluster_id: Cluster UUID
        update_data: Fields to update
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated cluster details
    """
    service = get_cluster_service(db)
    return service.update_cluster(cluster_id, current_user.id, update_data)


@router.delete(
    "/{cluster_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete cluster",
    description="Delete a cluster (must have no active instances)"
)
def delete_cluster(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> None:
    """
    Delete cluster

    Cannot delete clusters with active instances.
    Terminate all instances before deleting the cluster.

    Args:
        cluster_id: Cluster UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        None (204 No Content)
    """
    service = get_cluster_service(db)
    service.delete_cluster(cluster_id, current_user.id)


@router.get(
    "/{cluster_id}/agent-install",
    response_model=AgentInstallCommand,
    summary="Get agent installation command",
    description="Generate Kubernetes Agent installation command for cluster"
)
def get_agent_install_command(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> AgentInstallCommand:
    """
    Get agent installation command

    Generates a kubectl command to install the Spot Optimizer Agent
    in the Kubernetes cluster. The agent polls for actions and executes
    Kubernetes operations (evict, cordon, drain, label).

    Args:
        cluster_id: Cluster UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Installation command and instructions
    """
    service = get_cluster_service(db)
    return service.generate_agent_install_command(cluster_id, current_user.id)


@router.post(
    "/{cluster_id}/heartbeat",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update cluster heartbeat",
    description="Agent endpoint to update cluster heartbeat"
)
def update_heartbeat(
    cluster_id: str,
    db: Session = Depends(get_db)
) -> None:
    """
    Update cluster heartbeat

    Called by the Kubernetes Agent every 60 seconds to indicate
    the cluster is alive and the agent is functioning.

    Args:
        cluster_id: Cluster UUID
        db: Database session

    Returns:
        None (204 No Content)
    """
    service = get_cluster_service(db)
    service.update_heartbeat(cluster_id)
