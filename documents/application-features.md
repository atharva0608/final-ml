# Application Feature Catalog

This document provides a current inventory of the Spot Optimizer platform's features across frontend + backend, including active capabilities, partial implementations, and hidden/zombie code.

## 1. Feature Catalog

### Legend
*   **Status**:
    *   🟢 **Active**: Fully implemented and exposed in UI.
    *   🟡 **Partial**: Backend exists but UI is incomplete/mocked or missing critical endpoints.
    *   🔴 **Hidden**: Fully implemented backend but no UI exposure.
    *   🧟 **Zombie**: Deprecated, redundant, or unused code.
*   **Roles**: **SA** (Super Admin), **OA** (Org Admin), **TL** (Team Lead), **MB** (Member).

| Category | Feature | Status | Description & Logic | SA | OA | TL | MB |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Authentication & Access** | **Login / Token Refresh / Password Change** | 🟢 | Email/password auth with JWT. Defaults: access 60m, refresh 30d (configurable in `config.py`). Bcrypt hashing (12 rounds). | ✅ | ✅ | ✅ | ✅ |
| | **Signup & Org Provisioning** | 🟢 | Organization auto-creation on signup; first user becomes ORG_ADMIN. | ✅ | ✅ | ❌ | ❌ |
| | **Pending Invite Acceptance** | 🟢 | Users created in `PENDING_INVITE` accept/decline via `/auth/invitation-response`; decline hard-deletes account. Dedicated `InviteAcceptance.jsx` page. | ✅ | ✅ | ✅ | ✅ |
| | **RBAC Enforcement (Roles + Access Levels)** | 🟢 | `RequireRole`, `RequireAccess`, `RequirePermission` middleware; CLIENT treated as ORG_ADMIN. 5-tier hierarchy: SUPER_ADMIN → ORG_ADMIN → CLIENT → TEAM_LEAD → MEMBER. Access levels: READ_ONLY, EXECUTION, FULL. | ✅ | ✅ | ✅ | ✅ |
| | **Role & Permission Matrix** | 🟢 | Custom roles + permission matrix editor (`/roles`). System roles read-only. `PermissionMatrix.jsx` UI. | ✅ | ✅ | ❌ | ❌ |
| **Organization & Teams** | **Organization Members** | 🟢 | Org admins add/remove/update members; direct user creation with default password `demo1234` and `must_reset_password`. | ✅ | ✅ | ❌ | ❌ |
| | **Team Management & Invites** | 🟢 | Create/rename teams, assign/remove members; Team Leads can invite to own team. Dedicated `TeamManagement.jsx` with `TeamFormModal.jsx`. | ✅ | ✅ | ✅ | ❌ |
| | **Team Details & Analytics** | 🟢 | Per-team detail page (`/teams/:teamId`) with member list, governance config, and team-level analytics. | ✅ | ✅ | ✅ | ✅ |
| | **Team Governance Policies** | 🟢 | Per-team approval toggles for destructive actions (CONNECT_ACCOUNT, TERMINATE_INSTANCE, etc.). `TeamGovernance.jsx` UI. | ✅ | ✅ | ✅ | ❌ |
| | **Member Permission Overrides** | 🟢 | Granular per-member overrides stored on team member record. `MemberPermissionsModal.jsx` for JSON-based customization. | ✅ | ✅ | ✅ | ❌ |
| **Onboarding & Cloud Accounts** | **Onboarding Flow** | 🟢 | Welcome → Connect AWS role → Verify; generates External ID and CloudFormation template. Multi-step wizard: `WelcomeStep` → `ConnectStep` → `VerifyStep` → `SuccessStep`. | ✅ | ✅ | ✅ | ❌ |
| | **AWS Account Linking** | 🟢 | Link/validate accounts with Role ARN + External ID; requires EXECUTION/FULL access level. Platform Identity verification via `SystemConfig` credentials. | ✅ | ✅ | ✅ | ❌ |
| | **Connection Info / External ID** | 🟢 | `/organization/connection-info` provides External ID + platform account ID. | ✅ | ✅ | ✅ | ✅ |
| | **CloudFormation Templates** | 🟢 | `read-only-role.yaml` and `full-access-role.yaml` templates served via `/templates/aws-onboarding`. Cross-account IAM role with confused deputy prevention. | ✅ | ✅ | ✅ | ❌ |
| **Dashboard & Analytics** | **KPI Dashboard & Widgets** | 🟢 | Role-based widget layouts via `widgetRegistry.js` and `roleDefaults.js`. Personalization per role (SUPER_ADMIN, ORG_ADMIN, TEAM_LEAD, MEMBER). Widgets: CostKPICard, SavingsKPICard, SavingsChart, FleetComposition, ActivityFeed, ClusterHealthCard, PendingApprovalsCard. | ✅ | ✅ | ✅ | ✅ |
| | **Realized vs Potential Savings** | 🟢 | `SavingsKPICard` shows net realized savings with percentage trend. `HeroMetricsPanel` shows total potential savings with trend comparison. `SavingsGauge` shows selected vs total potential savings as animated gauge. | ✅ | ✅ | ✅ | ✅ |
| | **Notification Badges** | 🟢 | `PendingApprovalsCard` shows count badge for pending approvals. Dashboard invitation modal with visual badge indicators. `Badge.jsx` multi-color system (gray, blue, green, yellow, red, purple, orange). | ✅ | ✅ | ✅ | ✅ |
| | **Fleet Composition** | 🟢 | Instance type distribution pie chart widget (`FleetComposition.jsx`). | ✅ | ✅ | ✅ | ✅ |
| | **Audit Log Viewer** | 🟢 | Query audit logs with filters (actor, event, resource); alias `/audit/logs` for UI. `AuditLog.jsx` component. | ✅ | ✅ | ✅ | ✅ |
| | **Team Analytics** | 🟢 | Team-level spend, waste, cost trends, member/account details. Consolidated team stats via `metricAPI`. | ✅ | ✅ | ✅ | ✅ |
| | **Account Analytics** | 🟢 | Dedicated per-account analytics page (`/accounts/:accountId/analytics`) with cost breakdown, waste analysis, and efficiency metrics. | ✅ | ✅ | ✅ | ✅ |
| **Cluster Management** | **Cluster Inventory & Details** | 🟢 | List, filter, and view cluster details. `ClusterList.jsx` + `ClusterDetails.jsx`. | ✅ | ✅ | ✅ | ✅ |
| | **Node Inventory** | 🟢 | Node list per cluster with utilization stats. `NodeList.jsx`. | ✅ | ✅ | ✅ | ✅ |
| | **Agent Install (Manual + Auto)** | 🟢 | Install script + auto-inject via `AgentInjectorService`: cross-account role assumption, EKS access entry creation, K8s token generation, automatic manifest deployment with RBAC. Helm chart support. | ✅ | ✅ | ❌ | ❌ |
| | **Agent RBAC & HOST_PROC** | 🟢 | Helm chart DaemonSet with ClusterRole (nodes, pods, eviction, configmaps, metrics API). HOST_PROC env var + `/proc` volume mount for host-level metrics. Host network mode enabled. | ✅ | ✅ | ❌ | ❌ |
| | **Connection Verification & Cost Updates** | 🟢 | Verify install, update resource cost metrics. | ✅ | ✅ | ❌ | ❌ |
| | **Cluster Disconnect** | 🟢 | `ClusterDisconnectModal.jsx` for disconnecting clusters with optional node deletion. | ✅ | ✅ | ❌ | ❌ |
| | **Agent Heartbeat & Status** | 🟢 | Periodic heartbeat from agent to backend. Last seen timestamp tracking per cluster. Status lifecycle: DISCOVERED → ACTIVE → DISCONNECTED. | ✅ | ✅ | ✅ | ✅ |
| **Optimization & Policies** | **Right Sizing** | 🟢 | Over-provisioned instance recommendations via `optimization` API. Dedicated `RightSizing.jsx` page. Rightsizer module with CPU/memory-based analysis. | ✅ | ✅ | ✅ | ✅ |
| | **Spot Optimization** | 🟢 | `SpotOptimizer` module: instance selection balancing price (0.6 weight) vs interruption risk (0.4 weight). Redis price caching. On-demand fallback. | ✅ | ✅ | ❌ | ❌ |
| | **Cluster Policies** | 🟢 | PolicyConfig UI + `policy_routes` for optimization constraints. Stored as JSONB in `cluster_policies` table. | ✅ | ✅ | ❌ | ❌ |
| | **Hibernation Scheduling** | 🟢 | Cron-based schedules per cluster. `HibernationSchedule.jsx` UI. Worker executes via `hibernation_worker.py`. | ✅ | ✅ | ❌ | ❌ |
| | **Template Builder** | 🟢 | Node template creation & defaults. `TemplateList.jsx` + `TemplateBuilder.jsx`. | ✅ | ✅ | ❌ | ❌ |
| | **Bin Packing Analysis** | 🟢 | `bin_packer.py` module for fragmentation analysis and node consolidation recommendations. | ✅ | ✅ | ❌ | ❌ |
| **Resource Hygiene (Cleanup)** | **Resource Scan & Inventory** | 🟢 | `/cleanup/scan` for orphaned resources across regions. 11 resource types: EC2 Instances, EBS Volumes, Snapshots, Elastic IPs, Load Balancers, NAT Gateways, ENIs, RDS, S3, IAM Users, IAM Access Keys. Redis-cached with 1-hour TTL and `force_refresh` bypass. | ✅ | ✅ | ✅ | ✅ |
| | **EBS Volume Categorization** | 🟢 | 4-way categorization: Active / Orphaned / Non-Compliant / Safe-to-Delete. Dynamic reason tagging (age, cost, compliance). | ✅ | ✅ | ✅ | ✅ |
| | **Dependency Checks** | 🟢 | Pre-delete dependency mapping (`/cleanup/check-dependencies`). | ✅ | ✅ | ✅ | ✅ |
| | **Authorize / Unauthorize / Cleanup Actions** | 🟢 | Executes actions; members may require approval (JIT). Returns 202 when approval required. | ✅ | ✅ | ✅ | ✅ |
| | **Resource Discovery for JIT** | 🟢 | `/cleanup/discover` endpoint for discovering resources within active JIT access windows. | ✅ | ✅ | ✅ | ✅ |
| | **Bulk Tagging Wizard** | 🟢 | Template/manual tagging with collision handling. `BulkTagWizard.jsx`. | ✅ | ✅ | ✅ | ✅ |
| | **Optimization Wizards (RI/S3/RDS)** | 🟢 | Guided UI flows for optimization review: `RIWizard.jsx`, `S3Wizard.jsx`, `RDSWizard.jsx`. | ✅ | ✅ | ✅ | ✅ |
| | **Cleanup Sidebar & Filtering** | 🟢 | `CleanupSidebar.jsx` for resource type navigation. `FilterPanel.jsx` for region, account, status filtering. | ✅ | ✅ | ✅ | ✅ |
| | **Live Savings Gauge** | 🟢 | Animated semi-circle gauge showing selected savings impact. `SavingsGauge.jsx`. | ✅ | ✅ | ✅ | ✅ |
| | **Cleanup Policies (Automated)** | 🟢 | Rule-based automated cleanup via `cleanup_policy_routes.py`. `CleanupPolicies.jsx` UI for policy CRUD. Conditions + actions model. | ✅ | ✅ | ❌ | ❌ |
| **Governance & Tagging** | **Governance Settings (Policy-as-Code)** | 🟢 | Org-level governance toggles and critical action rules. `GovernanceSettings.jsx` + `GovernanceManager.jsx` components. | ✅ | ✅ | ❌ | ❌ |
| | **Tag Policies (Enforcement)** | 🟡 | CRUD for required/advisory/regex policies via `TagPoliciesManager.jsx` + `TagPoliciesList.jsx`; compliance stats currently stubbed. | ✅ | ✅ | ❌ | ❌ |
| | **Tag Templates** | 🟢 | Reusable tag presets with dynamic variables. `TagTemplateManager.jsx` in Settings. | ✅ | ✅ | ✅ | ✅ |
| | **Auto-Tag Rules** | 🔴 | Backend routes (`/tags/rules`) with create, list, test, execute, preview, and variables endpoints. Dynamic value sources: static, user_email, user_id, org_id, creation_date, env_variable. Override behavior (SKIP_EXISTING/OVERWRITE). Resource scope filtering (compute/storage/database/network). **No UI wired.** | ✅ | ✅ | ❌ | ❌ |
| | **Smart Tags (TTL & Schedule)** | 🔴 | `smart_tag_routes.py` + `smart_tag_service.py` for TTL-based and schedule-based tag processing. Backend only. | ✅ | ✅ | ❌ | ❌ |
| | **Tag Management API** | 🟢 | Get/update/bulk-tag resources across EC2, EBS, S3, RDS; suggestions included via `tag_suggestion_service.py`. | ✅ | ✅ | ✅ | ✅ |
| **Tickets & Approvals (JIT)** | **Ticket Center** | 🟢 | Request/grant/approve/revoke access windows and action tickets. `TicketCenter.jsx` with role-based tabs (queue, incoming, my_requests). 3 ticket types: ACCESS_WINDOW, ACTION, SYSTEM_CLEANUP. | ✅ | ✅ | ✅ | ✅ |
| | **Delegated Access Grants** | 🟢 | Hierarchy support with `parent_id` for grant delegation. Consent workflow: PENDING → PENDING_CONSENT → APPROVED_ACTIVE → EXPIRED/REVOKED. Reason tracking: MAINTENANCE, INCIDENT, DEPLOYMENT, DEBUGGING, AUDIT, OTHER. | ✅ | ✅ | ✅ | ✅ |
| | **Access Request Modal** | 🟢 | Auto-triggered on 403 with `required_ticket`. Frontend intercepts via custom `governance:required` browser event dispatch. `TicketRequestModal.jsx` + `AccessRequestModal.jsx`. | ✅ | ✅ | ✅ | ✅ |
| | **Active Window Banner** | 🟢 | Countdown for approved access windows. `ActiveWindowBanner.jsx`. Real-time verification via `/tickets/active-window`. | ✅ | ✅ | ✅ | ✅ |
| **Admin & Platform** | **Admin Dashboard** | 🟢 | Platform overview: MRR, active users, clusters, spot instances. Live activity feed. `AdminDashboard.jsx` + `AdminOverview.jsx`. | ✅ | ❌ | ❌ | ❌ |
| | **Admin Organizations** | 🟢 | Organization management with enable/disable toggle. `AdminOrganizations.jsx`. | ✅ | ❌ | ❌ | ❌ |
| | **Admin Clients** | 🟢 | SaaS customer management. `AdminClients.jsx`. | ✅ | ❌ | ❌ | ❌ |
| | **Billing Overview** | 🟡 | API-backed with Stripe integration (portal session, webhook, subscription status). UI falls back to placeholder values when data missing. `AdminBilling.jsx`. | ✅ | ❌ | ❌ | ❌ |
| | **System Health** | 🟢 | Health checks + diagnostics. `AdminHealth.jsx` with service status, metrics, and incidents. `/health` (basic) and `/health/detailed` (DB, Redis, Celery, AWS, data freshness). Readiness and liveness probes. | ✅ | ❌ | ❌ | ❌ |
| | **Platform Health Widget** | 🟢 | Super admin dashboard widget showing API latency, DB connections, Redis memory, active workers, uptime. `PlatformHealthCard.jsx`. | ✅ | ❌ | ❌ | ❌ |
| | **Platform Settings** | 🟢 | Safe Mode and config toggles. `PlatformSettings.jsx` + `AdminConfig.jsx`. | ✅ | ❌ | ❌ | ❌ |
| | **Platform AWS Identity** | 🟢 | Connect platform AWS credentials for STS operations. Live status indicator with connect/disconnect flows. | ✅ | ❌ | ❌ | ❌ |
| | **Admin Lab** | 🟢 | Model registry and risk map UI. `AdminLab.jsx`. | ✅ | ❌ | ❌ | ❌ |
| | **Tenant List Widget** | 🟢 | Organization overview for super admins. `TenantListCard.jsx`. | ✅ | ❌ | ❌ | ❌ |
| **Advanced Analysis** | **RI Analysis** | 🟢 | RI overview, list, recommendations, analysis runs. `RIAnalysis.jsx` + `RIHealthCard.jsx`. Priority badges and monthly impact indicators. | ✅ | ✅ | ❌ | ❌ |
| | **Savings Plans Analysis** | 🔴 | Dedicated `SavingsPlanService` with utilization tracking, underutilization detection, monthly waste calculation, actual savings measurement. Lookback periods: 7/30/90 days. `savings_plan_utilization.py` model. **No dedicated UI page.** | ✅ | ✅ | ❌ | ❌ |
| | **Unified RI + Savings Plans Coverage** | 🔴 | Combined coverage report at `/ri/unified-coverage`. Merges RI and Savings Plans data into single view. Backend only. | ✅ | ✅ | ❌ | ❌ |
| | **S3 Analysis** | 🟡 | Overview + top opportunities with intelligent tiering recommendations. `S3Analysis.jsx` + `S3HealthCard.jsx`. Missing bucket list endpoint for pagination. | ✅ | ✅ | ❌ | ❌ |
| | **RDS Analysis** | 🟡 | Overview + top opportunities with Multi-AZ detection in non-prod. `RDSAnalysis.jsx` + `RDSHealthCard.jsx`. Missing instance list endpoint. | ✅ | ✅ | ❌ | ❌ |
| | **Transfer Analysis** | 🟡 | Overview + top opportunities for inter-AZ/region data transfer costs. `TransferAnalysis.jsx` + `TransferHealthCard.jsx`. List granularity limited. | ✅ | ✅ | ❌ | ❌ |
| **Settings** | **User Profile & Password** | 🟢 | `UserProfile.jsx` + `AccountSettings.jsx` for name and password changes. | ✅ | ✅ | ✅ | ✅ |
| | **Cloud Integrations** | 🟢 | AWS account management in settings. `CloudIntegrations.jsx` with account list, validation, and sync status. | ✅ | ✅ | ✅ | ❌ |
| | **Dashboard Preferences** | 🟢 | Widget layout preferences via `authAPI.updatePreferences()`. Role-based defaults with user customization. | ✅ | ✅ | ✅ | ✅ |
| **Kubernetes Agent** | **Metrics Collector** | 🟢 | `collector.py`: Node metrics (CPU, memory, pod count) from Kubernetes API. | ✅ | ✅ | ❌ | ❌ |
| | **Action Actuator** | 🟢 | `actuator.py`: Executes kubectl commands (cordon, drain, label). PDB validation, graceful shutdown. | ✅ | ✅ | ❌ | ❌ |
| | **Spot Interruption Poller** | 🟢 | `poller.py`: IMDS polling for 2-minute spot termination warnings. | ✅ | ✅ | ❌ | ❌ |
| | **WebSocket Client** | 🟢 | `websocket_client.py`: Real-time bidirectional communication with backend. | ✅ | ✅ | ❌ | ❌ |
| | **Dynamic Config Reload** | 🟢 | `config.py`: SIGHUP signal handler for runtime configuration reload. Dry-run mode support. | ✅ | ✅ | ❌ | ❌ |
| **ML & Intelligence** | **Spot Optimizer Engine** | 🟢 | `spot_optimizer.py` (MOD-SPOT-01): Instance selection with weighted scoring (price 0.6, risk 0.4). Redis price cache lookup. Opportunity detection. | ✅ | ✅ | ❌ | ❌ |
| | **Risk Tracker** | 🟢 | `risk_tracker.py`: Redis-backed global risk intelligence. Instance pool flagging system. | ✅ | ❌ | ❌ | ❌ |
| | **ML Model Server** | 🟢 | `ml_model_server.py`: ML model serving for predictions. `model_validator.py` for validation. | ✅ | ❌ | ❌ | ❌ |
| | **Lab Experiments** | 🔴 | `ExperimentLab.jsx` component exists but no route registered in `App.js` (wired under admin only at `/admin/lab`). A/B testing via `LabExperiment` model. | ✅ | ❌ | ❌ | ❌ |

