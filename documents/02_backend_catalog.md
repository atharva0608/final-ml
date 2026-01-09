# Backend Component Catalog

**Date:** 2024-05-23
**Scope:** `backend/` Directory

## ID Naming Convention
`BE-[TYPE]::[MODULE]::[NAME]`
*   **Types:** `API` (Route), `SVC` (Service), `SCH` (Schema), `MOD` (Model), `WRK` (Worker), `UTL` (Utility), `CFG` (Config)

## Catalog

| ID (Unique Tracking Code) | File Path | Type | Function / Feature Description | Main Dependencies |
| :--- | :--- | :--- | :--- | :--- |
| **BE-SVC::Auth::Main** | `backend/services/auth_service.py` | Service | User authentication, signup, login, token management (JWT). | `User`, `Organization`, `crypto` |
| **BE-SVC::Admin::Main** | `backend/services/admin_service.py` | Service | Super Admin operations: Client management, Platform stats, Logic to "verify_super_admin". | `User`, `Cluster`, `Instance` |
| **BE-SVC::Organization::Main** | `backend/services/organization_service.py` | Service | Member management (Invite, Remove, Update Role). RBAC enforcement (Org Admin vs Team Lead). | `User`, `OrganizationInvitation` |
| **BE-SVC::Account::Main** | `backend/services/account_service.py` | Service | AWS Account linkage. Validates Role ARN, External ID. Manages Account status. | `Account`, `boto3` (implied) |
| **BE-SVC::Cluster::Main** | `backend/services/cluster_service.py` | Service | Cluster discovery (AWS EKS), registration, heartbeat tracking, and agent install script generation. | `Cluster`, `Account`, `boto3` |
| **BE-SVC::Template::Main** | `backend/services/template_service.py` | Service | Node Template CRUD. Logic for setting default templates. | `NodeTemplate`, `User` |
| **BE-SVC::Policy::Main** | `backend/services/policy_service.py` | Service | Policy management. Validates spot percentages, min/max nodes, and resource limits. | `ClusterPolicy`, `Cluster`, `NodeTemplate` |
| **BE-SVC::Hibernation::Main** | `backend/services/hibernation_service.py` | Service | Hibernation schedule logic. Validates cron-like schedule matrix and timezone. | `HibernationSchedule` |
| **BE-SVC::Metrics::Main** | `backend/services/metrics_service.py` | Service | Metrics aggregation (Cost, Savings, Usage). Generates Dashboard KPIs and Time Series data. | `Instance`, `OptimizationJob` |
| **BE-SVC::Audit::Main** | `backend/services/audit_service.py` | Service | Audit logging and querying. tracks actor, event, resource, outcome, and diffs. | `AuditLog` |
| **BE-SVC::Lab::Main** | `backend/services/lab_service.py` | Service | ML Experimentation (A/B Testing). Manage experiments, variants, and calculate results/winners. | `LabExperiment`, `MLModel` |
| **BE-API::Admin::Main** | `backend/api/admin_routes.py` | API | Super Admin Endpoints. List Orgs/Clients, Billing, Dashboard Stats, Platform Stats. | `AdminService` |
| **BE-API::Account::Main** | `backend/api/account_routes.py` | API | AWS Account Management. Link, List, Delete accounts. | `AccountService` |
| **BE-API::Cluster::Main** | `backend/api/cluster_routes.py` | API | Cluster Operations. Discover, Register, Connect (AWS), Agent Install, Heartbeat. | `ClusterService` |
| **BE-API::Organization::Main** | `backend/api/organization_routes.py` | API | Organization Management. List Members, Invite (ORG_ADMIN), Update Role, Remove Member. | `OrganizationService` |
| **BE-API::Policy::Main** | `backend/api/policy_routes.py` | API | Optimization Policy Management. Create, List, Update, Delete, Toggle policies. | `PolicyService` |
| **BE-API::Hibernation::Main** | `backend/api/hibernation_routes.py` | API | Hibernation Schedule Management. Create, List, Update, Delete schedules. | `HibernationService` |
| **BE-API::Metrics::Main** | `backend/api/metrics_routes.py` | API | Dashboard Metrics. Savings, Costs, Instance Stats, Time Series. | `MetricsService` |
| **BE-API::Audit::Main** | `backend/api/audit_routes.py` | API | Audit Log Querying. Filter logs by actor, event, resource type. | `AuditService` |
| **BE-API::Lab::Main** | `backend/api/lab_routes.py` | API | Lab Experiments. Create, List, Start, Stop, Get Results for A/B testing. | `LabService` |
| **BE-API::Health::System** | `backend/api/health_routes.py` | API | System Health Monitoring. Get detailed health status (DB, Redis, Workers). | `HealthService` |
| **BE-API::Optimization::Main** | `backend/api/optimization_routes.py` | API | Rightsizing Recommendations. Analyze cluster workloads and return resize advice. | `RightSizer` |
| **BE-MOD::System::Base** | `backend/models/base.py` | Model | Base Audit Mixin and DB connection setup. | `SQLAlchemy` |
| **BE-MOD::Auth::User** | `backend/models/user.py` | Model | User Table. | `Base` |
| **BE-MOD::Auth::Org** | `backend/models/organization.py` | Model | Organization Table. | `Base` |
| **BE-MOD::Auth::Invite** | `backend/models/invitation.py` | Model | Organization Invitation Table. | `Base` |
| **BE-MOD::Infra::Account** | `backend/models/account.py` | Model | AWS Account Table. | `Base` |
| **BE-MOD::Infra::Cluster** | `backend/models/cluster.py` | Model | Kubernetes Cluster Table. | `Base` |
| **BE-MOD::Infra::Instance** | `backend/models/instance.py` | Model | Node/Instance Table. | `Base` |
| **BE-MOD::Infra::Template** | `backend/models/node_template.py` | Model | Node Template Table. | `Base` |
| **BE-MOD::Policy::Main** | `backend/models/cluster_policy.py` | Model | Cluster Policy Table. | `Base` |
| **BE-MOD::Policy::Hibernation** | `backend/models/hibernation_schedule.py` | Model | Hibernation Schedule Table. | `Base` |
| **BE-MOD::Lab::Experiment** | `backend/models/lab_experiment.py` | Model | Lab Experiment Table. | `Base` |
| **BE-MOD::Lab::MLModel** | `backend/models/ml_model.py` | Model | Machine Learning Model Table. | `Base` |
| **BE-MOD::Ops::AuditLog** | `backend/models/audit_log.py` | Model | Audit Log Table. | `Base` |
| **BE-MOD::Ops::OptJob** | `backend/models/optimization_job.py` | Model | Optimization Job Table. | `Base` |
| **BE-MOD::Ops::Onboarding** | `backend/models/onboarding.py` | Model | Onboarding State Table. | `Base` |
| **BE-SCH::Auth::Main** | `backend/schemas/auth_schemas.py` | Schema | Pydantic Schemas for Auth (Login, Signup, UserProfile). | `Pydantic` |
| **BE-SCH::Admin::Main** | `backend/schemas/admin_schemas.py` | Schema | Pydantic Schemas for Admin (ClientList, PlatformStats). | `Pydantic` |
| **BE-SCH::Cluster::Main** | `backend/schemas/cluster_schemas.py` | Schema | Pydantic Schemas for Cluster (Create, Update, Response). | `Pydantic` |
| **BE-SCH::Template::Main** | `backend/schemas/template_schemas.py` | Schema | Pydantic Schemas for Template (Create, Update, Response). | `Pydantic` |
| **BE-SCH::Policy::Main** | `backend/schemas/policy_schemas.py` | Schema | Pydantic Schemas for Policy (Create, Update, Response). | `Pydantic` |
| **BE-SCH::Metrics::Main** | `backend/schemas/metric_schemas.py` | Schema | Pydantic Schemas for Metrics (DashboardKPIs, TimeSeries). | `Pydantic` |
| **BE-API::Onboarding::Main** | `backend/api/onboarding_routes.py` | API | Onboarding Endpoints. Get State, AWS Deep Link, Verify Role, Skip. | `OnboardingService` |
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
| **BE-MODL::Optimizer::BinPack** | `backend/modules/bin_packer.py` | Module | Pod Bin-packing logic for node reduction. | `Kubernetes` |
| **BE-MODL::ML::Server** | `backend/modules/ml_model_server.py` | Module | Serving logic for ML models. | `Tensorflow/PyTorch` |
| **BE-MODL::ML::Validator** | `backend/modules/model_validator.py` | Module | Validation logic for ML model inputs/outputs. | `Pandas` |
| **BE-MODL::Risk::Tracker** | `backend/modules/risk_tracker.py` | Module | Tracking spot instance interruption risk. | `History Data` |
| **BE-WRK::Task::Discovery** | `backend/workers/tasks/discovery.py` | Worker | Periodic cluster/resource discovery task. | `boto3` |
| **BE-WRK::Task::EventProc** | `backend/workers/tasks/event_processor.py` | Worker | Processing K8s events (pod pending, etc). | `Redis` |
| **BE-WRK::Task::Hibernate** | `backend/workers/tasks/hibernation_worker.py` | Worker | Executing hibernation schedules (Stop/Start nodes). | `HibernationService` |
| **BE-WRK::Task::Optimize** | `backend/workers/tasks/optimization.py` | Worker | Triggering optimization runs. | `SpotOptimizer` |
| **BE-WRK::Task::Report** | `backend/workers/tasks/report_worker.py` | Worker | Generating periodic usage/savings reports. | `MetricsService` |
| **BE-APP::Main::Entrypoint** | `main.py` | App | **Critical**: Main ASGI application entrypoint (FastAPI app). | `Backend` |
| **BE-API::Router::Root** | `backend/api/__init__.py` | API | Central API Router aggregating all feature routes. | `FastAPI` |
| **BE-MOD::System::Registry** | `backend/models/__init__.py` | Model | Model Registry exporting models for Alembic. | `SQLAlchemy` |
| **BE-WRK::Task::Registry** | `backend/workers/tasks/__init__.py` | Worker | Task Registry exporting Celery tasks. | `Celery` |
| **BE-CFG::DB::Alembic** | `alembic.ini` | Config | Configuration for Alembic DB migrations. | `Alembic` |
| **BE-MIG::Env::Main** | `migrations/env.py` | Config | Python environment script for migrations. | `Alembic` |
| **BE-MIG::Ver::001_Initial** | `migrations/versions/001_initial_schema.py` | Migration | Initial database schema creation script. | `Alembic` |
| **BE-MIG::Ver::002_Seed** | `migrations/versions/002_seed_data.py` | Migration | Script to seed database with default data. | `Alembic` |
| **BE-AST::AWS::IAM_Full** | `backend/templates/aws/full-access-role.yaml` | Asset | CloudFormation template for Full Access IAM Role. | `AWS` |
| **BE-AST::AWS::IAM_ReadOnly** | `backend/templates/aws/read-only-role.yaml` | Asset | CloudFormation template for Read-Only IAM Role. | `AWS` |
| **BE-SCR::Admin::Seed** | `scripts/seed_admin.py` | Script | Utility to programmatically create an admin user. | `Python` |
| **BE-SCR::Data::SeedDemo** | `scripts/seed_demo_data.py` | Script | Utility to populate system with demo data. | `Python` |
| **BE-SCR::AWS::LaunchSpot** | `scripts/aws/launch_spot.py` | Script | Standalone script to test Spot Instance launching. | `boto3` |
| **BE-SCR::AWS::TermInstance** | `scripts/aws/terminate_instance.py` | Script | Standalone script to test Instance termination. | `boto3` |
| **BE-SCR::Org::Migrate** | `scripts/migrate_to_organizations.py` | Script | Utility to migrate legacy user data to Organizations. | `Python` |
| **BE-API::Auth::Main** | `backend/api/auth_routes.py` | API | Authentication Endpoints (Login, Signup, Refresh Token). | `AuthService` |
| **BE-API::Template::Main** | `backend/api/template_routes.py` | API | Node Template Endpoints (Create, List, Delete templates). | `TemplateService` |
| **BE-SVC::Onboarding::Main** | `backend/services/onboarding_service.py` | Service | Business logic for tracking user onboarding steps. | `OnboardingState` |
| **BE-SVC::Data::Pricing** | `backend/scrapers/pricing_collector.py` | Service | Scrapes and normalizes AWS EC2 pricing data. | `boto3` |
| **BE-SVC::Data::SpotRisk** | `backend/scrapers/spot_advisor_scraper.py` | Service | Fetches AWS Spot Advisor data for interruption risks. | `requests` |
| **BE-SCH::Account::Main** | `backend/schemas/account_schemas.py` | Schema | Pydantic models for AWS Account validation. | `Pydantic` |
| **BE-SCH::Audit::Main** | `backend/schemas/audit_schemas.py` | Schema | Pydantic models for Audit Log responses. | `Pydantic` |
| **BE-SCH::Hibernation::Main** | `backend/schemas/hibernation_schemas.py` | Schema | Pydantic models for Hibernation Schedules. | `Pydantic` |
| **BE-SCH::Lab::Main** | `backend/schemas/lab_schemas.py` | Schema | Pydantic models for ML Experiments. | `Pydantic` |
| **BE-SCH::Organization::Main** | `backend/schemas/organization_schemas.py` | Schema | Pydantic models for Org members and invites. | `Pydantic` |
| **BE-API::Settings::Main** | `backend/api/settings_routes.py` | API | Settings Endpoints. Profile management and Integrations. | `SettingsService` |
| **BE-SVC::Settings::Main** | `backend/services/settings_service.py` | Service | Logic for user profile updates and integrations (Mocked). | `User`, `Mocks` |
| **BE-SCH::Settings::Main** | `backend/schemas/settings_schemas.py` | Schema | Pydantic models for Settings and Integrations. | `Pydantic` |
| **BE-WRK::Core::App** | `backend/workers/app.py` | Worker | Celery Application instance and configuration. | `Celery` |
| **BE-OPS::Deploy::Main** | `scripts/deployment/deploy.sh` | Script | Main deployment shell script. | `Bash` |
| **BE-OPS::Deploy::Setup** | `scripts/deployment/setup.sh` | Script | Environment setup shell script. | `Bash` |
| **BE-CFG::Deps::Main** | `requirements.txt` | Config | Python dependency manifest for the backend. | `Pip` |
| **BE-CFG::System::EnvExample** | `.env.example` | Config | Template for environment variables. | `Env` |
| **BE-MIG::TPL::Script** | `migrations/script.py.mako` | Config | Mako template used by Alembic. | `Mako` |
| **BE-SCH::System::Registry** | `backend/schemas/__init__.py` | Schema | Exports all schemas. | `Python` |
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
| **BE-SVC::Data::Pricing** | `backend/scrapers/pricing_collector.py` | **Zombie** | Not imported by any service, worker, or API. Pricing data is likely mocked or static. |
| **BE-SVC::Data::SpotRisk** | `backend/scrapers/spot_advisor_scraper.py` | **Zombie** | Not imported by Risk Tracker or Decision Engine. Real-time interruption data is missing. |
| **BE-MODL::Optimizer::Rightsize** | `backend/modules/rightsizer.py` | **Zombie** | Only imported in `__init__.py` but never used in `decision_engine` or `optimization` worker. |


## Components with Uncertain / Pending Status
These components are present but their implementation status is questionable (potential mocks/stubs).

| ID | File Path | Status | Finding |
| :--- | :--- | :--- | :--- |
| **BE-SVC::Account::Main** | `backend/services/account_service.py` | **Mock Logic** | "Link Account" stores credentials without verifying AWS connection via STS. |
| **BE-SVC::Cluster::Main** | `backend/services/cluster_service.py` | **Stubbed** | `discover_clusters` method returns empty list `[]` with TODO comment. |
| **BE-SVC::Metrics::Main** | `backend/services/metrics_service.py` | **Simplified** | Uses hardcoded 70% spot discount assumption in `_calculate_savings`. |
| **BE-WRK::Task::Events** | `backend/workers/tasks/event_processor.py` | **Partial** | Logic exists but primary triggers (webhooks) seem missing from API routes. |
| **BE-CORE::Logic::Executor** | `backend/core/action_executor.py` | **Partial / Stubbed** | Core flow exists, but specific actions (RightSize, Consolidate) are TODOs. |

> **Note**: `HealthService` and `DecisionEngine` were audited and found to contain **Real** implementation logic, contrary to initial assumptions.
