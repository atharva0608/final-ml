# Fix Summary: Configuration Save & Instance Tracking Issues

## Issues Fixed

### 1. **Configuration Save Error** ❌ → ✅
**Error:** `Unknown column 'config_version' in 'field list'`

**Root Cause:**
The backend code expected a `config_version` column in the `agents` table that didn't exist in the database schema. This column is used to track configuration version changes and force agent config refreshes.

**Solution:**
- Added `config_version INT DEFAULT 0` column to the `agents` table in `database/schema.sql`
- Created migration script `database/fix_config_version_error.sql` for existing databases
- Created Python migration script `database/migrate_add_config_version.py` as alternative

**Action Required:** Run the SQL migration on your database (see instructions below)

---

### 2. **Instance Not Found After Switch** ❌ → ✅
**Error:** `Instance not found` for new instance ID after switching

**Root Cause:**
After an instance switch, the frontend immediately queries for instance data, but:
1. The new instance starts up
2. The frontend tries to fetch data immediately
3. The agent hasn't sent its first heartbeat yet
4. The `agents` table doesn't have the new instance_id
5. The API returns 404

**Solution:**
- **Backend:** Modified `/api/client/instances/<instance_id>/available-options` endpoint to fallback to `instances` table
- **Frontend:** Added retry logic (3 attempts with 2-second delays) to handle initialization delay

---

## Files Changed

### Backend (`backend/backend.py`)
- Line 3197-3216: Added fallback to `instances` table in `get_instance_available_options()`

### Frontend (`frontend/src/components/details/InstanceDetailPanel.jsx`)
- Lines 27-91: Added retry logic with timeout for `getInstanceAvailableOptions()`
- Separated API calls to load pricing/metrics first, then retry for options

### Database
- `database/schema.sql` - Line 108: Added `config_version` column
- `database/fix_config_version_error.sql` - Quick-apply SQL script
- `database/migrate_add_config_version.py` - Python migration script
- `database/FIX_CONFIG_VERSION_ERROR.md` - Detailed documentation

---

## How to Apply the Fixes

### Step 1: Apply Database Migration (REQUIRED)

**Option A: Using the SQL script (Recommended)**
```bash
# SSH to your server
ssh user@3.238.232.106

# Apply the migration
mysql -u spotuser -p spot_optimizer < database/fix_config_version_error.sql
```

**Option B: Manual SQL**
```sql
USE spot_optimizer;

ALTER TABLE agents
ADD COLUMN config_version INT DEFAULT 0
COMMENT 'Configuration version counter for forcing agent config refresh'
AFTER agent_version;

-- Verify
SELECT COLUMN_NAME, DATA_TYPE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'spot_optimizer'
  AND TABLE_NAME = 'agents'
  AND COLUMN_NAME = 'config_version';
```

### Step 2: Deploy Backend Changes
```bash
# Pull the latest changes
git pull origin claude/fix-instance-management-01CxyG4Xk2Nm49eCt4GyCHxh

# Restart the backend service
systemctl restart spot-optimizer-backend
# OR
pm2 restart backend
# OR however you run your backend
```

### Step 3: Deploy Frontend Changes
```bash
# Rebuild the frontend
cd frontend
npm run build

# The updated bundle will include the retry logic
```

### Step 4: Verify the Fixes

1. **Configuration Save:**
   - Open an agent's configuration page
   - Toggle any setting (auto-switch, manual replica, etc.)
   - Click Save
   - Should save successfully without errors ✅

2. **Instance Tracking After Switch:**
   - Trigger an instance switch
   - After switch completes, view the new instance details
   - Instance data should load (with possible 2-4 second delay) ✅

---

## Technical Details

### Config Version Column
- **Purpose:** Increment counter to force agents to refresh configuration
- **Type:** INT DEFAULT 0
- **Location:** `agents` table, after `agent_version` column
- **Usage:** Incremented whenever settings change (auto_switch, auto_terminate, replicas, etc.)

### Instance Lookup Fallback
```python
# Before: Only checked agents table
agent = execute_query("SELECT ... FROM agents WHERE instance_id = %s")

# After: Falls back to instances table
agent = execute_query("SELECT ... FROM agents WHERE instance_id = %s")
if not agent:
    agent = execute_query("SELECT ... FROM instances WHERE id = %s")
```

### Frontend Retry Logic
```javascript
// Retry up to 3 times with 2-second delays
for (let i = 0; i < 3; i++) {
  try {
    optionsData = await api.getInstanceAvailableOptions(instanceId);
    break;
  } catch (err) {
    if (i < 2) await new Promise(resolve => setTimeout(resolve, 2000));
  }
}
```

---

## Testing Checklist

- [ ] Database migration applied successfully
- [ ] Backend restarted
- [ ] Frontend rebuilt and deployed
- [ ] Configuration save works for all toggles:
  - [ ] Auto-Switch Mode
  - [ ] Manual Replica Mode
  - [ ] Auto-Terminate
  - [ ] Termination wait time
- [ ] Instance tracking works after switch:
  - [ ] New instance data loads
  - [ ] Available pools display
  - [ ] Pricing history loads
  - [ ] Metrics display correctly

---

## Rollback Procedure

If issues occur after applying fixes:

**Database Rollback:**
```sql
ALTER TABLE agents DROP COLUMN config_version;
```

**Code Rollback:**
```bash
git checkout HEAD~1
# Restart services
```

---

## Prevention

These issues are now permanently fixed:
- ✅ Schema file updated - future installations will include `config_version`
- ✅ Backend resilient to initialization delays
- ✅ Frontend retries failed requests automatically
- ✅ Comprehensive migration scripts provided

---

## Support

If you encounter any issues:
1. Check logs: `tail -f /var/log/spot-optimizer/backend.log`
2. Verify column exists: `SHOW COLUMNS FROM agents LIKE 'config_version'`
3. Check agent heartbeats: `SELECT instance_id, last_heartbeat_at FROM agents`
4. Review browser console for frontend errors
