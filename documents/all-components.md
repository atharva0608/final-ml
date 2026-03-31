# Complete Platform Component Inventory

> **Last Updated**: 2026-03-23 | **Source**: 100% verified against source files
> **Frontend**: React (CRA) · **Backend**: FastAPI + Celery · **DB**: PostgreSQL + Redis
> **Verification method**: Every file confirmed to exist on disk; every API endpoint verified in `api.js`

---

## Architecture Overview

```
frontend/src/
├── App.js                    # Router (30+ routes) — 381 lines
├── services/api.js           # Axios client (47 API modules) — 605 lines
├── store/                    # 3 Zustand stores
│   ├── useStore.js
│   ├── useASCPStore.js
│   └── useHibernationStore.js
├── hooks/                    # 4 custom hooks
│   ├── useDashboard.js
│   ├── usePermission.js
│   ├── useAdaptivePolling.js
│   └── useAuth.js
├── utils/formatters.js       # formatCurrency, formatDate, formatBytes
├── components/               # 22 directories
│   ├── dashboard/            # Fleet overview + widgets
│   ├── clusters/             # Cluster management + OverviewTab
│   ├── ascpai/            # ML engine UI
│   ├── right-sizing/         # Rightsizing dashboard
│   ├── hibernation/          # Schedule management
│   ├── cleanup/              # Resource hygiene
│   ├── settings/             # Org settings & tag governance
│   ├── admin/                # Super-admin panel
│   ├── auth/                 # Login/Signup/Invite
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
```

---

## 1. Authentication & Onboarding

### 1.1 Auth Components

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Email input | Input | Email | User enters email | — | — | `auth/Login.jsx` |
| Password input | Input | Password | User enters password | — | — | `auth/Login.jsx` |
| Login button | Button | Sign In | Submit credentials | `/api/v1/auth/login` | POST | `auth/Login.jsx` |
| Signup form | Form | Create Account | Register new user | `/api/v1/auth/signup` | POST | `auth/Signup.jsx` |
| Invitation banner | Banner | Accept/Decline | Respond to org invite | `/api/v1/auth/invitation-response` | POST | `auth/InviteAcceptance.jsx` |

**API module**: `authAPI` → `authAPI.login()`, `authAPI.signup()`, `authAPI.respondToInvitation()`
**Route**: `/login` (PublicRoute), `/signup` (PublicRoute), `/invite-acceptance` (ProtectedRoute)

### 1.2 Onboarding Wizard

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Welcome screen | Card | Welcome | Navigate to next step | — | — | `onboarding/WelcomeStep.jsx` |
| AWS mode selector | Dropdown | Access Mode | Choose FULL/READ_ONLY | — | — | `onboarding/ConnectStep.jsx` |
| CloudFormation link | Button | Launch Stack | Open AWS console | `/api/v1/onboarding/aws-link?mode=...` | GET | `onboarding/ConnectStep.jsx` |
| Role ARN input | Input | Role ARN | Enter AWS IAM role | — | — | `onboarding/ConnectStep.jsx` |
| Verify button | Button | Verify Connection | Validate ARN | `/api/v1/onboarding/verify` | POST | `onboarding/VerifyStep.jsx` |
| Skip button | Button | Skip | Skip onboarding | `/api/v1/onboarding/skip` | POST | `onboarding/ConnectStep.jsx` |
| Success screen | Card | All Set! | Navigate to dashboard | — | — | `onboarding/SuccessStep.jsx` |

**API module**: `onboardingAPI` → `getState()`, `getAwsLink(mode)`, `verify(roleArn)`, `skip()`
**Route**: `/onboarding` (ProtectedRoute, wraps `pages/Onboarding.jsx`)

---

## 2. Dashboard (Fleet Overview)

### 2.1 Main Dashboard

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Cost KPI card | Card | Total Monthly Cost | Display spend metric | `/api/v1/metrics/dashboard` | GET | `widgets/CostKPICard.jsx` |
| Savings KPI card | Card | Total Savings | Display savings metric | `/api/v1/metrics/dashboard` | GET | `widgets/SavingsKPICard.jsx` |
| Savings bar chart | Chart | Savings by Category | Visualize savings breakdown | `/api/v1/metrics/dashboard` | GET | `widgets/SavingsChart.jsx` |
| Fleet composition pie | Chart | Fleet Composition | Show instance type mix | `/api/v1/clusters` | GET | `widgets/FleetComposition.jsx` |
| Activity feed | List | Recent Activity | Show recent events | `/api/v1/audit/logs` | GET | `widgets/ActivityFeed.jsx` |
| Cluster health cards | Card grid | Cluster Health | Show cluster status | `/api/v1/clusters` | GET | `widgets/ClusterHealthCard.jsx` |
| Platform health | Card | Platform Health | Show system status | `/api/v1/admin/health` | GET | `widgets/PlatformHealthCard.jsx` |
| Pending approvals | Card | Pending Approvals | Show awaiting actions | `/api/v1/approvals/` | GET | `widgets/PendingApprovalsCard.jsx` |
| Agent status | Card | Agent Status | Show DaemonSet health (Full Fleet Visibility) | `/api/v1/admin/agent-fleet` | GET | `widgets/AgentStatusWidget.jsx` |
| Spend forecast | Chart | Spend Forecast | Predict future costs | `/api/v1/metrics/cost/timeseries` | GET | `widgets/SpendForecastWidget.jsx` |
| Trends chart | Area Chart | Fleet Trends | 30-day savings & spot trends | `/api/v1/multi-cluster/trends` | GET | `widgets/TrendsChart.jsx` |
| Tenant list | Table | Tenants | Show organizations | `/api/v1/admin/organizations` | GET | `widgets/TenantListCard.jsx` |
| Widget config | Modal | Customize Dashboard | Toggle widget visibility | `/api/v1/users/me/preferences` | PATCH | `Dashboard.jsx` |

**API modules**: `metricAPI`, `clusterAPI`, `auditAPI`, `multiClusterAPI`, `adminAPI`, `approvalsAPI`
**Route**: `/dashboard` → `components/dashboard/Dashboard.jsx`

---

## 3. Cluster Management

### 3.1 Cluster List & Details

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Cluster table | Table | Clusters | List all clusters | `/api/v1/clusters` | GET | `clusters/ClusterList.jsx` |
| Search input | Input | Search clusters | Filter cluster list | — (client-side) | — | `clusters/ClusterList.jsx` |
| Delete cluster btn | Button | Delete | Remove cluster | `/api/v1/clusters/{id}` | DELETE | `clusters/ClusterDeleteModal.jsx` |
| Disconnect agent btn | Button | Disconnect | Disconnect agent | `/api/v1/clusters/{id}/agent/disconnect` | POST | `clusters/ClusterDisconnectModal.jsx` |
| Cluster detail panel | Panel | Cluster Details | Show full cluster info | `/api/v1/clusters/{id}` | GET | `clusters/ClusterDetails.jsx` |
| Overview tab | Tab | Overview | Savings, spot ratio, cooldown | `/api/v1/clusters/{id}` + rebalancing | GET | `clusters/overview/OverviewTab.jsx` ✅ NEW |
| Node list table | Table | Nodes | Show cluster nodes | `/api/v1/clusters/{id}/nodes/detailed` | GET | `clusters/NodeList.jsx` |
| Node group breakdown | Chart | Node Groups | Breakdown by group | `/api/v1/clusters/{id}/nodes` | GET | `clusters/NodeGroupBreakdown.jsx` |
| Utilization sparkline | Chart | CPU/Mem Utilization | Inline utilization graph | `/api/v1/clusters/{id}/utilization` | GET | `clusters/ClusterUtilizationSparkline.jsx` |
| Health timeline | Timeline | Health Events | Show health history | `/api/v1/clusters/{id}` | GET | `clusters/ClusterHealthTimeline.jsx` |
| Spot ratio gauge | Gauge | Spot Ratio | Spot vs OD ratio | `/api/v1/clusters/{id}` | GET | `clusters/SpotRatioGauge.jsx` |
| Policy gap alert | Alert | Policy Gap | Show missing policies | — (derived) | — | `clusters/PolicyGapAlert.jsx` |
| Node template tab | Tab | Node Templates | Assign templates | `/api/v1/clusters/{id}/node-template/active` | GET | `clusters/NodeTemplateTab.jsx` |

### 3.2 Optimization Settings (within ClusterList)

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Auto-rebalance toggle | Toggle | Auto Rebalance | Enable/disable auto-rebalance | `/api/v1/clusters/{id}/optimization-settings` | PUT | `clusters/ClusterList.jsx` |
| Auto-rightsizing toggle | Toggle | Auto Rightsizing | Enable/disable rightsizing | `/api/v1/clusters/{id}/optimization-settings` | PUT | `clusters/ClusterList.jsx` |
| Maintain standby toggle | Toggle | Maintain Standby | Keep warm spare nodes | `/api/v1/clusters/{id}/optimization-settings` | PUT | `clusters/ClusterList.jsx` |
| Diversify pools toggle | Toggle | Diversify Spot Pools | Spread across pools | `/api/v1/clusters/{id}/optimization-settings` | PUT | `clusters/ClusterList.jsx` |
| Failure cooldown input | Input | Failure Cooldown (min) | Set cooldown minutes | `/api/v1/clusters/{id}/optimization-settings` | PUT | `clusters/ClusterList.jsx` |
| Save settings btn | Button | Save | Persist settings | `/api/v1/clusters/{id}/optimization-settings` | PUT | `clusters/ClusterList.jsx` |

**API modules**: `clusterAPI` → `getOptimizationSettings(id)`, `updateOptimizationSettings(id, settings)`, `getNodesDetailed(id)`, `disconnectAgent(id)`, `removeAgent(id)`, `optimize(id)`, `fallback(id)`
**Route**: `/clusters` → `components/clusters/ClusterList.jsx`

---

## 4. ASCP.AI (ML Engine)

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Pool rankings table | Table | ML Pool Rankings | Show ranked pools | `/api/v1/ascpai/pools/rankings` | POST | `ascpai/PoolRankings.jsx` |
| Global rankings card | Card | Global Rankings | Fleet-wide pool scores | `/api/v1/ascpai/pools/rankings` | POST | `ascpai/GlobalRankingsCard.jsx` |
| Blacklist monitor | Card | Risky Pools | Show blacklisted pools | `/api/v1/ascpai/blacklist` | GET | `ascpai/BlacklistMonitorCard.jsx` |
| Auto-rebalance audit | Card | Rebalance History | Recent rebalance actions | `/api/v1/ascpai/rebalancing/status` | GET | `ascpai/AutoRebalanceAuditCard.jsx` |
| Auto-rebalance modal | Modal | Rebalance Detail | Action detail + approve/deny | `/api/v1/ascpai/rebalancing-actions/{id}/approve` | POST | `ascpai/AutoRebalanceAuditModal.jsx` ✅ NEW |
| Rebalancing timeline | Timeline | Migration Progress | Live migration steps | `/api/v1/ascpai/rebalancing/status` | GET | `ascpai/RebalancingTimeline.jsx` |
| Volatility monitor | Card | Spot Volatility | Interruption rates | `/api/v1/ascpai/volatility/status` | GET | `ascpai/VolatilityMonitor.jsx` |
| Interruption heatmap | Heatmap | Interruption Heatmap | AZ risk visualization | `/api/v1/ascpai/volatility/status` | GET | `ascpai/InterruptionHeatmap.jsx` |
| Diversity gauge | Gauge | Pool Diversity | Instance type diversity | `/api/v1/ascpai/v3/diversity/{id}` | GET | `ascpai/DiversityGauge.jsx` |
| Optimization mode | Selector | Optimization Mode | Switch balanced/cost/perf | `/api/v1/ascpai/v3/cluster/{id}/optimization-mode` | PUT | `ascpai/OptimizationModeSelector.jsx` |
| Global intel panel | Panel | Global Intelligence | Region-wide insights | `/api/v1/ascpai/v3/global-intelligence/status` | GET | `ascpai/GlobalIntelligencePanel.jsx` |
| Workload classifier | Panel | Workload Classification | Stateless/Stateful tags | `/api/v1/ascpai/v3/workload-status/{id}` | GET | `ascpai/WorkloadClassificationPanel.jsx` |
| DE v3 dashboard | Dashboard | Decision Engine | Full DE metrics | `/api/v1/ascpai/v3/metrics` + multiple | GET | `ascpai/DecisionEngineV3Dashboard.jsx` |

**Key new API endpoints** (verified in api.js):
- `getNodeAlternatives(clusterId, nodeId)` → `/api/v1/ascpai/clusters/{id}/nodes/{nodeId}/alternatives`
- `getMarketView(clusterId)` → `/api/v1/ascpai/clusters/{id}/market-view`
- `getPoolAudit(clusterId, nodeId)` → `/api/v1/ascpai/clusters/{id}/nodes/{nodeId}/pool-audit`
- `getClusterSavings(clusterId)` → `/api/v1/ascpai/clusters/{id}/savings`
- `getSavingsVelocity(clusterId, days)` → `/api/v1/ascpai/savings-velocity`
- `getRebalancingContext(clusterId)` → `/api/v1/ascpai/v3/rebalancing-context/{id}`
- `approveRebalancingAction(actionId)` → `/api/v1/ascpai/rebalancing-actions/{id}/approve`
- `denyRebalancingAction(actionId)` → `/api/v1/ascpai/rebalancing-actions/{id}/deny`

