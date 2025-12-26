# Backend API Routes Module

## Purpose

RESTful API endpoints for all application features using FastAPI framework.

**Last Updated**: 2025-12-25 (Enhanced with comprehensive endpoint details)
**Authority Level**: HIGH

---

## API Files Overview

### Architecture
- **Framework**: FastAPI 0.95+
- **Router Pattern**: Each file defines a router with related endpoints
- **Authentication**: JWT Bearer tokens via `Depends(get_current_active_user)`
- **Request Validation**: Pydantic models
- **Response Format**: JSON with Pydantic schemas

---

## 1. client_routes.py ⭐ PRIMARY CLIENT API

**Purpose**: Main client dashboard and account management endpoints
**Lines**: ~460
**Router Prefix**: `/client`
**Tags**: `["client_dashboard"]`

### Endpoints:

#### GET /client/accounts
**Purpose**: List all connected AWS accounts for current user
**Authentication**: Required (JWT)
**Request**: None
**Response Model**: `List[AccountSummary]`
**Response Schema**:
```json
[
  {
    "id": "uuid-string",
    "account_id": "123456789012",
    "account_name": "Production AWS",
    "status": "active",
    "connection_method": "iam_role",
    "region": "us-east-1",
    "created_at": "2025-12-25T10:30:00Z",
    "updated_at": "2025-12-25T14:20:00Z"
  }
]
```
**Database Tables**: `accounts` (WHERE user_id = current_user.id)
**Frontend Components**:
- `ClientSetup.jsx` - `checkConnectedAccounts()` function
- `AuthGateway.jsx` - Account existence check

**Lines**: 41-81

---

#### DELETE /client/accounts/{account_id}
**Purpose**: Disconnect and delete AWS account
**Authentication**: Required (JWT)
**Status Code**: 200 (explicit, not 204) ⚠️ PROTECTED
**Path Parameters**:
- `account_id`: AWS Account ID (12 digits)

**Request**: None
**Response Schema**:
```json
{
  "success": true,
  "message": "AWS account disconnected successfully",
  "account_id": "123456789012"
}
```

**Security**:
- Ownership verification: `account.user_id == current_user.id`
- Cascade delete: Deletes all related instances first
- Returns HTTP 200 (NOT 204) to allow JSON response body

**Database Operations**:
1. Query `accounts` table (verify ownership)
2. Delete from `instances` table (WHERE account_id = account.id)
3. Delete from `accounts` table
4. Cascade: `experiment_logs`, `waste_resources` (via FK CASCADE)

**Frontend Components**:
- `ClientSetup.jsx` - `handleDisconnect()` function (line ~253)

**Protected Zone**: See `/progress/regression_guard.md#5`
**Fixed Issue**: P-2025-12-25-003 (HTTP 204 → 200)

**Lines**: 84-143

---

#### GET /client/dashboard
**Purpose**: Get dashboard metrics and summary
**Authentication**: Required (JWT)
**Query Parameters**:
- `account_id` (optional): Filter by specific account

**Response Schema**:
```json
{
  "total_cost": 1234.56,
  "instance_count": 23,
  "active_instances": 18,
  "stopped_instances": 5,
  "setup_required": false,
  "accounts": [
    {
      "account_id": "123456789012",
      "account_name": "Production",
      "status": "active",
      "instance_count": 15
    }
  ],
  "metrics": {
    "cpu_avg": 42.5,
    "memory_avg": 38.2,
    "cost_trend": [...]
  }
}
```

