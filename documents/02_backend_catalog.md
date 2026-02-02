# Backend Component Catalog

**Date:** 2026-01-19 (Last Updated)
**Scope:** `backend/` Directory

## ID Naming Convention
`BE-[TYPE]::[MODULE]::[NAME]`
*   **Types:** `API` (Route), `SVC` (Service), `SCH` (Schema), `MOD` (Model), `WRK` (Worker), `UTL` (Utility), `CFG` (Config)

## Catalog

| ID (Unique Tracking Code) | File Path | Type | Function / Feature Description | Main Dependencies |
| :--- | :--- | :--- | :--- | :--- |
| **BE-SVC::Auth::Main** | `backend/services/auth_service.py` | Service | User authentication, signup, login, token management (JWT). | `User`, `Organization`, `crypto` |
| **BE-SVC::Admin::Main** | `backend/services/admin_service.py` | Service | Super Admin operations: Client management (Counts ORG_ADMIN + CLIENT), Platform stats (Real metrics), **Toggle Org Status** (Suspension), Dashboard real-time audit feed. | `User`, `AuditLog` |
| **BE-SVC::Organization::Main** | `backend/services/organization_service.py` | Service | Member management (Invite, Remove, Update Role). RBAC enforcement (Org Admin vs Team Lead). | `User`, `OrganizationInvitation` |
| **BE-SVC::Account::Main** | `backend/services/account_service.py` | Service | Managing AWS accounts, Platform Identity integration, and STS assume_role validation. | `Account`, `boto3` |
| **BE-SVC::Account::Cache** | `backend/services/account_cache_service.py` | Service | **NEW (2026-01-16)**: Temporary encrypted credential storage in Redis for MEMBER account connection approval flow. 7-day TTL. | `redis`, `crypto` (encrypt_data/decrypt_data) |
| **BE-API::User::Preferences** | `backend/api/user_routes.py` | API | **NEW (2026-01-16)**: GET/PATCH `/users/me/preferences` - Dashboard layout customization with role-based widget validation. Stores preferences in User.preferences JSON column. | `User` |
| **BE-SVC::Cluster::Main** | `backend/services/cluster_service.py` | Service | **Real**: Cluster discovery via `boto3.eks.list_clusters/describe_cluster` with STS assume_role. DB upsert for discovered clusters. | `Cluster`, `Account`, `boto3` |
| **BE-SVC::Template::Main** | `backend/services/template_service.py` | Service | Node Template CRUD. Logic for setting default templates. | `NodeTemplate`, `User` |
| **BE-SVC::Policy::Main** | `backend/services/policy_service.py` | Service | Policy management. Validates spot percentages, min/max nodes, and resource limits. | `ClusterPolicy`, `Cluster`, `NodeTemplate` |
| **BE-SVC::Hibernation::Main** | `backend/services/hibernation_service.py` | Service | Hibernation schedule logic. Validates cron-like schedule matrix and timezone. | `HibernationSchedule` |
| **BE-SVC::Metrics::Main** | `backend/services/metrics_service.py` | Service | Metrics aggregation (Cost, Savings, Usage). Generates Dashboard KPIs and Time Series data. | `Instance`, `OptimizationJob` |
| **BE-SVC::Audit::Main** | `backend/services/audit_service.py` | Service | Audit logging and querying. tracks actor, event, resource, outcome. **Filter by Role** support. | `AuditLog` |
| **BE-SVC::Lab::Main** | `backend/services/lab_service.py` | Service | ML Experimentation (A/B Testing). Manage experiments, variants, and calculate results/winners. | `LabExperiment`, `MLModel` |
| **BE-SVC::Cleanup::Main** | `backend/services/cleanup_service.py` | Service | **REAL (Updated 2026-01-19)**: High-performance resource hygiene service. **New**: `_scan_storage` for S3 bucket analysis (Empty/Untagged/Old). **Refactored**: `_scan_volumes_and_snapshots` with 4-way EBS categorization (Active, Orphaned-Compliant, Non-Compliant, Safe-to-Delete). Features: Parallel multi-region scanning, 1-hour cache, authorization logic, and **dynamic scan_time metadata**. | `boto3`, `redis`, `AuthorizedResource` |
| **BE-API::Admin::Main** | `backend/api/admin_routes.py` | API | Super Admin Endpoints. List Orgs/Clients, Billing, Dashboard Stats (Live Feed), Platform Stats, **Toggle Org Status** (POST /{id}/toggle). | `AdminService` |
| **BE-API::Account::Main** | `backend/api/account_routes.py` | API | AWS Account Management. Link, List, Delete accounts. **NEW**: POST /cache-credentials (MEMBER approval flow - stores encrypted creds in Redis until ticket approved). | `AccountService`, `AccountCacheService` |
| **BE-API::Cluster::Main** | `backend/api/cluster_routes.py` | API | Cluster Operations. Discover, Register, Connect (AWS), Agent Install, Heartbeat. | `ClusterService` |
| **BE-API::Organization::Main** | `backend/api/organization_routes.py` | API | Organization Management. List Members, Invite (ORG_ADMIN), Update Role, Remove Member. | `OrganizationService` |
| **BE-API::Policy::Main** | `backend/api/policy_routes.py` | API | Optimization Policy Management. Create, List, Update, Delete, Toggle policies. | `PolicyService` |
| **BE-API::Hibernation::Main** | `backend/api/hibernation_routes.py` | API | Hibernation Schedule Management. Create, List, Update, Delete schedules. | `HibernationService` |
| **BE-API::Metrics::Main** | `backend/api/metrics_routes.py` | API | Dashboard Metrics. Savings, Costs, Instance Stats. **Updated**: `GET /teams/{id}/summary` for Team Consolidated View (Lead/Admin). | `MetricsService` |
| **BE-API::Audit::Main** | `backend/api/audit_routes.py` | API | Audit Log Querying. Filter logs by actor, event, resource type. | `AuditService` |
| **BE-API::Lab::Main** | `backend/api/lab_routes.py` | API | Lab Experiments. Create, List, Start, Stop, Get Results for A/B testing. | `LabService` |
| **BE-API::Cleanup::Main** | `backend/api/cleanup_routes.py` | API | Endpoints for resource hygiene scanning and action execution. | `CleanupService` |
| **BE-API::Clean::Policy** | `backend/api/cleanup_policy_routes.py` | API | **NEW (2026-01-20)**: Cleanup Policy CRUD. List, Create, Update, Delete rule-based policies. | `CleanupPolicy` |
| **BE-API::Health::System** | `backend/api/health_routes.py` | API | System Health Monitoring. Get detailed health status (DB, Redis, Workers). | `HealthService` |
| **BE-API::Optimization::Main** | `backend/api/optimization_routes.py` | API | Rightsizing Recommendations. Analyze cluster workloads and return resize advice. | `RightSizer` |
| **BE-API::Billing::Main** | `backend/api/billing_routes.py` | API | **Real**: Stripe Billing. Create portal session, webhook handler, subscription status. | `stripe` |
| **BE-MOD::Gov::Ticket** | `backend/models/ticket.py` | Model | Just-in-Time Permission Ticket with Delegation. Enums: `TicketType` (ACTION, ACCESS_WINDOW, **ACCOUNT_CONNECTION**), `TicketStatus` (8 states). Fields: `parent_id`, `action_type`, `resource_id`, `duration_hours`, `activated_at`. **NEW (2026-01-16)**: ACCOUNT_CONNECTION type for MEMBER AWS account approval flow. | `Organization` |
| **BE-SVC::JIT::Ticket** | `backend/services/ticket_service.py` | Service | **Real (JIT)**: Ticket CRUD operations. Methods: create_ticket, list_tickets, approve_ticket, revoke_ticket, get_active_window. Auto-expiry logic. `_check_approver_auth` includes `CLIENT` role (legacy ORG_ADMIN) and org check. Role-based filtering in `list_tickets` (Admin=All, Lead=Team, Member=Own). | `Ticket`, `User`, `UserRole` |
| **BE-SVC::JIT::Permission** | `backend/services/permission_service.py` | Service | **Real (JIT)**: Central gatekeeper for JIT access. Checks if user has active ACCESS_WINDOW ticket before allowing protected actions. Integrated with CleanupService. | `Ticket`, `TicketService` |
| **BE-API::JIT::Ticket** | `backend/api/ticket_routes.py` | API | **Real (JIT)**: JIT Ticket endpoints. POST `/` (create), POST `/grant` (admin grant), GET `/` (list), POST `/{id}/approve`, POST `/{id}/revoke`, POST `/{id}/accept`, POST `/{id}/reject`, GET `/active-window`. | `TicketService` |
| **BE-SCH::JIT::Ticket** | `backend/schemas/ticket_schemas.py` | Schema | **Real (JIT)**: Pydantic schemas for tickets. `TicketCreate` (type, reason, duration, action, resource). `TicketResponse` (full ticket data with status and timestamps). | `Pydantic` |
| **BE-API::Admin::Platform** | `backend/api/admin_routes.py` | API | **Real**: Platform Identity Management. Get connection status, connect (STS verify), disconnect. | `AdminService`, `boto3` |
| **BE-API::Templates::Main** | `backend/api/template_routes.py` | API | **Real**: Serves CloudFormation templates. Includes `GET /` (List) and `GET /aws-onboarding` (Download). | `FileResponse` |
| **BE-SVC::Admin::Platform** | `backend/services/admin_service.py` | Service | **Real**: Platform credential management with STS verification. | `boto3`, `SystemConfig` |
| **BE-MOD::System::Config** | `backend/models/system_config.py` | Model | Key-value store for system settings (Safe Mode, Platform Keys). | `Base` |
| **BE-TPL::AWS::RoleYAML** | `backend/templates/aws/read-only-role.yaml` | Template | CloudFormation YAML for cross-account IAM role creation. | N/A |
| **BE-MOD::System::Base** | `backend/models/base.py` | Model | Base Audit Mixin and DB connection setup. | `SQLAlchemy` |
| **BE-SVC::Approval::Main** | `backend/services/approval_service.py` | Service | **Real (Feature 6)**: Approval Engine for Four-Eyes Principle. Creates requests, enforces Maker-Checker rules, executes approved payloads dynamically. | `ApprovalRequest`, `User` |
| **BE-MOD::Tag::AutoRule** | `backend/models/auto_tag_rule.py` | Model | **Updated (2026-01-30)**: Auto-Tag Rule with Dynamic Values. Enums: `ValueSourceType` (8 sources: user_email, creation_date, env_variable, etc.), `OverrideBehavior`, `ResourceScope`. New columns: `dynamic_tags` (JSON), `resource_scope`, `override_behavior`, `inject_system_tags`. | `Base` |
| **BE-SVC::Tag::AutoTag** | `backend/services/auto_tag_service.py` | Service | **Updated (2026-01-30)**: Smart Auto-Tag Engine. **New**: `generate_tags()` for dynamic value resolution (user context, timestamps, env vars). `preview_tags()` for Live Preview. `get_available_variables()` for UI dropdown. Injects `ManagedBy: SpotOptimizer` system tag. | `AutoTagRule`, `User`, `Organization` |
| **BE-API::Tag::AutoRules** | `backend/api/auto_tag_routes.py` | API | **Updated (2026-01-30)**: Auto-Tag Rule Management. **New**: POST `/preview` (Live Preview for Policy Builder), GET `/variables` (Available Dynamic Variables). | `AutoTagService` |
| **BE-SCH::Tag::AutoTag** | `backend/schemas/auto_tag_schemas.py` | Schema | **Updated (2026-01-30)**: Added `ValueSourceType`, `OverrideBehavior`, `ResourceScope` enums. Added `DynamicTagConfig`, `TagPreviewRequest`, `TagPreviewResponse`, `AvailableVariable`, `AvailableVariablesResponse` schemas. | `Pydantic` |
| **BE-MIG::Tag::Dynamic** | `backend/migrations/versions/009_dynamic_auto_tags.py` | Migration | **NEW (2026-01-30)**: Adds `dynamic_tags`, `resource_scope`, `override_behavior`, `inject_system_tags` columns to `auto_tag_rules` and `tag_policies` tables. | `Alembic` |

