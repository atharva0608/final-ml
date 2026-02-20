# All Files — Deep Scan Catalog

> Auto-generated deep scan of every file in the project.
> Last updated: 2026-02-20 (12:20)
>
> **Recent Updates**: Right-Sizing consolidated from 12 separate files into single `RightSizingDashboard.jsx` (50KB all-in-one). Hibernation components (29 files) intact. Pages reduced from 9 to 7 (`HibernationDashboard.jsx`, `HibernationPage.jsx` removed — hibernation now accessed via component). Added: `REAL_IMPLEMENTATION_PLAN.md`, `Q&A.md` to documents. `CLAUDE.md` updated with comprehensive project reference. Backend: `REAL_IMPLEMENTATION_PLAN.md` created for AtharvaAI, Hibernation, and Right-Sizing real AWS API integration.

---

## Table of Contents
1. [Root-Level Files](#1-root-level-files)
2. [Backend — API Routes](#2-backend--api-routes)
3. [Backend — Services](#3-backend--services)
4. [Backend — Models](#4-backend--models)
5. [Backend — Schemas](#5-backend--schemas)
6. [Backend — Core](#6-backend--core)
7. [Backend — Resource_rules](#7-backend--resource_rules)
8. [Backend — Modules (ML)](#8-backend--modules-ml)
9. [Backend — Calculations](#9-backend--calculations)
10. [Backend — Scrapers](#10-backend--scrapers)
11. [Backend — Workers](#11-backend--workers)
12. [Backend — Routers](#12-backend--routers)
13. [Backend — Migrations](#13-backend--migrations)
14. [Backend — Hibernation Strategy](#14-backend--hibernation-strategy)
15. [Backend — Utils](#15-backend--utils)
16. [Backend — Scripts](#16-backend--scripts)
17. [Backend — Templates](#17-backend--templates)
18. [Backend — Static](#18-backend--static)
19. [Frontend — Pages](#19-frontend--pages)
20. [Frontend — Components](#20-frontend--components)
21. [Frontend — Services](#21-frontend--services)
22. [Frontend — Hooks](#22-frontend--hooks)
23. [Frontend — Store (Zustand)](#23-frontend--store-zustand)
24. [Frontend — Utils](#24-frontend--utils)
25. [Frontend — App Entry](#25-frontend--app-entry)
26. [Docker & Infrastructure](#26-docker--infrastructure)
27. [Helm Charts](#27-helm-charts)
28. [Root-Level Scripts](#28-root-level-scripts)
29. [Root-Level Migrations (Alembic)](#29-root-level-migrations-alembic)
30. [Documents](#30-documents)
31. [Config](#31-config)

---

## 1. Root-Level Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI application entry point |
| `alembic.ini` | Alembic migration configuration |
| `CLAUDE.md` | Comprehensive project reference (structure, API routes, services, schemas, troubleshooting) |
| `.env` | Environment variables (secrets, DB, Redis, AWS) |
| `.env.example` | Example env template |
| `.gitignore` | Git ignore rules |
| `package.json` | Root-level npm package config |
| `requirements.txt` | Python dependencies |
| `start.sh` | Main startup script (orchestrates backend + frontend + workers) |
| `rebuild.sh` | Quick rebuild script |
| `check-agent-status.sh` | Agent health check script |
| `redeploy-agent.sh` | Agent redeployment script |
| `test_real_apis.sh` | API integration test script |
| `test_scanner.py` | Scanner test utility |
| `debug_clusters.py` | Cluster debugging utility |
| `fix-auth.html` | Auth debugging page |
| `login_response.json` | Sample login response for testing |
| `cleanup_hibernation_demo_data.sql` | SQL to clean hibernation demo data |
| `changelogic.md` | Change logic documentation |
| `changes.txt` | Change log text |

### Root-Level Summary Docs (Markdown)
| File | Purpose |
|------|---------|
| `ALL_REAL_API_MIGRATION_COMPLETE.md` | Real API migration completion summary |
| `CHANGELOGIC_IMPLEMENTATION_SUMMARY.md` | Change logic implementation notes |
| `COMPONENTS_AUDIT_COMPLETE.md` | Component audit results |
| `COMPONENT_AUDIT_SUMMARY.md` | Audit summary |
| `DOCUMENTS_ALL_COMPONENTS_UPDATE_SUMMARY.md` | Documentation update summary |
| `HIBERNATION_COMPLETE_RESTRUCTURE.md` | Hibernation restructure notes |
| `HIBERNATION_FIXES_COMPLETE.md` | Hibernation fixes summary |
| `HIBERNATION_IMPLEMENTATION.md` | Hibernation implementation details |
| `HIBERNATION_INTEGRATION_SUMMARY.md` | Integration summary |
| `HIBERNATION_MODULAR_INTEGRATION.md` | Modular integration notes |
| `HIBERNATION_TESTING_GUIDE.md` | Testing guide |
| `HIBERNATION_UI_IMPROVEMENTS.md` | UI improvements |
| `HIBERNATION_VERIFICATION_COMPLETE.md` | Verification results |
| `KARPENTER_IMPLEMENTATION_SUMMARY.md` | Karpenter implementation summary |
| `MOCK_SYSTEM_REMOVAL_COMPLETE.md` | Mock system removal |
| `REAL_API_IMPLEMENTATION_COMPLETE.md` | Real API implementation |
| `REBUILD_RESTART_SUMMARY.md` | Rebuild/restart summary |
| `REGRESSION_TEST_SUMMARY.md` | Regression testing results |
| `RIGHT_SIZING_IMPLEMENTATION_COMPLETE.md` | Right-sizing implementation |

---

## 2. Backend — API Routes

**Directory:** `backend/api/`

| File | Purpose |
|------|---------|
| `__init__.py` | Router registry — mounts all sub-routers |
| `INFO.md` | API routes documentation |
| `account_routes.py` | Account CRUD operations |
| `admin_routes.py` | Super-admin endpoints (tenants, health, config) |
| `agent_routes.py` | Agent fleet management |
| `approval_routes.py` | Approval/ticket workflow |
| `atharvaai_routes.py` | Atharva AI assistant endpoints |
| `audit_routes.py` | Audit log retrieval |
| `auth_routes.py` | Authentication (login, signup, invite, password reset) |
| `auto_tag_routes.py` | Auto-tag rule management |
| `billing_routes.py` | Billing and invoice endpoints |
| `cluster_routes.py` | Cluster CRUD, connect/disconnect, metrics |
| `dashboard_routes.py` | Dashboard KPIs and summary data |
| `governance_routes.py` | Governance rule management |
| `health_routes.py` | Health check endpoint |
| `hibernation_routes.py` | Hibernation schedule CRUD, emergency sleep/wake, execution status, savings history, notification settings |
| `hygiene_policy_routes.py` | Hygiene policy management |
| `hygiene_routes.py` | Resource hygiene scan and cleanup |
| `installer_routes.py` | Agent installer (generates YAML) |
| `karpenter_routes.py` | Karpenter configuration and provisioner management |
| `lab_routes.py` | Experiment lab management |
| `metrics_routes.py` | Instance and cost metrics |
| `onboarding_routes.py` | AWS onboarding flow |
| `optimization_routes.py` | Optimization job management |
| `organization_routes.py` | Organization CRUD |
| `permission_routes.py` | Permission management (RBAC) |
| `pod_metrics_routes.py` | Pod-level metrics |
| `policy_routes.py` | Cluster policy management |
| `rds_routes.py` | RDS analysis endpoints |
| `ri_routes.py` | Reserved Instance analysis |
| `role_routes.py` | Role CRUD |
| `s3_routes.py` | S3 tiering analysis |
| `settings_routes.py` | User settings |
| `smart_tag_routes.py` | Smart tag suggestions |
| `tag_management_routes.py` | Bulk tag operations |
| `tag_policy_routes.py` | Tag compliance policy |
| `tag_template_routes.py` | Tag template CRUD |
| `team_routes.py` | Team management |
| `template_routes.py` | Rebalancing template management |
| `transfer_routes.py` | Data transfer optimization |
| `user_routes.py` | User profile management |

---

## 3. Backend — Services

**Directory:** `backend/services/`

| File | Purpose |
|------|---------|
| `__init__.py` | Service exports |
| `INFO.md` | Services documentation |
| `account_service.py` | Account business logic |
| `admin_service.py` | Admin operations (tenant management) |
| `agent_injector.py` | Kubernetes agent injection logic |
| `approval_service.py` | Approval workflow engine |
| `audit_service.py` | Audit logging |
| `auth_service.py` | Authentication & authorization |
| `auto_tag_service.py` | Auto-tagging engine |
| `cluster_service.py` | Cluster management & discovery |
| `governance_service.py` | Governance rule enforcement |
| `hibernation_service.py` | Hibernation schedule management, multi-cluster support, emergency controls, savings calculation |
| `hygiene_service.py` | Resource hygiene scanning (largest service — 128KB) |
| `hygiene_service_additions.py` | Additional hygiene rules |
| `karpenter_service.py` | Karpenter deployment, configuration, status monitoring, cluster-level settings, activity tracking |
| `lab_service.py` | Experiment lab logic |
| `metrics_service.py` | Instance & cost metrics aggregation |
| `ml_feature_service.py` | ML feature engineering |
| `onboarding_service.py` | AWS onboarding workflow |
| `organization_service.py` | Organization management |
| `permission_service.py` | RBAC permission logic |
| `policy_service.py` | Cluster policy enforcement |
| `pool_ranking_service.py` | Instance pool ranking |
| `rds_analysis_service.py` | RDS multi-AZ analysis |
| `resource_cost_service.py` | Resource cost calculation |
| `resource_pricing_service.py` | Pricing data management |
| `ri_analysis_service.py` | Reserved Instance waste detection |
| `rightsizing_service.py` | Right-sizing recommendations |
| `role_service.py` | Role management logic |
| `s3_tiering_service.py` | S3 intelligent tiering analysis |
| `savings_plan_service.py` | Savings plan analysis |
| `settings_service.py` | User settings management |
| `smart_tag_service.py` | Smart tag suggestions |
| `tag_management_service.py` | Bulk tag operations |
| `tag_policy_service.py` | Tag compliance enforcement |
| `tag_suggestion_service.py` | Tag suggestion engine |
| `team_service.py` | Team management logic |
| `template_service.py` | Rebalancing template management |
| `transfer_service.py` | Data transfer analysis |

---

## 4. Backend — Models

**Directory:** `backend/models/`

| File | Purpose |
|------|---------|
| `__init__.py` | Model exports & registry |
| `INFO.md` | Models documentation |
| `base.py` | SQLAlchemy base model with common fields |
| `account.py` | Account model (AWS accounts) |
| `agent_action.py` | Agent action log model |
| `api_key.py` | API key model |
| `approval.py` | Approval/ticket model |
| `audit_log.py` | Audit log model |
| `authorized_resource.py` | Authorized resource model |
| `auto_tag_rule.py` | Auto-tag rule model |
| `billing.py` | Billing model |
| `cluster.py` | Cluster model |
| `cluster_metric.py` | Cluster metric time-series |
| `cluster_policy.py` | Cluster policy model |
| `hibernation_schedule.py` | Hibernation schedule model |
| `hibernation_schedule_clusters.py` | Hibernation-cluster association |
| `hygiene_policy.py` | Hygiene policy model |
| `instance.py` | EC2 instance model |
| `invitation.py` | User invitation model |
| `lab_experiment.py` | Lab experiment model |
| `legacy_approval.py` | Legacy approval model |
| `ml_model.py` | ML model metadata |
| `node_template.py` | Node template (Karpenter) |
| `onboarding.py` | Onboarding progress model |
| `optimization_job.py` | Optimization job model |
| `organization.py` | Organization model |
| `permission.py` | Permission model |
| `platform_settings.py` | Platform settings model |
| `pod_metric.py` | Pod metric model |
| `pricing.py` | Instance pricing model |
| `rds_analysis.py` | RDS analysis results model |
| `rebalancing_action.py` | Rebalancing action log |
| `ri_utilization.py` | RI utilization model |
| `role.py` | Role model |
| `s3_analysis.py` | S3 analysis results model |
| `savings_plan_utilization.py` | Savings plan utilization model |
| `spot_price_history.py` | Spot price history model |
| `system_config.py` | System config model |
| `tag_policy.py` | Tag policy model |
| `tag_template.py` | Tag template model |
| `team.py` | Team model |
| `termination_event.py` | Spot termination event model |
| `transfer_analysis.py` | Transfer analysis model |
| `user.py` | User model (auth, roles, org) |

---

## 5. Backend — Schemas

**Directory:** `backend/schemas/`

| File | Purpose |
|------|---------|
| `__init__.py` | Schema exports |
| `INFO.md` | Schemas documentation |
| `account_schemas.py` | Account request/response schemas |
| `admin_schemas.py` | Admin panel schemas |
| `approval_schemas.py` | Approval workflow schemas |
| `audit_schemas.py` | Audit log schemas |
| `auth_schemas.py` | Auth (login, signup, token) schemas |
| `auto_tag_schemas.py` | Auto-tag schemas |
| `cluster_schemas.py` | Cluster schemas (largest — 14KB) |
| `dashboard_schemas.py` | Dashboard KPI schemas |
| `hibernation_schemas.py` | Hibernation schedule schemas |
| `hygiene_policy_schemas.py` | Hygiene policy schemas |
| `hygiene_schemas.py` | Resource hygiene schemas |
| `lab_schemas.py` | Lab experiment schemas |
| `metric_schemas.py` | Metric schemas |
| `organization_schemas.py` | Organization schemas |
| `pod_metric_schemas.py` | Pod metric schemas |
| `policy_schemas.py` | Cluster policy schemas |
| `role_schemas.py` | Role schemas |
| `settings_schemas.py` | Settings schemas |
| `tag_management_schemas.py` | Tag management schemas |
| `tag_policy_schemas.py` | Tag policy schemas |
| `tag_template_schemas.py` | Tag template schemas |
| `team_schemas.py` | Team schemas |
| `template_schemas.py` | Rebalancing template schemas |

---

## 6. Backend — Core

**Directory:** `backend/core/`

| File | Purpose |
|------|---------|
| `__init__.py` | Core module exports |
| `INFO.md` | Core module documentation |
| `action_executor.py` | AWS action executor (spot launches, terminations) |
| `api_gateway.py` | Internal API gateway for cross-service calls |
| `config.py` | Application configuration (Pydantic settings) |
| `crypto.py` | Encryption/decryption utilities |
| `decision_engine.py` | Optimization decision logic |
| `dependencies.py` | FastAPI dependency injection |
| `exceptions.py` | Custom exception hierarchy |
| `feature_registry.py` | Feature flag registry (largest — 48KB) |
| `health_service.py` | Platform health monitoring |
| `logger.py` | Structured logging configuration |
| `redis_client.py` | Redis connection setup |
| `sse_manager.py` | Server-Sent Events manager |
| `validators.py` | Input validation utilities |

---

## 7. Backend — Resource_rules

**Directory:** `backend/Resource_rules/`

| File | Purpose |
|------|---------|
| `__init__.py` | Rules registry & exports |
| `compute_rules.py` | EC2 compute hygiene rules |
| `database_rules.py` | RDS/database hygiene rules |
| `identity_rules.py` | IAM identity hygiene rules |
| `management_rules.py` | CloudWatch/management hygiene rules |
| `network_rules.py` | VPC/networking hygiene rules |
| `security_rules.py` | Security group/WAF hygiene rules |
| `storage_rules.py` | S3/EBS storage hygiene rules |

---

## 8. Backend — Modules (ML)

**Directory:** `backend/modules/`

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `INFO.md` | Modules documentation |
| `bin_packer.py` | Bin-packing algorithm for node optimization |
| `ml_model_server.py` | ML model serving (prediction API) |
| `model_validator.py` | Model validation utilities |
| `rightsizer.py` | Right-sizing recommendation engine |
| `risk_tracker.py` | Risk score tracking |
| `spot_optimizer.py` | Spot instance optimization |

---

## 9. Backend — Calculations

**Directory:** `backend/calculations/`

| File | Purpose |
|------|---------|
| `__init__.py` | Calculation exports |
| `README.md` | Calculations documentation |
| `cost_calculations.py` | Cost computation formulas |
| `metrics_calculations.py` | Metric aggregation formulas |
| `savings_calculations.py` | Savings computation formulas |

---

## 10. Backend — Scrapers

**Directory:** `backend/scrapers/`

| File | Purpose |
|------|---------|
| `__init__.py` | Scraper exports |
| `INFO.md` | Scrapers documentation |
| `pricing_collector.py` | AWS pricing API collector |
| `spot_advisor_scraper.py` | Spot Advisor data scraper |

---

## 11. Backend — Workers

**Directory:** `backend/workers/`

| File | Purpose |
|------|---------|
| `__init__.py` | Worker app exports |
| `INFO.md` | Workers documentation |
| `app.py` | Celery app configuration |

### Worker Tasks (`backend/workers/tasks/`)

| File | Purpose |
|------|---------|
| `__init__.py` | Task exports |
| `agent_tasks.py` | Agent management tasks |
| `approval_cleanup.py` | Expired approval cleanup |
| `atharvaai_worker.py` | AtharvaAI async processing |
| `auto_rebalancer.py` | Automatic rebalancing task |
| `cost_calculator.py` | Cost calculation task |
| `cost_explorer.py` | AWS Cost Explorer data fetch |
| `discovery.py` | Cluster discovery task |
| `event_processor.py` | Event processing pipeline |
| `health.py` | Health check task |
| `hibernation_worker.py` | Hibernation execution task |
| `optimization.py` | Optimization job runner |
| `pod_metrics_cleanup.py` | Pod metrics data cleanup |
| `pricing_task.py` | Pricing data refresh task |
| `report_worker.py` | Report generation task |
| `resource_pricing_worker.py` | Resource pricing update task |
| `savings_calculator.py` | Savings calculation task |
| `termination_monitor.py` | Spot termination monitoring |

---

## 12. Backend — Routers

**Directory:** `backend/routers/`

| File | Purpose |
|------|---------|
| `actions.py` | Action router (execute/rollback) |
| `agents.py` | Agent router (status, deploy) |
| `metrics.py` | Metrics router (pod, node) |

---

## 13. Backend — Migrations

### `backend/migrations/`

| File | Purpose |
|------|---------|
| `004_add_user_status.py` | Add user status column |
| `005_add_team_model.py` | Add team model tables |
| `006_update_hibernation_schedule.py` | Update hibernation schedule schema |
| `debug_columns.py` | Column debugging utility |
| `debug_db.py` | Database debugging utility |

#### `backend/migrations/versions/`

| File | Purpose |
|------|---------|
| `007_cleanup_policies.py` | Cleanup policy tables |
| `008_core_modules.py` | Core module tables |
| `009_dynamic_auto_tags.py` | Dynamic auto-tag tables |
| `010_tag_template_resource_scope.py` | Tag template scope column |
| `011_add_cluster_costs.py` | Cluster cost columns |
| `20260216_atharvaai_tables.py` | AtharvaAI tables |

### Root-level `migrations/` (Alembic)

| File | Purpose |
|------|---------|
| `INFO.md` | Migrations documentation |
| `env.py` | Alembic environment config |
| `script.py.mako` | Migration template |

#### `migrations/versions/`

| File | Purpose |
|------|---------|
| `001_initial_schema.py` | Initial database schema |
| `002_seed_data.py` | Initial seed data |
| `003_add_governance_columns.py` | Governance columns |
| `20260119_0550_…_add_team_member_permissions.py` | Team member permissions |
| `20260119_0644_…_add_ri_utilization_model.py` | RI utilization model |
| `20260119_0648_…_add_s3_analysis_model.py` | S3 analysis model |
| `20260119_0653_…_add_rds_analysis_model.py` | RDS analysis model |
| `20260119_0657_…_add_transfer_analysis_model.py` | Transfer analysis model |
| `20260130_1200_fix_tag_templates.py` | Fix tag templates |
| `20260210_add_cost_explorer_tables.py` | Cost explorer tables |
| `20260210_hibernation_strategies.py` | Hibernation strategies |
| `20260210_rename_tickets_to_approvals.py` | Rename tickets → approvals |
| `20260212_add_account_id_to_instances.py` | Account ID on instances |
| `20260216_add_schedule_type.py` | Schedule type column |
| `20260216_pod_metrics.py` | Pod metrics tables |

---

## 14. Backend — Hibernation Strategy

**Directory:** `backend/hibernation_strategy/`

| File | Purpose |
|------|---------|
| `__init__.py` | Strategy exports |
| `namespace_sleep.py` | Namespace sleep strategy (scale to 0) |
| `nuclear.py` | Nuclear hibernation (full shutdown) |
| `snapshot_restore.py` | Snapshot & restore strategy |

---

## 15. Backend — Utils

**Directory:** `backend/utils/`

| File | Purpose |
|------|---------|
| `INFO.md` | Utils documentation |
| `pricing_helper.py` | Pricing helper utilities |

---

## 16. Backend — Scripts

**Directory:** `backend/scripts/`

| File | Purpose |
|------|---------|
| `get_admin_token.py` | Generate admin auth token |
| `seed_permissions.py` | Seed RBAC permissions |
| `seed_rbac.py` | Seed RBAC roles |

---

## 17. Backend — Templates

**Directory:** `backend/templates/`

| File | Purpose |
|------|---------|
| `install.sh` | Agent installation script template |

### `backend/templates/aws/`

| File | Purpose |
|------|---------|
| `full-access-role.yaml` | AWS IAM full-access role template |
| `read-only-role.yaml` | AWS IAM read-only role template |

### `backend/templates/k8s/`

| File | Purpose |
|------|---------|
| `agent.yaml` | Kubernetes agent deployment template |

---

## 18. Backend — Static

**Directory:** `backend/static/`

| File | Purpose |
|------|---------|
| `asset-manifest.json` | Frontend asset manifest |
| `favicon.ico` | Application favicon |
| `index.html` | SPA entry point (served by backend) |
| `logo192.png` | App logo |
| `manifest.json` | PWA manifest |

### `backend/static/static/css/`
Compiled CSS bundles (build artifacts).

### `backend/static/static/js/`
Compiled JS bundles (build artifacts).

---

## 19. Frontend — Pages

**Directory:** `frontend/src/pages/`

| File | Purpose |
|------|---------|
| `AccountAnalytics.jsx` | Account analytics page |
| `Approvals.jsx` | Approval management page |
| `AtharvaAiPage.jsx` | Atharva AI assistant page |
| `Onboarding.jsx` | AWS onboarding wizard page |
| `Roles.jsx` | Role management page |
| `TeamDetails.jsx` | Team detail view page |
| `Teams.jsx` | Team management page |

---

## 20. Frontend — Components

### `components/admin/` (13 files)

| File | Purpose |
|------|---------|
| `AdminAgentFleet.jsx` | Agent fleet management panel |
| `AdminBilling.jsx` | Billing administration |
| `AdminClients.jsx` | Client management |
| `AdminConfig.jsx` | Platform configuration |
| `AdminDashboard.jsx` | Admin dashboard root |
| `AdminExperiments.jsx` | Experiment management |
| `AdminHealth.jsx` | Platform health monitoring |
| `AdminImpersonation.jsx` | User impersonation |
| `AdminOrganizations.jsx` | Organization management |
| `AdminOverview.jsx` | Admin overview dashboard |
| `AdminTenantDrilldown.jsx` | Tenant detail view |
| `PlatformSettings.jsx` | Platform settings panel |
| `INFO.md` | Admin components documentation |

### `components/approvals/` (3 files)

| File | Purpose |
|------|---------|
| `AccessRequestModal.jsx` | Access request modal |
| `ActiveWindowBanner.jsx` | Active approval window banner |
| `TicketRequestModal.jsx` | Ticket/approval request modal |

### `components/atharvaai/` (5 files)

| File | Purpose |
|------|---------|
| `AutoRebalanceAuditCard.jsx` | Auto-rebalance audit display |
| `InterruptionHeatmap.jsx` | Spot interruption heatmap |
| `PoolRankings.css` | Pool rankings styles |
| `PoolRankings.jsx` | Instance pool rankings |
| `RebalancingTimeline.jsx` | Rebalancing timeline visualization |

### `components/audit/` (2 files)

| File | Purpose |
|------|---------|
| `AuditLog.jsx` | Audit log viewer |
| `INFO.md` | Audit component documentation |

### `components/auth/` (4 files)

| File | Purpose |
|------|---------|
| `InviteAcceptance.jsx` | Invitation acceptance flow |
| `Login.jsx` | Login form |
| `Signup.jsx` | Signup form |
| `INFO.md` | Auth components documentation |

### `components/cleanup/` (10 files)

| File | Purpose |
|------|---------|
| `BulkTagWizard.jsx` | Bulk tag application wizard |
| `CleanupDashboard.jsx` | Resource cleanup dashboard |
| **layout/** | |
| `CleanupSidebar.jsx` | Cleanup sidebar navigation |
| `FilterPanel.jsx` | Resource filter panel |
| **summary/** | |
| `HeroMetricsPanel.jsx` | Hero metrics summary |
| `SavingsGauge.jsx` | Animated savings gauge |
| **tables/** | |
| `ResourceTable.jsx` | Resource results table |
| **wizards/** | |
| `RDSWizard.jsx` | RDS cleanup wizard |
| `RIWizard.jsx` | RI cleanup wizard |
| `S3Wizard.jsx` | S3 cleanup wizard |

### `components/clusters/` (11 files)

| File | Purpose |
|------|---------|
| `ClusterDeleteModal.jsx` | Cluster deletion confirmation |
| `ClusterDetails.jsx` | Cluster detail view |
| `ClusterDisconnectModal.jsx` | Cluster disconnect modal |
| `ClusterHealthTimeline.jsx` | Cluster health timeline |
| `ClusterList.jsx` | Cluster list view |
| `ClusterUtilizationSparkline.jsx` | Utilization sparkline chart |
| `NodeGroupBreakdown.jsx` | Node group breakdown |
| `NodeList.jsx` | Node list table |
| `PolicyGapAlert.jsx` | Policy gap alert |
| `SpotRatioGauge.jsx` | Spot ratio gauge |
| `INFO.md` | Cluster components documentation |

### `components/dashboard/` (16 files)

| File | Purpose |
|------|---------|
| `Dashboard.jsx` | Main dashboard component |
| `roleDefaults.js` | Role-based default widget config |
| `widgetRegistry.js` | Widget registry |
| `INFO.md` | Dashboard documentation |
| **widgets/** | |
| `ActivityFeed.jsx` | Activity feed widget |
| `AgentStatusWidget.jsx` | Agent status widget |
| `ClusterHealthCard.jsx` | Cluster health card |
| `CostKPICard.jsx` | Cost KPI card |
| `FleetComposition.jsx` | Fleet composition chart |
| `PendingApprovalsCard.jsx` | Pending approvals card |
| `PlatformHealthCard.jsx` | Platform health card |
| `SavingsChart.jsx` | Savings chart widget |
| `SavingsKPICard.jsx` | Savings KPI card |
| `SpendForecastWidget.jsx` | Spend forecast widget |
| `TenantListCard.jsx` | Tenant list card |
| `index.js` | Widget exports |

### `components/governance/` (4 files)

| File | Purpose |
|------|---------|
| `ActiveJITBanner.jsx` | Active JIT access banner |
| `JITRequestModal.jsx` | JIT access request modal |
| `PermissionGate.jsx` | Permission gate wrapper |
| `ProtectedButton.jsx` | Permission-protected button |

### `components/hibernation/` (29 files)

| File | Purpose |
|------|---------|
| `AdvancedConfiguration.jsx` | Advanced hibernation configuration options |
| `AuditHistory.jsx` | Compact execution history table with timestamps, actions, status |
| `ClusterOverview.jsx` | Cluster overview for hibernation |
| `ConflictDetectionModal.jsx` | Schedule conflict detection and resolution modal |
| `CostAnalytics.jsx` | Cost analytics panel |
| `CostAnalyticsDashboard.jsx` | Full cost analytics dashboard with savings breakdown |
| `EmergencyControls.jsx` | Emergency sleep/wake controls with force override buttons |
| `ExecutionHistory.jsx` | Detailed execution history log with filters |
| `HibernationDashboardNew.jsx` | **Primary dashboard**: LiveProgressBanner, SavingsReport, ScheduleMatrix (168-hour grid), StrategySelector, AuditHistory, EmergencyControls |
| `HibernationHeader.jsx` | Hibernation page header component |
| `HibernationScheduler.jsx` | Schedule creation wizard |
| `HibernationTypeCard.jsx` | Hibernation type selection card |
| `HibernationWizard.jsx` | Full hibernation setup wizard |
| `HistoryLog.jsx` | History log panel |
| `MultiTimezone.jsx` | Multi-timezone selector component |
| `NotificationSettings.jsx` | Notification settings: Email/Slack/Webhook, threshold alerts, failure notifications |
| `ScheduleBuilder.jsx` | Schedule builder component |
| `ScheduleCalendar.jsx` | Calendar-style schedule view |
| `ScheduleMatrix.jsx` | **168-hour weekly grid** (7 days × 24 hours) with click-and-drag, presets (Weeknights/Weekends/Nights), Clear/Fill All |
| `ScheduleModal.jsx` | Schedule creation modal |
| `ScheduleTemplates.jsx` | Pre-built schedule templates (Business Hours, Nights Only, Weekends Off) |
| `StatusBanner.jsx` | Live status banner with current hibernation state |
| `StrategySelector.jsx` | Strategy selector cards (Namespace Sleep, Nuclear, Snapshot & Restore) with wake time, savings %, risk level |
| `TimeBasedRules.jsx` | Time-based rule configuration |
| `UnifiedScheduleGrid.jsx` | Unified schedule grid component |
| `ValidationPanel.jsx` | Schedule validation panel with conflict detection |
| `index.js` | Hibernation component exports |
| `INFO.md` | Hibernation component documentation |
| `README.md` | Hibernation feature documentation |

### `components/lab/` (1 file)

| File | Purpose |
|------|---------|
| `ExperimentLab.jsx` | Experiment lab management |

### `components/layout/` (1 file)

| File | Purpose |
|------|---------|
| `MainLayout.jsx` | Main application layout (sidebar + content) |

### `components/onboarding/` (4 files)

| File | Purpose |
|------|---------|
| `ConnectStep.jsx` | AWS connection step |
| `SuccessStep.jsx` | Success confirmation step |
| `VerifyStep.jsx` | Verification step |
| `WelcomeStep.jsx` | Welcome/intro step |

### `components/policies/` (5 files)

| File | Purpose |
|------|---------|
| `CleanupPolicies.jsx` | Cleanup policy management |
| `PermissionMatrix.jsx` | Permission matrix view |
| `PolicyConfig.jsx` | Policy configuration |
| `TagTemplateManager.jsx` | Tag template manager |
| `INFO.md` | Policies documentation |

### `components/rds/` (2 files)

| File | Purpose |
|------|---------|
| `RDSAnalysis.jsx` | RDS analysis dashboard |
| `RDSHealthCard.jsx` | RDS health card |

### `components/ri/` (2 files)

| File | Purpose |
|------|---------|
| `RIAnalysis.jsx` | RI analysis dashboard |
| `RIHealthCard.jsx` | RI health card |

### `components/right-sizing/` (1 file — consolidated)

| File | Purpose |
|------|---------|
| `RightSizingDashboard.jsx` | **All-in-one 50KB consolidated dashboard** — Dual-mode container (Manual/Karpenter) with mode switcher, KPI strip, recommendations table with Pool Health column and Template compliance, enriched recommendations with blacklist checking, SavingsTracker, InstanceUsageDetailPanel, BatchApplyModal, ImpactSummary, RecommendationAgeIndicator, KarpenterEnable (one-click setup), KarpenterSetup (4-step wizard), KarpenterDashboard (live monitoring), KarpenterSettings (5-tab slide-over). Previously 12 separate files now consolidated into single component |

### `components/s3/` (2 files)

| File | Purpose |
|------|---------|
| `S3Analysis.jsx` | S3 tiering analysis dashboard |
| `S3HealthCard.jsx` | S3 health card |

### `components/transfer/` (2 files)

| File | Purpose |
|------|---------|
| `TransferAnalysis.jsx` | Data transfer analysis dashboard |
| `TransferHealthCard.jsx` | Data transfer health card |

### `components/settings/` (12 files)

| File | Purpose |
|------|---------|
| `AccountSettings.jsx` | Account settings page |
| `CloudIntegrations.jsx` | Cloud integration management |
| `GovernanceManager.jsx` | Governance settings manager |
| `GovernanceSettings.jsx` | Governance settings form |
| `MemberPermissionsModal.jsx` | Member permissions modal |
| `Settings.jsx` | Settings root component |
| `TagPoliciesList.jsx` | Tag policies list |
| `TagPoliciesManager.jsx` | Tag policies manager |
| `TagTemplateManager.jsx` | Tag template manager |
| `TeamGovernance.jsx` | Team governance settings |
| `TeamManagement.jsx` | Team management panel |
| `INFO.md` | Settings documentation |

### `components/shared/` (11 files)

| File | Purpose |
|------|---------|
| `Badge.jsx` | Badge component |
| `Button.jsx` | Button component |
| `Card.jsx` | Card component |
| `Dropdown.jsx` | Dropdown component |
| `EmptyState.jsx` | Empty state placeholder |
| `GaugeChart.jsx` | Gauge chart component |
| `Input.jsx` | Input component |
| `RiskBadge.jsx` | Risk badge component |
| `StatsCard.jsx` | Stats card component |
| `Switch.jsx` | Toggle switch component |
| `index.js` | Shared component exports |

---

## 21. Frontend — Services

**Directory:** `frontend/src/services/`

| File | Purpose |
|------|---------|
| `api.js` | Main API service (axios instance + all endpoints), includes karpenterAPI object with 8 Karpenter endpoints |
| `hibernationApi.js` | Hibernation-specific API service: schedules CRUD, emergency sleep/wake, execution status, savings history |
| `INFO.md` | Services documentation |

---

## 22. Frontend — Hooks

**Directory:** `frontend/src/hooks/`

| File | Purpose |
|------|---------|
| `useAuth.js` | Authentication hook |
| `useDashboard.js` | Dashboard data hook |
| `usePermission.js` | Permission check hook |
| `INFO.md` | Hooks documentation |

---

## 23. Frontend — Store (Zustand)

**Directory:** `frontend/src/store/`

| File | Purpose |
|------|---------|
| `useAtharvaStore.js` | AtharvaAI state store |
| `useHibernationStore.js` | Hibernation state store |
| `useStore.js` | Main application store |

---

## 24. Frontend — Utils

**Directory:** `frontend/src/utils/`

| File | Purpose |
|------|---------|
| `formatters.js` | Number/date/currency formatters |
| `INFO.md` | Utils documentation |

---

## 25. Frontend — App Entry

**Directory:** `frontend/src/`

| File | Purpose |
|------|---------|
| `App.js` | Main React app (routing, layout, auth) |
| `index.js` | ReactDOM entry point |
| `index.css` | Global styles |
| `INFO.md` | Frontend source documentation |

---

## 26. Docker & Infrastructure

**Directory:** `docker/`

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Multi-container orchestration |
| `Dockerfile.backend` | Backend container build |
| `Dockerfile.frontend` | Frontend container build |
| `nginx.conf` | Nginx reverse proxy config |
| `.env` | Docker-specific env vars |
| `INFO.md` | Docker infrastructure documentation |

---

## 27. Helm Charts

**Directory:** `charts/spot-optimizer-agent/`

| File | Purpose |
|------|---------|
| `Chart.yaml` | Helm chart metadata |
| `values.yaml` | Default chart values |
| **templates/** | |
| `clusterrole.yaml` | ClusterRole definition |
| `clusterrolebinding.yaml` | ClusterRoleBinding |
| `configmap.yaml` | ConfigMap |
| `daemonset.yaml` | DaemonSet definition |
| `secret.yaml` | Secret definition |
| `serviceaccount.yaml` | ServiceAccount |

---

## 28. Root-Level Scripts

**Directory:** `scripts/`

| File | Purpose |
|------|---------|
| `INFO.md` | Scripts documentation |
| `debug_users.py` | User debugging utility |
| `fix_demo_user.py` | Fix demo user data |
| `migrate_to_organizations.py` | Migrate to organization model |
| `publish_agent.sh` | Publish agent package |
| `publish_helm_chart.sh` | Publish Helm chart |
| `publish_to_dockerhub.sh` | Publish Docker images |
| `seed_admin.py` | Seed admin user |
| `seed_demo_data.py` | Seed demo/test data |
| `seed_test_data.py` | Seed test data |
| `setup_platform_creds.py` | Setup platform credentials |
| `update_and_seed.py` | Update and re-seed data |

### `scripts/aws/`

| File | Purpose |
|------|---------|
| `INFO.md` | AWS scripts documentation |
| `detach_volume.py` | EBS volume detach script |
| `launch_spot.py` | Spot instance launch script |
| `terminate_instance.py` | Instance termination script |
| `update_asg.py` | ASG update script |

### `scripts/deployment/`

| File | Purpose |
|------|---------|
| `INFO.md` | Deployment documentation |
| `deploy.sh` | Deployment script |
| `setup.sh` | Environment setup script |

---

## 29. Root-Level Migrations (Alembic)

See [Section 13](#13-backend--migrations) for the full migration listing.

---

## 30. Documents

**Directory:** `documents/`

| File | Purpose |
|------|---------|
| `MASTER_SUMMARY.md` | Master project summary |
| `README.md` | Documents directory README |
| `REAL_IMPLEMENTATION_PLAN.md` | Real implementation plan for AtharvaAI, Hibernation, and Right-Sizing AWS API integration |
| `Q&A.md` | Questions & answers documentation |
| `all-components.md` | All UI components catalog (this companion doc) |
| `all-files.md` | All files catalog (this document) |
| `backend-feature.md` | Backend feature documentation |
| `schema_info.md` | Database schema documentation |

---

## 31. Config

**Directory:** `config/`

| File | Purpose |
|------|---------|
| `INFO.md` | Configuration documentation |

**Directory:** `docs/`

| File | Purpose |
|------|---------|
| `all-components.md` | Alternative components documentation |

---

## File Count Summary

| Area | Files |
|------|-------|
| Backend — API Routes | 41 |
| Backend — Services | 39 |
| Backend — Models | 44 |
| Backend — Schemas | 25 |
| Backend — Core | 15 |
| Backend — Resource_rules | 8 |
| Backend — Modules | 8 |
| Backend — Calculations | 5 |
| Backend — Scrapers | 4 |
| Backend — Workers (incl. tasks) | 21 |
| Backend — Routers | 3 |
| Backend — Migrations | 17 |
| Backend — Hibernation Strategy | 4 |
| Backend — Utils | 2 |
| Backend — Scripts | 3 |
| Backend — Templates | 4 |
| Backend — Static | 5+ |
| Frontend — Pages | 7 |
| Frontend — Components | ~141 |
| Frontend — Services | 3 |
| Frontend — Hooks | 4 |
| Frontend — Store | 3 |
| Frontend — Utils | 2 |
| Frontend — App Entry | 4 |
| Docker & Infrastructure | 6 |
| Helm Charts | 8 |
| Root-Level Scripts | ~20 |
| Root-Level Migrations | ~18 |
| Documents | 8 |
| Root-Level Files | ~21 |
| **Total (approx.)** | **~498** |
