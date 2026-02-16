# User Flow & Technical Architecture

This document maps **every backend API endpoint** to its user flow, service logic, and database tables. Verified against all 37 route files and 103 frontend components.

---

## 1. Authentication & Onboarding

### User Actions
1.  **Sign Up** → Register a new organization (Company Name, Email, Password).
2.  **Login** → Authenticate with email/password.
3.  **Onboarding** → New users land on a "Connect AWS" wizard.
4.  **Connect AWS** → Generate CloudFormation stack URL, deploy in AWS, validate connection.
5.  **Accept Invitation** → Invited users accept an org invitation via token.
6.  **Logout** → Client-side token removal (stateless JWT).

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Sign Up** | `POST /api/v1/auth/signup` | `AuthService.signup`: Creates `Organization` + admin `User`. Bcrypt hashes password. | `organizations`, `users` |
| **Login** | `POST /api/v1/auth/login` | `AuthService.login`: Validates credentials, issues JWT. Updates `last_login`. | `users` |
| **Refresh Token** | `POST /api/v1/auth/refresh` | `AuthService.refresh_token`: Validates refresh token, issues new access token. | `users` |
| **Get Profile** | `GET /api/v1/auth/me` | `AuthService.get_user_profile`: Returns user info including org, team, role. | `users`, `organizations`, `teams` |
| **Update Profile** | `PUT /api/v1/auth/profile` | `AuthService.update_profile`: Updates `User.full_name`. | `users` |
| **Change Password** | `POST /api/v1/auth/change-password` | `AuthService.change_password`: Bcrypt verify + hash update. | `users` |
| **Respond to Invitation** | `POST /api/v1/auth/invitation-response` | `AuthService.respond_to_invitation`: Handles pending user invitation response. | `users`, `organizations` |
| **Logout** | `POST /api/v1/auth/logout` | Client-side token removal. Endpoint is a marker only (stateless JWT). | — |
| **Generate Stack URL** | `POST /api/v1/onboarding/generate-stack-url` | `OnboardingService.generate_stack_url`: Creates signed S3 URL for CloudFormation template with unique `ExternalID`. | `organizations` |
| **Download CF Template** | `GET /api/v1/onboarding/template` | `OnboardingService`: Reads CloudFormation YAML, injects ExternalID. Supports `mode=READ_ONLY|FULL_ACCESS`. | `organizations` |

---

## 2. Cluster Discovery & Management

### User Actions
1.  **Discovery** → System auto-discovers EKS clusters in connected AWS accounts.
2.  **View Clusters** → User sees a list of clusters with cost, node count, health.
3.  **Register Cluster** → User manually registers a cluster.
4.  **Connect AWS Cluster** → User connects an existing AWS cluster via STS (agentless).
5.  **Auto-Install Agent** → User clicks "Inject Agent" to install the agent via cross-account EKS access.
6.  **Generate Install Script** → User generates a Helm install command with cluster token.
7.  **View Details** → User opens a cluster for metrics, policies, schedules, node list.
8.  **Update/Delete** → User edits cluster settings or removes it.
9.  **Spot Fallback** → Agent triggers fallback node request on Spot interruption.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Clusters** | `GET /api/v1/clusters` | `ClusterService.list_clusters`: RBAC filtered, pagination + sorting + search + status/type/region/account filters. | `clusters`, `accounts` |
| **Register Cluster** | `POST /api/v1/clusters` | `ClusterService.register_cluster`: Manual cluster registration. | `clusters` |
| **Trigger Discovery** | `POST /api/v1/clusters/discover` | `ClusterService.discover_clusters`: Uses `boto3` to list EKS clusters. Creates/updates records. Syncs node groups. | `clusters`, `accounts` |
| **Connect AWS Cluster** | `POST /api/v1/clusters/connect-aws` | `ClusterService.connect_aws_cluster`: Connects via STS AssumeRole (agentless). | `clusters` |
| **Cluster Details** | `GET /api/v1/clusters/{id}` | `ClusterService.get_cluster`: Returns detailed cluster stats (cost, savings, node breakdown). | `clusters`, `instances` |
| **Update Cluster** | `PUT /api/v1/clusters/{id}` | `ClusterService.update_cluster`: Updates cluster details. | `clusters` |
| **Delete Cluster** | `DELETE /api/v1/clusters/{id}` | `ClusterService.delete_cluster`: Validates no active instances, removes. | `clusters`, `instances` |
| **Verify Connection** | `POST /api/v1/clusters/verify/{id}` | `ClusterService.verify_connection`: Checks `last_heartbeat` within 10min. | `clusters` |
| **Cluster Nodes** | `GET /api/v1/clusters/{id}/nodes` | `ClusterService.get_cluster_nodes`: Returns node list with utilization. | `instances` |
| **Auto-Install Agent** | `POST /api/v1/clusters/{id}/auto-install` | `ClusterService.auto_install_agent`: Cross-account role assumption → EKS access entry → Helm deploy. | `clusters` |
| **Generate Install Script** | `POST /api/v1/clusters/{id}/install-script` | `ClusterService.generate_install_script`: Generates Helm command with unique API key. | `clusters` |
| **Update Resource Costs** | `PUT /api/v1/clusters/{id}/resource-costs` | `ClusterService.update_resource_costs`: Updates CPU/Mem/Storage/Ingress/Egress costs. | `clusters` |
| **Spot Fallback** | `POST /api/v1/clusters/{id}/fallback` | Handles Spot interruption fallback request from agent. | `clusters`, `instances` |

---

## 3. Agent Communication

