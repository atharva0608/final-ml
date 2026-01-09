"""
Settings API Routes

Endpoints for user profile and system integrations
"""
from fastapi import APIRouter, Depends, status, Body
from sqlalchemy.orm import Session
from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user, RequireAccess
from backend.services.settings_service import get_settings_service, SettingsService
from backend.schemas.auth_schemas import UserProfile
from backend.schemas.settings_schemas import (
    UserProfileUpdate,
    Integration,
    IntegrationCreate,
    IntegrationList
)

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.get(
    "/profile",
    response_model=UserProfile,
    summary="Get user profile"
)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's profile details"""
    service = get_settings_service(db)
    return service.get_profile(current_user.id)

@router.patch(
    "/profile",
    response_model=UserProfile,
    summary="Update user profile"
)
def update_profile(
    update_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile info"""
    service = get_settings_service(db)
    return service.update_profile(current_user.id, update_data)

@router.get(
    "/integrations",
    response_model=IntegrationList,
    summary="List integrations"
)
def list_integrations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of active integrations"""
    service = get_settings_service(db)
    return service.get_integrations(current_user.id)

@router.post(
    "/integrations",
    response_model=Integration,
    status_code=status.HTTP_201_CREATED,
    summary="Add integration"
)
def add_integration(
    integration_data: IntegrationCreate,
    current_user: User = Depends(RequireAccess("FULL")),
    db: Session = Depends(get_db)
):
    """Add a new external integration"""
    service = get_settings_service(db)
    return service.add_integration(current_user.id, integration_data)

@router.delete(
    "/integrations/{integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete integration"
)
def delete_integration(
    integration_id: str,
    current_user: User = Depends(RequireAccess("FULL")),
    db: Session = Depends(get_db)
):
    """Remove an external integration"""
    service = get_settings_service(db)
    service.delete_integration(current_user.id, integration_id)
