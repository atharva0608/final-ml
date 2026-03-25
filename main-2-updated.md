# Spot Optimizer Platform — Comprehensive Technical Report

> **Source of truth**: All answers derived exclusively from `.py`, `.jsx`, `.yaml` code files.
> **Last updated**: 2026-03-23
> **Files analyzed**: 160+ backend Python services, 8 agent files, 70+ models, 36 workers, 20 core modules
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

The method accepts a `termination_mode` parameter. The old default `decrement_asg=True` behavior has been replaced with explicit mode control to prevent ASG DesiredCapacity corruption. See Section 11.3 for the full termination mode reference.

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

Actions stuck in `PENDING` or `PICKED_UP` status for >15 minutes are **auto-expired** by the `auto_rebalancer.py`. The rebalancer queries `AgentAction` records where `status IN (PENDING, PICKED_UP)` and `created_at < now() - 15min`, then sets `status=EXPIRED`. This prevents dead actions from blocking the rebalancer indefinitely. The next rebalancer cycle will create a fresh action.

**Q: Are actions processed in order or is there priority logic?**

Actions are processed in **FIFO order** by `created_at` timestamp. The Orchestrator polls `/agents/orchestrator/{id}/pending-commands` which returns actions ordered by `created_at ASC`. There is no priority queue — emergency actions bypass cooldowns at creation time but are still fetched in chronological order. Emergency actions are created by the `emergency_rebalancer`, which force-clears locks and cooldowns before insertion, so they are processed in the next cycle without waiting.

**Q: Is the Orchestrator polling endpoint authenticated the same way as other agent endpoints?**

**No — security gap identified.** The DaemonSet endpoints (`/agents/actions/pending`, `/agents/register`, `/agents/heartbeat`) use `Depends(validate_api_key)` which requires Bearer token auth. However, the Orchestrator endpoint `GET /agents/orchestrator/{cluster_id}/pending-commands` does **NOT** use `validate_api_key` — it takes `cluster_id` as a path parameter and queries directly. Similarly, `POST /agents/orchestrator/{cluster_id}/command-result` also lacks auth.

**Q: WebSocket reconnection — what are the exact backoff parameters and buffer behavior?**

From `agent/websocket_client.py`:
- **Reconnect delay**: Exponential backoff from `1s` → `60s` (`min_reconnect_delay=1`, `max_reconnect_delay=60`)
- **Max attempts**: 10 consecutive failures (`max_reconnect_attempts=10`)
- **Message buffer**: `collections.deque(maxlen=1000)` (`max_buffer_size=1000`)
- **Buffer overflow**: Messages are **silently dropped** (deque automatically evicts oldest)
- **On reconnect**: Buffered messages are flushed to the new connection
- **After 10 failures**: Falls back to HTTP action polling (`ACTION_POLL_INTERVAL=10s`)

### 1.7 What Happens if Agent is Uninstalled

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
| **Spot prices** | Platform (master) account | `ec2.describe_spot_price_history()` (paginator, all AZs, no filter) | Every 10 min | Redis: `spot_price:{region}:{az}:{instance_type}` → JSON `{"price": "0.0124", "timestamp": "..."}` |
| **On-demand prices** | Platform (master) account | AWS Pricing API `GetProducts` | Every 12h | Redis: `od_price:{region}:{type}` + `ondemand_price:{region}:{type}` → plain string `"0.0464"` |
| **Spot Advisor data** | Public (no auth) | Web scraper on AWS public JSON endpoint | Every 12h | Redis: `spot_advisor:{region}:{type}:Linux` → JSON `{"interruption_index": 0-4, "savings_percentage": 0-90}` |

**Critical: Redis key format contracts** (cache_builder depends on exact formats):
- Spot price value **MUST be JSON** `{"price": str, "timestamp": str}` — `cache_builder` uses `json.loads(raw).get('price')`
- OD price value **MUST be plain string** float — `_lookup_od_price()` uses `float(raw)` directly
- OD price written to **TWO keys**: `od_price:{region}:{type}` (AWSPricingService read) + `ondemand_price:{region}:{type}` (cache_builder read)

**Pricing worker** (`backend/workers/tasks/pricing_worker.py`):
- `refresh_regional_pricing()` runs every 10 minutes — calls `refresh_regional_pricing_batch()` (spot + OD combined).
- `ingest_spot_prices()` runs every 10 minutes — dedicated spot-only ingest via `_refresh_regional_pricing()` paginator.
- `refresh_ondemand()` runs every 12 hours — dedicated OD refresh via `get_ondemand_price()` per instance type.
- All tasks aggregate required instance types across all active clusters in a region.
- Fetches spot prices via EC2 API using the **platform's master account credentials** (no STS AssumeRole needed).
- Updates `pricing:last_updated:{region}` timestamp after a successful refresh.
- **Enterprise guardrail**: If a region's pricing has not been updated in the last 15 minutes, optimizations for that region are blocked.

**Spot Advisor scraper** (`spot_advisor_scraper.py`):
- Runs every 12 hours (Celery beat: `scrapers.spot_advisor.scrape`, 43200s).
- Fetches the public Spot Advisor JSON from `https://spot-bid-advisor.s3.amazonaws.com/spot-advisor.json`.
- Parses only Linux data — never loops over Windows/SUSE.
- Index map: `{0: 5, 1: 10, 2: 15, 3: 20, 4: 25, missing: None}` — KeyError → `None` (NEVER defaults to 5).
- Per-region hash comparison — skips unchanged regions.
- After every successful scrape writes two keys:
  - Global: `spot:advisor:last_scraped` (ISO timestamp)
  - Per-region: `spot:advisor:last_scraped:{region}` (ISO timestamp)
- `pool_ranking_service.py._ensure_spot_advisor_fresh()`: 6h=warn, 24h=re-scrape inline.
- Stores ALL instance types from the JSON — not just existing DB records.

#### Pricing Staleness — Decision Engine Impact (Code-Verified)

From `decision_engine.py` **Step 1b**:
- The Decision Engine checks `pricing:last_updated:{region}` timestamp in Redis.
- If `staleness_minutes > 15` → **reject all decisions** for that region with reason `"pricing_stale"`.
- If **no timestamp exists** (key missing) → **fail-open** (allow decisions to proceed).
- The `pricing_worker.py` clears `PRICING_STALE` flags when it successfully refreshes prices.

---

### 2.2 Data Fetch Frequency — Full Celery Beat Schedule

**Source**: `backend/workers/app.py` (verified 2026-03-23)

| Task Name | Schedule | Purpose |
|---|---|---|
| `workers.discovery.scan_all_accounts` | 300s (5 min) | Scan all AWS accounts for EC2 + EKS |
| `backend.workers.tasks.health.cleanup_zombie_nodes` | 120s (2 min) | Zombie node cleanup |
| `backend.workers.tasks.health.reset_stale_agents` | 60s (1 min) | Agent stale detection |
| `backend.workers.tasks.health.check_reversion_opportunities` | 3600s (1 hr) | Reversion check |
| `workers.cost.calculate_cluster_costs` | 900s (15 min) | Cost calculator |
| `workers.savings.calculate_real_savings` | 1800s (30 min) | Realized savings recalculation |
| `workers.approval.cleanup_expired` | 300s (5 min) | Approval cleanup |
| `workers.cost.sync_cost_explorer` | 86400s (24h) | Cost Explorer sync |
| `workers.cost.cleanup_old_cost_data` | 604800s (7 days) | Cost Explorer data cleanup |
| `workers.pricing.refresh_all_resource_prices` | 86400s (24h) | Resource pricing refresh |
| `backend.workers.tasks.daily_stats_aggregator.aggregate_daily_stats` | 86400s (24h) | Multi-cluster daily aggregation |
| `execute_hibernation_scheduler` | 60s (1 min) | Hibernation scheduler |
| `workers.optimizer.pool_optimization` | 1800s (30 min) | Unified pool optimization |
| `workers.optimizer.rightsizing_evaluation` | 86400s (24h) | Unified rightsizing evaluation |
| `workers.optimizer.resize_guard` | 300s (5 min) | Post-resize guard |
| `workers.optimizer.update_pod_restart_baseline` | 3600s (1 hr) | Pod restart baseline update |
| `workers.termination_monitor` | 30s | Termination monitor |
| `workers.auto_rebalancer` | 15s | Auto-rebalancer main loop |
| `workers.auto_scaler.run` | 30s | ASCP auto-scaler |
| `workers.ascpai.sync_karpenter_nodepools` | 30s | Karpenter NodePool sync |
| `workers.pod_metrics.cleanup_old_metrics` | 86400s (24h) | Pod metrics cleanup |
| `workers.pricing.refresh_regional_pricing` | 600s (10 min) | Regional spot price refresh |
| `pool_rotation.check_all_clusters` | 300s (5 min) | Pool rotation check |
| `pool_rotation.refresh_all_caches` | 900s (15 min) | Pool cache refresh |
| `workers.control_plane.run_all_clusters_decision_cycle` | 300s (5 min) | Control plane decision cycle |
| `warm_spare.maintain_all_clusters` | 300s (5 min) | Warm spare maintenance |
| `workers.sqs_consumer.poll_interruption_queues` | 30s | SQS interruption consumer |
| `cache_warmer` | 3600s (1 hr) | Cache warmer |
| `dry_run_refresher` | 300s (5 min) | Dry-run pre-verification for top 100 pools |
| `recovery_monitor` | 60s | Recovery monitor |
| `backend.workers.tasks.recovery_monitor.scan_orphans` | 300s (5 min) | Orphan instance scan |
| `build_global_pool_cache` (ap-south-1) | 3600s (1 hr) | Global pool cache rebuild — ap-south-1 |
| `build_global_pool_cache` (us-east-1) | 3600s (1 hr) | Global pool cache rebuild — us-east-1 |
| `build_global_pool_cache` (ap-southeast-1) | 3600s (1 hr) | Global pool cache rebuild — ap-southeast-1 |
| `scrapers.spot_advisor.scrape` | 43200s (12h) | Spot Advisor full scrape |
| `workers.instance_catalog.refresh_catalog` | crontab(hour=3, minute=0) | Instance catalog refresh nightly (beat key: `instance-catalog-refresh-daily-3am`) |
| `workers.pricing.refresh_ondemand` | 43200s (12h) | On-demand price refresh |
| `workers.pricing.ingest_spot_prices` | 600s (10 min) | Spot price ingest |
| `circuit_breaker.audit_log` | 600s (10 min) | Circuit breaker audit log |
| `health_monitor` | 300s (5 min) | Cluster health monitor |
| `drift_detector` | 900s (15 min) | Drift detector (stuck actions, stale caches) |
| `workers.reconciliation_worker` | 300s (5 min) | Reconciliation worker (DB vs EC2 state sync) |
| `workers.cleanup_terminated_instances` | crontab(hour=3, minute=30) | Nightly cleanup of terminated instance rows >30 days |
| `maintain_all_verified_pool_sets` | 300s (5 min) | Maintain per-cluster verified pool ZSET (capacity-confirmed, target=20) |
| `backend.workers.tasks.recovery_monitor.compute_all_cluster_coverage` | 300s (5 min) | Per-cluster spot coverage (COVERED/AT_RISK/STRANDED); writes `cluster_coverage:{cluster_id}` |

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
| `rebalancing_actions` | `rebalancing_action.py` | OD→Spot and S2S migration actions — see full schema below |
| `agent_actions` | `agent_action.py` | K8s actions sent to agent (CORDON, DRAIN, TERMINATE, PATCH) |
| `pod_metrics` | `pod_metric.py` | Pod-level CPU/memory for rightsizing |
| `termination_events` | `termination_event.py` | Spot interruption history |
| `rightsizing_proposals` | `rightsizing_proposal.py` | Rightsizing recommendations |
| `spot_advisor_rates` | `spot_advisor_rates.py` | AWS Spot Advisor data per instance type (UNIQUE on region+instance_type) |
| `family_hour_baselines` | `family_hour_baseline.py` | Weekly family-hour statistics for ML |
| `pricing` | `pricing.py` | Spot/OD price history |
| `daily_cluster_stats` | `daily_cluster_stats.py` | Daily aggregated cluster statistics |
| `optimizer_state` | `optimizer_state.py` | Per-cluster optimizer phase tracking |
| `system_config` | `system_config.py` | Platform-wide config (AWS keys, settings) |
| `api_keys` | `api_key.py` | Per-cluster API keys for agent auth |
| `audit_log` | `audit_log.py` | User action audit trail |
| `hibernation_schedules` | `hibernation_schedule.py` | Cluster hibernation schedules (many-to-many) |
| `cluster_baselines` | `cluster_baseline.py` | Per-cluster baseline metrics for savings anchoring |
| `launch_outcomes` | `launch_outcome.py` | Spot launch attempt results — feeds pool reputation |
| `instance_catalog` | `instance_catalog.py` | AWS instance type specs (vcpu, memory, architecture) |
| `node_alternative_cache` | `cluster.py` | Per-node alternative pool list with coverage status (COVERED/AT_RISK/STRANDED/IMMOVABLE) |
| `node_templates` | `node_template.py` | Global or cluster-scoped node constraint envelopes |
| `node_template_versions` | `node_template.py` | Immutable versioned constraint JSON for each template |
| `cluster_template_mappings` | `node_template.py` | One-to-one mapping: which active template version applies to each cluster |

