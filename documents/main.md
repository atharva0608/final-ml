# Spot Optimizer Platform — Comprehensive Technical Report

> **Source of truth**: All answers derived exclusively from `.py`, `.jsx`, `.yaml` code files.
> **Last updated**: 2026-03-12
> **Files analyzed**: 147+ backend Python services, 8 agent files, 67 models, 34 workers, 20 core modules
> **Depth**: Function-level analysis with exact line numbers, retry logic, fallback paths, and internal algorithms

---

## 1) Agents

### 1.1 Types of Agent

The platform deploys **two separate in-cluster workloads** into the client's Kubernetes cluster, both built from the same Docker image (`agent/Dockerfile` → `atharva608/spot-optimizer-agent:latest`):

| Workload | K8s Kind | Name | Replicas | Purpose |
|---|---|---|---|---|
| **DaemonSet Agent** | `DaemonSet` | `spot-agent` | 1 per node | Per-node data collection: pod/node metrics, IMDS spot polling, heartbeat |
| **Orchestrator** | `Deployment` | `spot-orchestrator` | 1 (singleton) | K8s action execution: cordon, drain, evict, patch NodePool, install/uninstall Karpenter |

**Deployed by**: `AgentInjectorService._deploy_agent()` (`backend/services/agent_injector.py` L1063-1444)
- DaemonSet created at L1200-1335
- Orchestrator Deployment created at L1338-1444

**DaemonSet Agent** (`spot-agent`) — runs on every node:
- `hostNetwork: true` for direct IMDS access and host metrics
- Mounts `/proc` → `/host/proc` (read-only) for `psutil` host metrics
- Sets `NODE_NAME` from `spec.nodeName` (Downward API) for per-node spot interruption handling
- Resources: `50m/64Mi` requests, `200m/256Mi` limits
- Tolerates ALL taints (`operator: Exists`) to ensure coverage on all nodes

**Orchestrator** (`spot-orchestrator`) — singleton Deployment:
- Polls `GET /api/v1/agents/orchestrator/{cluster_id}/pending-commands` for PENDING `AgentAction` records
- Executes K8s commands (CORDON_NODE, DRAIN_NODE, TERMINATE_NODE, PATCH_KARPENTER_NODEPOOL, INSTALL_KARPENTER, etc.)
- Reports results to `POST /api/v1/agents/orchestrator/{cluster_id}/command-result`
- Resources: `100m/128Mi` requests, `500m/512Mi` limits
- Readiness probe: `/healthz` on port 8080 (5s initial, 10s period)
- Liveness probe: `/healthz` on port 8080 (15s initial, 20s period)
- **Note**: Currently uses the same image as DaemonSet (`ORCHESTRATOR_IMAGE = AGENT_IMAGE`, L37-39)

Both share the same RBAC (`spot-agent-sa` ServiceAccount → `spot-agent-role` ClusterRole) and configuration (`spot-agent-config` ConfigMap + `spot-agent-secret` Secret).

**Internal components** (6 threads within the agent binary):

| Component | File | Used By | Purpose |
|---|---|---|---|
| **MetricsCollector** | `agent/collector.py` (559L) | DaemonSet | Collects pod + node + event metrics via K8s API or `psutil` (if `HOST_PROC` mounted), sends to backend every `COLLECTION_INTERVAL` (default 30s) |
| **ActionActuator** | `agent/actuator.py` (1635L) | Orchestrator | Executes K8s actions: cordon, uncordon, drain, evict, label, annotate, force-delete nodes, clear stuck VolumeAttachments |
| **SpotPoller** | `agent/poller.py` (191L) | DaemonSet | Polls AWS IMDS every 5s for spot termination notices + rebalance recommendations |
| **PodMetricsCollector** | `agent/pod_metrics_collector.py` (358L) | DaemonSet | Collects per-pod CPU/memory usage for right-sizing on local node only, sends every **5 minutes** |
| **HeartbeatSender** | `agent/heartbeat.py` (400L) | Both | Sends heartbeat every `HEARTBEAT_INTERVAL` (default 30s), exposes `/healthz` + `/readyz` K8s probes |
| **WebSocketClient** | `agent/websocket_client.py` (460L) | Orchestrator | Bidirectional WebSocket (`wss://`) for real-time action commands from backend |

### 1.2 Logic of Agent (How it Works)

**Startup sequence** (`agent/main.py`, `Agent.run()` L483-526):
1. Load config from environment variables
2. Call `register_with_backend()` → POST `/clusters/{cluster_id}/agent/register` with agent_id, version, capabilities
3. Initialize all 6 components in `initialize_components()`
4. Start each component in a separate daemon thread via `start_components()`
5. Enter `monitor_components()` loop (checks thread health, restarts dead threads)

**Action execution flow** (`actuator.py`, `ActionActuator`):
1. Backend pushes command via WebSocket: `{"type": "command", "action_id": "...", "action_type": "cordon_node", "payload": {...}}`
2. `WebSocketClient.handle_command()` (L262-310) dispatches to actuator
3. **HMAC verification**: `verify_signature()` (L78-101) — computes `HMAC-SHA256(canonical_payload, SECRET_KEY)` and compares
4. **PDB check**: `check_pdb_violation()` (L103-128) — queries PDBs in pod's namespace, checks `disruptions_allowed < 1`
5. Execute via K8s API (python `kubernetes` client)
6. Report result back: `{"type": "action_result", "action_id": "...", "success": true/false, "result": {...}}`

**Polling loop** (`poller.py`, `SpotPoller.run()` L96-119):
- Every 5 seconds: GET `http://169.254.169.254/latest/meta-data/spot/instance-action` (1s timeout)
- HTTP 200 → termination detected → `_notify_backend()` → POST `/api/v1/worker/spot-interruption`
- Also checks rebalance recommendations: `http://169.254.169.254/latest/meta-data/events/recommendations/rebalance`
- On termination: calls `actuator.handle_spot_interruption(notice)` for immediate cordon+drain

**Spot Interruption Protocol** (`actuator.py` L1559-1610):
1. `cordon_node(node_name, uncordon=False)` — mark unschedulable immediately
2. `drain_node(node_name, force=True, grace_period=30)` — **force=True** bypasses PDB by force-deleting protected pods (0 grace period) instead of eviction
3. `request_fallback_node(node_name)` — fire-and-forget POST to `/api/v1/clusters/{cluster_id}/fallback` requesting immediate OD replacement

**Node Termination Multi-Path** (`actuator._terminate_node()` L1120-1287):
1. Resolve node: `_find_node_by_instance_id()` (matches K8s `spec.providerID` = `aws://{az}/{instance_id}`)
2. If `decrement_asg=True` (default): ASG path
   a. `describe_auto_scaling_groups()` → get current `DesiredCapacity` + `MinSize`
   b. If `MinSize >= DesiredCapacity` → lower MinSize first via `update_auto_scaling_group()`
   c. Set `DesiredCapacity = max(new_min, current - 1)` before terminate
   d. `terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=True)`
3. If ASG fails → fallback to direct `ec2.terminate_instances()`
4. If EC2 unavailable → fallback to `core_v1.delete_node(name=node_name)` (K8s cloud controller cleans up)

**Action Dispatch** (`actuator.execute_action_v2()` L1328-1449) — 14 action types:
`EVICT_POD`, `CORDON_NODE`, `UNCORDON_NODE`, `FORCE_DELETE_NODE`, `DRAIN_NODE`, `LABEL_NODE`, `UPDATE_DEPLOYMENT`, `PATCH_KARPENTER_NODEPOOL`, `INSTALL_KARPENTER`, `UNINSTALL_KARPENTER`, `PATCH_CONTAINER_RESOURCES`, `TERMINATE_NODE`, `ANNOTATE_NODE` (via LABEL_NODE)
- All enum values normalized to UPPERCASE at dispatch boundary (FIX-ENUM-01)
- Node resolution priority: `payload.node_name` → `_find_node_by_instance_id(instance_id)` → `_find_node_name(instance_type, az)`

**HTTP Action Polling** (fallback when WebSocket unavailable, L1477-1557):
- Polls `GET /api/v1/agents/actions/pending` every `ACTION_POLL_INTERVAL` (default 10s)
- Executes each command via `execute_action_v2()`, reports result via `POST /api/v1/agents/actions/{id}/result`

**Component Health Monitor** (`main.py` L415-481):
- Runs every 30s in main thread
- Checks all 6 daemon threads via `thread.is_alive()`
- Auto-restarts dead threads (no limit on restart count)
- Graceful shutdown on SIGTERM/SIGINT → `stop_components()` → `deregister_from_backend()`

### 1.3 How Agent is Installed

**From UI → Backend → K8s**:
1. User creates cluster in UI → backend generates unique `CLUSTER_ID` + `API_TOKEN`
2. Backend's `AgentInjectorService` remotely deploys both workloads into the EKS cluster:
   a. **STS AssumeRole** into customer's AWS account (L235-309)
   b. **Get EKS token** via presigned STS GetCallerIdentity URL (L1005-1061)
   c. Create namespace `spot-optimizer`, Secret, ConfigMap, ServiceAccount, ClusterRole, ClusterRoleBinding
   d. Create **DaemonSet** `spot-agent` (L1200-1335)
   e. Create **Deployment** `spot-orchestrator` (L1338-1444)
3. Alternative: User applies YAML manifest manually: `kubectl apply -f agent.yaml` (template in `backend/templates/k8s/agent.yaml` — DaemonSet only)
4. Update endpoint: `PUT /api/v1/clusters/{id}/agent/update` → idempotently re-deploys DaemonSet + Orchestrator (L357-379)

**Environment variables** (`agent/config.py`, `Config.load_config()` L36-62):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `API_URL` | Yes | — | Backend API base URL |
| `CLUSTER_ID` | Yes | — | Unique cluster identifier |
| `API_TOKEN` | Yes | — | Bearer auth token |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `COLLECTION_INTERVAL` | No | `30` | Metrics collection interval (seconds) |
| `HEARTBEAT_INTERVAL` | No | `30` | Heartbeat interval (seconds) |
| `NAMESPACE` | No | `spot-optimizer` | Agent namespace |
| `DRY_RUN` | No | `false` | Log actions without executing |
| `WEBSOCKET_ENABLED` | No | `true` | Enable WebSocket client |

**Docker build**: `agent/Dockerfile` → `agent/build-and-push.sh` (builds + pushes to ECR)