**`AutoRebalanceAuditModal.jsx` — pool_change_reason display (Task 14)**:
Modal lines 72-89 display `pool_change_reason` field from the rebalancing action when present. This shows why a fallback pool was used (e.g., `"InsufficientInstanceCapacity on c6a.large"` or `"diversify_pools: duplicate pool"` or `"risk_threshold: 0.52 > 0.25"`). Implemented and working — NOT a missing feature.

**Route**: `/ascp-ai` → `pages/ASCPAiPage.jsx`

**WorkloadInspector cache-miss behavior** (backend, affects ASCP.AI + auto-rebalancer):
Cache ABSENT → async re-classification triggered + entire cluster skipped this cycle
Cache PRESENT → individual unclassified nodes filtered out

### Market View — Surface Clarification

PoolRankings.jsx (ASCP.AI page) has two sub-tabs:
  - Fleet Rankings: calls POST /api/v1/ascpai/pools/rankings (fleet-wide, no cluster context)
  - Market View: calls GET /api/v1/ascpai/clusters/{id}/market-view (per-cluster context)

ClusterDetails.jsx does NOT have a Market View tab.
Tabs in ClusterDetails: Overview, Optimization Settings, Node Template, Activity Log.

**Activity Log tab** (line 704): Renders the `rebalancingActions` state array (fetched from `GET /api/v1/ascpai/rebalancing/status`). Each entry shows action id, status, instance type, AZ, and timestamps. When the array is empty, a "No actions" placeholder is shown. This tab is fully implemented — not a stub.

### Market View — Pricing Data Pipeline & Redis Key Formats

The market view cache is built by `cache_builder.build_global_pool_cache()` (hourly beat) from
two sets of Redis keys. Both key format and value format are strict contracts:

| Key | Writer | Reader | Value format |
|---|---|---|---|
| `spot_price:{region}:{az}:{instance_type}` | `AWSPricingService._refresh_regional_pricing()` | `cache_builder` (json.loads → .get('price')) | JSON: `{"price": "0.0124", "timestamp": "..."}` |
| `od_price:{region}:{instance_type}` | `AWSPricingService.get_ondemand_price()` | `AWSPricingService` internal; `_lookup_od_price()` secondary fallback | Plain string: `"0.0464"` |
| `ondemand_price:{region}:{instance_type}` | `AWSPricingService.get_ondemand_price()` (dual write) + `pricing_collector` | `cache_builder._lookup_od_price()` (primary) | Plain string: `"0.0464"` |
| `market_view_cache:{region}` | `cache_builder.build_global_pool_cache()` | `GET /api/v1/ascpai/clusters/{id}/market-view` | JSON array of enriched pool dicts |
| `spot_advisor:{region}:{instance_type}:Linux` | `spot_advisor_scraper` (12h beat) | `_lookup_interruption_rate()` + fallback savings | JSON: `{"interruption_index": 0-4, "savings_percentage": 0-90}` |

**Spot_advisor fallback** (triggered when no `spot_price:*` keys exist):
- Uses `savings_percentage` from spot_advisor data: `spot_est = od_est × (1 - savings_pct/100)`
- Falls back to 70% savings estimate only when spot_advisor has no `savings_percentage` field
- All fallback pools marked `_is_estimated: True`

**Celery tasks driving the pipeline:**
- `workers.pricing.ingest_spot_prices` (every 10 min) → `_refresh_regional_pricing()` for all active regions
- `workers.pricing.refresh_ondemand` (every 12h) → `get_ondemand_price()` for all instance types per region
- `workers.pricing.refresh_regional_pricing` (every 10 min) → `refresh_regional_pricing_batch()` (spot + OD combined)
- `build_global_pool_cache` (hourly) → reads above keys, builds `market_view_cache:{region}`

---

## 5. Right-Sizing Dashboard

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Main dashboard | Page | Right-Sizing | Full rightsizing UI | Multiple | GET/POST | `right-sizing/RightSizingDashboard.jsx` |
| Karpenter tab | Tab | Karpenter Config | Karpenter-specific config tab | `/api/v1/karpenter/config` | GET/PATCH | `right-sizing/RightSizingKarpenterTab.jsx` ✅ NEW |

**Inline sub-components** (inside `RightSizingDashboard.jsx`):
- `AutoModeBanner` — shows auto-rebalance ON/OFF status
- `ClusterHealthExposureBar` — 4 node count cards (Total/Stateless/Stateful/Eligible)
- `ResizeGuardMonitoringPanel` — guard & stability metrics
- `StatelessSection` — node table with Apply buttons + Apply All
- `StatefulSection` — stateful node table with Request Approval
- `StatelessDetailedDrawer` — node detail modal
- `StatefulProposalModal` — OD resize approval flow
- `KarpenterConfigPanel` — strategy, spot%, families, feature toggles

**API modules**: `clusterAPI`, `karpenterAPI`, `ascpaiAPI`, `optimizationAPI`

**Key API calls verified**:
- `karpenterAPI.getRecommendations(clusterId)` → `/api/v1/karpenter/recommendations`
- `karpenterAPI.applyRecommendation(id, data)` → `/api/v1/karpenter/apply-recommendation/{id}`
- `karpenterAPI.batchApplyRecommendations(ids)` → `/api/v1/karpenter/apply-recommendations/batch`
- `karpenterAPI.updateConfig(clusterId, data)` → `/api/v1/karpenter/config/{clusterId}` PATCH
- `karpenterAPI.getHistory(clusterId)` → `/api/v1/karpenter/history`
- `optimizerCoordinatorAPI.listProposals(clusterId)` → `/api/v1/optimizer/proposals/{id}`
- `optimizerCoordinatorAPI.approveProposal(id)` → `/api/v1/optimizer/proposals/{id}/approve`

**Route**: `/right-sizing` → `components/right-sizing/RightSizingDashboard.jsx`

---

## 6. Hibernation Management

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Cluster overview cards | Card grid | Overview | Hibernation stats | `/api/v1/hibernation/schedules` | GET | `hibernation/ClusterOverview.jsx` |
| Dashboard tab | Tab | Dashboard | Summary view | `/api/v1/hibernation/schedules` | GET | `hibernation/DashboardTab.jsx` |
| Schedule calendar | Calendar | Schedule Calendar | Visual calendar view | `/api/v1/hibernation/schedules` | GET | `hibernation/ScheduleCalendar.jsx` |
| Schedule matrix | Grid | Schedule Matrix | Weekly hour matrix | `/api/v1/hibernation/schedules` | GET | `hibernation/ScheduleMatrix.jsx` |
| Schedule builder | Form | Schedule Builder | Create/edit schedule | `/api/v1/hibernation/schedules` | POST | `hibernation/ScheduleBuilder.jsx` |
| Schedule modal | Modal | Create Schedule | Full schedule form | `/api/v1/hibernation/schedules` | POST/PUT | `hibernation/ScheduleModal.jsx` |
| Hibernation wizard | Wizard | Setup Wizard | Guided schedule setup | `/api/v1/hibernation/schedules` | POST | `hibernation/HibernationWizard.jsx` |
| Strategy selector | Radio group | Strategy | Choose hibernation strategy | `/api/v1/hibernation/strategies` | GET | `hibernation/StrategySelector.jsx` |
| Hibernation type card | Card | Type Selection | Full/Partial/Custom | — | — | `hibernation/HibernationTypeCard.jsx` |
| Status banner | Banner | Status | Current hibernation state | `/api/v1/hibernation/schedules` | GET | `hibernation/StatusBanner.jsx` |
| Header | Header | Hibernation | Title + cluster selector | `/api/v1/clusters` | GET | `hibernation/HibernationHeader.jsx` |
| Emergency controls | Panel | Emergency Controls | Force wake/sleep | `/api/v1/hibernation/schedules/{id}/override` | POST | `hibernation/EmergencyControls.jsx` |
| Time-based rules | Form | Time Rules | Define schedule rules | — | — | `hibernation/TimeBasedRules.jsx` |
| Multi-timezone | Panel | Timezone Config | Set timezone for schedule | — | — | `hibernation/MultiTimezone.jsx` |
| Unified schedule grid | Grid | Schedule Grid | Full schedule view | `/api/v1/hibernation/schedules` | GET | `hibernation/UnifiedScheduleGrid.jsx` |
| Validation panel | Panel | Validation | Schedule validation | — | — | `hibernation/ValidationPanel.jsx` |
| Conflict detection modal | Modal | Conflict Detection | Overlapping schedule warn | — (client-side + backend `HibernationService._check_matrix_overlap`) | — | `hibernation/ConflictDetectionModal.jsx` |
| Advanced config | Panel | Advanced | Drain settings, grace | — | — | `hibernation/AdvancedConfiguration.jsx` |
| Cost analytics | Chart | Cost Savings | Hibernation savings | `/api/v1/metrics/cost` | GET | `hibernation/CostAnalytics.jsx` |
| Cost analytics dashboard | Dashboard | Cost Dashboard | Full cost analytics | `/api/v1/billing/costs/summary` | GET | `hibernation/CostAnalyticsDashboard.jsx` |
| Execution history | Table | History | Past hibernation events | `/api/v1/audit/logs` | GET | `hibernation/ExecutionHistory.jsx` |
| Audit history | Table | Audit | Detailed change log | `/api/v1/audit/logs` | GET | `hibernation/AuditHistory.jsx` |
| History log | List | History Log | Quick event log | — | — | `hibernation/HistoryLog.jsx` |
| Notification settings | Form | Notifications | Alert preferences | — | — | `hibernation/NotificationSettings.jsx` |
| HibernationDashboardNew | Page | Hibernation | Main hibernation page | Multiple | GET/POST | `hibernation/HibernationDashboardNew.jsx` |
| Hibernation scheduler | Form | Scheduler | Full scheduler | `/api/v1/hibernation/schedules` | POST/PUT | `hibernation/HibernationScheduler.jsx` |

**API module**: `hibernationAPI` → `list()`, `getByCluster(clusterId)`, `create()`, `update()`, `delete()`, `toggle()`, `override()`, `getStrategies()`
**Route**: `/hibernation/:clusterId?` → exported as `HibernationDashboard` from `components/hibernation/index.js`

**Backend conflict detection** (`backend/services/hibernation_service.py`):
- `_check_matrix_overlap(m1, m2, t1, t2)` — converts all schedule types to a 744-slot monthly array before comparing.
  - WEEKLY (168 slots) → tiled ×5 to 744 slots
  - DAILY (24 slots) → tiled ×31 to 744 slots
  - MONTHLY (744 slots) → used directly
  - Returns slot overlap count; any value > 0 is a conflict

**Hibernation strategies** — `StrategySelector.jsx` exposes three options from `GET /api/v1/hibernation/strategies`:

| Strategy | Mechanism | Savings | Wake Time | Risk |
|---|---|---|---|---|
| `NAMESPACE_SLEEP` | Scales all Deployment/StatefulSet replicas to 0 via K8s PATCH | ~80% | ~2 min | Low |
| `NUCLEAR` | Terminates all worker nodes (sets ASG desired=0) | ~70% | ~5 min | Medium |
| `SNAPSHOT_RESTORE` | EBS volume snapshot for each node + executes Nuclear | ~95% | ~15 min | High |

**Savings calculation**: `sleep_hours × cluster_hourly_cost × strategy_savings_pct`. `annual_savings = weekly_savings × 52`.

**Savings consistency note**: The `savings_map` dict in `hibernation_service.py` stores savings as decimals (`NAMESPACE_SLEEP: 0.80`, `NUCLEAR: 0.70`, `SNAPSHOT_RESTORE: 0.95`). The `GET /api/v1/hibernation/strategies` API returns them as integers (`80`, `70`, `95`). `StrategySelector.jsx` receives the integer form from the API. The internal decimal and the API integer represent the same values — the conversion is consistent and there is no mismatch between the hardcoded `savings_map` dict and the API response. Any future change to `savings_map` percentages must also update the API serialization layer to remain consistent.

---

## 7. Resource Hygiene (Cleanup)

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Cleanup dashboard | Page | Resource Hygiene | Main cleanup page | `/api/v1/hygiene/scan/{accountId}` | GET | `cleanup/CleanupDashboard.jsx` |
| Hero metrics panel | Cards | Summary | Waste/savings metrics | `/api/v1/hygiene/total-cost` | GET | `cleanup/summary/HeroMetricsPanel.jsx` |
| Savings gauge | Gauge | Savings Gauge | Visual savings donut | — (derived) | — | `cleanup/summary/SavingsGauge.jsx` |
| Resource table | Table | Resources | Wasteful resource list | `/api/v1/hygiene/scan/{id}` | GET | `cleanup/tables/ResourceTable.jsx` |
| Cleanup sidebar | Sidebar | Categories | Resource type filter | `/api/v1/hygiene/cost-services` | GET | `cleanup/layout/CleanupSidebar.jsx` |
| Filter panel | Panel | Filters | Region/type filters | — (client-side) | — | `cleanup/layout/FilterPanel.jsx` |
| Delete/cleanup button | Button | Clean Up | Execute cleanup action | `/api/v1/hygiene/action` | POST | `cleanup/CleanupDashboard.jsx` |
| Bulk tag wizard | Wizard | Bulk Tag | Tag multiple resources | — | — | `cleanup/BulkTagWizard.jsx` |
| RDS wizard | Wizard | RDS Cleanup | RDS-specific cleanup | `/api/v1/hygiene/scan/{id}` | GET | `cleanup/wizards/RDSWizard.jsx` |
| RI wizard | Wizard | RI Analysis | RI cleanup wizard | `/api/v1/hygiene/scan/{id}` | GET | `cleanup/wizards/RIWizard.jsx` |
| S3 wizard | Wizard | S3 Tiering | S3 tier wizard | `/api/v1/hygiene/scan/{id}` | GET | `cleanup/wizards/S3Wizard.jsx` |

