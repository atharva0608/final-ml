# All UI Components — Complete Frontend Inventory

> **Format:** Section → Subsection → 7-column table
>
> **Data Source Legend:** `Real API` · `Hardcoded (FAKE)` · `Computed` · `Props` · `N/A`
>
> **Last Updated:** 2026-02-23 — Deep-dive audit (every modal, tab, sub-component verified from source code)
>
> **Total:** 134 component files + 7 pages = 141 frontend files

---

## 1. Dashboard (15 files)

### 1.1 Overview Tab

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Monthly Spend KPI | Card | Total monthly cost + trend | Real API | `GET /api/v1/metrics/dashboard` | MetricsService.get_dashboard_kpis | Dashboard.jsx |
| Net Savings KPI | Card | Estimated savings + rate % | Real API | `GET /api/v1/metrics/dashboard` | MetricsService | Dashboard.jsx |
| Spot Ratio KPI | Card | Optimization rate % | Real API | `GET /api/v1/metrics/dashboard` | MetricsService | Dashboard.jsx |
| Total Nodes KPI | Card | Node count + cluster count | Real API | `GET /api/v1/clusters` | ClusterService | Dashboard.jsx |
| Spend Forecast | Widget | MTD + Projected EOM spend | Real API | `GET /api/v1/metrics/cost/timeseries` | MetricsService | widgets/SpendForecastWidget.jsx |
| Agent Status | Widget | Agent heartbeat monitor | Real API | `GET /api/v1/clusters` | ClusterService | widgets/AgentStatusWidget.jsx |
| Cluster Health | Widget | Cluster health cards | Props | — | — | widgets/ClusterHealthCard.jsx |
| Fleet Composition | Widget | Spot vs On-Demand pie | Real API | `GET /api/v1/metrics/instances` | MetricsService | widgets/FleetComposition.jsx |
| Activity Feed | Widget | Recent 5 audit entries | Props | — | — | widgets/ActivityFeed.jsx |
| Pending Approvals | Widget | Pending JIT count | Real API | `GET /api/v1/approvals/?status=PENDING` | ApprovalService | widgets/PendingApprovalsCard.jsx |

### 1.2 Cost Intelligence Tab

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Right-Sizing Feature Card | Card | Oversized instances summary + CTA | Hardcoded (empty state) | — | — | Dashboard.jsx |
| AtharvaAI Feature Card | Card | ML status + pools ranked + CTA | Hardcoded (empty state) | — | — | Dashboard.jsx |
| Hibernation Feature Card | Card | Sleep hours + savings + CTA | Hardcoded (empty state) | — | — | Dashboard.jsx |
| Hygiene Stats Banner | Banner | Safe-to-delete count + savings | Hardcoded (empty state) | — | — | Dashboard.jsx |
| RI Health Card | Mini Card | RI utilization CTA | Real API | `GET /api/v1/ri/overview` | RIAnalysisService | ri/RIHealthCard.jsx |
| S3 Health Card | Mini Card | S3 tiering savings CTA | Real API | `GET /api/v1/s3/overview` | S3TieringService | s3/S3HealthCard.jsx |
| RDS Health Card | Mini Card | RDS Multi-AZ savings CTA | Real API | `GET /api/v1/rds/overview` | RDSAnalysisService | rds/RDSHealthCard.jsx |
| Data Transfer Card | Mini Card | Transfer cost CTA | Real API | `GET /api/v1/transfer/overview` | TransferService | transfer/TransferHealthCard.jsx |

### 1.3 Infrastructure Tab

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Total Cost KPI | Card | Cluster total cost | Real API | `GET /api/v1/metrics/dashboard` | MetricsService | Dashboard.jsx |
| Total Nodes KPI | Card | Node count (spot/OD) | Real API | `GET /api/v1/clusters` | ClusterService | Dashboard.jsx |
| vCPU/Memory KPIs | Cards | Capacity stats | Hardcoded (0) | — | — | Dashboard.jsx |
| Clusters Card | Card | Cluster list + Discover | Real API | `GET /api/v1/clusters` | ClusterService | Dashboard.jsx |

### 1.4 Governance Tab

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Pending/Active/Consent KPIs | Cards | Governance stats | Hardcoded (0) | — | — | Dashboard.jsx |
| Governance Features rows | Card | Tagging/Automation/Approvals | N/A | — | — | Dashboard.jsx |
| Teams & Members rows | Card | Members/Teams/Roles | N/A | — | — | Dashboard.jsx |

### 1.5 Dashboard Widgets & Config

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| CostKPICard | Widget | Monthly spend + trend arrow | Real API | `GET /api/v1/metrics/dashboard` | MetricsService | widgets/CostKPICard.jsx |
| SavingsKPICard | Widget | Net savings % | Real API | `GET /api/v1/metrics/dashboard` | MetricsService | widgets/SavingsKPICard.jsx |
| SavingsChart | Widget | Cost bar chart (30d) | Real API | `GET /api/v1/metrics/cost/timeseries` | MetricsService | widgets/SavingsChart.jsx |
| PlatformHealthCard | Widget | Uptime (SUPER_ADMIN) | Real API | `GET /api/v1/admin/health` | AdminService | widgets/PlatformHealthCard.jsx |
| TenantListCard | Widget | Org list (SUPER_ADMIN) | Real API | `GET /api/v1/admin/clients` | AdminService | widgets/TenantListCard.jsx |
| Widget Registry | Config | Widget metadata map | N/A | — | — | dashboard/widgetRegistry.js |
| Role Defaults | Config | Default layouts per role | N/A | — | — | dashboard/roleDefaults.js |
| Widget Exports | Config | Central widget barrel | N/A | — | — | dashboard/widgets/index.js |

---

## 2. AtharvaAI Optimizer (9 files, AtharvaAiPage.jsx = 109 lines)

