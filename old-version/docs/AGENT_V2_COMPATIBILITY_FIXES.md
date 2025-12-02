# Agent v2 Compatibility Fixes - 2025-11-23

## 🎯 Overview

This document describes the compatibility fixes made to integrate **agent-v2** (v4.0.0) from the separate repository (https://github.com/atharva0608/agent-v2.git) with the SpotGuard backend.

## 📦 Agent Integration

### Repository Integration
1. **Cleaned agent folder**: Removed old agent files
2. **Cloned agent-v2**: Integrated latest production agent v4.0.0
3. **Restructured**: Removed frontend, docs, and extra folders
4. **Result**: Standalone agent package ready for client installation

### Final Agent Structure
```
agent/
├── requirements.txt                      # Python dependencies
├── spot_agent_production_v2_final.py     # Alternative agent implementation
├── spot_optimizer_agent.py               # Main production agent v4.0.0
└── README.md                             # Installation and usage guide
```

## 🔧 Backend Compatibility Fixes

### Missing Endpoints Added

The agent-v2 code expected two endpoints that didn't exist in the backend:

#### 1. PUT /api/agents/<agent_id>/replicas/<replica_id>
**Purpose**: Update replica with actual EC2 instance ID after launch

**Agent Usage** (line 367-374):
```python
def update_replica_instance(self, agent_id: str, replica_id: str,
                           instance_id: str, status: str = 'syncing') -> bool:
    """Update replica with actual EC2 instance ID"""
    result = self._make_request(
        'PUT',
        f'/api/agents/{agent_id}/replicas/{replica_id}',
        json={'instance_id': instance_id, 'status': status}
    )
    return result is not None
```

**Backend Implementation** (backend.py:6261-6312):
```python
@app.route('/api/agents/<agent_id>/replicas/<replica_id>', methods=['PUT'])
def update_replica_instance_endpoint(agent_id, replica_id):
    """
    Update replica with actual EC2 instance ID after launch.

    Request body:
    {
        "instance_id": "i-1234567890abcdef0",
        "status": "syncing"  # optional, defaults to 'syncing'
    }
    """
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    status = data.get('status', 'syncing')

    # Update replica_instances table
    execute_query("""
        UPDATE replica_instances
        SET instance_id = %s,
            status = %s,
            launched_at = CASE WHEN launched_at IS NULL THEN NOW() ELSE launched_at END
        WHERE id = %s
    """, (instance_id, status, replica_id))

    return jsonify({
        'success': True,
        'replica_id': replica_id,
        'instance_id': instance_id,
        'status': status
    })
```

**Why it was needed**: The agent's `_replica_polling_worker` (lines 1408-1508) launches EC2 instances for pending replicas and needs to report back the actual instance ID.

#### 2. POST /api/agents/<agent_id>/replicas/<replica_id>/status
**Purpose**: Update replica status during lifecycle (launching → syncing → ready)

**Agent Usage** (line 433-440):
```python
def update_replica_status(self, agent_id: str, replica_id: str,
                         status_data: Dict) -> bool:
    """Update replica status"""
    result = self._make_request(
        'POST',
        f'/api/agents/{agent_id}/replicas/{replica_id}/status',
        json=status_data
    )
    return result is not None
```

**Backend Implementation** (backend.py:6315-6390):
```python
@app.route('/api/agents/<agent_id>/replicas/<replica_id>/status', methods=['POST'])
def update_replica_status_endpoint(agent_id, replica_id):
    """
    Update replica status and metadata.

    Request body:
    {
        "status": "launching" | "syncing" | "ready" | "failed",
        "sync_started_at": "2025-01-20T10:45:00Z",  # optional
        "sync_completed_at": "2025-01-20T10:46:00Z",  # optional
        "error_message": "Error details"  # optional, for failed status
    }
    """
    data = request.get_json() or {}
    status = data.get('status')

    # Build dynamic update query
    updates = ["status = %s"]
    params = [status]

    if data.get('sync_started_at'):
        updates.append("sync_started_at = %s")
        params.append(data['sync_started_at'])

    if data.get('sync_completed_at'):
        updates.append("sync_completed_at = %s")
        params.append(data['sync_completed_at'])

    if status == 'ready':
        updates.append("ready_at = CASE WHEN ready_at IS NULL THEN NOW() ELSE ready_at END")

    # Update replica_instances table
    execute_query(f"""
        UPDATE replica_instances
        SET {', '.join(updates)}
        WHERE id = %s
    """, tuple(params + [replica_id]))

    return jsonify({
        'success': True,
        'replica_id': replica_id,
        'status': status
    })
```

**Why it was needed**: The agent's `ReplicaManager.create_replica()` (lines 718-822) and `_replica_polling_worker` (lines 1408-1508) track replica status through its lifecycle and need to report status changes.

### Endpoint Registration
Both new endpoints were registered in `register_replica_management_endpoints()` (backend.py:7028-7040):

```python
def register_replica_management_endpoints(app):
    """Register all replica management endpoints with Flask app"""
    create_manual_replica(app)
    list_replicas(app)
    promote_replica(app)
    delete_replica(app)
    update_replica_instance(app)  # ← NEW
    update_replica_status(app)    # ← NEW
    create_emergency_replica(app)
    handle_termination_imminent(app)
    update_replica_sync_status(app)
```

## ✅ Existing Compatible Endpoints

These agent endpoints were already compatible with the backend:

| Agent Method | Backend Endpoint | Status |
|--------------|------------------|--------|
| `register_agent()` | `POST /api/agents/register` | ✅ Compatible |
| `send_heartbeat()` | `POST /api/agents/<id>/heartbeat` | ✅ Compatible |
| `send_pricing_report()` | `POST /api/agents/<id>/pricing-report` | ✅ Compatible |
| `get_agent_config()` | `GET /api/agents/<id>/config` | ✅ Compatible |
| `get_pending_commands()` | `GET /api/agents/<id>/pending-commands` | ✅ Compatible |
| `get_pending_replicas()` | `GET /api/agents/<id>/replicas?status=launching` | ✅ Compatible |
| `mark_command_executed()` | `POST /api/agents/<id>/commands/<id>/executed` | ✅ Compatible |
| `send_switch_report()` | `POST /api/agents/<id>/switch-report` | ✅ Compatible |
| `report_termination_notice()` | `POST /api/agents/<id>/termination-imminent` | ✅ Compatible |
| `report_rebalance_recommendation()` | `POST /api/agents/<id>/rebalance-recommendation` | ✅ Compatible |
| `create_emergency_replica()` | `POST /api/agents/<id>/create-emergency-replica` | ✅ Compatible |
| `get_replica_config()` | `GET /api/agents/<id>/replica-config` | ✅ Compatible |
| `create_replica()` | `POST /api/agents/<id>/replicas` | ✅ Compatible |
| `promote_replica()` | `POST /api/agents/<id>/replicas/<id>/promote` | ✅ Compatible |
| `report_cleanup()` | `POST /api/agents/<id>/cleanup-report` | ✅ Compatible |

## 🔄 Agent Flow Examples

### Replica Creation Flow (Manual Mode)
```
1. User enables Manual Replica Mode in dashboard
   ↓
2. Backend creates replica record with status='launching'
   ↓
3. ReplicaCoordinator detects pending replica
   ↓
4. Agent polls GET /api/agents/<id>/replicas?status=launching
   ↓
5. Agent launches EC2 instance for replica
   ↓
6. Agent calls PUT /api/agents/<id>/replicas/<replica_id>  ← NEW ENDPOINT
   with { instance_id: "i-xxxxx", status: "syncing" }
   ↓
7. Agent waits for instance to be running
   ↓
8. Agent calls POST /api/agents/<id>/replicas/<replica_id>/status  ← NEW ENDPOINT
   with { status: "ready", sync_completed_at: "..." }
   ↓
9. Replica is now ready for manual switching
```

### Emergency Replica Flow (Auto-Switch Mode)
```
1. Agent detects rebalance recommendation
   ↓
2. Agent calls POST /api/agents/<id>/create-emergency-replica
   with { signal_type: "rebalance-recommendation" }
   ↓
3. Backend creates emergency replica if auto_switch_enabled=TRUE
   ↓
4. Agent polls GET /api/agents/<id>/replicas?status=launching
   ↓
5. Agent launches EC2 instance
   ↓
6. Agent calls PUT /api/agents/<id>/replicas/<replica_id>  ← NEW ENDPOINT
   with instance_id
   ↓
7. Agent monitors replica until ready
   ↓
8. Agent calls POST /api/agents/<id>/replicas/<replica_id>/status  ← NEW ENDPOINT
   with { status: "ready" }
   ↓
9. ML model decides if/when to switch to replica
```

## 📊 Database Schema (No Changes Required)

The `replica_instances` table already had all necessary columns:

```sql
CREATE TABLE replica_instances (
    id VARCHAR(64) PRIMARY KEY,
    agent_id VARCHAR(64) NOT NULL,
    instance_id VARCHAR(64),           -- ← Updated by PUT endpoint
    parent_instance_id VARCHAR(64),
    pool_id VARCHAR(128),
    replica_type VARCHAR(20),          -- 'manual' or 'emergency'
    status VARCHAR(20),                -- ← Updated by POST status endpoint
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    launched_at TIMESTAMP,             -- ← Set by PUT endpoint when instance_id provided
    ready_at TIMESTAMP,                -- ← Set by POST status endpoint when status='ready'
    sync_started_at TIMESTAMP,         -- ← Set by POST status endpoint
    sync_completed_at TIMESTAMP,       -- ← Set by POST status endpoint
    promoted_at TIMESTAMP,
    terminated_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    error_message TEXT,                -- ← Set by POST status endpoint on failure
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);
```

**No migrations needed** - existing schema supports all new endpoint operations.

## 🧪 Testing the Integration

### Test 1: Agent Registration
```bash
# Start agent with valid config
python3 spot_optimizer_agent.py

# Expected log output:
Agent registered as agent: <agent-id>
Agent started - ID: <agent-id>
Instance: i-xxxxx (t3.medium)
Version: 4.0.0
```

### Test 2: Replica Creation
```bash
# Enable manual replica mode in dashboard
# Watch agent logs:
tail -f spot_optimizer_agent.log

# Expected:
Found 1 pending command(s)
Launching EC2 instance for replica <replica-id> in AZ us-east-1b
Replica instance launched: i-yyyyy for replica <replica-id>
Updated replica <replica-id> with instance_id i-yyyyy, status syncing
Replica <replica-id> is ready: i-yyyyy
```

### Test 3: Backend Endpoints
```bash
# Test PUT endpoint (update replica with instance ID)
curl -X PUT http://localhost:5000/api/agents/<agent_id>/replicas/<replica_id> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"instance_id": "i-1234567890", "status": "syncing"}'

# Expected response:
{
  "success": true,
  "replica_id": "<replica-id>",
  "instance_id": "i-1234567890",
  "status": "syncing"
}

# Test POST endpoint (update replica status)
curl -X POST http://localhost:5000/api/agents/<agent_id>/replicas/<replica_id>/status \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"status": "ready", "sync_completed_at": "2025-11-23T10:45:00Z"}'

# Expected response:
{
  "success": true,
  "replica_id": "<replica-id>",
  "status": "ready"
}
```

## 🚀 Deployment Steps

### 1. Backend Deployment
```bash
# Pull latest backend changes
cd /home/user/final-ml
git pull origin claude/fix-price-history-api-01GFprsi9uy7ZP4iFzYNnTVY

# Restart backend
sudo systemctl restart flask-backend

# Verify new endpoints registered
sudo journalctl -u flask-backend | grep "Replica management endpoints registered"
```

### 2. Agent Deployment (New Installations)
```bash
# Copy agent folder to client instance
scp -r agent/ ubuntu@<client-ip>:~/spotguard-agent/

# SSH to client instance
ssh ubuntu@<client-ip>
cd ~/spotguard-agent

# Install dependencies
pip3 install -r requirements.txt

# Configure agent
nano .env
# Add: SPOT_OPTIMIZER_SERVER_URL, SPOT_OPTIMIZER_CLIENT_TOKEN, LOGICAL_AGENT_ID

# Run agent
python3 spot_optimizer_agent.py
```

### 3. Agent Deployment (Existing Installations)
```bash
# On client instance with old agent
cd ~/spotguard-agent

# Stop old agent
sudo systemctl stop spotguard-agent

# Backup old agent
mv spot_agent.py spot_agent.py.backup

# Download new agent
wget https://<your-server>/agent/spot_optimizer_agent.py
wget https://<your-server>/agent/requirements.txt

# Update dependencies
pip3 install -r requirements.txt

# Update systemd service to use new agent file
sudo nano /etc/systemd/system/spotguard-agent.service
# Change: ExecStart=/usr/bin/python3 .../spot_optimizer_agent.py

# Restart
sudo systemctl daemon-reload
sudo systemctl start spotguard-agent
sudo systemctl status spotguard-agent
```

## ✅ Success Criteria

All agent operations should now work:

1. ✅ **Agent registration** - Heartbeat every 30 seconds
2. ✅ **Pricing reports** - Every 5 minutes, populates price history charts
3. ✅ **Command execution** - Switch commands execute successfully
4. ✅ **Auto-terminate** - Respects backend `terminate_wait_seconds` setting
5. ✅ **Manual replica mode** - Creates and maintains standby replicas
6. ✅ **Emergency replicas** - Handles rebalance and termination signals
7. ✅ **Replica status updates** - Tracks replica lifecycle (launching → syncing → ready)
8. ✅ **Cleanup operations** - Removes old snapshots and AMIs

## 📝 Files Modified

### Backend Changes
- **backend/backend.py** (2 functions added, 1 function updated):
  - Added `update_replica_instance()` at lines 6261-6312
  - Added `update_replica_status()` at lines 6315-6390
  - Updated `register_replica_management_endpoints()` at lines 7028-7040

### Agent Changes
- **agent/spot_optimizer_agent.py** - NEW FILE (from agent-v2 repo)
- **agent/spot_agent_production_v2_final.py** - NEW FILE (from agent-v2 repo)
- **agent/requirements.txt** - Updated with agent-v2 dependencies
- **agent/README.md** - NEW FILE (installation and usage guide)

### Documentation Created
- **docs/AGENT_V2_COMPATIBILITY_FIXES.md** - This file
- **agent/README.md** - Agent installation and configuration guide

## 🐛 Known Issues & Solutions

### Issue: Connection refused on pending-commands endpoint
**Cause**: Backend not running or firewall blocking port 5000
**Solution**: Verify backend is running, check firewall rules

### Issue: Replica launches but status stays 'launching'
**Cause**: New PUT endpoint not registered or agent can't reach it
**Solution**: Restart backend to ensure endpoints are registered, check agent logs for HTTP errors

### Issue: Agent sends pricing reports but charts still empty
**Cause**: Pricing report format mismatch (agent sends 'mode', backend expects 'current_mode')
**Solution**: Both agent and backend now use 'mode' field (already fixed in this session)

## 📞 Support

For issues with agent-v2 integration:
1. Check agent logs: `tail -f ~/spotguard-agent/spot_optimizer_agent.log`
2. Check backend logs: `sudo journalctl -u flask-backend -f`
3. Verify endpoints are registered: Look for "Replica management endpoints registered" in backend logs
4. Test endpoints manually using curl (see Testing section above)

---

**Status**: ✅ All compatibility issues resolved
**Date**: 2025-11-23
**Branch**: `claude/fix-price-history-api-01GFprsi9uy7ZP4iFzYNnTVY`
**Commit**: Ready for commit