**Additional env vars** (`agent/main.py` init):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `BACKEND_URL` | Yes | `http://localhost:8000` | HTTP API base URL |
| `BACKEND_WS_URL` | Yes | `ws://localhost:8000/ws` | WebSocket URL |
| `API_KEY` | Yes | — | Bearer auth token |
| `SECRET_KEY` | No | auto-generated | HMAC verification key |
| `CLUSTER_ID` | Yes | — | Unique cluster identifier |
| `AGENT_ID` | No | `{hostname}-{uuid[:8]}` | Auto-generated agent ID |
| `NODE_NAME` | No | — | K8s node name (for spot interruption handling) |
| `ACTION_POLL_INTERVAL` | No | `10` | HTTP polling interval (seconds) |
| `AWS_REGION` / `CLUSTER_REGION` | No | `us-east-1` | AWS region for registration |

### 1.4 Agent ↔ Backend Communication

| Channel | Direction | Protocol | Endpoint | Agent |
|---|---|---|---|---|
| Registration | Agent → Backend | HTTP POST | `/agents/register` | Both |
| Heartbeat | Agent → Backend | HTTP POST | `/agents/heartbeat` | Both |
| Metrics | Agent → Backend | HTTP POST | `/clusters/{id}/metrics` | DaemonSet |
| Pod Metrics | Agent → Backend | HTTP POST | `/api/v1/pod-metrics/batch` | DaemonSet |
| Spot Interruption | Agent → Backend | HTTP POST | `/agents/spot-interruption` | DaemonSet |
| Rebalance Rec | Agent → Backend | HTTP POST | `/agents/rebalance-recommendation` | DaemonSet |
| Action Commands (WS) | Backend → Agent | WebSocket | `wss://{host}/ws/cluster/{id}` | Orchestrator |
| Action Commands (Poll) | Orchestrator → Backend | HTTP GET | `/agents/orchestrator/{id}/pending-commands` | Orchestrator |
| Action Results (WS) | Agent → Backend | WebSocket | Same WS connection | Orchestrator |
| Action Results (HTTP) | Orchestrator → Backend | HTTP POST | `/agents/orchestrator/{id}/command-result` | Orchestrator |
| Health Probes | K8s → Agent | HTTP GET | `/healthz`, `/readyz` | Both |

**Authentication**: All HTTP requests include `Authorization: Bearer {API_TOKEN}`. WebSocket uses query params: `?agent_id={agent_id}`. Actions verified via HMAC-SHA256.

### 1.5 Where Agent Stores What

| Data | Storage | Details |
|---|---|---|
| Configuration | In-memory (env vars) | Loaded at startup from environment |
| Metrics buffer | In-memory list | `MetricsCollector.metrics_buffer` — flushed to backend |
| Instance ID | In-memory cache | `SpotPoller._instance_id` — cached after first IMDS call |
| K8s client | In-memory | `kubernetes.config.load_incluster_config()` — uses service account |
| Component health | In-memory dict | `HeartbeatSender.component_health` |
| WebSocket msg buffer | In-memory deque | `WebSocketClient.message_buffer` (maxlen=100) — flushed on reconnect |

**No persistent local storage**. Agent is stateless — all state is sent to backend DB/Redis.

### 1.6 Additional Clarifications (Code-Verified)

**Q: How does the same container image determine whether to run as DaemonSet or Orchestrator?**

Currently, both workloads share the **same entrypoint** (`python main.py`) and the **same image** (`atharva608/spot-optimizer-agent:latest`). There is **no runtime role differentiation** via environment variables in the shipped code. The comment at `agent_injector.py` L37-39 (`ORCHESTRATOR_IMAGE = AGENT_IMAGE`) explicitly states this. The Orchestrator Deployment simply runs the same binary; both components (MetricsCollector for DaemonSet, WebSocketClient for Orchestrator) start in all instances. The practical differentiation comes from K8s topology: the DaemonSet runs per-node (can poll IMDS via `hostNetwork: true`), while the Deployment is a singleton that polls `pending-commands` and executes actions.

> **Nuance**: The WebSocket client starts in ALL agent pods (DaemonSet and Orchestrator). However, only the Orchestrator pod has a meaningful connection because action commands from the backend target the cluster-level WebSocket channel. DaemonSet pods on individual nodes connect but receive no action commands — they primarily send metrics and heartbeats. The SpotPoller (IMDS) only works on the DaemonSet because it requires `hostNetwork: true` to reach `169.254.169.254`.

**Q: What happens to in-flight actions if the Orchestrator pod is killed mid-action?**

Actions stuck in `PENDING` or `PICKED_UP` status for >15 minutes are **auto-expired** by the `auto_rebalancer.py` (L2367-2382). The rebalancer queries `AgentAction` records where `status IN (PENDING, PICKED_UP)` and `created_at < now() - 15min`, then sets `status=EXPIRED`. This prevents dead actions from blocking the rebalancer indefinitely. The next rebalancer cycle will create a fresh action.

**Q: Are actions processed in order or is there priority logic?**

Actions are processed in **FIFO order** by `created_at` timestamp. The Orchestrator polls `/agents/orchestrator/{id}/pending-commands` which returns actions ordered by `created_at ASC` (L375). There is no priority queue — emergency actions bypass cooldowns at creation time but are still fetched in chronological order. Emergency actions are created by the `emergency_rebalancer`, which force-clears locks and cooldowns before insertion, so they are processed in the next cycle without waiting.

**Q: Is the Orchestrator polling endpoint authenticated the same way as other agent endpoints?**

**No — security gap identified.** The DaemonSet endpoints (`/agents/actions/pending`, `/agents/register`, `/agents/heartbeat`) use `Depends(validate_api_key)` which requires Bearer token auth. However, the Orchestrator endpoint `GET /agents/orchestrator/{cluster_id}/pending-commands` (L357-395) does **NOT** use `validate_api_key` — it takes `cluster_id` as a path parameter and queries directly. Similarly, `POST /agents/orchestrator/{cluster_id}/command-result` (L398-429) also lacks auth. The Orchestrator uses the same `API_TOKEN` for any HTTP requests it makes, but the backend doesn't validate it on these specific endpoints.

**Q: WebSocket reconnection — what are the exact backoff parameters and buffer behavior?**

From `agent/websocket_client.py`:
- **Reconnect delay**: Exponential backoff from `1s` → `60s` (L67: `min_reconnect_delay=1`, `max_reconnect_delay=60`)
- **Max attempts**: 10 consecutive failures (L68: `max_reconnect_attempts=10`)
- **Message buffer**: `collections.deque(maxlen=1000)` (L68: `max_buffer_size=1000`)
- **Buffer overflow**: Messages are **silently dropped** (deque automatically evicts oldest)
- **On reconnect**: Buffered messages are flushed to the new connection
- **After 10 failures**: Falls back to HTTP action polling (`ACTION_POLL_INTERVAL=10s`)

**Q: What does the agent binary do at the entrypoint? Is there a single `main()` or separate workload-specific paths?**

Single entrypoint: `agent/main.py` → `Agent.run()` (L483-526). All 6 components (MetricsCollector, ActionActuator, SpotPoller, PodMetricsCollector, HeartbeatSender, WebSocketClient) are initialized and started as daemon threads. There is **no conditional branch** based on a `ROLE` env var — both DaemonSet and Orchestrator run identical code. The DaemonSet benefits from `hostNetwork: true` (IMDS access) and `NODE_NAME` (per-node targeting), while the Orchestrator benefits from WebSocket + action polling.

### 1.7 What Happens if Agent is Uninstalled

| Impact | Details |
|---|---|
| **Metrics stop** | Node/pod/event metrics stop flowing → backend marks cluster `DISCONNECTED` after heartbeat timeout |
| **Actions can't execute** | Backend queues AgentActions but they time out (auto-expire >15 min) → rebalancing actions fail with "agent unreachable" |
| **Spot polling stops** | IMDS termination detection stops → interruptions only detected via SQS/EventBridge (if configured) |
| **Right-sizing stops** | Pod metrics stop → no new right-sizing recommendations |
| **Existing instances persist** | EC2 instances are NOT terminated — they continue running as-is |
| **Optimization pauses** | control_plane_loop skips cluster (no heartbeat) |
| **Data retained** | All historical data in DB (instances, metrics, proposals) is preserved |

**API key rotation on disconnect**: When a user calls `POST /clusters/{id}/agent/disconnect` (`cluster_routes.py` L531-565), the backend generates a new `secrets.token_urlsafe(32)` API key and sets `agent_installed="N"`, `status=DISCONNECTED`. The running agent pods immediately start receiving **HTTP 401** responses and can no longer authenticate. Historical data is preserved.

**Full removal**: `DELETE /clusters/{id}/agent` (`cluster_routes.py` L568-666) additionally deletes all `pod_metrics` and `instance` records, resets status to `DISCOVERED`, and clears `last_heartbeat`. Also attempts K8s uninstall (deletes DaemonSet + Orchestrator + namespace) and AWS cleanup (deletes Karpenter IAM resources).

---

## 2) Data Sources

### 2.1 Price Data Sources

| Price Type | AWS Account | API | Frequency | Storage |
|---|---|---|---|---|
| **Spot prices** | Client account (via STS AssumeRole) | `ec2.describe_spot_price_history()` | Every 10 min | Redis: `pricing:{region}:spot:{instance_type}:{az}` |
| **On-demand prices** | Platform (master) account | AWS Pricing API `GetProducts` | Daily at 1 AM | Redis: `pricing:{region}:ondemand:{instance_type}` |
| **Spot Advisor data** | Public (no auth) | AWS Spot Advisor JSON endpoint | Daily at 2 AM | Redis: `spot:advisor:{region}` → DB: `spot_advisor_rates` table |

**Pricing worker** (`backend/workers/tasks/pricing_worker.py`):
- `refresh_regional_pricing()` runs every 10 min
- Aggregates required instance types across all clusters in region
- Batch fetches spot prices via EC2 API (client account credentials via STS AssumeRole)
- Updates `pricing:last_updated:{region}` timestamp
- **Enterprise guardrail**: If not updated within 15 minutes, optimizations are blocked
- **Emergency refresh**: `emergency_pricing_refresh()` triggered when stale pricing detected → clears `PRICING_STALE` flags
- **Health endpoint**: `get_pricing_health()` returns per-region freshness status

#### Pricing Staleness — Decision Engine Impact (Code-Verified)

From `decision_engine.py` **Step 1b** (L195-230):
- The Decision Engine checks `pricing:last_updated:{region}` timestamp in Redis
- If `staleness_minutes > 15` → **reject ALL decisions** for the cluster with reason `"pricing_stale"`
- If **no timestamp exists** (key missing) → **fail-open** (allow decisions to proceed)
- This means: a region that has NEVER had pricing data collected will NOT be blocked, but a region whose pricing stopped updating WILL be blocked after 15 minutes
- The `pricing_worker.py` clears `PRICING_STALE` flags when it successfully refreshes prices

### 2.2 Data Fetch Frequency

