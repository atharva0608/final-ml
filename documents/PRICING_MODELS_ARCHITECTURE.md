# Three Pricing Models Architecture

## Overview

The Spot Optimizer platform implements **three distinct pricing models** to provide comprehensive cost visibility and optimization opportunities. Each model serves a specific purpose and is used in different parts of the application.

---

## Model A: Actual Cost (AWS Cost Explorer)

### What It Is
Invoice-accurate cost directly from AWS Cost Explorer API - **what AWS actually charged**.

### Data Source
- **Primary**: AWS Cost Explorer API
- **Fallback**: EC2 instance pricing (when Cost Explorer unavailable)

### Characteristics
- 100% accurate - matches AWS invoice exactly
- Includes ALL AWS services (EC2, S3, RDS, VPC, Security Hub, KMS, etc.)
- Includes amortized costs (Savings Plans, Reserved Instances, EDPs)
- Updated daily via Celery worker (`cost_explorer_worker.py`)
- Stored in `daily_costs` table

### Refresh Schedule
- **Worker**: `sync_cost_explorer` task
- **Frequency**: Every 24 hours
- **Data Range**: Current month (MTD projected to full month)

### Use Cases
1. **Dashboard Overview** (`/api/v1/dashboard/overview`)
   - `actual_cost` field
   - Shows monthly projection: `(MTD / days_elapsed) × 30`

2. **Total Discovered Cost Header**
   - Resource Hygiene page header
   - Endpoint: `/api/v1/hygiene/total-cost`

3. **Cost Breakdown** (`/api/v1/dashboard/cost-breakdown`)
   - Groups by category: compute, storage, network, security, management, others

4. **Sidebar Cost Services** (`/api/v1/hygiene/cost-services`)
   - Shows actual AWS spend by service category

### Example Response
```json
{
  "actual_cost": 54.44,
  "source": "cost_explorer",
  "period": "monthly_projection"
}
```

---

## Model B: Resources Cost (Sum of Individual Resources @ 24/7)

### What It Is
Sum of each individual resource's cost assuming **24/7 uptime** for 30 days (720 hours).

### Data Source
- **Instances**: `hourly_rate × 720 hours`
- **Volumes**: `GB × $0.10/GB-month` (gp3)
- **Snapshots**: `GB × $0.05/GB-month`
- **Elastic IPs**: `$3.60/mo` if unattached, `$0` if attached
- **Load Balancers**: `$16.20/mo` (ALB base)
- **NAT Gateways**: `$32.40/mo` (base)
- **RDS**: `hourly_rate × 720 hours`

### Characteristics
- Resource-level granularity
- Assumes constant uptime (no usage patterns)
- Cached in Redis with 24-hour TTL
- Independent of actual AWS billing
- Useful for resource inventory cost estimation

### Refresh Schedule
- **Worker**: `refresh_all_resource_prices` task
- **Frequency**: Every 24 hours
- **Cache**: Redis with 24-hour TTL
- **Key Pattern**: `resource_price:{resource_type}:{resource_id}`

### Implementation
1. **Service**: `ResourcePricingService` (`backend/services/resource_pricing_service.py`)
   - Methods for calculating each resource type
   - Fallback pricing tables for all common instance types

2. **Worker**: `resource_pricing_worker.py`
   - Scans all accounts and resources
   - Calculates monthly cost for each
   - Stores in Redis cache

3. **Cache Structure**:
```json
{
  "cost": 7.49,
  "currency": "USD",
  "updated_at": "2026-02-12T10:00:00Z",
  "metadata": {
    "account_id": "abc-123",
    "region": "us-east-1",
    "name": "my-instance"
  }
}
```

### Use Cases
1. **Resource Hygiene Tables**
   - Cost/Mo column in all resource tables
   - Shows individual resource cost

2. **Dashboard Overview** (`/api/v1/dashboard/overview`)
   - `resources_cost` field
   - Sum of all cached resource costs

3. **Sidebar Category Totals**
   - Groups resources by type and sums costs

### Example Response
```json
{
  "resources_cost": 23.62,
  "breakdown": {
    "instances": 15.00,
    "volumes": 5.00,
    "snapshots": 2.50,
    "load_balancers": 1.12
  }
}
```

---

## Model C: Optimization Cost (Potential Savings)

### What It Is
Cost that can be **eliminated or optimized** through hygiene improvements and rightsizing.

### Data Source
- **Hygiene Waste**: Orphaned/unauthorized resources
- **Optimization Opportunities**: Stopped instances, idle resources, rightsizing

### Characteristics
- Forward-looking (potential, not actual)
- Identifies actionable savings
- Updated on-demand when user clicks Refresh
- Combines hygiene analysis + optimization recommendations

