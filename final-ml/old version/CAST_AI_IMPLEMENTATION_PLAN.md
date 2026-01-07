# CAST AI Features Implementation Plan

**Status**: Planning Phase
**Created**: 2025-12-26
**Branch**: `claude/aws-dual-mode-connectivity-fvlS3`

---

## Overview

This document outlines the complete implementation plan for CAST AI-inspired features in the client dashboard. Each feature is broken down into frontend components, backend APIs, database models, and testing requirements.

---

## ✅ Completed Features

### 1. Node Templates
**Status**: ✅ COMPLETE
**Component**: `frontend/src/components/NodeTemplates.jsx`
**Features**:
- Table layout with toggle switches
- Favorite star icons
- CPU/Memory progress bars with utilization
- "Create template" dropdown
- Search functionality
- Mock data (4 templates)

**Pending**:
- Backend API integration
- Real data from `/v1/client/templates` endpoint

### 2. Available Savings (UI Only)
**Status**: ⚠️ UI COMPLETE, Backend Pending
**Component**: `frontend/src/components/AvailableSavings.jsx`
**Features**:
- Large cost metrics display
- Green gradient cost card
- Progress to optimal bar (82.9%)
- Rebalance button
- Workload rightsizing toggle
- Side-by-side configuration comparison
- Efficiency metrics grid
- Mock data

**Pending**:
- Backend API: `GET /v1/client/savings`
- Real cost calculation logic
- Rebalance action implementation

---

## 🚧 In Progress

### 3. Login & Authentication
**Status**: 🚧 FIXING
**Issues**:
- Token validation delays blocking login page
- AuthContext hanging on "Verifying session..."

**Recent Fixes** (Commit: 3c61eae):
- Added immediate loading finish if no credentials
- Added 3-second timeout for token validation
- Clear session on validation failure

**Testing Required**:
- Clear localStorage and verify login page shows
- Test with invalid tokens
- Test with valid tokens

---

## 📋 Pending Features

### 4. Dashboard
**Priority**: HIGH
**Status**: ⏳ Not Started

#### Components to Create:
1. **ClusterDashboard.jsx** (Main dashboard)
2. **ClusterDetailsPanel.jsx** (Left panel)
3. **NodesSummaryPanel.jsx** (Top-right)
4. **WorkloadsSummary.jsx** (Below nodes)
5. **AutoscalerPoliciesSummary.jsx**
6. **HibernationSchedulesSummary.jsx**
7. **ResourceUtilizationCharts.jsx** (Donut charts)

#### Backend APIs Needed:
```
GET /v1/client/clusters/{cluster_id}/dashboard
  → cluster_details
  → nodes_summary
  → workloads_summary
  → autoscaler_policies
  → hibernation_schedules
  → resource_utilization
```

#### Database Models:
- Cluster (extends Account)
- Node (extends Instance)
- Workload/Pod tracking
- AutoscalerPolicy
- HibernationSchedule

#### UI Features:
- ✅ Cluster status badge (Connected/Disconnected/Read-only)
- ✅ Kubernetes provider, region, version
- ✅ Node breakdown (On-Demand, Spot, Fallback)
- ✅ Node ownership (Platform-managed vs Cloud-managed)
- ✅ Total Pods vs Scheduled Pods
- ✅ Autoscaler policies count (e.g., "2 / 3 enabled")
- ✅ Hibernation schedules count
- ✅ CPU/Memory/Storage donut charts

---

### 5. Cluster List
**Priority**: HIGH
**Status**: ⏳ Not Started

#### Component:
**ClusterList.jsx**

#### Cluster States to Implement:
1. PENDING - Cluster created, agent not verified
2. CONNECTING - Agent install in progress
3. CONNECTED - Agent fully operational
4. READ_ONLY - Metrics only, optimization disabled
5. PARTIALLY_CONNECTED - Missing permissions
6. DISCONNECTED - Agent unreachable
7. ERROR - Terminal failure
8. REMOVING - Deletion in progress
9. REMOVED - Fully deleted

#### Features:
- **Summary Overview Panel**:
  - Total compute cost (monthly)
  - Total nodes (Spot/Fallback/On-Demand)
  - Total CPU
  - Total memory

- **Cluster Table**:
  - Cluster name
  - Status badge
  - Provider (GKE, EKS, AKS, etc.)
  - Region
  - Nodes count
  - Monthly cost
  - Actions: "Adjust costs", "Disconnect", "Remove"

- **Disconnect Modal**:
  - Cluster name confirmation input
  - "Delete all platform-created nodes" checkbox with warning
  - Cancel / Disconnect buttons

#### Backend APIs:
```
GET /v1/client/clusters
  → List all clusters with status

POST /v1/client/clusters
  → Create cluster connection

DELETE /v1/client/clusters/{cluster_id}
  → Disconnect cluster

POST /v1/client/clusters/{cluster_id}/remove
  → Remove cluster with node deletion option
```

---

### 6. Optimization
**Priority**: MEDIUM
**Status**: ⏳ Not Started