**API module**: `hygieneAPI` (also exported as `cleanupAPI`) → `scan(accountId)`, `execute(payload, accountId)`, `getTotalCost(accountId)`, `getCostServices(accountId)`, `getScanHistory(accountId, days)`, `checkDependencies()`, `discover()`
**Route**: `/hygiene` → `components/cleanup/CleanupDashboard.jsx`

---

## 8. Settings & Tag Governance

### 8.1 Settings

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Settings page | Page | Settings | Main tabs container | Multiple | GET | `settings/Settings.jsx` |
| Account settings | Tab | Account | Profile & org info | `/api/v1/auth/me` | GET | `settings/AccountSettings.jsx` |
| Cloud integrations | Tab | Integrations | AWS account mgmt | `/api/v1/accounts` | GET | `settings/CloudIntegrations.jsx` |
| Team management | Tab | Team Members | Invite/remove members | `/api/v1/organization/members` | GET | `settings/TeamManagement.jsx` |
| Team governance | Tab | Team Governance | Team-level policies | `/api/v1/teams/{id}/governance` | PUT | `settings/TeamGovernance.jsx` |
| Member permissions modal | Modal | Permissions | Edit member permissions | `/api/v1/users/{id}/permissions` | POST | `settings/MemberPermissionsModal.jsx` |
| Governance settings | Page | Automation Settings | Autopilot & approvals | `/api/v1/governance/policies` | GET/PATCH | `settings/GovernanceSettings.jsx` |
| Governance manager | Component | Governance | Governance wrapper | — | — | `settings/GovernanceManager.jsx` |

### 8.2 Tag Governance

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Tag governance page | Page | Tag Governance | Full tag mgmt page | Multiple | GET/POST | `settings/TagGovernancePage.jsx` |
| Tag policies list | Table | Tag Policies | List tag policies | `/api/v1/tags/policies/` | GET | `settings/TagPoliciesList.jsx` |
| Tag policies manager | Page | Tagging Policies | Tag policy CRUD | `/api/v1/tags/policies/` | GET/POST/PUT/DELETE | `settings/TagPoliciesManager.jsx` |

**API modules**: `authAPI`, `accountAPI`, `organizationAPI`, `teamAPI`, `governanceAPI`, `tagPolicyAPI`, `tagTemplateAPI`, `tagAutomationAPI`, `tagScoringAPI`, `tagComplianceAPI`
**Routes**: `/settings`, `/tagging-policies`, `/automation-settings`

---

## 9. Policies & Governance

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Policy config page | Page | Policies | Create/edit policies | `/api/v1/policies` | GET/POST/PUT | `policies/PolicyConfig.jsx` |
| Policy toggle | Toggle | Enable/Disable | Toggle policy active | `/api/v1/policies/{id}/toggle` | POST | `policies/PolicyConfig.jsx` |
| Permission matrix | Table | Permissions | Feature-role matrix | `/api/v1/permissions/feature-registry` | GET | `policies/PermissionMatrix.jsx` |
| Cleanup policies | Tab | Cleanup Policies | Resource cleanup rules | `/api/v1/policies` | GET | `policies/CleanupPolicies.jsx` |
| Permission gate | Wrapper | — | Feature access guard | `/api/v1/permissions/check` | POST | `governance/PermissionGate.jsx` |
| Protected button | Button | — | Permission-gated action | `/api/v1/permissions/check` | POST | `governance/ProtectedButton.jsx` |
| Active JIT banner | Banner | Active Access | Show JIT access status | `/api/v1/approvals/my-jit-approvals` | GET | `governance/ActiveJITBanner.jsx` |
| JIT request modal | Modal | Request Access | JIT access form | `/api/v1/approvals/jit-request` | POST | `governance/JITRequestModal.jsx` |

**Route**: `/policies` → `components/policies/PolicyConfig.jsx`

---

## 10. Approvals

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Approvals page | Page | Approvals | List all approvals | `/api/v1/approvals/` | GET | `pages/Approvals.jsx` |
| Approve button | Button | Approve | Approve request | `/api/v1/approvals/{id}/approve` | POST | `pages/Approvals.jsx` |
| Reject button | Button | Reject | Reject request | `/api/v1/approvals/{id}/reject` | POST | `pages/Approvals.jsx` |
| Revoke button | Button | Revoke | Revoke access | `/api/v1/approvals/{id}/revoke` | POST | `pages/Approvals.jsx` |
| Ticket request modal | Modal | Create Ticket | Submit approval request | `/api/v1/approvals/` | POST | `approvals/TicketRequestModal.jsx` |
| Access request modal | Modal | Request Access | Feature access request | `/api/v1/approvals/jit-request` | POST | `approvals/AccessRequestModal.jsx` |

> ⚠️ `TicketRequestModal` is also registered globally in `App.js` (L156) and triggered via `governance:required` CustomEvent on 403 responses.

**API module**: `approvalsAPI` (also exported as `approvalAPI`, `ticketAPI`, `ticketsAPI`)
**Route**: `/approvals` → `pages/Approvals.jsx`

**Rebalancing action approval flow** (when `manual_approval_required=True` on a cluster):
- Rebalancing action is created with `status=pending_approval` instead of `in_progress`
- `AutoRebalanceAuditCard.jsx` and `AutoRebalanceAuditModal.jsx` show pending items
- `approveRebalancingAction(id)` → `POST /api/v1/rebalancing-actions/{id}/approve` → action transitions to `in_progress`; auto_rebalancer picks up on next 15s cycle
- `denyRebalancingAction(id)` → `POST /api/v1/rebalancing-actions/{id}/deny` → action transitions to `failed`
- No auto-approve timeout; actions expire after `approval_expiry_hours` (default 24h) via `approval_cleanup` Celery beat (every 5 min)

---

## 11. Admin Panel (SUPER_ADMIN)

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Admin dashboard | Page | Admin Dashboard | Platform overview | `/api/v1/admin/dashboard` | GET | `admin/AdminDashboard.jsx` |
| Admin overview | Tab | Overview | Summary stats | `/api/v1/admin/stats` | GET | `admin/AdminOverview.jsx` |
| Client management | Page | Clients | Manage users | `/api/v1/admin/clients` | GET | `admin/AdminClients.jsx` |
| Toggle client | Button | Enable/Disable | Toggle client status | `/api/v1/admin/clients/{id}/toggle` | POST | `admin/AdminClients.jsx` |
| Reset password | Button | Reset Password | Force password reset | `/api/v1/admin/clients/{id}/reset-password` | POST | `admin/AdminClients.jsx` |
| Organization mgmt | Page | Organizations | Manage orgs | `/api/v1/admin/organizations` | GET | `admin/AdminOrganizations.jsx` |
| Toggle org | Button | Enable/Disable | Toggle org status | `/api/v1/admin/organizations/{id}/toggle` | POST | `admin/AdminOrganizations.jsx` |
| Impersonate btn | Button | Impersonate | Login as org | `/api/v1/admin/impersonate` | POST | `admin/AdminOrganizations.jsx` |
| Health monitor | Page | System Health | Backend health checks | `/api/v1/admin/health` | GET | `admin/AdminHealth.jsx` |
| Experiments lab | Page | Experiments | A/B test management | `/api/v1/lab/experiments` | GET/POST | `admin/AdminExperiments.jsx` |
| Platform config | Page | Configuration | Feature flags | — | — | `admin/AdminConfig.jsx` |
| Platform settings | Tab | Settings | Platform-level config | — | — | `admin/PlatformSettings.jsx` |
| Billing dashboard | Page | Billing | Billing overview | `/api/v1/admin/billing` | GET | `admin/AdminBilling.jsx` |

**New API endpoints** (verified in api.js):
- `adminAPI.getCircuitBreakers()` → `/api/v1/admin/circuit-breakers` ✅ NEW
- `adminAPI.resetCircuitBreaker(clusterId)` → `/api/v1/admin/circuit-breakers/{id}/reset` ✅ NEW

**Routes**: `/admin`, `/admin/clients`, `/admin/health`, `/admin/experiments`, `/admin/config`, `/admin/organizations`, `/admin/billing` (all AdminRoute)

---

## 12. Teams & Roles

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Teams page | Page | Teams | List all teams | `/api/v1/teams/` | GET | `pages/Teams.jsx` |
| Create team btn | Button | Create Team | Create new team | `/api/v1/teams/` | POST | `pages/Teams.jsx` |
| Team details page | Page | Team Details | Team detail + members | `/api/v1/teams/{id}` | GET | `pages/TeamDetails.jsx` |
| Members tab | Tab | Members | Team member list | `/api/v1/teams/{id}` | GET | `teams/MembersTab.jsx` |
| Teams tab | Tab | Teams | Teams overview | `/api/v1/teams/` | GET | `teams/TeamsTab.jsx` |
| Roles & policies tab | Tab | Roles & Policies | Role management | `/api/v1/roles` | GET | `teams/RolesPoliciesTopTab.jsx` |
| Roles page | Page | Roles | Full RBAC management | `/api/v1/roles` | GET/POST/PUT/DELETE | `pages/Roles.jsx` |
| Invite member btn | Button | Invite | Invite team member | `/api/v1/teams/{id}/invite` | POST | `pages/TeamDetails.jsx` |

**Routes**: `/teams`, `/teams/:teamId`, `/roles`

---

## 13. Cost Analysis Pages

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Account analytics | Page | Account Analytics | Per-account cost view | `/api/v1/metrics/accounts/{id}/summary` | GET | `pages/AccountAnalytics.jsx` |
| RI analysis | Page | RI Analysis | Reserved Instance recs | `/api/v1/ri/` | GET | `ri/RIAnalysis.jsx` |
| RI health card | Card | RI Utilization | RI utilization gauge | `/api/v1/ri/` | GET | `ri/RIHealthCard.jsx` |
| S3 analysis | Page | S3 Tiering | S3 tier recommendations | `/api/v1/s3/` | GET | `s3/S3Analysis.jsx` |
| S3 health card | Card | S3 Storage Health | S3 tiering summary | `/api/v1/s3/overview` | GET | `s3/S3HealthCard.jsx` |
| RDS analysis | Page | RDS Analysis | RDS recommendations | `/api/v1/rds/` | GET | `rds/RDSAnalysis.jsx` |
| RDS health card | Card | RDS Health | RDS metrics | `/api/v1/rds/` | GET | `rds/RDSHealthCard.jsx` |
| Transfer analysis | Page | Data Transfer | Transfer cost analysis | `/api/v1/transfer/` | GET | `transfer/TransferAnalysis.jsx` |
| Transfer health card | Card | Data Transfer Health | Transfer cost summary | `/api/v1/transfer/overview` | GET | `transfer/TransferHealthCard.jsx` |

**Routes**: `/accounts/:accountId/analytics`, `/ri-analysis`, `/s3-analysis`, `/rds-analysis`, `/transfer-analysis`

**Backend service implementations** (all 4 are real services, not Cost Explorer pass-throughs):

| Feature | Routes File | Service Class | Key Backend Endpoints |
|---|---|---|---|
| Reserved Instances | `api/ri_routes.py` | `RIAnalysisService` | `GET /api/v1/ri/overview` (utilization stats, waste metrics), `POST /api/v1/ri/analyze` (7/30/90-day lookback), `POST /api/v1/ri/execute-action` (actions: `sell_marketplace`, `modify`, `convert`, `monitor`), `GET /api/v1/ri/savings-plans`, `GET /api/v1/ri/coverage` |
| S3 Tiering | `api/s3_routes.py` | `S3TieringService` | `GET /api/v1/s3/overview` (bucket count, tier waste, recommendations), `POST /api/v1/s3/analyze` (trigger cross-account analysis) |
| RDS Optimization | `api/rds_routes.py` | `RDSAnalysisService` | `GET /api/v1/rds/overview` (Multi-AZ waste, idle instances), `POST /api/v1/rds/analyze` (Multi-AZ configuration recommendations) |
| Data Transfer | `api/transfer_routes.py` | `TransferAnalysisService` | `GET /api/v1/transfer/overview` (cross-AZ + egress cost breakdown), `POST /api/v1/transfer/analyze` (traffic pattern analysis) |

---

## 14. Audit Log

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Audit log page | Page | Audit Logs | View system audit events | `/api/v1/audit/logs` | GET | `audit/AuditLog.jsx` |
| Export logs | Button | Export | Download logs | `/api/v1/audit/export` | GET | `audit/AuditLog.jsx` |

**Route**: `/audit` → `components/audit/AuditLog.jsx`

---

## 15. Node Templates

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Templates page | Page | Node Templates | Global template registry | `/api/v1/node-templates` | GET | `pages/NodeTemplates.jsx` |
| Create template btn | Button | Create Template | New template form | `/api/v1/node-templates` | POST | `pages/NodeTemplates.jsx` |
| Delete template btn | Button | Delete | Remove template | `/api/v1/node-templates/{id}` | DELETE | `pages/NodeTemplates.jsx` |
| Version list | Table | Versions | Template versions | `/api/v1/node-templates/{id}/versions` | GET | `pages/NodeTemplates.jsx` |
| Validate btn | Button | Validate | Check template | `/api/v1/node-templates/validate` | POST | `pages/NodeTemplates.jsx` |

