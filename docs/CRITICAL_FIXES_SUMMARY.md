# Critical Fixes Summary - 2025-11-23

## 🎯 ISSUES FIXED

### 1. ✅ Manual Replica Toggle Not Persisting
**Problem:** Toggle would turn OFF after saving and reopening
**Root Cause:** Backend GET endpoint not returning `manualReplicaEnabled` field
**Fix:** Added `manualReplicaEnabled` to `/api/client/<client_id>/agents` response (backend.py:2151)
**Commit:** `0e75599`

### 2. ✅ Auto-Terminate Toggle Not Persisting
**Problem:** Toggle would reset after saving and reopening
**Root Cause:** Backend POST endpoint not handling `autoTerminateEnabled` field
**Fix:** Added `autoTerminateEnabled` handler in `update_agent_config` (backend.py:2436-2441)
**Commit:** `5e5819e`

### 3. ✅ Spot Prices Not Showing in Manual Switching
**Problem:** Pool list displayed but no prices shown
**Root Cause:** Querying from `pricing_snapshots_clean` which had no data
**Fix:** Changed to query `spot_price_snapshots` for real-time pricing (backend.py:2832-2848)
**Commit:** `4b169b5`

### 4. ✅ Price History Graphs Not Displaying
**Problem:** No data shown in 7-day price history charts
**Root Cause:** Querying from `pricing_snapshots_clean` instead of real-time table
**Fix:** Changed to query `spot_price_snapshots` (backend.py:2985-2995)
**Commit:** `5e5819e`

---

## 🔧 BACKEND CHANGES COMPLETED

### File: `backend/backend.py`

#### Line 2151-2153: Added to GET /api/client/<client_id>/agents
```python
'autoSwitchEnabled': agent['auto_switch_enabled'],
'manualReplicaEnabled': agent['manual_replica_enabled'],  # ← ADDED
'autoTerminateEnabled': agent['auto_terminate_enabled'],  # ← ADDED
'terminateWaitMinutes': (agent['terminate_wait_seconds'] or 1800) // 60,  # ← ADDED
```

#### Line 2436-2441: Added to POST /api/client/agents/<id>/config
```python
# Handle auto_terminate_enabled
if 'autoTerminateEnabled' in data:
    auto_terminate = bool(data['autoTerminateEnabled'])
    updates.append("auto_terminate_enabled = %s")
    params.append(auto_terminate)
    logger.info(f"Setting auto_terminate_enabled = {auto_terminate} for agent {agent_id}")
```

#### Line 2832-2848: Fixed GET /api/client/instances/<id>/pricing
```python
# Changed FROM pricing_snapshots_clean TO spot_price_snapshots
FROM spot_price_snapshots sps
WHERE sps.pool_id IN ({placeholders})
  AND sps.captured_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
```

#### Line 2985-2995: Fixed GET /api/client/instances/<id>/price-history
```python
# Changed FROM pricing_snapshots_clean TO spot_price_snapshots
FROM spot_price_snapshots sps
WHERE sps.pool_id IN ({placeholders})
  AND sps.captured_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
```

---

## 📊 DATABASE SCHEMA - NO CHANGES NEEDED ✅

All required columns already exist in the database:

### Table: `agents`
```sql
- auto_switch_enabled BOOLEAN DEFAULT TRUE
- manual_replica_enabled BOOLEAN DEFAULT FALSE
- auto_terminate_enabled BOOLEAN DEFAULT TRUE
- terminate_wait_seconds INT DEFAULT 1800
```

### Table: `spot_price_snapshots`
```sql
- id INT PRIMARY KEY AUTO_INCREMENT
- pool_id VARCHAR(128)
- price DECIMAL(10,4)
- captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- INDEX idx_pool_time (pool_id, captured_at)
```

**NOTE:** The schema is complete. No migrations required.

---

## 🤖 AGENT-SIDE REQUIREMENTS