---

## 2. Zombie & Redundant Code Analysis

These features exist in the codebase but are flagged for cleanup or repair.

| Component | Diagnosis | File Path | Recommendation | Reason |
| :--- | :--- | :--- | :--- | :--- |
| **Smart Tags** | 🧟 **Redundant** | `backend/api/smart_tag_routes.py` | **Delete** | Overlaps with `auto_tag_routes.py` and tag policy system. Appears legacy. |
| **Legacy Tag Template Manager** | 🧟 **Unused** | `frontend/src/components/policies/TagTemplateManager.jsx` | **Remove** | Replaced by settings `TagTemplateManager`; no imports. |
| **BulkTagEditor** | 🧟 **Unused** | `frontend/src/components/cleanup/BulkTagEditor.jsx` | **Remove** | Superseded by `BulkTagWizard`; no imports. |
| **InlineTagEditor** | 🧟 **Unused** | `frontend/src/components/cleanup/InlineTagEditor.jsx` | **Remove** | Superseded by `BulkTagWizard`; no imports. |
| **Experiment Lab (User-facing)** | 🔴 **Hidden** | `frontend/src/components/lab/ExperimentLab.jsx` | **Wire Up or Remove** | Component exists but no user-facing route registered in `App.js`. Admin-only at `/admin/lab`. |
| **S3 Bucket List** | 🟡 **Missing** | `backend/api/s3_routes.py` | **Fix** | Only `/overview` and `/analyze` exist; UI needs a list endpoint. |
| **RDS Instance List** | 🟡 **Missing** | `backend/api/rds_routes.py` | **Fix** | UI uses `top_opportunities`; no list endpoint for pagination. |
| **Transfer Details List** | 🟡 **Partial** | `backend/api/transfer_routes.py` | **Enhance** | Overview exists, but list granularity is limited to top opportunities. |
| **Tag Policy Compliance Stats** | 🟡 **Stubbed** | `backend/api/tag_policy_routes.py` | **Implement** | `compliance/stats` currently returns empty stats. |
| **Savings Plans UI** | 🔴 **Missing** | N/A | **Build** | `SavingsPlanService` and `savings_plan_utilization.py` model exist; no dedicated UI page. |
| **Unified Coverage UI** | 🔴 **Missing** | N/A | **Build** | `/ri/unified-coverage` endpoint exists; needs UI integration in RI Analysis page. |
| **Auto-Tag Rules UI** | 🔴 **Missing** | N/A | **Build** | Backend has complete CRUD + preview + test + execute + variables endpoints; no UI wired. |
| **Audit Log Export** | 🟡 **Stubbed** | `backend/api/audit_routes.py` | **Implement** | Export endpoint exists but returns stubbed data. |

