"""
Billing Routes - AWS Cost Explorer + Stripe integration endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from backend.models.base import get_db
from backend.models.user import User
from backend.models.account import Account
from backend.models.billing import DailyCost, CostExplorerSyncStatus
from backend.core.dependencies import get_current_user
from backend.core.config import settings
from backend.workers.tasks.cost_explorer import sync_cost_explorer
from datetime import datetime, timedelta
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.post("/create-portal-session")
async def create_portal_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a Stripe Billing Portal session for the user's organization.
    Returns a URL to redirect the user to Stripe's hosted billing portal.
    """
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        # Get the organization's Stripe customer ID
        org = current_user.organization
        if not org or not getattr(org, 'stripe_customer_id', None):
            raise HTTPException(400, "Organization not linked to Stripe")
        
        # Create a billing portal session
        session = stripe.billing_portal.Session.create(
            customer=org.stripe_customer_id,
            return_url=f"{settings.FRONTEND_URL}/settings/billing"
        )
        
        return {"url": session.url}
        
    except ImportError:
        logger.warning("Stripe not installed, returning mock URL")
        return {"url": "/settings/billing?mock=true", "mock": True}
    except Exception as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(500, f"Billing error: {str(e)}")


@router.post("/webhook/stripe")
async def stripe_webhook():
    """
    Stripe webhook handler for subscription events.
    Handles: checkout.session.completed, customer.subscription.deleted
    """
    # Note: In production, verify the Stripe signature
    # stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    
    # Placeholder - actual implementation requires webhook verification
    return {"received": True}


