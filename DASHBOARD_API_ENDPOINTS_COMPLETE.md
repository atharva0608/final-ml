# Dashboard API Endpoints - Complete Mapping

## Overview

All dashboard components have been verified and connected to their proper API endpoints. This document maps each dashboard component to its backend endpoint and data flow.

---

## ✅ **Top KPI Cards** (Always Visible)

### **1. Monthly Spend**
- **Component**: `CostKPICard.jsx`
- **API Endpoint**: `/api/v1/metrics/dashboard`
- **Response Field**: `dashboardKPIs.total_cost`
- **Hook**: `useDashboard()` → `metricsAPI.getDashboard()`
- **Status**: ✅ **Connected**
- **Data Flow**:
  ```
  useDashboard Hook
  → metricsAPI.getDashboard()
  → GET /api/v1/metrics/dashboard
  → MetricsService.get_dashboard_kpis()
  → Calculates from instances.price × 720 hours
  → Returns: { total_cost: 7.49, ... }
  ```

### **2. Net Savings**
- **Component**: `SavingsKPICard.jsx`
- **API Endpoint**: `/api/v1/metrics/dashboard`
- **Response Field**: `dashboardKPIs.estimated_savings`
- **Hook**: `useDashboard()` → `metricsAPI.getDashboard()`
- **Status**: ✅ **Connected**
- **Data Flow**:
  ```
  useDashboard Hook
  → metricsAPI.getDashboard()
  → GET /api/v1/metrics/dashboard
  → MetricsService.get_dashboard_kpis()
  → Calculates spot vs on-demand price difference
  → Returns: { estimated_savings: 0.00, ... }
  ```

---

## ✅ **Health Cards** (Optimization Widgets)

### **3. RI Health (Reserved Instances)**
- **Component**: `RIHealthCard.jsx`
- **API Endpoint**: `/api/v1/ri/overview`
- **Direct API Call**: Uses `api.get()` directly in component
- **Status**: ✅ **Connected**
- **Expected Response**:
  ```json
  {
    "total_ris": 0,
    "underutilized_count": 0,
    "underutilized_percentage": 0,
    "wasted_spend_monthly": 0,
    "wasted_spend_annual": 0,
    "health_status": "healthy",
    "top_opportunities": []
  }
  ```
- **Empty State**: "No Reserved Instances found. Connect AWS accounts to analyze RI utilization."
- **Data Source**: `ri_utilization` table populated by RI discovery worker

### **4. S3 Health**
- **Component**: `S3HealthCard.jsx`
- **API Endpoint**: `/api/v1/s3/overview`
- **Direct API Call**: Uses `api.get()` directly
- **Status**: ✅ **Connected**
- **Expected Response**:
  ```json
  {
    "total_buckets": 0,
    "total_size_gb": 0,
    "total_cost_monthly": 0,
    "savings_opportunities": 0,
    "potential_savings": 0,
    "top_recommendations": []
  }
  ```
- **Empty State**: "No S3 buckets analyzed. Connect AWS accounts to detect savings."
- **Data Source**: `s3_bucket_analysis` table populated by S3 discovery worker

### **5. RDS Health**
- **Component**: `RDSHealthCard.jsx`
- **API Endpoint**: `/api/v1/rds/overview`
- **Direct API Call**: Uses `api.get()` directly
- **Status**: ✅ **Connected**
- **Expected Response**:
  ```json
  {
    "total_instances": 0,
    "idle_instances": 0,
    "oversized_instances": 0,
    "total_monthly_cost": 0,
    "potential_savings": 0,
    "top_recommendations": []
  }
  ```
- **Empty State**: "No RDS instances found. Connect AWS accounts to detect savings."
- **Data Source**: `rds_instance_analysis` table populated by RDS discovery worker

### **6. Data Transfer**
- **Component**: `TransferHealthCard.jsx`
- **API Endpoint**: `/api/v1/transfer/overview`
- **Direct API Call**: Uses `api.get()` directly
- **Status**: ✅ **Connected**
- **Expected Response**:
  ```json
  {
    "total_transfer_gb": 0,
    "total_cost_monthly": 0,
    "cross_region_cost": 0,
    "internet_cost": 0,
    "optimization_opportunities": []
  }
  ```
