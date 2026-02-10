# Backend Catalog — Complete File Registry

> **Last Updated**: 2026-02-10
> **Total Files**: 169 across 9 subdirectories
> **Naming**: Reflects Global Naming Synchronization (tickets->approvals, cleanup->hygiene)
> **Complements**: SYSTEM_ARCHITECTURE.md (logic & data flow), API_REFERENCE.md (endpoint details)

---

## 1. API Routes (`backend/api/`) — 36 files

Route handlers organized by domain. Each file defines a FastAPI `APIRouter`.

| File | Prefix | Tags | Purpose | Key Endpoints | Auth |
|:-----|:-------|:-----|:--------|:--------------|:-----|
| `auth_routes.py` | `/auth` | auth | Login, signup, refresh, password change | POST login/signup/refresh, GET me, PATCH password | Mixed |
| `account_routes.py` | `/accounts` | accounts | AWS account CRUD, STS validation | GET list, POST link/validate/disconnect | OA+ |
| `admin_routes.py` | `/admin` | admin | Platform admin: clients, health, identity | GET dashboard/clients/health, POST toggle/connect | SA |
| `agent_routes.py` | `/agents` | agents | Agent heartbeat + metrics ingestion | POST heartbeat, POST batch-metrics | API Key |
| `approval_routes.py` | `/approvals` | approvals | JIT approval lifecycle (create, approve, reject, revoke, delegate) | POST create/jit-request, POST approve/reject/revoke/delegate | Yes |
| `audit_routes.py` | `/audit` | audit | Audit log queries + export | GET logs, GET export | Yes |
| `auto_tag_routes.py` | `/tags/rules` | auto-tags | Auto-tag rule CRUD + preview + execute | POST create/preview/test/execute, GET list/variables | OA+ |
| `billing_routes.py` | `/billing` | billing | Stripe portal + webhook | POST create-portal-session, POST webhook | OA+ |
| `cluster_routes.py` | `/clusters` | clusters | Cluster CRUD, agent install, disconnect | GET list/detail, POST auto-install/verify/disconnect | Yes |
| `governance_routes.py` | `/governance` | governance | Org governance rules + autopilot | GET/PATCH rules, POST run-autopilot | OA+ |
| `health_routes.py` | `/health` | health | Basic + detailed health checks | GET /, GET /detailed | No/SA |
| `hibernation_routes.py` | `/hibernation` | hibernation | Schedule CRUD for cluster sleep/wake | GET list, POST create, PUT update, DELETE | JIT |
| `hygiene_routes.py` | `/hygiene` | hygiene | Resource scan + action execution | GET scan, POST action/authorize/unauthorize | JIT |
| `hygiene_policy_routes.py` | `/hygiene-policies` | hygiene-policies | Automated cleanup rule CRUD | GET list, POST create, PUT update, DELETE | OA+ |
| `installer_routes.py` | `/installer` | installer | Public agent installer endpoint | GET /{cluster_id} | No |
| `lab_routes.py` | `/lab` | lab | ML experiments + model registry + live switch | GET experiments/models, POST create/graduate/live-switch | SA |
| `metrics_routes.py` | `/metrics` | metrics | Dashboard KPIs, cost series, team/account stats | GET dashboard/cost/instances/time-series/teams/accounts | Yes |
| `onboarding_routes.py` | `/onboarding` | onboarding | AWS connection wizard flow | POST aws-link/verify/reset, GET template | Yes |
| `optimization_routes.py` | `/optimization` | optimization | Rightsizing recommendations | GET rightsizing/{id} | Yes |
| `organization_routes.py` | `/organization` | organization | Members, invitations, connection info | GET members/connection-info, POST invite | Yes |
| `permission_routes.py` | `/permissions` | permissions | JIT permission checks + feature registry | POST check, GET my-features/feature-registry | Yes |
| `policy_routes.py` | `/policies` | policies | Cluster optimization policy CRUD | GET/{cluster_id}, POST create, PUT update | OA+ |
| `rds_routes.py` | `/rds` | rds | RDS cost analysis | GET overview/top-opportunities | Yes |
| `ri_routes.py` | `/ri` | ri | RI utilization + recommendations | GET overview/list/recommendations, POST analysis | Yes |
| `role_routes.py` | `/roles` | roles | Role + permission matrix management | GET list/permissions-matrix, POST create | Yes |
| `s3_routes.py` | `/s3` | s3 | S3 cost analysis + tiering | GET overview, POST analyze | Yes |
| `settings_routes.py` | `/settings` | settings | User/platform preferences | GET/PUT settings | Yes |
| `smart_tag_routes.py` | `/tags/smart` | smart-tags | TTL and schedule tag processing | POST process | OA+ |
| `tag_management_routes.py` | `/tags/management` | tag-management | Read/write tags on AWS resources | GET/PUT /{resource_id}, POST bulk | JIT |
| `tag_policy_routes.py` | `/tags/policies` | tag-policies | Tag enforcement policy CRUD | GET list, POST create, GET compliance/stats | OA+ |
| `tag_template_routes.py` | `/tags/templates` | tag-templates | Reusable tag template CRUD | GET list, POST create, PUT update, DELETE | OA+ |
| `team_routes.py` | `/teams` | teams | Team CRUD, member management, governance | GET list/detail, POST create/invite/remove | TL+ |
| `template_routes.py` | `/templates` | templates | Node template CRUD + AWS CF download | GET list, POST create, PUT update, DELETE | OA+ |
| `transfer_routes.py` | `/transfer` | transfer | Data transfer cost analysis | GET overview/top-opportunities | Yes |
| `user_routes.py` | `/users` | users | User preferences (dashboard layout) | GET/PATCH /me/preferences | Yes |
| `__init__.py` | — | — | Router aggregation + registration | Combines all routers into `api_router` | — |

