# All UI Components — Section-by-Section Breakdown

> Every visible element on every page, grouped by sidebar section.
> **"Backend Logic"** column is left blank for manual fill.
>
> **Legend for Data Source:** `Real API` = connected to live backend endpoint • `Mock API` = backend returns mock/dummy data • `Hardcoded` = static value in frontend code • `Demo Data` = seeded/demo data from backend • `Computed` = derived from other data on the client side
>
> **🔴 Red API Endpoint** = Endpoint exists in backend but is **NOT called** from the frontend (unused)

---

## 1. Dashboard

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Page Title** "Dashboard" | Text | Heading + role-based subtitle | Hardcoded | — | — | — | — | dashboard/Dashboard.jsx | App.js |
| **Customize Button** | Button | Toggles edit mode for widget layout | N/A | — | — | — | — | dashboard/Dashboard.jsx | App.js |
| **Refresh Button** | Button | Refreshes all dashboard data | Real API | `GET /api/v1/metrics/dashboard` | MetricsService.get_dashboard_kpis → queries Instances+CostExplorer, calculates total cost, savings, spot ratio, node counts | instances, clusters, daily_costs | instances.price, instances.lifecycle, clusters.monthly_cost, clusters.estimated_savings, clusters.node_count, clusters.spot_count | dashboard/Dashboard.jsx, api/metrics_routes.py, services/metrics_service.py | App.js |
| **Add Widget Button** (edit mode) | Button | Opens widget drawer | N/A | — | — | — | — | dashboard/Dashboard.jsx | App.js |
| **Save Layout Button** (edit mode) | Button | Persists custom widget layout | Real API | `PATCH /api/v1/users/me/preferences` | No backend logic — frontend saves to localStorage only | users (unused) | users.preferences (defined but unused by frontend) | dashboard/Dashboard.jsx, api/user_routes.py, services/auth_service.py | App.js |
| **Remove Widget Button** (edit mode) | Button | Red circle ✕ on each widget | N/A | — | — | — | — | dashboard/Dashboard.jsx | App.js |
| **Widget Drawer** | Card Grid | Available widgets for role, Add/Added state | Computed | — | — | — | — | dashboard/Dashboard.jsx | App.js |
| **Onboarding Card** | Card | CTA to connect AWS; shown when no accounts | Computed | — | — | — | — | dashboard/Dashboard.jsx | App.js |
| **Dynamic Widget Grid** | Card Grid | 4-col responsive grid of active widgets | Real API | Multiple (see widgets below) |  |  |  | dashboard/Dashboard.jsx | App.js |
| **Empty State** "No widgets added" | Display | Shown when layout empty; CTA to add widgets | Hardcoded | — | — | — | — | dashboard/Dashboard.jsx | App.js |

### Dashboard Widgets

| Widget | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **CostKPICard** | Card | Current month spend vs previous with trend | Real API | `GET /api/v1/metrics/dashboard` | MetricsService.get_dashboard_kpis → queries Instances+CostExplorer, calculates total cost, savings, spot ratio, node counts | instances, clusters, daily_costs | instances.price, instances.lifecycle, clusters.monthly_cost, clusters.estimated_savings, clusters.node_count, clusters.spot_count | dashboard/widgets/CostKPICard.jsx, api/metrics_routes.py, services/metrics_service.py | dashboard/widgetRegistry.js |
| **SavingsKPICard** | Card | Net savings + savings percentage | Real API | `GET /api/v1/metrics/dashboard` | MetricsService.get_dashboard_kpis → queries Instances+CostExplorer, calculates total cost, savings, spot ratio, node counts | instances, clusters, daily_costs | instances.price, instances.lifecycle, clusters.monthly_cost, clusters.estimated_savings, clusters.node_count, clusters.spot_count | dashboard/widgets/SavingsKPICard.jsx, api/metrics_routes.py, services/metrics_service.py | dashboard/widgetRegistry.js |
| **SavingsChart** | Graph | Line/area chart of cost over time | Real API | `GET /api/v1/metrics/cost/timeseries` | MetricsService.get_cost_time_series → daily cost data points over date range | daily_costs, instances | daily_costs.date, daily_costs.amount, instances.price | dashboard/widgets/SavingsChart.jsx, api/metrics_routes.py, services/metrics_service.py | dashboard/widgetRegistry.js |
| **FleetComposition** | Graph | Pie/donut of instance fleet breakdown | Hardcoded | 🔴 `GET /api/v1/metrics/instances` | MetricsService.get_instance_metrics → groups by lifecycle (SPOT/ON_DEMAND) | instances | instances.instance_type, instances.lifecycle, instances.cpu_util, instances.memory_util, instances.state | dashboard/widgets/FleetComposition.jsx, api/metrics_routes.py, services/metrics_service.py | dashboard/widgetRegistry.js |
| **ActivityFeed** | Table | Latest 5 audit log entries | Real API | `GET /api/v1/audit/logs` | AuditService.get_audit_logs → paginated DB query with filters (date, actor, event, outcome) | audit_logs | audit_logs.timestamp, audit_logs.actor_id, audit_logs.actor_name, audit_logs.event, audit_logs.resource, audit_logs.resource_type, audit_logs.outcome, audit_logs.ip_address | dashboard/widgets/ActivityFeed.jsx, api/audit_routes.py, services/audit_service.py | dashboard/widgetRegistry.js |
| **ClusterHealthCard** | Card | Cluster list with health indicators | Real API | `GET /api/v1/clusters` | ClusterService.list_clusters → RBAC filtered, pagination+sorting | clusters, accounts | clusters.name, clusters.region, clusters.status, clusters.node_count, clusters.monthly_cost, accounts.aws_account_id | dashboard/widgets/ClusterHealthCard.jsx | dashboard/widgetRegistry.js |
| **PendingApprovalsCard** | Card | Pending JIT requests summary | Hardcoded | 🔴 `GET /api/v1/approvals/` | ApprovalService.list_approvals → RBAC filtered | approvals, users | approvals.status, approvals.user_id, approvals.type, approvals.feature_id, approvals.created_at, approvals.expires_at | dashboard/widgets/PendingApprovalsCard.jsx, api/approval_routes.py, services/approval_service.py | dashboard/widgetRegistry.js |
| **PlatformHealthCard** (Super Admin) | Card | Uptime %, active workers | Hardcoded | 🔴 `GET /api/v1/admin/health` | No service logic — route stub only | — | — | dashboard/widgets/PlatformHealthCard.jsx, api/admin_routes.py, services/organization_service.py | dashboard/widgetRegistry.js |
| **TenantListCard** (Super Admin) | Card | Organization/tenant list | Real API | `GET /api/v1/admin/clients` | AdminService.list_clients → queries all Organizations with user counts | organizations, users | organizations.id, organizations.name, organizations.status | dashboard/widgets/TenantListCard.jsx, api/admin_routes.py, services/organization_service.py | dashboard/widgetRegistry.js |

### Dashboard Modals

| Modal | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **InvitationModal** | Modal | Accept/Decline org invitation | Real API | `POST /api/v1/auth/invitation-response` | OrganizationService.accept_invitation → validates token, creates User with must_reset_password=True | users, organizations | users.email, users.password_hash, users.role, users.organization_id, users.must_reset_password | auth/InviteAcceptance.jsx, api/auth_routes.py, services/auth_service.py | App.js |
| **AccessRequestModal** | Modal | JIT access request for restricted roles | Real API | `POST /api/v1/approvals/jit-request` | ApprovalService.create_jit_request → creates Approval with JIT_ACCESS type | approvals | approvals.user_id, approvals.type, approvals.feature_id, approvals.jit_scope, approvals.reason_category, approvals.duration_hours, approvals.status | approvals/AccessRequestModal.jsx, api/approval_routes.py, services/approval_service.py | dashboard/Dashboard.jsx |

---

## 2. Approvals

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Page Title** | Text | "Access Governance" / "Access Requests" (role-based) | Hardcoded | — | — | — | — | pages/Approvals.jsx | App.js |
| **Grant / Request Access Button** | Button | Opens TicketRequestModal | N/A | — | — | — | — | approvals/TicketRequestModal.jsx | App.js, governance/PermissionGate.jsx, pages/Approvals.jsx |
| **Active JIT Banner** | Display | Shows currently active JIT grants | Real API | `GET /api/v1/approvals/active-window` | ApprovalService.get_active_window → APPROVED_ACTIVE where expires_at > now | approvals | approvals.status, approvals.expires_at | approvals/ActiveWindowBanner.jsx, api/approval_routes.py, services/approval_service.py | — |
| **Pending Grants Alert** (purple) | Display | Action Required banner for PENDING_CONSENT | Real API | `GET /api/v1/approvals/` | ApprovalService.list_approvals → RBAC filtered | approvals, users | approvals.status, approvals.user_id, approvals.type, approvals.feature_id, approvals.created_at, approvals.expires_at | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |

### Stats Summary (Admin Only)

| Stat Card | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Pending Requests** (yellow) | Card | Count of PENDING tickets | Computed | `GET /api/v1/approvals/` | ApprovalService.list_approvals → RBAC filtered | approvals, users | approvals.status, approvals.user_id, approvals.type, approvals.feature_id, approvals.created_at, approvals.expires_at | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |
| **Active Grants** (green) | Card | Count of APPROVED_ACTIVE tickets | Computed | `GET /api/v1/approvals/` | ApprovalService.list_approvals → RBAC filtered | approvals, users | approvals.status, approvals.user_id, approvals.type, approvals.feature_id, approvals.created_at, approvals.expires_at | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |
| **Awaiting Consent** (purple) | Card | Count of PENDING_CONSENT tickets | Computed | `GET /api/v1/approvals/` | ApprovalService.list_approvals → RBAC filtered | approvals, users | approvals.status, approvals.user_id, approvals.type, approvals.feature_id, approvals.created_at, approvals.expires_at | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |

### Tabs

| Tab | Type | Role | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Pending Requests** | Tab | ORG_ADMIN | Real API | `GET /api/v1/approvals/` | ApprovalService.list_approvals → RBAC filtered | approvals, users | approvals.status, approvals.user_id, approvals.type, approvals.feature_id, approvals.created_at, approvals.expires_at | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |
| **Active Grants** | Tab | ORG_ADMIN | Real API | `GET /api/v1/approvals/` | ApprovalService.list_approvals → RBAC filtered | approvals, users | approvals.status, approvals.user_id, approvals.type, approvals.feature_id, approvals.created_at, approvals.expires_at | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |
| **Incoming Requests** | Tab | TEAM_LEAD | Real API | `GET /api/v1/approvals/` | ApprovalService.list_approvals → RBAC filtered | approvals, users | approvals.status, approvals.user_id, approvals.type, approvals.feature_id, approvals.created_at, approvals.expires_at | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |
| **Active Team Access** | Tab | TEAM_LEAD | Real API | `GET /api/v1/approvals/` | ApprovalService.list_approvals → RBAC filtered | approvals, users | approvals.status, approvals.user_id, approvals.type, approvals.feature_id, approvals.created_at, approvals.expires_at | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |
| **My Outgoing Requests** | Tab | TEAM_LEAD | Real API | `GET /api/v1/approvals/my-jit-approvals` | ApprovalService.get_active_jit_approvals → filters by user_id + JIT type | approvals | approvals.user_id, approvals.type, approvals.status | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |
| **My Requests** | Tab | MEMBER | Real API | `GET /api/v1/approvals/my-jit-approvals` | ApprovalService.get_active_jit_approvals → filters by user_id + JIT type | approvals | approvals.user_id, approvals.type, approvals.status | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |

### Tickets Table

