# API Usage Matrix & Reference
**Last Updated:** 2026-01-19
# 📡 API Information & Usage Guide
**Last Updated:** 2026-01-20
**Purpose:** Complete reference for all backend API endpoints with request/response examples.

---

## Authentication

All endpoints except `/auth/*` and `/health` require JWT token:

```bash
Authorization: Bearer <jwt_token>
```

---

## Cost Analysis APIs (Production-Grade)

### S3 Storage Optimization

#### GET /api/v1/s3/overview
**Purpose:** Get S3 optimization summary

**Response:**
```json
{
  "total_buckets": 45,
  "buckets_needs_optimization": 12,
  "total_estimated_savings": 2847.50,
  "buckets_no_lifecycle": 8
}
```

#### POST /api/v1/s3/analyze  
**Purpose:** Trigger S3 analysis (Storage Lens + dynamic pricing)

**Features:**
- Uses S3 Storage Lens API (scalable to billions of objects)
- Falls back to CloudWatch if Storage Lens unavailable
- Dynamic regional pricing via AWS Price List API

**Response:**
```json
{
  "buckets_analyzed": 45,
  "total_estimated_savings": 2847.50,
  "details": [
    {
      "bucket_name": "my-bucket",
      "analysis_method": "storage_lens",
      "pricing_source": "price_list_api",
      "monthly_cost": 234.50,
      "estimated_savings": 140.70
    }
  ]
}
```

---

### Data Transfer Analysis

#### GET /api/v1/transfer/overview
**Purpose:** Get transfer cost summary

**Response:**
```json
{
  "total_monthly_transfer_cost": 1250.00,
  "total_estimated_savings": 187.50,
  "top_opportunities": [...]
}
```

#### POST /api/v1/transfer/analyze?lookback_days=30
**Purpose:** Analyze data transfer costs with configurable period

**Query Parameters:**
- `lookback_days` (integer, 7-90, default: 30): Analysis period

**Lookback Period Guide:**
- **7 days**: Quick recent snapshot
- **30 days**: Standard monthly analysis (recommended)
- **90 days**: Quarterly trend (most reliable for decisions)

**Features:**
- Granular traffic categorization (internet_egress, inter_az, inter_region, nat_gateway)
- Actual Cost Explorer costs (no hardcoded estimates)
- Conservative, realistic savings projections

**Response:**
```json
{
  "items_analyzed": 5,
  "lookback_days": 30,
  "total_estimated_savings": 187.50,
  "details": [
    {
      "transfer_type": "NAT Gateway Data Processing",
      "traffic_direction": "nat_gateway",
      "monthly_cost": 450.00,
      "estimated_savings": 135.00,
      "recommendation": "use_vpc_endpoint"
    }
  ]
}
```

---

### Reserved Instances & Savings Plans

#### GET /api/v1/ri/overview
**Purpose:** Get RI health summary

**Response:**
```json
{
  "total_ris": 24,
  "underutilized_count": 6,
  "wasted_spend_monthly": 1840.00,
  "health_status": "warning"
}
```

#### POST /api/v1/ri/analyze?lookback_days=30
**Purpose:** Analyze RI utilization with configurable lookback

**Query Parameters:**
- `lookback_days` (integer, 7-90, default: 30): Analysis period

**Features:**
- Configurable lookback for reliable analysis
- Recommendations prioritize Savings Plans migration
- Modern AWS best practices

**Response:**
```json
{
  "status": "success",
  "lookback_days": 30,
  "summary": {
    "total_ris": 24,
    "underutilized_count": 6,
    "monthly_waste": 1840.00,
    "annual_waste": 22080.00
  }
}
```

#### GET /api/v1/ri/savings-plans/overview
**Purpose:** Get Savings Plans health summary

**Response:**
```json
{
  "total_plans": 8,
  "underutilized_count": 2,
  "total_monthly_commitment": 5000.00,
  "wasted_spend_monthly": 450.00,
  "actual_savings_monthly": 3200.00,
  "avg_coverage_percentage": 78.5,
  "health_status": "good"
}
```

