# All UI Components — Complete Frontend Inventory

> **Format:** Section → Subsection → 7-column table
>
> **Data Source Legend:** `Real API` · `Hardcoded (FAKE)` · `Computed` · `Props` · `N/A`
>
> **Last Updated:** 2026-02-28 — Deep-dive audit + logic.md cross-reference + codebase verification (line counts re-verified via `wc -l`)
>
> **Total:** 136 component files + 8 pages + 11 infrastructure = 155 frontend files (5 ghost entries removed, 1 new component added, 11 infra files newly documented)

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

## 2. AtharvaAI Optimizer (14 files, AtharvaAiPage.jsx = 122 lines)

> **Sidebar:** COST INTELLIGENCE › AtharvaAI Optimizer › Dashboard | Decision Engine v3 | Pool Rankings | Interruption Heatmap | Rebalancing

### 2.1 Dashboard Sub-Tab (`/atharva-ai?tab=dashboard`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| AtharvaAiPage | Page | 5-tab ML optimizer layout | Real API | `GET /api/v1/clusters` | ClusterService | pages/AtharvaAiPage.jsx |
| Global Rankings | Card | Top cross-region target pools | Real API | `GET /api/v1/atharvaai/rankings/global` | GlobalPoolCacheService (65-min TTL, 50 pools/region) | atharvaai/GlobalRankingsCard.jsx |
| Blacklist Monitor | Card | ML pool backoffs & saturation | Real API | `GET /api/v1/atharvaai/blacklist/status` | BlacklistService (tiered TTL: 6h/12h/24h+backoff, cascade at 70%) | atharvaai/BlacklistMonitorCard.jsx |
| Auto Rebalance Audit | Timeline | Rebalancing audit log | Real API | `GET /api/v1/atharvaai/rebalancing/status` | auto_rebalancer.py (Emergency 90s / Graceful 10min) | atharvaai/AutoRebalanceAuditCard.jsx |
| Volatility Banner | Banner | Global Volatility/Regime warn | Real API | `GET /api/v1/atharvaai/volatility/{id}` | EventMonitor.detect_volatility_regime (75th percentile, 2h TTL) | layout/MainLayout.jsx (inline logic) |

### 2.2 Decision Engine v3 Sub-Tab (`/atharva-ai?tab=decision-engine-v3`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Decision Engine V3 Dashboard | Dashboard | 15-step pipeline visualizer + observability metrics | Real API | `GET /api/v1/atharvaai/decision-engine/state`, `/metrics` | DecisionEngine (15-step pipeline: cooldown→pricing→classification→risk ceiling→diversity→delta) | atharvaai/DecisionEngineV3Dashboard.jsx |
| Optimization Mode Selector | Selector | Cost/Balanced/ZeroDowntime mode picker | Real API | `PATCH /api/v1/atharvaai/optimization-mode/{cluster_id}` | DecisionEngine (3 profiles: COST_FIRST/BALANCED/NO_DOWNTIME_FIRST) | atharvaai/OptimizationModeSelector.jsx |
| Diversity Gauge | Gauge | Pool diversity visualization | Real API | `GET /api/v1/atharvaai/diversity/{cluster_id}` | DiversityEnforcer (max_family_ratio 30-40%, max_az_ratio 40-50%) | atharvaai/DiversityGauge.jsx |
| Global Intelligence Panel | Panel | Region-wide spot intelligence summary | Real API | `GET /api/v1/atharvaai/global-intelligence/{region}` | GlobalPoolCacheService (65-min TTL, top 50 pools) | atharvaai/GlobalIntelligencePanel.jsx |
| Workload Classification Panel | Panel | Stateless/Stateful node classification | Real API | `GET /api/v1/atharvaai/workload-classification/{cluster_id}` | WorkloadInspector (5 categories: SYSTEM_PROTECTED/STATEFUL/DRAIN_UNSAFE/STATELESS_ELIGIBLE) | atharvaai/WorkloadClassificationPanel.jsx |

### 2.3 Pool Rankings Sub-Tab (`/atharva-ai?tab=rankings`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Pool Rankings | Dashboard | ML pool rankings table | Real API | `POST /api/v1/atharvaai/pools/rankings` | PoolRankingService (9-step 2-tier pipeline: Tier1 global cache → Tier2 client filter → DryRun) | atharvaai/PoolRankings.jsx |
| Pool Rankings CSS | Styles | Table styles | N/A | — | — | atharvaai/PoolRankings.css |

### 2.4 Interruption Heatmap Sub-Tab (`/atharva-ai?tab=heatmap`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Interruption Heatmap | Calendar | 30-day interruption frequency (159 lines) | Real API | `GET /api/v1/atharvaai/heatmap/{cluster_id}` | atharvaai_routes.get_interruption_heatmap (aggregates TerminationEvent data by day×hour) | atharvaai/InterruptionHeatmap.jsx |
| Volatility Monitor | Card | Regional volatility signal display (52 lines) | Real API | `GET /api/v1/atharvaai/volatility/{id}` | EventMonitor | atharvaai/VolatilityMonitor.jsx |

### 2.5 Rebalancing Sub-Tab (`/atharva-ai?tab=rebalancing`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Rebalancing Timeline | Timeline | Sub-hour precision chart (125 lines) | Real API | `GET /api/v1/atharvaai/rebalancing/timeline` | auto_rebalancer.py (cordon→drain→Karpenter reschedule) | atharvaai/RebalancingTimeline.jsx |

### 2.6 Shared / Config

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| AtharvaAI Index | Export | Central barrel export | N/A | — | — | atharvaai/index.js |

---

## 3. Right-Sizing (1 file, 817 lines — RightSizingDashboard.jsx)

> **Sidebar:** COST INTELLIGENCE › Right-Sizing › Karpenter | Configuration | Optimization History | Savings Tracker
>
> **Backend pipeline**: `RightSizingService.generate_recommendations()` → `_analyze_controller()` → phase-aware buffer → P99 floor → confidence gate → cost estimation → `OptimizerCoordinator` proposal creation

### 3.1 Manual Mode — Savings Section

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
| EV Delta & Risk Columns | Table Cols | Spot EV score + Disruption Risk % | Computed | — | scoring.compute_expected_value (EV = savings × (1-risk)) | RightSizingDashboard.jsx |
| Fallbacks Visual Tags | Badges | Top 3 safest fallback instances | Computed | — | PoolRankingService (2-tier ML pipeline) | RightSizingDashboard.jsx |

### 3.2 Manual Mode — Bin-Packing

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| BinpackBlock | Visual | Before/after node consolidation | Real API | `GET /api/v1/karpenter/stats` | KarpenterService | RightSizingDashboard.jsx |

### 3.3 Karpenter Sub-Tab (`/right-sizing?tab=karpenter`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| KarpenterSection container | Section | Real API recommendations | Real API | `GET /api/v1/karpenter/recommendations` | KarpenterService | RightSizingDashboard.jsx |
| Karpenter Recommendations Table | Table | Instance right-sizing recs | Real API | `GET /api/v1/karpenter/recommendations` | KarpenterService | RightSizingDashboard.jsx |
| Apply Recommendation Modal | Modal | Apply single rec | Real API | `POST /api/v1/karpenter/apply-recommendation/{id}` | KarpenterService | RightSizingDashboard.jsx |
| Batch Apply | Button | Apply multiple recs | Real API | `POST /api/v1/karpenter/apply-recommendations/batch` | KarpenterService | RightSizingDashboard.jsx |
| Activity Feed | List | Recent Karpenter events | Real API | `GET /api/v1/karpenter/activity` | KarpenterService | RightSizingDashboard.jsx |
| Karpenter Status | Card | NodePool live status | Real API | `GET /api/v1/karpenter/status` | KarpenterService | RightSizingDashboard.jsx |
| Mode Toggle per cluster | Toggle | Manual/Auto per cluster | Real API | `PATCH /api/v1/karpenter/mode/{cluster_id}` | KarpenterService (switch_to_spot/switch_to_ondemand with 12h fallback TTL) | RightSizingDashboard.jsx |