**Route**: `/node-templates` → `pages/NodeTemplates.jsx`

---

## 16. Shared / Reusable Components

| Component | Type | File | Notes |
|---|---|---|---|
| Button | Button | `shared/Button.jsx` | variant, size, onClick, disabled |
| Card | Container | `shared/Card.jsx` | children, style |
| Input | Input | `shared/Input.jsx` | label, value, onChange, type |
| Badge | Badge | `shared/Badge.jsx` | color, children |
| Switch | Toggle | `shared/Switch.jsx` | checked, onChange |
| Dropdown | Select | `shared/Dropdown.jsx` | options, value, onChange |
| EmptyState | Placeholder | `shared/EmptyState.jsx` | message, icon |
| StatsCard | Card | `shared/StatsCard.jsx` | title, value, trend |
| GaugeChart | Chart | `shared/GaugeChart.jsx` | value, max, label |
| RiskBadge | Badge | `shared/RiskBadge.jsx` | level (low/med/high) |
| NotificationPanel | Panel | `shared/NotificationPanel.jsx` | — |
| ErrorBoundary | Error Guard | `shared/ErrorBoundary.jsx` | ✅ NEW — wraps component trees to catch render errors |

---

## 17. Layout & Global

| Component | Type | Responsibility | File |
|---|---|---|---|
| MainLayout | Shell | Sidebar + header + content area | `layout/MainLayout.jsx` |
| App.js | Router | Route definitions + auth guards (381 lines) | `App.js` |
| ProtectedRoute | Guard | Auth-required wrapper | `App.js` |
| AdminRoute | Guard | SUPER_ADMIN role wrapper | `App.js` |
| PublicRoute | Guard | Redirect authenticated users | `App.js` |
| PermissionGate | Guard | Feature-level access control via `featureId` prop | `governance/PermissionGate.jsx` |

**PermissionGate** wraps most routes in `App.js` — checks `featureId` via `POST /api/v1/permissions/check`.

---

## 18. Multi-Cluster Fleet

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Fleet summary | Card | Fleet Summary | Aggregated fleet metrics | `/api/v1/multi-cluster/summary` | GET | `dashboard/Dashboard.jsx` |
| Fleet actions | Feed | Fleet Actions | Recent fleet actions | `/api/v1/multi-cluster/actions` | GET | `dashboard/Dashboard.jsx` |
| Fleet trends chart | Area Chart | Fleet Trends | 30-day trends | `/api/v1/multi-cluster/trends` | GET | `dashboard/widgets/TrendsChart.jsx` |

**API module**: `multiClusterAPI` → `getSummary()`, `getActions(limit)`, `getTrends(days)`

---

## 19. Optimizer Coordinator Dashboard

| UI Element | Type | Label | Action | API Endpoint | Method | File |
|---|---|---|---|---|---|---|
| Optimizer status panel | Panel | Optimizer Status | Show evaluation state | `/api/v1/optimizer/status/{id}` | GET | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Trigger evaluation btn | Button | Trigger Evaluation | Run optimization cycle | `/api/v1/optimizer/evaluate/{id}` | POST | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Proposals table | Table | Proposals | List proposals | `/api/v1/optimizer/proposals/{id}` | GET | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Approve proposal btn | Button | Approve | Approve a proposal | `/api/v1/optimizer/proposals/{id}/approve` | POST | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Reject proposal btn | Button | Reject | Reject a proposal | `/api/v1/optimizer/proposals/{id}/reject` | POST | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| EV comparison panel | Panel | Expected Value | Before/after comparison | `/api/v1/optimizer/comparison/{id}` | GET | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Trust phase indicator | Badge | Trust Phase | Show Observer/Advisor/Auto | `/api/v1/optimizer/trust-phase/{id}` | GET | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Resize guard status | Panel | Resize Guard | Show guard state | `/api/v1/optimizer/resize-guard/{id}` | GET | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Circuit breaker status | Panel | Circuit Breaker | Show breaker state | `/api/v1/optimizer/circuit-breaker/{id}` | GET | `optimizer/OptimizerCoordinatorDashboard.jsx` |
| Initialize cluster btn | Button | Initialize | Set up cluster optimizer | `/api/v1/optimizer/initialize/{id}` | POST | `optimizer/OptimizerCoordinatorDashboard.jsx` |

**API module**: `optimizerCoordinatorAPI`

---

## 20. Backend-Only Routes (No Direct UI Component)

| Backend Route File | Prefix | Purpose | Consumers |
|---|---|---|---|
| `agent_routes.py` | `/api/v1/agent/` | DaemonSet agent heartbeat & reporting | Agent DaemonSet |
| `ai_agent_routes.py` | `/api/v1/ai-agent/` | AI-driven remediation agent | Automated backend |
| `decision_routes.py` | `/api/v1/decision/` | Decision engine logs (`decisionEngineAPI.getLogs`) | `decisionEngineAPI` in `api.js` |
| `health_routes.py` | `/api/v1/health` | Liveness/readiness probe | Docker/K8s |
| `installer_routes.py` | `/api/v1/installer/` | Agent installer script generation | Onboarding flow |
| `pod_metrics_routes.py` | `/api/v1/pod-metrics/` | Pod-level CPU/memory metrics | `optimizationAPI` in `api.js` |
| `worker_routes.py` | `/api/v1/worker/` | Agent-reported metrics ingestion | Agent DaemonSet |
| `metrics_routes.py` (rejections) | `/api/v1/metrics/rejections/{clusterId}` | Decision engine rejection counters | `metricAPI.getRejectionCounters()` |
| `metrics_routes.py` (health-timeline) | `/metrics/cluster/{id}/health-timeline` (no `/api/v1` prefix) | Cluster health event timeline | `ClusterHealthTimeline.jsx` (on-mount fetch) |

**Authentication note (agent_routes.py)**: ALL endpoints in `agent_routes.py` require `validate_api_key`. The orchestrator-specific endpoints (`GET /agents/orchestrator/{cluster_id}/pending-commands`, `POST /agents/orchestrator/{cluster_id}/command-result`) were previously unauthenticated — fixed with explicit `validate_api_key` dependency (lines ~362, ~409). These are NOT listed in the table above because they are under `/api/v1/agents/`, not `/api/v1/agent/`.

**WebSocket / role separation note (agent_routes.py)**: Both DaemonSet pods and Orchestrator pods run the same binary. The WebSocket client starts in ALL pods, but DaemonSet pods use only the HTTP polling endpoints (`/agents/actions/pending`, `/agents/actions/{action_id}/result`). The WebSocket connection established by DaemonSet pods is not used for orchestration. The component inventory description "DaemonSet agent heartbeat & reporting" describes the primary use case — it is not a clean architectural separation.

**ClusterHealthTimeline traceability note**: The route `GET /metrics/cluster/{cluster_id}/health-timeline` has no `/api/v1` prefix and passes through Nginx directly. If the Nginx proxy rule changes, `ClusterHealthTimeline.jsx` will fail silently. Backend source: `backend/api/metrics_routes.py`.

### Billing Routes — /api/v1/billing/...
(`backend/api/billing_routes.py`)

| Endpoint | Method | Purpose |
|---|---|---|
| `/billing/create-portal-session` | POST | Create Stripe billing portal session |
| `/billing/webhook/stripe` | POST | Stripe webhook for subscription events |
| `/billing/status` | GET | Billing/subscription status for organization |
| `/billing/costs/summary` | GET | Cost summary with compute/resource breakdown |
| `/billing/costs/daily` | GET | Daily cost trend for last N days |
| `/billing/costs/by-service` | GET | Cost breakdown by AWS service |
| `/billing/costs/sync-status` | GET | AWS Cost Explorer sync status |
| `/billing/costs/sync` | POST | Trigger manual Cost Explorer sync |

### Admin Routes — /api/v1/admin/...
(`backend/api/admin_routes.py`, SUPER_ADMIN role required)

| Endpoint | Method | Purpose |
|---|---|---|
| `/admin/organizations` | GET | List all organizations (paginated) |
| `/admin/organizations/{org_id}/toggle` | POST | Toggle org active status |
| `/admin/clients` | GET | List all client users |
| `/admin/clients/{id}` | GET | Get client details |
| `/admin/clients/{id}/toggle` | POST | Toggle client active status |
| `/admin/clients/{id}/reset-password` | POST | Reset client password |
| `/admin/stats` | GET | Platform-wide stats |
| `/admin/health` | GET | Platform health status |
| `/admin/billing` | GET | Platform billing overview |
| `/admin/dashboard` | GET | Admin dashboard aggregate stats |
| `/admin/agent-fleet` | GET | All clusters with agent installed + fleet status |
| `/admin/config/{key}` | GET | Get system config value |
| `/admin/config` | PATCH | Update system config |
| `/admin/platform/connection` | GET | Platform AWS connection status |
| `/admin/impersonate` | POST | Impersonate an organization |
| `/admin/platform/connect` | POST | Connect platform AWS identity |
| `/admin/platform/disconnect` | DELETE | Disconnect platform AWS identity |
| `/admin/circuit-breakers` | GET | All circuit breaker states |
| `/admin/circuit-breakers/{cluster_id}/reset` | POST | Reset circuit breaker to NORMAL |

**Known operator gap — `cluster_baselines` table**: There is no admin UI endpoint or operator tool to surface or create missing `ClusterBaseline` rows. Clusters onboarded before the `cluster_baselines` table was added will use a Redis fallback for savings calculations (drift-affected numbers). There is no automated backfill task as of 2026-03-24. Operators must act via direct DB access:
1. Identify affected clusters: `SELECT id FROM clusters WHERE id NOT IN (SELECT cluster_id FROM cluster_baselines);`
2. Create a baseline row manually via the `savings_calculator` service `compute_baseline()` method, or directly insert into the `cluster_baselines` table.

Until a `ClusterBaseline` row exists, the `SavingsCalculator` service silently falls back to Redis on-demand prices for that cluster, producing savings numbers that drift with AWS price changes rather than being anchored to the original cluster cost.

**`cluster_cooldown_states` table (Issue 13)**: DB-backed stabilization lock state. Written by `CooldownController.acquire_stabilization_lock()` (model: `ClusterCooldownState` in `backend/models/cluster.py`). Migration: `20260325_add_max_concurrent_and_cooldown_states`. Schema: `cluster_id` (PK, FK→clusters), `stabilization_until` (DateTime), `last_action_at` (DateTime), `updated_at`. Queried by `auto_rebalancer.py` Guard 2 when `spot:stabilization_lock:{cluster_id}` is absent from Redis. If `stabilization_until > utcnow()`, remaining seconds are re-hydrated into Redis.

**`max_concurrent_rebalance_actions` column (Issue 12)**: Added to `cluster_optimization_settings` (Integer, nullable). Default NULL treated as 1 (preserve one-at-a-time behavior). Migration: `20260325_add_max_concurrent_and_cooldown_states`. Used by `auto_rebalancer.py` before creating a new `RebalancingAction` — if active actions count >= this value, creation is skipped.

### Two Execution Paths (provision-before-cordon by design)

SubstituteManager path (execution_controller.py):
  Pre-warms replacement node → then CORDON/DRAIN/TERMINATE source

Auto-rebalancer Pillar 1 (auto_rebalancer.py):
  Provisions spot node → waits → then CORDON/DRAIN/TERMINATE source
  Both paths are intentional: avoids stranded cordoned nodes on launch failure.

### Phase 2 Failure Safeguards (auto_rebalancer.py — P-H2, P-H3, P-C3)

Three safeguards added to the CORDON and DRAIN failure paths:

**P-C3 — ASG suspend flag committed early**: `action_metadata = {'asg_suspended': True, 'asg_name_used': _asg_name}` is committed to DB immediately after `suspend_asg_processes()` succeeds — before any code that can throw. Exception handler reads this flag to decide whether to resume the ASG. Without this commit, a crash left the ASG permanently frozen.

**P-H2 — Stabilization lock on failure**: `CooldownController.acquire_stabilization_lock()` is called at both CORDON and DRAIN failure paths, before rolling back. Prevents a new `RebalancingAction` from being created on the same cluster while rollback UNCORDON is still in-flight (was: 15-second re-flap window with zero protection).

**P-H3 — Immediate backoff key on failure**: On CORDON or DRAIN failure, `spot:rebalanced:instance:{_wa_instance_id}` is now written with an exponential backoff TTL (minimum 60s) instead of being deleted. The delete created a window during rollback where a new action could re-cordon the same node while uncordon was still running.

### Emergency Rebalancer Fix (P-C1)

`RebalancingAction` is now created with correct model fields only:
- Valid: `trigger`, `source_pool`, `target_pool`, `status`, `started_at`, `source_instance_id`, `action_metadata`
- Invalid (removed): `id=generate_uuid()`, `source_instance_type`, `source_az`, `action_type`, `trigger_reason`, `created_at`

Prior to this fix, DB writes failed silently — interrupted nodes were never cordoned or drained.

### Stale Action Expiry — Orphan EC2 Cleanup (P-C2)

The stale `RebalancingAction` expiry loop (>45 min `in_progress`/`waiting_agent`) now checks `action_metadata['replacement_spot_instance_id']`. If set, calls `_do_rollback_terminate_orphan_spot()` to terminate the orphan EC2. Without this, each timed-out action left a running spot node not tracked in DB, causing the cluster to grow by 1 per occurrence.

