# Refactoring Guide: Using the Calculations Module

## Overview

This guide shows how to refactor existing services to use the new modular calculations module.

---

## Benefits of Refactoring

✅ **Reduced Code Duplication** - Calculation logic in one place
✅ **Easier Testing** - Test calculations independently
✅ **Maintainability** - Update formula once, applies everywhere
✅ **Consistency** - Same formula used across all services
✅ **Documentation** - Clear docstrings explain each calculation

---

## Refactoring metrics_service.py

### Step 1: Import Calculation Functions

**Add to top of metrics_service.py:**

```python
from backend.calculations import (
    calculate_total_cost,
    calculate_monthly_cost,
    calculate_cost_by_lifecycle,
    calculate_spot_savings,
    calculate_savings_percentage,
    calculate_percentage
)
```

### Step 2: Refactor _calculate_cost_metrics Method

**Before:**

```python
def _calculate_cost_metrics(
    self,
    user_id: str,
    start_date: datetime,
    end_date: datetime,
    cluster_id: Optional[str] = None,
    team_id: Optional[str] = None
) -> CostMetrics:
    user = self.db.query(User).filter(User.id == user_id).first()
    if not user or not user.organization_id:
        return CostMetrics(total_cost=Decimal('0.0'), spot_cost=Decimal('0.0'), on_demand_cost=Decimal('0.0'), currency="USD")

    instance_query = self.db.query(Instance).join(Account).filter(
        Account.organization_id == user.organization_id
    )

    if cluster_id:
        instance_query = instance_query.filter(Instance.cluster_id == cluster_id)

    active_instances = instance_query.filter(
        Instance.state.in_(['running', 'pending'])
    ).all()

    # Calculate costs
    total_cost = Decimal('0.0')
    spot_cost = Decimal('0.0')
    on_demand_cost = Decimal('0.0')

    for instance in active_instances:
        hourly_cost = Decimal(str(instance.price)) if instance.price else Decimal('0.05')
        instance_start = max(instance.created_at, start_date) if instance.created_at else start_date
        instance_end = min(datetime.utcnow(), end_date)
        hours = (instance_end - instance_start).total_seconds() / 3600
        instance_cost = hourly_cost * Decimal(str(hours))
        total_cost += instance_cost

        if instance.lifecycle == InstanceLifecycle.SPOT:
            spot_cost += instance_cost
        else:
            on_demand_cost += instance_cost

    return CostMetrics(
        total_cost=total_cost,
        spot_cost=spot_cost,
        on_demand_cost=on_demand_cost,
        currency="USD"
    )
```

**After:**

```python
def _calculate_cost_metrics(
    self,
    user_id: str,
    start_date: datetime,
    end_date: datetime,
    cluster_id: Optional[str] = None,
    team_id: Optional[str] = None
) -> CostMetrics:
    # Get user and validate
    user = self.db.query(User).filter(User.id == user_id).first()
    if not user or not user.organization_id:
        return CostMetrics(
            total_cost=Decimal('0.0'),
            spot_cost=Decimal('0.0'),
            on_demand_cost=Decimal('0.0'),
            currency="USD"
        )

    # Get instances
    instance_query = self.db.query(Instance).join(Account).filter(
        Account.organization_id == user.organization_id
    )

    if cluster_id:
        instance_query = instance_query.filter(Instance.cluster_id == cluster_id)

    active_instances = instance_query.filter(
        Instance.state.in_(['running', 'pending'])
    ).all()

    # Calculate costs using modular functions
    total_cost, spot_cost, on_demand_cost = calculate_cost_by_lifecycle(
        instances=active_instances,
        start_date=start_date,
        end_date=end_date
    )

    return CostMetrics(
        total_cost=total_cost,
        spot_cost=spot_cost,
        on_demand_cost=on_demand_cost,
        currency="USD"
    )
```

**Improvements:**
- ✅ Reduced from 30 lines to 20 lines
- ✅ Calculation logic extracted to testable function
- ✅ Same calculation can be reused elsewhere

---

### Step 3: Refactor _calculate_savings Method