#### POST /api/v1/ri/savings-plans/analyze?lookback_days=30
**Purpose:** Analyze Savings Plans utilization

**Query Parameters:**
- `lookback_days` (integer, 7-90, default: 30): Analysis period

**Features:**
- Modern alternative to Reserved Instances
- More flexible coverage across services/regions
- Actual savings tracking from Cost Explorer

**Response:**
```json
{
  "status": "success",
  "lookback_days": 30,
  "summary": {
    "total_plans": 8,
    "underutilized_count": 2,
    "monthly_waste": 450.00,
    "actual_savings": 3200.00
  }
}
```

#### GET /api/v1/ri/unified-coverage
**Purpose:** Combined RI + Savings Plans coverage report

**Features:**
- Prevents double-counting commitments
- Shows total organizational coverage
- Aggregated health status

**Response:**
```json
{
  "reserved_instances": {
    "count": 24,
    "underutilized": 6,
    "monthly_waste": 1840.00
  },
  "savings_plans": {
    "count": 8,
    "underutilized": 2,
    "monthly_waste": 450.00,
    "actual_savings": 3200.00
  },
  "unified": {
    "total_monthly_commitment": 10000.00,
    "total_monthly_waste": 2290.00,
    "coverage_percentage": 78.5,
    "health_status": "warning"
  }
}
```

---

## Implementation Notes

### Pricing Cache
- All pricing data cached in Redis for 24 hours
- First request per region: ~500ms (API call)
- Subsequent requests: ~5ms (Redis hit)
- TTL configurable via `PRICING_CACHE_TTL` env var

### IAM Permissions Required
```json
{
  "Effect": "Allow",
  "Action": [
    "pricing:GetProducts",
    "s3:ListStorageLensConfigurations",
    "ce:GetSavingsPlansUtilization",
    "ce:GetSavingsPlansCoverage"
  ],
  "Resource": "*"
}
```

### Best Practices
- Use 30-day lookback for standard analysis
- Use 90-day lookback for financial planning decisions
- Enable S3 Storage Lens for optimal bucket analysis
- Check Savings Plans coverage before buying new RIs

---

## 1. Authentication & Users

| API Endpoint | Frontend Component | Backend Service | Functionality & Logic | Scenario |
|:--- |:--- |:--- |:--- |:--- |
| `POST /api/v1/auth/signup` | `Signup.jsx` (`authAPI.signup`) | `AuthService` | **Logic**: Validates inputs, hashes password (bcrypt), creates atomic `User` + `Organization`, returns JWT. | **Registration**: New user signs up for the platform. |
| `POST /api/v1/auth/login` | `Login.jsx` (`authAPI.login`) | `AuthService` | **Logic**: Verifies credentials, checks suspension status, issues Access/Refresh tokens. | **Login**: User accesses the dashboard. |
| `POST /api/v1/auth/refresh` | `api.js` (Interceptor) | `AuthService` | **Logic**: Rotates Access Token using valid Refresh Token. Blacklists old token. | **Session**: Silent token refresh to keep user logged in. |
| `GET /api/v1/auth/me` | `useAuth.js` (`authAPI.me`) | `AuthService` | **Logic**: Decodes JWT, fetches full `User` context with Org and Permissions. | **App Load**: Restoring user session on page refresh. |
| `POST /api/v1/auth/invitation-response`| `InviteAcceptance.jsx` | `AuthService` | **Logic**: Transitions User from `PENDING_INVITE` to `ACTIVE` (or deletes if declined). | **Onboarding**: Invited team member accepts their invite. |
| `PATCH /api/v1/users/me` | `UserProfile.jsx` | `UserService` | **Logic**: Updates mutable profile fields (Name, Phone). | **Profile**: User updating their display name. |
| `GET /api/v1/users/me/preferences` | `Dashboard.jsx` | `UserService` | **Logic**: Retrieves JSON widget layout preferences. Falls back to Role Defaults. | **Dashboard**: Loading user's custom dashboard layout. |
| `PATCH /api/v1/users/me/preferences`| `Dashboard.jsx` | `UserService` | **Logic**: Validates and persists JSON widget layout. | **Dashboard**: User saves a new widget arrangement. |