---

## 3. Detailed Logic Specifications

### A. AWS Onboarding & Account Linking
1.  **Start:** User enters onboarding flow or Cloud Integrations.
2.  **Template:** Backend generates External ID and CloudFormation template (`/onboarding/aws-link` or `/onboarding/template`). Templates: `read-only-role.yaml` (read-only + pricing) and `full-access-role.yaml` (cleanup permissions).
3.  **Verify:** `/onboarding/verify` validates STS assume-role; account record is created. Platform Identity verified via `SystemConfig` credentials.
4.  **Discovery:** `ClusterService.discover_clusters` triggered automatically on successful validation. Background discovery worker runs every 5 minutes.

### B. JIT Access Enforcement & Ticketing
1.  **Enforcement:** `PermissionService.enforce()` blocks high-risk actions for non-admins.
2.  **Signal:** Backend raises `GovernanceError` with `required_ticket: true` (HTTP 403).
3.  **UI Intercept:** Frontend API interceptor dispatches custom `governance:required` browser event. `TicketRequestModal` opens automatically.
4.  **Ticket Types:** ACCESS_WINDOW (time-boxed access), ACTION (single action), SYSTEM_CLEANUP (automated cleanup).
5.  **Approval Workflow:** PENDING → PENDING_CONSENT → APPROVED_ACTIVE → EXPIRED/REVOKED.
6.  **Delegation:** Grants support hierarchy via `parent_id` for delegated access.
7.  **Reasons:** MAINTENANCE, INCIDENT, DEPLOYMENT, DEBUGGING, AUDIT, OTHER.
8.  **Active Window:** `/tickets/active-window` provides real-time verification. `ActiveWindowBanner.jsx` shows countdown.