### 3.4 Configuration Sub-Tab (`/right-sizing?tab=config`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Settings Panel (5 tabs) | Slide-over | General/NodePool/Consolidation/Drift/Advanced | Real API | `GET/PUT /api/v1/karpenter/config` | KarpenterService | RightSizingDashboard.jsx |
| General Config | Form | TTL, batch size, cooldown settings | Real API | `PUT /api/v1/karpenter/config` | KarpenterService | RightSizingDashboard.jsx |
| NodePool Config | Form | NodePool-level overrides | Real API | `PUT /api/v1/karpenter/config` | KarpenterService | RightSizingDashboard.jsx |
| Consolidation Config | Form | Consolidation policy toggles | Real API | `PUT /api/v1/karpenter/config` | KarpenterService | RightSizingDashboard.jsx |
| Drift Detection | Form | Drift policy settings | Real API | `PUT /api/v1/karpenter/config` | KarpenterService | RightSizingDashboard.jsx |
| Advanced Config | Form | ML model, risk, and debug flags | Real API | `PUT /api/v1/karpenter/config` | KarpenterService | RightSizingDashboard.jsx |

### 3.5 Optimization History Sub-Tab (`/right-sizing?tab=history`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| History Chart | Chart | 7-day optimization event timeline | Real API | `GET /api/v1/karpenter/stats?period=week` | KarpenterService | RightSizingDashboard.jsx |
| History Table | Table | Past optimization actions with status | Real API | `GET /api/v1/karpenter/activity` | KarpenterService | RightSizingDashboard.jsx |

### 3.6 Savings Tracker Sub-Tab (`/right-sizing?tab=savings`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Cumulative Savings KPI | Card | Total savings generated | Real API | `GET /api/v1/karpenter/stats` | KarpenterService | RightSizingDashboard.jsx |
| Savings Trend Chart | Chart | Weekly savings progression | Real API | `GET /api/v1/karpenter/stats?period=week` | KarpenterService | RightSizingDashboard.jsx |
| Per-Cluster Savings | Table | Savings breakdown per cluster | Real API | `GET /api/v1/clusters` | ClusterService | RightSizingDashboard.jsx |

---

## 4. Resource Hygiene (10 files)

### 4.1 Main Dashboard (CleanupDashboard.jsx, 1,074 lines)

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

### 4.2 Wizards

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Bulk Tag Wizard | Modal wizard | 3-step tag workflow (592 lines) | Real API | `POST /api/v1/hygiene/action` | HygieneService | cleanup/BulkTagWizard.jsx |
| RI Wizard | Modal wizard | RI waste remediation (150 lines) | Real API | `GET /api/v1/ri/overview` | RIAnalysisService | cleanup/wizards/RIWizard.jsx |
| S3 Wizard | Modal wizard | S3 tiering wizard (188 lines) | Real API | `GET /api/v1/s3/overview` | S3TieringService | cleanup/wizards/S3Wizard.jsx |
| RDS Wizard | Modal wizard | RDS Multi-AZ wizard (157 lines) | Real API | `GET /api/v1/rds/overview` | RDSAnalysisService | cleanup/wizards/RDSWizard.jsx |

---

## 5. Hibernation (28 files)

> **Sidebar:** COST INTELLIGENCE › Hibernation › Schedules | Strategies | Execution History

### 5.1 Schedules Sub-Tab (`/hibernation?tab=schedules`) — HibernationDashboardNew.jsx, 1,310 lines

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Tab Navigation | Tabs | Schedules/Savings/Emergency/Strategies/Audit | Computed | — | — | HibernationDashboardNew.jsx L968 |
| Schedule List | List | All created schedules | Real API | `GET /api/v1/hibernation/schedules` | HibernationService | HibernationDashboardNew.jsx |
| Schedule Item | Card | Individual schedule (strategy, status, clusters) | Props | — | — | HibernationDashboardNew.jsx L618–717 |
| Schedule Form | Modal form | Create/Edit schedule (name, strategy, clusters, schedule matrix, timezone) | Real API | `POST/PUT /api/v1/hibernation/schedules` | HibernationService | HibernationDashboardNew.jsx L433–616 |
| Schedule Matrix (168-cell grid) | Grid | 7-day × 24-hour drag-to-paint sleep grid | Props | — | — | hibernation/ScheduleMatrix.jsx (204 lines) |
| Matrix Quick Presets | Buttons | Business Hours / Weekends / Nights presets | Computed | — | — | ScheduleMatrix.jsx L55–94 |
| Matrix Stats | KPIs | Sleep Hours / Est. Savings / Awake Hours | Computed | — | — | ScheduleMatrix.jsx L99–101 |
| Toggle Schedule | Switch | Enable/disable schedule | Real API | `PATCH /api/v1/hibernation/schedules/{id}` | HibernationService | HibernationDashboardNew.jsx L925 |
| Delete Schedule | Button | Delete with confirmation | Real API | `DELETE /api/v1/hibernation/schedules/{id}` | HibernationService | HibernationDashboardNew.jsx L937 |
| Live Progress Banner | Banner | Polls active execution status every 2s | Real API | `GET /api/v1/hibernation/status/active` | HibernationService.get_active_hibernation_status (node progress tracking) | HibernationDashboardNew.jsx L86–156 |

### 5.2 Strategies Sub-Tab (`/hibernation?tab=strategies`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Strategy Selector | Card grid | 3 strategy cards (Namespace Sleep, Node Drain, Full Cluster) | Hardcoded `STRATEGIES[]` L13–58 | — | HibernationService (3 strategies: NAMESPACE_SLEEP 80% / NUCLEAR 70% / SNAPSHOT_RESTORE 95%) | HibernationDashboardNew.jsx L393–431 |
| Strategy Reference | Table | Comparison table (wake time, savings, risk) | Hardcoded `STRATEGIES[]` | — | HibernationService.calculate_weekly_savings | HibernationDashboardNew.jsx L828–864 |

### 5.3 Execution History Sub-Tab (`/hibernation?tab=history`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Audit History widget | Card | Last 5 executions + auto-refresh 30s | Real API | `GET /api/v1/audit/logs?resource_type=HIBERNATION&limit=5` | AuditService | hibernation/AuditHistory.jsx (153 lines) |
| Savings Report | Dashboard | Monthly/weekly savings with charts | Real API | `GET /api/v1/hibernation/savings/history` | HibernationService.get_savings_history (aggregates AuditLog by month, fills gaps) | HibernationDashboardNew.jsx L158–382 |
| Emergency Controls | Panel | Wake-all / Sleep-now per cluster | Real API | `POST /api/v1/hibernation/emergency/*` | HibernationService + hibernation_worker.py (distributed lock per cluster, 180s TTL) | HibernationDashboardNew.jsx L719–826 |

### 5.4 Other Hibernation Files

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Schedule Calendar | Calendar | Visual calendar view (302 lines) | Props | — | — | hibernation/ScheduleCalendar.jsx |
| Unified Schedule Grid | Grid | Alternate 168-hour grid (346 lines) | Props | — | — | hibernation/UnifiedScheduleGrid.jsx |
| Schedule Builder | Builder | Schedule creation UI | Props | — | — | hibernation/ScheduleBuilder.jsx |
| Schedule Modal | Modal | Create schedule dialog | Real API | `POST /api/v1/hibernation/schedules` | HibernationService.create_schedule (matrix validation + conflict detection) | hibernation/ScheduleModal.jsx |
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