## 2. Organization & Teams

| API Endpoint | Frontend Component | Backend Service | Functionality & Logic | Scenario |
|:--- |:--- |:--- |:--- |:--- |
| `GET /api/v1/organization/members` | `TeamManagement.jsx` | `OrganizationService`| **Logic**: Lists all Org members with Account/Team counts. Admin only. | **Admin**: Viewing user directory. |
| `POST /api/v1/organization/members` | `TeamManagement.jsx` | `OrganizationService`| **Logic**: Creates `User` (Status=PENDING), sends email. | **Invite**: Admin inviting a colleague. |
| `PATCH /api/v1/organization/members/{id}`| `TeamManagement.jsx` | `OrganizationService`| **Logic**: Updates Member Role/Access Level. Enforces hierarchy safety. | **Admin**: Promoting a user to Team Lead. |
| `DELETE /api/v1/organization/members/{id}`| `TeamManagement.jsx`| `OrganizationService`| **Logic**: Soft deletes user, kills active sessions. | **Admin**: Removing a user who left the company. |
| `GET /api/v1/teams/` | `TeamManagement.jsx` | `TeamService` | **Logic**: Lists Teams. Filter: Admin=All, Lead=Owned. | **Teams**: Viewing team hierarchy. |
| `POST /api/v1/teams/` | `TeamManagement.jsx` | `TeamService` | **Logic**: Creates new Team with default Governance. | **Teams**: Creating a "Backend Engineering" team. |
| `POST /api/v1/teams/{id}/assign` | `TeamManagement.jsx` | `TeamService` | **Logic**: Moves existing User to Team. | **Teams**: Assigning a user to a team. |
| `POST /api/v1/teams/{id}/invite` | `TeamManagement.jsx` | `TeamService` | **Logic**: Creates + Assigns User in one step. | **Teams**: Direct invite to specific team. |
| `PUT /api/v1/teams/{id}/governance` | `TeamGovernance.jsx` | `TeamService` | **Logic**: Updates `governance_config` JSON (Budget, Allowed Actions). | **Policy**: Restricting a team's ability to delete RDS. |

## 3. Infrastructure & Onboarding

| API Endpoint | Frontend Component | Backend Service | Functionality & Logic | Scenario |
|:--- |:--- |:--- |:--- |:--- |
| `GET /api/v1/accounts` | `FilterPanel.jsx` | `AccountService` | **Logic**: Lists connected AWS Accounts. Filter by User Access. | **Filter**: Selecting an account to inspect. |
| `POST /api/v1/onboarding/verify` | `ConnectStep.jsx` | `AccountService` | **Logic**: STS AssumeRole check. Triggers Discovery Scan. Creates `Account`. | **Connect**: Linking a new AWS account. |
| `GET /api/v1/onboarding/aws-link` | `ConnectStep.jsx` | `TemplateService` | **Logic**: Generates CloudFormation URL with ExtID. | **Connect**: Redirecting to AWS Console. |
| `POST /api/v1/accounts/{id}/approve`| `CloudIntegrations.jsx`| `AccountService` | **Logic**: Admin approves Member's link request. Decrypts creds. | **Approval**: Admin finalizing an account connection. |
| `POST /api/v1/accounts/{id}/disconnect`| `CloudIntegrations.jsx`| `AccountService` | **Logic**: Deletes Role ARN, keeps historical data. | **Disconnect**: Removing AWS access safely. |

## 4. Resource Hygiene (Cleanup)

| API Endpoint | Frontend Component | Backend Service | Functionality & Logic | Scenario |
|:--- |:--- |:--- |:--- |:--- |
| `GET /api/v1/cleanup/scan/{account}` | `CleanupDashboard.jsx` | `CleanupService` | **Logic**: Parallel Scan (EC2, EBS, S3, RDS). Checks Cache. | **Scan**: User viewing wasted resources. |
| `POST /api/v1/cleanup/action` | `ResourceTable.jsx` | `CleanupService` | **Logic**: JIT Permission Check. Executes Boto3 Terminate/Delete. | **Action**: User deleting an unattached volume. |
| `GET /api/v1/cleanup/check-dependencies`| `ResourceTable.jsx` | `CleanupService` | **Logic**: Checks for attached dependencies (e.g. Snapshot -> AMI). | **Safety**: Pre-flight check before deletion. |
| `POST /api/v1/cleanup/discover` | `TicketRequestModal.jsx` | `CleanupService` | **Logic**: Real-time AWS List call for Resource ID picker. | **JIT**: Searching for an instance to access. |

