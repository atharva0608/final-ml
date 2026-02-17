"""
Admin API Routes

FastAPI endpoints for super admin operations and user management
"""
from fastapi import APIRouter, Depends, status, Query, Body, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional
from datetime import datetime, timedelta
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
    OrganizationSummary,
    BillingResponse,
    DashboardResponse,
    SystemHealth,
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


@router.get("/health", response_model=SystemHealth, summary="Get platform health status")
def get_platform_health(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
) -> SystemHealth:
    """Get platform-wide system health metrics including API latency, DB connections, Redis, and worker status"""
    service = get_admin_service(db)
    return service.get_platform_health(current_user)


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


@router.get("/agent-fleet", summary="Get platform-wide agent fleet status")
def get_agent_fleet(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    Get all agents across all organizations with their health status.
    Returns platform-wide view of agent deployment and connectivity.
    """
    from backend.models.cluster import Cluster
    from backend.models.organization import Organization
    from backend.models.account import Account

    # Query all clusters with agents installed, joined to organizations
    agents = db.query(
        Cluster.id.label('cluster_id'),
        Cluster.name.label('cluster_name'),
        Cluster.region,
        Cluster.last_heartbeat,
        Cluster.agent_version,
        Organization.name.label('organization_name'),
        Organization.id.label('organization_id')
    ).join(Account, Cluster.account_id == Account.id)\
     .join(Organization, Account.organization_id == Organization.id)\
     .filter(Cluster.agent_installed == True)\
     .order_by(Organization.name, Cluster.name)\
     .all()

    # Convert to list of dicts
    result = []
    for agent in agents:
        result.append({
            "cluster_id": agent.cluster_id,
            "cluster_name": agent.cluster_name,
            "region": agent.region,
            "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
            "agent_version": agent.agent_version,
            "organization_name": agent.organization_name,
            "organization_id": agent.organization_id
        })

    return result


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


@router.post("/impersonate", summary="Impersonate an organization")
def impersonate_organization(
    organization_id: str = Body(..., embed=True),
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    Generate a scoped JWT token to impersonate an organization for debugging/support.
    Returns a temporary token that provides access as that organization's admin.
    """
    from backend.models.organization import Organization
    from backend.core.security import create_access_token
    from backend.models.audit_log import AuditLog
    import uuid

    # Verify organization exists
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    if not org:
        raise HTTPException(404, "Organization not found")

    if not org.is_active:
        raise HTTPException(400, "Cannot impersonate inactive organization")

    # Find an ORG_ADMIN user from this organization to impersonate as
    from backend.models.user import UserRole
    org_admin = db.query(User).filter(
        and_(User.organization_id == organization_id, User.role == UserRole.ORG_ADMIN)
    ).first()

    if not org_admin:
        raise HTTPException(400, "No ORG_ADMIN found for this organization")

    # Create scoped token with impersonation flag
    token_data = {
        "user_id": org_admin.id,
        "organization_id": organization_id,
        "impersonated_by": current_user.id,
        "impersonation": True
    }
    token = create_access_token(token_data, expires_delta=timedelta(hours=4))

    # Log the impersonation action
    audit_entry = AuditLog(
        id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        actor_id=str(current_user.id),
        actor_name=current_user.email,
        event="ADMIN_IMPERSONATION",
        resource=organization_id,
        resource_type="ORGANIZATION",
        outcome="SUCCESS",
        ip_address="system",
        details={"impersonated_org": org.name, "impersonated_user": org_admin.email}
    )
    db.add(audit_entry)
    db.commit()

    return {
        "token": token,
        "organization": {"id": org.id, "name": org.name, "slug": org.slug},
        "user": {"id": org_admin.id, "email": org_admin.email},
        "expires_at": (datetime.utcnow() + timedelta(hours=4)).isoformat()
    }


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