## 6. Clusters (12 files, ClusterList.jsx = 1,588 lines)

> **Sidebar:** INFRASTRUCTURE › Clusters

### 6.1 Master-Detail View

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

### 6.2 Sub-Components

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Delete Modal | Modal | Delete with pre-checks | Real API | `DELETE /api/v1/clusters/{id}` | ClusterService | clusters/ClusterDeleteModal.jsx |
| Disconnect Modal | Modal | Disconnect confirm | Real API | `POST /api/v1/clusters/{id}/disconnect` | ClusterService | clusters/ClusterDisconnectModal.jsx |
| Cluster Details (standalone) | Modal | Detail modal (alt) | Real API | `GET /api/v1/clusters/{id}` | ClusterService | clusters/ClusterDetails.jsx |
| • Optimization Mode Selector | Dropdown | Cost / Balanced / Zero Downtime | Real API | `PATCH /api/v1/clusters/{id}` | ClusterService | clusters/ClusterDetails.jsx |
| • Stateless Workload Classification | Badge | ML-driven workload risk tag | Real API | `GET /api/v1/clusters/{id}/classification` | WorkloadInspector (SYSTEM_PROTECTED/STATEFUL_PROTECTED/DRAIN_UNSAFE/STATELESS_ELIGIBLE) | clusters/ClusterDetails.jsx |
| • Substitute Engine Status | Card | Prewarming state tracking | Real API | `GET /api/v1/substitute/status/{cluster_id}` | SubstituteManager (5-state: IDLE→PREWARMING→READY→ACTIVE→RELEASING) | clusters/ClusterDetails.jsx |
| • Cooldown Status Widget | Widget | Active cooldown timeline | Real API | `GET /api/v1/cooldown/{cluster_id}` | CooldownController (5 cooldown types: cluster 60m / pool 120m / resize 6h / switch 30m / substitute 2h) | clusters/ClusterDetails.jsx |
| • Circuit Breaker Panel | Panel | Active interruption blocks | Real API | `GET /api/v1/execution/status/{cluster_id}` | KarpenterService circuit breaker (>10 failures/10min = block) | clusters/ClusterDetails.jsx |
| Health Timeline | Timeline | Health history | Props | — | — | clusters/ClusterHealthTimeline.jsx |
| Utilization Sparkline | Chart | Inline sparkline | Props | — | — | clusters/ClusterUtilizationSparkline.jsx |
| Node List | Table | Node management | Real API | `GET /api/v1/clusters/{id}/nodes` | ClusterService | clusters/NodeList.jsx |
| Node Group Breakdown | View | Node group view | Props | — | — | clusters/NodeGroupBreakdown.jsx |
| Policy Gap Alert | Alert | Policy violation alerts | Props | — | — | clusters/PolicyGapAlert.jsx |
| Spot Ratio Gauge | Gauge | Spot vs OD gauge | Props | — | — | clusters/SpotRatioGauge.jsx |
| Node Template Tab | Tab | View/assign global templates to cluster | Real API | `GET /api/v1/templates`, `POST /api/v1/templates/assign` | NodeTemplateService | clusters/NodeTemplateTab.jsx |

---

## 7. Node Templates (4 files)

> **Sidebar:** COST INTELLIGENCE › Node Templates

### 7.1 Enterprise Template Registry (pages/NodeTemplates.jsx, 930 lines)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Node Templates Page | Page | Enterprise control plane for global templates | Real API | `GET /api/v1/templates` | NodeTemplateService | pages/NodeTemplates.jsx |
| Template Grid | Grid | Template cards with version badges | Real API | `GET /api/v1/templates` | NodeTemplateService | NodeTemplates.jsx |
| Create Template | Modal | New template with constraint editor | Real API | `POST /api/v1/templates` | NodeTemplateService | NodeTemplates.jsx L41 |
| Template Detail Modal | Modal | Version history + constraint view + candidate preview | Real API | `GET /api/v1/templates/{id}/versions` | NodeTemplateService | NodeTemplates.jsx L79 |
| Constraint Editor | Form | vCPU/memory bounds, family allow/exclude, AZ selection | Props | — | — | NodeTemplates.jsx |
| Candidate Pool Simulator | Table | Preview instances matching constraints | Real API | `POST /api/v1/templates/validate` | NodeTemplateService | NodeTemplates.jsx L97 |
| Promote Version | Button | Promote new version of constraints | Real API | `POST /api/v1/templates/{id}/versions` | NodeTemplateService | NodeTemplates.jsx L115 |

### 7.2 Legacy Template Files

> **⚠️ NOTE**: The following files (`templates/TemplateBuilder.jsx`, `templates/TemplateList.jsx`) were previously documented but do **NOT exist** in the codebase. They have been removed from this inventory. The Node Templates functionality lives entirely in `pages/NodeTemplates.jsx` and `clusters/NodeTemplateTab.jsx`.

---

## 8. Approvals (pages/Approvals.jsx, 505 lines + 3 components)

> **Sidebar:** GOVERNANCE › Approvals

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
| Ticket Request Modal | Modal | Full ticket creation form (672 lines) | Real API | `POST /api/v1/approvals/jit-request` | ApprovalService | approvals/TicketRequestModal.jsx |
| Access Request Modal | Modal | Quick JIT access request | Real API | `POST /api/v1/approvals/jit-request` | ApprovalService | approvals/AccessRequestModal.jsx |
| JIT Request Modal | Modal | JIT elevation form | Real API | `POST /api/v1/approvals/jit-request` | ApprovalService | governance/JITRequestModal.jsx |
| Risk Badge | Badge | Risk level indicator | Props | — | — | shared/RiskBadge.jsx |

---

## 9. Tag Governance (TagGovernancePage.jsx, 1,560 lines + 2 wrappers)

> **Sidebar:** GOVERNANCE › Tag Governance › Governance Policies | Tag Templates | Scoring Engine | Automation Rules | Compliance Monitor

### 9.1 Governance Policies Tab (`/tagging-policies?tab=policies`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Policies list | Table | All defined tag policies | Real API | `GET /api/v1/governance/policies` | GovernanceService | TagGovernancePage.jsx |
| Policy Row | Row | Policy with toggle/edit/delete | Props | — | — | TagGovernancePage.jsx L358–408 |
| Policy Create/Edit Modal | Modal | Full policy editor (conditions, actions, scope) | Real API | `POST/PUT /api/v1/governance/policies` | GovernanceService | TagGovernancePage.jsx L410–488 |

### 9.2 Tag Templates Tab (`/tagging-policies?tab=templates`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Tag Templates grid | Grid | Tag template cards | Real API | `GET /api/v1/governance/tag-templates` | TagManagementService | TagGovernancePage.jsx |
| Template Card | Card | Template with tags + scope badge | Props | — | — | TagGovernancePage.jsx L594–673 |
| Template Builder wizard | Full page | 3-step builder for tag templates | Real API | `POST /api/v1/governance/tag-templates` | TagManagementService | TagGovernancePage.jsx L675–948 |

### 9.3 Scoring Engine Tab (`/tagging-policies?tab=scoring`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Score Donut chart | Donut | Org-wide compliance score (0-100) | Real API | `GET /api/v1/governance/scoring` | TagScoringService | TagGovernancePage.jsx L158–177 |
| Compliance Bar | Bar | Per-resource compliance % | Computed | — | — | TagGovernancePage.jsx L179–190 |
| Tag Heatmap | Grid | Tag coverage by resource type | Computed | — | — | TagGovernancePage.jsx L192–202 |

