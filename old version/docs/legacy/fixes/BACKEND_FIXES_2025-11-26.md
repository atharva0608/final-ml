# Backend Fixes - November 26, 2025

## Issues Identified and Fixed

### 1. ❌ Database Schema Missing Columns - CRITICAL

**Problem:**
```
ERROR - HTTP error 500: /api/agents/.../instances-to-terminate
{"error":"1054 (42S22): Unknown column 'i.termination_attempted_at' in 'where clause'"}
```

The backend code references `termination_attempted_at` and `termination_confirmed` columns that don't exist in the database.

**Root Cause:**
- Migration file exists: `database/migrations/add_termination_tracking.sql`
- But the migration was never applied to the production database
- Backend endpoints at `backend.py:906, 931, 987, 998, 1016, 1022` use these columns

**Fix Applied:**
1. ✅ Updated `database/schema.sql` to include new columns in base schema
2. ✅ Created migration scripts:
   - `database/migrations/apply_termination_tracking.sh` (Bash version)
   - `database/migrations/apply_migration.py` (Python version)

**Columns Added:**
```sql
-- instances table
termination_attempted_at TIMESTAMP NULL COMMENT 'When agent last attempted to terminate this instance'
termination_confirmed BOOLEAN DEFAULT FALSE COMMENT 'TRUE if AWS confirmed termination'

-- replica_instances table
termination_attempted_at TIMESTAMP NULL COMMENT 'When agent last attempted to terminate this instance'
termination_confirmed BOOLEAN DEFAULT FALSE COMMENT 'TRUE if AWS confirmed termination'
```

**Indexes Added:**
```sql
CREATE INDEX idx_instances_zombie_termination ON instances(instance_status, termination_attempted_at, region);
CREATE INDEX idx_replicas_termination ON replica_instances(status, termination_attempted_at, agent_id);
```

---

### 2. ❌ Auto-Termination Not Working on AWS

**Problem:**
- Agent logs show "Auto-terminate ENABLED: waiting 60s before terminating old instance..."
- Old instance (i-029c1999a147722de) never gets terminated in AWS
- Frontend shows instance as terminated but AWS Console shows it still running

