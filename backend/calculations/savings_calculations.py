"""
Savings Calculation Functions

All savings-related calculations for the Spot Optimizer platform.

Savings calculation principles:
1. Spot savings = (On-demand equivalent price - Actual spot price)
2. Average spot discount = 70% (used when exact prices unknown)
3. Hibernation savings = Cost of instances during sleep period
4. Total savings = Spot savings + Hibernation savings + RI savings + Other optimizations
"""

from decimal import Decimal
from typing import Optional, Dict, List, Tuple


# Constants
AVERAGE_SPOT_DISCOUNT = 0.70  # 70% average spot discount vs on-demand
SPOT_MULTIPLIER = 0.30  # Spot instances typically cost 30% of on-demand


def calculate_spot_savings(
    spot_cost: float,
    spot_discount: float = AVERAGE_SPOT_DISCOUNT
) -> Decimal:
    """
    Calculate savings from using spot instances instead of on-demand.

    Formula: spot_cost / (1 - discount) - spot_cost
    If spot_cost is $30 and discount is 70%, on-demand would be $100, savings = $70

    Args:
        spot_cost: Actual cost paid for spot instances
        spot_discount: Discount percentage (0.70 = 70% discount)

    Returns:
        Savings amount as Decimal

    Example:
        >>> calculate_spot_savings(30.0, 0.70)  # $30 spot cost with 70% discount
        Decimal('70.00')  # Would have cost $100 on-demand, saved $70
    """
    if spot_cost <= 0:
        return Decimal('0.0')

    # Calculate what it would have cost on-demand
    # spot_cost = on_demand_cost * (1 - discount)
    # on_demand_cost = spot_cost / (1 - discount)
    multiplier = 1 - spot_discount
    on_demand_equivalent = spot_cost / multiplier if multiplier > 0 else 0.0

    # Savings = what we would have paid - what we actually paid
    savings = on_demand_equivalent - spot_cost

    return Decimal(str(savings))


def calculate_hibernation_savings(
    instance_hourly_cost: float,
    hibernation_hours: float
) -> Decimal:
    """
    Calculate savings from hibernating instances (scaling to zero).

    Args:
        instance_hourly_cost: Cost per hour when instance is running
        hibernation_hours: Number of hours instance was hibernated

    Returns:
        Savings from hibernation as Decimal

    Example:
        >>> calculate_hibernation_savings(0.10, 480)  # $0.10/hr for 20 days (480 hrs)
        Decimal('48.00')
    """
    if instance_hourly_cost <= 0 or hibernation_hours <= 0:
        return Decimal('0.0')

    savings = instance_hourly_cost * hibernation_hours
    return Decimal(str(savings))


def calculate_total_savings(
    spot_cost: float,
    on_demand_cost: float,
    hibernation_savings: float = 0.0,
    ri_savings: float = 0.0,
    spot_discount: float = AVERAGE_SPOT_DISCOUNT
) -> Decimal:
    """
    Calculate total savings across all optimization strategies.

    Args:
        spot_cost: Actual cost for spot instances
        on_demand_cost: Cost for on-demand instances
        hibernation_savings: Savings from hibernation
        ri_savings: Savings from Reserved Instances
        spot_discount: Average spot discount (default 70%)

    Returns:
        Total savings as Decimal

    Example:
        >>> calculate_total_savings(30.0, 100.0, 20.0, 10.0)
        Decimal('100.00')  # $70 spot + $20 hibernation + $10 RI = $100 total savings
    """
    # Calculate spot savings
    spot_savings_amount = calculate_spot_savings(spot_cost, spot_discount)

    # Total all savings
    total = float(spot_savings_amount) + hibernation_savings + ri_savings

    return Decimal(str(total))


def calculate_savings_percentage(
    savings_amount: float,
    total_cost_without_optimization: float
) -> float:
    """
    Calculate savings as a percentage of what would have been spent.

    Formula: (savings / total_without_optimization) × 100

    Args:
        savings_amount: Total savings amount
        total_cost_without_optimization: What it would have cost without optimization

    Returns:
        Savings percentage (0-100)

    Example:
        >>> calculate_savings_percentage(70.0, 100.0)
        70.0  # 70% savings
    """
    if total_cost_without_optimization <= 0:
        return 0.0

    percentage = (savings_amount / total_cost_without_optimization) * 100

    return round(percentage, 2)