### User Actions
*(Internal — agent communicates with backend, no direct user interaction)*

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Register Agent** | `POST /api/v1/agents/register` | Validates API key → sets cluster status to `ACTIVE`, `agent_installed='Y'`, updates `last_heartbeat`. | `clusters` |
| **Deregister Agent** | `POST /api/v1/agents/deregister` | Validates API key → sets cluster status to `INACTIVE`, `agent_installed='N'`. | `clusters` |
| **Heartbeat** | `POST /api/v1/agents/heartbeat` | Validates API key → updates `last_heartbeat`. Auto-activates cluster if inactive. | `clusters` |

### Installer Scripts

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Linux Installer** | `GET /api/v1/installer/linux` | Dynamically generates shell script with pre-filled `cluster_id`, `api_key`, backend URL. Includes K8s manifest. | — |
| **macOS Installer** | `GET /api/v1/installer/macos` | Alias to Linux installer (kubectl compatible). | — |

---

## 4. Dashboard & Metrics

### User Actions
1.  **View Dashboard** → User sees high-level KPIs: Total Cost, Savings, Spot Ratio.
2.  **Three Pricing Models** → Actual Cost (Cost Explorer), Resources Cost (sum of instances), Optimization Cost (savings potential).
3.  **Cost Trends** → Daily cost chart and savings analysis.
4.  **Fleet Composition** → Spot vs. On-Demand vs. instances by type/state.
5.  **Activity Feed** → Latest audit log entries.
6.  **Cluster Health** → Cluster list with health indicators.
7.  **Pending Approvals** → Pending JIT requests.
8.  **Customize Layout** → User adds/removes/reorders dashboard widgets.

### Technical Implementation — Dashboard Routes (`/dashboard`)

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Dashboard Overview** | `GET /api/v1/dashboard/overview` | Returns all 3 pricing models: actual cost (Cost Explorer), resources cost (Redis cache), optimization cost (hygiene waste). | `daily_costs`, `instances`, `clusters`, `accounts` |
| **Cost Breakdown** | `GET /api/v1/dashboard/cost-breakdown` | Cost by category (Compute, Storage, Network, Security, Management, Others) from Cost Explorer. | `daily_costs`, `accounts` |
| **Savings Projection** | `GET /api/v1/dashboard/savings-projection` | Current vs optimized spend, savings breakdown (hygiene waste + optimization opportunities). | `daily_costs`, `instances`, `accounts` |
| **Fleet Composition** | `GET /api/v1/dashboard/fleet-composition` | Instance breakdown by type, lifecycle (spot/on-demand), state (running/stopped). Live DB query. | `instances`, `clusters`, `accounts` |
| **Activity Feed** | `GET /api/v1/dashboard/activity-feed` | Recent audit events, configurable limit. | `audit_logs` |

### Technical Implementation — Metrics Routes (`/metrics`)

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Dashboard KPIs** | `GET /api/v1/metrics/dashboard` | `MetricsService.get_dashboard_kpis`: Total/active instances, Spot split, total cost, savings. | `daily_costs`, `instances`, `clusters` |
| **Cost Metrics** | `GET /api/v1/metrics/cost` | `MetricsService.get_cost_metrics`: Detailed cost breakdown. Supports cluster/team/date filters. | `daily_costs` |
| **Instance Metrics** | `GET /api/v1/metrics/instances` | `MetricsService.get_instance_metrics`: Instance counts by state, lifecycle, architecture. | `instances` |
| **Cost Time Series** | `GET /api/v1/metrics/cost/timeseries` | `MetricsService.get_cost_time_series`: Daily cost data points. Default 30 days. | `daily_costs` |
| **Cluster Metrics** | `GET /api/v1/metrics/cluster/{id}` | `MetricsService.get_cluster_metrics`: Per-cluster instance counts, spot split, status. | `instances`, `clusters` |
| **Team Summary** | `GET /api/v1/metrics/teams/{id}/summary` | `MetricsService.get_team_consolidated_stats`: Team cost/savings/waste aggregation. RBAC enforced. | `users`, `instances`, `clusters`, `teams` |
| **Account Summary** | `GET /api/v1/metrics/accounts/{id}/summary` | `MetricsService.get_account_summary`: Per-account cost/waste aggregation. | `daily_costs`, `accounts` |
| **Cost by Service** | `GET /api/v1/metrics/cost/breakdown` | `MetricsService.get_cost_breakdown`: AWS service categories (EC2, Storage, Database, Network, Security, Management). | `daily_costs` |
| **Waste Breakdown** | `GET /api/v1/metrics/waste/breakdown` | `MetricsService.get_waste_breakdown`: Hygiene waste + optimization waste (A+B) for financial dashboard. | `instances`, `daily_costs`, `accounts` |

---

## 5. Billing & Cost Explorer

