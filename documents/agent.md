# Agent System — Complete Technical Reference

> All facts in this document are verified directly against the codebase. Source file and line references are provided for every claim.

---

## Table of Contents

1. [Agent Identity & Deployment](#1-agent-identity--deployment)
2. [Communication & Endpoints](#2-communication--endpoints)
3. [Agent Lifecycle & Failure Management](#3-agent-lifecycle--failure-management)
4. [Rebalancing Method on Agent Side](#4-rebalancing-method-on-agent-side)
5. [Data Fetched by the Agent](#5-data-fetched-by-the-agent)
6. [AWS API Calls from the Agent](#6-aws-api-calls-from-the-agent)
7. [Backend Response to Agent Messages](#7-backend-response-to-agent-messages)
8. [Monitoring & Debugging](#8-monitoring--debugging)
9. [Edge Cases & Resilience](#9-edge-cases--resilience)

---

## 1. Agent Identity & Deployment

### The Two Agents

There are two distinct agents deployed per cluster:

| | **Node Agent** | **Orchestrator** |
|---|---|---|
| **Primary role** | Execute K8s actions (cordon/drain/delete node), collect per-node metrics, report spot-interruption events | Cluster-level coordination (Karpenter management, cluster-wide actions) |
| **Entry point** | `agent/main.py` — `Agent` class | Same codebase, different runtime role |
| **Deployment kind** | `DaemonSet` — one pod per node | `Deployment` — exactly 1 replica |
| **Image** | `atharva608/spot-optimizer-agent:{{ .Chart.AppVersion }}` | `atharva608/spot-optimizer-agent:{{ .Chart.AppVersion }}` |
| **Namespace** | `spot-optimizer` (configurable via `values.yaml`) | `spot-optimizer` |
| **Source** | `charts/spot-optimizer-agent/templates/daemonset.yaml` | `charts/spot-optimizer-agent/templates/orchestrator-deployment.yaml` |

**Image tag policy** (`charts/spot-optimizer-agent/values.yaml` lines 1–4):
```yaml
image:
  repository: atharva608/spot-optimizer-agent
  tag: "{{ .Chart.AppVersion }}"
  pullPolicy: IfNotPresent
```

Both agent types use the same image with `pullPolicy: IfNotPresent` (fix N4 — was `Always`/`latest`). The agent sends `"version": "1.0.1"` in the registration payload (`agent/main.py` line 143). The backend does **not reject** mismatched versions but logs a warning when the registered version differs from `EXPECTED_AGENT_VERSION = "1.0.1"` (`backend/routers/agents.py`, fix N3). This provides visibility without blocking older agents.

### Kubernetes RBAC

**ClusterRole**: `spot-optimizer-agent`  
**Source**: `charts/spot-optimizer-agent/templates/clusterrole.yaml`

| API Group | Resources | Verbs |
|---|---|---|
| `""` (core) | `nodes` | `get`, `list`, `watch`, `patch`, `update` |
| `""` (core) | `pods` | `get`, `list`, `watch` |
| `""` (core) | `pods/eviction` | `create` |
| `""` (core) | `pods/log` | `get` |
| `""` (core) | `persistentvolumeclaims` | `get`, `list`, `watch` |
| `""` (core) | `events` | `get`, `list`, `watch` |
| `policy` | `poddisruptionbudgets` | `get`, `list`, `watch` |
| `karpenter.sh` | `nodepools`, `nodeclaims` | `get`, `list`, `watch`, `patch`, `update` |
| `karpenter.k8s.aws` | `ec2nodeclasses` | `get`, `list`, `watch`, `patch`, `update`, `create` |
| `metrics.k8s.io` | `nodes`, `pods` | `get`, `list` |

The DaemonSet also mounts `/host/proc` from the node's filesystem for psutil-based CPU/memory collection (`daemonset.yaml`), and runs with `hostNetwork: true` and tolerates all taints (`operator: Exists`) so it can schedule on any node including masters and tainted spot nodes.

---

## 2. Communication & Endpoints

### Protocols

| Channel | Protocol | Used For |
|---|---|---|
| Action delivery (primary) | **WebSocket** | Backend pushes actions to agent in real-time |
| Action delivery (fallback) | **HTTP polling** | Agent polls when WebSocket is unavailable |
| Heartbeat | **HTTP POST** | Agent → backend every 30 seconds |
| Metrics | **HTTP POST** | Agent → backend every 60 seconds |
| Spot interruption notification | **HTTP POST** | Agent → backend on IMDS detection |
| Action result reporting | **HTTP POST** | Agent → backend after action completes |

### WebSocket

**URL** (`agent/websocket_client.py`):
```
{BACKEND_WS_URL}/ws/cluster/{cluster_id}?agent_id={agent_id}
```

**Authentication**: `Authorization: Bearer {API_KEY}` header on connection upgrade.  
**Ping**: 20-second interval, 10-second timeout (configured in `WebSocketClient.__init__`).  
**Message buffer (two-tier, fix BUG-4/N6)**: Critical messages (`action_result`, `heartbeat` types) go to an unbounded `critical_queue` (`queue.Queue()`) — never dropped. Metrics go to a `metrics_buffer` ring buffer (`collections.deque(maxlen=200)`) — oldest entries dropped when full. Both queues are flushed on reconnect, critical queue first.

### HTTP Endpoints Called by the Agent

All HTTP calls use `Authorization: Bearer {API_KEY}` unless noted.

| Method | URL | Source file | Frequency | Purpose |
|---|---|---|---|---|
| `POST` | `/api/v1/agents/register` | `agent/main.py:121` | Once on startup | Register agent with backend |
| `POST` | `/api/v1/agents/heartbeat` | `agent/heartbeat.py` | Every 30 s | Liveness signal + health metrics |
| `POST` | `/api/v1/agents/deregister` | `agent/main.py:172` | On graceful shutdown | Remove agent from backend |
| `GET` | `/api/v1/agents/actions/pending` | `agent/actuator.py` | ~every 15 s (fallback) | Poll for pending actions when WebSocket is down |
| `POST` | `/api/v1/agents/actions/{action_id}/result` | `agent/actuator.py` | After each action | Report action completion/failure |
| `POST` | `/api/v1/agents/actions/{action_id}/heartbeat` | `agent/actuator.py` | Every 30 s during action | Action-level liveness signal — backend writes `action_heartbeat:{id}` Redis key (TTL 120 s) |
| `POST` | `/api/v1/agent-metrics/batch` | `agent/collector.py` | Every 60 s | Node-level CPU/memory metrics |
| `POST` | `/api/v1/pod-metrics/batch` | `agent/pod_metrics_collector.py` | Every 60 s | Pod-level CPU/memory metrics |
| `POST` | `/api/v1/worker/spot-interruption` | `agent/poller.py:140` | On IMDS detection | Spot termination/rebalance notice |

> **Spot interruption authentication differs**: this endpoint uses `X-API-Key: {API_KEY}` header, not `Authorization: Bearer`.

### What Each Agent Sends

#### Registration payload (`agent/main.py` lines 122–146)
```json
{
  "cluster_id": "<CLUSTER_ID>",
  "agent_id": "<generated-uuid>",
  "cluster_name": "<CLUSTER_NAME env or k8s-cluster-{prefix}>",
  "region": "<AWS_REGION or CLUSTER_REGION env>",
  "timestamp": "<ISO 8601 UTC>",
  "capabilities": ["metrics_collection", "action_execution", "websocket_communication"],
  "version": "1.0.1"
}
```

#### Heartbeat payload (`agent/heartbeat.py`)
```json
{
  "cluster_id": "<CLUSTER_ID>",
  "agent_id": "<agent_id>",
  "timestamp": "<ISO 8601 UTC>",
  "health": {
    "cpu_percent": 42.1,
    "memory_percent": 61.3,
    "disk_percent": 38.2,
    "network_bytes_sent": 1024000,
    "network_bytes_recv": 2048000,
    "process_count": 5,
    "components": {
      "metrics_collector": "healthy",
      "action_actuator": "healthy",
      "websocket_client": "healthy",
      "spot_poller": "healthy",
      "pod_metrics_collector": "healthy"
    }
  }
}
```
**Interval**: 30 seconds (`HEARTBEAT_INTERVAL` env, default `30`).

#### Metrics payload (`agent/collector.py`)
Sent to `/api/v1/agent-metrics/batch`. Contains per-node metrics: CPU utilization (%), memory utilization (%), disk utilization (%), network I/O.  
**Interval**: 60 seconds (`COLLECTION_INTERVAL` env, default `60`).

#### Pod metrics payload (`agent/pod_metrics_collector.py`)
Sent to `/api/v1/pod-metrics/batch`. Contains per-pod CPU/memory.  
DaemonSet mode: only pods on the local node (via `NODE_NAME` env).  
**Interval**: 60 seconds (`POD_METRICS_INTERVAL` env, default `60`).

#### Spot interruption notification (`agent/poller.py`)
```json
{
  "cluster_id": "<CLUSTER_ID>",
  "instance_id": "<EC2 instance ID from IMDS>",
  "action": "terminate",
  "termination_time": "<ISO 8601>"
}
```

#### Action result (`agent/actuator.py`)
```json
{
  "action_id": "<id>",
  "status": "completed|failed",
  "error": "<error message or null>",
  "started_at": "<ISO 8601>",
  "completed_at": "<ISO 8601>"
}
```

### How the Backend Sends Actions to the Agent

**Primary path — WebSocket push** (`backend/api/api_gateway.py` lines 1063–1070):
- When the agent connects, all pending `AgentAction` rows are immediately delivered.
- Every ~15 seconds, the gateway checks for new `PENDING` actions and pushes them.
- On delivery the action is marked `PICKED_UP` with a `picked_up_at` timestamp to prevent re-delivery.

**Fallback path — HTTP polling**:
- Agent periodically calls `GET /api/v1/agents/actions/pending`.
- Results same `AgentAction` records in `PENDING` state.

The action payload mirrors what the backend stored in `AgentAction.payload`, e.g. for a DRAIN_NODE:
```json
{
  "ignore_daemonsets": true,
  "grace_period_seconds": 60,
  "rebalancing_action_id": 123,
  "zero_downtime_step": 3
}
```

---

## 3. Agent Lifecycle & Failure Management

### Startup Sequence (`agent/main.py` lines 487–520)

```
1. Register signal handlers (SIGTERM, SIGINT)
2. Call register_with_backend()
   → POST /api/v1/agents/register
   → If fails: log error and EXIT (sys.exit / return False stops startup)
3. initialize_components()
   → Create MetricsCollector, ActionActuator, HeartbeatSender,
      WebSocketClient, SpotPoller, PodMetricsCollector
4. Start component threads
5. Enter monitoring loop (checks thread health)
```

If registration fails (`agent/main.py` line 493):
```python
if not self.register_with_backend():
    logger.error("Failed to register with backend, exiting...")
    return  # agent exits
```
The DaemonSet will restart the pod (normal Kubernetes restart policy). The agent retries registration on each restart attempt.

### Thread Health Monitoring (`agent/main.py`)

A central monitoring loop watches all component threads. If a thread dies:
- **Max restart attempts**: 5 per component
- **Backoff**: exponential — `2^n` seconds, capped at 60 s
  - Attempt 1: 1 s, 2: 2 s, 3: 4 s, 4: 8 s, 5: 16 s (then capped at 60 s)
- After 5 failed restarts: the agent logs a critical error but continues running other components.

### Action Failure Handling (Agent Side)

When an action fails internally (e.g. eviction rejected by PDB):

1. **Agent retries eviction**: 5 attempts, 10-second backoff between attempts (`agent/actuator.py`).
2. If all retries exhausted: returns `PDB_VIOLATION_MAX_RETRIES` error string.
3. Agent POSTs action result with `status: failed` and the error message to `/api/v1/agents/actions/{action_id}/result`.
4. Backend detects the failure (see §7) and triggers rollback.

**There is no local state persistence on the agent side.** If the agent crashes mid-action, it has no on-disk checkpoint. The backend detects the crash via heartbeat loss (>5 minutes) and uses the action heartbeat Redis key (`action_heartbeat:{action_id}`, TTL 120 s) to detect stale in-progress actions.

> **Who sets `action_heartbeat`:** Two writers maintain this key (fix N5):
> 1. The **backend Celery worker** (`auto_rebalancer.py`) updates it via `redis.setex(f"action_heartbeat:{action_id}", 120, ...)` on each 15-second rebalancer cycle while processing `waiting_agent` actions.
> 2. The **agent** (`agent/actuator.py` — `_action_heartbeat_loop()`) POSTs to `/api/v1/agents/actions/{action_id}/heartbeat` every 30 s while the action is running; the backend endpoint then calls `redis.setex()`.
>
> Whichever writer ran most recently wins. The key expires within 120 s only if **both** writers stop — at which point the recovery monitor marks the action stale.

### Action Timeouts

| Action | Timeout | Configurable |
|---|---|---|
| Drain | 15 minutes default | Yes — `ClusterOptimizationSettings.drain_timeout_minutes` |
| Spot node join wait | 30 minutes | Yes — `ClusterOptimizationSettings.spot_join_timeout_minutes` |
| Spot stabilization wait | 90 seconds | No — hardcoded |
| Grace period per pod | 60 seconds (in drain action payload) / 20 s (some paths) | No |
| Action heartbeat TTL | 120 seconds | No |
| Action stale expiry (PENDING/PICKED_UP) | 15 minutes | No — `auto_rebalancer.py:3921` |

### Rollback When Drain Fails

The **backend** orchestrates rollback, not the agent. When the agent reports drain failure:

1. Backend calls `_do_rollback_uncordon_and_terminate()` (`auto_rebalancer.py` lines 2910–2960).
2. Queues `UNCORDON_NODE` AgentAction for the same node:
   ```python
   AgentAction(
       action_type=AgentActionType.UNCORDON_NODE,
       payload={"node_name": <rb_node>},
   )
   ```
3. Calls `_do_rollback_terminate_orphan_spot()` — terminates the provisioned replacement spot via EC2 `terminate_instances` (direct boto3 call by backend, not via agent).
4. Sets stabilization lock `spot:stabilization_lock:{cluster_id}` (TTL 60 s) and failure backoff `rebalance_failures:{instance_id}` (TTL 86400 s) to prevent immediate re-attempt.

The agent only receives and executes the UNCORDON_NODE action — it does not initiate any rollback logic itself.

### Duplicate Action Handling

- **Primary dedup**: Actions are marked `PICKED_UP` with `picked_up_at` immediately upon WebSocket delivery. A PICKED_UP action is not re-delivered (`api_gateway.py` lines 1063–1070).
- **No agent-side dedup**: The agent does not maintain a set of seen action IDs. It trusts the PICKED_UP flag to prevent re-delivery.
- **Concurrent actions on same node**: Not explicitly locked on the agent side. The backend uses a distributed lock `lock:node_action:{cluster_id}` (1200-second timeout — Z10 fix, was 180s) before draining (`auto_rebalancer.py` line 979) to serialize K8s drain. Only one drain per cluster is allowed to proceed at a time.

---

## 4. Rebalancing Method on Agent Side

### Full Cordon → Drain → Terminate Sequence

The backend sends three separate `AgentAction` records in order. The sequence:

**Step 1: LABEL_NODE** (`auto_rebalancer.py` lines 2793–2810)
- Labels the new replacement node: `karpenter.sh/do-not-disrupt=true`

**Step 2: CORDON_NODE** (`auto_rebalancer.py` lines 2814–2823; `agent/actuator.py` cordon handler)
- Payload:
  ```json
  {
    "instance_id": "<old instance ID>",
    "instance_type": "<type>",
    "az": "<AZ>",
    "rebalancing_action_id": 123,
    "zero_downtime_step": 2
  }
  ```
- Agent calls Kubernetes `CoreV1Api.patch_node()` with `spec.unschedulable = true`.
- The agent **does not verify unschedulability** before proceeding — the K8s API call is synchronous.

**Step 3: DRAIN_NODE** (`auto_rebalancer.py` lines 2824–2833; `agent/actuator.py` drain handler)
- Payload: `{ "ignore_daemonsets": true, "grace_period_seconds": 60, "rebalancing_action_id": 123, "zero_downtime_step": 3 }`
- Exact drain algorithm (`agent/actuator.py`):
  1. Cordon the node again (idempotent safety).
  2. List all pods on the node.
  3. Skip DaemonSet pods (owner reference `DaemonSet`).
  4. Skip mirror pods (annotation `kubernetes.io/config.mirror`).
  5. For each remaining pod:
     a. Check PodDisruptionBudget — if eviction would violate PDB, retry up to 5 times with 10-second backoff.
     b. If all 5 retries fail: return `PDB_VIOLATION_MAX_RETRIES`.
     c. Call `CoreV1Api.create_namespaced_pod_eviction()` with the configured grace period.
  6. After all evictions submitted: clear `VolumeAttachment` objects pointing to the node.
  7. Clear `metadata.finalizers` on any pods stuck in `Terminating` state.
  8. No dry-run is performed before drain.

**Step 4: TERMINATE_NODE** (backend only — `auto_rebalancer.py` lines 2834–2848)
- **The agent does NOT terminate the EC2 instance.** The backend calls AWS directly (boto3):
  - Primary: `autoscaling:TerminateInstanceInAutoScalingGroup` with `ShouldDecrementDesiredCapacity=True`.
  - Fallback (if `ValidationError` meaning already detached): `ec2:TerminateInstances`.
- The agent may receive `FORCE_DELETE_NODE` to delete the Kubernetes node object (`kubectl delete node`), but EC2 termination happens backend-side.

### Force Drain (Spot Interruption Path)

When spot IMDS detects termination, the agent uses `force=True`:
- PDB checks are **bypassed**.
- `grace_period_seconds = 0`.
- Flow: cordon → iterate pods (skip DaemonSet) → forcibly evict everything.

### PDB Respect

- Standard drain: respects PDBs (5 retries, 10 s backoff, then fail with `PDB_VIOLATION_MAX_RETRIES`).
- Force drain (spot interruption): ignores PDBs.
- The `force` flag in the DRAIN_NODE payload controls this behavior. **As of fix N1**, `force` is set by the backend based on `respect_pdb_enabled` in `StatelessRuntimeRules` (`auto_rebalancer.py`): `force=True` when `respect_pdb_enabled=False` (bypasses PDB), `force=False` when `respect_pdb_enabled=True` (respects PDB, 5 retries). This field is user-configurable in the cluster's runtime rules.

### Drain Completion Verification

The agent does **not** watch for pod eviction completion events. It submits eviction API calls and considers drain done when all non-DaemonSet pods have been successfully evicted (eviction API returns success) or have been forcibly deleted. It does not poll pod count — eviction API success/failure is the signal.

### Logging per Action Step

All logs go to **stdout** via Python `logging` module. Log level defaults to `INFO` (`agent/config.py` line 45):
```python
self.log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
```
Valid levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

Each action step emits `logger.info(...)` or `logger.error(...)` with the node name, action type, and step number. Logs are collected by whatever log aggregator is configured on the cluster (cloud-provider stdout log collection, Fluentd, etc.).

---

## 5. Data Fetched by the Agent

### Kubernetes API Calls

| Resource | Verb | Why |
|---|---|---|
| `nodes` | `get`, `list`, `watch` | Cordon, node metadata, metrics |
| `nodes` | `patch`, `update` | Cordon/uncordon, labeling |
| `pods` | `list` | Drain (find pods on node) |
| `pods/eviction` | `create` | Drain — evict each pod |
| `persistentvolumeclaims` | `get`, `list` | VolumeAttachment cleanup |
| `events` | `list` | Diagnostics |
| `poddisruptionbudgets` | `get`, `list` | PDB check during drain |
| `karpenter.sh/nodepools` | `get`, `list`, `patch`, `update` | PATCH_KARPENTER_NODEPOOL action |
| `karpenter.k8s.aws/ec2nodeclasses` | `get`, `list`, `patch`, `update`, `create` | INSTALL_KARPENTER action |
| `metrics.k8s.io/nodes` | `get`, `list` | Fallback node metrics (if psutil unavailable) |
| `metrics.k8s.io/pods` | `get`, `list` | Pod metrics (secondary source) |

**Watch vs list**: The agent uses `list` calls, not watches. There is no watch connection maintained. Metrics are collected on a fixed interval via `list` calls.

### IMDS (EC2 Instance Metadata) Calls (`agent/poller.py`)

| Endpoint | Frequency | Purpose |
|---|---|---|
| `http://169.254.169.254/latest/meta-data/spot/instance-action` | Every 5 s (`IMDS_POLL_INTERVAL_SECONDS` env) | Detect AWS spot termination notice (HTTP 200 = termination imminent, HTTP 404 = normal) |
| `http://169.254.169.254/latest/meta-data/events/recommendations/rebalance` | Every 5 s | Detect AWS EC2 rebalance recommendation |

On termination detection:
1. Execute force drain locally (cordon + evict all non-DaemonSet pods, PDB bypassed).
2. POST to `/api/v1/worker/spot-interruption` with `X-API-Key` header.
3. Backend's emergency rebalancer takes over.

### How New Spot Nodes Are Detected

The agent **does not** report node-join events. When a new spot instance is provisioned, it joins as a Kubernetes node. The backend's **Celery task** (`auto_rebalancer.py`) polls for the new node by watching the `node_joined:{instance_id}` Redis key:
- This key is set by the backend's node discovery/event pipeline when the node's `Ready` condition becomes `True`.
- The auto-rebalancer waits up to `spot_join_timeout_minutes` (default 30 min) for this key to appear.

---

## 6. AWS API Calls from the Agent

### Short Answer: The Agent Makes **No Direct AWS SDK Calls**

The DaemonSet agent does not import or use `boto3`. All AWS operations (EC2 terminate, ASG terminate, dry-run, describe-instances) are performed by the **backend Celery workers** running in Docker/ECS — not by the in-cluster agent.

### What the Agent Does Instead

| Instead of | Agent uses |
|---|---|
| `ec2:TerminateInstances` | Kubernetes `kubectl delete node` (FORCE_DELETE_NODE action) |
| `ec2:DescribeInstances` | Kubernetes node object labels/annotations |
| IMDS for instance metadata | `http://169.254.169.254/…` HTTP calls (no IAM required) |
| Karpenter management | `helm` CLI via `subprocess` (INSTALL/UNINSTALL_KARPENTER actions) |

### AWS Credentials Pattern

The Helm chart uses a **Kubernetes Secret** (`spot-agent-secret`) that stores `API_KEY`. The agent uses this only for backend communication, not for AWS.

For **Karpenter installation** (`agent/actuator.py` lines 833–907), the INSTALL_KARPENTER action runs `helm install` via subprocess. This operation requires that the node's IAM instance profile or a service account with IRSA has IAM permissions to manage Karpenter CRDs — but this is a Helm/kubectl operation, not a direct AWS SDK call from the agent.

### Backend AWS Calls (for reference)

The **backend** (Celery worker `auto_rebalancer.py`) makes these calls on behalf of the rebalancing system:

| Call | Error Handling |
|---|---|
| `autoscaling:TerminateInstanceInAutoScalingGroup` | 3 retries, exponential backoff `2^n` s (1s, 2s, 4s) for `Throttling`/`RequestLimitExceeded`; on `ValidationError` falls back to `ec2:TerminateInstances` |
| `ec2:TerminateInstances` | Fallback after ASG ValidationError |
| `ec2:RunInstances` (spot launch) | SHA256 `ClientToken` for idempotent dedup (lines 1363–1373) |
| `ec2:DescribeInstances` (dry-run) | Max 5 API calls per rebalancing cycle, cached in Redis |

---

## 7. Backend Response to Agent Messages

### On Heartbeat (`backend/routers/agents.py` lines 170–214)

1. Looks up the `Cluster` row by `cluster_id`.
2. Sets `cluster.last_heartbeat = datetime.utcnow()`.
3. **If `cluster.agent_installed != 'Y'`** (was previously reset by stale-agent task):
   - Sets `cluster.agent_installed = 'Y'`
   - Sets `cluster.status = ClusterStatus.ACTIVE`
4. Commits to DB.
5. Returns `{"success": true, "timestamp": "<UTC>"}`.

The heartbeat response does **not** return pending actions — action delivery is via WebSocket push or the dedicated `/actions/pending` endpoint.

### On Action Result (`/api/v1/agents/actions/{action_id}/result`)

Backend updates the `AgentAction` record:
- `status = COMPLETED` or `FAILED`
- `completed_at = now()`
- An async state-machine trigger runs to advance the `RebalancingAction` state (see state machine below).

State machine transitions (atomic with `UPDATE ... WHERE current_state = :from_state`, `auto_rebalancer.py` lines 45–72):

```
CREATED → POOL_SELECTED → SOURCE_CORDONED → SOURCE_DRAINED
        → REPLACEMENT_LAUNCHING → REPLACEMENT_READY
        → SOURCE_TERMINATING → COMPLETED

Any state → FAILED (on error)
```

Distributed lock `rebalance:lock:{cluster_id}` (45-minute TTL, extended every 60 s by heartbeat thread) is held for the entire rebalancing workflow.

### On Spot Interruption Report (`POST /api/v1/worker/spot-interruption`)

The backend calls `EmergencyEventProcessor` which triggers an emergency rebalance task. The `RebalancingAction` is created with `reason=spot_interruption` and normal priority queuing resumes.

### On Invalid Payloads

FastAPI validates the request. If required fields are missing (`cluster_id` in heartbeat):
- Returns `HTTP 400 Bad Request` with detail: `"cluster_id is required"`.
- Does not close the WebSocket connection — WebSocket and HTTP are independent.

### Backend "Abort Action" Command

The backend can push any `AgentAction` type via WebSocket, including `UNCORDON_NODE`. There is **no explicit "abort" message type** — rollback is done by sending new compensating actions (UNCORDON_NODE) after the failed action is detected. The backend never sends a signal mid-execution to abort an in-flight action.

---

## 8. Monitoring & Debugging

### Agent Health Endpoint

The `HeartbeatSender` runs an embedded HTTP health server on **port 8080** (`agent/heartbeat.py`):

| Path | Purpose |
|---|---|
| `GET /healthz` | Liveness — returns 200 if agent process is alive |
| `GET /readyz` | Readiness — returns 200 when all components are initialized |
| `GET /metrics` | Prometheus-format metrics (action counts, failures, latency) |

The DaemonSet liveness/readiness probes point to this server.

### Log Collection

All agent logs go to **stdout**. They are picked up by the cluster's standard log collection stack (e.g., AWS CloudWatch Container Insights, Fluentd, Datadog agent). No file-based logging — pure structured `logging` output.

Log level is controlled by `LOG_LEVEL` env var (default: `INFO`). For debug traces on drain steps, set `LOG_LEVEL=DEBUG`.

Useful log patterns:
```bash
# All action execution logs
kubectl logs -n spot-optimizer -l app=spot-optimizer-agent | grep "action"

# Drain steps
kubectl logs -n spot-optimizer -l app=spot-optimizer-agent | grep -i "drain\|evict\|PDB"

# Heartbeat failures
kubectl logs -n spot-optimizer -l app=spot-optimizer-agent | grep "heartbeat"
```

### Backend Health Monitoring

The Celery task `reset_stale_agents` (schedule: every 1 minute, `backend/workers/app.py` lines 57–59) monitors agent liveness:
- Queries all `Cluster` rows with `agent_installed='Y'` and `last_heartbeat < now() - 5 minutes`.
- Resets stale clusters: `agent_installed='N'`, `status=DISCOVERED`.
- Clears CPU/memory utilization (`cpu_util=None`, `memory_util=None`) on all running instances in that cluster to prevent stale metrics from driving auto-scaling decisions.
- Busts the Redis `clusters:*` cache so the UI reflects the change immediately.

### Admin Intervention via Backend API

There is **no dedicated admin "force-uncordon" or "force-abort" REST endpoint**. However, an admin can:

1. **Directly create an `AgentAction`** in the database with type `UNCORDON_NODE` — it will be delivered to the agent via WebSocket on next push cycle.
2. **Cancel a stuck `RebalancingAction`**: Set `current_state = 'FAILED'` in the DB to break out of the active state machine.
3. **Release the cluster lock**: Delete Redis key `rebalance:lock:{cluster_id}` — this unblocks a new rebalancing cycle.
4. **Drain check on agent side**: Query `/metrics` on port 8080 of the specific DaemonSet pod to see in-progress action state.

### Checking Action State

From the backend API:
```bash
GET /api/v1/rebalancing/actions/<action_id>
```
Returns `current_state`, `status`, `action_metadata` (includes per-step timestamps), and `duration_seconds`.

From the agent side:
```bash
kubectl exec -n spot-optimizer <pod-name> -- curl localhost:8080/metrics
```

---

## 9. Edge Cases & Resilience

### Startup Crash Prevention (BUG-11 fix)

`Dict` is now imported from `typing` in `agent/main.py` (was previously missing, causing a `NameError` crash on agent startup when `Dict[str, int]` was referenced in `__init__`). All required typing imports: `Optional`, `Dict`.

### Agent Disconnection / Reconnection

**WebSocket reconnect** (`agent/websocket_client.py`):
- On disconnect: exponential backoff `reconnect_delay × 2^attempt`, capped at 60 seconds.
- Max 10 reconnect attempts before the WebSocket thread exits (the thread monitor then restarts it after its own backoff).
- **In-flight actions continue to completion** during disconnect — action execution runs in a separate thread, not in the WebSocket receive loop.
- **Message buffer (two-tier, fix BUG-4/N6)**: Critical messages (`action_result`, `heartbeat` types) go to an unbounded `critical_queue` — never dropped. Metrics go to a `metrics_buffer` ring buffer (`deque(maxlen=200)`) — oldest dropped when full. On reconnect the critical queue is flushed first, then metrics.
- **Flush safety (BUG-12 fix)**: If `send_message` fails during `flush_buffer`, the critical message is re-queued via `put()` instead of being dropped. Flush stops immediately (connection may not be ready) and retries on the next reconnect cycle.
- **On reconnect**: pending action results are sent immediately from the critical queue. The backend will also re-deliver any `PENDING` (not yet `PICKED_UP`) actions.

### Network Partition Between Agent and Backend

- Agent **continues to run** indefinitely — it does not shut down due to partition.
- IMDS polling continues independently (no network to backend required).
- Heartbeats will fail silently (logged as `logger.error`) but execution continues.
- **Backend side**: `reset_stale_agents_task` runs every minute. After 5 minutes without heartbeat:
  - `agent_installed = 'N'`
  - `status = DISCOVERED`
  - Utilization metrics cleared
  - All `PENDING`/`PICKED_UP` `AgentAction`s for the cluster are cancelled (`status = CANCELLED`) — fix BUG-9
  - All `in_progress`/`waiting_agent` `RebalancingAction`s are marked `failed` with error `AGENT_WENT_OFFLINE` — fix BUG-9
  - `action_heartbeat:{id}` Redis keys for affected actions are deleted
  - No new rebalancing actions are queued (backend won't dispatch to an apparently offline agent)
- On partition recovery: first successful heartbeat restores `agent_installed = 'Y'` and `status = ACTIVE`. Stale cluster is freed within 5 minutes instead of up to 45 minutes.

### Action for Non-Existent Node

If the agent receives a `CORDON_NODE` or `DRAIN_NODE` action for a node that does not exist:
- The Kubernetes `patch_node()` or `list_namespaced_pod()` call will raise a `404 Not Found` exception.
- The agent catches this as an action failure and reports `status: failed` with the Kubernetes exception detail.
- No retry from the agent — single attempt, fail fast.

### Agent as Target of Its Own Action (Self-Termination)

**All three destructive operations are now guarded against self-termination** (fix Z3). `cordon_node()`, `drain_node()`, and `force_delete_node()` all check whether `node_name == os.getenv('NODE_NAME')` at the start of execution. If the target node matches the agent's own node, the action is rejected with a `SELF_DELETE_ATTEMPT` error before any Kubernetes API call is made.

The backend's rebalancing logic already avoids selecting nodes running agent pods (DaemonSet pods are skipped during drain), so this guard is a defense-in-depth measure.

**Exception: Spot Interruption Self-Cordon (BUG-13 fix)**

During a genuine spot interruption detected via IMDS, the agent **must** cordon and drain its own node — this is the correct emergency procedure. `handle_spot_interruption()` in `actuator.py` now calls `_emergency_self_cordon_drain()`, which bypasses the Z3 self-guard and calls the Kubernetes API directly to cordon the node and evict all non-DaemonSet, non-mirror pods with a 30s grace period. If the `handle_spot_interruption` method is absent from the actuator, the poller's fallback also calls `_emergency_self_cordon_drain()`.

### Component Health Thread Safety (BUG-14 fix)

`HeartbeatSender.component_health` is accessed from multiple threads (main thread via `set_component_health()`, heartbeat thread via `send_heartbeat()` and `collect_agent_metrics()`). A `threading.Lock` (`_health_lock`) now protects all reads and writes. Reads take a snapshot (`dict(self.component_health)`) under the lock and release immediately.

### Agent Crash During In-Progress Action

The agent stores **no local state** (no disk persistence, no SQLite). On crash/restart:
1. Kubernetes restarts the pod (DaemonSet restart policy).
2. Agent re-registers with the backend on startup.
3. The in-progress action is still in `PICKED_UP` state in the backend DB.
4. The backend detects it via the **action heartbeat** Redis key:
   - Key: `action_heartbeat:{action_id}`, TTL 120 s, set by the backend worker heartbeat thread (not the agent).
   - If key has not been refreshed for >2 minutes, the action is considered stale.
5. Backend marks the action `FAILED` and initiates rollback (uncordon + orphan spot termination).
6. The **backend re-queues** the in-progress action if appropriate, or the admin must manually retry.

### Multiple Agents Acting on Same Node

In a DaemonSet deployment, only one agent pod runs per node. If two pods for the same cluster both connect to the backend WebSocket, the `PICKED_UP` flag prevents both from receiving the same action — only the first socket to connect and receive the action will get it marked `PICKED_UP`.

There is no explicit leader election for AgentActions. The concurrency model relies on:
1. `PICKED_UP` mark on WebSocket delivery (first-come-first-served).
2. Backend distributed lock `lock:node_action:{cluster_id}` (1200-second mutex — Z10 fix, was 180s) prevents parallel drain for the same cluster.

### AWS API Throttling

Handled entirely on the **backend side** (agent makes no AWS calls). See §6. The backend uses:
- 3 retries with `2^n` second backoff for ASG/EC2 throttle errors.
- Dry-run result caching in Redis (max 5 live API calls per cycle).
- Idempotent `ClientToken` (SHA256 hash) for `RunInstances` so a retry never double-launches.

### Critical Pods Running After Drain Timeout

When drain times out (`drain_timeout_minutes`, default 15):
- The backend marks the action `FAILED` (state: `FAILED`).
- Rollback begins: UNCORDON_NODE sent to agent, orphan spot instance terminated.
- `SM_DRAIN_TIMEOUT` state is **declared** in `auto_rebalancer.py` (lines 29–42) but is **not actively transitioned to** — the system falls through to `FAILED` state.
- There is no "force drain after timeout" mechanism — the backend gives up and uncordons.

### Kubernetes API Server Unreachable During Action

If the K8s API server becomes unreachable while the agent is executing drain:
- Each Kubernetes client call will raise a connection exception.
- The agent catches it as an action failure.
- Reports `status: failed` to backend on reconnect (buffered in WebSocket message buffer).
- The backend proceeds with rollback once it receives the failure report.
- While the connection never recovers, the backend detects the crash via action heartbeat staleness (>120 s) and marks the action failed on its own. Note: with the two-tier message buffer, critical action results are queued unboundedly — they are not dropped even under prolonged disconnection.

---

## Appendix: Environment Variables

| Variable | Default | Component | Purpose |
|---|---|---|---|
| `BACKEND_URL` | (required) | All | HTTP base URL |
| `BACKEND_WS_URL` | (required) | WebSocketClient | WebSocket base URL |
| `CLUSTER_ID` | (required) | All | Cluster identifier |
| `API_KEY` | (required, from Secret) | All | Bearer token for auth |
| `HEARTBEAT_INTERVAL` | `30` | HeartbeatSender | Seconds between heartbeats |
| `COLLECTION_INTERVAL` | `60` | MetricsCollector | Seconds between node metric sends |
| `POD_METRICS_INTERVAL` | `60` | PodMetricsCollector | Seconds between pod metric sends |
| `IMDS_POLL_INTERVAL_SECONDS` | `5` | SpotPoller | Seconds between IMDS polls |
| `LOG_LEVEL` | `INFO` | All | Python log level |
| `CLUSTER_NAME` | `k8s-cluster-{prefix}` | Agent startup | Display name for registration |
| `AWS_REGION` / `CLUSTER_REGION` | `us-east-1` | Agent startup | Region sent during registration |
| `NODE_NAME` | (from K8s downward API) | PodMetricsCollector | Node to scope pod metrics to |

---

## Appendix: Redis Keys (Agent-Related)

| Key | TTL | Set By | Purpose |
|---|---|---|---|
| `action_heartbeat:{action_id}` | 120 s | Backend Celery worker **and** agent (`_action_heartbeat_loop()` in `actuator.py`) | Detect stale in-progress actions |
| `rebalance:lock:{cluster_id}` | 2700 s (extended) | Backend auto_rebalancer | Per-cluster execution mutex |
| `node_joined:{instance_id}` | Varies | Backend node discovery pipeline | Signals new spot node joined K8s |
| `spot:asserted_spot:{instance_id}` | 600 s | Backend Phase 1 | Guard misclassification on direct launch |
| `spot:stabilization_lock:{cluster_id}` | 60 s | Backend rollback | Prevent immediate re-attempt after failure |
| `rebalance_failures:{instance_id}` | 86400 s | Backend failure path | Failure counter for backoff |
| `native_spot_status:{cluster_id}:{ng}` | 300 s | Backend API | Cache AWS native-spot status (5-min cache) |