### 9.4 Automation Rules Tab (`/tagging-policies?tab=automation`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Automation rules list | Table | Auto-tagging rules | Real API | `GET /api/v1/governance/automation` | TagAutomationService | TagGovernancePage.jsx |
| New Automation Rule modal | Modal | Create rule with triggers + tag actions | Real API | `POST /api/v1/governance/automation` | TagAutomationService | TagGovernancePage.jsx L1201–1313 |
| Run Autopilot button | Button | One-click tag automation | Real API | `POST /api/v1/governance/run-autopilot` | TagAutomationService | TagGovernancePage.jsx |

### 9.5 Compliance Monitor Tab (`/tagging-policies?tab=monitor`)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Drift Monitor | Dashboard | Real-time compliance drift | Real API | `GET /api/v1/governance/drift` | TagComplianceService | TagGovernancePage.jsx |
| Compliance Timeline | Timeline | Historical compliance changes | Real API | `GET /api/v1/governance/timeline` | TagComplianceService | TagGovernancePage.jsx |

### 9.6 Wrappers

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| TagPoliciesManager | Wrapper | Thin redirect to TagGovernancePage (16 lines) | N/A | — | — | settings/TagPoliciesManager.jsx |
| ~~TagTemplateManager~~ | ~~Manager~~ | ~~Standalone template CRUD~~ | ~~Real API~~ | — | — | ⚠️ **GHOST** — `settings/TagTemplateManager.jsx` does NOT exist. Template CRUD handled inline by TagGovernancePage.jsx §9.2 |
| GovernanceSettings | Manager | Automation toggles (253 lines) | Real API | `GET /api/v1/governance/policies` | GovernanceService | settings/GovernanceSettings.jsx |
| Tag Policies List | Table | Tag policy listing | Real API | `GET /api/v1/policies` | PolicyService | settings/TagPoliciesList.jsx |

---

## 10. Automation (`/automation-settings`)

> **Sidebar:** GOVERNANCE › Automation

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Governance Settings | Page | Autopilot rules & governance automation toggles | Real API | `GET /api/v1/governance/policies` | GovernanceService | settings/GovernanceSettings.jsx |

---

## 11. Teams & Members (3 tab components + 2 page files)

> **Sidebar:** ORGANIZATION › Teams & Members

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

## 12. Audit Logs (AuditLog.jsx, 453 lines)

> **Sidebar:** SYSTEM › Audit Logs

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Audit Log Page | Page | Filterable audit trail | Real API | `GET /api/v1/audit/logs` | AuditService | audit/AuditLog.jsx |
| Event Type Filter | Dropdown | 16 event types (login, cluster.created, schedule.toggled, etc.) | Hardcoded event list L11–33 | — | — | AuditLog.jsx |
| Diff Viewer Modal | Modal | Before/after JSON diff | Computed (calculates diff) | — | — | AuditLog.jsx L83–98 |
| Export CSV | Button | Download filtered logs as CSV | Real API | `GET /api/v1/audit/export` | AuditService | AuditLog.jsx L121 |
| Clear Filters | Button | Reset all filters | Computed | — | — | AuditLog.jsx L146 |
| Event Badge | Badge | Color-coded event type badge | Computed | — | — | AuditLog.jsx L158 |

---

## 13. Settings (Settings.jsx, 219 lines + 3 tab components)

> **Sidebar:** SYSTEM › Settings

### 13.1 Account Settings Tab (AccountSettings.jsx, 378 lines)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Profile Section | Form | Name + email update | Real API | `PUT /api/v1/auth/profile` | AuthService | settings/AccountSettings.jsx |
| Password Change | Form | Current + new + confirm password | Real API | `POST /api/v1/auth/change-password` | AuthService | AccountSettings.jsx L63 |
| Preferences | Form | Timezone, theme, notifications | Real API | `PUT /api/v1/users/me/preferences` | UserService | AccountSettings.jsx L97 |

### 13.2 Cloud Integrations Tab (CloudIntegrations.jsx, 500 lines)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Connection Info | Card | External ID + Account ID for AWS | Real API | `GET /api/v1/organization/connection-info` | AuthService | settings/CloudIntegrations.jsx |
| Regenerate External ID | Button | Generate new external ID | Real API | `POST /api/v1/organization/connection-info/regenerate` | AuthService | CloudIntegrations.jsx L60 |
| Connected Accounts list | List | AWS accounts with status | Real API | `GET /api/v1/accounts` | AccountService | CloudIntegrations.jsx L76 |
| Add Account form | Form | Role ARN input | Real API | `POST /api/v1/accounts` | AccountService | CloudIntegrations.jsx L88 |
| Validate Account | Button | Test AWS connection | Real API | `POST /api/v1/accounts/{id}/validate` | AccountService | CloudIntegrations.jsx L117 |
| Delete Account | Button | Remove AWS account | Real API | `DELETE /api/v1/accounts/{id}` | AccountService | CloudIntegrations.jsx L164 |

### 13.3 Billing Tab (inline BillingTab, 147 lines)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Billing Status | Card | Plan, status, period | Real API | `GET /api/v1/billing/status` | BillingService | Settings.jsx L76 |
| Usage Summary | Card | Clusters, members, scans | Real API | `GET /api/v1/billing/costs/summary` | BillingService | Settings.jsx |
| Manage Billing | Button | Opens Stripe portal | Real API | `POST /api/v1/billing/create-portal-session` | BillingService | Settings.jsx L116 |

---

## 14. Admin Panel (9 files, SUPER_ADMIN only)

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

## 16. Optimizer Coordinator Dashboard (1 file, 694 lines)

> **Sidebar:** COST INTELLIGENCE › Optimizer Coordinator
>
> **Backend pipeline**: `OptimizerCoordinator` phase state machine (INITIAL_POOL → STABILIZATION → RIGHTSIZING → COMBINED → EXECUTION → COOLDOWN) + trust phases (Phase 0/1/2)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Optimizer Coordinator Dashboard | Dashboard | Unified optimizer status + proposals viewer | Real API | `GET /api/v1/optimizer/status/{cluster_id}` | OptimizerCoordinator (phase state machine, combined EV) | optimizer/OptimizerCoordinatorDashboard.jsx |
| Trust Phase Panel | Panel | Phase 0/1/2 progression display | Real API | `GET /api/v1/optimizer/trust-phase/{cluster_id}` | OptimizerCoordinator.get_cluster_trust_phase (0-30min/30min-2h/>2h) | OptimizerCoordinatorDashboard.jsx |
| Rightsizing Proposals Table | Table | Proposals with approve/reject actions | Real API | `GET /api/v1/optimizer/proposals/{cluster_id}` | RightSizingService + OptimizerCoordinator | OptimizerCoordinatorDashboard.jsx |
| EV Comparison Panel | Panel | 3-option EV comparison (current/new/do nothing) | Real API | `GET /api/v1/optimizer/ev-comparison/{proposal_id}` | scoring.compute_combined_expected_value (3-option model) | OptimizerCoordinatorDashboard.jsx |
| Resize Guard Status | Card | Resize circuit breaker state | Real API | `GET /api/v1/optimizer/resize-guard/{cluster_id}` | resize_guard_worker.py (failure_count_24h tracking) | OptimizerCoordinatorDashboard.jsx |
| Circuit Breaker Status | Card | Execution failure tracking | Real API | `GET /api/v1/optimizer/circuit-breaker/{cluster_id}` | KarpenterService circuit breaker (>10 failures/10min) | OptimizerCoordinatorDashboard.jsx |
| Approve Proposal | Button | Approve rightsizing proposal | Real API | `POST /api/v1/optimizer/proposals/{id}/approve` | OptimizerCoordinator → ActionExecutor | OptimizerCoordinatorDashboard.jsx |
| Reject Proposal | Button | Reject with reason | Real API | `POST /api/v1/optimizer/proposals/{id}/reject` | OptimizerCoordinator | OptimizerCoordinatorDashboard.jsx |