**Database Tables**:
- `accounts` (user's accounts)
- `instances` (aggregated metrics)
- `experiment_logs` (cost calculations)

**Frontend Components**:
- `ClientDashboard.jsx` - Main dashboard component

**Lines**: 147-457

---

#### GET /client/summary
**Purpose**: High-level account summary
**Authentication**: Required (JWT)

**Response Schema**:
```json
{
  "total_accounts": 3,
  "total_instances": 45,
  "total_monthly_cost": 3450.12,
  "accounts_by_status": {
    "active": 2,
    "connected": 1,
    "failed": 0
  }
}
```

**Database Tables**: `accounts`, `instances`

**Lines**: 459-531

---

#### GET /client/costs/export
**Purpose**: Export cost and savings data as CSV file (last 30 days)
**Authentication**: Required (JWT)
**Query Parameters**:
- `format` (default: "csv"): Export format

**Response Type**: StreamingResponse (text/csv)
**Response**: CSV file download with following columns:
```csv
Date,Instance ID,Instance Type,Availability Zone,Old Spot Price,New Spot Price,Hourly Savings,Monthly Projected,Decision,Reason
2025-12-26 10:30:00,i-abc123,t3.medium,us-east-1a,$0.0416,$0.0312,$0.0104,$7.59,SWITCH,Cost savings
...
TOTAL,,,,,,,$1234.56,,
```

**CSV Structure**:
- Header row with column names
- Data rows (one per experiment log entry from last 30 days)
- Summary row with total monthly projected savings
- Filename format: `cost_savings_export_YYYY-MM-DD.csv`

**Database Query**:
```sql
SELECT
  el.execution_time, i.instance_id, i.instance_type, i.availability_zone,
  el.old_spot_price, el.new_spot_price, el.projected_hourly_savings,
  el.decision, el.decision_reason
FROM experiment_logs el
JOIN instances i ON el.instance_id = i.id
WHERE i.account_id = <user's account>
  AND el.execution_time >= NOW() - INTERVAL '30 days'
  AND el.old_spot_price IS NOT NULL
  AND el.new_spot_price IS NOT NULL
ORDER BY el.execution_time DESC
```

**Database Tables**:
- `experiment_logs` (cost optimization data)
- `instances` (instance metadata)
- `accounts` (user account lookup)

**Frontend Components**:
- `NodeFleet.jsx` - Export CSV button (line ~584-601)
- `services/api.js` - `exportCostsCsv()` method (line ~150-185)

**Technical Details**:
- Uses FastAPI StreamingResponse for file download
- CSV generated in-memory using io.StringIO
- Monthly projected savings = hourly_savings × 730 hours
- Content-Disposition header sets download filename
- Handles missing cost data gracefully

**Lines**: 383-531

---

## 2. onboarding_routes.py ⭐ CRITICAL ONBOARDING

**Purpose**: AWS account connection workflows (CloudFormation + Credentials methods)
**Lines**: ~760
**Router Prefix**: `/client/onboarding`
**Tags**: `["onboarding"]`

### Endpoints:

#### POST /client/onboarding/create
**Purpose**: Create new onboarding request (Step 1)
**Authentication**: Required (JWT)
**Request**: None
**Response Schema**:
```json
{
  "id": "pending-abc123",
  "external_id": "random-uuid-for-security",
  "status": "pending"
}
```

**Database Operations**:
1. Create temporary record in `accounts` table
2. account_id = "pending-{random}"
3. status = "pending"
4. Generate secure external_id (UUID)

**Frontend Components**:
- `ClientSetup.jsx` - `createOnboardingRequest()` function (line ~38)

**Lines**: 40-92

---

#### POST /client/onboarding/connect/credentials
**Purpose**: Connect AWS account via Access Keys (Step 1 alternative)
**Authentication**: Required (JWT)
**Request Schema**:
```json
{
  "account_name": "Production AWS",
  "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
  "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
  "region": "us-east-1"
}
```

**Response Schema**:
```json
{
  "account_id": "123456789012",
  "status": "connected",
  "message": "AWS account connected successfully"
}
```

**Security**:
- Validates credentials via AWS STS GetCallerIdentity
- Encrypts credentials with AES-256 (Fernet) before storage
- **Global uniqueness check**: Prevents AWS account from being claimed by multiple users ⚠️ CRITICAL

**Database Operations**:
1. Call AWS STS to get account ID
2. Check if account_id exists for different user (security check)
3. Encrypt aws_access_key_id and aws_secret_access_key
4. Insert into `accounts` table with connection_method='access_keys'
5. Trigger background discovery worker

**Protected Zone**: See `/progress/regression_guard.md#2`
**Fixed Issue**: P-2025-12-25-001 (Account takeover vulnerability)

**Lines**: 94-272

---

#### GET /client/onboarding/template/{account_id}
**Purpose**: Generate CloudFormation template (Step 2)
**Authentication**: Required (JWT)
**Path Parameters**:
- `account_id`: Pending account ID from create endpoint

**Response Schema**:
```json
{
  "template": {
    "AWSTemplateFormatVersion": "2010-09-09",
    "Resources": {
      "SpotOptimizerRole": {
        "Type": "AWS::IAM::Role",
        "Properties": {
          "AssumeRolePolicyDocument": {...},
          "Policies": [...]
        }
      }
    },
    "Outputs": {
      "RoleARN": {
        "Value": {"Fn::GetAtt": ["SpotOptimizerRole", "Arn"]}
      }
    }
  }
}
```

**IAM Permissions Included**:
- ec2:DescribeInstances (read)
- ec2:DescribeInstanceTypes (read)
- ec2:StopInstances, ec2:StartInstances (write)
- cloudwatch:GetMetricStatistics (read)

**Frontend Components**:
- `ClientSetup.jsx` - `downloadTemplate()` function (line ~54)

**Lines**: 274-451

---

#### POST /client/onboarding/{account_id}/verify
**Purpose**: Verify CloudFormation deployment and assume role (Step 3)
**Authentication**: Required (JWT)
**Path Parameters**:
- `account_id`: Pending account ID

**Request Schema**:
```json
{
  "role_arn": "arn:aws:iam::123456789012:role/SpotOptimizerRole"
}
```

**Response Schema**:
```json
{
  "status": "connected",
  "account_id": "123456789012",
  "message": "Connection verified successfully"
}
```

**Process**:
1. Verify ownership of onboarding request
2. Call AWS STS AssumeRole with external_id
3. If successful:
   - Extract real AWS account ID from assumed role
   - **Global uniqueness check** (prevent account takeover)
   - Update account record: account_id, role_arn, status='connected'
   - Trigger background discovery worker
4. If failed: Return error with details

**Security**:
- External ID prevents confused deputy attack
- Global uniqueness prevents account takeover
- Role ARN validation

**Database Operations**:
1. Query `accounts` WHERE id = account_id AND user_id = current_user.id
2. Check `accounts` for existing account_id (security)
3. Update account record with role_arn and real account_id
4. Trigger `discovery_worker.py` in background

**Frontend Components**:
- `ClientSetup.jsx` - `verifyConnection()` function (line ~84)

**Protected Zone**: See `/progress/regression_guard.md#2`

**Lines**: 453-587

---

#### GET /client/onboarding/{account_id}/discovery
**Purpose**: Check discovery status (polling endpoint)
**Authentication**: Required (JWT)
**Path Parameters**:
- `account_id`: AWS Account ID

**Response Schema**:
```json
{
  "status": "active",
  "instances_discovered": 23,
  "discovery_progress": 100,
  "message": "Discovery complete"
}
```

**Frontend Components**:
- `ClientSetup.jsx` - `startPollingAccountStatus()` function (line ~162)
- Polls every 3 seconds until status='active'

**Lines**: 589-680

---

## 3. auth.py ⭐ PROTECTED - AUTHENTICATION

**Purpose**: User authentication and session management
**Lines**: ~200
**Router Prefix**: `/auth`
**Tags**: `["authentication"]`

### Endpoints:

#### POST /auth/login
**Purpose**: Authenticate user and generate JWT token
**Authentication**: None (public endpoint)
**Request Schema** (OAuth2PasswordRequestForm):
```json
{
  "username": "user@example.com",
  "password": "SecurePassword123"
}
```

**Response Schema**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "user@example.com",
    "email": "user@example.com",
    "role": "client"
  }
}
```

**Process**:
1. Query `users` table by username
2. Verify password hash with bcrypt
3. Generate JWT token (24-hour expiration) ⚠️ PROTECTED
4. Update last_login timestamp
5. Return token + user data

**Security**:
- Bcrypt password verification (12 rounds)
- JWT token with HS256 algorithm
- Token expiration: 24 hours (NEVER change without approval)

**Database Tables**: `users`

**Frontend Components**:
- Login.jsx (if exists)
- `services/api.js` - `login()` function

**Protected Zone**: See `/progress/regression_guard.md#1`
**Fixed Issue**: Token expiration was 5 minutes, now 24 hours

