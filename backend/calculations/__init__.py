"""
Calculations Module

This module contains all calculation logic used throughout the application.
Calculations are separated from service logic to:
1. Make them easier to test
2. Enable reuse across different services
3. Simplify maintenance and updates to calculation formulas
4. Provide a single source of truth for business logic

Modules:
- cost_calculations: Cost-related calculations (hourly, daily, monthly costs)
- savings_calculations: Savings calculations (spot vs on-demand, hibernation, etc.)
- metrics_calculations: General metrics calculations (averages, percentages, etc.)
"""

from .cost_calculations import (
    calculate_instance_cost,
    calculate_total_cost,
    calculate_daily_cost,
    calculate_monthly_cost,
    calculate_cost_by_lifecycle
)

from .savings_calculations import (
    calculate_spot_savings,
    calculate_hibernation_savings,
    calculate_total_savings,
    calculate_savings_percentage,
    calculate_potential_savings
)

from .metrics_calculations import (
    calculate_percentage,
    calculate_utilization,
    calculate_average,
    calculate_waste_percentage
)

__all__ = [
    # Cost calculations
    'calculate_instance_cost',
    'calculate_total_cost',
    'calculate_daily_cost',
    'calculate_monthly_cost',
    'calculate_cost_by_lifecycle',

    # Savings calculations
    'calculate_spot_savings',
    'calculate_hibernation_savings',
    'calculate_total_savings',
    'calculate_savings_percentage',
    'calculate_potential_savings',

    # Metrics calculations
    'calculate_percentage',
    'calculate_utilization',
    'calculate_average',
    'calculate_waste_percentage',
]