---

---

## 17. Other Components

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

### Pages (8 files — 4 already documented inline above, 4 listed here)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | File Name |
|---|---|---|---|---|---|---|
| Account Analytics | Page | AWS account cost analytics (145 lines) | Real API | `GET /api/v1/metrics/accounts/{id}` | MetricsService | pages/AccountAnalytics.jsx |
| Node Templates | Page | Enterprise template control plane (930 lines) | Real API | `GET /api/v1/templates`, `POST /api/v1/templates/validate` | NodeTemplateService | pages/NodeTemplates.jsx |
| Onboarding | Page | 4-step new user wizard (109 lines) | Real API | `GET /api/v1/onboarding/state` | OnboardingService | pages/Onboarding.jsx |
| Roles | Page | Role management + permission matrix (122 lines) | Real API | `GET /api/v1/roles` | RoleService | pages/Roles.jsx |

> **Also documented inline:** `pages/Approvals.jsx` (§8), `pages/Teams.jsx` + `pages/TeamDetails.jsx` (§11), `pages/AtharvaAiPage.jsx` (§2)

### Infrastructure & Utilities (11 files)

| File | Type | What It Does | Dependencies |
|---|---|---|---|
| `App.js` | Router | Root component — route definitions, auth guard, lazy loading | React Router, MainLayout, all pages |
| `index.js` | Entry | ReactDOM.render entry point | App.js |
| `index.css` | Styles | Global CSS — design tokens, reset, dark mode variables | — |
| `services/api.js` | Service | Axios instance + all API endpoint functions (cluster, karpenter, hygiene, atharvaai, governance, billing, admin) | Axios |
| `services/hibernationApi.js` | Service | Hibernation-specific API functions (schedules CRUD, savings, emergency) | Axios |
| `hooks/useAuth.js` | Hook | Auth context — login/logout state, token management, role check | api.js |
| `hooks/useDashboard.js` | Hook | Dashboard data fetching + widget state management | api.js |
| `hooks/usePermission.js` | Hook | RBAC permission check — `hasPermission(action, resource)` | useAuth |
| `store/useStore.js` | Store | Global Zustand store — clusters, selectedCluster, notifications | Zustand |
| `store/useAtharvaStore.js` | Store | AtharvaAI-specific state — rankings, mode, volatility | Zustand |
| `store/useHibernationStore.js` | Store | Hibernation state — schedules, active status, savings | Zustand |
| `utils/formatters.js` | Utility | Number/date/currency formatting helpers | — |

---

## 18. UNUSED / DUPLICATE / UNWIRED — Cleanup Audit

### 18.1 🔴 ORPHAN Components (No Import Found)

| Component | Lines | Category | Recommendation | Reason |
|-----------|-------|----------|----------------|--------|
| **settings/TeamManagement.jsx** | 795 | LEGACY | 🗑️ DELETE | Superseded by `teams/MembersTab.jsx` + `TeamsTab.jsx` |
| **settings/GovernanceManager.jsx** | 62 | DUPLICATE | 🗑️ DELETE | Overlaps with GovernanceSettings.jsx |
| **approvals/ActiveWindowBanner.jsx** | — | DUPLICATE | 🗑️ DELETE | Duplicate of governance/ActiveJITBanner.jsx |
| **hibernation/HibernationScheduler.jsx** | 622 | ORPHAN | 🔌 WIRE UP | May be intended for schedule tab |
| **hibernation/HibernationWizard.jsx** | 411 | ORPHAN | 🔌 WIRE UP | Setup wizard not routed |
| **hibernation/UnifiedScheduleGrid.jsx** | 346 | ORPHAN | 🔌 WIRE UP | Alternate schedule grid |
| **hibernation/DashboardTab.jsx** | 162 | ORPHAN | 🔌 WIRE UP | Dashboard sub-tab |
| **hibernation/ClusterOverview.jsx** | 135 | ORPHAN | 🔌 WIRE UP | Cluster summary |
| **hibernation/HibernationHeader.jsx** | 120 | ORPHAN | 🔌 WIRE UP | Header |
| **hibernation/HistoryLog.jsx** | 103 | ORPHAN | 🔌 WIRE UP | History log |
| **hibernation/MultiTimezone.jsx** | 97 | ORPHAN | 🔌 WIRE UP | Timezone support |
| **hibernation/AdvancedConfiguration.jsx** | 84 | ORPHAN | 🔌 WIRE UP | Advanced settings |
| **hibernation/TimeBasedRules.jsx** | 135 | ORPHAN | 🔌 WIRE UP | Time rules |
| **clusters/ClusterDetails.jsx** | 1,161 | ORPHAN | 🔌 WIRE UP | Detail modal (inline version exists in ClusterList) |
| **clusters/ClusterDeleteModal.jsx** | 126 | ORPHAN | 🔌 WIRE UP | Delete modal |
| **clusters/ClusterDisconnectModal.jsx** | 128 | ORPHAN | 🔌 WIRE UP | Disconnect modal |
| **clusters/ClusterUtilizationSparkline.jsx** | 50 | ORPHAN | 🔌 WIRE UP | Sparkline |
| **clusters/PolicyGapAlert.jsx** | 28 | ORPHAN | 🔌 WIRE UP | Policy alerts |
| **clusters/SpotRatioGauge.jsx** | 54 | ORPHAN | 🔌 WIRE UP | Gauge (inline version in ClusterList) |
| **cleanup/layout/CleanupSidebar.jsx** | 289 | ORPHAN | 🔌 WIRE UP | Sidebar (inline version in CleanupDashboard) |
| **cleanup/summary/HeroMetricsPanel.jsx** | 139 | ORPHAN | 🔌 WIRE UP | KPI panel (inline version in CleanupDashboard) |

**Summary: 21 orphans. 3 DELETE (duplicates). 18 WIRE UP.**

### 18.2 ⚠️ FAKE Data in Production Code

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

### 18.3 🔴 Backend Endpoints NOT Called from Frontend

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
| `GET /api/v1/optimizer/status/{cluster_id}` | optimizer_coordinator_routes.py | 🔌 WIRE UP |
| `GET /api/v1/pool-rotation/status/{cluster_id}` | pool_rotation_routes.py | 🔌 WIRE UP |
| `POST /api/v1/pool-rotation/force/{cluster_id}` | pool_rotation_routes.py | 🔌 WIRE UP |

### 18.4 Frontend API Calls with No Backend Route

| Frontend Call | Status |
|---------------|--------|
| `GET /api/v1/admin/agent-fleet` | ❌ Missing |
| `GET /api/v1/admin/dashboard` | ❌ Missing |
| `GET /api/v1/admin/stats` | ❌ Missing |
| `GET /api/v1/billing/create-portal-session` | ❌ Missing |
| `GET /api/v1/billing/costs/summary` | ❌ Missing |
| `GET /api/v1/billing/status` | ❌ Missing |

---

**Total: 136 components + 8 pages + 11 infra = 155 files · Orphans: 18 (3 DELETE, 15 WIRE UP) · Ghost Files Removed: 5 · Fake Data: 0 (7 resolved, 1 kept) · Unused Backend: 14 · Missing Backend: 6**

---

## 19. Backend Remediation Patches (2026-02-26)

The following backend integration fixes and metric-lag enhancements were applied. These affect the backend logic referenced in the tables above:

| Fix | File Modified | Backend Logic Affected | Impact |
|-----|--------------|----------------------|--------|
| FIX 1: Template Enforcement | `rightsizing_service.py` | `RightSizingService.create_rightsizing_proposals` | Proposals now filtered against cluster's active Node Template constraints (vCPU/memory bounds, family allow/exclude) |
| FIX 3: Proposal Freeze | `optimizer_coordinator.py` | `OptimizerCoordinator.can_run_pool_optimization` | Pool optimization blocked while rightsizing proposal is pending evaluation |
| FIX 4: Substitute Cooldown | `substitute_manager.py` | `SubstituteManager.promote_substitute` | 2-hour cooldown recorded after substitute promotion to prevent churn |
| FIX 5: Pricing Freshness | `decision_engine.py` | `DecisionEngine.evaluate_action_plan` | Pricing data staleness check (>15 min) blocks pool evaluations unless emergency |
| ENH 2: Confidence Gate | `rightsizing_service.py` | `RightSizingService._analyze_controller` | LOW confidence recommendations blocked; high CPU volatility skipped |
| ENH 3: P99 Fallback Floor | `rightsizing_service.py` | `RightSizingService._analyze_controller` | Proposed size must exceed P99 × 1.3 to handle burst workloads |
| ENH 6: Metric Freshness | `rightsizing_service.py` | `RightSizingService.generate_recommendations` | Rightsizing skipped if latest metric timestamp > 5 min stale |
| ENH 8: Volatility Buffer | `rightsizing_service.py` | `RightSizingService._analyze_controller` | Safety buffer dynamically increased to 35% during volatile spot markets |

---

## 20. Sub-Element Appendix — Buttons, Dropdowns, Toggles, Table Columns, Badges

> Every interactive micro-element extracted by reading the actual JSX. Organised by parent component.

---

### 20.1 PoolRankings.jsx (716 lines)

**Tabs (3):**
| Tab | State Value | Icon |
|---|---|---|
| Market View | `market` | FiGlobe |
| Node-Specific View | `node` | FiServer |
| Cluster Impact View | `cluster` | FiPieChart |

**Buttons & Controls:**
| Element | Type | Line | Action |
|---|---|---|---|
| Refresh | Button | L322 | `loadData() + fetchBlacklist()` |
| Auto-refresh (30s) | Checkbox | L330 | Sets 30s interval polling |

**Market View Table Columns (9):**
`Rank` · `Instance Type` · `AZ` · `vCPU / Mem` · `Spot Price` · `Interruption` · `ML Score` · `Health` · `Used By Cluster`

**Node-Specific View — Summary Cards (5):**
`Total Nodes` · `Stateless` · `Eligible` · `In Cooldown` · `Proj. Savings`

**Node-Specific View Table Columns (9):**
`Node Name` · `Current Type` · `Current Cost` · `Target Pool` · `Proj. Savings` · `Risk Score` · `Confidence` · `Status` · `Action (Schedule button)`

**Cluster Impact View — Summary Cards (4):**
`Current Cost` · `Projected Cost` · `Estimated Savings` · `Spot Exposure`

**Cluster Impact View — Chart Placeholders (3):**
`AZ Distribution (Pie)` · `Instance Family Distribution (Bar)` · `Spot vs On-Demand Ratio (Gauge)`

**Cluster Impact View Table Columns (7):**
`Target Pool` · `Eligible Nodes` · `Avg Savings` · `Total Savings` · `Avg Risk` · `Health` · `Cluster Usage`

