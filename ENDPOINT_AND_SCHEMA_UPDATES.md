# Backend Endpoint and Schema Updates - v4.2

## Summary

This document outlines the backend endpoints created and schema cleanup performed to synchronize with the frontend repository (`https://github.com/atharva0608/frontend-.git`).

---

## 1. New Backend Endpoints Created

### 1.1 Get All Instances (Global Admin View)

**Endpoint:** `GET /api/admin/instances`

**Purpose:** Retrieve all instances across all clients in a single API call, replacing the frontend workaround that fetched instances client-by-client.

**Query Parameters:**
- `status` (optional): Filter by status (e.g., `active`, `terminated`)
- `mode` (optional): Filter by mode (e.g., `spot`, `ondemand`)
- `region` (optional): Filter by AWS region (e.g., `us-east-1`)

**Response:**
```json
{
  "instances": [
    {
      "id": "i-1234567890abcdef0",
      "instanceType": "t3.medium",
      "region": "us-east-1",
      "az": "us-east-1a",
      "currentMode": "spot",
      "currentPoolId": "t3.medium.us-east-1a",
      "spotPrice": 0.0312,
      "ondemandPrice": 0.0416,
      "isActive": true,
      "clientId": "client-uuid-123",
      "clientName": "Acme Corp",
      "agentId": "agent-uuid-456",
      "installedAt": "2025-01-15T10:30:00Z",
      "lastSwitchAt": "2025-01-18T14:22:00Z"
    }
  ],
  "total": 42,
  "filters": {
    "status": "active",
    "mode": "spot"
  }
}
```

**Backend Location:** `backend.py` lines 1434-1495

---

### 1.2 Get All Agents (Global Admin View)

**Endpoint:** `GET /api/admin/agents`

**Purpose:** Retrieve all agents across all clients in a single API call, replacing the frontend workaround that fetched agents client-by-client.

**Query Parameters:**
- `status` (optional): Filter by status (e.g., `online`, `offline`)

**Response:**
```json
{
  "agents": [
    {
      "id": "agent-uuid-456",
      "logicalAgentId": "prod-web-01",
      "hostname": "web-server-prod",
      "instanceId": "i-1234567890abcdef0",
      "instanceType": "t3.medium",
      "region": "us-east-1",
      "az": "us-east-1a",
      "currentMode": "spot",
      "currentPoolId": "t3.medium.us-east-1a",
      "status": "online",
      "enabled": true,
      "autoSwitchEnabled": true,
      "lastHeartbeatAt": "2025-01-19T08:45:00Z",
      "clientId": "client-uuid-123",
      "clientName": "Acme Corp",
      "agentVersion": "4.0.0"
    }
  ],
  "total": 15,
  "filters": {
    "status": "online"
  }
}
```

**Backend Location:** `backend.py` lines 1497-1549

---

### 1.3 Get Instance Price History

**Endpoint:** `GET /api/client/instances/<instance_id>/price-history`

**Purpose:** Retrieve historical pricing data for a specific instance to show price trends over time.

**Query Parameters:**
- `days` (optional, default: 7): Number of days of history to retrieve
- `interval` (optional, default: `hour`): Granularity of data points (`hour` or `day`)

**Response:**
```json
{
  "instanceId": "i-1234567890abcdef0",
  "days": 7,
  "interval": "hour",
  "history": [
    {
      "time": "2025-01-19T08:00:00Z",
      "avgPrice": 0.0315,
      "minPrice": 0.0310,
      "maxPrice": 0.0320,
      "avgOnDemand": 0.0416
    },
    {
      "time": "2025-01-19T09:00:00Z",
      "avgPrice": 0.0318,
      "minPrice": 0.0312,
      "maxPrice": 0.0325,
      "avgOnDemand": 0.0416
    }
  ],
  "dataPoints": 168
}
```

**Backend Location:** `backend.py` lines 1943-2009

---

## 2. Schema Cleanup (v5.1 → v6.0)

### 2.1 Removed Tables (6 total)

The following tables were present in `schema.sql` v5.1 but were **never queried** by the backend:

1. **`audit_logs`** - Comprehensive audit trail (unused)
2. **`cost_records`** - Cost tracking records (never populated)
3. **`model_predictions`** - ML predictions (replaced by `decision_engine_log`)
4. **`ondemand_prices`** - Current on-demand prices (duplicate of `ondemand_price_snapshots`)
5. **`replicas`** - Replica management (feature not implemented)
6. **`spot_prices`** - Current spot prices (duplicate of `spot_price_snapshots`)

