# �️ Complete Repository File Index
**Last Updated:** 2026-01-19
**Scope:** Exhaustive inventory of every file in the project.

> This document provides a detailed description of every file in the repository, explaining its purpose (**Why**), implementation details (**How**), and associated components/APIs.

---

## 📂 Root Directory
*   `main.py`: **Entry Point**.
    *   *Why*: Required by some PaaS loaders, imports `app` from `backend.core.api_gateway`.
*   `requirements.txt`: **Python Dependencies**.
    *   *Why*: PIP package list.
    *   *Includes*: `fastapi`, `uvicorn`, `sqlalchemy`, `asyncpg`, `boto3`, `celery`, `redis`.
*   `package.json`: **Node Dependencies**.
    *   *Why*: NPM package list & scripts.
    *   *Scripts*: `dev` (Vite), `build` (TSC + Vite), `lint`.
*   `rebuild.sh`: **Dev Utility**.
    *   *Why*: Quick script to `docker-compose down -v && docker-compose up --build`.
*   `start.sh`: **Runtime Script**.
    *   *Why*: Bootstraps the backend container (Migrations -> Seed -> Uvicorn).

---

## 📂 Backend (`backend/`)

### 🔌 API Layer (`backend/api/`)
*   `__init__.py`: Exports `api_router`. Registers all sub-routers.
*   `auth_routes.py`: **Identity Endpoints**.
    *   *APIs*: `/auth/login`, `/auth/signup`, `/auth/refresh`, `/auth/me`.
    *   *How*: Uses `OAuth2PasswordRequestForm` logic. Calls `AuthService`.
*   `account_routes.py`: **AWS Account Management**.
    *   *APIs*: `/accounts`, `/accounts/{id}/validate`.
    *   *How*: Interfaces with `AccountService` to store Role ARNs.
*   `admin_routes.py`: **Super Admin Control**.
    *   *APIs*: `/admin/stats`, `/admin/users`, `/admin/tenants`.
    *   *How*: Protected by `require_super_admin` dependency.
*   `cleanup_routes.py`: **Resource Hygiene**.
    *   *APIs*: `/cleanup/scan/{account_id}`, `/cleanup/action`.
    *   *How*: Triggers `CleanupService` scans via `ThreadPoolExecutor`.
*   `cluster_routes.py`: **Kubernetes Management**.
    *   *APIs*: `/clusters`, `/clusters/connect`.
    *   *How*: CRUD for Cluster model.
*   `governance_routes.py`: **Policy Enforcement**.
    *   *APIs*: `/governance/rules`, `/governance/autopilot`.
    *   *How*: Configures auto-cleanup thresholds.
*   `health_routes.py`: **System Monitoring**.
    *   *APIs*: `/health/system`.
    *   *How*: Pings Redis, DB, Celery to verify uptime.
*   `metric_routes.py`: **Analytics**.
    *   *APIs*: `/metrics/dashboard`, `/metrics/cost`, `/metrics/savings`.
    *   *How*: Aggregates SQL queries for frontend charts.
*   `optimization_routes.py`: **AI logic**.
    *   *APIs*: `/optimization/rightsizing/{id}`.
    *   *How*: Exposed `RightSizer` module recommendations.
*   `policy_routes.py`: **Cluster Policies**.
    *   *APIs*: `/policies`.
    *   *How*: Manage Karpenter/BinPack settings.
*   `ri_routes.py`: **RI Analysis**.
    *   *APIs*: `/ri/analysis`.
    *   *How*: Calculates Reserved Instance utilization.
*   `rds_routes.py`: **DB Analysis**.
    *   *APIs*: `/rds/analysis`.
    *   *How*: Scans for Single-AZ RDS instances.
*   `s3_routes.py`: **Storage Analysis**.
    *   *APIs*: `/s3/analysis`.
    *   *How*: Scans for old versions/multipart uploads.
*   `settings_routes.py`: **User Config**.
    *   *APIs*: `/settings/integrations`.
    *   *How*: Webhook management (Slack/PD).
*   `template_routes.py`: **Node Templates**.
    *   *APIs*: `/templates`.
    *   *How*: CRUD for instance launch references.
*   `ticket_routes.py`: **JIT Access**.
    *   *APIs*: `/tickets`, `/tickets/{id}/approve`.
    *   *How*: Manages time-bound access requests.
*   `transfer_routes.py`: **Network Cost**.
    *   *APIs*: `/transfer/analysis`.
    *   *How*: Analyzes cross-AZ data transfer.

### 🧠 Core (`backend/core/`)
*   `action_executor.py`: **Orchestrator**.
    *   *How*: Dispatches actions to `boto3` (AWS) or `kubernetes` (K8s). Contains logic logic for `spot_replacement` (implemented) and `right_sizing` (stub).