### Recovery Monitor — Bug Fixes

**P-C4 — detect_karpenter_stalls cross-account creds**: For clusters with `aws_role_arn`, the function now calls STS `assume_role` before creating the EC2 boto3 client. Previously used platform creds — stall detection was blind to EC2 instances in customer accounts.

**P-M5 — scan_orphans Pass 1 guard**: Pass 1 (platform-creds scan) now runs only when at least one cluster has `aws_role_arn IS NULL`. In all-cross-account deployments, Pass 1 was scanning the platform account every 5 min without finding anything — wasting EC2 API quota.

### Auto-Rebalancer Additional Fixes

**P-H1 — Karpenter timeout now fails safely**: When Karpenter provisioning timeout fires with `_other_running > 0`, the action now FAILs instead of proceeding to drain. Previously, drain executed without a confirmed replacement, permanently shrinking the cluster.

**P-H4 — Last-node guard launch registered in DB**: After the emergency replacement spot launch in the last-node guard path (~line 3840), an `Instance` DB record is created (`lifecycle=SPOT, state='pending', launched_by='platform'`) and `spot:asserted_spot:{id}` (TTL=300s) is set. Without registration, `scan_orphans` terminated the node as orphan and discovery misclassified it as OD.

**P-M1 — node_count updated during sync**: `_sync_instance_state_from_aws()` now also sets `cluster.node_count = spot_count + od_count` alongside the existing `spot_count`/`on_demand_node_count` updates. Previously, `node_count` was stale by up to 5 min during active rebalancing.

**P-M4 — Pool rankings cache miss skips cluster**: Guard 2.5 (`global_pool_rankings:{region}` absent) now sets `_pm4_skip_cluster = True` and skips the cluster entirely (with CRITICAL log via 1h dedup key). Previously continued processing, causing 240 full DB pipeline calls/hour per cluster during Redis restart.

**P-M6 — Interval gate fires at default 15s**: Per-cluster interval gate condition changed from `_check_interval > 15` to `_check_interval >= 15`. The `spot:last_check:{cluster_id}` key was never written at the default 15s interval, making Celery backpressure burst protection non-functional for all intervals ≤ 15s.

**P-M2 — EC2 terminate failure cooldown extended to 4h**: `spot:term_failed:{instance_id}` TTL increased from 5400s (90 min) to 14400s (4 hours). The 90-min window was too short for operator review — after expiry the rebalancer retried with both the OD node and the orphan spot still running (cluster at N+1, double billing).

**P-M3 — RC3 streak TTL doubled to 10 minutes**: `rc3:sync_od_streak:{aws_iid}` TTL increased from 300s (5 min) to 600s (10 min). The original 5-min TTL exactly matched the Celery beat cycle period — any beat jitter of ≥1 second caused the streak key to expire between observations 2 and 3, silently resetting the counter and delaying SPOT→OD lifecycle changes by up to 15 min (3 extra observations). With 600s TTL (2× cycle window), expiry-at-boundary races are eliminated.

---

## API Client Module Index (`frontend/src/services/api.js` — 605 lines)

| Module Name | Export Aliases | Prefix | Primary Backend |
|---|---|---|---|
| `authAPI` | `authService` | `/api/v1/auth/` + `/api/v1/users/me/preferences` | `auth_routes.py` |
| `clusterAPI` | `clustersAPI` | `/api/v1/clusters/` | `cluster_routes.py` |
| `accountAPI` | `accountsAPI` | `/api/v1/accounts/` | `account_routes.py` |
| `adminAPI` | — | `/api/v1/admin/` | `admin_routes.py` |
| `metricAPI` | `metricsAPI` | `/api/v1/metrics/` | `metrics_routes.py` |
| `optimizationAPI` | — | `/api/v1/optimization/` + `/api/v1/pod-metrics/` | `optimization_routes.py` |
| `policyAPI` | `policiesAPI` | `/api/v1/policies/` | `policy_routes.py` |
| `hibernationAPI` | — | `/api/v1/hibernation/` | `hibernation_routes.py` |
| `auditAPI` | — | `/api/v1/audit/` | `audit_routes.py` |
| `templateAPI` | `templatesAPI` | `/api/v1/templates/` | `node_template_routes.py` |
| `nodeTemplateAPI` | — | `/api/v1/node-templates/` + `/api/v1/clusters/{id}/node-template/` | `node_template_routes.py` |
| `experimentsAPI` | `labAPI` | `/api/v1/lab/` | `lab_routes.py` |
| `onboardingAPI` | — | `/api/v1/onboarding/` | `onboarding_routes.py` |
| `organizationAPI` | — | `/api/v1/organization/` | `organization_routes.py` |
| `teamAPI` | — | `/api/v1/teams/` | `team_routes.py` |
| `userAPI` | — | `/api/v1/users/me` | `user_routes.py` |
| `billingAPI` | — | `/api/v1/billing/` | `billing_routes.py` |
| `hygieneAPI` | `cleanupAPI` | `/api/v1/hygiene/` | `hygiene_routes.py` |
| `ascpaiAPI` | — | `/api/v1/ascpai/` + `/api/v1/ascpai/clusters/{id}/...` | `ascpai_routes.py` |
| `ascpaiAPI` | — | `/api/v1/ascpai/` (alternate object, legacy) | `ascpai_routes.py` |
| `approvalsAPI` | `approvalAPI`, `ticketAPI`, `ticketsAPI` | `/api/v1/approvals/` | `approval_routes.py` |
| `governanceAPI` | — | `/api/v1/governance/` | `governance_routes.py` |
| `rolesAPI` | — | `/api/v1/roles/` | `role_routes.py` |
| `permissionAPI` | `permissionsAPI` | `/api/v1/permissions/` | `permission_routes.py` |
| `karpenterAPI` | — | `/api/v1/karpenter/` | `karpenter_routes.py` |
| `nativeSpotAPI` | — | `/api/v1/karpenter/native-spot/` | `karpenter_routes.py` ✅ NEW |
| `tagPolicyAPI` | — | `/api/v1/tags/policies/` | `tag_policy_routes.py` |
| `tagTemplateAPI` | — | `/api/v1/tags/templates/` | `tag_management_routes.py` |
| `tagAutomationAPI` | — | `/api/v1/tags/automation/` | `tag_automation_routes.py` |
| `tagScoringAPI` | — | `/api/v1/tags/scoring/` | `tag_scoring_routes.py` |
| `tagComplianceAPI` | — | `/api/v1/tags/compliance/` | `tag_compliance_routes.py` |
| `decisionEngineAPI` | — | `/api/v1/ascpai/v3/` + legacy | `ascpai_routes.py` |
| `optimizerCoordinatorAPI` | — | `/api/v1/optimizer/` | `optimizer_coordinator_routes.py` |
| `poolRotationAPI` | — | `/api/v1/pool-rotation/` | `pool_rotation_routes.py` |
| `multiClusterAPI` | — | `/api/v1/multi-cluster/` | `multi_cluster_routes.py` |

---

## State Management

### Zustand Stores

| Store | File | State Managed |
|---|---|---|
| `useAuthStore` | `store/useStore.js` | `user`, `accessToken`, `isAuthenticated`, `login()`, `logout()` |
| `useAtharvaStore` | `store/useASCPStore.js` | ASCP.AI panel state, selected cluster, cache |
| `useHibernationStore` | `store/useHibernationStore.js` | Hibernation wizard state, selected schedule |

### Custom Hooks

| Hook | File | Purpose |
|---|---|---|
| `useDashboard` | `hooks/useDashboard.js` | Dashboard data fetching & widget state |
| `usePermission` | `hooks/usePermission.js` | Permission checking helper |
| `useAdaptivePolling` | `hooks/useAdaptivePolling.js` | Intelligent polling that backs off when tab is hidden ✅ NEW |
| `useAuth` | `hooks/useAuth.js` | Auth state helper (wraps useAuthStore) ✅ NEW |

### Utilities

| Utility | File | Functions |
|---|---|---|
| Formatters | `utils/formatters.js` | `formatCurrency()`, `formatDate()`, `formatBytes()` |

---

## Complete File Count Summary (Verified)

| Category | Count | Location |
|---|---|---|
| Frontend Components (`.jsx`) | 113 | `frontend/src/components/` |
| Frontend Pages (`.jsx`) | 8 | `frontend/src/pages/` |
| Barrel Index Files (`.js`) | 4 | Various `index.js` |
| Zustand Stores (`.js`) | 3 | `frontend/src/store/` |
| Custom Hooks (`.js`) | 4 | `frontend/src/hooks/` |
| Utility Modules (`.js`) | 1 | `frontend/src/utils/` |
| API Client (`.js`) | 1 | `frontend/src/services/api.js` |
| App Entry (`.js`) | 2 | `App.js`, `index.js` |
| **Frontend Total** | **136** | |

### Component Count by Directory (Verified)

| Directory | File Count |
|---|---|
| `admin/` | 9 |
| `approvals/` | 2 |
| `ascpai/` | 13 |
| `audit/` | 1 |
| `auth/` | 3 |
| `cleanup/` | 10 |
| `clusters/` | 12 |
| `dashboard/` | 13 |
| `governance/` | 4 |
| `hibernation/` | 26 |
| `layout/` | 1 |
| `onboarding/` | 4 |
| `optimizer/` | 1 |
| `policies/` | 3 |
| `rds/` | 2 |
| `ri/` | 2 |
| `right-sizing/` | 2 |
| `s3/` | 2 |
| `settings/` | 11 |
| `shared/` | 12 |
| `teams/` | 3 |
| `transfer/` | 2 |
| **Total** | **138** |

---

## Route Map (verified from App.js)

| Path | Component | Guard |
|---|---|---|
| `/login` | `auth/Login.jsx` | PublicRoute |
| `/signup` | `auth/Signup.jsx` | PublicRoute |
| `/invite-acceptance` | `auth/InviteAcceptance.jsx` | ProtectedRoute |
| `/onboarding` | `pages/Onboarding.jsx` | ProtectedRoute |
| `/dashboard` | `dashboard/Dashboard.jsx` | ProtectedRoute |
| `/clusters` | `clusters/ClusterList.jsx` | PermissionGate:`compute:view` |
| `/policies` | `policies/PolicyConfig.jsx` | PermissionGate:`policy:manage` |
| `/right-sizing` | `right-sizing/RightSizingDashboard.jsx` | PermissionGate:`compute:view` |
| `/hibernation/:clusterId?` | `hibernation/HibernationDashboardNew.jsx` | PermissionGate:`hibernation:view` |
| `/automation-settings` | `settings/GovernanceSettings.jsx` | PermissionGate:`policy:manage` |
| `/audit` | `audit/AuditLog.jsx` | PermissionGate:`audit:view` |
| `/hygiene` | `cleanup/CleanupDashboard.jsx` | PermissionGate:`hygiene:view` |
| `/approvals` | `pages/Approvals.jsx` | ProtectedRoute |
| `/settings` | `settings/Settings.jsx` | ProtectedRoute |
| `/tagging-policies` | `settings/TagPoliciesManager.jsx` | PermissionGate:`policy:manage` |
| `/node-templates` | `pages/NodeTemplates.jsx` | PermissionGate:`compute:view` |
| `/teams` | `pages/Teams.jsx` | PermissionGate:`team:view` |
| `/teams/:teamId` | `pages/TeamDetails.jsx` | PermissionGate:`team:view` |
| `/roles` | `pages/Roles.jsx` | PermissionGate:`team:manage_roles` |
| `/accounts/:accountId/analytics` | `pages/AccountAnalytics.jsx` | ProtectedRoute |
| `/ri-analysis` | `ri/RIAnalysis.jsx` | ProtectedRoute |
| `/s3-analysis` | `s3/S3Analysis.jsx` | ProtectedRoute |
| `/rds-analysis` | `rds/RDSAnalysis.jsx` | ProtectedRoute |
| `/transfer-analysis` | `transfer/TransferAnalysis.jsx` | ProtectedRoute |
| `/ascp-ai` | `pages/ASCPAiPage.jsx` | ProtectedRoute |
| `/admin` | `admin/AdminDashboard.jsx` | AdminRoute |
| `/admin/clients` | `admin/AdminClients.jsx` | AdminRoute |
| `/admin/health` | `admin/AdminHealth.jsx` | AdminRoute |
| `/admin/experiments` | `admin/AdminExperiments.jsx` | AdminRoute |
| `/admin/config` | `admin/AdminConfig.jsx` | AdminRoute |
| `/admin/organizations` | `admin/AdminOrganizations.jsx` | AdminRoute |
| `/admin/billing` | `admin/AdminBilling.jsx` | AdminRoute |

---

## APPENDIX A: Internal Sub-Components

### A.1 Dashboard (`Dashboard.jsx`)

**Inline Sub-Components:**

| Sub-Component | Type | Purpose |
|---|---|---|
| `Badge` | Display | Colored label chip |
| `Dot` | Display | Status dot indicator |
| `SectionLabel` | Display | Uppercase section header |
| `EmptyChip` | Display | Empty state placeholder |
| `Sparkline` | Chart | SVG mini line chart |
| `KpiCard` | Card | Main KPI metric with trend |
| `Card` | Container | Section wrapper with title |
| `HealthMiniCard` | Card | RI/S3/RDS/Transfer mini card |
| `FeatureRow` | Row | Optimization feature status row |