#### `rebalancing_actions` Full Column Schema (code-verified 2026-03-23)

| Column | Type | Nullable | Purpose |
|---|---|---|---|
| `id` | Integer PK | — | Auto-increment |
| `cluster_id` | String(100) | No | Cluster identifier |
| `trigger` | String(20) | No | `'emergency'` or `'graceful'` |
| `source_pool` | String(100) | No | `'instance_type:az'` of replaced node |
| `target_pool` | String(100) | No | `'instance_type:az'` of new pool |
| `status` | String(20) | No | `in_progress`, `completed`, `failed`, `deferred`, `waiting_agent`, `pending_approval`, `EXPIRED` |
| `nodes_affected` | Integer | Yes | |
| `pods_migrated` | Integer | Yes | |
| `started_at` | DateTime | No | |
| `completed_at` | DateTime | Yes | |
| `duration_seconds` | Integer | Yes | |
| `error_message` | Text | Yes | |
| `action_metadata` | JSONB | Yes | Step timestamps, instance IDs, pool details |
| `realized_savings_hourly_usd` | Float | Yes | Legacy column |
| `realized_savings_monthly_usd` | Float | Yes | Legacy column |
| `source_od_price_hr` | Float | Yes | OD price at decision time |
| `target_spot_price_hr` | Float | Yes | Intended spot price |
| `estimated_savings_hr` | Float | Yes | |
| `estimated_savings_mo` | Float | Yes | |
| `actual_instance_type` | String(50) | Yes | May differ from target if fallback used |
| `actual_az` | String(50) | Yes | |
| `actual_spot_price_hr` | Float | Yes | |
| `realized_savings_hr` | Float | Yes | |
| `realized_savings_mo` | Float | Yes | |
| `realized_savings_pct` | Float | Yes | |
| `savings_gap_hr` | Float | Yes | estimated − realized (0 if no fallback) |
| `created_at` | DateTime | server_default | |
| `current_state` | String(30) | Yes | State machine state (see below) |
| `state_entered_at` | DateTime | Yes | When `current_state` was entered |
| `state_history` | JSONB | Yes | `[{state, entered_at, exited_at}]` |
| `lock_version` | Integer | Yes (default 0) | Optimistic-lock counter |
| `source_instance_id` | String(50) | Yes | EC2 instance ID of the replaced node |

**State machine values** (`current_state`): `CREATED` → `POOL_SELECTED` → `SOURCE_CORDONED` → `SOURCE_DRAINED` → `REPLACEMENT_LAUNCHING` → `REPLACEMENT_READY` → `SOURCE_TERMINATING` → `COMPLETED` | `FAILED` | `DRAIN_TIMEOUT`

#### `launch_outcomes` Full Column Schema (code-verified 2026-03-23)

| Column | Type | Nullable | Purpose |
|---|---|---|---|
| `id` | Integer PK | — | Auto-increment |
| `pool_key` | String(100) | No | `'instance_type:az'` |
| `cluster_id` | String(100) | No | |
| `instance_type` | String(50) | No | |
| `az` | String(50) | No | |
| `region` | String(50) | No | |
| `outcome` | String(20) | No | `'success'`, `'failed'`, `'interrupted'` |
| `actual_spot_price_hr` | Float | Yes | Price at launch time |
| `uptime_hours` | Float | Yes | Hours alive; `None` = still running |
| `launched_at` | DateTime | No | |
| `resolved_at` | DateTime | Yes | `None` = still running |
| `failure_reason` | Text | Yes | Populated when outcome ≠ success |
| `rebalancing_action_id` | Integer | Yes | Links to `rebalancing_actions.id` |
| `created_at` | DateTime | server_default | |

**Indexes**: `idx_launch_outcomes_pool_key (pool_key, launched_at)`, `idx_launch_outcomes_cluster (cluster_id, launched_at)`

#### `node_alternative_cache` Full Column Schema (code-verified 2026-03-23)

| Column | Type | Nullable | Purpose |
|---|---|---|---|
| `id` | Integer PK | — | Auto-increment |
| `cluster_id` | String(36) FK→clusters | No | Cluster this node belongs to |
| `node_id` | String(36) | Yes | `Instance.id` (if available) |
| `node_name` | String(255) | No | K8s node name or instance ID |
| `instance_type` | String(50) | Yes | EC2 instance type |
| `resource_profile` | JSONB | Yes | `NodeProfile` dict (vCPU, memory, arch) |
| `alternative_pools` | JSONB | Yes | List of ranked pool dicts |
| `alternative_count` | Integer | Yes (default 0) | Number of viable alternative pools |
| `best_pool` | String(150) | Yes | `'instance_type:az'` of top alternative |
| `best_saving_pct` | Float | Yes | Savings % vs current pool |
| `coverage_status` | String(20) | Yes | `COVERED` (≥3), `AT_RISK` (1-2), `STRANDED` (0), `IMMOVABLE` |
| `computed_at` | DateTime | No | When this row was last computed |

**Index**: `idx_nac_cluster_node (cluster_id, node_name)`

#### `cluster_baselines` Full Column Schema (code-verified 2026-03-23)

| Column | Type | Nullable | Purpose |
|---|---|---|---|
| `cluster_id` | String(36) PK FK→clusters | — | Primary key + FK |
| `primary_node_type` | String(50) | Yes | Most common instance type in cluster |
| `primary_az` | String(50) | Yes | Primary availability zone |
| `baseline_monthly_cost` | Float | Yes | Monthly cost at baseline snapshot (USD) |
| `baseline_spot_count` | Integer | Yes | Spot node count at snapshot |
| `baseline_od_count` | Integer | Yes | On-demand node count at snapshot |
| `computed_at` | DateTime | No | When baseline was first computed |
| `updated_at` | DateTime | No | Last update timestamp |

**Known operator gap — missing `cluster_baselines` rows**: There is no admin API endpoint or automated backfill task to create `ClusterBaseline` rows for clusters onboarded before the table was introduced. Clusters without a baseline row permanently fall back to Redis on-demand prices in `SavingsCalculator`, producing drift-affected savings numbers. Operators must identify and fix affected clusters manually:
```sql
-- Identify clusters without a baseline row:
SELECT id FROM clusters WHERE id NOT IN (SELECT cluster_id FROM cluster_baselines);
```
To create a baseline row, call the `compute_baseline()` method of `savings_calculator.py` or insert directly into `cluster_baselines`. No automated migration path exists as of 2026-03-24.

#### `node_templates` / `node_template_versions` / `cluster_template_mappings` Schema

**`node_templates`**: `id (UUID PK)`, `name (String 255)`, `scope (Enum: GLOBAL/CLUSTER)`, `created_by`, `created_at`

**`node_template_versions`**: `id (UUID PK)`, `template_id (FK→node_templates)`, `version_number (Integer)`, `status (Enum: DRAFT/ACTIVE/ARCHIVED)`, `constraints_json (JSON)` — immutable constraint envelope (allowed families, architectures, AZ constraints, vCPU/memory bounds)

**`cluster_template_mappings`**: `id (UUID PK)`, `cluster_id (FK→clusters)`, `template_id (FK→node_templates)`, `version_id (FK→node_template_versions)`, `is_default (Boolean)`, `assigned_at` — unique constraint on `(cluster_id, is_default)` ensures each cluster has exactly one active default template

**Note**: The `NodeTemplate` Python dataclass in `pool_ranking_service.py` (with `source_od_price: Optional[float]`) is a runtime-only filter envelope passed through the ranking pipeline — it is **not** the `node_templates` DB model.

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
| `ec2:RunInstances` (DryRun) | Client | Spot capacity validation (`DryRun=True` with `InstanceMarketOptions.MarketType=spot`) |
| `ec2:DescribeInstanceAttribute` | Client | Copy user-data for spot launch |
| `ec2:DescribeSubnets` | Client | AZ-aware subnet selection |
| `eks:DescribeCluster` | Client | Cluster validation |
| `autoscaling:DescribeAutoScalingGroups` | Client | ASG discovery |
| `autoscaling:SuspendProcesses/ResumeProcesses` | Client | ASG freeze during detach-not-decrement window (2-3s only) |
| `autoscaling:DetachInstances` | Client | Detach instance without decrementing DesiredCapacity (Mode 1 replacement path) |
| `autoscaling:UpdateAutoScalingGroup` | Client | Hibernation nuclear path only |
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
- Problem: AWS omits `InstanceLifecycle` for some Karpenter spot nodes → appears as OD
- Solution: Redis counter `rc3:sync_od_streak:{aws_iid}` (10-min TTL, keyed on EC2 instance ID — P-M3 fix: was 5 min / 300s; doubled to eliminate Celery beat jitter boundary expiry between observation 2 and 3)
- Requires 3 consecutive OD observations before allowing SPOT→OD downgrade
- Confirmed SPOT reading immediately resets counter
- Key is written by `auto_rebalancer.py` (not discovery.py). Read by `auto_rebalancer.py` and the `/clusters/{id}/nodes/{node_id}/status` debug endpoint.

**Spot Assertion Guard** (before RC3 logic, discovery.py):
- Problem: Newly-launched spot instances have AWS API propagation delay (~10–30s) for `InstanceLifecycle` field; discovery worker defaults to 'on-demand' when field absent → RC3 streak can reach 3 within 15 min → permanent OD downgrade
- Solution: `auto_rebalancer.py` sets `spot:asserted_spot:{instance_id}` (TTL=300s, 5 min) immediately after pre-registering a new spot instance. Discovery worker checks this key before RC3 logic; if present, overrides real_lifecycle to SPOT to prevent false OD classification during the AWS propagation window.
- Root cause of c6a.large OD display bug: discovery defaulted lifecycle to OD for newly-launched spots, RC3 streak reached threshold within one poll cycle.

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

### 2.6 Alembic Migration Chain (verified 2026-03-23)

Current HEAD: `20260323_launch_outcomes`