### User Actions
1.  **View Billing** → User views subscription plan, payment method, usage stats.
2.  **Manage Subscription** → User opens Stripe Billing Portal.
3.  **Cost Summary** → User views cost breakdown by compute/resources for a period.
4.  **Daily Trends** → User views daily cost trending chart.
5.  **Cost by Service** → User views top cost-consuming AWS services.
6.  **Sync Status** → User checks Cost Explorer data freshness per account.
7.  **Manual Sync** → Admin triggers manual Cost Explorer refresh.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Billing Status** | `GET /api/v1/billing/status` | Returns current org subscription/plan status. | `organizations` |
| **Stripe Portal** | `POST /api/v1/billing/portal-session` | Creates Stripe Billing Portal session, returns redirect URL. | `organizations` |
| **Stripe Webhook** | `POST /api/v1/billing/webhook` | Handles `checkout.session.completed`, `customer.subscription.deleted`. | `organizations` |
| **Cost Summary** | `GET /api/v1/billing/cost-summary` | Cost Explorer breakdown by compute/resources. Supports `period` (month/week/day/quarter) and `account_id` filter. | `daily_costs`, `accounts` |
| **Daily Costs** | `GET /api/v1/billing/daily-costs` | Daily cost trend for last N days (1-90). | `daily_costs`, `accounts` |
| **Costs by Service** | `GET /api/v1/billing/costs-by-service` | Top AWS services by spend with breakdown. Supports limit (1-50). | `daily_costs`, `accounts` |
| **Sync Status** | `GET /api/v1/billing/sync-status` | Per-account Cost Explorer data freshness and health. | `daily_costs`, `accounts` |
| **Trigger Sync** | `POST /api/v1/billing/trigger-sync` | Manually triggers Cost Explorer sync (Celery task). Optional `account_id`. | `daily_costs`, `accounts` |

---

## 6. Cost Optimization (Hibernation & Rightsizing)

### User Actions
1.  **Hibernation Schedule** → Create a weekly schedule to stop clusters during off-hours.
2.  **Strategy Selection** → Pick a hibernation strategy (Namespace Sleep, Node Scale-Down, Full Hibernation, Custom).
3.  **Rightsizing** → View recommendations to downsize underutilized instances.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Schedules** | `GET /api/v1/hibernation/schedules` | `HibernationService.list_schedules`: Returns configs linked to clusters. | `hibernation_schedules` |
| **Create Schedule** | `POST /api/v1/hibernation/schedules` | `HibernationService.create_schedule`: Saves 7×24 hour matrix. Agent polls this. | `hibernation_schedules` |
| **Update Schedule** | `PUT /api/v1/hibernation/schedules/{id}` | `HibernationService.update_schedule`: Updates weekly grid and settings. | `hibernation_schedules`, `audit_logs` |
| **Toggle Schedule** | `POST /api/v1/hibernation/schedules/{id}/toggle` | `HibernationService.toggle_schedule`: Flips `is_active`. | `hibernation_schedules` |
| **Strategy List** | `GET /api/v1/hibernation/strategies` | Returns hardcoded strategy definitions. | — |
| **Execution History** | `GET /api/v1/hibernation/history` | `HibernationService.get_history`: Past activation/deactivation logs. | `audit_logs` |
| **Cluster Policy** | `GET /api/v1/policies/cluster/{id}` | `PolicyService.get_policy`: Returns Spot config (e.g., "70% Spot"). | `cluster_policies` |
| **Rightsizing** | `GET /api/v1/optimization/rightsizing/{id}` | `Rightsizer.analyze_resource_usage`: CPU/Mem analysis against instance specs. | `instances` |

---

## 7. Governance & Teams

### User Actions
1.  **Team Management** → Admin creates teams, invites members.
2.  **RBAC** → Admin assigns roles (Admin, Editor, Viewer).
3.  **Custom Roles** → Admin creates custom roles with granular permissions.
4.  **JIT Access** → Users request temporary elevated access with scope, reason, duration.
5.  **Approvals** → Admins approve/reject/revoke JIT requests. Delegated grants supported.

### Technical Implementation — Teams & Members

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Teams** | `GET /api/v1/teams` | `TeamService.list_teams`: RBAC filtered. | `teams`, `users` |
| **Create Team** | `POST /api/v1/teams/` | `TeamService.create_team`: Admin-only. | `teams` |
| **Team Stats** | `GET /api/v1/teams/{id}/stats` | `TeamService.get_team_stats`: Member count + cost aggregation. | `users`, `teams` |
| **Invite Member** | `POST /api/v1/teams/{id}/invite` | `TeamService.invite_member`: Creates `PENDING_INVITE` User with default password. | `users`, `teams` |
| **Assign to Team** | `POST /api/v1/teams/{id}/assign` | `TeamService.assign_member`: RBAC check, updates `User.team_id`. | `users`, `teams` |
| **Team Governance** | `GET /api/v1/teams/{id}/governance` | `TeamService.get_team_governance`: Team-level policy config. | `teams` |

### Technical Implementation — Organization Members

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Members** | `GET /api/v1/organization/members` | `OrganizationService.list_members`: All Users in organization. | `users`, `teams`, `roles` |
| **Add Member** | `POST /api/v1/organization/members` | `OrganizationService.create_invitation`: Creates user with default password. ORG_ADMIN only. | `users` |
| **Update Member** | `PATCH /api/v1/organization/members/{id}` | `OrganizationService.update_member_role`: Enforces hierarchy. | `users` |
| **Remove Member** | `DELETE /api/v1/organization/members/{id}` | `OrganizationService.remove_member`: ORG_ADMIN only. | `users` |
| **List Invitations** | `GET /api/v1/organization/invitations` | `OrganizationService.list_invitations`: Pending invites. | `users` |
| **Accept Invitation** | `POST /api/v1/organization/invitations/{token}/accept` | `OrganizationService.accept_invitation`: Public endpoint, token auth. Creates user with `must_reset_password=True`. | `users`, `organizations` |