- **Empty State**: "No significant transfer costs detected yet."
- **Data Source**: `data_transfer_analysis` table populated by transfer cost worker

---

## ✅ **Visualization Widgets**

### **7. Savings Projection**
- **Component**: `SavingsChart.jsx`
- **API Endpoint**: `/api/v1/metrics/cost/timeseries`
- **Response Field**: `costTimeSeries`
- **Hook**: `useDashboard()` → `metricsAPI.getCostTimeSeries()`
- **Status**: ✅ **Fixed** (removed hardcoded data)
- **Data Flow**:
  ```
  useDashboard Hook
  → metricsAPI.getCostTimeSeries()
  → GET /api/v1/metrics/cost/timeseries
  → MetricsService.get_cost_time_series()
  → Calculates historical cost data
  → Returns: [{ date: '2026-01-01', cost: 7.49 }, ...]
  ```
- **Empty State**: "No cost data available yet"
- **Chart Type**: Bar chart with "Without Optimization" vs "With Optimization"

### **8. Fleet Composition**
- **Component**: `FleetComposition.jsx`
- **API Endpoint**: `/api/v1/metrics/instances`
- **Response Field**: `type_distribution`
- **Direct API Call**: Uses `fetch()` with `access_token`
- **Status**: ✅ **Fixed** (corrected token key from `token` to `access_token`)
- **Data Flow**:
  ```
  FleetComposition Component
  → fetch('/api/v1/metrics/instances')
  → GET /api/v1/metrics/instances
  → MetricsService.get_instance_metrics()
  → Queries instances by type, groups by instance_type
  → Returns: { type_distribution: { "t3.micro": 1, "m5.large": 5 } }
  → Component transforms to: [{ name: "t3.micro", value: 1 }, ...]
  ```
- **Expected Response**:
  ```json
  {
    "total_instances": 1,
    "running_instances": 1,
    "type_distribution": {
      "t3.micro": 1
    }
  }
  ```
- **Empty State**: "No instances found"
- **Chart Type**: Donut pie chart showing instance type percentages

### **9. Activity Feed**
- **Component**: `ActivityFeed.jsx`
- **API Endpoint**: `/api/v1/audit/logs`
- **Response Field**: `activities`
- **Fetch**: Dashboard component calls `auditAPI.list({ limit: 5 })`
- **Status**: ✅ **Fixed** (removed hardcoded activities)
- **Data Flow**:
  ```
  Dashboard.jsx (useEffect)
  → auditAPI.list({ limit: 5 })
  → GET /api/v1/audit/logs?limit=5
  → AuditService.list_logs()
  → Returns: { logs: [{ event_name, resource_id, status, created_at }, ...] }
  → Transformed to: [{ action, resource, status, time }, ...]
  ```
- **Expected Response**:
  ```json
  {
    "logs": [
      {
        "id": "uuid",
        "event_name": "instance.created",
        "resource_id": "i-0e4ec4b774d92f6ea",
        "status": "success",
        "created_at": "2026-02-12T12:00:00Z"
      }
    ]
  }
  ```
- **Empty State**: "No recent activity"
- **Display**: List of recent actions with icons and timestamps

### **10. Cluster Health**
- **Component**: `ClusterHealthCard.jsx`
- **API Endpoint**: `/api/v1/clusters`
- **Response Field**: `clusters`
- **Fetch**: Dashboard component calls `clusterAPI.listClusters()`
- **Status**: ✅ **Fixed** (removed hardcoded clusters)
- **Data Flow**:
  ```
  Dashboard.jsx (useEffect)
  → clusterAPI.listClusters()
  → GET /api/v1/clusters
  → ClusterService.list_clusters()
  → Returns: { clusters: [{ name, status, node_count }, ...] }
  ```
- **Expected Response**:
  ```json
  {
    "clusters": [
      {
        "id": "uuid",
        "name": "prod-cluster",
        "status": "ACTIVE",
        "node_count": 12,
        "monthly_cost": 150.00
      }
    ]
  }
  ```
- **Empty State**: "No clusters found"
- **Display**: List of clusters with status indicators and node counts

---

## Backend Routes Summary

### **Metrics Routes** (`/api/v1/metrics/...`)