| Data | Frequency | Source |
|---|---|---|
| Node/pod metrics | 30s | Agent → `/clusters/{id}/metrics` |
| Pod right-sizing metrics | 5 min | Agent → `/api/v1/pod-metrics/batch` |
| Spot prices | 10 min | `pricing_worker` → AWS EC2 API |
| On-demand prices | Daily 1 AM | `pricing_worker` → AWS Pricing API |
| Spot Advisor | Daily 2 AM | `spot_advisor_scraper` → AWS JSON |
| EC2 instances (discovery) | 5 min | `discovery_worker` → AWS EC2 |
| EKS clusters (discovery) | 5 min | `discovery_worker` → AWS EKS |
| ML pipeline (pool ranking) | 1 hour | `atharvaai_worker` → ONNX inference |
| Family baselines | Weekly | `atharvaai_worker` |
| Agent heartbeat | 30s | Agent → `/clusters/{id}/heartbeat` |

### 2.3 Database Tables (Key Tables)

| Table | Model File | Purpose |
|---|---|---|
| `clusters` | `cluster.py` | EKS cluster metadata, status, settings |
| `instances` | `instance.py` | EC2 instances (id, type, lifecycle, az, state, architecture, standby) |
| `accounts` | `account.py` | AWS accounts (role_arn, external_id, regions) |
| `cluster_optimization_settings` | `cluster.py` | Per-cluster toggles (auto_rebalance, rightsizing, diversify, etc.) |
| `optimization_strategy` | `cluster.py` | Risk ceiling, min savings, tradeoff, diversity strictness |
| `stateless_runtime_rules` | `cluster.py` | Max rebalances/24h, resize cooldown, PDB respect, prewarm |
| `stateful_rules` | `cluster.py` | Manual resize, approval required, max downscale % |
| `rebalancing_actions` | `rebalancing_action.py` | OD→Spot and S2S migration actions |
| `agent_actions` | `agent_action.py` | K8s actions sent to agent (CORDON, DRAIN, TERMINATE, PATCH) |
| `pod_metrics` | `pod_metric.py` | Pod-level CPU/memory for right-sizing |
| `termination_events` | `termination_event.py` | Spot interruption history |
| `rightsizing_proposals` | `rightsizing_proposal.py` | Right-sizing recommendations |
| `spot_advisor_rates` | `spot_advisor_rates.py` | AWS Spot Advisor data per instance type |
| `family_hour_baselines` | `family_hour_baseline.py` | Weekly family-hour statistics for ML |
| `pricing` | `pricing.py` | Spot/OD price history |
| `daily_cluster_stats` | `daily_cluster_stats.py` | Daily aggregated cluster statistics |
| `optimizer_state` | `optimizer_state.py` | Per-cluster optimizer phase tracking |
| `system_config` | `system_config.py` | Platform-wide config (AWS keys, settings) |
| `api_keys` | `api_key.py` | Per-cluster API keys for agent auth |
| `audit_log` | `audit_log.py` | User action audit trail |
| `hibernation_schedules` | `hibernation_schedule.py` | Cluster hibernation schedules (many-to-many) |

### 2.4 AWS Permissions Required

| Permission | Account | Purpose |
|---|---|---|
| `sts:AssumeRole` | Platform → Client | Cross-account access |
| `ec2:DescribeInstances` | Client | Discovery, state sync |
| `ec2:DescribeSpotPriceHistory` | Client | Spot price collection |
| `ec2:RunInstances` | Client | Direct spot launch (non-Karpenter) |
| `ec2:TerminateInstances` | Client | Node termination (rebalancing) |
| `ec2:DescribeInstanceTypes` | Client | Instance catalog |
| `ec2:CreateFleet` (DryRun) | Client | Capacity validation |
| `ec2:DescribeInstanceAttribute` | Client | Copy user-data for spot launch |
| `ec2:DescribeSubnets` | Client | AZ-aware subnet selection |
| `eks:DescribeCluster` | Client | Cluster validation |
| `autoscaling:DescribeAutoScalingGroups` | Client | ASG discovery |
| `autoscaling:SuspendProcesses/ResumeProcesses` | Client | ASG freeze during rebalance |
| `autoscaling:UpdateAutoScalingGroup` | Client | Hibernation nuclear + ASG pre-decrement |
| `sqs:ReceiveMessage/DeleteMessage` | Client | Spot interruption events |
| `pricing:GetProducts` | Platform | On-demand pricing |
| `ce:GetCostAndUsage` | Client | Cluster cost calculation (Cost Explorer) |
| `eks:ListClusters` | Client | Multi-region EKS discovery |

### 2.5 Discovery Worker Deep Dive

**Source**: `backend/workers/tasks/discovery.py` (868 lines)

**Multi-region scanning** (L322-377): Scans 14 AWS regions for each account:
`ap-south-1, ap-southeast-1/2, ap-northeast-1/2, us-east-1/2, us-west-1/2, eu-west-1/2, eu-central-1, ca-central-1, sa-east-1`
- Account's configured region scanned first
- EKS clusters + EC2 instances scanned independently per region

**Cross-account auth** (L282-319):
1. `_get_platform_sts_client()` — uses `PLATFORM_AWS_ACCESS_KEY` + `PLATFORM_AWS_SECRET` from `SystemConfig` table
2. `sts.assume_role(RoleArn=account.role_arn, ExternalId=account.external_id)`
3. Same-account fallback: If AssumeRole fails with AccessDenied and caller account == role account → uses env credentials directly

**RC3 Guard — SPOT→OD lifecycle protection** (L720-768):
- Problem: AWS omits `InstanceLifecycle` for some Karpenter spot nodes → appears as OD
- Solution: Redis counter `rc3:od_streak:{instance_id}` (30-min TTL)
- Requires 3 consecutive OD observations before allowing SPOT→OD downgrade
- Confirmed SPOT reading immediately resets counter

**RC4 Fix — Ghost instance cleanup** (L794-839):
- After scan: any DB instance with `state='running'` NOT seen in scan → marked `terminated`
- Terminated instances older than 5 min → deleted from DB

**Cluster cleanup grace periods** (L583-633):
- Grace 1: Never delete clusters created < 60 minutes ago
- Grace 2: Agent-installed clusters require 2h heartbeat absence
- Grace 3: Any cluster with heartbeat < 10 min ago preserved

**Cost calculation** (L436-515):
- Primary: AWS Cost Explorer (`ce.get_cost_and_usage()`) filtered by EKS tag
- Fallback: Sum instance prices from `pricing_helper.get_ec2_price()` per running instance

### 2.6 Additional Clarifications (Code-Verified)

**Q: Does a pricing API downtime block ALL clusters or only the affected region?**

Only the affected region. Pricing staleness is checked per-region via `pricing:last_updated:{region}`. If `ap-south-1` pricing goes stale but `us-east-1` is fresh, only `ap-south-1` clusters are blocked. Each region has its own staleness check at Decision Engine Step 1b.

**Q: Is there an emergency pricing refresh mechanism?**

Yes. `pricing_worker.py` has `emergency_pricing_refresh()` which is triggered when stale pricing is detected. It clears the `PRICING_STALE` Redis flag (`cluster:{id}:pricing_stale`) and forces an immediate re-fetch of spot prices for the region.

**Q: How are "required instance types" aggregated for spot price fetching?**

From `pricing_worker.py` L33-119: `refresh_regional_pricing()` calls `pricing_service.refresh_regional_pricing_batch(region=reg, instance_types=None)`. When `instance_types=None`, `AWSPricingService` auto-detects by querying all clusters in that region from the DB, then collecting their associated instance types from the `instances` table. This ensures only relevant types are fetched, minimizing AWS API calls.

**Q: What happens if the pricing refresh fails for one region?**

Per-region resilience: the worker iterates `regions_to_refresh` and wraps each region in `try/except` (L67-96). If one region fails, it logs an error and continues to the next. The `pricing:last_updated:{region}` timestamp is only updated on success — so a failed region will trigger the 15-minute staleness gate on its next Decision Engine evaluation.

**Q: How does the discovery worker handle partial region failures?**

From `discovery.py` L336-377: Both EKS scanning (L337-353) and EC2 scanning (L360-377) use per-region `try/except` with `continue` on failure. If `ap-northeast-2` is inaccessible, the worker logs `"Region {scan_region} not accessible"` at DEBUG level and proceeds to the next region. Cluster cleanup runs only AFTER all regions are scanned (`_cleanup_deleted_clusters()`), preventing false-positive deletions from single-region failures.

**Q: Is `pricing:last_updated:{region}` updated on partial or full refresh?**

It is updated by `AWSPricingService.refresh_regional_pricing_batch()` after successfully fetching prices for that region. The timestamp is set regardless of how many instance types were fetched — even a partial refresh (some type failures) updates the timestamp as long as the batch call succeeds overall.

---

## 3) Actions

### 3.1 Auto Rebalance ON Only

**What happens**: The `execute_rebalancing` Celery task runs every ~15s. For each cluster with `auto_rebalance_enabled=True`, it:
1. Finds running ON_DEMAND instances
2. Uses ML pool ranking to find better spot pools (3-pass Double Gate)
3. Creates `RebalancingAction` (type: `od_to_spot`)
4. Executes via `execute_rebalancing_action()` → 2-phase model

**Stateful vs Stateless**:
- **Stateless nodes** (`WorkloadInspector` → `STATELESS_ELIGIBLE`): Eligible for automatic migration
- **Stateful nodes** (`STATEFUL_PROTECTED`): Blocked from auto-rebalance unless `auto_stateful_rightsizing_enabled=True` AND `StatefulRules.require_approval=False`

**Failure handling**:
- CORDON failure → uncordon + terminate orphan spot + resume ASG
- DRAIN failure (PDB conflict) → skip EC2 terminate + terminate orphan spot + clear cooldown for retry
- EC2 terminate failure → terminate orphan spot
- All instance types exhausted → fail action, set instance cooldown

**Verification of success**:
- Phase 1: Wait for spot node to appear in K8s with `node_name` and running ≥90s
- Phase 2: After DRAIN, verify pods rescheduled to new node (grace period check)
- Post-success: Re-calculate realized savings, update cluster `realized_savings_monthly`

**Fallback mechanisms**:
1. Architecture filter (prevents ARM/AMD mismatch)
2. Instance type cascade (tries up to 6 types)
3. Karpenter → Direct EC2 fallback
4. S2S OD fallback (for risk triggers)
5. Pre-launch orphan detection (prevents duplicate spots)
6. Direct EC2 orphan termination (bypasses DB lag)

**Data used**:
- DB: `instances`, `clusters`, `cluster_optimization_settings`, `optimization_strategy`, `stateless_runtime_rules`, `rebalancing_actions`, `agent_actions`
- Redis: cooldowns, locks, pool rankings, node classifications, architecture constraints

