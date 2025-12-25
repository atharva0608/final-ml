# Dependency Index

## Purpose

Maps component dependencies and change impact radius.

**Last Updated**: 2025-12-25

---

## Dependency Graph

### Authentication System
**Location**: `backend/api/auth.py`

**Depends On**:
- Database (`users` table)
- JWT library (python-jose)
- Password hashing (passlib/bcrypt)

**Depended By**:
- ALL protected API endpoints
- Frontend AuthContext
- AuthGateway routing
- Client Dashboard
- Admin Dashboard
- Account Management
- Onboarding flows

**Impact Radius**: **CRITICAL** - Affects entire application

**Change Protocol**:
- Requires regression testing of all flows
- Must update `/progress/regression_guard.md` if modified
- Security review required

---

### Account Management
**Location**: `backend/api/client_routes.py`

**Depends On**:
- Authentication system
- Database (`accounts`, `instances` tables)
- System logger

**Depended By**:
- Client Dashboard
- AuthGateway
- Frontend ClientSetup
- Discovery Worker (reads account details)

**Impact Radius**: **HIGH** - Affects all client workflows

**Change Protocol**:
- Must verify AuthGateway routing still works
- Must test dashboard empty states
- Must verify discovery worker integration

---

### AWS Onboarding (CloudFormation)
**Location**: `backend/api/onboarding_routes.py:453`

**Depends On**:
- AWS STS (AssumeRole)
- Database (`accounts` table)
- Encryption utility (for External ID)
- Discovery Worker (background task)

**Depended By**:
- Frontend ClientSetup (CloudFormation tab)
- Account Management (creates accounts)

**Impact Radius**: **MEDIUM** - Affects onboarding flow only

**Change Protocol**:
- Must verify IAM role assumption works
- Must test CloudFormation template generation
- Must verify discovery triggers correctly

---

### AWS Onboarding (Credentials)
**Location**: `backend/api/onboarding_routes.py:94`

**Depends On**:
- AWS STS (GetCallerIdentity)
- Database (`accounts` table)
- Encryption utility (`utils/crypto.py`)
- Discovery Worker (background task)

**Depended By**:
- Frontend ClientSetup (Credentials tab)
- Account Management (creates accounts)

**Impact Radius**: **MEDIUM** - Affects onboarding flow only

**Change Protocol**:
- Must verify credential encryption/decryption
- Must test AWS validation
- Must verify discovery triggers correctly

---

### Discovery Worker
**Location**: `backend/workers/discovery_worker.py`

**Depends On**:
- Database (`accounts`, `instances` tables)
- AWS EC2 API (DescribeInstances)
- AWS STS (for CloudFormation accounts)
- Encryption utility (for access key accounts)
- Health Check System (NEW: 2025-12-25)

**Depended By**:
- Onboarding flows (both CloudFormation and Credentials)
- Client Dashboard (displays discovered instances)
- Rediscovery operations

**Impact Radius**: **HIGH** - Affects data availability in dashboard

**Change Protocol**:
- Must verify account status transitions
- Must test both connection methods (IAM role + access keys)
- Must verify health check trigger
- Must test error handling (failed status)

---

### Health Check System
**Location**: `backend/utils/component_health_checks.py`

**Depends On**:
- Database (query latency test)
- Redis (if enabled)
- System logs table

**Depended By**:
- Health Monitor Worker
- Discovery Worker (triggers after completion - NEW)
- Monitoring endpoints

**Impact Radius**: **LOW** - Monitoring only

**Change Protocol**:
- Can modify without affecting core functionality
- Must not block critical paths

---

### Client Dashboard
**Location**: `backend/api/client_routes.py:147`

**Depends On**:
- Authentication system
- Database (`accounts`, `instances`, `experiment_logs`, `downtime_logs`)
- Account Management (reads accounts)

**Depended By**:
- Frontend DashboardLayout
- Frontend NodeFleet component

**Impact Radius**: **HIGH** - Main user interface

**Change Protocol**:
- Must preserve API contract (response structure)
- Must handle all account statuses (no_account, pending, connected, active, failed)
- Must include `setup_required` flag

---

### AuthGateway (Frontend)
**Location**: `frontend/src/components/AuthGateway.jsx`