### Technical Implementation — Roles & Permissions

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Roles** | `GET /api/v1/roles` | `RoleService.list_roles`: Available roles and permission sets. | `roles`, `permissions`, `role_permissions` |
| **List Permissions** | `GET /api/v1/roles/permissions` | `RoleService.list_permissions`: All permission slugs grouped by module. | `permissions` |
| **Create/Update Role** | `POST/PUT /api/v1/roles` | `RoleService.update_role`: Updates name/description/permissions. | `roles`, `role_permissions` |
| **Delete Role** | `DELETE /api/v1/roles/{id}` | `RoleService.delete_role`: Blocks system role deletion. | `roles` |
| **Assign Role** | `POST /api/v1/roles/assign` | Assigns role to user. | `users`, `roles` |
| **Set User Permissions** | `POST /api/v1/users/{id}/permissions` | `RoleService.update_user_permissions`: Custom permission assignment. ORG_ADMIN only. | `users`, `permissions` |

### Technical Implementation — Approvals & JIT

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Create Approval** | `POST /api/v1/approvals` | `ApprovalService.create_approval`: Generic access request. | `approvals` |
| **List Approvals** | `GET /api/v1/approvals` | `ApprovalService.list_approvals`: RBAC filtered (own/team/org). | `approvals`, `users` |
| **JIT Request** | `POST /api/v1/approvals/jit-request` | `ApprovalService.create_jit_request`: Time-bound feature access with scope, reason, duration. | `approvals` |
| **My JIT Approvals** | `GET /api/v1/approvals/my-jit-approvals` | `ApprovalService.get_active_jit_approvals`: User's active JIT grants. | `approvals` |
| **Active Window** | `GET /api/v1/approvals/active-window` | `ApprovalService.get_active_window`: Active execution window check (`expires_at > now`). | `approvals` |
| **Approve** | `POST /api/v1/approvals/{id}/approve` | `ApprovalService.approve`: Sets APPROVED_ACTIVE, calculates `expires_at`, SSE broadcast. | `approvals` |
| **Reject** | `POST /api/v1/approvals/{id}/reject` | `ApprovalService.reject`: Sets REJECTED. Validates approver role. | `approvals` |
| **Revoke** | `POST /api/v1/approvals/{id}/revoke` | `ApprovalService.revoke`: Sets REVOKED, clears `expires_at`, SSE broadcast. | `approvals` |
| **Accept Grant** | `POST /api/v1/approvals/{id}/accept` | `ApprovalService.accept_grant`: User accepts delegated grant. | `approvals` |
| **Delegated Grant** | `POST /api/v1/approvals/delegate` | `ApprovalService.create_delegated_approvals`: Admin grants access to multiple users. | `approvals` |

### Technical Implementation — Permission System (JIT Feature Access)

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Check Permission** | `POST /api/v1/permissions/check` | `PermissionService.check_permission`: Non-blocking check for feature access. Returns status + active ticket. | `approvals`, `users` |
| **My Features** | `GET /api/v1/permissions/my-features` | `PermissionService.list_features`: All features (immediate, requestable, denied). | `approvals`, `users`, `roles` |
| **Revoke Access** | `DELETE /api/v1/permissions/revoke/{user_id}/{feature_id}` | `PermissionService.revoke_feature_access`: Admin revokes user's JIT access. | `approvals` |
| **Feature Registry** | `GET /api/v1/permissions/registry` | Returns complete feature catalog with approval requirements. | — (in-memory) |
| **SSE Stream** | `GET /api/v1/permissions/stream` | Server-Sent Events for real-time permission updates (grant/revoke/expire). Token via query param. | `approvals` |

---

## 8. Resource Hygiene (Cleanup)

### User Actions
1.  **Scan Resources** → Triggers a scan to find unused EBS volumes, old snapshots, unattached EIPs.
2.  **Region Selection** → Specific region or all regions (Global Scan). Cache bypass with `force_refresh`.
3.  **Check Dependencies** → Verify resource dependencies before cleanup.
4.  **Execute Cleanup** → Select orphaned resources and delete (RBAC + optional approval).
5.  **Discover Resources** → Search for resource IDs by type (for JIT approval scoping).
6.  **View Total Cost** → Total discovered cost using Cost Explorer or instance pricing fallback.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Hygiene Scan** | `GET /api/v1/hygiene/scan/{accountId}` | `HygieneService.scan_resources`: STS AssumeRole → parallel region scan (EC2/EBS/S3/RDS/VPC/IAM). Identifies waste. Supports `regions` and `force_refresh`. | `accounts` |
| **Check Dependencies** | `GET /api/v1/hygiene/check-dependencies` | `HygieneService.check_dependencies`: Checks AMI refs, attachments, associations. | — (AWS API only) |
| **Execute Cleanup** | `POST /api/v1/hygiene/action` | `HygieneService.execute_action`: RBAC + optional approval; `boto3` DELETE/RELEASE/STOP. Logs to audit. | `accounts`, `audit_logs` |
| **Discover Resources** | `GET /api/v1/hygiene/discover` | `HygieneService.discover_resources`: Search for resource IDs by type for JIT scoping. | `accounts` |
| **Total Cost** | `GET /api/v1/hygiene/total-cost` | Uses Cost Explorer data or EC2 instance pricing fallback. Dual-source with priority. | `daily_costs`, `instances` |
| **Cost by Service** | `GET /api/v1/hygiene/cost-services` | *DEPRECATED* — breakdown moved to scan result. Returns empty for backward compat. | — |

### Hygiene Policies (Automated Cleanup Rules)

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Policies** | `GET /api/v1/hygiene-policies/` | DB query on `HygienePolicy` by org. Supports `resource_type` filter. | `hygiene_policies` |
| **Create Policy** | `POST /api/v1/hygiene-policies/` | Creates policy with resource type, conditions, action, priority. ORG_ADMIN only. | `hygiene_policies` |
| **Get Policy** | `GET /api/v1/hygiene-policies/{id}` | Single policy with org ownership check. | `hygiene_policies` |
| **Update Policy** | `PATCH /api/v1/hygiene-policies/{id}` | Partial update with ownership check. ORG_ADMIN only. | `hygiene_policies` |
| **Delete Policy** | `DELETE /api/v1/hygiene-policies/{id}` | Ownership check + delete. ORG_ADMIN only. | `hygiene_policies` |

