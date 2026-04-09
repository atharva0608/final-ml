# Agent System — Complete Technical Reference

> **Last validated**: June 2026 · **Source of truth**: `agent/` + `backend/routers/agents.py` + `backend/models/agent_action.py`
>
> Every claim is verified against the current codebase. Source file references are provided throughout.

---

## Table of Contents

1. [Agent Identity & Deployment](#1-agent-identity--deployment)
2. [Communication & Endpoints](#2-communication--endpoints)
3. [Agent Lifecycle & Failure Management](#3-agent-lifecycle--failure-management)
4. [Action Types & Dispatch](#4-action-types--dispatch)
5. [Rebalancing Method on Agent Side](#5-rebalancing-method-on-agent-side)
6. [Termination Modes (TERMINATE_NODE)](#6-termination-modes-terminate_node)
7. [Karpenter Management](#7-karpenter-management)
8. [Right-Sizing (PATCH_CONTAINER_RESOURCES)](#8-right-sizing-patch_container_resources)
9. [Data Fetched by the Agent](#9-data-fetched-by-the-agent)
10. [AWS API Calls from the Agent](#10-aws-api-calls-from-the-agent)
11. [Backend Response to Agent Messages](#11-backend-response-to-agent-messages)
12. [Monitoring & Debugging](#12-monitoring--debugging)
13. [Edge Cases & Resilience](#13-edge-cases--resilience)

---

## 1. Agent Identity & Deployment

**Source**: `agent/main.py`, `charts/spot-optimizer-agent/`

### The Two Agents

| | **Node Agent** | **Orchestrator** |
|---|---|---|
| **Primary role** | Execute K8s actions (cordon/drain/delete), collect per-node metrics, report spot-interruption events | Cluster-level coordination (Karpenter management, cluster-wide actions) |
| **Entry point** | `agent/main.py` — `Agent` class | Same codebase, different runtime role |
| **Deployment kind** | `DaemonSet` — one pod per node | `Deployment` — exactly 1 replica |
| **Image** | `atharva608/spot-optimizer-agent:{{ .Chart.AppVersion }}` | Same image |
| **Namespace** | `spot-optimizer` (configurable via `values.yaml`) | `spot-optimizer` |
| **Source** | `charts/spot-optimizer-agent/templates/daemonset.yaml` | `charts/spot-optimizer-agent/templates/orchestrator-deployment.yaml` |

**Image tag policy**: `pullPolicy: IfNotPresent` (fix N4). Agent sends `"version": "1.0.1"` in registration. Backend does **not reject** mismatched versions but logs a warning when version differs from `EXPECTED_AGENT_VERSION = "1.0.1"` (fix N3).

### Six Components (Threads)

| Component | Class | Thread Name | Purpose |
|-----------|-------|------------|---------|
| Metrics Collector | `MetricsCollector` | `MetricsCollector` | Node/pod metrics + cluster events |
| Action Actuator | `ActionActuator` | `ActionActuator` | Execute K8s actions |
| Heartbeat Sender | `HeartbeatSender` | `HeartbeatSender` | Liveness + health metrics + Karpenter detection |
| WebSocket Client | `WebSocketClient` | `WebSocketClient` | Bidirectional backend communication |
| Spot Poller | `SpotPoller` | `SpotPoller` | IMDS termination/rebalance detection |
| Pod Metrics Collector | `PodMetricsCollector` | `PodMetricsCollector` | Per-pod CPU/memory for right-sizing |

### Kubernetes RBAC

**ClusterRole**: `spot-optimizer-agent`

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

DaemonSet config: mounts `/host/proc` for psutil-based CPU/memory collection, runs with `hostNetwork: true`, tolerates all taints (`operator: Exists`).

---

## 2. Communication & Endpoints

### Protocols

| Channel | Protocol | Used For |
|---|---|---|
| Action delivery (primary) | **WebSocket** | Backend pushes actions to agent real-time |
| Action delivery (fallback) | **HTTP polling** | Agent polls when WebSocket is unavailable |
| Action result (fallback) | **HTTP POST** | When WebSocket send fails (BUG-1 fix) |
| Heartbeat | **HTTP POST** | Agent → backend every 30 s |
| Metrics | **HTTP POST** | Agent → backend every 60 s |
| Spot interruption notification | **HTTP POST** | Agent → backend on IMDS detection |
| Action result reporting | **WebSocket / HTTP POST** | Agent → backend after action completes |

### WebSocket

**Source**: `agent/websocket_client.py`

**URL**: `{BACKEND_WS_URL}/ws/cluster/{cluster_id}?agent_id={agent_id}`
**Authentication**: `Authorization: Bearer {API_KEY}` header on connection upgrade
**Ping**: 20-second interval, 10-second timeout
**Reconnect**: Exponential backoff `delay × 2^attempt`, capped at 60 seconds, max 10 attempts

### Two-Tier Message Buffer (BUG-1/BUG-4/N6 fix)

| Tier | Container | Max Size | Contents |
|------|-----------|----------|----------|
| Critical | `queue.Queue()` | Unbounded (never dropped) | `action_result`, `action_heartbeat`, `action_still_running` |
| Best-effort | `collections.deque(maxlen=200)` | 200 (oldest dropped) | Metrics, heartbeats |

On reconnect: critical queue flushed first, then metrics. If WebSocket send fails during flush, critical message is re-queued (BUG-12 fix).

### HTTP Endpoints Called by the Agent

| Method | URL | Frequency | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/agents/register` | Once on startup | Register agent with backend |
| `POST` | `/api/v1/agents/heartbeat` | Every 30 s | Liveness + health + Karpenter status |
| `POST` | `/api/v1/agents/deregister` | On graceful shutdown | Remove agent from backend |
| `GET` | `/api/v1/agents/actions/pending` | ~every 10 s (fallback) | Poll for pending actions |
| `POST` | `/api/v1/agents/actions/{action_id}/result` | After each action | HTTP fallback for action result |
| `POST` | `/api/v1/agents/actions/{action_id}/heartbeat` | Every 30 s during action | Action-level liveness signal (N5 fix) |
| `POST` | `/api/v1/agent-metrics/batch` | Every 60 s | Node-level metrics |
| `POST` | `/api/v1/pod-metrics/batch` | Every 60 s | Pod-level metrics |
| `POST` | `/api/v1/worker/spot-interruption` | On IMDS detection | Spot termination notice |
| `POST` | `/api/v1/worker/rebalance-recommendation` | On IMDS detection | EC2 rebalance recommendation |

> **Spot interruption authentication**: Uses `X-API-Key: {API_KEY}` header, not `Authorization: Bearer`.

### Payloads

#### Registration (`agent/main.py` lines 132–144)
```json
{
  "cluster_id": "<CLUSTER_ID>",
  "agent_id": "<hostname-uuid8>",
  "cluster_name": "<CLUSTER_NAME env or k8s-cluster-{prefix}>",
  "region": "<AWS_REGION or CLUSTER_REGION env>",
  "timestamp": "<ISO 8601 UTC>",
  "capabilities": ["metrics_collection", "action_execution", "websocket_communication"],
  "version": "1.0.1"
}
```

#### Heartbeat (`agent/heartbeat.py` lines 437–448)
```json
{
  "cluster_id": "<CLUSTER_ID>",
  "agent_id": "<agent_id>",
  "timestamp": "<ISO 8601 UTC>",
  "status": "healthy",
  "metrics": { "cpu": {...}, "memory": {...}, "disk": {...}, "network": {...}, "process": {...} },
  "components": { "collector": true, "actuator": true, "websocket": true },
  "karpenter_status": {
    "detected": true,
    "pods_running": 2,
    "controller_healthy": true,
    "webhook_healthy": true,
    "last_check": "<ISO 8601>",
    "error": null
  }
}
```

#### Spot Interruption (`agent/poller.py` lines 131–137)
```json
{
  "cluster_id": "<CLUSTER_ID>",
  "node_name": "<NODE_NAME>",
  "instance_id": "<EC2 instance ID from IMDS>",
  "action": "terminate",
  "termination_time": "<from IMDS notice>"
}
```

---

## 3. Agent Lifecycle & Failure Management

**Source**: `agent/main.py`

### Startup Sequence (lines 481–524)

```
1. Register signal handlers (SIGTERM, SIGINT)
2. Register with backend → POST /api/v1/agents/register
   → If fails: log error and EXIT (return code 1)
3. Initialize all 6 components
4. Start component threads (all daemon=True)
5. Enter monitor_components() loop (checks every 30 s)
```

### Thread Health Monitoring (`_restart_thread`, lines 424–453)

When a component thread dies:
- **Max restart attempts**: 5 per component
- **Backoff**: `min(2^count, 60)` seconds → 2s, 4s, 8s, 16s, 32s, then capped at 60s
- After 5 failed restarts: component marked DEAD, no further restarts (manual intervention required)
- Other components continue running

### Graceful Shutdown (lines 351–408)

```
1. Stop components in order: collector → actuator → websocket → spot_poller → pod_metrics → heartbeat (last)
2. Wait 10 seconds for thread join
3. Deregister from backend → POST /api/v1/agents/deregister
```

### Action Timeouts

| Action | Timeout | Configurable |
|---|---|---|
| Drain | 15 minutes default | Yes — `ClusterOptimizationSettings.drain_timeout_minutes` |
| Spot node join wait | 30 minutes | Yes — `ClusterOptimizationSettings.spot_join_timeout_minutes` |
| Spot stabilization wait | 90 seconds | No |
| Grace period per pod | 30 seconds default | Yes — via action payload `grace_period` |
| Action heartbeat TTL | 120 seconds | No |
| PENDING/PICKED_UP stale expiry | 15 minutes | No |

---

## 4. Action Types & Dispatch

**Source**: `backend/models/agent_action.py`, `agent/actuator.py` (`execute_action_v2`)

### 12 Action Types

| Action Type | Agent Handler | Purpose |
|---|---|---|
| `EVICT_POD` | `evict_pod()` | Evict a single pod |
| `CORDON_NODE` | `cordon_node()` | Mark node unschedulable |
| `UNCORDON_NODE` | `cordon_node(uncordon=True)` | Mark node schedulable |
| `DRAIN_NODE` | `drain_node()` | Evict all pods from node |
| `LABEL_NODE` | `label_node()` | Add/remove node labels |
| `TERMINATE_NODE` | `_terminate_node()` | Terminate EC2 instance (4 modes) |
| `FORCE_DELETE_NODE` | `force_delete_node()` | Force-delete K8s node object + clear finalizers |
| `UPDATE_DEPLOYMENT` | `update_deployment()` | Update replicas or image |
| `INSTALL_KARPENTER` | `install_karpenter()` | Install via Helm + create NodePools |
| `UNINSTALL_KARPENTER` | `uninstall_karpenter()` | Helm uninstall + delete namespace |
| `PATCH_CONTAINER_RESOURCES` | `_patch_container_resources()` | Update CPU/memory requests/limits |
| `REMOVE_POD_FINALIZERS` | `_remove_pod_finalizers()` | Clear stuck finalizers from Terminating pods |

### Priority-Based Ordering (Issue #7)

| Priority | Use Case | Ordering |
|----------|---------|----------|
| `0` (normal) | Auto-rebalancer actions | FIFO by `created_at` |
| `10` (emergency) | Spot interruption / IMDS event | Pre-empts normal actions |

SQL: `ORDER BY priority DESC, created_at ASC`

### Action Statuses

```
PENDING → PICKED_UP → COMPLETED
                    → FAILED
                    → EXPIRED (TTL: 1 hour default)
```

### HMAC Verification (`agent/actuator.py` lines 78–101)

Every action payload is verified with HMAC-SHA256 using `SECRET_KEY`. If signature fails, action is rejected.

### Node Resolution in Agent

For actions that reference nodes, the agent resolves node names using two strategies:
1. **`_find_node_by_instance_id()`** (preferred): Scans `spec.providerID` (`aws://<az>/<instance_id>`)
2. **`_find_node_name()`** (fallback): Uses K8s labels `node.kubernetes.io/instance-type` + `topology.kubernetes.io/zone`

---

## 5. Rebalancing Method on Agent Side

### Full Cordon → Drain → Terminate Sequence

The backend sends separate `AgentAction` records in order:

**Step 1: LABEL_NODE** — Labels replacement node: `karpenter.sh/do-not-disrupt=true`

**Step 2: CORDON_NODE** — Agent calls `patch_node()` with `spec.unschedulable = true`
- Z3 guard: Refuses to cordon agent's own node (`SELF_CORDON_ATTEMPT`)

**Step 3: DRAIN_NODE** — Exact drain algorithm (`agent/actuator.py`):
1. Cordon the node again (idempotent safety)
2. List all pods on the node (`list_pod_for_all_namespaces(field_selector=spec.nodeName=...)`)
3. Skip DaemonSet pods (owner reference check)
4. Skip mirror pods (`kubernetes.io/config.mirror` annotation)
5. Skip unmanaged pods unless `force=True`
6. For each remaining pod:
   - Check PDB: if PDB allows disruption → evict via `create_namespaced_pod_eviction()`
   - If PDB blocks and `force=True` → force-delete pod (grace_period=0)
   - If PDB blocks and `force=False` → 5 retries with 10s backoff, then `PDB_VIOLATION_MAX_RETRIES`
   - PDB check error → fail-open (allow drain, ISSUE-13 fix)
7. Clear stuck VolumeAttachments on the node (prevents Multi-Attach errors)
8. Result: success with eviction count, or failure with error list

**Step 4: TERMINATE_NODE** — See §6.

### Force Drain (Spot Interruption Path)

When spot IMDS detects termination:
- `force=True`: PDB checks bypassed, `grace_period_seconds = 0`
- Agent cordons + force-evicts everything (skip DaemonSet)

### PDB Handling

| Scenario | Behavior |
|----------|----------|
| Standard drain | Respect PDBs (5 retries, 10s backoff, then `PDB_VIOLATION_MAX_RETRIES`) |
| Force drain (spot interruption) | Bypass PDBs (force-delete with grace_period=0) |
| PDB check error | Fail-open — allow drain (ISSUE-13 fix, matches `kubectl drain` behavior) |
| Configurable via backend | `respect_pdb_enabled` in `StatelessRuntimeRules` controls `force` flag (fix N1) |

### VolumeAttachment Cleanup (`clear_stuck_volume_attachments`)

After drain completes, agent proactively clears stuck VolumeAttachments:
- Scans all VolumeAttachments on the drained node
- Identifies stuck: has attach/detach error or pending >60s
- Force-deletes stuck attachments to prevent Multi-Attach errors on new node
- Best-effort — failure doesn't fail the drain

---

## 6. Termination Modes (TERMINATE_NODE)

**Source**: `agent/actuator.py` `_terminate_node()` (lines 1180–1496)

Four termination modes controlled by `termination_mode` in payload:

### Mode: `karpenter` (Direct EC2)
```
1. ec2.terminate_instances() — ZERO ASG interaction
```
Karpenter manages node inventory independently of ASG DesiredCapacity.

### Mode: `replacement` (Detach-Not-Decrement)
```
1. Redis NX lock: asg:suspend_lock:{asg_name} (30s TTL)
2. suspend_processes(['Launch'])
3. detach_instances(ShouldDecrementDesiredCapacity=False) ← ASG keeps target
4. ec2.terminate_instances()
5. resume_processes(['Launch'])
```

### Mode: `asg_no_decrement` (Terminate via ASG, No Decrement)
```
1. terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=False)
```
Used when replacement is already attached to ASG.

### Mode: `scaledown` (Legacy ASG Decrement)
```
1. Pre-check: lower MinSize if MinSize ≥ DesiredCapacity
2. terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=True)
```
Used only for OD consolidation where ASG should shrink.

### Label Safety Check (TASK-1.2)
If node label `spot-optimizer/termination-mode=replacement` but caller requests `scaledown`, action is **BLOCKED** (`termination_mode_conflict` error).

### Fallback Chain
If EC2 terminate fails → Fall through to `kubectl delete node` (cloud controller cleans up EC2).

---

## 7. Karpenter Management

**Source**: `agent/actuator.py` (`install_karpenter`, `_create_default_karpenter_resources`)

### INSTALL_KARPENTER Flow

```
1. helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter
   --version <version> --namespace karpenter --create-namespace
   --set settings.clusterName=<name>
   --set settings.interruptionQueue=<sqs_queue_name>
   --wait --timeout 5m
2. Register KarpenterNodeRole as EC2_LINUX EKS access entry (RBAC-03)
3. Create default Karpenter resources
```

### Default Resources Created

| Resource | Name | Type | Purpose |
|----------|------|------|---------|
| EC2NodeClass | `default` | `karpenter.k8s.aws/v1` | AL2023 amiFamily with `al2023@latest` alias (dual amd64+arm64) |
| NodePool | `stateless-spot` | `karpenter.sh/v1` | Spot capacity, weight=10 (highest priority) |
| NodePool | `stateful-od` | `karpenter.sh/v1` | On-demand capacity, weight=5 |
| NodePool | `default` | `karpenter.sh/v1` | Spot+OD catch-all, weight=1 (fallback) |

### SQS Queue Name (Bug A-2 fix)
Strict queue name: uses `KarpenterInterruptionQueue-{cluster_name}` instead of bare cluster name. Prevents silent mismatch that breaks interruption handling.

### EKS Access Entry (RBAC-03)
`_register_karpenter_node_role_access_entry()` creates an `EC2_LINUX` access entry for `KarpenterNodeRole-{cluster_name}`. Without this, Karpenter-provisioned nodes cannot join the EKS cluster.

### UNINSTALL_KARPENTER Flow
```
1. helm uninstall karpenter --namespace karpenter --wait --timeout 3m
2. Delete namespace (best-effort)
```
Idempotent: if release not found, returns success.

---

## 8. Right-Sizing (PATCH_CONTAINER_RESOURCES)

**Source**: `agent/actuator.py` (`_patch_container_resources`, lines 1015–1106)

Patches CPU/memory requests and limits for a specific container in a Deployment, StatefulSet, or DaemonSet.

### Why Both Node and Pod Changes Are Needed

| Change | What | Effect |
|--------|------|--------|
| Karpenter NodePool update | Node size | Immediate — new node matches workload |
| PATCH_CONTAINER_RESOURCES | Pod spec | Requests/limits match actual usage → tighter bin-packing |

### Payload
```json
{
  "namespace": "production",
  "controller_type": "Deployment",
  "controller_name": "my-app",
  "container_name": "app",
  "resources": {
    "requests": {"cpu": "250m", "memory": "512Mi"},
    "limits": {"cpu": "500m", "memory": "768Mi"}
  }
}
```

Supports: `Deployment`, `StatefulSet`, `DaemonSet`.

---

## 9. Data Fetched by the Agent

### Kubernetes API Calls

| Resource | Verb | Why |
|---|---|---|
| `nodes` | `get`, `list`, `watch`, `patch`, `update` | Cordon/uncordon, labeling, metrics |
| `pods` | `list` | Drain (find pods on node), metrics |
| `pods/eviction` | `create` | Drain — evict each pod |
| `persistentvolumeclaims` | `get`, `list` | VolumeAttachment cleanup |
| `events` | `list` | Cluster events collection |
| `poddisruptionbudgets` | `get`, `list` | PDB check during drain |
| `karpenter.sh/nodepools` | `get`, `list`, `create` | Install Karpenter resources |
| `karpenter.k8s.aws/ec2nodeclasses` | `get`, `list`, `patch`, `create` | Install Karpenter resources |
| `metrics.k8s.io/nodes` | `list` | Node metrics (metrics-server) |
| `metrics.k8s.io/pods` | `list` | Pod metrics (right-sizing data) |
| `storage.k8s.io/volumeattachments` | `list`, `delete` | Stuck VolumeAttachment cleanup |

**Watch vs list**: Agent uses `list` calls, not watches. Metrics collected on fixed interval via `list` calls.

### Metrics Collection (`agent/collector.py`)

**Dual-source node metrics**:
1. **Priority 1**: Direct psutil via `/host/proc` (HOST_PROC env) — no API server load
2. **Priority 2**: Kubernetes metrics-server API (`metrics.k8s.io/v1beta1/nodes`)

**Collected data per node**: CPU (usage + capacity + allocatable), memory (usage + capacity + allocatable), ready status, unschedulable flag, labels, warm-up detection (<5 min old = CALIBRATING).

**Collected data per pod**: CPU/memory (usage + request + limit), restart count, labels, scheduling constraints (node_selector, tolerations, pod affinity/anti-affinity, topology spread constraints).

**Events**: Last 5 minutes of cluster events, including involved object metadata.

### Pod Metrics Collection (`agent/pod_metrics_collector.py`)

Dedicated collector for right-sizing analysis:
- Extracts controller owner references (Deployment/StatefulSet/DaemonSet — traces through ReplicaSet)
- DaemonSet mode: only sends pods on the local node (`NODE_NAME` env)
- Includes scheduling constraints: `node_selector`, `tolerations`, `affinity`, `topology_spread_constraints`
- Skips system namespaces: `kube-system`, `kube-public`, `kube-node-lease`

### IMDS Calls (`agent/poller.py`)

| Endpoint | Frequency | Purpose |
|---|---|---|
| `http://169.254.169.254/latest/meta-data/spot/instance-action` | Every 5 s | Detect spot termination notice |
| `http://169.254.169.254/latest/meta-data/events/recommendations/rebalance` | Every 5 s | Detect EC2 rebalance recommendation |
| `http://169.254.169.254/latest/meta-data/instance-id` | Once (cached) | Get instance ID for notifications |

### Karpenter Live Detection (`agent/heartbeat.py`, lines 194–287)

On every heartbeat cycle, the agent checks if Karpenter is actually running:
1. Scans pods in `karpenter` and `kube-system` namespaces
2. Checks label `app.kubernetes.io/name=karpenter`, falls back to name-based search
3. Reports: `detected`, `pods_running`, `controller_healthy`, `webhook_healthy`
4. Backend stores result in Redis: `karpenter:live_status:{cluster_id}` (60s TTL)

---

## 10. AWS API Calls from the Agent

### The Agent Makes AWS SDK Calls ONLY for Termination and Karpenter

| Operation | When | AWS Calls |
|-----------|------|-----------|
| TERMINATE_NODE (karpenter mode) | After drain | `ec2:TerminateInstances` |
| TERMINATE_NODE (replacement mode) | After drain | `autoscaling:SuspendProcesses`, `DetachInstances`, `ResumeProcesses`, `ec2:TerminateInstances` |
| TERMINATE_NODE (scaledown mode) | After drain | `autoscaling:DescribeAutoScalingInstances`, `TerminateInstanceInAutoScalingGroup` |
| INSTALL_KARPENTER | On install | `sts:GetCallerIdentity`, `eks:DescribeAccessEntry`, `eks:CreateAccessEntry` |
| Region detection | On terminate | IMDS token + placement/region (IMDSv2) |

### AWS Credentials Pattern

- **TERMINATE_NODE**: Uses node's IAM instance profile or IRSA
- **INSTALL_KARPENTER**: Uses node's IAM role via `boto3` (must have `sts:`, `eks:` permissions)
- **Everything else**: No AWS calls (K8s API only)
- Agent secret (`spot-agent-secret`) stores `API_KEY` for backend auth only

---

## 11. Backend Response to Agent Messages

### On Heartbeat (`backend/routers/agents.py` lines 250–350)

1. Looks up `Cluster` row by `cluster_id`
2. Sets `cluster.last_heartbeat = datetime.utcnow()`
3. If `cluster.agent_installed != 'Y'` (was reset by stale-agent task):
   - Sets `agent_installed = 'Y'`, `status = ACTIVE`
4. **Karpenter live detection**: Processes `karpenter_status` from payload:
   - If detected: Updates Redis keys `karpenter:detected:{cluster_id}` (120s), `spot:karpenter:installed:{cluster_id}` (1h)
   - If not detected and was previously installed: Marks as `missing` for UI reinstall prompt
   - Auto-sets `karpenter_mode = AUTO` if detected but not previously configured
5. Returns `{"success": true, "timestamp": "<UTC>"}`

### On Registration (`backend/routers/agents.py` lines 45–149)

If cluster doesn't exist in DB, **auto-creates** it:
- Creates default `Account` (with `is_validated='N'` — requires operator IAM setup)
- Creates `Cluster` with `status=ACTIVE`, `agent_installed='Y'`
- P-C19 fix: No placeholder ARN — operator must configure real credentials

### On Action Result (`/api/v1/agents/actions/{action_id}/result`)

HTTP fallback endpoint (BUG-1 fix):
1. Updates `AgentAction.status` to `completed` or `failed`
2. Sets `completed_at`, stores `result` and `error_message`
3. Clears `action_heartbeat:{action_id}` Redis key for immediate pickup
4. Backend's rebalancer state machine advances on next cycle

### On Spot Interruption

Backend calls `EmergencyEventProcessor` → creates `RebalancingAction` with `reason=spot_interruption` and priority queuing.

---

## 12. Monitoring & Debugging

### Agent Health Endpoints

**Source**: `agent/heartbeat.py` — HTTP server on **port 8080**

| Path | Purpose |
|---|---|
| `GET /healthz` | Liveness — returns 200 if agent process alive |
| `GET /readyz` | Readiness — returns 200 when collector is healthy |
| `GET /metrics` | JSON metrics (CPU, memory, disk, network, component health) |

DaemonSet liveness/readiness probes point to this server.

### Log Collection

All logs go to **stdout** via Python `logging` module. Picked up by cluster's standard log collection.

- **Log level**: Controlled by `LOG_LEVEL` env var (default: `INFO`)
- **Config reload**: SIGHUP reloads config without restart (`agent/config.py`)

```bash
# All action execution logs
kubectl logs -n spot-optimizer -l app=spot-optimizer-agent | grep "action"

# Drain steps
kubectl logs -n spot-optimizer -l app=spot-optimizer-agent | grep -i "drain\|evict\|PDB"

# Karpenter detection
kubectl logs -n spot-optimizer -l app=spot-optimizer-agent | grep "karpenter"
```

### Backend Stale Agent Detection

Celery task `reset_stale_agents` (every 1 minute):
- Queries clusters with `agent_installed='Y'` and `last_heartbeat < now() - 5 minutes`
- Resets: `agent_installed='N'`, `status=DISCOVERED`
- Clears CPU/memory utilization on all instances
- Cancels `PENDING`/`PICKED_UP` AgentActions → `CANCELLED` (BUG-9 fix)
- Marks `in_progress`/`waiting_agent` RebalancingActions → `failed` with `AGENT_WENT_OFFLINE`

### Admin Intervention

No dedicated admin "force-abort" endpoint. Instead:
1. Create `AgentAction` with type `UNCORDON_NODE` in DB — delivered via WebSocket
2. Cancel stuck `RebalancingAction`: set `current_state = 'FAILED'` in DB
3. Release cluster lock: delete Redis key `rebalance:lock:{cluster_id}`
4. Query agent metrics: `curl pod-ip:8080/metrics`

---

## 13. Edge Cases & Resilience

### Self-Termination Guards (Z3 Fix)

All destructive operations check `node_name == os.getenv('NODE_NAME')`:

| Method | Guard |
|--------|-------|
| `cordon_node()` | Returns `SELF_CORDON_ATTEMPT` |
| `drain_node()` | Returns `SELF_DRAIN_ATTEMPT` |
| `force_delete_node()` | Returns `SELF_DELETE_ATTEMPT` |

**Exception: Spot Interruption Self-Drain (BUG-13 fix)**: During genuine spot interruption via IMDS, the agent **must** cordon and drain its own node. `handle_spot_interruption()` bypasses the Z3 guard and calls `_emergency_self_cordon_drain()`.

### Agent Crash During In-Progress Action

1. Kubernetes restarts the pod (DaemonSet restart policy)
2. Agent re-registers with backend
3. In-progress action remains in `PICKED_UP` state
4. Backend detects via action heartbeat Redis key (TTL 120s)
5. After 2+ minutes with no refresh → action marked `FAILED` → rollback initiated
6. **No local state persistence** — no disk checkpoint, no SQLite

### WebSocket Reconnection

- Exponential backoff: `delay × 2^attempt`, capped at 60s
- Max 10 reconnect attempts before thread exits (thread monitor restarts it)
- In-flight actions continue during disconnect (separate thread)
- On reconnect: `action_still_running` message sent if action in progress (BUG-2 fix)
- Critical messages never dropped (unbounded `critical_queue`)

### Network Partition

| Side | Behavior |
|------|----------|
| **Agent** | Continues running indefinitely. IMDS polling independent. Heartbeats fail silently. |
| **Backend** (after 5 min) | `agent_installed='N'`, cancel pending actions, mark rebalancing as `AGENT_WENT_OFFLINE` |
| **Recovery** | First successful heartbeat restores `agent_installed='Y'`, `status=ACTIVE` |

### Component Thread Safety (BUG-14 fix)

`HeartbeatSender.component_health` protected by `threading.Lock` (`_health_lock`). All reads take snapshot `dict(self.component_health)` under lock.

### Action Heartbeat Dual-Writer (N5 fix)

Two writers maintain `action_heartbeat:{action_id}` (TTL 120s):
1. **Backend Celery worker** (`auto_rebalancer.py`): Updates via `redis.setex()` on each 15s cycle
2. **Agent** (`actuator.py` → `_action_heartbeat_loop()`): POSTs to `/api/v1/agents/actions/{action_id}/heartbeat` every 30s

Whichever ran most recently wins. Key expires only if **both** stop.

### FORCE_DELETE_NODE + Finalizer Cleanup (Issue #12)

After deleting the K8s node object, agent removes finalizers from any pods stuck in `Terminating` state that were on that node. Prevents StatefulSet pods from being stuck indefinitely.

### Duplicate Action Prevention

- `PICKED_UP` flag with `picked_up_at` timestamp on WebSocket delivery
- No agent-side dedup (trusts `PICKED_UP` flag)
- Backend distributed lock `lock:node_action:{cluster_id}` (1200s TTL, Z10 fix) serializes drains

---

## Appendix: Environment Variables

| Variable | Default | Component | Purpose |
|---|---|---|---|
| `BACKEND_URL` | (required) | All | HTTP base URL |
| `BACKEND_WS_URL` | (required) | WebSocketClient | WebSocket base URL |
| `CLUSTER_ID` | (required) | All | Cluster identifier |
| `API_KEY` | (required, from Secret) | All | Bearer token for auth |
| `SECRET_KEY` | (auto-generated) | ActionActuator | HMAC verification key |
| `HEARTBEAT_INTERVAL` | `30` | HeartbeatSender | Seconds between heartbeats |
| `COLLECTION_INTERVAL` | `60` | MetricsCollector | Seconds between node metric sends |
| `POD_METRICS_INTERVAL` | `60` | PodMetricsCollector | Seconds between pod metric sends |
| `IMDS_POLL_INTERVAL_SECONDS` | `5` | SpotPoller | Seconds between IMDS polls |
| `ACTION_POLL_INTERVAL` | `10` | ActionActuator | Seconds between action polls (HTTP fallback) |
| `LOG_LEVEL` | `INFO` | All | Python log level |
| `CLUSTER_NAME` | `k8s-cluster-{prefix}` | Agent startup | Display name for registration |
| `AWS_REGION` / `CLUSTER_REGION` | `us-east-1` | Agent startup | Region sent during registration |
| `NODE_NAME` | (K8s downward API) | PodMetricsCollector, drain guard | Node to scope pods to |
| `HOST_PROC` | (not set) | MetricsCollector | Host /proc path for psutil |
| `DRY_RUN` | `false` | Config | Log actions without executing |
| `WEBSOCKET_ENABLED` | `true` | Config | Enable WebSocket client |
| `BATCH_SIZE` | `100` | MetricsCollector | Max metrics per batch |

---

## Appendix: Redis Keys (Agent-Related)

| Key | TTL | Set By | Purpose |
|---|---|---|---|
| `action_heartbeat:{action_id}` | 120 s | Backend worker + Agent | Detect stale in-progress actions |
| `rebalance:lock:{cluster_id}` | 2700 s | Backend auto_rebalancer | Per-cluster execution mutex |
| `node_joined:{instance_id}` | Varies | Backend discovery pipeline | Signals new node joined K8s |
| `karpenter:live_status:{cluster_id}` | 60 s | Backend (from agent heartbeat) | Live Karpenter pod status |
| `karpenter:detected:{cluster_id}` | 120 s | Backend (from agent heartbeat) | Karpenter detection cache |
| `spot:karpenter:installed:{cluster_id}` | 3600 s | Backend (from agent heartbeat) | Karpenter installed mode |
| `spot:stabilization_lock:{cluster_id}` | 60 s | Backend rollback | Prevent immediate re-attempt |
| `rebalance_failures:{instance_id}` | 86400 s | Backend failure path | Failure counter for backoff |

---

## Appendix: File Index

| File | Lines | Primary Responsibility |
|------|-------|----------------------|
| `agent/main.py` | 547 | Agent startup, registration, thread monitoring |
| `agent/actuator.py` | 1909 | All K8s action execution (12 action types) |
| `agent/websocket_client.py` | 552 | WebSocket communication, two-tier buffer |
| `agent/heartbeat.py` | 537 | Health server, heartbeat, Karpenter detection |
| `agent/poller.py` | 199 | IMDS spot termination/rebalance polling |
| `agent/collector.py` | 585 | Node/pod metrics + cluster events |
| `agent/pod_metrics_collector.py` | 408 | Pod-level metrics for right-sizing |
| `agent/config.py` | 187 | Configuration validation + SIGHUP reload |
| `backend/routers/agents.py` | 351 | Registration, heartbeat, action heartbeat/result |
| `backend/models/agent_action.py` | 102 | 12 action types, priority, status enums |