| Column | Type | What It Shows | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Type** | Display | Colored dot + feature name + risk badge | Real API | `GET /api/v1/approvals/` | ApprovalService.list_approvals → RBAC filtered | approvals, users | approvals.status, approvals.user_id, approvals.type, approvals.feature_id, approvals.created_at, approvals.expires_at | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |
| **Requester** (admin only) | Text | User email | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Reason** | Text | Category badge + reason text | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Duration** | Text | Hours (e.g. "4h") | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Status** | Display | Colored badge: Active/Pending/Revoked/etc | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Created** | Text | Relative time + absolute date | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Expires** (active_grants tab) | Text | Time remaining or "Expired" | Computed | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Approve Button** | Button | Approve pending request | Real API | `POST /api/v1/approvals/{id}/approve` | ApprovalService.approve → sets APPROVED_ACTIVE, calculates expires_at, SSE broadcast | approvals | approvals.status, approvals.approver_id, approvals.approved_at, approvals.expires_at | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |
| **Reject Button** | Button | Reject pending request | Real API | `POST /api/v1/approvals/{id}/reject` | ApprovalService.reject → sets REJECTED, validates approver role | approvals | approvals.status, approvals.approver_id | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |
| **Revoke Button** | Button | Revoke active grant | Real API | `POST /api/v1/approvals/{id}/revoke` | ApprovalService.revoke → sets REVOKED, clears expires_at, SSE broadcast | approvals | approvals.status, approvals.expires_at | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |
| **Accept Button** | Button | Accept consent-pending grant | Real API | `POST /api/v1/approvals/{id}/accept` | ApprovalService.accept_grant → sets APPROVED_ACTIVE with time window | approvals | approvals.status, approvals.activated_at, approvals.expires_at | pages/Approvals.jsx, api/approval_routes.py, services/approval_service.py | App.js |

### Approvals Modals

| Modal | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **TicketRequestModal** | Modal | Create access request form | Real API | `POST /api/v1/approvals/` + `POST /api/v1/approvals/jit-request` | ApprovalService.create_jit_request → creates Approval with JIT_ACCESS type | approvals | approvals.user_id, approvals.type, approvals.feature_id, approvals.jit_scope, approvals.reason_category, approvals.duration_hours, approvals.status | approvals/TicketRequestModal.jsx, api/approval_routes.py, services/approval_service.py | App.js, governance/PermissionGate.jsx, pages/Approvals.jsx |

---

## 3. Teams

### Page-Level Tabs

| Tab | Type | What It Renders | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Team Structure** | Tab | TeamManagement component | N/A | — | — | — | — | pages/Approvals.jsx | App.js |
| **Roles & Policies** (admin) | Tab | Roles component | N/A | — | — | — | — | pages/Approvals.jsx | App.js |

### Members Sub-Tab

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Add Member Button** | Button | Opens invite modal | N/A | — | — | — | — | settings/TeamManagement.jsx | pages/Teams.jsx |
| **Team Filter Dropdown** | Dropdown | Filters by team | Computed | — | — | — | — | settings/TeamManagement.jsx | pages/Teams.jsx |
| **ACTIVE / INVITED Toggle** | Button | Switches member filter | N/A | — | — | — | — | settings/TeamManagement.jsx | pages/Teams.jsx |
| **Search Box** | Input | Search by name/email | N/A | — | — | — | — | settings/TeamManagement.jsx | pages/Teams.jsx |

#### Members Table

| Column | Type | What It Shows | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Name** | Display | Avatar + full name + email | Real API | `GET /api/v1/organization/members` | OrganizationService.list_members → all Users in organization | users, teams, roles | users.email, users.full_name, users.role, users.status, users.team_id | settings/TeamManagement.jsx, api/organization_routes.py, services/organization_service.py | pages/Teams.jsx |
| **Email** | Text | Email address | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Team** | Display | Team name badge | Real API | `GET /api/v1/teams/` | TeamService.get_teams_for_user → RBAC filtered | teams, users | teams.id, teams.name, users.team_id (count) | settings/TeamManagement.jsx, api/team_routes.py, services/team_service.py | pages/Teams.jsx |
| **Access** | Display | Role badge or "Custom Policy" | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Actions Menu** (3-dot) | Dropdown | Configure Access / Move to Team / Make Inactive | N/A | — | — | — | — | settings/TeamManagement.jsx | pages/Teams.jsx |
| **Configure Access** | Button | Opens edit access modal | N/A | — | — | — | — | settings/TeamManagement.jsx | pages/Teams.jsx |
| **Move to Team** | Button | Opens move modal | Real API | `POST /api/v1/teams/{id}/assign` | TeamService.assign_member → RBAC check, updates User.team_id | users, teams | users.team_id | settings/TeamManagement.jsx, api/team_routes.py, services/team_service.py | pages/Teams.jsx |
| **Make Inactive** | Button | Opens delete confirmation | Real API | `DELETE /api/v1/organization/members/{id}` | OrganizationService.update_member_role → enforces hierarchy | users | users.role, users.access_level | settings/TeamManagement.jsx, api/organization_routes.py, services/organization_service.py | pages/Teams.jsx |

### Teams Sub-Tab

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **New Team Button** | Button | Opens create team modal | N/A | — | — | — | — | settings/TeamManagement.jsx | pages/Teams.jsx |
| **Team Cards** | Card Grid | Name, ID, member count, progress bar | Real API | `GET /api/v1/teams/` | TeamService.get_teams_for_user → RBAC filtered | teams, users | teams.id, teams.name, users.team_id (count) | settings/TeamManagement.jsx, api/team_routes.py, services/team_service.py | pages/Teams.jsx |

### Roles & Permissions Sub-Tab

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **New Role Button** | Button | Opens role editor modal | N/A | — | — | — | — | pages/Roles.jsx | App.js, pages/Teams.jsx |
| **Roles Table** | Table | Role name, description, module permissions (ALL/SOME/-) | Real API | `GET /api/v1/roles` + `GET /api/v1/roles/permissions` | RoleService.list_roles + list_permissions | roles, permissions, role_permissions | roles.name, roles.type, permissions.slug, permissions.module | pages/Roles.jsx | App.js, pages/Teams.jsx |
| **Edit Role Button** (custom) | Button | Opens role editor | N/A | — | — | — | — | pages/Roles.jsx | App.js, pages/Teams.jsx |
| **Delete Role Button** (custom) | Button | Deletes custom role | Real API | `DELETE /api/v1/roles/{id}` | RoleService.delete_role → blocks system role deletion | roles | roles.id, roles.type | pages/Roles.jsx, api/role_routes.py, services/role_service.py | App.js, pages/Teams.jsx |

### Teams Modals

| Modal | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Invite Modal** | Modal | Full name, email, role/policy, team, PermissionMatrix | Real API | `POST /api/v1/teams/{id}/invite` | TeamService.invite_member → creates PENDING_INVITE User with default password | users, teams | users.email, users.password_hash, users.role, users.status, users.team_id, users.must_reset_password | policies/PermissionMatrix.jsx, api/team_routes.py, services/team_service.py | pages/Roles.jsx, settings/TeamManagement.jsx |
| **Configure Access Modal** | Modal | Edit role or custom permissions | Real API | `PATCH /api/v1/organization/members/{id}` + `POST /api/v1/users/{id}/permissions` + `POST /api/v1/roles/assign` | OrganizationService.update_member_role → enforces hierarchy | users | users.role, users.access_level | settings/MemberPermissionsModal.jsx, api/organization_routes.py, services/organization_service.py | pages/TeamDetails.jsx |
| **Move Team Modal** | Modal | Member email, team dropdown | Real API | `POST /api/v1/teams/{id}/assign` | TeamService.assign_member → RBAC check, updates User.team_id | users, teams | users.team_id | settings/TeamManagement.jsx, api/team_routes.py, services/team_service.py | pages/Teams.jsx |
| **Create Team Modal** | Modal | Team name input | Real API | `POST /api/v1/teams/` | TeamService.create_team → admin-only | teams | teams.name, teams.organization_id | settings/TeamManagement.jsx, api/team_routes.py, services/team_service.py | pages/Teams.jsx |
| **Delete Confirmation** | Modal | Confirm member removal | Real API | `DELETE /api/v1/organization/members/{id}` | OrganizationService.update_member_role → enforces hierarchy | users | users.role, users.access_level | settings/TeamManagement.jsx, api/organization_routes.py, services/organization_service.py | pages/Teams.jsx |
| **Role Editor Modal** | Modal | Name, description, PermissionMatrix | Real API | `POST /api/v1/roles` + `PUT /api/v1/roles/{id}` | RoleService.update_role → updates name/description/permissions | roles, role_permissions | roles.name, roles.description | policies/PermissionMatrix.jsx | pages/Roles.jsx, settings/TeamManagement.jsx |
| **Team Details Modal** | Modal | Members, Resources, Monthly Cost | Real API | `GET /api/v1/teams/{id}/stats` | TeamService.get_team_stats → member count | users, teams | teams.id, users.team_id (count) | pages/TeamDetails.jsx, api/team_routes.py, services/team_service.py | App.js |

### Team Details Page (/teams/:id)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Team Header** | Text | Team name, created date | Real API | `GET /api/v1/teams/{id}` | TeamService → returns Team by ID | teams | teams.id, teams.name, teams.created_at | pages/Teams.jsx, api/team_routes.py, services/team_service.py | App.js |
| **Stats Cards** | Card | Members, Clusters, Monthly Cost, Savings | Real API | `GET /api/v1/teams/{id}/stats` | TeamService.get_team_stats → member count | users, teams | teams.id, users.team_id (count) | pages/Teams.jsx, api/team_routes.py, services/team_service.py | App.js |
| **Members List** | Table | Name, email, role badge | Real API | (included in stats) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Cost Breakdown** | Graph | Pie chart of cost by service | Real API | `GET /api/v1/metrics/teams/{id}/summary` | MetricsService.get_team_consolidated_stats → team cost/savings aggregation | users, instances, clusters, teams | teams.id, users.team_id, clusters.monthly_cost | pages/Teams.jsx, api/metrics_routes.py, services/metrics_service.py | App.js |

### Roles & Policies Tab (Top-Level)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Role Cards Grid** | Card Grid | Role name, System/Custom badge, permission count | Real API | `GET /api/v1/roles` | RoleService.list_roles + list_permissions | roles, permissions, role_permissions | roles.name, roles.type, permissions.slug, permissions.module | pages/Teams.jsx | App.js |
| **Role Editor** | Display | PermissionMatrix + Save Changes | Real API | `PUT /api/v1/roles/{id}` | RoleService.update_role → updates name/description/permissions | roles, role_permissions | roles.name, roles.description | policies/PermissionMatrix.jsx, api/role_routes.py, services/role_service.py | pages/Roles.jsx, settings/TeamManagement.jsx |

---

## 4. Clusters

### KPI Strip

