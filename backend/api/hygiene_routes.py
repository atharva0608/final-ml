from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.core.dependencies import get_db, get_current_user, verify_tenant_action
from backend.services.hygiene_service import HygieneService
from backend.schemas.hygiene_schemas import HygieneSummary, HygieneAction
from backend.models.user import User
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/hygiene",
    tags=["hygiene"]
)

@router.get("/scan/{account_id}", response_model=HygieneSummary)
def scan_resources(
    account_id: str,
    regions: Optional[List[str]] = Query(None),
    force_refresh: bool = Query(False, description="Bypass cache and fetch fresh data from AWS"),
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_tenant_action)
):
    """
    Scan for orphaned resources.
    Pass regions=['ALL'] to scan all available regions.
    Pass force_refresh=true to bypass cache (use after cleanup actions).
    """
    service = HygieneService(db)
    try:
        return service.scan_resources(account_id, regions, organization=current_user.organization, force_refresh=force_refresh)
    except Exception as e:
        logger.exception(f"Scan failed for account {account_id}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/check-dependencies")
def check_dependencies(
    account_id: str = Query(...),
    resource_type: str = Query(...),
    resource_id: str = Query(...),
    region: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_tenant_action)
):
    """
    Feature 1: Deep Dependency Mapping
    Pre-flight check before deletion to verify no blocking resources.
    """
    service = HygieneService(db)
    try:
        result = service.check_dependencies(account_id, resource_type, resource_id, region)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/action")
def execute_hygiene_action(
    action: HygieneAction,
    account_id: str = Query(..., description="The account ID to execute action on"),
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_tenant_action)
):
    """
    Execute hygiene actions (Terminate, Delete, Release).
    Supports RBAC - Members require approval.
    """
    # fix_A1 (HYGIENE-REGION-01): Reject pseudo-regions — they cause silent mis-targeting
    _region = (action.region or "").strip().lower()
    if not _region or _region in ("global", "all", "none"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"region must be a valid AWS region (e.g. 'us-east-1'). "
                f"Received: {action.region!r}. "
                "Select a specific region before executing an action."
            ),
        )

    service = HygieneService(db)
    try:
        result = service.execute_action(account_id, action, user=current_user)
        # Return 202 Accepted if pending approval
        if result and result.get("status") == "pending_approval":
            return JSONResponse(status_code=202, content=result)
        return result
    except Exception as e:
        logger.exception(f"Hygiene action failed: {action.action_type}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/discover")