### Components

#### A. Hygiene Waste
Resources that are orphaned or no longer needed:
- Unattached EBS volumes (>30 days)
- Old snapshots (>90 days)
- Unattached Elastic IPs
- Stopped instances (>30 days)
- Idle load balancers (no traffic)
- Idle RDS instances (no connections)

#### B. Optimization Opportunities
Resources that can be optimized:
- Stopped instances still paying for EBS
- Oversized instances (CPU < 20%)
- Underutilized databases (low connections)
- Single-AZ RDS that could be optimized
- Unoptimized S3 lifecycle policies
- RI/Savings Plan recommendations

### Refresh Schedule
- **On-Demand**: User clicks Refresh button
- **Cached**: 1-hour TTL in Redis
- **Force Refresh**: Bypasses cache

### Implementation
1. **Hygiene Scan** (`HygieneService.scan_resources()`)
   - Scans all resources across regions
   - Marks unauthorized resources
   - Calculates cost for each orphaned resource

2. **Cost Calculation**:
```python
# Hygiene waste from cached scans
for resource in scan_result.resources:
    if not resource.is_authorized:
        hygiene_waste += resource.cost_per_month

# Optimization opportunities
stopped_instances = query_stopped_instances()
optimization_waste = len(stopped_instances) * avg_ebs_cost
```

### Use Cases
1. **Resource Hygiene Page**
   - "POTENTIAL SAVINGS" card
   - Shows sum of A + B

2. **Dashboard Overview** (`/api/v1/dashboard/overview`)
   - `optimization_cost` field

3. **Savings Projection** (`/api/v1/dashboard/savings-projection`)
   - Breaks down hygiene waste vs optimization opportunities
   - Shows optimized spend after savings

### Example Response
```json
{
  "current_spend": 54.44,
  "optimized_spend": 37.14,
  "potential_savings": 17.30,
  "breakdown": {
    "hygiene_waste": 8.50,
    "optimization_opportunities": 8.80
  }
}
```

---

## API Endpoints Summary

### Model A: Actual Cost (Cost Explorer)
| Endpoint | Description |
|----------|-------------|
| `/api/v1/dashboard/overview` | `actual_cost` field |
| `/api/v1/dashboard/cost-breakdown` | By category |
| `/api/v1/hygiene/total-cost` | Total discovered cost |
| `/api/v1/hygiene/cost-services` | By service |

### Model B: Resources Cost (Individual @ 24/7)
| Endpoint | Description |
|----------|-------------|
| `/api/v1/dashboard/overview` | `resources_cost` field |
| `/api/v1/hygiene/scan/{account_id}` | Cost/Mo in resource tables |

### Model C: Optimization Cost (Potential Savings)
| Endpoint | Description |
|----------|-------------|
| `/api/v1/dashboard/overview` | `optimization_cost` field |
| `/api/v1/dashboard/savings-projection` | Detailed breakdown |
| `/api/v1/metrics/waste-breakdown` | A+B breakdown |

---

## Data Flow

### Model A: Cost Explorer Flow
```
AWS Cost Explorer API
    ↓
cost_explorer_worker.py (daily)
    ↓
daily_costs table (PostgreSQL)
    ↓
metrics_service.py queries
    ↓
API response (projected monthly)
```

### Model B: Resources Cost Flow
```
AWS Resources (EC2, EBS, RDS, etc.)
    ↓
resource_pricing_worker.py (daily)
    ↓
Resource cost calculation
    ↓
Redis cache (24-hour TTL)
    ↓
hygiene_service.py reads cache
    ↓
Cost/Mo column in tables
```

### Model C: Optimization Cost Flow
```
User clicks Refresh
    ↓
hygiene_service.scan_resources()
    ↓
Analyze unauthorized resources
    ↓
Calculate optimization opportunities
    ↓
Redis cache (1-hour TTL)
    ↓
Potential Savings card
```

---

## Cache Strategy

### Redis Cache Keys
```
# Model A (Cost Explorer)
- Key: `hygiene:total_cost:{org_id}:{account_id}`
- TTL: 24 hours

# Model B (Resources Cost)
- Key: `resource_price:{resource_type}:{resource_id}`
- TTL: 24 hours

# Model C (Hygiene Scan)
- Key: `cleanup:scan:{account_id}:{regions}`
- TTL: 1 hour
```

### Cache Invalidation
- **Cost Explorer**: Refreshed daily by worker
- **Resource Pricing**: Refreshed daily by worker
- **Hygiene Scan**: User-triggered refresh or 1-hour expiry

---

## Celery Workers

