# Database Module

## Purpose

Database models, migrations, and connection management using SQLAlchemy ORM.

**Last Updated**: 2025-12-25

---

## Files

### models.py
**Purpose**: SQLAlchemy database models (schema definitions)
**Lines**: ~500

**Tables Defined**:
1. **users** - User accounts
   - id, username, email, password_hash, role
   - Roles: client, admin, super_admin

2. **accounts** - AWS account connections
   - id, user_id, account_id (AWS ID), account_name
   - connection_method (iam_role | access_keys)
   - status (pending | connected | active | failed)
   - role_arn, external_id (CloudFormation)
   - aws_access_key_id, aws_secret_access_key (encrypted)
   - region, account_metadata (JSON)

3. **instances** - EC2 instance inventory
   - id, account_id, instance_id (AWS ID)
   - instance_type, state, lifecycle (on-demand | spot)
   - auth_status (authorized | unauthorized)
   - instance_metadata (JSON)

4. **experiment_logs** - Optimization history
5. **downtime_logs** - SLA tracking
6. **system_logs** - Application logs

**Relationships**:
- User → Accounts (one-to-many)
- Account → Instances (one-to-many, cascade delete)
- Account → ExperimentLogs (one-to-many)

**Recent Changes**: None recent (schema stable)

**Reference**: `/docs/legacy/architecture/DATABASE_SCHEMA.md` (historical)

---

### connection.py
**Purpose**: Database connection and session management
**Lines**: ~100

**Key Components**:
- `engine` - SQLAlchemy engine
- `SessionLocal` - Session factory
- `get_db()` - Dependency for FastAPI routes

**Configuration**:
- Connection string from `DATABASE_URL` environment variable
- Connection pooling enabled
- Echo mode for debugging (development only)

**Usage**:
```python
from database.connection import get_db

@router.get("/endpoint")
async def handler(db: Session = Depends(get_db)):
    # Database operations
    pass
```

**Recent Changes**: None recent

---

## Database Migrations

### migrations/
**Purpose**: Alembic migration scripts
**Status**: Not actively used (manual schema updates)

**To Create Migration**:
```bash
alembic revision --autogenerate -m "Description"
alembic upgrade head
```

---

## Recent Changes

### 2025-12-25: Documentation Only
**Reason**: Add info.md for governance structure
**Impact**: None (documentation only)

### Historical: Schema Stable
**Last Schema Change**: Pre-2025-11-23
**Current Version**: Stable
**No pending migrations**

---

## Dependencies

**Requires**:
- SQLAlchemy
- MySQL or PostgreSQL database server
- Environment variable: `DATABASE_URL`

**Required By**:
- All backend API routes
- All workers
- Entire backend application

---

## Testing

### Manual Testing
```python
from database.connection import SessionLocal
from database.models import User, Account

db = SessionLocal()
users = db.query(User).all()
print(users)
db.close()
```

---

_Last Updated: 2025-12-25_
_See: `/index/system_index.md` for database architecture_