## 5. Governance & JIT Access

| API Endpoint | Frontend Component | Backend Service | Functionality & Logic | Scenario |
|:--- |:--- |:--- |:--- |:--- |
| `POST /api/v1/tickets/` | `TicketRequestModal.jsx` | `TicketService` | **Logic**: Creates PENDING ticket. Notifies Approvers. | **Request**: Member asking for SSH access. |
| `GET /api/v1/tickets/` | `TicketCenter.jsx` | `TicketService` | **Logic**: Lists tickets. filtered by Role (Requester vs Approver). | **Review**: Lead checking request queue. |
| `POST /api/v1/tickets/{id}/approve` | `TicketCenter.jsx` | `TicketService` | **Logic**: Sets ACTIVE status, expiry time. Grants Permissions. | **Grant**: Lead approving access. |
| `POST /api/v1/tickets/{id}/revoke` | `TicketCenter.jsx` | `TicketService` | **Logic**: Immediately revokes access/ticket. | **Revoke**: Admin cancelling access early. |
| `GET /api/v1/tickets/active-window` | `ActiveWindowBanner.jsx`| `TicketService` | **Logic**: checks for currently valid JIT grant. | **Banner**: Displaying time remaining. |
| `GET /api/v1/approvals/pending` | `ApprovalCenter.jsx` | `ApprovalService`| **Logic**: Lists Cleanup/Action requests requiring "Four-Eyes". | **Review**: Reviewing "Delete Database" requests. |
| `POST /api/v1/approvals/{id}/approve`| `ApprovalCenter.jsx` | `ApprovalService`| **Logic**: Executes the deferred serialized action. | **Execute**: Approving the deletion. |

## 6. Metrics & Analytics

| API Endpoint | Frontend Component | Backend Service | Functionality & Logic | Scenario |
|:--- |:--- |:--- |:--- |:--- |
| `GET /api/v1/metrics/dashboard` | `Dashboard.jsx` | `MetricsService` | **Logic**: Aggregates KPIs (Cost, Savings, Resource Counts). | **Dash**: Main KPI display. |
| `GET /api/v1/metrics/cost/timeseries`| `SavingsChart.jsx` | `MetricsService` | **Logic**: Daily/Weekly cost aggregation for charts. | **Chart**: Visualizing spend trends. |
| `GET /api/v1/metrics/teams/{id}/summary`| `TeamDetails.jsx` | `MetricsService` | **Logic**: Team-scoped cost aggregation. | **Team**: Viewing specific team's impact. |
| `GET /api/v1/optimization/rightsizing/{id}`| `RightSizing.jsx` | `RightSizer` | **Logic**: Analyzes CPU/Mem history vs Instance Type. | **Optimize**: Recommendations to downsize. |

## 7. Cost Optimization Details

| API Endpoint | Frontend Component | Backend Service | Functionality & Logic | Scenario |
|:--- |:--- |:--- |:--- |:--- |
| `GET /api/v1/ri/analysis` | `RIAnalysis.jsx` | `RIService` | **Logic**: Calculates RI Coverage & Utilization. | **RI**: Checking reserved instance usage. |
| `GET /api/v1/s3/analysis` | `S3Analysis.jsx` | `S3Service` | **Logic**: Scans for Intelligent Tiering opportunities. | **Storage**: optimizing S3 costs. |
| `GET /api/v1/rds/analysis` | `RDSAnalysis.jsx` | `RDSService` | **Logic**: Checks for Single-AZ Dev instances / Idle DBs. | **Database**: Optimizing RDS usage. |
| `GET /api/v1/transfer/analysis` | `TransferAnalysis.jsx`| `TransferService`| **Logic**: Analyzes Cross-AZ/Region Data Transfer costs. | **Network**: Reducing data transfer fees. |