**Depends On**:
- Account Management API (`/client/accounts`)
- React Router (navigation)

**Depended By**:
- App.jsx routing
- Client routes protection

**Impact Radius**: **MEDIUM** - Client routing only

**Change Protocol**:
- Must verify routing logic for both states (accounts exist / no accounts)
- Must handle API errors gracefully
- Must not create redirect loops

---

### ClientSetup (Frontend)
**Location**: `frontend/src/components/ClientSetup.jsx`

**Depends On**:
- Account Management API (list, delete)
- Onboarding APIs (create, verify, connect)
- Discovery Status API
- Polling mechanism

**Depended By**:
- AuthGateway (redirects here if no accounts)
- App.jsx routing

**Impact Radius**: **MEDIUM** - Onboarding flow only

**Change Protocol**:
- Must test both connection methods
- Must verify polling cleanup on unmount
- Must test disconnect flow
- Must verify account list refresh

---

### Database Models
**Location**: `database/models.py`

**Depends On**:
- SQLAlchemy ORM
- Database server (MySQL/PostgreSQL)

**Depended By**:
- ALL backend modules
- Discovery Worker
- Dashboard APIs
- Onboarding APIs

**Impact Radius**: **CRITICAL** - Entire system

**Change Protocol**:
- Requires database migration (Alembic)
- Must update all dependent queries
- Must update API response models
- Requires full regression testing

---

### Encryption Utility
**Location**: `backend/utils/crypto.py`

**Depends On**:
- Cryptography library (Fernet)
- Environment variable (`ENCRYPTION_KEY`)

**Depended By**:
- Onboarding (credentials flow)
- Discovery Worker (access key decryption)

**Impact Radius**: **HIGH** - Affects credential security

**Change Protocol**:
- **NEVER** change encryption algorithm without migration plan
- Must preserve ability to decrypt existing credentials
- Security review required

---

## Cascade Delete Relationships

### Account Deletion

```
DELETE Account
  ↓
CASCADE DELETE all Instances (backend/api/client_routes.py:121)
  ↓
Implicit: ExperimentLogs (if FK configured with cascade)
```

**Impact**: Removes all associated data
**Rollback**: No automatic rollback - destructive operation

---

## Shared Dependencies

### All Backend Modules

**Common Dependencies**:
- `database/connection.py` - DB session management
- `utils/system_logger.py` - Structured logging
- `api/auth.py` - Authentication decorators

### All Frontend Components

**Common Dependencies**:
- `services/api.js` - HTTP client
- `context/AuthContext.jsx` - User state
- React Router - Navigation

---

## Circular Dependency Prevention

### Rules

1. **API layer** MUST NOT import from Workers
2. **Workers** CAN import from API utils but not routes
3. **Frontend components** MUST NOT import from other feature components (use shared components)

### Violations

None currently detected.

---

## External Service Dependencies

### AWS Services

**Required**:
- STS (AssumeRole, GetCallerIdentity)
- EC2 (DescribeInstances)

**Optional**:
- Pricing API
- CloudWatch (if metrics enabled)

**Failure Mode**:
- Onboarding: Show error, don't create account
- Discovery: Mark account as `failed`, log error
- Dashboard: Show stale data, indicate connection issue

### Database

**Required**: MySQL or PostgreSQL

**Failure Mode**:
- Application cannot start
- Health check fails immediately

---

## Change Impact Matrix

| Change Location | Impact Radius | Must Test |
|----------------|---------------|-----------|
| `database/models.py` | CRITICAL | ALL features |
| `api/auth.py` | CRITICAL | ALL protected routes |
| `api/client_routes.py` | HIGH | Dashboard, AuthGateway |
| `api/onboarding_routes.py` | MEDIUM | Onboarding flow, Discovery |
| `workers/discovery_worker.py` | HIGH | Dashboard data, Account status |
| `utils/crypto.py` | HIGH | Onboarding (credentials), Discovery |
| `utils/component_health_checks.py` | LOW | Monitoring only |
| Frontend `App.jsx` | HIGH | All routes |
| Frontend `ClientSetup.jsx` | MEDIUM | Onboarding only |
| Frontend `AuthGateway.jsx` | MEDIUM | Client routing |

---

_Last Updated: 2025-12-25_
