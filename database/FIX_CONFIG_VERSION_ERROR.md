# Fix for "Unknown column 'config_version' in 'field list'" Error

## Problem

When trying to save agent configuration, you encounter the following error:

```
Failed to save configuration: 1054 (42S22): Unknown column 'config_version' in 'field list'
POST http://3.238.232.106:5000/api/client/agents/4a6c9d7a-6eef-4abe-97aa-dfbe208e648e/config 500 (INTERNAL SERVER ERROR)
```

## Root Cause

The backend code (`backend/backend.py`) references a `config_version` column in the `agents` table that doesn't exist in the database. This column is used to track configuration changes and force agent config refreshes.

The backend uses this column in several places:
- `backend/backend.py:2478` - When updating auto_terminate_enabled
- `backend/backend.py:2486` - When enabling auto_switch_enabled
- `backend/backend.py:2502` - When disabling auto_switch_enabled
- `backend/backend.py:2508` - When enabling manual_replica_enabled
- `backend/backend.py:2519` - When disabling manual_replica_enabled

## Solution

Add the missing `config_version` column to the `agents` table.

### Option 1: Run the SQL Fix Script (Recommended)

Connect to your MySQL database and run the fix script:

```bash
mysql -u your_db_user -p spot_optimizer < database/fix_config_version_error.sql
```

Or if you have the credentials in environment variables:

```bash
mysql -u $DB_USER -p$DB_PASSWORD -h $DB_HOST spot_optimizer < database/fix_config_version_error.sql
```

### Option 2: Run the SQL Command Manually

Connect to your MySQL database and run this command:

```sql
USE spot_optimizer;

ALTER TABLE agents
ADD COLUMN config_version INT DEFAULT 0
COMMENT 'Configuration version counter for forcing agent config refresh'
AFTER agent_version;
```

### Option 3: Use MySQL Workbench or phpMyAdmin

1. Connect to your `spot_optimizer` database
2. Open the SQL editor
3. Run the ALTER TABLE command from Option 2 above
4. Execute the query

## Verification

After applying the fix, verify the column was added:

```sql
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_DEFAULT,
    IS_NULLABLE,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'spot_optimizer'
  AND TABLE_NAME = 'agents'
  AND COLUMN_NAME = 'config_version';
```

Expected output:
```
COLUMN_NAME     | DATA_TYPE | COLUMN_DEFAULT | IS_NULLABLE | COLUMN_COMMENT
----------------|-----------|----------------|-------------|--------------------------------
config_version  | int       | 0              | YES         | Configuration version counter...
```

## Testing

After applying the fix:

1. Reload your frontend application
2. Navigate to an agent's configuration page
3. Try changing a setting (e.g., toggle auto-switch or manual replica)
4. Click Save
5. The configuration should save successfully without errors

## Files Changed

This fix includes updates to:

1. **database/schema.sql** - Updated to include `config_version` column in the agents table definition
2. **database/fix_config_version_error.sql** - SQL script to apply the fix to existing databases
3. **database/migrate_add_config_version.py** - Python migration script (alternative method)

## Prevention

The schema.sql file has been updated to include this column, so future database installations will not encounter this issue.
