"""
Hibernation Schedule API Routes

REST API endpoints for managing hibernation schedules.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from backend.core.dependencies import get_db, get_current_user
from backend.services.hibernation_service import HibernationService
from backend.schemas.hibernation_schemas import (
    HibernationScheduleCreate,
    HibernationScheduleUpdate,
    HibernationScheduleResponse,
    HibernationScheduleList,
    StrategyComparisonResponse,
    SavingsEstimateResponse,
    ConflictCheckResponse
)
from backend.models.user import User
from backend.models.hibernation_schedule import HibernationStrategy, ScheduleType

router = APIRouter(prefix="/hibernation", tags=["Hibernation"])


@router.get("/schedules", response_model=HibernationScheduleList)
def list_schedules(
    cluster_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List hibernation schedules with filtering"""
    service = HibernationService(db)
    schedules, total = service.list_schedules(
        cluster_id=cluster_id,
        is_active=is_active,
        page=page,
        page_size=page_size
    )
    
    return {
        "schedules": schedules,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/schedules/{schedule_id}", response_model=HibernationScheduleResponse)
def get_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific hibernation schedule"""
    service = HibernationService(db)
    return service.get_schedule(schedule_id)


@router.post("/schedules", response_model=HibernationScheduleResponse)
def create_schedule(
    schedule_data: HibernationScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new hibernation schedule"""
    service = HibernationService(db)
    
    return service.create_schedule(
        name=schedule_data.name,
        description=schedule_data.description,
        schedule_matrix=schedule_data.schedule_matrix,
        strategy=HibernationStrategy(schedule_data.strategy),
        cluster_ids=schedule_data.cluster_ids,
        schedule_type=ScheduleType(schedule_data.schedule_type),
        date_overrides=schedule_data.date_overrides,
        timezone=schedule_data.timezone,
        pre_warm_minutes=schedule_data.pre_warm_minutes,
        is_active=schedule_data.is_active
    )


@router.put("/schedules/{schedule_id}", response_model=HibernationScheduleResponse)
def update_schedule(
    schedule_id: str,
    schedule_data: HibernationScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing hibernation schedule"""
    service = HibernationService(db)
    
    updates = schedule_data.dict(exclude_unset=True)
    if "strategy" in updates:
        updates["strategy"] = HibernationStrategy(updates["strategy"])
    if "schedule_type" in updates:
        updates["schedule_type"] = ScheduleType(updates["schedule_type"])
    
    return service.update_schedule(schedule_id, **updates)


@router.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a hibernation schedule"""
    service = HibernationService(db)
    service.delete_schedule(schedule_id)
    return {"message": "Schedule deleted successfully"}


@router.post("/schedules/{schedule_id}/toggle", response_model=HibernationScheduleResponse)
def toggle_schedule(
    schedule_id: str,
    is_active: bool = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Activate or pause a hibernation schedule"""
    service = HibernationService(db)
    return service.toggle_schedule(schedule_id, is_active)


@router.get("/strategies/compare", response_model=List[StrategyComparisonResponse])
def compare_strategies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comparison data for all hibernation strategies"""
    service = HibernationService(db)
    return service.compare_strategies()


@router.get("/schedules/{schedule_id}/savings", response_model=SavingsEstimateResponse)
def estimate_savings(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Calculate estimated savings for a schedule"""
    service = HibernationService(db)
    schedule = service.get_schedule(schedule_id)
    return service.calculate_weekly_savings(schedule)


@router.get("/savings/history")
def get_savings_history(
    months: int = Query(6, ge=1, le=24, description="Number of months of history"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get historical savings trend for last N months.
    Aggregates hibernation execution logs from audit_logs table.
    """
    service = HibernationService(db)
    return service.get_savings_history(months, current_user.organization_id)


@router.get("/status/active")
def get_active_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get status of currently active hibernation operation (if any).
    Returns progress, elapsed time, and estimated completion.
    """
    service = HibernationService(db)
    return service.get_active_hibernation_status(current_user.organization_id)


# ── Emergency Controls ──────────────────────────────────────

def _get_org_clusters(db: Session, user: User, cluster_id: str = None):
    """Get clusters for the user's organization, optionally filtering by ID."""
    from backend.models.cluster import Cluster
    from backend.models.account import Account
    
    query = db.query(Cluster).join(Account, Cluster.account_id == Account.id).filter(
        Account.organization_id == user.organization_id
    )
    if cluster_id and cluster_id != "all":
        query = query.filter(Cluster.id == cluster_id)
    return query.all()


@router.post("/emergency/sleep")
def emergency_sleep(
    cluster_id: Optional[str] = Query(None, description="Specific cluster ID, or omit for all"),
    strategy: str = Query("NAMESPACE_SLEEP", description="Strategy to use"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Immediately hibernate selected or all clusters."""
    clusters = _get_org_clusters(db, current_user, cluster_id)
    if not clusters:
        raise HTTPException(status_code=404, detail="No clusters found")
    
    results = []
    success_count = 0
    error_count = 0
    for cluster in clusters:
        try:
            from backend.workers.tasks.hibernation_worker import _get_strategy_class
            strategy_cls = _get_strategy_class(strategy)
            cluster_config = {"cluster_name": cluster.name, "region": cluster.region, "kubeconfig": {}}
            strat = strategy_cls(cluster_config)
            result = strat.sleep({})
            
            cluster.is_hibernating = True
            cluster.hibernation_state = {
                "action": "emergency_sleep",
                "strategy": strategy,
                "started_at": datetime.utcnow().isoformat(),
                "triggered_by": current_user.email
            }
            results.append({"cluster_id": cluster.id, "cluster_name": cluster.name, "status": "sleeping"})
            success_count += 1
        except Exception as e:
            results.append({"cluster_id": cluster.id, "cluster_name": cluster.name, "status": "error", "error": str(e)})
            error_count += 1
    
    db.commit()
    return {"action": "emergency_sleep", "results": results, "success_count": success_count, "error_count": error_count}


@router.post("/emergency/wake")
def emergency_wake(
    cluster_id: Optional[str] = Query(None, description="Specific cluster ID, or omit for all"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Immediately wake selected or all clusters."""
    clusters = _get_org_clusters(db, current_user, cluster_id)
    if not clusters:
        raise HTTPException(status_code=404, detail="No clusters found")
    
    results = []
    success_count = 0
    error_count = 0
    for cluster in clusters:
        try:
            state = cluster.hibernation_state or {}
            strategy_name = state.get("strategy", "NAMESPACE_SLEEP")
            
            from backend.workers.tasks.hibernation_worker import _get_strategy_class
            strategy_cls = _get_strategy_class(strategy_name)
            cluster_config = {"cluster_name": cluster.name, "region": cluster.region, "kubeconfig": {}}
            strat = strategy_cls(cluster_config)
            result = strat.wake(state)
            
            cluster.is_hibernating = False
            cluster.hibernation_state = {}
            results.append({"cluster_id": cluster.id, "cluster_name": cluster.name, "status": "awake"})
            success_count += 1
        except Exception as e:
            results.append({"cluster_id": cluster.id, "cluster_name": cluster.name, "status": "error", "error": str(e)})
            error_count += 1
    
    db.commit()
    return {"action": "emergency_wake", "results": results, "success_count": success_count, "error_count": error_count}


@router.post("/emergency/temp-hibernate")
def emergency_temp_hibernate(
    cluster_id: Optional[str] = Query(None, description="Specific cluster ID, or omit for all"),
    hours: int = Query(4, ge=1, le=24, description="Duration in hours"),
    strategy: str = Query("NAMESPACE_SLEEP", description="Strategy to use"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Temporarily hibernate selected or all clusters for a specified duration."""
    clusters = _get_org_clusters(db, current_user, cluster_id)
    if not clusters:
        raise HTTPException(status_code=404, detail="No clusters found")
    
    wake_at = datetime.utcnow() + timedelta(hours=hours)
    
    results = []
    success_count = 0
    error_count = 0
    for cluster in clusters:
        try:
            from backend.workers.tasks.hibernation_worker import _get_strategy_class
            strategy_cls = _get_strategy_class(strategy)
            cluster_config = {"cluster_name": cluster.name, "region": cluster.region, "kubeconfig": {}}
            strat = strategy_cls(cluster_config)
            result = strat.sleep({})
            
            cluster.is_hibernating = True
            cluster.hibernation_state = {
                "action": "temp_hibernate",
                "strategy": strategy,
                "started_at": datetime.utcnow().isoformat(),
                "wake_at": wake_at.isoformat(),
                "duration_hours": hours,
                "triggered_by": current_user.email
            }
            results.append({"cluster_id": cluster.id, "cluster_name": cluster.name, "status": "sleeping", "wake_at": wake_at.isoformat()})
            success_count += 1
        except Exception as e:
            results.append({"cluster_id": cluster.id, "cluster_name": cluster.name, "status": "error", "error": str(e)})
            error_count += 1
    
    db.commit()
    return {"action": "temp_hibernate", "results": results, "success_count": success_count, "error_count": error_count, "wake_at": wake_at.isoformat()}