**Impact:** Reduces database complexity, removes ~6 unused tables, simplifies maintenance.

---

### 2.2 Removed Views (3 total)

1. **`agent_overview`** - Agent summary with pricing (unused)
2. **`client_savings_summary`** - Client savings aggregation (unused)
3. **`active_spot_pools`** - Active pools with latest prices (unused)

**Kept View:**
- `recent_switches` - Used by backend to display recent switch activity

---

### 2.3 Removed Stored Procedures (11 total)

All stored procedures were removed as **none** were called by the backend:

1. `register_agent`
2. `get_pending_commands`
3. `mark_command_executed`
4. `get_cheapest_pool`
5. `calculate_agent_savings`
6. `calculate_client_savings`
7. `check_switch_limits`
8. `update_spot_pool_prices`
9. `cleanup_old_data`
10. `update_client_total_savings`
11. `compute_monthly_savings`

**Rationale:** Backend uses direct SQL queries instead of stored procedures for better maintainability and debugging.

---

### 2.4 Removed Events (4 total)

All MySQL scheduled events were removed:

1. `evt_daily_cleanup` - Daily data cleanup
2. `evt_mark_stale_agents` - Mark offline agents
3. `evt_compute_monthly_savings` - Monthly aggregation
4. `evt_update_total_savings` - Update client totals

**Rationale:** Backend handles these operations programmatically through APScheduler or on-demand API calls.

---

### 2.5 Kept Tables (19 total)

All remaining tables are **actively used** by the backend:

| Table Name | Purpose |
|------------|---------|
| `clients` | Client accounts |
| `agents` | Agent instances |
| `agent_configs` | Agent configuration |
| `commands` | Command queue |
| `spot_pools` | Available spot pools |
| `spot_price_snapshots` | Historical spot prices |
| `ondemand_price_snapshots` | Historical on-demand prices |
| `pricing_reports` | Agent pricing reports |
| `instances` | Instance tracking |
| `switches` | Switch history |
| `model_registry` | ML model metadata |
| `risk_scores` | Risk assessments |
| `pending_switch_commands` | Legacy command queue |
| `decision_engine_log` | Decision audit log |
| `system_events` | System event log |
| `notifications` | User notifications |
| `clients_daily_snapshot` | Client growth analytics |
| `agent_decision_history` | Agent decision tracking |
| `client_savings_monthly` | Monthly savings aggregation |

---

## 3. Frontend Updates Required

### 3.1 Update `apiClient.jsx` Methods

Replace the workaround implementations with direct API calls:

#### Before (Workaround):
```javascript
async getAllInstancesGlobal(filters = {}) {
  console.warn('getAllInstancesGlobal: Using workaround - fetching from all clients');
  const clients = await this.getAllClients();
  const allInstances = [];
  for (const client of clients) {
    const instances = await this.getInstances(client.id, filters);
    // ... merge logic
  }
  return allInstances;
}
```

#### After (Direct API Call):
```javascript
async getAllInstancesGlobal(filters = {}) {
  const params = new URLSearchParams(
    Object.entries(filters).filter(([_, v]) => v && v !== 'all')
  );
  const query = params.toString() ? `?${params}` : '';
  return this.request(`/api/admin/instances${query}`);
}
```

---

#### Before (Workaround):
```javascript
async getAllAgentsGlobal() {
  console.warn('getAllAgentsGlobal: Using workaround - fetching from all clients');
  const clients = await this.getAllClients();
  const allAgents = [];
  for (const client of clients) {
    const agents = await this.getAgents(client.id);
    // ... merge logic
  }
  return allAgents;
}
```

#### After (Direct API Call):
```javascript
async getAllAgentsGlobal(filters = {}) {
  const params = new URLSearchParams(
    Object.entries(filters).filter(([_, v]) => v && v !== 'all')
  );
  const query = params.toString() ? `?${params}` : '';
  return this.request(`/api/admin/agents${query}`);
}
```

---

#### Before (Mock):
```javascript
async getPriceHistory(instanceId, days = 7, interval = 'hour') {
  console.warn('getPriceHistory: Backend endpoint not implemented, returning empty array');
  return [];
}
```