**Badges & Indicators:**
| Badge | Logic | Colors |
|---|---|---|
| Rank Badge | Gold (#1), Green (≤3), Gray (>3) | bg-yellow-100, bg-green-100, bg-gray-100 |
| Interruption Badge | 5-tier: <5%, 5-10%, 10-15%, 15-20%, >20% | green/blue/yellow/orange/red |
| Health Badge | `getHealthBadge(is_flagged)` | green=Healthy, red=Unstable |
| Region Badge | Inline blue pill | bg-blue-100 |
| Template Badge | Green with lock icon (FiLock) | text-green-700 |
| Strategy Badge | Active Strategy + Risk Ceiling + Min Savings | bg-indigo-50 |
| Capacity Validated | FiCheckCircle per row | text-blue-500 |
| Flagged Warning | FiAlertTriangle per row if `is_flagged` | text-red-600 |

**Alerts:**
| Alert | Condition | Style |
|---|---|---|
| Blacklist Alert | `blacklist.length > 0` | bg-red-50, shows TTL badges per pool |
| Execution Safety Banner | Hidden by default (`hidden` css class) | bg-orange-50 |
| Error Alert | `error !== null` | bg-red-50 |
| No Cluster Selected | `!clusterId` | text-center empty state |
| Empty State (Market) | `pools.length === 0` | text-center empty state |

**Legend Panel** (Market tab only): ML Score, Interruption, Validated descriptions + current cluster info + template info.

---

### 20.2 DecisionEngineV3Dashboard.jsx (449 lines)

**Automation Controls (2 toggles):**
| Toggle | State Key | API Call |
|---|---|---|
| Auto-Rightsizing | `config.rightsizing` | `PATCH /api/v1/clusters/{id}` → `rightsizing_enabled` |
| Auto-Rebalancing (Spot) | `config.autoRebalance` | `PATCH /api/v1/clusters/{id}` → `auto_rebalance_enabled` |

**Optimization Mode Selector** (embedded `<OptimizationModeSelector>` component):
3 modes: `COST_FIRST` · `BALANCED` · `NO_DOWNTIME_FIRST`

**Effective Configuration Panel (6 KPIs):**
`Stateful Spot` · `Active Template` · `Risk Strategy` · `Target Spot Exposure %` · `Substitute Mode` · `Auto-Rebalance Mode (ON/OFF with green pulse)`

**Execution Pipeline Precedence Diagram (3 numbered steps):**
1. Cluster Policy → Global Overrides & Targets
2. Node Template → Hardware & Capacity Constraints
3. Optimization Strategy → Risk vs Cost Math Scoring

**Custom EV Controls (5 inputs — only visible in CUSTOM mode):**
| Input | Type | Config Key |
|---|---|---|
| Risk Ceiling % | Number | `optimization_strategy.risk_ceiling_percent` |
| Minimum Savings % | Number | `optimization_strategy.min_savings_percent` |
| Volatility Tolerance % | Number | `optimization_strategy.volatility_tolerance_percent` |
| Migration Penalty Multiplier | Number (step 0.1) | `optimization_strategy.migration_penalty_multiplier` |
| Diversity Strictness Level | Dropdown (Low/Medium/High) | `optimization_strategy.diversity_strictness_level` |

**Stateless Optimization Rules (6 controls):**
| Control | Type | Config Key |
|---|---|---|
| Instance Diversification | Toggle | `stateless_rules.instance_diversification_enabled` |
| Substitute Strategy | Dropdown (PREWARMED/ON_DEMAND) | `stateless_rules.substitute_strategy` |
| Respect PDBs | Toggle | `stateless_rules.respect_pdb_enabled` |
| Max Rebalances per 24h | Number | `stateless_rules.max_rebalances_per_24h` |
| Resize Headroom Multiplier | Number (step 0.1) | `stateless_rules.resize_headroom_multiplier` |
| Volatility Safety Multiplier | Number (step 0.05) | `stateless_rules.volatility_safety_multiplier` |

**Stateful Optimization Rules (5 controls):**
| Control | Type | Config Key |
|---|---|---|
| Allow Manual Resize | Toggle | `stateful_rules.manual_resize_allowed` |
| Show On-Demand Savings Only | Toggle | `stateful_rules.show_ondemand_only` |
| Block Spot for Stateful | Toggle (disabled, always ON) | `stateful_rules.block_spot_for_stateful` |
| Require Approval Always | Toggle (disabled, always ON) | `stateful_rules.require_approval` |
| Maximum Downscale % | Number | `optimization_strategy.risk_ceiling_percent` |

**Bottom Bar:** Save Optimization Rules button (`saving ? "Saving..." : "Save Optimization Rules"`)

---

### 20.3 ClusterDetails.jsx (1124 lines)

**Tabs (4):** `Overview` · `Optimization Settings` · `Node Template` · `Activity Log`

**Header Buttons:**
| Button | Action | API |
|---|---|---|
| Instant Rebalance | `clusterAPI.optimize(clusterId)` | `POST /api/v1/clusters/{id}/optimize` |
| Refresh | `fetchClusterDetails()` | Parallel fetch 11 endpoints |
| Close (✕) | `onClose()` callback | — |

**Overview Tab — Status Card (4 fields):**
`Status Badge` · `Cluster ID (truncated)` · `Created Date` · `Last Heartbeat`

**Utilization Card (5 KPIs):**
`CPU Utilization %` · `Memory Utilization %` · `Pod Count` · `Node Count` · `Avg CPU/Mem per pod`

**Workload Classification Card:**
`Type Badge (STATELESS/STATEFUL/MIXED)` · `PVC Pods (x/total)` · `StatefulSet Pods (x/total)` · `Analysis text` · `Spot Optimization recommendation badge`

**Node Details — Expandable Table (7 columns per pod):**
`Pod Name (mono)` · `Namespace` · `Controller (Badge)` · `CPU (millicores)` · `Memory (MB)` · `Storage (PVC badge)` · `Type (Stateful/Stateless badge)`

Each node header shows: `Instance Type` · `Lifecycle Badge (spot/on-demand)` · `Classification Badge` · `AZ` · `CPU %` · `Memory %` · `Pod Count` · `Expand Arrow (▶/▼)`

**Cluster Metrics Card (7 KPIs):**
`Total Instances` · `Spot Instances` · `On-Demand` · `Spot Ratio %` · `Monthly Cost` · `Estimated Savings` · `Avg CPU`

**Decision Engine State Panel:**
| Sub-element | Type | States |
|---|---|---|
| Optimization Mode | Dropdown | COST_FIRST / BALANCED / NO_DOWNTIME_FIRST |
| Workload Capability | Badge | STATELESS (green) / STATEFUL (red) / UNKNOWN (gray) |
| Substitute Engine | Badge | IDLE / PREWARMING (yellow + countdown) / ACTIVE (green + pool target) |
| Circuit Breaker | Badge + Button | CLOSED (green) / OPEN (red) + "Resume Ops" button |
| Cooldown Enforcer | Status Card | Duration (min) · Last Switch (time) · Status: LOCKED/READY |

**Optimization Policy Card (6 fields):**
`Spot Target %` · `Node Range (min-max)` · `Target CPU %` · `Target Memory %` · `Fallback (Enabled/Disabled)` · `Diversification (Enabled/Disabled)` · (or) `Configure Policy button`

**Hibernation Schedule Card (6 fields):**
`Strategy` · `Timezone` · `Pre-warm Minutes` · `Active Hours (x/168)` · `Last Action` · `Last Action At` · `Edit Schedule button`

---

### 20.4 ClusterList.jsx (1589 lines) — Inline Micro-Components

**Inline Component Definitions:**
| Component | Lines | Purpose |
|---|---|---|
| ToggleSwitch | L79–98 | Custom toggle (green=on, border=off) |
| OptimizationSettingsTab | L101–242 | 5-toggle settings panel (inline in ClusterList) |
| MiniBar | L244–254 | CPU/Memory utilization progress bar |
| Tag | L257–266 | Tinted badge with neutral text |
| MetricBox | L268–280 | Labeled metric card |
| NodeTreemap | L285–557 | Paginated (20/page) node bubble visualization |
| SpotRing | L561–582 | SVG donut chart for spot ratio |
| ClusterListItem | L584–669 | Cluster card in sidebar list |
| ClusterDetail | L680–end | Detail panel for selected cluster |
| SectionHeader | L671–678 | Styled section label |

**OptimizationSettingsTab — 5 Controls:**
| Control | Type | API Field |
|---|---|---|
| Auto Rebalance (ML Spot Optimization) | ToggleSwitch | `automation_controls.auto_rebalance_enabled` |
| Auto Right-Sizing | ToggleSwitch | `automation_controls.auto_rightsizing_enabled` |
| Cooldown Duration Override | Number input (seconds) | `automation_controls.cooldown_override_minutes` |
| Conservative Mode (Fresh Cluster Protection) | ToggleSwitch | `automation_controls.conservative_mode_enabled` |
| Manual Approval Required (RBAC) | ToggleSwitch | `automation_controls.manual_approval_required` |

**NodeTreemap Features:**
- Utilization Legend: Critical ≥85% (red) · High 65–84% (amber) · Healthy 30–64% (green) · Low <30% (blue)
- Node size: Large (≥64GB), Medium (≥32GB), Small (<32GB)
- Hover tooltip portal: Name · Type · Instance · Workload · CPU · Memory · Pods · Age · Ready
- Pagination: Prev/Next buttons + page number buttons
- Node type breakdown strip: spot · fallback · on-demand counts

**ClusterDetail Header Buttons:**
| Button | Condition | Action |
|---|---|---|
| Install Agent | `agent_installed === 'N'` and status is `no-agent`/`DISCOVERED` | `clusterAPI.autoInstallAgent(id)` |
| Refresh | Always visible | `refresh-clusters` event |
| Disconnect | `agent_installed === 'Y'` | `clusterAPI.disconnectAgent(id)` with confirm |
| Remove | Always visible | `clusterAPI.deleteCluster(id)` with confirm |

---

### 20.5 Dashboard.jsx (657 lines) — Inline Micro-Components

**Inline Component Definitions:**
| Component | Lines | Purpose |
|---|---|---|
| Badge | L46–55 | Pill badge with color |
| Dot | L57–62 | Status dot |
| SectionLabel | L64–70 | Uppercase section title |
| EmptyChip | L72–80 | Empty state inline chip |
| Sparkline | L83–93 | SVG polyline sparkline |
| KpiCard | L96–131 | KPI metric card with trend arrow |
| Card | L134–150 | Section card wrapper |
| HealthMiniCard | L153–174 | Health check card (RI/S3/RDS/Transfer) |
| FeatureRow | L177–200 | Governance feature list item |

**Tabs (4):** `Overview` · `Cost Intelligence` · `Infrastructure` · `Governance`

**Overview Tab Elements:**
- 4 KPI Cards: `Monthly Spend` · `Net Savings` · `Spot Ratio` · `Total Nodes`
- 3 Widgets: `SpendForecastWidget` · `AgentStatusWidget` · `ClusterHealthCard`
- `FleetComposition` + `ActivityFeed` widgets
- `PendingApprovalsCard`
- Onboarding banner + `Connect AWS Account →` button (shown when no accounts + non-super-admin)

**Cost Intelligence Tab Elements:**
- 3 Feature Cards (Right-Sizing / AtharvaAI / Hibernation) — each has 4 KPI stats + navigation button
- Resource Hygiene card: 4 KPIs (`Safe to Delete` · `Orphaned` · `Potential Savings` · `Last Scan`) + `Run Scan →` button
- 4 Health Mini Cards: `RI Health` · `S3 Health` · `RDS Health` · `Data Transfer` — each with `Analyze →` CTA

**Infrastructure Tab Elements:**
- 4 KPI Cards: `Total Cost` · `Total Nodes` · `Total vCPU` · `Total Memory`
- Clusters card with `Discover` + `View all →` buttons
- Node Templates card with `Manage →` + `+ Create Template` buttons

**Governance Tab Elements:**
- 3 KPI Cards: `Pending Requests` · `Active Grants` · `Awaiting Consent`
- Governance Features list: `Tagging Policies` · `Automation Settings` · `Approvals`
- Teams & Members list: `Members` · `Teams` · `Roles & Policies`

---

### 20.6 OptimizerCoordinatorDashboard.jsx (677 lines)

**Cards (6 sections):**

**1. Optimization Status Card (3 KPIs + Timeline):**
| KPI | States |
|---|---|
| Current Phase | Badge: Pool Optimization (blue) / Stabilization (yellow) / Rightsizing Eval (purple) / Combined Execution (indigo) / Cooldown (gray) |
| Pool Optimization | Ready (green) / Blocked (gray) + reason text |
| Rightsizing Evaluation | Ready (green) / Blocked (gray) + reason text |

**Phase Timeline** — 5-step visual: `Pool Optimization → Stabilization → Rightsizing Eval → Combined Execution → Cooldown` (active phase highlighted with blue border)

**2. Cooldown Status Card (3 action types):**
`resize` · `pool_switch` · `substitute` — each shows remaining minutes or "Ready"

**3. Progressive Trust Phase Card (4 KPIs):**
`Current Phase (0/1/2)` · `Cluster Age (hours)` · `Safety Buffer %` · `Min Samples` + status info banner

**4. Post-Resize Guard Card (3 KPIs):**
`Guard Status (Monitoring/Inactive)` · `Recent Executions (last 2h)` · `Active Proposals being monitored` + Health check rules: CPU >85%, Pod restarts 2x baseline, Memory pressure >5 events

**5. Resize Circuit Breaker Card (3 KPIs + Alerts):**
| KPI | States |
|---|---|
| Status | OPEN (red bg) / CLOSED (green bg) |
| Failures (24h) | count / threshold — turns red when at threshold |
| Auto Reset | 24h when open, N/A when closed |

Alerts: Red warning when OPEN, Yellow caution when failures > 0 but not open

**6. Rightsizing Proposals Card:**
- Refresh button
- Proposal list — each shows: `Status Badge (PENDING/APPROVED/REJECTED/EXECUTED)` · `Created date` · `Current → Proposed instance type` · `Savings $/mo` · `Savings %` · `Rejection reason` · `Execute button (APPROVED only)`

**EV Comparison Panel (3 options):**
| Option | Fields | Highlight |
|---|---|---|
| Option A (Pool optimization) | Hourly cost, Savings, Risk %, EV | Blue border if recommended |
| Option B (Rightsizing) | Hourly cost, Savings, Risk %, EV | Blue border if recommended |
| Option C (Baseline) | Hourly cost, No change, Risk %, EV | Blue border if recommended |

**Action Buttons (approval flow):**
- `Approve & Execute` button (FiCheck icon) — for PENDING proposals
- `Reject` button (FiX icon) — prompts for rejection reason
- `Close (✕)` — dismiss EV comparison

---

### 20.7 HibernationDashboardNew.jsx — Key Sub-Elements

**Tabs:** `Schedules` · `History` · `Savings`

**Schedule Card Sub-Elements:**
- Toggle per schedule (active/inactive)
- Edit button per schedule
- Delete button per schedule
- Weekly matrix grid (168 hour cells: 24h × 7 days) with click-to-toggle
- Strategy dropdown (`namespace_sleep` / `node_scale_down` / `combined`)
- Timezone select dropdown
- Pre-warm minutes number input
- Save Schedule button
- Cancel button

**History Tab:**
- Execution history table columns: `Timestamp` · `Action (Hibernate/Wake)` · `Strategy` · `Status (Badge)` · `Duration` · `Savings`
- Live Progress Banner (during active execution)

**Savings Tab:**
- Savings report KPIs: `Total Saved` · `Avg per Schedule` · `Non-Business Hours Covered %`
- Savings history chart placeholder

---

### 20.8 Right-Sizing Components — Key Sub-Elements

**RightSizingDashboard.jsx:**
- Cluster selector dropdown
- Time range selector (24h / 7d / 30d)
- Recommendation table columns: `Controller` · `Namespace` · `Kind` · `Current CPU` · `Recommended CPU` · `Current Memory` · `Recommended Memory` · `Savings` · `Confidence Badge` · `Action (Apply)`
- Apply button per row
- Apply All button
- Refresh button

**EVDelta.jsx:**
- EV delta visualization bars (current vs proposed)
- Savings percentage badge per controller

**InstanceFallbackChain.jsx:**
- Fallback chain table: `Priority` · `Instance Type` · `Status` · `Price` · `TTL`
- Override button

**KarpenterModeToggle.jsx:**
- Mode toggle: `Insights Only (dry-run)` vs `Auto-Optimize`
- Mode description text
- Confirmation modal on mode switch

---

### 20.9 Admin Components — Key Sub-Elements

**AdminDashboard.jsx:**
- System health KPI cards: `Active Clusters` · `Healthy Agents` · `API Latency` · `Error Rate`
- Recent audit log table

**AdminHealth.jsx:**
- Service status list: each service shows name + status badge (healthy/degraded/down)
- Database connection pool status
- Memory usage gauge
- CPU usage gauge

**AdminClients.jsx:**
- Client list table: `Name` · `Organization` · `Status Badge` · `Clusters` · `Last Active`
- Add Client button
- Edit/Delete action buttons per row

**AdminBilling.jsx:**
- Billing summary cards
- Invoice table: `Date` · `Amount` · `Status` · `Download` button

---

### 20.10 Settings & Other Components — Key Sub-Elements

**Settings.jsx:**
- Profile section: email, name display
- Notification preferences toggles
- API key management (reveal/regenerate)
- Theme toggle (if present)

**Shared Components (shared/):**
- `Button.jsx`: variants = `primary` / `outline` / `ghost` / `danger`, sizes = `sm` / `md` / `lg`, supports `icon` prop, `loading` state
- `Card.jsx`: wrapper with border/shadow, optional `title` prop
- `Badge.jsx`: colors = `green` / `blue` / `yellow` / `red` / `purple` / `gray` / `indigo`, sizes = `sm` / `lg`
- `Modal.jsx`: overlay + centered content + close button
- `Input.jsx`: text/number/password with label + error state

**Dashboard Widgets (dashboard/widgets/):**
- `ActivityFeed.jsx`: action log list with status dot (success/error/info)
- `AgentStatusWidget.jsx`: agent connection status + count
- `ClusterHealthCard.jsx`: cluster health summary
- `FleetComposition.jsx`: fleet stats visualization
- `PendingApprovalsCard.jsx`: pending approval list
- `SpendForecastWidget.jsx`: projected spend chart

**AtharvaAI Additional Components:**
- `OptimizationModeSelector.jsx`: 3-mode radio card selector (COST_FIRST / BALANCED / NO_DOWNTIME_FIRST) with descriptions + save
- `AutoRebalanceAuditCard.jsx`: audit entries table + status badges
- `RebalancingTimeline.jsx`: timeline event list with action badges
- `InterruptionHeatmap.jsx`: heatmap grid (instance type × AZ) with color intensity
- `GlobalPoolCache.jsx`: cache hit/miss stats + pool list table + TTL badges
- `WorkloadClassificationView.jsx`: classification badge + pod breakdown
- `VolatilityMonitor.jsx`: real-time volatility feed + regime badges

**Cluster Additional Components:**
- `NodeList.jsx`: node table with status/type/utilization per node
- `NodeGroupBreakdown.jsx`: node group cards with instance counts
- `ClusterHealthTimeline.jsx`: health event timeline
- `NodeTemplateTab.jsx`: node template CRUD — create/edit/delete forms with fields: Name, Architectures multi-select, vCPU min/max, Memory min/max, Allowed Families multi-select, Excluded Types list, Allowed Zones checkboxes