### C. Cleanup Scan & Action Execution
1.  **Scan:** `/cleanup/scan/{account_id}` returns resources + summary across regions. Supports 11 resource types.
2.  **Caching:** Results cached in Redis with key `cleanup:scan:{account_id}:{regions}`, 1-hour TTL. `force_refresh` parameter bypasses cache.
3.  **Review:** UI filters by type/authorization state via `CleanupSidebar` + `FilterPanel`. `HeroMetricsPanel` shows 4 metrics (Potential Savings, Resource Allocation, Tag Health, Safety Assessment).
4.  **Execute:** `/cleanup/action` performs cleanup; returns 202 when approval is required.
5.  **Discover:** `/cleanup/discover` for resource discovery within active JIT windows.

### D. Tag Governance Stack
| Tool | Purpose | UI |
| :--- | :--- | :--- |
| **Tag Policies** | Enforcement rules (required/advisory/regex) | TagPoliciesManager + TagPoliciesList (Settings) |
| **Tag Templates** | Preset tags with dynamic variables | TagTemplateManager (Settings + Cleanup) |
| **Auto-Tag Rules** | Dynamic rule engine with 6 value sources (static, user_email, user_id, org_id, creation_date, env_variable) + preview + test | Backend only (no UI) |
| **Smart Tags** | TTL and schedule-based tag processing | Backend only (legacy, overlaps auto-tag) |
| **Tag Suggestions** | AI-powered tag suggestions via `tag_suggestion_service.py` | Integrated in cleanup tag flow |

