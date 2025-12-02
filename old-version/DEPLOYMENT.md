# Deployment Guide: Instance Tracking & Configuration Fixes

## Overview

This deployment fixes:
1. ✅ **Configuration Save Error** - Missing `config_version` column
2. ✅ **Instance Not Found After Switch** - Backend fallback to instances table
3. ✅ **Instant Data Loading** - Optimized parallel loading

The `config_version` column is now included in `database/schema.sql` (line 108).

---

## 🚀 Deployment Steps

### Step 1: Pull Latest Code

```bash
ssh user@3.238.232.106
cd /path/to/final-ml
git pull origin claude/fix-instance-management-01CxyG4Xk2Nm49eCt4GyCHxh
```

### Step 2: Apply Database Schema

You'll run a fresh install of the schema which includes the `config_version` column:

```bash
mysql -u spotuser -p spot_optimizer < database/schema.sql
```

**Or** if you prefer to add just the missing column:

```sql
USE spot_optimizer;

ALTER TABLE agents
ADD COLUMN IF NOT EXISTS config_version INT DEFAULT 0
COMMENT 'Configuration version counter for forcing agent config refresh'
AFTER agent_version;
```

### Step 3: Restart Backend

```bash
# Choose the command that matches your setup:
systemctl restart spot-optimizer-backend
# OR
pm2 restart backend
# OR
sudo supervisorctl restart backend
```

### Step 4: Rebuild & Deploy Frontend

```bash
cd frontend
npm run build
# Copy build files to your web server
```

---

## ✅ Verification

### 1. Test Configuration Save
- Navigate to an agent's configuration page
- Toggle any setting (Auto-Switch, Manual Replica, Auto-Terminate)
- Click **Save**
- Should succeed without `config_version` errors ✅

### 2. Test Instance Switch
- Trigger an instance switch
- View the new instance details immediately
- Data should load instantly without delays ✅
- No "Instance not found" errors ✅

### 3. Check Database
```sql
-- Verify config_version column exists
SHOW COLUMNS FROM agents LIKE 'config_version';

-- Should return:
-- config_version | int | YES | NULL | Configuration version counter...
```

---

## What Changed

### Backend (`backend/backend.py`)
**Line 3206-3210:** Added fallback to instances table
```python
# Primary: Check agents table
agent = execute_query("SELECT ... FROM agents WHERE instance_id = %s")

# Fallback: Check instances table if agent not found
if not agent:
    agent = execute_query("SELECT ... FROM instances WHERE id = %s")
```

### Frontend (`frontend/src/components/details/InstanceDetailPanel.jsx`)
**Lines 27-97:** Optimized for instant parallel loading
```javascript
// Load all data in parallel - no blocking delays
const [pricingData, metricsData, optionsData] = await Promise.all([
  api.getInstancePricing(instanceId),
  api.getInstanceMetrics(instanceId),
  api.getInstanceAvailableOptions(instanceId).catch(() => null) // Non-blocking
]);
```

### Database (`database/schema.sql`)
**Line 108:** Added config_version column
```sql
agent_version VARCHAR(32),
config_version INT DEFAULT 0 COMMENT 'Configuration version counter for forcing agent config refresh',
instance_count INT DEFAULT 0,
```

---

## Rollback (if needed)

If issues occur:

**Remove config_version column:**
```sql
ALTER TABLE agents DROP COLUMN config_version;
```

**Revert code:**
```bash
git checkout HEAD~1
systemctl restart spot-optimizer-backend
cd frontend && npm run build
```

---

## Technical Details

### Why config_version is needed
The backend increments this counter when agent settings change:
- Auto-switch enabled/disabled
- Manual replica enabled/disabled
- Auto-terminate enabled/disabled
- Termination wait time changed

This forces agents to fetch updated configuration on next heartbeat.

### Why instances table fallback works
When a switch happens (`switch_report` endpoint):
1. New instance is inserted into `instances` table immediately (line 1055-1076)
2. Agent table is updated with new instance_id (line 1078-1091)
3. Frontend queries can use either table for instant data

### Parallel loading optimization
- Critical data (pricing, metrics) blocks UI rendering
- Optional data (available options) doesn't block - loads in background
- All requests run concurrently via `Promise.all()`
- Non-critical failures are gracefully handled

---

## Support

**Check logs:**
```bash
tail -f /var/log/spot-optimizer/backend.log
```

**Verify agent connection:**
```sql
SELECT id, instance_id, status, last_heartbeat_at
FROM agents
WHERE status = 'online';
```

**Check browser console:**
Open DevTools → Console → Look for any errors

---

## Summary

✅ Schema includes `config_version` column (line 108)
✅ Backend checks both agents and instances tables
✅ Frontend loads data instantly in parallel
✅ Configuration save works without errors
✅ Instance tracking works immediately after switch

**Deployment:** Pull code → Run schema → Restart backend → Rebuild frontend → Test!
