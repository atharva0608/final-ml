"""
Admin API Routes

FastAPI endpoints for super admin operations and user management
"""
from fastapi import APIRouter, Depends, status, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user, require_super_admin
from backend.services.admin_service import get_admin_service
from backend.schemas.admin_schemas import (
    ClientList,
    ClientFilter,
    UserManagement,
    PlatformStats,
    PasswordReset,
    OrganizationList,
    OrganizationFilter,
    BillingResponse,
    DashboardResponse,
)
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/organizations",
    response_model=OrganizationList,
    summary="List all organizations",
    description="Get paginated list of organizations (Super admin only)"
)
def list_organizations(
    search: Optional[str] = Query(None, description="Search by name or slug"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
) -> OrganizationList:
    filters = OrganizationFilter(search=search, page=page, page_size=page_size)
    service = get_admin_service(db)
    return service.list_organizations(current_user, filters)


@router.post("/organizations/{org_id}/toggle", response_model=OrganizationSummary)
def toggle_organization_status(
    org_id: str,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
) -> OrganizationSummary:
    service = get_admin_service(db)
    return service.toggle_organization_status(current_user, org_id)


@router.get(
    "/clients",
    response_model=ClientList,
    summary="List all clients",
    description="Get paginated list of client users (Super admin only)"
)
def list_clients(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    created_after: Optional[datetime] = Query(None),
    created_before: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
) -> ClientList:
    filters = ClientFilter(
        search=search, is_active=is_active,
        created_after=created_after, created_before=created_before,
        page=page, page_size=page_size
    )
    service = get_admin_service(db)
    return service.list_clients(current_user, filters)


@router.get("/clients/{client_id}", response_model=UserManagement)
def get_client_details(
    client_id: str,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
) -> UserManagement:
    service = get_admin_service(db)
    return service.get_client_details(current_user, client_id)


@router.post("/clients/{client_id}/toggle", response_model=UserManagement)
def toggle_client_status(
    client_id: str,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
) -> UserManagement:
    service = get_admin_service(db)
    return service.toggle_client_status(current_user, client_id)


@router.post("/clients/{client_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_client_password(
    client_id: str,
    password_data: PasswordReset,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
) -> None:
    service = get_admin_service(db)
    service.reset_client_password(current_user, client_id, password_data.new_password)


@router.get("/stats", response_model=PlatformStats)
def get_platform_stats(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
) -> PlatformStats:
    service = get_admin_service(db)
    return service.get_platform_stats(current_user)


@router.get("/billing", response_model=BillingResponse)
def get_billing_info(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
) -> BillingResponse:
    service = get_admin_service(db)
    return service.get_billing_info(current_user)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard_stats(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
) -> DashboardResponse:
    service = get_admin_service(db)
    return service.get_dashboard_stats(current_user)


# ============================================
# System Config Endpoints (Safe Mode, etc.)
# ============================================

@router.get("/config/{key}", summary="Get system config value")
def get_config_value(
    key: str,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    from backend.models.system_config import SystemConfig
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if config:
        return {"key": config.key, "value": config.value}
    defaults = {
        "SAFE_MODE": True,
        "RISK_TTL_MINUTES": 30,
        "OPTIMIZATION_COOLDOWN_MINUTES": 60,
        "AGENT_VERSION": "v1.4.2"
    }
    return {"key": key, "value": defaults.get(key, None)}


@router.patch("/config", summary="Update system config")
def update_config_value(
    key: str = Body(...),
    value = Body(...),
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    from backend.models.system_config import SystemConfig
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if config:
        config.value = str(value)
    else:
        config = SystemConfig(key=key, value=str(value))
        db.add(config)
    db.commit()
    return {"key": key, "value": value, "message": f"Config '{key}' updated successfully"}


# ============================================
# Platform Identity Management Endpoints
# ============================================

@router.get("/platform/connection", summary="Get platform AWS connection status")
def get_platform_connection(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    service = get_admin_service(db)
    return service.get_platform_connection(current_user)


@router.post("/platform/connect", summary="Connect platform AWS identity")
def connect_platform(
    access_key_id: str = Body(..., embed=True),
    secret_access_key: str = Body(..., embed=True),
    region: str = Body("us-east-1", embed=True),
    role_arn: str = Body(None, embed=True),
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    service = get_admin_service(db)
    return service.update_platform_credentials(
        requesting_user=current_user,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region=region,
        role_arn=role_arn
    )


@router.delete("/platform/disconnect", summary="Disconnect platform AWS identity")
def disconnect_platform(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    service = get_admin_service(db)
    return service.disconnect_platform(current_user)