### 2.1 AtharvaAI Main Dashboards

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| AtharvaAiPage | Page | 4-tab ML optimizer layout | Real API | `GET /api/v1/clusters` | ClusterService | pages/AtharvaAiPage.jsx |
| Global Rankings | Card | Top cross-region target pools | Real API | `GET /api/v1/atharvaai/rankings/global` | AdvancedMLPredictorService | atharvaai/GlobalRankingsCard.jsx |
| Blacklist Monitor | Card | ML pool backoffs & saturation | Real API | `GET /api/v1/atharvaai/blacklist/status` | BackoffManager | atharvaai/BlacklistMonitorCard.jsx |
| Pool Rankings | Card list | Top ML eviction predictions | Real API | `GET /api/v1/atharvaai/rankings/{cluster_id}` | AdvancedMLPredictorService | atharvaai/PoolRankings.jsx |
| Auto Rebalance Audit | Timeline | Rebalancing audit log | Real API | `GET /api/v1/atharvaai/rebalancing/status` | AutoRebalancerService | atharvaai/AutoRebalanceAuditCard.jsx |
| Interruption Heatmap | Calendar | 30-day interruption spread | Real API | `GET /api/v1/atharvaai/heatmap/{cluster_id}` | AdvancedMLPredictorService | atharvaai/InterruptionHeatmap.jsx |
| Rebalancing Timeline | Timeline | Sub-hour precision chart | Real API | `GET /api/v1/atharvaai/rebalancing/timeline` | AutoRebalancerService | atharvaai/RebalancingTimeline.jsx |
| Decision Engine | Timeline | 15-step execution visualizer | Real API | `GET /api/v1/atharvaai/decision-engine/{id}` | DecisionEngine | atharvaai/DecisionEngine.jsx |
| Volatility Banner | Banner | Global Volatility/Regime warn | Real API | `GET /api/v1/atharvaai/volatility/{id}` | VolatilityManager | layout/MainLayout.jsx (inline logic) |

---

## 3. Right-Sizing (1 file, 1,178 lines)

### 2.1 Manual Mode — Savings Section (Lines 273–487)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Cluster Selector | Dropdown | Select cluster | Real API | `GET /api/v1/clusters` | ClusterService | RightSizingDashboard.jsx |
| Mode Toggle | Button | Manual ↔ Auto switch | N/A | — | — | RightSizingDashboard.jsx |
| Emergency Pause Controls | Card | Per-cluster pause/resume grid | Computed (local state) | — | — | RightSizingDashboard.jsx |
| Emergency Pause Modal | Modal | Timed/indefinite pause (1/2/4/8/24h presets) | Computed | — | — | RightSizingDashboard.jsx |
| Total Potential Savings KPI | Card | Summed savings across clusters | Real API | `GET /api/v1/clusters` | ClusterService | RightSizingDashboard.jsx |
| Over-provisioned Nodes KPI | Card | Waste node count | Real API | `GET /api/v1/clusters` | ClusterService | RightSizingDashboard.jsx |
| Avg Optimization Score KPI | Card | Computed average from cluster data | Real API | `GET /api/v1/clusters` | ClusterService | RightSizingDashboard.jsx |
| Instances Analyzed KPI | Card | Recommendation count | Real API | `GET /api/v1/karpenter/recommendations` | KarpenterService | RightSizingDashboard.jsx |
| Cluster-wise Savings Chart | Bar chart | Per-cluster savings breakdown | Real API | `GET /api/v1/clusters` | ClusterService | RightSizingDashboard.jsx |
| Top Recommendations | Card list | Top 6 instance resizing recs | Real API | `GET /api/v1/karpenter/recommendations` | KarpenterService | RightSizingDashboard.jsx |
| EV Delta & Risk Columns | Table Cols | Spot EV score + Disruption Risk % | Computed | — | Decision Engine v3 | RightSizingDashboard.jsx |
| Fallbacks Visual Tags | Badges | Top 3 safest fallback instances | Computed | — | PoolRankingService | RightSizingDashboard.jsx |

### 3.2 Manual Mode — Bin-Packing

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| BinpackBlock | Visual | Before/after node consolidation | Real API | `GET /api/v1/karpenter/stats` | KarpenterService | RightSizingDashboard.jsx |

### 2.3 Karpenter Mode (Lines 546–1178)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| KarpenterSection container | Section | Real API recommendations | Real API | `GET /api/v1/karpenter/recommendations` | KarpenterService | RightSizingDashboard.jsx L546 |
| Karpenter Recommendations Table | Table | Instance right-sizing recs | Real API | `GET /api/v1/karpenter/recommendations` | KarpenterService | RightSizingDashboard.jsx |
| Apply Recommendation Modal | Modal | Apply single rec | Real API | `POST /api/v1/karpenter/apply-recommendation/{id}` | KarpenterService | RightSizingDashboard.jsx |
| Batch Apply | Button | Apply multiple recs | Real API | `POST /api/v1/karpenter/apply-recommendations/batch` | KarpenterService | RightSizingDashboard.jsx |
| Activity Feed | List | Recent Karpenter events | Real API | `GET /api/v1/karpenter/activity` | KarpenterService | RightSizingDashboard.jsx |
| Karpenter Status | Card | NodePool live status | Real API | `GET /api/v1/karpenter/status` | KarpenterService | RightSizingDashboard.jsx |
| Mode Toggle per cluster | Toggle | Manual/Auto per cluster | Real API | `PATCH /api/v1/karpenter/mode/{cluster_id}` | KarpenterService | RightSizingDashboard.jsx |
| Settings Panel (5 tabs) | Slide-over | General/NodePool/Consolidation/Drift/Advanced | Real API | `GET/PUT /api/v1/karpenter/config` | KarpenterService | RightSizingDashboard.jsx |
| History Chart | Chart | 7-day optimization history | Real API | `GET /api/v1/karpenter/stats?period=week` | KarpenterService | RightSizingDashboard.jsx |

---

## 3. Resource Hygiene (10 files)

### 3.1 Main Dashboard (CleanupDashboard.jsx, 1,074 lines)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Account Selector | Dropdown | Select AWS account | Real API | `GET /api/v1/accounts` | AccountService | CleanupDashboard.jsx |
| Scan Button | Button | Trigger hygiene scan | Real API | `GET /api/v1/hygiene/scan/{account_id}` | HygieneService | CleanupDashboard.jsx |
| Sidebar (inline) | Nav | Resource type filter (EC2/EBS/EIP/ELB/S3/ECS/RDS) | Computed from scan data | — | — | CleanupDashboard.jsx L111–218 |
| KPI Card — Resources Found | Card | Total resource count | Real API | from scan response | — | CleanupDashboard.jsx L73 |
| KPI Card — Monthly Waste | Card | Estimated waste cost | Real API | `GET /api/v1/hygiene/total-cost` | HygieneService | CleanupDashboard.jsx L532 |
| KPI Card — Safe-to-Delete | Card | Count with safe status | Real API | from scan response | — | CleanupDashboard.jsx |
| KPI Card — Account Cost | Card | Total account cost | Real API | `GET /api/v1/hygiene/total-cost` | HygieneService | CleanupDashboard.jsx |
| Ring Gauge | Chart | Savings % circular | Computed | — | — | CleanupDashboard.jsx L407 |
| Spark Bars | Chart | 7-day trend bars | Computed (fallback L743) | — | — | CleanupDashboard.jsx L429 |
| Resource Table (inline) | Table | Resource list with checkboxes, status, actions | Real API | from scan data | — | CleanupDashboard.jsx L220–389 |
| Bulk Action Bar | Action bar | Tag All / Delete / Terminate buttons | Real API | `POST /api/v1/hygiene/action` | HygieneService | CleanupDashboard.jsx L545 |
| Remediation Wizard buttons | Buttons | Open RI/S3/RDS cost wizards | N/A | — | — | CleanupDashboard.jsx L948–963 |
| Filter Panel | Filters | Status + search + region filter | Props | — | — | cleanup/layout/FilterPanel.jsx |
| Cleanup Sidebar | Nav | Legacy sidebar (unused) | Props | — | — | cleanup/layout/CleanupSidebar.jsx |
| Hero Metrics Panel | Banner | KPI summary (unused) | Props | — | — | cleanup/summary/HeroMetricsPanel.jsx |
| Savings Gauge | Chart | Circular gauge (unused) | Props | — | — | cleanup/summary/SavingsGauge.jsx |
| Resource Table (standalone) | Table | Resource list (unused) | Props | — | — | cleanup/tables/ResourceTable.jsx |