```
20260323_add_launch_outcomes_reputation_constraints  ← HEAD (launch_outcomes table, state columns, unique constraints)
  ↑
20260320_add_current_state_to_rebalancing_actions    (current_state column + index)
  ↑
20260320_add_savings_columns_to_rebalancing_actions  (actual_instance_type, actual_az, actual_spot_price_hr, etc.)
  ↑
20260320_add_instance_cluster_state_index            (3 new indexes on instances table)
  ↑
20260320_add_node_alternative_cache_and_cluster_baselines
  ↑
20260320_add_realized_savings_to_rebalancing_actions
  ↑
20260316_add_spot_join_timeout
  ↑
20260316_add_check_interval
  ↑
20260316_add_autoscaler_settings
  ↑
20260316_add_ascp_auto_scaler
  ↑
20260314_add_launched_by_to_instances
  ↑
20260311_add_max_family_diversification_cap_pct
  ↑
20260311_add_force_delete_node_action
  ↑
20260310_add_stateful_rightsizing_toggle
  ↑
20260309_cleanup_volume_tables   (previous stable HEAD)
```

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

The rebalancer loads `global_pool_rankings:{region}` from Redis — the ML pipeline produces this list ranked by `EV = savings × (1 - risk)`. On top of this ranked list the rebalancer applies filters:
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

**Handling nodes that exceed risk ceiling:**
- If risk > `risk_ceiling_percent` but no better EV candidate exists → widen search by `risk_savings_tradeoff_pct`, pick lowest risk candidate
- If still nothing → fall back to OD of original type (for originally-OD nodes). For always-spot nodes → no action.

**EV formula asymmetry note**: The `candidate_ev > current_ev` comparison is NOT symmetric. `candidate_ev` is computed via `evaluate_candidate_ev()` (full 6-term model including reputation multiplier, DryRun weight, pool age penalty, and synergy bonus). `current_ev` is computed via `compute_expected_value()` (simplified 2-term model: `savings × (1 - risk)`). The two-sided asymmetry means candidate pools are evaluated more rigorously than the current pool — this intentionally creates a small bias toward keeping existing nodes stable (switching requires a higher-quality candidate to pass Gate 1). See `auto_rebalancer.py` for the asymmetric call sites.

---

#### Execution Flow (Gate 1 Passes)

**Step 1 — DryRun capacity check:**
```
ec2.run_instances(DryRun=True, InstanceMarketOptions={MarketType: spot}, instance_type=target, az=target_az)
  AMI sourced from: describe_images (cached 24h in Redis as dry_run:ami:{region})
→ DryRunOperation error: capacity confirmed → proceed
→ InsufficientInstanceCapacity: no spot capacity → try next candidate
→ Other ClientError: conservative fail → try next candidate
→ AMI lookup failure: fall back to describe_instance_type_offerings()
→ All exhausted (max_instance_type_attempts=6): mark failed, set pool cooldown, exit
```

### Dry Run — Fail-Safe Capacity Validation

*   **Method**: `ec2.run_instances(DryRun=True)` with `InstanceMarketOptions.MarketType=spot` — confirms actual spot capacity (not just AZ offering). AMI cached 24h per region (`dry_run:ami:{region}`).
*   **TTL**: `DRY_RUN_PASS_TTL = 480s` (8 min, Issue 3b: was 600s — reduced so refresher fires before TTL expires); `DRY_RUN_FAIL_TTL = 300s` (5 min). `DRY_RUN_CACHE_TTL` is a backward-compat alias for PASS_TTL.
*   **Fail-Safe Policy**: On any capacity ambiguity or API failure, the engine returns **False** (conservative safety) and triggers a 6-hour pool blacklist.
*   **Insufficient Capacity**: Triggers `report_launch_failure()` (6h blacklist) AND immediately calls `invalidate_dry_run_cache(instance_type, az, redis)` to write "fail" to `dry_run:{type}:{az}` in real time — no waiting for the 5-min refresher cycle.
*   **Exported function**: `invalidate_dry_run_cache(instance_type, az, redis, mark_failed=True)` — called by `auto_rebalancer.py` whenever `InsufficientInstanceCapacity` is caught at actual launch time.

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
→ Pre-register new instance in DB
→ Set spot:asserted_spot:{new_instance_id} (300s TTL)
    Prevents discovery worker from OD-downgrading this node during AWS API propagation delay
→ Wait for node to join K8s as Ready (300s timeout)
→ Timeout → terminate orphan, rollback, set cooldown
```

**Step 3 — Cordon + Drain old node:**
```
CORDON: PATCH /api/v1/nodes/{old_node} → spec.unschedulable=true

DRAIN:  For each pod on old node:
          Skip: DaemonSet pods
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

**Step 5 — Terminate old node (termination_mode="replacement"):**

*With Karpenter:*
```
ec2.terminate_instances(old_instance_id)
No ASG interaction at all. ✅
```

*Without Karpenter (ASG path — tight 2-3 second window only):*
```
with redis.lock('asg:suspend_lock:{asg_name}', timeout=30):
    autoscaling.suspend_processes(['Launch'])
    autoscaling.detach_instances(
        old_instance_id,
        ShouldDecrementDesiredCapacity=False  ← never True in Mode 1
    )
    ec2.terminate_instances(old_instance_id)
    autoscaling.resume_processes(['Launch'])

ASG DesiredCapacity unchanged before, during, after ✅
```

**Step 6 — Post-action cleanup:**
```
Mark RebalancingAction COMPLETED
Set per-instance cooldown: spot:rebalanced:instance:{id} (24h TTL)
Set cluster cooldown: spot:cooldown:cluster:{id} (60min TTL)
Set post-launch cooldown: spot:post_launch_cooldown:{new_ec2_id} (60s TTL)
  → S2S loop skips this node for 60s after successful launch
If actual_type ≠ original target type (fallback launch):
  Set S2S suppression: spot:s2s_suppressed:{new_ec2_id} (180s TTL)
  → S2S loop skips this node for 180s (2× 90s stabilization window)
Recalculate realized savings: calculate_real_savings.delay()
Record pool reputation: PoolReputationService.record_launch_outcome(outcome='success')
```

**Step 6 (on failure):**
```
Mark RebalancingAction FAILED
Set backoff: rebalance_failures:{instance_id} with exponential backoff (5min → 1hr)
Report to DecisionEngineService.report_launch_failure()
Record pool reputation: PoolReputationService.record_launch_outcome(outcome='failed')

Issue 14 — Event-driven pool ranking refresh (debounced):
  If spot:launch_blocked:... was just set (no-join timeout path):
    Check ranking_refresh_pending:{region} (60s debounce key)
    If absent: setex ranking_refresh_pending 60s; dispatch build_global_pool_cache.apply_async(countdown=5)
    → Ensures ranking cache reflects updated blacklist without waiting for hourly rebuild
```

**P-C3 — ASG suspend flag committed before exception zone**:
After `suspend_asg_processes()` succeeds, the action's `action_metadata = {'asg_suspended': True, 'asg_name_used': _asg_name}` is committed to DB **immediately** — before any downstream code that could throw. The exception handler reads this flag to decide whether to call `resume_asg_processes()`. Without this early commit, a crash between suspension and the later write left the ASG permanently frozen (no DB record to trigger resume).

**P-C2 — Stale action expiry now cleans orphan EC2**:
When a `RebalancingAction` times out (stuck `in_progress`/`waiting_agent` >45 min), the expiry loop now checks `action_metadata['replacement_spot_instance_id']`. If set, `_do_rollback_terminate_orphan_spot()` is called to terminate the orphan EC2. Without this, each timed-out action left a running spot node with no DB record, causing the cluster to grow by 1 per occurrence.

---

#### DaemonSet Pods — Why Skipped During Drain

DaemonSet pods are skipped during drain for three reasons:
1. They tolerate `node.kubernetes.io/unschedulable` — evicting them causes immediate rescheduling onto the same cordoned node, creating an infinite eviction loop
2. They are infrastructure (kube-proxy, aws-node, spot-agent, fluentd), not workload — evicting them breaks node networking and monitoring
3. They self-manage — when the node terminates, the DaemonSet controller stops scheduling there. When the new node joins, it automatically schedules a fresh pod. No intervention needed.

---

#### Last-Node Safety

The safety gate `Never drain the last running node` checks `running_node_count == 1` — it counts **all running nodes regardless of lifecycle type**. In the normal replacement flow this gate effectively never fires because the replacement node is always launched (Step 2) before the drain (Step 3) — by the time drain executes, `running_node_count` is already `n + 1`.

**P-H4 — Last-node guard launch now registers in DB**:
When the last-node guard fires in the non-Karpenter path (~line 3840), the emergency replacement spot launch now: (1) creates an `Instance` DB record (`lifecycle=SPOT, state='pending', launched_by='platform'`) and (2) sets `spot:asserted_spot:{_new_spot_id}` (TTL=300s) in Redis. Without this registration, `scan_orphans()` would terminate the newly-launched node as an unregistered orphan, and the discovery worker would misclassify it as OD due to AWS `InstanceLifecycle` propagation delay.

**When does it actually fire?** Only in a catastrophic simultaneous multi-node failure. The three realistic scenarios:

```
Scenario A — Single-node cluster:
  Cluster has 1 node total (OD)
  Optimizer launches replacement spot node → now 2 nodes
  Drain old node → running_node_count = 2 → gate does NOT fire
  Terminate old node → back to 1 node (spot)
  Gate never fires even here.

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
```

---

#### Realized Savings Calculation (Code-Verified)

From `savings_calculator.py`:
```
realized_savings = SUM( MAX(0, od_price - spot_price) )  for each running SPOT instance
                   where spot-optimizer/launched-by=platform
```
- `od_price` = on-demand price from Redis `pricing:ec2:{region}:{type}` (via `pricing_helper.get_ec2_price()`); falls back to `action.source_od_price_hr` from the matching RebalancingAction row
- `spot_price` = live spot price from Redis `pricing:spot:{region}:{type}:{az or 'any'}` (via `pricing_helper.get_spot_price()`)
- Only running SPOT instances tagged with `spot-optimizer/launched-by=platform` are summed
- Note: `pricing:ec2:` / `pricing:spot:` keys are written by `pricing_helper.py`. The separate market-view pipeline uses `ondemand_price:{region}:{type}` / `spot_price:{region}:{az}:{type}` keys (written by `aws_pricing_service.py` / `_refresh_regional_pricing`). These are two distinct subsystems.
- Result stored as `Cluster.realized_savings_monthly` in DB
- Recalculated after every successful rebalance (`calculate_real_savings.delay()`) and periodically by Celery beat

---

#### Settings

| Setting | Table | Default | Description |
|---|---|---|---|
| `auto_rebalance_enabled` | `cluster_optimization_settings` | `False` | Master toggle |
| `manual_approval_required` | `cluster_optimization_settings` | `False` | Require user approval per action — see Approval Workflow below |
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

#### Approval Workflow (`manual_approval_required=True`)

When `manual_approval_required=True`, the rebalancer creates the action with `status=pending_approval` instead of `in_progress` and halts until a human acts.

**State flow:**
```
pending_approval
  → (POST /rebalancing-actions/{id}/approve) → in_progress → completed / failed
  → (POST /rebalancing-actions/{id}/deny)    → failed (with deny reason)
  → (approval_cleanup every 5 min)           → EXPIRED (after approval_expiry_hours, default 24h)
```

- No auto-approve timeout — actions stay `pending_approval` until explicitly approved, denied, or expired by the cleanup worker
- `AutoRebalanceAuditModal.jsx` and `AutoRebalanceAuditCard.jsx` display pending items
- Stateful rightsizing always requires approval regardless of this setting

---