| Endpoint | Method | Purpose | Response Model |
|----------|--------|---------|----------------|
| `/dashboard` | GET | Dashboard KPIs | `DashboardKPIs` |
| `/cost` | GET | Cost breakdown | `CostMetrics` |
| `/instances` | GET | Instance metrics | `InstanceMetrics` |
| `/cost/timeseries` | GET | Historical cost data | `TimeSeriesData` |
| `/cluster/{id}` | GET | Cluster-specific metrics | `ClusterMetrics` |
| `/teams/{id}/summary` | GET | Team cost summary | `TeamSummary` |
| `/accounts/{id}/summary` | GET | Account cost summary | `AccountSummary` |

### **Health Routes** (`/api/v1/.../overview`)

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/ri/overview` | GET | RI utilization summary | RI health data |
| `/s3/overview` | GET | S3 bucket analysis | S3 health data |
| `/rds/overview` | GET | RDS instance analysis | RDS health data |
| `/transfer/overview` | GET | Data transfer costs | Transfer health data |

### **Other Routes**

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/clusters` | GET | List all clusters | `ClusterList` |
| `/audit/logs` | GET | Audit log entries | `AuditLogList` |
| `/accounts` | GET | List AWS accounts | `AccountList` |

---

## Data Flow Architecture

### **User Loads Dashboard**
```
1. Browser loads Dashboard.jsx
2. useDashboard() hook fires (useEffect)
3. Parallel API calls:
   ├─ GET /api/v1/metrics/dashboard     → Monthly Spend, Net Savings
   ├─ GET /api/v1/metrics/cost          → Cost breakdown
   ├─ GET /api/v1/metrics/instances     → Fleet Composition data
   └─ GET /api/v1/metrics/cost/timeseries → Savings Projection data

4. Dashboard component additional calls:
   ├─ GET /api/v1/audit/logs?limit=5    → Activity Feed
   └─ GET /api/v1/clusters               → Cluster Health

5. Health cards load independently:
   ├─ GET /api/v1/ri/overview           → RI Health
   ├─ GET /api/v1/s3/overview           → S3 Health
   ├─ GET /api/v1/rds/overview          → RDS Health
   └─ GET /api/v1/transfer/overview     → Data Transfer

6. FleetComposition widget loads independently:
   └─ GET /api/v1/metrics/instances     → Instance type distribution
```

### **Backend Data Sources**
```
Dashboard KPIs
├─ Queries: instances, clusters, accounts
├─ Calculates: total_cost, estimated_savings, optimization_rate
└─ Returns: Real-time aggregated metrics

Fleet Composition
├─ Queries: instances.instance_type
├─ Groups by: instance_type
└─ Returns: { "t3.micro": 1, "m5.large": 5, ... }

Activity Feed
├─ Queries: audit_logs
├─ Filters: latest 5 entries
└─ Returns: [ { event_name, resource_id, status, timestamp } ]

Cluster Health
├─ Queries: clusters
├─ Filters: user's organization
└─ Returns: [ { name, status, node_count, monthly_cost } ]

Health Cards
├─ RI Health: Queries ri_utilization table
├─ S3 Health: Queries s3_bucket_analysis table
├─ RDS Health: Queries rds_instance_analysis table
└─ Transfer: Queries data_transfer_analysis table
```

---

## Current Database State

**After all fixes:**
```sql
-- Database has real data
SELECT
  (SELECT COUNT(*) FROM accounts) as accounts,              -- 1
  (SELECT COUNT(*) FROM clusters) as clusters,              -- 0
  (SELECT COUNT(*) FROM instances) as instances,            -- 1 (t3.micro)
  (SELECT COUNT(*) FROM instances WHERE account_id IS NOT NULL) as with_account_id;  -- 1

-- Instance is standalone with direct account link
SELECT instance_id, account_id, cluster_id, price, (price * 720) as monthly_cost
FROM instances;
-- Result: i-0e4ec4b774d92f6ea | 52aae359... | NULL | 0.0104 | $7.49
```

---

## What User Should See

### **After Hard Refresh (Cmd+Shift+R):**