---

## 2. Services (`backend/services/`) — 32 files

Business logic layer. Each service class encapsulates domain operations.

### 2.1 Core Domain Services

| File | Class | Size | Purpose | Key Dependencies |
|:-----|:------|:-----|:--------|:----------------|
| `auth_service.py` | `AuthService` | 11KB | Login/signup/refresh/password, JWT tokens | User, Organization, bcrypt, python-jose |
| `cluster_service.py` | `ClusterService` | 32KB | Discovery, listing (Redis 30s), install script, disconnect | Account, Instance, boto3 (EKS/EC2), Redis |
| `account_service.py` | `AccountService` | 11KB | AWS account link/validate/disconnect, RBAC filtering | Account, boto3 (STS), ClusterService |
| `approval_service.py` | `ApprovalService` | 13KB | JIT ticket lifecycle (create/approve/reject/revoke/delegate) | Approval, User, PermissionService |
| `permission_service.py` | `PermissionService` | 10KB | Central gatekeeper: enforce/check/list features | Approval, FeatureRegistry |
| `hygiene_service.py` | `HygieneService` | 85KB | 11-type resource scan, parallel (ThreadPoolExecutor), actions | boto3, Redis, AuthorizedResource, ApprovalService |
| `hygiene_service_additions.py` | — | 4KB | Extended hygiene helpers (dependency checks) | HygieneService |
| `governance_service.py` | `GovernanceService` | 8KB | Org rules, autopilot execution, compliance | HygieneService, AuditLog |
| `metrics_service.py` | `MetricsService` | 31KB | Dashboard KPIs, cost series, team/account stats | Instance, OptimizationJob, ClusterMetric |

### 2.2 Infrastructure Services