---

## 9. Tagging & Templates

### User Actions
1.  **Tag Policies** → Admin creates policies to enforce tag standards (required keys, allowed values).
2.  **Tag Templates** → Admin creates reusable tag templates with dynamic variables.
3.  **Tag Management** → User views/edits tags on individual resources or in bulk.
4.  **Auto-Tag Rules** → Admin creates rules for automated tagging with conditions, test/execute modes.
5.  **Smart Tags** → Admin runs TTL and Schedule-based smart tag processing.

### Technical Implementation — Tag Policies

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Tag Policies** | `GET /api/v1/tags/policies` | `TagPolicyService.list_policies`: By `organization_id`. | `tag_policies` |
| **Create Tag Policy** | `POST /api/v1/tags/policies` | `TagPolicyService.create_policy`: Enforcement rule for a tag key. | `tag_policies` |
| **Update Tag Policy** | `PUT /api/v1/tags/policies/{id}` | `TagPolicyService.update_policy`: Updates enforcement level, allowed values. | `tag_policies` |
| **Delete Tag Policy** | `DELETE /api/v1/tags/policies/{id}` | Removes tag policy. | `tag_policies` |

### Technical Implementation — Tag Templates

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Templates** | `GET /api/v1/tags/templates/` | DB query by `organization_id`. | `tag_templates` |
| **Create Template** | `POST /api/v1/tags/templates/` | Creates with dynamic variable support. | `tag_templates` |
| **Update Template** | `PUT /api/v1/tags/templates/{id}` | Updates name, tags, scope. | `tag_templates` |
| **Delete Template** | `DELETE /api/v1/tags/templates/{id}` | CRUD delete. | `tag_templates` |

### Technical Implementation — Tag Management (Resource-level)

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Get Resource Tags** | `GET /api/v1/tags/resources/{type}/{id}` | `TagManagementService.get_resource_tags` + `TagSuggestionService.suggest_tags_for_resource`: Returns current tags + AI suggestions. | `tag_policies`, `accounts` |
| **Update Resource Tags** | `POST /api/v1/tags/resources/{type}/{id}` | `TagManagementService.update_resource_tags`: `boto3 create_tags`; validates against tag policies. | `tag_policies`, `accounts` |
| **Bulk Tag** | `POST /api/v1/tags/resources/bulk` | `TagManagementService.bulk_update_tags`: Apply tags to multiple resources. | `tag_policies`, `accounts` |

### Technical Implementation — Auto-Tag Rules

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Rules** | `GET /api/v1/tags/rules/` | `AutoTagService.list_rules`: Active/all rules for org. | `auto_tag_rules` |
| **Create Rule** | `POST /api/v1/tags/rules/` | `AutoTagService.create_rule`: Admin only. | `auto_tag_rules` |
| **Get Rule** | `GET /api/v1/tags/rules/{id}` | `AutoTagService.get_rule`: Single rule. | `auto_tag_rules` |
| **Test Rule** | `POST /api/v1/tags/rules/{id}/test` | `AutoTagService.test_rule`: Preview matches against an account. | `auto_tag_rules`, `accounts` |
| **Execute Rule** | `POST /api/v1/tags/rules/{id}/execute` | `AutoTagService.execute_rule`: Admin applies rule to an account. | `auto_tag_rules`, `accounts` |
| **Delete Rule** | `DELETE /api/v1/tags/rules/{id}` | Soft-delete (`is_active=False`). Admin only. | `auto_tag_rules` |
| **Preview Tags** | `POST /api/v1/tags/rules/preview` | `AutoTagService.preview_tags`: Live preview for Policy Builder Wizard. | — |
| **Available Variables** | `GET /api/v1/tags/rules/variables` | `AutoTagService.get_available_variables`: Dynamic variable list for "Value Type" dropdown. | — |

### Technical Implementation — Smart Tags

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Run Smart Tags** | `POST /api/v1/tags/smart/run` | `SmartTagService.process_smart_tags`: TTL + Schedule tag processing. Supports `dry_run`. | `accounts` |

---

## 10. Node Templates

### User Actions
1.  **View Templates** → User sees a grid of node templates with architecture, disk, instance families.
2.  **Create/Edit Template** → User configures architecture, root volume, instance families, Spot config.
3.  **Set Default** → User designates a template as the default.
4.  **Delete Template** → User removes an unused template.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Templates** | `GET /api/v1/templates` | `TemplateService.list_templates`: By organization. | `node_templates` |
| **Create Template** | `POST /api/v1/templates` | `TemplateService.create_template`: Architecture, families, strategy. | `node_templates` |
| **Update Template** | `PUT /api/v1/templates/{id}` | `TemplateService.update_template`: Validates ownership. | `node_templates` |
| **Delete Template** | `DELETE /api/v1/templates/{id}` | `TemplateService.delete_template`: Blocks deletion of last default. | `node_templates` |
| **Set Default** | `POST /api/v1/templates/{id}/set-default` | `TemplateService.set_default`: Unsets others, sets `is_default='Y'`. | `node_templates` |
| **Template Options** | `GET /api/v1/templates/options` | Returns available instance families/sizes. *Endpoint exists but unused by frontend.* | — |