**Communication with agents**: Backend creates `AgentAction` records (CORDON_NODE, DRAIN_NODE, TERMINATE_NODE, PATCH_KARPENTER_NODEPOOL) → pushed to **Orchestrator** via WebSocket or polled via HTTP (`/agents/orchestrator/{id}/pending-commands`)

**AWS operations**: `RunInstances` (spot), `TerminateInstances`, `DescribeInstances`, `SuspendProcesses/ResumeProcesses` (ASG), `DescribeAutoScalingGroups`, `DescribeSubnets`, `DescribeInstanceAttribute`

#### Realized Savings Calculation (Code-Verified)

From `savings_calculator.py` (L109-146):
```
realized_savings = SUM( MAX(0, od_price - spot_price) )  for each running SPOT instance
```
- `od_price` = on-demand price for the instance type from Redis `pricing:{region}:ondemand:{type}`
- `spot_price` = live spot price from Redis `pricing:{region}:spot:{type}:{az}`
- Only running SPOT instances are summed (lifecycle=SPOT, state=running)
- Result stored as `Cluster.realized_savings_monthly` in DB
- Recalculated after every successful rebalance (`calculate_real_savings.delay()`) and periodically by Celery beat

#### Action Expiry (Code-Verified)

From `auto_rebalancer.py` L2367-2382:
- `AgentAction` records in `PENDING` or `PICKED_UP` status for **>15 minutes** are auto-expired
- This prevents orphaned actions (from agent restarts or crashes) from blocking the rebalancer indefinitely
- The auto-expiry runs at the start of each rebalancer cycle (every ~15s)

#### Conflict Resolution — Both Modes ON (Code-Verified)

When BOTH auto-rebalance and auto-rightsizing are enabled, the **Optimizer Coordinator** resolves conflicts by comparing three options:
- **Option A**: New pool only (keep current size)
- **Option B**: New size + best pool for new size (combined)
- **Option C**: Do nothing

Each option is scored by Expected Value (`EV = savings × (1 - risk)`) and the highest EV wins. A node cannot simultaneously be processed by both modes — the rebalancer holds a per-cluster lock (`key_rebalance_lock`) that blocks concurrent operations.

#### Cluster Autoscaler Interaction

If the cluster autoscaler adds a new node during rebalancing, it does **not** interfere. The rebalancer targets specific instance IDs (not node counts), and ASG `SuspendProcesses`/`ResumeProcesses` is used during active rebalancing to prevent ASG from launching replacement nodes for terminated instances.

**User input settings** + defaults:

| Setting | Table | Default |
|---|---|---|
| `auto_rebalance_enabled` | `cluster_optimization_settings` | `False` |
| `manual_approval_required` | `cluster_optimization_settings` | `False` |
| `cooldown_override_minutes` | `cluster_optimization_settings` | `60` |
| `diversify_pools` | `cluster_optimization_settings` | `False` |
| `max_family_diversification_cap_pct` | `cluster_optimization_settings` | `40` |
| `maintain_standby` | `cluster_optimization_settings` | `False` |
| `target_spot_exposure_pct` | `cluster_optimization_settings` | `100` |
| `risk_ceiling_percent` | `optimization_strategy` | `25` |
| `min_savings_percent` | `optimization_strategy` | `15` |
| `risk_savings_tradeoff_pct` | `optimization_strategy` | `20` |
| `max_rebalances_per_24h` | `stateless_runtime_rules` | `5` |
| `respect_pdb_enabled` | `stateless_runtime_rules` | `True` |

**With/without Karpenter**:
- **With Karpenter**: Creates `PATCH_KARPENTER_NODEPOOL` AgentAction → agent patches NodePool CRD → Karpenter provisions spot node
- **Without Karpenter**: `_launch_spot_instance_direct()` → boto3 `run_instances()` with spot market options, copies AMI/subnet/SGs/user-data from source instance

### 3.2 Auto Rightsizing ON Only

**What happens**: Right-sizing engine runs via `optimizer_coordinator_worker.py` → `RightSizingService.generate_recommendations()`:
1. Queries `pod_metrics` table (168h window)
2. Calculates P50, P95, P99 for CPU + memory per controller
3. Recommends: P95 + 20% safety buffer
4. Classifies: OVERSIZED (request ≥50% above P95), UNDERSIZED (P95 ≥95% of request), RIGHT_SIZED

**Stateful vs Stateless**: Both analyzed. Recommendations generated for all controllers. Stateful nodes flagged separately.

**Instance-Aware mode** (`instance_aware_rightsizing=True`): Only generates recommendations if a better spot pool exists (double gate: risk < 15% AND spot < OD price).

**Settings**:

| Setting | Default | Purpose |
|---|---|---|
| `auto_rightsizing_enabled` | `False` | Enable right-sizing recommendations |
| `instance_aware_rightsizing` | `False` | Double-gate pool validation |
| `resize_cooldown_minutes` | `120` | Cooldown between resizes |
| `resize_headroom_multiplier` | `1.2` | Safety buffer multiplier |

**Data**: Reads from `pod_metrics` table (sent by `PodMetricsCollector` every 5 min). Writes to `rightsizing_proposals` table.

### 3.3 Both ON (Synergy Mode)

When BOTH `auto_rebalance_enabled=True` AND `auto_rightsizing_enabled=True`:

1. **Bin-packing is activated** during OD→Spot rebalancing:
   ```
   required_vcpu = current_vcpu × (cpu_util / 100) × 1.30  (30% buffer)
   required_mem  = current_mem  × (mem_util / 100) × 1.30
   ```
   Selects cheapest instance type fitting requirements AND costing less than current.

2. **API force-locks** `optimization_target` to `"spot"` (prevents conflict)

3. **Optimizer Coordinator** evaluates 3 options:
   - Option A: Current size + new pool (pool only)
   - Option B: New size + best pool for new size (combined)
   - Option C: Current size + current pool (do nothing)
   Picks highest EV option.

4. **Auto-stateful rightsizing** phase runs after main loop: finds over-provisioned OD stateful nodes, queues CORDON→DRAIN→TERMINATE with 48h cooldown.

---

## 4) ML Model

### 4.1 Models Used

| Model | File | Type | Purpose |
|---|---|---|---|
| **Classifier** | `ml_model/classifier_6.onnx` | ONNX binary classification | Predicts `risk_probability` (0-1) |
| **Regressor** | `ml_model/regressor_6.onnx` | ONNX regression | Predicts `predicted_savings` (%) |
| **Category mapping** | `ml_model/category_mapping.json` | JSON | Maps categorical features to integer indices |
| **Risk threshold** | `ml_model/risk_threshold.json` | JSON | `optimal_threshold: 0.35`, `model_version: 6` |

### 4.2 Features (45 total)

| Category | Count | Features |
|---|---|---|
| Temporal | 10 | Hour, day_of_week, sin/cos hour, sin/cos day, month, quarter, is_weekend, is_us_business_hours |
| Lag/History | 3 | 1h, 4h, 24h lagged savings |
| Rolling Windows | 8 | 4h/24h mean, std, min, max of savings |
| Price Dynamics | 5 | Spread, ratio, momentum, OD-spot delta, volatility |
| Family Patterns | 6 | Family-hour mean/std savings, family popularity, family stability |
| Family Stress | 3 | Cross-instance contagion count, stress ratio, stress decay |
| Events | 3 | Holiday flag, stress period active, volatility regime |
| Categorical | 7 | Family index, size index, AZ index (encoded via category_mapping.json) |

### 4.3 Pipeline Invocation

- **Global pipeline** runs every **1 hour** via `execute_pool_ranking_pipeline` Celery task
- Processes ALL regions (11 regions) with ALL instance types
- **Per-cluster**: Not per-cluster — global cache shared by all clusters
- **Per-customer**: Not per-customer — same ML models for all

**Data flow**:
1. `MLFeatureService.engineer_features()` → 45-feature vector per pool
2. `classifier_6.onnx` → `risk_probability`
3. `regressor_6.onnx` → `predicted_savings`
4. `ml_score = savings × (1 - risk)`
5. Store top 100 pools per region in Redis: `global_pool_rankings:{region}` (65-min TTL)

**Input data from**: Redis (spot prices, on-demand prices, family baselines, spot advisor data)
**Output data to**: Redis: `global_pool_rankings:{region}` → consumed by Decision Engine and Auto-Rebalancer

### 4.4 ML Circuit Breaker

If ONNX inference fails 3+ times in 10 minutes:
- Redis: `atharvaai:ml_fail_count` (INCR, 10-min TTL)
- Redis: `atharvaai:ml_degraded` (10-min TTL)
- Fallback: heuristic scoring `savings × (1 - advisor_risk)`

### 4.5 Additional Clarifications (Code-Verified)

**Q: How is the ML model trained? What data does it use?**

Training script: `ml_model/model/spot_optimizer_v1/scripts/train.py` (286 lines).
- **Framework**: LightGBM (hybrid model — classifier + regressor)
- **Training data**: Historical spot pricing data loaded via `load_all_data(config)` from Parquet files in `ml_model/model/spot_optimizer_v1/data/`
- **Features**: 45 features (same as inference — temporal, lag/history, rolling windows, price dynamics, family patterns, stress events)
- **Horizon**: Single horizon: 6h (36 intervals at 10-min granularity)
- **Split**: Chronological (not random) — `train_pct / val_pct / test_pct` from config
- **Output**: `.onnx` models saved in timestamped `training_results/run_{timestamp}/models/` folders
- **Hyperparameters**: `num_leaves=21, max_depth=9, lambda_l2=0.319, learning_rate=0.075, early_stopping=100 rounds`
- **Validation**: MAPE, RMSE, R² for regressor; F1, AUC for classifier; threshold optimization on validation set
- **Pool baselines**: Computed per `(InstanceType, AZ)` — mean + std of historical savings for Z-score classification
- **Feature caching**: Results cached as `preprocessed_features_cache.parquet` to skip recomputation

**Q: What happens if an ONNX model file is missing or corrupted?**

There is **no explicit `FileNotFoundError` handler** in the ONNX loading code. If the model file is missing at startup, the `onnxruntime.InferenceSession()` constructor will raise an exception. The ML Circuit Breaker (Section 4.4) would activate after 3 consecutive failures — falling back to heuristic scoring. However, a completely missing model file would cause ALL inference attempts to fail, triggering the circuit breaker every 10 minutes indefinitely.

**Q: How does the system handle new instance families that have no historical data?**

For families without historical data, the feature engineering pipeline sets family-level features (family-hour mean/std, popularity, stability) to **zero or NaN** which LightGBM handles natively. The `category_mapping.json` file maps known families to integer indices; unknown families would get a default/unknown index. Pool rankings depend on available pricing data — if spot pricing exists for a new family (from AWS API), it will be ranked; if no pricing exists, it won't appear in the candidate pool.