### 3.2 Auto Rightsizing Only (`auto_rightsizing_enabled=True`, `auto_rebalance_enabled=False`)

**What this mode owns:**
- How much CPU/memory each pod **requests**
- Nothing else — no node type decisions, no node count decisions, no pool selection

**Karpenter is required.** If not installed, mode is fully disabled.

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

**Gate 1:** classification is OVERSIZED or UNDERSIZED → PASS else FAIL (right_sized)

**Gate 2:** delta between current_request and recommended_request > 20% AND controller not on resize_cooldown → PASS else FAIL (delta_too_small / resize_cooldown_active)

---

#### Step 5 — Execution

**Stateless controllers:** `PATCH_CONTAINER_RESOURCES` AgentAction → K8s rolling update.

**Stateful controllers:** Recommendation stored in `rightsizing_proposals`, displayed in UI. No automatic execution — manual approval required always.

---

#### Step 6 — What Karpenter Does (Standard Operation)

After `PATCH_CONTAINER_RESOURCES`, Karpenter observes changed pod demands and naturally provisions or consolidates nodes. The platform makes no further API calls.

---

#### Step 7 — ASG Behavior

We do not touch nodes, pools, or ASG directly in Mode 2. Everything below is Karpenter's standard behavior after we patch pod requests.

```
rightsizing_target="spot":
  Spot nodes are Karpenter-managed
  After pod requests shrink → Karpenter consolidation fires (consolidateAfter: 30s)
  Empty nodes terminated by Karpenter
  termination_mode="karpenter" — we do not call any termination API ourselves ✅

rightsizing_target="on_demand":
  OD nodes are in ASG
  Karpenter evicts pods → node empties
  Platform detects empty OD node:
    termination_mode="scaledown"
    ShouldDecrementDesiredCapacity=True ← correct and intentional here only
    ASG DesiredCapacity decrements ✅
```

---

#### Step 8 — Resize Guard (2 Hours Post-Execution)

```
CPU stress:      cpu_avg_10m > 85% sustained 10min → FAILED → revert
Pod restarts:    restart_rate > baseline × 2        → FAILED → revert
Memory pressure: >5 pressure events in 2h window   → FAILED → revert

Revert = re-patch requests back to original values (stateless only)
Stateful failures → alert only, manual rollback required
```

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

### 3.3 Both ON — Synergy Mode

**Karpenter is required.**

**Two independent gates** — each has its own acceptance criteria and rejection reasons logged separately. They do not interact with each other's scoring.

**Gate 1 — Rebalancing gate:**
```
PASS if ALL of:
  candidate_ev > current_ev + delta_threshold
  AND savings >= min_savings_percent
  AND risk < risk_ceiling_percent
  AND node not on cooldown
  AND candidate passes DryRun
```

**Gate 2 — Rightsizing gate:**
```
PASS if ALL of:
  classification is OVERSIZED or UNDERSIZED
  AND delta between current_request and recommended_request > 20%
  AND controller not on resize_cooldown
```

| Gate 1 | Gate 2 | Action | Node count | Termination method |
|---|---|---|---|---|
| PASS | PASS | Combined — resize pods AND switch pool | Same or reduces | Detach pattern or Karpenter consolidation |
| PASS | FAIL | Switch pool only, keep current pod sizes | Same | Detach + direct terminate |
| FAIL | PASS | Resize pods only, Karpenter provisions naturally | May reduce or increase | Karpenter handles entirely |
| FAIL | FAIL | No action | Same | None |

`ShouldDecrementDesiredCapacity=True` is **never used in synergy mode** — `rightsizing_target` is locked to `"spot"`.

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

- **Global pipeline** runs every **1 hour** via `build_global_pool_cache` Celery task (three scheduled instances: ap-south-1, us-east-1, ap-southeast-1)
- Processes all instance types × all AZs in the region
- **Per-cluster**: Not per-cluster — global cache `global_pool_rankings:{region}` shared by all clusters in the region

**Data flow**:
1. `MLFeatureService.engineer_features()` → 45-feature vector per pool
2. `classifier_6.onnx` → `risk_probability`
3. `regressor_6.onnx` → `predicted_savings`
4. `ml_score = savings × (1 - risk)` — EV used here for pool ranking only
5. Apply pool reputation multiplier from `PoolReputationService.bulk_get_multipliers()` (see Section 4.5)
6. **Tiered Spot Advisor filter** (5 passes, stops when `global_limit=1500` met):
   - Pass 0: max_rank=0 (<5% interruption — safest)
   - Pass 1: max_rank=1 (≤10%)
   - Pass 2: max_rank=2 (≤15%)
   - Pass 3: max_rank=3 (≤20%) — needed for COST_FIRST profiles (25% ceiling)
   - Pass 4: max_rank=4 (≤25%) — maximum ceiling, covers all profile types
   **Note**: All 5 passes run at global tier so COST_FIRST per-cluster filters always find 15-25% pools.
   **Absent data fallback**: When Spot Advisor data is absent for a pool (no Redis entry, no hardcoded rate), `spot_advisor_rank` is set to **rank=4** (worst-case, ≤25%) — not rank=1 (conservative). This ensures unknown families sort last in all passes rather than appearing deceptively safe.
7. Store top 1500 pools per region in Redis: `global_pool_rankings:{region}` (65-min TTL)

**Input data from**: Redis (spot prices, on-demand prices, family baselines, spot advisor data)
**Output data to**: Redis: `global_pool_rankings:{region}` → consumed by Decision Engine, Auto-Rebalancer

### 4.4 ML Circuit Breaker

If ONNX inference fails 3+ times in 10 minutes:
- Redis: `ascpai:ml_fail_count` (INCR, 10-min TTL)
- Redis: `ascpai:ml_degraded` (10-min TTL)
- Fallback: heuristic scoring `savings × (1 - advisor_risk)` via `_fallback_scoring()`

**Additional safeguard**: If `_step7_ml_scoring` returns 0 pools for a non-empty candidate list (e.g., ONNX rejects all via risk threshold), `_score_candidates` activates `_fallback_scoring` rather than returning an empty list. This prevents caching an empty result.

**Non-empty cache guard**: `_get_or_compute_global_rankings` only writes to Redis if the computed pool list is non-empty — if the pipeline returns 0 pools, the existing cache key is left intact rather than being overwritten with `[]`.

### 4.5 Pool Reputation Integration (Stage 5.3)

**Source**: `backend/services/pool_ranking_service.py` (in `_step7_ml_scoring`)

Before the per-pool scoring loop, the pipeline batch-fetches reputation multipliers for all candidate pools in a single `mget` call:

```python
_rep_svc = PoolReputationService(self.db, self.redis)
_pool_keys = [f"{p.instance_type}:{p.az}" for p in pools]
_reputation_mults = _rep_svc.bulk_get_multipliers(_pool_keys)
```

Inside the loop, the multiplier is applied to `final_score`:
```python
_rep_mult = _reputation_mults.get(f"{pool.instance_type}:{pool.az}", 1.00)
if _rep_mult != 1.00:
    final_score = round(final_score * _rep_mult, 6)
```

**Reputation multiplier tiers** (from `pool_reputation_service.py`):

| Condition | Multiplier | Meaning |
|---|---|---|
| success_rate ≥ 0.95 AND avg_uptime > 168h | 1.10 | Excellent — boost score |
| success_rate ≥ 0.85 | 1.05 | Good |
| success_rate ≥ 0.70 | 0.95 | Below-average — small penalty |
| success_rate < 0.70 | 0.80 | Poor — significant penalty |
| No data yet (< 3 samples) | 1.00 | Neutral |

Redis key: `pool_reputation:{pool_key}`, TTL 3600s. Rolling 30-day window, max 500 rows.

### predicted_savings — Two Meanings, No Aliasing

ScoredPool.predicted_savings: ONNX regressor output (0–1). Used by S2S logic. Never modified.
PoolRankingResponse.predicted_savings: (OD - spot) / OD. Computed fresh at serialization.
Not read from ScoredPool — fresh local computation in ascpai_routes.py:263.

**Critical invariant**: `ScoredPool.predicted_savings` MUST NOT be mutated after ONNX inference. The S2S (Spot-to-Spot) tradeoff logic in `auto_rebalancer.py` compares `current_pool.predicted_savings` against `candidate_pool.predicted_savings` to decide if switching spot pools is beneficial. If any code path modifies `ScoredPool.predicted_savings` post-inference (e.g., applying a multiplier or overwriting it from an API response), the S2S comparison will silently use a different value than what the ONNX model predicted, causing incorrect pool selection decisions. The `PoolRankingResponse.predicted_savings` field (API-level, fresh computation) is a different object and safe to serialize as needed.

### 4.6 Market View Fallback Chain (Code-Verified)

When `GET /api/v2/clusters/{id}/market-view` is called and both Redis keys are cold:

1. Check `market_view_cache:{region}` → miss
2. Check `global_pool_rankings:{region}` → miss
3. **Inline compute trigger**: calls `_get_or_compute_global_rankings(region, 1500)` synchronously
4. If inline compute produces pools → writes to `global_pool_rankings:{region}` → returns data
5. **Frontend fallback**: if `getMarketView()` returns empty pools but `getRankings()` response has data, frontend `loadData()` uses rankings as the market view source:
   ```javascript
   if (mvPools.length === 0 && Array.isArray(rankings) && rankings.length > 0) {
       mvPools = rankings;
   }
   ```

### Market View vs Generic Rankings — Two Separate Surfaces

POST /api/v1/ascpai/pools/rankings → PoolRankings.jsx (ASCP.AI page)
  Fleet-wide rankings, no source node context, m5.large neutral baseline

GET /api/v1/ascpai/clusters/{id}/market-view → PoolRankings.jsx Market View tab
  Per-cluster rankings, filtered by source node vCPU/memory/arch/OD price ceiling

GET /api/v1/ascpai/clusters/{id}/nodes/{node_id}/status → debug endpoint (Task 13)
  Returns per-node lifecycle, active cooldowns, spot_assertion TTL, S2S suppression,
  and RC3 OD streak count. Useful for diagnosing lifecycle misclassification without
  needing Redis CLI access. Response fields: instance_id, instance_type, lifecycle, az,
  state, spot_assertion (bool), cooldowns {rebalanced, post_launch, spot_assertion,
  rc3_od_streak}, suppression {s2s}.

ClusterDetails.jsx tabs: Overview / Optimization Settings / Node Template / Activity Log
  No Market View tab in cluster detail — market view is on ASCP.AI page only.

### 4.7 Market View Known Bugs — Root Cause & Fix (2026-03-24)

Three bugs caused the Market View to show only `ap-south-1a` with uniform ~70% savings:

| Bug | Root Cause | File | Fix |
|---|---|---|---|
| Spot price parse failure | `_refresh_regional_pricing()` stored prices as plain string `str(price)`; `cache_builder` does `json.loads(raw).get('price')` → AttributeError on float → all pools silently dropped → spot_advisor fallback triggers | `aws_pricing_service.py:404` | Store as JSON: `json.dumps({"price": str(price), "timestamp": ...})` |
| OD key mismatch → uniform 70% | `get_ondemand_price()` wrote `od_price:{region}:{type}`; `_lookup_od_price()` reads `ondemand_price:{region}:{type}` → always 0 → `_estimate_od_price()` (us-east-1 calibrated) → estimated OD ≈ 3× actual spot → ~70% for all pools | `aws_pricing_service.py:235`, `cache_builder.py:131` | Dual write: both `od_price:` and `ondemand_price:` keys; `_lookup_od_price()` tries both |
| Spot_advisor fallback hardcoded 70% | Fallback path (no spot_price keys) used `spot_est = od_est * 0.30` — uniform 70% for all types | `cache_builder.py:306` | Use `savings_percentage` from `spot_advisor:{region}:{type}:Linux` Redis key |
| Missing task implementations | `ingest_spot_prices` and `refresh_ondemand` tasks referenced in `app.py` beat schedule but never registered → Celery "unregistered task" errors every 10 min / 12h | `pricing_worker.py` | Implemented both tasks as proper Celery task functions |

