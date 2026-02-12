from fastapi import APIRouter, Depends, HTTPException, Query, Response
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
    service = HygieneService(db)
    try:
        result = service.execute_action(account_id, action, user=current_user)
        # Return 202 Accepted if pending approval
        if result.get("status") == "pending_approval":
            return Response(status_code=202, content=result, media_type="application/json")
        return result
    except Exception as e:
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
    from backend.core.cache import cache_client
    import json

    # Check cache first (24-hour TTL)
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
    Get list of AWS services consuming cost (for Resource Hygiene sidebar).
    Cached for 24 hours for production-grade performance.

    Returns services grouped by category with counts and costs:
    - COMPUTE: EC2, EKS, Lambda
    - STORAGE: S3, EBS, EFS, Snapshots
    - DATABASE: RDS, DynamoDB
    - NETWORK: VPC, Load Balancers, Data Transfer, Elastic IPs
    - SECURITY: Security Hub, KMS, Secrets Manager
    - MANAGEMENT: Config, Systems Manager, CloudWatch
    - OTHERS: All remaining services

    Returns:
        {
            "categories": [
                {
                    "name": "COMPUTE",
                    "resources": [
                        {"name": "Instances", "count": 1, "cost": 7.40},
                        {"name": "EKS Clusters", "count": 0, "cost": 2.55}
                    ]
                },
                {
                    "name": "NETWORK",
                    "resources": [
                        {"name": "VPC", "count": 1, "cost": 8.10},
                        {"name": "Elastic IPs", "count": 2, "cost": 0.0}
                    ]
                },
                ...
            ]
        }
    """
    from backend.models.account import Account
    from backend.models.billing import DailyCost
    from backend.models.instance import Instance
    from backend.models.cluster import Cluster
    from sqlalchemy import func
    from datetime import datetime, timedelta
    from collections import defaultdict
    from backend.core.cache import cache_client
    import json

    # Check cache first (24-hour TTL)
    cache_key = f"hygiene:cost_services:{current_user.organization_id}:{account_id or 'all'}"
    cached_data = cache_client.get(cache_key)
    if cached_data:
        try:
            return json.loads(cached_data)
        except:
            pass

    # Get accounts
    org_accounts = db.query(Account).filter(
        Account.organization_id == current_user.organization_id
    )

    if account_id:
        org_accounts = org_accounts.filter(Account.id == account_id)

    org_accounts = org_accounts.all()
    org_account_ids = [acc.id for acc in org_accounts]

    if not org_account_ids:
        result = {"categories": []}
        cache_client.setex(cache_key, 86400, json.dumps(result))  # 24 hours
        return result

    # Get Cost Explorer data for current month
    start_date = datetime.now().replace(day=1).date()
    end_date = datetime.now().date()

    cost_data = db.query(
        DailyCost.service_name,
        func.sum(DailyCost.cost_amount).label('cost')
    ).filter(
        DailyCost.account_id.in_(org_account_ids),
        DailyCost.date >= start_date,
        DailyCost.date <= end_date
    ).group_by(DailyCost.service_name).all()

    # Project to full month
    days_so_far = (end_date - start_date).days + 1
    service_costs = {
        service: (float(cost) / days_so_far * 30)
        for service, cost in cost_data
    }

    # Get resource counts
    instance_count = db.query(func.count(Instance.id)).filter(
        Instance.account_id.in_(org_account_ids),
        Instance.state.in_(['running', 'pending'])
    ).scalar() or 0

    cluster_count = db.query(func.count(Cluster.id)).filter(
        Cluster.account_id.in_(org_account_ids)
    ).scalar() or 0

    # Build categories
    categories = []

    # COMPUTE
    ec2_cost = sum(cost for svc, cost in service_costs.items() if "Elastic Compute Cloud" in svc or "EC2" in svc)
    eks_cost = sum(cost for svc, cost in service_costs.items() if "Elastic Container Service for Kubernetes" in svc or "EKS" in svc)
    lambda_cost = sum(cost for svc, cost in service_costs.items() if "Lambda" in svc)

    compute_resources = [
        {"name": "Instances", "count": instance_count, "cost": round(ec2_cost, 2)},
        {"name": "EKS Clusters", "count": cluster_count, "cost": round(eks_cost, 2)}
    ]
    if lambda_cost > 0:
        compute_resources.append({"name": "Lambda Functions", "count": 0, "cost": round(lambda_cost, 2)})

    categories.append({
        "name": "COMPUTE",
        "resources": compute_resources
    })

    # STORAGE
    s3_cost = sum(cost for svc, cost in service_costs.items() if "Simple Storage Service" in svc or "S3" in svc)
    ebs_cost = sum(cost for svc, cost in service_costs.items() if "Elastic Block Store" in svc or "EBS" in svc)
    efs_cost = sum(cost for svc, cost in service_costs.items() if "Elastic File System" in svc or "EFS" in svc)
    backup_cost = sum(cost for svc, cost in service_costs.items() if "Backup" in svc)

    storage_resources = []
    if s3_cost > 0:
        storage_resources.append({"name": "S3 Buckets", "count": 0, "cost": round(s3_cost, 2)})
    if ebs_cost > 0:
        storage_resources.append({"name": "EBS Volumes", "count": 0, "cost": round(ebs_cost, 2)})
    if efs_cost > 0:
        storage_resources.append({"name": "EFS File Systems", "count": 0, "cost": round(efs_cost, 2)})
    if backup_cost > 0:
        storage_resources.append({"name": "AWS Backup", "count": 0, "cost": round(backup_cost, 2)})

    if storage_resources:
        categories.append({"name": "STORAGE", "resources": storage_resources})

    # NETWORK
    vpc_cost = sum(cost for svc, cost in service_costs.items() if "Virtual Private Cloud" in svc or "VPC" in svc)
    lb_cost = sum(cost for svc, cost in service_costs.items() if "Load Balancing" in svc or "Elastic Load Balancing" in svc)
    transfer_cost = sum(cost for svc, cost in service_costs.items() if "Data Transfer" in svc)

    network_resources = []
    if vpc_cost > 0:
        network_resources.append({"name": "VPC", "count": 1, "cost": round(vpc_cost, 2)})
    if lb_cost > 0:
        network_resources.append({"name": "Load Balancers", "count": 0, "cost": round(lb_cost, 2)})
    if transfer_cost > 0:
        network_resources.append({"name": "Data Transfer", "count": 0, "cost": round(transfer_cost, 2)})

    if network_resources:
        categories.append({"name": "NETWORK", "resources": network_resources})

    # SECURITY
    security_hub_cost = sum(cost for svc, cost in service_costs.items() if "Security Hub" in svc)
    kms_cost = sum(cost for svc, cost in service_costs.items() if "Key Management Service" in svc or "KMS" in svc)
    secrets_cost = sum(cost for svc, cost in service_costs.items() if "Secrets Manager" in svc)

    security_resources = []
    if security_hub_cost > 0:
        security_resources.append({"name": "Security Hub", "count": 1, "cost": round(security_hub_cost, 2)})
    if kms_cost > 0:
        security_resources.append({"name": "KMS Keys", "count": 0, "cost": round(kms_cost, 2)})
    if secrets_cost > 0:
        security_resources.append({"name": "Secrets Manager", "count": 0, "cost": round(secrets_cost, 2)})

    if security_resources:
        categories.append({"name": "SECURITY", "resources": security_resources})

    # MANAGEMENT
    config_cost = sum(cost for svc, cost in service_costs.items() if "Config" in svc)
    ssm_cost = sum(cost for svc, cost in service_costs.items() if "Systems Manager" in svc)
    cloudwatch_cost = sum(cost for svc, cost in service_costs.items() if "CloudWatch" in svc)

    management_resources = []
    if config_cost > 0:
        management_resources.append({"name": "AWS Config", "count": 1, "cost": round(config_cost, 2)})
    if ssm_cost > 0:
        management_resources.append({"name": "Systems Manager", "count": 1, "cost": round(ssm_cost, 2)})
    if cloudwatch_cost > 0:
        management_resources.append({"name": "CloudWatch", "count": 0, "cost": round(cloudwatch_cost, 2)})

    if management_resources:
        categories.append({"name": "MANAGEMENT", "resources": management_resources})

    # DATABASE
    rds_cost = sum(cost for svc, cost in service_costs.items() if "Relational Database Service" in svc or "RDS" in svc)
    dynamodb_cost = sum(cost for svc, cost in service_costs.items() if "DynamoDB" in svc)

    database_resources = []
    if rds_cost > 0:
        database_resources.append({"name": "RDS Instances", "count": 0, "cost": round(rds_cost, 2)})
    if dynamodb_cost > 0:
        database_resources.append({"name": "DynamoDB Tables", "count": 0, "cost": round(dynamodb_cost, 2)})

    if database_resources:
        categories.append({"name": "DATABASES", "resources": database_resources})

    # OTHERS (remaining services)
    tracked_services = {
        "Elastic Compute Cloud", "EC2", "Elastic Container Service for Kubernetes", "EKS", "Lambda",
        "Simple Storage Service", "S3", "Elastic Block Store", "EBS", "Elastic File System", "EFS", "Backup",
        "Virtual Private Cloud", "VPC", "Load Balancing", "Data Transfer",
        "Security Hub", "Key Management Service", "KMS", "Secrets Manager",
        "Config", "Systems Manager", "CloudWatch",
        "Relational Database Service", "RDS", "DynamoDB"
    }

    other_services = []
    for svc, cost in service_costs.items():
        if not any(tracked in svc for tracked in tracked_services):
            other_services.append({"name": svc, "count": 0, "cost": round(cost, 2)})

    if other_services:
        categories.append({"name": "OTHERS", "resources": other_services})

    result = {"categories": categories}
    cache_client.setex(cache_key, 86400, json.dumps(result))  # Cache for 24 hours
    return result