### E. Agent Injection & Deployment
1.  **Cross-Account:** `AgentInjectorService` assumes customer IAM role via STS.
2.  **EKS Access:** Creates EKS access entry for backend role.
3.  **Token:** Generates OIDC-based Kubernetes token.
4.  **Deploy:** Deploys full agent stack (DaemonSet, ServiceAccount, ClusterRole, ConfigMap, Secret) via Kubernetes API.
5.  **RBAC:** ClusterRole grants: nodes, pods, pods/eviction, namespaces, services, configmaps (get/list/watch/patch/update/delete), deployments/replicasets/daemonsets/statefulsets (get/list/watch), metrics API (get/list).
6.  **Host Access:** HOST_PROC env var + `/proc` volume mount for host-level memory/CPU metrics.
7.  **Async:** Background task via `agent_tasks.py` for non-blocking installation.

### F. Savings Plans & RI Analysis
1.  **RI Analysis:** Utilization tracking, waste detection, recommendations. Full UI with `RIAnalysis.jsx`.
2.  **Savings Plans:** Dedicated `SavingsPlanService` with underutilization detection, monthly waste tracking, actual savings calculation. Lookback periods: 7/30/90 days.
3.  **Unified Coverage:** Combined RI + Savings Plans coverage report at `/ri/unified-coverage`. Backend only.

