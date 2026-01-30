
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
    HibernationScheduleFilter
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
