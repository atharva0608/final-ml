"""
Hibernation Schedule API Routes

REST API endpoints for managing hibernation schedules.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
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
