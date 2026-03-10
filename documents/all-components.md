# Complete Platform Component Inventory

> **Generated**: 2026-03-06 | **Source**: Codebase structural analysis  
> **Frontend**: React (CRA) · **Backend**: FastAPI + Celery · **DB**: PostgreSQL + Redis

---

## Architecture Overview

```
frontend/src/
├── App.js                    # Router (30+ routes)
├── services/api.js           # Axios client (25+ API modules)
├── store/useStore.js          # Zustand auth store
├── components/               # 22 directories, 139 files
│   ├── dashboard/            # Fleet overview widgets
│   ├── clusters/             # Cluster management
│   ├── atharvaai/            # ML engine UI
│   ├── right-sizing/         # Karpenter rightsizing
│   ├── hibernation/          # Schedule management
│   ├── cleanup/              # Resource hygiene
│   ├── settings/             # Org settings & tags
│   ├── admin/                # Super-admin panel
│   ├── auth/                 # Login/Signup
│   ├── governance/           # Permission gates & JIT
│   ├── policies/             # Optimization policies
│   ├── approvals/            # Ticket & access modals
│   ├── onboarding/           # AWS setup wizard
│   ├── shared/               # Reusable primitives
│   ├── ri/                   # Reserved Instance analysis
│   ├── s3/                   # S3 tiering
│   ├── rds/                  # RDS analysis
│   ├── transfer/             # Data Transfer analysis
│   ├── audit/                # Audit log viewer
│   ├── teams/                # Team management tabs
│   ├── optimizer/            # Optimizer coordinator
│   └── layout/               # MainLayout shell
└── pages/                    # 8 page-level components

backend/
├── api/                      # 44 FastAPI route files
├── services/                 # 65 service modules
├── models/                   # SQLAlchemy models
├── schemas/                  # Pydantic schemas
├── workers/                  # Celery tasks
└── core/                     # Auth, config, DB
```

---

## 1. Authentication & Onboarding

### 1.1 Auth Components

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Email input | Input | Email | User enters email | — | — | — | — | `auth/Login.jsx` |
| Password input | Input | Password | User enters password | — | — | — | — | `auth/Login.jsx` |
| Login button | Button | Sign In | Submit credentials | `/api/v1/auth/login` | POST | `auth_routes.py` | `auth_service.py` | `auth/Login.jsx` |
| Signup form | Form | Create Account | Register new user | `/api/v1/auth/signup` | POST | `auth_routes.py` | `auth_service.py` | `auth/Signup.jsx` |
| Invitation banner | Banner | Accept/Decline | Respond to org invite | `/api/v1/auth/invitation-response` | POST | `auth_routes.py` | `auth_service.py` | `auth/InviteAcceptance.jsx` |

**Dependencies**: `useAuthStore` (Zustand), `authAPI` → `auth_routes.py` → `auth_service.py` → `users` table

### 1.2 Onboarding Wizard

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Welcome screen | Card | Welcome | Navigate to next step | — | — | — | — | `onboarding/WelcomeStep.jsx` |
| AWS mode selector | Dropdown | Access Mode | Choose FULL/READ_ONLY | — | — | — | — | `onboarding/ConnectStep.jsx` |
| CloudFormation link | Button | Launch Stack | Open AWS console | `/api/v1/onboarding/aws-link` | GET | `onboarding_routes.py` | `onboarding_service.py` | `onboarding/ConnectStep.jsx` |
| Role ARN input | Input | Role ARN | Enter AWS IAM role | — | — | — | — | `onboarding/ConnectStep.jsx` |
| Verify button | Button | Verify Connection | Validate ARN | `/api/v1/onboarding/verify` | POST | `onboarding_routes.py` | `onboarding_service.py` | `onboarding/VerifyStep.jsx` |
| Skip button | Button | Skip | Skip onboarding | `/api/v1/onboarding/skip` | POST | `onboarding_routes.py` | `onboarding_service.py` | `onboarding/ConnectStep.jsx` |
| Success screen | Card | All Set! | Navigate to dashboard | — | — | — | — | `onboarding/SuccessStep.jsx` |

**Dependencies**: `onboardingAPI` → `onboarding_routes.py` → `onboarding_service.py` → `organizations`, `aws_accounts` tables

---

## 2. Dashboard (Fleet Overview)

### 2.1 Main Dashboard

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Cost KPI card | Card | Total Monthly Cost | Display spend metric | `/api/v1/metrics/dashboard` | GET | `metrics_routes.py` | `metrics_service.py` | `widgets/CostKPICard.jsx` |
| Savings KPI card | Card | Total Savings | Display savings metric | `/api/v1/metrics/dashboard` | GET | `metrics_routes.py` | `metrics_service.py` | `widgets/SavingsKPICard.jsx` |
| Savings bar chart | Chart | Savings by Category | Visualize savings breakdown | `/api/v1/metrics/dashboard` | GET | `metrics_routes.py` | `metrics_service.py` | `widgets/SavingsChart.jsx` |
| Fleet composition pie | Chart | Fleet Composition | Show instance type mix | `/api/v1/clusters` | GET | `cluster_routes.py` | `cluster_service.py` | `widgets/FleetComposition.jsx` |
| Activity feed | List | Recent Activity | Show recent events | `/api/v1/audit/logs` | GET | `audit_routes.py` | `audit_service.py` | `widgets/ActivityFeed.jsx` |
| Cluster health cards | Card grid | Cluster Health | Show cluster status | `/api/v1/clusters` | GET | `cluster_routes.py` | `cluster_service.py` | `widgets/ClusterHealthCard.jsx` |
| Platform health | Card | Platform Health | Show system status | `/api/v1/admin/health` | GET | `admin_routes.py` | `admin_service.py` | `widgets/PlatformHealthCard.jsx` |
| Pending approvals | Card | Pending Approvals | Show awaiting actions | `/api/v1/approvals/` | GET | `approval_routes.py` | `approval_service.py` | `widgets/PendingApprovalsCard.jsx` |
| Agent status | Card | Agent Status | Show DaemonSet health | `/api/v1/admin/agent-fleet` | GET | `admin_routes.py` | `admin_service.py` | `widgets/AgentStatusWidget.jsx` |
| Spend forecast | Chart | Spend Forecast | Predict future costs | `/api/v1/metrics/cost/timeseries` | GET | `metrics_routes.py` | `metrics_service.py` | `widgets/SpendForecastWidget.jsx` |
| Trends chart | Area Chart | Fleet Trends | 30-day savings & spot trends | `/api/v1/multi-cluster/trends` | GET | `multi_cluster_routes.py` | `DailyClusterStat` model | `widgets/TrendsChart.jsx` |
| Tenant list | Table | Tenants | Show organizations | `/api/v1/admin/organizations` | GET | `admin_routes.py` | `admin_service.py` | `widgets/TenantListCard.jsx` |
| Widget config | Modal | Customize Dashboard | Toggle widget visibility | `/api/v1/users/me/preferences` | PATCH | `user_routes.py` | — | `Dashboard.jsx` |
| Access request modal | Modal | Request Access | Request feature access | `/api/v1/approvals/jit-request` | POST | `approval_routes.py` | `approval_service.py` | `approvals/AccessRequestModal.jsx` |

**Dependencies**: `Dashboard.jsx` → `metricAPI`, `clusterAPI`, `auditAPI`, `multiClusterAPI` → `metrics_routes.py`, `cluster_routes.py`, `audit_routes.py`, `multi_cluster_routes.py`  
**State**: `widgetRegistry.js`, `roleDefaults.js`, `useAuthStore`

---

## 3. Cluster Management

### 3.1 Cluster List & Details

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Cluster table | Table | Clusters | List all clusters | `/api/v1/clusters` | GET | `cluster_routes.py` | `cluster_service.py` | `clusters/ClusterList.jsx` |
| Search input | Input | Search clusters | Filter cluster list | — (client-side) | — | — | — | `clusters/ClusterList.jsx` |
| Delete cluster btn | Button | Delete | Remove cluster | `/api/v1/clusters/{id}` | DELETE | `cluster_routes.py` | `cluster_service.py` | `clusters/ClusterDeleteModal.jsx` |
| Disconnect agent btn | Button | Disconnect | Disconnect agent | `/api/v1/clusters/{id}/agent/disconnect` | POST | `cluster_routes.py` | `cluster_service.py` | `clusters/ClusterDisconnectModal.jsx` |
| Cluster detail panel | Panel | Cluster Details | Show full cluster info | `/api/v1/clusters/{id}` | GET | `cluster_routes.py` | `cluster_service.py` | `clusters/ClusterDetails.jsx` |
| Node list table | Table | Nodes | Show cluster nodes | `/api/v1/clusters/{id}/nodes/detailed` | GET | `cluster_routes.py` | `cluster_service.py` | `clusters/NodeList.jsx` |
| Node group breakdown | Chart | Node Groups | Breakdown by group | `/api/v1/clusters/{id}/nodes` | GET | `cluster_routes.py` | `cluster_service.py` | `clusters/NodeGroupBreakdown.jsx` |
| Utilization sparkline | Chart | CPU/Mem Utilization | Inline utilization graph | `/api/v1/clusters/{id}/utilization` | GET | `cluster_routes.py` | `cluster_service.py` | `clusters/ClusterUtilizationSparkline.jsx` |
| Health timeline | Timeline | Health Events | Show health history | `/api/v1/clusters/{id}` | GET | `cluster_routes.py` | `cluster_service.py` | `clusters/ClusterHealthTimeline.jsx` |
| Spot ratio gauge | Gauge | Spot Ratio | Spot vs OD ratio | `/api/v1/clusters/{id}` | GET | `cluster_routes.py` | `cluster_service.py` | `clusters/SpotRatioGauge.jsx` |
| Policy gap alert | Alert | Policy Gap | Show missing policies | — (derived) | — | — | — | `clusters/PolicyGapAlert.jsx` |
| Node template tab | Tab | Node Templates | Assign templates | `/api/v1/clusters/{id}/node-template/active` | GET | `node_template_routes.py` | `template_service.py` | `clusters/NodeTemplateTab.jsx` |