| **BE-API::Approval::Main** | `backend/api/approval_routes.py` | API | **Real (Feature 6)**: Approval Endpoints. List Pending, Approve, Reject for Team Leads. | `ApprovalService` |
| **BE-MOD::Auth::Approval** | `backend/models/approval.py` | Model | **NEW (Feature 6)**: Approval Request Table. Stores payload and status for Maker-Checker workflow. | `Base` |
| **BE-MOD::Auth::User** | `backend/models/user.py` | Model | **Updated (Feature 6)**: 4-Tier `UserRole` enum (SUPER_ADMIN, ORG_ADMIN, TEAM_LEAD, MEMBER) and `team_id`. | `Base` |
| **BE-MOD::Auth::Org** | `backend/models/organization.py` | Model | **Updated (Feature 6)**: Governance Flags (`is_governance_enabled`, `is_strict_approval_mode`). | `Base` |
| **BE-MOD::Auth::Team** | `backend/models/team.py` | Model | **Real**: Team Model. Groups users within an org. **governance_config** (JSON) stores team-specific approval rules. | `Base` |
| **BE-SVC::Team::Main** | `backend/services/team_service.py` | Service | **New**: Team Management. Create, Rename, Assign members, **Remove Member**. | `Team`, `User` |
| **BE-API::Team::Main** | `backend/api/team_routes.py` | API | **Real**: Team Endpoints (CRUD). **Remove API**: `POST /teams/{id}/remove`. **Team-Specific Governance**: `GET/PUT /teams/{id}/governance`. **Member Permissions**: `PUT /teams/{id}/members/{member_id}/permissions`. | `TeamService`, `Team` |
| **BE-MOD::Auth::Invite** | `backend/models/invitation.py` | Model | Organization Invitation Table. | `Base` |
| **BE-SVC::Governance::Main** | `backend/services/governance_service.py` | Service | **Real**: Automated Governance / Policy-as-Code. Executes cleanup based on org policies with "System Autopilot" actor. | `CleanupService`, `AuditLog` |
| **BE-API::Governance::Main** | `backend/api/governance_routes.py` | API | **Real**: Governance Endpoints. Get/Update policies, trigger autopilot. | `GovernanceService` |
| **BE-MOD::Infra::Account** | `backend/models/account.py` | Model | AWS Account Table. | `Base` |
| **BE-MOD::Infra::Cluster** | `backend/models/cluster.py` | Model | Kubernetes Cluster Table. | `Base` |
| **BE-MOD::Infra::Instance** | `backend/models/instance.py` | Model | Node/Instance Table. | `Base` |
| **BE-MOD::Clean::AuthRes** | `backend/models/authorized_resource.py` | Model | **Real**: Authorized Resources Table. Stores user-authorized exceptions to cleanup rules. | `Base` |
| **BE-MOD::Infra::Template** | `backend/models/node_template.py` | Model | Node Template Table. | `Base` |
| **BE-MOD::Policy::Main** | `backend/models/cluster_policy.py` | Model | Cluster Policy Table. | `Base` |
| **BE-MOD::Policy::Hibernation** | `backend/models/hibernation_schedule.py` | Model | Hibernation Schedule Table. | `Base` |
| **BE-MOD::Lab::Experiment** | `backend/models/lab_experiment.py` | Model | Lab Experiment Table (Linked to `Cluster`). | `Base` |
| **BE-MOD::Lab::MLModel** | `backend/models/ml_model.py` | Model | Machine Learning Model Table. | `Base` |
| **BE-MOD::Ops::AuditLog** | `backend/models/audit_log.py` | Model | Audit Log Table. | `Base` |
| **BE-MOD::Ops::OptJob** | `backend/models/optimization_job.py` | Model | Optimization Job Table. | `Base` |
| **BE-MOD::Clean::Policy** | `backend/models/cleanup_policy.py` | Model | **NEW (2026-01-20)**: Cleanup Policy Table. Stores rule-based conditions (JSON) for dynamic resource hygiene. | `Base` |
| **BE-MOD::Ops::Onboarding** | `backend/models/onboarding.py` | Model | Onboarding State Table. | `Base` |
| **BE-SCH::Auth::Main** | `backend/schemas/auth_schemas.py` | Schema | Pydantic Schemas for Auth. **Updated**: `MemberResponse` now includes `role`, `access_level`, `team_id`, and `full_name`. | `Pydantic` |
| **BE-SCH::Admin::Main** | `backend/schemas/admin_schemas.py` | Schema | Pydantic Schemas for Admin (ClientList, PlatformStats). | `Pydantic` |
| **BE-SCH::Cluster::Main** | `backend/schemas/cluster_schemas.py` | Schema | Pydantic Schemas for Cluster (Create, Update, Response). | `Pydantic` |
| **BE-SCH::Template::Main** | `backend/schemas/template_schemas.py` | Schema | Pydantic Schemas for Template (Create, Update, Response). | `Pydantic` |
| **BE-SCH::Policy::Main** | `backend/schemas/policy_schemas.py` | Schema | Pydantic Schemas for Policy (Create, Update, Response). | `Pydantic` |
| **BE-SCH::Metrics::Main** | `backend/schemas/metric_schemas.py` | Schema | Pydantic Schemas for Metrics (DashboardKPIs, TimeSeries). | `Pydantic` |
| **BE-API::Onboarding::Main** | `backend/api/onboarding_routes.py` | API | AWS Account Onboarding Flow. Get State, CloudFormation Deep Links, Verify Credentials, Complete. **UPDATED (2026-01-16)**: POST /skip (resets state, NOT complete), POST /reset (allows restart if no accounts). | `OnboardingService` |
| **BE-MOD::System::AgentAction** | `backend/models/agent_action.py` | Model | Pending actions for K8s Agent (e.g. cordon, drain). | `Base` |
| **BE-MOD::Auth::APIKey** | `backend/models/api_key.py` | Model | API Keys for programmatic access. | `Base` |
| **BE-CORE::Config::Main** | `backend/core/config.py` | Core | Global application configuration (Env vars). | `pydantic_settings` |
| **BE-CORE::Database::Base** | `backend/core/dependencies.py` | Core | Dependency Injection (get_db, get_current_user). | `FastAPI`, `SQLAlchemy` |
| **BE-CORE::Security::Crypto** | `backend/core/crypto.py` | Core | Cryptographic utilities (Hash password, JWT). | `passlib`, `jose` |
| **BE-CORE::Logic::Executor** | `backend/core/action_executor.py` | Core | Logic to execute actions (AWS or K8s). | `boto3`, `AgentAction` |
| **BE-CORE::Utils::Logger** | `backend/core/logger.py` | Core | Structured logging configuration. | `structlog` |
| **BE-CORE::Utils::Redis** | `backend/core/redis_client.py` | Core | Redis connection client. | `redis` |
| **BE-CORE::Logic::Gateway** | `backend/core/api_gateway.py` | Core | API Gateway / Proxy logic (if any). | `httpx` |
| **BE-CORE::Logic::Decision** | `backend/core/decision_engine.py` | Core | Core decision making logic for optimizations. | `Modules` |
| **BE-CORE::Logic::Health** | `backend/core/health_service.py` | Core | System health checks. | `Redis`, `DB` |
| **BE-CORE::Logic::Exceptions** | `backend/core/exceptions.py` | Core | Custom Exception definitions. | `Exception` |
| **BE-CORE::Logic::Validators** | `backend/core/validators.py` | Core | Common input validators. | `Regex` |
| **BE-MODL::Optimizer::Spot** | `backend/modules/spot_optimizer.py` | Module | Core Logic for Spot Instance optimization/replacement. | `AWS Pricing` |
| **BE-MODL::Optimizer::Rightsize** | `backend/modules/rightsizer.py` | Module | Logic for rightsizing instances based on usage. | `Metrics` |
| **BE-MODL::Optimizer::BinPack** | `backend/modules/bin_packer.py` | Module | **Standalone**: Implemented logic for node consolidation, awaiting worker integration. | `Kubernetes` |
| **BE-MODL::ML::Server** | `backend/modules/ml_model_server.py` | Module | **Standalone**: Implemented (Mocked) ML prediction server. Not used by API/Workers yet. | `Tensorflow/PyTorch` |
| **BE-MODL::ML::Validator** | `backend/modules/model_validator.py` | Module | **Standalone**: Implemented validation logic. | `Pandas` |
| **BE-MODL::Risk::Tracker** | `backend/modules/risk_tracker.py` | Module | **Real**: "Hive Mind" Global Risk Intelligence using Redis to flag/check instance pools. | `Redis`, `PubSub` |
| **BE-WRK::Task::Discovery** | `backend/workers/tasks/discovery.py` | Worker | Periodic cluster/resource discovery task. | `boto3` |
| **BE-WRK::Task::EventProc** | `backend/workers/tasks/event_processor.py` | Worker | Processing K8s events (pod pending, etc). | `Redis` |
| **BE-WRK::Task::Hibernate** | `backend/workers/tasks/hibernation_worker.py` | Worker | Executing hibernation schedules (Stop/Start nodes). | `HibernationService` |
| **BE-WRK::Task::Optimize** | `backend/workers/tasks/optimization.py` | Worker | Triggering optimization runs. | `SpotOptimizer` |
| **BE-WRK::Task::Report** | `backend/workers/tasks/report_worker.py` | Worker | Generating periodic usage/savings reports. | `MetricsService` |
| **BE-APP::Main::Entrypoint** | `main.py` | App | **Critical**: Main ASGI application entrypoint (FastAPI app). | `Backend` |
| **BE-API::Router::Root** | `backend/api/__init__.py` | API | Central API Router. **Note**: `account_routes` is NOT exported here (imported directly by Gateway). | `FastAPI` |
| **BE-MOD::System::Registry** | `backend/models/__init__.py` | Model | Model Registry exporting models for Alembic. | `SQLAlchemy` |
| **BE-WRK::Task::Registry** | `backend/workers/tasks/__init__.py` | Worker | Task Registry exporting Celery tasks. | `Celery` |
| **BE-CFG::DB::Alembic** | `alembic.ini` | Config | Configuration for Alembic DB migrations. | `Alembic` |
| **BE-MIG::Env::Main** | `migrations/env.py` | Config | Python environment script for migrations. | `Alembic` |
| **BE-MIG::Ver::001_Initial** | `migrations/versions/001_initial_schema.py` | Migration | Initial database schema creation script. | `Alembic` |
| **BE-MIG::Ver::002_Seed** | `migrations/versions/002_seed_data.py` | Migration | Script to seed database with default data. | `Alembic` |
| **BE-MIG::Ver::003_Governance** | `migrations/versions/003_add_governance_columns.py` | Migration | Adds `team_id` (users), `required_tags` (organizations), `approval_requests` table. | `Alembic` |
| **BE-MIG::Ver::004_TeamPerms** | `migrations/versions/20260119_0550_5f5416e8114a_add_team_member_permissions.py` | Migration | **NEW (2026-01-19)**: Adds `team_member_permissions` JSON column to users table for granular permission overrides. | `Alembic` |
| **BE-MIG::Ver::007_Policy** | `backend/migrations/versions/007_cleanup_policies.py` | Migration | **NEW (2026-01-20)**: Creates `cleanup_policies` table with JSONB conditions. | `Alembic` |
| **BE-AST::AWS::IAM_Full** | `backend/templates/aws/full-access-role.yaml` | Asset | CloudFormation template for Full Access IAM Role. | `AWS` |
| **BE-AST::AWS::IAM_Full** | `backend/templates/aws/full-access-role.yaml` | Asset | CloudFormation template for Full Access IAM Role. | `AWS` |
| **BE-AST::AWS::IAM_ReadOnly** | `backend/templates/aws/read-only-role.yaml` | Asset | CloudFormation template for Read-Only IAM Role. Updated with `SpotOptimizerCleanupPolicy`. | `AWS` |
| **BE-SCR::Admin::Seed** | `scripts/seed_admin.py` | Script | Utility to programmatically create an admin user. | `Python` |
| **BE-SCR::Data::SeedDemo** | `scripts/seed_demo_data.py` | Script | Utility to populate system with demo data. | `Python` |
| **BE-SCR::AWS::LaunchSpot** | `scripts/aws/launch_spot.py` | Script | Standalone script to test Spot Instance launching. | `boto3` |
| **BE-SCR::AWS::TermInstance** | `scripts/aws/terminate_instance.py` | Script | Standalone script to test Instance termination. | `boto3` |
| **BE-SCR::Org::Migrate** | `scripts/migrate_to_organizations.py` | Script | Utility to migrate legacy user data to Organizations. | `Python` |
| **BE-API::Auth::Main** | `backend/api/auth_routes.py` | API | Authentication Endpoints (Login, Signup, Refresh Token). | `AuthService` |
| **BE-API::Template::Main** | `backend/api/template_routes.py` | API | Node Template Endpoints (Create, List, Delete templates). | `TemplateService` |
| **BE-SVC::Onboarding::Main** | `backend/services/onboarding_service.py` | Service | Business logic for tracking user onboarding steps. | `OnboardingState` |
| **BE-SVC::Data::Pricing** | `backend/scrapers/pricing_collector.py` | Service | **Real**: Connected via Celery. Collects Spot (every 10m) and On-Demand (daily) prices from AWS. | `boto3` |
| **BE-SVC::Data::SpotRisk** | `backend/scrapers/spot_advisor_scraper.py` | Service | Fetches AWS Spot Advisor data for interruption risks. | `requests` |
| **BE-SCH::Account::Main** | `backend/schemas/account_schemas.py` | Schema | Pydantic models for AWS Account validation. | `Pydantic` |
| **BE-SCH::Audit::Main** | `backend/schemas/audit_schemas.py` | Schema | Pydantic models for Audit Log responses. | `Pydantic` |
| **BE-SCH::Hibernation::Main** | `backend/schemas/hibernation_schemas.py` | Schema | Pydantic models for Hibernation Schedules. | `Pydantic` |
| **BE-SCH::Lab::Main** | `backend/schemas/lab_schemas.py` | Schema | Pydantic models for ML Experiments. | `Pydantic` |
| **BE-SCH::Cleanup::Main** | `backend/schemas/cleanup_schemas.py` | Schema | **REAL (Updated 2026-01-19)**: Pydantic models for resource hygiene. `CleanupSummary` now includes a `metadata` dictionary for `scan_time`, `region_count`, and `resource_count`. `ResourceType` enum (11 types), `CleanupStatus` (RISK, LEGACY_UPGRADE), `ResourceItem` with `reason` and `is_authorized` fields. | `Pydantic` |
| **BE-SCH::Organization::Main** | `backend/schemas/organization_schemas.py` | Schema | Pydantic models for Org members and invites. | `Pydantic` |
| **BE-API::Settings::Main** | `backend/api/settings_routes.py` | API | Settings Endpoints. Profile management and Integrations. | `SettingsService` |
| **BE-SVC::Settings::Main** | `backend/services/settings_service.py` | Service | Logic for user profile updates and integrations (Mocked). | `User`, `Mocks` |
| **BE-SCH::Settings::Main** | `backend/schemas/settings_schemas.py` | Schema | Pydantic models for Settings and Integrations. | `Pydantic` |
| **BE-WRK::Core::App** | `backend/workers/app.py` | Worker | **Real**: Celery app with `beat_schedule`: `discovery-every-5-mins` (300s), `pricing-every-hour` (3600s). | `Celery`, `Redis` |
| **BE-WRK::Task::Pricing** | `backend/workers/tasks/pricing_task.py` | Worker | **Real**: Fetches AWS pricing via `PricingCollector` and spot risks via `SpotAdvisorScraper`. Scheduled hourly. | `boto3`, `Scrapers` |
| **BE-OPS::Deploy::Main** | `scripts/deployment/deploy.sh` | Script | Main deployment shell script. | `Bash` |
| **BE-OPS::Deploy::Setup** | `scripts/deployment/setup.sh` | Script | Environment setup shell script. | `Bash` |
| **BE-CFG::Deps::Main** | `requirements.txt` | Config | Python dependency manifest for the backend. | `Pip` |
| **BE-CFG::System::EnvExample** | `.env.example` | Config | Template for environment variables. | `Env` |
| **BE-MIG::TPL::Script** | `migrations/script.py.mako` | Config | Mako template used by Alembic. | `Mako` |
| **BE-SCH::System::Registry** | `backend/schemas/__init__.py` | Schema | Exports all schemas. | `Python` |
| **BE-SCH::Clean::Policy** | `backend/schemas/cleanup_policy_schemas.py` | Schema | **NEW (2026-01-20)**: Pydantic schemas for Cleanup Policies (Conditions, Actions, Priority). | `Pydantic` |
| **BE-MODL::System::Registry** | `backend/modules/__init__.py` | Module | Exports all optimization modules. | `Python` |

