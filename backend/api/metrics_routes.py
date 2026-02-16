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
    - Total cost and estimated savings (projected monthly for current month)
    - Optimization job statistics

    Default time range: Current month (beginning of month to today)

    Args:
        start_date: Optional start date (default: first day of current month)
        end_date: Optional end date (default: today)
        cluster_id: Optional cluster filter
        current_user: Authenticated user
        db: Database session

    Returns:
        Dashboard KPIs with projected monthly costs
    """
    # Default to current month for accurate monthly spend display
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    filters = MetricFilter(
        start_date=start_date or month_start,
        end_date=end_date or now,
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
    team_id: Optional[str] = Query(None, description="Filter by team ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> CostMetrics:
    """
    Get cost metrics

    Returns detailed cost breakdown:
    - Total cost (projected monthly for current month)
    - Spot instance cost
    - On-demand instance cost

    Default time range: Current month (beginning of month to today)

    Args:
        start_date: Optional start date (default: first day of current month)
        end_date: Optional end date (default: today)
        cluster_id: Optional cluster filter
        team_id: Optional team filter
        current_user: Authenticated user
        db: Database session

    Returns:
        Cost metrics with breakdown
    """
    # Default to current month for accurate monthly spend display
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    filters = MetricFilter(
        start_date=start_date or month_start,
        end_date=end_date or now,
        cluster_id=cluster_id,
        team_id=team_id
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
    team_id: Optional[str] = Query(None, description="Filter by team ID"),
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
        team_id: Optional team filter
        current_user: Authenticated user
        db: Database session

    Returns:
        Time series data with daily cost points
    """
    filters = MetricFilter(
        start_date=start_date or (datetime.utcnow() - timedelta(days=30)),
        end_date=end_date or datetime.utcnow(),
        cluster_id=cluster_id,
        team_id=team_id
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


@router.get(
    "/teams/{team_id}/summary",
    summary="Get team consolidated stats",
    description="Get aggregated metrics for all members in a team (Admin/Lead view)"
)
def get_team_summary(
    team_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get consolidated team statistics for Admin/Lead dashboard.
    
    Aggregates cost, waste, instance counts across all team members.
    Only accessible by ORG_ADMIN, CLIENT, or TEAM_LEAD of the team.
    
    Args:
        team_id: Team UUID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Consolidated team stats
    """
    from backend.models.user import UserRole
    from fastapi import HTTPException
    
    # Security Check: Only Leads/Admins can view consolidated data
    is_admin = current_user.role in [UserRole.ORG_ADMIN, UserRole.CLIENT, UserRole.SUPER_ADMIN]
    is_team_lead_of_team = current_user.role == UserRole.TEAM_LEAD and str(current_user.team_id) == team_id
    
    if not (is_admin or is_team_lead_of_team):
        raise HTTPException(403, "Access denied: consolidated view is restricted to admins and team leads.")
    
    service = get_metrics_service(db)
    return service.get_team_consolidated_stats(team_id)


@router.get(
    "/accounts/{account_id}/summary",
    summary="Get account consolidated stats",
    description="Get aggregated metrics for a specific AWS account"
)
def get_account_summary(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get consolidated account statistics.

    Aggregates cost, waste, instance counts for an AWS account.

    Args:
        account_id: Account UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Consolidated account stats
    """
    service = get_metrics_service(db)
    return service.get_account_consolidated_stats(account_id)


@router.get(
    "/cost/breakdown",
    summary="Get cost breakdown by service category",
    description="Get AWS cost breakdown by service category (EC2, Storage, Database, Networking, Others)"
)
def get_cost_breakdown(
    start_date: Optional[datetime] = Query(None, description="Start of time range"),
    end_date: Optional[datetime] = Query(None, description="End of time range"),
    team_id: Optional[str] = Query(None, description="Filter by team ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get cost breakdown by AWS service category for resource hygiene.

    Groups AWS services into categories:
    - EC2 (Compute instances and containers)
    - Storage (S3, EBS, EFS, Backup)
    - Database (RDS, DynamoDB, ElastiCache)
    - Networking (VPC, Data Transfer, Load Balancers)
    - Others (All remaining services like Security Hub, KMS, Config)

    Uses Cost Explorer data when available (100% accurate, includes all AWS services).
    Falls back to EC2 instance pricing if Cost Explorer data unavailable.

    Args:
        start_date: Optional start date (default: 30 days ago)
        end_date: Optional end date (default: now)
        team_id: Optional team filter
        current_user: Authenticated user
        db: Database session

    Returns:
        {
            "total_cost": 46.41,
            "breakdown": [
                {"category": "EC2", "cost": 22.62, "percentage": 48.7, "services": ["EC2 - Other", "EC2 - Compute"]},
                {"category": "Networking", "cost": 8.10, "percentage": 17.5, "services": ["VPC"]},
                {"category": "Others", "cost": 15.69, "percentage": 33.8, "services": ["Security Hub", "KMS"]}
            ]
        }
    """
    service = get_metrics_service(db)
    return service.get_cost_breakdown_by_service(
        user_id=current_user.id,
        start_date=start_date or (datetime.utcnow() - timedelta(days=30)),
        end_date=end_date or datetime.utcnow(),
        team_id=team_id
    )


@router.get("/waste-breakdown")
def get_waste_breakdown(
    start_date: Optional[datetime] = Query(None, description="Start date for analysis"),
    end_date: Optional[datetime] = Query(None, description="End date for analysis"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get A+B waste breakdown for Financial Engineering Dashboard.

    Returns:
        {
            "hygiene_waste": {
                "orphaned_volumes": 8.50,
                "orphaned_snapshots": 4.20,
                "unused_eips": 3.65,
                "idle_load_balancers": 0.95,
                "idle_rds": 0.00,
                "total": 17.30
            },
            "optimization_waste": {
                "ri_waste": 7.50,
                "s3_lifecycle": 3.20,
                "rds_multiaz": 2.10,
                "data_transfer": 0.00,
                "total": 12.80
            },
            "total_waste": 30.10,
            "current_spend": 59.39,
            "optimized_spend": 29.29,
            "savings_percentage": 50.7
        }

    A = Hygiene Waste (orphaned resources)
    B = Optimization Waste (inefficient configurations)
    Total Potential Savings = A + B
    """
    service = get_metrics_service(db)
    return service.get_waste_breakdown(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date
    )
