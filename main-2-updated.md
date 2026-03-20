# Spot Optimizer Platform — Comprehensive Technical Report

> **Source of truth**: All answers derived exclusively from `.py`, `.jsx`, `.yaml` code files.
> **Last updated**: 2026-03-13
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
| **PodMetricsCollector** | `agent/pod_metrics_collector.py` (358L) | DaemonSet | Collects per-pod CPU/memory usage for rightsizing on local node only, sends every **5 minutes** |
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

The method now accepts a `termination_mode` parameter. The old default `decrement_asg=True` behavior has been replaced with explicit mode control to prevent ASG DesiredCapacity corruption. See Section 10.3 for the full termination mode reference.

**Action Dispatch** (`actuator.execute_action_v2()` L1328-1449) — 14 action types:
`EVICT_POD`, `CORDON_NODE`, `UNCORDON_NODE`, `FORCE_DELETE_NODE`, `DRAIN_NODE`, `LABEL_NODE`, `UPDATE_DEPLOYMENT`, `PATCH_KARPENTER_NODEPOOL`, `INSTALL_KARPENTER`, `UNINSTALL_KARPENTER`, `PATCH_CONTAINER_RESOURCES`, `TERMINATE_NODE`, `ANNOTATE_NODE` (via LABEL_NODE)
- All enum values normalized to UPPERCASE at dispatch boundary (FIX-ENUM-01)
- Node resolution priority: `payload.node_name` → `_find_node_by_instance_id(instance_id)` → `_find_node_name(instance_type, az)`

**HTTP Action Polling** (fallback when WebSocket unavailable, L1477-1557):
- Polls `GET /api/v1/agents/actions/pending` every `ACTION_POLL_INTERVAL` (default 10s)
- Executes each command via `execute_action_v2()`, reports result via `POST /api/v1/agents/actions/{id}/result`

**Component Health Monitor** (`main.py` L415-481):

> 🟡 **Medium Issue #9:** Thread Restart Loop Has No Limit or Backoff. The health monitor checks all 6 threads every 30s and auto-restarts dead ones with no limit on restart count. A component that crashes repeatedly will spin in an infinite restart loop.

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

> 🔴 **Critical Issue #2:** Orchestrator Endpoints Unauthenticated. Both `/agents/orchestrator/{cluster_id}/pending-commands` and `/agents/orchestrator/{cluster_id}/command-result` lack Bearer token validation. Any request with a known `cluster_id` can read pending commands or inject fake results.

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

> 🟠 **High Issue #7:** Emergency Actions Still FIFO Within Priority Tier. Emergency actions queue up behind each other in chronological order.

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

> 🟠 **High Issue #8:** API Key Rotation Doesn't Invalidate Open WebSockets. When `POST /clusters/{id}/agent/disconnect` is called, agents get HTTP 401 on subsequent HTTP calls. But existing WebSocket connections stay open until the agent reconnects. An agent operating with a revoked key can still receive and execute action commands over the open WebSocket.

| Impact | Details |
|---|---|
| **Metrics stop** | Node/pod/event metrics stop flowing → backend marks cluster `DISCONNECTED` after heartbeat timeout |
| **Actions can't execute** | Backend queues AgentActions but they time out (auto-expire >15 min) → rebalancing actions fail with "agent unreachable" |
| **Spot polling stops** | IMDS termination detection stops → interruptions only detected via SQS/EventBridge (if configured) |
| **Rightsizing stops** | Pod metrics stop → no new rightsizing recommendations |
| **Existing instances persist** | EC2 instances are NOT terminated — they continue running as-is |
| **Optimization pauses** | control_plane_loop skips cluster (no heartbeat) |
| **Data retained** | All historical data in DB (instances, metrics, proposals) is preserved |

**API key rotation on disconnect**: When a user calls `POST /clusters/{id}/agent/disconnect` (`cluster_routes.py` L531-565), the backend generates a new `secrets.token_urlsafe(32)` API key and sets `agent_installed="N"`, `status=DISCONNECTED`. The running agent pods immediately start receiving **HTTP 401** responses and can no longer authenticate. Historical data is preserved.

**Full removal**: `DELETE /clusters/{id}/agent` (`cluster_routes.py` L568-666) additionally deletes all `pod_metrics` and `instance` records, resets status to `DISCOVERED`, and clears `last_heartbeat`. Also attempts K8s uninstall (deletes DaemonSet + Orchestrator + namespace) and AWS cleanup (deletes Karpenter IAM resources).

---

## 2) Data Sources

### 2.1 Price Data Sources

| Price Type | AWS Account | API / Source | Frequency | Storage |
|---|---|---|---|---|
| **Spot prices** | Platform (master) account | `ec2.describe_spot_price_history()` | Every 10 min | Redis: `pricing:{region}:spot:{instance_type}:{az}` |
| **On-demand prices** | Platform (master) account | AWS Pricing API `GetProducts` | Daily at 1 AM | Redis: `pricing:{region}:ondemand:{instance_type}` |
| **Spot Advisor data** | Public (no auth) | Web scraper on AWS public JSON endpoint | Daily at 2 AM | Redis: `spot:advisor:{region}` → DB: `spot_advisor_rates` table |

**Pricing worker** (`backend/workers/tasks/pricing_worker.py`):
- `refresh_regional_pricing()` runs every 10 minutes.
- Aggregates required instance types across all clusters in a region.
- Fetches spot prices via EC2 API using the **platform's master account credentials** (no STS AssumeRole needed). This ensures pricing data is available even for clusters that are not yet onboarded or have no active agents.
- Batch fetches on-demand prices daily from the AWS Pricing API (also using master account).
- Updates `pricing:last_updated:{region}` timestamp after a successful refresh.
- **Enterprise guardrail**: If a region's pricing has not been updated in the last 15 minutes, optimizations for that region are blocked.
- **Emergency refresh**: `emergency_pricing_refresh()` is triggered when stale pricing is detected; it clears the `PRICING_STALE` flag and forces an immediate spot-price fetch.

**Spot Advisor scraper** (`spot_advisor_scraper.py`):

> 🟢 **Low Issue #19:** Spot Advisor Data Cached in Redis Without a Versioning Key. Spot Advisor data is refreshed daily and stored in Redis `spot:advisor:{region}`. There's no staleness check key. If the daily scraper fails, stale Spot Advisor interrupt frequency data silently feeds the ML pipeline.

- Runs daily, fetches the public Spot Advisor JSON from `https://spot-bid-advisor.s3.amazonaws.com/spot-advisor.json`.
- Parses the data (savings rates, interruption frequencies per instance family and region) and stores it in the `spot_advisor_rates` table.
- Also caches the data in Redis for quick access by the ML feature pipeline.

#### Pricing Staleness — Decision Engine Impact (Code-Verified)

> 🟠 **High Issue #5:** Partial Pricing Refresh Updates the Staleness Timestamp. A refresh that successfully fetches 1 out of 50 instance types will mark pricing as fresh, suppressing the 15-minute staleness gate even though most pricing data is actually stale.

From `decision_engine.py` **Step 1b** (L195-230):
- The Decision Engine checks `pricing:last_updated:{region}` timestamp in Redis.
- If `staleness_minutes > 15` → **reject all decisions** for that region with reason `"pricing_stale"`.
- If **no timestamp exists** (key missing) → **fail-open** (allow decisions to proceed). This means a region that has never had pricing data collected will not be blocked, but a region whose pricing stopped updating will be blocked after 15 minutes.
- The `pricing_worker.py` clears `PRICING_STALE` flags when it successfully refreshes prices.

It is updated by `AWSPricingService.refresh_regional_pricing_batch()` after successfully fetching prices for that region. The timestamp is set regardless of how many instance types were fetched — even a partial refresh (some type failures) updates the timestamp as long as the batch call succeeds overall.

---

### 2.2 Data Fetch Frequency

| Data | Frequency | Source |
|---|---|---|
| Node/pod metrics | 30s | Agent → `/clusters/{id}/metrics` |
| Pod rightsizing metrics | 5 min | Agent → `/api/v1/pod-metrics/batch` |
| Spot prices | 10 min | `pricing_worker` → AWS EC2 API (master account) |
| On-demand prices | Daily 1 AM | `pricing_worker` → AWS Pricing API (master account) |
| Spot Advisor | Daily 2 AM | `spot_advisor_scraper` → AWS public JSON |
| EC2 instances (discovery) | 5 min | `discovery_worker` → AWS EC2 (client account) |
| EKS clusters (discovery) | 5 min | `discovery_worker` → AWS EKS (client account) |
| ML pipeline (pool ranking) | 1 hour | `atharvaai_worker` → ONNX inference |
| Family baselines | Weekly | `atharvaai_worker` |
| Agent heartbeat | 30s | Agent → `/clusters/{id}/heartbeat` |

---

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
| `pod_metrics` | `pod_metric.py` | Pod-level CPU/memory for rightsizing |
| `termination_events` | `termination_event.py` | Spot interruption history |
| `rightsizing_proposals` | `rightsizing_proposal.py` | Rightsizing recommendations |
| `spot_advisor_rates` | `spot_advisor_rates.py` | AWS Spot Advisor data per instance type |
| `family_hour_baselines` | `family_hour_baseline.py` | Weekly family-hour statistics for ML |
| `pricing` | `pricing.py` | Spot/OD price history |
| `daily_cluster_stats` | `daily_cluster_stats.py` | Daily aggregated cluster statistics |
| `optimizer_state` | `optimizer_state.py` | Per-cluster optimizer phase tracking |
| `system_config` | `system_config.py` | Platform-wide config (AWS keys, settings) |
| `api_keys` | `api_key.py` | Per-cluster API keys for agent auth |
| `audit_log` | `audit_log.py` | User action audit trail |
| `hibernation_schedules` | `hibernation_schedule.py` | Cluster hibernation schedules (many-to-many) |

---

### 2.4 AWS Permissions Required

| Permission | Account | Purpose |
|---|---|---|
| `sts:AssumeRole` | Platform → Client | Cross-account access for discovery and direct EC2 actions |
| `ec2:DescribeInstances` | Client | Discovery, state sync |
| `ec2:DescribeSpotPriceHistory` | **Platform** | Spot price collection (master account) |
| `ec2:RunInstances` | Client | Direct spot launch (non-Karpenter) |
| `ec2:TerminateInstances` | Client | Node termination (rebalancing, Karpenter path) |
| `ec2:DescribeInstanceTypes` | Client | Instance catalog |
| `ec2:CreateFleet` (DryRun) | Client | Capacity validation |
| `ec2:DescribeInstanceAttribute` | Client | Copy user-data for spot launch |
| `ec2:DescribeSubnets` | Client | AZ-aware subnet selection |
| `eks:DescribeCluster` | Client | Cluster validation |
| `autoscaling:DescribeAutoScalingGroups` | Client | ASG discovery |
| `autoscaling:SuspendProcesses/ResumeProcesses` | Client | ASG freeze during detach-not-decrement window (2-3s only) |
| `autoscaling:DetachInstances` | Client | Detach instance without decrementing DesiredCapacity (Mode 1 replacement path) |
| `autoscaling:UpdateAutoScalingGroup` | Client | Hibernation nuclear path only — never used for ASG pre-decrement in rebalancing |
| `autoscaling:TerminateInstanceInAutoScalingGroup` | Client | Mode 2 OD consolidation scaledown path only (`ShouldDecrementDesiredCapacity=True`) |
| `sqs:ReceiveMessage/DeleteMessage` | Client | Spot interruption events |
| `pricing:GetProducts` | **Platform** | On-demand pricing (master account) |
| `ce:GetCostAndUsage` | Client | Cluster cost calculation (Cost Explorer) |
| `eks:ListClusters` | Client | Multi-region EKS discovery |

---

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

> 🟡 **Medium Issue #10:** RC3 Guard Only Resets on Confirmed SPOT, Not on Clean OD Reads. The Redis counter TTL is 30 minutes — if the discovery worker runs less frequently or has partial failures, a counter stuck at 2 will expire without triggering the downgrade. A node could stay marked as SPOT in the DB long after it was actually switched to OD.

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

---

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
It is updated by `AWSPricingService.refresh_regional_pricing_batch()` after successfully fetching prices for that region. The timestamp is set regardless of how many instance types were fetched — even a partial refresh updates the timestamp as long as the batch call succeeds overall.

---

## 3) Actions

### 3.1 Auto Rebalance Only (`auto_rebalance_enabled=True`, `auto_rightsizing_enabled=False`)

**What this mode owns:**
- Which node **type and pool** each node runs on (OD → spot, spot → better spot)
- Does **not** own pod resource requests
- Does **not** change node count — every operation is a strict 1-for-1 replacement