**Scenario C (confirmed root cause for single-AZ + uniform 70%)**:
1. `spot_price:*` keys exist (primary path runs) but stored as plain string not JSON
2. `json.loads` → float → `.get()` → AttributeError → ALL pools dropped from primary path
3. Falls to spot_advisor fallback (enumerates all 3 AZs from `_REGION_AZS`)
4. `_lookup_od_price` fails (key prefix mismatch) → `_estimate_od_price()` → uniform `od * 0.30` = 70%

---

## 5) Decision Engine

**Source**: `backend/core/decision_engine.py`

### 5.1 Purpose

Evaluates whether to switch a node from its current pool to a better spot pool. Runs as part of `control_plane_loop.py` (every 5 min) for proactive optimization, and is also called by `reconciliation_worker.py` for per-node coverage classification.

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

### 5.3 15-Step Control Plane Pipeline

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
| 13 | Delta threshold check (best_ev - current_ev ≥ profile.delta_threshold) | Config |
| 14 | APPROVED — select best candidate | — |

### 5.4 `rank_for_node()` — Per-Node Alternative Ranking Pipeline

Used by reconciliation worker and market-view to find alternative pools for a specific node. Steps with size/architecture constraints applied per-node:

| Step | Logic |
|---|---|
| 1 | Load all pools from `global_pool_rankings:{region}` → `all_pools` |
| 2 | Size filter: `vcpu >= min_vcpu_required` AND `memory_gb >= min_memory_required` → `pools` |
| 3 | Architecture filter: exclude pools not matching `required_arch` |
| 4 | Blacklist filter: exclude pools in `risky_pools:{region}` |
| 5 | Price gate: exclude pools where `spot_price >= source_od_price` |
| 6 | Apply soft penalties (recent failure count) |
| 7 | Sort by interruption rate ascending |
| **Step 8** | `_relax_with_tier_expansion(pools, current_risk_tier)` — uses **size-filtered `pools`** (not `all_pools`) — ensures min_memory constraint is respected during tier relaxation |
| **Step 9** | If `gated` is still empty after Step 8 AND `instance_type` + `az` are known: call `_get_same_type_az_alternatives()` — scans Redis `spot_price:{region}:*:{instance_type}` keys for the same instance type in other AZs. Returns pools matching the exact type with valid spot price in other AZs. |

**`_derive_specs_heuristic(instance_type)`**: Returns `(vcpu, memory_gb, architecture)` for common instance types using a hardcoded lookup + size-class-based derivation. Used when `instance_catalog` table returns no entry for a given type.

**`resource_profile` in reconciliation worker** (`reconciliation_worker.py:_compute_cluster_coverage`):
Each node's `node_info` dict now includes a `resource_profile` key so `rank_for_node` applies correct size constraints:
```python
node_info = {
    'instance_type': inst.instance_type,
    'az': inst.az,
    'spot_price': inst.price or 0.0,
    'risk_tier': 2,
    'architecture': _arch,
    'resource_profile': {
        'min_vcpu_required': _vcpu,
        'min_memory_required': _mem,
        'architecture': _arch or 'amd64',
    },
}
```

### 5.5 Validation

- Rejection counters tracked in Redis: `spot:rejection_counters:{cluster_id}` (24h TTL, hash)
- Each step logs reason if rejected → observable via `ObservabilityLogger`
- Decision audit: Redis key `obs:decisions:{cluster_id}` (last 100 decisions, 24h TTL)

### 5.6 Optimization Profiles

| Profile | `risk_ceiling` | `delta_threshold` | Meaning |
|---|---|---|---|
| `COST_FIRST` | 0.25 (25%) | 0.02 (2%) | Accept higher risk, switch on tiny improvements |
| `BALANCED` | 0.20 (20%) | 0.03 (3%) | Moderate risk, moderate improvement required |
| `NO_DOWNTIME_FIRST` | 0.10 (10%) | 0.04 (4%) | Very low risk, significant improvement required |

---

## 6) Pool Reputation System

**Sources**: `backend/models/launch_outcome.py`, `backend/services/pool_reputation_service.py`

### 6.1 Purpose

Tracks historical launch outcomes per spot pool and computes a reputation multiplier (0.80–1.10) that adjusts ML scores in Stage 5.3 of the pool ranking pipeline. A pool with a consistently high success rate and long average uptime gets a score boost; a pool with frequent failures gets penalized.

### 6.2 LaunchOutcome Model

One row per `RunInstances` or `CreateFleet` call. See full schema in Section 2.3.

**Outcome values**:
- `'success'` — instance launched and joined cluster
- `'failed'` — RunInstances/CreateFleet returned capacity error or similar
- `'interrupted'` — spot interruption notice received while running

### 6.3 PoolReputationService

**File**: `backend/services/pool_reputation_service.py`

**Public methods**:

| Method | Signature | Purpose |
|---|---|---|
| `record_launch_outcome` | `(pool_key, cluster_id, instance_type, az, region, outcome, actual_spot_price_hr=None, uptime_hours=None, launched_at=None, resolved_at=None, failure_reason=None, rebalancing_action_id=None) → LaunchOutcome` | Persist row + immediately refresh Redis reputation key |
| `update_pool_reputation` | `(pool_key) → dict` | Recompute from DB (30-day rolling window, max 500 rows) and write to Redis |
| `get_reputation_multiplier` | `(pool_key) → float` | Return cached multiplier; defaults to 1.00 on miss |
| `get_reputation` | `(pool_key) → dict` | Return full reputation dict from Redis |
| `bulk_get_multipliers` | `(pool_keys: list) → dict` | Batch-fetch via `mget` for all pools — used by ML pipeline |

**Redis key**: `pool_reputation:{pool_key}` (TTL 3600s)

**Value format**:
```json
{
  "pool_key": "m5.large:ap-south-1a",
  "success_rate": 0.97,
  "avg_uptime_hours": 210.5,
  "sample_count": 42,
  "reputation_mult": 1.10,
  "updated_at": "2026-03-23T10:00:00"
}
```

### 6.4 Wiring in auto_rebalancer.py

After every `waiting_agent` action resolves (whether completed or failed), the reputation is recorded:

```python
# auto_rebalancer.py — after _wa.status is determined
_rep_outcome = 'success' if _wa.status == 'completed' else 'failed'
_rep_svc.record_launch_outcome(
    pool_key=_rep_target_pool,
    cluster_id=_wa.cluster_id,
    instance_type=_rep_itype,
    az=_rep_az,
    region=cluster.region,
    outcome=_rep_outcome,
    actual_spot_price_hr=_wa.actual_spot_price_hr,
    launched_at=_wa.started_at,
    resolved_at=_wa.completed_at,
    failure_reason=_wa.error_message if _rep_outcome == 'failed' else None,
    rebalancing_action_id=_wa.id,
)
# Logs: "[auto_rebalancer] Pool reputation recorded: {pool_key} → {outcome}"
```

---

## 7) Execution Engine

**Source**: `backend/core/action_executor.py` (643 lines) + `backend/services/execution_controller.py` (359 lines)

### 7.1 6-Step Safe Node Replacement

| Step | Action | K8s/AWS API | Fallback |
|---|---|---|---|
| 1 | DryRun capacity check | `ec2:CreateFleet` (DryRun) | Skip if not available |
| 2 | Provision substitute node | `ec2:RunInstances` or Karpenter PATCH | Instance type cascade |
| 3 | Wait substitute Ready (300s timeout) | K8s: GET node, check Ready condition | Timeout → fail + rollback |
| 4 | Drain original node | K8s: cordon + evict pods (60s grace) | PDB violation → rollback |
| 5 | Verify workload health | K8s: check pod restarts, ready count | Unhealthy → rollback |
| 6 | Terminate original node | `ec2:TerminateInstances` (mode-dependent) | Failure → rollback |

### Two Execution Paths

execution_controller.py (SubstituteManager path):
  Launch → Wait → Cordon → Drain → Terminate
  Pre-warmed node ready before source is touched. Intentional.

auto_rebalancer.py Pillar 1 (main rebalancing):
  Provision → Wait → Cordon → Drain → Terminate
  NodePool patched before cordon for Karpenter; speculative launch before cordon
  for non-Karpenter (avoids stranded cordoned node if launch fails).

Both are provision-before-cordon by design.

### 7.2 Agent Interaction

Backend creates `AgentAction` records in DB → agent polls via HTTP or receives via WebSocket.

Action types (`agent_action.py`): `CORDON_NODE`, `UNCORDON_NODE`, `DRAIN_NODE`, `TERMINATE_NODE`, `PATCH_KARPENTER_NODEPOOL`, `LABEL_NODE`, `ANNOTATE_NODE`, `EVICT_POD`, `FORCE_DELETE_NODE`, `INSTALL_KARPENTER`, `UNINSTALL_KARPENTER`, `PATCH_CONTAINER_RESOURCES`, `UPDATE_DEPLOYMENT`

### 7.3 Control Plane Loop (8-Step Decision Cycle)

**Source**: `backend/workers/tasks/control_plane_loop.py`

Runs **every 5 minutes** per active cluster via `workers.control_plane.run_all_clusters_decision_cycle` Celery beat task.

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

### 7.4 Optimizer Coordinator (Phased Timing Strategy)

**Source**: `backend/workers/tasks/optimizer_coordinator_worker.py`

| Task | Frequency | Purpose |
|---|---|---|
| `pool_optimization_worker` | Every 30 min | Spot ML pool ranking — only changes pool, never size |
| `rightsizing_evaluation_worker` | Every 24h | Pod-level rightsizing — only proposes, does not execute |
| `evaluate_proposal_task` | Event-driven | Runs Gate 1 and Gate 2 independently |
| `execute_approved_proposal_task` | User/auto trigger | Executes approved rightsizing proposals |

### 7.5 Reconciliation Worker

**Source**: `backend/workers/tasks/reconciliation_worker.py`

Runs every 5 minutes. Two tasks:

**`reconciliation_worker`** — DB vs live EC2 state sync:
- For each active cluster: queries live EC2 instances (tagged to cluster) vs DB `instances` table
- Uses 2-miss Redis counter (`reconcile:miss:{instance_id}`, 10-min TTL) before marking terminated — prevents false positives from API transients
- Skips clusters with in-progress/waiting_agent RebalancingActions
- After reconciliation: calls `_compute_cluster_coverage()` to refresh coverage data

**`_compute_cluster_coverage()`** — per-node coverage scoring:
- For each running instance, calls `DecisionEngine.rank_for_node()` with full `resource_profile`
- Classifies each node: `COVERED` (≥3 alternatives), `AT_RISK` (1-2), `STRANDED` (0)
- Writes `cluster_coverage:{cluster_id}` to Redis (TTL 300s)

**`cleanup_terminated_instances`** — nightly beat (crontab 3:30 AM):
- Deletes Instance rows where `state='terminated'` AND `updated_at < now() - 30 days`
- Keeps recent terminated rows for audit/savings calculations

---

## 8) Karpenter

### 8.1 What it Does

Karpenter is a Kubernetes node autoscaler. The platform integrates with Karpenter to manage node pools based on ML-driven recommendations.

