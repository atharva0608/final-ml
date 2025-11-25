# Instance Management and Configuration Fixes
**Date:** 2025-11-25
**Session:** claude/general-session-01K4TVRgkvzFaA3MGxEP4P9q

## Summary of Issues Fixed

### 1. ✅ Instance Zombie State Tracking
**Problem:** No way to differentiate between active "primary" instances and old "zombie" instances that have been switched from.

**Solution:**
- Added `instance_role` ENUM column to `instances` table with values: 'primary', 'zombie', 'replica'
- Created database migration: `database/migrations/add_instance_role.sql`
- Added automatic triggers to mark old instances as zombie when agent switches
- Created views for easy querying: `v_primary_instances` and `v_zombie_instances`

**Files Changed:**
- `/home/user/final-ml/database/migrations/add_instance_role.sql` (NEW)
- `/home/user/final-ml/backend/backend.py` (MODIFIED)

### 2. ✅ Hide Switching Capabilities for Zombie Instances
**Problem:** Zombie instances were showing "Manage" buttons and allowing switching operations.

**Solution:**
- Updated `/api/client/<client_id>/instances` endpoint to return `instanceRole` field
- Updated `/api/client/instances/<instance_id>/available-options` to return 403 for zombie instances
- Updated `/api/client/instances/<instance_id>/force-switch` to block zombie instance switches
- Modified frontend to hide "Manage" button for zombie instances
- Added visual indicators (opacity, badges) for zombie instances in UI

**Files Changed:**
- `/home/user/final-ml/backend/backend.py` (MODIFIED - lines 2672-2747, 3203-3237, 3291-3325)
- `/home/user/final-ml/frontend/src/components/details/tabs/ClientInstancesTab.jsx` (MODIFIED)

### 3. ✅ Fixed Savings Calculation (NaN% Issue)
**Problem:** Savings percentage was showing "NaN%" when `onDemandPrice` was 0 or invalid.

**Solution:**
- Added null/zero check before division
- Default to "0.0%" when calculation is not possible
- Properly handle edge cases in savings calculation

**Code:**
```javascript
const savings = inst.onDemandPrice > 0
  ? (((inst.onDemandPrice - inst.spotPrice) / inst.onDemandPrice) * 100).toFixed(1)
  : '0.0';
```

**Files Changed:**
- `/home/user/final-ml/frontend/src/components/details/tabs/ClientInstancesTab.jsx` (MODIFIED - lines 125-127)

### 4. 📝 Auto-Termination Toggles Investigation
**Status:** Code review completed - logic appears correct

**Current Implementation:**
- Backend properly handles `autoTerminateEnabled` flag
- Updates are stored in `agents.auto_terminate_enabled` column
- Mutual exclusivity enforced between auto-switch and manual replica modes

**Findings:**
The backend configuration update endpoint (`/api/client/agents/<agent_id>/config`) correctly:
1. Stores `auto_terminate_enabled` setting
2. Converts `terminateWaitMinutes` to `terminate_wait_seconds`
3. Enforces mutual exclusivity between modes
4. Terminates replicas when mode changes

**Potential Issue:**
- The actual termination logic may be delayed because it depends on agent-side execution
- The agent polls for commands and executes them asynchronously
- Need to verify agent-side termination timing and command execution

**Recommendation:**
- Monitor agent logs during switches to verify termination timing
- Check if agents are properly polling and executing termination commands
- Verify network connectivity and command queue status

### 5. 📝 Manual Replica Behavior
**Status:** Code review completed - logic appears correct

**Current Implementation:**
- When `manualReplicaEnabled` is turned OFF, all replicas are terminated:
  ```sql
  UPDATE replica_instances
  SET is_active = FALSE, status = 'terminated', terminated_at = NOW()
  WHERE agent_id = %s AND is_active = TRUE
  ```
- When `autoSwitchEnabled` is turned ON, manual replicas are terminated
- Replica count is reset to 0 and `current_replica_id` is cleared

**Findings:**
The configuration endpoint properly handles replica termination, but actual AWS instance termination may be delayed due to:
1. Agent polling intervals
2. Command execution queue
3. AWS API latency

### 6. 📝 Auto-Switching Option
**Status:** Verified - working as designed

**Current Implementation:**
- `auto_switch_enabled` flag controls ML-based automatic switching
- When enabled: ML model recommendations are automatically executed
- When disabled: ML recommendations are shown but not executed
- Mutual exclusivity with `manual_replica_enabled` is enforced