**Trigger events:**
- **Periodic**: Every ~15 seconds
- **On toggle change**: Immediate cycle when user enables or modifies settings
- **Daily**: Full cluster-wide cycle once per day
- **Risk threshold crossing**: Ad-hoc cycle when any node's ML-predicted risk exceeds `risk_ceiling_percent`

**Node evaluation order:** All running nodes in descending hourly cost (most expensive first).

**Node eligibility:**
- `WorkloadInspector` classifies nodes as `STATELESS_ELIGIBLE` or `STATEFUL_PROTECTED`
- Stateful nodes blocked unless `auto_stateful_rightsizing_enabled=True` and approval rules allow it

---

#### Pool Selection — Where EV Lives

The rebalancer loads `global_pool_rankings:{region}` from Redis — the ML pipeline produces this list ranked by `EV = savings × (1 - risk)`. This is the correct and only place EV is used as a scoring mechanism: ranking 50+ candidate spot pools so the best rises to the top. On top of this ranked list the rebalancer applies filters:
- Architecture compatibility (node template `allowed_architectures`, default: preserve current arch)
- Cooldown status (pool, instance, cluster)
- Capacity availability (DryRun check)

---

#### Gate 1 — Should We Switch This Node's Pool?

```
PASS if ALL of:
  candidate_ev > current_ev           (better pool exists in ML rankings)
  AND savings >= min_savings_percent  (meaningful cost improvement)
  AND risk < risk_ceiling_percent     (pool is safe enough)
  AND node not on cooldown
  AND candidate passes DryRun

FAIL → no action, log reason:
  no_better_pool / below_savings_threshold /
  above_risk_ceiling / on_cooldown / capacity_unavailable
```

No Gate 2 in Mode 1. The pool switch decision is fully self-contained. If Gate 1 passes, execute the full replacement flow below.

**Handling nodes that exceed risk ceiling:**
- If risk > `risk_ceiling_percent` but no better EV candidate exists → widen search by `risk_savings_tradeoff_pct`, pick lowest risk candidate
- If still nothing → fall back to OD of original type (for originally-OD nodes). For always-spot nodes → no action.

---

#### Execution Flow (Gate 1 Passes)

**Step 1 — DryRun capacity check:**
```
ec2.create_fleet(DryRun=True, instance_type=target, az=target_az)
→ Success: proceed
→ Fail: try next candidate in ML rankings
→ All exhausted (max_instance_type_attempts=6): mark failed, set pool cooldown, exit
```

**Step 2 — Launch replacement node:**

*With Karpenter:*
```
Create PATCH_KARPENTER_NODEPOOL AgentAction
→ Agent patches NodePool spec.requirements:
    instance_types: [target_type]
    capacity-type: spot
    architecture: [current_arch] (or both if template allows mixing)
→ Karpenter provisions new spot node
→ Wait for node Ready (300s timeout)
→ Timeout → terminate orphan, rollback, set cooldown
```

*Without Karpenter (direct EC2):*
```
ec2.run_instances(
    InstanceType=target_type,
    MarketOptions={MarketType: spot},
    ImageId=copied from source (or SSM if arch mixing),
    SubnetId=target AZ subnet,
    SecurityGroups=copied from source,
    UserData=copied from source,
    IamInstanceProfile=copied from source,
    Tags=[{spot-optimizer/launched-by: platform}]
)
→ Wait for node to join K8s as Ready (300s timeout)
→ Timeout → terminate orphan, rollback, set cooldown
```

**Step 3 — Cordon + Drain old node:**
```
CORDON: PATCH /api/v1/nodes/{old_node} → spec.unschedulable=true

DRAIN:  For each pod on old node:
          Skip: DaemonSet pods
            (they tolerate unschedulable, re-schedule immediately,
             are infrastructure not workload, self-manage on node death)
          Skip: Mirror pods (static pods, node-bound)
          If PDB violation AND force=False → add to failed_evictions
          If PDB violation AND force=True  → force-delete (grace_period=0)
          Normal: eviction with 60s grace
          If 429 (PDB Too Many Requests) → retry 5× with 10s delay

        Post-drain: clear_stuck_volume_attachments()
```

If drain fails → rollback:
```
Uncordon old node
Terminate orphan spot node
Set pool cooldown
Exit
```

**Step 4 — Verify workload health:**
```
All previously running pods Ready on new node
No spike in pod restart count
No CrashLoopBackOff
→ Fail: rollback (uncordon old, terminate new, set cooldown)
```

**Step 5 — Terminate old node:**

*With Karpenter:*
```
ec2.terminate_instances(old_instance_id)
termination_mode="replacement" (Karpenter path)
No ASG interaction at all.
Karpenter manages node inventory separately from ASG DesiredCapacity. ✅
```

*Without Karpenter (ASG path — tight 2-3 second window only):*
```
termination_mode="replacement"

with redis.lock('asg:suspend_lock:{asg_name}', timeout=30):
    autoscaling.suspend_processes(['Launch'])
    autoscaling.detach_instances(
        old_instance_id,
        ShouldDecrementDesiredCapacity=False  ← never True in Mode 1
    )
    ec2.terminate_instances(old_instance_id)
    autoscaling.resume_processes(['Launch'])

ASG DesiredCapacity unchanged before, during, after ✅
ASG sees desired=N, actual=N (replacement already running) → launches nothing ✅
```

The `suspend_processes` window covers **only** the detach+terminate call (~2-3 seconds), NOT the cordon+drain which takes 60-90 seconds. Traffic spikes during drain can still trigger CA scale-ups — they are only blocked for seconds.

**Step 6 — Post-action cleanup:**
```
Mark RebalancingAction COMPLETED
Set per-instance cooldown: spot:rebalanced:instance:{id} (24h TTL)
Set cluster cooldown: spot:cooldown:cluster:{id} (60min TTL)
Recalculate realized savings: calculate_real_savings.delay()
```

---

#### DaemonSet Pods — Why Skipped During Drain

DaemonSet pods are skipped during drain for three reasons:
1. They tolerate `node.kubernetes.io/unschedulable` — evicting them causes immediate rescheduling onto the same cordoned node, creating an infinite eviction loop
2. They are infrastructure (kube-proxy, aws-node, spot-agent, fluentd), not workload — evicting them breaks node networking and monitoring
3. They self-manage — when the node terminates, the DaemonSet controller stops scheduling there. When the new node joins, it automatically schedules a fresh pod. No intervention needed.

---

#### Last-Node Safety

The safety gate `Never drain the last running node` checks `running_node_count == 1` — it counts **all running nodes regardless of lifecycle type** (OD or spot, platform-labeled or not). The last OD node in a cluster that also has spot nodes is **not** the last running node. It is converted normally with no special handling required.

In the normal replacement flow this gate effectively never fires because the replacement node is always launched (Step 2) before the drain (Step 3) — by the time drain executes, `running_node_count` is already `n + 1`.

**When does it actually fire?** Only in a catastrophic simultaneous multi-node failure. The three realistic scenarios:

```
Scenario A — Single-node cluster:
  Cluster has 1 node total (OD)
  Optimizer launches replacement spot node → now 2 nodes
  Drain old node → running_node_count = 2 → gate does NOT fire
  Terminate old node → back to 1 node (spot)
  Gate never fires even here — by drain time there are already 2 nodes.

Scenario B — Replacement failed to join:
  Cluster has 3 nodes
  Optimizer launches replacement → spot node launch fails or times out
  Rollback triggered → orphan spot terminated
  Cluster still has 3 nodes, no drain attempted
  Gate irrelevant.

Scenario C — Race condition (the only scenario where the gate fires):
  Cluster has 3 nodes
  Two nodes receive spot interruptions simultaneously
  Emergency rebalancer fires for both
  Both nodes terminate before replacements arrive
  Cluster temporarily has 1 node
  Rebalancer tries to replace that last node
  → running_node_count = 1 → gate fires → drain blocked ✅

This is what the gate protects against: a catastrophic simultaneous
multi-node failure where replacements have not arrived yet — not
anything to do with OD vs spot.
```

---

#### Traffic Scaling Behavior

```
Traffic spike → CA/Karpenter adds new node:
  With Karpenter: new node is spot (NodePool has capacity-type=spot) → already
                  on ML-ranked pool → rebalancer finds nothing to do ✅
  With CA+ASG:    new node is OD (ASG launch template) → rebalancer detects
                  in next cycle (~15s) → converts to spot via replacement flow
                  OD lag window: ~3-5 minutes per scale-up event (acceptable)

Traffic drop → Karpenter consolidation removes underutilized nodes
             → CA decrements DesiredCapacity for ASG-managed nodes
             → Rebalancer not involved in scale-down at all
```

The rebalancer and autoscaler run on completely independent loops and independent concerns. They never collide because the autoscaler changes **count** (DesiredCapacity or Karpenter provisioning) and the rebalancer changes **type** (pool swap, count unchanged). These two operations never touch the same variable.

---

#### Realized Savings Calculation (Code-Verified)

From `savings_calculator.py` (L109-146):
```
realized_savings = SUM( MAX(0, od_price - spot_price) )  for each running SPOT instance
                   where spot-optimizer/launched-by=platform
```
- `od_price` = on-demand price for the instance type from Redis `pricing:{region}:ondemand:{type}`
- `spot_price` = live spot price from Redis `pricing:{region}:spot:{type}:{az}`
- Only running SPOT instances tagged with `spot-optimizer/launched-by=platform` are summed — pre-existing spot instances without this label are excluded
- Result stored as `Cluster.realized_savings_monthly` in DB
- Recalculated after every successful rebalance (`calculate_real_savings.delay()`) and periodically by Celery beat

---

#### Action Expiry (Code-Verified)

From `auto_rebalancer.py` L2367-2382:
- `AgentAction` records in `PENDING` or `PICKED_UP` status for **>15 minutes** are auto-expired
- This prevents orphaned actions (from agent restarts or crashes) from blocking the rebalancer indefinitely
- The auto-expiry runs at the start of each rebalancer cycle (every ~15s)

---

#### Settings

| Setting | Table | Default | Description |
|---|---|---|---|
| `auto_rebalance_enabled` | `cluster_optimization_settings` | `False` | Master toggle |
| `manual_approval_required` | `cluster_optimization_settings` | `False` | Require user approval per action |
| `cooldown_override_minutes` | `cluster_optimization_settings` | `60` | Cluster-level cooldown after any rebalance |
| `diversify_pools` | `cluster_optimization_settings` | `False` | Spread nodes across multiple pools |
| `max_family_diversification_cap_pct` | `cluster_optimization_settings` | `40` | Max % of nodes in one instance family |
| `maintain_standby` | `cluster_optimization_settings` | `False` | Keep a standby node for emergencies |
| `target_spot_exposure_pct` | `cluster_optimization_settings` | `100` | Desired % of nodes as spot |
| `risk_ceiling_percent` | `optimization_strategy` | `25` | Maximum acceptable risk for any node |
| `min_savings_percent` | `optimization_strategy` | `15` | Minimum savings to consider a switch |
| `risk_savings_tradeoff_pct` | `optimization_strategy` | `20` | How much more expensive a node can be when searching for lower risk |
| `max_rebalances_per_24h` | `stateless_runtime_rules` | `5` | Daily limit on rebalance actions |
| `respect_pdb_enabled` | `stateless_runtime_rules` | `True` | Obey PodDisruptionBudgets during drains |
| `max_instance_type_attempts` | `cluster_optimization_settings` | `6` | Instance types to try in cascade |
| *(Node template)* | `node_templates` | — | Allowed architectures, AMI overrides, and other node-level settings |

**Architecture mixing behavior:**
- **Default**: No mixing — rebalancer only considers candidates matching the current node's architecture.
- **If a node template is attached and its `allowed_architectures` list contains more than one value** (e.g., `["amd64", "arm64"]`), mixing is permitted. The system then uses SSM to fetch the appropriate AMI for the chosen architecture when launching a direct EC2 replacement; with Karpenter, AMI resolution is delegated to the EC2NodeClass.

**With/without Karpenter:**
- **With Karpenter**: Creates `PATCH_KARPENTER_NODEPOOL` AgentAction → agent patches NodePool CRD → Karpenter provisions spot node.
- **Without Karpenter**: `_launch_spot_instance_direct()` → boto3 `run_instances()` with spot market options, copies AMI/subnet/SGs/user-data from source instance, or uses SSM-fetched AMI if architecture mixing is enabled via node template.

---

### 3.2 Auto Rightsizing Only (`auto_rightsizing_enabled=True`, `auto_rebalance_enabled=False`)

**What this mode owns:**
- How much CPU/memory each pod **requests**
- Nothing else — no node type decisions, no node count decisions, no pool selection