#### After (Real API):
```javascript
async getPriceHistory(instanceId, days = 7, interval = 'hour') {
  return this.request(`/api/client/instances/${instanceId}/price-history?days=${days}&interval=${interval}`);
}
```

---

### 3.2 Remove Console Warnings

The following methods now have real implementations and should remove their `console.warn()` statements:

1. `getAllInstancesGlobal()` - Line 282
2. `getAllAgentsGlobal()` - Line 309
3. `getPriceHistory()` - Line 267

---

### 3.3 Update `globalSearch()` (Future Enhancement)

The `globalSearch(query)` method (line 261) still returns mock data. This could be enhanced in the future to search across:
- Client names
- Instance IDs
- Agent logical IDs
- Instance types

**Suggested Future Endpoint:** `GET /api/admin/search?q={query}`

---

## 4. Testing Recommendations

### 4.1 Backend Endpoint Testing

Test each new endpoint with various filters:

```bash
# Test global instances endpoint
curl http://localhost:5002/api/admin/instances?status=active&mode=spot

# Test global agents endpoint
curl http://localhost:5002/api/admin/agents?status=online

# Test price history endpoint
curl http://localhost:5002/api/client/instances/i-1234567890abcdef0/price-history?days=7&interval=hour
```

### 4.2 Frontend Integration Testing

1. **Global Instances View**: Verify the admin dashboard shows all instances without multiple API calls
2. **Global Agents View**: Verify the admin agents page loads quickly
3. **Price History Charts**: Verify instance detail pages show historical price trends

### 4.3 Performance Testing

- **Before**: Fetching 10 clients × 5 instances each = 10 API calls
- **After**: Fetching all 50 instances = 1 API call

Expected improvement: ~10x reduction in API calls for global views.

---

## 5. Migration Notes

### 5.1 Database Schema Migration

To migrate from v5.1 to v6.0:

**Option 1: Fresh Installation (Recommended for new deployments)**
```bash
mysql -u root -p spot_optimizer < schema_cleaned.sql
```

**Option 2: Drop Unused Tables (Existing deployments)**
```sql
-- Backup first!
mysqldump -u root -p spot_optimizer > backup_before_cleanup.sql

-- Drop unused tables
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS cost_records;
DROP TABLE IF EXISTS model_predictions;
DROP TABLE IF EXISTS ondemand_prices;
DROP TABLE IF EXISTS replicas;
DROP TABLE IF EXISTS spot_prices;

-- Drop unused views
DROP VIEW IF EXISTS agent_overview;
DROP VIEW IF EXISTS client_savings_summary;
DROP VIEW IF EXISTS active_spot_pools;

-- Drop unused procedures
DROP PROCEDURE IF EXISTS register_agent;
DROP PROCEDURE IF EXISTS get_pending_commands;
-- ... (drop all 11 procedures)

-- Drop unused events
DROP EVENT IF EXISTS evt_daily_cleanup;
-- ... (drop all 4 events)
```

### 5.2 Backward Compatibility

✅ **Fully Compatible**: All existing endpoints remain unchanged
✅ **Additive Only**: Only new endpoints were added
✅ **No Breaking Changes**: Frontend using old workaround methods will continue to work

---

## 6. File Locations

| File | Location | Purpose |
|------|----------|---------|
| `backend.py` | `/home/user/final-ml/backend.py` | Backend with new endpoints |
| `schema.sql` | `/home/user/final-ml/schema.sql` | Original schema v5.1 |
| `schema_cleaned.sql` | `/home/user/final-ml/schema_cleaned.sql` | Cleaned schema v6.0 |
| `apiClient.jsx` | `frontend-analysis/src/services/apiClient.jsx` | Frontend API client (needs updates) |

---

## 7. Version History

- **v4.0** - Initial backend with file upload and restart functionality
- **v4.1** - Added decision engine and ML model file uploads
- **v4.2** - Added automatic backend restart after uploads + 3 new endpoints
- **Schema v6.0** - Cleaned schema removing 6 tables, 3 views, 11 procedures, 4 events

---

## 8. Next Steps

1. ✅ Backend endpoints created
2. ✅ Schema cleaned
3. ⏳ **Frontend team**: Update `apiClient.jsx` with real API calls
4. ⏳ **QA team**: Test new endpoints and performance improvements
5. ⏳ **DevOps**: Deploy schema v6.0 to staging/production

---

**Questions or Issues?**
Contact the backend team or open an issue in the repository.
