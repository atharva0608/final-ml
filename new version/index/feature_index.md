# Feature Index

## Purpose

Complete catalog of all features, their locations, and dependencies.

**Last Updated**: 2025-12-25

---

## Authentication & Authorization

### User Authentication

**Module**: `backend/api/auth.py`
**Added**: Initial release

**API Endpoints**:
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `GET /api/auth/me` - Get current user

**Database Tables**:
- `users`

**Frontend Components**:
- `LoginPage.jsx`
- `AuthContext.jsx`

**Dependencies**:
- Requires: Database, JWT library
- Required by: All protected routes

**Scenario**: `/scenarios/auth_flow.md`

**Key Functions**:
- `create_access_token()` - backend/api/auth.py:45
- `get_current_active_user()` - backend/api/auth.py:67

---

## AWS Account Management

### Multi-Account Support

**Module**: `backend/api/client_routes.py`, `frontend/src/components/ClientSetup.jsx`
**Added**: 2025-12-25

**API Endpoints**:
- `GET /client/accounts` - List connected accounts
- `DELETE /client/accounts/{account_id}` - Disconnect account

**Database Tables**:
- `accounts`
- `instances` (cascade delete)

**Frontend Components**:
- `ClientSetup.jsx` - Account list & connection UI
- `AuthGateway.jsx` - Routing based on account status

**Dependencies**:
- Requires: Authentication, Database
- Required by: Client Dashboard, Discovery Worker

**Scenario**: `/scenarios/account_management_flow.md`

**Key Functions**:
- `get_connected_accounts()` - backend/api/client_routes.py:42
- `disconnect_account()` - backend/api/client_routes.py:85
- `checkConnectedAccounts()` - frontend/src/components/ClientSetup.jsx:218

**Business Logic**:
- Users can connect multiple AWS accounts
- Global uniqueness check prevents duplicate claims
- Deletion cascades to related instances

**Security**:
- Ownership verification on all operations
- HTTP 409 Conflict if account belongs to different user

---

## AWS Account Onboarding

### CloudFormation Connection

**Module**: `backend/api/onboarding_routes.py`
**Added**: Initial release
**Updated**: 2025-12-25 (added uniqueness check)

**API Endpoints**:
- `POST /onboarding/create` - Create onboarding request
- `GET /onboarding/template/{account_id}` - Get CloudFormation template
- `POST /onboarding/{account_id}/verify` - Verify IAM role connection

**Database Tables**:
- `accounts`

**Frontend Components**:
- `ClientSetup.jsx` (CloudFormation tab)

**Dependencies**:
- Requires: AWS STS, Database
- Required by: Discovery Worker

**Scenario**: `/scenarios/client_onboarding_flow.md#cloudformation`

**Key Functions**:
- `create_onboarding_request()` - backend/api/onboarding_routes.py:41
- `get_cloudformation_template()` - backend/api/onboarding_routes.py:274
- `verify_connection()` - backend/api/onboarding_routes.py:453

**Business Logic**:
- Generates unique External ID
- Creates CloudFormation template with IAM role
- Verifies role assumption via AWS STS
- Triggers background discovery on success

### Access Keys Connection

**Module**: `backend/api/onboarding_routes.py`
**Added**: Initial release
**Updated**: 2025-12-25 (added uniqueness check)

**API Endpoints**:
- `POST /onboarding/connect/credentials` - Connect with access keys

**Database Tables**:
- `accounts` (encrypted credentials)

**Frontend Components**:
- `ClientSetup.jsx` (Credentials tab)

**Dependencies**:
- Requires: AWS STS, Encryption utility, Database
- Required by: Discovery Worker

**Scenario**: `/scenarios/client_onboarding_flow.md#credentials`

**Key Functions**:
- `connect_with_credentials()` - backend/api/onboarding_routes.py:94

**Business Logic**:
- Validates credentials with AWS STS GetCallerIdentity
- Encrypts credentials before storage (AES-256)
- Supports UPSERT for re-connections
- Triggers background discovery on success

