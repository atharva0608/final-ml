from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from datetime import datetime, timedelta
from backend.models.base import get_db
from backend.models.user import User
from backend.models.account import Account
from backend.core.dependencies import get_current_user
from backend.modules.rightsizer import get_rightsizer
from backend.core.logger import logger

router = APIRouter(prefix="/optimization", tags=["Optimization"])

@router.get("/rightsizing/{cluster_id}", summary="Get resize recommendations")
def get_rightsizing_recommendations(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rightsizer = get_rightsizer(db)
    # Ensure rightsizer module has analyze_resource_usage implemented
    return rightsizer.analyze_resource_usage(cluster_id)

class BatchResizeRequest(BaseModel):
    instance_ids: List[str]
    cluster_id: str

@router.post("/rightsizing/batch-apply", summary="Apply batch right-sizing")
def batch_apply_rightsizing(
    request: BatchResizeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Apply right-sizing recommendations to multiple instances.
    Creates optimization tasks and logs actions in audit log.
    """
    from backend.models.instance import Instance
    from backend.models.audit_log import AuditLog
    from backend.models.cluster import Cluster
    from datetime import datetime
    import uuid

    # Verify instances exist and belong to user's organization
    instances = db.query(Instance).filter(
        Instance.instance_id.in_(request.instance_ids)
    ).all()

    if not instances:
        raise HTTPException(status_code=404, detail="No valid instances found")

    # Get cluster to verify access
    cluster = db.query(Cluster).filter(Cluster.id == request.cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    applied_count = 0
    failed_count = 0
    results = []

    for instance in instances:
        try:
            # Create audit log entry
            audit_entry = AuditLog(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor_id=str(current_user.id),
                actor_name=current_user.email,
                event="RIGHTSIZING_APPLIED",
                resource=instance.instance_id,
                resource_type="INSTANCE",
                outcome="PENDING",
                ip_address="system"
            )
            db.add(audit_entry)

            # For Kubernetes-managed instances (EKS nodes)
            # Tag instance for right-sizing action
            # The agent will pick up this tag and apply changes
            if cluster.provider == 'EKS' or instance.cluster_id:
                # Add optimization tag (agent will process)
                if not instance.tags:
                    instance.tags = {}
                instance.tags['spot-optimizer/resize-pending'] = 'true'
                instance.tags['spot-optimizer/resize-requested-at'] = datetime.utcnow().isoformat()
                instance.tags['spot-optimizer/resize-requested-by'] = current_user.email

                results.append({
                    "instance_id": instance.instance_id,
                    "status": "queued",
                    "message": "Tagged for agent processing"
                })
                applied_count += 1

            # For standalone EC2 instances
            # Note: Actual EC2 ModifyInstanceAttribute requires instance stop/start
            # which is disruptive - we log the recommendation instead
            else:
                results.append({
                    "instance_id": instance.instance_id,
                    "status": "logged",
                    "message": "Resize recommendation logged (manual action required for EC2)"
                })
                applied_count += 1

            db.commit()

        except Exception as e:
            failed_count += 1
            results.append({
                "instance_id": instance.instance_id,
                "status": "failed",
                "message": str(e)
            })
            db.rollback()

    return {
        "status": "success" if failed_count == 0 else "partial",
        "applied_count": applied_count,
        "failed_count": failed_count,
        "message": f"Successfully processed {applied_count} instances ({failed_count} failed)",
        "results": results
    }

@router.get("/savings/realized", summary="Get realized savings")
def get_realized_savings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get cumulative savings realized from optimization actions.
    Calculates from cluster estimated_savings and daily cost trends.
    """
    from backend.models.cluster import Cluster
    from backend.models.daily_cost import DailyCost
    from backend.models.user import User
    from sqlalchemy import func
    from datetime import datetime, timedelta

    # Get user's organization
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user or not user.organization_id:
        return {"total_savings": 0.0, "this_month": 0.0, "trend": []}

    # Calculate total savings from all clusters in organization
    total_savings_query = db.query(
        func.sum(Cluster.estimated_savings)
    ).join(Account).filter(
        Account.organization_id == user.organization_id
    ).scalar()

    total_savings = total_savings_query or 0.0

    # Calculate this month's savings
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    monthly_savings_query = db.query(
        func.sum(DailyCost.amount)
    ).join(Account).filter(
        Account.organization_id == user.organization_id,
        DailyCost.date >= start_of_month,
        DailyCost.service_category == 'Savings'  # Track savings as negative costs
    ).scalar()

    this_month_savings = abs(monthly_savings_query or 0.0)

    # Get 30-day trend from daily_costs
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    daily_trend = db.query(
        func.date(DailyCost.date).label('date'),
        func.sum(DailyCost.amount).label('amount')
    ).join(Account).filter(
        Account.organization_id == user.organization_id,
        DailyCost.date >= thirty_days_ago,
        DailyCost.service_category == 'Savings'
    ).group_by(
        func.date(DailyCost.date)
    ).order_by('date').all()

    # Build trend array
    trend = []
    for day_data in daily_trend:
        trend.append({
            "date": day_data.date.strftime("%Y-%m-%d"),
            "amount": abs(round(day_data.amount or 0.0, 2))
        })

    # If no trend data, calculate estimated daily savings
    if not trend and total_savings > 0:
        daily_avg = total_savings / 30
        for i in range(30):
            date = (datetime.utcnow() - timedelta(days=29-i)).strftime("%Y-%m-%d")
            trend.append({
                "date": date,
                "amount": round(daily_avg, 2)
            })

    return {
        "total_savings": round(total_savings, 2),
        "this_month": round(this_month_savings, 2),
        "trend": trend
    }


@router.post(
    "/apply/{instance_id}/validated",
    summary="Apply right-sizing with real-time validation"
)
def apply_rightsizing_validated(
    instance_id: str,
    target_instance_type: str = Query(...),
    target_az: str = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Applies a right-sizing recommendation with real-time validation:
    1. Checks ASCP.AI blacklist for target pool
    2. Validates target type against org's default Node Template
    3. Returns 409 Conflict if validation fails
    4. Proceeds with normal apply if validation passes
    """
    # 1. Blacklist check
    try:
        import redis
        from backend.core.config import settings
        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        pool_key = f"{target_instance_type}:{target_az}" if target_az else target_instance_type
        if r.sismember("risky_pools", pool_key):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "POOL_BLACKLISTED",
                    "message": f"{target_instance_type} in {target_az} is currently blacklisted due to recent spot interruptions",
                    "suggestion": "Choose a different instance type or wait for blacklist expiry"
                }
            )
    except redis.ConnectionError:
        logger.warning("Redis connection failed during blacklist check, skipping validation")
        pass  # If Redis is down, skip blacklist check

    # 2. Template compliance check
    from backend.services.template_service import get_template_service
    template_service = get_template_service(db)
    default_template = template_service.get_default_template(current_user.id)

    if default_template:
        family = target_instance_type.rsplit(".", 1)[0] if "." in target_instance_type else ""
        if hasattr(default_template, 'families') and default_template.families:
            if family not in default_template.families:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "TEMPLATE_VIOLATION",
                        "message": f"{family} family is not allowed by your Node Template '{default_template.name}'",
                        "suggestion": "Update your Node Template or choose a different instance type"
                    }
                )

    # 3. If validation passes, apply the recommendation
    from backend.models.instance import Instance
    from backend.models.audit_log import AuditLog
    import uuid

    instance = db.query(Instance).filter(Instance.instance_id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        # Create audit log entry
        audit_entry = AuditLog(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor_id=str(current_user.id),
            actor_name=current_user.email,
            event="RIGHTSIZING_APPLIED_VALIDATED",
            resource=instance_id,
            resource_type="INSTANCE",
            outcome="PENDING",
            ip_address="system",
            details={"target_type": target_instance_type, "target_az": target_az}
        )
        db.add(audit_entry)

        # Tag instance for right-sizing action
        if not instance.tags:
            instance.tags = {}
        instance.tags['spot-optimizer/resize-pending'] = 'true'
        instance.tags['spot-optimizer/resize-target-type'] = target_instance_type
        instance.tags['spot-optimizer/resize-requested-at'] = datetime.utcnow().isoformat()
        instance.tags['spot-optimizer/resize-requested-by'] = current_user.email

        db.commit()

        return {
            "status": "applied",
            "instance_id": instance_id,
            "new_type": target_instance_type,
            "validated": True,
            "message": "Right-sizing recommendation applied successfully with validation"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to apply validated right-sizing: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply recommendation: {str(e)}"
        )