| KPI Card | Type | What It Shows | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **CostKPI** | Card | Total monthly cost, trend | Real API | `GET /api/v1/metrics/dashboard` | MetricsService.get_dashboard_kpis → queries Instances+CostExplorer, calculates total cost, savings, spot ratio, node counts | instances, clusters, daily_costs | instances.price, instances.lifecycle, clusters.monthly_cost, clusters.estimated_savings, clusters.node_count, clusters.spot_count | clusters/ClusterList.jsx, api/metrics_routes.py, services/metrics_service.py | App.js |
| **NodesKPI** | Card | Total nodes, spot vs on-demand | Real API | `GET /api/v1/metrics/dashboard` | MetricsService.get_dashboard_kpis → queries Instances+CostExplorer, calculates total cost, savings, spot ratio, node counts | instances, clusters, daily_costs | instances.price, instances.lifecycle, clusters.monthly_cost, clusters.estimated_savings, clusters.node_count, clusters.spot_count | clusters/ClusterList.jsx, api/metrics_routes.py, services/metrics_service.py | App.js |
| **ResourceKPI (CPU)** | Card | Total vCPU | Real API | `GET /api/v1/metrics/dashboard` | MetricsService.get_dashboard_kpis → queries Instances+CostExplorer, calculates total cost, savings, spot ratio, node counts | instances, clusters, daily_costs | instances.price, instances.lifecycle, clusters.monthly_cost, clusters.estimated_savings, clusters.node_count, clusters.spot_count | clusters/ClusterList.jsx, api/metrics_routes.py, services/metrics_service.py | App.js |
| **ResourceKPI (Memory)** | Card | Total memory | Real API | `GET /api/v1/metrics/dashboard` | MetricsService.get_dashboard_kpis → queries Instances+CostExplorer, calculates total cost, savings, spot ratio, node counts | instances, clusters, daily_costs | instances.price, instances.lifecycle, clusters.monthly_cost, clusters.estimated_savings, clusters.node_count, clusters.spot_count | clusters/ClusterList.jsx, api/metrics_routes.py, services/metrics_service.py | App.js |

### Cluster List

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Page Header** "Clusters" | Text | Title + subtitle | Hardcoded | — | — | — | — | clusters/ClusterList.jsx | App.js |
| **Refresh Discovery Button** | Button | Triggers cluster re-discovery | Real API | `POST /api/v1/clusters/discover` | ClusterService.discover_clusters → boto3 EKS list_clusters, creates/updates records | clusters, accounts | clusters.name, clusters.arn, clusters.region, clusters.version, clusters.endpoint, clusters.status, clusters.account_id | clusters/ClusterList.jsx, api/cluster_routes.py, services/cluster_service.py | App.js |
| **Cluster Cards** | Card Grid | Provider, name, region, status, nodes, cost, spot ratio | Real API | `GET /api/v1/clusters` | ClusterService.list_clusters → RBAC filtered, pagination+sorting | clusters, accounts | clusters.name, clusters.region, clusters.status, clusters.node_count, clusters.monthly_cost, accounts.aws_account_id | clusters/ClusterList.jsx | App.js |

### Cluster Card Actions

| Action | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Inject Agent** | Button | Installs optimization agent | Real API | `POST /api/v1/clusters/{id}/auto-install` | ClusterService.generate_agent_install_command → Helm install with cluster token | clusters | clusters.id, clusters.api_key, clusters.agent_installed | clusters/ClusterList.jsx, api/cluster_routes.py, services/cluster_service.py | App.js |
| **Reconnect** | Button | Re-establishes connection | Real API | `POST /api/v1/clusters/verify/{id}` | ClusterService.verify_connection → checks last_heartbeat within 10min | clusters | clusters.last_heartbeat, clusters.status | clusters/ClusterList.jsx, api/cluster_routes.py, services/cluster_service.py | App.js |
| **Disconnect** | Button | Opens disconnect modal | N/A | — | — | — | — | clusters/ClusterList.jsx | App.js |
| **Remove** | Button | Opens delete modal | Real API | `DELETE /api/v1/clusters/{id}` | ClusterService.delete_cluster → validates no active instances, removes | clusters, instances | clusters.id (cascade deletes related records) | clusters/ClusterList.jsx, api/cluster_routes.py, services/cluster_service.py | App.js |
| **Click Card** | Button | Opens ClusterDetails modal | Real API | `GET /api/v1/clusters/{id}` | ClusterService → fetches Cluster by ID with RBAC | clusters, accounts | clusters.*, accounts.aws_account_id | clusters/ClusterDetails.jsx, api/cluster_routes.py, services/cluster_service.py | clusters/ClusterList.jsx |

### Cluster Detail Modal

| Section | Type | What It Shows | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Header** | Text | Cluster name, region, provider | Real API | `GET /api/v1/clusters/{id}` | ClusterService → fetches Cluster by ID with RBAC | clusters, accounts | clusters.*, accounts.aws_account_id | clusters/ClusterList.jsx, api/cluster_routes.py, services/cluster_service.py | App.js |
| **Instant Rebalance Button** | Button | Triggers optimization | Real API | 🔴 `POST /api/v1/clusters/{id}/optimize` | Not implemented — route stub only | — | — | clusters/ClusterList.jsx, api/cluster_routes.py, services/cluster_service.py | App.js |
| **Refresh Button** | Button | Refreshes cluster data | Real API | `GET /api/v1/clusters/{id}` | ClusterService → fetches Cluster by ID with RBAC | clusters, accounts | clusters.*, accounts.aws_account_id | clusters/ClusterList.jsx, api/cluster_routes.py, services/cluster_service.py | App.js |
| **Status Overview** | Card | Status badge, Cluster ID, Created, Last Heartbeat | Real API | (included in cluster data) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Cluster Metrics** | Card | Total/Spot/On-Demand instances, Spot Ratio, Cost, Savings, CPU | Real API | `GET /api/v1/metrics/cluster/{id}` | MetricsService.get_cluster_metrics → per-cluster cost, savings, spot ratio | instances, clusters | clusters.monthly_cost, clusters.estimated_savings, instances.lifecycle, instances.price | clusters/ClusterList.jsx, api/metrics_routes.py, services/metrics_service.py | App.js |
| **Optimization Policy** | Card | Spot Target, Node Range, Target CPU/Memory, Fallback, Diversification | Real API | `GET /api/v1/policies/cluster/{id}` | PolicyService.get_policy_by_cluster → queries ClusterPolicy with RBAC | cluster_policies | cluster_policies.cluster_id, cluster_policies.config | clusters/ClusterList.jsx, api/policy_routes.py, services/policy_service.py | App.js |
| **Hibernation Schedule** | Card | Strategy, Timezone, Pre-warm, Active Hours, Last Action | Real API | `GET /api/v1/hibernation/schedules?cluster_id={id}` | HibernationService.list_schedules → paginated with cluster_id filter | hibernation_schedules | hibernation_schedules.cluster_id, hibernation_schedules.schedule_matrix, hibernation_schedules.is_active, hibernation_schedules.strategy | clusters/ClusterList.jsx, api/hibernation_routes.py, services/hibernation_service.py | App.js |
| **Edit Schedule Button** | Button | Opens HibernationScheduleV2 modal | N/A | — | — | — | — | clusters/ClusterList.jsx | App.js |
| **Configure Policy Button** | Button | Shown when no policy exists | N/A | — | — | — | — | clusters/ClusterList.jsx | App.js |
| **Cluster Configuration** | Card | K8s Version, VPC ID, Tags, Agent Installed | Real API | (included in cluster data) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Node List** | Table | Nodes in the cluster | Real API | `GET /api/v1/clusters/{id}/nodes` | ClusterService → queries Instance table by cluster_id | instances | instances.instance_id, instances.instance_type, instances.lifecycle, instances.az, instances.cpu_util, instances.memory_util, instances.state | clusters/ClusterList.jsx, api/cluster_routes.py, services/cluster_service.py | App.js |
| **Close Button** | Button | Closes modal | N/A | — | — | — | — | clusters/ClusterList.jsx | App.js |

#### Node List Sub-Component (inside Cluster Detail)

| Column | Type | What It Shows | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Header** "Node List" | Text | Title + node count badge | Real API | `GET /api/v1/clusters/{id}/nodes` | ClusterService → queries Instance table by cluster_id | instances | instances.instance_id, instances.instance_type, instances.lifecycle, instances.az, instances.cpu_util, instances.memory_util, instances.state | clusters/ClusterList.jsx, api/cluster_routes.py, services/cluster_service.py | App.js |
| **Instance ID** | Text | EC2 instance ID (e.g. i-0123...) | Real API | (in nodes response) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Type** | Text | Instance type (e.g. c5.large) | Real API | (in nodes response) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Lifecycle** | Display | SPOT (green badge) / ON_DEMAND (blue badge) | Real API | (in nodes response) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **CPU %** | Graph | Utilization bar (green <80%, red ≥80%) + percentage | Real API | (in nodes response) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Zone** | Text | Availability zone (e.g. us-east-1a) | Real API | (in nodes response) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Mock Fallback** | — | If API fails, 3 hardcoded rows are shown | Hardcoded | — | — | — | — | clusters/ClusterList.jsx | App.js |

---

## 5. Optimizations

> This section acts as a routing container; no standalone UI elements.

---

## 6. AtharvaAi

### Page Layout

| Section | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **OptimizationStatusHeader** | Card | Engine status (Running/Paused), optimization toggle | Mock API | `GET /api/v1/atharva/status` | AtharvaService.get_system_status → in-memory mock | — (in-memory) | — | atharva/OptimizationStatusHeader.jsx, api/atharva_routes.py, services/atharva_service.py | pages/AtharvaAiPage.jsx |
| **Auto-Rebalancing Toggle** | Button | Enable/disable auto-rebalancing | Mock API | `POST /api/v1/atharva/settings` | AtharvaService.update_settings → in-memory, no DB | — (in-memory) | — | api/atharva_routes.py, services/atharva_service.py | — |
| **Live Activity Feed** | Table | Color-coded recent events list | Mock API | `GET /api/v1/atharva/activity` | AtharvaService.get_activity → pre-seeded mock events | — (in-memory) | — | api/atharva_routes.py, services/atharva_service.py | — |

### LivePoolRankings Table

| Column | Type | What It Shows | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Rank** | Display | # with change indicator (↑/↓/—) | Mock API | `GET /api/v1/atharva/pools/rankings` | AtharvaService.get_pool_rankings → random mock data | — (in-memory) | — | api/atharva_routes.py, services/atharva_service.py | — |
| **Pool Name** | Text | Clickable → PoolDetailsModal | Mock API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Instances** | Text | Running/total count | Mock API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Spot %** | Display | Percentage with colored bar | Mock API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Risk** | Display | Badge (Low/Medium/High/Critical) | Mock API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Cost/hr** | Text | Hourly cost | Mock API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Interruption** | Display | Rate with trend indicator | Mock API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **View Details Button** | Button | Opens PoolDetailsModal | N/A | — | — | — | — | atharva/PoolDetailsModal.jsx | pages/AtharvaAiPage.jsx |
| **Blacklist Button** | Button | Blacklists pool | Mock API | `POST /api/v1/atharva/blacklist` | AtharvaService.add_to_blacklist → in-memory list | — (in-memory) | — | api/atharva_routes.py, services/atharva_service.py | — |
| **Switch Button** | Button | Opens SwitchConfirmationModal | N/A | — | — | — | — | atharva/SwitchConfirmationModal.jsx | pages/AtharvaAiPage.jsx |

### Filtering Pipeline Stats

| Stat | Type | What It Shows | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Total Pools** | Display | Starting count | Mock API | (in rankings response) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Compliance** | Display | After compliance filter | Mock API | (in rankings response) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Risk** | Display | After risk filter | Mock API | (in rankings response) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Cost** | Display | After cost filter | Mock API | (in rankings response) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Capacity** | Display | After capacity filter | Mock API | (in rankings response) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Final** | Display | Top 10 result | Mock API | (in rankings response) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |

### NodeTemplateEditor

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Template List** | Card | Cards with name, arch, vCPU/memory | Mock API | `GET /api/v1/atharva/node-templates` | AtharvaService node templates → in-memory list | — (in-memory) | — | api/atharva_routes.py, services/atharva_service.py | — |
| **Create Button** | Button | Creates new template | Mock API | `POST /api/v1/atharva/node-templates` | AtharvaService node templates → in-memory list | — (in-memory) | — | api/atharva_routes.py, services/atharva_service.py | — |
| **Edit Button** | Button | Opens edit form | N/A | — | — | — | — | — | — |
| **Clone Button** | Button | Clones template | Mock API | `POST /api/v1/atharva/node-templates` | AtharvaService node templates → in-memory list | — (in-memory) | — | api/atharva_routes.py, services/atharva_service.py | — |
| **Delete Button** | Button | Deletes template | Mock API | `DELETE /api/v1/atharva/node-templates/{id}` | AtharvaService node templates → in-memory list | — (in-memory) | — | api/atharva_routes.py, services/atharva_service.py | — |
| **Template Form** | Form | Architecture, vCPU, Memory, Instance Families, etc. | Hardcoded (options) | `PUT /api/v1/atharva/node-templates/{id}` | AtharvaService node templates → in-memory list | — (in-memory) | — | api/atharva_routes.py, services/atharva_service.py | — |

### AtharvaAi Modals

| Modal | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **PoolDetailsModal** | Modal | 6 tabs: Overview, Specs, Risk, Cost, Usage, Switch Preview | Mock API | `GET /api/v1/atharva/pools/{id}/details` | AtharvaService.get_pool_details → random mock detail | — (in-memory) | — | atharva/PoolDetailsModal.jsx, api/atharva_routes.py, services/atharva_service.py | pages/AtharvaAiPage.jsx |
| **SwitchConfirmationModal** | Modal | Safety checks, reason, auto-resume, confirm | Mock API | `POST /api/v1/atharva/pools/switch` | AtharvaService.switch_pool → mock safety checks | — (in-memory) | — | atharva/SwitchConfirmationModal.jsx, api/atharva_routes.py, services/atharva_service.py | pages/AtharvaAiPage.jsx |

### Other AtharvaAi Data

| Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Recommendations** | Card | AI optimization recommendations | Mock API | `GET /api/v1/atharva/recommendations` | AtharvaService.get_recommendations → hardcoded mock | — (in-memory) | — | atharva/Recommendations.jsx, api/atharva_routes.py, services/atharva_service.py | pages/AtharvaAiPage.jsx |
| **RiskMonitor** | Card | Real-time risk indicators | Mock API | `GET /api/v1/atharva/risk-history` | AtharvaService.get_risk_history → mock time-series | — (in-memory) | — | atharva/RiskMonitor.jsx, api/atharva_routes.py, services/atharva_service.py | pages/AtharvaAiPage.jsx |
| **Blacklist Management** | Table | Blacklisted pools list | Mock API | `GET /api/v1/atharva/blacklist` | AtharvaService.get_blacklist → in-memory list | — (in-memory) | — | api/atharva_routes.py, services/atharva_service.py | — |
| **Remove from Blacklist** | Button | Unblacklists a pool | Mock API | `DELETE /api/v1/atharva/blacklist/{poolId}` | AtharvaService.remove_from_blacklist → in-memory | — (in-memory) | — | api/atharva_routes.py, services/atharva_service.py | — |

---

## 7. Tagging Policies

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Page Title** "Tag Policies" | Text | Section header | Hardcoded | — | — | — | — | settings/TagPoliciesList.jsx | settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |
| **Create Policy Button** | Button | Opens create form | N/A | — | — | — | — | settings/TagPoliciesList.jsx | settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |
| **Policies Table** | Table | Tag key, enforcement badge, allowed values, description | Real API | `GET /api/v1/tags/policies` | TagPolicyService.list_policies → by organization_id | tag_policies | tag_policies.id, tag_policies.tag_key, tag_policies.enforcement_level, tag_policies.is_active | settings/TagPoliciesList.jsx, api/tag_policy_routes.py, services/tag_policy_service.py | settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |
| **Edit Policy Button** | Button | Opens edit form | N/A | — | — | — | — | settings/TagPoliciesList.jsx | settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |
| **Delete Policy Button** | Button | Deletes policy | Real API | `DELETE /api/v1/tags/policies/{id}` | TagPolicyService → CRUD on TagPolicy record | tag_policies | tag_policies.tag_key, tag_policies.enforcement_level, tag_policies.allowed_values | settings/TagPoliciesList.jsx, api/tag_policy_routes.py, services/tag_policy_service.py | settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |

### Policy Form (Create/Edit)

| Field | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Tag Key** | Input | Tag key name | N/A | — | — | — | — | settings/TagPoliciesList.jsx | settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |
| **Enforcement Level** | Dropdown | Required / Advisory / Recommended | Hardcoded | — | — | — | — | settings/TagPoliciesList.jsx | settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |
| **Allowed Values** | Input | Add/remove values list | N/A | — | — | — | — | settings/TagPoliciesList.jsx | settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |
| **Description** | Input | Policy description | N/A | — | — | — | — | settings/TagPoliciesList.jsx | settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |
| **Cancel Button** | Button | Discards changes | N/A | — | — | — | — | settings/TagPoliciesList.jsx | settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |
| **Save Button** | Button | Creates or updates policy | Real API | `POST /api/v1/tags/policies` + `PUT /api/v1/tags/policies/{id}` | TagPolicyService.create_policy | tag_policies | tag_policies.tag_key, tag_policies.enforcement_level, tag_policies.allowed_values, tag_policies.value_mode | settings/TagPoliciesList.jsx, api/tag_policy_routes.py, services/tag_policy_service.py | settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |

---

## 8. Templates

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Page Title** "Node Templates" | Text | Title + subtitle | Hardcoded | — | — | — | — | templates/TemplateCards.jsx | — |
| **Create Template Button** | Button | Opens TemplateBuilder modal | N/A | — | — | — | — | templates/TemplateBuilder.jsx | templates/TemplateList.jsx |
| **Template Grid** | Card Grid | Name, Default badge, Arch, Disk, Instance Families | Real API | `GET /api/v1/templates` | TemplateService.list_templates → by organization | node_templates | node_templates.name, node_templates.families, node_templates.architecture, node_templates.strategy, node_templates.is_default | templates/TemplateCards.jsx | — |
| **Delete Button** | Button | Deletes template | Real API | `DELETE /api/v1/templates/{id}` | TemplateService.delete_template → blocks last default | node_templates | node_templates.id, node_templates.is_default | templates/TemplateCards.jsx, api/template_routes.py, services/template_service.py | — |
| **Set as Default Button** | Button | Sets template as default | Real API | `POST /api/v1/templates/{id}/set-default` | TemplateService.set_default → unsets others, sets is_default='Y' | node_templates | node_templates.is_default | templates/TemplateCards.jsx, api/template_routes.py, services/template_service.py | — |
| **Empty State** | Display | "No templates found" + Create button | Hardcoded | — | — | — | — | templates/TemplateCards.jsx | — |

### TemplateBuilder Modal

| Section | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Template Name** | Input | Name field | N/A | — | — | — | — | templates/TemplateBuilder.jsx | templates/TemplateList.jsx |
| **Architecture** | Dropdown | amd64/arm64 selection | Hardcoded | — | — | — | — | templates/TemplateBuilder.jsx | templates/TemplateList.jsx |
| **Root Volume** | Form | Type dropdown + Size input | Hardcoded | — | — | — | — | templates/TemplateBuilder.jsx | templates/TemplateList.jsx |
| **Instance Families** | Form | Multi-select checkboxes | Hardcoded | 🔴 `GET /api/v1/templates/options` | No service logic — route exists | — | — | templates/TemplateBuilder.jsx, api/template_routes.py, services/template_service.py | templates/TemplateList.jsx |
| **Instance Sizes** | Form | Size exclusion options | Hardcoded | — | — | — | — | templates/TemplateBuilder.jsx | templates/TemplateList.jsx |
| **Spot Configuration** | Form | Spot %, interruption tolerance | Hardcoded | — | — | — | — | templates/TemplateBuilder.jsx | templates/TemplateList.jsx |
| **Save Button** | Button | Creates/updates template | Real API | `POST /api/v1/templates` + `PUT /api/v1/templates/{id}` | TemplateService.update_template → validates ownership | node_templates | node_templates.name, node_templates.families, node_templates.architecture | templates/TemplateBuilder.jsx | templates/TemplateList.jsx |

---

## 9. Right-Sizing

### Summary Stats

| Stat Card | Type | What It Shows | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Potential Monthly Savings** | Card | Dollar amount (14-day analysis) | Real API | `GET /api/v1/optimization/rightsizing/{clusterId}` | Queries Instance table, compares current vs recommended by CPU/memory | instances | instances.instance_type, instances.cpu_util, instances.memory_util, instances.price | right-sizing/RightSizing.jsx, api/optimization_routes.py, services/metrics_service.py | App.js |
| **Over-provisioned Instances** | Card | Instance count | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Optimization Score** | Card | Score /100 | Hardcoded | — | — | — | — | right-sizing/RightSizing.jsx | App.js |

### Recommendations Table

| Column | Type | What It Shows | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Instance** | Text | Instance ID | Real API | `GET /api/v1/optimization/rightsizing/{clusterId}` | Queries Instance table, compares current vs recommended by CPU/memory | instances | instances.instance_type, instances.cpu_util, instances.memory_util, instances.price | right-sizing/RightSizing.jsx, api/optimization_routes.py, services/metrics_service.py | App.js |
| **Current** | Display | Current instance type badge | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Recommendation** | Display | Downsized type with arrow | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **CPU / Mem Util** | Graph | CPU % bar + Memory % bar | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Savings** | Text | Monthly savings amount | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Apply Button** | Button | Applies recommendation | Real API | `POST /api/v1/optimization/apply/{id}` | Executes type change via boto3 modify_instance_attribute | instances | instances.instance_id, instances.instance_type | right-sizing/RightSizing.jsx, api/optimization_routes.py, services/metrics_service.py | App.js |

### Side Panel

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Resource Efficiency Card** | Card | "Select an instance to view usage charts" | Hardcoded | — | — | — | — | right-sizing/RightSizing.jsx | App.js |

---

## 10. Resource Hygiene (Cleanup)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Page Header** | Text | Title + region/account info | Hardcoded | — | — | — | — | — | — |
| **Scan Button** | Button | Triggers resource scan | Real API | `GET /api/v1/hygiene/scan/{accountId}` | HygieneService.scan_resources → STS AssumeRole, parallel region scan (EC2/EBS/S3/RDS/VPC/IAM) | accounts (STS creds only) | accounts.role_arn, accounts.external_id — resources in AWS not DB | api/hygiene_routes.py, services/hygiene_service.py | — |
| **Region Dropdown** | Dropdown | Select region or "All Regions (Global)" | Hardcoded | — | — | — | — | — | — |
| **Account Selector** | Dropdown | Picks AWS account | Real API | `GET /api/v1/accounts` | AccountService.list_accounts → RBAC filtered | accounts | accounts.id, accounts.aws_account_id, accounts.role_arn, accounts.status, accounts.is_default | — | — |
| **Total Cost Display** | Card | Estimated cost | Real API | `GET /api/v1/hygiene/total-cost` | MetricsService.get_cost_breakdown_by_service | daily_costs | daily_costs.amount, daily_costs.service_category | api/hygiene_routes.py, services/hygiene_service.py | — |
| **Cost by Service** | Graph | Service-level cost breakdown | Real API | `GET /api/v1/hygiene/cost-services` | MetricsService.get_cost_breakdown_by_service | daily_costs | daily_costs.amount, daily_costs.service_category | api/hygiene_routes.py, services/hygiene_service.py | — |