### A.2 Clusters (`ClusterList.jsx`)

**Inline Sub-Components:**

| Sub-Component | Type | Purpose |
|---|---|---|
| `ToggleSwitch` | Toggle | Animated on/off switch |
| `OptimizationSettingsTab` | Panel | Auto-rebalance/rightsizing/standby/diversify/cooldown settings |
| `MiniBar` | Chart | Inline utilization bar |
| `Tag` | Display | Tinted tag/badge chip |
| `MetricBox` | Card | Labeled metric with icon |
| `NodeTreemap` | Visualization | Treemap grid of cluster nodes (paginated, 20/page) |
| `SpotRing` | Chart | SVG donut showing spot ratio |
| `ClusterListItem` | Row | Single cluster row with sparkline |
| `SectionHeader` | Display | Section heading |
| `ClusterDetail` | Panel | Full cluster detail (connected agent) |
| `NoAgentDetail` | Panel | Cluster detail (no agent) |
| `ClustersPage` | Page | Main clusters page with list + detail |

### A.3 ASCP.AI (`ASCPAiPage.jsx`)

**Tabs** (via URL `?tab=`):

| Tab | URL Param | Components Rendered |
|---|---|---|
| Dashboard (default) | `dashboard` | `BlacklistMonitorCard`, `AutoRebalanceAuditCard`, `InterruptionHeatmap`, `RebalancingTimeline`, `PoolRankings` |
| Rankings | `rankings` | `PoolRankings` only |
| Heatmap | `heatmap` | `InterruptionHeatmap` only |
| Rebalancing | `rebalancing` | `AutoRebalanceAuditCard`, `RebalancingTimeline` |
| Decision Engine v3 | `decision-engine-v3` | `DecisionEngineV3Dashboard` |

### A.4 Right-Sizing (`RightSizingDashboard.jsx`)

**Tabs**: Live View (default), History, Configuration

**Live View:**
1. Auto Mode Banner — auto-rebalance + auto-rightsizing ON/OFF
2. Cluster Health & Exposure — node count cards with change indicators
3. Guard Panel — rollbacks, emergency triggers, circuit breaker
4. Stateless Nodes Table — sortable table with per-node Apply button + Apply All
5. Stateful Nodes Table — table with Request Approval workflow

**History Tab:** Savings KPIs, Execution Plan table (Approve/Reject), Action History table

**Configuration Tab:** Strategy Selector (Balanced/Cost/Performance), Spot Target Slider, Instance Families, Feature Toggles

Integration verified: RightSizingKarpenterTab does NOT exist as a separate imported component.
RightSizingDashboard.jsx uses inline conditional rendering for all tabs:
  - karpenter tab: renders KarpenterConfigPanel inline (lines 1035-1076)
  - history tab: renders optimization history table inline
  - config tab: renders KarpenterConfigPanel + settings inline
  - savings tab: renders realized savings table inline
The activeTab state (from URL searchParam 'tab', default 'karpenter') controls which
content block renders. No separate RightSizingKarpenterTab import exists.

### A.5 Hibernation (`HibernationDashboardNew.jsx`)

**Tabs**: Dashboard, Schedules, Calendar, Wizard, Emergency, Analytics, History, Notifications, Settings

| Tab | Key Sub-Components |
|---|---|
| Dashboard | `DashboardTab`, `ClusterOverview` |
| Schedules | `UnifiedScheduleGrid`, `ScheduleModal` |
| Calendar | `ScheduleCalendar` |
| Wizard | `HibernationWizard`, `HibernationTypeCard`, `StrategySelector`, `ScheduleBuilder` |
| Emergency | `EmergencyControls`, `StatusBanner` |
| Analytics | `CostAnalytics`, `CostAnalyticsDashboard` |
| History | `ExecutionHistory`, `AuditHistory`, `HistoryLog` |
| Notifications | `NotificationSettings` |
| Settings | `AdvancedConfiguration`, `TimeBasedRules`, `MultiTimezone`, `ValidationPanel` |

### A.6 Cleanup (`CleanupDashboard.jsx`)

**Inline Sub-Components:**

| Sub-Component | type | Purpose |
|---|---|---|
| `StatusPill` | Display | Resource status colored pill |
| `SectionLabel` | Display | Section header |
| `KpiCard` | Card | Summary metric card |
| `Checkbox` | Input | Selectable checkbox with indeterminate |
| `AnimatedNum` | Display | Animated number counter |
| `RingGauge` | Chart | SVG ring/donut gauge |
| `SparkBars` | Chart | Mini bar chart |

**Main Sections:** Account Selector → Summary KPIs → Sidebar Categories → Resource Table → Action Bar → Wizard Modals

### A.7 Settings (`Settings.jsx`)

**Tabs**: Account, Integrations, Billing

| Tab | Component | Key Elements |
|---|---|---|
| Account | `AccountSettings` | Profile form, password change, org info, connection info |
| Integrations | `CloudIntegrations` | AWS account list, add account, validate, set default |
| Billing | Inline BillingTab | Plan info, usage metrics, manage billing portal |

### A.8 Approvals (`Approvals.jsx`)

**Tabs** (client-side filter):

| Tab | Filter |
|---|---|
| Pending | `status == pending` |
| Active | `status == approved` |
| History | `status in [rejected, expired, revoked]` |
| Outgoing | `requester == currentUser` |

### A.9 Admin Panel

**AdminOverview:** Platform stats cards, agent fleet grid, recent activity feed
**AdminClients:** Search+filter, client table, Toggle/Reset Password/Impersonate actions
**AdminOrganizations:** Org table with pagination, Toggle/View/Impersonate
**AdminHealth:** Backend health grid, DB status, Redis status, worker queue depths
**AdminExperiments:** Experiment list, create form, Start/Stop buttons, results panel
**AdminBilling:** Revenue summary cards, org billing breakdown, Stripe portal
**AdminConfig / PlatformSettings:** Feature flags table, system configuration parameters

---

## 21. Gauges & Charts — Detailed Reference

All entries below are 100% verified by reading the source file.

---

### 21.1 `shared/GaugeChart.jsx` (76 lines)

**Type**: SVG semi-circle gauge
**Library**: Pure SVG (no Recharts)
**Props**:

| Prop | Type | Default | Description |
|---|---|---|---|
| `value` | number | required | Current numeric value |
| `maxValue` | number | required | Maximum value (divides to get %) |
| `label` | string | required | Text label below gauge |
| `unit` | string | optional | Unit text below value |
| `color` | string | `'blue'` | Color theme: `blue`, `green`, `yellow`, `red`, `indigo`, `gray` |

**Rendering**: SVG arc path `M 5 50 A 45 45 0 0 1 95 50` (half-circle). Dash-array calculated as `(pct/100) × 141.37`. Animated via `setTimeout + CSS transition-all duration-1000`.
**Used by**: Dashboard widgets, right-sizing panels

---

### 21.2 `cleanup/summary/SavingsGauge.jsx` (80 lines)

**Type**: Recharts Pie half-donut + framer-motion number counter
**Library**: Recharts (`PieChart`, `Pie`, `Cell`) + framer-motion (`animate`)
**Props**:

| Prop | Type | Description |
|---|---|---|
| `selectedSavings` | number | Dollar value of selected resources' potential savings |
| `totalPotentialSavings` | number | Total potential savings across all resources |

**Gauge**: `startAngle={180}` `endAngle={0}`, `cx=50%` `cy=100%` (anchored at bottom). Segments: selected=`#16a34a` (green-600), remaining=`#e5e7eb` (gray-200).
**Counter**: `framer-motion animate(0, selectedSavings, { duration: 0.8, ease: "easeOut" })` — animates dollar value on mount.
**Used by**: `cleanup/summary/HeroMetricsPanel.jsx`

---

### 21.3 `clusters/SpotRatioGauge.jsx` (55 lines)

**Type**: Recharts Pie half-donut
**Library**: Recharts (`PieChart`, `Pie`, `Cell`, `Tooltip`)
**Props**:

| Prop | Type | Description |
|---|---|---|
| `spotPct` | number | Spot % (0–100) |
| `onDemandPct` | number | On-demand % (0–100) |

**Gauge**: `startAngle={180}` `endAngle={0}`, `innerRadius={20}` `outerRadius={30}`, `paddingAngle={2}`. Colors: Spot=`#10B981` (green), On-Demand=`#F59E0B` (amber).
**Center label**: `Math.round(spotVal)%` + "SPOT" label below.
**Tooltip**: `formatter={(val) => [Math.round(val) + '%']}` at 10px font
**Used by**: `clusters/ClusterList.jsx` (inline in node list rows)

---

### 21.4 `ascpai/DiversityGauge.jsx` (144 lines)

**Type**: Bar-style horizontal progress gauges (family + AZ)
**Library**: Pure CSS `div` width bars (no Recharts)
**Props**:

| Prop | Type | Description |
|---|---|---|
| `clusterId` | string | Cluster ID to fetch diversity status |

**API**: `decisionEngineAPI.getDiversityStatus(clusterId)` → `GET /api/v1/ascpai/v3/diversity/{id}` — polls every **30 seconds**.
**Response fields used**: `family_percentages`, `family_distribution`, `az_percentages`, `az_distribution`, `total_nodes`
**Thresholds** (verified from source):
- Family concentration: **>40%** → orange bar + `text-orange-700` + shows `ConcentrationAlert` warning banner
- AZ concentration: **>50%** → orange bar + `text-orange-700` + shows `ConcentrationAlert` warning banner

**Section 1**: Instance Family Distribution — one progress bar per family
**Section 2**: Availability Zone Distribution — one progress bar per AZ
**Footer**: "Recommended limits: Family ≤40%, AZ ≤50%"

---

### 21.5 `clusters/overview/OverviewTab.jsx` (767 lines)

**Type**: Multi-section overview page with **4 inline SVG gauges + 1 Recharts area chart**
**Library**: Recharts (`AreaChart`, `Area`, `XAxis`, `YAxis`, `CartesianGrid`, `Tooltip`, `Legend`, `ResponsiveContainer`)
**Props**:

| Prop | Description |
|---|---|
| `cluster` | Cluster object |
| `metrics` | Cluster metrics |
| `utilization` | CPU/memory utilization |
| `karpenterInstallStatus` | `{ karpenter_installed: bool }` |
| `schedule` | Active hibernation schedule |
| `policy` | Active optimization policy |
| `nodeRecommendations` | Array of right-sizing recommendations |
| `nodesDetailed` | `{ nodes: [], total_nodes, total_pods, spot_friendly_pods }` |
| `costTrends` | `{ data_points: [{ timestamp, value }] }` |
| `rightsizing` | Array of rightsizing recs |
| `onInstallKarpenter` | Callback to install Karpenter |
| `onManagePolicies` | Callback to open policy page |

**Inline Sub-Components (all inline, no separate files)**:

| Component | Type | Description |
|---|---|---|
| `SavingsDonut` | SVG donut | Shows `savingsPct` — green if ≥50%, orange if ≥25%, red below. 64×64px, rotated -90deg |
| `NodeRing` | SVG ring | Spot ratio ring — colored by `spotRatioPct`: green if ≥70%, orange if ≥40%, blue below |
| `ConfigTable` | Table | Instance type breakdown — Qty, Instance, Hourly, Total Hourly, Total Monthly — with totals footer |
| `CostTooltip` | Recharts Tooltip | Custom tooltip showing Current cost/h, Optimal cost/h, and Available Savings % on hover |

**7 Rendered Sections**:

| # | Section | Content |
|---|---|---|
| 1 | **Agent Banner** | Green/orange left-bordered banner showing agent health + last heartbeat |
| 2 | **Top Row** | 3-column grid: Cost & Savings card (`SavingsDonut`), Node Composition card (`NodeRing`), Pods card with workload classification chips |
| 3 | **Optimization Status** | 4-column strip: ASCP.ai active status, Right-Sizing over-provisioned count, Policies count, Hibernation active status |
| 4 | **Karpenter Management** | Karpenter installed/not installed status card + Install button |
| 5 | **Spot Instance Analysis** | Table: workload name (derived from `node_name`; if node_name starts with `ip-` uses `instance_type` fallback — K8s assigns IP-based hostnames), replicas, current type (SPOT/ON DEMAND), recommendation (SPOT/STABLE) |
| 6 | **Current + Optimized Config** | 2-col `ConfigTable` pair: current configuration vs projected optimized configuration (monthly cost, instances, CPU, RAM) |
| 7 | **Cluster Cost Trends** | Recharts `AreaChart` with 24h/7d toggle — "Current Cluster Cost" (blue area) vs "Optimal Cluster Cost" (green area). Left panel shows avg current/optimal cost + available savings % |

**Cost trend data source**: `costTrends.data_points[].{ timestamp, value }` — optimal = `value × (1 - savingsFraction)`

**Node recommendations data source** (`nodeRecommendations` prop, fetched from `GET /api/v1/ascpai/clusters/{id}/node-recommendations`):
- Backend (`ascpai_routes.py`) fetches `top_pools` using `NodeTemplate(architecture=["amd64","arm64"], ...)` for broad global coverage
- For each OD node, source architecture is derived from the instance family name: families ending in `g` (t4g, c6g, m6g, r6g, etc.) or `a1` → `arm64`; all others → `amd64`
- Only pools matching the source node's architecture are used (`_candidate_pools`); prevents arm64 (Graviton) pool recommendations for x86_64 workloads
- Falls back to all pools if no architecture-matched pools exist