### 3.2 Optimization Settings (within ClusterList)

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Auto-rebalance toggle | Toggle | Auto Rebalance | Enable/disable auto-rebalance | `/api/v1/clusters/{id}/optimization-settings` | PUT | `cluster_routes.py` | `cluster_service.py` | `clusters/ClusterList.jsx` |
| Auto-rightsizing toggle | Toggle | Auto Rightsizing | Enable/disable rightsizing | `/api/v1/clusters/{id}/optimization-settings` | PUT | `cluster_routes.py` | `cluster_service.py` | `clusters/ClusterList.jsx` |
| Maintain standby toggle | Toggle | Maintain Standby | Keep warm spare nodes | `/api/v1/clusters/{id}/optimization-settings` | PUT | `cluster_routes.py` | `cluster_service.py` | `clusters/ClusterList.jsx` |
| Diversify pools toggle | Toggle | Diversify Spot Pools | Spread across pools | `/api/v1/clusters/{id}/optimization-settings` | PUT | `cluster_routes.py` | `cluster_service.py` | `clusters/ClusterList.jsx` |
| Failure cooldown input | Input | Failure Cooldown (min) | Set cooldown minutes | `/api/v1/clusters/{id}/optimization-settings` | PUT | `cluster_routes.py` | `cluster_service.py` | `clusters/ClusterList.jsx` |
| Save settings btn | Button | Save | Persist settings | `/api/v1/clusters/{id}/optimization-settings` | PUT | `cluster_routes.py` | `cluster_service.py` | `clusters/ClusterList.jsx` |

**Dependencies**: `clusterAPI`, `karpenterAPI`, `nodeTemplateAPI` → `cluster_routes.py`, `karpenter_routes.py`, `node_template_routes.py` → `cluster_service.py`, `karpenter_service.py`

---

## 4. AtharvaAI (ML Engine)

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Pool rankings table | Table | ML Pool Rankings | Show ranked pools | `/api/v1/atharvaai/pools/rankings` | POST | `atharvaai_routes.py` | `pool_ranking_service.py` | `atharvaai/PoolRankings.jsx` |
| Global rankings card | Card | Global Rankings | Fleet-wide pool scores | `/api/v1/atharvaai/pools/rankings` | POST | `atharvaai_routes.py` | `pool_ranking_service.py` | `atharvaai/GlobalRankingsCard.jsx` |
| Blacklist monitor | Card | Risky Pools | Show blacklisted pools | `/api/v1/atharvaai/blacklist` | GET | `atharvaai_routes.py` | `blacklist_service.py` | `atharvaai/BlacklistMonitorCard.jsx` |
| Auto-rebalance audit | Card | Rebalance History | Recent rebalance actions | `/api/v1/atharvaai/rebalancing/status` | GET | `atharvaai_routes.py` | `cluster_service.py` | `atharvaai/AutoRebalanceAuditCard.jsx` |
| Rebalancing timeline | Timeline | Migration Progress | Live migration steps | `/api/v1/atharvaai/rebalancing/status` | GET | `atharvaai_routes.py` | `cluster_service.py` | `atharvaai/RebalancingTimeline.jsx` |
| Volatility monitor | Card | Spot Volatility | Interruption rates | `/api/v1/atharvaai/volatility/status` | GET | `atharvaai_routes.py` | `pool_ranking_service.py` | `atharvaai/VolatilityMonitor.jsx` |
| Interruption heatmap | Heatmap | Interruption Heatmap | AZ risk visualization | `/api/v1/atharvaai/volatility/status` | GET | `atharvaai_routes.py` | `pool_ranking_service.py` | `atharvaai/InterruptionHeatmap.jsx` |
| Diversity gauge | Gauge | Pool Diversity | Instance type diversity | `/api/v1/atharvaai/v3/diversity/{id}` | GET | `atharvaai_routes.py` | `diversity_enforcer.py` | `atharvaai/DiversityGauge.jsx` |
| Optimization mode | Selector | Optimization Mode | Switch balanced/cost/perf | `/api/v1/atharvaai/v3/cluster/{id}/optimization-mode` | PUT | `atharvaai_routes.py` | `cluster_service.py` | `atharvaai/OptimizationModeSelector.jsx` |
| Global intel panel | Panel | Global Intelligence | Region-wide insights | `/api/v1/atharvaai/v3/global-intelligence/status` | GET | `atharvaai_routes.py` | `pool_ranking_service.py` | `atharvaai/GlobalIntelligencePanel.jsx` |
| Workload classifier | Panel | Workload Classification | Stateless/Stateful tags | `/api/v1/atharvaai/v3/workload-status/{id}` | GET | `atharvaai_routes.py` | `workload_inspector.py` | `atharvaai/WorkloadClassificationPanel.jsx` |
| DE v3 dashboard | Dashboard | Decision Engine | Full DE metrics | Multiple v3 endpoints | GET | `atharvaai_routes.py` | `decision_engine_service.py` | `atharvaai/DecisionEngineV3Dashboard.jsx` |

**Dependencies**: `atharvaaiAPI`, `decisionEngineAPI` → `atharvaai_routes.py` → `pool_ranking_service.py`, `blacklist_service.py`, `diversity_enforcer.py`, `workload_inspector.py`

---

## 5. Right-Sizing Dashboard

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Cluster selector | Dropdown | Select Cluster | Switch cluster context | `/api/v1/clusters` | GET | `cluster_routes.py` | `cluster_service.py` | `right-sizing/RightSizingDashboard.jsx` |
| Auto-mode banner | Banner | Auto ON/OFF | Show automation status | `/api/v1/clusters/{id}/optimization-settings` | GET | `cluster_routes.py` | `cluster_service.py` | `RightSizingDashboard.jsx` |
| Cluster overview cards | Card grid | Total/Stateless/Stateful | Node counts | `/api/v1/karpenter/recommendations` | GET | `karpenter_routes.py` | `karpenter_service.py` | `RightSizingDashboard.jsx` |
| Exposure gauges | Charts | Spot/AZ/Family | Distribution gauges | — (derived from recs) | — | — | — | `RightSizingDashboard.jsx` |
| Guard panel | Card | Guard & Stability | Rollbacks, triggers, circuit | — (hardcoded safety) | — | — | — | `RightSizingDashboard.jsx` |
| Stateless nodes table | Table | Stateless Nodes | View/apply recommendations | `/api/v1/karpenter/recommendations` | GET | `karpenter_routes.py` | `rightsizing_service.py` | `RightSizingDashboard.jsx` |
| Apply button | Button | Apply/Optimize | Apply single recommendation | `/api/v1/karpenter/apply-recommendation/{id}` | POST | `karpenter_routes.py` | `karpenter_service.py` | `RightSizingDashboard.jsx` |
| Apply all button | Button | Apply All Eligible | Batch apply recommendations | — (iterative) | — | — | — | `RightSizingDashboard.jsx` |
| Stateless detail modal | Modal | Node Details | Show candidates, checks | — (derived) | — | — | — | `RightSizingDashboard.jsx` |
| Stateful nodes table | Table | Stateful Nodes | View OD resize proposals | `/api/v1/karpenter/recommendations` | GET | `karpenter_routes.py` | `rightsizing_service.py` | `RightSizingDashboard.jsx` |
| Request approval btn | Button | Request Approval | Submit stateful resize | `/api/v1/karpenter/apply-recommendation/{id}` | POST | `karpenter_routes.py` | `karpenter_service.py` | `RightSizingDashboard.jsx` |
| Execution plan table | Table | Execution Plan | List pending proposals | `/api/v1/optimizer/proposals/{id}` | GET | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `RightSizingDashboard.jsx` |
| Approve proposal btn | Button | Approve | Approve proposal | `/api/v1/optimizer/proposals/{id}/approve` | POST | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `RightSizingDashboard.jsx` |
| Reject proposal btn | Button | Reject | Reject proposal | `/api/v1/optimizer/proposals/{id}/reject` | POST | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `RightSizingDashboard.jsx` |
| History table | Table | Action History | Past resize actions | `/api/v1/karpenter/history` | GET | `karpenter_routes.py` | `karpenter_service.py` | `RightSizingDashboard.jsx` |
| Savings KPIs | Cards | Resizes/Savings/Rate | Month-to-date KPIs | `/api/v1/karpenter/history` | GET | `karpenter_routes.py` | `karpenter_service.py` | `RightSizingDashboard.jsx` |
| Karpenter config panel | Form | Configuration | Strategy, families, toggles | `/api/v1/karpenter/config` | PATCH | `karpenter_routes.py` | `karpenter_service.py` | `RightSizingDashboard.jsx` |
| Strategy selector | Button group | Optimization Strategy | balanced/cost/performance | `/api/v1/karpenter/config` | PATCH | `karpenter_routes.py` | `karpenter_service.py` | `RightSizingDashboard.jsx` |
| Spot target slider | Slider | Spot Target % | Set spot percentage | `/api/v1/karpenter/config` | PATCH | `karpenter_routes.py` | `karpenter_service.py` | `RightSizingDashboard.jsx` |
| Instance family chips | Toggle chips | Instance Families | Enable/disable families | `/api/v1/karpenter/config` | PATCH | `karpenter_routes.py` | `karpenter_service.py` | `RightSizingDashboard.jsx` |
| Diversify pools toggle | Toggle | Diversify Pools | Spread across pools | `/api/v1/karpenter/config` | PATCH | `karpenter_routes.py` | `karpenter_service.py` | `RightSizingDashboard.jsx` |
| Rebalancing timeline | Timeline | Active Migrations | Live migration steps | `/api/v1/atharvaai/rebalancing/status` | GET | `atharvaai_routes.py` | `cluster_service.py` | `atharvaai/RebalancingTimeline.jsx` |