*   `api_gateway.py`: **App Factory**.
    *   *How*: Configures `FastAPI` app, CORS, Exception Handlers.
*   `config.py`: **Configuration**.
    *   *How*: `pydantic.BaseSettings` loading env vars (`DATABASE_URL`, `AWS_REGION`).
*   `database.py`: **Persistence**.
    *   *How*: `sqlalchemy` engine and session factory.
*   `decision_engine.py`: **AI Brain**.
    *   *How*: Resolves conflicts between modules (e.g. don't scale down if upgrading).
*   `dependencies.py`: **DI & Auth**.
    *   *How*: `get_current_user` extracts JWT from header & queries DB.
*   `exceptions.py`: **Error Classes**.
    *   *How*: Defines `ResourceNotFound`, `Unauthorized`, `PermissionDenied`.
*   `redis_client.py`: **Caching**.
    *   *How*: Returns `redis.Redis` pool.
*   `redis_pubsub.py`: **Realtime**.
    *   *How*: Async Redis subscriber for WebSockets.
*   `validators.py`: **Input Check**.
    *   *How*: Regex for ARNs, Names.

### 💾 Models (`backend/models/`)
*   `user.py`: **Identity**. `User` table (email, hash, role).
*   `organization.py`: **Tenant**. `Organization` table (name, plan).
*   `account.py`: **Cloud Link**. `Account` table (role_arn, external_id).
*   `team.py`: **RBAC Group**. `Team` table (parent_org).
*   `instance.py`: **Inventory**. `Instance` table (synced from AWS).
*   `audit_log.py`: **Compliance**. `AuditLog` table (Immutable action history).
*   `ticket.py`: **JIT Request**. `Ticket` table (status, expiry).
*   `approval.py`: **Governance**. `ApprovalRequest` table (pending actions).
*   `authorized_resource.py`: **Whitelist**. `AuthorizedResource` table (cleanup exemptions).
*   `base.py`: **SQLAlchemy Base**. Shared metadata.
*   `cluster.py`: **K8s Metadata**. `Cluster` table.
*   `cluster_policy.py`: **Config**. `ClusterPolicy` table (JSON settings).
*   `hibernation_schedule.py`: **Time Limits**. `HibernationSchedule` table (Cron matrix).
*   `lab_experiment.py`: **Testing**. `LabExperiment` table (A/B tests).
*   `ml_model.py`: **AI Artifacts**. `MLModel` table.
*   `node_template.py`: **Launch Specs**. `NodeTemplate` table.
*   `optimization_job.py`: **Async Jobs**. `OptimizationJob` table.
*   `permission.py`: **RBAC**. `Permission` table.
*   `role.py`: **RBAC**. `Role` table.
*   `system_config.py`: **Global Settings**. `SystemConfig` table.
*   `agent_action.py`: **K8s Queue**. `AgentAction` table.
*   `api_key.py`: **Agent Auth**. `ApiKey` table.
*   `rds_analysis.py`, `ri_utilization.py`, `s3_analysis.py`, `transfer_analysis.py`: **Analysis Tables**.

### 🕵️ Modules (`backend/modules/`)
*   `spot_optimizer.py`: **Spot Logic**. Selects best instance types.
*   `rightsizer.py`: **Sizing Logic**. Analyzes Prometheus metrics.
*   `risk_tracker.py`: **Stability**. Scores instance pools.
*   `bin_packer.py`: **Scheduling**. Optimizes pod placement.
*   `ml_model_server.py`: **Inference**. Hosts sklearn models.
*   `model_validator.py`: **Safety**. Checks model performance.

### 🏗️ Services (`backend/services/`)
*   `auth_service.py`: **Identity Logic**. Login/Signup/Refresh/Password.
*   `account_service.py`: **AWS Logic**. STS AssumeRole, Encryption, Link.
*   `cleanup_service.py`: **Hygiene Logic**. The "Scanner". (EC2/EBS/S3/RDS/Network).
*   `admin_service.py`: **Platform Logic**. Global stats/management.
*   `cluster_service.py`: **K8s Logic**. EKS Discovery, Agent Install.
*   `metrics_service.py`: **Data Logic**. Complex SQL aggregation for Dashboards.
*   `ticket_service.py`: **JIT Logic**. Grant/Revoke/Expire tickets.
*   `approval_service.py`: **Governance Logic**. Queue/Approve/Reject.
*   `organization_service.py`: **Tenant Logic**. Invite/Remove members.
*   `team_service.py`: **Group Logic**. Assign users, team governance.
*   `settings_service.py`: **Config Logic**. Integrations management.
*   `template_service.py`: **Spec Logic**. CRUD for Templates.
*   `policy_service.py`: **Rule Logic**. CRUD for Policies.
*   `hibernation_service.py`: **Schedule Logic**. Matrix validation.
*   `lab_service.py`: **Experiment Logic**. A/B test management.
*   `permission_service.py`: **RBAC Logic**. Permission checks.
*   `role_service.py`: **RBAC Logic**. Role management.
*   `ri_analysis_service.py`, `s3_tiering_service.py`, `rds_analysis_service.py`, `transfer_service.py`: **Specific Cost Logics**.

### 👷 Workers (`backend/workers/`)
*   `app.py`: **Celery App**. Configures Broker (Redis) and Beat Schedule.
*   `tasks/`:
    *   `discovery.py`: **Inventory Sync**. Calls `ClusterService.discover`.
    *   `pricing_task.py`: **Cost Sync**. Scrapes AWS Pricing.
    *   `event_processor.py`: **Real-time**. Handles Agent events (Interrupts).
    *   `hibernation_worker.py`: **Enforcer**. Turns off clusters.
    *   `optimization.py`: **AI Job**. Runs `SpotOptimizer`.
    *   `report_worker.py`: **Email**. Sends weekly summaries.

---

## 📂 Frontend (`frontend/src/`)

### 🧱 Components (`frontend/src/components/`)
*   **dashboard/**:
    *   `Dashboard.jsx`: Main View.
    *   `SavingsChart.jsx`: Visualization.
    *   `widgetRegistry.js`: Dynamic Widget loader.
*   **cleanup/**:
    *   `CleanupDashboard.jsx`: Hygiene View.
    *   `ResourceTable.jsx`: Data Grid with Actions.
    *   `SafetyScoreBadge.jsx`: Risk Indicator.
    *   `charts/`: Specialized charts for cleanup.
*   **tickets/**:
    *   `TicketCenter.jsx`: JIT Request Management.
    *   `TicketRequestModal.jsx`: User request form.
    *   `ActiveWindowBanner.jsx`: Access countdown.
*   **admin/**:
    *   `AdminDashboard.jsx`: Super Admin Home.
    *   `AdminOrganizations.jsx`: Tenant List.
*   **settings/**:
    *   `TeamManagement.jsx`: RBAC/Team View.
    *   `IntegrationSettings.jsx`: Webhooks.
    *   `GovernanceSettings.jsx`: Policy Toggles.
*   **auth/**:
    *   `Login.jsx`, `Signup.jsx`, `InviteAcceptance.jsx`.
*   **clusters/**:
    *   `ClusterList.jsx`: Inventory.
    *   `ClusterConnectModal.jsx`: Import Wizard.
*   **ri/**, **s3/**, **rds/**, **transfer/**:
    *   `*Analysis.jsx`: Specific Cost Views.
    *   `*HealthCard.jsx`: Widget summaries.
*   **shared/**:
    *   `Card.jsx`, `Button.jsx`, `Badge.jsx`: UI Primitives.
    *   `GaugeChart.jsx`: Reusable D3/Recharts component.

### 🚛 Logic (`frontend/src/`)
*   `hooks/useAuth.js`: **Auth State**. Manages User/Token.
*   `hooks/useDashboard.js`: **Data Fetching**. SWR-like logic for metrics.
*   `services/api.js`: **Network Layer**. Axios instance + Interceptors.
*   `store/useStore.js`: **Global State**. Zustand store.
*   `utils/formatters.js`: **Helpers**. Currency/Date formatting.

---

## � Scripts (`scripts/`)
*   `aws/`:
    *   `launch_spot.py`: **Automation**. Boto3 script to launch instances.
    *   `terminate_instance.py`: **Automation**. Boto3 script to kill instances.
*   `deployment/`:
    *   `deploy.sh`: **CI/CD**. Build & Push logic.
    *   `setup.sh`: **Init**. Local env setup.
*   `seed_rbac.py`: **Database Init**. Populates default Roles/Permissions.
*   `seed_demo_data.py`: **Dev Data**. Fills DB with fake stats.

## � Configuration (`config/`)
*   `INFO.md`: Explains environment variables.

## 📂 Docker (`docker/`)
*   `Dockerfile.backend`, `Dockerfile.frontend`: Container specs.
*   `docker-compose.yml`: Local orchestrator.

## � Documentation (`documents/`, `docs/`)
*   `00_master_index.md`: **Foundational Map**. (This file).
*   `01_frontend_catalog.md`: UI Inventory.
*   `02_backend_catalog.md`: Backend Inventory.
*   `03_change_ledger.md`: Changelog.
*   `04_application_permissions.md`: RBAC Matrix.
*   `05_logic.md`: Business Logic Deep Dive.
*   `06_api_info.md`: API Usage Matrix.
*   `07_known_issues.md`: Technical Debt.
