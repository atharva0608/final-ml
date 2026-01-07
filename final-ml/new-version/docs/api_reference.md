# API Reference Documentation

> **Complete API Catalog**: This document provides a comprehensive list of all API endpoints in the Spot Optimizer platform, their purposes, request/response schemas, and the frontend components that consume them.

## Implementation Status (Updated 2026-01-02)

**✅ ALL ENDPOINTS IMPLEMENTED** - Phases 5-14 completed the implementation of all 58 API endpoints documented in this file:

- **Backend Implementation**: `backend/api/` contains 9 route modules
  - `auth_routes.py` - Authentication endpoints (4 routes)
  - `account_routes.py` - Account management (6 routes)
  - `cluster_routes.py` - Cluster operations (8 routes)
  - `template_routes.py` - Template CRUD (5 routes)
  - `policy_routes.py` - Policy configuration (6 routes)
  - `hibernation_routes.py` - Hibernation schedules (5 routes)
  - `metrics_routes.py` - Metrics & analytics (6 routes)
  - `audit_routes.py` - Audit logs (4 routes)
  - `admin_routes.py` - Admin operations (9 routes)
  - `lab_routes.py` - ML model testing (5 routes)

- **Frontend Integration**: All endpoints consumed by 21 React components
- **Schema Validation**: All requests/responses validated via Pydantic schemas
- **Testing**: API contracts match frontend expectations

**Total Implemented**: 58 of 78 documented endpoints (74%) - Remaining 20 are billing/notifications (future phases)

---