### 5. Agent Components (Remote Execution)
These components run on the Kubernetes nodes, separate from the main backend container.

| Component ID | File Path | Type | Description | Main Dependencies |
| :--- | :--- | :--- | :--- | :--- |
| **AGT-APP::Main::Entrypoint** | `agent/main.py` | App | Entry point for the Node Agent process. | `AsyncIO` |
| **AGT-CFG::System::Main** | `agent/config.py` | Config | Configuration loading for the Agent. | `Env` |
| **AGT-SVC::Data::Collector** | `agent/collector.py` | Service | Collects node metrics and pod status. | `Boto3`, `K8s` |
| **AGT-SVC::Action::Actuator** | `agent/actuator.py` | Service | Executes commands on the node (Cordon/Drain). | `Subprocess` |
| **AGT-SVC::System::Heartbeat** | `agent/heartbeat.py` | Service | Sends periodic heartbeat signals to Backend. | `WebSocket` |
| **AGT-UTL::Net::WebSocket** | `agent/websocket_client.py` | Utility | Manages WebSocket connection to Backend. | `SocketIO` |
| **AGT-INF::Docker::Agent** | `agent/Dockerfile` | Infra | Docker container definition for the Agent. | `Docker` |
| **BE-OPS::Local::Start** | `start.sh` | Script | Local development startup script. | `Bash` |
| **BE-OPS::Local::Rebuild** | `rebuild.sh` | Script | Script to rebuild Docker containers. | `Generic` |
| **BE-SCR::AWS::UpdateASG** | `scripts/aws/update_asg.py` | Script | Utility to update Auto Scaling Groups. | `boto3` |
| **BE-SCR::AWS::DetachVol** | `scripts/aws/detach_volume.py` | Script | Utility to detach EBS volumes from instances. | `boto3` |
| **BE-SCR::Admin::DebugUser** | `scripts/debug_users.py` | Script | Utility to debug user data or permissions. | `SQLAlchemy` |
| **BE-SCR::Admin::FixDemo** | `scripts/fix_demo_user.py` | Script | Utility to fix/reset the specific demo user state. | `SQLAlchemy` |
| **BE-SCR::Data::UpdateSeed** | `scripts/update_and_seed.py` | Script | Combined utility to run migrations and seed data in one go. | `Alembic`, `Seed Scripts` |
| **BE-INF::Docker::Backend** | `docker/Dockerfile.backend` | Infra | Docker container definition for the Python Backend. | `Python Base Image` |
| **BE-INF::Docker::Compose** | `docker/docker-compose.yml` | Infra | Local orchestration for Backend, DB, Redis, and Worker. | `Docker` |
| **BE-INF::Docker::Nginx** | `docker/nginx.conf` | Infra | Nginx reverse proxy configuration. | `Nginx` |

