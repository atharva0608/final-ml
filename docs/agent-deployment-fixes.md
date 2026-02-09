# Agent Pod Crash Fixes and Backend Implementation

## Summary
Fixed critical agent pod crashes and implemented missing backend API endpoints to enable full agent-to-backend communication.

## Issues Fixed

### 1. Agent Pod Crashes ✅
**Problem**: Agent pods were crashing with Error status and constant restarts
```
NAME                  READY   STATUS    RESTARTS   AGE
spot-agent-dpsfr      0/1     Error     1          60s
spot-agent-w6dch      0/1     Error     1          60s
```

**Root Causes Identified**:
- `RuntimeError: threads can only be started once` (agent/main.py:292)
- Duplicate websocket_client initialization (lines 221-232)
- Missing RBAC permissions for metrics.k8s.io API group
- Missing RBAC permissions for events resource
- 404 errors for missing backend endpoints

**Fixes Applied**:
- Removed duplicate `websocket_client` initialization in agent/main.py
- Removed duplicate `thread.start()` call
- Added RBAC permissions in agent_injector.py:
  - metrics.k8s.io API group (pods, nodes)
  - events resource in core API group
- Rebuilt and pushed agent image to Docker Hub
- Implemented missing backend endpoints (see below)

### 2. Missing Backend Endpoints ✅
**Problem**: Agent was getting 404 errors when trying to communicate with backend
```
404 Client Error: Not Found for url: .../api/v1/actions/poll
404 Client Error: Not Found for url: .../api/v1/metrics/batch
```

**Implementation**:

#### A. Actions Router (`backend/routers/actions.py`)
- **GET /api/v1/actions/poll** - Agents poll for pending actions
  - Returns up to 10 pending actions for specified cluster
  - Marks actions as PICKED_UP when agent retrieves them
  - Returns action type, parameters, and signature

- **POST /api/v1/actions/{action_id}/result** - Agents report execution results
  - Updates action status (COMPLETED or FAILED)
  - Stores result data and error messages
  - Records completion timestamp

