# User Flow & Technical Architecture

This document outlines the complete user journey through the platform, mapping each step to the underlying backend logic, API endpoints, and database tables involved.

---

## 1. Authentication & Onboarding

### User Actions
1.  **Sign Up**: User registers a new organization (Company Name, Email, Password).
2.  **Login**: User logs in with email/password.
3.  **Onboarding**: New users land on a "Connect AWS" wizard.
4.  **Connect AWS**: User generates a CloudFormation stack URL, deploys it in their AWS account, and the system validates the connection.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Sign Up** | `POST /api/v1/auth/signup` | `AuthService.signup`: Creates `Organization` + admin `User`. Hashes password. | `organizations`, `users` |
| **Login** | `POST /api/v1/auth/login` | `AuthService.login`: Validates credentials, issues JWT. Updates `last_login`. | `users` |
| **Generate Stack** | `POST /api/v1/onboarding/generate-stack-url` | `OnboardingService.generate_stack_url`: Creates signed S3 URL for CloudFormation template with unique `ExternalID`. | `organizations` (reads `external_id`) |
| **Validate Account** | `POST /api/v1/accounts/validate/{id}` | `AccountService.validate_account`: Attempts STS `AssumeRole` using the Role ARN provided by CloudFormation output. Sets status to `ACTIVE`. | `accounts` |

---

## 2. Cluster Discovery & Management

### User Actions
1.  **Dashboard Load**: System auto-discovers EKS clusters in the connected AWS account.
2.  **View Clusters**: User sees a list of clusters with cost, node count, and health status.
3.  **Install Agent**: User clicks "Inject Agent" to install the optimization agent (Helm chart) on a cluster.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Discovery** | `POST /api/v1/clusters/discover` | `ClusterService.discover_clusters`: Uses `boto3` to list EKS clusters. Creates/updates `Cluster` records. Syncs node groups. | `clusters`, `accounts` |
| **List Clusters** | `GET /api/v1/clusters` | `ClusterService.list_clusters`: Returns clusters filtered by user's organization. | `clusters` |
| **Cluster Details** | `GET /api/v1/clusters/{id}` | `ClusterService.get_cluster`: Returns detailed cluster stats (cost, savings, node breakdown). | `clusters`, `instances` |
| **Agent Install** | `POST /api/v1/clusters/{id}/auto-install` | `ClusterService.generate_install_command`: Generates Helm command with unique cluster token. | `clusters` (updates `agent_installed`) |

---

## 3. Dashboard & Metrics

### User Actions
1.  **View Dashboard**: User sees high-level KPIs: Total Cost, Savings, Spot Ratio.
2.  **Cost Trends**: User views a daily cost chart and savings analysis.
3.  **Fleet Composition**: User sees the breakdown of Spot vs. On-Demand instances.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Dashboard KPIs** | `GET /api/v1/metrics/dashboard` | `MetricsService.get_dashboard_kpis`: Aggregates data from `daily_costs` and `instances` tables. Calculates total spend, savings, potential savings. | `daily_costs`, `instances`, `clusters` |
| **Cost Time Series** | `GET /api/v1/metrics/cost/timeseries` | `MetricsService.get_cost_time_series`: Returns daily cost data points for charts. | `daily_costs` |
| **Instance Metrics** | `GET /api/v1/metrics/instances` | `MetricsService.get_instance_metrics`: Aggregates instance counts by lifecycle (SPOT/ON-DEMAND) and family. | `instances` |

---

## 4. Cost Optimization (Hibernation & Rightsizing)