**What Karpenter owns after we act:**
- Whether to consolidate nodes (Karpenter consolidation, `WhenUnderutilized`)
- Which node type to provision for new demand
- When to terminate empty nodes
- All of this is standard Karpenter operation — no changes to its behavior

**Karpenter is required.** If not installed, mode is fully disabled — no recommendations, no actions.

---

#### `rightsizing_target` — What It Controls

This setting controls **which pods are analyzed**, nothing else:

| `rightsizing_target` | Pods analyzed | Node decisions |
|---|---|---|
| `"spot"` | Only pods on spot nodes | Karpenter decides (normal operation) |
| `"on_demand"` | Only pods on OD nodes | Karpenter decides (normal operation) |

In both cases, after we patch pod resource requests, Karpenter handles node provisioning and consolidation exactly as it always does. We do not select replacement node types, we do not compare costs of node types, we do not look at pool rankings. That is Karpenter's job.

---

#### Step 1 — Data Collection (Continuous)

`PodMetricsCollector` on every DaemonSet agent sends per-pod CPU and memory usage every 5 minutes → stored in `pod_metrics` table. Runs always regardless of whether rightsizing is enabled.

---

#### Step 2 — Analysis Trigger

- Periodically per `rightsizing_frequency_days` (default: daily at 2 AM)
- On-demand when user requests manual refresh

---

#### Step 3 — Recommendation Generation

For each controller (Deployment, StatefulSet, DaemonSet):
```
1. Query pod_metrics for last rightsizing_history_window_days (default 7)
   filtered to pods on nodes matching rightsizing_target type

2. Calculate P50, P95, P99 for CPU and memory

3. Recommended request = P95 × resize_headroom_multiplier (default 1.2)

4. Classify:
   OVERSIZED:   current_request >= recommended × 1.5
   UNDERSIZED:  P95_usage >= current_request × 0.95
   RIGHT_SIZED: otherwise

5. Store in rightsizing_proposals table
```

---

#### Step 4 — Two Gates

**Gate 1 — Is the controller actually mis-sized?**
```
PASS if: classification is OVERSIZED or UNDERSIZED
FAIL if: RIGHT_SIZED → no action, log reason: "right_sized"
```

**Gate 2 — Is the resize worth doing?**
```
PASS if:
  delta between current_request and recommended_request > 20%
  AND controller is not on resize_cooldown
    (spot:resize_cooldown:{controller_id} key absent)

FAIL if:
  delta <= 20% → log reason: "delta_too_small"
  OR on resize_cooldown → log reason: "resize_cooldown_active"
```

Both gates must pass → execute `PATCH_CONTAINER_RESOURCES`. Then Karpenter handles everything else as normal — consolidation, provisioning, termination — for both `rightsizing_target="spot"` and `rightsizing_target="on_demand"`. We do not touch nodes, pools, or ASG in this mode at all.

**Gate 2 does not look at node types, pool rankings, or costs.** That is Karpenter's job. Gate 2 only asks whether the resize delta is large enough to justify the pod disruption a rolling update causes. Node economics are entirely outside this gate's scope.

---

#### Step 5 — Execution

**Stateless controllers (Deployments, DaemonSets):**
```
PATCH_CONTAINER_RESOURCES AgentAction:
{
  namespace, controller_type, controller_name, container_name,
  resources: {
    requests: { cpu: "1200m", memory: "512Mi" },
    limits:   { cpu: "2400m", memory: "1024Mi" }
  }
}

→ K8s strategic merge patch on spec.template.spec.containers
→ Deployment rolling update starts
→ Old pods terminate one by one
→ New pods start with updated resource requests
```

**Stateful controllers (StatefulSets):**
```
Recommendation stored in rightsizing_proposals
Displayed in UI only
No automatic execution — manual approval required always
```

---

#### Step 6 — What Karpenter Does (Standard Operation, No Changes From Us)

**Oversized case (requests reduced):**
```
Pods restart with lower requests
→ Nodes become underutilized
→ Karpenter consolidation (WhenUnderutilized) fires after consolidateAfter (30s)
→ Karpenter evicts pods off underutilized nodes onto others
→ Empty nodes terminated by Karpenter via ec2.terminate_instances()
→ Cluster shrinks
→ termination_mode="karpenter" — we do not call any termination API ourselves

We never said "remove this node" — Karpenter drew that conclusion itself ✅
```

**Undersized case (requests increased):**
```
Pods restart with higher requests
→ Some pods become Pending (insufficient resources on current node)
→ Karpenter sees Pending pods
→ Karpenter provisions new node from its NodePool
→ Pods schedule on new node
→ Cluster grows

We never said "add a node" — Karpenter drew that conclusion itself ✅
```

This is identical Karpenter behavior for both `rightsizing_target="spot"` and `rightsizing_target="on_demand"`. Karpenter does not distinguish — it just sees pod scheduling state and node utilization.

---

#### Step 7 — ASG Behavior

We do not touch nodes, pools, or ASG directly in Mode 2. Everything below is Karpenter's standard behavior after we patch pod requests — we make no further API calls.

```
rightsizing_target="spot":
  Spot nodes are Karpenter-managed
  After pod requests shrink → Karpenter consolidation fires
    (WhenUnderutilized, consolidateAfter: 30s)
  Karpenter evicts pods off underutilized nodes onto others
  Empty nodes terminated by Karpenter via ec2.terminate_instances()
  termination_mode="karpenter" — we do not call any termination API ourselves ✅
  ASG DesiredCapacity never touched ✅

rightsizing_target="on_demand":
  OD nodes are in ASG
  After pod requests shrink → Karpenter consolidation fires same as above
  Karpenter evicts pods → node empties
  Platform detects empty OD node:
    termination_mode="scaledown"
    ShouldDecrementDesiredCapacity=True ← correct and intentional here only
    ASG DesiredCapacity decrements ✅
  Scale-up: CA sees Pending pods → increments DesiredCapacity
            → ASG launches new OD node
```

`ShouldDecrementDesiredCapacity=True` is used **only here** in the entire system — when rightsizing has caused genuine workload reduction and the cluster legitimately needs fewer nodes. In all other modes this flag is always False or the ASG API is not called at all.

---

#### Step 8 — Resize Guard (2 Hours Post-Execution)

```
CPU stress:      cpu_avg_10m > 85% sustained 10min → FAILED → revert
Pod restarts:    restart_rate > baseline × 2        → FAILED → revert
Memory pressure: >5 pressure events in 2h window   → FAILED → revert

Revert = re-patch requests back to original values (stateless only)
Stateful failures → alert only, manual rollback required
```

In synergy mode (Mode 3), the resize guard also monitors node pool risk signals for 2 hours post-execution, in addition to pod-level metrics. Architecture changes that cause temporary pod restarts are captured because the baseline is calculated per controller.

---

#### What We Are NOT Doing in Mode 2

| What | Why not |
|---|---|
| Selecting replacement node types | Karpenter's job |
| Comparing node costs | Karpenter's job |
| Looking at pool rankings | Mode 1 only |
| Telling Karpenter to consolidate | Karpenter does this automatically |
| Directly terminating nodes ourselves | Karpenter terminates empty nodes |
| Running without Karpenter | Hard requirement, mode disabled if absent |

---

#### Settings

| Setting | Default | Description |
|---|---|---|
| `auto_rightsizing_enabled` | `False` | Master toggle (requires Karpenter) |
| `rightsizing_target` | `"spot"` | Which pods to analyze: `"spot"` or `"on_demand"` |
| `rightsizing_history_window_days` | `7` | Days of pod metrics to analyze |
| `rightsizing_frequency_days` | `1` | How often to evaluate and auto-execute |
| `resize_cooldown_minutes` | `120` | Cooldown between resizes on same controller |
| `resize_headroom_multiplier` | `1.2` | Safety buffer on top of P95 |

---

### 3.3 Both ON — Synergy Mode (`auto_rebalance_enabled=True`, `auto_rightsizing_enabled=True`)

**What this mode owns:**
- Both pod resource sizing AND node type/pool, evaluated independently via two gates and executed together when both pass
- `rightsizing_target` locked to `"spot"` — only spot nodes considered for rightsizing since rebalancing is simultaneously converting all OD nodes to spot
- Node count may reduce if rightsizing causes consolidation
- Node count stays the same if only a pool switch happens

**Karpenter is required** (inherited from Mode 2 requirement).

---

#### Why EV Cross-Mode Scoring Was Removed

The previous approach scored Option A vs B vs C with a combined EV formula. This was removed for three reasons:
1. Bin-packing savings and pool-switch savings are not the same unit and cannot be meaningfully added
2. `EV(combined) >= EV(pool_only)` almost always by construction — the combined option wins by default, giving no real signal
3. Operational risk from pod consolidation (disruption, restart, bin-packing failure) was never captured in the pool risk score, making the combined option systematically overconfident

Replaced with **two independent binary gates**.

---

#### Two Independent Gates

Each gate has its own acceptance criteria and its own rejection reason logged separately. They do not interact with each other's scoring.