### 3.2 Wizards

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Bulk Tag Wizard | Modal wizard | 3-step tag workflow (592 lines) | Real API | `POST /api/v1/hygiene/action` | HygieneService | cleanup/BulkTagWizard.jsx |
| RI Wizard | Modal wizard | RI waste remediation (150 lines) | Real API | `GET /api/v1/ri/overview` | RIAnalysisService | cleanup/wizards/RIWizard.jsx |
| S3 Wizard | Modal wizard | S3 tiering wizard (188 lines) | Real API | `GET /api/v1/s3/overview` | S3TieringService | cleanup/wizards/S3Wizard.jsx |
| RDS Wizard | Modal wizard | RDS Multi-AZ wizard (157 lines) | Real API | `GET /api/v1/rds/overview` | RDSAnalysisService | cleanup/wizards/RDSWizard.jsx |

---

## 4. Hibernation (28 files)

### 4.1 Schedules (HibernationDashboardNew.jsx, 1,132 lines)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Tab Navigation | Tabs | Schedules/Savings/Emergency/Strategies/Audit | Computed | — | — | HibernationDashboardNew.jsx L968 |
| Schedule List | List | All created schedules | Real API | `GET /api/v1/hibernation/schedules` | HibernationService | HibernationDashboardNew.jsx |
| Schedule Item | Card | Individual schedule (strategy, status, clusters) | Props | — | — | HibernationDashboardNew.jsx L618–717 |
| Schedule Form | Modal form | Create/Edit schedule (name, strategy, clusters, schedule matrix, timezone) | Real API | `POST/PUT /api/v1/hibernation/schedules` | HibernationService | HibernationDashboardNew.jsx L433–616 |
| Schedule Matrix (168-cell grid) | Grid | 7-day × 24-hour drag-to-paint sleep grid | Props | — | — | hibernation/ScheduleMatrix.jsx (205 lines) |
| Matrix Quick Presets | Buttons | Business Hours / Weekends / Nights presets | Computed | — | — | ScheduleMatrix.jsx L55–94 |
| Matrix Stats | KPIs | Sleep Hours / Est. Savings / Awake Hours | Computed | — | — | ScheduleMatrix.jsx L99–101 |
| Toggle Schedule | Switch | Enable/disable schedule | Real API | `PATCH /api/v1/hibernation/schedules/{id}` | HibernationService | HibernationDashboardNew.jsx L925 |
| Delete Schedule | Button | Delete with confirmation | Real API | `DELETE /api/v1/hibernation/schedules/{id}` | HibernationService | HibernationDashboardNew.jsx L937 |
| Live Progress Banner | Banner | Polls active execution status every 2s | Real API | `GET /api/v1/hibernation/status/active` | HibernationService | HibernationDashboardNew.jsx L86–156 |

### 4.2 Strategies

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Strategy Selector | Card grid | 3 strategy cards (Namespace Sleep, Node Drain, Full Cluster) | Hardcoded `STRATEGIES[]` L13–58 | — | — | HibernationDashboardNew.jsx L393–431 |
| Strategy Reference | Table | Comparison table (wake time, savings, risk) | Hardcoded `STRATEGIES[]` | — | — | HibernationDashboardNew.jsx L828–864 |

### 4.3 Execution History / Audit

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Audit History widget | Card | Last 5 executions + auto-refresh 30s | Real API | `GET /api/v1/audit/logs?resource_type=HIBERNATION&limit=5` | AuditService | hibernation/AuditHistory.jsx (154 lines) |
| Savings Report | Dashboard | Monthly/weekly savings with charts | Real API | `GET /api/v1/hibernation/savings/history` | HibernationService | HibernationDashboardNew.jsx L158–382 |
| Emergency Controls | Panel | Wake-all / Sleep-now per cluster | Real API | `POST /api/v1/hibernation/emergency/*` | HibernationService | HibernationDashboardNew.jsx L719–826 |