**Before:**

```python
def _calculate_savings(
    self,
    user_id: str,
    start_date: datetime,
    end_date: datetime,
    cluster_id: Optional[str] = None,
    team_id: Optional[str] = None
) -> SavingsBreakdown:
    cost_metrics = self._calculate_cost_metrics(
        user_id, start_date, end_date, cluster_id, team_id
    )

    # Calculate what it would cost if all were on-demand
    # Assume 70% average spot discount
    spot_cost_float = float(cost_metrics.spot_cost)
    on_demand_float = float(cost_metrics.on_demand_cost)
    total_cost_float = float(cost_metrics.total_cost)

    spot_equivalent_on_demand = spot_cost_float / 0.3 if spot_cost_float > 0 else 0.0
    total_if_on_demand = on_demand_float + spot_equivalent_on_demand

    # Calculate savings
    total_savings = total_if_on_demand - total_cost_float

    # Calculate percentage
    if total_if_on_demand > 0:
        savings_percentage = (total_savings / total_if_on_demand) * 100
    else:
        savings_percentage = 0.0

    return SavingsBreakdown(
        total_savings=total_savings,
        spot_savings=total_savings,
        hibernation_savings=0.0,
        savings_percentage=savings_percentage
    )
```

**After:**

```python
def _calculate_savings(
    self,
    user_id: str,
    start_date: datetime,
    end_date: datetime,
    cluster_id: Optional[str] = None,
    team_id: Optional[str] = None
) -> SavingsBreakdown:
    # Get cost metrics
    cost_metrics = self._calculate_cost_metrics(
        user_id, start_date, end_date, cluster_id, team_id
    )

    # Calculate spot savings using modular function
    spot_cost_float = float(cost_metrics.spot_cost)
    on_demand_float = float(cost_metrics.on_demand_cost)

    spot_savings = calculate_spot_savings(
        spot_cost=spot_cost_float,
        spot_discount=0.70
    )

    # Calculate total if on-demand (for percentage calculation)
    spot_equivalent_on_demand = spot_cost_float / 0.3 if spot_cost_float > 0 else 0.0
    total_if_on_demand = on_demand_float + spot_equivalent_on_demand

    # Calculate savings percentage
    savings_pct = calculate_savings_percentage(
        savings_amount=float(spot_savings),
        total_cost_without_optimization=total_if_on_demand
    )

    return SavingsBreakdown(
        total_savings=float(spot_savings),
        spot_savings=float(spot_savings),
        hibernation_savings=0.0,  # TODO: Calculate from hibernation
        savings_percentage=savings_pct
    )
```

**Improvements:**
- ✅ Calculation formulas documented in separate module
- ✅ Easy to test savings calculation independently
- ✅ Formula changes in one place affect all usages

---

### Step 4: Refactor Team/Account Cost Calculations

**Before (in get_team_stats):**

```python
# Lines 601-616 in metrics_service.py
total_cost = 0.0
hours_in_month = 720
if account_ids:
    instances = self.db.query(Instance).filter(
        Instance.account_id.in_(account_ids),
        Instance.state.in_(['running', 'pending'])
    ).all()
    for instance in instances:
        hourly_price = instance.price or Decimal('0.05')
        monthly_cost = float(hourly_price) * hours_in_month
        total_cost += monthly_cost
```

**After:**

```python
from backend.calculations import calculate_account_cost

# Get instances
if account_ids:
    instances = self.db.query(Instance).filter(
        Instance.account_id.in_(account_ids),
        Instance.state.in_(['running', 'pending'])
    ).all()

    # Calculate using modular function
    total_cost = float(calculate_account_cost(instances))
```

**Improvements:**
- ✅ Reduced from 10 lines to 5 lines
- ✅ HOURS_PER_MONTH constant managed in one place
- ✅ Same logic used for all account cost calculations

---

## Refactoring Other Services

### Example: cluster_service.py

**Before:**

```python
def update_cluster_costs(cluster_id: str, db: Session):
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    instances = db.query(Instance).filter(Instance.cluster_id == cluster_id).all()

    total = 0.0
    for instance in instances:
        price = instance.price or 0.05
        total += price * 720

    cluster.monthly_cost = total
    db.commit()
```