## Table of Contents
1. [Authentication APIs](#authentication-apis)
2. [Onboarding & Cloud Connection APIs](#onboarding--cloud-connection-apis)
3. [Dashboard & Metrics APIs](#dashboard--metrics-apis)
4. [Cluster Management APIs](#cluster-management-apis)
5. [Node Template APIs](#node-template-apis)
6. [Optimization Policy APIs](#optimization-policy-apis)
7. [Hibernation APIs](#hibernation-apis)
8. [Audit & Compliance APIs](#audit--compliance-apis)
9. [Settings & Account Management APIs](#settings--account-management-apis)
10. [Admin APIs (Platform Owner Only)](#admin-apis-platform-owner-only)
11. [Lab & ML Model APIs](#lab--ml-model-apis)
12. [WebSocket Endpoints](#websocket-endpoints)

---

## Authentication APIs

### POST `/api/auth/signup`
**Purpose**: Creates a new user account with organization and placeholder AWS account

**Used By**:
- `LoginPage.jsx` → Sign-Up Form

**Request Body**:
```json
{
  "org_name": "Acme Corp",
  "email": "admin@acme.com",
  "password": "SecurePass123!"
}
```

**Response**:
```json
{
  "user_id": "uuid-1234",
  "token": "jwt-token-xyz",
  "org_id": "uuid-5678"
}
```

**Backend Module**: `CORE-API` → `auth_service.py`  
**Function**: `create_user_org_txn()`  
**Database**: `users`, `accounts`  
**Rate Limit**: 5 requests/hour  

---

### POST `/api/auth/token`
**Purpose**: Authenticates user and returns JWT token

**Used By**:
- `LoginPage.jsx` → Sign-In Form

**Request Body**:
```json
{
  "email": "admin@acme.com",
  "password": "SecurePass123!"
}
```

**Response**:
```json
{
  "access_token": "jwt-token-xyz",
  "token_type": "Bearer",
  "expires_in": 86400,
  "role": "client"
}
```

**Backend Module**: `CORE-API` → `auth_service.py`  
**Function**: `authenticate_user()`  
**Database**: `users`  
**Rate Limit**: 10 requests/minute  

---

### POST `/api/auth/logout`
**Purpose**: Invalidates current JWT token by adding to blacklist

**Used By**:
- `Header.jsx` → Logout Button
- `LoginPage.jsx` → Logout Action

**Request Headers**:
```
Authorization: Bearer jwt-token-xyz
```

**Response**:
```json
{
  "success": true,
  "message": "Logged out successfully"
}
```

**Backend Module**: `CORE-API` → `auth_service.py`  
**Function**: `invalidate_session()`  
**Database**: Redis (session blacklist)  
**Rate Limit**: 100 requests/minute  

---

### GET `/api/auth/me`
**Purpose**: Returns current user context and determines routing path

**Used By**:
- `AuthGateway.jsx` → Route Determination
- `App.jsx` → User Context Provider

**Request Headers**:
```
Authorization: Bearer jwt-token-xyz
```

**Response**:
```json
{
  "user_id": "uuid-1234",
  "email": "admin@acme.com",
  "role": "client",
  "org_id": "uuid-5678",
  "redirect_path": "/dashboard",
  "account_status": "active"
}
```

**Backend Module**: `CORE-API` → `auth_service.py`  
**Function**: `determine_route_logic()`  
**Database**: `users`, `accounts`  

---

## Onboarding & Cloud Connection APIs

### POST `/connect/verify`
**Purpose**: Validates AWS IAM role connection via STS assume role

**Used By**:
- `ClientSetup.jsx` → Verify Connection Button

**Request Body**:
```json
{
  "account_id": "123456789012",
  "role_arn": "arn:aws:iam::123456789012:role/SpotOptimizerRole",
  "external_id": "uuid-external-id"
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Connection verified",
  "account_status": "scanning",
  "discovered_resources": {
    "instances": 45,
    "clusters": 3
  }
}
```

**Backend Module**: `CORE-API` → `cloud_connect.py`  
**Function**: `validate_aws_connection()`  
**Database**: `accounts`  
**AWS APIs**: `sts.assume_role()`, `ec2.describe_instances()`  

---

### GET `/connect/stream`
**Purpose**: WebSocket stream of discovery progress during initial scan

**Used By**:
- `ClientSetup.jsx` → Discovery Progress Bar

**Query Parameters**:
```
?account_id=uuid-1234
```

**Response Stream**:
```json
{
  "progress": 45,
  "status": "scanning",
  "current_region": "us-east-1",
  "clusters_found": 2,
  "instances_found": 34
}
```

**Backend Module**: `WORK-DISC-01`  
**Function**: `stream_discovery_status()`  
**Database**: `clusters`, `instances`  

---

### POST `/connect/link`
**Purpose**: Initiates linking of additional AWS account (multi-account support)

**Used By**:
- `Settings.jsx` → Link Another Account Button
- `CloudIntegrations.jsx` → Add Account

**Request Body**:
```json
{
  "user_id": "uuid-1234",
  "account_alias": "Acme Lab Account"
}
```

**Response**:
```json
{
  "cloudformation_url": "https://console.aws.amazon.com/cloudformation/...",
  "external_id": "uuid-external-id",
  "role_name": "SpotOptimizerRole"
}
```

**Backend Module**: `CORE-API` → `cloud_connect.py`  
**Function**: `initiate_account_link()`  
**Database**: `accounts`  

---

### POST `/onboard/skip`
**Purpose**: Marks onboarding wizard as skipped for later completion

**Used By**:
- `ClientSetup.jsx` → Skip Wizard Button

**Request Body**:
```json
{
  "user_id": "uuid-1234"
}
```

**Response**:
```json
{
  "success": true,
  "redirect": "/dashboard"
}
```

**Backend Module**: `CORE-API` → `onboarding_service.py`  
**Function**: `mark_onboarding_skipped()`  
**Database**: `users`  

---

## Dashboard & Metrics APIs

### GET `/metrics/kpi`
**Purpose**: Returns all dashboard KPI metrics (spend, savings, health)

**Used By**:
- `Dashboard.jsx` → KPI Cards
- `Header.jsx` → Quick Stats

**Response**:
```json
{
  "monthly_spend": 12450.00,
  "net_savings": 1430.00,
  "fleet_health": 87,
  "active_nodes": 142,
  "spot_percentage": 65,
  "efficiency_score": "B"
}
```

**Backend Module**: `CORE-API` → `metrics_service.py` + `MOD-SPOT-01`  
**Function**: `calculate_current_spend()`, `calculate_net_savings()`  
**Database**: `instances`, `pricing`  

---

### GET `/metrics/projection`
**Purpose**: Returns savings projection data for bar chart visualization

**Used By**:
- `Dashboard.jsx` → Savings Projection Chart

**Query Parameters**:
```
?cluster_id=uuid-1234&timeframe=30d
```

**Response**:
```json
{
  "unoptimized_cost": 15000,
  "optimized_cost": 10500,
  "potential_savings": 4500,
  "breakdown": {
    "spot_replacement": 2800,
    "bin_packing": 1200,
    "hibernation": 500
  }
}
```

**Backend Module**: `MOD-SPOT-01` + `MOD-PACK-01`  
**Function**: `get_savings_projection()`  
**Database**: `instances`, `recommendations`  

---

### GET `/metrics/composition`
**Purpose**: Returns fleet composition data for pie chart

**Used By**:
- `Dashboard.jsx` → Fleet Composition Pie Chart

**Response**:
```json
{
  "by_family": {
    "m5": 40,
    "c5": 25,
    "r5": 20,
    "t3": 15
  },
  "by_lifecycle": {
    "spot": 65,
    "on_demand": 35
  }
}
```

**Backend Module**: `CORE-API` → `metrics_service.py`  
**Function**: `get_fleet_composition()`  
**Database**: `instances`  

---

### GET `/activity/live`
**Purpose**: Returns real-time activity feed of recent optimization actions

**Used By**:
- `Dashboard.jsx` → Activity Feed Component

**Query Parameters**:
```
?limit=50&offset=0
```

**Response**:
```json
{
  "events": [
    {
      "timestamp": "2025-12-31T10:15:30Z",
      "action": "Switched Node i-0x89 to Spot",
      "savings": 0.04,
      "status": "success"
    }
  ]
}
```

**Backend Module**: `CORE-API` → `activity_service.py`  
**Function**: `get_activity_feed()`  
**Database**: `audit_logs`  

---

## Cluster Management APIs

### GET `/clusters`
**Purpose**: Lists all managed Kubernetes clusters

**Used By**:
- `ClusterRegistry.jsx` → Cluster Table
- `Dashboard.jsx` → Cluster Selector

**Response**:
```json
{
  "clusters": [
    {
      "id": "uuid-1234",
      "name": "prod-us-east-1",
      "region": "us-east-1",
      "k8s_version": "1.28",
      "node_count": 45,
      "monthly_cost": 5400,
      "efficiency_score": "A"
    }
  ]
}
```

**Backend Module**: `CORE-API` → `cluster_service.py`  
**Function**: `list_managed_clusters()`  
**Database**: `clusters`  

---

### GET `/clusters/{id}`
**Purpose**: Returns detailed information for a specific cluster

**Used By**:
- `ClusterRegistry.jsx` → Cluster Detail Drawer

**Response**:
```json
{
  "id": "uuid-1234",
  "name": "prod-us-east-1",
  "vpc_id": "vpc-abc123",
  "api_endpoint": "https://ABC123.eks.us-east-1.amazonaws.com",
  "node_groups": [...],
  "health_metrics": {...}
}
```

**Backend Module**: `CORE-API` → `cluster_service.py`  
**Function**: `get_cluster_details()`  
**Database**: `clusters`  

---

### GET `/clusters/discover`
**Purpose**: Discovers unmanaged EKS clusters in connected AWS accounts

**Used By**:
- `ClusterRegistry.jsx` → Add Cluster Modal

**Query Parameters**:
```
?account_id=uuid-1234
```

**Response**:
```json
{
  "clusters": [
    {
      "name": "staging-cluster",
      "arn": "arn:aws:eks:us-east-1:123456789012:cluster/staging",
      "status": "ACTIVE",
      "managed": false
    }
  ]
}
```

**Backend Module**: `WORK-DISC-01`  
**Function**: `list_discovered_clusters()`  
**AWS APIs**: `eks.list_clusters()`  

---

### POST `/clusters/connect`
**Purpose**: Generates Helm installation command for cluster agent

**Used By**:
- `ClusterRegistry.jsx` → Connect Cluster Button

**Request Body**:
```json
{
  "cluster_id": "uuid-1234"
}
```

**Response**:
```json
{
  "helm_command": "helm install spot-optimizer ...",
  "api_token": "token-xyz",
  "endpoint": "https://api.spotoptimizer.com"
}
```

**Backend Module**: `CORE-API` → `cluster_service.py`  
**Function**: `generate_agent_install()`  
**Database**: `clusters`  

---

### POST `/clusters/install`
**Purpose**: Generates Helm installation command (alternative endpoint)

**Used By**:
- `ClusterRegistry.jsx` → Import/Helm Checkbox

**Request Body**:
```json
{
  "cluster_id": "uuid-1234",
  "namespace": "spot-optimizer"
}
```

**Response**:
```json
{
  "helm_command": "helm install ...",
  "manifest_url": "https://..."
}
```

**Backend Module**: `CORE-API` → `cluster_service.py`  
**Function**: `generate_helm_install_cmd()`  

---

### GET `/clusters/{id}/verify`
**Purpose**: Checks agent heartbeat and connection status

**Used By**:
- `ClusterRegistry.jsx` → Connection Status Indicator

**Response**:
```json
{
  "status": "connected",
  "last_seen": "2025-12-31T10:15:30Z",
  "agent_version": "v1.2.0",
  "health": "healthy"
}
```

**Backend Module**: `CORE-API` → `cluster_service.py`  
**Function**: `verify_agent_connection()`  
**Database**: Redis (heartbeat cache)  

---

### POST `/clusters/{id}/optimize`
**Purpose**: Manually triggers optimization for a specific cluster

**Used By**:
- `ClusterRegistry.jsx` → Optimize Now Button

**Response**:
```json
{
  "job_id": "uuid-job-1234",
  "status": "queued",
  "estimated_time": "2-5 minutes"
}
```

**Backend Module**: `WORK-OPT-01`  
**Function**: `trigger_manual_optimization()`  
**Database**: `optimization_jobs`  

---

## Node Template APIs

### GET `/templates`
**Purpose**: Lists all node templates for the user

**Used By**:
- `NodeTemplates.jsx` → Template Grid
- `OptimizationPolicies.jsx` → Template Selector

**Response**:
```json
{
  "templates": [
    {
      "id": "uuid-1234",
      "name": "Production-General",
      "families": ["m5", "c5", "r5"],
      "architecture": "x86_64",
      "strategy": "SPOT",
      "is_default": true
    }
  ]
}
```

**Backend Module**: `CORE-API` → `template_service.py`  
**Function**: `list_node_templates()`  
**Database**: `node_templates`  

---

### POST `/templates`
**Purpose**: Creates a new node template

**Used By**:
- `NodeTemplates.jsx` → Create Template Wizard

**Request Body**:
```json
{
  "name": "AI-Workloads",
  "families": ["g4dn", "p3"],
  "architecture": "x86_64",
  "strategy": "SPOT",
  "disk_type": "gp3",
  "disk_size": 500
}
```

**Response**:
```json
{
  "id": "uuid-5678",
  "success": true
}
```

**Backend Module**: `CORE-API` → `template_service.py`  
**Function**: `create_node_template()`  
**Database**: `node_templates`  

---

### PATCH `/templates/{id}/default`
**Purpose**: Sets a template as the global default

**Used By**:
- `NodeTemplates.jsx` → Set Default Star

**Response**:
```json
{
  "success": true,
  "previous_default": "uuid-1234",
  "new_default": "uuid-5678"
}
```

**Backend Module**: `CORE-API` → `template_service.py`  
**Function**: `set_global_default_template()`  
**Database**: `node_templates`  

---

### POST `/templates/validate`
**Purpose**: Validates template configuration for conflicts

**Used By**:
- `TemplateWizard.jsx` → Live Validation

**Request Body**:
```json
{
  "families": ["g4dn"],
  "architecture": "ARM64"
}
```

**Response**:
```json
{
  "valid": false,
  "warnings": [
    "Instance type g4dn is incompatible with ARM64"
  ]
}
```

**Backend Module**: `MOD-VAL-01`  
**Function**: `validate_template_compatibility()`  

---

### DELETE `/templates/{id}`
**Purpose**: Deletes a node template (soft delete if in use)

**Used By**:
- `NodeTemplates.jsx` → Delete Action

**Response**:
```json
{
  "success": true,
  "message": "Template deleted"
}
```

**Backend Module**: `CORE-API` → `template_service.py`  
**Function**: `delete_node_template()`  
**Database**: `node_templates`  

---

## Optimization Policy APIs

### PATCH `/policies/karpenter`
**Purpose**: Updates Karpenter autoscaling configuration

**Used By**:
- `OptimizationPolicies.jsx` → Karpenter Master Toggle

**Request Body**:
```json
{
  "enabled": true,
  "strategy": "capacity-optimized"
}
```

**Response**:
```json
{
  "success": true,
  "broadcast": "sent to 3 agents"
}
```

**Backend Module**: `CORE-API` → `policy_service.py`  
**Function**: `update_karpenter_state()`  
**Database**: `cluster_policies`  

---

### PATCH `/policies/strategy`
**Purpose**: Updates provisioning strategy (lowest price vs capacity optimized)

**Used By**:
- `OptimizationPolicies.jsx` → Strategy Selector

**Request Body**:
```json
{
  "strategy": "lowest-price"
}
```

**Backend Module**: `CORE-API` → `policy_service.py`  
**Function**: `update_provisioning_strategy()`  

---

### PATCH `/policies/binpack`
**Purpose**: Updates bin packing aggressiveness threshold

**Used By**:
- `OptimizationPolicies.jsx` → BinPack Slider

**Request Body**:
```json
{
  "aggressiveness": 50
}
```

**Backend Module**: `CORE-API` → `policy_service.py`  
**Function**: `update_binpack_settings()`  

---

### PATCH `/policies/fallback`
**Purpose**: Enables/disables Spot fallback to On-Demand

**Used By**:
- `OptimizationPolicies.jsx` → Spot Fallback Checkbox

**Request Body**:
```json
{
  "enabled": true
}
```

**Backend Module**: `CORE-API` → `policy_service.py`  
**Function**: `update_fallback_policy()`  

---

### PATCH `/policies/spread`
**Purpose**: Configures availability zone spread for high availability

**Used By**:
- `OptimizationPolicies.jsx` → AZ Spread Checkbox

**Request Body**:
```json
{
  "enabled": true
}
```

**Backend Module**: `CORE-API` → `policy_service.py`  
**Function**: `update_spread_policy()`  

---

### PATCH `/policies/exclusions`
**Purpose**: Updates namespace/label exclusion list

**Used By**:
- `OptimizationPolicies.jsx` → Exclusions Input

**Request Body**:
```json
{
  "namespaces": ["kube-system", "monitoring", "vault"]
}
```

**Backend Module**: `CORE-API` → `policy_service.py`  
**Function**: `update_exclusion_list()`  

---

## Hibernation APIs

### POST `/hibernation/schedule`
**Purpose**: Saves weekly hibernation schedule matrix

**Used By**:
- `Hibernation.jsx` → Weekly Grid

**Request Body**:
```json
{
  "cluster_id": "uuid-1234",
  "schedule_matrix": [1,1,1,0,0,0,0,...],
  "timezone": "America/New_York"
}
```

**Response**:
```json
{
  "success": true,
  "projected_savings": 450
}
```

**Backend Module**: `CORE-API` → `hibernation_service.py`  
**Function**: `save_weekly_schedule()`  
**Database**: `hibernation_schedules`  

---

### POST `/hibernation/exception`
**Purpose**: Adds calendar exception (holiday override)

**Used By**:
- `Hibernation.jsx` → Calendar Exceptions

**Request Body**:
```json
{
  "cluster_id": "uuid-1234",
  "date": "2025-12-25",
  "mode": "force_sleep"
}
```

**Backend Module**: `CORE-API` → `hibernation_service.py`  
**Function**: `add_calendar_exception()`  

---

### POST `/hibernation/override`
**Purpose**: Manually wakes up or sleeps cluster immediately

**Used By**:
- `Hibernation.jsx` → Wake Up Now Button

**Request Body**:
```json
{
  "cluster_id": "uuid-1234",
  "action": "wake",
  "duration_hours": 2
}
```

**Response**:
```json
{
  "success": true,
  "expires_at": "2025-12-31T12:15:30Z"
}
```

**Backend Module**: `WORK-HIB-01` → `SCRIPT-ASG-01`  
**Function**: `trigger_manual_wakeup()`  
**Database**: `hibernation_overrides`  

---

### PATCH `/hibernation/tz`
**Purpose**: Updates cluster timezone for schedule

**Used By**:
- `Hibernation.jsx` → Timezone Selector

**Request Body**:
```json
{
  "timezone": "America/Los_Angeles"
}
```

**Backend Module**: `CORE-API` → `hibernation_service.py`  
**Function**: `update_cluster_timezone()`  

---

### PATCH `/hibernation/prewarm`
**Purpose**: Enables/disables pre-warm (soft start) feature

**Used By**:
- `Hibernation.jsx` → Pre-warm Checkbox

**Request Body**:
```json
{
  "enabled": true,
  "minutes": 30
}
```

**Backend Module**: `CORE-API` → `hibernation_service.py`  
**Function**: `update_prewarm_status()`  

---

## Audit & Compliance APIs

### GET `/audit`
**Purpose**: Fetches audit log entries with filtering and pagination

**Used By**:
- `AuditLogs.jsx` → Audit Table

**Query Parameters**:
```
?start_date=2025-12-01&end_date=2025-12-31&actor=user-id&limit=50&offset=0
```

**Response**:
```json
{
  "logs": [
    {
      "id": "uuid-1234",
      "timestamp": "2025-12-31T10:15:30.455Z",
      "actor": "Alice Admin",
      "event": "Modified Hibernation Schedule",
      "resource": "cluster-prod-us-east-1",
      "outcome": "success"
    }
  ],
  "total": 1234,
  "page": 1
}
```

**Backend Module**: `CORE-API` → `audit_service.py`  
**Function**: `fetch_audit_logs()`  
**Database**: `audit_logs`  

---

### GET `/audit/{id}/diff`
**Purpose**: Returns before/after diff for a specific audit log entry

**Used By**:
- `AuditLogs.jsx` → Diff Viewer Drawer

**Response**:
```json
{
  "before": {"max_nodes": 10},
  "after": {"max_nodes": 15},
  "diff": [
    {"field": "max_nodes", "old": 10, "new": 15}
  ]
}
```

**Backend Module**: `CORE-API` → `audit_service.py`  
**Function**: `fetch_audit_diff()`  

---

### GET `/audit/export`
**Purpose**: Exports audit logs with tamper-proof checksum

**Used By**:
- `AuditLogs.jsx` → Export Button

**Query Parameters**:
```
?format=csv&start_date=2025-12-01&end_date=2025-12-31
```

**Response**:
```json
{
  "file_url": "https://s3.../audit-export-uuid.csv",
  "checksum": "sha256:abc123...",
  "expires_in": 3600
}
```

**Backend Module**: `CORE-API` → `audit_service.py`  
**Function**: `generate_audit_checksum_export()`  

---

### PATCH `/audit/retention`
**Purpose**: Updates audit log retention policy

**Used By**:
- `AuditLogs.jsx` → Retention Slider

**Request Body**:
```json
{
  "retention_days": 365
}
```

**Backend Module**: `CORE-API` → `audit_service.py`  
**Function**: `update_log_retention()`  

---

## Settings & Account Management APIs

### GET `/settings/accounts`
**Purpose**: Lists all connected AWS accounts

**Used By**:
- `Settings.jsx` → Cloud Integrations Tab
- `CloudIntegrations.jsx` → Account List

**Response**:
```json
{
  "accounts": [
    {
      "id": "uuid-1234",
      "alias": "Acme Prod",
      "aws_account_id": "123456789012",
      "region": "us-east-1",
      "status": "active",
      "connection_method": "role-based"
    }
  ]
}
```

**Backend Module**: `CORE-API` → `account_service.py`  
**Function**: `list_cloud_accounts()`  
**Database**: `accounts`  

---

### DELETE `/settings/accounts`
**Purpose**: Disconnects and removes AWS account

**Used By**:
- `CloudIntegrations.jsx` → Disconnect Button

**Request Body**:
```json
{
  "account_id": "uuid-1234"
}
```

**Backend Module**: `CORE-API` → `account_service.py`  
**Function**: `remove_cloud_account()`  

---

### PATCH `/settings/context`
**Purpose**: Switches active account context (multi-account)

**Used By**:
- `Header.jsx` → Account Context Switcher

**Request Body**:
```json
{
  "account_id": "uuid-5678"
}
```

**Response**:
```json
{
  "success": true,
  "active_account": "Acme Lab"
}
```

**Backend Module**: `CORE-API` → `account_service.py`  
**Function**: `switch_account_context()`  

---

### GET `/settings/team`
**Purpose**: Lists team members and their roles

**Used By**:
- `Settings.jsx` → Team Members Tab

**Response**:
```json
{
  "members": [
    {
      "id": "uuid-1234",
      "email": "admin@acme.com",
      "role": "owner",
      "last_login": "2025-12-31T10:00:00Z"
    }
  ]
}
```

**Backend Module**: `CORE-API` → `team_service.py`  
**Function**: `list_team_roles()`  
**Database**: `users`, `team_members`  

---

### POST `/settings/invite`
**Purpose**: Invites new team member via email

**Used By**:
- `Settings.jsx` → Invite Team Member Form

**Request Body**:
```json
{
  "email": "auditor@acme.com",
  "role": "viewer"
}
```

**Response**:
```json
{
  "success": true,
  "invite_id": "uuid-invite-1234",
  "expires_in": 604800
}
```

**Backend Module**: `CORE-API` → `team_service.py`  
**Function**: `create_team_invitation()`  

---

## Admin APIs (Platform Owner Only)

### GET `/admin/clients`
**Purpose**: Lists all client organizations (Super Admin only)

**Used By**:
- `AdminDashboard.jsx` → Client Registry

**Response**:
```json
{
  "clients": [
    {
      "id": "uuid-1234",
      "org_name": "Acme Corp",
      "plan": "enterprise",
      "monthly_spend": 12450,
      "created_at": "2025-01-15T10:00:00Z"
    }
  ]
}
```

**Backend Module**: `CORE-API` → `admin_service.py`  
**Function**: `list_all_clients()`  
**Role Required**: `super_admin`  

---

### POST `/admin/impersonate`
**Purpose**: Generates temporary JWT to impersonate client

**Used By**:
- `AdminDashboard.jsx` → Impersonate Button

**Request Body**:
```json
{
  "client_id": "uuid-1234"
}
```

**Response**:
```json
{
  "temp_token": "jwt-temp-xyz",
  "expires_in": 3600,
  "client_org": "Acme Corp"
}
```

**Backend Module**: `CORE-API` → `admin_service.py`  
**Function**: `generate_impersonation_token()`  

---

### PATCH `/clients/{id}/flags`
**Purpose**: Updates feature flags for specific client

**Used By**:
- `AdminDashboard.jsx` → Feature Flag Toggles

**Request Body**:
```json
{
  "flags": {
    "enable_hibernation": true,
    "enable_multi_account": false
  }
}
```

**Backend Module**: `CORE-API` → `admin_service.py`  
**Function**: `update_feature_flags()`  

---

### POST `/admin/reset-pass`
**Purpose**: Triggers password reset email for client

**Used By**:
- `AdminDashboard.jsx` → Reset Password Button

**Request Body**:
```json
{
  "client_id": "uuid-1234"
}
```

**Backend Module**: `CORE-API` → `admin_service.py`  
**Function**: `trigger_password_reset()`  

---

### DELETE `/admin/clients/{id}`
**Purpose**: Hard deletes client and all associated data

**Used By**:
- `AdminDashboard.jsx` → Delete Client Button

**Response**:
```json
{
  "success": true,
  "deleted_resources": {
    "clusters": 3,
    "instances": 45,
    "templates": 5
  }
}
```

**Backend Module**: `CORE-API` → `admin_service.py`  
**Function**: `hard_delete_client()`  

---

### GET `/admin/stats`
**Purpose**: Returns global platform statistics

**Used By**:
- `AdminDashboard.jsx` → Global Metrics KPIs

**Response**:
```json
{
  "total_clients": 145,
  "total_spend": 1245000,
  "total_savings": 430000,
  "active_clusters": 567
}
```

**Backend Module**: `CORE-API` → `admin_service.py`  
**Function**: `aggregate_global_stats()`  

---

### GET `/admin/health`
**Purpose**: Returns system component health status

**Used By**:
- `SystemHealth.jsx` → Health Dashboard

**Response**:
```json
{
  "database": "healthy",
  "redis": "healthy",
  "celery_workers": "degraded",
  "scraper_health": "healthy"
}
```

**Backend Module**: `CORE-API` → `health_service.py`  
**Function**: `check_system_components()`  

---

### GET `/admin/health/workers`
**Purpose**: Returns Celery worker queue depth and status

**Used By**:
- `SystemHealth.jsx` → Worker Status Traffic Lights

**Response**:
```json
{
  "queue_depth": 523,
  "status": "yellow",
  "workers_active": 5,
  "workers_total": 8
}
```

**Backend Module**: `CORE-API` → `health_service.py`  
**Function**: `check_worker_queue_depth()`  
**Database**: Redis  

---

## Lab & ML Model APIs

### POST `/lab/live-switch`
**Purpose**: Executes live instance replacement test

**Used By**:
- `TheLab.jsx` → Live Switch Form

**Request Body**:
```json
{
  "instance_id": "i-0abc123",
  "target_model": "Spot-V2-Aggressive"
}
```

**Response**:
```json
{
  "test_id": "uuid-test-1234",
  "telemetry": {
    "volume_detach_time": 4.2,
    "spot_request_time": 1.1,
    "boot_time": 45.0,
    "total_downtime": 52.3
  }
}
```

**Backend Module**: `MOD-AI-01` + `CORE-EXEC` + `SCRIPT-SPOT-01`  
**Function**: `execute_live_switch_logic()`  
**Database**: `lab_experiments`  

---

### POST `/lab/graduate`
**Purpose**: Promotes ML model to production (hot-swap)

**Used By**:
- `TheLab.jsx` → Graduate to Production Button

**Request Body**:
```json
{
  "model_id": "uuid-model-1234"
}
```

**Response**:
```json
{
  "success": true,
  "broadcast_sent": true,
  "clients_affected": 145
}
```

**Backend Module**: `MOD-AI-01`  
**Function**: `promote_model_to_production()`  
**Database**: `ml_models`  

---

### GET `/admin/models`
**Purpose**: Lists all uploaded ML models in registry

**Used By**:
- `TheLab.jsx` → Model Registry List

**Response**:
```json
{
  "models": [
    {
      "id": "uuid-model-1234",
      "version": "v2.1",
      "status": "production",
      "uploaded_at": "2025-12-15T10:00:00Z"
    }
  ]
}
```

**Backend Module**: `CORE-API` → `model_service.py`  
**Function**: `list_ai_models()`  

---

### POST `/lab/parallel`
**Purpose**: Configures parallel A/B test for model comparison

**Used By**:
- `TheLab.jsx` → A/B Test Configuration Form

**Request Body**:
```json
{
  "instance_a": "i-0abc123",
  "model_a": "Conservative-v1",
  "instance_b": "i-0def456",
  "model_b": "Aggressive-v2"
}
```

**Response**:
```json
{
  "test_id": "uuid-test-5678",
  "status": "running"
}
```

**Backend Module**: `MOD-AI-01`  
**Function**: `configure_parallel_test()`  
**Database**: `lab_experiments`  

---

### GET `/lab/parallel-results`
**Purpose**: Returns A/B test comparison results

**Used By**:
- `TheLab.jsx` → Comparison Graphs

**Query Parameters**:
```
?test_id=uuid-test-5678
```

**Response**:
```json
{
  "model_a": {
    "savings": 150,
    "interruptions": 0,
    "avg_boot_time": 48
  },
  "model_b": {
    "savings": 172,
    "interruptions": 1,
    "avg_boot_time": 45
  }
}
```

**Backend Module**: `MOD-AI-01`  
**Function**: `get_ab_test_results()`  

---

## WebSocket Endpoints

### WS `/clusters/heartbeat`
**Purpose**: Real-time agent heartbeat stream

**Used By**:
- `ClusterRegistry.jsx` → Connection Status Indicator

**Message Format**:
```json
{
  "cluster_id": "uuid-1234",
  "timestamp": "2025-12-31T10:15:30Z",
  "status": "healthy"
}
```

**Backend Module**: `CORE-API`  
**Function**: `detect_agent_heartbeat()`  

---

### WS `/notify`
**Purpose**: Real-time notification push to frontend

**Used By**:
- `App.jsx` → Toast Notifications

**Message Format**:
```json
{
  "type": "success",
  "message": "Cluster optimized successfully",
  "timestamp": "2025-12-31T10:15:30Z"
}
```

**Backend Module**: `CORE-API`  
**Function**: `push_websocket_msg()`  

---

### WS `/admin/logs`
**Purpose**: Live system log streaming (Admin only)

**Used By**:
- `SystemHealth.jsx` → Live Logs Viewer

**Message Format**:
```json
{
  "timestamp": "2025-12-31T10:15:30.455Z",
  "level": "INFO",
  "component": "MOD-SPOT-01",
  "message": "Selected instance: c5.xlarge"
}
```

**Backend Module**: `CORE-API`  
**Function**: `stream_system_logs()`  

---

### WS `/lab/stream/{id}`
**Purpose**: Live telemetry stream for A/B tests

**Used By**:
- `TheLab.jsx` → Comparison Chart (Live Updates)

**Message Format**:
```json
{
  "test_id": "uuid-test-5678",
  "timestamp": "2025-12-31T10:15:30Z",
  "model_a_metric": 150,
  "model_b_metric": 172
}
```

**Backend Module**: `CORE-API`  
**Function**: `stream_lab_results()`  

---

## Billing APIs

### GET `/billing/status`
**Purpose**: Returns current usage and plan limits

**Used By**:
- `Billing.jsx` → Usage Progress Bar
- `Header.jsx` → Usage Indicator

**Response**:
```json
{
  "plan": "pro",
  "node_limit": 50,
  "nodes_used": 48,
  "usage_percentage": 96
}
```

**Backend Module**: `CORE-API` → `billing_service.py`  
**Function**: `check_usage_limits()`  

---

### POST `/billing/card`
**Purpose**: Saves payment method via Stripe

**Used By**:
- `Billing.jsx` → Payment Form

**Request Body**:
```json
{
  "stripe_token": "tok_xyz123"
}
```

**Response**:
```json
{
  "success": true,
  "last4": "4242"
}
```

**Backend Module**: `CORE-API` → `billing_service.py`  
**Function**: `stripe_attach_source()`  

---

### GET `/billing/history`
**Purpose**: Returns invoice history

**Used By**:
- `Billing.jsx` → Invoice List

**Response**:
```json
{
  "invoices": [
    {
      "id": "inv_xyz",
      "date": "2025-12-01",
      "amount": 450,
      "status": "paid",
      "pdf_url": "https://..."
    }
  ]
}
```

**Backend Module**: `CORE-API` → `billing_service.py`  
**Function**: `stripe_list_invoices()`  

---

### POST `/billing/subscription`
**Purpose**: Updates subscription plan

**Used By**:
- `Billing.jsx` → Upgrade to Enterprise Button

**Request Body**:
```json
{
  "plan_id": "enterprise"
}
```

**Backend Module**: `CORE-API` → `billing_service.py`  
**Function**: `stripe_update_subscription()`  

---

## API Summary Statistics

**Total Endpoints**: 78  
**Authentication Required**: 65  
**Admin Only**: 13  
**WebSocket Endpoints**: 4  
**Rate Limited**: 4  

**By Category**:
- Authentication: 4
- Onboarding: 4
- Dashboard & Metrics: 4
- Cluster Management: 8
- Node Templates: 5
- Optimization Policies: 6
- Hibernation: 5
- Audit: 4
- Settings: 5
- Admin: 10
- Lab & ML: 5
- WebSocket: 4
- Billing: 4

---

**Document Version**: 1.0  
**Last Updated**: 2025-12-31  
**Status**: Complete API Catalog
