"""
Metrics Calculation Functions

General metrics and statistical calculations for the Spot Optimizer platform.
These functions provide utility calculations for percentages, averages, ratios, etc.
"""

from typing import List, Optional, Dict
from decimal import Decimal


def calculate_percentage(
    part: float,
    total: float,
    decimal_places: int = 2
) -> float:
    """
    Calculate percentage of part relative to total.

    Args:
        part: The part value
        total: The total value
        decimal_places: Number of decimal places to round to

    Returns:
        Percentage (0-100)

    Example:
        >>> calculate_percentage(25, 100)
        25.0
        >>> calculate_percentage(1, 3, 2)
        33.33
    """
    if total == 0:
        return 0.0

    percentage = (part / total) * 100
    return round(percentage, decimal_places)


def calculate_utilization(
    used: float,
    capacity: float,
    decimal_places: int = 2
) -> float:
    """
    Calculate utilization percentage.

    Args:
        used: Amount used
        capacity: Total capacity
        decimal_places: Number of decimal places

    Returns:
        Utilization percentage (0-100)

    Example:
        >>> calculate_utilization(75, 100)
        75.0
        >>> calculate_utilization(8, 16, 1)
        50.0
    """
    return calculate_percentage(used, capacity, decimal_places)


def calculate_average(
    values: List[float],
    decimal_places: int = 2
) -> float:
    """
    Calculate average of a list of values.

    Args:
        values: List of numeric values
        decimal_places: Number of decimal places

    Returns:
        Average value

    Example:
        >>> calculate_average([10, 20, 30])
        20.0
        >>> calculate_average([1.5, 2.5, 3.5], 1)
        2.5
    """
    if not values or len(values) == 0:
        return 0.0

    average = sum(values) / len(values)
    return round(average, decimal_places)


def calculate_waste_percentage(
    wasted: float,
    total: float,
    decimal_places: int = 2
) -> float:
    """
    Calculate waste percentage (inverse of utilization).

    Args:
        wasted: Amount wasted
        total: Total amount
        decimal_places: Number of decimal places

    Returns:
        Waste percentage (0-100)

    Example:
        >>> calculate_waste_percentage(25, 100)
        25.0
    """
    return calculate_percentage(wasted, total, decimal_places)


def calculate_growth_rate(
    current: float,
    previous: float,
    decimal_places: int = 2
) -> float:
    """
    Calculate growth rate (positive or negative).

    Args:
        current: Current value
        previous: Previous value
        decimal_places: Number of decimal places

    Returns:
        Growth rate as percentage (can be negative)

    Example:
        >>> calculate_growth_rate(120, 100)
        20.0  # 20% growth
        >>> calculate_growth_rate(80, 100)
        -20.0  # 20% decrease
    """
    if previous == 0:
        return 0.0 if current == 0 else 100.0

    growth = ((current - previous) / previous) * 100
    return round(growth, decimal_places)


def calculate_ratio(
    numerator: float,
    denominator: float,
    decimal_places: int = 2
) -> float:
    """
    Calculate ratio of two values.

    Args:
        numerator: Top value
        denominator: Bottom value
        decimal_places: Number of decimal places

    Returns:
        Ratio value

    Example:
        >>> calculate_ratio(3, 4)
        0.75
        >>> calculate_ratio(10, 3, 3)
        3.333
    """
    if denominator == 0:
        return 0.0

    ratio = numerator / denominator
    return round(ratio, decimal_places)