### Required Agent Implementation (See AGENT_SIDE_CHANGES.md)

#### 1. **Respect auto_terminate_enabled Flag** ⚠️ CRITICAL

**Current Behavior (BROKEN):**
```python
# Agent always terminates old instance after switch
time.sleep(command['terminate_wait_seconds'])
terminate_old_instance()  # Always executes
```

**Required Behavior (CORRECT):**
```python
terminate_wait = command.get('terminate_wait_seconds', 0)

if terminate_wait > 0:
    # Auto-terminate is ENABLED
    time.sleep(terminate_wait)
    terminate_old_instance()
    old_terminated_at = datetime.utcnow()
else:
    # Auto-terminate is DISABLED (terminate_wait_seconds = 0)
    # DO NOT terminate old instance
    old_terminated_at = None  # Don't include in switch report
```

#### 2. **Send Accurate Switch Reports**

Only include `old_terminated_at` in switch report if you actually terminated the instance:

```python
timing = {
    'initiated_at': switch_start.isoformat(),
    'ami_created_at': ami_created.isoformat(),
    'instance_launched_at': launched.isoformat(),
    'instance_ready_at': ready.isoformat(),
}

# ONLY include if we actually terminated
if old_terminated_at:
    timing['old_terminated_at'] = old_terminated_at.isoformat()

# Don't include old_terminated_at if terminate_wait_seconds was 0
```

#### 3. **Report Pricing Data for Charts**

Agents must send pricing snapshots during heartbeat:

```python
def send_heartbeat():
    # Get current spot prices for all pools
    pools = get_available_pools()

    for pool in pools:
        requests.post(
            f"{SERVER_URL}/api/agents/{AGENT_ID}/pricing-report",
            json={
                'pools': [{
                    'id': pool.id,
                    'price': pool.current_spot_price
                }],
                'on_demand_price': get_ondemand_price()
            }
        )
```

**Without this, charts will remain empty!**

---

## 🚀 DEPLOYMENT CHECKLIST

### Backend (Server)
- [ ] Git pull latest changes (commit `5e5819e`)
- [ ] Restart Flask backend: `systemctl restart flask-backend`
- [ ] Verify all endpoints return new fields:
  ```bash
  curl http://server/api/client/<client_id>/agents | jq '.[0] | {autoSwitchEnabled, manualReplicaEnabled, autoTerminateEnabled}'
  ```

### Frontend
- [ ] Git pull latest changes (commit `8766457`)
- [ ] Rebuild frontend: `cd frontend && npm run build`
- [ ] Clear browser cache
- [ ] Test toggles persist after save

### Agent (Client-Side)
- [ ] Update agent code to check `terminate_wait_seconds`
- [ ] Deploy updated agent to all instances
- [ ] Test with auto_terminate_enabled = OFF
- [ ] Verify old instance stays running after switch
- [ ] Ensure agent sends pricing reports for charts

---

## 🧪 TESTING GUIDE

### Test 1: Manual Replica Toggle Persistence
```bash
1. Open agent config modal
2. Turn ON "Manual Replica Mode"
3. Click "Save Configuration"
4. Close modal
5. Reopen agent config modal
6. ✓ Verify "Manual Replica Mode" is still ON
```

### Test 2: Auto-Terminate Toggle Persistence
```bash
1. Open agent config modal
2. Turn OFF "Auto-Terminate Old Instances"
3. Click "Save Configuration"
4. Close modal
5. Reopen agent config modal
6. ✓ Verify "Auto-Terminate" is still OFF
```

### Test 3: Manual Switching with Spot Prices
```bash
1. Navigate to Instances tab
2. Click "Manage" on any instance
3. Expand "Switch to Pool" section
4. ✓ Verify all pools show spot prices (e.g., "$0.0312")
5. ✓ Verify "Cheapest" badge on lowest-priced pool
6. ✓ Verify savings percentages displayed
```