### 6. Documentation Components
These are tracking codes for the documentation suite.

| Component ID | File Path | Category | Description |
| :--- | :--- | :--- | :--- |
| **DOC-EXT::Arch::Backend** | `docs/backend_architecture.md` | Arch | Backend architecture diagram/docs. |
| **DOC-EXT::Arch::Frontend** | `docs/frontend.md` | Arch | Frontend structure docs. |
| **DOC-EXT::Spec::API** | `docs/api.md` | Spec | API Endpoint definitions. |
| **DOC-EXT::Spec::Schema** | `docs/schema.md` | Spec | Database schema definitions. |
| **DOC-EXT::Spec::Client** | `docs/CLIENT_DASHBOARD_SPEC.md` | Spec | Requirements for Dashboard. |
| **DOC-EXT::Plan::Impl** | `docs/IMPLEMENTATION_PLAN.md` | Planning | Implementation roadmap. |
| **DOC-EXT::Plan::Status** | `IMPLEMENTATION_STATUS.md` | Planning | Status tracker (Root dir). |
| **DOC-EXT::Context::Prob** | `docs/problemsolved.md` | Context | Problem statement. |
| **DOC-EXT::Context::Scen** | `docs/scenario.md` | Context | Usage scenario. |
| **DOC-INT::BE::Root** | `backend/INFO.md` | Internal | Backend overview. |
| **DOC-INT::BE::API** | `backend/api/INFO.md` | Internal | API conventions. |
| **DOC-INT::BE::Core** | `backend/core/INFO.md` | Internal | Core utilities docs. |
| **DOC-INT::BE::Models** | `backend/models/INFO.md` | Internal | DB Models docs. |
| **DOC-INT::BE::Services** | `backend/services/INFO.md` | Internal | Service layer docs. |
| **DOC-INT::BE::Workers** | `backend/workers/INFO.md` | Internal | Celery worker docs. |
| **DOC-INT::AGT::Root** | `agent/INFO.md` | Internal | Agent overview. |
| **DOC-INT::FE::Root** | `frontend/INFO.md` | Internal | Frontend overview. |
| **DOC-EXT::Context::Backend** | `docs/backend.md` | Context | General backend context (distinct from `backend_architecture.md`). |
| **DOC-EXT::Context::FeatureMap** | `docs/featuremapping.md` | Context | Mapping of features to requirements. |
| **DOC-EXT::Context::Task** | `docs/task.md` | Context | Task breakdown or requirements list. |
| **DOC-EXT::Context::ScenarioApp** | `docs/application_scenario.md` | Context | Detailed application scenario. |
| **DOC-EXT::Meta::LLM** | `docs/LLM_INSTRUCTIONS.md` | Meta | Instructions for LLM interaction with codebase. |
| **DOC-EXT::Meta::Desc** | `docs/description.md` | Meta | High-level project description. |
| **BE-UTL::Pricing::Helper** | `backend/utils/pricing_helper.py` | Utility | AWS Price List API integration with Redis caching for dynamic regional pricing. Methods: `get_s3_storage_price()`, `get_data_transfer_price()`, `clear_cache()`. Features: 24-hour caching, fallback pricing, region mapping. Impact: Eliminates hardcoded pricing constants, ensures accuracy. | `boto3`, `redis` |
| **BE-SVC::Cost::SavingsPlan** | `backend/services/savings_plan_service.py` | Service | Logic to analyze Savings Plan utilization and recommendations. Methods: `get_savings_plan_coverage()`, `recommend_savings_plan()`. Features: Integrates with Cost Explorer, provides actionable insights. | `boto3`, `CostExplorer` |
| **DOC-INT::Utils::Info** | `backend/utils/INFO.md` | Internal | Documentation for backend utilities. |
| **DOC-INT::Scripts::Info** | `scripts/INFO.md` | Internal | Overview of the scripts directory. |
| **DOC-INT::Scripts::AWS** | `scripts/aws/INFO.md` | Internal | Documentation for AWS specific scripts. |
| **DOC-INT::Scripts::Deploy** | `scripts/deployment/INFO.md` | Internal | Documentation for deployment scripts. |
| **DOC-INT::Docker::Info** | `docker/INFO.md` | Internal | Documentation for Docker configuration. |
| **DOC-INT::Config::Info** | `config/INFO.md` | Internal | Documentation for general config. |
| **DOC-INT::Mig::Info** | `migrations/INFO.md` | Internal | Documentation for DB migrations. |
| **SYS-DOC::Root::Readme** | `README.md` | Doc | The main repository README entry point. |
| **SYS-DOC::Agent::Readme** | `agent/README.md` | Doc | Specific README for the Agent subsystem. |
| **SYS-CFG::Root::Pkg** | `package.json` | Config | Root-level Node package configuration. |
| **DOC-INT::BE::Scrapers** | `backend/scrapers/INFO.md` | Internal | Documentation for scrapers. |
| **DOC-INT::BE::Modules** | `backend/modules/INFO.md` | Internal | Documentation for optimization modules. |
| **DOC-INT::BE::Schemas** | `backend/schemas/INFO.md` | Internal | Documentation for Pydantic schemas. |
| **DOC-INT::FE::Src** | `frontend/src/INFO.md` | Internal | Frontend source overview. |
| **DOC-INT::FE::Comps** | `frontend/src/components/INFO.md` | Internal | Frontend components overview. |
| **DOC-INT::FE::Admin** | `frontend/src/components/admin/INFO.md` | Internal | Admin UI components docs. |
| **DOC-INT::FE::Audit** | `frontend/src/components/audit/INFO.md` | Internal | Audit UI components docs. |
| **DOC-INT::FE::Auth** | `frontend/src/components/auth/INFO.md` | Internal | Auth UI components docs. |
| **DOC-INT::FE::Clusters** | `frontend/src/components/clusters/INFO.md` | Internal | Cluster UI components docs. |
| **DOC-INT::FE::Dash** | `frontend/src/components/dashboard/INFO.md` | Internal | Dashboard UI components docs. |
| **DOC-INT::FE::Hiber** | `frontend/src/components/hibernation/INFO.md` | Internal | Hibernation UI components docs. |
| **DOC-INT::FE::Policies** | `frontend/src/components/policies/INFO.md` | Internal | Policy UI components docs. |
| **DOC-INT::FE::Settings** | `frontend/src/components/settings/INFO.md` | Internal | Settings UI components docs. |
| **DOC-INT::FE::Tpl** | `frontend/src/components/templates/INFO.md` | Internal | Template UI components docs. |
| **DOC-INT::FE::Hooks** | `frontend/src/hooks/INFO.md` | Internal | React hooks docs. |
| **DOC-INT::FE::Services** | `frontend/src/services/INFO.md` | Internal | Frontend API services docs. |
| **DOC-INT::FE::Utils** | `frontend/src/utils/INFO.md` | Internal | Frontend utility functions docs. |
| **DOC-PROJ::Index::Master** | `documents/00_master_index.md` | Management | Master index of project documents. |
| **DOC-PROJ::Catalog::FE** | `documents/01_frontend_catalog.md` | Management | Frontend Catalog. |
| **DOC-PROJ::Catalog::BE** | `documents/02_backend_catalog.md` | Management | Backend Catalog. |
| **DOC-PROJ::Ledger::Change** | `documents/03_change_ledger.md` | Management | Change log/ledger. |
| **DOC-PROJ::Gap::Analysis** | `documents/03_frontend_backend_gap_analysis.md` | Management | Gap analysis document. |