**Root Cause:**
The database schema error (Issue #1) blocks the termination process:
1. Agent waits 60 seconds (as configured)
2. Agent polls `/api/agents/{agent_id}/instances-to-terminate`
3. Endpoint fails with SQL error due to missing `termination_attempted_at` column
4. Agent never receives the list of instances to terminate
5. Termination never happens in AWS

**Fix:**
Apply the database migration (see Issue #1). Once the columns exist, the termination flow will work:
1. Agent polls `/instances-to-terminate` endpoint
2. Backend queries for zombie instances past their wait period
3. Agent receives list and terminates via AWS EC2 API
4. Agent reports back via `/termination-report` endpoint
5. Backend updates `termination_confirmed = TRUE`

---

### 3. ❌ New Instance Not Showing in Instance List

**Problem:**
- Agent launched new instance i-0f75d6fccfb53a938 via switch command
- Instance not appearing in frontend instance list
- User also manually launched instance via AWS Console which didn't appear

**Root Cause - Scenario A (Agent-launched instance):**
The agent should call `/api/agents/{agent_id}/switch-report` after completing a switch, which:
1. Inserts new instance into `instances` table
2. Marks old instance as zombie or terminated
3. Updates agent's `instance_id` pointer

If the switch-report call failed or wasn't made, the instance won't appear.

**Root Cause - Scenario B (Manually-launched instance):**
When you launch an instance manually via AWS Console:
1. Backend doesn't know about it (no automatic discovery)
2. Agent needs to report it via switch-report OR
3. Use the new manual registration endpoint

**Fix Applied:**
1. ✅ Added new endpoint: `POST /api/agents/{agent_id}/register-instance`
2. Allows manual registration of instances launched outside agent control
3. Automatically demotes old primary instances when registering a new primary
4. Updates agent's instance_id pointer

---

### 4. ❌ Old Instance Still Showing as Primary

**Problem:**
After launching new instance, old instance still appears as primary in frontend.

**Root Cause:**
When the switch-report endpoint is called successfully, it should:
```sql
-- Mark old instance as zombie
UPDATE instances SET instance_status = 'zombie', is_primary = FALSE
WHERE id = 'old-instance-id'

-- Mark new instance as primary
INSERT INTO instances (..., is_primary = TRUE, instance_status = 'running_primary')
```

If switch-report wasn't called or failed, these updates don't happen.

**Fix Applied:**
The new `/register-instance` endpoint (Issue #3) properly handles primary instance transitions:
1. Demotes all existing primary instances to zombie status
2. Registers new instance as primary
3. Updates agent's instance_id pointer

---

## Required Actions

### STEP 1: Apply Database Migration (REQUIRED)

**Option A - Using Python Script (Recommended):**
```bash
cd /home/user/final-ml
python3 database/migrations/apply_migration.py
```

**Option B - Using Bash Script:**
```bash
cd /home/user/final-ml
chmod +x database/migrations/apply_termination_tracking.sh
./database/migrations/apply_termination_tracking.sh
```

**Option C - Manual SQL:**
```bash
mysql -h <host> -u <user> -p <database> < database/migrations/add_termination_tracking.sql
```

### STEP 2: Restart Backend Server

After applying the migration, restart your backend server to ensure changes take effect:

```bash
# Find the backend process
ps aux | grep backend.py

# Kill and restart
sudo systemctl restart spot-optimizer-backend
# OR
pkill -f backend.py && python3 backend/backend.py &
```

### STEP 3: Register Manually Launched Instance (If Applicable)

If you launched an instance manually via AWS Console, register it with the backend:

```bash
curl -X POST "https://your-backend-url/api/agents/<agent-id>/register-instance" \
  -H "Authorization: Bearer <client-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "instance_id": "i-0f75d6fccfb53a938",
    "instance_type": "t3.medium",
    "region": "ap-south-1",
    "az": "ap-south-1c",
    "mode": "spot",
    "pool_id": "t3.medium.ap-south-1c",
    "is_primary": true,
    "spot_price": 0.0416,
    "ondemand_price": 0.0832
  }'
```

Replace:
- `<agent-id>`: Your agent UUID (from logs: `f389c0c2-1bd9-4a07-a7a6-10a84a048f2c`)
- `<client-token>`: Your API authentication token
- Instance details with your actual values

### STEP 4: Verify Fixes

**Check 1 - Database Columns Exist:**
```sql
DESCRIBE instances;
-- Should show termination_attempted_at and termination_confirmed columns

DESCRIBE replica_instances;
-- Should show termination_attempted_at and termination_confirmed columns
```

**Check 2 - Instance Appears in List:**
```bash
curl -X GET "https://your-backend-url/api/client/<client-id>/instances" \
  -H "Authorization: Bearer <token>"
```

**Check 3 - Termination Endpoint Works:**
```bash
curl -X GET "https://your-backend-url/api/agents/<agent-id>/instances-to-terminate" \
  -H "Authorization: Bearer <token>"
```

Should return JSON (not 500 error):
```json
{
  "instances": [...],
  "auto_terminate_enabled": true,
  "terminate_wait_seconds": 60
}
```

**Check 4 - Monitor Agent Logs:**
```bash
tail -f /var/log/spot-optimizer/agent-error.log
```

You should no longer see:
- ❌ `HTTP error 500: instances-to-terminate`
- ❌ `Unknown column 'termination_attempted_at'`

You should see:
- ✅ `Found N pending command(s)`
- ✅ `Instance X confirmed terminated by agent`
- ✅ Successful termination confirmations

---

## Files Changed

### Modified Files:
1. **`database/schema.sql`**
   - Added `termination_attempted_at` and `termination_confirmed` to `instances` table
   - Added `termination_attempted_at` and `termination_confirmed` to `replica_instances` table
   - Added indexes for efficient termination queries

2. **`backend/backend.py`**
   - Added new endpoint: `POST /api/agents/<agent_id>/register-instance` (lines 1045-1168)
   - Allows manual instance registration
   - Handles primary instance transitions properly

### New Files Created:
1. **`database/migrations/apply_termination_tracking.sh`**
   - Bash script to apply migration
   - Interactive with user prompts

2. **`database/migrations/apply_migration.py`**
   - Python script to apply migration
   - Reads credentials from .env file
   - Better error handling and feedback

3. **`docs/BACKEND_FIXES_2025-11-26.md`** (this file)
   - Comprehensive documentation of issues and fixes

---

## Understanding the Termination Flow

### Normal Flow (When Working):

```
1. Agent executes switch command
   └─> Launches new instance (i-new)
   └─> Old instance (i-old) still running

2. Agent calls /switch-report
   └─> Backend marks i-old as 'zombie', is_primary=FALSE
   └─> Backend inserts i-new as 'running_primary', is_primary=TRUE
   └─> Backend updates agent.instance_id = i-new

3. Agent waits terminate_wait_seconds (e.g., 60s)
   └─> Traffic has time to drain from old instance

4. Agent polls /instances-to-terminate
   └─> Backend queries: SELECT * FROM instances
       WHERE instance_status = 'zombie'
       AND TIMESTAMPDIFF(SECOND, updated_at, NOW()) >= terminate_wait_seconds
       AND termination_attempted_at IS NULL  <-- THIS WAS FAILING

5. Agent receives [i-old] in response
   └─> Agent calls AWS EC2: terminate_instances([i-old])

6. Agent calls /termination-report
   └─> Backend updates:
       - instance_status = 'terminated'
       - termination_confirmed = TRUE
       - terminated_at = NOW()

7. Frontend shows:
   └─> Active: i-new (running_primary)
   └─> Terminated: i-old (terminated)
```

### What Was Happening (Broken):

```
1-3. Same as above ✅

4. Agent polls /instances-to-terminate
   └─> Backend query fails ❌
       Error: Unknown column 'termination_attempted_at'
   └─> Returns HTTP 500 error
   └─> Agent logs error but continues

5. Agent never receives list of instances to terminate
   └─> Never calls AWS terminate_instances()

6. Result:
   └─> Frontend shows i-old as terminated (database says zombie/terminated)
   └─> AWS Console shows i-old still running (was never terminated)
   └─> You're paying for zombie instance! 💸
```

---

## Prevention

### For Future Development:

1. **Always apply migrations before deploying code that uses new columns**
   - Check `database/migrations/` directory
   - Run migration scripts on staging first
   - Verify columns exist before pushing backend changes

2. **Test termination flow in staging**
   ```bash
   # Test the complete flow
   1. Issue switch command
   2. Wait terminate_wait_seconds
   3. Verify old instance terminates in AWS
   4. Check database: termination_confirmed = TRUE
   ```

3. **Monitor for SQL errors**
   ```bash
   # Set up alerts for these errors
   grep -i "unknown column" /var/log/spot-optimizer/*.log
   grep -i "1054" /var/log/spot-optimizer/*.log
   ```

4. **Add health check endpoint**
   ```python
   @app.route('/api/health/database-schema', methods=['GET'])
   def check_schema():
       # Verify all required columns exist
       # Return 200 if OK, 500 if missing columns
   ```

---

## Questions?

If you encounter issues after applying these fixes:

1. Check the migration was applied successfully:
   ```sql
   SHOW COLUMNS FROM instances LIKE 'termination_attempted_at';
   ```

2. Verify backend server was restarted

3. Check backend logs for any new errors:
   ```bash
   tail -f /var/log/spot-optimizer/backend.log
   ```

4. Test the endpoints manually with curl (see STEP 4 above)

---

## Summary

✅ **Database schema updated** - Added termination tracking columns
✅ **Migration scripts created** - Easy to apply changes
✅ **Manual instance registration** - New endpoint for manually launched instances
✅ **Primary instance logic** - Properly demotes old primaries
✅ **Documentation** - Complete guide for troubleshooting

**Next Steps:**
1. Apply the migration (STEP 1)
2. Restart backend (STEP 2)
3. Register manual instance if needed (STEP 3)
4. Verify everything works (STEP 4)

The termination flow should now work correctly! 🎉