def discover_resources(
    account_id: str = Query(...),
    resource_type: str = Query(...),
    region: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Resource Discovery for JIT Approvals.
    Allows searching for Resource IDs by type (INSTANCE, VOLUME, RDS_DB).
    """
    service = HygieneService(db)
    try:
        return service.get_discoverable_resources(account_id, resource_type, region)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/total-cost")
def get_total_discovered_cost(
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get total cost of all discovered resources.

    Uses Cost Explorer data when available (includes all AWS services).
    Falls back to EC2 instance pricing if Cost Explorer unavailable.
    Cached for 24 hours for production-grade performance.

    Returns:
        {
            "total_cost": 59.39,
            "source": "cost_explorer",  # or "ec2_fallback"
            "currency": "USD",
            "period": "monthly_projection",
            "breakdown": {
                "ec2": 22.62,
                "storage": 0.73,
                "networking": 8.10,
                "database": 0.0,
                "others": 27.94
            }
        }
    """
    from backend.models.account import Account
    from backend.models.billing import DailyCost
    from backend.models.instance import Instance
    from sqlalchemy import func
    from datetime import datetime, timedelta
    from decimal import Decimal
    from backend.core.redis_client import get_redis_client
    import json

    # Check cache first (24-hour TTL)
    cache_client = get_redis_client()
    cache_key = f"hygiene:total_cost:{current_user.organization_id}:{account_id or 'all'}"
    cached_data = cache_client.get(cache_key)
    if cached_data:
        try:
            return json.loads(cached_data)
        except:
            pass

    # Get accounts for this user's organization
    org_accounts = db.query(Account.id, Account.aws_account_id).filter(
        Account.organization_id == current_user.organization_id
    )

    if account_id:
        org_accounts = org_accounts.filter(Account.id == account_id)

    org_accounts = org_accounts.all()
    org_account_ids = [acc.id for acc in org_accounts]

    if not org_account_ids:
        result = {
            "total_cost": 0.0,
            "source": "no_accounts",
            "currency": "USD",
            "period": "monthly_projection",
            "breakdown": {}
        }
        cache_client.setex(cache_key, 86400, json.dumps(result))  # 24 hours
        return result

    # Try Cost Explorer first (current month)
    start_date = datetime.now().replace(day=1).date()
    end_date = datetime.now().date()

    cost_query = db.query(
        DailyCost.service_name,
        func.sum(DailyCost.cost_amount).label('cost')
    ).filter(
        DailyCost.account_id.in_(org_account_ids),
        DailyCost.date >= start_date,
        DailyCost.date <= end_date
    ).group_by(DailyCost.service_name).all()

    if cost_query:
        # Cost Explorer data available - calculate monthly projection
        days_so_far = (end_date - start_date).days + 1
        mtd_cost = sum(float(cost) for _, cost in cost_query)
        projected_monthly = (mtd_cost / days_so_far) * 30

        # Categorize services
        breakdown = {"ec2": 0.0, "storage": 0.0, "networking": 0.0, "database": 0.0, "others": 0.0}

        for service, cost in cost_query:
            daily_cost = float(cost) / days_so_far * 30  # Project to full month

            if any(s in service for s in ["Elastic Compute Cloud", "EC2", "Elastic Container Service"]):
                breakdown["ec2"] += daily_cost
            elif any(s in service for s in ["Simple Storage Service", "Elastic Block Store", "Elastic File System", "Backup"]):
                breakdown["storage"] += daily_cost
            elif any(s in service for s in ["Virtual Private Cloud", "Data Transfer", "Load Balancing", "CloudFront", "Route 53"]):
                breakdown["networking"] += daily_cost
            elif any(s in service for s in ["Relational Database Service", "DynamoDB", "ElastiCache", "Redshift"]):
                breakdown["database"] += daily_cost
            else:
                breakdown["others"] += daily_cost

        result = {
            "total_cost": round(projected_monthly, 2),
            "source": "cost_explorer",
            "currency": "USD",
            "period": "monthly_projection",
            "breakdown": {k: round(v, 2) for k, v in breakdown.items()}
        }
        cache_client.setex(cache_key, 86400, json.dumps(result))  # Cache for 24 hours
        return result

    # Fallback: EC2 instance pricing
    instances = db.query(Instance).filter(
        Instance.account_id.in_(org_account_ids),
        Instance.state.in_(['running', 'pending'])
    ).all()

    total_cost = sum(float(inst.price or 0) * 720 for inst in instances)  # Monthly (720 hours)

    result = {
        "total_cost": round(total_cost, 2),
        "source": "ec2_fallback",
        "currency": "USD",
        "period": "monthly_projection",
        "breakdown": {
            "ec2": round(total_cost, 2),
            "storage": 0.0,
            "networking": 0.0,
            "database": 0.0,
            "others": 0.0
        }
    }
    cache_client.setex(cache_key, 86400, json.dumps(result))  # Cache for 24 hours
    return result


@router.get("/cost-services")
def get_cost_consuming_services(
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    DEPRECATED: This endpoint is no longer used in the frontend.

    The cost services breakdown has been moved to the resources scan result.
    This endpoint remains for backward compatibility but returns empty data.

    Returns:
        {"categories": [], "deprecated": true}
    """
    return {
        "categories": [],
        "deprecated": True,
        "message": "This endpoint is deprecated. Use /hygiene/scan endpoint for resource breakdown."
    }

@router.get("/scan-history")
def get_scan_history(
    account_id: str = Query(..., description="The account ID to fetch scan history for"),
    days: int = Query(7, ge=1, le=30, description="Number of days of history"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get historical scan trend data for sparkline charts.
    """
    service = HygieneService(db)
    try:
        return service.get_scan_history(account_id, days, organization_id=current_user.organization_id)
    except Exception as e:
        logger.exception("Failed to get scan history for account %s", account_id)
        raise HTTPException(status_code=500, detail=str(e))