**Dependencies**: `clusterAPI`, `karpenterAPI`, `atharvaaiAPI`, `optimizerCoordinatorAPI` → `cluster_routes.py`, `karpenter_routes.py`, `atharvaai_routes.py`, `optimizer_coordinator_routes.py` → `cluster_service.py`, `karpenter_service.py`, `rightsizing_service.py`, `optimizer_coordinator.py`

---

## 6. Hibernation Management

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Cluster overview cards | Card grid | Overview | Cluster hibernation stats | `/api/v1/hibernation/schedules` | GET | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/ClusterOverview.jsx` |
| Dashboard tab | Tab | Dashboard | Summary view | `/api/v1/hibernation/schedules` | GET | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/DashboardTab.jsx` |
| Schedule calendar | Calendar | Schedule Calendar | Visual calendar view | `/api/v1/hibernation/schedules` | GET | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/ScheduleCalendar.jsx` |
| Schedule matrix | Grid | Schedule Matrix | Weekly hour matrix | `/api/v1/hibernation/schedules` | GET | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/ScheduleMatrix.jsx` |
| Schedule builder | Form | Schedule Builder | Create/edit schedule | `/api/v1/hibernation/schedules` | POST | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/ScheduleBuilder.jsx` |
| Schedule modal | Modal | Create Schedule | Full schedule form | `/api/v1/hibernation/schedules` | POST/PUT | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/ScheduleModal.jsx` |
| Hibernation wizard | Wizard | Setup Wizard | Guided schedule setup | `/api/v1/hibernation/schedules` | POST | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/HibernationWizard.jsx` |
| Strategy selector | Radio group | Strategy | Choose hibernation strategy | `/api/v1/hibernation/strategies` | GET | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/StrategySelector.jsx` |
| Hibernation type card | Card | Type Selection | Full/Partial/Custom | — | — | — | — | `hibernation/HibernationTypeCard.jsx` |
| Status banner | Banner | Status | Current hibernation state | `/api/v1/hibernation/schedules` | GET | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/StatusBanner.jsx` |
| Header | Header | Hibernation | Title + cluster selector | `/api/v1/clusters` | GET | `cluster_routes.py` | `cluster_service.py` | `hibernation/HibernationHeader.jsx` |
| Emergency controls | Panel | Emergency Controls | Force wake/sleep | `/api/v1/hibernation/schedules/{id}/override` | POST | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/EmergencyControls.jsx` |
| Time-based rules | Form | Time Rules | Define schedule rules | — | — | — | — | `hibernation/TimeBasedRules.jsx` |
| Multi-timezone | Panel | Timezone Config | Set timezone for schedule | — | — | — | — | `hibernation/MultiTimezone.jsx` |
| Unified schedule grid | Grid | Schedule Grid | Full schedule view | `/api/v1/hibernation/schedules` | GET | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/UnifiedScheduleGrid.jsx` |
| Validation panel | Panel | Validation | Schedule validation | — | — | — | — | `hibernation/ValidationPanel.jsx` |
| Conflict detection modal | Modal | Conflict Detection | Overlapping schedule warn | — (client-side) | — | — | — | `hibernation/ConflictDetectionModal.jsx` |
| Advanced config | Panel | Advanced | Drain settings, grace | — | — | — | — | `hibernation/AdvancedConfiguration.jsx` |
| Cost analytics | Chart | Cost Savings | Hibernation savings | `/api/v1/metrics/cost` | GET | `metrics_routes.py` | `metrics_service.py` | `hibernation/CostAnalytics.jsx` |
| Cost analytics dashboard | Dashboard | Cost Dashboard | Full cost analytics | `/api/v1/billing/costs/summary` | GET | `billing_routes.py` | — | `hibernation/CostAnalyticsDashboard.jsx` |
| Execution history | Table | History | Past hibernation events | `/api/v1/audit/logs` | GET | `audit_routes.py` | `audit_service.py` | `hibernation/ExecutionHistory.jsx` |
| Audit history | Table | Audit | Detailed change log | `/api/v1/audit/logs` | GET | `audit_routes.py` | `audit_service.py` | `hibernation/AuditHistory.jsx` |
| History log | List | History Log | Quick event log | — | — | — | — | `hibernation/HistoryLog.jsx` |
| Notification settings | Form | Notifications | Alert preferences | — | — | — | — | `hibernation/NotificationSettings.jsx` |
| HibernationDashboardNew | Page | Hibernation | Main hibernation page | Multiple | GET/POST | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/HibernationDashboardNew.jsx` |
| Hibernation scheduler | Form | Scheduler | Full scheduler | `/api/v1/hibernation/schedules` | POST/PUT | `hibernation_routes.py` | `hibernation_service.py` | `hibernation/HibernationScheduler.jsx` |

**Dependencies**: `hibernationAPI`, `clusterAPI`, `billingAPI` → `hibernation_routes.py` → `hibernation_service.py` → `hibernation_schedules` table

---

## 7. Resource Hygiene (Cleanup)

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Cleanup dashboard | Page | Resource Hygiene | Main cleanup page | `/api/v1/hygiene/scan/{accountId}` | GET | `hygiene_routes.py` | `hygiene_service.py` | `cleanup/CleanupDashboard.jsx` |
| Hero metrics panel | Cards | Summary | Waste/savings metrics | `/api/v1/hygiene/total-cost` | GET | `hygiene_routes.py` | `hygiene_service.py` | `cleanup/summary/HeroMetricsPanel.jsx` |
| Savings gauge | Gauge | Savings Gauge | Visual savings donut | — (derived) | — | — | — | `cleanup/summary/SavingsGauge.jsx` |
| Resource table | Table | Resources | Wasteful resource list | `/api/v1/hygiene/scan/{id}` | GET | `hygiene_routes.py` | `hygiene_service.py` | `cleanup/tables/ResourceTable.jsx` |
| Cleanup sidebar | Sidebar | Categories | Resource type filter | `/api/v1/hygiene/cost-services` | GET | `hygiene_routes.py` | `hygiene_service.py` | `cleanup/layout/CleanupSidebar.jsx` |
| Filter panel | Panel | Filters | Region/type filters | — (client-side) | — | — | — | `cleanup/layout/FilterPanel.jsx` |
| Delete/cleanup button | Button | Clean Up | Execute cleanup action | `/api/v1/hygiene/action` | POST | `hygiene_routes.py` | `hygiene_service.py` | `cleanup/CleanupDashboard.jsx` |
| Bulk tag wizard | Wizard | Bulk Tag | Tag multiple resources | — | — | — | — | `cleanup/BulkTagWizard.jsx` |
| RDS wizard | Wizard | RDS Cleanup | RDS-specific cleanup | `/api/v1/hygiene/scan/{id}` | GET | `hygiene_routes.py` | `hygiene_service.py` | `cleanup/wizards/RDSWizard.jsx` |
| RI wizard | Wizard | RI Analysis | RI cleanup wizard | `/api/v1/hygiene/scan/{id}` | GET | `hygiene_routes.py` | `hygiene_service.py` | `cleanup/wizards/RIWizard.jsx` |
| S3 wizard | Wizard | S3 Tiering | S3 tier wizard | `/api/v1/hygiene/scan/{id}` | GET | `hygiene_routes.py` | `hygiene_service.py` | `cleanup/wizards/S3Wizard.jsx` |

**Dependencies**: `hygieneAPI`, `accountAPI` → `hygiene_routes.py` → `hygiene_service.py` → AWS Cost Explorer + resource APIs

---

## 8. Settings & Tag Governance

### 8.1 Settings

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Settings page | Page | Settings | Main settings container | Multiple | GET | Multiple | Multiple | `settings/Settings.jsx` |
| Account settings | Tab | Account | Profile & org info | `/api/v1/auth/me` | GET | `auth_routes.py` | `auth_service.py` | `settings/AccountSettings.jsx` |
| Cloud integrations | Tab | Integrations | AWS account mgmt | `/api/v1/accounts` | GET | `account_routes.py` | `account_service.py` | `settings/CloudIntegrations.jsx` |
| Team management | Tab | Team Members | Invite/remove members | `/api/v1/organization/members` | GET | `organization_routes.py` | `organization_service.py` | `settings/TeamManagement.jsx` |
| Team governance | Tab | Team Governance | Team-level policies | `/api/v1/teams/{id}/governance` | PUT | `team_routes.py` | `team_service.py` | `settings/TeamGovernance.jsx` |
| Member permissions modal | Modal | Permissions | Edit member permissions | `/api/v1/users/{id}/permissions` | POST | `user_routes.py` | — | `settings/MemberPermissionsModal.jsx` |
| Governance settings | Page | Automation Settings | Autopilot & approvals | `/api/v1/governance/policies` | GET/PATCH | `governance_routes.py` | `governance_service.py` | `settings/GovernanceSettings.jsx` |
| Governance manager | Component | Governance | Governance wrapper | — | — | — | — | `settings/GovernanceManager.jsx` |