| File | Class | Size | Purpose | Key Dependencies |
|:-----|:------|:-----|:--------|:----------------|
| `agent_injector.py` | `AgentInjectorService` | 32KB | 4-step agent deploy: STS→AccessEntry→Token→Manifests | boto3 (STS/EKS), kubernetes client |
| `onboarding_service.py` | `OnboardingService` | 9KB | AWS connection wizard state machine | Account, Onboarding model |
| `template_service.py` | `TemplateService` | 12KB | Node template CRUD, default management | NodeTemplate |
| `policy_service.py` | `PolicyService` | 13KB | Cluster optimization policy CRUD, validation | ClusterPolicy, NodeTemplate |
| `hibernation_service.py` | `HibernationService` | 13KB | Schedule CRUD, cron validation, timezone | HibernationSchedule |

### 2.3 Analysis & Cost Services

| File | Class | Size | Purpose | Key Dependencies |
|:-----|:------|:-----|:--------|:----------------|
| `ri_analysis_service.py` | `RIAnalysisService` | 19KB | RI utilization, waste detection, recommendations | boto3 (CE), RIUtilization |
| `savings_plan_service.py` | `SavingsPlanService` | 13KB | SP underutilization, monthly waste | boto3 (CE), SavingsPlanUtilization |
| `s3_tiering_service.py` | `S3TieringService` | 17KB | S3 bucket analysis, lifecycle optimization | boto3 (S3/CloudWatch) |
| `rds_analysis_service.py` | `RDSAnalysisService` | 9KB | RDS cost analysis, idle detection | boto3 (RDS/CloudWatch) |
| `transfer_service.py` | `TransferService` | 10KB | Data transfer cost breakdown | boto3 (CE) |

### 2.4 Tagging Services

| File | Class | Size | Purpose | Key Dependencies |
|:-----|:------|:-----|:--------|:----------------|
| `auto_tag_service.py` | `AutoTagService` | 19KB | Dynamic auto-tag rules, 6 value sources, preview | AutoTagRule, User, Organization |
| `tag_management_service.py` | `TagManagementService` | 10KB | Read/write AWS tags on resources | boto3 (EC2/S3/RDS) |
| `tag_policy_service.py` | `TagPolicyService` | 10KB | Tag enforcement policy CRUD, compliance stats | TagPolicy |
| `tag_suggestion_service.py` | `TagSuggestionService` | 5KB | AI-powered tag suggestions | TagPolicy, existing tags |
| `smart_tag_service.py` | `SmartTagService` | 12KB | TTL-based expiry + schedule tag processing | boto3, TagPolicy |

### 2.5 Organization & Admin Services

| File | Class | Size | Purpose | Key Dependencies |
|:-----|:------|:-----|:--------|:----------------|
| `admin_service.py` | `AdminService` | 19KB | Platform stats, client management, identity | User, AuditLog, SystemConfig, boto3 |
| `organization_service.py` | `OrganizationService` | 12KB | Members, invitations, role updates | User, Invitation |
| `team_service.py` | `TeamService` | 8KB | Team CRUD, member assignment, governance | Team, User |
| `role_service.py` | `RoleService` | 16KB | Role + permission CRUD, permission matrix | Role, Permission |
| `audit_service.py` | `AuditService` | 5KB | Audit log queries, role-filtered | AuditLog |
| `settings_service.py` | `SettingsService` | 4KB | User/platform preferences | User, SystemConfig |
| `lab_service.py` | `LabService` | 18KB | ML experiments, A/B testing, model registry | LabExperiment, MLModel |

---

## 3. Models (`backend/models/`) — 37 files

SQLAlchemy ORM models. All inherit from `Base` (declarative base with audit mixin).

### 3.1 Auth & Organization

| File | Class | Table | Key Columns |
|:-----|:------|:------|:------------|
| `user.py` | `User` | `users` | id, email, password_hash, role (4-tier enum), organization_id, team_id, preferences (JSON) |
| `organization.py` | `Organization` | `organizations` | id, name, required_tags (JSON), automation_enabled, automation_requires_approval, is_governance_enabled |
| `team.py` | `Team` | `teams` | id, name, organization_id, governance_config (JSON) |
| `role.py` | `Role` | `roles` | id, name, description, permissions (M2M) |
| `permission.py` | `Permission` | `permissions` | id, name, description, resource_type |
| `invitation.py` | `Invitation` | `invitations` | id, email, organization_id, role, status, token |
| `api_key.py` | `APIKey` | `api_keys` | id, key_hash, user_id, name, scopes, expires_at |