### 4.4 Other Hibernation Files

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Schedule Calendar | Calendar | Visual calendar view (302 lines) | Props | — | — | hibernation/ScheduleCalendar.jsx |
| Unified Schedule Grid | Grid | Alternate 168-hour grid (346 lines) | Props | — | — | hibernation/UnifiedScheduleGrid.jsx |
| Schedule Builder | Builder | Schedule creation UI | Props | — | — | hibernation/ScheduleBuilder.jsx |
| Schedule Templates | Templates | Preset schedule library | Props | — | — | hibernation/ScheduleTemplates.jsx |
| Schedule Modal | Modal | Create schedule dialog | Real API | `POST /api/v1/hibernation/schedules` | HibernationService | hibernation/ScheduleModal.jsx |
| Conflict Detection Modal | Modal | Schedule overlap detection | Computed | — | — | hibernation/ConflictDetectionModal.jsx |
| Status Banner | Banner | Live execution status | Real API | `GET /api/v1/hibernation/status/active` | HibernationService | hibernation/StatusBanner.jsx |
| Strategy Selector (standalone) | Cards | 3 strategy cards (standalone version) | Props | — | — | hibernation/StrategySelector.jsx |
| Validation Panel | Panel | Pre-execution validation checks | Props | — | — | hibernation/ValidationPanel.jsx |
| Notification Settings | Form | Email/Slack config | Real API | `GET/PUT /api/v1/hibernation/notifications` | HibernationService | hibernation/NotificationSettings.jsx |
| Hibernation Wizard | Wizard | 3-step setup (411 lines) | Real API | `POST /api/v1/hibernation/setup` | HibernationService | hibernation/HibernationWizard.jsx |
| Cost Analytics Dashboard | Dashboard | Savings analytics (481 lines) | Real API | `GET /api/v1/hibernation/savings/history` | HibernationService | hibernation/CostAnalyticsDashboard.jsx |
| Cost Analytics (alt) | Component | Alternate cost analysis view | Props | — | — | hibernation/CostAnalytics.jsx |
| Emergency Controls (standalone) | Panel | Standalone emergency panel | Real API | `POST /api/v1/hibernation/emergency/*` | HibernationService | hibernation/EmergencyControls.jsx |
| Execution History | Page | Full audit trail | Real API | `GET /api/v1/hibernation/audit-logs` | HibernationService | hibernation/ExecutionHistory.jsx |
| Hibernation Type Card | Card | Strategy info display card | Props | — | — | hibernation/HibernationTypeCard.jsx |
| Dashboard Tab | Tab | Dashboard sub-tab view | Props | — | — | hibernation/DashboardTab.jsx |
| Cluster Overview | Component | Cluster summary display | Props | — | — | hibernation/ClusterOverview.jsx |
| Hibernation Header | Component | Page header bar | Props | — | — | hibernation/HibernationHeader.jsx |
| History Log | Component | History log viewer | Props | — | — | hibernation/HistoryLog.jsx |
| Multi Timezone | Component | Multi-timezone support | Props | — | — | hibernation/MultiTimezone.jsx |
| Advanced Configuration | Component | Advanced settings panel | Props | — | — | hibernation/AdvancedConfiguration.jsx |
| Time Based Rules | Component | Time-based rule config | Props | — | — | hibernation/TimeBasedRules.jsx |
| Index barrel | Export | Re-exports HibernationDashboard | N/A | — | — | hibernation/index.js |

---

## 5. Clusters (10 files, ClusterList.jsx = 1,111 lines)

### 5.1 Master-Detail View

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Clusters Page container | Page | Master-detail layout | Real API | `GET /api/v1/clusters` | ClusterService | clusters/ClusterList.jsx |
| Cluster List (left panel) | List | Cluster cards with status dots | Real API | `GET /api/v1/clusters` | ClusterService | ClusterList.jsx L375–460 |
| Discover Clusters button | Button | Trigger AWS discovery | Real API | `POST /api/v1/clusters/discover` | ClusterService | ClusterList.jsx L943 |
| Cluster Detail (right panel) | Detail | Full cluster info, 3 sections | Real API | `GET /api/v1/clusters/{id}` | ClusterService | ClusterList.jsx L471–788 |
| KPI Strip (4 cards) | Cards | Cost, Nodes, CPU %, Memory % | Computed from cluster data | — | — | ClusterList.jsx |
| Node Treemap | Visualization | Grid of node blocks (paginated 20/page) | Props from cluster.nodes | — | — | ClusterList.jsx L119–349 |
| Spot Ring gauge | Chart | Spot/On-Demand/Fallback ratio ring | Props | — | — | ClusterList.jsx L351–373 |
| No-Agent Detail | Card | CTA for installing agent | Props | — | — | ClusterList.jsx L790–817 |

### 5.2 Sub-Components

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Delete Modal | Modal | Delete with pre-checks | Real API | `DELETE /api/v1/clusters/{id}` | ClusterService | clusters/ClusterDeleteModal.jsx |
| Disconnect Modal | Modal | Disconnect confirm | Real API | `POST /api/v1/clusters/{id}/disconnect` | ClusterService | clusters/ClusterDisconnectModal.jsx |
| Cluster Details (standalone) | Modal | Detail modal (alt) | Real API | `GET /api/v1/clusters/{id}` | ClusterService | clusters/ClusterDetails.jsx |
| • Optimization Mode Selector | Dropdown | Cost / Balanced / Zero Downtime | Real API | `PATCH /api/v1/clusters/{id}` | ClusterService | clusters/ClusterDetails.jsx |
| • Stateless Workload Classification | Badge | ML-driven workload risk tag | Real API | `GET /api/v1/clusters/{id}/classification` | WorkloadInspector | clusters/ClusterDetails.jsx |
| • Substitute Engine Status | Card | Prewarming state tracking | Real API | `GET /api/v1/substitute/status/{cluster_id}` | SubstituteManager | clusters/ClusterDetails.jsx |
| • Cooldown Status Widget | Widget | Active cooldown timeline | Real API | `GET /api/v1/cooldown/{cluster_id}` | CooldownEnforcer | clusters/ClusterDetails.jsx |
| • Circuit Breaker Panel | Panel | Active interruption blocks | Real API | `GET /api/v1/execution/status/{cluster_id}` | DecisionEngine | clusters/ClusterDetails.jsx |
| Health Timeline | Timeline | Health history | Props | — | — | clusters/ClusterHealthTimeline.jsx |
| Utilization Sparkline | Chart | Inline sparkline | Props | — | — | clusters/ClusterUtilizationSparkline.jsx |
| Node List | Table | Node management | Real API | `GET /api/v1/clusters/{id}/nodes` | ClusterService | clusters/NodeList.jsx |
| Node Group Breakdown | View | Node group view | Props | — | — | clusters/NodeGroupBreakdown.jsx |
| Policy Gap Alert | Alert | Policy violation alerts | Props | — | — | clusters/PolicyGapAlert.jsx |
| Spot Ratio Gauge | Gauge | Spot vs OD gauge | Props | — | — | clusters/SpotRatioGauge.jsx |

---

## 6. Node Templates (2 files)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Template List | Page | Grid of template cards (207 lines) | Real API | `GET /api/v1/templates` | TemplateService | templates/TemplateList.jsx |
| Template Card | Card | Name, architecture, families, usage stats | Props | — | — | TemplateList.jsx |
| Create Template button | Button | Opens TemplateBuilder modal | N/A | — | — | TemplateList.jsx |
| Delete Template | Button | Confirm + delete | Real API | `DELETE /api/v1/templates/{id}` | TemplateService | TemplateList.jsx L56 |
| Set Default | Button | Set as default template | Real API | `PUT /api/v1/templates/{id}/default` | TemplateService | TemplateList.jsx L46 |
| Test in AtharvaAI | Button | Navigate to `/atharvaai?template_id={id}` | N/A | — | — | TemplateList.jsx |
| Template Builder | Modal form | 4 sections: General, Instance Families, Taints, SGs (412 lines) | Real API | `POST /api/v1/templates`, `GET /api/v1/templates/options` | TemplateService | templates/TemplateBuilder.jsx |
| Family multi-select | Checkboxes | Instance family selection | Real API | `GET /api/v1/templates/options` | TemplateService | TemplateBuilder.jsx L43 |
| Taints editor | Dynamic list | Key/Value/Effect taint builder | Computed | — | — | TemplateBuilder.jsx L88 |