### 8.2 Tag Governance

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Tag governance page | Page | Tag Governance | Full tag mgmt page | Multiple tag APIs | GET/POST | Multiple tag routes | Multiple tag services | `settings/TagGovernancePage.jsx` |
| Tag policies list | Table | Tag Policies | List tag policies | `/api/v1/tags/policies/` | GET | `tag_policy_routes.py` | `tag_policy_service.py` | `settings/TagPoliciesList.jsx` |
| Tag policies manager | Page | Tagging Policies | Tag policy CRUD | `/api/v1/tags/policies/` | GET/POST/PUT/DELETE | `tag_policy_routes.py` | `tag_policy_service.py` | `settings/TagPoliciesManager.jsx` |

**Dependencies**: `authAPI`, `accountAPI`, `organizationAPI`, `teamAPI`, `governanceAPI`, `tagPolicyAPI`, `tagTemplateAPI`, `tagAutomationAPI`, `tagScoringAPI`, `tagComplianceAPI`

---

## 9. Policies & Governance

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Policy config page | Page | Policies | Create/edit policies | `/api/v1/policies` | GET/POST/PUT | `policy_routes.py` | `policy_service.py` | `policies/PolicyConfig.jsx` |
| Policy toggle | Toggle | Enable/Disable | Toggle policy active | `/api/v1/policies/{id}/toggle` | POST | `policy_routes.py` | `policy_service.py` | `policies/PolicyConfig.jsx` |
| Permission matrix | Table | Permissions | Feature-role matrix | `/api/v1/permissions/feature-registry` | GET | `permission_routes.py` | `permission_service.py` | `policies/PermissionMatrix.jsx` |
| Cleanup policies | Tab | Cleanup Policies | Resource cleanup rules | `/api/v1/policies` | GET | `policy_routes.py` | `policy_service.py` | `policies/CleanupPolicies.jsx` |
| Permission gate | Wrapper | — | Feature access guard | `/api/v1/permissions/check` | POST | `permission_routes.py` | `permission_service.py` | `governance/PermissionGate.jsx` |
| Protected button | Button | — | Permission-gated action | `/api/v1/permissions/check` | POST | `permission_routes.py` | `permission_service.py` | `governance/ProtectedButton.jsx` |
| Active JIT banner | Banner | Active Access | Show JIT access status | `/api/v1/approvals/my-jit-approvals` | GET | `approval_routes.py` | `approval_service.py` | `governance/ActiveJITBanner.jsx` |
| JIT request modal | Modal | Request Access | JIT access form | `/api/v1/approvals/jit-request` | POST | `approval_routes.py` | `approval_service.py` | `governance/JITRequestModal.jsx` |

---

## 10. Approvals

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Approvals page | Page | Approvals | List all approvals | `/api/v1/approvals/` | GET | `approval_routes.py` | `approval_service.py` | `pages/Approvals.jsx` |
| Approve button | Button | Approve | Approve request | `/api/v1/approvals/{id}/approve` | POST | `approval_routes.py` | `approval_service.py` | `pages/Approvals.jsx` |
| Reject button | Button | Reject | Reject request | `/api/v1/approvals/{id}/reject` | POST | `approval_routes.py` | `approval_service.py` | `pages/Approvals.jsx` |
| Revoke button | Button | Revoke | Revoke access | `/api/v1/approvals/{id}/revoke` | POST | `approval_routes.py` | `approval_service.py` | `pages/Approvals.jsx` |
| Ticket request modal | Modal | Create Ticket | Submit approval request | `/api/v1/approvals/` | POST | `approval_routes.py` | `approval_service.py` | `approvals/TicketRequestModal.jsx` |
| Access request modal | Modal | Request Access | Feature access request | `/api/v1/approvals/jit-request` | POST | `approval_routes.py` | `approval_service.py` | `approvals/AccessRequestModal.jsx` |

---

## 11. Admin Panel (SUPER_ADMIN)

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Admin dashboard | Page | Admin Dashboard | Platform overview | `/api/v1/admin/dashboard` | GET | `admin_routes.py` | `admin_service.py` | `admin/AdminDashboard.jsx` |
| Admin overview | Tab | Overview | Summary stats | `/api/v1/admin/stats` | GET | `admin_routes.py` | `admin_service.py` | `admin/AdminOverview.jsx` |
| Client management | Page | Clients | Manage users | `/api/v1/admin/clients` | GET | `admin_routes.py` | `admin_service.py` | `admin/AdminClients.jsx` |
| Toggle client | Button | Enable/Disable | Toggle client status | `/api/v1/admin/clients/{id}/toggle` | POST | `admin_routes.py` | `admin_service.py` | `admin/AdminClients.jsx` |
| Reset password | Button | Reset Password | Force password reset | `/api/v1/admin/clients/{id}/reset-password` | POST | `admin_routes.py` | `admin_service.py` | `admin/AdminClients.jsx` |
| Organization mgmt | Page | Organizations | Manage orgs | `/api/v1/admin/organizations` | GET | `admin_routes.py` | `admin_service.py` | `admin/AdminOrganizations.jsx` |
| Toggle org | Button | Enable/Disable | Toggle org status | `/api/v1/admin/organizations/{id}/toggle` | POST | `admin_routes.py` | `admin_service.py` | `admin/AdminOrganizations.jsx` |
| Impersonate btn | Button | Impersonate | Login as org | `/api/v1/admin/impersonate` | POST | `admin_routes.py` | `admin_service.py` | `admin/AdminOrganizations.jsx` |
| Health monitor | Page | System Health | Backend health checks | `/api/v1/admin/health` | GET | `admin_routes.py` | `admin_service.py` | `admin/AdminHealth.jsx` |
| Experiments lab | Page | Experiments | A/B test management | `/api/v1/lab/experiments` | GET/POST | `lab_routes.py` | `lab_service.py` | `admin/AdminExperiments.jsx` |
| Platform config | Page | Configuration | Feature flags | — | — | — | — | `admin/AdminConfig.jsx` |
| Platform settings | Tab | Settings | Platform-level config | — | — | — | — | `admin/PlatformSettings.jsx` |
| Billing dashboard | Page | Billing | Billing overview | `/api/v1/admin/billing` | GET | `admin_routes.py` | `admin_service.py` | `admin/AdminBilling.jsx` |

**Dependencies**: `adminAPI`, `experimentsAPI`, `billingAPI` → `admin_routes.py`, `lab_routes.py`, `billing_routes.py` → `admin_service.py`, `lab_service.py`

---

## 12. Teams & Roles

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Teams page | Page | Teams | List all teams | `/api/v1/teams/` | GET | `team_routes.py` | `team_service.py` | `pages/Teams.jsx` |
| Create team btn | Button | Create Team | Create new team | `/api/v1/teams/` | POST | `team_routes.py` | `team_service.py` | `pages/Teams.jsx` |
| Team details page | Page | Team Details | Team detail + members | `/api/v1/teams/{id}` | GET | `team_routes.py` | `team_service.py` | `pages/TeamDetails.jsx` |
| Members tab | Tab | Members | Team member list | `/api/v1/teams/{id}` | GET | `team_routes.py` | `team_service.py` | `teams/MembersTab.jsx` |
| Teams tab | Tab | Teams | Teams overview | `/api/v1/teams/` | GET | `team_routes.py` | `team_service.py` | `teams/TeamsTab.jsx` |
| Roles & policies tab | Tab | Roles & Policies | Role management | `/api/v1/roles` | GET | `role_routes.py` | `role_service.py` | `teams/RolesPoliciesTopTab.jsx` |
| Roles page | Page | Roles | Full RBAC management | `/api/v1/roles` | GET/POST/PUT/DELETE | `role_routes.py` | `role_service.py` | `pages/Roles.jsx` |
| Invite member btn | Button | Invite | Invite team member | `/api/v1/teams/{id}/invite` | POST | `team_routes.py` | `team_service.py` | `pages/TeamDetails.jsx` |

---

## 13. Cost Analysis Pages

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Account analytics | Page | Account Analytics | Per-account cost view | `/api/v1/metrics/accounts/{id}/summary` | GET | `metrics_routes.py` | `metrics_service.py` | `pages/AccountAnalytics.jsx` |
| RI analysis | Page | RI Analysis | Reserved Instance recs | `/api/v1/ri/` | GET | `ri_routes.py` | `ri_analysis_service.py` | `ri/RIAnalysis.jsx` |
| RI health card | Card | RI Utilization | RI utilization gauge | `/api/v1/ri/` | GET | `ri_routes.py` | `ri_analysis_service.py` | `ri/RIHealthCard.jsx` |
| S3 analysis | Page | S3 Tiering | S3 tier recommendations | `/api/v1/s3/` | GET | `s3_routes.py` | `s3_tiering_service.py` | `s3/S3Analysis.jsx` |
| RDS analysis | Page | RDS Analysis | RDS recommendations | `/api/v1/rds/` | GET | `rds_routes.py` | `rds_analysis_service.py` | `rds/RDSAnalysis.jsx` |
| RDS health card | Card | RDS Health | RDS metrics | `/api/v1/rds/` | GET | `rds_routes.py` | `rds_analysis_service.py` | `rds/RDSHealthCard.jsx` |
| Transfer analysis | Page | Data Transfer | Transfer cost analysis | `/api/v1/transfer/` | GET | `transfer_routes.py` | `transfer_service.py` | `transfer/TransferAnalysis.jsx` |