### 3.2 AWS Infrastructure

| File | Class | Table | Key Columns |
|:-----|:------|:------|:------------|
| `account.py` | `Account` | `accounts` | id, organization_id, role_arn, external_id, status, last_sync_at, sync_status |
| `cluster.py` | `Cluster` | `clusters` | id, account_id, name, arn, region, status, monthly_cost, estimated_savings, cpu_usage_pct, mem_usage_pct, last_heartbeat |
| `instance.py` | `Instance` | `instances` | id, cluster_id, instance_id, instance_type, lifecycle (SPOT/ON_DEMAND), price, cpu_util, memory_util, last_heartbeat, status |
| `cluster_metric.py` | `ClusterMetric` | `cluster_metrics` | id, cluster_id, timestamp, cpu_pct, memory_pct, node_count, pod_count |

### 3.3 Optimization & Policies

| File | Class | Table | Key Columns |
|:-----|:------|:------|:------------|
| `cluster_policy.py` | `ClusterPolicy` | `cluster_policies` | id, cluster_id, config (JSONB) |
| `node_template.py` | `NodeTemplate` | `node_templates` | id, organization_id, name, instance_types, constraints |
| `hibernation_schedule.py` | `HibernationSchedule` | `hibernation_schedules` | id, cluster_id, schedule (JSON), timezone, active |
| `optimization_job.py` | `OptimizationJob` | `optimization_jobs` | id, cluster_id, type, status, result, savings |

### 3.4 Governance & Approvals

| File | Class | Table | Key Columns |
|:-----|:------|:------|:------------|
| `approval.py` | `Approval` | `approvals` | id, type (enum), status (8-state enum), feature_id, jit_scope, requester_id, approver_id, duration_hours, expires_at, parent_id |
| `audit_log.py` | `AuditLog` | `audit_logs` | id, actor_id, action, target, outcome, metadata (JSON), timestamp |
| `authorized_resource.py` | `AuthorizedResource` | `authorized_resources` | id, resource_id, resource_type, user_id, reason |
| `hygiene_policy.py` | `HygienePolicy` | `hygiene_policies` | id, organization_id, name, resource_type, conditions (JSON), actions (JSON) |
| `legacy_approval.py` | `ApprovalRequest` | `approval_requests` | Deprecated maker-checker model (kept for migration reference) |

### 3.5 Tagging

| File | Class | Table | Key Columns |
|:-----|:------|:------|:------------|
| `auto_tag_rule.py` | `AutoTagRule` | `auto_tag_rules` | id, org_id, name, dynamic_tags (JSON), resource_scope, override_behavior, inject_system_tags |
| `tag_template.py` | `TagTemplate` | `tag_templates` | id, org_id, name, tags (JSON), description |
| `tag_policy.py` | `TagPolicy` | `tag_policies` | id, org_id, name, required_tags, allowed_values, enforcement_level |

### 3.6 Cost Analysis

| File | Class | Table | Key Columns |
|:-----|:------|:------|:------------|
| `pricing.py` | `SpotPriceHistory`, `OnDemandPricing` | `spot_price_history`, `ondemand_pricing` | Instance type, region, price, timestamp |
| `ri_utilization.py` | `RIUtilization` | `ri_utilization` | id, account_id, ri_id, utilization_pct, hourly_waste |
| `savings_plan_utilization.py` | `SavingsPlanUtilization` | `savings_plan_utilization` | id, account_id, plan_id, utilization_pct |
| `s3_analysis.py` | `S3Analysis` | `s3_analysis` | id, account_id, bucket, size_gb, storage_class, tiering_recommendation |
| `rds_analysis.py` | `RDSAnalysis` | `rds_analysis` | id, account_id, instance_id, engine, utilization_pct |
| `transfer_analysis.py` | `TransferAnalysis` | `transfer_analysis` | id, account_id, source_region, dest_region, cost |