---

## 7. Approvals (pages/Approvals.jsx, 506 lines + 3 components)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Approvals Page | Page | 3-tab approval manager | Real API | `GET /api/v1/approvals/` | ApprovalService | pages/Approvals.jsx |
| My Requests tab | Tab | User's own JIT requests | Real API | `GET /api/v1/approvals/?filter=mine` | ApprovalService | Approvals.jsx L153 |
| Received tab | Tab | Requests pending approval | Real API | `GET /api/v1/approvals/?filter=received` | ApprovalService | Approvals.jsx |
| All Requests tab | Tab | All org-wide requests | Real API | `GET /api/v1/approvals/` | ApprovalService | Approvals.jsx |
| Approve action | Button | Approve JIT request | Real API | `POST /api/v1/approvals/{id}/approve` | ApprovalService | Approvals.jsx L50 |
| Revoke action | Button | Revoke active grant | Real API | `POST /api/v1/approvals/{id}/revoke` | ApprovalService | Approvals.jsx L66 |
| Reject action | Button | Reject request | Real API | `POST /api/v1/approvals/{id}/reject` | ApprovalService | Approvals.jsx L82 |
| Active JIT Banner | Banner | Active JIT grant indicator | Real API | `GET /api/v1/approvals/active-window` | ApprovalService | governance/ActiveJITBanner.jsx |
| Ticket Request Modal | Modal | Full ticket creation form (511 lines) | Real API | `POST /api/v1/approvals/jit-request` | ApprovalService | approvals/TicketRequestModal.jsx |
| Access Request Modal | Modal | Quick JIT access request | Real API | `POST /api/v1/approvals/jit-request` | ApprovalService | approvals/AccessRequestModal.jsx |
| JIT Request Modal | Modal | JIT elevation form | Real API | `POST /api/v1/approvals/jit-request` | ApprovalService | governance/JITRequestModal.jsx |
| Risk Badge | Badge | Risk level indicator | Props | — | — | shared/RiskBadge.jsx |

---

## 8. Tag Governance (TagGovernancePage.jsx, 1,490 lines + 2 wrappers)

### 8.1 Policies Tab (Lines 269–356)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Policies list | Table | All defined tag policies | Real API | `GET /api/v1/governance/policies` | GovernanceService | TagGovernancePage.jsx |
| Policy Row | Row | Policy with toggle/edit/delete | Props | — | — | TagGovernancePage.jsx L358–408 |
| Policy Create/Edit Modal | Modal | Full policy editor (conditions, actions, scope) | Real API | `POST/PUT /api/v1/governance/policies` | GovernanceService | TagGovernancePage.jsx L410–488 |

### 8.2 Templates Tab (Lines 490–592)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Tag Templates grid | Grid | Tag template cards | Real API | `GET /api/v1/governance/tag-templates` | TagManagementService | TagGovernancePage.jsx |
| Template Card | Card | Template with tags + scope badge | Props | — | — | TagGovernancePage.jsx L594–673 |
| Template Builder wizard | Full page | 3-step builder for tag templates | Real API | `POST /api/v1/governance/tag-templates` | TagManagementService | TagGovernancePage.jsx L675–948 |

### 8.3 Scoring Tab (Lines 950–1086)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Score Donut chart | Donut | Org-wide compliance score (0-100) | Real API | `GET /api/v1/governance/scoring` | TagScoringService | TagGovernancePage.jsx L158–177 |
| Compliance Bar | Bar | Per-resource compliance % | Computed | — | — | TagGovernancePage.jsx L179–190 |
| Tag Heatmap | Grid | Tag coverage by resource type | Computed | — | — | TagGovernancePage.jsx L192–202 |

### 8.4 Automation Tab (Lines 1088–1313)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Automation rules list | Table | Auto-tagging rules | Real API | `GET /api/v1/governance/automation` | TagAutomationService | TagGovernancePage.jsx |
| New Automation Rule modal | Modal | Create rule with triggers + tag actions | Real API | `POST /api/v1/governance/automation` | TagAutomationService | TagGovernancePage.jsx L1201–1313 |
| Run Autopilot button | Button | One-click tag automation | Real API | `POST /api/v1/governance/run-autopilot` | TagAutomationService | TagGovernancePage.jsx |

### 8.5 Monitor Tab (Lines 1315–1490)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Drift Monitor | Dashboard | Real-time compliance drift | Real API | `GET /api/v1/governance/drift` | TagComplianceService | TagGovernancePage.jsx |
| Compliance Timeline | Timeline | Historical compliance changes | Real API | `GET /api/v1/governance/timeline` | TagComplianceService | TagGovernancePage.jsx |

### 8.6 Wrappers

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| TagPoliciesManager | Wrapper | Thin redirect to TagGovernancePage (16 lines) | N/A | — | — | settings/TagPoliciesManager.jsx |
| TagTemplateManager | Manager | Standalone template CRUD (500 lines) | Real API | `POST/PUT /api/v1/governance/tag-templates` | TagManagementService | settings/TagTemplateManager.jsx |
| GovernanceSettings | Manager | Automation toggles (254 lines) | Real API | `GET /api/v1/governance/policies` | GovernanceService | settings/GovernanceSettings.jsx |
| Tag Policies List | Table | Tag policy listing | Real API | `GET /api/v1/policies` | PolicyService | settings/TagPoliciesList.jsx |

---

## 9. Teams & Members (3 tab components + 2 page files)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Teams Page | Page | 3-tab layout | Real API | Multiple | — | pages/Teams.jsx |
| Members Tab | Tab | Member list + invite + remove (167 lines) | Real API | `GET /api/v1/organization/members` | OrganizationService | teams/MembersTab.jsx |
| Invite Member form | Form | Name + email + role selector | Real API | `POST /api/v1/organization/invitations` | OrganizationService | MembersTab.jsx L267 |
| Teams Tab | Tab | Team cards + create team | Real API | `GET /api/v1/teams/` | TeamService | teams/TeamsTab.jsx |
| Roles & Policies Tab | Tab | Role CRUD + permission matrix | Real API | `GET /api/v1/roles` | RoleService | teams/RolesPoliciesTopTab.jsx |
| Create Role modal | Modal | Role name + description + permissions | Real API | `POST /api/v1/roles` | RoleService | RolesPoliciesTopTab.jsx L111 |
| Team Details Page | Page | Team members + governance + analytics (680 lines) | Real API | `GET /api/v1/teams/{id}` | TeamService | pages/TeamDetails.jsx |
| Member Permissions Modal | Modal | Edit member permissions | Real API | `PUT /api/v1/permissions/{id}` | PermissionService | settings/MemberPermissionsModal.jsx |
| Team Governance | Page | Team-level governance settings | Real API | `GET /api/v1/teams/` | TeamService | settings/TeamGovernance.jsx |