---

## 4. Middleware & Infrastructure
*   **CORS:** Dynamic origin allowlist in `api_gateway.py` + fallback headers for errors.
*   **Request Logging:** Logs Method, Path, Status, Duration, UserID + adds `X-Process-Time` header.
*   **Exception Handling:** Global handlers for `SpotOptimizerException`, validation errors, and 500s.
*   **Rate Limiting:** **Missing middleware**. Config exists (`API_RATE_LIMIT=100/min`, `API_TIMEOUT_SECONDS=30`) but no middleware is wired.
*   **Health Checks:** `/health` (basic) and `/health/detailed` (DB + Redis + Celery + AWS + data freshness). Readiness and liveness probes.
*   **JWT Defaults:** Access token 60 minutes; refresh token 30 days (configurable).
*   **WebSocket:** Endpoint for real-time agent communication in `api_gateway.py`.

---

## 5. Background Workers & Scheduled Tasks
| Worker | File | Schedule | Description |
| :--- | :--- | :--- | :--- |
| **Discovery** | `discovery.py` | Every 5 minutes | EKS cluster discovery across linked accounts |
| **Pricing (Spot)** | `pricing_task.py` | Every 5-10 minutes | Spot price collection via `describe_spot_price_history()` |
| **Pricing (On-Demand)** | `pricing_task.py` | Daily at 1:00 AM UTC | On-demand price collection via AWS Price List API |
| **Optimization** | `optimization.py` | Every 15 minutes | Spot replacement, opportunity detection, bin packing |
| **Hibernation** | `hibernation_worker.py` | Every minute | Checks `hibernation_schedules` table for actions |
| **Reports** | `report_worker.py` | Daily/weekly | Usage and savings reports |
| **Events** | `event_processor.py` | Continuous | K8s event processing (pod pending, etc.) |
| **Agent Injection** | `agent_tasks.py` | On-demand | Async cluster agent installation |
| **Health** | `health.py` | Periodic | Background health monitoring |

