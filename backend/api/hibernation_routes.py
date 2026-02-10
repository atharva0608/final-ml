
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from backend.models.user import User
from backend.models.base import get_db
from backend.services.hibernation_service import HibernationService
from backend.core.dependencies import get_current_user

def get_hibernation_service(db: Session = Depends(get_db)) -> HibernationService:
    return HibernationService(db)
from backend.schemas.hibernation_schemas import (
    HibernationScheduleResponse,
    HibernationScheduleList,
    HibernationScheduleCreate,
    HibernationScheduleUpdate,
    HibernationScheduleFilter,
    ManualOverrideRequest,
    StrategyInfo,
    StrategyComparisonResponse,
)
from backend.core.exceptions import ResourceNotFoundError, ResourceAlreadyExistsError, ValidationError

router = APIRouter(prefix="/hibernation", tags=["hibernation"])

@router.get("/schedules", response_model=HibernationScheduleList)
def list_schedules(
    page: int = 1,
    page_size: int = 20,
    cluster_id: str = None,
    is_active: bool = None,
    current_user: User = Depends(get_current_user),
    service: HibernationService = Depends(get_hibernation_service)
):
    """
    List hibernation schedules
    """
    filters = HibernationScheduleFilter(
        page=page,
        page_size=page_size,
        cluster_id=cluster_id,
        is_active=is_active
    )
    return service.list_schedules(current_user.id, filters)

@router.post("/schedules", response_model=HibernationScheduleResponse)
def create_schedule(
    schedule_data: HibernationScheduleCreate,
    current_user: User = Depends(get_current_user),
    service: HibernationService = Depends(get_hibernation_service)
):
    """
    Create a new hibernation schedule for a cluster
    """
    try:
        return service.create_schedule(current_user.id, schedule_data)
    except (ResourceAlreadyExistsError, ResourceNotFoundError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/schedules/{schedule_id}", response_model=HibernationScheduleResponse)
def get_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    service: HibernationService = Depends(get_hibernation_service)
):
    """
    Get schedule details
    """
    try:
        return service.get_schedule(schedule_id, current_user.id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.put("/schedules/{schedule_id}", response_model=HibernationScheduleResponse)
def update_schedule(
    schedule_id: str,
    update_data: HibernationScheduleUpdate,
    current_user: User = Depends(get_current_user),
    service: HibernationService = Depends(get_hibernation_service)
):
    """
    Update schedule details
    """
    try:
        return service.update_schedule(schedule_id, current_user.id, update_data)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    service: HibernationService = Depends(get_hibernation_service)
):
    """
    Delete a hibernation schedule
    """
    try:
        service.delete_schedule(schedule_id, current_user.id)
        return {"status": "success", "message": "Schedule deleted"}
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/schedules/{schedule_id}/toggle", response_model=HibernationScheduleResponse)
def toggle_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    service: HibernationService = Depends(get_hibernation_service)
):
    """
    Toggle schedule active status (Enable/Disable)
    """
    try:
        return service.toggle_schedule(schedule_id, current_user.id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/schedules/{schedule_id}/override")
def override_schedule(
    schedule_id: str,
    override_data: ManualOverrideRequest,
    current_user: User = Depends(get_current_user),
    service: HibernationService = Depends(get_hibernation_service),
    db: Session = Depends(get_db)
):
    """
    Manual wake/sleep override — dispatches Celery task
    """
    from backend.models.hibernation_schedule import HibernationSchedule as HibModel

    schedule = db.query(HibModel).filter(HibModel.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    from backend.workers.tasks.hibernation_worker import manual_sleep_cluster, manual_wake_cluster

    strategy = getattr(schedule, 'strategy', None)

    if override_data.action == "SLEEP":
        manual_sleep_cluster.delay(schedule.cluster_id, strategy)
        return {"status": "queued", "action": "SLEEP", "cluster_id": schedule.cluster_id}
    else:
        manual_wake_cluster.delay(schedule.cluster_id, strategy)
        return {"status": "queued", "action": "WAKE", "cluster_id": schedule.cluster_id}


@router.get("/strategies", response_model=StrategyComparisonResponse)
def get_strategies():
    """
    Get available hibernation strategies with comparison data
    """
    strategies = [
        StrategyInfo(
            name="NAMESPACE_SLEEP",
            display_name="Namespace Sleep",
            description="Scales workloads to 0 replicas. Cluster Autoscaler drains idle nodes. Fast recovery.",
            wake_time="~2 min",
            savings_pct=80,
            safety="HIGH",
            best_for="Stateless dev/test workloads"
        ),
        StrategyInfo(
            name="NUCLEAR",
            display_name="Nuclear",
            description="Scales all ASGs to 0. Maximum cost savings but slower recovery.",
            wake_time="~8 min",
            savings_pct=99,
            safety="MEDIUM",
            best_for="Maximum cost reduction, non-critical environments"
        ),
        StrategyInfo(
            name="SNAPSHOT_RESTORE",
            display_name="Snapshot & Restore",
            description="Snapshots EBS volumes before Nuclear shutdown. Preserves data with AZ affinity.",
            wake_time="~12 min",
            savings_pct=90,
            safety="HIGH",
            best_for="Stateful workloads, databases"
        ),
    ]
    return StrategyComparisonResponse(strategies=strategies)