---

## 10. Audit Logs (AuditLog.jsx, 454 lines)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Audit Log Page | Page | Filterable audit trail | Real API | `GET /api/v1/audit/logs` | AuditService | audit/AuditLog.jsx |
| Event Type Filter | Dropdown | 16 event types (login, cluster.created, schedule.toggled, etc.) | Hardcoded event list L11–33 | — | — | AuditLog.jsx |
| Diff Viewer Modal | Modal | Before/after JSON diff | Computed (calculates diff) | — | — | AuditLog.jsx L83–98 |
| Export CSV | Button | Download filtered logs as CSV | Real API | `GET /api/v1/audit/export` | AuditService | AuditLog.jsx L121 |
| Clear Filters | Button | Reset all filters | Computed | — | — | AuditLog.jsx L146 |
| Event Badge | Badge | Color-coded event type badge | Computed | — | — | AuditLog.jsx L158 |

---

## 11. Settings (Settings.jsx, 220 lines + 3 tab components)

### 11.1 Account Settings Tab (AccountSettings.jsx, 379 lines)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Profile Section | Form | Name + email update | Real API | `PUT /api/v1/auth/profile` | AuthService | settings/AccountSettings.jsx |
| Password Change | Form | Current + new + confirm password | Real API | `POST /api/v1/auth/change-password` | AuthService | AccountSettings.jsx L63 |
| Preferences | Form | Timezone, theme, notifications | Real API | `PUT /api/v1/users/me/preferences` | UserService | AccountSettings.jsx L97 |

### 11.2 Cloud Integrations Tab (CloudIntegrations.jsx, 501 lines)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Connection Info | Card | External ID + Account ID for AWS | Real API | `GET /api/v1/organization/connection-info` | AuthService | settings/CloudIntegrations.jsx |
| Regenerate External ID | Button | Generate new external ID | Real API | `POST /api/v1/organization/connection-info/regenerate` | AuthService | CloudIntegrations.jsx L60 |
| Connected Accounts list | List | AWS accounts with status | Real API | `GET /api/v1/accounts` | AccountService | CloudIntegrations.jsx L76 |
| Add Account form | Form | Role ARN input | Real API | `POST /api/v1/accounts` | AccountService | CloudIntegrations.jsx L88 |
| Validate Account | Button | Test AWS connection | Real API | `POST /api/v1/accounts/{id}/validate` | AccountService | CloudIntegrations.jsx L117 |
| Delete Account | Button | Remove AWS account | Real API | `DELETE /api/v1/accounts/{id}` | AccountService | CloudIntegrations.jsx L164 |

### 11.3 Billing Tab (inline BillingTab, 147 lines)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Billing Status | Card | Plan, status, period | Real API | `GET /api/v1/billing/status` | BillingService | Settings.jsx L76 |
| Usage Summary | Card | Clusters, members, scans | Real API | `GET /api/v1/billing/costs/summary` | BillingService | Settings.jsx |
| Manage Billing | Button | Opens Stripe portal | Real API | `POST /api/v1/billing/create-portal-session` | BillingService | Settings.jsx L116 |

---

## 12. Admin Panel (9 files)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Admin Dashboard | Container | Tab routing for admin | N/A | — | — | admin/AdminDashboard.jsx |
| Admin Clients | Page | Client/tenant CRUD | Real API | `GET /api/v1/admin/clients` | AdminService | admin/AdminClients.jsx |
| Admin Organizations | Page | Organization management | Real API | `GET /api/v1/admin/organizations` | AdminService | admin/AdminOrganizations.jsx |
| Admin Health | Page | Platform health & ML Inference Status | Real API | `GET /api/v1/admin/health` | AdminService + SystemMonitor | admin/AdminHealth.jsx |
| Admin Config | Page | System config K/V editor | Real API | `GET /api/v1/admin/config` | AdminService | admin/AdminConfig.jsx |
| Admin Billing | Page | Billing + usage | Real API | `GET /api/v1/admin/billing` | AdminService | admin/AdminBilling.jsx |
| Admin Experiments | Page | Experiment lab | Real API | `GET /api/v1/lab/experiments` | LabService | admin/AdminExperiments.jsx |
| Platform Settings | Page | Platform config | Real API | `GET /api/v1/admin/config` | AdminService | admin/PlatformSettings.jsx |
| Admin Overview | Page | Admin overview | Computed | — | — | admin/AdminOverview.jsx |

---

## 13. AtharvaAI (5 files)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| AtharvaAI Page | Page | 3-tab layout (Rankings/Heatmap/Timeline) | N/A | — | — | pages/AtharvaAiPage.jsx |
| Pool Rankings | Dashboard | ML pool rankings table (353 lines) | Real API | `POST /api/v1/atharvaai/pools/rankings` | PoolRankingService | atharvaai/PoolRankings.jsx |
| Interruption Heatmap | Heatmap | Spot interruption frequency (159 lines) | Real API | `GET /api/v1/atharvaai/interruption-heatmap` | PoolRankingService | atharvaai/InterruptionHeatmap.jsx |
| Rebalancing Timeline | Timeline | Auto-rebalancing events (125 lines) | Real API | `GET /api/v1/atharvaai/rebalancing/status` | PoolRankingService | atharvaai/RebalancingTimeline.jsx |
| Auto Rebalance Audit | Card | Compact audit (157 lines) | Real API | `GET /api/v1/atharvaai/rebalancing/status` | PoolRankingService | atharvaai/AutoRebalanceAuditCard.jsx |
| Pool Rankings CSS | Styles | Table styles | N/A | — | — | atharvaai/PoolRankings.css |

---

## 14. Other Components

### Auth (3 files)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Login | Form | Login form with email/password | Real API | `POST /api/v1/auth/login` | AuthService | auth/Login.jsx |
| Signup | Form | Registration form | Real API | `POST /api/v1/auth/signup` | AuthService | auth/Signup.jsx |
| Invite Acceptance | Form | Accept org invite | Real API | `POST /api/v1/auth/invitation-response` | AuthService | auth/InviteAcceptance.jsx |