---

## 11. AtharvaAi Optimization Engine

### User Actions
1.  **Engine Status** → View Running/Paused state, toggle auto-rebalancing.
2.  **Pool Rankings** → View ranked instance pools by compliance, risk, cost, capacity.
3.  **Pool Details** → Inspect pool across 6 tabs (Overview, Specs, Risk, Cost, Usage, Switch Preview).
4.  **Switch Pool** → Switch to a better-ranked pool with safety checks.
5.  **Blacklist** → Blacklist/unblacklist a pool from optimization.
6.  **Recommendations** → AI-generated optimization recommendations.
7.  **Risk Monitor** → Real-time risk indicators and historical trends.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Engine Status** | `GET /api/v1/atharva/status` | `AtharvaService.get_system_status`: Running/Paused. *Mock/in-memory.* | — |
| **Update Settings** | `POST /api/v1/atharva/settings` | `AtharvaService.update_settings`: Toggles auto-rebalancing. *In-memory.* | — |
| **Activity Feed** | `GET /api/v1/atharva/activity` | `AtharvaService.get_activity`: Pre-seeded mock events. | — |
| **Pool Rankings** | `GET /api/v1/atharva/pools/rankings` | `AtharvaService.get_pool_rankings`: Ranked pools with filtering pipeline stats. *Mock.* | — |
| **Pool Details** | `GET /api/v1/atharva/pools/{id}/details` | `AtharvaService.get_pool_details`: 6-tab detail view. *Mock.* | — |
| **Switch Pool** | `POST /api/v1/atharva/pools/switch` | `AtharvaService.switch_pool`: Safety checks + pool switch. *Mock.* | — |
| **Add to Blacklist** | `POST /api/v1/atharva/blacklist` | `AtharvaService.add_to_blacklist`: In-memory blacklist. | — |
| **View Blacklist** | `GET /api/v1/atharva/blacklist` | `AtharvaService.get_blacklist`: Returns blacklisted pools. | — |
| **Remove from Blacklist** | `DELETE /api/v1/atharva/blacklist/{poolId}` | `AtharvaService.remove_from_blacklist`. | — |
| **Node Templates** | `GET/POST/PUT/DELETE /api/v1/atharva/node-templates` | In-memory CRUD for engine node templates. | — |
| **Recommendations** | `GET /api/v1/atharva/recommendations` | `AtharvaService.get_recommendations`: *Hardcoded mock.* | — |
| **Risk History** | `GET /api/v1/atharva/risk-history` | `AtharvaService.get_risk_history`: Mock time-series risk data. | — |

---

## 12. Automation & Governance Settings

### User Actions
1.  **View Policies** → Admin views governance configuration (approval requirements, strict mode, automation config).
2.  **Update Policies** → Admin toggles governance, strict mode, required tags, automation config.
3.  **Run Autopilot** → Admin triggers automated cleanup for a specific account.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Get Policies** | `GET /api/v1/governance/policies` | Returns org governance flags: `is_governance_enabled`, `is_strict_mode`, `require_automation_approval`, `required_tags`, `automation_config`. | `organizations` |
| **Update Policies** | `PATCH /api/v1/governance/policies` | Updates `Organization` fields. ORG_ADMIN only. | `organizations` |
| **Run Autopilot** | `POST /api/v1/governance/run-autopilot` | `GovernanceService.run_automated_cleanup`: Scans + auto-executes, logs as 'System Autopilot'. | `organizations`, `accounts`, `audit_logs` |

---

## 13. Audit & Logging

### User Actions
1.  **View Logs** → Admin views history of all sensitive actions.
2.  **Filter Logs** → Filter by actor, date, event type, or role.
3.  **Export** → Download audit logs as JSON.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Get Audit Logs** | `GET /api/v1/audit/logs` | `AuditService.get_logs`: Paginated with filters (date, actor, event, outcome). | `audit_logs` |
| **Export Logs** | `GET /api/v1/audit/export` | `AuditService`: Full result set as JSON download. | `audit_logs` |

---

## 14. Settings & Profile Management

### User Actions
1.  **View/Edit Profile** → Update display name.
2.  **Change Password** → Requires current password.
3.  **Preferences** → Dashboard layout, theme. Validated per role.
4.  **Integrations** → Manage external integrations (CRUD).
5.  **Cloud Connections** → View connection info (External ID, Platform Account ID), regenerate External ID.

### Technical Implementation — User Routes (`/users`)

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Update Profile** | `PATCH /api/v1/users/me` | Direct `User.full_name` update. | `users` |
| **Update Preferences** | `PATCH /api/v1/users/me/preferences` | Validates widget keys per role, merges with existing preferences. | `users` |
| **Get Preferences** | `GET /api/v1/users/me/preferences` | Returns preferences + role. | `users` |

### Technical Implementation — Settings Routes (`/settings`)

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Get Profile** | `GET /api/v1/settings/profile` | `SettingsService.get_profile`: Full profile details. | `users` |
| **Update Profile** | `PATCH /api/v1/settings/profile` | `SettingsService.update_profile`: Profile info update. | `users` |
| **List Integrations** | `GET /api/v1/settings/integrations` | `SettingsService.get_integrations`: Active integrations. | `users` |
| **Add Integration** | `POST /api/v1/settings/integrations` | `SettingsService.add_integration`: FULL access only. | `users` |
| **Delete Integration** | `DELETE /api/v1/settings/integrations/{id}` | `SettingsService.delete_integration`: FULL access only. | `users` |

