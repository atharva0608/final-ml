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
from backend.core.dependencies import get_current_user, require_super_admin  # noqa: F401
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


# ── T19: Circuit Breaker Admin Endpoints ─────────────────────────────────────

@router.get("/circuit-breakers", summary="Get all cluster circuit breaker states")
def get_circuit_breakers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return circuit breaker state for all clusters."""
    try:
        from backend.core.redis_client import get_redis_client
        from backend.services.circuit_breaker import CircuitBreaker

        from backend.models.cluster import Cluster as _Cluster
        clusters = db.query(_Cluster).all()
        redis = get_redis_client()
        cb = CircuitBreaker(redis)

        result = []
        for cluster in clusters:
            status = cb.get_full_status(cluster.id)
            result.append({
                "cluster_id": cluster.id,
                "cluster_name": cluster.name,
                **status,
            })
        return {"circuit_breakers": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/circuit-breakers/{cluster_id}/reset", summary="Reset circuit breaker to NORMAL")
def reset_circuit_breaker(
    cluster_id: str,
    current_user: User = Depends(require_super_admin),
):
    """Force reset a cluster's circuit breaker to NORMAL state."""
    try:
        from backend.core.redis_client import get_redis_client
        from backend.services.circuit_breaker import CircuitBreaker

        redis = get_redis_client()
        cb = CircuitBreaker(redis)
        result = cb.reset(cluster_id, reason=f"manual_reset_by_{current_user.email}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AWS Pool Intelligence ─────────────────────────────────────────────────────

# All supported AWS regions shown in the UI
_ALL_AWS_REGIONS = [
    "ap-south-1",       # Mumbai
    "ap-southeast-1",   # Singapore
    "ap-southeast-2",   # Sydney
    "ap-northeast-1",   # Tokyo
    "ap-northeast-2",   # Seoul
    "us-east-1",        # N. Virginia
    "us-east-2",        # Ohio
    "us-west-1",        # N. California
    "us-west-2",        # Oregon
    "eu-west-1",        # Ireland
    "eu-west-2",        # London
    "eu-central-1",     # Frankfurt
    "eu-north-1",       # Stockholm
    "ca-central-1",     # Canada
    "sa-east-1",        # São Paulo
]

_REGION_DISPLAY_NAMES = {
    "ap-south-1":    "Mumbai (ap-south-1)",
    "ap-southeast-1": "Singapore (ap-southeast-1)",
    "ap-southeast-2": "Sydney (ap-southeast-2)",
    "ap-northeast-1": "Tokyo (ap-northeast-1)",
    "ap-northeast-2": "Seoul (ap-northeast-2)",
    "us-east-1":     "N. Virginia (us-east-1)",
    "us-east-2":     "Ohio (us-east-2)",
    "us-west-1":     "N. California (us-west-1)",
    "us-west-2":     "Oregon (us-west-2)",
    "eu-west-1":     "Ireland (eu-west-1)",
    "eu-west-2":     "London (eu-west-2)",
    "eu-central-1":  "Frankfurt (eu-central-1)",
    "eu-north-1":    "Stockholm (eu-north-1)",
    "ca-central-1":  "Canada (ca-central-1)",
    "sa-east-1":     "São Paulo (sa-east-1)",
}

_AZ_SUFFIXES = ["a", "b", "c"]


@router.get("/aws-pool-data", summary="AWS pool intelligence per region")
def get_aws_pool_data(
    regions: str = Query("ap-south-1", description="Comma-separated list of AWS regions to inspect"),
    current_user: User = Depends(require_super_admin),
):
    """
    Returns pool pipeline stats and health data for each requested region.

    Per-region stats block:
      • catalog_types      – distinct instance types in the instance catalog
      • raw_candidates     – catalog_types × 3 AZs = total candidate pool universe
      • after_spot_advisor – pools annotated (all pass, SA rank attached, no hard gate)
      • after_blacklist    – pools surviving the hard-failure-count ≥ 3 pre-filter
      • in_global_cache    – pools currently in the Redis global_pool_rankings cache
      • cache_age_minutes  – how old the cache is (None = not cached)
      • client_filters_applied – example: arch + vCPU + memory removes ~X pools
      • blacklisted_pools  – pools in risky_pools:{region} set with active metadata
      • risky_pools        – short-lived RISK:* flagged pools (GlobalRiskTracker)
    """
    import json as _json
    from backend.core.redis_client import get_redis_client
    from backend.services.blacklist_service import BlacklistService

    redis = get_redis_client()
    blacklist_svc = BlacklistService(redis)

    requested_regions = [r.strip() for r in regions.split(",") if r.strip() in _ALL_AWS_REGIONS]
    if not requested_regions:
        raise HTTPException(status_code=400, detail="No valid regions requested")

    # Load instance catalog to compute universe size
    try:
        from backend.services.dynamic_instance_helpers import load_instance_catalog_from_db
        from backend.models.base import get_db as _get_db
        _db = next(_get_db())
        catalog = load_instance_catalog_from_db(_db)
    except Exception:
        catalog = {}
    catalog_size = len(catalog)

    results = []
    for region in requested_regions:
        region_azs = [f"{region}{s}" for s in _AZ_SUFFIXES]
        raw_candidates = catalog_size * len(region_azs)

        # ── Pool pipeline counts ────────────────────────────────────────────
        # Step 3: Spot Advisor - all pools annotated, no hard gate
        after_spot_advisor = raw_candidates  # annotation only, nothing filtered

        # Step 4: Blacklist pre-filter — pools with failure_count >= 3 are skipped
        hard_blacklisted_count = 0
        try:
            bl_set_key = f"risky_pools:{region}"
            bl_members = redis.smembers(bl_set_key)
            for member in bl_members:
                member_str = member.decode("utf-8") if isinstance(member, bytes) else member
                failures_raw = redis.get(f"blacklist_failures:{member_str}")
                failures = int(failures_raw) if failures_raw else 0
                if failures >= 3:
                    hard_blacklisted_count += 1
        except Exception:
            pass
        # Each hard-blacklisted pool appears in 1 AZ, so subtract directly
        after_blacklist = max(0, after_spot_advisor - hard_blacklisted_count)

        # ── Global cache stats ──────────────────────────────────────────────
        cache_key = f"global_pool_rankings:{region}"
        in_global_cache = 0
        cache_age_minutes = None
        try:
            cached_raw = redis.get(cache_key)
            if cached_raw:
                pool_list = _json.loads(cached_raw)
                in_global_cache = len(pool_list) if isinstance(pool_list, list) else 0
                # Redis TTL remaining → compute age from GLOBAL_CACHE_TTL (65 min)
                GLOBAL_CACHE_TTL = 65 * 60
                ttl_remaining = redis.ttl(cache_key)
                if ttl_remaining and ttl_remaining > 0:
                    cache_age_minutes = round((GLOBAL_CACHE_TTL - ttl_remaining) / 60, 1)
        except Exception:
            pass

        # ── Client filter example (typical reduction) ───────────────────────
        # Representative: amd64 + 2-64 vCPU + 4-256 GB memory ≈ 60-70% of catalog
        # We estimate by counting catalog entries matching that envelope
        typical_client_filtered = 0
        if catalog:
            for itype, specs in catalog.items():
                if (
                    specs.get("architecture") in ("amd64", "x86_64")
                    and 2 <= specs.get("vcpu", 0) <= 64
                    and 4 <= specs.get("memory_gb", 0) <= 256
                ):
                    typical_client_filtered += len(region_azs)

        # ── Blacklisted pools with health details ───────────────────────────
        blacklisted_pools = []
        try:
            bl_details = blacklist_svc.get_blacklist_status(region)
            for entry in bl_details:
                failures_raw = redis.get(f"blacklist_failures:{entry['instance_type']}:{entry['az']}")
                failures = int(failures_raw) if failures_raw else entry.get("failure_count", 0)
                ttl_h = entry.get("ttl_hours", 0)
                severity = (
                    "critical" if failures >= 5
                    else "high" if failures >= 3
                    else "medium"
                )
                blacklisted_pools.append({
                    "instance_type": entry.get("instance_type", ""),
                    "az": entry.get("az", ""),
                    "reason": entry.get("reason", "unknown"),
                    "failure_count": failures,
                    "ttl_hours": ttl_h,
                    "ttl_remaining_seconds": entry.get("ttl_remaining_seconds", 0),
                    "backoff": ttl_h >= 48,
                    "severity": severity,
                    "flagged_at": entry.get("flagged_at"),
                    "expires_at": entry.get("expires_at"),
                })
        except Exception:
            pass

        # Sort: critical first
        _sev_order = {"critical": 0, "high": 1, "medium": 2}
        blacklisted_pools.sort(key=lambda x: (_sev_order.get(x["severity"], 3), -x["failure_count"]))

        # ── RISK:* shortlived flags (GlobalRiskTracker) ─────────────────────
        risky_pools = []
        try:
            for key in redis.scan_iter(match="RISK:*"):
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                parts = key_str.split(":")
                if len(parts) >= 3:
                    az = parts[1]
                    instance_type = ":".join(parts[2:])
                    # Only include if the AZ belongs to this region
                    if any(az.startswith(region) for _ in [1]):
                        ttl = redis.ttl(key)
                        risky_pools.append({
                            "instance_type": instance_type,
                            "az": az,
                            "ttl_remaining_seconds": max(ttl, 0) if ttl > 0 else 0,
                            "expires_in_minutes": round(max(ttl, 0) / 60, 1),
                        })
        except Exception:
            pass

        results.append({
            "region": region,
            "display_name": _REGION_DISPLAY_NAMES.get(region, region),
            "pipeline": {
                "catalog_types":         catalog_size,
                "azs":                   len(region_azs),
                "raw_candidates":        raw_candidates,
                "after_spot_advisor":    after_spot_advisor,
                "after_blacklist":       after_blacklist,
                "after_blacklist_removed": hard_blacklisted_count,
                "in_global_cache":       in_global_cache,
                "cache_limit":           1500,
                "cache_age_minutes":     cache_age_minutes,
                "typical_after_client_filter": typical_client_filtered,
                "client_filter_removed": max(0, raw_candidates - typical_client_filtered),
            },
            "blacklisted_pools": blacklisted_pools,
            "risky_pools":        risky_pools,
            "blacklisted_count":  len(blacklisted_pools),
            "risky_count":        len(risky_pools),
        })

    return {
        "regions": results,
        "all_regions": _ALL_AWS_REGIONS,
        "region_display_names": _REGION_DISPLAY_NAMES,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
    }