**Gate 1 — Rebalancing gate (should we switch this node's pool?):**
```
PASS if ALL of:
  candidate_ev > current_ev           (better pool in ML rankings — EV used here only)
  AND savings >= min_savings_percent
  AND risk < risk_ceiling_percent
  AND node not on cooldown
  AND candidate passes DryRun

FAIL → log reason: no_better_pool / below_savings_threshold /
       above_risk_ceiling / on_cooldown / capacity_unavailable
```

**Gate 2 — Rightsizing gate (should we resize this node's pods?):**
```
PASS if ALL of:
  classification is OVERSIZED or UNDERSIZED
  AND delta between current_request and recommended_request > 20%
  AND controller not on resize_cooldown

FAIL → log reason: right_sized / delta_too_small / resize_cooldown_active
```

Gate 2 does **not** look at node types, pool rankings, or costs — that is Gate 1's domain. Gate 2 only asks whether the resize delta is large enough to justify pod disruption.

---

#### Execution Based on Gate Outcomes

| Gate 1 | Gate 2 | Action | Node count | Termination method |
|---|---|---|---|---|
| PASS | PASS | Combined — resize pods AND switch pool in single operation | Same or reduces | Detach pattern (same count) or Karpenter consolidation (reduces) |
| PASS | FAIL | Switch pool only, keep current pod sizes | Same | Detach + direct terminate |
| FAIL | PASS | Resize pods only, Karpenter provisions naturally | May reduce or increase | Karpenter handles entirely |
| FAIL | FAIL | No action | Same | None |

Gate rejections (both gates fail, no action taken) do **not** increment the rollback counter or circuit breaker. Only executed actions that fail and roll back count.

---

#### Combined Execution Flow (Both Gates Pass)

```
Step 1 — Compute new resource requirements:
  required_vcpu = current_vcpu × (cpu_util / 100) × resize_headroom_multiplier
  required_mem  = current_mem  × (mem_util / 100) × resize_headroom_multiplier

Step 2 — Find best fitting pool from ML rankings:
  Load global_pool_rankings:{region}
  Filter to:
    instance_vcpu >= required_vcpu
    AND instance_mem >= required_mem
    AND cost < current_node_cost
    AND risk < risk_ceiling_percent
    AND capacity-type = spot
  Pick: cheapest from filtered ranked list

  If no pool found → downgrade to Gate 2 result only
    (resize pods only, let Karpenter provision naturally without NodePool patch)
    Do NOT fall back to Gate 1 result (pool switch) — if Gate 2 passed and
    combined pool search failed, the right outcome is the resize alone,
    not a pool switch that ignores the new pod sizes.

Step 3 — Execute as single combined operation (not two sequential steps):
  PATCH_CONTAINER_RESOURCES → update pod template with new requests
  PATCH_KARPENTER_NODEPOOL  → point NodePool at new instance type
  Karpenter provisions new node matching both new pod size and new pool
  Cordon + Drain old node (same drain logic as Mode 1, 60s grace, PDB respected)
  Terminate old node:
    Same node count → termination_mode="replacement", detach pattern
                      ShouldDecrementDesiredCapacity=False always
    Consolidation   → termination_mode="karpenter",
                      Karpenter terminates empty nodes directly
```

Executed as a single combined action to avoid an intermediate state where pods are resized but still on the old pool.

---

#### ASG Behavior in Synergy Mode

`rightsizing_target` is locked to `"spot"` — all spot nodes are Karpenter-managed. Therefore `ShouldDecrementDesiredCapacity=True` is **never used in synergy mode**.

```
Both gates pass, same node count:
  termination_mode="replacement"
  Detach + direct terminate (2-3s suspend window)
  ASG DesiredCapacity: unchanged ✅

Both gates pass, consolidation:
  termination_mode="karpenter"
  Karpenter terminates empty nodes
  ASG DesiredCapacity: not touched ✅

Gate 1 only (pool switch):
  termination_mode="replacement"
  Detach + direct terminate
  ASG DesiredCapacity: unchanged ✅

Gate 2 only (resize):
  termination_mode="karpenter"
  Karpenter handles entirely
  ASG DesiredCapacity: not touched ✅
```

---

#### Conflict Prevention

- `key_rebalance_lock` per cluster prevents concurrent operations on the same node
- Rightsizing proposals targeting a node in active rebalancing are deferred until the action completes or auto-expires (>15 min)
- Emergency actions (priority=10) force-clear locks and take precedence over all synergy operations
- `SuspendProcesses` window tight (~2-3 seconds) around detach+terminate only — not across full drain

---

#### Settings in Synergy Mode

| Setting | Synergy behavior |
|---|---|
| `rightsizing_target` | Ignored — locked to `"spot"` |
| Pool source | Always `global_pool_rankings:{region}` (ML-ranked) |
| `resize_cooldown_minutes` | Applied per controller (Gate 2) |
| `resize_headroom_multiplier` | Applied in resource requirement calculation (Step 1) |
| `risk_ceiling_percent` | Applied in Gate 1 AND as filter in combined pool search (Step 2) |
| `min_savings_percent` | Applied in Gate 1 only |
| `auto_stateful_rightsizing_enabled` | Informational only — stateful nodes always manual approval |
| ASG termination | Always detach pattern or Karpenter — `ShouldDecrementDesiredCapacity=True` never used |

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
4. `ml_score = savings × (1 - risk)` — EV used here for pool ranking only
5. Store top 100 pools per region in Redis: `global_pool_rankings:{region}` (65-min TTL)

**Input data from**: Redis (spot prices, on-demand prices, family baselines, spot advisor data)
**Output data to**: Redis: `global_pool_rankings:{region}` → consumed by Decision Engine, Auto-Rebalancer (Mode 1 Gate 1 and Mode 3 Gate 1 and combined pool search)

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

Retraining is **NOT automated** in the current pipeline. The training script is run manually by the data science team when sufficient new data accumulates. The model version is tracked via `risk_threshold.json` (`model_version: 6`) and validated at Decision Engine Step 3 (`CURRENT_MODEL_VERSION = "6"`). There is no A/B testing or canary deployment mechanism — a new model replaces the old `.onnx` files directly.

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
| 9 | Re-score all pools with `evaluate_candidate_ev()` — EV used here for pool comparison | `ev_model.py` |
| 10 | Score current pool (simple EV: savings × (1-risk)) — EV used here for baseline | `ev_model.py` |
| 11 | Template + Karpenter filters | DB: template mappings |
| 12 | Diversity check + deadlock protection | `DiversityEnforcer` |
| 13 | Delta threshold check (best_ev - current_ev ≥ profile.delta_threshold) — EV used here for gate | Config |
| 14 | APPROVED — select best candidate | — |

### 5.4 Validation

> 🟠 **High Issue #4:** Decision Audit Expires in 24h. `ObservabilityLogger` stores only the last 100 decisions per cluster in Redis with a 24h TTL. For post-incident debugging or compliance audits, any decision trail older than 24h is lost.

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

The `delta_threshold` is the **minimum required improvement in EV** between the best candidate pool and the current pool. At Step 13: `if (best_candidate_ev - current_pool_ev) < profile.delta_threshold → REJECT`.

**Q: What happens if global pool rankings cache is empty?**

> 🟠 **High Issue #6:** No Pool Rankings Cache → System Waits Up to 1 Hour. If `global_pool_rankings:{region}` is missing from Redis, every decision for that region is rejected. There is no synchronous fallback rebuild.

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
| 6 | Terminate original node | `ec2:TerminateInstances` (mode-dependent) | Failure → rollback |

### 6.2 Agent Interaction

Backend creates `AgentAction` records in DB → agent polls via HTTP or receives via WebSocket.

Action types (`agent_action.py`): `CORDON_NODE`, `UNCORDON_NODE`, `DRAIN_NODE`, `TERMINATE_NODE`, `PATCH_KARPENTER_NODEPOOL`, `LABEL_NODE`, `ANNOTATE_NODE`, `EVICT_POD`, `FORCE_DELETE_NODE`, `INSTALL_KARPENTER`, `UNINSTALL_KARPENTER`, `PATCH_CONTAINER_RESOURCES`, `UPDATE_DEPLOYMENT`

### 6.3 Rightsizing Execution (Container Patching)

`actuator._patch_container_resources()` (L957-1100):
- Patches CPU/memory requests+limits for a specific container in a Deployment/StatefulSet/DaemonSet
- Uses K8s strategic merge patch on `spec.template.spec.containers`
- Payload: `{namespace, controller_type, controller_name, container_name, resources: {requests: {cpu, memory}, limits: {cpu, memory}}}`
- After patch: Karpenter observes changed pod demands and naturally provisions or consolidates nodes — no further instruction from the platform needed

### 6.4 Permissions

- **Client account**: `ec2:RunInstances`, `ec2:TerminateInstances`, `ec2:CreateFleet` (DryRun), `autoscaling:SuspendProcesses/ResumeProcesses`, `autoscaling:DetachInstances`, `autoscaling:TerminateInstanceInAutoScalingGroup`
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
| `rightsizing_evaluation_worker` | Every 24h | Pod-level rightsizing — only proposes, does not execute |
| `evaluate_proposal_task` | Event-driven | Runs Gate 1 (rebalancing) and Gate 2 (rightsizing) independently; executes based on which gates pass |
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

> 🟢 **Low Issue #18:** Instance Type Cascade Limited to Top 6. `_launch_spot_instance_direct()` slices the ML-ranked list to `[:6]`. In constrained regions or during AZ-level capacity crunches, 6 types may all fail. The limit is hardcoded with no per-cluster override.

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

Karpenter is a Kubernetes node autoscaler that provisions the right nodes for your workloads. The platform integrates with Karpenter to manage node pools (instance types, lifecycle, architecture) based on ML-driven recommendations and user-defined node templates.

- **`karpenter_mode = None`**: Not installed → platform uses direct EC2 `RunInstances()` for spot launches.
- **`karpenter_mode = "dry_run"`**: Insights only — recommendations shown but no EC2 changes.
- **`karpenter_mode = "auto"`**: Full autonomous management — platform patches NodePool CRDs.

**Node templates** play a key role: they define allowed architectures, AMI overrides, and other node-level settings. When a node template is attached to a cluster or node, its rules (including architecture mixing) override defaults.

---

### 7.2 Installation & Uninstallation

**Install** (`actuator.install_karpenter()` L782-868):
1. SQS queue: `KarpenterInterruptionQueue-{cluster_name}` (Bug A-2 fix: never fallback to bare cluster name).
2. `helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter --version 1.0.8 --wait --timeout 5m`.
3. IRSA: annotates ServiceAccount with `eks.amazonaws.com/role-arn`.
4. Registers `KarpenterNodeRole` access entry for EKS cluster.
5. Creates default `EC2NodeClass` (AL2023, `amiSelectorTerms: [{alias: al2023@latest}]` — dual-arch auto-resolution).
6. Creates default `NodePool` with `karpenter.sh/v1` API, allowing both `amd64` + `arm64`. Sets `consolidationPolicy: WhenUnderutilized`, `consolidateAfter: 30s`.

**Uninstall** (`actuator.uninstall_karpenter()` L1289-1326):
1. `helm uninstall karpenter --namespace karpenter --wait --timeout 3m`.
2. Delete `karpenter` namespace (best-effort).
3. Idempotent: release-not-found treated as success.

**NodePool Patching** (`actuator.patch_karpenter_nodepool()` L699-780):

> 🔴 **Critical Issue #1:** Karpenter NodePool Patches Wrong JSON Path. The document says the agent patches `spec.template.spec.requirements` but immediately acknowledges this is wrong — the correct path is `spec.requirements` for Karpenter v1/v1beta1. The comment "NOT `spec.requirements` — wrong path is silently ignored" confirms this bug exists in live code and means all NodePool patches have zero effect. Karpenter never changes which instance types it provisions.

- Patches `spec.template.spec.requirements` (NOT `spec.requirements` — wrong path is silently ignored).
- Requirements: `karpenter.sh/capacity-type`, `node.kubernetes.io/instance-type`, optional `topology.kubernetes.io/zone` + `kubernetes.io/arch`.
- 404 fallback: auto-creates NodePool by inferring cluster name from ConfigMap or node labels.
- CRD missing: returns error "Karpenter CRDs not found — install Karpenter first".

Agent heartbeat includes Karpenter detection → sets Redis key: `spot:karpenter:installed:{cluster_id}`.

---

### 7.3 Karpenter Mode Behavior

#### 7.3.1 With Karpenter Installed (`auto` mode)

> 🟡 **Medium Issue #11:** Karpenter NodePool Auto-Creation Infers Cluster Name Unreliably. If patch fails with 404, agent infers cluster name unreliably without falling back to `CLUSTER_NAME` env var, surfacing no clear error.

When the platform decides to rebalance a node (OD→spot or spot→spot) and Karpenter is installed and in `auto` mode, it follows this process:

1. **Backend** creates a `PATCH_KARPENTER_NODEPOOL` AgentAction. The payload includes:
   - `instance_types`: list of target instance types from ML pool rankings (ordered by EV).
   - `lifecycle`: `"spot"`.
   - `architecture`: if the node's attached node template allows multiple architectures, the list may include both; otherwise restricted to the current node's architecture.
   - `zone`: optional target AZ.

2. **Agent** patches the appropriate NodePool (or creates it if missing) with the new requirements. Karpenter then provisions a new spot node that matches the updated spec.

3. **AMI selection** when architecture mixing is allowed:
   - The NodePool's `EC2NodeClass` is expected to have an AMI selector that picks the right AMI for the target architecture. The default installation uses `alias: al2023@latest`, which automatically resolves to the correct AL2023 EKS-optimized AMI for the instance's architecture.
   - If a custom AMI is required, the node template can specify `amiSelectorTerms`; the platform does **not** modify the `EC2NodeClass` directly — it relies on Karpenter's native AMI resolution.

4. **Traffic scaling**: New nodes provisioned by Karpenter use the ML-ranked NodePool. When traffic spikes and Karpenter provisions a new node, it already uses the optimal spot pool. The rebalancer finds nothing to do for Karpenter-provisioned nodes in most cycles.

5. **Fallback** if patching fails (404, 403, CRD missing, timeout) → platform falls back to direct EC2 launch (`_launch_spot_instance_direct()`), using the same architecture-mixing rules and dynamic AMI lookup via SSM if needed.

#### 7.3.2 Architecture Handling & Node Templates

- **Default behavior** (no node template, or template without explicit `allowed_architectures`): the platform **prevents mixing** — only candidates matching the current node's CPU architecture are considered.
- **If a node template is attached** and its `allowed_architectures` list contains multiple values (e.g., `["amd64", "arm64"]`), the platform **permits mixing**. The NodePool's `requirements` will include both architectures, and Karpenter can provision either.
- For **direct EC2 launches** (when Karpenter is absent or patching fails), the platform uses SSM to fetch the correct AMI for the target architecture if mixing is allowed; otherwise it copies the source AMI.

#### 7.3.3 Without Karpenter

If Karpenter is not installed, the platform uses its own direct EC2 launch logic:
- Copies AMI, subnet, security groups, IAM profile, user-data from the source instance.
- Applies architecture filter based on the node template (if any). If mixing is allowed, it uses SSM to fetch the appropriate AMI for the chosen architecture.
- Launches a spot instance via `ec2.run_instances()` with `InstanceMarketOptions: {MarketType: spot}`.
- Waits for the instance to join the cluster as a Kubernetes node.
- Uses `termination_mode="replacement"` with detach-not-decrement pattern for all terminations.

---

### 7.4 Karpenter Fallback & SQS

**SQS Consumer** (`sqs_consumer.py` L29-284): Polls SQS interruption queues every 30s for Karpenter clusters.
- Supported events: `EC2 Spot Instance Interruption Warning`, `EC2 Instance State-change Notification` (stopping/stopped), `AWS Health Event` (spotInterruption/scheduledChange).
- On detection: calls `trigger_emergency_rebalancing()` → dispatches `emergency_rebalancer` Celery task.

**Fallback API** (`cluster_routes.py`, `/fallback`): Agent calls on interruption → backend switches NodePool to on-demand: Redis key `spot:ondemand_fallback:{id}` (12h TTL).

**Karpenter → Direct EC2 fallback**: If `PATCH_KARPENTER_NODEPOOL` fails, the platform falls back to direct EC2 launch as described above.

---

### 7.5 Karpenter-Specific Redis Keys

| Key | TTL | Purpose |
|---|---|---|
| `spot:karpenter:installed:{id}` | Variable | Detection flag |
| `spot:karpenter:nodepool_updated:{id}` | 30 min | NodePool refresh cooldown |
| `spot:karpenter:provision_requested:{id}` | 15 min | Last-node provision dedup |
| `spot:ondemand_fallback:{id}` | 12h | On-demand fallback flag |
| `spot:execution_failures:{id}` | 10 min | Karpenter circuit breaker |

---

### 7.6 Karpenter Internals and Integration (Detailed)

Karpenter is an open-source, flexible, high-performance Kubernetes node autoscaler. It provisions the right compute resources (EC2 instances) to match your workload's requirements. The Spot Optimizer Platform integrates deeply with Karpenter to manage instance types, lifecycle (spot/on-demand), and architecture, while also respecting **node templates** that define per-workload constraints. Below we explain how Karpenter operates **inside the customer's cluster** and how the **backend platform interacts** with it.

---

#### 7.6.1 Karpenter on the Cluster Side

Inside the customer's EKS cluster, Karpenter runs as a Deployment (typically in the `karpenter` namespace). It consists of several components:

- **Controller**: Watches for unschedulable pods and creates new nodes to accommodate them.
- **Webhook**: Validates and defaults custom resources (NodePool, EC2NodeClass).
- **Metrics**: Exposes Prometheus metrics for monitoring.

Karpenter uses two primary CRDs:

1. **NodePool** — defines constraints and behaviors for node provisioning:
   - **Requirements**: Instance types, zones, architecture, capacity type (spot/on-demand), etc.
   - **Limits**: Maximum CPU/memory that can be provisioned.
   - **Disruption**: Controls for node consolidation, drift, and expiration. Required setting: `consolidationPolicy: WhenUnderutilized`, `consolidateAfter: 30s`.
   - **Template**: References an `EC2NodeClass` that supplies AWS-specific details.

2. **EC2NodeClass** — holds AWS-specific configuration:
   - **AMI selection**: `alias: al2023@latest` automatically resolves to the correct EKS-optimized AMI for the instance's architecture.
   - **Subnet selectors**: Tags or IDs.
   - **Security group selectors**: Tags or IDs.
   - **IAM instance profile**: The IAM role to attach to instances.
   - **User data**: Startup script for nodes.

When a pod cannot be scheduled, Karpenter evaluates all NodePools, selects one that matches the pod's requirements, and provisions an EC2 instance. The new node then joins the cluster.

Karpenter also handles:
- **Spot interruptions**: Watches SQS queues for termination notices and cordons/drains nodes before they are reclaimed.
- **Consolidation**: Replaces under-utilized nodes with smaller or cheaper ones (`consolidationPolicy: WhenUnderutilized`). This is standard Karpenter operation — the platform does not instruct it.

**Critical interaction with Mode 2 and Mode 3**: After the platform patches pod resource requests via `PATCH_CONTAINER_RESOURCES`, Karpenter observes changed pod demands. If pods now require less, Karpenter consolidates. If pods require more, Karpenter provisions. The platform makes no further API calls — Karpenter draws its own conclusions from the changed pod state.

---

#### 7.6.2 Backend Platform Integration

The Spot Optimizer Platform manages Karpenter indirectly by patching its `NodePool` resources based on ML-driven pool rankings and user-defined node templates. It does **not** provision nodes itself when Karpenter is in `auto` mode.

**Detection and status**:
- The agent's `HeartbeatSender` checks for Karpenter pods and sets Redis key `spot:karpenter:installed:{cluster_id}`.
- The backend also reads DB field `karpenter_mode` (set by the user).

**Node templates**:
- Stored in the database, attached to a cluster or individual node groups.
- Each template defines: `allowed_architectures`, `ami_overrides`, and other node-level settings.
- When a node is evaluated for rebalancing, its associated template determines the architecture mixing policy.

**Steering Karpenter (Mode 1 and Mode 3)**:
When the platform decides to rebalance a node, it creates an `AgentAction` of type `PATCH_KARPENTER_NODEPOOL`. The payload contains:
- `instance_types`: list of target instance types from ML pool rankings (ordered by EV).
- `lifecycle`: `"spot"` (or `"on_demand"` if fallback is triggered).
- `architecture`: single value or both if template allows mixing.
- `zone`: optional target AZ.

**Mode 2 interaction (Rightsizing only)**:
- The platform patches pod resource requests only (`PATCH_CONTAINER_RESOURCES`).
- No `PATCH_KARPENTER_NODEPOOL` is sent.
- Karpenter independently observes the changed pod demands and reacts as usual — provisioning new nodes or consolidating existing ones.
- This is identical standard Karpenter behavior for both `rightsizing_target="spot"` and `rightsizing_target="on_demand"`.

**Fallback to direct EC2**:
If patching fails (CRD missing, RBAC error, timeout) or Karpenter is not installed, the platform falls back to its own direct EC2 launch logic (`_launch_spot_instance_direct()`). In this fallback path, if architecture mixing is allowed, the platform uses **SSM Parameter Store** to fetch the appropriate EKS-optimized AMI for the target architecture.

---

#### 7.6.3 Interaction with Other Platform Components

| Component | Role in Karpenter Integration |
|---|---|
| **Node Template Service** | Stores and provides architecture constraints and AMI overrides. Used during rebalancing to determine mixing policy. |
| **ML Pipeline (Pool Ranking)** | Produces ranked lists of instance types (with EV scores). Passed to Karpenter via NodePool patches in Mode 1 and Mode 3. Not used in Mode 2 — Karpenter selects freely. |
| **Decision Engine** | Decides whether a node should be rebalanced and which candidate pools to target. Considers node template restrictions. |
| **Rebalancer (Mode 1)** | Creates `PATCH_KARPENTER_NODEPOOL` actions and handles fallback to direct EC2. Uses `termination_mode="replacement"` always. |
| **Rightsizing Engine (Mode 2)** | Creates `PATCH_CONTAINER_RESOURCES` actions only. Never interacts with Karpenter directly — Karpenter reacts to pod spec changes on its own. |
| **Optimizer Coordinator (Mode 3)** | Evaluates Gate 1 and Gate 2 independently. Creates combined action when both pass. |
| **Emergency Rebalancer** | On spot interruption, may directly patch NodePool to on-demand fallback or initiate standby replacement. |
| **Agent (Orchestrator)** | Executes the actual Karpenter API calls (patching NodePool, install/uninstall). |
| **SQS Consumer** | Listens for interruption events and triggers emergency flows. |

---

#### 7.6.4 Summary of Benefits

- **Leverages Karpenter's native capabilities** — consolidation, spot interruption handling, and flexible provisioning.
- **ML-driven intelligence** — the platform tells Karpenter **which** instance types to use (Mode 1/3), and Karpenter handles **how** to provision them efficiently.
- **Mode 2 purity** — rightsizing only patches pod specs; Karpenter independently decides node types and count. No coupling between rightsizing and node selection.
- **Node templates** give fine-grained control over architecture mixing and AMI selection.
- **Fallback paths** ensure robustness: if Karpenter fails or is not installed, the platform's own direct EC2 logic takes over.
- **Unified emergency handling** — both Karpenter and the platform react to spot interruptions via the same SQS queue, providing redundancy.

---

## 8) Emergency System

### 8.1 What Constitutes an Emergency

> 🟢 **Low Issue #20:** SQS and IMDS Both Trigger Emergency for Same Interruption. Both `SpotPoller` and SQS can detect the same spot interruption, resulting in two emergency rebalancing tasks running for the same node simultaneously without deduplication beyond the 15-minute action expiry.

| Event | Source | Bypass |
|---|---|---|
| Spot termination notice (2-min warning) | IMDS via SpotPoller / SQS / EventBridge | Delta threshold, savings check, cluster cooldown, pool cooldown |
| EC2 rebalance recommendation | IMDS via SpotPoller | Proactive migration trigger |
| Instance state-change to stopping/stopped | SQS / EventBridge | Emergency rebalancing |
| AWS Health Event (spotInterruption) | SQS | Emergency rebalancing |

All emergency events trigger the creation of an **emergency action** with `priority=10`. This ensures that emergency actions are processed immediately and, if multiple emergencies occur, they can run in parallel.

---

### 8.2 Emergency Flow

**Source**: `backend/workers/tasks/emergency_rebalancer.py` (287L) + `termination_monitor.py` (340L)

**Step-by-step**:

1. **Detection**
   - SpotPoller (IMDS every 5s) on the DaemonSet agent.
   - SQS consumer (every 30s) polling the cluster's interruption queue.
   - EventBridge (via SQS) for instance state changes or health events.

2. **Notification**
   Agent POSTs to `/api/v1/worker/spot-interruption` with `{cluster_id, instance_id, action, termination_time}`.

3. **Backend processing** (`detect_termination_notice()` in `termination_monitor.py`):
   a. Create a `TerminationEvent` record in the database.
   b. Blacklist the affected pool: `SADD risky_pools:{region}` + metadata with TTL (12h).
   c. Update pool pressure in `risk_engine.py`.
   d. Override cluster cooldown via `CooldownController.override_for_emergency()` (clears cluster-level cooldown and rebalance lock).
   e. **Create an emergency action** — a `RebalancingAction` with `priority=10` and `action_type="emergency"`. The action payload includes the instance ID, node name, and termination time.

4. **Action dispatch**
   - The backend immediately pushes the emergency action to the cluster's WebSocket channel as an `emergency_command` message (bypassing the normal polling).
   - The orchestrator's `ActionExecutor` receives the command and submits it to the **emergency thread pool**.
   - Multiple emergencies on different nodes run concurrently (respecting per-node locks).

5. **Emergency rebalancing** (`emergency_rebalancer.py`):
   - **Standby-first path** (if `maintain_standby=True` and a standby node exists):
     1. UNCORDON standby node.
     2. CORDON the interrupted node.
     3. DRAIN the interrupted node with `grace_period=90`, `force=True` (bypass PDBs).
     4. Terminate the interrupted node using `termination_mode="replacement"`.
     5. Mark the standby as active (remove standby label).
     6. Launch a **new standby asynchronously** — respects node template settings.
   - **Normal emergency** (no standby): Creates a `RebalancingAction` with `type="emergency"` and `priority=10`. The auto-rebalancer picks it up immediately because of its high priority, bypassing the normal gate checks.
   - If Karpenter is installed, the action may involve patching the NodePool (e.g., to fallback to on-demand). The fallback logic (Section 7.4) is triggered if needed.

6. **Result reporting**
   The agent reports the outcome via `POST /agents/orchestrator/{cluster_id}/command-result` (or WebSocket). The action is marked `COMPLETED` or `FAILED`, and the cluster's realized savings are recalculated if successful.

---

### 8.3 Monitoring

- `TerminationEvent` records are stored in the database for audit and analysis.
- Redis key `spot:cluster_state:{id}` tracks the cluster's instability level (used by the circuit breaker).
- Circuit breaker transitions:
  - `NORMAL → CONSERVATIVE` after ≥2 rollbacks in 1 hour.
  - `CONSERVATIVE → HALT` after ≥3 rollbacks in 1 hour.
  - Automatic recovery after 30 minutes (CONSERVATIVE) or 2 hours (NORMAL).
- Cross-cluster propagation: `InstabilityPropagator` updates pool pressure for all clusters sharing the affected pool/AZ.

---

### 8.4 Permissions

- **Client AWS account**:
  - `ec2:TerminateInstances` — to terminate the interrupted instance.
  - `ec2:RunInstances` — to launch a new standby (if needed).
  - `sqs:ReceiveMessage` / `sqs:DeleteMessage` — for SQS interruption queue consumption.
- **Agent Kubernetes RBAC**:
  - `patch` nodes (cordon/uncordon).
  - `create` pods/eviction (drain).
  - (If Karpenter is used) `patch` nodepools.

---

### 8.5 Additional Clarifications (Code-Verified)

**Q: Can emergency actions for different clusters run in parallel?**
Yes. The `emergency_rebalancer` is a Celery task that runs independently per cluster. Within a single cluster, the new `ActionExecutor` (with priority-based concurrency) allows multiple emergency actions to run in parallel, provided they target different nodes. Per-node locks ensure safety.

**Q: How are emergency actions prioritized over normal ones?**
Emergency actions are created with `priority=10` (vs. normal priority 0). The orchestrator's polling endpoint orders actions by `priority DESC, created_at ASC`. More importantly, the backend pushes them immediately via WebSocket as `emergency_command` messages, bypassing the queue entirely.

**Q: What is the emergency drain grace period?**
From `emergency_rebalancer.py` L186-206:
- `grace_period=90` seconds — gives pods time to shut down cleanly.
- `force=True` — bypasses PodDisruptionBudgets immediately (AWS does not honour PDBs at the 2-minute hard deadline).
- `emergency=True` — signals the actuator to use the 90-second escalation timer. Any pod still running at T-90s is force-deleted with `grace_period=0` so Kubernetes can reschedule before the 120-second AWS kill.

**Q: What happens if no standby node exists during an emergency?**
From `emergency_rebalancer.py` L115-120: Falls back to `_execute_normal_emergency()`, which creates a `RebalancingAction` with `type="emergency"` and `priority=10`. The auto-rebalancer picks this up with priority (bypasses normal gate checks). The new node (if launched) respects any node template settings.

**Q: What happens if the standby node itself receives an interruption?**
The standby node is treated like any other node — the SpotPoller on that node detects the interruption and triggers the same emergency flow. The cluster temporarily loses its standby protection, but a new standby is created asynchronously. In the meantime, any subsequent primary interruption falls back to the normal emergency path.

**Q: How does the InstabilityPropagator work?**
From `instability_propagator.py` (256L): It uses **Redis pipeline commands**, not pub/sub.
1. On interruption: `INCR propagator:events:{region}:{az}:{type}` (30-min TTL window).
2. Track clusters: `SADD propagator:affected_count:{region}:{az}:{type}` — adds `cluster_id` to a set (2h TTL).
3. Compute Bayesian pool pressure via `calculate_bayesian_pool_pressure()` from `risk_engine.py`.
4. Store pressure: `SET propagator:pool_pressure:{region}:{az}:{type}` (2h TTL).
5. Recompute AZ average by scanning all pool pressure keys for the AZ.
6. **SYSTEMIC threshold**: If ≥3 clusters in the affected set → `recommended_action: ESCALATE_ALL`.
7. Propagation is **synchronous** — it runs within the same request/task that processes the interruption event.

**Q: Is the 90-second emergency drain grace period configurable?**
No. The 90-second grace period is **hardcoded** in `emergency_rebalancer.py`. The `force=True` flag is also hardcoded for emergency drains. These values are chosen based on AWS's 2-minute termination warning.

---

## 9) Rules

### 9.1 Safety Gates (All Rebalancing)

The following safety gates are enforced before any rebalancing action (OD→spot or spot→spot) can proceed. Emergency actions (priority=10) bypass all gates except node-level locking and last-node safety.

| Gate | Condition | Location | Bypassed by Emergency? |
|---|---|---|---|
| Execution lock | Redis NX `lock:workers.auto_rebalancer` (300s) | `auto_rebalancer.py` L1280 | Yes (lock cleared) |
| Optimizer phase | Skip if OptimizerState in `RIGHTSIZING_EVALUATION` or `SYNERGY_EXECUTION` | L2260 | Yes |
| Daily limit | `max_rebalances_per_24h` (default 5, completed only) | L2315 | Yes |
| One-at-a-time | Skip if PENDING/PICKED_UP AgentActions (auto-expire >15 min) | L2546 | Yes (emergency actions jump queue) |
| Last-node safety | Never drain the last running node (counts ALL nodes, not just OD) | L2610 | **No** (even emergency cannot drain last node) |
| Cluster cooldown | `cooldown_override_minutes` (default 60 min) after last completed | L2265 | Yes (force-cleared) |
| Per-instance cooldown | `spot:rebalanced:instance:{id}` (24h TTL) | L890 | Yes (force-cleared) |
| Architecture filter | Exclude candidates not matching allowed architectures (based on node template) | L753-786 | No (but node template may allow mixing) |
| Allocatable check | Reject smaller type if rightsizing OFF | L717-737 | No |
| Concurrency lock | `lock:rebalance_exec:{cluster_id}` (5 min) | L600 | Yes (cleared) |
| Stabilization lock | `CooldownController.check_stabilization_lock()` | L2280 | Yes (cleared) |
| Substitute mutex | Skip if SubstituteManager active | L2300 | Yes (cleared) |
| Resize cooldown | `spot:resize_cooldown:{controller_id}` — checked independently in Gate 2, per-controller | L2295 | Yes (cleared) |

**Notes:**
- **Last-node safety**: The gate checks `running_node_count == 1` — it counts **all running nodes regardless of lifecycle type** (OD or spot, platform-labeled or not). The last OD node in a cluster that also has spot nodes is not the last running node; it is converted normally with no special handling. In the standard replacement flow this gate effectively never fires because the replacement node is always launched before drain — `running_node_count` is already `n + 1` by the time drain executes. The gate only fires in a catastrophic simultaneous multi-node failure where two or more nodes are interrupted at the same time and both terminate before replacements arrive, temporarily leaving only one node alive. See Section 3.1 Last-Node Safety for the three concrete scenarios.
- **Architecture filter**: By default, only instance types matching the current node's CPU architecture are considered. If a node template is attached and its `allowed_architectures` list contains multiple values, the filter is relaxed to include all specified architectures. During emergency replacements, the architecture filter still applies — the emergency rebalancer reads `spot-optimizer/allowed-architectures` from the interrupted node's labels to determine whether cross-architecture candidates are permitted.
- **Resize cooldown key**: The cooldown is tracked **per controller** (`spot:resize_cooldown:{controller_id}`), not per cluster. Each Deployment, StatefulSet, and DaemonSet has its own independent resize cooldown timer.
- **Cooldown AND logic**: All applicable cooldowns must be satisfied for normal actions. Emergency actions force-clear cluster, pool, and instance cooldowns via `emergency_rebalancer.py` (L50-52).
- **Gate rejections in Mode 3**: If both Gate 1 and Gate 2 fail in synergy mode (no action taken), this does **not** increment the rollback counter or circuit breaker. Only executed actions that fail mid-flight count.

---

### 9.2 Blacklisting

**Source**: `backend/services/blacklist_service.py` (423 lines)

**What**: A pool (instance type + AZ) is marked as risky when it experiences an interruption or a DryRun capacity failure. Blacklisted pools are excluded from ML rankings and rebalancing candidates.

**When it happens**:
- Spot interruption detected (IMDS or SQS) → pool blacklisted for 24h (deterministic).
- DryRun capacity failure 1-2× in 24h → blacklisted for 6h.
- DryRun capacity failure 3+× in 24h → blacklisted for 12h (hard reject in ML pipeline).
- ML-predicted high risk (>0.45) → blacklisted for 24h (predictive).
- Execution DryRun failure → **no blacklist**, only a penalty in scoring.

**When it decays**: TTL-based decay via Redis `EXPIRE`. After TTL expires, the pool is automatically removed from `risky_pools:{region}`.

**Storage**:
- Redis SET: `risky_pools:{region}` — all blacklisted pools in the region.
- Redis KEY: `blacklist_failures:{instance_type}:{az}` — failure count (30-day expiry).
- Redis KEY: `risky_pool_meta:{instance_type}:{az}` — JSON metadata with reason, first failure time, etc. (12h TTL).

**Cascade protection**: If >70% of pools in a region are blacklisted

> 🟡 **Medium Issue #14:** Cascade Protection Suspended for 30 Min on Predictive Blacklist, Not Deterministic. If a wave of real interruptions blacklists >70% of pools, predictive blacklisting is suspended even though that's the moment ML risk signals are most needed.

, the system suspends **predictive** blacklisting (ML risk, DryRun, capacity checks) for 30 minutes. Deterministic blacklisting (actual interruptions) is **always** honored. The suspension is stored in Redis: `spot:blacklist_suspended:{region}` (30 min TTL).

**Exponential backoff** (`blacklist_pool()` L38-109):

> 🟡 **Medium Issue #16:** Blacklist Exponential Backoff Maxes at 7 Days, Fixed Multiplier. The blacklist TTL doubles per failure up to 7 days. A pool that had a single bad day could be locked out for a week, and a pool with 5 old failures would immediately get a 7-day blacklist on the next single interruption.

- Base TTL: 24 hours.
- Multiplier: 2× per failure.
- Maximum: 168 hours (7 days).
- Failure counter kept for 30 days.

**Tiered blacklist** (Decision Engine v3, `blacklist_pool_tiered()` L213-268):

| Trigger | TTL |
|---|---|
| DryRun capacity failure 1-2×/24h | 6 hours |
| DryRun capacity failure 3+×/24h | 12 hours |
| ML high risk (>0.45) | 24 hours |
| Termination event (ITN/rebalance-rec) | 24 hours |
| Execution DryRun failure | No blacklist (penalty only) |

**Architecture-aware blacklisting**: Blacklist entries are per `(instance_type, az)`, so they naturally respect architecture — an `arm64` type is separate from an `amd64` type.

**Redis key hygiene** (`cleanup_redis_keys()` L382-422): A daily scan finds orphaned `spot:*` keys with no TTL and sets a 24h safety TTL, preventing key explosion.

---

### 9.3 Cooldown Types

Cooldowns prevent excessive or repetitive actions. All cooldowns are stored in Redis with appropriate TTLs. Emergency actions (priority=10) force-clear cluster, pool, and per-instance cooldowns.

| Type | Redis Key | Default TTL | Purpose | Emergency Bypass? |
|---|---|---|---|---|
| Cluster switch | `spot:cooldown:cluster:{id}` | 60 min | Prevent cluster-level flapping after any rebalance | Yes (cleared) |
| Pool reuse | `spot:cooldown:pool:{pool_id}` | 120 min | Prevent reusing a pool that recently failed | Yes (cleared) |
| Pool switch | `spot:cooldown:action:pool_switch:{id}` | 30 min | Prevent rapid pool changes on the same node | Yes (cleared) |
| Resize | `spot:resize_cooldown:{controller_id}` | 360 min (6h) | Prevent size oscillation on a controller — checked per-controller independently in Gate 2 | Yes (cleared) |
| Substitute | `spot:cooldown:action:substitute:{id}` | 120 min | Prevent substitute node churn | Yes (cleared) |
| Stabilization lock | `spot:stabilization_lock:{id}` | 300s (5 min) | Post-execution stabilization window | Yes (cleared) |
| Per-instance rebalance | `spot:rebalanced:instance:{id}` | 24h | Prevent re-targeting the same EC2 instance | Yes (cleared) |
| ASG suspend lock | `asg:suspend_lock:{asg_name}` | 30s | Serializes concurrent detach-not-decrement operations across multiple replacements in same ASG | No (per-operation) |
| Stateful per-cluster | `spot:stateful:resize:cluster:{id}` | 48h | Stateful rightsizing cluster cooldown | No (stateful never auto-executed) |
| Stateful per-instance | `spot:stateful:resize:instance:{id}` | 48h | Stateful rightsizing instance cooldown | No (stateful never auto-executed) |

---

### 9.4 Which Safety Gates Are Configurable?

| Gate | Configurable? | How |
|---|---|---|
| Execution lock (300s) | No | Hardcoded |
| Daily limit (`max_rebalances_per_24h`) | **Yes** | `stateless_runtime_rules` table |
| Cluster cooldown (`cooldown_override_minutes`) | **Yes** | `cluster_optimization_settings` table |
| Per-instance cooldown (24h) | No | Hardcoded |
| Architecture filter | **Via node template** | `allowed_architectures` in node template |
| Concurrency lock (5 min) | No | Hardcoded |
| PDB respect (`respect_pdb_enabled`) | **Yes** | `stateless_runtime_rules` table |
| Resize cooldown | **Yes** | `stateless_runtime_rules.resize_cooldown_minutes` |
| Stabilization lock (5 min) | No | Hardcoded |
| Allow architecture mixing | **Via node template** | `allowed_architectures` (if contains >1 entry) |

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
| **Patch Container Resources** | `PATCH /apis/apps/v1/namespaces/{ns}/{kind}/{name}` → `spec.template.spec.containers` | `patch` deployments/daemonsets/statefulsets | `actuator._patch_container_resources()` |
| **Detach Instance** | `autoscaling:DetachInstances` (AWS API) | AWS IAM | `actuator._detach_instance_from_asg()` |

---

### 10.2 Drain Logic Details

`actuator.drain_node()` (L282-407):

1. **Cordon** the node first (`cordon_node(node_name, uncordon=False)`).
2. **List all pods** on the node: `list_pod_for_all_namespaces(field_selector='spec.nodeName={node_name}')`.
3. **Skip**:
   - **DaemonSet pods** (`owner_ref.kind == 'DaemonSet'`) — skipped for three reasons: (1) they tolerate `node.kubernetes.io/unschedulable` so evicting them causes immediate rescheduling onto the same cordoned node creating an infinite eviction loop, (2) they are infrastructure (kube-proxy, aws-node, spot-agent, fluentd), not workload — evicting them breaks node networking and monitoring, (3) they self-manage — when the node terminates the DaemonSet controller stops scheduling there, and when the replacement node joins it automatically schedules a fresh pod. No intervention needed.
   - **Mirror pods** (annotation `kubernetes.io/config.mirror`) — static pods bound to the node, not managed by any controller.
   - **Unmanaged pods** (no controller owner reference) unless `force=True`.
4. For each remaining pod:
   - Check PDB violation → if violation **and** `force=True` → **force-delete** pod with `grace_period_seconds=0` (bypasses PDB entirely).
   - If violation **and** `force=False` → skip and add to `failed_evictions` list.
   - Normal eviction: `create_namespaced_pod_eviction()` with grace period (default 60s for normal rebalancing, 90s for emergency).
5. **Eviction retry**: If Kubernetes returns HTTP 429 (PDB Too Many Requests) → retry up to **5 times** with **10s delay** each (L145-205).
6. **VolumeAttachment cleanup** (post-drain, L372-384): `clear_stuck_volume_attachments(node_name, timeout_seconds=30)`.
   - Lists all VolumeAttachments for the node via `StorageV1Api`.
   - Detects stuck attachments: has error OR pending > timeout seconds.
   - Force-deletes stuck attachments → prevents Multi-Attach errors on replacement node.
   - Safe and idempotent — the pod is already gone (drained) and the volume is unused.

**Grace period by caller:**

| Caller | grace_period | force | PDB behavior |
|---|---|---|---|
| Auto rebalancer (Mode 1) | 60s | False | Respected — drain blocked if violated |
| Auto rebalancer (Mode 1, `respect_pdb_enabled=False`) | 60s | True | Force-deleted |
| Synergy mode (Mode 3) | 60s | False | Respected |
| Emergency rebalancer | 90s | True | Bypassed immediately |
| Spot interruption (IMDS) | 30s | True | Bypassed — no time |

**Emergency drain override**: When `drain_node()` is called with `emergency=True`, grace period is set to **90 seconds** and `force=True` is forced. Any pod still running at T-90s is force-deleted with `grace_period=0` so Kubernetes can reschedule before the hard kill.

---

### 10.3 Node Termination — `termination_mode` Parameter

`actuator._terminate_node()` (L1120-1287) accepts a `termination_mode` parameter that controls how the node is removed. Using the wrong mode corrupts ASG DesiredCapacity — this is the critical correctness constraint in the entire termination path.

| `termination_mode` | When used | AWS call | DesiredCapacity |
|---|---|---|---|
| `"replacement"` | Mode 1 (all pool switches), Mode 3 same-count operations | Detach + direct terminate | **Unchanged** |
| `"karpenter"` | Mode 2 spot consolidation, Mode 3 spot consolidation | Karpenter terminates directly | **Not touched** |
| `"scaledown"` | Mode 2 OD consolidation only (intentional capacity reduction) | `ShouldDecrementDesiredCapacity=True` | **Decrements** |

**`termination_mode="replacement"` — detach-not-decrement pattern:**

Used for every node termination in Mode 1 and Mode 3 same-count operations. Node count must never change.

```
Phases 1-2 (launch + cordon/drain): No ASG interaction needed.

Phase 3 — tight 2-3 second window only:
  with redis.lock('asg:suspend_lock:{asg_name}', timeout=30):
      autoscaling.suspend_processes(['Launch'])
      autoscaling.detach_instances(
          InstanceIds=[old_instance_id],
          AutoScalingGroupName=asg_name,
          ShouldDecrementDesiredCapacity=False  ← critical, never True
      )
      ec2.terminate_instances(InstanceIds=[old_instance_id])
      autoscaling.resume_processes(['Launch'])

Result:
  ASG DesiredCapacity unchanged ✅
  ASG sees desired=N, actual=N (replacement node already running) → launches nothing ✅
  Traffic spike during drain → CA can still scale (only blocked for 2-3s) ✅
```

The Redis lock around `suspend_processes` is required. Without it, two concurrent replacements can both call `suspend_processes` and the first `resume_processes` re-enables Launch before the second replacement's detach+terminate completes — creating a window where ASG launches an unwanted node.

The `suspend_processes` window covers **only** the detach+terminate call (~2-3 seconds), NOT the cordon+drain which takes 60-90 seconds. This ensures CA scale-ups in response to traffic are only blocked for seconds, not minutes.

**With Karpenter (replacement mode):**
```
ec2.terminate_instances(old_instance_id)
No ASG interaction at all.
Karpenter manages node inventory separately from ASG DesiredCapacity. ✅
```

**`termination_mode="karpenter"` — Karpenter handles entirely:**

Used when Mode 2 or Mode 3 rightsizing causes a spot node to become empty through consolidation. We do not call any termination API ourselves.

```
Pod resource requests patched down
→ Karpenter consolidation detects underutilized node (WhenUnderutilized, consolidateAfter: 30s)
→ Karpenter evicts remaining pods to other nodes
→ Karpenter calls ec2.terminate_instances() directly
→ ASG DesiredCapacity not touched ✅
```

**`termination_mode="scaledown"` — intentional capacity reduction:**

Used **only** when Mode 2 rightsizing with `rightsizing_target="on_demand"` causes a genuine reduction in required cluster capacity. This is the only place in the entire system where `ShouldDecrementDesiredCapacity=True` is correct.

```
autoscaling.terminate_instance_in_auto_scaling_group(
    InstanceId=instance_id,
    ShouldDecrementDesiredCapacity=True  ← intentional, correct only here
)
ASG DesiredCapacity decrements by 1 ✅
Cluster genuinely needs fewer nodes — workload reduced ✅
```

**Caller → termination_mode mapping:**

| Caller | termination_mode |
|---|---|
| Auto rebalancer Mode 1 (all cases) | `"replacement"` |
| Synergy Mode 3, Gate 1 only (pool switch) | `"replacement"` |
| Synergy Mode 3, both gates, same node count | `"replacement"` |
| Synergy Mode 3, both gates, consolidation | `"karpenter"` |
| Rightsizing Mode 2, spot consolidation | `"karpenter"` |
| Rightsizing Mode 2, OD consolidation | `"scaledown"` |
| Emergency rebalancer | `"replacement"` (or direct EC2 if Karpenter) |

---

### 10.4 PDB Enforcement

> 🟡 **Medium Issue #13:** PDB Check Fails Safe in Wrong Direction.
> **Resolution**: Changed fail-safe to return `False` (safe) when an error occurs, but only after logging the error. The rationale: if the K8s API is temporarily unavailable, we should not block drains; the pod may still be evictable. To avoid false positives, the error is logged and the drain proceeds (with `force=False`). This matches the behavior of `kubectl drain`.

`check_pdb_violation()` (L103-128):

1. List all PDBs in the pod's namespace via `PolicyV1Api.list_namespaced_pod_disruption_budget()`.
2. For each PDB, check if `spec.selector.match_labels` matches all pod labels.
3. If a matched PDB has `status.disruptions_allowed < 1` → UNSAFE (return `True`).
4. If all PDBs allow disruption → SAFE (return `False`).
5. **Fail-safe**: On any API error → return `False` (allow drain) and log the error. Drain proceeds with `force=False`, meaning if the pod actually has a PDB violation, the eviction API will return 429 and the retry logic handles it.

**PDB interaction with termination modes:**

| termination_mode | PDB behavior |
|---|---|
| `"replacement"` (normal) | Respected — drain blocked if `disruptions_allowed < 1` |
| `"replacement"` (`respect_pdb_enabled=False`) | Force-deleted with `grace_period=0` |
| `"karpenter"` | Karpenter respects PDBs natively during consolidation |
| `"scaledown"` | Karpenter respects PDBs natively |
| Emergency | Always bypassed — `force=True`, no time to respect PDBs at 2-min deadline |

---

### 10.5 Force Delete Node

> 🟡 **Medium Issue #12:** Force-Delete Node Doesn't Remove Pod Finalizers.
> **Resolution**: Added `REMOVE_POD_FINALIZERS` action. After force-delete, agent lists all pods in `Terminating` state on the deleted node and patches them to remove finalizers. Triggered automatically after force-delete or manually via UI button.

`actuator.force_delete_node()` (L254-280):

- Used when the underlying EC2 instance is gone (hardware failure, spot reclamation) and the node is stuck in `NotReady`.
- Equivalent to `kubectl delete node <name> --grace-period=0 --force`.
- If node already absent (404) → treated as success (idempotent).
- After deletion, agent lists all pods in `Terminating` state on the node and patches finalizers to `[]` via strategic merge patch — prevents StatefulSet pods with PVCs from hanging in `Terminating` indefinitely.
- Force-delete does **not** go through the detach pattern — the EC2 instance is already gone at this point, so there is no ASG interaction needed. The ASG will detect the instance is gone and react according to its own health check policy.

---

### 10.6 Node Resolution

Multiple resolution strategies (fallback chain):

1. `payload.node_name` — direct from backend DB.
2. `_find_node_by_instance_id(instance_id)` (L662-678) — matches `spec.providerID` containing `aws://{az}/{instance_id}`.
3. `_find_node_name(instance_type, az)` (L680-697) — label-based: `node.kubernetes.io/instance-type` + `topology.kubernetes.io/zone`.

---

### 10.7 Node Template Association

When a new node is provisioned (via Karpenter or direct EC2), the platform associates it with a node template if one was used. This association is stored as K8s labels on the node object, enabling the rebalancer and rightsizing engine to apply architecture constraints and template-specific settings on all future operations targeting that node.

**Standard labels applied:**

| Label | Value | Purpose |
|---|---|---|
| `spot-optimizer/template-id` | UUID of the node template | Identifies which template governs this node |
| `spot-optimizer/allowed-architectures` | Comma-separated list e.g. `"amd64"` or `"amd64,arm64"` | Tells rebalancer whether architecture mixing is permitted when replacing this node |
| `spot-optimizer/launched-by` | `"platform"` | Tags platform-launched instances for accurate savings calculation |
| `spot-optimizer/termination-mode` | `"replacement"` or `"scaledown"` | Records intended termination behavior for this node |

**How labels are applied:**

- **Direct EC2 launch**: Backend includes a user-data script that applies labels via `kubectl patch node` after the node joins the cluster. Alternatively a `LABEL_NODE` AgentAction is sent once the node is Ready.
- **Karpenter**: NodePool `spec.template.metadata.labels` is patched to include these labels when the platform creates or updates a NodePool. Karpenter automatically stamps new nodes with these labels at provisioning time.
- **Existing nodes**: Backend sends a `LABEL_NODE` AgentAction to apply or update template associations after a template change.

**How labels are consumed:**

- **Rebalancer (Mode 1 and Mode 3)**: Reads `spot-optimizer/allowed-architectures` to determine whether to include cross-architecture candidates in pool search. If label contains multiple values → mixing permitted. If label is missing → default to preserving current architecture.
- **Termination logic**: Reads `spot-optimizer/termination-mode` to confirm the correct `termination_mode` for this node. Acts as a secondary safety check — if the label says `"replacement"` and the caller tries `"scaledown"`, the termination is blocked and logged as a conflict.
- **Savings calculator**: Reads `spot-optimizer/launched-by=platform` to include only platform-launched instances in `realized_savings` calculation. Pre-existing spot instances without this label are excluded.

**Last-node safety interaction:**

The last-node safety gate counts **all running nodes regardless of lifecycle type or label** — not just OD nodes or platform-labeled nodes. So the last OD node in a cluster that also has spot nodes is not the last running node. It is converted normally. The gate only fires when `running_node_count == 1` total, which in the normal replacement flow never triggers because the replacement node is always launched before the drain step — meaning `running_node_count` is already `n + 1` by the time drain executes.

---

## 11) Failure Handling

### 11.1 Failure by Phase

| Phase | Failure | Action | Recovery | Notes |
|---|---|---|---|---|
| **Phase 1** (spot launch) | All instance types exhausted | Action status → `failed`, error message set | Instance cooldown set, retry next cycle | If node template allows architecture mixing, the system may retry with different architecture variants before failing. |
| **Phase 1** | Karpenter timeout | Single node → refuse drain; Multi node → proceed | Fail action / proceed with drain | Timeout may occur if Karpenter cannot provision a node matching the updated NodePool requirements. Falls back to direct EC2 launch. |
| **Phase 2** (CORDON) | K8s API error | Uncordon + terminate orphan spot + resume ASG | Cooldown cleared for retry | For emergency actions, the system retries immediately (with priority) instead of clearing cooldown. |
| **Phase 2** (DRAIN) | PDB conflict | Skip EC2 terminate, terminate orphan spot directly via EC2 API | Cooldown cleared for retry | Emergency actions force-drain with `force=True`, bypassing PDBs; normal actions respect PDBs. |
| **Phase 2** (DRAIN) | Timeout | Same as PDB conflict | Cooldown cleared for retry | Emergency drain uses a 90-second grace period and force-deletes remaining pods. |
| **Phase 2** (TERMINATE) | EC2 API error | Terminate orphan spot, report failure | Manual intervention flagged | The orphan spot (the new node) is terminated to avoid billing; the original node remains. |
| **Orphan cleanup** | DB record not found | Direct EC2 termination via `replacement_spot_instance_id` from metadata | — | If the DB record of the replacement node is missing, the system uses the instance ID stored in the action metadata. |
| **Pre-launch** | Previous orphan found | Verify AWS state → terminate if running/pending | Clean metadata of failed action | Before launching a new spot instance, the system checks for any previously launched orphan and terminates it to avoid duplicates. |

**Emergency action special handling**:
- Emergency actions (priority=10) bypass most cooldowns and locks, but still respect node-level locking to prevent concurrent operations on the same node.
- If an emergency action fails during Phase 2 (drain/terminate), the system will **not** clear cooldowns (since they were already cleared) but will log the failure and trigger an immediate retry via the emergency rebalancer (if within the 2-minute window).

---

### 11.2 Circuit Breaker

The circuit breaker protects the cluster from repeated failures by progressively reducing automation aggressiveness. It operates per cluster and is influenced by cross-cluster propagation.

| State | Trigger | Effect | Recovery |
|---|---|---|---|
| **NORMAL** | — | Full automation, normal risk thresholds. | — |
| **NORMAL → CONSERVATIVE** | ≥2 rollbacks (failed actions) in 1 hour | Risk multiplier: 1.3 (effective risk ceiling multiplied by 0.77). Normal actions still allowed but with tighter risk tolerance. Emergency actions unaffected. | After 30 minutes with no new rollbacks, returns to NORMAL. |
| **CONSERVATIVE → HALT** | ≥3 rollbacks in 1 hour | **ALL automation blocked** — no normal rebalancing or rightsizing actions. Emergency actions (spot interruptions) still run. | After 30 minutes stable (no rollbacks), moves to CONSERVATIVE. |
| **HALT → CONSERVATIVE** | 30 min stable | Automation resumes in CONSERVATIVE mode. | — |
| **CONSERVATIVE → NORMAL** | 2 hours stable | Full automation restored. | — |

**Circuit breaker and priority actions**: Emergency actions (priority=10) do **not** increment the rollback counter for the circuit breaker. Only normal rebalancing and rightsizing actions that fail and roll back affect the circuit breaker. Gate rejections in Mode 3 (both gates fail, no action taken) also do **not** increment the rollback counter.

---

### 11.3 Cross-Cluster Propagation

When a spot interruption occurs in one cluster, the `InstabilityPropagator` updates pool pressure for **all clusters** sharing the same pool (region + AZ + instance type). This is done synchronously within the interruption handling task.

- **Redis keys**:
  - `propagator:events:{region}:{az}:{type}` — counter of recent interruptions (30-min TTL).
  - `propagator:affected_count:{region}:{az}:{type}` — set of cluster IDs affected (2h TTL).
  - `propagator:pool_pressure:{region}:{az}:{type}` — computed Bayesian pressure score (2h TTL).

- **SYSTEMIC event**: If ≥3 clusters are in the affected set for a given pool, the system sets `RISK:{az}:{instance_type} = "DANGER"` (30 min TTL). This triggers an **escalation** in all clusters using that pool — the effective risk ceiling is lowered further.

- **Node template impact**: Pool pressure is per specific `(instance_type, az)`. If the template allows mixing, the cluster might still avoid the pressured pool by selecting a different architecture variant, provided that variant is not also under pressure.

---

### 11.4 Resize Guard

`resize_guard_worker.py` monitors cluster health for **2 hours** after any rightsizing action (either automatic or manual). It checks:

- **CPU stress**: If `cpu_avg_10m > 85%` sustained for 10 minutes → proposal marked `FAILED` → revert (stateless only) or alert (stateful).
- **Pod restart spike**: If pod restart rate exceeds `baseline × 2` (baseline calculated from the 24h before the resize) → proposal marked `FAILED` → revert.
- **Memory pressure**: If more than 5 memory pressure events are recorded on any node in the 2-hour window → proposal marked `FAILED` → revert.

**Synergy mode addition**: In Mode 3, the resize guard also monitors node pool risk signals for 2 hours post-execution in addition to pod-level metrics. This catches cases where the new combined pool choice (after both gates passed) leads to elevated pool risk that wasn't predicted at decision time.

**Interaction with node templates**: If a resize involved changing the node's architecture (because the template allowed mixing), the resize guard still applies the same checks. The baseline for pod restarts is calculated per controller, so architecture changes that cause temporary pod restarts are captured.

If a proposal fails the resize guard, an audit event is logged and the system may revert the rightsizing action. Automatic reversion is only attempted for stateless controllers; stateful actions require manual rollback.

---

## Additional Questions

### Security & RBAC

> 🔴 **Critical Issue #2:** Orchestrator Endpoints Unauthenticated. Both `/agents/orchestrator/{cluster_id}/pending-commands` and `/agents/orchestrator/{cluster_id}/command-result` lack Bearer token validation. Any request with a known `cluster_id` can read pending commands or inject fake results.

- **Agent auth**: Bearer token (`API_TOKEN`) set during installation.
- **Action verification**: HMAC-SHA256 with `SECRET_KEY` on every action payload (WebSocket and HTTP).
- **Backend API**: Organization-scoped RBAC via `Role` + `Permission` models. Users are assigned roles (admin, viewer, operator) with permissions like `cluster:edit`, `action:approve`, `api_key:manage`.
- **Cross-account**: STS AssumeRole with ExternalId for customer AWS accounts.
- **API key rotation**: `POST /clusters/{id}/agent/disconnect` generates a new `secrets.token_urlsafe(32)` key — running agents receive 401 immediately. Permission required: `api_key:manage`.
- **Orchestrator endpoint auth gap**: The orchestrator polling endpoints currently do **not** use `validate_api_key`. This is scheduled to be fixed in the next release.

---

### Multi-tenancy

- Data isolated by `organization_id` → `account_id` → `cluster_id` hierarchy.
- Each cluster has a unique `API_KEY` for agent authentication.
- Redis keys include `cluster_id` to isolate data (e.g., `spot:cooldown:cluster:{id}`).
- DB queries always filter by `cluster_id` (and often by `organization_id` via joined tables).
- Node templates are also scoped to an organization and can be shared across multiple clusters in the same org.

---

### High Availability & Scaling

- **Backend**: Gunicorn workers with configurable number of processes. Typically run behind a load balancer.
- **Celery workers**: Separate containers for:
  - `celery-worker` (general tasks, including rebalancing and rightsizing).
  - `celery-beat` (scheduler for periodic tasks).
  - `celery-emergency` (dedicated worker for the `emergency` queue, with higher concurrency and priority).
- **Redis**: Single instance (no HA configured in current setup). A Redis restart would temporarily lose cooldowns, blacklists, and pool rankings — all are rebuilt automatically by periodic tasks within minutes.
- **Database**: PostgreSQL with JSONB columns for flexible metadata. Configured with replication (RDS Multi-AZ) for production deployments.
- **Component failure**: Celery auto-retries tasks with `max_retries=3` and exponential backoff. If a worker dies, tasks are re-queued (if using acks_late) or picked up by another worker.
- **Emergency queue**: Dedicated worker ensures that spot interruption handling is never blocked by long-running normal rebalancing tasks.

---

### Cost Tracking & Reporting

> 🟠 **High Issue #3:** Savings Formula Counts Pre-Existing Spot Instances. The formula `SUM(MAX(0, od_price - spot_price))` applied to every running spot instance regardless of whether Spot Optimizer placed it would inflate savings. This is addressed by filtering to `spot-optimizer/launched-by=platform` labeled instances only.

- **SavingsCalculator** (`savings_calculator.py`): Computes per-cluster realized savings as:
  ```
  realized_savings = SUM( MAX(0, od_price - spot_price) )
                     for each running SPOT instance
                     where spot-optimizer/launched-by=platform
  ```
  - `od_price` from Redis `pricing:{region}:ondemand:{type}`.
  - `spot_price` from Redis `pricing:{region}:spot:{type}:{az}`.
  - Only instances with `lifecycle='spot'`, `state='running'`, and `spot-optimizer/launched-by=platform` label are included. Pre-existing spot instances without this label are excluded.
- **Daily aggregation**: `daily_cluster_stats` table stores per-cluster snapshots of savings, spot usage %, and cost.
- **Cluster.realized_savings_monthly**: Updated after every successful rebalance and recalculated periodically by Celery beat.
- **Cost attribution**: Savings are attributed to the cluster where the spot instance runs.

---

### Upgrade Process

- **Agent upgrades**: The agent runs as a DaemonSet and Deployment. Upgrades are performed by updating the container image (`kubectl set image` or reapplying the manifest). The agent version is reported in the heartbeat and `User-Agent` header.
- **Backend upgrades**: Rolling updates via Kubernetes Deployment; database migrations are run automatically via Alembic (as an init container or job).
- **WebSocket protocol**: Designed to be backward-compatible. New action types unknown to old agents are logged as errors but do not crash the agent. However, new features (e.g., priority actions) may require a minimum agent version.
- **Update endpoint**: `POST /clusters/{id}/update-agent` redeploys both DaemonSet and Orchestrator with the latest image.
- **Version skew policy**: No strict policy, but it is recommended to keep agents within one major version of the backend.

---

### Compliance & Auditing (Code-Verified)

> 🟠 **High Issue #4:** Decision Audit Expires in 24h, Not Persisted to DB. `ObservabilityLogger` stores only the last 100 decisions per cluster in Redis with a 24h TTL. For post-incident debugging or compliance audits, any decision trail older than 24h is lost.

**Audit Log Model** (`audit_log.py`):

| Column | Type | Purpose |
|---|---|---|
| `id` | `String(36)` PK | UUID |
| `timestamp` | `DateTime(tz)` | Millisecond-precision audit timestamp |
| `actor_id` | `String(36)` | User ID or `system` |
| `actor_name` | `String(255)` | Human-readable actor name |
| `event` | `String(255)` | Action performed (e.g., `CLUSTER_CREATED`, `REBALANCE_APPROVED`, `NODE_TEMPLATE_UPDATED`) |
| `resource` | `String(255)` | Resource affected (e.g., cluster ID, instance ID, template ID) |
| `resource_type` | Enum | `CLUSTER`, `INSTANCE`, `TEMPLATE`, `POLICY`, `HIBERNATION`, `USER`, `ACCOUNT` |
| `outcome` | Enum | `SUCCESS` or `FAILURE` |
| `ip_address` | `String(45)` | IPv4 or IPv6 |
| `user_agent` | `String(512)` | Request user agent |
| `diff_before` | JSONB | State before change (for updates) |
| `diff_after` | JSONB | State after change |
| `checksum` | `String(64)` | SHA-256 tamper-evidence hash of `(actor_id + event + resource + timestamp + diffs)` |

- **Immutable**: No `update()` method on the model — updates are prevented at the application layer.
- **Tamper detection**: SHA-256 checksum computed on insert by `audit_service.py`. A periodic Celery task re-verifies integrity by recalculating checksums and alerting on mismatch.
- **Indexes**: `timestamp DESC`, `(actor_id, timestamp)`, `(resource_type, timestamp)` for fast querying.
- **Retention policy**: No automatic deletion; records persist indefinitely.
- **Decision audit**: `ObservabilityLogger` stores the last 100 decision outcomes per cluster in Redis (`obs:decisions:{id}`, 24h TTL) for quick debugging.
- **Execution history**: `rebalancing_actions` and `agent_actions` tables retain full history of all actions, including metadata (e.g., selected pools, failure reasons, node template used, gate outcomes for synergy mode).
- **Termination events**: `termination_events` table records every spot interruption, including pool, AZ, and source (IMDS/SQS).

---

### Failure Notification

- **Circuit breaker audit**: A scheduled Celery task (`circuit_breaker.audit_log`) logs circuit breaker state changes to the audit log and to a dedicated Redis channel.
- **Logging**: All failures are logged via structured logging (Python `logging` module) with fields like `cluster_id`, `action_id`, `error`, and `stack_trace`.
- **No external alerting by default**: The platform does **not** include built-in integrations with Slack, PagerDuty, or email. However, it exposes metrics (e.g., Prometheus counters for failed actions) that can be used to trigger alerts in external monitoring systems.
- **UI visibility**: Failed actions are visible in the dashboard with status `failed` and an `error_message`. Decision rejection counters (`spot:rejection_counters:{cluster_id}`) are exposed via the cluster summary endpoint. Gate rejection reasons (`gate_1_rejection`, `gate_2_rejection`) are logged per-action in synergy mode.