- **`karpenter_mode = None`**: Not installed → platform uses direct EC2 `RunInstances()`.
- **`karpenter_mode = "dry_run"`**: Insights only — recommendations shown but no EC2 changes.
- **`karpenter_mode = "auto"`**: Full autonomous management — platform patches NodePool CRDs.

---

### 8.2 Installation & Uninstallation

**Install** (`actuator.install_karpenter()` L782-868):
1. SQS queue: `KarpenterInterruptionQueue-{cluster_name}`
2. `helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter --version 1.0.8 --wait --timeout 5m`
3. IRSA: annotates ServiceAccount with `eks.amazonaws.com/role-arn`
4. Registers `KarpenterNodeRole` access entry for EKS cluster
5. Creates default `EC2NodeClass` (AL2023, `amiSelectorTerms: [{alias: al2023@latest}]`)
6. Creates default `NodePool` with `karpenter.sh/v1` API, allowing both `amd64` + `arm64`. Sets `consolidationPolicy: WhenUnderutilized`, `consolidateAfter: 30s`

**Uninstall** (`actuator.uninstall_karpenter()` L1289-1326):
1. `helm uninstall karpenter --namespace karpenter --wait --timeout 3m`
2. Delete `karpenter` namespace (best-effort)
3. Idempotent: release-not-found treated as success

**NodePool Patching** (`actuator.patch_karpenter_nodepool()` L699-780):
- Patches `spec.template.spec.requirements`
- Requirements: `karpenter.sh/capacity-type`, `node.kubernetes.io/instance-type`, optional `topology.kubernetes.io/zone` + `kubernetes.io/arch`
- 404 fallback: auto-creates NodePool by inferring cluster name from ConfigMap or node labels

Agent heartbeat includes Karpenter detection → sets Redis key: `spot:karpenter:installed:{cluster_id}`.

---

### 8.3 Karpenter-Specific Redis Keys

| Key | TTL | Purpose |
|---|---|---|
| `spot:karpenter:installed:{id}` | Variable | Detection flag |
| `spot:karpenter:nodepool_updated:{id}` | 30 min | NodePool refresh cooldown |
| `spot:karpenter:provision_requested:{id}` | 15 min | Last-node provision dedup |
| `spot:ondemand_fallback:{id}` | 12h | On-demand fallback flag |
| `spot:execution_failures:{id}` | 10 min | Karpenter circuit breaker |

---

### 8.4 Karpenter Fallback & SQS

**SQS Consumer** (`sqs_consumer.py` L29-284): Polls SQS interruption queues every 30s for Karpenter clusters.
- Supported events: `EC2 Spot Instance Interruption Warning`, `EC2 Instance State-change Notification` (stopping/stopped), `AWS Health Event` (spotInterruption/scheduledChange).
- On detection: calls `trigger_emergency_rebalancing()` → dispatches `emergency_rebalancer` Celery task.

**Fallback API** (`cluster_routes.py`, `/fallback`): Agent calls on interruption → backend switches NodePool to on-demand: Redis key `spot:ondemand_fallback:{id}` (12h TTL).

---

## 9) Emergency System

### 9.1 What Constitutes an Emergency

| Event | Source | Bypass |
|---|---|---|
| Spot termination notice (2-min warning) | IMDS via SpotPoller / SQS / EventBridge | Delta threshold, savings check, cluster cooldown, pool cooldown |
| EC2 rebalance recommendation | IMDS via SpotPoller | Proactive migration trigger |
| Instance state-change to stopping/stopped | SQS / EventBridge | Emergency rebalancing |
| AWS Health Event (spotInterruption) | SQS | Emergency rebalancing |

All emergency events trigger creation of an emergency action with `priority=10`.

---

### 9.2 Emergency Flow

**Source**: `backend/workers/tasks/emergency_rebalancer.py` + `termination_monitor.py`

**Step-by-step**:

1. **Detection**: SpotPoller (IMDS every 5s) or SQS consumer (every 30s)
2. **Notification**: Agent POSTs to `/api/v1/worker/spot-interruption`
3. **Backend processing** (`detect_termination_notice()`):
   - Create `TerminationEvent` record
   - Blacklist the affected pool: `SADD risky_pools:{region}` (12h TTL)
   - Update pool pressure in `risk_engine.py`
   - Override cluster cooldown via `CooldownController.override_for_emergency()`
   - Create emergency `RebalancingAction` with `priority=10`
4. **Action dispatch**: Backend pushes via WebSocket as `emergency_command` message
5. **Emergency rebalancing**:
   - **Standby-first path** (if `maintain_standby=True` and standby exists): UNCORDON standby → CORDON interrupted → DRAIN (grace_period=90, force=True) → TERMINATE → launch new standby async
   - **Normal emergency**: Creates `RebalancingAction` with `type="emergency"` and `priority=10`
   - **P-C1 fix (RebalancingAction fields)**: `RebalancingAction` is created with correct model fields: `trigger='emergency'`, `source_pool`, `target_pool`, `started_at`, `source_instance_id`, `action_metadata={"trigger_reason": reason}`. Invalid fields previously used (`id=generate_uuid()`, `source_instance_type`, `source_az`, `action_type`, `trigger_reason`, `created_at`) caused DB write failures — interrupted nodes were not cordoned or drained.
6. **Result reporting**: Agent reports outcome; action marked `COMPLETED` or `FAILED`
7. **2-hour cluster cooldown set**: After ANY emergency rebalancing path completes (standby failover, normal emergency, or Karpenter path), `key_cluster_cooldown(cluster_id)` is set with a 2-hour TTL. This matches `COOLDOWN_SUBSTITUTE_MIN = 120 min` and prevents a second rebalancing cycle from firing immediately after an emergency event on the same cluster.
8. **Event-driven pool ranking refresh (Issue 14)**: After `report_termination()`, if `ranking_refresh_pending:{region}` is absent, it is set (TTL=60s) and `build_global_pool_cache` Celery task is dispatched (countdown=5s). Deduplicates to 1 refresh per region per 60s.

---

### 9.3 Monitoring

- `TerminationEvent` records stored in DB for audit
- Redis key `spot:cluster_state:{id}` tracks cluster instability (used by circuit breaker)
- **Circuit breaker Redis keys** (per-cluster, 24h TTL): `cb:state:{cluster_id}`, `cb:rollbacks:{cluster_id}` (1h TTL), `cb:last_failure:{cluster_id}` (1h TTL), `cb:state_entered:{cluster_id}`
- Circuit breaker transitions (source: `backend/services/circuit_breaker.py`):
  - `NORMAL → CONSERVATIVE` after ≥2 rollbacks in 1 hour window
  - `CONSERVATIVE → HALT` after ≥3 rollbacks in 1 hour window from CONSERVATIVE state
  - `HALT → CONSERVATIVE` after 30 min no new failures
  - `CONSERVATIVE → NORMAL` after 2 hours in CONSERVATIVE state AND 30 min no new failures
- **Counter non-increment carve-outs**: Emergency actions (`is_emergency=True`, priority=10) and Mode 3 gate rejections (`is_gate_rejection=True`) do **not** increment the rollback counter — they are expected operational events, not signs of instability
- **Risk multiplier**: `NORMAL = 1.0`; `CONSERVATIVE = 1.3 × exp(-t/120min)` (exponential decay over time in state); `HALT = 2.0`
- Cross-cluster propagation: `InstabilityPropagator` updates pool pressure for all clusters sharing affected pool/AZ

---

### 9.4 Drain Grace Periods

From `emergency_rebalancer.py`:
- Emergency drain: `grace_period=90`, `force=True` — bypasses PDBs immediately
- 90 seconds is **hardcoded** — chosen based on AWS's 2-minute termination warning
- Any pod still running at T-90s is force-deleted with `grace_period=0`

---

### 9.5 Recovery Monitor — Key Behaviors (Bug Fixes)

**Source**: `backend/workers/tasks/recovery_monitor.py`

**`scan_orphans()` — P-M5 fix (Pass 1 guard)**:
Pass 1 (platform-creds EC2 scan for same-account clusters) now runs only when at least one cluster has `aws_role_arn IS NULL`. In all-cross-account deployments (all clusters use assumed roles), Pass 1 previously ran every 5 min against the platform account and found nothing — wasting EC2 API quota. Pass 2 (per-cluster assumed-role) still runs unconditionally.

**`detect_karpenter_stalls()` — P-C4 fix (cross-account creds)**:
For clusters with `aws_role_arn` set, this function now calls STS `assume_role` before creating the EC2 boto3 client. Previously it used platform credentials, so stall detection was blind to EC2 instances in customer AWS accounts — orphan EC2s were never terminated after Karpenter stalls in cross-account deployments. On assume_role failure, the cluster is skipped with a WARNING log.

**`_sync_instance_state_from_aws()` — P-M1 fix (node_count sync)**:
This function now updates `cluster.node_count = spot_count + od_count` in addition to `cluster.spot_count` and `cluster.on_demand_node_count`. Previously, `node_count` was only updated by the discovery worker (every 5 min), causing API consumers to see a stale node count during active rebalancing windows. With this fix, the cluster table is kept consistent in real time as instances are provisioned and terminated.

---

## 10) Rules

### 10.1 Safety Gates (All Rebalancing)

| Gate | Condition | Bypassed by Emergency? |
|---|---|---|
| Execution lock | Redis NX `lock:workers.auto_rebalancer` (300s) | Yes (lock cleared) |
| Daily limit | `max_rebalances_per_24h` (default 5, completed only) | Yes |
| One-at-a-time | Skip if PENDING/PICKED_UP AgentActions (auto-expire >15 min) | Yes (emergency jumps queue) |
| Last-node safety | Never drain the last running node | **No** |
| Cluster cooldown | `cooldown_override_minutes` (default 60 min) | Yes (force-cleared) |
| Per-instance cooldown | `spot:rebalanced:instance:{id}` (24h TTL) | Yes (force-cleared) |
| Architecture filter | Exclude candidates not matching allowed architectures | No (template may allow mixing) |
| Allocatable check | Reject smaller type if rightsizing OFF | No |
| Concurrency lock | `lock:rebalance_exec:{cluster_id}` (5 min) | Yes (cleared) |
| Stabilization lock | `CooldownController.check_stabilization_lock()` | Yes (cleared) |

---

### 10.2 Blacklisting

**Source**: `backend/services/blacklist_service.py` (423 lines)

**Tiered blacklist**:

| Trigger | TTL |
|---|---|
| DryRun capacity failure 1-2×/24h | 6 hours |
| DryRun capacity failure 3+×/24h | 12 hours |
| ML high risk (>0.45) | 24 hours |
| Termination event (ITN/rebalance-rec) | 15 minutes (0.25h) via `blacklist_pool_tiered()` |
| **Emergency rebalancer path** (any — standby failover, normal, or Karpenter) | **24 hours** via `key_blacklist_global()` — written in addition to the 15-min tiered blacklist from `report_termination()` |
| Launch failure 3+/24h (FAILURE_THRESHOLD=3) | 6 hours |
| Launch failure 5+/24h | 12 hours |
| Execution DryRun failure | No blacklist (penalty only) |

**Note on `LAUNCH_FAILURE_WINDOW_HOURS = 24`**: This constant (previously named `BLACKLIST_TTL_HOURS`) is the rolling window for counting launch failures via sorted-set expiry — it is NOT the blacklist duration itself. The blacklist TTL is determined by the failure count (6h or 12h above). The 24h window controls how long failure events stay in the `pool_failures:{pool_key}` sorted set.

**Storage**:
- Redis SET: `risky_pools:{region}` — all blacklisted pools in the region
- Redis KEY: `blacklist_failures:{instance_type}:{az}` — failure count (30-day expiry)
- Redis KEY: `risky_pool_meta:{instance_type}:{az}` — JSON metadata (12h TTL)
- Redis COUNTER: `ranking_version:{region}` — incremented on **every** blacklist event (both `blacklist_pool` and `blacklist_pool_tiered`). Downstream execution plans snapshot this version at creation time; mismatch before execution step triggers re-rank.

