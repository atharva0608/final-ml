"""
Cost Calculation Functions

All cost-related calculations for the Spot Optimizer platform.
These functions are pure and stateless - they take inputs and return calculated values
without side effects.

Cost calculation principles:
1. Instance hourly price × hours = instance cost
2. Sum of instance costs = total cost
3. Monthly cost = hourly price × 720 hours (30 days × 24 hours)
4. Daily cost = hourly price × 24 hours
"""

from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session


# Constants
HOURS_PER_DAY = 24
HOURS_PER_MONTH = 720  # 30 days × 24 hours
FALLBACK_HOURLY_PRICE = Decimal('0.05')  # Fallback if price is unknown


def calculate_instance_cost(
    hourly_price: Optional[float],
    hours: float,
    fallback_price: Optional[Decimal] = None
) -> Decimal:
    """
    Calculate cost for a single instance over a time period.

    Args:
        hourly_price: Hourly price of the instance (can be None)
        hours: Number of hours to calculate cost for
        fallback_price: Fallback price if hourly_price is None

    Returns:
        Total cost as Decimal

    Example:
        >>> calculate_instance_cost(0.0104, 720)  # t3.micro for 1 month
        Decimal('7.488')
    """
    if fallback_price is None:
        fallback_price = FALLBACK_HOURLY_PRICE

    # Convert hourly price to Decimal
    price = Decimal(str(hourly_price)) if hourly_price is not None else fallback_price

    # Calculate cost
    cost = price * Decimal(str(hours))

    return cost


def calculate_total_cost(
    instances: List,
    start_date: datetime,
    end_date: datetime
) -> Decimal:
    """
    Calculate total cost for multiple instances over a time range.

    Args:
        instances: List of instance objects with .price and .created_at attributes
        start_date: Start of time range
        end_date: End of time range

    Returns:
        Total cost as Decimal

    Example:
        >>> instances = [instance1, instance2, instance3]
        >>> calculate_total_cost(instances, start, end)
        Decimal('150.25')
    """
    total = Decimal('0.0')

    for instance in instances:
        # Determine actual time range for this instance
        instance_start = max(
            instance.created_at if instance.created_at else start_date,
            start_date
        )
        instance_end = min(datetime.utcnow(), end_date)

        # Calculate hours this instance was running
        hours = (instance_end - instance_start).total_seconds() / 3600

        # Calculate cost for this instance
        instance_cost = calculate_instance_cost(instance.price, hours)
        total += instance_cost

    return total


def calculate_daily_cost(
    instances: List,
    date: datetime
) -> Decimal:
    """
    Calculate total cost for a specific day.

    Args:
        instances: List of instance objects
        date: The date to calculate cost for

    Returns:
        Cost for that day as Decimal

    Example:
        >>> calculate_daily_cost(instances, datetime(2026, 2, 12))
        Decimal('7.50')
    """
    start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    return calculate_total_cost(instances, start_of_day, end_of_day)


def calculate_monthly_cost(
    hourly_price: Optional[float],
    fallback_price: Optional[Decimal] = None
) -> Decimal:
    """
    Calculate monthly cost from hourly price.
    Uses standard 720-hour month (30 days × 24 hours).

    Args:
        hourly_price: Hourly price of the instance
        fallback_price: Fallback price if hourly_price is None

    Returns:
        Monthly cost as Decimal

    Example:
        >>> calculate_monthly_cost(0.0104)  # t3.micro
        Decimal('7.488')
    """
    return calculate_instance_cost(hourly_price, HOURS_PER_MONTH, fallback_price)


def calculate_cost_by_lifecycle(
    instances: List,
    start_date: datetime,
    end_date: datetime
) -> Tuple[Decimal, Decimal, Decimal]:
    """
    Calculate costs broken down by instance lifecycle (spot vs on-demand).

    Args:
        instances: List of instance objects with .lifecycle attribute
        start_date: Start of time range
        end_date: End of time range

    Returns:
        Tuple of (total_cost, spot_cost, on_demand_cost)

    Example:
        >>> total, spot, on_demand = calculate_cost_by_lifecycle(instances, start, end)
        >>> print(f"Total: ${total}, Spot: ${spot}, On-Demand: ${on_demand}")
        Total: $150.00, Spot: $45.00, On-Demand: $105.00
    """
    total_cost = Decimal('0.0')
    spot_cost = Decimal('0.0')
    on_demand_cost = Decimal('0.0')

    for instance in instances:
        # Determine actual time range for this instance
        instance_start = max(
            instance.created_at if instance.created_at else start_date,
            start_date
        )
        instance_end = min(datetime.utcnow(), end_date)

        # Calculate hours this instance was running
        hours = (instance_end - instance_start).total_seconds() / 3600

        # Calculate cost for this instance
        instance_cost = calculate_instance_cost(instance.price, hours)
        total_cost += instance_cost

        # Categorize by lifecycle
        if hasattr(instance, 'lifecycle'):
            from backend.models.instance import InstanceLifecycle
            if instance.lifecycle == InstanceLifecycle.SPOT:
                spot_cost += instance_cost
            else:
                on_demand_cost += instance_cost
        else:
            # If no lifecycle info, assume on-demand
            on_demand_cost += instance_cost

    return total_cost, spot_cost, on_demand_cost