### 3.7 System & Lab

| File | Class | Table | Key Columns |
|:-----|:------|:------|:------------|
| `system_config.py` | `SystemConfig` | `system_config` | key, value (key-value platform settings) |
| `platform_settings.py` | `PlatformSettings` | `platform_settings` | id, key, value, description |
| `onboarding.py` | `Onboarding` | `onboarding` | id, organization_id, step, status |
| `lab_experiment.py` | `LabExperiment` | `lab_experiments` | id, name, cluster_id, status, variants (JSON), results |
| `ml_model.py` | `MLModel` | `ml_models` | id, name, version, status, artifact_path |
| `agent_action.py` | `AgentAction` | `agent_actions` | id, cluster_id, action_type, target, status, result |
| `base.py` | `Base`, `AuditMixin` | — | Declarative base + created_at/updated_at mixin |

---

## 4. Schemas (`backend/schemas/`) — 21 files

Pydantic v2 validation schemas for request/response serialization.

| File | Key Classes | Domain |
|:-----|:------------|:-------|
| `auth_schemas.py` | `LoginRequest`, `SignupRequest`, `TokenResponse`, `UserResponse`, `MemberResponse` | Authentication |
| `account_schemas.py` | `AccountCreate`, `AccountResponse`, `AccountListResponse` | AWS Accounts |
| `admin_schemas.py` | `ClientListResponse`, `PlatformStatsResponse`, `PlatformConnectRequest` | Admin Panel |
| `approval_schemas.py` | `ApprovalCreate`, `ApprovalGrantCreate`, `ApprovalResponse`, `JITRequestCreate` | JIT Approvals |
| `audit_schemas.py` | `AuditLogQuery`, `AuditLogResponse`, `AuditExportRequest` | Audit |
| `auto_tag_schemas.py` | `AutoTagRuleCreate`, `DynamicTagConfig`, `TagPreviewRequest/Response`, `AvailableVariable` | Auto-Tagging |
| `cluster_schemas.py` | `ClusterResponse`, `ClusterListItem`, `InstallScriptResponse`, `ClusterFilter` | Clusters |
| `hibernation_schemas.py` | `HibernationCreate`, `HibernationUpdate`, `HibernationResponse` | Hibernation |
| `hygiene_schemas.py` | `HygieneStatus`, `HygieneSummary`, `HygieneActionType`, `HygieneAction` | Resource Hygiene |
| `hygiene_policy_schemas.py` | `HygienePolicyCreate`, `HygienePolicyUpdate`, `HygienePolicyResponse` | Hygiene Policies |
| `lab_schemas.py` | `ExperimentCreate`, `ExperimentResponse`, `ModelResponse` | Lab/ML |
| `metric_schemas.py` | `DashboardKPIs`, `CostTimeSeries`, `InstanceMetrics` | Metrics |
| `organization_schemas.py` | `InviteRequest`, `MemberUpdateRequest` | Organization |
| `policy_schemas.py` | `PolicyCreate`, `PolicyUpdate`, `PolicyResponse` | Cluster Policies |
| `role_schemas.py` | `RoleCreate`, `RoleResponse`, `PermissionMatrixResponse` | RBAC |
| `settings_schemas.py` | `SettingsResponse`, `SettingsUpdateRequest` | Settings |
| `tag_management_schemas.py` | `TagUpdateRequest`, `BulkTagRequest`, `TagResponse` | Tag Management |
| `tag_policy_schemas.py` | `TagPolicyCreate`, `TagPolicyResponse`, `ComplianceStatsResponse` | Tag Policies |
| `tag_template_schemas.py` | `TagTemplateCreate`, `TagTemplateResponse` | Tag Templates |
| `team_schemas.py` | `TeamCreate`, `TeamResponse`, `TeamGovernanceUpdate` | Teams |
| `template_schemas.py` | `NodeTemplateCreate`, `NodeTemplateUpdate`, `NodeTemplateResponse` | Node Templates |