**Cascade protection**: If >70% of pools in a region are blacklisted, predictive blacklisting is suspended for 30 minutes. Deterministic blacklisting (actual interruptions) is **always** honored. Key: `spot:blacklist_suspended:{region}` (30 min TTL).

---

### 10.3 Cooldown Types

| Type | Redis Key | Default TTL | Emergency Bypass? |
|---|---|---|---|
| Cluster switch | `spot:cooldown:cluster:{id}` | 60 min | Yes (cleared) |
| Pool reuse | `spot:cooldown:pool:{pool_id}` | 120 min | Yes (cleared) |
| Pool switch | `spot:cooldown:action:pool_switch:{id}` | 30 min | Yes (cleared) |
| Resize | `spot:resize_cooldown:{controller_id}` | 360 min (6h) | Yes (cleared) |
| Stabilization lock | `spot:stabilization_lock:{id}` | 60s (1 min) — was 300s; Issue 1 fix. Issue 13: also persisted to `cluster_cooldown_states` DB table; re-hydrated on Redis miss | Yes (cleared) |
| Per-instance rebalance | `spot:rebalanced:instance:{id}` | 24h | Yes (cleared) |
| ASG suspend lock | `asg:suspend_lock:{asg_name}` | 30s | No (per-operation) |
| Stateful per-cluster | `spot:stateful:resize:cluster:{id}` | 48h | No (stateful never auto-executed) |
| Stateful per-instance | `spot:stateful:resize:instance:{id}` | 48h | No (stateful never auto-executed) |

---

## 11) Kubernetes Logic

### 11.1 Actions by Type

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

### 11.2 Drain Logic Details

`actuator.drain_node()` (L282-407):

1. Cordon the node first
2. List all pods on the node
3. **Skip**: DaemonSet pods (infinite eviction loop risk), Mirror pods (static, node-bound), Unmanaged pods unless `force=True`
4. For each remaining pod:
   - PDB violation AND `force=True` → force-delete with `grace_period_seconds=0`
   - PDB violation AND `force=False` → skip, add to `failed_evictions`
   - Normal: eviction with grace period
5. **Eviction retry**: HTTP 429 (PDB Too Many Requests) → retry 5× with 10s delay
6. **VolumeAttachment cleanup** (post-drain): detect + force-delete stuck attachments (timeout 30s)

**Grace period by caller:**

| Caller | grace_period | force | PDB behavior |
|---|---|---|---|
| Auto rebalancer (Mode 1) | 60s | False | Respected |
| Auto rebalancer (Mode 1, `respect_pdb_enabled=False`) | 60s | True | Force-deleted |
| Synergy mode (Mode 3) | 60s | False | Respected |
| Emergency rebalancer | 90s | True | Bypassed immediately |
| Spot interruption (IMDS) | 30s | True | Bypassed |

---

### 11.3 Node Termination — `termination_mode` Parameter

| `termination_mode` | When used | AWS call | DesiredCapacity |
|---|---|---|---|
| `"replacement"` | Mode 1 (all pool switches), Mode 3 same-count operations, emergency | Detach + direct terminate | **Unchanged** |
| `"karpenter"` | Mode 2 spot consolidation, Mode 3 spot consolidation | Karpenter terminates directly | **Not touched** |
| `"scaledown"` | Mode 2 OD consolidation only (intentional capacity reduction) | `ShouldDecrementDesiredCapacity=True` | **Decrements** |

**`termination_mode="replacement"` — detach-not-decrement pattern:**

```
Phase 3 — tight 2-3 second window only:
  with redis.lock('asg:suspend_lock:{asg_name}', timeout=30):
      autoscaling.suspend_processes(['Launch'])
      autoscaling.detach_instances(
          InstanceIds=[old_instance_id],
          ShouldDecrementDesiredCapacity=False  ← critical, never True
      )
      ec2.terminate_instances(InstanceIds=[old_instance_id])
      autoscaling.resume_processes(['Launch'])

Result:
  ASG DesiredCapacity unchanged ✅
  ASG sees desired=N, actual=N (replacement node already running) → launches nothing ✅
```

**With Karpenter:** `ec2.terminate_instances(old_instance_id)` — no ASG interaction at all.

---

### 11.4 PDB Enforcement

`check_pdb_violation()` (L103-128):
1. List all PDBs in the pod's namespace
2. For each PDB, check if `spec.selector.match_labels` matches all pod labels
3. If matched PDB has `status.disruptions_allowed < 1` → UNSAFE (return `True`)
4. **Fail-safe**: On any API error → return `False` (allow drain) and log the error

---

### 11.5 Force Delete Node

`actuator.force_delete_node()` (L254-280):
- Used when underlying EC2 instance is gone and node is stuck in `NotReady`
- If node already absent (404) → treated as success (idempotent)
- After deletion, patches all `Terminating` pods on the node to remove finalizers → prevents StatefulSet pods with PVCs from hanging indefinitely

---

### 11.6 Node Resolution

Multiple resolution strategies (fallback chain):

1. `payload.node_name` — direct from backend DB
2. `_find_node_by_instance_id(instance_id)` (L662-678) — matches `spec.providerID` containing `aws://{az}/{instance_id}`
3. `_find_node_name(instance_type, az)` (L680-697) — label-based: `node.kubernetes.io/instance-type` + `topology.kubernetes.io/zone`

---

## 12) Failure Handling

### 12.1 Failure by Phase

| Phase | Failure | Action | Recovery |
|---|---|---|---|
| **Phase 1** (spot launch) | All instance types exhausted | Action status → `failed` | Instance cooldown set, retry next cycle |
| **Phase 1** | Karpenter timeout | P-H1 fix: action FAILs when `_other_running > 0` but Karpenter timeout fires — previously proceeded to drain, permanently shrinking the cluster | Fail action; operator should check Karpenter NodeClaim status |
| **Phase 2** (CORDON) | K8s API error | Acquire stabilization lock → Uncordon + terminate orphan spot + resume ASG | Immediate backoff key written (min 60s); no retry window during rollback (P-H2, P-H3) |
| **Phase 2** (DRAIN) | PDB conflict | Acquire stabilization lock → Skip EC2 terminate, terminate orphan spot directly | Immediate backoff key written; prevents re-flap during rollback (P-H2, P-H3) |
| **Phase 2** (DRAIN) | Timeout | Same as PDB conflict | Same (P-H2, P-H3) |
| **Phase 2** (TERMINATE) | EC2 API error | Terminate orphan spot, report failure; retry blocked for 4h via `spot:term_failed:{id}` (P-M2 fix: was 90 min) | Manual intervention flagged |
| **Orphan cleanup** | DB record not found | Direct EC2 termination via `replacement_spot_instance_id` from metadata | — |
| **Stale action expiry** | `RebalancingAction` stuck `in_progress`/`waiting_agent` >45 min | Mark `failed`; P-C2 fix: if `action_metadata['replacement_spot_instance_id']` is set, call `_do_rollback_terminate_orphan_spot()` to clean up orphan EC2 | Prevents cluster from growing by 1 per timed-out action |
| **Pre-launch** | Previous orphan found | Verify AWS state → terminate if running/pending | Clean metadata of failed action |

---

### 12.2 Circuit Breaker

**Source**: `backend/services/circuit_breaker.py`
**Redis keys** (per-cluster, 24h TTL): `cb:state:{cluster_id}`, `cb:rollbacks:{cluster_id}` (1h TTL), `cb:last_failure:{cluster_id}` (1h TTL), `cb:state_entered:{cluster_id}`

| State | Trigger | Effect | Recovery |
|---|---|---|---|
| **NORMAL** | — | Full automation, risk multiplier = 1.0 | — |
| **NORMAL → CONSERVATIVE** | ≥2 rollbacks in 1h window | Risk multiplier: `1.3 × exp(-t/120min)` (exponential decay); actions still allowed | Time-based only — after 2h in CONSERVATIVE AND 30 min no failures → NORMAL |
| **CONSERVATIVE → HALT** | ≥3 rollbacks in 1h window while in CONSERVATIVE | **ALL automation blocked** (emergency actions still run); risk multiplier = 2.0 | After 30 min no new failures → CONSERVATIVE |
| **HALT → CONSERVATIVE** | 30 min no new failures | Automation resumes in CONSERVATIVE mode | — |
| **CONSERVATIVE → NORMAL** | 2h in CONSERVATIVE state AND 30 min no new failures | Full automation restored, risk multiplier = 1.0 | — |

**Counter non-increment carve-outs**: Emergency actions (`is_emergency=True`, priority=10) **and** Mode 3 gate rejections (`is_gate_rejection=True`) do **not** increment the rollback counter.

**Recovery is time-based only** — calling `record_success()` does not trigger immediate recovery; transitions happen via `check_and_auto_recover()` which evaluates time elapsed since last failure.

---

### 12.3 Resize Guard

`resize_guard_worker.py` monitors cluster health for **2 hours** after any rightsizing action:
- **CPU stress**: `cpu_avg_10m > 85%` sustained 10 min → FAILED → revert
- **Pod restart spike**: restart rate exceeds `baseline × 2` → FAILED → revert
- **Memory pressure**: >5 memory pressure events in 2h window → FAILED → revert

---

## 13) Additional Topics

### Nginx-Proxied Routes (No /api/v1 Prefix)

Some backend routes are served WITHOUT the `/api/v1` prefix, accessed directly via Nginx:

| Route | Backend File | Consumer | Notes |
|---|---|---|---|
| `GET /metrics/cluster/{cluster_id}/health-timeline` | `backend/api/metrics_routes.py` | `ClusterHealthTimeline.jsx` (on-mount) | Returns health event timeline; no `/api/v1` prefix |
| `GET /metrics/rejections/{clusterId}` | `backend/api/metrics_routes.py` | `metricAPI.getRejectionCounters()` | Decision engine rejection counters |

**Traceability note**: These routes do not appear in the standard `/api/v1/...` route tables. If the Nginx proxy configuration changes or `metrics_routes.py` is moved, consumers such as `ClusterHealthTimeline.jsx` will fail silently with no fallback.

---

### Security & RBAC

- **Agent auth**: Bearer token (`API_TOKEN`) set during installation
- **Action verification**: HMAC-SHA256 with `SECRET_KEY` on every action payload
- **Backend API**: Organization-scoped RBAC via `Role` + `Permission` models
- **Cross-account**: STS AssumeRole with ExternalId for customer AWS accounts
- **API key rotation**: `POST /clusters/{id}/agent/disconnect` generates new `secrets.token_urlsafe(32)` key

---

### Multi-tenancy

- Data isolated by `organization_id` → `account_id` → `cluster_id` hierarchy
- Each cluster has a unique `API_KEY` for agent authentication
- Redis keys include `cluster_id` to isolate data
- DB queries always filter by `cluster_id` (and often by `organization_id` via joined tables)

---

### High Availability & Scaling

- **Backend**: Gunicorn workers with configurable number of processes
- **Celery workers**: Separate containers for `celery-worker`, `celery-beat`, `celery-emergency`
- **Redis**: Single instance — a Redis restart would temporarily lose cooldowns, blacklists, and pool rankings; all rebuilt automatically by periodic tasks within minutes
- **Database**: PostgreSQL with JSONB columns for flexible metadata; RDS Multi-AZ for production
- **Emergency queue**: Dedicated worker ensures spot interruption handling is never blocked by long-running normal rebalancing tasks

---