**Security**:
- Credentials encrypted at rest
- Global uniqueness check for AWS Account IDs
- Never exposes decrypted credentials to frontend

---

## Resource Discovery

### EC2 Instance Discovery

**Module**: `backend/workers/discovery_worker.py`
**Added**: Initial release
**Updated**: 2025-12-25 (added health check trigger)

**Background Tasks**:
- `run_initial_discovery()` - Full account scan
- `trigger_rediscovery()` - Refresh existing account

**Database Tables**:
- `accounts` (status updates)
- `instances` (discovered resources)

**Dependencies**:
- Requires: AWS EC2 API, Database, Encryption (for access keys)
- Required by: Client Dashboard

**Scenario**: `/scenarios/resource_discovery_flow.md`

**Key Functions**:
- `scan_ec2_instances()` - backend/workers/discovery_worker.py:122
- `get_session_for_account()` - backend/workers/discovery_worker.py:67

**Business Logic**:
- Assumes IAM role or uses encrypted access keys
- Scans EC2 instances in configured regions
- Identifies clusters from tags
- Updates account status: connected → active
- Triggers immediate health checks

**Status Transitions**:
- `pending` → `connected` (after credential validation)
- `connected` → `active` (after successful discovery)
- `connected` → `failed` (if discovery errors)

---

## Client Dashboard

### Dashboard Data Aggregation

**Module**: `backend/api/client_routes.py`
**Added**: Initial release
**Updated**: 2025-12-25 (added setup_required flag)

**API Endpoints**:
- `GET /client/dashboard` - Get dashboard data
- `GET /client/summary` - Lightweight summary

**Database Tables**:
- `accounts`
- `instances`
- `experiment_logs`
- `downtime_logs`

**Frontend Components**:
- `DashboardLayout.jsx`
- `NodeFleet.jsx`

**Dependencies**:
- Requires: Authentication, Account Management
- Required by: Client UI

**Scenario**: `/scenarios/client_dashboard_flow.md`

**Key Functions**:
- `get_client_dashboard()` - backend/api/client_routes.py:147

**Business Logic**:
- Returns `setup_required: true` if no accounts
- Shows discovery progress for connected accounts
- Aggregates instance counts, savings, SLA metrics
- Supports multiple account scenarios

**Empty States**:
- No account: setup_required = true
- Pending: Shows progress
- Connected: Shows "Discovering..."
- Active: Shows full dashboard

---

## Data Export & Reporting

### CSV Cost Export

**Module**: `backend/api/client_routes.py`, `frontend/src/components/NodeFleet.jsx`
**Added**: 2025-12-26

**API Endpoints**:
- `GET /client/costs/export?format=csv` - Export cost data as CSV file

**Database Tables**:
- `experiment_logs` (cost optimization data)
- `instances` (instance metadata)
- `accounts` (user account lookup)

**Frontend Components**:
- `NodeFleet.jsx` - Export CSV button (line ~584-601)
- `services/api.js` - exportCostsCsv() method (line ~150-185)

**Dependencies**:
- Requires: Authentication, Account Management, Cost Data
- Required by: Financial reporting, external analysis

**Scenario**: None (straightforward feature)

**Key Functions**:
- `export_costs_csv()` - backend/api/client_routes.py:383
- `exportCostsCsv()` - frontend/src/services/api.js:150
- Export button onClick handler - frontend/src/components/NodeFleet.jsx:584

**Business Logic**:
- Queries last 30 days of cost optimization data
- Joins experiment_logs with instances table
- Calculates monthly projected savings (hourly × 730 hours)
- Generates CSV in-memory using io.StringIO
- Returns StreamingResponse with downloadable file
- Includes summary row with total savings

**CSV Structure**:
```csv
Date,Instance ID,Instance Type,Availability Zone,Old Spot Price,New Spot Price,Hourly Savings,Monthly Projected,Decision,Reason
2025-12-26 10:30:00,i-abc123,t3.medium,us-east-1a,$0.0416,$0.0312,$0.0104,$7.59,SWITCH,Cost savings
...
TOTAL,,,,,,,$1234.56,,
```