### Scan Results

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Resource Type Tabs** | Tab | Tabs for EC2, EBS, Snapshots, etc. | Real API | (from scan response) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Results Table** | Table | Resource ID, type, region, tags, status, cost, checkbox | Real API | `GET /api/v1/hygiene/scan/{accountId}` | HygieneService.scan_resources → STS AssumeRole, parallel region scan (EC2/EBS/S3/RDS/VPC/IAM) | accounts (STS creds only) | accounts.role_arn, accounts.external_id — resources in AWS not DB | api/hygiene_routes.py, services/hygiene_service.py | — |
| **Select All Checkbox** | Button | Selects all resources | N/A | — | — | — | — | — | — |
| **Delete Selected Button** | Button | Deletes selected resources | Real API | `POST /api/v1/hygiene/action` | HygieneService.execute_action → RBAC + optional approval; boto3 DELETE/RELEASE/STOP | accounts, audit_logs | accounts.role_arn, audit_logs.event, audit_logs.resource | api/hygiene_routes.py, services/hygiene_service.py | — |
| **Tag Selected Button** | Button | Opens BulkTagWizard | N/A | — | — | — | — | cleanup/BulkTagWizard.jsx | cleanup/CleanupDashboard.jsx |
| **Check Dependencies** | Button | Checks resource dependencies | Real API | `GET /api/v1/hygiene/check-dependencies` | HygieneService.check_dependencies → checks AMI refs, attachments, associations | — (AWS API only) | — | api/hygiene_routes.py, services/hygiene_service.py | — |

### Sub-Components

| Component | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **BulkTagWizard** | Modal | Multi-step wizard for bulk tagging | Real API | `POST /api/v1/tags/resources/{type}/{id}/` | TagManagementService.update_resource_tags → boto3 create_tags; validates against policies | tag_policies, accounts | tag_policies.tag_key, accounts.role_arn | cleanup/BulkTagWizard.jsx, api/tag_management_routes.py, services/tag_management_service.py | cleanup/CleanupDashboard.jsx |
| **GovernanceManager** | Card | 3-tab container for governance | N/A | — | — | — | — | — | — |

#### BulkTagWizard — Step-by-Step Breakdown

| Step / Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Step Progress Bar** | Display | 4 circles: Select Tags → Variables → Collision → Execute | Computed | — | — | — | — | — | — |
| **Step 1: Mode Selector** | Button | "Use Template" or "Manual Entry" toggle cards | N/A | — | — | — | — | — | — |
| **Template Dropdown** (template mode) | Dropdown | Lists saved tag templates | Real API | `GET /api/v1/tags/templates/` | DB query on tag_templates by organization_id | tag_templates | tag_templates.id, tag_templates.name, tag_templates.tags, tag_templates.resource_scope, tag_templates.is_default | api/tag_template_routes.py, services/template_service.py | — |
| **Template Preview** | Display | Key=Value tag badges from chosen template | Computed | — | — | — | — | — | — |
| **Manual Tag Key Input** | Input | Tag key text field | N/A | — | — | — | — | — | — |
| **Manual Tag Value Input** | Input | Tag value text field | N/A | — | — | — | — | — | — |
| **Add Tag Button** (+) | Button | Adds key=value pair to list | N/A | — | — | — | — | — | — |
| **Remove Tag Button** (🗑️) | Button | Deletes manual tag from list | N/A | — | — | — | — | — | — |
| **Step 2: Variable Inputs** | Input | Dynamic inputs for template variables like `{PROJECT_ID}` | N/A | — | — | — | — | — | — |
| **Step 3: Skip Existing** | Radio | Keep existing tag values, only add missing | N/A | — | — | — | — | — | — |
| **Step 3: Overwrite (Force)** | Radio | Replace all existing tag values | N/A | — | — | — | — | — | — |
| **Step 3: Summary** | Display | Resource count + tag count + mode | Computed | — | — | — | — | — | — |
| **Step 4: Progress Bar** | Display | Green bar 0-100% during execution | Computed | — | — | — | — | — | — |
| **Step 4: Results** | Display | ✅ Success count + ❌ Failed count | Computed | — | — | — | — | — | — |
| **Back Button** | Button | Go to previous step | N/A | — | — | — | — | — | — |
| **Next / Apply Tags Button** | Button | Advance step or execute tagging | Real API | `POST /api/v1/tags/resources/{type}/{id}/` | TagManagementService.update_resource_tags → boto3 create_tags; validates against policies | tag_policies, accounts | tag_policies.tag_key, accounts.role_arn | api/tag_management_routes.py, services/tag_management_service.py | — |
| **Done Button** (step 4) | Button | Closes wizard after completion | N/A | — | — | — | — | — | — |

#### GovernanceManager — Tabs

| Tab | Type | What It Renders | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Cleanup Rules** (purple) | Tab | CleanupPolicies component | N/A | — | — | — | — | policies/CleanupPolicies.jsx | settings/GovernanceManager.jsx |
| **Tag Policies** (red) | Tab | TagPoliciesList component | N/A | — | — | — | — | settings/TagPoliciesList.jsx | settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |
| **Tag Templates** (blue) | Tab | TagTemplateManager component | N/A | — | — | — | — | settings/TagTemplateManager.jsx | App.js, cleanup/CleanupDashboard.jsx, settings/GovernanceManager.jsx, settings/TagPoliciesManager.jsx |

#### CleanupPolicies Sub-Component (Cleanup Rules tab)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Header** "Cleanup Policies" | Text | Title + subtitle | Hardcoded | — | — | — | — | — | — |
| **Create Policy Button** | Button | Opens create modal | N/A | — | — | — | — | — | — |
| **Policy Cards** | Card | Name, Active/Disabled badge, resource type badge, conditions pills, action label | Real API | `GET /cleanup-policies/` | DB query on cleanup_policies for org | cleanup_policies | cleanup_policies.name, cleanup_policies.resource_type, cleanup_policies.conditions, cleanup_policies.action | — | — |
| **Edit Button** (✏️) | Button | Opens edit modal pre-filled | N/A | — | — | — | — | — | — |
| **Delete Button** (🗑️) | Button | Confirms and deletes policy | Real API | `DELETE /cleanup-policies/{id}` | CRUD on cleanup_policies | cleanup_policies | cleanup_policies.name, cleanup_policies.conditions, cleanup_policies.action, cleanup_policies.is_active | — | — |
| **Empty State** | Display | "No policies defined yet" + Create button | Hardcoded | — | — | — | — | — | — |

##### Cleanup Policy Modal (Create/Edit)

| Field | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Policy Name** | Input | Required name | N/A | — | — | — | — | — | — |
| **Description** | Input | Policy description | N/A | — | — | — | — | — | — |
| **Resource Type** | Dropdown | VOLUME/SNAPSHOT/ELASTIC_IP/LOAD_BALANCER/RDS_DB/S3_BUCKET | Hardcoded | — | — | — | — | — | — |
| **Action** | Dropdown | Notify Only / Delete / Snapshot & Delete | Hardcoded | — | — | — | — | — | — |
| **Conditions Builder** | Form | Rule rows with Field + Operator + Value | N/A | — | — | — | — | — | — |
| **Rule Field Input** | Input | e.g. `age_days` | N/A | — | — | — | — | — | — |
| **Rule Operator** | Dropdown | > / < / = / Exists / Missing | Hardcoded | — | — | — | — | — | — |
| **Rule Value Input** | Input | Threshold value | N/A | — | — | — | — | — | — |
| **Add Condition** | Button | Adds new rule row | N/A | — | — | — | — | — | — |
| **Remove Condition** (✕) | Button | Removes rule row | N/A | — | — | — | — | — | — |
| **Enable Policy Checkbox** | Checkbox | Toggles policy active state | N/A | — | — | — | — | — | — |
| **Cancel Button** | Button | Closes modal | N/A | — | — | — | — | — | — |
| **Save Policy Button** | Button | Creates or updates policy | Real API | `POST /cleanup-policies/` + `PATCH /cleanup-policies/{id}` | Creates CleanupPolicy | cleanup_policies | cleanup_policies.name, cleanup_policies.resource_type, cleanup_policies.conditions, cleanup_policies.action | — | — |

#### TagTemplateManager Sub-Component (Tag Templates tab)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Header** "Tag Templates" | Text | Title + subtitle | Hardcoded | — | — | — | — | — | — |
| **Create Template Button** | Button | Opens create modal | N/A | — | — | — | — | — | — |
| **Info Banner** | Display | Explains dynamic variables + usage tips | Hardcoded | — | — | — | — | — | — |
| **Template Cards** (3-col grid) | Card Grid | Name, Default badge, description, scope, tag previews | Real API | `GET /api/v1/tags/templates/` | DB query on tag_templates by organization_id | tag_templates | tag_templates.id, tag_templates.name, tag_templates.tags, tag_templates.resource_scope, tag_templates.is_default | api/tag_template_routes.py, services/template_service.py | — |
| **Edit Button** (✏️) | Button | Opens edit modal pre-filled | N/A | — | — | — | — | — | — |
| **Delete Button** (🗑️) | Button | Confirms and deletes template | Real API | `DELETE /api/v1/tags/templates/{id}` | CRUD on tag_templates record | tag_templates | tag_templates.name, tag_templates.tags | api/tag_template_routes.py, services/template_service.py | — |
| **Empty State** | Display | "No templates defined yet" + Create link | Hardcoded | — | — | — | — | — | — |

##### Tag Template Modal (Create/Edit)

| Field | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Template Name** | Input | Required name | N/A | — | — | — | — | — | — |
| **Description** | Textarea | When to use this template | N/A | — | — | — | — | — | — |
| **Resource Scope** | Dropdown | All/EC2/S3/RDS/EBS/Load Balancers | Hardcoded | — | — | — | — | — | — |
| **Tag Builder** | Form | Key-Value rows with edit/delete | N/A | — | — | — | — | — | — |
| **Tag Key Input** | Input | New tag key | N/A | — | — | — | — | — | — |
| **Tag Value Input** | Input | New tag value (supports variables) | N/A | — | — | — | — | — | — |
| **Add Tag Button** (+) | Button | Adds key=value row | N/A | — | — | — | — | — | — |
| **Remove Tag Button** (🗑️) | Button | Removes tag row | N/A | — | — | — | — | — | — |
| **Dynamic Variable Buttons** | Button | Click to insert: `{CURRENT_USER_EMAIL}`, `{CURRENT_DATE}`, `{PROJECT_ID}`, etc. | Hardcoded | — | — | — | — | — | — |
| **Set as Default Checkbox** | Checkbox | Makes this the default template | N/A | — | — | — | — | — | — |
| **Cancel Button** | Button | Closes modal | N/A | — | — | — | — | — | — |
| **Create/Update Template Button** | Button | Saves template | Real API | `POST /api/v1/tags/templates/` + `PUT /api/v1/tags/templates/{id}` | Creates tag template record | tag_templates | tag_templates.name, tag_templates.description, tag_templates.tags, tag_templates.resource_scope | api/tag_template_routes.py, services/template_service.py | — |

---

## 11. Hibernation

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Back to Clusters Link** | Button | Navigates to /clusters | N/A | — | — | — | — | hibernation/HibernationSchedule.jsx | App.js |
| **Page Header** | Text | "Cluster Hibernation" + cluster name | Computed | — | — | — | — | hibernation/HibernationSchedule.jsx | App.js |

