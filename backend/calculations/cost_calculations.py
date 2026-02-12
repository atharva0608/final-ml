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