- **POST /api/v1/actions/** - Create new actions (used by backend)
  - Validates action type and cluster
  - Creates action in PENDING status
  - Returns action ID for tracking

- **GET /api/v1/actions/{action_id}** - Get action details
- **GET /api/v1/actions/cluster/{cluster_id}** - List all actions for cluster

#### B. Metrics Router (`backend/routers/metrics.py`)
- **POST /api/v1/metrics/batch** - Receive batched metrics from agents
  - Accepts pod, node, and event metrics
  - Stores aggregated metrics in database
  - Caches latest metrics in Redis (5 min TTL for nodes, 1 min for summary)
  - Returns acknowledgment with counts

- **GET /api/v1/metrics/cluster/{cluster_id}/latest** - Get latest metrics
  - Returns cached metrics if available
  - Falls back to database query
  - Used by frontend for real-time dashboards

- **GET /api/v1/metrics/cluster/{cluster_id}/history** - Get historical metrics
  - Query metrics from past N hours (default 24)
  - Used for trend analysis and graphs

### 3. Database Models ✅
**Created**: ClusterMetric model
```python
# Stores metrics with flexible JSONB storage
- id: Primary key
- cluster_id: Foreign key to clusters
- metric_type: "pod", "node", "event", or "aggregated"
- metric_data: JSONB with metric-specific fields
- timestamp: When metrics were collected
```

**Updated**: Cluster model
- Added `metrics` relationship to ClusterMetric

**Used**: AgentAction model (already existed)
- Proper enum types: AgentActionStatus, AgentActionType
- Status flow: PENDING → PICKED_UP → COMPLETED/FAILED

### 4. Other Fixes ✅
- Fixed frontend ClusterList to use INACTIVE instead of non-existent DISCONNECTED status
- Improved docker-compose healthchecks for better container monitoring
- Created `check-agent-status.sh` monitoring script

## Agent Communication Flow

### 1. Action Execution
```
Backend → Creates AgentAction (PENDING)
         ↓
Agent   → Polls /api/v1/actions/poll (every 10s)
         ↓
Backend → Returns actions, marks as PICKED_UP
         ↓
Agent   → Executes action (evict, cordon, drain, etc.)
         ↓
Agent   → Reports result to /api/v1/actions/{id}/result
         ↓
Backend → Marks action as COMPLETED/FAILED
```

### 2. Metrics Collection
```
Agent   → Collects pod/node/event metrics from K8s API
         ↓
Agent   → Batches metrics (up to 100 items)
         ↓
Agent   → Sends to /api/v1/metrics/batch (every 60s)
         ↓
Backend → Stores in database + caches in Redis
         ↓
Frontend → Queries /api/v1/metrics/cluster/{id}/latest
```

## Deployment Steps

### 1. Agent Image
✅ Built and pushed to Docker Hub:
```bash
docker build -t atharva608/spot-optimizer-agent:latest .
docker push atharva608/spot-optimizer-agent:latest
```

### 2. Backend
✅ Restarted with new endpoints:
```bash
docker restart spot-optimizer-backend
# Status: healthy ✓
```

### 3. Agent Deployment (Next Step)
**To deploy the fixed agent to your cluster:**

1. Click "Activate Optimization" in the UI for your cluster
   - This will trigger agent injection via backend

2. Monitor pod status:
   ```bash
   ./check-agent-status.sh
   # or
   kubectl get pods -n spot-optimizer -w
   ```

3. Check agent logs:
   ```bash
   kubectl logs -f <pod-name> -n spot-optimizer
   ```

4. Verify agent is sending data:
   - Check cluster status in UI (should go from offline → online)
   - Check backend logs for incoming metrics: `docker logs -f spot-optimizer-backend | grep metrics`

## Expected Agent Logs (Healthy)
```
INFO - Starting Kubernetes Agent...
INFO - Agent registered successfully
INFO - Metrics collector initialized
INFO - Action actuator initialized
INFO - Heartbeat sender initialized
INFO - WebSocket client initialized
INFO - Spot Termination Poller initialized
INFO - All components started successfully
INFO - Agent is running. Press Ctrl+C to stop.
INFO - Collected metrics for 15 pods
INFO - Collected metrics for 2 nodes
INFO - Successfully sent 20 metrics to backend
```

## Expected Backend Logs (Healthy)
```
INFO - Received metrics batch from cluster {id}: 15 pods, 2 nodes, 3 events
INFO - Cluster {id} polled 0 actions
INFO - HTTP request GET /api/v1/actions/poll 200 5.2ms
INFO - HTTP request POST /api/v1/metrics/batch 200 12.8ms
```

## Troubleshooting

### If agent pods still crash:
1. Check pod logs: `kubectl logs <pod-name> -n spot-optimizer`
2. Check pod events: `kubectl describe pod <pod-name> -n spot-optimizer`
3. Verify image was pulled: `kubectl get pods -n spot-optimizer -o jsonpath='{.items[0].status.containerStatuses[0].image}'`
4. Check RBAC permissions: `kubectl get clusterrolebinding spot-agent-binding -o yaml`

### If metrics not appearing:
1. Check agent logs for HTTP errors
2. Verify backend is receiving requests: `docker logs -f spot-optimizer-backend | grep metrics`
3. Check Redis connectivity: `docker exec -it spot-optimizer-redis redis-cli ping`
4. Query database: Check `cluster_metrics` table

### If actions not executing:
1. Verify action was created: `curl http://localhost:8000/api/v1/actions/cluster/{id}`
2. Check agent is polling: Look for "polled N actions" in agent logs
3. Verify HMAC signature (if implemented)
4. Check action status in database

## Files Changed
- ✅ agent/main.py (duplicate thread fixes)
- ✅ backend/services/agent_injector.py (RBAC permissions)
- ✅ backend/routers/actions.py (new)
- ✅ backend/routers/metrics.py (new)
- ✅ backend/models/cluster_metric.py (new)
- ✅ backend/models/__init__.py (exports)
- ✅ backend/models/cluster.py (relationship)
- ✅ backend/core/api_gateway.py (router registration)
- ✅ check-agent-status.sh (new monitoring script)

## Git Commits
- `1e7e3d0` - fix: Agent crash - remove duplicate thread starts and add RBAC permissions
- `24d44e1` - feat: Implement agent communication endpoints and cluster metrics storage

## Next Steps
1. Deploy agent to cluster via UI ("Activate Optimization")
2. Monitor pod status and logs
3. Verify metrics appearing in UI
4. Test action execution (manually create test action)
5. Monitor cluster goes from offline → online

---
Last Updated: 2026-02-09
Status: Ready for deployment ✅