#### Component:
**OptimizationSettings.jsx**

#### Sections:
1. **Workload Rightsizing**
   - Toggle: Enable/Disable
   - Metrics: Current efficiency, Waste, $ Saved, Additional savings %
   - "View" button → Opens Workloads Efficiency report

2. **Use Spot Instances**
   - Toggle: Enable/Disable
   - Options:
     - All workloads
     - Spot-friendly workloads only
   - Metrics: Workloads to run on Spot, Additional actions needed, Available savings %

3. **ARM Support**
   - Toggle: Enable/Disable
   - Slider: % of CPUs to run on ARM (0-100%)
   - Metrics: Available savings %

#### Backend APIs:
```
GET /v1/client/clusters/{cluster_id}/optimization
  → Current optimization settings

PUT /v1/client/clusters/{cluster_id}/optimization
  → Update optimization policies
```

#### Database Model:
```python
class OptimizationPolicy(Base):
    cluster_id: FK
    rightsizing_enabled: bool
    spot_instances_enabled: bool
    spot_mode: 'all' | 'friendly_only'
    arm_enabled: bool
    arm_cpu_percentage: int
```

---

### 7. Cost Monitoring
**Priority**: MEDIUM
**Status**: ⏳ Not Started

#### Component:
**CostMonitoring.jsx**

#### Features:
- **Overview Metrics**:
  - Total Compute Cost
  - Cost Trend (+/- %)
  - Time range selector (Daily/Weekly/Monthly)

- **Cost Breakdown Views**:
  - Cost by Cluster
  - Cost by Node/Instance Type
  - Cost by Workload

- **Filters**:
  - Cluster, Namespace, Workload
  - Resource type (CPU/Memory)
  - Pricing model (Spot/On-Demand)
  - Time range

- **Historical Analysis**:
  - Time-series cost trends (line/bar charts)
  - Day-over-day, Month-over-month comparisons

#### Backend APIs:
```
GET /v1/client/costs/overview
  → Total cost, trend

GET /v1/client/costs/breakdown
  ?by=cluster|node|workload
  ?time_range=7d|30d|90d
  → Cost breakdown data

GET /v1/client/costs/trends
  ?start_date=2024-01-01
  ?end_date=2024-12-31
  → Time-series cost data
```

---

### 8. Security & Compliance
**Priority**: LOW (Nice to have)
**Status**: ⏳ Not Started

#### Component:
**SecurityCompliance.jsx**

#### Features:
- Security Dashboard (compliance score, vulnerabilities, non-compliant resources)
- Compliance Report (violations with severity)
- Vulnerabilities Report (container image scanning)
- Attack Paths visualization
- Node OS Update Monitoring

**Note**: This feature requires significant backend integration with security scanning tools. Consider as Phase 2.

---

### 9. Autoscaler
**Priority**: MEDIUM
**Status**: ⏳ Not Started

#### Component:
**AutoscalerSettings.jsx**

#### Settings:
1. **Unscheduled Pods Policy**
   - Toggle: Automatically add nodes for unschedulable pods

2. **Node Deletion Policy**
   - Toggle: Remove idle nodes
   - TTL configuration

3. **Evictor Mode**
   - Toggle: Compact pods into fewer nodes
   - Aggressive mode (includes single-replica apps)

4. **Scoped Mode**
   - Limit autoscaling to CAST AI-managed nodes only

#### Backend APIs:
```
GET /v1/client/clusters/{cluster_id}/autoscaler
PUT /v1/client/clusters/{cluster_id}/autoscaler
```

---

### 10. Cluster Hibernation
**Priority**: MEDIUM
**Status**: ⏳ Not Started

#### Component:
**ClusterHibernation.jsx**

#### Features:
- **Create Schedule**:
  - "Add hibernation schedule" button
  - "Quickstart with workday schedule" preset

- **Schedule List**:
  - Schedule name
  - Enable/Disable toggle
  - Status indicator (Active/Disabled)
  - Edit/Delete actions

- **Schedule Configuration**:
  - Active periods (when cluster runs)
  - Hibernate periods (when cluster scales down)
  - Days of the week
  - Timezone awareness

- **Cost Impact Display**:
  - Total cluster cost
  - Estimated savings %
  - Before vs after cost trend

#### Backend APIs:
```
GET /v1/client/clusters/{cluster_id}/hibernation/schedules
POST /v1/client/clusters/{cluster_id}/hibernation/schedules
PUT /v1/client/clusters/{cluster_id}/hibernation/schedules/{schedule_id}
DELETE /v1/client/clusters/{cluster_id}/hibernation/schedules/{schedule_id}
```

#### Database Model:
```python
class HibernationSchedule(Base):
    cluster_id: FK
    name: str
    enabled: bool
    active_periods: JSONB  # [{day, start_time, end_time}]
    timezone: str
    created_at, updated_at
```

---

### 11. Audit Log
**Priority**: MEDIUM
**Status**: ⏳ Not Started