**File Download**:
- Browser-side blob creation and download
- Filename from Content-Disposition header
- Default format: `cost_savings_export_YYYY-MM-DD.csv`
- Automatic cleanup of object URLs

**Security**:
- Requires JWT authentication
- Only exports data for current user's accounts
- Backend validates ownership via account_id filter

**Use Cases**:
- Financial reporting and audit trails
- External analysis in Excel/Google Sheets
- Historical cost tracking
- Budget planning and forecasting

---

## Health Monitoring

### Component Health Checks

**Module**: `backend/utils/component_health_checks.py`, `backend/workers/health_monitor.py`
**Added**: Initial release
**Updated**: 2025-12-25 (triggered after discovery)

**Components Monitored**:
- Database latency
- Redis queue depth (if enabled)
- K8s watcher heartbeat (if enabled)
- Optimizer last run
- Price scraper freshness
- Risk engine data age
- ML inference model status

**API Endpoints**:
- `GET /api/health` (implied)

**Dependencies**:
- Requires: Database, System logs
- Required by: Monitoring, SLA tracking

**Key Functions**:
- `run_all_health_checks()` - backend/utils/component_health_checks.py:437

**Business Logic**:
- Runs every 30 seconds (monitor loop)
- Tracks state transitions (healthy → degraded → critical)
- Auto-captures diagnostic context on degradation
- Now triggered immediately after discovery completes

---

## Frontend Routing

### AuthGateway (Smart Routing)

**Module**: `frontend/src/components/AuthGateway.jsx`
**Added**: 2025-12-25

**Routes**:
- Checks `/client/accounts` on mount
- Redirects to `/onboarding/setup` if no accounts
- Redirects to `/client` if accounts exist

**Dependencies**:
- Requires: Authentication, Account Management API
- Required by: Client routes in App.jsx

**Scenario**: `/scenarios/auth_flow.md#routing`

**Key Functions**:
- `checkAccounts()` - frontend/src/components/AuthGateway.jsx:10

**Business Logic**:
- Prevents blank dashboard pages
- Ensures users land on correct page
- Handles network errors gracefully

---

## Polling & Real-Time Updates

### Account Status Polling

**Module**: `frontend/src/components/ClientSetup.jsx`
**Added**: 2025-12-25

**Polling Logic**:
- Polls `/client/accounts` every 3 seconds
- Tracks status: connected → active
- Shows progress messages
- Auto-stops after 3 minutes or when active

**Dependencies**:
- Requires: Account Management API
- Required by: Onboarding flow

**Key Functions**:
- `startPollingAccountStatus()` - frontend/src/components/ClientSetup.jsx:162

**Business Logic**:
- Provides real-time feedback during discovery
- Shows elapsed time
- Cleans up interval on unmount

---

## Database Schema

### Core Tables

#### users
- `id` - Primary key
- `username` - Unique
- `email` - Unique
- `password_hash` - bcrypt
- `role` - client | admin | super_admin

#### accounts
- `id` - Primary key
- `user_id` - Foreign key to users
- `account_id` - AWS Account ID (globally unique)
- `account_name` - Display name
- `status` - pending | connected | active | failed
- `connection_method` - iam_role | access_keys
- `role_arn` - CloudFormation IAM role (nullable)
- `external_id` - For IAM role assumption (nullable)
- `aws_access_key_id` - Encrypted (nullable)
- `aws_secret_access_key` - Encrypted (nullable)
- `region` - AWS region
- `account_metadata` - JSON

#### instances
- `id` - Primary key
- `account_id` - Foreign key to accounts
- `instance_id` - AWS Instance ID
- `instance_type` - t2.micro, etc.
- `state` - running | stopped | terminated
- `lifecycle` - on-demand | spot
- `auth_status` - authorized | unauthorized
- `instance_metadata` - JSON

---

_Last Updated: 2025-12-26_
_Entries: 12 features_
