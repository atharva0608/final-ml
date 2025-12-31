"""
Metrics API Routes

FastAPI endpoints for dashboard metrics and KPIs
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user
from backend.services.metrics_service import get_metrics_service
from backend.schemas.metric_schemas import (
    DashboardKPIs,
    CostMetrics,
    InstanceMetrics,
    TimeSeriesData,
    ClusterMetrics,
    MetricFilter,
)
from datetime import datetime, timedelta

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get(
    "/dashboard",
    response_model=DashboardKPIs,
    summary="Get dashboard KPIs",
    description="Get key performance indicators for dashboard display"
)
def get_dashboard_kpis(
    start_date: Optional[datetime] = Query(None, description="Start of time range"),
    end_date: Optional[datetime] = Query(None, description="End of time range"),
    cluster_id: Optional[str] = Query(None, description="Filter by cluster ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> DashboardKPIs:
    """
    Get dashboard KPIs

    Returns key metrics including:
    - Total and active instances
    - Spot vs on-demand split
    - Total cost and estimated savings
    - Optimization job statistics

    Default time range: Last 30 days

    Args:
        start_date: Optional start date (default: 30 days ago)
        end_date: Optional end date (default: now)
        cluster_id: Optional cluster filter
        current_user: Authenticated user
        db: Database session

    Returns:
        Dashboard KPIs
    """
    filters = MetricFilter(
        start_date=start_date or (datetime.utcnow() - timedelta(days=30)),
        end_date=end_date or datetime.utcnow(),
        cluster_id=cluster_id
    )
    service = get_metrics_service(db)
    return service.get_dashboard_kpis(current_user.id, filters)


@router.get(
    "/cost",
    response_model=CostMetrics,
    summary="Get cost metrics",
    description="Get detailed cost breakdown"
)
def get_cost_metrics(
    start_date: Optional[datetime] = Query(None, description="Start of time range"),
    end_date: Optional[datetime] = Query(None, description="End of time range"),
    cluster_id: Optional[str] = Query(None, description="Filter by cluster ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> CostMetrics:
    """
    Get cost metrics

    Returns detailed cost breakdown:
    - Total cost
    - Spot instance cost
    - On-demand instance cost

    Default time range: Last 30 days

    Args:
        start_date: Optional start date (default: 30 days ago)
        end_date: Optional end date (default: now)
        cluster_id: Optional cluster filter
        current_user: Authenticated user
        db: Database session

    Returns:
        Cost metrics with breakdown
    """
    filters = MetricFilter(
        start_date=start_date or (datetime.utcnow() - timedelta(days=30)),
        end_date=end_date or datetime.utcnow(),
        cluster_id=cluster_id
    )
    service = get_metrics_service(db)
    return service.get_cost_metrics(current_user.id, filters)


@router.get(
    "/instances",
    response_model=InstanceMetrics,
    summary="Get instance metrics",
    description="Get instance usage breakdown"
)
def get_instance_metrics(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> InstanceMetrics:
    """
    Get instance metrics

    Returns instance counts by:
    - State (running, pending, stopping, stopped, terminated)
    - Lifecycle (spot, on-demand)
    - Architecture (amd64, arm64)

    Args:
        cluster_id: Optional cluster filter
        current_user: Authenticated user
        db: Database session

    Returns:
        Instance metrics with breakdowns
    """
    filters = MetricFilter(cluster_id=cluster_id)
    service = get_metrics_service(db)
    return service.get_instance_metrics(current_user.id, filters)


@router.get(
    "/cost/timeseries",
    response_model=TimeSeriesData,
    summary="Get cost time series",
    description="Get daily cost data over time for charts"
)
def get_cost_time_series(
    start_date: Optional[datetime] = Query(None, description="Start of time range"),
    end_date: Optional[datetime] = Query(None, description="End of time range"),
    cluster_id: Optional[str] = Query(None, description="Filter by cluster ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> TimeSeriesData:
    """
    Get cost time series

    Returns daily cost data points for charting.
    Useful for rendering cost trends over time.

    Default time range: Last 30 days

    Args:
        start_date: Optional start date (default: 30 days ago)
        end_date: Optional end date (default: now)
        cluster_id: Optional cluster filter
        current_user: Authenticated user
        db: Database session

    Returns:
        Time series data with daily cost points
    """
    filters = MetricFilter(
        start_date=start_date or (datetime.utcnow() - timedelta(days=30)),
        end_date=end_date or datetime.utcnow(),
        cluster_id=cluster_id
    )
    service = get_metrics_service(db)
    return service.get_cost_time_series(current_user.id, filters)


@router.get(
    "/cluster/{cluster_id}",
    response_model=ClusterMetrics,
    summary="Get cluster metrics",
    description="Get metrics for a specific cluster"
)
def get_cluster_metrics(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ClusterMetrics:
    """
    Get cluster metrics

    Returns cluster-specific metrics:
    - Instance counts
    - Spot vs on-demand split
    - Last optimization timestamp
    - Cluster status

    Args:
        cluster_id: Cluster UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Cluster metrics
    """
    service = get_metrics_service(db)
    return service.get_cluster_metrics(cluster_id, current_user.id)