### Strategy Selector

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Strategy Cards** | Card Grid | Namespace Sleep, Node Scale-Down, Full Hibernation, Custom | Real API | `GET /api/v1/hibernation/strategies` | Returns hardcoded strategy definitions | — | — | hibernation/StrategySelector.jsx, api/hibernation_routes.py, services/hibernation_service.py | hibernation/HibernationSchedule.jsx, pages/HibernationPage.jsx |
| **Strategy Description** | Text | Explanation of selected strategy | Hardcoded | — | — | — | — | hibernation/StrategySelector.jsx | hibernation/HibernationSchedule.jsx, pages/HibernationPage.jsx |

### Hibernation Scheduler (2/3 width)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Weekly Calendar Grid** | Graph | 7×24 clickable grid (days × hours) | Real API | `GET /api/v1/hibernation/schedules` | HibernationService.list_schedules → paginated with cluster_id filter | hibernation_schedules | hibernation_schedules.cluster_id, hibernation_schedules.schedule_matrix, hibernation_schedules.is_active, hibernation_schedules.strategy | hibernation/HibernationScheduler.jsx, api/hibernation_routes.py, services/hibernation_service.py | pages/HibernationPage.jsx |
| **Time Inputs** | Input | Start/end time pickers | N/A | — | — | — | — | hibernation/HibernationScheduler.jsx | pages/HibernationPage.jsx |
| **Scheduled Jobs List** | Table | Configured hibernation jobs | Real API | (included in schedules) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Timezone Selector** | Dropdown | Timezone selection | Hardcoded | — | — | — | — | hibernation/HibernationScheduler.jsx | pages/HibernationPage.jsx |
| **Save Schedule Button** | Button | Creates/updates schedule | Real API | `POST /api/v1/hibernation/schedules` + `PUT /api/v1/hibernation/schedules/{id}` | HibernationService.create_schedule → creates with weekly grid | hibernation_schedules, audit_logs | hibernation_schedules.cluster_id, hibernation_schedules.schedule_matrix, hibernation_schedules.timezone, hibernation_schedules.strategy | hibernation/HibernationScheduler.jsx, api/hibernation_routes.py, services/hibernation_service.py | pages/HibernationPage.jsx |
| **Toggle Active Button** | Button | Enables/disables schedule | Real API | `POST /api/v1/hibernation/schedules/{id}/toggle` | HibernationService.toggle_schedule → flips is_active | hibernation_schedules | hibernation_schedules.is_active | hibernation/HibernationScheduler.jsx, api/hibernation_routes.py, services/hibernation_service.py | pages/HibernationPage.jsx |

### Right Sidebar (1/3 width)

| Component | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **ValidationPanel** | Card | Warnings/errors for schedule config | Computed | — | — | — | — | hibernation/ValidationPanel.jsx | hibernation/HibernationSchedule.jsx, pages/HibernationPage.jsx |
| **CostAnalytics** | Card | Estimated savings from hibernation | Computed | — | — | — | — | hibernation/CostAnalytics.jsx | hibernation/HibernationSchedule.jsx, pages/HibernationPage.jsx |


### Hibernation Sub-Components

| Component | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **HibernationHeader** | Header | Page header with cluster name, back button, status badge | Computed | — | — | — | — | hibernation/HibernationSchedule.jsx | hibernation/HibernationHeader.jsx |
| **ClusterOverview** | Card | Cluster summary — node count, instance types, current state | Real API | `GET /api/v1/clusters/{id}` | ClusterService.get_cluster → single cluster details | clusters | clusters.name, clusters.node_count, clusters.status, clusters.region | hibernation/HibernationSchedule.jsx | hibernation/ClusterOverview.jsx |
| **HibernationGrid** | Grid | Visual weekly schedule grid — 7×24 clickable cells for hour selection | Computed | — | — | — | — | — | hibernation/HibernationGrid.jsx |
| **HibernationTypeCard** | Card | Strategy type card — icon, name, description, pros/cons | Hardcoded | — | — | — | — | hibernation/HibernationScheduleV2.jsx | hibernation/HibernationTypeCard.jsx |
| **ScheduleTemplates** | Card | Pre-built schedule templates — Business Hours, Nights & Weekends, etc. | Hardcoded | — | — | — | — | hibernation/HibernationSchedule.jsx | hibernation/ScheduleTemplates.jsx |
| **TimeBasedRules** | Form | Custom time-based rules — recurring on/off windows | Computed | — | — | — | — | hibernation/HibernationSchedule.jsx | hibernation/TimeBasedRules.jsx |
| **MultiTimezone** | Form | Multi-timezone awareness — schedule in different timezones | Computed | — | — | — | — | hibernation/HibernationSchedule.jsx | hibernation/MultiTimezone.jsx |
| **AdvancedConfiguration** | Form | Advanced hibernation settings — grace periods, scaling rules, alerts | Computed | — | — | — | — | hibernation/HibernationSchedule.jsx | hibernation/AdvancedConfiguration.jsx |
| **HistoryLog** | Table | Hibernation execution history — past activations/deactivations with timestamps | Real API | `GET /api/v1/hibernation/history` | HibernationService.get_history → execution logs | audit_logs | audit_logs.event, audit_logs.timestamp, audit_logs.resource | hibernation/HibernationSchedule.jsx | hibernation/HistoryLog.jsx |

### Unused Hibernation Endpoints

| Endpoint | Status | Notes | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|
| 🔴 `POST /api/v1/hibernation/schedules/{id}/override` | Unused | Override endpoint defined but not called from UI | Defined but not called — would allow one-time override | hibernation_schedules | hibernation_schedules.date_overrides | hibernation/HibernationSchedule.jsx, api/hibernation_routes.py, services/hibernation_service.py | App.js |
| 🔴 `DELETE /api/v1/hibernation/schedules/{id}` | Unused | Delete endpoint defined but not called from UI | HibernationService.delete_schedule → audit logged | hibernation_schedules, audit_logs | hibernation_schedules.id | hibernation/HibernationSchedule.jsx, api/hibernation_routes.py, services/hibernation_service.py | App.js |

---

## 12. Automation Settings

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Governance Policies** | Card | Autopilot and automation rules | Real API | `GET /api/v1/governance/policies` | GovernanceService.get_organization_policies → merges defaults with org overrides | organizations | organizations.governance_config, organizations.is_governance_enabled | settings/GovernanceSettings.jsx, api/governance_routes.py, services/governance_service.py | App.js, policies/PolicyConfig.jsx |
| **Update Policies Button** | Button | Saves automation config | Real API | `PATCH /api/v1/governance/policies` | Updates Organization.governance_config JSON | organizations | organizations.governance_config | settings/GovernanceSettings.jsx, api/governance_routes.py, services/governance_service.py | App.js, policies/PolicyConfig.jsx |
| **Run Autopilot Button** | Button | Triggers autopilot scan | Real API | `POST /api/v1/governance/run-autopilot` | GovernanceService.run_automated_cleanup → scans + auto-executes, logs as 'System Autopilot' | organizations, accounts, audit_logs | organizations.governance_config, accounts.role_arn, audit_logs.actor_name | settings/GovernanceSettings.jsx, api/governance_routes.py, services/governance_service.py | App.js, policies/PolicyConfig.jsx |

---

## 13. Audit Logs

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Page Title** "Audit Logs" | Text | Title + total record count | Real API | `GET /api/v1/audit/logs` | AuditService.get_audit_logs → paginated DB query with filters (date, actor, event, outcome) | audit_logs | audit_logs.timestamp, audit_logs.actor_id, audit_logs.actor_name, audit_logs.event, audit_logs.resource, audit_logs.resource_type, audit_logs.outcome, audit_logs.ip_address | audit/AuditLog.jsx, api/audit_routes.py, services/audit_service.py | App.js |
| **Show/Hide Filters Button** | Button | Toggles filter panel | N/A | — | — | — | — | audit/AuditLog.jsx | App.js |
| **Export Button** | Button | Downloads logs as JSON | Real API | `GET /api/v1/audit/export` | AuditService → full result set as JSON download | audit_logs | audit_logs.* (all columns) | audit/AuditLog.jsx, api/audit_routes.py, services/audit_service.py | App.js |

### Filters Panel

| Filter | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Event Type Dropdown** | Dropdown | Filter by event type | Hardcoded (options) | — | — | — | — | audit/AuditLog.jsx | App.js |
| **Start Date** | Input | Date range start | N/A | — | — | — | — | audit/AuditLog.jsx | App.js |
| **End Date** | Input | Date range end | N/A | — | — | — | — | audit/AuditLog.jsx | App.js |
| **Actor Role** (admin) | Dropdown | Filter by role | Hardcoded (options) | — | — | — | — | audit/AuditLog.jsx | App.js |
| **Clear Filters Button** | Button | Resets all filters | N/A | — | — | — | — | audit/AuditLog.jsx | App.js |

### Audit Log Table

| Column | Type | What It Shows | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Timestamp** | Text | Formatted datetime | Real API | `GET /api/v1/audit/logs` | AuditService.get_audit_logs → paginated DB query with filters (date, actor, event, outcome) | audit_logs | audit_logs.timestamp, audit_logs.actor_id, audit_logs.actor_name, audit_logs.event, audit_logs.resource, audit_logs.resource_type, audit_logs.outcome, audit_logs.ip_address | audit/AuditLog.jsx, api/audit_routes.py, services/audit_service.py | App.js |
| **Event** | Display | Color-coded badge (green/blue/red/purple) | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Actor** | Text | Email or "System" | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Resource** | Text | Resource type : Resource ID | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **IP Address** | Text | IP or "-" | Real API | (included in above) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **View Diff Link** | Button | Opens Diff Viewer modal | N/A | — | — | — | — | audit/AuditLog.jsx | App.js |

### Pagination

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Page Info** | Text | "Page X of Y (Z total records)" | Computed | — | — | — | — | audit/AuditLog.jsx | App.js |
| **Previous Button** | Button | Navigate back | N/A | — | — | — | — | audit/AuditLog.jsx | App.js |
| **Next Button** | Button | Navigate forward | N/A | — | — | — | — | audit/AuditLog.jsx | App.js |

### Diff Viewer Modal

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Modal Header** "State Changes" | Text | Title + close button | Hardcoded | — | — | — | — | audit/AuditLog.jsx | App.js |
| **Event Summary** | Display | Event badge, timestamp, actor, resource | Real API | (from selected log) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Diff List** | Display | Per field: key, type badge, Before (red bg), After (green bg) | Computed | — | — | — | — | audit/AuditLog.jsx | App.js |
| **Close Button** | Button | Closes modal | N/A | — | — | — | — | audit/AuditLog.jsx | App.js |

---

## 14. Settings

### Settings Tabs

| Tab | Type | What It Renders | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Account** | Tab | AccountSettings component | N/A | — | — | — | — | pages/Approvals.jsx | App.js |
| **Cloud Integrations** | Tab | CloudIntegrations component | N/A | — | — | — | — | settings/CloudIntegrations.jsx | settings/Settings.jsx |
| **Billing** | Tab | BillingTab component | N/A | — | — | — | — | pages/Approvals.jsx | App.js |

### Account Tab

#### User Profile Card

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Avatar Circle** | Display | First letter of name/email, blue bg | Computed | — | — | — | — | settings/Settings.jsx | App.js |
| **Full Name** | Text | User's display name | Real API | `GET /api/v1/auth/me` | AuthService.get_user_profile → returns user info | users, organizations, teams | users.email, users.full_name, users.role, users.organization_id, users.team_id | settings/Settings.jsx, api/auth_routes.py, services/auth_service.py | App.js |
| **Email** | Text | User's email address | Real API | (in auth/me) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Role** | Text | User role (CLIENT/ORG_ADMIN/etc.) | Real API | (in auth/me) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Organization** | Text | Organization name | Real API | (in auth/me) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |

#### Edit Profile Card

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Full Name Input** | Input | Editable name (min 2 chars) | Real API | `GET /api/v1/auth/me` | AuthService.get_user_profile → returns user info | users, organizations, teams | users.email, users.full_name, users.role, users.organization_id, users.team_id | settings/Settings.jsx, api/auth_routes.py, services/auth_service.py | App.js |
| **Save Profile Button** | Button | Updates name via API | Real API | `PUT /api/v1/auth/profile` | AuthService → updates User.full_name | users | users.full_name | settings/Settings.jsx, api/auth_routes.py, services/auth_service.py | App.js |

#### Change Password Card

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Current Password** | Input | Password field (autocomplete=current-password) | N/A | — | — | — | — | settings/Settings.jsx | App.js |
| **New Password** | Input | Password field (min 8 chars) | N/A | — | — | — | — | settings/Settings.jsx | App.js |
| **Confirm New Password** | Input | Must match new password | N/A | — | — | — | — | settings/Settings.jsx | App.js |
| **Update Password Button** | Button | Calls change-password API | Real API | `POST /api/v1/auth/change-password` | AuthService.change_password → bcrypt verify + hash update | users | users.password_hash | settings/Settings.jsx, api/auth_routes.py, services/auth_service.py | App.js |

#### Preferences Card

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Timezone Selector** | Dropdown | UTC, America/*, Europe/*, Asia/*, Australia/* | Hardcoded (options) | — | — | — | — | settings/Settings.jsx | App.js |
| **All Notifications Toggle** | Toggle | Master switch for email notifications | Hardcoded | 🔴 `PATCH /api/v1/users/me/preferences` | No backend logic — frontend saves to localStorage only | users (unused) | users.preferences (defined but unused by frontend) | settings/Settings.jsx, api/user_routes.py, services/auth_service.py | App.js |
| **Optimization Alerts Toggle** | Toggle | Notify on optimization job completion | Hardcoded | (saves to localStorage) — | — | — | — | settings/Settings.jsx | App.js |
| **Weekly Reports Toggle** | Toggle | Weekly cost/savings summaries | Hardcoded | (saves to localStorage) — | — | — | — | settings/Settings.jsx | App.js |
| **Cost Threshold Alerts Toggle** | Toggle | Alert when costs exceed thresholds | Hardcoded | (saves to localStorage) — | — | — | — | settings/Settings.jsx | App.js |
| **Save Preferences Button** | Button | Saves to localStorage (not API) | Hardcoded | 🔴 Preferences API exists but **not called** — | — | — | — | settings/Settings.jsx | App.js |

#### Danger Zone Card

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Warning Text** | Text | "Once you delete… no going back" | Hardcoded | — | — | — | — | settings/AccountSettings.jsx | settings/Settings.jsx |
| **Delete Account Button** | Button | Currently **no handler** — non-functional | N/A | 🔴 No backend endpoint — | — | — | — | settings/AccountSettings.jsx | settings/Settings.jsx |

### Cloud Integrations Tab

#### Header Section

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Page Title** "Cloud Integrations" | Text | Title + subtitle | Hardcoded | — | — | — | — | settings/CloudIntegrations.jsx | settings/Settings.jsx |
| **Link AWS Account Button** | Button | Opens add account modal (governance-protected) | N/A | — | — | — | — | settings/CloudIntegrations.jsx | settings/Settings.jsx |

#### CloudFormation Setup Card (blue gradient)

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Download CloudFormation Template Button** | Button | Downloads YAML via blob | Real API | `GET /api/v1/onboarding/template?mode=READ_ONLY` | OnboardingService → reads CloudFormation YAML, injects ExternalID | organizations | organizations.external_id | settings/CloudIntegrations.jsx, api/onboarding_routes.py, services/onboarding_service.py | settings/Settings.jsx |
| **Launch CloudFormation Console Link** | Button | Opens AWS console with pre-filled params | Computed | — | — | — | — | settings/CloudIntegrations.jsx | settings/Settings.jsx |
| **Platform Account ID** | Display | Auto-detected AWS account + badge | Real API | `GET /api/v1/organization/connection-info` | OrganizationService → returns org's external_id | organizations | organizations.external_id, organizations.name | settings/CloudIntegrations.jsx, api/organization_routes.py, services/organization_service.py | settings/Settings.jsx |
| **Auto-detected Badge** | Display | Green badge if auto-detected | Real API | (in connection-info) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Not Configured Badge** | Display | Red badge if missing | Real API | (in connection-info) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **External ID** | Display | Bold blue code block | Real API | (in connection-info) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Copy External ID Button** | Button | Copies to clipboard | N/A | — | — | — | — | settings/CloudIntegrations.jsx | settings/Settings.jsx |
| **Regenerate Button** (admin only) | Button | Regenerates external ID with confirmation | Real API | `POST /api/v1/organization/connection-info/regenerate` | OrganizationService.regenerate_external_id → new 32-char random | organizations | organizations.external_id | settings/CloudIntegrations.jsx, api/organization_routes.py, services/organization_service.py | settings/Settings.jsx |

#### Linked Accounts List

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Empty State** | Card | "No AWS accounts linked" + Link button | Hardcoded | — | — | — | — | settings/CloudIntegrations.jsx | settings/Settings.jsx |
| **Account Card** (per account) | Card | AWS account ID + badges + details + action buttons | Real API | `GET /api/v1/accounts` | AccountService.list_accounts → RBAC filtered | accounts | accounts.id, accounts.aws_account_id, accounts.role_arn, accounts.status, accounts.is_default | settings/CloudIntegrations.jsx | settings/Settings.jsx |
| **Default Badge** (green) | Display | Shown if account is default | Real API | (in accounts data) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Validated Badge** (green) | Display | Shown if status=active | Real API | (in accounts data) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Pending Approval Badge** (yellow) | Display | Shown if status=PENDING_APPROVAL | Real API | (in accounts data) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Pending Validation Badge** (yellow) | Display | Shown if status=pending | Real API | (in accounts data) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Role ARN** | Text | Monospace full ARN | Real API | (in accounts data) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **External ID** | Text | External ID or "N/A" | Real API | (in accounts data) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Primary Region** | Text | Region name | Real API | (in accounts data) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Linked Date** | Text | Formatted date | Real API | (in accounts data) ↑ | ↑ same endpoint | ↑ | ↑ | ↑ | ↑ |
| **Approve Button** (admin, pending) | Button | Approves pending account | Real API | `POST /api/v1/accounts/{id}/approve` | Sets Account.status=ACTIVE | accounts | accounts.status | settings/CloudIntegrations.jsx, api/account_routes.py, services/account_service.py | settings/Settings.jsx |
| **Validate / Retry Validation Button** | Button | Validates credentials | Real API | `POST /api/v1/accounts/{id}/validate` | AccountService.validate_account → re-runs STS AssumeRole | accounts | accounts.role_arn, accounts.external_id, accounts.status | settings/CloudIntegrations.jsx, api/account_routes.py, services/account_service.py | settings/Settings.jsx |
| **Set Default Button** (active, non-default) | Button | Sets as default account | Real API | `POST /api/v1/accounts/{id}/set-default` | AccountService.set_default_account → unsets others | accounts | accounts.is_default | settings/CloudIntegrations.jsx, api/account_routes.py, services/account_service.py | settings/Settings.jsx |
| **Delete Button** (🗑️, governance-protected) | Button | Unlinks account with confirmation | Real API | `DELETE /api/v1/accounts/{id}` | AccountService.delete_account → removes record | accounts | accounts.id | settings/CloudIntegrations.jsx, api/account_routes.py, services/account_service.py | settings/Settings.jsx |

#### Add Account Modal

| Field | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **AWS Account ID** | Input | 12-digit account number (pattern validated) | N/A | — | — | — | — | settings/CloudIntegrations.jsx | settings/Settings.jsx |
| **IAM Role ARN** | Input | Full ARN (prefix validated) | N/A | — | — | — | — | settings/CloudIntegrations.jsx | settings/Settings.jsx |
| **External ID** | Input | Auto-filled, disabled (from org) | Real API | `GET /api/v1/organization/connection-info` | OrganizationService → returns org's external_id | organizations | organizations.external_id, organizations.name | settings/CloudIntegrations.jsx, api/organization_routes.py, services/organization_service.py | settings/Settings.jsx |
| **Primary Region** | Dropdown | 11 AWS regions (us-east-1 default) | Hardcoded | — | — | — | — | settings/CloudIntegrations.jsx | settings/Settings.jsx |
| **Set as Default Checkbox** | Checkbox | Set this as default account | N/A | — | — | — | — | settings/CloudIntegrations.jsx | settings/Settings.jsx |
| **Cancel Button** | Button | Closes modal, resets form | N/A | — | — | — | — | settings/CloudIntegrations.jsx | settings/Settings.jsx |
| **Link Account Button** | Button | Creates account via API | Real API | `POST /api/v1/accounts` | AccountService.link_aws_account → STS AssumeRole verification | accounts | accounts.aws_account_id, accounts.role_arn, accounts.external_id, accounts.organization_id, accounts.status | settings/CloudIntegrations.jsx | settings/Settings.jsx |

### Billing Tab

#### Current Plan Card

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Plan Name** | Text | e.g. "Professional" | Hardcoded | 🔴 `GET /api/v1/admin/billing` | No real logic — returns hardcoded plan data | — | — | settings/Settings.jsx, api/admin_routes.py, services/organization_service.py | App.js |
| **Billing Cycle** | Text | e.g. "Monthly" | Hardcoded | — | — | — | — | settings/Settings.jsx | App.js |
| **Amount** | Text | e.g. "$299/month" | Hardcoded | — | — | — | — | settings/Settings.jsx | App.js |
| **Next Billing Date** | Text | Future date | Hardcoded | — | — | — | — | settings/Settings.jsx | App.js |
| **Change Plan Button** | Button | No handler — non-functional | N/A | — | — | — | — | settings/Settings.jsx | App.js |
| **Cancel Subscription Button** | Button | No handler — non-functional | N/A | — | — | — | — | settings/Settings.jsx | App.js |

#### Payment Method Card

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Card Type** | Display | e.g. "VISA" | Hardcoded | — | — | — | — | settings/Settings.jsx | App.js |
| **Masked Number** | Text | e.g. "•••• •••• •••• 4242" | Hardcoded | — | — | — | — | settings/Settings.jsx | App.js |
| **Expiry Date** | Text | e.g. "12/2025" | Hardcoded | — | — | — | — | settings/Settings.jsx | App.js |
| **Update Payment Button** | Button | No handler — non-functional | N/A | — | — | — | — | settings/Settings.jsx | App.js |

#### Usage Stats

| Metric | Type | What It Shows | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Clusters Used** | Display | Progress bar (e.g. 3/10) | Hardcoded | — | — | — | — | settings/Settings.jsx | App.js |
| **Nodes Managed** | Display | Progress bar (e.g. 45/100) | Hardcoded | — | — | — | — | settings/Settings.jsx | App.js |
| **API Requests** | Display | Progress bar (e.g. 12,450/50,000) | Hardcoded | — | — | — | — | settings/Settings.jsx | App.js |

---


### Team Governance

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **TeamGovernance** | Card | Team-level governance settings — budget limits, approval requirements | Real API | `GET /api/v1/teams/{id}/governance` | TeamService.get_team_governance → team policy config | teams | teams.governance_config | pages/TeamDetails.jsx | settings/TeamGovernance.jsx |

---

## Unused Backend Endpoints Summary

> 🔴 These backend route files exist but have **no corresponding frontend usage**:

| Backend Route File | Endpoints | Status | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|
| 🔴 `settings_routes.py` | `GET/PATCH /api/v1/settings/profile`, `GET/POST/DELETE /api/v1/settings/integrations` | settingsAPI defined in `api.js` but **never imported** in any component | Not wired | — | — | — | — |
| 🔴 `lab_routes.py` | `GET/POST /api/v1/lab/experiments`, `POST .../start`, `POST .../stop`, `GET .../results` | experimentsAPI defined but **no Lab page exists** in sidebar | Not wired | lab_experiments | lab_experiments.* | — | — |
| 🔴 `smart_tag_routes.py` | Smart tagging endpoints | No frontend integration | Not wired | — | — | — | — |
| 🔴 `auto_tag_routes.py` | Auto-tagging endpoints | No frontend integration | Not wired | auto_tag_rules | auto_tag_rules.* | — | — |
| 🔴 `hygiene_policy_routes.py` | Hygiene policy management | No frontend integration | Not wired | cleanup_policies | cleanup_policies.* | — | — |
| 🔴 `rds_routes.py` | RDS analysis endpoints | No frontend integration | Not wired | rds_analysis | rds_analysis.* | — | — |
| 🔴 `ri_routes.py` | Reserved Instance analysis | No frontend integration | Not wired | ri_utilization | ri_utilization.* | — | — |
| 🔴 `s3_routes.py` | S3 tiering analysis | No frontend integration | Not wired | s3_analysis | s3_analysis.* | — | — |
| 🔴 `transfer_routes.py` | Data transfer optimization | No frontend integration | Not wired | transfer_analysis | transfer_analysis.* | — | — |
| 🔴 `installer_routes.py` | Agent installer routes | Used only during onboarding, not via sidebar | Not wired | — | — | — | — |
| 🔴 `dashboard_routes.py` | Dashboard-specific routes | Frontend uses `metricAPI` instead | Not wired | — | — | — | — |

---

## 15. Admin Panel

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **AdminDashboard** | Page | Admin panel home — tab navigation for Overview, Clients, Health, Billing, Experiments, Orgs, Settings | Real API | `GET /api/v1/admin/dashboard-stats` | AdminService.get_dashboard_stats → org/user/cluster counts | organizations, users, clusters | organizations.id, users.id, clusters.id | App.js | admin/AdminDashboard.jsx |
| **AdminOverview** | Card | Platform-wide stat cards (users, orgs, clusters, cost) + recent activity | Real API | `GET /api/v1/admin/dashboard-stats` | AdminService.get_dashboard_stats | organizations, users, clusters | organizations.name, users.role, clusters.name | admin/AdminDashboard.jsx | admin/AdminOverview.jsx |
| **AdminClients** | Table | List all organizations with status, user count, toggle active/inactive | Real API | `GET /api/v1/admin/clients` | AdminService.list_clients → queries all Organizations | organizations, users | organizations.id, organizations.name, organizations.status | App.js | admin/AdminClients.jsx |
| **AdminHealth** | Card | System health metrics — API latency, DB connections, worker status | Real API | `GET /api/v1/admin/health` | Health check endpoint — pings DB + services | — | — | App.js | admin/AdminHealth.jsx |
| **AdminBilling** | Card | Platform billing overview — plans, revenue, subscription status | Real API | `GET /api/v1/admin/billing` | AdminService.get_billing → aggregated billing data | organizations | organizations.plan, organizations.billing_status | App.js | admin/AdminBilling.jsx |
| **AdminExperiments** | Table | List/manage lab experiments across all organizations | Real API | `GET /api/v1/lab/experiments` | LabService.list_experiments → all experiments | lab_experiments | lab_experiments.name, lab_experiments.status, lab_experiments.type | App.js | admin/AdminExperiments.jsx |
| **AdminOrganizations** | Table | Manage organizations — view details, toggle status, reset passwords | Real API | `GET /api/v1/admin/organizations` | AdminService.list_organizations → paginated org list | organizations, users | organizations.id, organizations.name, organizations.created_at, organizations.status | App.js | admin/AdminOrganizations.jsx |
| **AdminConfig** | Form | Platform-wide configuration settings (feature flags, limits) | Real API | `GET /api/v1/admin/config` | AdminService.get_config → platform settings | — | — | App.js | admin/AdminConfig.jsx |
| **PlatformSettings** | Form | Global platform settings — AWS config, cost explorer settings | Real API | `GET /api/v1/settings/platform` | Reads/writes platform-level config | — | — | admin/AdminConfig.jsx | admin/PlatformSettings.jsx |

---

## 16. Auth

| UI Element | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **Login** | Page | Email + password login form with validation | N/A | `POST /api/v1/auth/login` | AuthService.login → validates credentials, returns JWT | users | users.email, users.password_hash, users.role, users.organization_id | App.js | auth/Login.jsx |
| **Signup** | Page | Organization registration form — company name, email, password | N/A | `POST /api/v1/auth/signup` | AuthService.signup → creates Organization + admin User | organizations, users | organizations.name, users.email, users.password_hash, users.role | App.js | auth/Signup.jsx |

---

## 17. Governance Components

| Component | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **ActiveJITBanner** | Banner | Shows active JIT access session with countdown timer | Real API | `GET /api/v1/approvals/active-jit` | ApprovalService.get_active_jit → checks active JIT sessions | approvals | approvals.status, approvals.expires_at, approvals.jit_scope | pages/Approvals.jsx | governance/ActiveJITBanner.jsx |
| **JITRequestModal** | Modal | Just-in-Time access request form — scope, reason, duration | N/A | `POST /api/v1/approvals/jit-request` | ApprovalService.create_jit_request → creates JIT_ACCESS approval | approvals | approvals.user_id, approvals.type, approvals.jit_scope, approvals.reason_category, approvals.duration_hours | governance/ProtectedButton.jsx | governance/JITRequestModal.jsx |
| **ProtectedButton** | Wrapper | Wraps buttons with permission check — shows lock/JIT request if unauthorized | Computed | — | — | — | — | settings/CloudIntegrations.jsx | governance/ProtectedButton.jsx |

---

## 18. Layout

| Component | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **MainLayout** | Layout | App shell — sidebar navigation, top bar, role-based menu items | Computed | `GET /api/v1/clusters` | ClusterService.list_clusters → badge count for sidebar | clusters | clusters.id (count) | App.js | layout/MainLayout.jsx |

---

## 19. Onboarding Steps

| Step | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **WelcomeStep** | Step | Welcome screen with platform features overview + Get Started CTA | Hardcoded | — | — | — | — | pages/Onboarding.jsx | onboarding/WelcomeStep.jsx |
| **ConnectStep** | Step | AWS CloudFormation setup — generates stack URL, copies external ID | Real API | `POST /api/v1/onboarding/generate-stack-url` | OnboardingService.generate_stack_url → creates CloudFormation URL | accounts | accounts.role_arn, accounts.external_id | pages/Onboarding.jsx | onboarding/ConnectStep.jsx |
| **VerifyStep** | Step | Verifying AWS connection — auto-polls for validation | Real API | `POST /api/v1/accounts/validate/{id}` | AccountService.validate_account → STS assume-role test | accounts | accounts.status, accounts.role_arn | pages/Onboarding.jsx | onboarding/VerifyStep.jsx |
| **SuccessStep** | Step | Success screen with confetti — CTA to go to Dashboard | Hardcoded | — | — | — | — | pages/Onboarding.jsx | onboarding/SuccessStep.jsx |

---

## 20. Cost Optimization Modules

| Component | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **RIHealthCard** | Card | RI waste detection summary — total waste %, savings potential | Real API | `GET /api/v1/ri/analysis` | Queries RI utilization data from Cost Explorer | daily_costs | daily_costs.amount, daily_costs.service | dashboard/widgetRegistry.js | ri/RIHealthCard.jsx |
| **RIAnalysis** | Page | Full RI analysis — underutilized reservations, exchange recommendations | Real API | `GET /api/v1/ri/analysis` | RI utilization analysis via Cost Explorer APIs | daily_costs | daily_costs.amount, daily_costs.service | App.js | ri/RIAnalysis.jsx |
| **S3HealthCard** | Card | S3 intelligent tiering summary — buckets analyzed, savings | Real API | `GET /api/v1/s3/analysis` | S3 bucket analysis via S3/CloudWatch APIs | — | — | dashboard/widgetRegistry.js | s3/S3HealthCard.jsx |
| **S3Analysis** | Page | Full S3 tiering analysis — per-bucket recommendations | Real API | `GET /api/v1/s3/analysis` | S3 intelligent tiering recommendations | — | — | App.js | s3/S3Analysis.jsx |
| **RDSHealthCard** | Card | RDS Multi-AZ analysis summary — instances, potential savings | Real API | `GET /api/v1/rds/analysis` | RDS Multi-AZ analysis via RDS describe APIs | — | — | dashboard/widgetRegistry.js | rds/RDSHealthCard.jsx |
| **RDSAnalysis** | Page | Full RDS analysis — Multi-AZ recommendations per instance | Real API | `GET /api/v1/rds/analysis` | RDS analysis with cost optimization suggestions | — | — | App.js | rds/RDSAnalysis.jsx |
| **TransferHealthCard** | Card | Data transfer optimization summary — cross-AZ/region costs | Real API | `GET /api/v1/transfer/analysis` | Data transfer analysis via CloudWatch/VPC APIs | — | — | dashboard/widgetRegistry.js | transfer/TransferHealthCard.jsx |
| **TransferAnalysis** | Page | Full data transfer analysis — optimization recommendations | Real API | `GET /api/v1/transfer/analysis` | Data transfer cost optimization analysis | — | — | App.js | transfer/TransferAnalysis.jsx |

---

## 21. Experiment Lab

| Component | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **ExperimentLab** | Page | Create/manage A/B cost experiments — compare strategies with controls | Real API | `GET /api/v1/lab/experiments` + `POST /api/v1/lab/experiments` | LabService.list/create experiments → A/B testing engine | lab_experiments | lab_experiments.name, lab_experiments.status, lab_experiments.type, lab_experiments.control_config, lab_experiments.variant_config | App.js | lab/ExperimentLab.jsx |

---

## 22. Account Analytics

| Component | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **AccountAnalytics** | Page | Per-account cost analytics — service breakdown, daily trends, top resources | Real API | `GET /api/v1/metrics/cost` + `GET /api/v1/metrics/instances` | MetricsService.get_cost_metrics + get_instance_metrics | daily_costs, instances, accounts | daily_costs.amount, daily_costs.service, instances.instance_type, accounts.aws_account_id | App.js | pages/AccountAnalytics.jsx |

---

## 23. Shared UI Primitives

| Component | Type | What It Does | Data Source | API Endpoint | Backend Logic | DB Table | Columns Used | Dependencies | File Name |
|---|---|---|---|---|---|---|---|---|---|
| **EmptyState** | Display | Reusable empty state — icon, title, description, optional CTA button | N/A | — | — | — | — | right-sizing/RightSizing.jsx | shared/EmptyState.jsx |
| **GaugeChart** | Graph | Animated circular gauge chart — percentage display with color thresholds | N/A | — | — | — | — | cleanup/summary/HeroMetricsPanel.jsx | shared/GaugeChart.jsx |
| **RiskBadge** | Badge | Risk level indicator badge — LOW/MEDIUM/HIGH/CRITICAL with color coding | N/A | — | — | — | — | governance/JITRequestModal.jsx, pages/Approvals.jsx | shared/RiskBadge.jsx |
| **StatsCard** | Card | Reusable stat card — title, value, trend indicator, sparkline | N/A | — | — | — | — | — | shared/StatsCard.jsx |