**After:**

```python
from backend.calculations import calculate_cluster_cost

def update_cluster_costs(cluster_id: str, db: Session):
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    instances = db.query(Instance).filter(Instance.cluster_id == cluster_id).all()

    # Calculate using modular function
    cluster.monthly_cost = float(calculate_cluster_cost(instances))
    db.commit()
```

---

## Testing After Refactoring

### Before Refactoring:
- ❌ Must test entire service method
- ❌ Need database setup for testing
- ❌ Difficult to test edge cases

### After Refactoring:
- ✅ Test calculation independently
- ✅ No database needed
- ✅ Easy to test edge cases

**Example Test:**

```python
# tests/calculations/test_cost_calculations.py
from backend.calculations import calculate_monthly_cost
from decimal import Decimal

def test_t3_micro_monthly_cost():
    """Test monthly cost for t3.micro instance"""
    cost = calculate_monthly_cost(0.0104)
    assert cost == Decimal('7.488')

def test_monthly_cost_with_none_price():
    """Test fallback when price is None"""
    cost = calculate_monthly_cost(None)
    assert cost == Decimal('36.00')  # 0.05 × 720

def test_monthly_cost_with_custom_fallback():
    """Test custom fallback price"""
    cost = calculate_monthly_cost(None, fallback_price=Decimal('0.10'))
    assert cost == Decimal('72.00')  # 0.10 × 720
```

---

## Migration Checklist

Use this checklist to refactor each service:

### Metrics Service
- [x] Import calculation functions
- [x] Refactor `_calculate_cost_metrics`
- [x] Refactor `_calculate_savings`
- [x] Refactor `_calculate_daily_cost`
- [ ] Refactor team stats cost calculation
- [ ] Refactor account stats cost calculation
- [ ] Add unit tests for calculations

### Cluster Service
- [ ] Refactor `update_cluster_costs`
- [ ] Refactor cluster cost aggregation
- [ ] Add unit tests

### Workers
- [ ] Refactor `cost_calculator.py` worker
- [ ] Refactor `discovery.py` pricing logic
- [ ] Add unit tests

### API Routes
- [ ] Update billing routes to use calculations
- [ ] Update dashboard routes
- [ ] Verify all endpoints return consistent data

---

## Common Patterns

### Pattern 1: Single Instance Cost
```python
from backend.calculations import calculate_monthly_cost

monthly_cost = calculate_monthly_cost(instance.price)
```

### Pattern 2: Multiple Instances Total Cost
```python
from backend.calculations import calculate_total_cost

total = calculate_total_cost(instances, start_date, end_date)
```

### Pattern 3: Cost by Lifecycle Split
```python
from backend.calculations import calculate_cost_by_lifecycle

total, spot, on_demand = calculate_cost_by_lifecycle(instances, start, end)
```

### Pattern 4: Savings Calculation
```python
from backend.calculations import calculate_spot_savings, calculate_savings_percentage

savings = calculate_spot_savings(spot_cost, 0.70)
percentage = calculate_savings_percentage(savings, total_if_on_demand)
```

---

## Verification

After refactoring, verify:

1. **Run Tests**: `pytest tests/calculations/`
2. **Check Dashboard**: Monthly spend should still show $7.49
3. **Check API**: `/api/v1/metrics/dashboard` returns same data
4. **Check Logs**: No calculation errors in backend logs

---

## Next Steps

1. **Complete Current Refactoring**: Finish refactoring metrics_service.py
2. **Add Unit Tests**: Write tests for all calculation functions
3. **Refactor Other Services**: Apply same pattern to cluster_service, workers
4. **Document Changes**: Update API docs with new calculation logic
5. **Future**: Implement AWS Cost Explorer integration (see changes.txt)

---

## Support

If you encounter issues during refactoring:
1. Check the calculation function docstring
2. Review examples in `/backend/calculations/README.md`
3. Run unit tests to verify behavior
4. Check that imports are correct