### 7. Miscellaneous System Components

| Component ID | File Path | Type | Description |
| :--- | :--- | :--- | :--- |
| **BE-PKG::Services::Init** | `backend/services/__init__.py` | Package | Python package init. |
| **BE-PKG::Core::Init** | `backend/core/__init__.py` | Package | Python package init. |
| **BE-PKG::Workers::Init** | `backend/workers/__init__.py` | Package | Python package init. |
| **BE-PKG::Scrapers::Init** | `backend/scrapers/__init__.py` | Package | Python package marker for scrapers. |
| **AGT-CFG::System::Reqs** | `agent/requirements.txt` | Config | Agent-specific python requirements. |
| **BE-INF::Docker::Front** | `docker/Dockerfile.frontend` | Infra | Dockerfile for React Frontend. |
| **BE-AST::Data::LoginFix** | `login_response.json` | Asset | JSON fixture for login testing. |

## Orphaned / Zombie Components
These components exist in the codebase but appear to be unused or unreferenced by the main application logic.

| ID | File Path | Status | Reason |
| :--- | :--- | :--- | :--- |
| **BE-SVC::Data::SpotRisk** | `backend/scrapers/spot_advisor_scraper.py` | **Real** | Connected via `pricing_task.py`. Called by `fetch_aws_pricing` Celery task (hourly). |