**Q: How often are models retrained?**

Retraining is **NOT automated** in the current pipeline. The training script (`ml_model/model/spot_optimizer_v1/scripts/train.py`) is run manually by the data science team when sufficient new data accumulates. The model version is tracked via `risk_threshold.json` (`model_version: 6`) and validated at Decision Engine Step 3 (`CURRENT_MODEL_VERSION = "6"`). There is no A/B testing or canary deployment mechanism — a new model replaces the old `.onnx` files directly.

**Q: How does `category_mapping.json` handle unknown families?**

The mapping file contains known `(family, size, az)` → integer index mappings. For unknown categories not present in the mapping, the feature engineering code falls back to a default index (typically 0 or -1). LightGBM treats these as a separate category naturally, but predictions for completely unknown families will have lower confidence since the model has no training data for them.

---

## 5) Decision Engine

**Source**: `backend/core/decision_engine.py` (781 lines)

### 5.1 Purpose

Evaluates whether to switch a node from its current pool to a better spot pool. Runs as part of `control_plane_loop.py` (every 5 min) for proactive optimization.

### 5.2 Inputs

| Input | Source | Storage |
|---|---|---|
| Global pool rankings | `PoolRankingService` | Redis: `global_pool_rankings:{region}` |
| Cluster optimization mode | `Cluster.optimization_mode` | DB: `clusters` table |
| Node classification | `WorkloadInspector` | Redis: `spot:node_classification:{id}` |
| Cluster instability state | `risk_engine.py` | Redis: `spot:cluster_state:{id}` |
| Circuit breaker state | `circuit_breaker.py` | Redis: `cb:state:{id}` |
| Cooldown status | `cooldown_controller.py` | Redis: various `spot:cooldown:*` keys |
| Pricing data | `pricing_worker` | Redis: `pricing:{region}:*` |
| Trust phase | `optimizer_coordinator.py` | Redis/DB: `OptimizerState` |

### 5.3 15-Step Pipeline

| Step | Logic | Data Source |
|---|---|---|
| 1 | Cluster cooldown check (bypass if emergency) | Redis: `spot:cooldown:cluster:{id}` |
| 1b | Pricing freshness ≤15 min (fail-open if no timestamp) | Redis: `pricing:last_updated:{region}` |
| 2 | Pool cooldown filter (ITN bypass if emergency) | Redis: `spot:cooldown:pool:{pool_id}` |
| 2b | Fetch node classification from WorkloadInspector | Redis: `spot:node_classification:{id}` |
| 2c | Filter STATELESS_ELIGIBLE nodes only | Classification cache |
| 3 | Validate model version matches `CURRENT_MODEL_VERSION = "6"` | DB: `Cluster.model_version` |
| 4 | Load optimization profile (COST_FIRST/BALANCED/NO_DOWNTIME_FIRST) | DB: `Cluster.optimization_mode` |
| 5 | Load global rankings from Redis | Redis: `global_pool_rankings:{region}` |
| 6 | THREE-LAYER RISK CEILING: Profile + Volatility adj + Trust phase | Config + Redis |
| 7 | Capacity freshness penalty (stale DryRun data penalized) | Redis: `capacity:{type}:{az}` |
| 8 | Volatility guard (handled in Step 6) | — |
| 9 | Re-score all pools with `evaluate_candidate_ev()` | `ev_model.py` |
| 10 | Score current pool (simple EV: savings × (1-risk)) | `ev_model.py` |
| 11 | Template + Karpenter filters | DB: template mappings |
| 12 | Diversity check + deadlock protection | `DiversityEnforcer` |
| 13 | Delta threshold check (best_ev - current_ev ≥ profile.delta_threshold) | Config |
| 14 | APPROVED — select best candidate | — |

### 5.4 Validation

- Rejection counters tracked in Redis: `spot:rejection_counters:{cluster_id}` (24h TTL, hash)
- Each step logs reason if rejected → observable via `ObservabilityLogger`
- Decision audit: Redis key `obs:decisions:{cluster_id}` (last 100 decisions, 24h TTL)

### 5.5 Account Used

The Decision Engine **does not make AWS API calls directly**. It consumes data already fetched by other workers (pricing_worker, discovery_worker) using client account credentials.

### 5.6 Additional Clarifications (Code-Verified)

**Q: What exactly is the "delta threshold" and how does it differ per profile?**

From `decision_engine.py` L56-84 — `OPTIMIZATION_PROFILES`:

| Profile | `risk_ceiling` | `delta_threshold` | Meaning |
|---|---|---|---|
| `COST_FIRST` | 0.25 (25%) | 0.02 (2%) | Accept higher risk, switch on tiny improvements |
| `BALANCED` | 0.20 (20%) | 0.03 (3%) | Moderate risk, moderate improvement required |
| `NO_DOWNTIME_FIRST` | 0.10 (10%) | 0.04 (4%) | Very low risk, significant improvement required |

The `delta_threshold` is the **minimum required improvement in Expected Value (EV)** between the best candidate pool and the current pool. At Decision Engine Step 13: `if (best_candidate_ev - current_pool_ev) < profile.delta_threshold → REJECT`. This prevents switching for marginal gains.

**Q: What happens if global pool rankings cache is empty?**

From `decision_engine.py` → `_load_global_rankings()`: If the Redis key `global_pool_rankings:{region}` is missing or empty, the method returns `None`. The pipeline then **rejects the decision** at Step 5 with reason `"no_global_rankings"`. There is **no synchronous rebuild** — the system waits for the next hourly `execute_pool_ranking_pipeline` Celery task to populate the cache.

**Q: How does the volatility guard adjust the risk ceiling?**

At Step 6 (THREE-LAYER RISK CEILING), the effective risk ceiling is computed as:
```
effective_ceiling = profile.risk_ceiling × volatility_multiplier × trust_phase_multiplier
```
- `volatility_multiplier`: Derived from recent spot price volatility in the region (higher volatility → lower multiplier → tighter risk)
- `trust_phase_multiplier`: Based on `OptimizerState` — new clusters start with stricter ceilings that relax over time as the system proves stable

---

## 6) Execution Engine

**Source**: `backend/core/action_executor.py` (18916 bytes) + `backend/services/execution_controller.py` (231 lines)

### 6.1 6-Step Safe Node Replacement

| Step | Action | K8s/AWS API | Fallback |
|---|---|---|---|
| 1 | DryRun capacity check | `ec2:CreateFleet` (DryRun) | Skip if not available |
| 2 | Provision substitute node | `ec2:RunInstances` or Karpenter PATCH | Instance type cascade |
| 3 | Wait substitute Ready (300s timeout) | K8s: GET node, check Ready condition | Timeout → fail + rollback |
| 4 | Drain original node | K8s: cordon + evict pods (60s grace) | PDB violation → rollback |
| 5 | Verify workload health | K8s: check pod restarts, ready count | Unhealthy → rollback |
| 6 | Terminate original node | `ec2:TerminateInstances` | Failure → rollback |

### 6.2 Agent Interaction

Backend creates `AgentAction` records in DB → agent polls via HTTP or receives via WebSocket.

Action types (`agent_action.py`): `CORDON_NODE`, `UNCORDON_NODE`, `DRAIN_NODE`, `TERMINATE_NODE`, `PATCH_KARPENTER_NODEPOOL`, `LABEL_NODE`, `ANNOTATE_NODE`, `EVICT_POD`, `FORCE_DELETE_NODE`, `INSTALL_KARPENTER`, `UNINSTALL_KARPENTER`, `PATCH_CONTAINER_RESOURCES`, `UPDATE_DEPLOYMENT`

### 6.3 Right-Sizing Execution (Container Patching)

`actuator._patch_container_resources()` (L957-1100):
- Patches CPU/memory requests+limits for a specific container in a Deployment/StatefulSet/DaemonSet
- Uses K8s strategic merge patch on `spec.template.spec.containers`
- **Why needed**: After node size change (Karpenter), pod spec still requests old resources → blocks bin-packing efficiency
- Payload: `{namespace, controller_type, controller_name, container_name, resources: {requests: {cpu, memory}, limits: {cpu, memory}}}`

### 6.4 Permissions

- **Client account**: `ec2:RunInstances`, `ec2:TerminateInstances`, `ec2:CreateFleet` (DryRun), `autoscaling:*`
- **K8s RBAC**: `get/list/patch` nodes, `create` pods/eviction, `get` PDBs, `get/list` pods, `get/patch` deployments/statefulsets/daemonsets

### 6.5 Control Plane Loop (8-Step Decision Cycle)

**Source**: `backend/workers/tasks/control_plane_loop.py` (390 lines)

Runs **every 5 minutes** per active cluster via `run_all_clusters_decision_cycle` Celery beat task.

| Step | Method | Purpose |
|---|---|---|
| 1 | `_step1_update_market_signals()` | Fetch latest spot prices, volatility, advisor data, pool pressure |
| 2 | `_step2_update_blacklist_tiers()` | Cleanup expired blacklist entries |
| 3 | `_step3_update_cluster_instability()` | Auto-recover circuit breaker based on elapsed time |
| 4 | `_step4_filter_nodes()` | Return nodes eligible for optimization (stateless, off cooldown) |
| 5 | `_step5_rightsizing_baseline()` | Compute current sizing baseline for the cluster |
| 6 | `_step6_evaluate_pools()` | Evaluate candidate pools with full risk + EV model + Decision Engine |
| 7 | `_step7_diversification_simulation()` | Filter candidates that would violate diversification constraints |
| 8 | `_step8_build_execution_plan()` | Build final execution plan respecting concurrency limits |

Services initialized in `_init_services()`: `BlacklistService`, `CooldownController`, `PoolRankingService`, `RiskEngine`, `DecisionEngine`, `WorkloadInspector`, `DiversityEnforcer`, `RightsizingService`

### 6.6 Optimizer Coordinator (Phased Timing Strategy)

**Source**: `backend/workers/tasks/optimizer_coordinator_worker.py` (251 lines)

| Task | Frequency | Purpose |
|---|---|---|
| `pool_optimization_worker` | Every 30 min | Spot ML pool ranking — only changes pool, never size |
| `rightsizing_evaluation_worker` | Every 24h | Pod-level right-sizing — only proposes, does not execute |
| `evaluate_proposal_task` | Event-driven | Compares Option A (size+pool) vs Option B (new pool) vs Option C (nothing) using combined EV |
| `execute_approved_proposal_task` | User/auto trigger | Executes approved rightsizing proposals |

**Phase requirements**:
- Pool optimization: Only runs if OptimizerState in `INITIAL_POOL_OPTIMIZATION`, `STABILIZATION`, or `COOLDOWN`
- Rightsizing evaluation: Requires ≥1 hour stabilization + ≥24 hour stability window