#### Component:
**AuditLog.jsx**

#### Features:
- **Table Columns**:
  - Timestamp
  - Operation Name
  - Initiated By (User email or Policy name)
  - Event Details (expandable)

- **Expandable Details**:
  - JSON/YAML view toggle
  - Resource IDs, parameters, before/after values

- **Filtering**:
  - Text search
  - Time range
  - Initiated by
  - Advanced: Rebalance ID, Node ID, Policy applied

- **Event Types**:
  - User actions (disconnect, reconnect, template CRUD)
  - Policy actions (autoscaler events, rightsizing)
  - System events (hibernated/resumed)

#### Backend APIs:
```
GET /v1/client/audit-log
  ?cluster_id={id}
  ?start_time={timestamp}
  ?end_time={timestamp}
  ?operation={operation_name}
  ?initiated_by={user_email|policy_name}
```

#### Database Model:
```python
class AuditLog(Base):
    id: UUID
    cluster_id: FK
    operation: str
    initiated_by: str  # user email or "system"
    details: JSONB
    timestamp: DateTime
```

---

## Implementation Phases

### **Phase 1: Core Dashboard & Cluster Management** (Week 1-2)
1. ✅ Fix login page issue
2. ⏳ Cluster List with states
3. ⏳ Dashboard (cluster details, nodes, workloads)
4. ⏳ Basic cost monitoring

### **Phase 2: Optimization & Cost Control** (Week 3-4)
5. ⏳ Optimization settings
6. ⏳ Available Savings (backend integration)
7. ⏳ Cluster Hibernation
8. ⏳ Autoscaler settings

### **Phase 3: Visibility & Governance** (Week 5-6)
9. ⏳ Enhanced Cost Monitoring
10. ⏳ Audit Log
11. ⏳ Node Templates (backend integration)

### **Phase 4: Advanced Features** (Future)
12. ⏳ Security & Compliance
13. ⏳ Attack Paths
14. ⏳ Node OS Update Monitoring

---

## Backend API Routes Summary

```python
# Cluster Management
GET    /v1/client/clusters
POST   /v1/client/clusters
GET    /v1/client/clusters/{id}
DELETE /v1/client/clusters/{id}
POST   /v1/client/clusters/{id}/remove

# Dashboard
GET    /v1/client/clusters/{id}/dashboard

# Optimization
GET    /v1/client/clusters/{id}/optimization
PUT    /v1/client/clusters/{id}/optimization

# Cost Monitoring
GET    /v1/client/costs/overview
GET    /v1/client/costs/breakdown
GET    /v1/client/costs/trends

# Savings
GET    /v1/client/clusters/{id}/savings
POST   /v1/client/clusters/{id}/rebalance

# Hibernation
GET    /v1/client/clusters/{id}/hibernation/schedules
POST   /v1/client/clusters/{id}/hibernation/schedules
PUT    /v1/client/clusters/{id}/hibernation/schedules/{schedule_id}
DELETE /v1/client/clusters/{id}/hibernation/schedules/{schedule_id}

# Autoscaler
GET    /v1/client/clusters/{id}/autoscaler
PUT    /v1/client/clusters/{id}/autoscaler

# Node Templates
GET    /v1/client/clusters/{id}/templates
POST   /v1/client/clusters/{id}/templates
PUT    /v1/client/clusters/{id}/templates/{template_id}
DELETE /v1/client/clusters/{id}/templates/{template_id}

# Audit Log
GET    /v1/client/audit-log
```

---

## Database Models Needed

```python
# Already exists
- User
- Account (can be extended to Cluster)
- Instance (can be extended to Node)
- ExperimentLog

# New models needed
- Cluster (or extend Account)
- OptimizationPolicy
- HibernationSchedule
- AutoscalerPolicy
- NodeTemplate
- AuditLog
- CostLog (for historical tracking)
```

---

## Testing Strategy

1. **Unit Tests**:
   - Each component isolated
   - Mock API responses

2. **Integration Tests**:
   - Full user flows
   - End-to-end scenarios

3. **Visual Regression**:
   - Screenshot comparisons
   - CAST AI design fidelity

4. **Performance Tests**:
   - Large cluster data
   - Historical cost data (90 days+)

---

## Documentation Updates Needed

- `frontend/src/components/info.md` - Add all new components
- `backend/api/info.md` - Document new API routes
- `backend/database/info.md` - Document new models
- Create user guide for each feature

---

## Next Steps

1. **Immediate** (Today):
   - ✅ Fix login page (DONE - commit 3c61eae)
   - Create this implementation plan (DONE)

2. **Short-term** (This Week):
   - Implement Cluster List component
   - Create Dashboard skeleton
   - Design database schema for new models

3. **Medium-term** (Next 2 Weeks):
   - Implement Optimization settings
   - Integrate Available Savings with backend
   - Build Hibernation feature

---

**Last Updated**: 2025-12-26
**Maintained By**: Claude (AI Assistant)
**Status**: Living Document - Updated as features are implemented
