# Agent Module Information

## Overview
The Kubernetes Agent ("The Probe") runs inside customer clusters to collect metrics and execute optimization actions.

## Purpose
- Collect pod and node metrics from Kubernetes API
- Execute optimization actions (eviction, cordoning, draining)
- Send heartbeat and health metrics to backend
- Real-time communication via WebSocket

## Implementation Status
✅ **IMPLEMENTED** - Phase 9.5 (2026-01-02)

## Files

### Core Modules (~2,800 lines total)
- `config.py` (170 lines) - Configuration management with validation
  - Load/validate environment variables
  - SIGHUP handler for config reload
  - URL builders for API endpoints

- `collector.py` (420 lines) - Metrics collection
  - `collect_pod_metrics()` - CPU/RAM usage, status, requests/limits
  - `collect_node_metrics()` - Allocatable resources, utilization
  - `collect_cluster_events()` - Pod evictions, OOMKills, Spot interruptions
  - Metrics Server integration
  - Batch and send to backend

- `actuator.py` (460 lines) - Action execution
  - `evict_pod()` - Graceful pod eviction with PDB respect
  - `cordon_node()` - Mark node unschedulable
  - `drain_node()` - Drain all pods from node
  - `label_node()` - Add/remove node labels
  - `update_deployment()` - Update resource requests/limits
  - HMAC signature verification for security

- `heartbeat.py` (310 lines) - Health reporting
  - HTTP server on port 8080 (`/healthz`, `/readyz`)
  - Send agent metrics (CPU, memory, errors)
  - Report Kubernetes API connectivity
  - Health status tracking

- `websocket_client.py` (350 lines) - Real-time communication
  - WebSocket connection to backend
  - Handle action commands, config updates, pings
  - Reconnection with exponential backoff
  - Offline message buffering

- `main.py` (390 lines) - Entry point
  - Agent orchestration
  - Register with backend
  - Start collector, actuator, heartbeat threads
  - Graceful shutdown handling

### Packaging
- `Dockerfile` - Multi-stage build, non-root user, health check
- `requirements.txt` - Dependencies (kubernetes, websockets, requests, psutil)
- `README.md` - Installation and usage guide

### Deployment
- Helm chart in `/charts/spot-optimizer-agent/`
  - Deployment, ServiceAccount, RBAC
  - ConfigMap, Secret, Service
  - Liveness/Readiness probes

## Dependencies
- `kubernetes>=28.1.0` - Kubernetes Python client
- `websockets>=12.0` - WebSocket client library
- `requests>=2.31.0` - HTTP client
- `psutil>=5.9.6` - System metrics

## Configuration
Required environment variables:
- `API_URL` - Backend API URL
- `CLUSTER_ID` - Unique cluster identifier
- `API_TOKEN` - Authentication token

Optional:
- `LOG_LEVEL` - Logging level (default: INFO)
- `COLLECTION_INTERVAL` - Metrics collection interval (default: 30s)
- `HEARTBEAT_INTERVAL` - Heartbeat interval (default: 30s)
- `DRY_RUN` - Dry-run mode (default: false)
- `WEBSOCKET_ENABLED` - Enable WebSocket (default: true)

## Usage Examples

### Deploy with Helm
```bash
helm install spot-optimizer-agent ./charts/spot-optimizer-agent \
  --namespace spot-optimizer \
  --set config.apiUrl="https://api.spotoptimizer.com" \
  --set config.clusterId="prod-cluster" \
  --set config.apiToken="your-token"
```

### View Agent Logs
```bash
kubectl logs -n spot-optimizer deployment/spot-optimizer-agent -f
```

### Check Health
```bash
kubectl exec -n spot-optimizer deployment/spot-optimizer-agent -- \
  curl http://localhost:8080/healthz
```

## Security
- HMAC signature verification for all actions
- Bearer token authentication
- Non-root container user (UID 1000)
- Minimal RBAC permissions (read-only + specific write for actions)

## Module IDs
- `AGENT-CFG-01` - Configuration management
- `AGENT-COLLECT-01` - Metrics collection
- `AGENT-ACT-01` - Action execution
- `AGENT-HEALTH-01` - Health reporting
- `AGENT-WS-01` - WebSocket client
- `AGENT-MAIN-01` - Main orchestrator

## Recent Changes

### 2026-01-02 - Initial Implementation (Phase 9.5)
- Implemented all 6 core agent modules
- Created Docker packaging with multi-stage build
- Created Helm chart for Kubernetes deployment
- Added comprehensive README documentation
- Total: ~2,800 lines of Python code

## Testing
- Unit tests: Pending (Phase 11)
- Integration tests: Pending (Phase 11)
- Manual testing: Verify with `kubectl` commands

## Future Enhancements
- Prometheus metrics export
- Advanced scheduling strategies
- Multi-cluster support
- Custom resource handlers