---

## 14. Node Templates

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Templates page | Page | Node Templates | Global template registry | `/api/v1/node-templates` | GET | `node_template_routes.py` | `template_service.py` | `pages/NodeTemplates.jsx` |
| Create template btn | Button | Create Template | New template form | `/api/v1/node-templates` | POST | `node_template_routes.py` | `template_service.py` | `pages/NodeTemplates.jsx` |
| Delete template btn | Button | Delete | Remove template | `/api/v1/node-templates/{id}` | DELETE | `node_template_routes.py` | `template_service.py` | `pages/NodeTemplates.jsx` |
| Version list | Table | Versions | Template versions | `/api/v1/node-templates/{id}/versions` | GET | `node_template_routes.py` | `template_service.py` | `pages/NodeTemplates.jsx` |
| Validate btn | Button | Validate | Check template | `/api/v1/node-templates/validate` | POST | `node_template_routes.py` | `template_service.py` | `pages/NodeTemplates.jsx` |

---

## 15. Shared / Reusable Components

| Component | Type | Props | Used By | File |
|---|---|---|---|---|
| Button | Button | variant, size, onClick, disabled | All sections | `shared/Button.jsx` |
| Card | Container | children, style | Dashboard, Clusters, Settings | `shared/Card.jsx` |
| Input | Input | label, value, onChange, type | Auth, Settings, Forms | `shared/Input.jsx` |
| Badge | Badge | color, children | Tables, Lists | `shared/Badge.jsx` |
| Switch | Toggle | checked, onChange | Settings, Policies | `shared/Switch.jsx` |
| Dropdown | Select | options, value, onChange | Filters, Forms | `shared/Dropdown.jsx` |
| EmptyState | Placeholder | message, icon | Tables, Lists | `shared/EmptyState.jsx` |
| StatsCard | Card | title, value, trend | Dashboard, Analytics | `shared/StatsCard.jsx` |
| GaugeChart | Chart | value, max, label | Cleanup, Clusters | `shared/GaugeChart.jsx` |
| RiskBadge | Badge | level (low/med/high) | AtharvaAI, Pools | `shared/RiskBadge.jsx` |
| NotificationPanel | Panel | — | Layout | `shared/NotificationPanel.jsx` |

---

## 16. Layout & Global

| Component | Type | Responsibility | File |
|---|---|---|---|
| MainLayout | Shell | Sidebar + header + content | `layout/MainLayout.jsx` |
| App.js | Router | Route definitions + auth guards | `App.js` |
| ProtectedRoute | Guard | Auth-required wrapper | `App.js` |
| AdminRoute | Guard | SUPER_ADMIN wrapper | `App.js` |
| PublicRoute | Guard | Redirect if authenticated | `App.js` |
| PermissionGate | Guard | Feature-level access control | `governance/PermissionGate.jsx` |

---

## 17. Multi-Cluster Fleet

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Fleet summary | Card | Fleet Summary | Aggregated fleet metrics | `/api/v1/multi-cluster/summary` | GET | `multi_cluster_routes.py` | DB queries | `dashboard/Dashboard.jsx` |
| Fleet actions | Feed | Fleet Actions | Recent fleet actions | `/api/v1/multi-cluster/actions` | GET | `multi_cluster_routes.py` | `rebalancing_actions` table | `dashboard/Dashboard.jsx` |
| Fleet trends chart | Area Chart | Fleet Trends | 30-day trends | `/api/v1/multi-cluster/trends` | GET | `multi_cluster_routes.py` | `DailyClusterStat` model | `dashboard/widgets/TrendsChart.jsx` |

**Dependencies**: `multiClusterAPI` → `multi_cluster_routes.py` → `daily_cluster_stats`, `rebalancing_actions`, `clusters`, `instances` tables  
**Background**: `aggregate_daily_stats` Celery task runs via `daily_stats_aggregator.py` on beat schedule

---

## API Client Module Index (`frontend/src/services/api.js`)

| Module | Prefix | Backend Route File | Primary Service |
|---|---|---|---|
| `authAPI` | `/api/v1/auth/` | `auth_routes.py` | `auth_service.py` |
| `clusterAPI` | `/api/v1/clusters/` | `cluster_routes.py` | `cluster_service.py` |
| `accountAPI` | `/api/v1/accounts/` | `account_routes.py` | `account_service.py` |
| `adminAPI` | `/api/v1/admin/` | `admin_routes.py` | `admin_service.py` |
| `metricAPI` | `/api/v1/metrics/` | `metrics_routes.py` | `metrics_service.py` |
| `optimizationAPI` | `/api/v1/optimization/` | `optimization_routes.py` | `rightsizing_service.py` |
| `policyAPI` | `/api/v1/policies/` | `policy_routes.py` | `policy_service.py` |
| `hibernationAPI` | `/api/v1/hibernation/` | `hibernation_routes.py` | `hibernation_service.py` |
| `auditAPI` | `/api/v1/audit/` | `audit_routes.py` | `audit_service.py` |
| `templateAPI` | `/api/v1/templates/` | `node_template_routes.py` | `template_service.py` |
| `nodeTemplateAPI` | `/api/v1/node-templates/` | `node_template_routes.py` | `template_service.py` |
| `experimentsAPI` | `/api/v1/lab/` | `lab_routes.py` | `lab_service.py` |
| `onboardingAPI` | `/api/v1/onboarding/` | `onboarding_routes.py` | `onboarding_service.py` |
| `organizationAPI` | `/api/v1/organization/` | `organization_routes.py` | `organization_service.py` |
| `teamAPI` | `/api/v1/teams/` | `team_routes.py` | `team_service.py` |
| `userAPI` | `/api/v1/users/` | `user_routes.py` | — |
| `billingAPI` | `/api/v1/billing/` | `billing_routes.py` | — |
| `hygieneAPI` | `/api/v1/hygiene/` | `hygiene_routes.py` | `hygiene_service.py` |
| `atharvaaiAPI` | `/api/v1/atharvaai/` | `atharvaai_routes.py` | `pool_ranking_service.py` |
| `approvalsAPI` | `/api/v1/approvals/` | `approval_routes.py` | `approval_service.py` |
| `governanceAPI` | `/api/v1/governance/` | `governance_routes.py` | `governance_service.py` |
| `rolesAPI` | `/api/v1/roles/` | `role_routes.py` | `role_service.py` |
| `permissionAPI` | `/api/v1/permissions/` | `permission_routes.py` | `permission_service.py` |
| `karpenterAPI` | `/api/v1/karpenter/` | `karpenter_routes.py` | `karpenter_service.py` |
| `tagPolicyAPI` | `/api/v1/tags/policies/` | `tag_policy_routes.py` | `tag_policy_service.py` |
| `tagTemplateAPI` | `/api/v1/tags/templates/` | `tag_management_routes.py` | `tag_management_service.py` |
| `tagAutomationAPI` | `/api/v1/tags/automation/` | `tag_automation_routes.py` | `tag_automation_service.py` |
| `tagScoringAPI` | `/api/v1/tags/scoring/` | `tag_scoring_routes.py` | `tag_scoring_service.py` |
| `tagComplianceAPI` | `/api/v1/tags/compliance/` | `tag_compliance_routes.py` | `tag_compliance_service.py` |
| `decisionEngineAPI` | `/api/v1/atharvaai/v3/` | `atharvaai_routes.py` | `decision_engine_service.py` |
| `optimizerCoordinatorAPI` | `/api/v1/optimizer/` | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` |
| `poolRotationAPI` | `/api/v1/pool-rotation/` | `pool_rotation_routes.py` | `pool_rotation_service.py` |
| `multiClusterAPI` | `/api/v1/multi-cluster/` | `multi_cluster_routes.py` | — |

---

## Backend Service Dependency Map

| Service | Key Dependencies | Database Tables |
|---|---|---|
| `auth_service.py` | JWT, bcrypt | `users`, `organizations` |
| `cluster_service.py` | AWS EC2/EKS, agent comms | `clusters`, `instances`, `cluster_optimization_settings` |
| `karpenter_service.py` | cluster_service, pool_ranking | `karpenter_configs`, `karpenter_recommendations` |
| `pool_ranking_service.py` | ML model (ONNX), AWS Spot API | `pool_rankings`, `spot_volatility_cache` |
| `blacklist_service.py` | pool_ranking_service | `blacklisted_pools` |
| `rightsizing_service.py` | karpenter_service, metrics | `instances`, `pod_metrics` |
| `optimizer_coordinator.py` | karpenter_service, guardrail | `optimizer_proposals` |
| `hibernation_service.py` | cluster_service, scheduler | `hibernation_schedules` |
| `hygiene_service.py` | AWS Cost Explorer, EC2, S3, RDS | `hygiene_scans`, `waste_resources` |
| `metrics_service.py` | cluster_service, billing | `metrics_snapshots` |
| `admin_service.py` | all services | `users`, `organizations` |
| `policy_service.py` | cluster_service | `optimization_policies` |
| `approval_service.py` | permission_service | `approvals`, `jit_access` |
| `permission_service.py` | role_service | `permissions`, `feature_registry` |
| `role_service.py` | — | `roles`, `role_permissions` |
| `team_service.py` | organization_service | `teams`, `team_members` |
| `organization_service.py` | auth_service | `organizations`, `org_members` |
| `onboarding_service.py` | AWS STS/CloudFormation | `organizations`, `aws_accounts` |
| `lab_service.py` | cluster_service | `experiments` |
| `audit_service.py` | — | `audit_logs` |
| `decision_engine_service.py` | pool_ranking, cooldown | `decision_logs` |
| `diversity_enforcer.py` | cluster_service | `instances` |
| `workload_inspector.py` | cluster_service | `instances`, `pod_metrics` |
| `substitute_manager.py` | karpenter_service, cluster | `substitute_nodes` |
| `pool_rotation_service.py` | pool_ranking_service | `pool_configs` |
| `tag_policy_service.py` | — | `tag_policies` |
| `tag_management_service.py` | — | `tag_templates` |
| `tag_automation_service.py` | tag_policy_service | `tag_automation_rules` |
| `tag_scoring_service.py` | tag_policy_service | `tag_scores` |
| `tag_compliance_service.py` | tag_policy_service | `tag_compliance` |
| `ri_analysis_service.py` | AWS CE | `ri_recommendations` |
| `s3_tiering_service.py` | AWS S3 | `s3_tiering_recs` |
| `rds_analysis_service.py` | AWS RDS | `rds_recommendations` |
| `transfer_service.py` | AWS CE | `transfer_analysis` |

---

## Component Hierarchy Diagram

```
App.js
├── PublicRoute
│   ├── Login
│   └── Signup
├── ProtectedRoute
│   ├── Onboarding (WelcomeStep → ConnectStep → VerifyStep → SuccessStep)
│   └── MainLayout
│       ├── Dashboard (CostKPI, SavingsKPI, SavingsChart, FleetComposition,
│       │    ActivityFeed, ClusterHealth, PlatformHealth, PendingApprovals,
│       │    AgentStatus, SpendForecast, TrendsChart, TenantList)
│       ├── ClusterList → ClusterDetails (NodeList, NodeGroupBreakdown,
│       │    SpotRatioGauge, UtilizationSparkline, HealthTimeline, NodeTemplateTab)
│       ├── RightSizingDashboard (AutoModeBanner, ClusterHealthExposureBar,
│       │    ResizeGuardPanel, StatelessSection, StatefulSection,
│       │    KarpenterConfigPanel, RebalancingTimeline)
│       ├── HibernationDashboard (Header, StatusBanner, ScheduleCalendar,
│       │    ScheduleMatrix, HibernationWizard, EmergencyControls,
│       │    CostAnalytics, ExecutionHistory, NotificationSettings)
│       ├── CleanupDashboard (HeroMetrics, SavingsGauge, ResourceTable,
│       │    CleanupSidebar, FilterPanel, BulkTagWizard)
│       ├── AtharvaAiPage (PoolRankings, GlobalRankings, BlacklistMonitor,
│       │    AutoRebalanceAudit, VolatilityMonitor, InterruptionHeatmap,
│       │    DiversityGauge, DecisionEngineV3Dashboard)
│       ├── PolicyConfig (CleanupPolicies, PermissionMatrix)
│       ├── Settings (AccountSettings, CloudIntegrations, TeamManagement,
│       │    GovernanceSettings, TagGovernancePage)
│       ├── Approvals
│       ├── AuditLog
│       ├── Teams → TeamDetails (MembersTab, TeamsTab, RolesPoliciesTopTab)
│       ├── Roles
│       ├── NodeTemplates
│       ├── RIAnalysis, S3Analysis, RDSAnalysis, TransferAnalysis
│       ├── AccountAnalytics
│       └── AdminRoute
│           ├── AdminDashboard (AdminOverview)
│           ├── AdminClients
│           ├── AdminOrganizations
│           ├── AdminHealth
│           ├── AdminExperiments
│           ├── AdminConfig (PlatformSettings)
│           └── AdminBilling
└── PermissionGate (wraps most routes)
    └── ProtectedButton, ActiveJITBanner, JITRequestModal