### Onboarding (4 files)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Welcome Step | Step | Welcome screen with overview | N/A | — | — | onboarding/WelcomeStep.jsx |
| Connect Step | Step | AWS role ARN entry | Real API | `GET /api/v1/onboarding/aws-link` | OnboardingService | onboarding/ConnectStep.jsx |
| Verify Step | Step | Connection verification polling | Real API | `POST /api/v1/onboarding/verify` | OnboardingService | onboarding/VerifyStep.jsx |
| Success Step | Step | Success confirmation + next steps | N/A | — | — | onboarding/SuccessStep.jsx |

### Governance (4 files)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Permission Gate | HOC | RBAC wrapper | Computed | `GET /api/v1/permissions/check` | PermissionService | governance/PermissionGate.jsx |
| Protected Button | Button | Button with perm check | Computed | — | — | governance/ProtectedButton.jsx |
| JIT Request Modal | Modal | JIT elevation form | Real API | `POST /api/v1/approvals/jit-request` | ApprovalService | governance/JITRequestModal.jsx |
| Active JIT Banner | Banner | Active grant indicator | Real API | `GET /api/v1/approvals/active-window` | ApprovalService | governance/ActiveJITBanner.jsx |

### Policies (3 files)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Policy Config | Form | Spot policy config (26 settings) | Real API | `GET/PUT /api/v1/policies/{id}` | PolicyService | policies/PolicyConfig.jsx |
| Permission Matrix | Grid | Permission grid editor | Real API | `GET /api/v1/roles/permissions` | RoleService | policies/PermissionMatrix.jsx |
| Cleanup Policies | Page | Cleanup policy config | Real API | `GET /api/v1/policies` | PolicyService | policies/CleanupPolicies.jsx |

### Cost Health Checks (8 files)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| RI Analysis + Health Card | Dashboard + Card | RI analysis | Real API | `GET /api/v1/ri/overview` | RIAnalysisService | ri/RIAnalysis.jsx, ri/RIHealthCard.jsx |
| S3 Analysis + Health Card | Dashboard + Card | S3 tiering | Real API | `GET /api/v1/s3/overview` | S3TieringService | s3/S3Analysis.jsx, s3/S3HealthCard.jsx |
| RDS Analysis + Health Card | Dashboard + Card | RDS Multi-AZ | Real API | `GET /api/v1/rds/overview` | RDSAnalysisService | rds/RDSAnalysis.jsx, rds/RDSHealthCard.jsx |
| Transfer Analysis + Health Card | Dashboard + Card | Data transfer costs | Real API | `GET /api/v1/transfer/overview` | TransferService | transfer/TransferAnalysis.jsx, transfer/TransferHealthCard.jsx |

### Shared Design System (12 files)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Notification Panel | Panel | Global slide-over notifications | Real API | Multiple (`hygiene`, `karpenter`, `approvals`, `atharvaai`, `hibernation`) | Multiple Services | shared/NotificationPanel.jsx |
| NCard | Card | Individual notification card | Props | — | — | shared/NotificationPanel.jsx |
| FilterTab | Tab | Filter notifications by category | Props | — | — | shared/NotificationPanel.jsx |
| Notification Components | Components | `DrainBar`, `ApprovalRow`, `SavingsRow`, etc. | Props | — | — | shared/NotificationPanel.jsx |
| Button | Primitive | Button with variants (primary/outline/danger) | N/A | — | — | shared/Button.jsx |
| Card | Primitive | Container card wrapper | N/A | — | — | shared/Card.jsx |
| Badge | Primitive | Color-coded badge/tag | N/A | — | — | shared/Badge.jsx |
| Input | Primitive | Form input with label/error | N/A | — | — | shared/Input.jsx |
| Dropdown | Primitive | Select dropdown | N/A | — | — | shared/Dropdown.jsx |
| Switch | Primitive | Toggle switch | N/A | — | — | shared/Switch.jsx |
| GaugeChart | Primitive | Circular gauge chart | N/A | — | — | shared/GaugeChart.jsx |
| StatsCard | Primitive | KPI stats card with trend | N/A | — | — | shared/StatsCard.jsx |
| EmptyState | Primitive | Empty state placeholder | N/A | — | — | shared/EmptyState.jsx |
| RiskBadge | Primitive | Risk level indicator badge | N/A | — | — | shared/RiskBadge.jsx |
| Shared Index | Export | Central barrel export | N/A | — | — | shared/index.js |

### Layout (1 file)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| MainLayout | Layout | Sidebar + content wrapper + Notification Bell | Real API | `GET /api/v1/clusters` (sidebar) | ClusterService | layout/MainLayout.jsx |

### Pages (7 files — 4 already documented inline above, 3 listed here)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Account Analytics | Page | AWS account cost analytics (350 lines) | Real API | `GET /api/v1/metrics/accounts/{id}` | MetricsService | pages/AccountAnalytics.jsx |
| Onboarding | Page | 4-step new user wizard (210 lines) | Real API | `GET /api/v1/onboarding/state` | OnboardingService | pages/Onboarding.jsx |
| Roles | Page | Role management + permission matrix (280 lines) | Real API | `GET /api/v1/roles` | RoleService | pages/Roles.jsx |

> **Also documented inline:** `pages/Approvals.jsx` (§7), `pages/Teams.jsx` + `pages/TeamDetails.jsx` (§9), `pages/AtharvaAiPage.jsx` (§13)

---

## 15. UNUSED / DUPLICATE / UNWIRED — Cleanup Audit

### 15.1 🔴 ORPHAN Components (No Import Found)