---

## 6. Redis Caching Strategy
| Cache Key Pattern | TTL | Purpose |
| :--- | :--- | :--- |
| `spot_price:*` | 10 minutes | Real-time spot pricing per region/instance |
| `ondemand_price:*` | 24 hours | On-demand pricing (daily refresh) |
| `cleanup:scan:{account}:{regions}` | 1 hour | Cleanup scan results per account/region |
| Celery task results | 1 day | Background task outcomes |
| Risk tracker data | Variable | Global spot interruption risk intelligence |
| **Memory Monitoring** | — | Redis memory usage tracked in health status |
| **Data Freshness** | — | Health check verifies cache TTL > 300s |

---

## 7. Feature Flags & Configuration
| Flag | Default | Description |
| :--- | :--- | :--- |
| Hibernation | Configurable | Enable/disable cluster hibernation feature |
| Karpenter | Configurable | Enable Karpenter-based node provisioning |
| ML Lab | Configurable | Enable ML experimentation features |
| Admin Impersonation | Configurable | Allow super admins to impersonate users |
| Safe Mode | Toggleable | Platform-wide safety toggle preventing destructive actions |
| Prometheus Metrics | Disabled | Opt-in metrics export |

---

## 8. Technology Stack Summary
| Layer | Technology | Version |
| :--- | :--- | :--- |
| **Backend** | FastAPI | 0.109.0 |
| **Database** | PostgreSQL + SQLAlchemy | 2.0 ORM |
| **Migrations** | Alembic | 1.13.1 |
| **Task Queue** | Celery + Redis | 5.3.6 |
| **Caching** | Redis | 5.0.1+ |
| **Auth** | JWT (python-jose) + Bcrypt | — |
| **Validation** | Pydantic | 2.5.3 |
| **AWS SDK** | Boto3 | 1.34.34 |
| **Frontend** | React | 18.2.0 |
| **Routing** | React Router DOM | 6 |
| **State** | Zustand | 4.4.7 |
| **HTTP Client** | Axios | — |
| **UI** | Tailwind CSS + Radix UI + Lucide | 3.3.0 |
| **Charts** | Recharts | 2.15.4 |
| **Animations** | Framer Motion | 10.16.4 |
| **Agent** | Python + kubernetes client | 29.0.0 |
| **Orchestration** | Kubernetes + Helm 3 | — |
| **Containers** | Docker + Docker Compose | — |
| **Billing** | Stripe (optional) | — |
| **Email** | SendGrid / AWS SES (optional) | — |

---

## 9. API Route Summary (100+ Endpoints)
| Prefix | Route File | Key Endpoints |
| :--- | :--- | :--- |
| `/api/v1/auth` | `auth_routes.py` | signup, login, refresh, me, password, invitation-response |
| `/api/v1/organization` | `organization_routes.py` | members, invitations, connection-info |
| `/api/v1/teams` | `team_routes.py` | CRUD, members, governance |
| `/api/v1/accounts` | `account_routes.py` | link, validate, sync |
| `/api/v1/clusters` | `cluster_routes.py` | list, details, install-agent, verify |
| `/api/v1/metrics` | `metrics_routes.py` | dashboard, cost, instances, time-series, team-stats |
| `/api/v1/cleanup` | `cleanup_routes.py` | scan, check-dependencies, action, discover |
| `/api/v1/cleanup-policies` | `cleanup_policy_routes.py` | CRUD for automated cleanup rules |
| `/api/v1/policies` | `policy_routes.py` | cluster optimization constraints |
| `/api/v1/templates` | `template_routes.py` | node templates, AWS onboarding template |
| `/api/v1/hibernation` | `hibernation_routes.py` | schedule CRUD |
| `/api/v1/tickets` | `ticket_routes.py` | create, active-window, delegate |
| `/api/v1/approvals` | `approval_routes.py` | approve, reject, revoke, grant-accept |
| `/api/v1/audit` | `audit_routes.py` | logs, export (stubbed) |
| `/api/v1/admin` | `admin_routes.py` | dashboard, clients, health, platform-identity |
| `/api/v1/ri` | `ri_routes.py` | overview, list, recommendations, analysis, unified-coverage |
| `/api/v1/s3` | `s3_routes.py` | overview, analyze |
| `/api/v1/rds` | `rds_routes.py` | overview, top-opportunities |
| `/api/v1/transfer` | `transfer_routes.py` | overview, top-opportunities |
| `/api/v1/tags/rules` | `auto_tag_routes.py` | create, list, test, execute, preview, variables |
| `/api/v1/tags/smart` | `smart_tag_routes.py` | TTL/schedule tag processing |
| `/api/v1/tags/management` | `tag_management_routes.py` | get/update/bulk tags |
| `/api/v1/tags/templates` | `tag_template_routes.py` | template CRUD |
| `/api/v1/tags/policies` | `tag_policy_routes.py` | policy CRUD, compliance/stats |
| `/api/v1/governance` | `governance_routes.py` | rules, compliance |
| `/api/v1/roles` | `role_routes.py` | CRUD, permissions matrix |
| `/api/v1/optimization` | `optimization_routes.py` | rightsizing recommendations |
| `/api/v1/lab` | `lab_routes.py` | experiments, models |
| `/api/v1/billing` | `billing_routes.py` | portal-session, webhook, subscription |
| `/api/v1/settings` | `settings_routes.py` | user/platform preferences |
| `/api/v1/health` | `health_routes.py` | basic, detailed |
| `/api/v1/agent` | `agent_routes.py` | register, deregister, heartbeat |
| `/api/v1/onboarding` | `onboarding_routes.py` | aws-link, verify, template |
| `/api/v1/installer` | `installer_routes.py` | public installer endpoints |
| `/api/v1/users` | `user_routes.py` | profile, management |

