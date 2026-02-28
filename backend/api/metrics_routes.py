"""
Metrics API Routes

FastAPI endpoints for dashboard metrics and KPIs
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
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


class ClusterUtilizationResponse(BaseModel):
    cpu_history: List[float]
    memory_history: List[float]
    cpu_current: float
    memory_current: float

@router.get("/cluster/{cluster_id}/utilization", response_model=ClusterUtilizationResponse)
def get_cluster_utilization(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get cluster utilization history (7 days)"""
    from backend.models.cluster_metric import ClusterMetric
    from backend.models.cluster import Cluster
    from datetime import datetime, timedelta
    from sqlalchemy import func

    # Get cluster to verify access
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # Get current utilization from cluster table
    cpu_current = cluster.cpu_usage_pct or 0.0
    memory_current = cluster.mem_usage_pct or 0.0

    # Get 7-day history from cluster_metrics table
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy import cast, Float
    
    # Query daily average metrics
    daily_metrics = db.query(
        func.date(ClusterMetric.timestamp).label('day'),
        func.avg(cast(ClusterMetric.metric_data['cpu_usage_pct'].astext, Float)).label('avg_cpu'),
        func.avg(cast(ClusterMetric.metric_data['mem_usage_pct'].astext, Float)).label('avg_mem')
    ).filter(
        ClusterMetric.cluster_id == cluster_id,
        ClusterMetric.timestamp >= seven_days_ago
    ).group_by(
        func.date(ClusterMetric.timestamp)
    ).order_by('day').all()

    # Build 7-day arrays (fill missing days with 0)
    cpu_history = []
    memory_history = []

    if daily_metrics:
        for metric in daily_metrics[-7:]:  # Last 7 days
            cpu_history.append(round(metric.avg_cpu or 0.0, 2))
            memory_history.append(round(metric.avg_mem or 0.0, 2))

    # If no historical data, use current values
    if not cpu_history:
        cpu_history = [cpu_current] * 7
        memory_history = [memory_current] * 7

    # Pad if less than 7 days
    while len(cpu_history) < 7:
        cpu_history.insert(0, 0.0)
    while len(memory_history) < 7:
        memory_history.insert(0, 0.0)

    return {
        "cpu_history": cpu_history,
        "memory_history": memory_history,
        "cpu_current": round(cpu_current, 2),
        "memory_current": round(memory_current, 2)
    }

class NodeGroupStats(BaseModel):
    name: str
    instance_type: str
    count: int
    lifecycle: str  # spot/on-demand

@router.get("/cluster/{cluster_id}/nodegroups", response_model=List[NodeGroupStats])
def get_cluster_nodegroups(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get node group breakdown"""
    from backend.models.instance import Instance
    from sqlalchemy import func

    # Query instances grouped by node_group_name, instance_type, and lifecycle
    node_groups = db.query(
        Instance.node_group_name.label('name'),
        Instance.instance_type.label('instance_type'),
        Instance.lifecycle.label('lifecycle'),
        func.count(Instance.id).label('count')
    ).filter(
        Instance.cluster_id == cluster_id,
        Instance.state == 'running'
    ).group_by(
        Instance.node_group_name,
        Instance.instance_type,
        Instance.lifecycle
    ).all()

    result = []
    for ng in node_groups:
        result.append({
            "name": ng.name or f"{ng.lifecycle}-{ng.instance_type}",
            "instance_type": ng.instance_type,
            "count": ng.count,
            "lifecycle": ng.lifecycle.lower() if ng.lifecycle else "on-demand"
        })

    return result

class HealthEvent(BaseModel):
    timestamp: datetime
    status: str  # 'healthy', 'degraded', 'unavailable'
    message: str

@router.get("/cluster/{cluster_id}/health-timeline", response_model=List[HealthEvent])
def get_cluster_health_timeline(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get cluster health event timeline (24h)"""
    from backend.models.audit_log import AuditLog
    from backend.models.cluster import Cluster

    # Get cluster current status
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # Get audit logs for cluster in last 24 hours
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)

    # Query relevant events from audit logs
    events = db.query(AuditLog).filter(
        AuditLog.resource == cluster_id,
        AuditLog.timestamp >= twenty_four_hours_ago
    ).order_by(AuditLog.timestamp.desc()).limit(50).all()

    timeline = []

    # Map cluster status to health status
    status_map = {
        'ACTIVE': 'healthy',
        'ONLINE': 'healthy',
        'DEGRADED': 'degraded',
        'OFFLINE': 'unavailable',
        'ERROR': 'unavailable',
        'PROVISIONING': 'degraded'
    }

    # Add current status as most recent event
    current_status = status_map.get(cluster.status, 'healthy')
    timeline.append({
        "timestamp": cluster.last_heartbeat or datetime.utcnow(),
        "status": current_status,
        "message": f"Cluster {cluster.status.lower()}"
    })

    # Process audit log events
    for event in events:
        # Determine health status from event
        if event.outcome == 'SUCCESS':
            status = 'healthy'
            message = f"{event.event}: {event.actor_name}"
        elif event.outcome == 'FAILURE':
            status = 'degraded'
            message = f"Failed: {event.event}"
        else:
            status = 'degraded'
            message = event.event

        # Map specific events to health statuses
        if 'termination' in event.event.lower() or 'interrupt' in event.event.lower():
            status = 'degraded'
            message = f"Node interrupted: {event.event}"
        elif 'error' in event.event.lower():
            status = 'unavailable'
        elif 'scale' in event.event.lower() or 'node' in event.event.lower():
            status = 'healthy'

        timeline.append({
            "timestamp": event.timestamp,
            "status": status,
            "message": message
        })

    # If no events, create a healthy baseline
    if len(timeline) == 1:
        timeline.append({
            "timestamp": twenty_four_hours_ago,
            "status": "healthy",
            "message": "Cluster operational"
        })

    return timeline[:20]  # Return up to 20 most recent events


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


# ── Task 7.6: Decision Engine Rejection Counters ─────────────────────

@router.get(
    "/rejections/{cluster_id}",
    summary="Get rejection counters",
    description="Get decision engine rejection counters from Redis (24h rolling window)"
)
def get_rejection_counters(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
):
    """Fetch per-reason rejection counters for a cluster."""
    from backend.core.redis_client import get_redis_client
    from backend.core.logger import logger

    try:
        redis = get_redis_client()
        counters_key = f"spot:rejection_counters:{cluster_id}"
        raw = redis.hgetall(counters_key) or {}

        counters = {}
        for key, val in raw.items():
            reason = key.decode() if isinstance(key, bytes) else key
            counters[reason] = int(val)

        ttl = redis.ttl(counters_key)

        return {
            "status": "success",
            "cluster_id": cluster_id,
            "counters": counters,
            "ttl_seconds": ttl if ttl > 0 else None,
            "resets_in_hours": round(ttl / 3600, 1) if ttl and ttl > 0 else None,
        }
    except Exception as e:
        logger.error(f"Failed to fetch rejection counters for {cluster_id}: {e}")
        return {
            "status": "error",
            "cluster_id": cluster_id,
            "counters": {},
            "ttl_seconds": None,
            "resets_in_hours": None,
        }
