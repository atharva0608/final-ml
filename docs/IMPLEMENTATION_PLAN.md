# Client Dashboard Implementation Plan

This plan details the steps to implement the Client Dashboard as defined in `CLIENT_DASHBOARD_SPEC.md`.

## Proposed Changes

### 1. Navigation & App Structure
**Goal**: Enforce the strict navigation flow defined in the spec.

- **MainLayout.jsx**: Update sidebar items.
- **App.js**: Update routes, add `Right-Sizing`.

### 2. Dashboard (Executive View)
**Goal**: "Value delivery" visibility.
- **Dashboard.jsx**: KPI Cards, Savings Graph, Cluster Map.

### 3. Cluster Management
**Goal**: Manage K8s connection.
- **ClusterList.jsx**: Connection Wizard, Cluster Registry.

### 4. Automation Policies
**Goal**: Configure rules of engagement.
- **PolicyConfig.jsx**: Provisioning, Scheduling, Constraints, Specs, Aggressiveness.

### 5. Node Templates
**Goal**: Infrastructure specs.
- **TemplateList.jsx**: Template Builder.

### 6. Workload Rightsizing [NEW]
**Goal**: Efficiency.
- **RightSizing.jsx**: Usage Graph, Throttling, Waste Heatmap.

### 7. Hibernation
**Goal**: Cost schedules.
- **HibernationSchedule.jsx**: Visual Scheduler.

### 8. Audit Log
**Goal**: Transparency.
- **AuditLog.jsx**: Event Feed, Diff View.

### 9. Settings
**Goal**: Admin.
- **AccountSettings.jsx**: Integrations, Billing, Team.