### 6.7 Additional Clarifications (Code-Verified)

**Q: How does the platform prevent two rebalancing actions from running in parallel on the same cluster?**

Three layers of concurrency control (`auto_rebalancer.py`):
1. **Global execution lock**: `lock:workers.auto_rebalancer` — Redis NX lock with 300s TTL (L1398). Only one rebalancer cycle runs at a time across all clusters.
2. **Per-cluster rebalance lock**: `key_rebalance_lock(cluster_id)` — Redis NX lock with 600s TTL (L501-511). If a concurrent action holds the lock, new actions are deferred with status `deferred`.
3. **Stabilization lock**: `CooldownController.is_stabilization_locked()` (L517-520) — cross-system safety gate. If another system (e.g., rightsizing) recently acted, the cluster enters a 5-min stabilization period.

**Q: How does the emergency rebalancer bypass these locks?**

From `emergency_rebalancer.py` L50-52:
```python
redis.delete(key_cluster_cooldown(cluster_id))
redis.delete(key_rebalance_lock(cluster_id))
```
The emergency rebalancer **force-clears** both the cluster cooldown and the rebalance lock before processing. Emergency actions always take priority over normal automation.

**Q: What is the instance type cascade algorithm?**

From `auto_rebalancer.py` L408-463 (`_launch_spot_instance_direct()`):
1. Takes `target_instance_types` list from ML pool rankings (ordered by EV score, best first)
2. Tries up to **6 types** (`[:6]` slice): for each type, calls `ec2.run_instances()` with `MarketType=spot`
3. On capacity error (`InsufficientInstanceCapacity`, `SpotMaxPriceTooLow`, `InstanceLimitExceeded`, `Unsupported`) → logs warning and **continues to next type**
4. On any other error → **propagates exception** immediately
5. If ALL 6 types exhausted → returns `(None, None, None)` → action marked `failed`
6. **AZ handling**: If `target_az` is specified, finds a subnet in that AZ via `describe_subnets`. If target AZ has no available subnet, falls back to the source instance's subnet.

**Q: Is the DryRun capacity check configurable or can it be skipped?**

There is **no configuration flag** to disable DryRun in the current code. The DryRun step (`ec2.create_fleet(DryRun=True)`) is always attempted when available. If the API returns an error (e.g., permissions issue), the step is skipped and the system proceeds to the actual launch. This is a "best-effort" capacity pre-check.

---

## 7) Karpenter

### 7.1 What it Does

Karpenter is a Kubernetes node autoscaler that provisions the right nodes for your workloads. The platform integrates with Karpenter to manage node pools (instance types, lifecycle, architecture):

- **`karpenter_mode = None`**: Not installed → platform uses direct EC2 `RunInstances()` for spot launches
- **`karpenter_mode = "dry_run"`**: Insights only — recommendations shown but no EC2 changes
- **`karpenter_mode = "auto"`**: Full autonomous management — platform patches NodePool CRDs

### 7.2 Installation & Uninstallation

**Install** (`actuator.install_karpenter()` L782-868):
1. SQS queue: `KarpenterInterruptionQueue-{cluster_name}` (Bug A-2 fix: never fallback to bare cluster name)
2. `helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter --version 1.0.8 --wait --timeout 5m`
3. IRSA: annotates ServiceAccount with `eks.amazonaws.com/role-arn`
4. Registers `KarpenterNodeRole` access entry for EKS cluster
5. Creates default `EC2NodeClass` (AL2023, `amiSelectorTerms: [{alias: al2023@latest}]` — dual-arch auto-resolution)
6. Creates default `NodePool` with `karpenter.sh/v1` API, allows both `amd64` + `arm64`

**Uninstall** (`actuator.uninstall_karpenter()` L1289-1326):
1. `helm uninstall karpenter --namespace karpenter --wait --timeout 3m`
2. Delete `karpenter` namespace (best-effort)
3. Idempotent: release-not-found treated as success

**NodePool Patching** (`actuator.patch_karpenter_nodepool()` L699-780):
- Patches `spec.template.spec.requirements` (NOT `spec.requirements` — wrong path is silently ignored)
- Requirements: `karpenter.sh/capacity-type`, `node.kubernetes.io/instance-type`, optional `topology.kubernetes.io/zone` + `kubernetes.io/arch`
- 404 fallback: auto-creates NodePool by inferring cluster name from ConfigMap or node labels
- CRD missing: returns error "Karpenter CRDs not found — install Karpenter first"

Agent heartbeat includes Karpenter detection → sets Redis key: `spot:karpenter:installed:{cluster_id}`

#### Karpenter Detection Mechanism (Code-Verified)

From `auto_rebalancer.py` L2264-2273 and L814-834:
- **Primary**: DB column `Cluster.karpenter_mode` (Enum: `auto`, `dry_run`, or `None`) — set when user enables Karpenter via UI
- **Fallback**: Redis key `spot:karpenter:installed:{cluster_id}` — set by agent heartbeat when Karpenter pods are detected in-cluster
- **Pre-check**: Before using Karpenter path, the rebalancer verifies that a `INSTALL_KARPENTER` AgentAction with status `COMPLETED` exists for the cluster (L820-834). If no completed install found → falls back to direct EC2 launch. This prevents silently patching a non-existent NodePool.

### 7.3 Karpenter Mode Behavior

**With Karpenter installed (auto mode)**:
1. Backend creates `PATCH_KARPENTER_NODEPOOL` AgentAction with payload: `{architecture: [...], instance_types: [...], lifecycle: "spot"}`
2. Agent patches Karpenter NodePool CRD via K8s CustomObjectsApi (`karpenter.sh/v1` group)
3. Karpenter provisions appropriate spot node (AL2023 resolves correct AMI per architecture)
4. Platform waits for new node to join cluster (timeout: varies by node count)
5. Phase 2: CORDON → DRAIN → TERMINATE old node

**PATCH failure modes**: 404 (NodePool not found → auto-creates), 403 (RBAC → error returned), CRD missing ("Karpenter CRDs not found"), timeout → falls back to `_launch_spot_instance_direct()`.

**Without Karpenter**:
1. Backend calls `_launch_spot_instance_direct()` directly
2. Copies AMI, subnet, security groups, IAM profile, user-data from source instance
3. Architecture filter ensures AMI compatibility (L753-786)
4. Launches spot instance via `ec2.run_instances()` with `InstanceMarketOptions: {MarketType: spot}`
5. Waits for instance to join cluster as K8s node

### 7.4 Karpenter Fallback & SQS

**SQS Consumer** (`sqs_consumer.py` L29-284): Polls SQS interruption queues every 30s for Karpenter clusters.
- Supported events: `EC2 Spot Instance Interruption Warning`, `EC2 Instance State-change Notification` (stopping/stopped), `AWS Health Event` (spotInterruption/scheduledChange)
- On detection: calls `trigger_emergency_rebalancing()` → dispatches `emergency_rebalancer` Celery task

**Fallback API** (`cluster_routes.py`, `/fallback`): Agent calls on interruption → backend switches NodePool to `on-demand`: Redis key `spot:ondemand_fallback:{id}` (12h TTL).

**Karpenter → Direct EC2 fallback**: If PATCH_KARPENTER_NODEPOOL fails → `_launch_spot_instance_direct()` used instead.

### 7.5 Karpenter-Specific Redis Keys

| Key | TTL | Purpose |
|---|---|---|
| `spot:karpenter:installed:{id}` | Variable | Detection flag |
| `spot:karpenter:nodepool_updated:{id}` | 30 min | NodePool refresh cooldown |
| `spot:karpenter:provision_requested:{id}` | 15 min | Last-node provision dedup |
| `spot:ondemand_fallback:{id}` | 12h | On-demand fallback flag |
| `spot:execution_failures:{id}` | 10 min | Karpenter circuit breaker |

---

## 8) Emergency System

### 8.1 What Constitutes an Emergency

| Event | Source | Bypass |
|---|---|---|
| Spot termination notice (2-min warning) | IMDS via SpotPoller / SQS / EventBridge | Delta threshold, savings check, cluster cooldown, pool cooldown |
| EC2 rebalance recommendation | IMDS via SpotPoller | Proactive migration trigger |
| Instance state-change to stopping/stopped | SQS EventBridge | Emergency rebalancing |
| AWS Health Event (spotInterruption) | SQS | Emergency rebalancing |

### 8.2 Emergency Flow

**Source**: `backend/workers/tasks/emergency_rebalancer.py` (287L) + `termination_monitor.py` (340L)

**Step-by-step**:
1. **Detection**: SpotPoller (IMDS every 5s) OR SQS consumer (every 30s) OR EventBridge
2. **Notification**: Agent POSTs to `/api/v1/worker/spot-interruption` with `{cluster_id, instance_id, action, termination_time}`
3. **Backend processing** (`detect_termination_notice()` in `termination_monitor.py`):
   a. Create `TerminationEvent` record in DB
   b. Blacklist pool: `SADD risky_pools:{region}` + metadata with TTL (12h)
   c. Update pool pressure in `risk_engine.py`
   d. Override cluster cooldown via `CooldownController.override_for_emergency()`
4. **Emergency rebalancing** (`emergency_rebalancer.py`):
   - **Standby-first path** (if `maintain_standby=True` and standby node exists):
     1. UNCORDON standby node
     2. CORDON interrupted node
     3. DRAIN interrupted node
     4. Terminate interrupted node
     5. Mark standby as active
     6. Launch new standby asynchronously
   - **Normal emergency** (no standby): Creates `RebalancingAction` with type `emergency` → auto_rebalancer picks up (bypasses double gate)

### 8.3 Monitoring

- `TerminationEvent` records in DB
- Redis: `spot:cluster_state:{id}` tracks instability
- Circuit breaker: moves NORMAL → CONSERVATIVE → HALT
- Cross-cluster propagation: `InstabilityPropagator` updates pool pressure for ALL clusters sharing affected pool

### 8.4 Permissions

- **Client account**: `ec2:TerminateInstances`, `ec2:RunInstances`, `sqs:ReceiveMessage/DeleteMessage`
- **Agent K8s RBAC**: `patch` nodes (cordon/uncordon), `create` pods/eviction (drain)

### 8.5 Additional Clarifications (Code-Verified)

**Q: Can emergency actions for different clusters run in parallel?**

Yes. The `emergency_rebalancer` is a Celery task (queue: `emergency`). Each invocation clears locks for its **specific cluster only** (`key_cluster_cooldown(cluster_id)`, `key_rebalance_lock(cluster_id)`). Different clusters' emergency tasks run independently. However, within a single cluster, the standby failover is serial: UNCORDON → CORDON → DRAIN → TERMINATE → mark active → launch new standby.

