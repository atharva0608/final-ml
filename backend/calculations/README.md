# Calculations Module

## Overview

This module contains all calculation logic for the Spot Optimizer platform. By centralizing calculations, we:

1. **Make logic easy to test** - Pure functions with clear inputs/outputs
2. **Enable reuse** - Same calculation used across multiple services
3. **Simplify maintenance** - Change calculation in one place
4. **Document formulas** - Clear documentation of business logic

---

## Module Structure

```
backend/calculations/
├── __init__.py                    # Public API exports
├── cost_calculations.py           # Cost-related calculations
├── savings_calculations.py        # Savings calculations
├── metrics_calculations.py        # General metrics/statistics
└── README.md                      # This file
```

---

## Calculation Principles

### Current Implementation (v1.0)
**Method**: Hourly Price × Hours
- **Formula**: `monthly_cost = instance.price_per_hour × 720 hours`
- **Source**: Instance prices from AWS Pricing API or fallback table
- **Accuracy**: ~85-90% (misses data transfer, EBS IOPS, etc.)
- **Performance**: Fast, no API calls needed
- **Use Case**: Development, testing, small deployments

### Future Implementation (v2.0) - Recommended in changes.txt
**Method**: AWS Cost Explorer API
- **Formula**: Direct from AWS Cost Explorer (AmortizedCost)
- **Source**: AWS Cost Explorer API calls
- **Accuracy**: 100% (matches AWS invoice)
- **Performance**: Slower, requires API calls and caching
- **Use Case**: Production, enterprise deployments

---

## Usage Examples

### Example 1: Calculate Monthly Cost for an Instance

```python
from backend.calculations import calculate_monthly_cost

# Calculate monthly cost for a t3.micro instance
monthly_cost = calculate_monthly_cost(
    hourly_price=0.0104  # t3.micro price per hour
)
# Result: Decimal('7.488')
```

### Example 2: Calculate Total Cost for Multiple Instances

```python
from backend.calculations import calculate_total_cost
from datetime import datetime, timedelta

# Get instances from database
instances = db.query(Instance).filter(
    Instance.state == 'running'
).all()

# Calculate cost for last 7 days
start_date = datetime.utcnow() - timedelta(days=7)
end_date = datetime.utcnow()

total_cost = calculate_total_cost(instances, start_date, end_date)
# Result: Decimal('52.42')
```

### Example 3: Calculate Spot Savings

```python
from backend.calculations import calculate_spot_savings, calculate_savings_percentage

# Calculate savings from using spot instances
spot_cost = 30.0  # Actual cost for spot instances
savings = calculate_spot_savings(spot_cost, spot_discount=0.70)
# Result: Decimal('70.00')  # Saved $70 vs on-demand

# Calculate savings percentage
on_demand_equivalent = 100.0
percentage = calculate_savings_percentage(savings, on_demand_equivalent)
# Result: 70.0  # 70% savings
```

### Example 4: Calculate Cost by Lifecycle

```python
from backend.calculations import calculate_cost_by_lifecycle

# Calculate costs split by spot vs on-demand
total, spot, on_demand = calculate_cost_by_lifecycle(
    instances=all_instances,
    start_date=start_of_month,
    end_date=end_of_month
)
# Result: (Decimal('150.00'), Decimal('45.00'), Decimal('105.00'))
```

---

## Refactoring Services to Use Calculations Module

### Before (tightly coupled):

```python
# In metrics_service.py
def get_cost_metrics(self, user_id, filters):
    total_cost = Decimal('0.0')
    for instance in instances:
        hourly_cost = Decimal(str(instance.price)) if instance.price else Decimal('0.05')
        instance_start = max(instance.created_at, start_date)
        instance_end = min(datetime.utcnow(), end_date)
        hours = (instance_end - instance_start).total_seconds() / 3600
        instance_cost = hourly_cost * Decimal(str(hours))
        total_cost += instance_cost
    return total_cost
```

### After (modular):

```python
# In metrics_service.py
from backend.calculations import calculate_total_cost

def get_cost_metrics(self, user_id, filters):
    instances = self._get_instances(user_id, filters)
    total_cost = calculate_total_cost(
        instances=instances,
        start_date=filters.start_date,
        end_date=filters.end_date
    )
    return total_cost
```

**Benefits**:
- ✅ 15 lines reduced to 5 lines
- ✅ Calculation logic testable independently
- ✅ Same logic reused across multiple services
- ✅ Easy to update calculation formula in one place

---

## Testing Calculations

All calculation functions are pure (no side effects) and easy to test:

```python
# tests/test_calculations.py
from backend.calculations import calculate_monthly_cost
from decimal import Decimal

def test_monthly_cost_calculation():
    # t3.micro monthly cost
    cost = calculate_monthly_cost(0.0104)
    assert cost == Decimal('7.488')

def test_monthly_cost_with_fallback():
    # When price is None, use fallback
    cost = calculate_monthly_cost(None, fallback_price=Decimal('0.10'))
    assert cost == Decimal('72.00')  # 0.10 × 720 hours
```

---

## Migration Path: v1.0 → v2.0

To migrate to AWS Cost Explorer (as recommended in changes.txt):

### Phase 1: Hybrid Approach
- Keep current hourly calculation for real-time estimates
- Add AWS Cost Explorer worker to fetch daily costs
- Store in `daily_costs` table
- Use Cost Explorer data for historical/invoice-accurate reporting

### Phase 2: Cost Explorer Primary
- Use Cost Explorer as primary source
- Keep hourly calculation as fallback only
- Add caching layer to reduce API calls

### Implementation:
```python
# In calculations/cost_calculations.py
def calculate_cost_from_explorer(
    account_id: str,
    start_date: datetime,
    end_date: datetime,
    db: Session
) -> Decimal:
    """
    Calculate cost using AWS Cost Explorer data (cached in DB).
    Falls back to hourly calculation if Cost Explorer data not available.
    """
    # Try Cost Explorer data first
    cost_records = db.query(DailyCost).filter(
        DailyCost.account_id == account_id,
        DailyCost.date >= start_date,
        DailyCost.date <= end_date
    ).all()

    if cost_records:
        # Use accurate Cost Explorer data
        return Decimal(sum(r.cost_amount for r in cost_records))
    else:
        # Fallback to hourly estimation
        instances = db.query(Instance).filter(
            Instance.account_id == account_id,
            Instance.state == 'running'
        ).all()
        return calculate_total_cost(instances, start_date, end_date)
```

---

## Constants Reference

All calculation constants are defined in the module:

| Constant | Value | Description |
|----------|-------|-------------|
| `HOURS_PER_DAY` | 24 | Hours in a day |
| `HOURS_PER_MONTH` | 720 | Hours in a standard month (30 × 24) |
| `FALLBACK_HOURLY_PRICE` | $0.05 | Default price when actual price unknown |
| `AVERAGE_SPOT_DISCOUNT` | 0.70 | Average 70% discount for spot instances |
| `SPOT_MULTIPLIER` | 0.30 | Spot instances cost ~30% of on-demand |

To change any constant, update it in the calculation file and all calculations will use the new value.

---

## Best Practices

1. **Always use Decimal for money** - Avoid float for currency calculations
2. **Document formulas** - Include formula in docstring
3. **Provide examples** - Show expected input/output in docstring
4. **Keep functions pure** - No database queries in calculation functions
5. **Test edge cases** - Test with zero, negative, None values

---

## Support

For questions or issues with calculations:
1. Check the docstring in the function
2. Review the examples in this README
3. Run the unit tests to understand behavior
4. Consult changes.txt for future roadmap