---

## 5. Workers (`backend/workers/tasks/`) — 10 files

Celery background tasks with Redis broker.

| File | Task Name | Schedule | Purpose | Key Logic |
|:-----|:----------|:---------|:--------|:----------|
| `discovery.py` | `discovery_worker_loop` | Every 5 min | EKS cluster scan + instance inventory | STS assume-role per account, EKS ListClusters/DescribeCluster, auto-cleanup deleted clusters (10min grace) |
| `pricing_task.py` | `update_spot_prices`, `update_ondemand_prices` | 5-10 min / Daily 1AM | Spot + on-demand price updates | `describe_spot_price_history()`, AWS Price List API |
| `optimization.py` | `run_optimization` | Every 15 min | Spot replacement + bin packing | SpotOptimizer scoring, Rightsizer analysis |
| `cost_calculator.py` | `recalculate_cluster_costs` | Every 15 min | Sync cluster monthly_cost from instances | SUM(instance.price), clear Redis cache |
| `savings_calculator.py` | `calculate_savings` | Every 15 min | Realized + potential savings computation | Compare spot vs on-demand pricing |
| `hibernation_worker.py` | `check_hibernation_schedules` | Every 1 min | Enforce sleep/wake schedules | Timezone-aware cron matching, scale up/down |
| `health.py` | `health_check_task` | Every 5 min | System health monitoring | DB, Redis, Celery, AWS connectivity |
| `report_worker.py` | `generate_reports` | Daily/weekly | Usage and savings reports | Aggregation, PDF generation |
| `event_processor.py` | `process_events` | Continuous | K8s event processing | Event classification, alert generation |
| `agent_tasks.py` | `inject_agent_task` | On-demand | Async agent installation | Calls AgentInjectorService.inject() |

---

## 6. Core (`backend/core/`) — 13 files

Framework infrastructure, middleware, and shared utilities.

| File | Purpose | Key Exports |
|:-----|:--------|:------------|
| `api_gateway.py` | FastAPI app factory: CORS, middleware, exception handlers, router registration | `create_app()` |
| `config.py` | Environment configuration (pydantic_settings) | `Settings` class with all env vars |
| `dependencies.py` | FastAPI dependency injection: DB session, current user, role checks | `get_db()`, `get_current_user()`, `require_role()` |
| `crypto.py` | Password hashing (bcrypt), JWT encode/decode, Fernet encryption | `hash_password()`, `verify_password()`, `encrypt_data()`, `decrypt_data()` |
| `exceptions.py` | Custom exception hierarchy | `SpotOptimizerException`, `GovernanceError`, `ResourceNotFoundError` |
| `feature_registry.py` | 73+ protected features with risk levels, durations, approver roles | `FEATURE_REGISTRY` dict, `get_feature()` |
| `health_service.py` | Detailed system health: DB, Redis, Celery, AWS, data freshness | `HealthService` class |
| `action_executor.py` | Cloud write operations: drain, launch, verify, terminate | `ActionExecutor` class |
| `decision_engine.py` | Core optimization decision logic | `DecisionEngine` class |
| `redis_client.py` | Redis connection singleton | `redis_client` instance |
| `logger.py` | Structured logging (structlog) | `get_logger()` |
| `validators.py` | Shared validation utilities | Various validator functions |
| `__init__.py` | Package exports | Aggregated imports |

---

## 7. ML/Optimization Modules (`backend/modules/`) — 7 files

Standalone optimization engines used by workers and services.