## 8. Admin & System

| API Endpoint | Frontend Component | Backend Service | Functionality & Logic | Scenario |
|:--- |:--- |:--- |:--- |:--- |
| `GET /api/v1/admin/dashboard` | `AdminOverview.jsx` | `AdminService` | **Logic**: Global Platform Stats (MRR, Total Users). | **Super Admin**: Platform oversight. |
| `GET /api/v1/admin/organizations` | `AdminOrganizations.jsx`| `AdminService` | **Logic**: Lists all Tenant Organizations. | **Super Admin**: Managing tenants. |
| `POST /api/v1/admin/organizations/{id}/toggle`| `AdminOrganizations.jsx`| `AdminService` | **Logic**: Suspends/Activates a Tenant. | **Super Admin**: Banning a tenant. |
| `GET /api/v1/health/system` | `AdminHealth.jsx` | `HealthService` | **Logic**: Checks Redis/DB/Celery connectivity. | **Monitor**: System health check. |
| `POST /api/v1/admin/platform/connect`| `PlatformSettings.jsx`| `AdminService` | **Logic**: Connects the Hosting/Platform-own AWS account. | **Setup**: Initial platform configuration. |

## 9. Clusters & Workloads

| API Endpoint | Frontend Component | Backend Service | Functionality & Logic | Scenario |
|:--- |:--- |:--- |:--- |:--- |
| `GET /api/v1/clusters` | `ClusterList.jsx` | `ClusterService` | **Logic**: Lists K8s Clusters + Agent Status. | **K8s**: Viewing managed clusters. |
| `POST /api/v1/clusters/connect-aws` | `ClusterConnectModal.jsx`| `ClusterService` | **Logic**: Registers Cluster via AWS API (No Agent). | **K8s**: Importing a cluster. |
| `POST /api/v1/clusters/install-script`| `ClusterConnectModal.jsx`| `ClusterService` | **Logic**: Generates Helm Upgrade command with unique API key. | **K8s**: Installing Agent. |
| `GET /api/v1/hibernation/schedule/{id}`| `HibernationSchedule.jsx`| `HibernationService`| **Logic**: Returns 24x7 CRON schedule matrix. | **Hibernate**: Viewing sleep schedules. |

## 10. Templates & Policies

| API Endpoint | Frontend Component | Backend Service | Functionality & Logic | Scenario |
|:--- |:--- |:--- |:--- |:--- |
| `GET /api/v1/templates` | `TemplateList.jsx` | `TemplateService` | **Logic**: Lists saved Node Templates. | **Templates**: Managing instance specs. |
| `GET /api/v1/templates/options` | `TemplateBuilder.jsx` | `TemplateService` | **Logic**: Returns available Instance Families/Sizes. | **Builder**: Populating dropdowns. |
| `GET /api/v1/policies` | `PolicyConfig.jsx` | `PolicyService` | **Logic**: Lists Optimization Policies. | **Policy**: Viewing global settings. |

## 11. Lab & Experiments

| API Endpoint | Frontend Component | Backend Service | Functionality & Logic | Scenario |
|:--- |:--- |:--- |:--- |:--- |
| `GET /api/v1/lab/experiments` | `ExperimentLab.jsx` | `LabService` | **Logic**: List A/B tests and results. | **Dev**: Checking experiment data. |
| `POST /api/v1/lab/experiments` | `ExperimentLab.jsx` | `LabService` | **Logic**: Create new optimization experiment. | **Dev**: Starting a new test. |

## 12. Settings

| API Endpoint | Frontend Component | Backend Service | Functionality & Logic | Scenario |
|:--- |:--- |:--- |:--- |:--- |
| `GET /api/v1/settings/integrations` | `IntegrationSettings.jsx`| `SettingsService` | **Logic**: Lists Slack/PagerDuty webhooks. | **Settings**: Managing alerts. |
| `POST /api/v1/settings/integrations`| `IntegrationSettings.jsx`| `SettingsService` | **Logic**: Adds a new webhook integration. | **Settings**: Adding a Slack channel. |