### Cost Tracking & Reporting

- **SavingsCalculator** (`savings_calculator.py`):
  ```
  realized_savings = SUM( MAX(0, od_price - spot_price) )
                     for each running SPOT instance
                     where spot-optimizer/launched-by=platform
  ```
  - `od_price` from Redis `pricing:ec2:{region}:{type}` (via `pricing_helper.get_ec2_price()`); falls back to `action.source_od_price_hr` from the completed RebalancingAction
  - `spot_price` from Redis `pricing:spot:{region}:{type}:{az or 'any'}` (via `pricing_helper.get_spot_price()`)
  - Pre-existing spot instances without the `launched-by=platform` label are excluded
- **Daily aggregation**: `daily_cluster_stats` table stores per-cluster snapshots
- **Cluster.realized_savings_monthly**: Updated after every successful rebalance and recalculated periodically by Celery beat (every 30 min)

---

### Compliance & Auditing

**Audit Log Model** (`audit_log.py`):

| Column | Type | Purpose |
|---|---|---|
| `id` | String(36) PK | UUID |
| `timestamp` | DateTime(tz) | Millisecond-precision audit timestamp |
| `actor_id` | String(36) | User ID or `system` |
| `actor_name` | String(255) | Human-readable actor name |
| `event` | String(255) | Action performed |
| `resource` | String(255) | Resource affected |
| `resource_type` | Enum | `CLUSTER`, `INSTANCE`, `TEMPLATE`, `POLICY`, `HIBERNATION`, `USER`, `ACCOUNT` |
| `outcome` | Enum | `SUCCESS` or `FAILURE` |
| `ip_address` | String(45) | IPv4 or IPv6 |
| `user_agent` | String(512) | Request user agent |
| `diff_before` | JSONB | State before change |
| `diff_after` | JSONB | State after change |
| `checksum` | String(64) | SHA-256 tamper-evidence hash |

- **Immutable**: No `update()` method — updates prevented at application layer
- **Tamper detection**: SHA-256 checksum computed on insert by `audit_service.py`
- **Retention policy**: No automatic deletion; records persist indefinitely
- **Decision audit**: `ObservabilityLogger` stores last 100 decisions per cluster in Redis (`obs:decisions:{id}`, 24h TTL)
- **Execution history**: `rebalancing_actions` and `agent_actions` tables retain full action history

---

## Hibernation Engine

**File**: `backend/services/hibernation_service.py` | **Strategy execution**: `backend/hibernation_strategy/`

### Three Hibernation Strategies

| Strategy (`HibernationStrategy` enum) | Mechanism | Savings | Wake Time | Risk |
|---|---|---|---|---|
| `NAMESPACE_SLEEP` | Scales all Deployment/StatefulSet replicas to 0 via K8s PATCH | 80% | ~2 min | Low |
| `NUCLEAR` | Sets ASG `desired=0` + terminates all worker nodes | 70% | ~5 min | Medium |
| `SNAPSHOT_RESTORE` | Creates EBS volume snapshots for all node volumes, then executes NUCLEAR | 95% | ~15 min | High |

### Schedule Types

| Type | Matrix Format | Slot Count | Meaning of `1` |
|---|---|---|---|
| `WEEKLY` | 168-char binary string | 7 days × 24 h | Hibernating |
| `DAILY` | 24-char binary string | 24 h (tiled across 31 days for conflict detection) | Hibernating |
| `MONTHLY` | 744-char binary string | 31 days × 24 h | Hibernating |

### Conflict Detection

`_check_matrix_overlap()` expands all types to 744-slot monthly array before AND-comparing. Any overlap > 0 raises `ConflictError` — two schedules cannot hibernate the same cluster at overlapping times.

### Wake Staleness Thresholds

After a cluster wakes from hibernation, stale state is detected by elapsed time since last activity. Actual thresholds (from `hibernation_service.py`):

| Strategy | Staleness Threshold |
|---|---|
| `NUCLEAR` | 8 hours |
| `SNAPSHOT_RESTORE` | 8 hours |
| `NAMESPACE_SLEEP` | 24 hours |

NUCLEAR=8h: ASG state drifts (scale events/health checks) — 8h prevents stale ASG counts
SNAPSHOT_RESTORE=8h: EBS snapshot ages — 8h prevents restoring outdated state
NAMESPACE_SLEEP=24h: Only replica counts stored; 24h acceptable
Note: 8h is staleness of SAVED STATE used to plan wake, not the wake operation duration.

Clusters exceeding these thresholds trigger a full re-sync of cluster state before resuming optimization.

### Runtime Guards

- `cluster.is_hibernating = True` → Guard 0 in auto_rebalancer blocks ALL rebalancing for this cluster
- `cluster.hibernation_lock` — UUID lock preventing concurrent hibernation operations
- `cluster.hibernation_state (JSONB)` — tracks `{nodes_processed, total_nodes, strategy, schedule_name}`

---

## Substitute Manager

**File**: `backend/services/substitute_manager.py`

Maintains **pre-warmed running spot nodes** (uncordoned) for zero-downtime migration — distinct from standby nodes (which are cordoned spare nodes).

| State | Description |
|---|---|
| `IDLE` | No substitute. APScheduler checks every 5 min. |
| `PREWARMING` | EC2 launched, waiting for K8s join (up to 10 min). |
| `READY` | Fully joined, uncordoned, awaiting migration assignment. |
| `ACTIVE` | Being used as migration destination (HANDBACK_HOURS=6). |
| `RELEASING` | Migration complete, draining back to pool. |

Substitute is sized to the **largest current cluster node** (max vCPU × memory). Filters AZs with <10 available subnet IPs (Redis 60s cache).

> **ORM access path**: The toggle controlling whether a cluster maintains a standby substitute is `ClusterOptimizationSettings.maintain_standby`. Code accesses it via `cluster.optimization_settings.maintain_standby` (using the `optimization_settings` ORM relationship on the `Cluster` model). This is NOT `cluster.settings` JSONB — that attribute does not exist on the model.

---

## Cross-Cluster Instability Propagator

**File**: `backend/services/instability_propagator.py`

When a spot interruption fires, propagates the event to all clusters sharing the same pool. Prevents local noise from triggering global blacklists.

- **Systemic threshold**: `SYSTEMIC_CLUSTER_THRESHOLD = 3` — if ≥3 clusters affected by same pool → systemic escalation
- **Rolling window**: 30 min event counter per pool
- **Key TTL**: 2 h (all propagator Redis keys expire after 2h)
- **Redis keys written**: `propagator:pool_pressure:{region}:{az}:{itype}`, `propagator:az_pressure:{region}:{az}`, `propagator:events:{...}`, `propagator:affected_count:{...}`

---

## WorkloadInspector — Classification Algorithm

**File**: `backend/services/workload_inspector.py`

Classifies each K8s node by its workload safety profile. Runs every 10 min via APScheduler (`job_scan_clusters`). Results cached in `spot:node_classification:{cluster_id}` (TTL 600s).

| Priority | Condition | Classification |
|---|---|---|
| 1 | Control-plane / system pool labels | `SYSTEM_PROTECTED` |
| 2 | Any pod owned by StatefulSet | `STATEFUL_PROTECTED` |
| 3 | Any pod has PVC backed by EBS CSI | `STATEFUL_PROTECTED` |
| 4 | Any pod has hostPath volume | `STATEFUL_PROTECTED` |
| 5 | PDB with `maxUnavailable=0` covers any pod | `DRAIN_UNSAFE` |
| 6 | None of above | `STATELESS_ELIGIBLE` |

**Critical**: `cluster.workload_type` DB column is NOT used for safety decisions at runtime. Only the Redis cache is authoritative.

**Cache miss behavior** (updated 2026-03-24):
- Cache ABSENT: trigger async re-classification AND skip the entire cluster this cycle (no fall-through to processing unclassified nodes)
- Cache PRESENT: filter out individual OD nodes not found in the cache (~10-min race window for new nodes)

---

## VolatilityMonitor — Frontend Location

**Component**: `frontend/src/components/ascpai/VolatilityMonitor.jsx`

**Location**: Mounted in `App.js` root above the router, wrapped in `ErrorBoundary`. NOT inside `MainLayout.jsx`. This ensures its lifecycle is fully independent of layout rendering and it persists across route changes without remounting.

- `React.memo(VolatilityMonitor)` still in place
- Polls `/api/v1/ascpai/volatility/status` every 600,000ms (10 min)
- Hidden when `regime === 'NORMAL'`; shows sticky alert banner otherwise

---

## Reserved Instance / S3 / RDS / Data Transfer Analysis

All four features have real backend service implementations accessible via REST API.

| Feature | Routes File | Service Class | Key Endpoints |
|---|---|---|---|
| Reserved Instances | `api/ri_routes.py` | `RIAnalysisService` | `GET /api/v1/ri/overview`, `POST /api/v1/ri/analyze`, `POST /api/v1/ri/execute-action` (sell/modify/convert), `GET /api/v1/ri/coverage` |
| S3 Tiering | `api/s3_routes.py` | `S3TieringService` | `GET /api/v1/s3/overview`, `POST /api/v1/s3/analyze` |
| RDS Optimization | `api/rds_routes.py` | `RDSAnalysisService` | `GET /api/v1/rds/overview`, `POST /api/v1/rds/analyze` |
| Data Transfer | `api/transfer_routes.py` | `TransferAnalysisService` | `GET /api/v1/transfer/overview`, `POST /api/v1/transfer/analyze` |

---

### Billing Routes — /api/v1/billing/...
(`backend/api/billing_routes.py`)

| Endpoint | Method | Purpose |
|---|---|---|
| `/billing/create-portal-session` | POST | Create Stripe billing portal session |
| `/billing/webhook/stripe` | POST | Stripe webhook for subscription events |
| `/billing/status` | GET | Billing/subscription status for organization |
| `/billing/costs/summary` | GET | Cost summary with compute/resource breakdown |
| `/billing/costs/daily` | GET | Daily cost trend for last N days |
| `/billing/costs/by-service` | GET | Cost breakdown by AWS service |
| `/billing/costs/sync-status` | GET | AWS Cost Explorer sync status |
| `/billing/costs/sync` | POST | Trigger manual Cost Explorer sync |

### Admin Routes — /api/v1/admin/...
(`backend/api/admin_routes.py`, SUPER_ADMIN role required)

| Endpoint | Method | Purpose |
|---|---|---|
| `/admin/organizations` | GET | List all organizations (paginated) |
| `/admin/organizations/{org_id}/toggle` | POST | Toggle org active status |
| `/admin/clients` | GET | List all client users |
| `/admin/clients/{id}` | GET | Get client details |
| `/admin/clients/{id}/toggle` | POST | Toggle client active status |
| `/admin/clients/{id}/reset-password` | POST | Reset client password |
| `/admin/stats` | GET | Platform-wide stats |
| `/admin/health` | GET | Platform health status |
| `/admin/billing` | GET | Platform billing overview |
| `/admin/dashboard` | GET | Admin dashboard aggregate stats |
| `/admin/agent-fleet` | GET | All clusters with agent installed + fleet status |
| `/admin/config/{key}` | GET | Get system config value |
| `/admin/config` | PATCH | Update system config |
| `/admin/platform/connection` | GET | Platform AWS connection status |
| `/admin/impersonate` | POST | Impersonate an organization |
| `/admin/platform/connect` | POST | Connect platform AWS identity |
| `/admin/platform/disconnect` | DELETE | Disconnect platform AWS identity |
| `/admin/circuit-breakers` | GET | All circuit breaker states |
| `/admin/circuit-breakers/{cluster_id}/reset` | POST | Reset circuit breaker to NORMAL |
