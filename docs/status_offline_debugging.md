# Status Showing "Offline" - Debugging Guide

## Current State

### Database Evidence (✅ Correct)
```sql
Status: ACTIVE
Agent Installed: Y
Last Heartbeat: 24 seconds ago
Seconds Since Heartbeat: 24.3

✅ All conditions for "Connected" are met!
```

### Frontend Logic (Should Work)
```javascript
const isReallyConnected = () => {
  // Check 1: Status must be ACTIVE
  if (cluster.status !== 'ACTIVE') return false;

  // Check 2: Must have heartbeat
  if (!cluster.last_heartbeat) return false;

  // Check 3: Heartbeat within last 2 minutes
  const lastHB = new Date(cluster.last_heartbeat);
  const twoMinAgo = new Date(Date.now() - 2 * 60 * 1000);
  return lastHB > twoMinAgo;  // true = Connected
};
```

## Debug Steps Added

### 1. Frontend Console Logging (ADDED)
I've added detailed console logging to ClusterList.jsx. The console will now show:
```
Status Check for spot-demo-1 {
  status: 'ACTIVE',
  last_heartbeat: '2026-02-09T12:42:54.933797',
  agent_installed: true
}
  Last HB: 2026-02-09T12:42:54.933Z
  Two min ago: 2026-02-09T12:41:19.260Z
  Is Connected: true/false
```

### 2. How to Debug

**Step 1: Open Browser Console**
- Chrome/Edge: `F12` or `Ctrl+Shift+I` (Windows/Linux) / `Cmd+Option+I` (Mac)
- Click "Console" tab

**Step 2: Refresh Page**
- Hard refresh: `Ctrl+Shift+R` (Windows/Linux) / `Cmd+Shift+R` (Mac)

**Step 3: Check Console Output**
Look for lines starting with "Status Check for spot-demo-1"

**Step 4: Share Results**
- Screenshot the console output
- This will show us exactly what data the frontend is receiving

## Possible Issues

### Issue 1: Date Parsing Problem
**Symptom**: Frontend can't parse the date string
**Check**: Console shows "Invalid Date" or NaN
**Fix**: Backend needs to format date differently

### Issue 2: Status Field Mismatch
**Symptom**: Console shows status as something other than 'ACTIVE'
**Check**: Console shows status value
**Fix**: Check enum serialization in backend

### Issue 3: Missing last_heartbeat Field
**Symptom**: Console shows last_heartbeat as null/undefined
**Check**: Console shows "No last_heartbeat"
**Fix**: Backend not returning the field

### Issue 4: Timezone Issue
**Symptom**: Dates look correct but comparison fails
**Check**: Compare lastHB timestamp with twoMinAgo timestamp
**Fix**: Adjust date parsing to handle timezone

### Issue 5: Cached Old Data
**Symptom**: Data doesn't change after refresh
**Check**: Check Network tab for 304 responses
**Fix**: Clear browser cache + Redis cache

## Manual Testing Commands

### Test 1: Check API Response
```bash
# Get actual API response (requires auth token)
curl -s "http://localhost:8000/api/v1/clusters" \
  -H "Authorization: Bearer YOUR_TOKEN" | jq '.clusters[0] | {name, status, last_heartbeat}'
```

### Test 2: Check Database
```bash
docker exec spot-optimizer-postgres psql -U postgres -d spot_optimizer -c "
SELECT
    name,
    status,
    last_heartbeat,
    agent_installed,
    EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) AS seconds_ago
FROM clusters;
"
```

### Test 3: Clear All Caches
```bash
# Clear Redis
docker exec spot-optimizer-redis redis-cli FLUSHALL

# Restart backend (clears internal caches)
docker restart spot-optimizer-backend
```

## Expected Console Output (If Working)

```
Status Check for spot-demo-1 {
  status: 'ACTIVE',
  last_heartbeat: '2026-02-09T12:42:54.933797',
  agent_installed: true
}
  Last HB: 2026-02-09T12:42:54.933Z
  Two min ago: 2026-02-09T12:41:19.260Z
  Is Connected: true ✅
```

Then status should show: **"Connected"** (green)

## If Console Shows Different Values

### Case 1: status is not 'ACTIVE'
```javascript
// Console shows:
status: 'DISCOVERED' // or 'PENDING', 'INACTIVE', etc.

// Problem: Backend returning wrong status
// Fix: Check cluster status in database
```

### Case 2: last_heartbeat is null
```javascript
// Console shows:
last_heartbeat: null

// Problem: Backend not including last_heartbeat in API response
// Fix: Check ClusterListItem schema includes last_heartbeat
```

### Case 3: Date parsing fails
```javascript
// Console shows:
Last HB: Invalid Date
Two min ago: 2026-02-09T12:41:19.260Z

// Problem: Date format not recognized by JavaScript
// Fix: Backend needs to return ISO 8601 format
```

### Case 4: Comparison fails despite valid dates
```javascript
// Console shows:
Last HB: 2026-02-09T12:42:54.933Z
Two min ago: 2026-02-09T12:41:19.260Z
Is Connected: false ❌

// Problem: Logic error or timezone issue
// Fix: Check if dates are being compared correctly
```

## Next Steps

1. **User Action Required**:
   - Open browser console (F12)
   - Hard refresh page (Ctrl+Shift+R)
   - Check console output
   - Share screenshot of console

2. **Once we see console output**, we can:
   - Identify exact issue
   - Apply targeted fix
   - Verify solution works

## Files Modified for Debugging

1. `/frontend/src/components/clusters/ClusterList.jsx` - Added console logging
2. `/docs/status_offline_debugging.md` - This guide

## Quick Fix Attempts (Already Done)

✅ Cleared Redis cache
✅ Verified database has correct values
✅ Verified backend includes last_heartbeat in API
✅ Verified frontend has correct logic
✅ Added debug logging

**Next: Need to see actual console output to identify the issue!**
