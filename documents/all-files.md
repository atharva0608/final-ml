# All Files — Deep Scan Catalog

> Auto-generated deep scan of every file in the project.
> Last updated: 2026-02-18

---

## Table of Contents
1. [Root-Level Files](#1-root-level-files)
2. [Backend — API Routes](#2-backend--api-routes)
3. [Backend — Services](#3-backend--services)
4. [Backend — Models](#4-backend--models)
5. [Backend — Schemas](#5-backend--schemas)
6. [Backend — Core](#6-backend--core)
7. [Backend — Resource_rules](#7-backend--resource_rules)
8. [Backend — Hibernation_strategy](#8-backend--hibernation_strategy)
9. [Backend — Workers](#9-backend--workers)
10. [Backend — Calculations](#10-backend--calculations)
11. [Backend — Modules](#11-backend--modules)
12. [Backend — Scrapers](#12-backend--scrapers)
13. [Backend — Routers (Legacy)](#13-backend--routers-legacy)
14. [Backend — Migrations](#14-backend--migrations)
15. [Backend — Scripts](#15-backend--scripts)
16. [Agent](#16-agent)
17. [Frontend — Pages](#17-frontend--pages)
18. [Frontend — Components](#18-frontend--components)
19. [Frontend — Services / Hooks / Store / Utils](#19-frontend--services--hooks--store--utils)
20. [Scripts (Root-Level)](#20-scripts-root-level)
21. [ML Model](#21-ml-model)
22. [Documents](#22-documents)
23. [Duplicate / Unused / Legacy Files](#23-duplicate--unused--legacy-files)

---

## 1. Root-Level Files

| File | Purpose | Feature |
|------|---------|---------|
| `main.py` (backend/) | FastAPI app entry point, mounts all routers | Core Platform |
| `start.sh` | Starts backend + frontend containers | DevOps |
| `rebuild.sh` | Rebuilds Docker containers | DevOps |
| `redeploy-agent.sh` | Redeploys agent to K8s | DevOps, Agent |
| `test_real_apis.sh` | Shell script to test live API endpoints | Testing |
| `test_scanner.py` | Test script for cleanup scanner | Resource Cleanup |
| `requirements.txt` | Python dependencies | Core Platform |
| `package.json` | Node.js project config | Frontend |
| `Dockerfile` | Backend Docker image | DevOps |
| `docker-compose.yaml` | Multi-container orchestration | DevOps |
| `.env` | Environment variables | Core Platform |

---

## 2. Backend — API Routes

**Base prefix**: `/api/v1`

| File | Prefix | Endpoints | Purpose | Feature(s) |
|------|--------|-----------|---------|------------|
| `__init__.py` | — | 0 | Registers all routers on the main APIRouter | Core Platform |
| `auth_routes.py` | `/auth` | 8 | Login, signup, token refresh, password reset, invite accept | Authentication, RBAC |
| `account_routes.py` | `/accounts` | 7 | AWS account CRUD, role verification, discovery trigger | Accounts, Onboarding |
| `cluster_routes.py` | `/clusters` | 13 | Cluster CRUD, connect/disconnect, node list, scan, agent inject | Cluster Management, Agent |
| `dashboard_routes.py` | `/dashboard` | 5 | Overview KPIs, cost breakdown, savings projection, fleet, activity feed | Dashboard |
| `metrics_routes.py` | `/metrics` | 12 | Cost metrics, instance metrics, time-series, cluster utilization, nodegroups, waste breakdown | Metrics, Cost Optimization |
| `admin_routes.py` | `/admin` | 17 | Platform admin: orgs, clients, stats, health, billing, agent-fleet, config, impersonation | Admin, Platform |
| `organization_routes.py` | `/organization` | 8 | Org profile, members, invitations, member management | Organization, RBAC |
| `team_routes.py` | `/teams` | 12 | Team CRUD, member management, permissions, roles | Teams, RBAC |
| `role_routes.py` | `/roles` | 8 | Role CRUD, permissions list, role assignment, RBAC seed | RBAC |
| `permission_routes.py` | `/permissions` | 5 | Permission matrix, user permissions, grant/revoke | RBAC |
| `user_routes.py` | `/users` | 4 | User profile updates, preferences | User Management |
| `approval_routes.py` | `/approvals` | 11 | Approval requests, delegation, JIT access, approve/reject/revoke | Approvals, Governance |
| `governance_routes.py` | `/governance` | 3 | Governance policies list, update, auto-pilot run | Governance |
| `hibernation_routes.py` | `/hibernation` | 8 | Schedules CRUD, toggle, override, strategy comparison | Hibernation |
| `hygiene_routes.py` | `/hygiene` | 6 | Resource scan, hygiene summary, scan history, authorize resources | Resource Cleanup |
| `hygiene_policy_routes.py` | `/hygiene-policies` | 5 | Hygiene policy CRUD | Resource Cleanup |
| `optimization_routes.py` | `/optimization` | 3 | Right-sizing recommendations, batch apply, realized savings | Right-Sizing |
| `policy_routes.py` | `/policies` | 7 | Cluster policy CRUD, policy templates | Policies |
| `template_routes.py` | `/templates` | 7 | Node template CRUD, set default | Node Templates |
| `tag_management_routes.py` | `/tags/resources` | 3 | Get/set resource tags, bulk tag | Tag Management |
| `tag_policy_routes.py` | `/tags/policies` | 6 | Tag policy CRUD, attach to team | Tag Policies |
| `tag_template_routes.py` | `/tags/templates` | 5 | Tag template CRUD | Tag Templates |
| `auto_tag_routes.py` | `/tags/rules` | 8 | Auto-tag rule CRUD, enable/disable, run | Auto-Tagging |
| `smart_tag_routes.py` | `/tags/smart` | 1 | AI-powered tag suggestions | Smart Tags |
| `billing_routes.py` | `/billing` | 8 | Stripe portal, webhook, billing status, cost summary, daily costs, by-service, sync | Billing |
| `ri_routes.py` | `/ri` | 8 | RI utilization overview, recommendations, savings, purchase simulation | RI Optimization |
| `s3_routes.py` | `/s3` | 2 | S3 tiering overview, recommendations | S3 Optimization |
| `rds_routes.py` | `/rds` | 2 | RDS analysis overview, recommendations | RDS Optimization |
| `transfer_routes.py` | `/transfer` | 2 | Data transfer overview, analyze | Data Transfer |
| `pod_metrics_routes.py` | `/pod-metrics` | 4 | Pod metrics batch upload, list, cleanup, right-sizing | Pod Metrics |
| `settings_routes.py` | `/settings` | 5 | Platform settings get/update, notification preferences | Settings |
| `audit_routes.py` | `/audit` | 3 | Audit log list, resource history, export | Audit |
| `onboarding_routes.py` | `/onboarding` | 7 | Onboarding steps, status, AWS account creation flow | Onboarding |
| `agent_routes.py` | `/agents` | 3 | Agent heartbeat, WebSocket registration, status | Agent |
| `installer_routes.py` | `/installer` | 2 | Linux/macOS agent install scripts | Agent, Installer |
| `lab_routes.py` | `/lab` | 8 | Experiment lab CRUD, run, results, compare | Experiment Lab |
| `health_routes.py` | `/health` | 1 | System health check | Core Platform |
| `atharvaai_routes.py` | `/atharvaai` | 5 | Pool rankings, rebalancing timeline, interruption heatmap, auto-rebalance audit | AtharvaAI |

---

## 3. Backend — Services

| File | Purpose | Feature(s) |
|------|---------|------------|
| `__init__.py` | Package init | — |
| `auth_service.py` | Auth logic: JWT, login, signup, password hashing | Authentication |
| `account_service.py` | AWS account management, STS role verification, discovery | Accounts |
| `cluster_service.py` | Cluster CRUD, K8s connection, node discovery | Cluster Management |
| `admin_service.py` | Platform admin ops: org/user management, stats, health | Admin |
| `organization_service.py` | Org CRUD, member invitations, team assignment | Organization |
| `team_service.py` | Team CRUD, member handling | Teams |
| `role_service.py` | Role/permission CRUD, RBAC seed | RBAC |
| `permission_service.py` | Permission matrix, grant/revoke | RBAC |
| `approval_service.py` | Approval workflow, JIT access, delegation | Approvals, Governance |
| `governance_service.py` | Governance policy engine, auto-pilot | Governance |
| `hibernation_service.py` | Schedule management, strategy execution, cost calc | Hibernation |
| `hygiene_service.py` | AWS resource scanner (14 scan methods), classification | Resource Cleanup |
| `hygiene_service_additions.py` | Extended hygiene scan helpers | Resource Cleanup |
| `metrics_service.py` | Dashboard KPIs, cost/instance metrics, time-series | Metrics |
| `policy_service.py` | Cluster policy engine | Policies |
| `template_service.py` | Node template management | Node Templates |
| `tag_management_service.py` | AWS resource tag get/set/bulk operations | Tag Management |
| `tag_policy_service.py` | Tag policy enforcement, compliance check | Tag Policies |
| `auto_tag_service.py` | Auto-tag rule execution | Auto-Tagging |
| `smart_tag_service.py` | AI tag suggestions via OpenAI/LLM | Smart Tags |
| `tag_suggestion_service.py` | Further tag suggestion helpers | Smart Tags |
| `onboarding_service.py` | Onboarding step tracking, CloudFormation | Onboarding |
| `settings_service.py` | Platform settings CRUD | Settings |
| `audit_service.py` | Audit log creation and queries | Audit |
| `agent_injector.py` | K8s agent Helm install/upgrade | Agent |
| `lab_service.py` | Experiment creation, execution, comparison | Experiment Lab |
| `rightsizing_service.py` | EC2 right-sizing recommendations | Right-Sizing |
| `ri_analysis_service.py` | Reserved Instance utilization analysis | RI Optimization |
| `s3_tiering_service.py` | S3 intelligent tiering audit | S3 Optimization |
| `rds_analysis_service.py` | RDS Multi-AZ, idle instance analysis | RDS Optimization |
| `transfer_service.py` | Data transfer cost analysis | Data Transfer |
| `savings_plan_service.py` | Savings Plan utilization tracking | Savings Plans |
| `resource_cost_service.py` | Per-resource cost estimation via CUR/CE | Cost Optimization |
| `resource_pricing_service.py` | On-demand pricing lookups | Cost Optimization |
| `pool_ranking_service.py` | Spot pool scoring and rankings | AtharvaAI |
| `karpenter_service.py` | Karpenter provisioner integration | Cluster Management |
| `ml_feature_service.py` | ML feature extraction for model input | AtharvaAI, ML |

---

## 4. Backend — Models

| File | Purpose | Feature(s) |
|------|---------|------------|
| `__init__.py` | SQLAlchemy model registry, imports all models | Core Platform |
| `base.py` | Declarative base, common mixins | Core Platform |
| `user.py` | User model (auth, preferences, roles) | Authentication, RBAC |
| `organization.py` | Organization model | Organization |
| `account.py` | AWS Account model | Accounts |
| `cluster.py` | Cluster model (EKS/K8s) | Cluster Management |
| `cluster_metric.py` | Cluster time-series metrics | Metrics |
| `cluster_policy.py` | Cluster-attached policies | Policies |
| `instance.py` | EC2 instance model | Cluster Management |
| `billing.py` | Billing/subscription records | Billing |
| `approval.py` | Approval workflow records | Approvals |
| `legacy_approval.py` | **LEGACY** — Old approval model pre-refactor | Approvals |
| `authorized_resource.py` | Resource authorization whitelist | Resource Cleanup |
| `hibernation_schedule.py` | Hibernate schedule model | Hibernation |
| `hygiene_policy.py` | Hygiene policy model | Resource Cleanup |
| `tag_policy.py` | Tag policy model | Tag Policies |
| `tag_template.py` | Tag template model | Tag Templates |
| `auto_tag_rule.py` | Auto-tag rule model | Auto-Tagging |
| `node_template.py` | Node template model | Node Templates |
| `optimization_job.py` | Right-sizing job tracker | Right-Sizing |
| `lab_experiment.py` | Experiment Lab model + ExperimentStatus enum | Experiment Lab |
| `ml_model.py` | ML model metadata storage | AtharvaAI |
| `pricing.py` | EC2 pricing cache model | Cost Optimization |
| `spot_price_history.py` | Spot price time-series | AtharvaAI |
| `ri_utilization.py` | RI utilization records | RI Optimization |
| `rds_analysis.py` | RDS analysis records | RDS Optimization |
| `s3_analysis.py` | S3 tiering analysis records | S3 Optimization |
| `transfer_analysis.py` | Data transfer analysis records | Data Transfer |
| `savings_plan_utilization.py` | Savings Plan utilization | Savings Plans |
| `pod_metric.py` | Pod-level metric records | Pod Metrics |
| `rebalancing_action.py` | AtharvaAI rebalancing action log | AtharvaAI |
| `termination_event.py` | Spot interruption event log | AtharvaAI |
| `agent_action.py` | Agent action log | Agent |
| `api_key.py` | API key management | Authentication |
| `audit_log.py` | Audit log records | Audit |
| `invitation.py` | User invitation records | Organization |
| `permission.py` | Permission definitions | RBAC |
| `role.py` | Role definitions | RBAC |
| `team.py` | Team model | Teams |
| `onboarding.py` | Onboarding progress tracker | Onboarding |
| `platform_settings.py` | Platform settings key-value | Settings |
| `system_config.py` | System configuration store | Core Platform |

---

## 5. Backend — Schemas

| File | Purpose | Feature(s) |
|------|---------|------------|
| `__init__.py` | Package init | — |
| `auth_schemas.py` | Login/signup request/response models | Authentication |
| `account_schemas.py` | Account request/response models | Accounts |
| `cluster_schemas.py` | Cluster/node request/response models | Cluster Management |
| `dashboard_schemas.py` | Dashboard KPI response models | Dashboard |
| `metric_schemas.py` | Metric response models | Metrics |
| `admin_schemas.py` | Admin panel schemas | Admin |
| `organization_schemas.py` | Org management schemas | Organization |
| `team_schemas.py` | Team schemas | Teams |
| `role_schemas.py` | Role/permission schemas | RBAC |
| `approval_schemas.py` | Approval workflow schemas | Approvals |
| `hibernation_schemas.py` | Hibernation schedule schemas | Hibernation |
| `hygiene_schemas.py` | Resource hygiene schemas (ResourceType, HygieneStatus, ResourceItem) | Resource Cleanup |
| `hygiene_policy_schemas.py` | Hygiene policy request/response | Resource Cleanup |
| `policy_schemas.py` | Cluster policy schemas | Policies |
| `template_schemas.py` | Node template schemas | Node Templates |
| `tag_management_schemas.py` | Tag management schemas | Tag Management |
| `tag_policy_schemas.py` | Tag policy schemas | Tag Policies |
| `tag_template_schemas.py` | Tag template schemas | Tag Templates |
| `auto_tag_schemas.py` | Auto-tag rule schemas | Auto-Tagging |
| `lab_schemas.py` | Experiment lab schemas | Experiment Lab |
| `settings_schemas.py` | Settings schemas | Settings |
| `audit_schemas.py` | Audit log schemas | Audit |
| `pod_metric_schemas.py` | Pod metric schemas | Pod Metrics |

---

## 6. Backend — Core

| File | Purpose | Feature(s) |
|------|---------|------------|
| `__init__.py` | Package init | — |
| `config.py` | Pydantic Settings: DB URL, JWT secret, AWS creds, CORS | Core Platform |
| `dependencies.py` | FastAPI dependency injection (DB session, current user) | Core Platform |
| `exceptions.py` | Custom HTTP exceptions | Core Platform |
| `logger.py` | Structured logging config | Core Platform |
| `validators.py` | Input validation utilities | Core Platform |
| `crypto.py` | Encryption/decryption for secrets | Core Platform |
| `redis_client.py` | Redis connection factory | Core Platform |
| `sse_manager.py` | Server-Sent Events manager for real-time UI updates | Core Platform |
| `api_gateway.py` | Central API gateway for external service calls | Core Platform |
| `action_executor.py` | Executes approved actions (terminate, resize, etc.) | Optimization, Governance |
| `decision_engine.py` | ML-based decision engine for spot optimization | AtharvaAI |
| `feature_registry.py` | Feature flag registry | Core Platform |
| `health_service.py` | System health check logic | Core Platform |

---

## 7. Backend — Resource_rules

| File | Purpose | Feature(s) |
|------|---------|------------|
| `__init__.py` | `RuleVerdict` enum, shared constants (`SAFE_THRESHOLD_DAYS`, `EXEMPT_KEYWORDS`), helper functions | Resource Cleanup |
| `compute_rules.py` | Rules: EC2 stopped/running, RI, EKS, ECS, ASG | Resource Cleanup |
| `storage_rules.py` | Rules: EBS volumes, snapshots, S3, S3 lifecycle, EFS | Resource Cleanup |
| `database_rules.py` | Rules: RDS idle/legacy, Multi-AZ, DynamoDB, ElastiCache | Resource Cleanup |
| `network_rules.py` | Rules: ELB, ENI, EIP, NAT Gateway, VPC, VPC Endpoints, TGW | Resource Cleanup |
| `identity_rules.py` | Rules: IAM Users (dormant), IAM Keys (stale) | Resource Cleanup |
| `security_rules.py` | Rules: KMS Keys, Secrets Manager, Security Hub, CloudTrail, GuardDuty | Resource Cleanup |
| `management_rules.py` | Rules: CloudWatch Logs/Alarms, Lambda, EventBridge, Config, SSM | Resource Cleanup |

---

## 8. Backend — Hibernation_strategy

**Modular hibernation strategy implementations with editable configuration parameters**

| File | Purpose | Lines | Editable Config | Feature(s) |
|------|---------|-------|-----------------|------------|
| `__init__.py` | Exports NamespaceSleepStrategy, NuclearStrategy, SnapshotRestoreStrategy | 30 | — | Hibernation |
| `namespace_sleep.py` | **NamespaceSleepStrategy**: Scale K8s workloads to 0, let autoscaler drain nodes. Config: SYSTEM_NAMESPACES, GRACE_PERIOD_SECONDS, SLEEP_ORDER, WAKE_ORDER (8 params) | 600+ | ✅ Yes | Hibernation |
| `nuclear.py` | **NuclearStrategy**: Scale ASGs to 0 directly (hard shutdown). Config: MIN_DESIRED_CAPACITY, SCALE_DOWN_TIMEOUT, TERMINATION_POLICIES (7 params) | 450+ | ✅ Yes | Hibernation |
| `snapshot_restore.py` | **SnapshotRestoreStrategy**: Snapshot EBS volumes before Nuclear sleep. Config: SNAPSHOT_TIMEOUT, KEEP_SNAPSHOTS_DAYS, PARALLEL_SNAPSHOTS (8 params) | 550+ | ✅ Yes | Hibernation |

---

## 9. Backend — Workers

| File | Purpose | Feature(s) |
|------|---------|------------|
| `__init__.py` | Package init | — |
| `app.py` | Celery app initialization and beat schedule | Core Platform |
| **tasks/** | | |
| `__init__.py` | Task registration | — |
| `discovery.py` | Periodic cluster/account discovery | Cluster Management, Accounts |
| `optimization.py` | Periodic right-sizing analysis | Right-Sizing |
| `cost_calculator.py` | Periodic cost aggregation | Cost Optimization |
| `cost_explorer.py` | AWS Cost Explorer sync | Cost Optimization, Billing |
| `savings_calculator.py` | Realized savings calculation | Cost Optimization |
| `pricing_task.py` | EC2 pricing data refresh | Cost Optimization |
| `resource_pricing_worker.py` | Per-resource pricing lookup | Cost Optimization |
| `hibernation_worker.py` | Cron-based hibernate/wake execution (delegates to modular Hibernation_strategy classes) | Hibernation |
| `agent_tasks.py` | Agent status polling | Agent |
| `health.py` | Periodic health checks | Core Platform |
| `event_processor.py` | Spot interruption event processing | AtharvaAI |
| `termination_monitor.py` | Monitor instance terminations | AtharvaAI |
| `auto_rebalancer.py` | Automatic workload rebalancing | AtharvaAI |
| `atharvaai_worker.py` | AtharvaAI background analysis | AtharvaAI |
| `approval_cleanup.py` | Expire old approvals | Approvals, Governance |
| `pod_metrics_cleanup.py` | Purge old pod metrics | Pod Metrics |
| `report_worker.py` | Scheduled report generation | Reporting |

---

## 10. Backend — Calculations

| File | Purpose | Feature(s) |
|------|---------|------------|
| `__init__.py` | Package init | — |
| `cost_calculations.py` | Cost aggregation formulas | Cost Optimization |
| `metrics_calculations.py` | Metric aggregation formulas | Metrics |
| `savings_calculations.py` | Savings projection formulas | Cost Optimization |

---

## 11. Backend — Modules

| File | Purpose | Feature(s) |
|------|---------|------------|
| `__init__.py` | Package init | — |
| `bin_packer.py` | Bin-packing algorithm for node consolidation | Right-Sizing |
| `ml_model_server.py` | ONNX model inference server | AtharvaAI |
| `model_validator.py` | ML model validation checks | AtharvaAI |
| `rightsizer.py` | Right-sizing recommendation engine | Right-Sizing |
| `risk_tracker.py` | Spot interruption risk scoring | AtharvaAI |
| `spot_optimizer.py` | Spot instance optimization logic | AtharvaAI |

---

## 12. Backend — Scrapers

| File | Purpose | Feature(s) |
|------|---------|------------|
| `__init__.py` | Package init | — |
| `pricing_collector.py` | Scrapes AWS EC2 pricing JSON | Cost Optimization |
| `spot_advisor_scraper.py` | Scrapes AWS Spot Advisor data | AtharvaAI |

---

## 13. Backend — Routers (Legacy)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `actions.py` | **LEGACY** — Old action execution endpoints, replaced by `api/optimization_routes.py` | Right-Sizing |
| `agents.py` | **LEGACY** — Old agent endpoints, replaced by `api/agent_routes.py` | Agent |
| `metrics.py` | **LEGACY** — Old metrics endpoints, replaced by `api/metrics_routes.py` | Metrics |

---

## 14. Backend — Migrations

| File | Purpose | Feature(s) |
|------|---------|------------|
| `004_add_user_status.py` | Add `status` column to users table | Authentication |
| `005_add_team_model.py` | Create teams table | Teams |
| `debug_columns.py` | Debug script to inspect DB columns | DevOps |
| `debug_db.py` | Debug script to inspect DB state | DevOps |
| `versions/007_cleanup_policies.py` | Create cleanup/hygiene policy tables | Resource Cleanup |
| `versions/008_core_modules.py` | Create core module tables | Core Platform |
| `versions/009_dynamic_auto_tags.py` | Create auto-tag rules tables | Auto-Tagging |
| `versions/010_tag_template_resource_scope.py` | Add resource scope to tag templates | Tag Templates |
| `versions/011_add_cluster_costs.py` | Add cost columns to clusters | Cluster Management |
| `versions/20260216_atharvaai_tables.py` | Create AtharvaAI tables (rebalancing, pool rankings) | AtharvaAI |

---

## 15. Backend — Scripts

| File | Purpose | Feature(s) |
|------|---------|------------|
| `get_admin_token.py` | Generate admin JWT for testing | DevOps |
| `seed_permissions.py` | Seed platform permissions | RBAC |
| `seed_rbac.py` | Seed RBAC roles and permissions | RBAC |

---

## 16. Agent

| File | Purpose | Feature(s) |
|------|---------|------------|
| `main.py` | Agent entry point, starts all threads | Agent |
| `config.py` | Agent configuration from env vars | Agent |
| `collector.py` | Collects node/instance metrics from K8s | Agent, Metrics |
| `pod_metrics_collector.py` | Collects pod-level CPU/memory metrics | Agent, Pod Metrics |
| `actuator.py` | Executes approved actions on the cluster | Agent, Optimization |
| `heartbeat.py` | Periodic heartbeat to backend | Agent |
| `poller.py` | Polls backend for pending actions | Agent |
| `websocket_client.py` | WebSocket real-time connection to backend | Agent |
| `Dockerfile` | Agent Docker image | DevOps |
| `build-and-push.sh` | Build and push agent image | DevOps |
| `requirements.txt` | Agent Python dependencies | Agent |

---

## 17. Frontend — Pages

| File | Purpose | Feature(s) |
|------|---------|------------|
| `App.js` | Root component, routing, auth guard | Core Platform |
| `index.js` | React entry point | Core Platform |
| `index.css` | Global styles | Core Platform |
| `pages/AccountAnalytics.jsx` | AWS account analytics page | Accounts, Metrics |
| `pages/Approvals.jsx` | Approvals management page | Approvals |
| `pages/AtharvaAiPage.jsx` | AtharvaAI visualization page | AtharvaAI |
| `pages/HibernationPage.jsx` | Hibernation management page | Hibernation |
| `pages/Onboarding.jsx` | Onboarding flow page | Onboarding |
| `pages/Roles.jsx` | Roles management page | RBAC |
| `pages/TeamDetails.jsx` | Individual team details page | Teams |
| `pages/Teams.jsx` | Teams list page | Teams |

---

## 18. Frontend — Components

### Admin (`components/admin/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `AdminDashboard.jsx` | Admin panel layout with tabs | Admin |
| `AdminOverview.jsx` | Platform overview stats | Admin |
| `AdminOrganizations.jsx` | Organization management table | Admin |
| `AdminClients.jsx` | Client/user management table | Admin |
| `AdminHealth.jsx` | System health status cards | Admin |
| `AdminBilling.jsx` | Billing management panel | Admin, Billing |
| `AdminConfig.jsx` | System config editor | Admin |
| `AdminAgentFleet.jsx` | Agent fleet status view | Admin, Agent |
| `AdminExperiments.jsx` | Experiment overview for admin | Admin, Experiment Lab |
| `AdminImpersonation.jsx` | Org impersonation toggle | Admin |
| `AdminTenantDrilldown.jsx` | Tenant deep-dive analytics | Admin |
| `PlatformSettings.jsx` | Platform settings panel | Admin, Settings |

### Auth (`components/auth/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `Login.jsx` | Login page | Authentication |
| `Signup.jsx` | Signup page | Authentication |
| `InviteAcceptance.jsx` | Invitation acceptance flow | Authentication, Organization |

### Dashboard (`components/dashboard/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `Dashboard.jsx` | Main dashboard with widget grid | Dashboard |
| `roleDefaults.js` | Default widget layout per role | Dashboard, RBAC |
| `widgetRegistry.js` | Widget type registry | Dashboard |
| `widgets/ActivityFeed.jsx` | Activity feed widget | Dashboard |
| `widgets/AgentStatusWidget.jsx` | Agent status widget | Dashboard, Agent |
| `widgets/ClusterHealthCard.jsx` | Cluster health widget | Dashboard, Cluster Management |
| `widgets/CostKPICard.jsx` | Cost KPI widget | Dashboard, Cost Optimization |
| `widgets/FleetComposition.jsx` | Fleet composition chart | Dashboard |
| `widgets/PendingApprovalsCard.jsx` | Pending approvals widget | Dashboard, Approvals |
| `widgets/PlatformHealthCard.jsx` | Platform health widget | Dashboard, Admin |
| `widgets/SavingsChart.jsx` | Savings trend chart | Dashboard, Cost Optimization |
| `widgets/SavingsKPICard.jsx` | Savings KPI widget | Dashboard, Cost Optimization |
| `widgets/SpendForecastWidget.jsx` | Spending forecast widget | Dashboard, Cost Optimization |
| `widgets/TenantListCard.jsx` | Tenant list widget | Dashboard, Admin |
| `widgets/index.js` | Widget exports | Dashboard |

### Cleanup (`components/cleanup/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `CleanupDashboard.jsx` | Resource hygiene main dashboard | Resource Cleanup |
| `BulkTagWizard.jsx` | Wizard for bulk-tagging resources | Resource Cleanup, Tag Management |
| `layout/CleanupSidebar.jsx` | Cleanup sidebar with filters | Resource Cleanup |
| `layout/FilterPanel.jsx` | Filter panel for resource table | Resource Cleanup |
| `summary/HeroMetricsPanel.jsx` | Hero metrics: total waste, savings | Resource Cleanup |
| `summary/SavingsGauge.jsx` | Animated savings gauge chart | Resource Cleanup |
| `tables/ResourceTable.jsx` | Resource listing table with actions | Resource Cleanup |
| `wizards/RDSWizard.jsx` | RDS optimization wizard | RDS Optimization |
| `wizards/RIWizard.jsx` | RI optimization wizard | RI Optimization |
| `wizards/S3Wizard.jsx` | S3 tiering wizard | S3 Optimization |

### Clusters (`components/clusters/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `ClusterList.jsx` | Cluster listing with cards | Cluster Management |
| `ClusterDetails.jsx` | Cluster detail view | Cluster Management |
| `ClusterDeleteModal.jsx` | Cluster deletion confirmation | Cluster Management |
| `ClusterDisconnectModal.jsx` | Cluster disconnect confirmation | Cluster Management |
| `ClusterHealthTimeline.jsx` | Health event timeline | Cluster Management |
| `ClusterUtilizationSparkline.jsx` | Utilization sparkline chart | Cluster Management, Metrics |
| `NodeGroupBreakdown.jsx` | Node group details | Cluster Management |
| `NodeList.jsx` | Node listing table | Cluster Management |
| `PolicyGapAlert.jsx` | Policy compliance alerts | Cluster Management, Policies |
| `SpotRatioGauge.jsx` | Spot/On-demand ratio gauge | Cluster Management |

### Hibernation (`components/hibernation/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `HibernationScheduler.jsx` | Main schedule creation UI | Hibernation |
| `HibernationSchedule.jsx` | Schedule list/detail view | Hibernation |
| `HibernationScheduleV2.jsx` | V2 schedule with drag-and-drop | Hibernation |
| `HibernationGrid.jsx` | Weekly grid view | Hibernation |
| `HibernationHeader.jsx` | Hibernation page header | Hibernation |
| `HibernationTypeCard.jsx` | Strategy type selector card | Hibernation |
| `StrategySelector.jsx` | Strategy comparison selector | Hibernation |
| `ScheduleTemplates.jsx` | Preset schedule templates | Hibernation |
| `ClusterOverview.jsx` | Cluster-level hibernation overview | Hibernation |
| `CostAnalytics.jsx` | Hibernation cost savings analytics | Hibernation, Cost Optimization |
| `AdvancedConfiguration.jsx` | Advanced hibernation settings | Hibernation |
| `TimeBasedRules.jsx` | Time-based rule builder | Hibernation |
| `UnifiedScheduleGrid.jsx` | Unified multi-cluster grid | Hibernation |
| `MultiTimezone.jsx` | Multi-timezone support | Hibernation |
| `HistoryLog.jsx` | Hibernation action history | Hibernation |
| `ValidationPanel.jsx` | Schedule validation checks | Hibernation |

### AtharvaAI (`components/atharvaai/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `PoolRankings.jsx` | Spot pool rankings table | AtharvaAI |
| `PoolRankings.css` | Pool rankings styles | AtharvaAI |
| `RebalancingTimeline.jsx` | Rebalancing event timeline | AtharvaAI |
| `InterruptionHeatmap.jsx` | Spot interruption heatmap | AtharvaAI |
| `AutoRebalanceAuditCard.jsx` | Auto-rebalance audit log card | AtharvaAI |

### Right-Sizing (`components/right-sizing/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `RightSizing.jsx` | Main right-sizing page | Right-Sizing |
| `BatchApplyModal.jsx` | Batch-apply recommendations modal | Right-Sizing |
| `ImpactSummary.jsx` | Impact summary of recommendations | Right-Sizing |
| `InstanceUsageDetailPanel.jsx` | Instance usage detail | Right-Sizing |
| `RecommendationAgeIndicator.jsx` | Recommendation age badge | Right-Sizing |
| `SavingsTracker.jsx` | Savings tracker post-apply | Right-Sizing |

### Cost Optimization Modules

| File | Purpose | Feature(s) |
|------|---------|------------|
| `ri/RIAnalysis.jsx` | RI utilization analysis page | RI Optimization |
| `ri/RIHealthCard.jsx` | RI health summary card | RI Optimization |
| `rds/RDSAnalysis.jsx` | RDS analysis page | RDS Optimization |
| `rds/RDSHealthCard.jsx` | RDS health summary card | RDS Optimization |
| `s3/S3Analysis.jsx` | S3 tiering analysis page | S3 Optimization |
| `s3/S3HealthCard.jsx` | S3 health summary card | S3 Optimization |
| `transfer/TransferAnalysis.jsx` | Data transfer analysis page | Data Transfer |
| `transfer/TransferHealthCard.jsx` | Transfer health card | Data Transfer |

### Governance/Approvals (`components/governance/`, `components/approvals/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `governance/PermissionGate.jsx` | Permission-gated component wrapper | RBAC |
| `governance/ProtectedButton.jsx` | Button requiring specific permission | RBAC |
| `governance/JITRequestModal.jsx` | Just-In-Time access request modal | Approvals, Governance |
| `governance/ActiveJITBanner.jsx` | Active JIT session banner | Approvals, Governance |
| `approvals/TicketRequestModal.jsx` | Approval ticket request modal | Approvals |
| `approvals/AccessRequestModal.jsx` | Access request modal | Approvals |
| `approvals/ActiveWindowBanner.jsx` | Active approval window banner | Approvals |

### Settings (`components/settings/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `Settings.jsx` | Settings page layout | Settings |
| `AccountSettings.jsx` | Account-level settings | Settings, Accounts |
| `CloudIntegrations.jsx` | AWS integration management | Settings, Accounts |
| `GovernanceManager.jsx` | Governance settings manager | Governance |
| `GovernanceSettings.jsx` | Governance settings form | Governance |
| `TeamManagement.jsx` | Team management from settings | Teams |
| `TeamGovernance.jsx` | Team governance settings | Teams, Governance |
| `MemberPermissionsModal.jsx` | Member permission editor modal | RBAC |
| `TagPoliciesList.jsx` | Tag policies listing | Tag Policies |
| `TagPoliciesManager.jsx` | Tag policies CRUD manager | Tag Policies |
| `TagTemplateManager.jsx` | Tag template CRUD manager | Tag Templates |

### Policies (`components/policies/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `PolicyConfig.jsx` | Cluster policy configuration | Policies |
| `CleanupPolicies.jsx` | Cleanup policy management | Resource Cleanup |
| `PermissionMatrix.jsx` | Permission matrix viewer | RBAC |
| `TagTemplateManager.jsx` | Tag template manager (duplicate) | Tag Templates |

### Other Components

| File | Purpose | Feature(s) |
|------|---------|------------|
| `layout/MainLayout.jsx` | App chrome: sidebar, topbar, content area | Core Platform |
| `audit/AuditLog.jsx` | Audit log viewer | Audit |
| `lab/ExperimentLab.jsx` | Experiment Lab UI | Experiment Lab |
| `templates/TemplateBuilder.jsx` | Node template builder | Node Templates |
| `templates/TemplateList.jsx` | Node template listing | Node Templates |
| `teams/TeamsTab.jsx` | Teams tab component | Teams |
| `teams/MembersTab.jsx` | Members tab component | Teams |
| `teams/RolesPoliciesTopTab.jsx` | Roles & policies tab | Teams, RBAC |
| `onboarding/WelcomeStep.jsx` | Onboarding welcome step | Onboarding |
| `onboarding/ConnectStep.jsx` | Onboarding AWS connect step | Onboarding |
| `onboarding/VerifyStep.jsx` | Onboarding verification step | Onboarding |
| `onboarding/SuccessStep.jsx` | Onboarding success step | Onboarding |

### Shared (`components/shared/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `index.js` | Shared component exports | Core Platform |
| `Badge.jsx` | Reusable badge component | Core Platform |
| `Button.jsx` | Reusable button component | Core Platform |
| `Card.jsx` | Reusable card component | Core Platform |
| `Dropdown.jsx` | Reusable dropdown component | Core Platform |
| `EmptyState.jsx` | Empty state placeholder | Core Platform |
| `GaugeChart.jsx` | Reusable gauge chart | Core Platform |
| `Input.jsx` | Reusable input component | Core Platform |
| `RiskBadge.jsx` | Risk-level badge | Core Platform |
| `StatsCard.jsx` | Stats card component | Core Platform |
| `Switch.jsx` | Toggle switch component | Core Platform |

---

## 19. Frontend — Services / Hooks / Store / Utils

### Services

| File | Purpose | Feature(s) |
|------|---------|------------|
| `services/api.js` | Axios API client with all endpoint functions | Core Platform |

### Hooks

| File | Purpose | Feature(s) |
|------|---------|------------|
| `hooks/useAuth.js` | Auth state hook (login, logout, token) | Authentication |
| `hooks/useDashboard.js` | Dashboard data fetching hook | Dashboard |
| `hooks/usePermission.js` | Permission checking hook | RBAC |

### Store (Zustand)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `store/useStore.js` | Main app state store | Core Platform |
| `store/useHibernationStore.js` | Hibernation state store | Hibernation |
| `store/useAtharvaStore.js` | AtharvaAI state store | AtharvaAI |

### Utils

| File | Purpose | Feature(s) |
|------|---------|------------|
| `utils/formatters.js` | Number, date, currency formatting helpers | Core Platform |

---

## 20. Scripts (Root-Level)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `scripts/seed_admin.py` | Seed admin user into DB | DevOps |
| `scripts/seed_demo_data.py` | Seed demo org, users, clusters, accounts | DevOps |
| `scripts/seed_test_data.py` | Seed test data for development | DevOps |
| `scripts/fix_demo_user.py` | Fix demo user credentials | DevOps |
| `scripts/debug_users.py` | Debug user records | DevOps |
| `scripts/migrate_to_organizations.py` | Migrate legacy users to org model | DevOps |
| `scripts/setup_platform_creds.py` | Setup platform AWS credentials | DevOps |
| `scripts/update_and_seed.py` | Update DB schema + seed data | DevOps |
| `scripts/publish_agent.sh` | Publish agent Docker image | DevOps |
| `scripts/publish_helm_chart.sh` | Publish Helm chart to registry | DevOps |
| `scripts/publish_to_dockerhub.sh` | Push images to DockerHub | DevOps |
| `scripts/deployment/deploy.sh` | Production deployment script | DevOps |
| `scripts/deployment/setup.sh` | Initial server setup | DevOps |
| `scripts/aws/detach_volume.py` | Detach EBS volume via AWS API | AWS Operations |
| `scripts/aws/launch_spot.py` | Launch spot instance | AWS Operations |
| `scripts/aws/terminate_instance.py` | Terminate instance | AWS Operations |
| `scripts/aws/update_asg.py` | Update ASG capacity | AWS Operations |

---

## 21. ML Model

### `ml_model/decision_engine/`

| File | Purpose | Feature(s) |
|------|---------|------------|
| `webscraper/spot_advisor_enhanced.py` | Enhanced Spot Advisor data scraper | AtharvaAI |

### `ml_model/model/spot_optimizer_v1/`

| File | Purpose | Feature(s) |
|------|---------|------------|
| `src/model.py` | LightGBM model for spot interruption prediction | AtharvaAI |
| `src/data.py` | Data pipeline (pandas-based) | AtharvaAI |
| `src/data_polars.py` | Data pipeline (polars-based, faster) | AtharvaAI |
| `src/backtest.py` | Backtesting engine | AtharvaAI |
| `src/visualize.py` | Training visualization dashboard | AtharvaAI |
| `src/logger.py` | ML training logger | AtharvaAI |
| `scripts/train.py` | Local training script | AtharvaAI |
| `scripts/backtest.py` | Backtesting runner | AtharvaAI |
| `scripts/optimize_hyperparameters.py` | Hyperparameter optimization | AtharvaAI |
| `scripts/verify_onnx_local.py` | ONNX model verification | AtharvaAI |
| `tests/test_decision_engine.py` | Decision engine unit tests | AtharvaAI |
| `tests/test_threshold_optimization.py` | Threshold optimization tests | AtharvaAI |

### SageMaker Migration (`sagemaker_migration/`)

| File | Purpose | Feature(s) |
|------|---------|------------|
| `scripts/train_wrapper.py` | SageMaker training wrapper | AtharvaAI, ML Ops |
| `scripts/submit_final_training.py` | Submit SageMaker training job | AtharvaAI, ML Ops |
| `scripts/hpo_submitter.py` | Submit HPO job to SageMaker | AtharvaAI, ML Ops |
| `scripts/submit_preprocessing_job.py` | Submit preprocessing job | AtharvaAI, ML Ops |
| `scripts/preprocess_features_sagemaker.py` | Feature preprocessing for SageMaker | AtharvaAI, ML Ops |
| `scripts/acid_test_entrypoint.py` | Container environment test | AtharvaAI, ML Ops |
| `scripts/analyze_container_env.py` | Container environment analyzer | AtharvaAI, ML Ops |
| `scripts/submit_env_check.py` | Environment check submission | AtharvaAI, ML Ops |
| `scripts/submit_spot_eval.py` | Spot evaluation submission | AtharvaAI, ML Ops |
| `scripts/test_training_code.py` | Training code tests | AtharvaAI, ML Ops |
| `scripts/test_wrapper_integration.py` | Wrapper integration tests | AtharvaAI, ML Ops |
| `spot_processing/preprocess_spot_wrapper.py` | Spot data preprocessing wrapper | AtharvaAI, ML Ops |
| `spot_processing/submit_spot_processing.py` | Submit spot data processing | AtharvaAI, ML Ops |

---

## 22. Documents

| File | Purpose |
|------|---------|
| `documents/README.md` | Documentation index |
| `documents/MASTER_SUMMARY.md` | Master project summary |
| `documents/all-components.md` | UI component catalog with dependencies |
| `documents/backend-feature.md` | Backend feature documentation |
| `documents/schema_info.md` | Database schema documentation |
| `documents/all-files.md` | **This file** — complete file catalog |

---

## 23. Duplicate / Unused / Legacy Files

| File | Status | Reason |
|------|--------|--------|
| `backend/routers/actions.py` | **LEGACY** | Superseded by `backend/api/optimization_routes.py`. Old-style router before API restructuring. |
| `backend/routers/agents.py` | **LEGACY** | Superseded by `backend/api/agent_routes.py`. Old router preserved for backward compat. |
| `backend/routers/metrics.py` | **LEGACY** | Superseded by `backend/api/metrics_routes.py`. Old router before modularization. |
| `backend/models/legacy_approval.py` | **LEGACY** | Old approval model before approval/ticket refactor. Kept for migration reference. |
| `backend/migrations/debug_columns.py` | **UNUSED (Debug)** | One-time debug script to inspect DB columns. Not needed in production. |
| `backend/migrations/debug_db.py` | **UNUSED (Debug)** | One-time debug script to inspect DB state. Not needed in production. |
| `backend/test_scanner_fix.py` | **UNUSED (Debug)** | Temporary test script for scanner bug fix. Should be removed. |
| `test_scanner.py` | **UNUSED (Debug)** | Root-level test script for cleanup scanner. Should be moved to tests/. |
| `test_real_apis.sh` | **UNUSED (Debug)** | Shell script for live API testing. Not part of CI, should be moved to scripts/. |
| `scripts/debug_users.py` | **UNUSED (Debug)** | One-time debug script for user records. Not needed in production. |
| `scripts/fix_demo_user.py` | **UNUSED (Debug)** | One-time fix script for demo user. Not reusable. |
| `backend/services/hygiene_service_additions.py` | **PARTIAL DUPLICATE** | Extended helper methods for hygiene service. Could be merged into `hygiene_service.py` or `Resource_rules/`. |
| `components/policies/TagTemplateManager.jsx` | **DUPLICATE** | Identical purpose to `components/settings/TagTemplateManager.jsx`. Two copies of same component. |
| `components/hibernation/HibernationSchedule.jsx` | **POTENTIAL DUPLICATE** | Overlaps with `HibernationScheduleV2.jsx` — V1 may be legacy. |
| `ml_model/model/spot_optimizer_v1/src/data.py` | **PARTIAL DUPLICATE** | Pandas-based data pipeline, superseded by `data_polars.py` (faster). Kept for fallback. |
| `REBUILD_RESTART_SUMMARY.md` | **UNUSED** | One-time build summary document. Not maintained. |

---

> **Total files catalogued:** ~220+ (excluding `node_modules`, `__pycache__`, `.git`, training result artifacts)