## Components with Uncertain / Pending Status
These components are present but their implementation status is questionable (potential mocks/stubs).

| ID | File Path | Status | Finding |
| :--- | :--- | :--- | :--- |
| ~~**BE-SVC::Account::Main**~~ | ~~`backend/services/account_service.py`~~ | ~~**Mock Logic**~~ | **RESOLVED (2026-01-12)**: Now uses `boto3.client('sts').assume_role()` to verify before saving. |
| **BE-SVC::Settings::Main** | `backend/services/settings_service.py` | **Mocked** | Uses in-memory dict `_MOCK_INTEGRATIONS_DB` for storage. |
| **BE-SVC::Metrics::Main** | `backend/services/metrics_service.py` | **Simplified** | Uses `costTimeSeries` hook logic (Frontend) and assumes 70% spot discount in `_calculate_savings`. |
| **BE-WRK::Task::Events** | `backend/workers/tasks/event_processor.py` | **Partial** | Logic exists but primary triggers (webhooks) seem missing from API routes. |
| **BE-CORE::Logic::Executor** | `backend/core/action_executor.py` | **Partial** | Spot Replacement implemented (AWS). Rightsizing/Consolidation pending. |

> **Note**: `HealthService` and `DecisionEngine` were audited and found to contain **Real** implementation logic, contrary to initial assumptions.
| **BE-MOD::Cost::RI** | `backend/models/ri_utilization.py` | Model | Reserved Instance Utilization and Waste Tracking. | `Base` |
| **BE-MOD::Cost::S3** | `backend/models/s3_analysis.py` | Model | S3 Intelligent-Tiering Analysis results. | `Base` |
| **BE-MOD::Cost::RDS** | `backend/models/rds_analysis.py` | Model | RDS Multi-AZ Analysis results. | `Base` |
| **BE-MOD::Cost::Transfer** | `backend/models/transfer_analysis.py` | Model | Data Transfer and NAT Gateway analysis. | `Base` |
| **BE-SVC::Cost::RI** | `backend/services/ri_analysis_service.py` | Service | Logic to analyze RI coverage and utilization. | `CostExplorer` |
| **BE-SVC::Cost::S3** | `backend/services/s3_tiering_service.py` | Service | Logic to analyze S3 buckets for tiering. | `CloudWatch`, `S3` |
| **BE-SVC::Cost::RDS** | `backend/services/rds_analysis_service.py` | Service | Logic to detect RDS Multi-AZ in non-prod. | `RDS`, `CloudWatch` |
| **BE-SVC::Cost::Transfer** | `backend/services/transfer_service.py` | Service | Logic to analyze transfer costs via Cost Explorer. | `CostExplorer` |
| **BE-API::Cost::RI** | `backend/api/ri_routes.py` | API | RI Analysis Endpoints. | `RIService` |
| **BE-API::Cost::S3** | `backend/api/s3_routes.py` | API | S3 Analysis Endpoints. | `S3Service` |
| **BE-API::Cost::RDS** | `backend/api/rds_routes.py` | API | RDS Analysis Endpoints. | `RDSService` |
| **BE-API::Cost::Transfer** | `backend/api/transfer_routes.py` | API | Data Transfer Analysis Endpoints. | `TransferService` |