---

## 4. Other API Files (Summary)

### lab.py - ML EXPERIMENT TRACKING
**Lines**: ~900 | **Prefix**: `/lab`
- GET /lab/experiments - List experiments
- POST /lab/experiments - Create experiment
- GET /lab/models - List ML models
- POST /lab/models/{id}/promote - Promote model

**Database**: `experiment_logs`, `ml_models`, `instances`

---

### admin.py - ADMIN DASHBOARD
**Lines**: ~800 | **Prefix**: `/admin`
- GET /admin/users - List all users (admin only)
- GET /admin/system-health - System health
- POST /admin/users/{id}/toggle-active - Enable/disable user

**Database**: `users`, `component_health`, `system_logs`

---

### metrics_routes.py - METRICS
**Lines**: ~500 | **Prefix**: `/metrics`
- GET /metrics/instance/{id} - CloudWatch metrics
- GET /metrics/account/{id} - Account aggregated metrics

**AWS API**: CloudWatch GetMetricStatistics

---

### ai_routes.py - ML PREDICTIONS
**Lines**: ~530 | **Prefix**: `/ai`
- POST /ai/predict - Get ML prediction
- GET /ai/recommendations - Optimization recommendations

---

### governance_routes.py - MODEL GOVERNANCE
**Lines**: ~320 | **Prefix**: `/governance`
- GET /governance/models - Model lifecycle status

