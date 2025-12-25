# Database Migrations Module

## Purpose

SQL migration scripts for database schema changes.

**Last Updated**: 2025-12-25
**Authority Level**: HIGH

---

## Files

### 001_expand_account_id_column.sql
**Purpose**: Expand account_id column to accommodate longer AWS account IDs
**Lines**: ~25
**Applied**: Unknown (check migration history)

**Changes**:
- Alter `accounts.account_id` column type
- Likely VARCHAR(12) → VARCHAR(20) or similar
- Required for AWS account ID format changes

**Impact**: Schema change, requires data migration

### 003_fix_client_user_role.sql
**Purpose**: Fix user role assignments for client users
**Lines**: ~15
**Applied**: 2025-12-23 (likely)

**Changes**:
- Update `users.role` column values
- Fix incorrect role assignments
- Ensure client users have correct 'client' role

**Impact**: Data fix, affects authentication and authorization

---

## Migration Workflow

### Manual Migration Process
```bash
# 1. Backup database first
pg_dump your_database > backup.sql

# 2. Apply migration
psql your_database < database/migrations/00X_migration_name.sql

# 3. Verify changes
psql your_database -c "SELECT * FROM users LIMIT 5;"

# 4. Update migration log
echo "00X_migration_name.sql - Applied YYYY-MM-DD" >> migrations_applied.log
```

### Migration Best Practices
1. **Always backup before migration**
2. **Test in development first**
3. **Use transactions** (BEGIN; ... COMMIT;)
4. **Add rollback script** (if possible)
5. **Document in this info.md**

---

## Migration Naming Convention

**Format**: `NNN_descriptive_name.sql`
- NNN: 3-digit sequential number (001, 002, 003, ...)
- descriptive_name: Snake_case description
- .sql extension

**Examples**:
- 001_expand_account_id_column.sql
- 002_add_encryption_key_column.sql
- 003_fix_client_user_role.sql

---

## Dependencies

### Depends On:
- PostgreSQL database
- backend/database/models.py (SQLAlchemy models)
- Database connection

### Depended By:
- Application startup (requires schema)
- All database operations
- Data integrity

**Impact Radius**: CRITICAL (affects entire database)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing migrations
**Impact**: No migrations added, documentation baseline
**Reference**: `/index/recent_changes.md`

### 2025-12-23: Client Role Fix (003)
**File**: 003_fix_client_user_role.sql
**Reason**: Some client users had incorrect role assignments
**Impact**: Fixed authentication issues for client users
**Reference**: Legacy documentation

---

## Creating New Migration

### Step-by-Step
```sql
-- File: database/migrations/004_add_new_column.sql

-- Description: Add email_verified column to users table
-- Author: LLM Session / Developer
-- Date: 2025-12-25

BEGIN;

-- Add column
ALTER TABLE users
ADD COLUMN email_verified BOOLEAN DEFAULT FALSE NOT NULL;

-- Update existing users (if needed)
UPDATE users SET email_verified = TRUE WHERE created_at < '2025-01-01';

COMMIT;

-- Rollback script (separate file: 004_rollback.sql)
-- ALTER TABLE users DROP COLUMN email_verified;
```

### After Creating Migration
1. Add to this info.md
2. Update backend/database/models.py (if schema change)
3. Test in development
4. Apply to production
5. Update `/index/recent_changes.md`

---

## Known Issues

### None

Migrations module is stable as of 2025-12-25.

---

## TODO / Planned Migrations

1. **Add indexes** (if performance issues)
2. **Add foreign key constraints** (if not already present)
3. **Add cascade delete rules** (if needed)

---

_Last Updated: 2025-12-25_
_Authority: HIGH - Database schema_
