"""
Lab API Routes

FastAPI endpoints for ML experimentation and A/B testing
"""
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user, RequireAccess
from backend.services.lab_service import get_lab_service
from backend.schemas.lab_schemas import (
    ExperimentCreate,
    ExperimentUpdate,
    ExperimentResponse,
    ExperimentList,
    ExperimentFilter,
    ExperimentResults,
)

router = APIRouter(prefix="/lab", tags=["Lab"])


@router.post(
    "/experiments",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create experiment",
    description="Create a new A/B testing experiment"
)
def create_experiment(
    experiment_data: ExperimentCreate,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> ExperimentResponse:
    """
    Create experiment

    Creates a new A/B testing experiment to compare two ML models:
    - Control model (baseline)
    - Variant model (new/experimental)

    Traffic is split according to specified percentages:
    - control_percentage + variant_percentage must equal 100

    Experiment starts in DRAFT status and must be explicitly started.

    Args:
        experiment_data: Experiment configuration
        current_user: Authenticated user
        db: Database session

    Returns:
        Created experiment details
    """
    service = get_lab_service(db)
    return service.create_experiment(current_user.id, experiment_data)


@router.get(
    "/experiments",
    response_model=ExperimentList,
    summary="List experiments",
    description="Get paginated list of experiments with filters"
)
def list_experiments(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster ID"),
    status: Optional[str] = Query(None, description="Filter by status (DRAFT/RUNNING/COMPLETED/CANCELLED)"),
    search: Optional[str] = Query(None, description="Search by name"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ExperimentList:
    """
    List experiments with filters

    Supports filtering by:
    - Cluster ID
    - Status (DRAFT, RUNNING, COMPLETED, CANCELLED)
    - Search text (matches name)

    Args:
        cluster_id: Optional cluster filter
        status: Optional status filter
        search: Optional search query
        page: Page number (default: 1)
        page_size: Items per page (default: 50, max: 100)
        current_user: Authenticated user
        db: Database session

    Returns:
        Paginated list of experiments
    """
    filters = ExperimentFilter(
        cluster_id=cluster_id,
        status=status,
        search=search,
        page=page,
        page_size=page_size
    )
    service = get_lab_service(db)
    return service.list_experiments(current_user.id, filters)


@router.get(
    "/experiments/{experiment_id}",
    response_model=ExperimentResponse,
    summary="Get experiment details",
    description="Get detailed information about a specific experiment"
)
def get_experiment(
    experiment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ExperimentResponse:
    """
    Get experiment by ID

    Args:
        experiment_id: Experiment UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Experiment details
    """
    service = get_lab_service(db)
    return service.get_experiment(experiment_id, current_user.id)


@router.patch(
    "/experiments/{experiment_id}",
    response_model=ExperimentResponse,
    summary="Update experiment",
    description="Update experiment configuration (only if not running)"
)
def update_experiment(
    experiment_id: str,
    update_data: ExperimentUpdate,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> ExperimentResponse:
    """
    Update experiment

    Allows updating experiment configuration:
    - Name and description
    - Model IDs
    - Traffic allocation percentages
    - Custom configuration

    Note: Can only update experiments in DRAFT status.
    Running or completed experiments cannot be modified.

    Args:
        experiment_id: Experiment UUID
        update_data: Fields to update
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated experiment details
    """
    service = get_lab_service(db)
    return service.update_experiment(experiment_id, current_user.id, update_data)


@router.delete(
    "/experiments/{experiment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete experiment",
    description="Delete an experiment (cannot delete running experiments)"
)
def delete_experiment(
    experiment_id: str,
    current_user: User = Depends(RequireAccess("FULL")),
    db: Session = Depends(get_db)
) -> None:
    """
    Delete experiment

    Removes an experiment from the system.
    Cannot delete running experiments - stop them first.

    Args:
        experiment_id: Experiment UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        None (204 No Content)
    """
    service = get_lab_service(db)
    service.delete_experiment(experiment_id, current_user.id)


@router.post(
    "/experiments/{experiment_id}/start",
    response_model=ExperimentResponse,
    summary="Start experiment",
    description="Start a draft experiment"
)
def start_experiment(
    experiment_id: str,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> ExperimentResponse:
    """
    Start experiment

    Begins the experiment and starts routing traffic according
    to the configured allocation percentages.

    Status transition: DRAFT → RUNNING

    Args:
        experiment_id: Experiment UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated experiment with RUNNING status
    """
    service = get_lab_service(db)
    return service.start_experiment(experiment_id, current_user.id)


@router.post(
    "/experiments/{experiment_id}/stop",
    response_model=ExperimentResponse,
    summary="Stop experiment",
    description="Stop a running experiment"
)
def stop_experiment(
    experiment_id: str,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> ExperimentResponse:
    """
    Stop experiment

    Ends the experiment and finalizes results.
    Traffic allocation returns to 100% control.

    Status transition: RUNNING → COMPLETED

    Args:
        experiment_id: Experiment UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated experiment with COMPLETED status
    """
    service = get_lab_service(db)
    return service.stop_experiment(experiment_id, current_user.id)


@router.get(
    "/experiments/{experiment_id}/results",
    response_model=ExperimentResults,
    summary="Get experiment results",
    description="Get performance comparison and analysis"
)
def get_experiment_results(
    experiment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ExperimentResults:
    """
    Get experiment results

    Returns detailed performance comparison between
    control and variant models including:
    - Total predictions per variant
    - Average cost and savings
    - Success rate
    - Statistical winner (if experiment completed)

    Args:
        experiment_id: Experiment UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Experiment results with performance comparison
    """
    service = get_lab_service(db)
    return service.get_experiment_results(experiment_id, current_user.id)