**Q: What is the emergency drain grace period?**

From `emergency_rebalancer.py` L186-206:
- `grace_period=90` (90 seconds — gives pods time to shut down cleanly)
- `force=True` — bypasses PodDisruptionBudgets immediately (AWS does NOT honor PDBs at the 2-minute hard deadline)
- `emergency=True` — signals the actuator to use the 90-second escalation timer
- Any pod still running at T-90s is **force-deleted** with `grace_period=0` so K8s can reschedule before the 120-second AWS kill

**Q: What happens if no standby node exists during an emergency?**

From `emergency_rebalancer.py` L115-120: Falls back to `_execute_normal_emergency()` which creates a `RebalancingAction` with `action_type="emergency"` and `action_metadata={"emergency": True, "bypass_double_gate": True}`. The auto_rebalancer picks this up with priority (bypasses the normal double gate checks).

**Q: What happens if the standby node itself receives an interruption?**

The standby node is treated as a normal running node by the SpotPoller (it has the same IMDS polling). If interrupted, the emergency_rebalancer detects it, cordons/drains it, and launches a replacement. There is no special handling — the standby is simply unavailable for the next primary interruption, forcing a normal emergency fallback.

**Q: How does the InstabilityPropagator actually work? Redis pub/sub or polling?**

From `instability_propagator.py` (256L): It uses **Redis pipeline commands** (INCR + SADD + EXPIRE), NOT pub/sub.
1. On interruption: `INCR propagator:events:{region}:{az}:{type}` (30-min TTL window)
2. Track clusters: `SADD propagator:affected_count:{region}:{az}:{type}` → adds `cluster_id` to set (2h TTL)
3. Compute Bayesian pool pressure via `calculate_bayesian_pool_pressure()` from `risk_engine.py`
4. Store pressure: `SET propagator:pool_pressure:{region}:{az}:{type}` (2h TTL)
5. Recompute AZ average: scans all pool pressure keys for the AZ via `keys()` pattern
6. **SYSTEMIC threshold**: If `≥3 clusters` in the affected set → `recommended_action: ESCALATE_ALL`
7. Propagation is **synchronous** — it runs within the same request/task that processes the interruption event, not via pub/sub

**Q: Is the 90-second emergency drain grace period configurable?**

No. The 90-second grace period is **hardcoded** in `emergency_rebalancer.py` — not configurable via environment variable or cluster setting. The `force=True` flag (bypassing PDBs) is also hardcoded for emergency drains.

---

## 9) Rules

### 9.1 Safety Gates (All Rebalancing)

| Gate | Condition | Location |
|---|---|---|
| Execution lock | Redis NX `lock:workers.auto_rebalancer` (300s) | `auto_rebalancer.py` L1280 |
| Optimizer phase | Skip if OptimizerState in RIGHTSIZING_EVALUATION or COMBINED_EXECUTION | L2260 |
| Daily limit | `max_rebalances_per_24h` (default 5, completed only) | L2315 |
| One-at-a-time | Skip if PENDING/PICKED_UP AgentActions (auto-expire >15 min) | L2546 |
| Last-node safety | Never drain the last running node | L2610 |
| Cluster cooldown | `cooldown_override_minutes` (default 60 min) after last completed | L2265 |
| Per-instance cooldown | `spot:rebalanced:instance:{id}` (24h TTL) | L890 |
| Architecture filter | Exclude ARM64/amd64 mismatch from candidate types | L753-786 |
| Allocatable check | Reject smaller type if rightsizing OFF | L717-737 |
| Concurrency lock | `lock:rebalance_exec:{cluster_id}` (5 min) | L600 |
| Stabilization lock | `CooldownController.check_stabilization_lock()` | L2280 |
| Substitute mutex | Skip if SubstituteManager active | L2300 |
| Resize cooldown | `spot:resize_cooldown:{cluster_id}` | L2295 |

### 9.2 Blacklisting

**Source**: `backend/services/blacklist_service.py` (423 lines)

**What**: Pool marked as risky when it experiences interruption or DryRun capacity failure.

**When it happens**:
- Spot interruption detected → pool blacklisted (24h)
- DryRun failure 1-2x/24h → blacklisted 6h
- DryRun failure 3+/24h → blacklisted 12h (hard reject in ML pipeline)

**When it decays**: TTL-based decay via Redis `EXPIRE`. After TTL expires, pool is removed from `risky_pools:{region}` set automatically.

**Storage**:
- Redis SET: `risky_pools:{region}` — all blacklisted pools
- Redis KEY: `blacklist_failures:{instance_type}:{az}` — failure count
- Redis KEY: `risky_pool_meta:{instance_type}:{az}` — JSON metadata (12h TTL)

**Cascade protection**: If >70% of pools are blacklisted → suspend PREDICTIVE blacklisting for 30 min: `spot:blacklist_suspended:{region}` (30 min TTL). Deterministic blacklisting (actual interruptions) always honored.

#### Which Safety Gates Are Configurable?

| Gate | Configurable? | How |
|---|---|---|
| Execution lock (300s) | No | Hardcoded |
| Daily limit (`max_rebalances_per_24h`) | **Yes** | `stateless_runtime_rules` table |
| Cluster cooldown (`cooldown_override_minutes`) | **Yes** | `cluster_optimization_settings` table |
| Per-instance cooldown (24h) | No | Hardcoded |
| Architecture filter | No | Automatic |
| Concurrency lock (5 min) | No | Hardcoded |
| PDB respect (`respect_pdb_enabled`) | **Yes** | `stateless_runtime_rules` table |
| Resize cooldown | **Yes** | `stateless_runtime_rules.resize_cooldown_minutes` |
| Stabilization lock (5 min) | No | Hardcoded |

**Cooldown AND logic**: All applicable cooldowns must be satisfied for an action to proceed. If a cluster has both a cluster cooldown AND a per-instance cooldown active, both must expire before the action can start. There is no "OR" or priority override (except for emergency actions which force-clear locks).

#### Blacklist Deep Dive (Code-Verified from `blacklist_service.py`)

**Exponential Backoff** (`blacklist_pool()` L38-109):
- Base TTL: 24 hours (`BASE_TTL_HOURS = 24`)
- Multiplier: 2× per failure (`BACKOFF_MULTIPLIER = 2`)
- Maximum: 168 hours / 7 days (`MAX_TTL_HOURS = 168`)
- Failure counter: `blacklist_failures:{pool_key}` — kept for 30 days (`expire(30 * 86400)`)
- Progression: 24h → 48h → 96h → 168h (cap)

**Tiered Blacklist** (Decision Engine v3, `blacklist_pool_tiered()` L213-268):

| Trigger | TTL |
|---|---|
| DryRun capacity failure 1-2×/24h | 6 hours |
| DryRun capacity failure 3+/24h | 12 hours |
| ML high risk (>0.45) | 24 hours |
| Termination event (ITN/rebalance-rec) | 24 hours |
| Execution DryRun failure | No blacklist (penalty only) |

**Cascade Dampener** (`check_cascade_risk()` L270-297 + `suspend_blacklisting()` L299-319):
- Trigger: `blacklisted_count / total_pools > 0.70`
- Suspends **PREDICTIVE** blacklisting only (ML risk, DryRun, capacity check) for 30 min
- Does **NOT** suspend **DETERMINISTIC** blacklisting (ITN from IMDS, AWS rebalance recommendation)
- This separation prevents cascade dampener from blocking real termination events

**Redis Key Hygiene** (`cleanup_redis_keys()` L382-422):
- Daily scan: finds orphaned `spot:*` keys with no TTL → sets 24h TTL as safety net
- Prevents key explosion from `50 pools × regions × clusters` over time

### 9.3 Cooldown Types

| Type | Redis Key | Default TTL | Purpose |
|---|---|---|---|
| Cluster switch | `spot:cooldown:cluster:{id}` | 60 min | Prevent cluster-level flapping |
| Pool reuse | `spot:cooldown:pool:{pool_id}` | 120 min | Prevent reusing failed pool |
| Pool switch | `spot:cooldown:action:pool_switch:{id}` | 30 min | Prevent rapid pool changes |
| Resize | `spot:cooldown:action:resize:{id}` | 360 min (6h) | Prevent size oscillation |
| Substitute | `spot:cooldown:action:substitute:{id}` | 120 min | Prevent substitute churn |
| Stabilization lock | `spot:stabilization_lock:{id}` | 300s (5 min) | Post-execution stabilization |
| Per-instance rebalance | `spot:rebalanced:instance:{id}` | 24h | Prevent re-targeting same instance |
| Stateful per-cluster | `spot:stateful:resize:cluster:{id}` | 48h | Stateful rightsizing cluster cooldown |
| Stateful per-instance | `spot:stateful:resize:instance:{id}` | 48h | Stateful rightsizing instance cooldown |

---

## 10) Kubernetes Logic

### 10.1 Actions by Type

| Action | K8s API | Permission | Agent Method |
|---|---|---|---|
| **Cordon** | `PATCH /api/v1/nodes/{name}` → `spec.unschedulable=true` | `patch` nodes | `actuator.cordon_node()` |
| **Uncordon** | `PATCH /api/v1/nodes/{name}` → `spec.unschedulable=false` | `patch` nodes | `actuator.cordon_node(uncordon=True)` |
| **Drain** | For each pod: `POST /api/v1/namespaces/{ns}/pods/{name}/eviction` | `create` pods/eviction | `actuator.drain_node()` |
| **Force Delete** | `DELETE /api/v1/nodes/{name}` with grace_period=0 | `delete` nodes | `actuator.force_delete_node()` |
| **Evict Pod** | `POST /api/v1/namespaces/{ns}/pods/{name}/eviction` | `create` pods/eviction | `actuator.evict_pod()` |
| **Label Node** | `PATCH /api/v1/nodes/{name}` → `metadata.labels` | `patch` nodes | `actuator.label_node()` |
| **Annotate Node** | `PATCH /api/v1/nodes/{name}` → `metadata.annotations` | `patch` nodes | `actuator.annotate_node()` |
| **Clear VolumeAttachments** | `DELETE /apis/storage.k8s.io/v1/volumeattachments/{name}` | `delete` volumeattachments | `actuator.clear_stuck_volume_attachments()` |
| **Patch NodePool** | `PATCH /apis/karpenter.sh/v1beta1/nodepools/{name}` | `patch` nodepools | via agent (Karpenter CRD) |

### 10.2 Drain Logic Details