| File | Class | Purpose | Key Algorithm |
|:-----|:------|:--------|:-------------|
| `spot_optimizer.py` | `SpotOptimizer` | Instance selection: price-risk scoring | Weighted score: price (0.6) + risk (0.4), diversification across AZs |
| `rightsizer.py` | `Rightsizer` | CPU/memory-based resize recommendations | P95 utilization → closest instance type match |
| `bin_packer.py` | `BinPacker` | Node fragmentation analysis, consolidation | First-fit-decreasing bin packing, fragmentation scoring |
| `risk_tracker.py` | `RiskTracker` | Global spot interruption risk intelligence | Redis-backed frequency tracking per instance type per AZ |
| `ml_model_server.py` | `MLModelServer` | ML model serving for predictions | Model loading, inference API, versioning |
| `model_validator.py` | `ModelValidator` | Model validation before promotion | Accuracy checks, data drift detection |
| `__init__.py` | — | Package exports | Aggregated imports |

---

## 8. Scripts (`backend/scripts/`) — 3 files

Reusable seed and utility scripts (one-time migration scripts deleted 2026-02-10).

| File | Purpose | Usage |
|:-----|:--------|:------|
| `seed_permissions.py` | Seed 12 base permissions + 3 default roles | `python -m backend.scripts.seed_permissions` |
| `seed_rbac.py` | Seed RBAC data (roles, permissions, associations) | `python -m backend.scripts.seed_rbac` |
| `get_admin_token.py` | Generate JWT for SUPER_ADMIN (development) | `python -m backend.scripts.get_admin_token` |

---

## 9. Templates (`backend/templates/aws/`) — 2 files

CloudFormation YAML templates for cross-account IAM roles.

| File | Purpose | Key Resources |
|:-----|:--------|:-------------|
| `read-only-role.yaml` | Default onboarding role (SecurityAudit + discovery) | IAM Role with ExternalId, SecurityAudit/EC2ReadOnly/CloudWatch policies, EKS discovery |
| `full-access-role.yaml` | Extended role for automation (tag-conditioned writes) | Above + ec2:TerminateInstances (tag:ManagedBy=SpotOptimizer), S3/RDS write access |

---

## 10. File Size Distribution (Top 15)

| File | Size | Notes |
|:-----|:-----|:------|
| `services/hygiene_service.py` | 85KB | 11-type parallel scanner — largest service |
| `core/feature_registry.py` | 44KB | 73+ feature definitions with metadata |
| `services/cluster_service.py` | 32KB | Discovery + Redis cache + install logic |
| `services/agent_injector.py` | 32KB | 4-step cross-account agent deployment |
| `services/metrics_service.py` | 31KB | KPI aggregation across all dimensions |
| `workers/tasks/discovery.py` | 28KB | EKS scanning + auto-cleanup logic |
| `workers/tasks/report_worker.py` | 22KB | Report generation pipeline |
| `services/auto_tag_service.py` | 19KB | Dynamic tag resolution engine |
| `services/ri_analysis_service.py` | 19KB | RI waste detection |
| `services/admin_service.py` | 19KB | Platform management |
| `core/action_executor.py` | 19KB | Cloud write operation orchestration |
| `core/decision_engine.py` | 18KB | Optimization decision logic |
| `services/lab_service.py` | 18KB | ML experiment management |
| `modules/spot_optimizer.py` | 17KB | Price-risk scoring engine |
| `services/s3_tiering_service.py` | 17KB | S3 lifecycle optimization |

---

## 11. Import Dependency Graph (Key Chains)

```
API Routes → Services → Models + boto3 + Redis
                      → PermissionService (for JIT enforcement)
                      → AuditService (for logging)

Workers → Services → Models + boto3 + Redis
        → Modules (SpotOptimizer, Rightsizer, BinPacker)

Core:
  api_gateway.py → All route files
  dependencies.py → User model, JWT (used by all routes)
  feature_registry.py → PermissionService
  exceptions.py → All services (GovernanceError, etc.)
```

---

**Last Updated**: 2026-02-10