def calculate_potential_savings(
    current_on_demand_cost: float,
    spot_discount: float = AVERAGE_SPOT_DISCOUNT,
    hibernation_opportunity_hours: float = 0.0,
    avg_hourly_cost: float = 0.0
) -> Decimal:
    """
    Calculate potential savings if optimizations were applied.
    Used for "opportunity" calculations.

    Args:
        current_on_demand_cost: Current cost for on-demand instances
        spot_discount: Expected spot discount if converted
        hibernation_opportunity_hours: Hours that could be hibernated
        avg_hourly_cost: Average hourly cost of instances

    Returns:
        Potential savings as Decimal

    Example:
        >>> calculate_potential_savings(100.0, 0.70, 200.0, 0.10)
        Decimal('90.00')  # $70 from spot + $20 from hibernation
    """
    # Potential spot savings
    potential_spot_savings = current_on_demand_cost * spot_discount

    # Potential hibernation savings
    potential_hibernation_savings = hibernation_opportunity_hours * avg_hourly_cost

    total_potential = potential_spot_savings + potential_hibernation_savings

    return Decimal(str(total_potential))


def calculate_optimization_rate(
    spot_instances: int,
    on_demand_instances: int,
    hibernated_hours: float = 0.0,
    total_hours: float = 720.0
) -> float:
    """
    Calculate overall optimization rate (0-100%).
    Considers both spot usage and hibernation.

    Args:
        spot_instances: Number of spot instances
        on_demand_instances: Number of on-demand instances
        hibernated_hours: Total hours hibernated
        total_hours: Total possible hours (default 720 for month)

    Returns:
        Optimization rate as percentage (0-100)

    Example:
        >>> calculate_optimization_rate(7, 3, 200, 720)
        75.5  # 70% spot + 27.8% hibernation = 75.5% optimized
    """
    total_instances = spot_instances + on_demand_instances

    if total_instances == 0:
        return 0.0

    # Spot optimization rate (what % are spot)
    spot_rate = (spot_instances / total_instances) * 100

    # Hibernation optimization rate (what % of time is hibernated)
    hibernation_rate = 0.0
    if total_hours > 0:
        hibernation_rate = (hibernated_hours / total_hours) * 100

    # Combined rate (weighted average)
    # Note: This is a simplified calculation
    # A more sophisticated approach would weight by cost
    combined_rate = (spot_rate * 0.7) + (hibernation_rate * 0.3)

    return round(combined_rate, 2)


def calculate_cost_breakdown(
    total_cost: float,
    spot_cost: float,
    on_demand_cost: float
) -> Dict[str, Dict[str, float]]:
    """
    Calculate cost breakdown with percentages.

    Args:
        total_cost: Total cost
        spot_cost: Cost of spot instances
        on_demand_cost: Cost of on-demand instances

    Returns:
        Dictionary with cost breakdown and percentages

    Example:
        >>> calculate_cost_breakdown(100.0, 30.0, 70.0)
        {
            'spot': {'cost': 30.0, 'percentage': 30.0},
            'on_demand': {'cost': 70.0, 'percentage': 70.0}
        }
    """
    breakdown = {
        'spot': {
            'cost': spot_cost,
            'percentage': (spot_cost / total_cost * 100) if total_cost > 0 else 0.0
        },
        'on_demand': {
            'cost': on_demand_cost,
            'percentage': (on_demand_cost / total_cost * 100) if total_cost > 0 else 0.0
        }
    }

    return breakdown


def calculate_roi(
    savings_amount: float,
    platform_cost: float = 0.0
) -> float:
    """
    Calculate ROI (Return on Investment) for the optimization platform.

    Formula: ((savings - cost) / cost) × 100

    Args:
        savings_amount: Total savings achieved
        platform_cost: Cost of using the platform (if any)

    Returns:
        ROI percentage

    Example:
        >>> calculate_roi(1000.0, 100.0)
        900.0  # 900% ROI
    """
    if platform_cost <= 0:
        return 0.0 if savings_amount <= 0 else float('inf')

    roi = ((savings_amount - platform_cost) / platform_cost) * 100

    return round(roi, 2)