### Cost Explorer Worker
```python
@app.task(name='workers.cost.sync_cost_explorer')
# Schedule: Every 24 hours
# Purpose: Fetch actual costs from AWS Cost Explorer
```

### Resource Pricing Worker
```python
@app.task(name='workers.pricing.refresh_all_resource_prices')
# Schedule: Every 24 hours
# Purpose: Update individual resource costs in Redis
```

---

## Key Files

### Services
- `backend/services/resource_cost_service.py` - Model A (Cost Explorer)
- `backend/services/resource_pricing_service.py` - Model B (Resources Cost)
- `backend/services/hygiene_service.py` - Model C (Optimization Cost)
- `backend/services/metrics_service.py` - Aggregates all models

### Workers
- `backend/workers/tasks/cost_explorer.py` - Model A worker
- `backend/workers/tasks/resource_pricing_worker.py` - Model B worker

### API Routes
- `backend/api/dashboard_routes.py` - Dashboard endpoints (all models)
- `backend/api/hygiene_routes.py` - Resource hygiene endpoints
- `backend/api/metrics_routes.py` - Metrics endpoints

### Schemas
- `backend/schemas/dashboard_schemas.py` - Dashboard response models

---

## Frontend Integration

### Dashboard Overview Component
```typescript
// Fetch all three pricing models
const response = await fetch('/api/v1/dashboard/overview');
const data = await response.json();

// data.actual_cost → MODEL A (Cost Explorer)
// data.resources_cost → MODEL B (Resources @ 24/7)
// data.optimization_cost → MODEL C (Potential Savings)
```

### Resource Hygiene Table
```typescript
// Each row has cost_per_month from MODEL B
const resources = await fetch('/api/v1/hygiene/scan/abc-123');

resources.forEach(resource => {
  // resource.cost_per_month from Redis cache
  console.log(`${resource.name}: $${resource.cost_per_month}/mo`);
});
```

### Potential Savings Card
```typescript
// Get detailed breakdown of MODEL C
const savings = await fetch('/api/v1/dashboard/savings-projection');

// savings.potential_savings = hygiene_waste + optimization_opportunities
// savings.current_spend = MODEL A (actual)
// savings.optimized_spend = actual - potential_savings
```

---

## Pricing Accuracy

### Model A: Actual Cost
- **Accuracy**: 100% (matches AWS invoice)
- **Coverage**: All AWS services
- **Latency**: 24-hour delay (Cost Explorer data)

### Model B: Resources Cost
- **Accuracy**: ~90% (static pricing + API queries)
- **Coverage**: Individual resources only
- **Latency**: Real-time (cached)

### Model C: Optimization Cost
- **Accuracy**: Estimated (based on patterns)
- **Coverage**: Identifiable waste + opportunities
- **Latency**: Real-time (on-demand)

---

## Best Practices

1. **Use Model A for Billing**
   - Always show actual AWS costs in financial reports
   - Model A is the source of truth for invoice reconciliation

2. **Use Model B for Inventory**
   - Show per-resource costs in tables and lists
   - Helps users understand individual resource impact

3. **Use Model C for Optimization**
   - Highlight savings opportunities
   - Drive user action to reduce waste

4. **Cache Aggressively**
   - Cost Explorer queries are expensive (AWS quota)
   - Resource pricing calculations are CPU-intensive
   - Cache all results with appropriate TTLs

5. **Fallback Gracefully**
   - Always have fallback pricing when APIs fail
   - Maintain comprehensive static pricing tables
   - Show data source in UI ("estimated" vs "actual")

---

## Monitoring

### Key Metrics
- Cost Explorer sync success rate
- Resource pricing worker completion time
- Cache hit rates for each model
- API response times

### Alerts
- Cost Explorer sync failures
- Redis cache unavailability
- Large discrepancies between models
- Missing resource prices in cache

---

## Future Enhancements

1. **Real-Time Cost Tracking**
   - Stream cost data instead of daily batch
   - Sub-hourly cost updates

2. **Advanced Optimization**
   - Machine learning for rightsizing recommendations
   - Predictive cost forecasting
   - Automated optimization execution

3. **Multi-Cloud Support**
   - Extend pricing models to Azure, GCP
   - Unified cost dashboard

4. **Cost Allocation**
   - Team-based cost attribution
   - Project/environment tagging
   - Chargeback reports

---

## Conclusion

The three pricing models work together to provide:
- **Accuracy**: Model A ensures billing accuracy
- **Granularity**: Model B enables resource-level analysis
- **Actionability**: Model C drives cost optimization

By separating these concerns, we maintain system flexibility and allow each model to be optimized independently.