```

---

*Total: **139 component files** · **8 page files** · **25+ API modules** · **44 backend routes** · **65 backend services***

---

## 18. Optimizer Coordinator Dashboard

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| Optimizer status panel | Panel | Optimizer Status | Show evaluation state | `/api/v1/optimizer/status/{id}` | GET | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Trigger evaluation btn | Button | Trigger Evaluation | Run optimization cycle | `/api/v1/optimizer/evaluate/{id}` | POST | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Proposals table | Table | Proposals | List proposals | `/api/v1/optimizer/proposals/{id}` | GET | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Approve proposal btn | Button | Approve | Approve a proposal | `/api/v1/optimizer/proposals/{id}/approve` | POST | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Reject proposal btn | Button | Reject | Reject a proposal | `/api/v1/optimizer/proposals/{id}/reject` | POST | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| EV comparison panel | Panel | Expected Value | Before/after comparison | `/api/v1/optimizer/comparison/{id}` | GET | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Trust phase indicator | Badge | Trust Phase | Show Observer/Advisor/Auto | `/api/v1/optimizer/trust-phase/{id}` | GET | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Resize guard status | Panel | Resize Guard | Show guard state | `/api/v1/optimizer/resize-guard/{id}` | GET | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Circuit breaker status | Panel | Circuit Breaker | Show breaker state | `/api/v1/optimizer/circuit-breaker/{id}` | GET | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Initialize cluster btn | Button | Initialize | Set up cluster optimizer | `/api/v1/optimizer/initialize/{id}` | POST | `optimizer_coordinator_routes.py` | `optimizer_coordinator.py` | `optimizer/OptimizerCoordinatorDashboard.jsx` |

**Dependencies**: `optimizerCoordinatorAPI` → `optimizer_coordinator_routes.py` → `optimizer_coordinator.py` → `optimizer_proposals`, `clusters` tables

---

## 19. Dashboard Health Cards (Missing Widgets)

| UI Element | Type | Label | Action | API Endpoint | Method | Backend Route | Service | File |
|---|---|---|---|---|---|---|---|---|
| S3 health card | Card | S3 Storage Health | S3 tiering summary | `/api/v1/s3/overview` | GET | `s3_routes.py` | `s3_tiering_service.py` | `s3/S3HealthCard.jsx` |
| Refresh S3 btn | Button | ↻ | Refresh S3 data | `/api/v1/s3/overview` | GET | `s3_routes.py` | `s3_tiering_service.py` | `s3/S3HealthCard.jsx` |
| View S3 details btn | Button | View Details | Navigate to S3 analysis | — (navigate) | — | — | — | `s3/S3HealthCard.jsx` |
| Optimize S3 btn | Button | Optimize | Navigate to S3 analysis | — (navigate) | — | — | — | `s3/S3HealthCard.jsx` |
| Transfer health card | Card | Data Transfer Health | Transfer cost summary | `/api/v1/transfer/overview` | GET | `transfer_routes.py` | `transfer_service.py` | `transfer/TransferHealthCard.jsx` |
| Refresh transfer btn | Button | ↻ | Refresh transfer data | `/api/v1/transfer/overview` | GET | `transfer_routes.py` | `transfer_service.py` | `transfer/TransferHealthCard.jsx` |
| View transfer btn | Button | View Details | Navigate to transfer analysis | — (navigate) | — | — | — | `transfer/TransferHealthCard.jsx` |

---

## 20. Backend-Only Routes (No Direct UI Component)

These backend route files serve internal/agent/system functions without a dedicated frontend component:

| Backend Route File | Prefix | Purpose | Service | Consumers |
|---|---|---|---|---|
| `agent_routes.py` | `/api/v1/agent/` | DaemonSet agent heartbeat & reporting | `agent_service.py` | Agent DaemonSet (not UI) |
| `ai_agent_routes.py` | `/api/v1/ai-agent/` | AI-driven remediation agent | `chaos_testing_service.py` | Automated backend agent |
| `decision_routes.py` | `/api/v1/decision/` | Decision engine logs & status | `decision_engine_service.py` | `decisionEngineAPI` in `api.js` |
| `health_routes.py` | `/api/v1/health` | Liveness/readiness probe | — | Docker/K8s health checks |
| `installer_routes.py` | `/api/v1/installer/` | Agent installer script generation | `agent_injector.py` | Onboarding flow (indirect) |
| `pod_metrics_routes.py` | `/api/v1/pod-metrics/` | Pod-level CPU/memory metrics | `rightsizing_service.py` | `optimizationAPI` in `api.js` |
| `worker_routes.py` | `/api/v1/worker/` | Agent-reported metrics ingestion | `cluster_service.py` | Agent DaemonSet (not UI) |

---

## 21. State Management & Utilities

### Zustand Stores

| Store | File | State Managed | Used By |
|---|---|---|---|
| `useAuthStore` | `store/useStore.js` | `user`, `accessToken`, `isAuthenticated`, `login()`, `logout()` | `App.js`, all ProtectedRoutes |
| `useAtharvaStore` | `store/useAtharvaStore.js` | AtharvaAI panel state, selected cluster, cache | AtharvaAI components |
| `useHibernationStore` | `store/useHibernationStore.js` | Hibernation wizard state, selected schedule | Hibernation components |

### Custom Hooks

| Hook | File | Purpose | Used By |
|---|---|---|---|
| `useDashboard` | `hooks/useDashboard.js` | Dashboard data fetching & widget state | `Dashboard.jsx` |
| `usePermission` | `hooks/usePermission.js` | Permission checking helper | `PermissionGate.jsx`, `ProtectedButton.jsx` |

### Utility Modules

| Utility | File | Functions | Used By |
|---|---|---|---|
| `formatters` | `utils/formatters.js` | `formatCurrency()`, `formatDate()`, `formatBytes()` | Multiple components |

---

## 22. Barrel Re-export Index Files

| File | Exports | Purpose |
|---|---|---|
| `atharvaai/index.js` | All AtharvaAI components | Single import point for AtharvaAI |
| `dashboard/widgets/index.js` | All dashboard widget components | Single import for dashboard widgets |
| `hibernation/index.js` | `HibernationDashboard` (from `HibernationDashboardNew`) | Entry point for hibernation section |
| `shared/index.js` | `Button`, `Card`, `Input`, `Badge`, `Switch`, `Dropdown`, `EmptyState`, `StatsCard`, `GaugeChart`, `RiskBadge` | Shared component library export |

---

## Complete File Count Summary

| Category | Count | Location |
|---|---|---|
| Frontend Components (`.jsx`) | 139 | `frontend/src/components/` |
| Frontend Pages (`.jsx`) | 8 | `frontend/src/pages/` |
| Barrel Index Files (`.js`) | 4 | Various `index.js` |
| Dashboard Utility (`.js`) | 2 | `roleDefaults.js`, `widgetRegistry.js` |
| Zustand Stores (`.js`) | 3 | `frontend/src/store/` |
| Custom Hooks (`.js`) | 2 | `frontend/src/hooks/` |
| Utility Modules (`.js`) | 1 | `frontend/src/utils/` |
| API Client (`.js`) | 1 | `frontend/src/services/api.js` |
| App Entry (`.js`) | 2 | `App.js`, `index.js` |
| **Frontend Total** | **162** | |
| Backend Route Files (`.py`) | 44 | `backend/api/` |
| Backend Services (`.py`) | 65 | `backend/services/` |
| Backend Models | 65 | `backend/models/` |
| Backend Schemas | 26 | `backend/schemas/` |
| Backend Workers | 37 | `backend/workers/` |
| **Backend Total** | **237** | |
| **Grand Total** | **399** | |

---

## APPENDIX A: Internal Sub-Components & Subsection Breakdown

This appendix documents every inline sub-component, tab, panel, and nested UI element defined inside the major component files but not exported as standalone files.

---

### A.1 Dashboard (`Dashboard.jsx` — 969 lines)

**Tabs**: Overview (default), Widget Configuration

**Inline Sub-Components:**

| Sub-Component | Type | Purpose | Lines |
|---|---|---|---|
| `Badge` | Display | Colored label chip | L46–56 |
| `Dot` | Display | Status dot indicator | L58–63 |
| `SectionLabel` | Display | Uppercase section header | L65–71 |
| `EmptyChip` | Display | Empty state placeholder | L73–81 |
| `Sparkline` | Chart | SVG mini line chart | L83–94 |
| `KpiCard` | Card | Main KPI metric with trend | L96–132 |
| `Card` | Container | Section wrapper with title | L134–151 |
| `HealthMiniCard` | Card | RI/S3/RDS/Transfer mini card | L153–175 |
| `FeatureRow` | Row | Optimization feature status row | L177–201 |

**Dashboard Layout Sections:**
1. **KPI Row** — 4x `KpiCard` (Total cost, Total savings, Cluster count, Active agents)
2. **Feature Status** — `FeatureRow` items (Spot Optimization, Auto-Rebalancing, Right-Sizing, Hibernation)
3. **Health Mini Cards** — `HealthMiniCard` items (RI Analysis, S3 Tiering, RDS Analysis, Data Transfer)
4. **Fleet Composition** — `FleetComposition` widget (pie chart)
5. **Savings Chart** — `SavingsChart` widget (bar chart)
6. **Trends Chart** — `TrendsChart` widget (area chart, multi-cluster)
7. **Cluster Health** — `ClusterHealthCard` grid
8. **Platform Health** — `PlatformHealthCard`
9. **Pending Approvals** — `PendingApprovalsCard`
10. **Activity Feed** — `ActivityFeed` (combined audit logs + multi-cluster actions)
11. **Agent Status** — `AgentStatusWidget`
12. **Tenant List** — `TenantListCard` (admin-only)
13. **Spend Forecast** — `SpendForecastWidget`

---

### A.2 Clusters (`ClusterList.jsx` — 2011 lines)

**Tabs/Views**: Cluster List View → Cluster Detail Panel (slide-in)

**Inline Sub-Components:**

| Sub-Component | Type | Purpose | Lines |
|---|---|---|---|
| `ToggleSwitch` | Toggle | Animated on/off switch | L81–101 |
| `OptimizationSettingsTab` | Panel | Settings for auto-rebalance/rightsizing/standby/diversify/cooldown | L103–360 |
| `MiniBar` | Chart | Inline utilization bar | L362–372 |
| `Tag` | Display | Tinted tag/badge chip | L374–384 |
| `MetricBox` | Card | Labeled metric with icon | L386–398 |
| `NodeTreemap` | Visualization | Treemap grid of cluster nodes (paginated, 20/page) | L403–680 |
| `SpotRing` | Chart | SVG donut showing spot ratio | L682–704 |
| `ClusterListItem` | Row | Single cluster row with sparkline | L706–791 |
| `SectionHeader` | Display | Section heading | L793–800 |
| `ClusterDetail` | Panel | Full cluster detail (connected agent) | L802–1445 |
| `NoAgentDetail` | Panel | Cluster detail (no agent) | L1447–1555 |
| `ClustersPage` | Page | Main clusters page with list + detail | L1557–2011 |

**ClusterDetail Internal Sections:**
1. **Header** — Cluster name, status, region, agent version
2. **Metrics Row** — CPU utilization, Memory utilization, Node count, Spot ratio (SpotRing)
3. **Node Treemap** — Visual grid of all nodes with type coloring
4. **Optimization Settings Tab** — Toggle switches (auto-rebalance, auto-rightsizing, maintain-standby, diversify-pools, failure-cooldown)
5. **Actions Bar** — Optimize, Fallback, Disconnect, Delete buttons

**OptimizationSettingsTab Subsections:**
1. **Auto-Rebalance Toggle** — Enable/disable with description
2. **Auto-Rightsizing Toggle** — Enable/disable with description
3. **Maintain Standby Toggle** — Keep warm spare nodes
4. **Diversify Spot Pools Toggle** — Spread across instance pools
5. **Failure Cooldown Input** — Minutes input (0–120)
6. **Node Template Selector** — Active template mapping display

---

### A.3 Cluster Details (`ClusterDetails.jsx` — 1312 lines)

**Tabs**: Overview, Nodes, Configuration, Node Templates, Health

| Tab | Sub-Component | API Used | Content |
|---|---|---|---|
| Overview | Inline metrics | `clusterAPI.getCluster` | Status, utilization, savings, spot ratio |
| Nodes | `NodeList` | `clusterAPI.getNodesDetailed` | Sortable node table with types |
| Nodes | `NodeGroupBreakdown` | `clusterAPI.getNodes` | Pie chart by node group |
| Configuration | `PolicyConfig` inline | `policyAPI.getPolicy` | Per-cluster policy settings |
| Node Templates | `NodeTemplateTab` | `nodeTemplateAPI.getActiveMapping` | Template assignment |
| Health | `ClusterHealthTimeline` | `clusterAPI.getCluster` | Health event timeline |

**Action Buttons:**
- Optimize → `clusterAPI.optimize(id)`
- Fallback → `clusterAPI.fallback(id)`
- Disconnect Agent → `clusterAPI.disconnectAgent(id)`
- Remove Agent → `clusterAPI.removeAgent(id)`
- Mode Selector → `clusterAPI.updateCluster(id, data)`

---

### A.4 Right-Sizing (`RightSizingDashboard.jsx` — 1169 lines)

**Tabs**: Live View (default), History, Configuration

**Inline Sub-Components:**

| Sub-Component | Type | Purpose | Lines |
|---|---|---|---|
| `Card` | Container | Section wrapper | L36–40 |
| `SectionLabel` | Display | Section header | L42–46 |
| `Badge` | Display | Status/count badge | L48–54 |
| `AutoModeBanner` | Banner | Shows auto-rebalance + auto-rightsizing ON/OFF | L59–112 |
| `ClusterHealthExposureBar` | Panel | 4-column card (Total/Stateless/Stateful/Eligible nodes) | L114–177 |
| `ResizeGuardMonitoringPanel` | Panel | Guard & stability metrics (rollbacks, triggers, circuit) | L179–218 |
| `StatelessDetailedDrawer` | Modal | Node detail with candidates, readiness checks, apply | L220–265 |
| `StatefulProposalModal` | Modal | OD resize proposal flow with approval | L267–328 |
| `StatelessSection` | Table | Stateless nodes table with Apply buttons | L331–513 |
| `StatefulSection` | Table | Stateful nodes table with Request Approval | L516–608 |
| `KarpenterConfigPanel` | Form | Full config panel (strategy, spot%, families, toggles) | L610–778 |
| `KarpenterConfigPanel.ToggleSwitch` | Toggle | Inline toggle for config | L653–657 |
| `KarpenterConfigPanel.ToggleRow` | Row | Label + description + toggle | L659–667 |

**Live View Subsections:**
1. **Auto Mode Banner** — Shows automation status
2. **Cluster Health & Exposure** — Node count cards with change indicators
3. **Guard Panel** — Rollbacks, emergency triggers, circuit breaker
4. **Stateless Nodes Table** — Sortable table with per-node Apply button + Apply All
5. **Stateful Nodes Table** — Table with Request Approval workflow

**History Tab Subsections:**
1. **Savings KPIs** — Total resizes, total savings, success rate cards
2. **Execution Plan Table** — Proposals from optimizer with Approve/Reject buttons
3. **Action History Table** — Past resize actions with timestamps

**Configuration Tab Subsections:**
1. **Strategy Selector** — Balanced/Cost/Performance button group
2. **Spot Target Slider** — Percentage selector (0–100%)
3. **Instance Families** — Togglable chip list (m5, c5, r5, etc.)
4. **Feature Toggles** — Diversify pools, AZ awareness, graviton preference

---

### A.5 AtharvaAI (`AtharvaAiPage.jsx` — 123 lines)

**Tabs** (via URL `?tab=`):

| Tab | URL Param | Components Rendered |
|---|---|---|
| Dashboard (default) | `dashboard` | `BlacklistMonitorCard`, `AutoRebalanceAuditCard`, `InterruptionHeatmap`, `RebalancingTimeline`, `PoolRankings` |
| Rankings | `rankings` | `PoolRankings` only |
| Heatmap | `heatmap` | `InterruptionHeatmap` only |
| Rebalancing | `rebalancing` | `AutoRebalanceAuditCard`, `RebalancingTimeline` |
| Decision Engine v3 | `decision-engine-v3` | `DecisionEngineV3Dashboard` |

---

### A.6 Hibernation (`HibernationDashboardNew.jsx` — 1124 lines)

**Tabs**: Dashboard, Schedules, Calendar, Wizard, Emergency, Analytics, History, Notifications, Settings

| Tab | Content | Key Sub-Components |
|---|---|---|
| Dashboard | Summary metrics + quick actions | `DashboardTab`, `ClusterOverview` |
| Schedules | Schedule list with toggle/edit/delete | `UnifiedScheduleGrid`, `ScheduleModal` |
| Calendar | Visual week/month calendar | `ScheduleCalendar` |
| Wizard | Guided setup flow | `HibernationWizard`, `HibernationTypeCard`, `StrategySelector`, `ScheduleBuilder` |
| Emergency | Force wake/sleep controls | `EmergencyControls`, `StatusBanner` |
| Analytics | Cost savings analytics | `CostAnalytics`, `CostAnalyticsDashboard` |
| History | Past execution log | `ExecutionHistory`, `AuditHistory`, `HistoryLog` |
| Notifications | Alert preferences | `NotificationSettings` |
| Settings | Advanced config | `AdvancedConfiguration`, `TimeBasedRules`, `MultiTimezone`, `ValidationPanel` |

---

### A.7 Cleanup (`CleanupDashboard.jsx` — 1123 lines)

**Layout**: Sidebar + Main Content

**Inline Sub-Components:**

| Sub-Component | Type | Purpose | Lines |
|---|---|---|---|
| `StatusPill` | Display | Resource status colored pill | L47–62 |
| `SectionLabel` | Display | Section header | L64–71 |
| `KpiCard` | Card | Summary metric card | L73–87 |
| `Checkbox` | Input | Selectable checkbox with indeterminate | L89–109 |
| `Sidebar` | Navigation | Resource category sidebar | L111–218 |
| `ResourceTable` | Table | Main resource table with selection | L220–389 |
| `AnimatedNum` | Display | Animated number counter | L391–405 |
| `RingGauge` | Chart | SVG ring/donut gauge | L407–427 |
| `SparkBars` | Chart | Mini bar chart | L429–442 |

**Main Page Sections:**
1. **Account Selector** — Dropdown to select AWS account
2. **Summary KPIs** — Total waste, potential savings, resources scanned, compliance %
3. **Sidebar Categories** — Unattached Volumes, Idle IPs, Old Snapshots, Unused SGs, etc.
4. **Resource Table** — Filtered by category, with status pills, bulk select, action buttons
5. **Action Bar** — Delete/Cleanup/Tag/Export buttons for selected resources
6. **Wizard Modals** — `RDSWizard`, `RIWizard`, `S3Wizard` slide-in panels

---

### A.8 Settings (`Settings.jsx` — 220 lines)

**Tabs**: Account, Integrations, Billing

| Tab | Component | Key Elements |
|---|---|---|
| Account | `AccountSettings` | Profile form, password change, org info, connection info |
| Integrations | `CloudIntegrations` | AWS account list, add account, validate, set default |
| Billing | `BillingTab` (inline) | Plan info, usage metrics, manage billing portal button |

**`AccountSettings` Subsections:**
- Profile info (name, email)
- Change Password form
- Organization details
- Connection Info (org ID, API key)

**`CloudIntegrations` Subsections:**
- AWS Accounts table
- Add Account modal
- Validate button per account
- Set Default button per account

---

### A.9 Tag Governance (`TagGovernancePage.jsx` — 1561 lines)

**Tabs/Sidebar Sections:**

| Section | Content | API Module |
|---|---|---|
| Policies | Tag policy CRUD with enforce/audit modes | `tagPolicyAPI` |
| Templates | Key templates (required keys + defaults) | `tagTemplateAPI` |
| Automation | Auto-tagging rules and schedules | `tagAutomationAPI` |
| Scoring | Tag health scores per resource/account | `tagScoringAPI` |
| Compliance | Compliance reports and violation lists | `tagComplianceAPI` |

**Inline Sub-Components (20+):**

| Sub-Component | Type | Purpose |
|---|---|---|
| `Ico` | Icon | SVG icon renderer |
| `Badge` | Display | Variant-colored badge |
| `Toggle` | Input | On/off toggle switch |
| `Btn` | Button | Primary/secondary/ghost button |
| `Input` | Input | Label + hint + error form input |
| `Select` | Input | Dropdown select |
| `Card` | Container | Section card |
| `InfoBanner` | Alert | Blue/yellow info banner |
| `Modal` | Modal | Full modal with header/footer |
| `ScoreDonut` | Chart | SVG donut score visualization |
| `ComplianceBar` | Chart | Compliance percentage bar |

---

### A.10 Approvals (`Approvals.jsx` — 506 lines)

**Tabs** (client-side filter):

| Tab | Filter | Content |
|---|---|---|
| Pending | `status == pending` | Tickets awaiting approval/rejection |
| Active | `status == approved` | Currently active JIT access grants |
| History | `status in [rejected, expired, revoked]` | Past decisions |
| Outgoing | `requester == currentUser` | User's own requests |

**Action Buttons per Tab:**
- Pending: Approve, Reject
- Active: Revoke
- Outgoing: Cancel (if pending)

---

### A.11 Team Details (`TeamDetails.jsx` — 463 lines)

**Tabs:**

| Tab | Content | API |
|---|---|---|
| Members | Member list with roles, invite, remove | `teamAPI.get(id)` |
| Analytics | Team cost/savings metrics, charts | `metricsAPI.getTeamSummary(id)` |
| Governance | Team-level governance config | `teamAPI.updateGovernance(id, config)` |

**Members Tab Subsections:**
- Member table (name, email, role, last active)
- Invite form (email, role dropdown)
- Remove member button (with confirmation)

---

### A.12 Governance Settings (`GovernanceSettings.jsx` — 254 lines)

**Sections** (no tabs, single scroll page):

| Section | Toggle/Control | API |
|---|---|---|
| Auto-Rightsizing | Enable/Disable toggle + mode (Insights/Auto) | `governance/policies` PATCH |
| Auto-Rebalancing | Enable/Disable toggle + aggressiveness slider | `governance/policies` PATCH |
| Hibernation Automation | Enable/Disable toggle | `governance/policies` PATCH |
| Approval Requirements | Require approval for destructive actions toggle | `governance/policies` PATCH |
| Cost Threshold | Dollar amount threshold for auto-approval | `governance/policies` PATCH |

---

### A.13 Admin Components Internal Sections

**AdminOverview (`AdminOverview.jsx`):**
- Platform Stats Cards (Total orgs, Total users, Active clusters, Monthly revenue)
- Agent Fleet status grid
- Recent activity feed

**AdminClients (`AdminClients.jsx`):**
- Search + filter bar
- Client table (name, email, org, status, last login)
- Actions: Toggle status, Reset password, Impersonate

**AdminOrganizations (`AdminOrganizations.jsx`):**
- Organization table with pagination
- Actions: Toggle org, View details, Impersonate

**AdminHealth (`AdminHealth.jsx`):**
- Backend service health grid
- Database connection status
- Redis connection status
- Worker queue depths

**AdminExperiments (`AdminExperiments.jsx`):**
- Experiment list table
- Create experiment form
- Start/Stop buttons
- Results panel

**AdminBilling (`AdminBilling.jsx`):**
- Revenue summary cards
- Organization billing breakdown table
- Stripe portal integration

**AdminConfig (`AdminConfig.jsx`) / PlatformSettings:**
- Feature flags table with toggles
- System configuration parameters