def calculate_median(values: List[float]) -> float:
    """
    Calculate median of a list of values.

    Args:
        values: List of numeric values

    Returns:
        Median value

    Example:
        >>> calculate_median([1, 2, 3, 4, 5])
        3.0
        >>> calculate_median([1, 2, 3, 4])
        2.5
    """
    if not values or len(values) == 0:
        return 0.0

    sorted_values = sorted(values)
    n = len(sorted_values)

    if n % 2 == 0:
        # Even number of values - average of middle two
        median = (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
    else:
        # Odd number of values - middle value
        median = sorted_values[n // 2]

    return median


def calculate_variance(values: List[float]) -> float:
    """
    Calculate variance of a list of values.

    Args:
        values: List of numeric values

    Returns:
        Variance value

    Example:
        >>> calculate_variance([2, 4, 4, 4, 5, 5, 7, 9])
        4.0
    """
    if not values or len(values) == 0:
        return 0.0

    mean = calculate_average(values, 10)  # High precision for intermediate calc
    variance = sum((x - mean) ** 2 for x in values) / len(values)

    return round(variance, 2)


def calculate_standard_deviation(values: List[float]) -> float:
    """
    Calculate standard deviation of a list of values.

    Args:
        values: List of numeric values

    Returns:
        Standard deviation

    Example:
        >>> calculate_standard_deviation([2, 4, 4, 4, 5, 5, 7, 9])
        2.0
    """
    variance = calculate_variance(values)
    std_dev = variance ** 0.5

    return round(std_dev, 2)


def calculate_percentile(
    values: List[float],
    percentile: float
) -> float:
    """
    Calculate percentile value from a list.

    Args:
        values: List of numeric values
        percentile: Percentile to calculate (0-100)

    Returns:
        Value at the given percentile

    Example:
        >>> calculate_percentile([1, 2, 3, 4, 5], 50)
        3.0  # 50th percentile (median)
    """
    if not values or len(values) == 0:
        return 0.0

    if percentile < 0 or percentile > 100:
        raise ValueError("Percentile must be between 0 and 100")

    sorted_values = sorted(values)
    index = (percentile / 100) * (len(sorted_values) - 1)

    if index.is_integer():
        return sorted_values[int(index)]
    else:
        # Interpolate between two values
        lower_index = int(index)
        upper_index = lower_index + 1
        weight = index - lower_index

        return sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight


def calculate_efficiency_score(
    actual: float,
    optimal: float,
    decimal_places: int = 2
) -> float:
    """
    Calculate efficiency score (how close to optimal).
    Returns 100 if actual equals optimal, lower if worse.

    Args:
        actual: Actual value
        optimal: Optimal value
        decimal_places: Number of decimal places

    Returns:
        Efficiency score (0-100)

    Example:
        >>> calculate_efficiency_score(90, 100)
        90.0  # 90% efficient
        >>> calculate_efficiency_score(110, 100)
        90.9  # 90.9% efficient (overspent)
    """
    if optimal == 0:
        return 100.0 if actual == 0 else 0.0

    if actual <= optimal:
        # Under or at optimal - calculate as percentage
        efficiency = (actual / optimal) * 100
    else:
        # Over optimal - penalize
        efficiency = (optimal / actual) * 100

    return round(min(efficiency, 100.0), decimal_places)


def calculate_distribution(
    values_dict: Dict[str, float]
) -> Dict[str, float]:
    """
    Calculate percentage distribution from a dictionary of values.

    Args:
        values_dict: Dictionary of category names to values

    Returns:
        Dictionary of category names to percentages

    Example:
        >>> calculate_distribution({'t3.micro': 5, 'm5.large': 10, 'c5.xlarge': 5})
        {'t3.micro': 25.0, 'm5.large': 50.0, 'c5.xlarge': 25.0}
    """
    total = sum(values_dict.values())

    if total == 0:
        return {key: 0.0 for key in values_dict.keys()}

    distribution = {
        key: round((value / total) * 100, 2)
        for key, value in values_dict.items()
    }

    return distribution


def calculate_weighted_average(
    values: List[float],
    weights: List[float],
    decimal_places: int = 2
) -> float:
    """
    Calculate weighted average.

    Args:
        values: List of values
        weights: List of weights (same length as values)
        decimal_places: Number of decimal places

    Returns:
        Weighted average

    Example:
        >>> calculate_weighted_average([10, 20, 30], [1, 2, 3])
        23.33  # (10*1 + 20*2 + 30*3) / (1+2+3)
    """
    if not values or not weights or len(values) != len(weights):
        return 0.0

    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(v * w for v, w in zip(values, weights))
    weighted_avg = weighted_sum / total_weight

    return round(weighted_avg, decimal_places)