| Component | Lines | Category | Recommendation | Reason |
|-----------|-------|----------|----------------|--------|
| **settings/TeamManagement.jsx** | 48KB | LEGACY | 🗑️ DELETE | Superseded by `teams/MembersTab.jsx` + `TeamsTab.jsx` |
| **settings/GovernanceManager.jsx** | ~480 | DUPLICATE | 🗑️ DELETE | Overlaps with GovernanceSettings.jsx |
| **approvals/ActiveWindowBanner.jsx** | ~120 | DUPLICATE | 🗑️ DELETE | Duplicate of governance/ActiveJITBanner.jsx |
| **hibernation/HibernationScheduler.jsx** | 622 | ORPHAN | 🔌 WIRE UP | May be intended for schedule tab |
| **hibernation/HibernationWizard.jsx** | 411 | ORPHAN | 🔌 WIRE UP | Setup wizard not routed |
| **hibernation/UnifiedScheduleGrid.jsx** | 346 | ORPHAN | 🔌 WIRE UP | Alternate schedule grid |
| **hibernation/ScheduleTemplates.jsx** | 284 | ORPHAN | 🔌 WIRE UP | Preset schedules |
| **hibernation/DashboardTab.jsx** | — | ORPHAN | 🔌 WIRE UP | Dashboard sub-tab |
| **hibernation/ClusterOverview.jsx** | — | ORPHAN | 🔌 WIRE UP | Cluster summary |
| **hibernation/HibernationHeader.jsx** | — | ORPHAN | 🔌 WIRE UP | Header |
| **hibernation/HistoryLog.jsx** | — | ORPHAN | 🔌 WIRE UP | History log |
| **hibernation/MultiTimezone.jsx** | — | ORPHAN | 🔌 WIRE UP | Timezone support |
| **hibernation/AdvancedConfiguration.jsx** | — | ORPHAN | 🔌 WIRE UP | Advanced settings |
| **hibernation/TimeBasedRules.jsx** | — | ORPHAN | 🔌 WIRE UP | Time rules |
| **clusters/ClusterDetails.jsx** | ~520 | ORPHAN | 🔌 WIRE UP | Detail modal (inline version exists in ClusterList) |
| **clusters/ClusterDeleteModal.jsx** | ~200 | ORPHAN | 🔌 WIRE UP | Delete modal |
| **clusters/ClusterDisconnectModal.jsx** | ~150 | ORPHAN | 🔌 WIRE UP | Disconnect modal |
| **clusters/ClusterUtilizationSparkline.jsx** | ~120 | ORPHAN | 🔌 WIRE UP | Sparkline |
| **clusters/PolicyGapAlert.jsx** | ~160 | ORPHAN | 🔌 WIRE UP | Policy alerts |
| **clusters/SpotRatioGauge.jsx** | ~120 | ORPHAN | 🔌 WIRE UP | Gauge (inline version in ClusterList) |
| **cleanup/layout/CleanupSidebar.jsx** | ~200 | ORPHAN | 🔌 WIRE UP | Sidebar (inline version in CleanupDashboard) |
| **cleanup/summary/HeroMetricsPanel.jsx** | ~150 | ORPHAN | 🔌 WIRE UP | KPI panel (inline version in CleanupDashboard) |

**Summary: 22 orphans. 3 DELETE (duplicates). 19 WIRE UP.**

### 15.2 ⚠️ FAKE Data in Production Code

| Component | What Was Fake | Status | Resolution |
|-----------|-------------|--------|------------|
| RightSizingDashboard.jsx | `const CLUSTERS = [...]` 4 hardcoded clusters | ✅ RESOLVED | Now uses `clusterAPI.listClusters()` |
| RightSizingDashboard.jsx | `const RECOMMENDATIONS = {...}` 8 hardcoded recs | ✅ RESOLVED | Now uses `karpenterAPI.getRecommendations()` |
| RightSizingDashboard.jsx | `const BINPACK_DATA = {...}` hardcoded binpack | ✅ RESOLVED | Now uses `karpenterAPI.getStats()` |
| RightSizingDashboard.jsx | `const ACTIVITY = [...]` 5 hardcoded events | ✅ RESOLVED | Mock fallback removed, empty array on error |
| RightSizingDashboard.jsx | `const HISTORY_EVENTS = [...]` 7-day fake | ✅ RESOLVED | Now uses `karpenterAPI.getStats('week')` |
| RightSizingDashboard.jsx | KPI strips, CPU gauges, 7-day benefits table | ✅ RESOLVED | Wired to `karpenterAPI.getStats('week')` |
| RightSizingDashboard.jsx | Activity fallback to mock | ✅ RESOLVED | Empty array on error |
| RightSizingDashboard.jsx | History chart mock fallback | ✅ RESOLVED | Empty array on error |
| TagGovernancePage.jsx | `const preview = [...]` fake resources | ✅ RESOLVED | Now uses `tagScoringAPI.preview()` |
| TagGovernancePage.jsx | `const resources = [...]` monitor list & KPIs | ✅ RESOLVED | Now uses `tagComplianceAPI.listResources()` |
| TeamsTab.jsx | Hardcoded `$4,820` / `$1,446` stats on TeamCard | ✅ RESOLVED | Wired to real API `team` properties |
| CleanupDashboard.jsx | Sparkline fallback values | 🟢 KEPT | Intentional graceful degradation |

### 15.3 🔴 Backend Endpoints NOT Called from Frontend

| Endpoint | Route File | Recommendation |
|----------|-----------|----------------|
| `GET /api/v1/hygiene/discover` | hygiene_routes.py | 🔌 WIRE UP |
| `GET /api/v1/hygiene/cost-services` | hygiene_routes.py | 🔌 WIRE UP |
| `GET /api/v1/atharvaai/health` | atharvaai_routes.py | 🔌 WIRE UP |
| `GET /api/v1/atharvaai/blacklist/check` | atharvaai_routes.py | Internal only |
| `POST /api/v1/clusters/{id}/fallback` | cluster_routes.py | 🔌 WIRE UP |
| `POST /api/v1/clusters/{id}/costs` | cluster_routes.py | 🔌 WIRE UP |
| `POST /api/v1/onboarding/reset` | onboarding_routes.py | 🔌 WIRE UP |
| `POST /api/v1/onboarding/authorize` | onboarding_routes.py | 🔌 WIRE UP |
| `GET /api/v1/health/system` | health_routes.py | 🔌 WIRE UP |
| `POST /api/v1/s3/analyze` | s3_routes.py | 🔌 WIRE UP |
| `POST /api/v1/rds/analyze` | rds_routes.py | 🔌 WIRE UP |

### 15.4 Frontend API Calls with No Backend Route

| Frontend Call | Status |
|---------------|--------|
| `GET /api/v1/admin/agent-fleet` | ❌ Missing |
| `GET /api/v1/admin/dashboard` | ❌ Missing |
| `GET /api/v1/admin/stats` | ❌ Missing |
| `GET /api/v1/billing/create-portal-session` | ❌ Missing |
| `GET /api/v1/billing/costs/summary` | ❌ Missing |
| `GET /api/v1/billing/status` | ❌ Missing |

---

**Total: 134 files + 7 pages = 141 · Orphans: 22 · Fake Data: 0 (7 resolved, 1 kept as graceful degradation) · Unused Backend: 11 · Missing Backend: 6**
