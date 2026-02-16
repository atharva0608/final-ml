"""
Dashboard API Routes - Three Pricing Models

This module implements three distinct pricing models:

MODEL A - Actual Cost (AWS Cost Explorer)
- Source: AWS Cost Explorer API
- What: Invoice-accurate cost - what AWS actually charged
- Use: Total Discovered Cost header, main dashboard monthly spend
- Endpoint: /dashboard/overview (actual_cost field)

MODEL B - Resources Cost (Sum of Individual Resources @ 24/7)
- Source: Individual resource pricing calculations
- What: Sum of each resource's cost assuming 24/7 uptime
- Use: Resource Hygiene Cost/Mo column, sidebar category totals
- Endpoint: /dashboard/resources-cost

MODEL C - Optimization Cost (Potential Savings)
- Source: Hygiene analysis (orphaned resources, rightsizing opportunities)
- What: Cost that can be eliminated or optimized
- Use: POTENTIAL SAVINGS card on Resource Hygiene page
- Endpoint: /dashboard/savings-projection
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
from decimal import Decimal

from backend.core.dependencies import get_db, get_current_user
from backend.models.user import User
from backend.models.account import Account
from backend.models.billing import DailyCost
from backend.models.instance import Instance
from backend.models.cluster import Cluster
from backend.services.metrics_service import MetricsService
from backend.services.resource_pricing_service import ResourcePricingService
from backend.services.hygiene_service import HygieneService
from backend.core.redis_client import get_redis_client
from sqlalchemy import func, and_
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/overview")
def get_dashboard_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get dashboard overview with all three pricing models.

    Returns:
        {
            "actual_cost": 54.44,           # MODEL A: From Cost Explorer (invoice-accurate)
            "resources_cost": 23.62,         # MODEL B: Sum of all resources @ 24/7
            "optimization_cost": 17.30,      # MODEL C: Potential savings
            "net_savings": 0.00,             # Spot savings realized
            "savings_rate": 0.0,             # Percentage
            "active_instances": 1,
            "total_clusters": 0,
            "health_scores": {
                "ri": null,
                "s3": null,
                "rds": null,
                "transfer": null
            }
        }
    """
    # Get organization accounts
    org_accounts = db.query(Account.id).filter(
        Account.organization_id == current_user.organization_id
    ).all()
    org_account_ids = [acc.id for acc in org_accounts]

    if not org_account_ids:
        return {
            "actual_cost": 0.0,
            "resources_cost": 0.0,
            "optimization_cost": 0.0,
            "net_savings": 0.0,
            "savings_rate": 0.0,
            "active_instances": 0,
            "total_clusters": 0,
            "health_scores": {"ri": None, "s3": None, "rds": None, "transfer": None}
        }

    # MODEL A: Actual Cost from Cost Explorer
    start_date = datetime.now().replace(day=1).date()
    end_date = datetime.now().date()

    cost_query = db.query(
        func.sum(DailyCost.cost_amount).label('total')
    ).filter(
        DailyCost.account_id.in_(org_account_ids),
        DailyCost.date >= start_date,
        DailyCost.date <= end_date
    ).scalar()

    if cost_query and cost_query > 0:
        days_elapsed = (end_date - start_date).days + 1
        actual_cost = (float(cost_query) / days_elapsed) * 30
    else:
        # Fallback to EC2 instances
        instances = db.query(Instance).filter(
            Instance.account_id.in_(org_account_ids),
            Instance.state.in_(['running', 'pending'])
        ).all()
        actual_cost = sum(float(inst.price or 0) * 720 for inst in instances)

    # MODEL B: Resources Cost (sum of individual resources @ 24/7)
    # This comes from cached resource pricing (updated by worker)
    resources_cost = calculate_resources_cost(db, org_account_ids)

    # MODEL C: Optimization Cost (potential savings from hygiene)
    optimization_cost = calculate_optimization_cost(db, org_account_ids)

    # Count active instances and clusters
    active_instances = db.query(func.count(Instance.id)).filter(
        Instance.account_id.in_(org_account_ids),
        Instance.state.in_(['running', 'pending'])
    ).scalar() or 0

    total_clusters = db.query(func.count(Cluster.id)).filter(
        Cluster.account_id.in_(org_account_ids)
    ).scalar() or 0

    # Calculate net savings (spot vs on-demand)
    # For now, we don't have realized spot savings, so this is 0
    net_savings = 0.0
    savings_rate = 0.0

    return {
        "actual_cost": round(actual_cost, 2),
        "resources_cost": round(resources_cost, 2),
        "optimization_cost": round(optimization_cost, 2),
        "net_savings": round(net_savings, 2),
        "savings_rate": round(savings_rate, 2),
        "active_instances": active_instances,
        "total_clusters": total_clusters,
        "health_scores": {
            "ri": None,
            "s3": None,
            "rds": None,
            "transfer": None
        }
    }