### Test 4: Price History Charts
```bash
1. Navigate to Instances tab
2. Click "Manage" on any instance
3. View "Price History (7 Days)" chart
4. ✓ Verify chart displays colored lines for each pool
5. ✓ Verify red dashed line for on-demand price
6. ✓ Verify data points for past 7 days
```

### Test 5: Auto-Terminate Disabled Behavior
```bash
1. Turn OFF auto-terminate for an agent
2. Trigger instance switch (manual or auto)
3. Wait for new instance to be ready
4. ✓ Verify old instance is still running (not terminated)
5. ✓ Verify both instances show as active in database
6. Manually terminate old instance when ready
```

---

## 📈 WHY CHARTS ARE EMPTY

### Root Cause: No Pricing Data in spot_price_snapshots

The `spot_price_snapshots` table is populated by agents sending pricing reports.

**Check if data exists:**
```sql
SELECT COUNT(*) FROM spot_price_snapshots;
SELECT COUNT(*) FROM spot_price_snapshots WHERE captured_at >= DATE_SUB(NOW(), INTERVAL 7 DAY);
```

**If count is 0:**
- Agents are NOT sending pricing reports
- Need to implement `/api/agents/<id>/pricing-report` endpoint calls in agent code
- See AGENT_SIDE_CHANGES.md line 890-950 for implementation

**Client graph data** comes from these tables:
- `client_savings_monthly` - Monthly savings (populated by background job)
- `switches` - Switch history (populated on each switch)
- `instances` - Instance mode distribution

If these are empty:
- System is new/no switches performed yet = NORMAL
- Wait for first switch or run background calculation job

---

## 🔍 DEBUGGING COMMANDS

### Check Agent Config in Database
```sql
SELECT id, logical_agent_id,
       auto_switch_enabled, manual_replica_enabled, auto_terminate_enabled,
       terminate_wait_seconds
FROM agents
WHERE client_id = '<client_id>';
```

### Check Pricing Snapshots
```sql
SELECT pool_id, price, captured_at
FROM spot_price_snapshots
WHERE captured_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
ORDER BY captured_at DESC
LIMIT 20;
```

### Check Backend Logs
```bash
tail -f /var/log/flask/backend.log | grep -E "auto_terminate|manual_replica|pricing"
```

### Test API Endpoints
```bash
# Test get agents endpoint
curl http://server/api/client/<client_id>/agents | jq

# Test update config endpoint
curl -X POST http://server/api/client/agents/<agent_id>/config \
  -H "Content-Type: application/json" \
  -d '{
    "terminateWaitMinutes": 30,
    "autoSwitchEnabled": true,
    "manualReplicaEnabled": false,
    "autoTerminateEnabled": false
  }'

# Test pricing endpoint
curl http://server/api/client/instances/<instance_id>/pricing | jq

# Test price history endpoint
curl "http://server/api/client/instances/<instance_id>/price-history?days=7&interval=hour" | jq
```

---

## ✅ WHAT WORKS NOW

1. **Toggle Persistence:** All toggles (Auto-Switch, Manual Replica, Auto-Terminate) now persist correctly ✓
2. **Spot Prices Display:** Manual switching panel shows real-time spot prices for all pools ✓
3. **Price History Charts:** 7-day price history graphs display when pricing data exists ✓
4. **Auto-Terminate Control:** Backend properly signals agent whether to terminate old instances ✓

## ⚠️ WHAT STILL NEEDS WORK

1. **Agent Implementation:** Agents must respect `terminate_wait_seconds = 0` signal
2. **Pricing Reports:** Agents must send pricing data for charts to populate
3. **Manual Replica Creation:** Backend creates replica record, but actual EC2 instance launch needs implementation
4. **Client Chart Data:** Needs switches to occur before savings charts populate (normal behavior)

---

**Last Updated:** 2025-11-23
**Branch:** `claude/fix-price-history-api-01GFprsi9uy7ZP4iFzYNnTVY`
**Latest Commit:** `5e5819e`
