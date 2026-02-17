# Backend Feature Flows — Spot Optimizer Platform

> Deep-dive into every major feature: how the user interacts, what happens step-by-step on the backend, AWS-side logic, database operations, and which UI components are involved.
>
> **Last Updated**: 2026-02-17

---

## Table of Contents

1. [User Signup & Login](#1-user-signup--login)
2. [AWS Account Onboarding](#2-aws-account-onboarding)
3. [Guided Onboarding Wizard](#3-guided-onboarding-wizard)
4. [Cluster Discovery & Management](#4-cluster-discovery--management)
5. [Agent Injection & Monitoring](#5-agent-injection--monitoring)
6. [Cluster Hibernation](#6-cluster-hibernation)
7. [Resource Hygiene (Cleanup Scanning)](#7-resource-hygiene-cleanup-scanning)
8. [AtharvaAI ML Pool Ranking (System A)](#8-atharvaai-ml-pool-ranking-system-a)
9. [Termination Detection & Auto-Rebalancing (System B)](#9-termination-detection--auto-rebalancing-system-b)
10. [Right-Sizing Recommendations](#10-right-sizing-recommendations)
11. [JIT Approval & Access Governance](#11-jit-approval--access-governance)
12. [RBAC & Permission System](#12-rbac--permission-system)
13. [Dashboard KPIs & Metrics](#13-dashboard-kpis--metrics)
14. [Tag Governance & Bulk Tagging](#14-tag-governance--bulk-tagging)
15. [Audit Logging](#15-audit-logging)
16. [Admin Panel (Super Admin)](#16-admin-panel-super-admin)
17. [Background Workers (Celery)](#17-background-workers-celery)

---

## 1. User Signup & Login

### What This Feature Does
Allows new organizations to register and existing users to log in. Supports invitation-based signups where a user joins an existing org.

### User Actions & Step-by-Step Flow

#### Signup Flow
1. **User fills signup form** — enters organization name, full name, email, password
2. **Frontend calls** `POST /api/v1/auth/signup`
3. **Backend-side logic:**
   - Checks if email already exists (case-insensitive) → rejects if duplicate
   - Checks for pending invitation (`organization_invitations` table) with matching email
   - **If invitation found:** User joins the existing org with the invited role + access level. Invitation status set to `ACCEPTED`
   - **If no invitation:** Creates new `Organization` (name, slug = hyphenated+timestamp), then creates `User` with role `ORG_ADMIN` and `access_level = FULL`. Sets `organization.owner_user_id` to new user
   - Password hashed with **bcrypt** before storing in `users.password_hash`
   - JWT access + refresh tokens generated (payload: user_id, org_id, role, email; expiry from `settings.ACCESS_TOKEN_EXPIRE_MINUTES`)
4. **Frontend stores JWT** in memory + Zustand store, redirects to Onboarding or Dashboard

#### Login Flow
1. **User enters email + password**
2. **Frontend calls** `POST /api/v1/auth/login`
3. **Backend-side logic:**
   - Finds user by email (case-insensitive)
   - Verifies password via bcrypt `verify_password()`
   - If `user.must_reset_password = True` → returns flag, frontend redirects to password reset
   - Generates JWT tokens, returns user profile + org data
4. **Frontend redirects** to Dashboard (or forced password reset page for invited users)

#### Logout
- `POST /api/v1/auth/logout` → adds JWT to **Redis blacklist** key `jwt_blacklist:<token>` with TTL = remaining token expiry time

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/auth_routes.py` | Routes: signup, login, logout, me, profile, change-password, first-login-reset, invitation-response |
| `services/auth_service.py` | Bcrypt hashing, JWT generation (access+refresh), invitation logic, password change validation |

### DB Tables Used
`users`, `organizations`, `organization_invitations` + Redis `jwt_blacklist:*`

### UI Components
`auth/Login.jsx`, `auth/Signup.jsx`, `auth/FirstLoginReset.jsx`, `layout/MainLayout.jsx` (logout), `settings/Settings.jsx` (profile/password change)

---

## 2. AWS Account Onboarding

### What This Feature Does
Links customer AWS accounts to the platform using IAM cross-account roles. The platform uses STS AssumeRole to access customer resources (EKS, EC2, S3, etc.) without storing long-term credentials.

### User Actions & Step-by-Step Flow

1. **User downloads CloudFormation template** — `GET /api/v1/onboarding/template`
   - Backend reads YAML template, injects org's unique `external_id` as a parameter
   - User deploys this in their AWS console → creates IAM Role with trust policy pointing to platform's AWS account
2. **User fills "Link Account" modal** — enters 12-digit AWS Account ID, full IAM Role ARN, selects region
   - `External ID` is auto-filled from org (disabled field, from `GET /api/v1/organization/connection-info`)
3. **Frontend calls** `POST /api/v1/accounts`
4. **Backend-side logic:**
   - **Security Rule:** Always overwrites user-provided External ID with org's canonical `external_id` from `organizations` table (prevents impersonation)
   - **AWS-side logic:** Calls `STS AssumeRole(RoleArn, ExternalId)` to verify the IAM trust policy is correctly configured
   - If STS succeeds → creates `Account` record
   - **Governance Rule (Members):** If `requester.role == MEMBER`, checks team governance config for `CONNECT_ACCOUNT` flag. If true → sets `status = PENDING_APPROVAL` and creates `ApprovalRequest` ticket. If false (fallback) → Members always need approval
   - **Governance Rule (Admins):** Admins get `status = ACTIVE` immediately
5. **Post-link validation** — `POST /api/v1/accounts/{id}/validate`
   - Re-runs STS AssumeRole to confirm credentials still work
   - On success → auto-triggers `cluster_service.discover_clusters()` to find EKS clusters in the account
6. **Set Default** — `POST /api/v1/accounts/{id}/set-default` → unsets all other accounts' `is_default`, sets this one

### AWS-Side Logic & Rules
- IAM Role must have trust policy allowing platform's AWS account ID to assume it
- External ID must match org's stored `external_id` (32-char random string)
- Role needs permissions: `eks:ListClusters`, `eks:DescribeCluster`, `ec2:Describe*`, `s3:List*`, `ce:GetCostAndUsage`, etc.

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/account_routes.py` | Routes: list, create, validate, set-default, approve, delete |
| `services/account_service.py` | STS AssumeRole verification, RBAC + governance approval workflow, auto-discovery trigger |
| `api/organization_routes.py` | Connection-info (external_id), regenerate external ID |
| `services/organization_service.py` | Member management, external ID regeneration (32-char random) |

### DB Tables Used
`accounts`, `organizations` (external_id), `approval_requests` (if governance requires approval)

### UI Components
`settings/CloudIntegrations.jsx` (account cards, link modal, validate/delete buttons), `onboarding/ConnectStep.jsx`, `onboarding/VerifyStep.jsx`

---

## 3. Guided Onboarding Wizard

### What This Feature Does
4-step wizard that guides new users through platform setup: Welcome → Connect AWS → Verify → Success.

### User Actions & Step-by-Step Flow

1. **Welcome Step** — static screen with feature overview, "Get Started" CTA
2. **Connect Step** — generates CloudFormation stack URL
   - `POST /api/v1/onboarding/generate-stack-url` → builds full AWS Console URL with pre-filled template parameters
   - User clicks "Launch in AWS Console" → opens AWS in new tab to deploy CloudFormation stack
   - External ID auto-copied for reference
3. **Verify Step** — auto-polls to check if connection succeeded
   - Frontend polls `POST /api/v1/accounts/validate/{id}` repeatedly → checks STS AssumeRole
   - Green checkmark when `account.status = ACTIVE`
4. **Success Step** — confetti animation, CTA to Dashboard
   - **Skip option**: `POST /api/v1/onboarding/skip` → sets `current_step = COMPLETED`, `onboarding_completed = True`

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/onboarding_routes.py` | Routes: get-state, template download, generate-stack-url, skip |
| `services/onboarding_service.py` | CloudFormation URL generation, state machine management |

### DB Tables Used
`onboarding_states`, `organizations`, `accounts`

### UI Components
`pages/Onboarding.jsx` (parent), `onboarding/WelcomeStep.jsx`, `onboarding/ConnectStep.jsx`, `onboarding/VerifyStep.jsx`, `onboarding/SuccessStep.jsx`

---

## 4. Cluster Discovery & Management

### What This Feature Does
Discovers EKS clusters in linked AWS accounts, manages cluster lifecycle (connect, verify, disconnect, delete).

### User Actions & Step-by-Step Flow

#### Discovery
1. **User clicks "Refresh Discovery"** on Cluster List page
2. **Frontend calls** `POST /api/v1/clusters/discover` with `account_id`
3. **Backend-side logic + AWS-side logic:**
   - STS AssumeRole into customer account using stored `role_arn` + `external_id`
   - Calls `eks.list_clusters()` → gets list of all EKS cluster names in the region
   - For each cluster: calls `eks.describe_cluster(name)` → gets version, endpoint, status
   - **DB logic:** Checks if `Cluster` record exists (by name + account_id). If exists → updates version/endpoint/status. If not → creates new `Cluster` with `status = DISCOVERED`
   - Commits all changes in single transaction

#### Agentless AWS Connection
1. **User clicks "Connect via AWS"** and enters cluster name, IAM Role ARN, region
2. `POST /api/v1/clusters/connect` → validates region, checks no duplicate name in org, creates Cluster with `is_agentless = 'Y'`, `status = ACTIVE`

#### Cluster Verification
- `POST /api/v1/clusters/verify/{id}` → checks if `Cluster.last_heartbeat` is within 10-minute window. If yes → `status = CONNECTED`. If stale → `status = DISCONNECTED`

#### Cluster Delete
- `DELETE /api/v1/clusters/{id}` → validates no active instances exist → cascade deletes `instances`, `cluster_metrics`, `hibernation_schedules` → audit logged

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/cluster_routes.py` | Routes: list, get, discover, connect, verify, disconnect, delete, nodes, auto-install |
| `services/cluster_service.py` | boto3 EKS discovery, STS session management, Helm install generation, heartbeat tracking |

### DB Tables Used
`clusters`, `accounts`, `instances`, `cluster_metrics`, `api_keys`

### UI Components
`clusters/ClusterList.jsx` (list page), `clusters/ClusterDetails.jsx` (detail panel), `clusters/NodeList.jsx` (nodes), `clusters/ClusterDisconnectModal.jsx`, `clusters/ClusterDeleteModal.jsx`

---

## 5. Agent Injection & Monitoring

### What This Feature Does
Deploys a DaemonSet/Deployment agent into the customer's Kubernetes cluster to collect pod metrics, send heartbeats, and enable real-time optimization.

### User Actions & Step-by-Step Flow

1. **User clicks "Inject Agent"** on a discovered cluster
2. **Frontend calls** `POST /api/v1/clusters/{id}/auto-install`
3. **Backend-side logic:**
   - Generates 64-char random API key using `secrets.token_urlsafe(48)`
   - Stores `key_hash` (SHA-256) in `api_keys` table with `cluster_id`
   - Generates Kubernetes YAML manifest containing:
     - `Namespace`: `spot-optimizer`
     - `ConfigMap`: cluster_id, api_endpoint, region
     - `Deployment`: agent container image `spotoptimizer/agent:latest` with envFrom configmap + secret
   - Returns install command to frontend
4. **User runs the kubectl command** in their terminal (or uses Helm script)
5. **Agent starts running:**
   - **Registers**: `POST /api/v1/agents/register` — verifies API key hash, sets `cluster.agent_installed = 'Y'`
   - **Heartbeat**: `POST /api/v1/agents/heartbeat` every 30 seconds — updates `cluster.last_heartbeat`
   - **Pod Metrics**: `POST /api/v1/pod-metrics/batch` every 5 min — batch inserts up to 500 pod CPU/memory readings
6. **Backend monitors** — if no heartbeat in 10 min, cluster status → `DISCONNECTED`

### AWS-Side Logic
- No direct AWS API calls for agent injection — it's pure Kubernetes
- Agent reads EC2 metadata from within pods to detect spot vs on-demand
- Agent uses `instance-metadata-service` to detect termination notices

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `services/agent_injector.py` | Helm-based agent deployment, API key generation, YAML manifest building |
| `api/agent_routes.py` | Routes: register, deregister, heartbeat (agent-only, no frontend UI) |
| `api/pod_metrics_routes.py` | Routes: batch ingest, query, cleanup (agent-only) |

### DB Tables Used
`clusters` (agent_installed, last_heartbeat), `api_keys` (key_hash), `pod_metrics` (CPU/memory readings)

### UI Components
`clusters/ClusterList.jsx` (inject agent button), `clusters/ClusterDetails.jsx` (connection status badge)

---

## 6. Cluster Hibernation

### What This Feature Does
Allows users to set weekly schedules that automatically sleep/wake clusters to save costs during non-business hours. Supports 4 strategies: Namespace Sleep, Node Scale-Down, Full Hibernation, and Custom.

### User Actions & Step-by-Step Flow

#### Creating a Schedule
1. **User navigates to Hibernation page** for a specific cluster (URL includes clusterId)
2. **User selects a strategy** — from StrategySelector cards:
   - **Namespace Sleep**: Scales down deployments to 0 replicas in selected namespaces
   - **Node Scale-Down**: Cordons and drains non-critical node groups
   - **Full Hibernation**: Combines namespace sleep + node scale-down
   - **Custom**: User-defined script execution
3. **User paints the weekly schedule grid** — 7 days × 24 hours = 168 cells. Each cell is `1` (active/awake) or `0` (hibernating). Stored as a 168-character string of 0s and 1s
4. **User selects timezone** — dropdown (e.g., `America/New_York`, `Asia/Kolkata`)
5. **User sets pre-warm minutes** — slider 0–60 min, how early to wake before scheduled active time
6. **User clicks "Save Schedule"**
7. **Frontend calls** `POST /api/v1/hibernation/schedules`
8. **Backend-side logic (validation rules):**
   - **Verifies cluster ownership**: `Cluster → Account → user_id` must match current user
   - **Checks no existing schedule**: Only 1 schedule per cluster (raises `ResourceAlreadyExistsError` if duplicate)
   - **Validates schedule matrix**: Must be exactly 168 characters, only `0` and `1` allowed
   - **Validates timezone**: Must be a valid IANA timezone string
   - **Validates pre-warm**: Must be 0–60 minutes
   - **Validates strategy**: Must be one of `NAMESPACE_SLEEP`, `NODE_SCALE_DOWN`, `FULL_HIBERNATION`, `CUSTOM`
   - Converts matrix list to string, creates `HibernationSchedule` record
   - **Audit log**: Records `HIBERNATION_SCHEDULE_CREATED` with schedule_id and strategy

#### Toggling a Schedule
1. **User clicks the toggle switch** on a schedule
2. `POST /api/v1/hibernation/schedules/{id}/toggle`
3. Flips `is_active` between `'Y'` and `'N'`, audit logged

#### How Execution Works (Background Worker)
- **Celery worker** (`hibernation_executor.py`) runs every **1 minute**
- Calls `HibernationService.get_active_schedules()` → fetches all schedules where `is_active = 'Y'`
- For each schedule:
  1. Converts current UTC time to schedule's timezone
  2. Calculates the 168-cell index: `(day_of_week × 24) + hour`
  3. Subtracts `pre_warm_minutes` from the index to check if pre-warming is needed
  4. If current cell = `0` (hibernate) and cluster is awake → **executes sleep action** based on strategy
  5. If current cell = `1` (active) and cluster is hibernating → **executes wake action**
  6. Pre-warm: If next cell is `1` but current is `0`, and we're within pre-warm window → starts wake early

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/hibernation_routes.py` | Routes: strategies, list/create/update/delete schedules, toggle, override |
| `services/hibernation_service.py` | Schedule CRUD with full validation (matrix, timezone, pre-warm, strategy), audit logging |

### DB Tables Used
`hibernation_schedules` (cluster_id, schedule_matrix, timezone, pre_warm_minutes, strategy, is_active), `clusters`, `audit_logs`

### UI Components
| Component | What It Does |
|:----------|:-------------|
| `pages/HibernationPage.jsx` | Page container — 2/3 scheduler + 1/3 sidebar |
| `hibernation/StrategySelector.jsx` | Strategy cards (4 options) |
| `hibernation/HibernationScheduler.jsx` | Interactive 7×24 grid for painting schedule |
| `hibernation/HibernationScheduleV2.jsx` | Alternative V2 scheduler with template support |
| `hibernation/ValidationPanel.jsx` | Validates schedule before saving |
| `hibernation/CostAnalytics.jsx` | Estimated cost savings from hibernation |
| `store/useHibernationStore.js` | Zustand store: strategy, schedule matrix, timezone, templates |

---

## 7. Resource Hygiene (Cleanup Scanning)

### What This Feature Does
Scans AWS accounts for orphaned, unused, and untagged resources across 7 categories (Compute, Storage, Network, DB, Security, Management, Identity). Detects zombies using 11+ heuristics and lets users clean up with governance controls.

### User Actions & Step-by-Step Flow

#### Scanning
1. **User selects an AWS account** from dropdown and clicks "Scan"
2. **Frontend calls** `GET /api/v1/hygiene/scan/{accountId}` (optional `?regions=us-east-1,eu-west-1` or `?regions=ALL`)
3. **Backend-side logic:**
   - **Cache check**: Generates cache key `cleanup:scan:{accountId}:{regions}` → checks Redis. If cached (1h TTL), returns immediately
   - **STS AssumeRole** into customer account
   - **Region resolution**: If `ALL`, calls `ec2.describe_regions()` to get all enabled regions (typically 15+). If specific region, uses that
   - **Parallel scanning**: Creates `ThreadPoolExecutor(max_workers=10)` and submits `_scan_region_worker()` per region
4. **Each region worker scans 7+ categories in parallel:**
   - **Compute**: EKS clusters, ECS clusters, Auto Scaling Groups — checks untagged, idle, zero-instance
   - **Storage**: Unattached EBS volumes, orphaned snapshots (no parent AMI), S3 empty/untagged buckets
   - **Network**: Unused Elastic IPs, orphaned ENIs (detached), unused NAT Gateways, VPC endpoints
   - **Database**: Unused RDS instances (CPU < 5% over 7d), idle ElastiCache clusters, orphaned RDS snapshots
   - **Security**: KMS keys (disabled/pending deletion), unused Secrets Manager secrets, stale IAM users
   - **Management**: Unused Config rules, SSM parameters, CloudWatch alarms, Lambda functions (0 invocations)
   - **Identity**: IAM users with no login in 90+ days, unused access keys
5. **Zombie detection heuristics** (11+ rules):
   - EBS volume with no attachments
   - Snapshot with no parent AMI
   - Elastic IP not associated to any instance
   - ENI with status = `available` (detached)
   - RDS instance with CPU avg < 5% for 7 days
   - S3 bucket with 0 objects
   - Security group with 0 attached instances (excluding default)
   - IAM user with no login in 90+ days
   - Lambda function with 0 invocations in 14 days
   - CloudWatch alarm in `INSUFFICIENT_DATA` state > 7 days
   - NAT Gateway with 0 bytes processed in 7 days
6. **Post-processing**: Marks resources as `is_authorized = True` if they exist in `authorized_resources` table (user previously authorized). Deducts authorized costs from total savings figure
7. **Caches result** in Redis (1h TTL), returns `HygieneSummary` with totals + per-resource data

#### Executing Cleanup Actions
1. **User selects resources** and clicks Delete / Authorize / Unauthorize
2. **Frontend calls** `POST /api/v1/hygiene/action`
3. **Backend governance checks (ordered):**
   - **Step 1 – System Approval Check**: If `org.require_automation_approval = True` → creates approval ticket instead of executing → returns `pending_approval` status
   - **Step 2 – JIT Permission Check**: Maps action type to feature ID (`TERMINATE/DELETE` → `hygiene:execute`). Calls `PermissionService.enforce()` for each resource. If user lacks permission and has no active JIT window → raises 403 error
   - **Step 3 – Execute via boto3**: Based on action type:
     - `DELETE`: `ec2.delete_volume()`, `ec2.delete_snapshot()`, `elbv2.delete_load_balancer()`, `ec2.deregister_image()`
     - `RELEASE`: `ec2.release_address()` (Elastic IPs)
     - `TERMINATE`: `ec2.terminate_instances()`
     - `STOP`: `rds.stop_db_instance()`
     - `AUTHORIZE`: Creates `AuthorizedResource` record in DB (exempts from future scans)
     - `UNAUTHORIZE`: Deletes `AuthorizedResource` record

### AWS-Side Logic & Rules
- Requires IAM permissions: `ec2:DeleteVolume`, `ec2:DeleteSnapshot`, `ec2:ReleaseAddress`, `ec2:TerminateInstances`, `rds:StopDBInstance`, `s3:DeleteBucket`, `iam:ListUsers`, etc.
- Resources can only be deleted in same region they were created
- Deep dependency checking: `check_dependencies()` verifies AMI references, volume attachments, ENI associations before allowing delete

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/hygiene_routes.py` | Routes: scan, action, cost-services, check-dependencies |
| `services/hygiene_service.py` | 2631 lines — parallel scanning engine, 7 categories, 11+ zombie heuristics, RBAC/JIT governance, boto3 action execution |

### DB Tables Used
`accounts`, `authorized_resources`, `cleanup_policies`, `audit_logs` + Redis `cleanup:scan:*` (cache)

### UI Components
| Component | What It Does |
|:----------|:-------------|
| `cleanup/CleanupDashboard.jsx` | Main page — hero metrics, filter bar, resource table |
| `cleanup/tables/ResourceTable.jsx` | Table with select-all, bulk actions, status badges |
| `cleanup/summary/HeroMetricsPanel.jsx` | Animated savings gauge + total waste + resource counts |
| `cleanup/FilterPanel.jsx` | Account, region, category, status filters |
| `cleanup/layout/CleanupSidebar.jsx` | Per-service cost breakdown |
| `cleanup/BulkTagWizard.jsx` | 3-step wizard for bulk tagging selected resources |

---

## 8. AtharvaAI ML Pool Ranking (System A)

### What This Feature Does
Runs an 8-step filtering + ML scoring pipeline every 30 seconds to rank EC2 Spot instance pools by safety and cost-effectiveness. Uses ONNX models trained on spot price history to predict interruption risk and savings potential.

### User Actions & Step-by-Step Flow

1. **User navigates to AtharvaAI page** → Pool Rankings table auto-loads
2. **Frontend calls** `GET /api/v1/atharvaai/rankings` (with cluster/template filters)
3. **Backend executes 8-step pipeline:**

#### Step 1 — Node Template Filtering
- Loads user-defined `NodeTemplate` (from `node_templates` table): architecture (amd64/arm64), vCPU range, memory range, allowed families (m5, c5, r5...), allowed sizes (large, xlarge...)
- Filters AWS instance catalog to only matching types
- Generates candidate pools as `(instance_type, availability_zone)` combinations

#### Step 2 — AZ Filtering
- If user specified allowed AZs → filters pools to those AZs only

#### Step 3 — Spot Advisor Filter
- Queries `spot_advisor_data` table for each pool's interruption frequency rank (1–5)
- **Rule: Eliminates pools with rank > 3** (more than 10% historical interruption rate)

#### Step 4 — Blacklist Check (System B Integration)
- Checks Redis set `risky_pools` for pools flagged by System B's termination detector
- **Does NOT eliminate** flagged pools — marks them for penalty in Step 7

#### Step 5 — Capacity Check
- Would call `ec2.describe_spot_price_history()` or `RunInstances --dry-run` to verify real-time capacity
- Currently assumes all pools have capacity (placeholder)

#### Step 6 — Price Fetch
- Calls AWS Pricing API to get current spot and on-demand prices for each remaining pool
- Calculates savings percentage: `(ondemand - spot) / ondemand`

#### Step 7 — ML Model Scoring (Core)
- For each pool:
  1. **Feature engineering** — `MLFeatureService.engineer_features()` creates **45 features** from `spot_price_history` data:
     - Price statistics: mean, std, min, max, range, coefficient of variation
     - Trend features: linear regression slope, direction
     - Volatility features: rolling std over 6h/12h/24h windows
     - Time features: hour_of_day, day_of_week, is_weekend (cyclical sin/cos encoding)
     - Spread features: spot-to-ondemand ratio, discount depth
  2. **ONNX classifier** (`classifier_6.onnx`) → predicts `savings_pct` (probability of maintaining savings)
  3. **ONNX regressor** (`regressor_6.onnx`) → predicts `cost_estimate` (expected hourly cost)
  4. **System B penalty** — if pool exists in Redis `risky_pools` set → applies `-0.50` penalty to savings_pct
  5. **Final score** = `(savings_pct × 100) - (cost_estimate × 0.1)` — higher is better
- If ONNX models unavailable → falls back to heuristic scoring using savings % and spot advisor rank

#### Step 8 — Final Ranking & Caching
- Sorts scored pools by `final_score` descending
- Assigns rank 1, 2, 3... to top N pools
- **Caches result in Redis** key `ml_rankings:*` with **30-second TTL**
- Returns top pools to frontend

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/atharvaai_routes.py` | Routes: rankings, termination/recent, rebalancing/trigger |
| `services/pool_ranking_service.py` | 8-step pipeline orchestrator, ONNX model loading, Redis caching |
| `services/ml_feature_service.py` | 45-feature extraction from spot_price_history |
| `services/resource_pricing_service.py` | AWS Pricing API data collection |

### DB Tables Used
`node_templates`, `spot_price_history`, `spot_advisor_data` + Redis: `ml_rankings:*`, `risky_pools`

### UI Components
`atharvaai/PoolRankings.jsx` (rankings table), `atharva/InterruptionHeatmap.jsx`, `atharva/RiskMonitor.jsx`, `atharva/RebalancingTimeline.jsx`, `store/useAtharvaStore.js` (Zustand)

---

## 9. Termination Detection & Auto-Rebalancing (System B)

### What This Feature Does
Monitors for EC2 spot termination notices in real-time (every 30 seconds), flags risky pools, and automatically migrates workloads to safer pools selected by System A.

### Step-by-Step Flow (Fully Automated — No User Action)

#### Termination Monitor Worker (every 30s)
1. Celery worker `termination_monitor.py` checks EC2 instance metadata for spot termination notices
2. When termination detected:
   - Creates `TerminationEvent` record (instance_type, AZ, timestamp, notice_time)
   - **Adds pool to Redis blacklist**: `SADD risky_pools "instance_type:az"` with metadata in `risky_pool_meta:<pool>` (12-hour TTL)
   - System A will penalize this pool in its next ranking cycle (Step 4 + Step 7 penalty)

#### Auto-Rebalancer Worker (every 15s)
1. Celery worker `auto_rebalancer.py` checks Redis `risky_pools`
2. For each flagged pool:
   1. **Cordons source node** — marks node as unschedulable (`kubectl cordon`)
   2. **Drains pods** — gracefully evicts all pods from the node (`kubectl drain --grace-period=30`)
   3. **Migrates to target pool** — uses System A's latest top-ranked pool as migration target
   4. **Creates `RebalancingAction` record** — logs source pool, target pool, pod count, duration
3. All moves recorded in `rebalancing_actions` table

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `workers/termination_monitor.py` | EC2 metadata polling, termination event recording, Redis blacklist |
| `workers/auto_rebalancer.py` | Pod migration orchestration, cordon/drain/migrate |

### DB Tables Used
`termination_events`, `rebalancing_actions`, `clusters` + Redis: `risky_pools`, `risky_pool_meta:*`

### UI Components
`atharva/InterruptionHeatmap.jsx` (AZ×hour heatmap), `atharva/RebalancingTimeline.jsx` (migration history)

---

## 10. Right-Sizing Recommendations

### What This Feature Does
Analyzes instance CPU/memory utilization and recommends downsizing or changing instance types to save costs.

### User Actions & Step-by-Step Flow

1. **User opens Right-Sizing page** for a cluster
2. **Frontend calls** `GET /api/v1/optimization/rightsizing/{clusterId}`
3. **Backend-side logic:**
   - Queries `instances` table for all instances in the cluster
   - For each instance: compares current `instance_type` against utilization data
   - Generates recommendations: "Change m5.xlarge → m5.large" with estimated monthly savings
4. **User clicks "Apply"** on a recommendation
5. `POST /api/v1/optimization/apply/{id}` → calls boto3 `modify_instance_attribute()` to change instance type (requires instance stop/start)

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/optimization_routes.py` | Routes: rightsizing analysis, apply recommendation |
| `services/rightsizing_service.py` | P95/P99 utilization analysis, recommendation engine |

### DB Tables Used
`instances`, `pod_metrics` (for P95/P99 analysis)

### UI Components
`right-sizing/RightSizing.jsx`

---

## 11. JIT Approval & Access Governance

### What This Feature Does
Just-In-Time (JIT) access control: users request time-limited elevated access, admins approve/reject, access automatically expires. Prevents standing privileges.

### User Actions & Step-by-Step Flow

#### Requesting Access
1. **User clicks a governance-protected button** (e.g., delete resource, connect account) → ProtectedButton detects insufficient permission
2. **JIT Request Modal** opens → user fills: scope (feature), reason category, reason text, duration (hours)
3. **Frontend calls** `POST /api/v1/approvals/jit-request`
4. **Backend creates** `Approval` record with `type=JIT_ACCESS`, `status=PENDING`, `jit_scope`, `duration_hours`

#### Admin Approving
1. **Admin sees pending request** on Approvals page → clicks "Approve"
2. `POST /api/v1/approvals/{id}/approve`
3. **Backend:**
   - Sets `status = APPROVED_ACTIVE`
   - Calculates `expires_at = now + duration_hours`
   - **SSE broadcast** notifies requesting user in real-time

#### Access Enforcement
- `GET /api/v1/approvals/check-permission` (called by `ProtectedButton` / `PermissionGate`)
- Backend checks: (1) Does user's role have the permission? (2) If not, is there an active JIT approval where `status = APPROVED_ACTIVE` AND `expires_at > now`?
- If yes → access granted. If no → shows lock icon / JIT request option

#### Access Expiry
- Active JIT window shows countdown timer (`ActiveJITBanner.jsx`)
- Admin can revoke early: `POST /api/v1/approvals/{id}/revoke` → sets `status = REVOKED`

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/approval_routes.py` | Routes: list, create, jit-request, approve, reject, revoke, active-window, my-jit-approvals |
| `services/approval_service.py` | JIT window management, SSE broadcasting, expiry calculation |
| `services/permission_service.py` | Permission resolution: role check + active JIT window check |

### DB Tables Used
`approvals` (user_id, type, status, jit_scope, duration_hours, expires_at, reason_category, reason_text)

### UI Components
`pages/Approvals.jsx`, `governance/JITRequestModal.jsx`, `governance/ProtectedButton.jsx`, `governance/PermissionGate.jsx`, `governance/ActiveJITBanner.jsx`

---

## 12. RBAC & Permission System

### What This Feature Does
Role-Based Access Control with 73+ granular permissions. Supports system roles (ORG_ADMIN, TEAM_LEAD, MEMBER) and custom roles.

### User Actions & Step-by-Step Flow

1. **Admin creates a custom role** — selects permissions from matrix → `POST /api/v1/roles` → creates `Role` with `type=CUSTOM`, links via `role_permissions` join table
2. **Admin assigns role to user** — `POST /api/v1/roles/assign` → updates `User.role_id`
3. **Permission enforcement** — every API call checks:
   - JWT middleware extracts user from token
   - `PermissionService.enforce(user, feature_id, resource_id)` → queries `roles → role_permissions → permissions` chain
   - If no direct permission → checks for active JIT approval window
   - If still denied → 403 Forbidden

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/role_routes.py` | Routes: CRUD roles, list permissions, assign role |
| `api/permission_routes.py` | Routes: check permissions, assign user permissions |
| `services/role_service.py` | Role CRUD, permission linking |
| `services/permission_service.py` | Permission resolution chain, JIT integration |

### DB Tables Used
`roles`, `permissions`, `role_permissions` (association), `user_permissions` (association), `users`

### UI Components
`pages/Roles.jsx` (role management), `policies/PermissionMatrix.jsx` (73+ permissions), `settings/MemberPermissionsModal.jsx`

---

## 13. Dashboard KPIs & Metrics

### What This Feature Does
Aggregates cost, savings, cluster, and instance data into dashboard widgets with time-series charts.

### User Actions & Step-by-Step Flow

1. **Dashboard page loads** → multiple parallel API calls:
   - `GET /api/v1/metrics/dashboard` → total cost (from `daily_costs`), total savings (from `clusters`), spot ratio (from `instances`), node count
   - `GET /api/v1/metrics/cost/timeseries` → daily costs over selected range for savings chart
   - `GET /api/v1/metrics/instances` → groups instances by lifecycle (SPOT/ON_DEMAND), calculates utilization averages for fleet composition widget
2. **Per-cluster detail** — `GET /api/v1/metrics/cluster/{id}` → monthly cost, savings, spot ratio, CPU utilization sparkline from `cluster_metrics`

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/metrics_routes.py` | Routes: dashboard KPIs, time-series cost data, cluster metrics, instance metrics |
| `services/metrics_service.py` | 53KB of aggregation logic — joins across `instances`, `clusters`, `daily_costs`, `cluster_metrics` |

### DB Tables Used
`instances`, `clusters`, `daily_costs`, `cluster_metrics`, `accounts`

### UI Components
`dashboard/widgets/CostKPICard.jsx`, `dashboard/widgets/SavingsChart.jsx`, `dashboard/widgets/FleetComposition.jsx`, `clusters/ClusterUtilizationSparkline.jsx`, `pages/AccountAnalytics.jsx`

---

## 14. Tag Governance & Bulk Tagging

### What This Feature Does
Enforces tagging policies across AWS resources, provides bulk-tagging wizard, manages reusable tag templates.

### User Actions & Step-by-Step Flow

#### Tag Policies
1. **Admin creates tag policy** — defines required tag key, enforcement level (WARN/BLOCK), allowed values
2. During cleanup scans, resources missing required tags are flagged as `is_compliant = False`

#### Bulk Tagging (from Cleanup Dashboard)
1. **User selects untagged resources** from cleanup results → opens BulkTagWizard
2. **Step 1**: Choose tag template (from `tag_templates`) or enter custom tags
3. **Step 2**: Review resources and tag preview
4. **Step 3**: Apply — `POST /api/v1/tags/resources/{type}/{id}/` → calls boto3 `create_tags()` on each selected resource, validates against tag policies

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/tag_policy_routes.py` | Policy CRUD |
| `api/tag_template_routes.py` | Template CRUD |
| `api/tag_management_routes.py` | Apply tags to AWS resources (boto3 create_tags) |
| `services/tag_policy_service.py` | Policy validation logic |
| `services/tag_management_service.py` | AWS resource tagging execution |

### DB Tables Used
`tag_policies`, `tag_templates`

### UI Components
`settings/TagPoliciesList.jsx`, `settings/TagTemplateManager.jsx`, `cleanup/BulkTagWizard.jsx`

---

## 15. Audit Logging

### What This Feature Does
Immutable, append-only audit trail of every significant action across the platform. Records who did what, when, from where, with before/after diffs.

### How It Works (Automatic — No User Action)
- Every CRUD action across the platform calls `audit_service.create_audit_log()` internally
- Records: `actor_id`, `actor_name`, `event` type, `resource` name, `resource_type`, `outcome` (SUCCESS/FAILURE), `ip_address`, `diff_before`, `diff_after`
- **Never deleted or modified** — append-only design

### User Actions
1. **View audit logs** — `GET /api/v1/audit/logs` with filters (date range, actor, event type, outcome, resource type) → paginated results
2. **Export logs** — `GET /api/v1/audit/export` → returns full filtered result set as JSON download

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/audit_routes.py` | Routes: list (paginated/filtered), export |
| `services/audit_service.py` | Append-only logging, query builder with filters |

### DB Tables Used
`audit_logs` (id, actor_id, actor_name, event, resource, resource_type, outcome, ip_address, diff_before, diff_after, created_at)

### UI Components
`audit/AuditLog.jsx`, `dashboard/widgets/ActivityFeed.jsx` (recent activity widget)

---

## 16. Admin Panel (Super Admin)

### What This Feature Does
Platform-wide management for super admins — view all organizations, users, clusters, and system health across the entire platform.

### User Actions & Step-by-Step Flow

1. **Admin navigates to Admin Panel** → loads Overview tab
   - `GET /api/v1/admin/dashboard-stats` → counts orgs, users, clusters platform-wide
2. **Clients tab** — `GET /api/v1/admin/clients` → lists all organizations with user counts, status, toggle active/inactive
3. **Health tab** — `GET /api/v1/admin/health` → pings DB connections, checks service status, returns uptime
4. **Billing tab** — `GET /api/v1/admin/billing` → currently returns hardcoded plan data (no real Stripe integration)
5. **Experiments tab** — `GET /api/v1/lab/experiments` → lists all lab experiments across all orgs

### Backend Files
| File | What It Does |
|:-----|:-------------|
| `api/admin_routes.py` | Routes: dashboard-stats, clients, health, billing, organizations, config |
| `services/admin_service.py` | Platform-wide queries, health checks |

### DB Tables Used
`organizations`, `users`, `clusters`

### UI Components
`admin/AdminDashboard.jsx` (tab navigation), `admin/AdminOverview.jsx`, `admin/AdminClients.jsx`, `admin/AdminHealth.jsx`, `admin/AdminBilling.jsx`, `admin/AdminExperiments.jsx`, `admin/AdminOrganizations.jsx`, `admin/AdminConfig.jsx`

---

## 17. Background Workers (Celery)

### What They Do
Automated tasks that run on schedules without user interaction.

| Worker | Schedule | What It Does | AWS APIs Used | DB Tables | Redis Keys |
|:-------|:---------|:-------------|:--------------|:----------|:-----------|
| **Cost Explorer Worker** | Every 6 hours | Fetches AWS Cost Explorer data via `ce.get_cost_and_usage()` → inserts daily cost records per service | `ce:GetCostAndUsage` | `daily_costs`, `cost_explorer_sync_status`, `accounts` | — |
| **Discovery Worker** | Every 30 min | Calls `eks.list_clusters()` and `eks.describe_cluster()` per linked account → creates/updates cluster and instance records | `eks:ListClusters`, `eks:DescribeCluster`, `ec2:DescribeInstances` | `clusters`, `instances`, `accounts` | — |
| **Termination Monitor** | Every 30 sec | Polls EC2 metadata for spot termination notices → records event, adds pool to Redis blacklist (12h TTL) | EC2 Instance Metadata | `termination_events` | `risky_pools`, `risky_pool_meta:*` |
| **Auto-Rebalancer** | Every 15 sec | Checks `risky_pools` → kubectl cordon/drain source node → migrate pods → record rebalancing action | — (Kubernetes API) | `rebalancing_actions`, `clusters` | `risky_pools` |
| **Spot Price Collector** | Every 10 min | Calls `ec2.describe_spot_price_history()` → inserts into rolling 144-point buffer per instance type per AZ | `ec2:DescribeSpotPriceHistory` | `spot_price_history` | — |
| **Pod Metrics Cleanup** | Daily | Deletes `pod_metrics` records older than 7 days | — | `pod_metrics` | — |
| **Hibernation Executor** | Every 1 min | Checks active schedules → converts UTC to schedule timezone → computes 168-cell index → executes sleep/wake actions per strategy | `eks:*` (for namespace/node operations) | `hibernation_schedules`, `clusters` | — |

---

**End of Backend Feature Flows**