1. **Monthly Spend**: **$7.49** ✓
2. **Net Savings**: **$0.00** ✓ (no spot instances)
3. **RI Health**: "No Reserved Instances found..." ✓
4. **S3 Health**: "No S3 buckets analyzed..." ✓
5. **RDS Health**: "No RDS instances found..." ✓
6. **Data Transfer**: "No significant transfer costs..." ✓
7. **Savings Projection**: Empty state ✓ (no historical data)
8. **Fleet Composition**: **t3.micro (100%)** ✓
9. **Activity Feed**: Empty state or real audit logs ✓
10. **Cluster Health**: Empty state ✓ (no clusters)

---

## Verification Commands

### **1. Check Backend Health**
```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy"}
```

### **2. Check Dashboard KPIs**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/metrics/dashboard
# Expected: {"total_cost": 7.49, ...}
```

### **3. Check Fleet Composition**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/metrics/instances
# Expected: {"type_distribution": {"t3.micro": 1}, ...}
```

### **4. Check Clusters**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/clusters
# Expected: {"clusters": []}
```

### **5. Check Activity Feed**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/audit/logs?limit=5"
# Expected: {"logs": [...]}
```

---

## Common Issues & Fixes

### **Issue 1: 401 Unauthorized Errors**
**Cause**: Invalid or missing authentication token
**Fix**:
- Check browser console: `localStorage.getItem('access_token')`
- Re-login if token is missing
- Verify token is being sent in `Authorization: Bearer <token>` header

### **Issue 2: Widget Shows "No Data" Despite Having Instances**
**Cause**:
- Frontend Docker image not rebuilt
- Redis cache stale
- Database missing account_id on instances

**Fix**:
```bash
# 1. Rebuild frontend
cd docker/
docker-compose build --no-cache frontend
docker-compose up -d frontend

# 2. Clear Redis cache
docker exec spot-optimizer-redis redis-cli FLUSHALL

# 3. Restart backend
docker-compose restart backend

# 4. Hard refresh browser
Cmd+Shift+R (Mac) or Ctrl+Shift+F5 (Windows)
```

### **Issue 3: Health Cards Show "No Data"**
**Cause**: Discovery workers haven't scanned AWS resources yet
**Expected**: This is CORRECT behavior if no AWS resources exist
**Note**: These populate only after:
- AWS account is connected
- Discovery workers scan (runs every 5 minutes)
- RI, S3, RDS, or Transfer resources are found

---

## Files Modified

### **Backend:**
1. ✅ `backend/services/metrics_service.py` - Updated 10+ queries to use account_id
2. ✅ `backend/models/instance.py` - Added account_id column
3. ✅ `backend/workers/tasks/discovery.py` - Sets account_id during discovery
4. ✅ `backend/api/metrics_routes.py` - All endpoints verified

### **Frontend:**
5. ✅ `frontend/src/components/dashboard/widgets/FleetComposition.jsx` - Fixed token key
6. ✅ `frontend/src/components/dashboard/widgets/SavingsChart.jsx` - Removed fake data
7. ✅ `frontend/src/components/dashboard/widgets/ActivityFeed.jsx` - Removed fake data
8. ✅ `frontend/src/components/dashboard/widgets/ClusterHealthCard.jsx` - Removed fake data
9. ✅ `frontend/src/services/api.js` - All endpoints defined correctly
10. ✅ `frontend/src/hooks/useDashboard.js` - Fetches from correct endpoints

### **Docker:**
- ✅ Frontend image rebuilt with hash: `main.6cf4eaa2.js`
- ✅ All containers healthy and running

---

## Summary

✅ **All dashboard components are now connected to real API endpoints**
✅ **No hardcoded or fake data remains**
✅ **All widgets show empty states when no data exists**
✅ **Fleet Composition authentication fixed**
✅ **Health cards properly fetch from respective endpoints**
✅ **Database has proper account_id linkage for standalone instances**

**The dashboard now displays 100% real data from the database!** 🎉

When you connect AWS accounts and discovery runs:
- Monthly Spend will show actual EC2 costs
- Fleet Composition will show instance type distribution
- Activity Feed will show real audit log events
- Health cards will show RI/S3/RDS/Transfer optimization opportunities
- Cluster Health will show actual EKS clusters

Everything is production-ready and scales automatically as resources are discovered.