### Dry Run — Fail-Safe Capacity Validation

*   **Method**: `ec2.run_instances(DryRun=True)` with `InstanceMarketOptions.MarketType=spot` (NOT `describe_instance_type_offerings()` — which only checks AZ offering, not actual spot capacity). AMI is resolved via `describe_images` and cached 24h in Redis as `dry_run:ami:{region}`. Falls back to `describe_instance_type_offerings()` only if AMI lookup fails.
*   **Error mapping**: `DryRunOperation` → pass (spot capacity confirmed); `InsufficientInstanceCapacity` → fail (no spot capacity now); any other `ClientError` → fail (conservative).
*   **Fail-Safe Policy**: On any capacity ambiguity or API failure, the engine returns **False** (conservative safety) and triggers a 6-hour pool blacklist.
*   **Real-time invalidation**: When `InsufficientInstanceCapacity` is caught at actual launch time, `auto_rebalancer.py` calls `invalidate_dry_run_cache(instance_type, az, redis)` to immediately mark `dry_run:{type}:{az}` as "fail" (300s TTL) without waiting for the next 5-min refresher cycle.

### Post-Launch Redis Guards (auto_rebalancer.py → S2S loop and discovery.py)

After a successful spot launch, `auto_rebalancer.py` sets three protective Redis keys:

| Key | TTL | Purpose |
|---|---|---|
| `spot:asserted_spot:{instance_id}` | 300s | Prevents discovery worker from OD-downgrading the node during AWS `InstanceLifecycle` API propagation delay. Root cause fix for c6a.large shown as OD. |
| `spot:post_launch_cooldown:{instance_id}` | 60s | S2S loop skips this node for 60s after any successful spot launch. |
| `spot:s2s_suppressed:{instance_id}` | 180s | Set only when actual launch type ≠ original target (fallback). S2S loop skips the node for 2× the 90s stabilization window. |

### Per-Cluster Guards and Counters (auto_rebalancer.py — changes.md session 2026-03-25)

Additional Redis keys written by the 15s rebalancer loop for safety, monitoring, and performance:

| Key | TTL | Purpose |
|---|---|---|
| `spot:stabilization_lock:{cluster_id}` | 60s (Issue 1: was 300s) | Guard 2 in the per-cluster scan loop. `CooldownController.acquire_stabilization_lock()` sets this after every successful action AND persists to `cluster_cooldown_states` DB table (Issue 13). Auto_rebalancer re-hydrates this key from DB on Redis miss (TTL==-2) so the stabilization window survives Redis restarts. |
| `spot:daily_count:{cluster_id}` | 86400s (Issue 2) | Redis-cached daily action count. Eliminates the DB `COUNT` query that ran every 15s per cluster. On cold start / Redis restart, DB is queried once and the result is written here. Incremented in the action completion handler. |
| `spot:skip_streak:{cluster_id}` | 300s rolling (Issue 6) | Consecutive skip counter per cluster. `_record_skip()` increments; `_record_active()` deletes. Warns at 20 skips (= 300s of inactivity) and every 20 after. |
| `class_miss_streak:{cluster_id}` | 90s (6 cycles) (Issue 7) | Tracks consecutive cycles where `spot:node_classification` cache was absent. DEBUG at 1, INFO at 2–3, WARNING at ≥4 (WorkloadInspector may be stalled). Cleared on cache HIT. |
| `ranking_stale_warned:{region}` | 3600s (Issue 9) | Guard 2.5 in the per-cluster scan loop. Set when `global_pool_rankings:{region}` key is absent from Redis (TTL==-2). Deduplicates the CRITICAL log to once per hour per region. Non-blocking — cluster processing continues after the log. |
| `spot:launch_blocked:{cluster_id}:{type}:{az}` | 300s (Issue 11) | Inline pool block set when a launched instance fails to join K8s (`node_joined:` key absent after `spot_join_timeout`). Pool selection skips this pool+AZ for 5 min to prevent orphan accumulation. |
| `ranking_refresh_pending:{region}` | 60s (Issue 14) | Debounce key preventing more than 1 `build_global_pool_cache` dispatch per region per 60s. Set by `emergency_rebalancer.py` after `report_termination` and by `auto_rebalancer.py` after `report_launch_failure`. |
| `spot:term_failed:{instance_id}` | 14400s / 4h (P-M2 fix: was 5400s / 90 min) | Blocks retry of EC2 terminate for a specific instance after API failure. 4h gives operators time to investigate before auto-retry; prevents re-attempt while cluster is at N+1. |
| `spot:node_active_action:{instance_id}` | 600s / 10 min (changes.md §2.2 — implemented 2026-03-26) | Per-node overlapping drain prevention. Set by auto_rebalancer when creating a new OD→spot action. Checked before action creation — if key exists, the instance is already being migrated and is skipped. Cleared in the completion handler on both success and failure paths. |
| `spot:discovery_last_updated:{cluster_id}` | 600s / 10 min (changes.md §2.3 — implemented 2026-03-26) | Written by `discovery.py:scan_eks_clusters` after each cluster sync (`db.commit()`). Allows the auto_rebalancer to detect stale DB state (key absent = discovery hasn't run in >10 min). Check guard in auto_rebalancer not yet wired (available for future use). |

### New Debug API Endpoint (Task 13) — `GET /api/v1/ascpai/clusters/{cluster_id}/nodes/{node_id}/status`

Returns per-node runtime state for debugging lifecycle misclassification and cooldown issues:
- `lifecycle`, `spot_assertion` (bool indicating `spot:asserted_spot` key is active)
- `cooldowns`: `rebalanced` (24h), `post_launch` (60s), `spot_assertion` (300s), `rc3_od_streak` (count + threshold + TTL)
- `suppression.s2s`: TTL + reason (`"fallback"` if set by fallback launch)

---

### 21.6 `ascpai/InterruptionHeatmap.jsx` (190 lines)

**Type**: 7-day × 24-hour risk heatmap grid
**Library**: Pure CSS grid (no charting library)
**Props**: None (self-contained, fetches own data)
**Polling**: `useAdaptivePolling` via combined `fetchAll()` — 5 min (300s) slow interval

**API calls**:
- `GET /api/v1/ascpai/interruption-heatmap?days=30` → grid data
- `GET /api/v1/ascpai/volatility/status` → `az_pressure` map for dot overlays

**Grid**: 7 rows (Sun–Sat) × 24 columns (0:00–23:00). Only every 3rd hour label shown.
Cell color logic (last-match-wins, matches source code):
- 0 interruptions → bg-gray-100 (no data)
- 1 interruption → bg-green-400 (safe)
- 2–4 interruptions → bg-orange-400 (moderate risk)
- ≥5 interruptions → bg-red-500 (high risk)

**AZ pressure dot overlays**: Small colored dot in top-right corner of each cell:
- `az_pressure < 3` → `bg-green-500`
- `az_pressure 3–5` → `bg-yellow-400`
- `az_pressure > 5` → `bg-red-500`

**Family filter dropdown**: "All Families" aggregates interruption_count; specific family shows only that family's data.
**Hover tooltip**: `{day} {h}:00 - {count} interruptions | AZ pressure: {n}`
**Legend**: Safe (gray) / Low (green) / Medium (orange) / High (red)

---

### 21.7 `ascpai/VolatilityMonitor.jsx` (53 lines)

**Type**: Sticky top-of-page alert banner
**Library**: None (pure JSX)
**Props**: None (completely self-contained)

**Location**: Mounted in `App.js` root above the router, wrapped in `ErrorBoundary`. NOT inside `MainLayout.jsx`. This ensures lifecycle is fully independent of layout rendering — component persists across all route changes without remounting or re-fetching.

**API**: `ascpaiAPI.getVolatilityStatus()` → `GET /api/v1/ascpai/volatility/status`
**Polling interval**: 600,000ms (10 minutes exactly — matches 2hr Redis TTL cadence)
**Render condition**: **Hidden** when `regime === 'NORMAL'`. Only renders when regime is non-normal.
**Colors**:
- `CRITICAL` → `bg-red-600` sticky banner
- Other non-normal → `bg-yellow-600` sticky banner
**Message**: "⚠️ VOLATILITY MONITOR: Market regime is currently {regime}. Expected Value risk ceilings are dynamically constrained."
**Fail-silent**: Errors are caught and logged — banner simply stays hidden if fetch fails.
**Memoization**: `React.memo(VolatilityMonitor)` — prevents re-renders on parent state changes. React.memo is still in place even after moving to App.js root.

---

### 21.8 `ascpai/BlacklistMonitorCard.jsx` (49 lines)

**Type**: Conditional red alert card
**Library**: None (pure JSX + SVG icon)
**Props**: None (self-contained)

**API**: `ascpaiAPI.getBlacklistStatus()` → `GET /api/v1/ascpai/blacklist`
**Polling**: `useAdaptivePolling` — 2 min (120s) slow interval (blacklist changes matter quickly)
**Render condition**: **Only renders** when `status.suspended === true`. Returns `null` in all other cases.
**Display**: Left-bordered red card (`bg-red-50 border-l-4 border-red-500`).
**Content**: Shows `status.active_count` (number of active blacklists), message explains predictive blacklisting is suspended due to high saturation. Notes that only exact ITNs (Spot Termination Notices) will trigger blacklisting.

---

### 21.9 `ascpai/GlobalRankingsCard.jsx` (86 lines)

**Type**: Table — Top 10 ML-ranked spot pools
**Library**: None (pure HTML table)
**Props**: None (self-contained)

**API**: `ascpaiAPI.getRankings(null, null, 10, null, { instance_type: 'm5.large', lifecycle: 'on-demand' })`
→ `POST /api/v1/ascpai/pools/rankings` with `m5.large on-demand` baseline context (region=null → API default)
**Polling**: `useAdaptivePolling` — 60s slow interval (pool prices change frequently)

**Columns**: Pool (instance_type + AZ), Savings %, Risk Probability, Expected Value
**Savings display**: `row.real_savings_pct * 100` if present, else `row.predicted_savings * 100`. Both fields are serialized per-pool in `ascpai_routes.py:263,301`
**Risk color**: Orange if `risk_probability > 0.4`, gray otherwise
**EV display**: `row.expected_value !== undefined ? row.expected_value.toFixed(4) : '-'` — null guard present. `expected_value` is computed via `compute_expected_value()` in `ascpai_routes.py:278` and included in `PoolRankingResponse` (field at line 56)
**Baseline**: `{ instance_type: 'm5.large', lifecycle: 'on-demand' }` — intentional neutral global reference (NOT cluster-specific)
**Header badge**: "LIVE AI" (indigo pill)

**Known limitation — baseline region risk**: `m5.large` is used as the savings baseline regardless of the user's region. In regions where `m5.large` is not common (e.g., `ap-south-1` dominated by `t3` families) or is priced differently, the savings % shown in GlobalRankingsCard will reflect a reference node that doesn't represent the user's actual fleet. This is intentional for a fleet-neutral global view but can appear misleading. There is no per-region or per-cluster baseline option in GlobalRankingsCard — users who need cluster-specific rankings should use the PoolRankings table (`ascpai/PoolRankings.jsx`) which accepts a cluster context.

Note: predicted_savings in API response = (OD - spot) / OD (real savings %).
      ScoredPool.predicted_savings (ONNX output) is NOT the same field —
      it is computed fresh at serialization and never mutates ScoredPool.

**S2S breakage risk**: `ScoredPool.predicted_savings` (ONNX output, range 0–1) is used by the S2S tradeoff logic in `auto_rebalancer.py` to compare current vs candidate spot pools. If any code in `ascpai_routes.py`, `auto_rebalancer.py`, or pool ranking utilities modifies `ScoredPool.predicted_savings` post-inference, S2S decisions will silently use incorrect values. The `PoolRankingResponse.predicted_savings` (API field, `(OD-spot)/OD`) is a separate computation on a different object and must never be confused with `ScoredPool.predicted_savings`.

---

### 21.10 `clusters/ClusterHealthTimeline.jsx` (64 lines)

**Type**: Vertical timeline of health events
**Library**: None (pure JSX, react-icons)
**Props**: `clusterId` (string)

**API**: `GET /metrics/cluster/{clusterId}/health-timeline` (note: no `/api/v1` prefix — calls through Nginx)
**Event icons**:
- `healthy` → `FiCheckCircle` green
- `degraded` → `FiAlertTriangle` yellow
- `unavailable` → `FiXCircle` red
- default → `FiActivity` gray

**Event badge colors**: green-50/text-green-700, yellow-50/text-yellow-700, red-50/text-red-700
**Loading state**: Animated gray skeleton (no spinner)

---

### 21.11 `dashboard/widgets/SavingsChart.jsx` (55 lines)

**Type**: Recharts BarChart — optimized vs unoptimized cost bars
**Library**: Recharts (`BarChart`, `Bar`, `XAxis`, `YAxis`, `CartesianGrid`, `Tooltip`, `Legend`, `ResponsiveContainer`)
**Props**:

| Prop | Description |
|---|---|
| `data` | Object with `chartData: [{ month, optimized, unoptimized }]` |
| `widgetKey` | Widget key identifier |

**Bars**: "Without Optimization" = `#ef4444` (red), "With Optimization" = `#10b981` (green). Both with `radius={[4,4,0,0]}`.
**Y-axis formatter**: `$${(v/1000).toFixed(0)}k`
**Tooltip formatter**: `$${value.toLocaleString()}`
**No-data state**: Centered icon + "No cost data available yet" + "Connect AWS accounts to see savings projections"

---

## 22. Sub-Component Inline Detail Reference

These are components defined **inline inside parent files** — they are NOT separate files.

### 22.1 Inside `clusters/overview/OverviewTab.jsx`

| Inline Component | Props | Visual | Color Logic |
|---|---|---|---|
| `SavingsDonut` | `pct` (0–100) | 64×64 SVG donut | ≥50% → `#22c55e` green; ≥25% → `#f97316` orange; <25% → `#ef4444` red |
| `NodeRing` | `pct`, `color` | 56×56 SVG ring via `<path>` arc | Color passed by parent: ≥70% spot → green, ≥40% → orange, else blue |
| `ConfigTable` | `rows`, `title`, `accent`, `totalLabel`, `totalMonthly`, `totalInstances`, `totalCpu`, `totalMem` | Full instance-type cost table + totals footer | Blue accent for current, green for optimized |
| `CostTooltip` | `active`, `payload`, `label` | Recharts custom tooltip | Shows "Available Savings: X%" when both areas visible |

**Cost derivation logic** (verified):
- `totalCost` = `metrics.monthly_cost` → `cluster.monthly_cost` → `nodeRecommendations × 730h` fallback chain
- `addlPotential` = `metrics.estimated_savings` → `cluster.estimated_savings` → computed from OD nodes where `target_spot_price > 0`; nodes with no spot price contribute **zero** (no fabricated savings via multiplier)
- `spotRatioPct` = derived directly from `nodesDetailed.nodes[].lifecycle` field values

### 22.2 Inside `cleanup/CleanupDashboard.jsx`

| Inline Component | Purpose |
|---|---|
| `StatusPill` | Colored pill for resource status (e.g., Running, Idle, Unattached) |
| `SectionLabel` | Uppercase gray section header |
| `KpiCard` | Metric card with title + value |
| `Checkbox` | Selectable checkbox with indeterminate state for bulk selection |
| `AnimatedNum` | Animated counter (count-up effect) |
| `RingGauge` | Small SVG ring/donut for compliance or scan % |
| `SparkBars` | Mini inline bar chart for scan trend |

### 22.3 Inside `dashboard/Dashboard.jsx`

| Inline Component | Purpose |
|---|---|
| `Badge` | Colored label chip with text |
| `Dot` | Small status dot (green/red/yellow) |
| `SectionLabel` | Uppercase section divider header |
| `EmptyChip` | Empty-state placeholder chip |
| `Sparkline` | SVG mini line chart (trend indicator) |
| `KpiCard` | Main KPI card with value, sub-label, and %trend |
| `Card` | White section card container with title |
| `HealthMiniCard` | Small card for RI/S3/RDS/Data Transfer status |
| `FeatureRow` | Row showing optimization feature name + on/off status |

### 22.4 Inside `clusters/ClusterList.jsx`

| Inline Component | Purpose |
|---|---|
| `ToggleSwitch` | Animated on/off toggle (via CSS transition) |
| `OptimizationSettingsTab` | Full settings panel: auto-rebalance, auto-rightsizing, maintain-standby, diversify, cooldown input |
| `MiniBar` | Inline utilization bar (CPU/memory %) |
| `Tag` | Tinted tag/badge chip |
| `MetricBox` | Labeled metric with icon |
| `NodeTreemap` | Grid of cluster nodes visualized as colored boxes (20/page, paginated) |
| `SpotRing` | Small SVG donut showing spot vs OD ratio |
| `ClusterListItem` | Single cluster row with embedded sparkline + collapse |
| `SectionHeader` | Bold section heading |
| `ClusterDetail` | Full cluster detail panel (rendered when agent connected) |
| `NoAgentDetail` | Simplified cluster panel (no agent installed) |
| `ClustersPage` | Root cluster page layout (list + detail side-by-side) |

---

## 23. Component Polling & Refresh Intervals (Verified)

| Component | Interval | Endpoint |
|---|---|---|
| `VolatilityMonitor` | 10 minutes (600,000ms) | `/api/v1/ascpai/volatility/status` |
| `DiversityGauge` | 30 seconds (30,000ms) | `/api/v1/ascpai/v3/diversity/{id}` |
| `BlacklistMonitorCard` | 2 minutes (120,000ms) via `useAdaptivePolling` | `/api/v1/ascpai/blacklist` |
| `GlobalRankingsCard` | 1 minute (60,000ms) via `useAdaptivePolling` | `/api/v1/ascpai/pools/rankings` |
| `InterruptionHeatmap` | 5 minutes (300,000ms) via `useAdaptivePolling` | `/api/v1/ascpai/interruption-heatmap?days=30` + volatility/status |
| `ClusterHealthTimeline` | One-time on mount | `/metrics/cluster/{id}/health-timeline` |
| `useAdaptivePolling` hook | Adaptive (backs off when tab hidden) | Configurable per consumer |

---

## 24. Backend-Only Features (No Frontend UI)

The following backend features exist and are fully functional but have **no corresponding frontend component**. Operators interact with them only via API or Redis/DB directly.

| Feature | Backend Location | Access Method | Notes |
|---|---|---|---|
| **SubstituteManager / Warm Spare** | `backend/services/substitute_manager.py` | `GET /api/v1/clusters/{id}/substitute/status` | No frontend widget; maintain_standby toggle is in `OptimizationSettingsTab` (ClusterList.jsx) but warm-spare status itself is API-only |
| **Pool Rotation Service** | `backend/services/pool_rotation_service.py` | `POST /api/v1/pool-rotation/clusters/{id}/force` | Force-rotation endpoint exists; no UI for viewing rotation history or current pool health scores |
| **ASCP Built-in Auto-Scaler** | `backend/workers/tasks/auto_scaler.py` | `ClusterOptimizationSettings.enable_ascp_auto_scaler` (DB toggle) | No UI toggle; must be enabled directly via DB or API patch to settings |
| **ClusterCooldownState lock visibility** | `backend/models/cluster.py` | `GET /api/v1/clusters/{id}` (no dedicated endpoint) | The DB-backed stabilization lock table is not surfaced in the UI; `spot:stabilization_lock` Redis TTL is shown in the stabilization card but the DB table is invisible |
| **NodeAlternativeCache** | `backend/models/cluster.py` | `GET /api/v1/clusters/{id}/nodes/{node_id}/alternatives` | Per-node alternative pool list is available via API but no frontend component renders it |
| **Circuit Breaker Admin** | `backend/api/admin_routes.py` | `GET /api/v1/admin/circuit-breakers` | Accessible only to SUPER_ADMIN role; no standard user UI |
| **Instability Propagator events** | `backend/services/instability_propagator.py` | Redis keys `propagator:pool_pressure:*` | Propagator adjusts pool scoring internally; no events visible in UI |

---

## 25. Known Operational Gaps

| Gap | Details | Workaround |
|---|---|---|
| **ClusterBaseline missing for legacy clusters** | Clusters onboarded before the `ClusterBaseline` table was added have no savings anchor row. `SavingsCalculator` returns $0 for these clusters. | Manually `INSERT INTO cluster_baselines (cluster_id, baseline_monthly_cost, ...) VALUES (...)` or trigger a recalculate via API once OD price data is available. |
| **Pricing queue not consumed without `-Q pricing` flag** | Celery worker started without `-Q celery,pricing` never consumes pricing tasks → spot prices go stale. | In `docker-compose.yml`, celery-worker command must include `-Q celery,pricing`. Emergency worker should use `-Q emergency`. |
| **SpotPriceHistory `az` column legacy name** | DB table has `az` column (NOT NULL) but `Instance` model uses `availability_zone`. Batch DB inserts fail silently; Redis writes succeed. | Redis-based pricing pipeline (not DB) is the authoritative path for spot prices. |
| **No Prometheus metrics for circuit breaker / rate limiter** | `cb:state:{cluster_id}` Redis keys are used internally but not exported as Prometheus gauges. | Use `GET /api/v1/admin/circuit-breakers` for a current snapshot. Alerting requires custom polling script. |
| **discovery_last_updated check not wired** | `spot:discovery_last_updated:{cluster_id}` is written by discovery.py but the auto_rebalancer main loop does not yet check it for staleness. | Current staleness protection: per-cycle DB reads + instance state reconciliation pass. |

---

## 26. Bug Fix Log — Session 2 (2026-03-26)

41 bugs fixed across 20+ files. Summary by category:

### Decision Engine (P-C11, P-C12, P-C13, P-M29)
- **P-C11**: `PoolRankingService` arg order corrected in `decision_engine.py` (`(self.db, self.redis)` not `(self.redis, self.db)`)
- **P-C12**: Non-existent `refresh_global_rankings()` replaced with `build_global_pool_cache()`
- **P-C13**: Redis key corrected from `spot:global_rankings:{region}` → `global_pool_rankings:{region}` (both read locations)
- **P-M29**: `_check_volatility_regime()` now accepts `b"true"`, `"true"`, `b"active"`, `"active"` (not just bytes literal)

### Right-Sizing Service (P-C6, P-C7, P-H6, P-H7, P-M8)
- **P-C6**: Added `.order_by(PodMetric.timestamp)` to pod metrics query in `rightsizing_service.py`
- **P-C7**: Volatility check fixed — `b"true"` never matched `decode_responses=True` string output
- **P-H6**: Percentile formula: `int((p/100) * (len-1))` not `int((p/100) * len)` (off-by-one)
- **P-H7**: Added `or None` guards for NULL CPU/memory request fields
- **P-M8**: Memory MB conversion uses `math.ceil()` not `int()` truncation

### Emergency Rebalancer (P-C16, P-H16)
- **P-C16**: `status = "in_progress"` (was `"pending"` — never consumed by any processor)
- **P-H16**: Fixed column names: `actual_instance_type`/`actual_az` (not `target_instance_type`/`target_az`)

### Pool Ranking Service (P-C14, P-M22, P-M25)
- **P-C14**: `_get_spot_advisor_data()` returns `{}` not `None` on exception
- **P-M22**: `_step4_blacklist_check` failure_count default: `or 1` → `or 0`
- **P-M25**: vCPU lower bound: `max(1, vcpu - 1)` → `max(1, vcpu)`

### Cross-Account Auth (P-C15, P-H11, P-H18)
- **P-C15**: `substitute_manager.py` — assumed-role creds + `ImageId` from Redis cache
- **P-H11**: `tag_management_service.py` — `ExternalId` added to assume_role
- **P-H18**: `recovery_monitor.py` — `ExternalId` added to all 3 assume_role calls

### Auto-Rebalancer (P-H5, P-H17)
- **P-H5**: Diversification guard: empty `target_az` skips occupancy check
- **P-H17**: ASG resume exception handler passes Cluster object not ARN string

### Redis / DB Safety (P-H14, P-H27, P-H28, P-M11, P-M28)
- **P-H14**: `optimizer_coordinator.py` — atomic Redis pipeline for INCR+EXPIRE
- **P-H27**: `spot_advisor_scraper.py` — session close only if this function created it
- **P-H28**: ARN `split(':')[4]` guarded with `len() > 4` check in 5 files
- **P-M11**: `rebalancing_action.py` — `ForeignKey("clusters.id", ondelete="CASCADE")` added
- **P-M28**: `cooldown_controller.py` — `_db.close()` moved to `finally` block

### Karpenter Routes (P-M24)
- **P-M24**: All `* 720` monthly cost multipliers → `* 730` hours

### Frontend (P-C17, P-C18, P-C19, P-H19–P-H26, P-M17–P-M21, P-M26)
- **P-C17/C18** (`RightSizingDashboard.jsx`): Fake safety panel + exposure charts removed, replaced with honest placeholders
- **P-C19** (`agents.py`): `000000000000` placeholder ARN → `role_arn=None, is_validated="N"`
- **P-H19** (`RightSizingDashboard.jsx`): Guard for synthetic `"stateful-*"` node IDs
- **P-H20/H21/H22** (`RightSizingKarpenterTab.jsx`): `|| 128` fallback, 94% hardcode, fake SVG charts — all removed
- **P-H23/H24** (`PoolRankings.jsx`): useEffect dependency fixes (interval thrash + polling reset)
- **P-H25** (`OverviewTab.jsx`): NaN guard on null spot price multiply
- **P-H26** (`useASCPStore.js`, `api.js`): Default region `'ap-south-1'` → `null`
- **P-M17/M18** (`DecisionEngineV3Dashboard.jsx`, `RightSizingDashboard.jsx`): `retryCount` state for retry button
- **P-M19/M20/M21** (`RightSizingDashboard.jsx`): Fake candidates, fake timestamps, hardcoded 50% — all removed
- **P-M26** (`api.js`): Duplicate `assignRole` removed

### Fix Status Totals (2026-03-26)
| Status | Critical | High | Medium | Total |
|---|---|---|---|---|
| **FIXED** | 17 | 24 | 25 | **66** |
| **PARTIALLY FIXED** | 2 | 2 | 1 | **5** |
| **N/A (removed)** | 0 | 1 | 3 | **4** |
| **Total** | **19** | **28** | **29** | **76** |

Partially fixed (no full resolution yet):
- **P-C8**: `INSTANCE_SPECS` in `karpenter_routes.py` still has hardcoded ap-south-1 reference prices
- **P-H10**: DryRun global budget (200/hr) can still starve under high load
- **P-M23**: `spot * 3.0` last-resort OD fallback for instance types not in `_ONDEMAND_FALLBACK` table