@router.get("/status")
async def get_billing_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the current billing/subscription status for the organization.
    """
    org = current_user.organization
    return {
        "plan": getattr(org, 'subscription_plan', 'free') if org else 'free',
        "status": "active",
        "features": {
            "clusters_limit": 5 if getattr(org, 'subscription_plan', 'free') == 'free' else -1,
            "spot_optimization": True,
            "hibernation": True,
            "advanced_analytics": getattr(org, 'subscription_plan', 'free') != 'free'
        }
    }


# ========================================
# AWS Cost Explorer Endpoints
# ========================================

@router.get("/costs/summary")
async def get_cost_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    period: str = Query("month", regex="^(month|week|day|quarter)$"),
    account_id: Optional[str] = None
):
    """
    Get cost summary with breakdown by compute/resources.

    Args:
        period: 'month' (MTD), 'week' (last 7 days), 'day' (yesterday), 'quarter' (QTD)
        account_id: Optional specific account filter

    Returns:
        {
            "period": "Month-to-Date",
            "date_range": {"start": "2026-02-01", "end": "2026-02-10"},
            "total_cost": 1250.50,
            "compute_cost": 825.30,
            "resource_cost": 325.20,
            "other_cost": 100.00,
            "top_services": [
                {"name": "Amazon EC2", "cost": 700.00},
                {"name": "Amazon RDS", "cost": 250.00}
            ],
            "currency": "USD"
        }
    """
    # Validate user has organization
    if not current_user.organization_id:
        raise HTTPException(400, "User not associated with an organization")

    # Define date range based on period
    today = datetime.utcnow().date()
    if period == "month":
        start_date = today.replace(day=1)
        period_label = "Month-to-Date"
    elif period == "week":
        start_date = today - timedelta(days=7)
        period_label = "Last 7 Days"
    elif period == "day":
        start_date = today - timedelta(days=1)
        period_label = "Yesterday"
    elif period == "quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start_date = today.replace(month=quarter_start_month, day=1)
        period_label = "Quarter-to-Date"
    else:
        start_date = today.replace(day=1)
        period_label = "Month-to-Date"

    end_date = today

    # Build query for accounts in user's organization
    account_query = db.query(Account).filter(
        Account.organization_id == current_user.organization_id
    )

    if account_id:
        account_query = account_query.filter(Account.id == account_id)

    account_ids = [acc.id for acc in account_query.all()]

    if not account_ids:
        return {
            "period": period_label,
            "date_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "total_cost": 0.0,
            "compute_cost": 0.0,
            "resource_cost": 0.0,
            "other_cost": 0.0,
            "top_services": [],
            "currency": "USD"
        }

    # Calculate total cost
    total_cost = db.query(func.sum(DailyCost.cost_amount)).filter(
        and_(
            DailyCost.account_id.in_(account_ids),
            DailyCost.date >= start_date,
            DailyCost.date <= end_date
        )
    ).scalar() or 0.0

    # Calculate compute cost (EC2, EKS, Lambda, Fargate)
    compute_services = [
        'Amazon Elastic Compute Cloud - Compute',
        'Amazon Elastic Container Service for Kubernetes',
        'AWS Lambda',
        'Amazon EC2 Container Service'
    ]
    compute_cost = db.query(func.sum(DailyCost.cost_amount)).filter(
        and_(
            DailyCost.account_id.in_(account_ids),
            DailyCost.date >= start_date,
            DailyCost.date <= end_date,
            DailyCost.service_name.in_(compute_services)
        )
    ).scalar() or 0.0

    # Calculate resource cost (RDS, S3, EBS)
    resource_services = [
        'Amazon Relational Database Service',
        'Amazon Simple Storage Service',
        'Amazon Elastic Block Store'
    ]
    resource_cost = db.query(func.sum(DailyCost.cost_amount)).filter(
        and_(
            DailyCost.account_id.in_(account_ids),
            DailyCost.date >= start_date,
            DailyCost.date <= end_date,
            DailyCost.service_name.in_(resource_services)
        )
    ).scalar() or 0.0

    # Calculate other costs
    other_cost = total_cost - compute_cost - resource_cost

    # Get top 5 services by cost
    top_services = db.query(
        DailyCost.service_name,
        func.sum(DailyCost.cost_amount).label('total')
    ).filter(
        and_(
            DailyCost.account_id.in_(account_ids),
            DailyCost.date >= start_date,
            DailyCost.date <= end_date
        )
    ).group_by(DailyCost.service_name).order_by(
        func.sum(DailyCost.cost_amount).desc()
    ).limit(5).all()

    return {
        "period": period_label,
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "total_cost": round(total_cost, 2),
        "compute_cost": round(compute_cost, 2),
        "resource_cost": round(resource_cost, 2),
        "other_cost": round(other_cost, 2),
        "top_services": [
            {"name": svc[0], "cost": round(svc[1], 2)}
            for svc in top_services
        ],
        "currency": "USD"
    }


@router.get("/costs/daily")
async def get_daily_costs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=90),
    account_id: Optional[str] = None
):
    """
    Get daily cost trend for the last N days.

    Args:
        days: Number of days to fetch (1-90)
        account_id: Optional specific account filter

    Returns:
        {
            "data": [
                {"date": "2026-02-01", "cost": 42.50},
                {"date": "2026-02-02", "cost": 45.20},
                ...
            ],
            "total_cost": 1250.00,
            "average_daily_cost": 41.67,
            "currency": "USD"
        }
    """
    if not current_user.organization_id:
        raise HTTPException(400, "User not associated with an organization")

    # Date range
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)

    # Get account IDs
    account_query = db.query(Account).filter(
        Account.organization_id == current_user.organization_id
    )
    if account_id:
        account_query = account_query.filter(Account.id == account_id)

    account_ids = [acc.id for acc in account_query.all()]

    if not account_ids:
        return {
            "data": [],
            "total_cost": 0.0,
            "average_daily_cost": 0.0,
            "currency": "USD"
        }

    # Get daily costs grouped by date
    daily_data = db.query(
        DailyCost.date,
        func.sum(DailyCost.cost_amount).label('cost')
    ).filter(
        and_(
            DailyCost.account_id.in_(account_ids),
            DailyCost.date >= start_date,
            DailyCost.date <= end_date
        )
    ).group_by(DailyCost.date).order_by(DailyCost.date).all()

    # Calculate totals
    total_cost = sum(d.cost for d in daily_data)
    avg_cost = total_cost / len(daily_data) if daily_data else 0.0

    return {
        "data": [
            {"date": d.date.isoformat(), "cost": round(d.cost, 2)}
            for d in daily_data
        ],
        "total_cost": round(total_cost, 2),
        "average_daily_cost": round(avg_cost, 2),
        "currency": "USD"
    }


@router.get("/costs/by-service")
async def get_costs_by_service(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    period: str = Query("month", regex="^(month|week|quarter)$"),
    account_id: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50)
):
    """
    Get cost breakdown by AWS service.

    Args:
        period: Time period ('month', 'week', 'quarter')
        account_id: Optional specific account filter
        limit: Number of top services to return (1-50)

    Returns:
        {
            "services": [
                {
                    "service_name": "Amazon EC2",
                    "cost": 700.00,
                    "percentage": 56.0,
                    "daily_average": 23.33
                },
                ...
            ],
            "total_cost": 1250.00,
            "currency": "USD"
        }
    """
    if not current_user.organization_id:
        raise HTTPException(400, "User not associated with an organization")

    # Define date range
    today = datetime.utcnow().date()
    if period == "month":
        start_date = today.replace(day=1)
    elif period == "week":
        start_date = today - timedelta(days=7)
    elif period == "quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start_date = today.replace(month=quarter_start_month, day=1)
    else:
        start_date = today.replace(day=1)

    end_date = today
    days_in_period = (end_date - start_date).days + 1

    # Get account IDs
    account_query = db.query(Account).filter(
        Account.organization_id == current_user.organization_id
    )
    if account_id:
        account_query = account_query.filter(Account.id == account_id)

    account_ids = [acc.id for acc in account_query.all()]

    if not account_ids:
        return {
            "services": [],
            "total_cost": 0.0,
            "currency": "USD"
        }

    # Get total cost for percentage calculation
    total_cost = db.query(func.sum(DailyCost.cost_amount)).filter(
        and_(
            DailyCost.account_id.in_(account_ids),
            DailyCost.date >= start_date,
            DailyCost.date <= end_date
        )
    ).scalar() or 0.0

    # Get cost breakdown by service
    service_costs = db.query(
        DailyCost.service_name,
        func.sum(DailyCost.cost_amount).label('cost')
    ).filter(
        and_(
            DailyCost.account_id.in_(account_ids),
            DailyCost.date >= start_date,
            DailyCost.date <= end_date
        )
    ).group_by(DailyCost.service_name).order_by(
        func.sum(DailyCost.cost_amount).desc()
    ).limit(limit).all()

    services = []
    for svc in service_costs:
        percentage = (svc.cost / total_cost * 100) if total_cost > 0 else 0.0
        daily_avg = svc.cost / days_in_period if days_in_period > 0 else 0.0

        services.append({
            "service_name": svc.service_name,
            "cost": round(svc.cost, 2),
            "percentage": round(percentage, 2),
            "daily_average": round(daily_avg, 2)
        })

    return {
        "services": services,
        "total_cost": round(total_cost, 2),
        "currency": "USD"
    }


@router.get("/costs/sync-status")
async def get_sync_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get Cost Explorer sync status for all accounts.

    Returns:
        {
            "accounts": [
                {
                    "account_id": "123456789012",
                    "account_name": "Production",
                    "last_sync_at": "2026-02-10T08:30:00Z",
                    "status": "SUCCESS",
                    "records_synced": 450,
                    "error_message": null
                },
                ...
            ],
            "overall_status": "healthy"
        }
    """
    if not current_user.organization_id:
        raise HTTPException(400, "User not associated with an organization")

    # Get all accounts for organization
    accounts = db.query(Account).filter(
        Account.organization_id == current_user.organization_id
    ).all()

    account_statuses = []
    failed_count = 0

    for account in accounts:
        sync_status = db.query(CostExplorerSyncStatus).filter(
            CostExplorerSyncStatus.account_id == account.id
        ).first()

        if sync_status:
            account_statuses.append({
                "account_id": account.aws_account_id,
                "account_name": getattr(account, 'name', account.aws_account_id),
                "last_sync_at": sync_status.last_sync_at.isoformat() if sync_status.last_sync_at else None,
                "last_synced_date": sync_status.last_synced_date.isoformat() if sync_status.last_synced_date else None,
                "status": sync_status.status,
                "records_synced": int(sync_status.records_synced),
                "error_message": sync_status.error_message
            })

            if sync_status.status == 'FAILED':
                failed_count += 1
        else:
            account_statuses.append({
                "account_id": account.aws_account_id,
                "account_name": getattr(account, 'name', account.aws_account_id),
                "last_sync_at": None,
                "last_synced_date": None,
                "status": "NEVER_SYNCED",
                "records_synced": 0,
                "error_message": "Cost Explorer data has never been synced for this account"
            })

    # Determine overall status
    if failed_count == 0:
        overall_status = "healthy"
    elif failed_count < len(accounts):
        overall_status = "degraded"
    else:
        overall_status = "unhealthy"

    return {
        "accounts": account_statuses,
        "overall_status": overall_status
    }


@router.post("/costs/sync")
async def trigger_cost_sync(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    account_id: Optional[str] = None
):
    """
    Manually trigger Cost Explorer sync.

    Args:
        account_id: Optional specific account to sync. If None, syncs all accounts.

    Returns:
        {
            "message": "Cost sync triggered successfully",
            "task_id": "abc-123-xyz"
        }
    """
    if not current_user.organization_id:
        raise HTTPException(400, "User not associated with an organization")

    # Verify account belongs to user's organization if account_id provided
    if account_id:
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.organization_id == current_user.organization_id
        ).first()

        if not account:
            raise HTTPException(404, "Account not found or access denied")

    # Trigger Celery task
    try:
        task = sync_cost_explorer.delay(account_id=account_id)

        return {
            "message": "Cost sync triggered successfully",
            "task_id": task.id
        }

    except Exception as e:
        logger.error(f"Failed to trigger cost sync: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to trigger sync: {str(e)}")
