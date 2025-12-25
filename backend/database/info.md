# Backend Database Module

## Purpose

Database connection, ORM models, and schema definitions for the application.

**Last Updated**: 2025-12-25
**Authority Level**: HIGH

---

## Files

### connection.py
**Purpose**: Database connection management and session handling
**Lines**: ~100
**Key Functions**:
- `get_db()` - Database session dependency (FastAPI)
- `SessionLocal` - SQLAlchemy session factory
- `Base` - Declarative base for all models
**Dependencies**: SQLAlchemy, environment variables
**Recent Changes**:
- 2025-12-23: Updated connection pooling configuration
**Reference**: Used by all API routes

### models.py ⭐ CRITICAL
**Purpose**: Complete ORM model definitions
**Lines**: ~600
**Models**:
1. **User** (lines ~50-100) - Authentication and user management
   - Fields: id, username, email, password_hash, role, is_active
   - Relationships: accounts, system_logs

2. **Account** (lines ~120-180) - AWS account connections
   - Fields: id, user_id, account_id, account_name, region, status, connection_method
   - Relationships: user, instances, logs
   - Status values: 'pending', 'connected', 'active', 'failed'

3. **Instance** (lines ~200-280) - EC2 instance tracking
   - Fields: id, account_id, instance_id, instance_type, state, region, cpu, memory
   - Relationships: account, experiment_logs

4. **ExperimentLog** (lines ~300-360) - ML experiment tracking
   - Fields: id, instance_id, experiment_name, status, metrics, created_at
   - Relationships: instance

5. **SystemLog** (lines ~380-420) - System event logging
   - Fields: id, user_id, action, details, timestamp
   - Relationships: user

6. **OnboardingRequest** (lines ~440-500) - Temporary onboarding state
   - Fields: id, user_id, request_id, connection_method, status, aws_account_id
   - Lifecycle: Created → Verified → Converted to Account → Deleted

**Dependencies**: SQLAlchemy, datetime, UUID
**Recent Changes**:
- 2025-12-25: No schema changes (governance establishment)
- 2025-12-23: Updated Account model status enum
**Reference**: `/index/feature_index.md#database-models`

### system_logs.py
**Purpose**: System logging utilities and helper functions
**Lines**: ~100
**Key Functions**:
- `log_user_action()` - Record user actions to database
- `get_recent_logs()` - Query helper for log retrieval
**Dependencies**: models.py, connection.py
**Recent Changes**: None recent

### __init__.py
**Purpose**: Package initialization and exports
**Exports**: Base, SessionLocal, get_db, all models

---

## Database Schema Relationships

```
User (1) ──→ (N) Account
  ↓
  └──→ (N) SystemLog

Account (1) ──→ (N) Instance
  ↓
  └──→ (N) AccountLog

Instance (1) ──→ (N) ExperimentLog
```

---

## Critical Behaviors

### Cascade Deletes
When Account is deleted:
1. All related Instances are deleted first (manual cascade in API)
2. ExperimentLogs are deleted via FK cascade (if configured)
3. Prevents orphaned records

**Protected Zone**: See `/progress/regression_guard.md#6`

### Status Transitions (Account)
```
'pending' → 'connected' (via onboarding API)
'connected' → 'active' (via discovery worker)
'connected' → 'failed' (on discovery error)
```

**Protected Zone**: See `/progress/regression_guard.md#4`

---

## Dependencies

### Depends On:
- SQLAlchemy ORM
- PostgreSQL database
- Environment variables (DATABASE_URL)

### Depended By:
- All API routes (`backend/api/*.py`)
- Discovery worker (`backend/workers/discovery_worker.py`)
- Health checks (`backend/utils/component_health_checks.py`)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing database structure
**Impact**: No schema changes, documentation baseline
**Reference**: `/index/recent_changes.md`

### 2025-12-23: Account Status Enum Update
**Files Changed**: models.py
**Reason**: Support new status transitions for discovery workflow
**Impact**: Added 'active' status to Account model
**Reference**: Legacy documentation

---

## Usage

### Creating New Models
1. Define model class in `models.py`
2. Add relationships to existing models
3. Create migration in `/database/migrations/`
4. Update this info.md
5. Update `/index/feature_index.md`
6. Update `/index/dependency_index.md`

### Querying
```python
from backend.database import get_db
from backend.database.models import Account

def example_route(db: Session = Depends(get_db)):
    accounts = db.query(Account).filter(Account.user_id == user_id).all()
```

---

## Known Issues

### None

Database layer is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: HIGH - Core data layer_