### Technical Implementation — Connection Management (`/organization`)

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Connection Info** | `GET /api/v1/organization/connection-info` | Returns External ID + Platform Account ID (auto-detected via DB config → env var → STS) + CF template URL. | `organizations`, `system_config` |
| **Regenerate External ID** | `POST /api/v1/organization/connection-info/regenerate` | `OrganizationService.regenerate_external_id`: New 32-char random ID. | `organizations` |

### Technical Implementation — Accounts (`/accounts`)

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Accounts** | `GET /api/v1/accounts` | `AccountService.list_accounts`: RBAC filtered. | `accounts` |
| **Link Account** | `POST /api/v1/accounts` | `AccountService.link_aws_account`: STS AssumeRole verification. EXECUTION access. | `accounts` |
| **Get Account** | `GET /api/v1/accounts/{id}` | `AccountService.get_account`: Org-scoped. | `accounts` |
| **Validate Account** | `POST /api/v1/accounts/{id}/validate` | `AccountService.validate_account`: Re-runs STS AssumeRole. | `accounts` |
| **Set Default** | `POST /api/v1/accounts/{id}/set-default` | `AccountService.set_default_account`: Unsets others. FULL access. | `accounts` |
| **Disconnect Account** | `POST /api/v1/accounts/{id}/disconnect` | `AccountService.disconnect_account`: Strips credentials, preserves history. FULL access. | `accounts` |
| **Delete Account** | `DELETE /api/v1/accounts/{id}` | `AccountService.delete_account`: Full removal. FULL access. | `accounts` |

---

## 15. Cost Optimization Modules

### User Actions
1.  **RI Analysis** → View Reserved Instance utilization, waste, and actionable recommendations.
2.  **Savings Plans** → Analyze Savings Plans utilization and coverage.
3.  **Unified Coverage** → Combined RI + SP coverage to prevent double-counting.
4.  **S3 Tiering** → Analyze S3 buckets for tiering optimization.
5.  **RDS Multi-AZ** → Review RDS instances for Multi-AZ optimization.
6.  **Data Transfer** → Identify cross-AZ/region transfer costs.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **RI Overview** | `GET /api/v1/ri/overview` | `RIAnalysisService.get_overview`: Total RIs, underutilization, waste. | `ri_utilization` |
| **List RIs** | `GET /api/v1/ri/list` | `RIAnalysisService.list_ris`: All RIs with utilization. Supports `underutilized_only` + `account_id` filters. | `ri_utilization` |
| **RI Recommendations** | `GET /api/v1/ri/{id}/recommendations` | `RIAnalysisService.get_recommendations`: Detailed actions + savings for a specific RI. | `ri_utilization` |
| **Analyze RI** | `POST /api/v1/ri/analyze` | `RIAnalysisService.analyze_utilization`: Triggers analysis. Configurable lookback (7/30/90 days). ORG_ADMIN. | `ri_utilization` |
| **Execute RI Action** | `POST /api/v1/ri/{id}/action` | Executes action: sell_marketplace, modify, convert, monitor. ORG_ADMIN. | `ri_utilization` |
| **SP Overview** | `GET /api/v1/ri/savings-plans/overview` | `SavingsPlanService.get_overview`: Savings Plans health. | — |
| **Analyze SP** | `POST /api/v1/ri/savings-plans/analyze` | `SavingsPlanService.analyze`: Triggers SP analysis. Configurable lookback. ORG_ADMIN. | — |
| **Unified Coverage** | `GET /api/v1/ri/unified-coverage` | Combined RI + SP report preventing double-counting. | `ri_utilization` |
| **S3 Overview** | `GET /api/v1/s3/overview` | `S3TieringService.get_overview`: S3 optimization summary. | — |
| **Analyze S3** | `POST /api/v1/s3/analyze` | `S3TieringService.analyze_all_buckets`: Triggers bucket analysis. ORG_ADMIN. | — |
| **RDS Overview** | `GET /api/v1/rds/overview` | `RDSAnalysisService.get_overview`: RDS optimization summary. | — |
| **Analyze RDS** | `POST /api/v1/rds/analyze` | `RDSAnalysisService.analyze_all`: Triggers Multi-AZ analysis. ORG_ADMIN. | — |
| **Transfer Overview** | `GET /api/v1/transfer/overview` | `TransferService.get_overview`: Transfer cost summary. | — |
| **Analyze Transfer** | `POST /api/v1/transfer/analyze` | `TransferService.analyze_all`: Triggers transfer analysis. Configurable lookback. ORG_ADMIN. | — |

---

## 16. Admin Panel (Super Admin)