@router.get("/cost-breakdown")
def get_cost_breakdown(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get cost breakdown by category (MODEL A: Actual Cost from Cost Explorer).

    Returns:
        {
            "compute": 29.99,
            "storage": 0.80,
            "network": 7.39,
            "security": 8.25,
            "management": 7.83,
            "others": 0.18
        }
    """
    # Get organization accounts
    org_accounts = db.query(Account.id).filter(
        Account.organization_id == current_user.organization_id
    ).all()
    org_account_ids = [acc.id for acc in org_accounts]

    if not org_account_ids:
        return {
            "compute": 0.0,
            "storage": 0.0,
            "network": 0.0,
            "security": 0.0,
            "management": 0.0,
            "others": 0.0
        }

    # Query Cost Explorer data
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
    days_elapsed = (end_date - start_date).days + 1
    breakdown = {
        "compute": 0.0,
        "storage": 0.0,
        "network": 0.0,
        "security": 0.0,
        "management": 0.0,
        "others": 0.0
    }

    for service, cost in cost_data:
        monthly_cost = (float(cost) / days_elapsed) * 30

        if any(s in service for s in ['Elastic Compute Cloud', 'EC2', 'Elastic Container Service', 'EKS', 'Lambda']):
            breakdown['compute'] += monthly_cost
        elif any(s in service for s in ['Simple Storage Service', 'Elastic Block Store', 'Elastic File System', 'Backup']):
            breakdown['storage'] += monthly_cost
        elif any(s in service for s in ['Virtual Private Cloud', 'Data Transfer', 'Load Balancing', 'CloudFront']):
            breakdown['network'] += monthly_cost
        elif any(s in service for s in ['Security Hub', 'Key Management Service', 'Secrets Manager']):
            breakdown['security'] += monthly_cost
        elif any(s in service for s in ['Config', 'Systems Manager', 'CloudWatch']):
            breakdown['management'] += monthly_cost
        else:
            breakdown['others'] += monthly_cost

    return {k: round(v, 2) for k, v in breakdown.items()}


@router.get("/savings-projection")
def get_savings_projection(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get savings projection (MODEL C: Optimization Cost).

    Returns:
        {
            "current_spend": 54.44,          # MODEL A: Actual from Cost Explorer
            "optimized_spend": 37.14,        # After removing waste
            "potential_savings": 17.30,      # MODEL C: Hygiene + optimization
            "breakdown": {
                "hygiene_waste": 8.50,       # Orphaned resources
                "optimization_opportunities": 8.80  # Rightsizing, etc.
            }
        }
    """
    # Get organization accounts
    org_accounts = db.query(Account.id).filter(
        Account.organization_id == current_user.organization_id
    ).all()
    org_account_ids = [acc.id for acc in org_accounts]

    if not org_account_ids:
        return {
            "current_spend": 0.0,
            "optimized_spend": 0.0,
            "potential_savings": 0.0,
            "breakdown": {
                "hygiene_waste": 0.0,
                "optimization_opportunities": 0.0
            }
        }

    # Get current spend (MODEL A)
    start_date = datetime.now().replace(day=1).date()
    end_date = datetime.now().date()

    cost_query = db.query(
        func.sum(DailyCost.cost_amount).label('total')
    ).filter(
        DailyCost.account_id.in_(org_account_ids),
        DailyCost.date >= start_date,
        DailyCost.date <= end_date
    ).scalar()

    if cost_query and cost_query > 0:
        days_elapsed = (end_date - start_date).days + 1
        current_spend = (float(cost_query) / days_elapsed) * 30
    else:
        instances = db.query(Instance).filter(
            Instance.account_id.in_(org_account_ids),
            Instance.state.in_(['running', 'pending'])
        ).all()
        current_spend = sum(float(inst.price or 0) * 720 for inst in instances)

    # Calculate potential savings (MODEL C)
    hygiene_waste = calculate_hygiene_waste(db, org_account_ids)
    optimization_opportunities = calculate_optimization_opportunities(db, org_account_ids)

    potential_savings = hygiene_waste + optimization_opportunities
    optimized_spend = max(0, current_spend - potential_savings)

    return {
        "current_spend": round(current_spend, 2),
        "optimized_spend": round(optimized_spend, 2),
        "potential_savings": round(potential_savings, 2),
        "breakdown": {
            "hygiene_waste": round(hygiene_waste, 2),
            "optimization_opportunities": round(optimization_opportunities, 2)
        }
    }


@router.get("/fleet-composition")
def get_fleet_composition(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get fleet composition breakdown.

    Returns:
        {
            "total_instances": 1,
            "by_type": {"t3.micro": 1},
            "by_lifecycle": {"on_demand": 1, "spot": 0},
            "by_state": {"running": 1, "stopped": 0}
        }
    """
    # Get organization accounts
    org_accounts = db.query(Account.id).filter(
        Account.organization_id == current_user.organization_id
    ).all()
    org_account_ids = [acc.id for acc in org_accounts]

    if not org_account_ids:
        return {
            "total_instances": 0,
            "by_type": {},
            "by_lifecycle": {"on_demand": 0, "spot": 0},
            "by_state": {"running": 0, "stopped": 0, "terminated": 0}
        }

    # Total instances
    total_instances = db.query(func.count(Instance.id)).filter(
        Instance.account_id.in_(org_account_ids)
    ).scalar() or 0

    # By type
    type_counts = db.query(
        Instance.instance_type,
        func.count(Instance.id)
    ).filter(
        Instance.account_id.in_(org_account_ids)
    ).group_by(Instance.instance_type).all()

    by_type = {t[0] or "unknown": t[1] for t in type_counts}

    # By lifecycle
    from backend.models.instance import InstanceLifecycle
    spot_count = db.query(func.count(Instance.id)).filter(
        Instance.account_id.in_(org_account_ids),
        Instance.lifecycle == InstanceLifecycle.SPOT
    ).scalar() or 0

    on_demand_count = total_instances - spot_count

    # By state
    running_count = db.query(func.count(Instance.id)).filter(
        Instance.account_id.in_(org_account_ids),
        Instance.state == 'running'
    ).scalar() or 0

    stopped_count = db.query(func.count(Instance.id)).filter(
        Instance.account_id.in_(org_account_ids),
        Instance.state == 'stopped'
    ).scalar() or 0

    terminated_count = db.query(func.count(Instance.id)).filter(
        Instance.account_id.in_(org_account_ids),
        Instance.state == 'terminated'
    ).scalar() or 0

    return {
        "total_instances": total_instances,
        "by_type": by_type,
        "by_lifecycle": {
            "on_demand": on_demand_count,
            "spot": spot_count
        },
        "by_state": {
            "running": running_count,
            "stopped": stopped_count,
            "terminated": terminated_count
        }
    }


@router.get("/activity-feed")
def get_activity_feed(
    limit: int = Query(10, description="Number of activities to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get recent activity feed.

    Returns:
        {
            "activities": [
                {
                    "timestamp": "2026-02-12T10:00:00Z",
                    "action": "INSTANCE_DISCOVERED",
                    "resource_id": "i-xxx",
                    "details": "New t3.micro instance discovered"
                }
            ]
        }
    """
    # For now, return empty list
    # In the future, this would query an audit log or event stream
    return {
        "activities": []
    }


# Helper functions for calculating costs

def calculate_resources_cost(db: Session, account_ids: list) -> float:
    """
    Calculate MODEL B: Resources Cost (sum of all resources @ 24/7).

    This sums up costs from Redis cache (populated by resource_pricing_worker).
    """
    redis_client = get_redis_client()
    total_cost = 0.0

    # Search for all cached resource prices
    # In production, we'd iterate through known resources
    # For now, we'll use a placeholder calculation based on running instances

    # Get all running instances
    instances = db.query(Instance).filter(
        Instance.account_id.in_(account_ids),
        Instance.state.in_(['running', 'pending'])
    ).all()

    for instance in instances:
        # Try to get from cache first
        cache_key = f"resource_price:INSTANCE:{instance.instance_id}"
        cached_cost = redis_client.get(cache_key)

        if cached_cost:
            try:
                cost_data = json.loads(cached_cost)
                total_cost += cost_data.get('cost', 0)
            except:
                # Fallback to instance price * 720
                total_cost += float(instance.price or 0) * 720
        else:
            # Fallback to instance price * 720
            total_cost += float(instance.price or 0) * 720

    return total_cost


def calculate_optimization_cost(db: Session, account_ids: list) -> float:
    """
    Calculate MODEL C: Optimization Cost (potential savings).

    This sums up all potential savings from hygiene issues and optimization opportunities.
    """
    hygiene_waste = calculate_hygiene_waste(db, account_ids)
    optimization_opportunities = calculate_optimization_opportunities(db, account_ids)
    return hygiene_waste + optimization_opportunities


def calculate_hygiene_waste(db: Session, account_ids: list) -> float:
    """
    Calculate hygiene waste from orphaned resources.
    """
    redis_client = get_redis_client()
    total_waste = 0.0

    # Try to get from cached hygiene scans
    for account_id in account_ids:
        cache_key = f"cleanup:scan:{account_id}:ALL"
        cached_data = redis_client.get(cache_key)

        if cached_data:
            try:
                data = json.loads(cached_data)
                for resource in data.get('resources', []):
                    # Only count unauthorized (orphaned) resources
                    if not resource.get('is_authorized', False):
                        total_waste += resource.get('cost_per_month', 0.0)
            except:
                pass

    return total_waste


def calculate_optimization_opportunities(db: Session, account_ids: list) -> float:
    """
    Calculate optimization opportunities (rightsizing, RI recommendations, etc.).

    For now, return 0. In the future, this would query optimization analysis results.
    """
    # Placeholder: Calculate based on stopped instances that still have EBS costs
    stopped_instances = db.query(Instance).filter(
        Instance.account_id.in_(account_ids),
        Instance.state == 'stopped'
    ).all()

    # Stopped instances still pay for EBS volumes
    # Estimate $0.10/GB-month for volumes
    # Assume average 30GB per instance
    optimization_cost = len(stopped_instances) * 30 * 0.10

    return optimization_cost