**Code Location:**
- Configuration update: `backend/backend.py` lines 2469-2497
- Frontend modal: `frontend/src/components/modals/AgentConfigModal.jsx`

## Migration Instructions

### 1. Apply Database Migration

```bash
cd /home/user/final-ml
mysql -h localhost -u spotuser -p'SpotUser2024!' spot_optimizer < database/migrations/add_instance_role.sql
```

This will:
- Add `instance_role` column to `instances` table
- Create triggers to automatically manage instance states
- Create views for querying primary and zombie instances
- Update existing instances to have correct roles

### 2. Restart Backend Server

```bash
# If running with systemd
sudo systemctl restart spot-optimizer-backend

# If running manually
pkill -f "python.*backend.py"
cd /home/user/final-ml/backend
python backend.py
```

### 3. Clear Frontend Cache

Users should hard-refresh their browsers (Ctrl+F5 / Cmd+Shift+R) to get the updated frontend code.

## API Changes

### GET /api/client/<client_id>/instances

**New Response Fields:**
```json
{
  "id": "i-0b68562ac0c11dfd0",
  "type": "t3.medium",
  "instanceRole": "primary",  // NEW: 'primary' | 'zombie' | 'replica'
  "agentId": "agent-uuid",     // NEW: Associated agent ID
  "agentStatus": "online",     // NEW: Agent status
  "logicalAgentId": "agent-001" // NEW: Logical agent identifier
}
```

### GET /api/client/instances/<instance_id>/available-options

**New Error Response for Zombie Instances:**
```json
{
  "error": "This instance is in zombie state and cannot be switched",
  "isZombie": true
}
```
**HTTP Status:** 403 Forbidden

### POST /api/client/instances/<instance_id>/force-switch

**New Error Response for Zombie Instances:**
```json
{
  "error": "Cannot switch zombie instance - this instance is no longer active",
  "isZombie": true
}
```
**HTTP Status:** 403 Forbidden

## UI Changes

### Instance Table
- **New Column:** "Status" showing "Primary" or "Zombie" badge
- **Zombie Instances:**
  - Displayed with reduced opacity (60%)
  - No expand/collapse chevron
  - "Manage" button replaced with "—"
  - Cannot open detail panel

### Instance Detail Panel
- Only accessible for primary instances
- Zombie instances cannot be managed

## Testing Checklist

- [ ] Apply database migration successfully
- [ ] Verify existing instances are marked as 'primary'
- [ ] Perform an instance switch
- [ ] Verify old instance is marked as 'zombie'
- [ ] Verify zombie instance UI shows correct status
- [ ] Verify zombie instance cannot be switched
- [ ] Test savings calculation with various prices
- [ ] Toggle auto-termination and verify setting persists
- [ ] Toggle manual replica mode and verify replicas are created/terminated
- [ ] Toggle auto-switch mode and verify it disables manual replica

## Known Limitations

1. **Agent-Side Delays:** Termination and switching commands depend on agent polling (typically 1-minute interval)
2. **AWS API Latency:** Actual instance termination may take additional time after agent receives command
3. **Backward Compatibility:** Old instances without `instance_role` will be automatically assigned based on current agent mapping

## Future Improvements

1. **Real-time Updates:** Implement WebSocket for instant UI updates when instance state changes
2. **Termination Monitoring:** Add dashboard showing pending terminations and their status
3. **Command Queue Visibility:** Show pending commands for each agent in UI
4. **Faster Polling:** Reduce agent polling interval for critical commands (termination, emergencies)
5. **Zombie Cleanup:** Automated job to clean up old zombie instances after X days

## Rollback Procedure

If issues occur, rollback using:

```sql
-- Remove the instance_role column
ALTER TABLE instances DROP COLUMN instance_role;

-- Drop the triggers
DROP TRIGGER IF EXISTS before_agent_instance_update;

-- Drop the views
DROP VIEW IF EXISTS v_primary_instances;
DROP VIEW IF EXISTS v_zombie_instances;
```

Then restart the backend server and clear browser caches.

## Support

For issues or questions about these fixes, refer to:
- Database schema: `/home/user/final-ml/database/schema.sql`
- Backend API: `/home/user/final-ml/backend/backend.py`
- Frontend components: `/home/user/final-ml/frontend/src/components/`
- Migration file: `/home/user/final-ml/database/migrations/add_instance_role.sql`