### User Actions
1.  **Platform Overview** → Stats, org/user/cluster counts.
2.  **Client Management** → List/toggle/reset clients. View details.
3.  **Organization Management** → List/toggle organizations.
4.  **System Config** → Get/set config values (Safe Mode, Risk TTL, etc.).
5.  **Billing** → Platform billing info.
6.  **Platform AWS Identity** → Connect/disconnect platform AWS credentials.
7.  **System Health** → API/DB/service health check.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Dashboard Stats** | `GET /api/v1/admin/dashboard` | `AdminService.get_dashboard_stats`: Org/user/cluster counts. | `organizations`, `users`, `clusters` |
| **Platform Stats** | `GET /api/v1/admin/stats` | `AdminService.get_platform_stats`: Platform-wide metrics. | `organizations`, `users`, `clusters` |
| **List Organizations** | `GET /api/v1/admin/organizations` | `AdminService.list_organizations`: Paginated org list with search. | `organizations`, `users` |
| **Toggle Organization** | `POST /api/v1/admin/organizations/{id}/toggle` | `AdminService.toggle_organization_status`: Active/inactive. | `organizations` |
| **List Clients** | `GET /api/v1/admin/clients` | `AdminService.list_clients`: Paginated user list. Filters: search, is_active, created_after/before. | `organizations`, `users` |
| **Client Details** | `GET /api/v1/admin/clients/{id}` | `AdminService.get_client_details`: Full user management view. | `users` |
| **Toggle Client** | `POST /api/v1/admin/clients/{id}/toggle` | `AdminService.toggle_client_status`: Enable/disable user. | `users` |
| **Reset Password** | `POST /api/v1/admin/clients/{id}/reset-password` | `AdminService.reset_client_password`: Sets new password. | `users` |
| **Billing** | `GET /api/v1/admin/billing` | `AdminService.get_billing_info`: Platform billing data. | `organizations` |
| **Get Config** | `GET /api/v1/admin/config/{key}` | Reads `SystemConfig` by key. Defaults for SAFE_MODE, RISK_TTL, etc. | `system_config` |
| **Update Config** | `PATCH /api/v1/admin/config` | Upserts `SystemConfig` record. | `system_config` |
| **Platform Connection** | `GET /api/v1/admin/platform/connection` | `AdminService.get_platform_connection`: AWS connection status. | `system_config` |
| **Connect Platform** | `POST /api/v1/admin/platform/connect` | `AdminService.update_platform_credentials`: Stores AWS access keys. | `system_config` |
| **Disconnect Platform** | `DELETE /api/v1/admin/platform/disconnect` | `AdminService.disconnect_platform`: Removes AWS credentials. | `system_config` |
| **System Health** | `GET /api/v1/health/system` | `HealthService.check_overall_health`: Pings DB + services. Super Admin only. | — |

---

## 17. Experiment Lab

### User Actions
1.  **Create Experiment** → Set up A/B cost experiment comparing optimization strategies.
2.  **Manage Experiments** → Start, stop, view results.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Experiments** | `GET /api/v1/lab/experiments` | `LabService.list_experiments`: By organization. | `lab_experiments` |
| **Create Experiment** | `POST /api/v1/lab/experiments` | `LabService.create_experiment`: A/B with control and variant configs. | `lab_experiments` |
| **Start Experiment** | `POST /api/v1/lab/experiments/{id}/start` | `LabService.start_experiment`: Activates. | `lab_experiments` |
| **Stop Experiment** | `POST /api/v1/lab/experiments/{id}/stop` | `LabService.stop_experiment`: Deactivates. | `lab_experiments` |
| **Get Results** | `GET /api/v1/lab/experiments/{id}/results` | `LabService.get_results`: Outcome data. | `lab_experiments` |

---

## Database Schema Summary (Key Tables)

| Table | Description |
| :--- | :--- |
| `organizations` | Root tenant records. Includes `governance_config`, `external_id`, `automation_config`, `required_tags`. |
| `users` | Platform users, linked to Org and Team. Includes role, status, `must_reset_password`, `preferences`. |
| `accounts` | Connected AWS accounts (Role ARNs, External IDs, status, `is_default`). |
| `clusters` | EKS clusters discovered in Accounts. Cost, savings, node counts, agent status, `api_key`, `last_heartbeat`. |
| `instances` | EC2 nodes within Clusters. Type, lifecycle, utilization, architecture. |
| `daily_costs` | Aggregated daily spend data by service (from Cost Explorer sync). |
| `cluster_policies` | Spot optimization rule configurations. |
| `hibernation_schedules` | Weekly start/stop schedules with strategy and timezone. |
| `audit_logs` | Immutable record of all system actions (actor, event, resource, IP, diff). |
| `teams` | Organizational teams with optional governance config. |
| `roles` | Role definitions (system and custom). |
| `permissions` | Permission slugs grouped by module. |
| `role_permissions` | Many-to-many linking roles to permissions. |
| `approvals` | JIT access requests with status lifecycle (PENDING → APPROVED_ACTIVE → EXPIRED/REVOKED). |
| `tag_policies` | Tag key enforcement rules (Required/Advisory/Recommended). |
| `tag_templates` | Reusable tag sets with dynamic variable support. |
| `auto_tag_rules` | Auto-tagging rule definitions with conditions and actions. |
| `node_templates` | Instance family/architecture templates for deployments. |
| `hygiene_policies` | Automated resource cleanup rules (conditions, actions, priority). |
| `lab_experiments` | A/B cost optimization experiments. |
| `ri_utilization` | Reserved Instance utilization tracking and waste detection. |
| `system_config` | Platform-level key-value configuration (SAFE_MODE, AWS credentials, etc.). |

---

## Endpoint Count Summary

| Section | Endpoints |
| :--- | :--- |
| 1. Authentication & Onboarding | 10 |
| 2. Cluster Discovery & Management | 13 |
| 3. Agent Communication & Installers | 5 |
| 4. Dashboard & Metrics | 14 |
| 5. Billing & Cost Explorer | 8 |
| 6. Cost Optimization (Hibernation & Rightsizing) | 8 |
| 7. Governance & Teams | 28 |
| 8. Resource Hygiene (Cleanup) | 11 |
| 9. Tagging & Templates | 17 |
| 10. Node Templates | 6 |
| 11. AtharvaAi Engine | 12 |
| 12. Automation & Governance | 3 |
| 13. Audit & Logging | 2 |
| 14. Settings & Profile | 15 |
| 15. Cost Optimization Modules | 14 |
| 16. Admin Panel | 15 |
| 17. Experiment Lab | 5 |
| **Total** | **~186** |