`actuator.drain_node()` (L282-407):
1. **Cordon** the node first (`cordon_node(node_name, uncordon=False)`)
2. **List all pods** on node: `list_pod_for_all_namespaces(field_selector='spec.nodeName={node_name}')`
3. **Skip**: DaemonSet pods (`owner_ref.kind == 'DaemonSet'`), mirror pods (`kubernetes.io/config.mirror` annotation)
4. **Skip unmanaged pods** (no controller) unless `force=True`
5. For each remaining pod:
   a. Check PDB violation → if violation AND `force=True` → **force-delete** pod with `grace_period_seconds=0` (bypasses PDB entirely)
   b. If violation AND `force=False` → skip + add to `failed_evictions` list
   c. Normal eviction: `create_namespaced_pod_eviction()` with grace period (default 30s)
6. **Eviction retry**: If K8s returns HTTP 429 (PDB Too Many Requests) → retry up to **5 times** with **10s delay** each (L145-205)
7. **VolumeAttachment cleanup** (post-drain, L372-384): `clear_stuck_volume_attachments(node_name, timeout_seconds=30)`
   - Lists all VolumeAttachments for the node via `StorageV1Api`
   - Detects "stuck" attachments: has error OR pending > timeout seconds
   - Force-deletes stuck attachments → prevents Multi-Attach errors on replacement node
   - **Safety**: This is safe and idempotent — the pod is already gone (drained) and the volume is unused. The cleanup prevents the replacement node from failing to mount the same EBS volume.

### 10.3 PDB Enforcement

`check_pdb_violation()` (L103-128):
1. List all PDBs in pod's namespace via `PolicyV1Api.list_namespaced_pod_disruption_budget()`
2. For each PDB, check if `spec.selector.match_labels` matches all pod labels
3. If matched PDB has `status.disruptions_allowed < 1` → UNSAFE (return True)
4. If all PDBs allow disruption → SAFE (return False)
5. **Fail-safe**: If any error checking PDBs → assume violation (return True)

### 10.4 Force Delete Node

`actuator.force_delete_node()` (L254-280):
- Used when underlying EC2 instance is gone (hardware failure, spot reclamation)
- **Finalizer warning**: Force-deleting a node does NOT remove finalizers on pods. Pods with finalizers (e.g., StatefulSet pods with persistent volume claims) may remain in `Terminating` state indefinitely after node deletion. The agent has **no finalizer removal logic** — this is a known K8s limitation. Manual intervention (`kubectl delete pod --force --grace-period=0`) may be needed.
- Node stuck in `NotReady`, holding StatefulSet pods in `Terminating` state
- Equivalent to `kubectl delete node <name> --grace-period=0 --force`
- If node already absent (404) → treated as success (idempotent)

### 10.5 Node Resolution

Multiple resolution strategies (fallback chain):
1. `payload.node_name` — direct from backend DB
2. `_find_node_by_instance_id(instance_id)` (L662-678) — matches `spec.providerID` containing `aws://{az}/{instance_id}`
3. `_find_node_name(instance_type, az)` (L680-697) — label-based: `node.kubernetes.io/instance-type` + `topology.kubernetes.io/zone`

---

## 11) Failure Handling

### 11.1 Failure by Phase

| Phase | Failure | Action | Recovery |
|---|---|---|---|
| **Phase 1** (spot launch) | All types exhausted | Action status → `failed`, error message set | Instance cooldown set, retry next cycle |
| **Phase 1** | Karpenter timeout | Single node → refuse drain; Multi node → proceed | Fail action / proceed with drain |
| **Phase 2** (CORDON) | K8s API error | Uncordon + terminate orphan spot + resume ASG | Cooldown cleared for retry |
| **Phase 2** (DRAIN) | PDB conflict | Skip terminate, terminate orphan spot directly via EC2 API | Cooldown cleared for retry |
| **Phase 2** (DRAIN) | Timeout | Same as PDB conflict | Cooldown cleared for retry |
| **Phase 2** (TERMINATE) | EC2 API error | Terminate orphan spot, report failure | Manual intervention flagged |
| **Orphan cleanup** | DB record not found | Direct EC2 termination via `replacement_spot_instance_id` from metadata | —  |
| **Pre-launch** | Previous orphan found | Verify AWS state → terminate if running/pending | Clean metadata of failed action |

### 11.2 Circuit Breaker

| State | Trigger | Effect |
|---|---|---|
| NORMAL → CONSERVATIVE | ≥2 rollbacks in 1h | Risk multiplier: 1.3 (decaying) |
| CONSERVATIVE → HALT | ≥3 rollbacks in 1h | ALL automation blocked |
| HALT → CONSERVATIVE | 30 min stable | Automation resumes cautiously |
| CONSERVATIVE → NORMAL | 2h stable | Full automation restored |

### 11.3 Cross-Cluster Propagation

When one cluster experiences interruption → `InstabilityPropagator` updates pool pressure for ALL clusters sharing that pool/AZ. If ≥3 clusters affected → SYSTEMIC event → Redis: `RISK:{az}:{instance_type}` = "DANGER" (30 min TTL).

### 11.4 Resize Guard

`resize_guard_worker.py` monitors cluster health for **2 hours** after any resize:
- CPU stress: `cpu_avg_10m > 85%` sustained → mark proposal FAILED
- Pod restart spike: `restart_rate > baseline × 2` → mark proposal FAILED
- Memory pressure: `> 5 events` → mark proposal FAILED

---

## Additional Questions

### Security & RBAC
- **Agent auth**: Bearer token (`API_TOKEN`) set during installation
- **Action verification**: HMAC-SHA256 with `SECRET_KEY` on every action payload
- **Backend API**: Organization-scoped RBAC via `Role` + `Permission` models
- **Cross-account**: STS AssumeRole with ExternalId for customer AWS accounts
- **API key rotation**: `POST /clusters/{id}/agent/disconnect` generates a new `secrets.token_urlsafe(32)` key → running agents receive 401 immediately. Permission required: `api_key:manage` (`role_service.py` L77, `feature_registry.py` L1004).
- **Orchestrator endpoint auth gap**: The orchestrator polling endpoints (`/agents/orchestrator/{cluster_id}/pending-commands` and `/agents/orchestrator/{cluster_id}/command-result`) do not use `validate_api_key` — they accept any request with a valid `cluster_id` path parameter. This is a potential security concern; DaemonSet endpoints (`/agents/actions/pending`, `/agents/register`, `/agents/heartbeat`) do enforce Bearer auth.

### Multi-tenancy
- Data isolated by `organization_id` → `account_id` → `cluster_id` hierarchy
- Each cluster has unique `API_KEY` for agent auth
- Redis keys include `cluster_id` for isolation
- DB queries always filter by `cluster_id`

### High Availability & Scaling
- **Backend**: Gunicorn workers (configurable)
- **Celery workers**: Separate containers for `celery-worker` (task execution) and `celery-beat` (scheduling)
- **Redis**: Single instance (no HA configured in current setup)
- **Database**: PostgreSQL with JSONB columns for flexible metadata
- **Component failure**: Celery auto-retries with `max_retries=3`, exponential backoff
- **Celery concurrency**: Configurable per-worker via `--concurrency` flag (default: number of CPUs). Tasks use `bind=True` for retry management. Emergency tasks use a dedicated `emergency` queue with separate consumers.
- **Redis HA**: Currently single-instance Redis — no Sentinel or Cluster mode configured. A Redis restart would temporarily lose cooldowns, blacklists, and pool rankings (all rebuilt automatically by periodic tasks).

### Cost Tracking & Reporting
- `SavingsCalculator` (`savings_calculator.py`): Calculates per-cluster realized savings
- `daily_cluster_stats`: Daily aggregation by cluster
- `Cluster.realized_savings_monthly`: Updated after each successful rebalance
- Formula: `realized_savings = SUM( MAX(0, od_price - spot_price) )` for each running SPOT instance
- Recalculated after each successful rebalancing action + periodically via Celery beat

### Upgrade Process
- Agent deployed as DaemonSet → `kubectl set image` or manifest reapply
- Backwards-compatible WebSocket protocol
- Version reported in heartbeat payload
- **Update endpoint**: `POST /clusters/{id}/update-agent` → idempotently re-deploys both DaemonSet + Orchestrator Deployment (L350-381)
- **Version skew**: No explicit version skew policy. Agent version is reported in the `User-Agent: SpotOptimizer-Agent/{version}` header (`config.py` L129) and in heartbeat payloads. The WebSocket protocol is designed to be backward-compatible — new action types unknown to old agents are logged as errors but don't crash the agent. New backend features may require agent updates to function.

### Compliance & Auditing (Code-Verified)

**Audit Log Model** (`audit_log.py`):

| Column | Type | Purpose |
|---|---|---|
| `id` | `String(36)` PK | UUID |
| `timestamp` | `DateTime(tz)` | Millisecond-precision audit timestamp |
| `actor_id` | `String(36)` | User ID or `system` |
| `actor_name` | `String(255)` | Human-readable actor name |
| `event` | `String(255)` | Action performed |
| `resource` | `String(255)` | Resource affected |
| `resource_type` | Enum | `CLUSTER`, `INSTANCE`, `TEMPLATE`, `POLICY`, `HIBERNATION`, `USER`, `ACCOUNT` |
| `outcome` | Enum | `SUCCESS` or `FAILURE` |
| `ip_address` | `String(45)` | IPv4 or IPv6 |
| `user_agent` | `String(512)` | Request user agent |
| `diff_before` | JSONB | State before change |
| `diff_after` | JSONB | State after change |
| `checksum` | `String(64)` | SHA-256 tamper-evidence hash of `(actor_id + event + resource + timestamp + diffs)` |

- **Immutable**: No `update()` method on the model — updates prevented at application layer (L74-75)
- **Tamper detection**: SHA-256 checksum computed on insert by `audit_service.py`. Periodic Celery task re-verifies integrity.
- **Indexes**: `timestamp DESC`, `(actor_id, timestamp)`, `(resource_type, timestamp)` for query performance
- **Retention policy**: No explicit TTL or retention policy in code — records persist indefinitely in PostgreSQL
- **Decision audit**: `ObservabilityLogger`: Decision audit trail in Redis (`obs:decisions:{id}`, last 100, 24h TTL)
- **Execution history**: `rebalancing_actions` + `agent_actions` tables with full metadata
- **Termination events**: `termination_events` table with pool, AZ, source

### Failure Notification

- **Circuit breaker audit** (`workers/app.py` L233): Scheduled Celery task `circuit_breaker.audit_log` periodically logs circuit breaker state changes
- **Logging**: All failures logged via structured `logger` (Python `logging` module) — no external notification system (Slack, PagerDuty, email) is configured in current code
- **UI visibility**: Failed actions visible in dashboard via `RebalancingAction.status='failed'` + `error_message` field
- **Decision rejection counters**: `spot:rejection_counters:{cluster_id}` (24h TTL hash) — visible via `/clusters/{id}/summary` endpoint


### Expected Value (EV) 