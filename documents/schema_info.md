# Database Schema Reference — Spot Optimizer Platform

> **Total Tables**: 42 (38 primary tables + 2 association tables + 2 duplicate/legacy)
> **Database**: PostgreSQL | **ORM**: SQLAlchemy
> **Last Updated**: 2026-02-17

---

## Table of Contents

1. [Core Identity & Multi-tenancy](#1-core-identity--multi-tenancy)
2. [RBAC & Permissions](#2-rbac--permissions)
3. [AWS Infrastructure](#3-aws-infrastructure)
4. [Metrics & Monitoring](#4-metrics--monitoring)
5. [Cost & Billing](#5-cost--billing)
6. [Cost Optimization Analysis](#6-cost-optimization-analysis)
7. [AtharvaAI ML & Pricing](#7-atharvaai-ml--pricing)
8. [System B: Termination & Rebalancing](#8-system-b-termination--rebalancing)
9. [Approvals & Audit](#9-approvals--audit)
10. [Tag Management](#10-tag-management)
11. [ML Lab & Experiments](#11-ml-lab--experiments)
12. [Scheduling & Automation](#12-scheduling--automation)
13. [System Configuration](#13-system-configuration)
14. [Association Tables](#14-association-tables)
15. [Unused / Legacy Schemas](#15-unused--legacy-schemas)

---

## 1. Core Identity & Multi-tenancy

### `organizations`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID primary key |
| owner_user_id | VARCHAR(36) | Yes | User who created the org |
| name | VARCHAR(255) | No | Organization display name |
| slug | VARCHAR(255) UNIQUE | No | URL-friendly identifier |
| external_id | VARCHAR(36) UNIQUE | Yes | AWS trust policy external ID |
| billing_email | VARCHAR(255) | Yes | Billing contact email |
| stripe_customer_id | VARCHAR(255) | Yes | Stripe integration ID |
| status | VARCHAR(50) | No | active / suspended |
| is_governance_enabled | BOOLEAN | No | Automated governance toggle |
| is_strict_approval_mode | BOOLEAN | No | Require approval even for admins |
| governance_config | JSON | No | Action-specific governance rules |
| required_tags | JSON | No | Required tag keys for compliance |
| require_automation_approval | BOOLEAN | No | Require approval for automated cleanup |
| automation_config | JSON | No | Hibernation automation defaults |
| created_at | DATETIME | No | Record creation time |
| updated_at | DATETIME | No | Last modification time |

**Used By**:
- **Backend**: `organization_service.py`, `auth_service.py`, `permission_service.py`, `team_service.py`
- **API Routes**: `organization_routes.py`, `auth_routes.py`
- **Frontend**: `OrgSettings.jsx`, `AdminDashboard.jsx`, `Dashboard.jsx`
- **Purpose**: Multi-tenancy root — all users, accounts, clusters, teams belong to an org. Governance toggles control automation behavior.

---

### `users`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID primary key |
| email | VARCHAR(255) UNIQUE | No | Login email |
| password_hash | VARCHAR(255) | No | bcrypt hash |
| role | ENUM(UserRole) | No | SUPER_ADMIN, ORG_ADMIN, TEAM_LEAD, MEMBER, CLIENT |
| is_active | VARCHAR(1) | No | Y/N active flag |
| organization_id | VARCHAR(36) FK | Yes | FK → organizations.id |
| access_level | ENUM(AccessLevel) | No | READ_ONLY, EXECUTION, FULL |
| team_id | VARCHAR(36) FK | Yes | FK → teams.id |
| full_name | VARCHAR(100) | Yes | Display name |
| role_id | VARCHAR(36) FK | Yes | FK → roles.id (fine-grained RBAC) |
| must_reset_password | BOOLEAN | No | Force password reset on first login |
| status | VARCHAR(20) | No | ACTIVE / PENDING_INVITE |
| preferences | JSON | Yes | Dashboard layout, theme prefs |
| team_member_permissions | JSON | Yes | Team-specific permission overrides |
| onboarding_completed | BOOLEAN | No | Onboarding flow completion flag |
| created_at | DATETIME | No | Record creation time |
| updated_at | DATETIME | No | Last modification time |

**Used By**:
- **Backend**: `auth_service.py` (JWT authentication, password verification), `permission_service.py` (RBAC checks), `team_service.py`
- **API Routes**: `auth_routes.py` (login/signup), `user_routes.py` (CRUD), `admin_routes.py`
- **Frontend**: `Login.jsx`, `Signup.jsx`, `ProfileSettings.jsx`, `FirstLoginReset.jsx`, `UserManagement.jsx`
- **Redis**: JWT token blacklist on logout
- **Purpose**: Authentication & authorization. Every API request validates user via JWT → user lookup.

---

### `accounts`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID primary key |
| organization_id | VARCHAR(36) FK | No | FK → organizations.id |
| user_id | VARCHAR(36) FK | Yes | Creator of the connection |
| aws_account_id | VARCHAR(12) | No | 12-digit AWS account ID |
| role_arn | VARCHAR(255) | Yes | IAM role ARN for cross-account access |
| external_id | VARCHAR(64) | Yes | STS external ID |
| region | VARCHAR(20) | Yes | Default region (us-east-1) |
| status | ENUM(AccountStatus) | No | pending, scanning, active, error, disconnected |
| last_sync_at | DATETIME | Yes | Last discovery sync time |
| sync_status | ENUM(SyncStatus) | Yes | healthy, warning, failed |
| sync_error | TEXT | Yes | Last sync error message |
| is_default | BOOLEAN | No | Default account flag |
| created_at | DATETIME | No | Record creation time |
| updated_at | DATETIME | No | Last modification time |

**Used By**:
- **Backend**: `cluster_service.py` (STS assume-role), `cost_explorer_service.py`, `discovery_worker.py`, `agent_injector.py`
- **API Routes**: `account_routes.py`, `onboarding_routes.py`
- **Frontend**: `ConnectAWS.jsx`, `AccountList.jsx`, `Dashboard.jsx` (AWS connection status)
- **Purpose**: AWS account connection. Used to assume IAM role for all AWS API calls (EKS, EC2, Cost Explorer, S3, RDS).

---

### `teams`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID primary key |
| name | VARCHAR(100) | No | Team display name |
| organization_id | VARCHAR(36) FK | No | FK → organizations.id |
| governance_config | JSON | No | Team-specific approval requirements |
| created_at | DATETIME | No | Record creation time |

**Used By**:
- **Backend**: `team_service.py`, `permission_service.py`
- **API Routes**: `team_routes.py`
- **Frontend**: `TeamList.jsx`, `TeamDetail.jsx`
- **Purpose**: Team grouping within orgs. Team leads can set per-team governance config.

---

### `onboarding_states`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | UUID PK | No | UUID primary key |
| user_id | VARCHAR(36) FK UNIQUE | No | FK → users.id (one-to-one) |
| current_step | ENUM(OnboardingStep) | No | WELCOME, CONNECT_AWS, VERIFYING, COMPLETED |
| external_id | VARCHAR UNIQUE | No | Secure random ID for AWS trust |
| aws_role_arn | VARCHAR | Yes | Role ARN entered during onboarding |
| aws_account_id | VARCHAR | Yes | AWS account ID entered |
| connection_mode | ENUM(ConnectionMode) | No | READ_ONLY or FULL_ACCESS |
| created_at | DATETIME | No | Record creation time |
| updated_at | DATETIME | No | Last modification time |

**Used By**:
- **Backend**: `onboarding_service.py`
- **API Routes**: `onboarding_routes.py`
- **Frontend**: `ConnectAWS.jsx`, onboarding wizard
- **Purpose**: Tracks user's progress through the AWS connection wizard.

---

### `organization_invitations`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID primary key |
| email | VARCHAR(255) | No | Invitee email |
| token | VARCHAR(255) UNIQUE | No | Invitation token |
| status | ENUM(InvitationStatus) | No | PENDING, ACCEPTED, EXPIRED |
| role | ENUM(UserRole) | No | Role to assign on accept |
| access_level | ENUM(AccessLevel) | No | Access level to assign |
| organization_id | VARCHAR(36) FK | No | FK → organizations.id |
| created_by | VARCHAR(36) FK | Yes | Inviter user ID |
| created_at | DATETIME | No | Invitation creation time |
| expires_at | DATETIME | No | Expiration deadline |
| updated_at | DATETIME | No | Last modification time |

**Used By**:
- **Backend**: `invitation_service.py`, `auth_service.py`
- **API Routes**: `invitation_routes.py`
- **Frontend**: `InviteUserModal.jsx`
- **Purpose**: Org admins invite users with pre-set role/access. Accepted invitations create user accounts.

---

## 2. RBAC & Permissions

### `roles`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID primary key |
| name | VARCHAR(100) | No | Role name (e.g., "Finance Viewer") |
| type | ENUM(RoleType) | No | SYSTEM (immutable) or CUSTOM |
| organization_id | VARCHAR(36) FK | Yes | NULL for system roles, set for custom |
| description | VARCHAR(500) | Yes | Role description |
| created_at | DATETIME | No | Record creation time |
| updated_at | DATETIME | No | Last modification time |

**Used By**:
- **Backend**: `permission_service.py` (role → permission resolution)
- **API Routes**: `permission_routes.py`
- **Frontend**: `RoleManagement.jsx`
- **Purpose**: Fine-grained RBAC. System roles are immutable; orgs can create custom roles.

---

### `permissions`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID primary key |
| slug | VARCHAR(100) UNIQUE | No | Permission identifier (e.g., "hygiene:execute") |
| name | VARCHAR(200) | No | Human-readable name |
| module | VARCHAR(50) | No | Category grouping (e.g., "Resource Hygiene") |
| description | TEXT | Yes | Description |

**Used By**:
- **Backend**: `permission_service.py`, `require_permission()` dependency
- **API Routes**: All protected routes via `Depends(require_permission(...))`
- **Frontend**: `ProtectedButton.jsx` (JIT approval flow)
- **Purpose**: 73+ granular capabilities. Linked to roles via `role_permissions` table.

---

## 3. AWS Infrastructure

### `clusters`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR PK | No | Cluster ID (from AWS) |
| name | VARCHAR | No | Cluster display name |
| account_id | VARCHAR FK | No | FK → accounts.id |
| arn | VARCHAR UNIQUE | No | AWS ARN |
| region | VARCHAR | No | AWS region |
| cluster_type | ENUM(ClusterType) | No | EKS, ECS, GKE, AKS |
| version | VARCHAR | Yes | Kubernetes version |
| endpoint | VARCHAR | Yes | API server endpoint |
| ca_data | TEXT | Yes | Base64 CA certificate |
| status | ENUM(ClusterStatus) | No | PENDING, DISCOVERED, ACTIVE, INACTIVE, ERROR, TERMINATED, DISCONNECTED |
| agent_installed | VARCHAR(1) | No | Y/N agent flag |
| is_agentless | VARCHAR(1) | No | Y/N agentless mode |
| api_key | VARCHAR | Yes | Agent auth key |
| aws_role_arn | VARCHAR | Yes | AWS role for K8s auth |
| aws_external_id | VARCHAR | Yes | AWS external ID |
| last_heartbeat | DATETIME | Yes | Last agent heartbeat |
| monthly_cost | INTEGER | No | Monthly cost (USD) |
| estimated_savings | INTEGER | No | Estimated savings (USD) |
| last_cost_update | DATETIME | Yes | Last cost sync |
| potential_savings_monthly | FLOAT | No | Savings if switch ON_DEMAND→SPOT |
| realized_savings_monthly | FLOAT | No | Savings already from SPOT |
| on_demand_node_count | INTEGER | No | On-demand node count |
| last_assessed | DATETIME | Yes | Last assessment time |
| inventory_summary | JSON | No | {total, on_demand, spot} |
| node_count | INTEGER | No | Total node count |
| spot_count | INTEGER | No | Spot node count |
| cpu_total / mem_total | INTEGER | No | Total CPU/memory |
| cpu_usage_pct / mem_usage_pct | FLOAT | No | Current utilization % |
| tags | JSON | No | AWS resource tags |
| created_at / updated_at | DATETIME | No | Timestamps |

**Used By**:
- **Backend**: `cluster_service.py`, `agent_injector.py`, `discovery_worker.py`, `karpenter_service.py`, `metrics_service.py`
- **API Routes**: `cluster_routes.py`, `metrics_routes.py`, `atharvaai_routes.py`
- **Frontend**: `ClusterList.jsx`, `ClusterDetails.jsx`, `Dashboard.jsx` (KPI: cluster count, spot ratio)
- **Purpose**: Central cluster registry. Used for discovery, agent management, cost tracking, and Karpenter integration.

---

### `instances`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID primary key |
| cluster_id | VARCHAR(36) FK | Yes | FK → clusters.id |
| account_id | VARCHAR(36) FK | Yes | FK → accounts.id |
| instance_id | VARCHAR(20) UNIQUE | No | AWS EC2 instance ID (i-xxxxx) |
| instance_type | VARCHAR(50) | No | e.g., m5.xlarge |
| lifecycle | ENUM(InstanceLifecycle) | No | spot / on-demand |
| az | VARCHAR(50) | No | Availability zone |
| price | FLOAT | Yes | Current hourly price |
| cpu_util / memory_util | FLOAT | Yes | Current utilization % |
| state | VARCHAR(20) | No | running, stopped, terminated |
| status | VARCHAR(20) | Yes | READY, CALIBRATING, UNKNOWN, TERMINATED |
| status_message | VARCHAR(255) | Yes | Health status message |
| architecture | VARCHAR(20) | Yes | amd64, arm64 |
| created_at / updated_at | DATETIME | No | Timestamps |
| last_heartbeat | DATETIME | Yes | Zombie node detection |

**Indexes**: `idx_cluster_lifecycle`, `idx_cluster_instance_type`, `idx_account_state`

**Used By**:
- **Backend**: `metrics_service.py` (KPI calculations), `discovery_worker.py`, `rightsizer.py`
- **API Routes**: `instance_routes.py`, `metrics_routes.py`, `optimization_routes.py`
- **Frontend**: `InstanceList.jsx`, `FleetComposition.jsx`, `SpotSavingsChart.jsx`, `Dashboard.jsx`
- **Purpose**: EC2 instance registry. Powers fleet composition charts, savings calculations, and right-sizing.

---

### `api_keys`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID primary key |
| cluster_id | VARCHAR(36) FK | No | FK → clusters.id |
| key_hash | VARCHAR(64) UNIQUE | No | SHA-256 hash of API key |
| key_prefix | VARCHAR(8) | No | First 8 chars for display |
| description | VARCHAR(255) | Yes | Key description |
| last_used_at | DATETIME | Yes | Last usage timestamp |
| created_at | DATETIME | No | Key creation time |
| expires_at | DATETIME | Yes | Optional expiration |

**Used By**:
- **Backend**: `agent_injector.py` (generates keys), `auth_middleware.py` (validates agent requests)
- **Purpose**: Agent authentication. DaemonSet uses API key to POST metrics and poll actions.

---

### `authorized_resources`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID |
| resource_id | VARCHAR | No | AWS resource ID |
| account_id | VARCHAR(36) FK | No | FK → accounts.id |
| region | VARCHAR | No | AWS region |
| resource_type | VARCHAR | No | INSTANCE, VOLUME, etc. |
| notes | TEXT | Yes | User notes |
| created_at | DATETIME | No | Record creation time |
| created_by_id | VARCHAR(36) FK | Yes | FK → users.id |

**Used By**:
- **Backend**: `hygiene_service.py` (whitelist check)
- **Purpose**: Whitelisted resources excluded from hygiene cleanup scans.

---

## 4. Metrics & Monitoring

### `cluster_metrics`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID |
| cluster_id | VARCHAR(36) FK | No | FK → clusters.id |
| metric_type | VARCHAR(50) | No | pod, node, event, aggregated |
| metric_data | JSONB | No | Flexible metric payload |
| timestamp | DATETIME | No | Collection timestamp |

**Indexes**: `idx_cluster_metric_cluster_time`, `idx_cluster_metric_type_time`, `idx_cluster_metric_cluster_type`

**Used By**:
- **Backend**: `metrics_service.py`, `metrics_routes.py` (cluster utilization endpoint)
- **Agent**: Sends batched metrics via POST
- **Frontend**: `ClusterUtilizationSparkline.jsx`, `Dashboard.jsx`
- **Purpose**: Time-series cluster-level metrics from agents. Powers utilization charts and health monitoring.

---

### `pod_metrics`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID |
| cluster_id | VARCHAR(36) FK | No | FK → clusters.id |
| namespace | VARCHAR(253) | No | K8s namespace |
| pod_name | VARCHAR(253) | No | Pod name |
| node_name | VARCHAR(253) | No | Node name |
| controller_kind | VARCHAR(50) | Yes | Deployment, StatefulSet, etc. |
| controller_name | VARCHAR(253) | Yes | Controller name |
| cpu_usage_millicores | INTEGER | No | Current CPU usage |
| cpu_request_millicores | INTEGER | Yes | CPU request |
| cpu_limit_millicores | INTEGER | Yes | CPU limit |
| memory_usage_bytes | BIGINT | No | Current memory usage |
| memory_request_bytes | BIGINT | Yes | Memory request |
| memory_limit_bytes | BIGINT | Yes | Memory limit |
| cpu_utilization_pct | FLOAT | Yes | usage/request × 100 |
| memory_utilization_pct | FLOAT | Yes | usage/request × 100 |
| container_count | INTEGER | No | Container count (default 1) |
| timestamp | DATETIME | No | Collection timestamp |
| metadata | JSONB | Yes | Labels, annotations |

**Indexes**: `idx_pod_metric_cluster_time`, `idx_pod_metric_controller`, `idx_pod_metric_node_time`, `idx_pod_metric_pod_time`

**Used By**:
- **Backend**: `rightsizing_service.py` (P95/P99 analysis), `pod_metrics_cleanup.py` (7-day retention)
- **API Routes**: `pod_metrics_routes.py` (batch, query, recommendations, cleanup)
- **Agent**: `pod_metrics_collector.py` → POST /api/v1/pod-metrics/batch every 5 min
- **Frontend**: `RightSizing.jsx`, `ImpactSummary.jsx`, `InstanceUsageDetailPanel.jsx`
- **Purpose**: High-frequency pod resource usage. Feeds the Right-Sizing engine for cost recommendations.
- **Retention**: 7 days (cleaned daily by Celery worker)

---

## 5. Cost & Billing

### `daily_costs`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR PK | No | Format: `ACC-ID_YYYY-MM-DD_SERVICE` |
| account_id | VARCHAR FK | No | FK → accounts.id |
| date | DATE | No | Cost record date |
| service_name | VARCHAR | No | AWS service name |
| cost_amount | FLOAT | No | Cost in USD |
| currency | VARCHAR | No | Always "USD" |
| cost_type | VARCHAR | No | Usage, Tax, Support, Refund |
| created_at / updated_at | DATETIME | No | Timestamps |

**Indexes**: `idx_account_date`, `idx_date_service`, `idx_account_date_service`

**Used By**:
- **Backend**: `cost_explorer_service.py` (fetches from AWS), `metrics_service.py` (KPI calculations)
- **Worker**: `cost_explorer_worker.py` (every 6 hours)
- **Frontend**: `CostTrends.jsx`, `CostBreakdown.jsx`, `Dashboard.jsx` (monthly spend KPI)
- **Purpose**: Cached AWS Cost Explorer data. Reduces expensive AWS API calls.

---

### `cost_explorer_sync_status`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR PK | No | Format: ACC-ID |
| account_id | VARCHAR FK UNIQUE | No | FK → accounts.id |
| last_sync_at | DATETIME | No | Last successful sync |
| last_synced_date | DATE | No | Last date fetched |
| status | VARCHAR | No | SUCCESS, FAILED, IN_PROGRESS |
| error_message | VARCHAR | Yes | Sync error message |
| records_synced | FLOAT | No | Records in last run |
| created_at / updated_at | DATETIME | No | Timestamps |

**Used By**:
- **Backend**: `cost_explorer_service.py` (prevents duplicate fetches)
- **Purpose**: Tracks AWS Cost Explorer sync health per account.

---

## 6. Cost Optimization Analysis

### `ri_utilization`

| Column | Type | Nullable | Description |
|:-------|:-----|:---------|:------------|
| id | VARCHAR(36) PK | No | UUID |
| organization_id / account_id | VARCHAR(36) FK | No | Org & account links |
| reservation_id | VARCHAR(100) | No | AWS RI ID |
| instance_type | VARCHAR(50) | No | Instance type |
| platform / region / availability_zone | VARCHAR | Various | Placement info |
| offering_class / scope | VARCHAR(20) | No | standard/convertible, regional/zonal |
| instance_count | INTEGER | No | RI quantity |
| upfront_cost / hourly_cost / monthly_cost | FLOAT | No | Financial data |
| utilization_percentage | FLOAT | No | 0-100% |
| utilized_hours / total_hours | FLOAT | No | Usage hours |
| monthly_waste / annual_waste | FLOAT | No | Wasted spend |
| unused_days | INTEGER | No | Days with 0% util |
| estimated_resale_value / resale_percentage | FLOAT | Yes | Marketplace data |
| start_date / end_date / days_remaining | Various | Various | Term info |
| recommendation_type / recommendation_detail | VARCHAR/JSON | Yes | sell, modify, keep, convert |
| last_analyzed_at / created_at / updated_at | DATETIME | No | Timestamps |

**Used By**:
- **Backend**: `ri_waste_service.py`, `cost_optimization_service.py`
- **Frontend**: `CostOptimization.jsx` (RI waste detection tab)
- **Purpose**: RI waste detection — identifies underutilized Reserved Instances.

---

### `s3_bucket_analysis`

27 columns covering bucket name, storage class distribution, access patterns, and recommendations.

**Used By**: `s3_analysis_service.py` → `CostOptimization.jsx` (S3 intelligent tiering tab)

### `rds_instance_analysis`

17 columns covering RDS instance details, Multi-AZ status, utilization metrics, and conversion recommendations.

**Used By**: `rds_analysis_service.py` → `CostOptimization.jsx` (RDS Multi-AZ tab)

### `data_transfer_analysis`

16 columns covering transfer type, bytes/cost, source resource, and optimization recommendations.

**Used By**: `transfer_analysis_service.py` → `CostOptimization.jsx` (Data Transfer tab)

### `savings_plan_utilization`

27 columns covering Savings Plan commitment, utilization, coverage, and renewal recommendations.

**Used By**: `savings_plan_service.py` → `CostOptimization.jsx` (Savings Plans tab)

---

## 7. AtharvaAI ML & Pricing

### `spot_price_history` (AtharvaAI — `spot_price_history.py`)

| Column | Type | Description |
|:-------|:-----|:------------|
| id | INTEGER PK | Auto-increment |
| instance_type | VARCHAR(50) | e.g., m5.xlarge |
| az | VARCHAR(20) | Availability zone |
| region | VARCHAR(20) | AWS region |
| timestamp | DATETIME | Price timestamp |
| spot_price | NUMERIC(10,6) | Spot price USD |
| ondemand_price | NUMERIC(10,6) | On-demand price USD |
| savings | NUMERIC(5,4) | Savings ratio |
| created_at | DATETIME | Record creation |

**Unique**: `(instance_type, az, timestamp)`

**Used By**:
- **Backend**: `ml_feature_service.py` (lag features, rolling stats), `spot_price_collector.py` (Celery worker)
- **Redis Cache**: ML rankings cached 30s TTL
- **Purpose**: 144-point rolling buffer per pool (24h × 10-min intervals). Powers the 45-feature ML pipeline.

### `ondemand_pricing` (pricing.py)

5 columns: `id`, `instance_type`, `region`, `price`, `updated_at`

**Used By**: `pool_ranking_service.py` (cost comparison)

### `spot_advisor_data` (pricing.py)

7 columns: `id`, `instance_type`, `region`, `os_type`, `interruption_frequency`, `interruption_index`, `savings_percentage`

**Used By**: `spot_advisor_enhanced.py` (Step 3 of ML pipeline), `pool_ranking_service.py`

### `node_templates`

| Column | Type | Description |
|:-------|:-----|:------------|
| id | VARCHAR(36) PK | UUID |
| user_id | VARCHAR(36) FK | FK → users.id |
| name | VARCHAR(255) | Template name |
| families | ARRAY(VARCHAR) | e.g., ['c5', 'c6i', 'm5'] |
| architecture | VARCHAR(20) | x86_64 or arm64 |
| strategy | ENUM | cheapest, balanced, performance |
| disk_type | ENUM | gp3, gp2, io1, io2 |
| disk_size | INTEGER | Size in GB |
| is_default | VARCHAR(1) | Y/N |
| created_at / updated_at | DATETIME | Timestamps |

**Used By**:
- **Backend**: `pool_ranking_service.py` (Step 1: node template filtering)
- **API Routes**: `template_routes.py`
- **Frontend**: `NodeTemplates.jsx`
- **Purpose**: User-defined instance family/architecture preferences for ML pool selection.

---

## 8. System B: Termination & Rebalancing

### `termination_events`

| Column | Type | Description |
|:-------|:-----|:------------|
| id | INTEGER PK | Auto-increment |
| instance_type | VARCHAR(50) | Instance type |
| az | VARCHAR(20) | Availability zone |
| region | VARCHAR(20) | AWS region |
| cluster_id | VARCHAR(100) | Associated cluster |
| instance_id | VARCHAR(50) | AWS instance ID |
| node_name | VARCHAR(100) | K8s node name |
| detected_at | DATETIME | Detection timestamp |
| source | VARCHAR(20) | daemonset, eventbridge, manual |
| action_taken | VARCHAR(50) | flagged, rebalanced, none |
| metadata | JSONB | Additional context |
| created_at | DATETIME | Record creation |

**Used By**:
- **Backend**: `termination_monitor.py` (Celery worker, every 30s), `atharvaai_routes.py`
- **Redis**: Blacklist set `risky_pools` with 12h TTL
- **Frontend**: `InterruptionHeatmap.jsx`, `OptimizationStatusHeader.jsx`
- **Purpose**: Logs spot termination notices. Feeds Redis blacklist (System B penalty in ML scoring).

### `rebalancing_actions`

| Column | Type | Description |
|:-------|:-----|:------------|
| id | INTEGER PK | Auto-increment |
| cluster_id | VARCHAR(100) | Cluster ID |
| trigger | VARCHAR(20) | emergency / graceful |
| source_pool | VARCHAR(100) | Origin pool (instance_type:az) |
| target_pool | VARCHAR(100) | Destination pool |
| status | VARCHAR(20) | in_progress, completed, failed |
| nodes_affected | INTEGER | Nodes moved |
| pods_migrated | INTEGER | Pods evicted/migrated |
| started_at / completed_at | DATETIME | Action timeline |
| duration_seconds | INTEGER | Total duration |
| error_message | TEXT | Error details if failed |
| metadata | JSONB | Additional context |
| created_at | DATETIME | Record creation |

**Used By**:
- **Backend**: `auto_rebalancer.py` (Celery worker, every 15s), `atharvaai_routes.py`
- **Frontend**: `RebalancingTimeline.jsx`, `AutoRebalanceAuditCard.jsx`, `OptimizationStatusHeader.jsx`
- **Purpose**: Tracks cordon → drain → migrate actions triggered by termination notices.

---

## 9. Approvals & Audit

### `approvals`

20 columns covering JIT feature access: user_id, organization_id, approver_id, feature_id, jit_scope, jit_metadata, duration_hours, status (PENDING → APPROVED_ACTIVE → EXPIRED), timestamps.

**Used By**:
- **Backend**: `approval_service.py`, `permission_service.py` (active window check)
- **API Routes**: `approval_routes.py`
- **Frontend**: `ApprovalQueue.jsx`, `ApprovalHistory.jsx`, `PendingApprovalsCard.jsx`, `ProtectedButton.jsx`
- **Purpose**: JIT (Just-In-Time) approval system. Time-bound feature access (1-8 hours).

### `audit_logs`

12 columns: immutable compliance trail with actor, event, resource, outcome, IP, before/after JSONB diffs.

**Used By**:
- **Backend**: All services log actions → `audit_service.py`
- **API Routes**: `admin_routes.py` (audit viewer)
- **Frontend**: `AuditLogViewer.jsx`
- **Purpose**: Immutable audit trail. No UPDATE allowed — append-only.

---

## 10. Tag Management

### `tag_policies` — Tag governance rules (14 cols)
**Used By**: `tag_policy_service.py`, `tag_policy_routes.py` → `TagPolicies.jsx`

### `tag_templates` — Reusable tag sets (11 cols)
**Used By**: `tag_template_service.py` → `TagTemplates.jsx`

### `auto_tag_rules` — Automated tagging rules (22 cols)
**Used By**: `auto_tag_service.py` → `AutoTagRules.jsx`

---

## 11. ML Lab & Experiments

### `ml_models` — ML model registry (8 cols: version, file_path, status, performance_metrics JSONB)
**Used By**: `experiment_service.py`, `lab_experiment_routes.py` → `ExperimentList.jsx`

### `lab_experiments` — A/B test experiments (7 cols: model_id, cluster_id, test_type, telemetry JSONB)
**Used By**: `experiment_service.py` → `ExperimentDetail.jsx`

---

## 12. Scheduling & Automation

### `agent_actions` — K8s action queue (11 cols: action_type, payload JSONB, status, expires_at)
**Used By**: `agent_action_service.py`, agent polls `GET /clusters/{id}/actions/pending`

### `cluster_policies` — Optimization policy config (4 cols: cluster_id, config JSONB)
**Used By**: `cluster_policy_service.py` → `ClusterSettings.jsx`

### `optimization_jobs` — Optimization run tracking (7 cols: cluster_id, status, results JSONB)
**Used By**: `optimization_service.py` → `RightSizing.jsx`

### `hibernation_schedules` — Cluster sleep/wake schedules (16 cols: schedule_matrix, strategy, saved_state)
**Used By**: `hibernation_service.py` → `HibernationSchedule.jsx`

### `cleanup_policies` — Hygiene automation rules (10 cols: resource_type, conditions, action)
**Used By**: `hygiene_service.py` → `HygieneDashboard.jsx`

---

## 13. System Configuration

### `platform_settings` — Global platform config (7 cols)
**Used By**: `admin_service.py` → `AdminDashboard.jsx`

### `system_configs` — Key-value config store (5 cols: key, value, description)
**Used By**: Safe Mode toggle, agent version tracking

---

## 14. Association Tables

### `user_permissions`
| Column | Type | Description |
|:-------|:-----|:------------|
| user_id | VARCHAR(36) FK PK | FK → users.id |
| permission_id | VARCHAR(36) FK PK | FK → permissions.id |

**Purpose**: Direct/custom permission overrides for individual users (bypasses role).

### `role_permissions`
| Column | Type | Description |
|:-------|:-----|:------------|
| role_id | VARCHAR(36) FK PK | FK → roles.id |
| permission_id | VARCHAR(36) FK PK | FK → permissions.id |

**Purpose**: Maps roles to their granted permissions (many-to-many).

---

## 15. Unused / Legacy Schemas

| Table | Model File | Status | Reason |
|:------|:-----------|:-------|:-------|
| `approval_requests` | `legacy_approval.py` | ⚠️ **LEGACY** | Replaced by `approvals` table. Old maker-checker workflow with simpler status (PENDING/APPROVED/REJECTED/FAILED). Still in codebase but not actively used by any route. |
| `spot_price_history` (pricing.py) | `pricing.py` | ⚠️ **DUPLICATE** | Duplicate definition in `pricing.py` alongside `ondemand_pricing` and `spot_advisor_data`. The active version is in `spot_price_history.py` with the `extend_existing` flag. |
| `ondemand_pricing` | `pricing.py` | ⚠️ **LOW USAGE** | Referenced by pool ranking service but no dedicated Celery worker populates it. May be seeded manually or via one-time scripts. |
| `spot_advisor_data` | `pricing.py` | ⚠️ **LOW USAGE** | Scraper fetches data into memory/Redis cache directly from S3 JSON. DB table exists but primary usage is the in-memory cache from `spot_advisor_enhanced.py`. |

---

## Redis Cache Usage Summary

| Key Pattern | Source Table | TTL | Purpose |
|:------------|:-------------|:----|:--------|
| `ml_rankings:<cluster_id>` | `spot_price_history` + ML models | 30s | Cached pool rankings from AtharvaAI pipeline |
| `risky_pools` (SET) | `termination_events` | 12h | Blacklisted pools (System B penalty) |
| `risky_pool_meta:<pool_key>` | `termination_events` | 12h | Termination metadata per pool |
| `jwt_blacklist:<token>` | `users` | Token expiry | Blacklisted JWT tokens on logout |
| `spot_advisor_cache` | `spot_advisor_data` | 1h | 29,794 pool interruption ratings |
| `session:<user_id>` | `users` | 24h | Active session cache |

---

**End of Schema Reference**