---

## 10. Database Models (36+ Models)
| Category | Models |
| :--- | :--- |
| **Auth & Users** | User, Organization, Team, Role, Permission, Invitation, APIKey |
| **AWS Integration** | Account, Cluster, Instance, NodeTemplate |
| **Cost & Optimization** | RIUtilization, SavingsPlanUtilization, S3Analysis, RDSAnalysis, TransferAnalysis, OptimizationJob, SpotPriceHistory, OnDemandPricing |
| **Governance** | Ticket, ApprovalRequest, AuditLog, AuthorizedResource, CleanupPolicy |
| **Tagging** | AutoTagRule, TagTemplate, TagPolicy |
| **Configuration** | ClusterPolicy, HibernationSchedule, SystemConfig, PlatformSettings |
| **ML/Lab** | LabExperiment, MLModel |
| **Agent** | AgentAction |

---

## 11. Frontend Routes (38 Total)

### Public Routes
| Path | Component |
| :--- | :--- |
| `/login` | Login.jsx |
| `/signup` | Signup.jsx |

### Protected Routes (MainLayout)
| Path | Component | Description |
| :--- | :--- | :--- |
| `/` → `/dashboard` | Dashboard.jsx | Role-customized widget dashboard |
| `/clusters` | ClusterList.jsx | Cluster inventory |
| `/policies` | PolicyConfig.jsx | Optimization policies |
| `/templates` | TemplateList.jsx | Node templates |
| `/right-sizing` | RightSizing.jsx | Instance rightsizing |
| `/hibernation` | HibernationSchedule.jsx | Cluster hibernation |
| `/audit` | AuditLog.jsx | Audit trail |
| `/cleanup` | CleanupDashboard.jsx | Resource hygiene |
| `/approvals` | TicketCenter.jsx | Ticket/approval center |
| `/settings` | Settings.jsx | Account, integrations, billing |
| `/settings/governance` | GovernanceSettings.jsx | Governance config |
| `/tag-management` | TagPoliciesManager.jsx | Tag policies |
| `/tag-templates` | TagTemplateManager.jsx | Tag templates |
| `/teams` | Teams.jsx | Team management |
| `/teams/:teamId` | TeamDetails.jsx | Team details |
| `/roles` | Roles.jsx | Role management |
| `/accounts/:accountId/analytics` | AccountAnalytics.jsx | Account analytics |
| `/ri-analysis` | RIAnalysis.jsx | RI analysis |
| `/s3-analysis` | S3Analysis.jsx | S3 analysis |
| `/rds-analysis` | RDSAnalysis.jsx | RDS analysis |
| `/transfer-analysis` | TransferAnalysis.jsx | Transfer analysis |
| `/invite-acceptance` | InviteAcceptance.jsx | Accept invitations |

### Admin Routes (SUPER_ADMIN Only)
| Path | Component |
| :--- | :--- |
| `/admin` | AdminDashboard.jsx |
| `/admin/clients` | AdminClients.jsx |
| `/admin/health` | AdminHealth.jsx |
| `/admin/lab` | AdminLab.jsx |
| `/admin/config` | AdminConfig.jsx |
| `/admin/organizations` | AdminOrganizations.jsx |
| `/admin/billing` | AdminBilling.jsx |