### User Actions
1.  **Hibernation Schedule**: User creates a weekly schedule (e.g., "Nights & Weekends") to stop clusters during off-hours.
2.  **Rightsizing**: User views recommendations to downsize underutilized instances.
3.  **Apply Policies**: User sets policies for Spot instance usage and node sizing.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Schedules** | `GET /api/v1/hibernation/schedules` | `HibernationService.list_schedules`: Returns hibernation configs linked to clusters. | `hibernation_schedules` |
| **Create Schedule** | `POST /api/v1/hibernation/schedules` | `HibernationService.create_schedule`: Saves 7x24 hour matrix. Agent polls this configuration. | `hibernation_schedules` |
| **Cluster Policy** | `GET /api/v1/policies/cluster/{id}` | `PolicyService.get_policy`: Returns Spot configuration (e.g., "70% Spot"). | `cluster_policies` |
| **Rightsizing Analysis** | `GET /api/v1/optimization/rightsizing/{id}` | `OptimizationService.analyze_cluster`: Compares CPU/Mem usage history against instance specs to recommend smaller types. | `instances`, `metrics` (internal) |

---

## 5. Governance & Teams

### User Actions
1.  **Team Management**: Admin creates teams (e.g., "DevOps", "Frontend") and invites members.
2.  **RBAC**: Admin assigns roles (Admin, Editor, Viewer) to users.
3.  **Approvals**: Users request access to restricted features (JIT Access); Admins approve/reject.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **List Teams** | `GET /api/v1/teams` | `TeamService.list_teams`: Returns teams for the organization. | `teams`, `users` |
| **Invite Member** | `POST /api/v1/organization/invite` | `OrganizationService.invite_user`: Creates `User` with `PENDING_INVITE` status. Sends email (mocked). | `users`, `teams`, `roles` |
| **Manage Roles** | `GET /api/v1/roles` | `RoleService.list_roles`: Returns available roles and permission sets. | `roles`, `permissions`, `role_permissions` |
| **JIT Access** | `POST /api/v1/approvals/jit-request` | `ApprovalService.create_request`: Creates a temporary access request. | `approvals` |

---

## 6. Resource Hygiene (Cleanup)

### User Actions
1.  **Scan Resources**: User triggers a scan to find unused EBS volumes, old snapshots, unattached EIPs.
2.  **Bulk Tagging**: User applies cost allocation tags to multiple resources at once.
3.  **Delete Waste**: User selects "orphaned" resources and deletes them to save costs.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Hygiene Scan** | `GET /api/v1/hygiene/scan` | `HygieneService.scan_resources`: Queries AWS APIs (EC2/EBS/etc.) in real-time. Identifies waste based on rules (e.g., unattached volume > 7 days). | `accounts` (for creds), *No DB storage for scan results* |
| **Bulk Tag** | `POST /api/v1/tags/resources` | `TagManagementService.apply_tags`: Calls AWS `create_tags` API for selected resource IDs. | `tag_policies` (validation) |
| **Execute Cleanup** | `POST /api/v1/hygiene/action` | `HygieneService.execute_action`: Calls AWS delete APIs. logs action to Audit Log. | `audit_logs` |

---

## 7. Audit & Logging

### User Actions
1.  **View Logs**: Admin views a history of all sensitive actions (login, delete cluster, change policy).
2.  **Filter Logs**: Admin filters by actor, date, or event type.

### Technical Implementation

| Feature | API Endpoint | Backend Logic | DB Tables |
| :--- | :--- | :--- | :--- |
| **Get Audit Logs** | `GET /api/v1/audit/logs` | `AuditService.get_logs`: Returns paginated logs. Captures `actor_id`, `event`, `resource`, `timestamp`. | `audit_logs` |

---

## Database Schema Summary (Key Tables)

-   **`organizations`**: Root tenant records.
-   **`users`**: Platform users, linked to Org and Team.
-   **`accounts`**: Connected AWS accounts (Role ARNs).
-   **`clusters`**: EKS clusters discovered in Accounts.
-   **`instances`**: EC2 nodes within Clusters (synced for cost calc).
-   **`daily_costs`**: Aggregated daily spend data.
-   **`cluster_policies`**: Configuration for optimization rules.
-   **`hibernation_schedules`**: Weekly start/stop schedules.
-   **`audit_logs`**: Immutable record of all system actions.