---

### waste_routes.py - WASTE DETECTION
**Lines**: ~120 | **Prefix**: `/waste`
- GET /waste/resources - List wasted resources

**Database**: `waste_resources`

---

### pipeline_routes.py - OPTIMIZATION
**Lines**: ~170 | **Prefix**: `/pipeline`
- POST /pipeline/optimize - Trigger optimization

---

### storage_routes.py - STORAGE MANAGEMENT
**Lines**: ~200 | **Prefix**: `/storage`
- EBS volume and snapshot management

---

### approval_routes.py - ACTION APPROVALS
**Lines**: ~190 | **Prefix**: `/approval`
- Approval workflow for risky actions

---

### websocket_routes.py - REAL-TIME
**Lines**: ~60 | **Route**: `/ws/{client_id}`
- WebSocket connections for live updates

---

## Dependencies

### Depends On:
- FastAPI framework
- Pydantic (validation)
- `backend/database/models.py` (all models)
- `backend/auth/dependencies.py` (authentication)
- `backend/workers/discovery_worker.py` (background tasks)
- `backend/utils/crypto.py` (encryption)
- boto3 (AWS SDK)

### Depended By:
- **CRITICAL**: All frontend components
- `frontend/src/services/api.js`

**Impact Radius**: CRITICAL (entire API surface)

---

## Recent Changes

### 2025-12-25: Comprehensive Enhancement
**Reason**: Added actual endpoint details, schemas, database connections, frontend mappings
**Impact**: Complete API documentation
**Reference**: Smart repository enhancement

### 2025-12-25: P-2025-12-25-003 Fix
**Files**: client_routes.py (line 84)
**Change**: DELETE status_code 204 → 200
**Reference**: `/progress/fixed_issues_log.md`

### 2025-12-25: P-2025-12-25-001 Fix
**Files**: onboarding_routes.py
**Change**: Global uniqueness check
**Reference**: `/progress/regression_guard.md#2`

---

_Last Updated: 2025-12-25 (Enhanced)_
_Authority: HIGH - Complete API reference_