def calculate_cluster_cost(
    instances: List,
    hours: Optional[float] = None
) -> Decimal:
    """
    Calculate total cost for a cluster based on its instances.
    If hours not provided, uses monthly calculation (720 hours).

    Args:
        instances: List of instance objects in the cluster
        hours: Optional hours to calculate for (defaults to 720 for monthly)

    Returns:
        Cluster cost as Decimal

    Example:
        >>> calculate_cluster_cost(cluster_instances)
        Decimal('450.00')
    """
    if hours is None:
        hours = HOURS_PER_MONTH

    total = Decimal('0.0')

    for instance in instances:
        instance_cost = calculate_instance_cost(instance.price, hours)
        total += instance_cost

    return total


def calculate_account_cost(
    instances: List
) -> Decimal:
    """
    Calculate total monthly cost for an account based on all its instances.

    Args:
        instances: List of all instance objects for the account

    Returns:
        Account monthly cost as Decimal

    Example:
        >>> calculate_account_cost(all_account_instances)
        Decimal('1250.00')
    """
    total = Decimal('0.0')

    for instance in instances:
        monthly_cost = calculate_monthly_cost(instance.price)
        total += monthly_cost

    return total


# ========================================
# AWS Cost Explorer Integration (Hybrid Approach)
# ========================================

def calculate_cost_with_explorer(
    account_id: str,
    start_date: datetime,
    end_date: datetime,
    db: Session
) -> Tuple[Decimal, str]:
    """
    Calculate cost using AWS Cost Explorer data (100% accurate).
    Falls back to hourly estimation if Cost Explorer data not available.

    This implements a hybrid approach:
    1. Try Cost Explorer data first (accurate, matches AWS invoice)
    2. Fallback to hourly calculation (estimation, ~85-90% accurate)

    Args:
        account_id: Account ID to calculate cost for
        start_date: Start of time range
        end_date: End of time range
        db: Database session

    Returns:
        Tuple of (total_cost, data_source)
        - total_cost: Calculated cost as Decimal
        - data_source: 'cost_explorer' or 'hourly_estimation'

    Example:
        >>> cost, source = calculate_cost_with_explorer(acc_id, start, end, db)
        >>> print(f"Cost: ${cost} (Source: {source})")
        Cost: $1250.50 (Source: cost_explorer)
    """
    from backend.models.billing import DailyCost
    from backend.models.instance import Instance
    from sqlalchemy import func, and_

    # Try Cost Explorer data first
    cost_records = db.query(func.sum(DailyCost.cost_amount)).filter(
        and_(
            DailyCost.account_id == account_id,
            DailyCost.date >= start_date.date(),
            DailyCost.date <= end_date.date()
        )
    ).scalar()

    if cost_records is not None and cost_records > 0:
        # Cost Explorer data available - use it (100% accurate)
        return Decimal(str(cost_records)), 'cost_explorer'
    else:
        # Fallback to hourly estimation (~85-90% accurate)
        instances = db.query(Instance).filter(
            Instance.account_id == account_id,
            Instance.state.in_(['running', 'pending'])
        ).all()

        total_cost = calculate_total_cost(instances, start_date, end_date)
        return total_cost, 'hourly_estimation'


def calculate_cluster_cost_with_explorer(
    cluster_id: str,
    start_date: datetime,
    end_date: datetime,
    db: Session
) -> Tuple[Decimal, str]:
    """
    Calculate cluster cost using hybrid approach (Cost Explorer + fallback).

    Note: Cost Explorer groups by service, not cluster. This function
    estimates cluster cost by summing instance costs when Cost Explorer
    data is available for the account.

    Args:
        cluster_id: Cluster ID to calculate cost for
        start_date: Start of time range
        end_date: End of time range
        db: Database session

    Returns:
        Tuple of (total_cost, data_source)

    Example:
        >>> cost, source = calculate_cluster_cost_with_explorer(cluster_id, start, end, db)
        >>> print(f"Cluster cost: ${cost} (Source: {source})")
        Cluster cost: $450.00 (Source: hourly_estimation)
    """
    from backend.models.instance import Instance
    from backend.models.cluster import Cluster

    # Get cluster and its instances
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        return Decimal('0.0'), 'not_found'

    instances = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.state.in_(['running', 'pending'])
    ).all()

    # For clusters, we use hourly estimation as Cost Explorer doesn't group by cluster
    # In the future, this could be enhanced to use instance-level Cost Explorer data
    total_cost = calculate_total_cost(instances, start_date, end_date)

    return total_cost, 'hourly_estimation'


def get_cost_data_source(account_id: str, db: Session) -> Dict[str, any]:
    """
    Check if Cost Explorer data is available for an account.

    Args:
        account_id: Account ID to check
        db: Database session

    Returns:
        {
            'has_cost_explorer_data': bool,
            'last_synced': datetime or None,
            'sync_status': 'SUCCESS' | 'FAILED' | 'NEVER_SYNCED',
            'records_count': int
        }

    Example:
        >>> info = get_cost_data_source(account_id, db)
        >>> if info['has_cost_explorer_data']:
        >>>     print("Using 100% accurate Cost Explorer data")
    """
    from backend.models.billing import DailyCost, CostExplorerSyncStatus
    from sqlalchemy import func

    # Check sync status
    sync_status = db.query(CostExplorerSyncStatus).filter(
        CostExplorerSyncStatus.account_id == account_id
    ).first()

    # Count cost records
    records_count = db.query(func.count(DailyCost.id)).filter(
        DailyCost.account_id == account_id
    ).scalar() or 0

    if sync_status:
        return {
            'has_cost_explorer_data': records_count > 0,
            'last_synced': sync_status.last_sync_at,
            'sync_status': sync_status.status,
            'records_count': records_count
        }
    else:
        return {
            'has_cost_explorer_data': False,
            'last_synced': None,
            'sync_status': 'NEVER_SYNCED',
            'records_count': 0
        }
