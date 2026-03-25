# Change Guide — `main-2-updated.md` vs Current Codebase

> **Purpose**: Section-wise mapping of every change described in `main-2-updated.md`, cross-referenced against actual source code.
> **Generated**: 2026-03-13
> **Rule**: All file paths and function names verified against live code — no reliance on intermediate docs.

---

## How to Read This Guide

Each change entry contains:

| Field | Meaning |
|---|---|
| **Change** | What the updated doc says should exist or happen |
| **Current Logic** | What the code actually does today (code-verified) |
| **Primary File** | The main file to modify |
| **Dependency Files** | Other files affected by this change |
| **Operation** | `CREATE` / `MODIFY` / `DELETE` |
| **UI Component** | Frontend component to update (if applicable) |
| **Name Mapping** | Where the doc uses a different name than the code |

---

## Section 1 — Agents

### 1.1 Node Termination — `termination_mode` Parameter

| Field | Value |
|---|---|
| **Change** | The doc describes `_terminate_node()` accepting a `termination_mode` parameter with three modes: `"replacement"` (detach-not-decrement), `"karpenter"` (Karpenter handles), `"scaledown"` (`ShouldDecrementDesiredCapacity=True`). The old `decrement_asg=True` default is replaced with explicit mode control. **Note**: §1.2 of the doc is intentionally a one-sentence redirect to §10.3 — this is by design, NOT a placeholder for a duplicate termination mode table. |
| **Current Logic** | `_terminate_node()` at L1122 uses `decrement_asg = payload.get("decrement_asg", True)`. Default is `True` → always calls `terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=True)`. There is **no** `termination_mode` parameter. The detach-not-decrement pattern does not exist in the agent. |
| **Primary File** | `agent/actuator.py` (L1122-1287) |
| **Dependency Files** | `backend/workers/tasks/auto_rebalancer.py` (sends TERMINATE_NODE payload — must include `termination_mode`), `backend/services/execution_controller.py`, `backend/workers/tasks/emergency_rebalancer.py` |
| **Operation** | `MODIFY` |
| **UI Component** | None |
| **Name Mapping** | Doc: `termination_mode` parameter → Code: `decrement_asg` boolean. Replace boolean with enum/string. Doc §1.2 is a redirect to §10.3, not a standalone section. |

**What to change**:
1. In `actuator.py` `_terminate_node()`, replace `decrement_asg` boolean with `termination_mode` string parameter (`"replacement"`, `"karpenter"`, `"scaledown"`).
2. For `"replacement"` mode: implement the detach-not-decrement pattern with Redis lock (`asg:suspend_lock:{asg_name}`), `suspend_processes(['Launch'])`, `detach_instances(ShouldDecrementDesiredCapacity=False)`, `ec2.terminate_instances()`, `resume_processes(['Launch'])`.
3. For `"karpenter"` mode: do nothing — Karpenter terminates directly.
4. For `"scaledown"` mode: keep existing `ShouldDecrementDesiredCapacity=True` logic.
5. Update all callers (`auto_rebalancer.py`, `emergency_rebalancer.py`, `execution_controller.py`) to pass `termination_mode` in the TERMINATE_NODE payload.

---

### 1.2 Orchestrator Endpoint Authentication (Issue #2)

| Field | Value |
|---|---|
| **Change** | Add Bearer token validation (`validate_api_key` dependency) to orchestrator endpoints. |
| **Current Logic** | `backend/routers/agents.py` — **none** of the endpoints (`/register`, `/deregister`, `/heartbeat`) use `validate_api_key`. The orchestrator polling endpoints (`GET /agents/orchestrator/{cluster_id}/pending-commands` and `POST /agents/orchestrator/{cluster_id}/command-result`) are defined in the API routes but also lack auth. |
| **Primary File** | `backend/routers/agents.py` |
| **Dependency Files** | `backend/api/routes/cluster_routes.py` (orchestrator endpoints may also be here), `backend/core/dependencies.py` (has `validate_api_key`), `agent/actuator.py` (must send Bearer token on these calls) |
| **Operation** | `MODIFY` |
| **UI Component** | None |
| **Name Mapping** | Doc refers to `/agents/orchestrator/{cluster_id}/pending-commands` and `/agents/orchestrator/{cluster_id}/command-result`. In `agents.py` router, these endpoints may be at different paths — verify exact path in `api/` routes. |

**What to change**:
1. Add `Depends(validate_api_key)` to both orchestrator endpoints.
2. Ensure agent's `poll_actions()` and `report_action_result()` send `Authorization: Bearer {API_TOKEN}` header (already done for DaemonSet endpoints in `actuator.py` L1482-1528).

---

### 1.3 Thread Restart Loop Backoff (Issue #9)

| Field | Value |
|---|---|
| **Change** | Add a max restart count and exponential backoff to the component health monitor. |
| **Current Logic** | `agent/main.py` L415-481 — health monitor runs every 30s, auto-restarts dead threads with **no limit** and **no backoff**. |
| **Primary File** | `agent/main.py` |
| **Dependency Files** | None |
| **Operation** | `MODIFY` |
| **UI Component** | Cluster Details → Agent Status panel. Show thread restart counts. **Location**: Cluster detail page → Agent tab / Health section. |
| **Name Mapping** | None |

**What to change**:
1. Add `max_restart_count` per component (e.g. 5).
2. Add exponential backoff delay (e.g. `2^n` seconds, capped at 60s).
3. After max restarts exceeded, log CRITICAL and stop attempting (mark component as DEAD).

---

### 1.4 WebSocket API Key Invalidation (Issue #8)

| Field | Value |
|---|---|
| **Change** | When `POST /clusters/{id}/agent/disconnect` is called, forcibly close existing WebSocket connections for that cluster. |
| **Current Logic** | API key rotation generates a new key and agents get HTTP 401 on subsequent HTTP calls. But **existing WebSocket connections stay open** until the agent reconnects. |
| **Primary File** | `backend/api/routes/cluster_routes.py` (disconnect endpoint L531-565) |
| **Dependency Files** | `backend/core/sse_manager.py` or WebSocket manager (needs a `close_connections_for_cluster()` method), `agent/websocket_client.py` |
| **Operation** | `MODIFY` |
| **UI Component** | Cluster Details → Settings → Agent section → Disconnect button. **Location**: Settings tab in cluster detail page. |
| **Name Mapping** | None |

---

### 1.5 Agent Component Architecture (DaemonSet + Deployment)

| Field | Value |
|---|---|
| **Change** | Doc describes agent as two K8s workloads: a **DaemonSet** (SpotPoller, MetricsCollector, **PodMetricsCollector**, HeartbeatSender — one per node) and a **Deployment** (Orchestrator/Actuator — one replica per cluster). The Deployment handles action execution via WebSocket push or HTTP polling. **PodMetricsCollector** (`agent/pod_metrics_collector.py`, 358L) collects pod-level CPU/memory metrics and sends every 5 minutes. |
| **Current Logic** | Verify `agent/main.py` has both DaemonSet and Deployment entrypoints. Verify `agent/poller.py` (SpotPoller), `agent/metrics_collector.py` (MetricsCollector), **`agent/pod_metrics_collector.py` (PodMetricsCollector)**, `agent/heartbeat.py` (HeartbeatSender), `agent/actuator.py` (Actuator), `agent/websocket_client.py` (WebSocket). |
| **Primary File** | `agent/main.py` |
| **Dependency Files** | `agent/poller.py`, `agent/metrics_collector.py`, `agent/pod_metrics_collector.py`, `agent/heartbeat.py`, `agent/actuator.py`, `agent/websocket_client.py` |
| **Operation** | `MODIFY` (verify all components exist and match doc) |
| **UI Component** | Cluster Details → Agent tab. Show DaemonSet vs Deployment status separately. **Location**: Cluster detail page → Agent section. |
| **Name Mapping** | Doc: "Orchestrator Deployment" → Code: single-replica Deployment running `actuator.py` + `websocket_client.py`. |

---

### 1.6 WebSocket Push for Emergency Actions

| Field | Value |
|---|---|
| **Change** | Emergency actions (`priority=10`) are pushed immediately via WebSocket as `emergency_command` messages, bypassing normal HTTP polling queue. |
| **Current Logic** | Verify `backend/core/sse_manager.py` or WebSocket manager sends `emergency_command` type messages. Verify `agent/websocket_client.py` handles this message type. |
| **Primary File** | `backend/core/sse_manager.py` (or WebSocket manager) |
| **Dependency Files** | `agent/websocket_client.py`, `backend/workers/tasks/emergency_rebalancer.py` |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

### 1.6a Emergency Action FIFO Ordering (Issue #7)

| Field | Value |
|---|---|
| **Change** | Emergency actions are still FIFO within the same priority tier — they queue chronologically. The orchestrator polling endpoint must return actions ordered by `priority DESC, created_at ASC` to ensure highest-priority actions execute first while maintaining FIFO within each tier. |
| **Current Logic** | Verify the orchestrator polling endpoint (`GET /agents/orchestrator/{cluster_id}/pending-commands`) orders by `priority DESC, created_at ASC`. If ordering is only by `created_at`, emergency actions (`priority=10`) could be delayed behind earlier normal actions (`priority=0`). |
| **Primary File** | `backend/routers/agents.py` (or `backend/api/routes/cluster_routes.py` — wherever the orchestrator polling endpoint is defined) |
| **Dependency Files** | `backend/models/agent_action.py` (`priority` field on AgentAction model) |
| **Operation** | `MODIFY` |
| **UI Component** | None |
| **Name Mapping** | None |

**What to change**:
1. In the orchestrator polling endpoint query, change ordering from `created_at ASC` to `priority DESC, created_at ASC`.
2. Verify `AgentAction` model has a `priority` field (integer, default 0, emergency = 10).

---

### 1.7 HMAC-SHA256 Action Verification

| Field | Value |
|---|---|
| **Change** | Every action payload (WebSocket and HTTP) is verified with HMAC-SHA256 using `SECRET_KEY`. |
| **Current Logic** | Verify HMAC signing exists in `backend/core/action_executor.py` and verification in `agent/actuator.py` or `agent/websocket_client.py`. |
| **Primary File** | `backend/core/action_executor.py` |
| **Dependency Files** | `agent/websocket_client.py`, `agent/actuator.py` |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

## Section 2 — Data Sources

### 2.1 Partial Pricing Refresh Staleness (Issue #5)

| Field | Value |
|---|---|
| **Change** | The pricing staleness timestamp should only be updated when ALL requested instance types are successfully fetched, not on partial success. |
| **Current Logic** | `backend/services/aws_pricing_service.py` → `refresh_regional_pricing_batch()` — sets `pricing:last_updated:{region}` timestamp after the batch call succeeds, regardless of how many instance types were fetched. A partial refresh (1/50 types succeed) marks pricing as fresh. |
| **Primary File** | `backend/services/aws_pricing_service.py` |
| **Dependency Files** | `backend/workers/tasks/pricing_worker.py` (calls `refresh_regional_pricing_batch`) |
| **Operation** | `MODIFY` |
| **UI Component** | None (backend-only). But pricing staleness status is shown in the dashboard — see Cluster Details → Health/Status section. |
| **Name Mapping** | None |

**What to change**:
1. Track the count of successfully fetched instance types vs total requested.
2. Only update `pricing:last_updated:{region}` if `success_count / total_count >= threshold` (e.g. 0.8 or 80%).
3. Or: add a `pricing:partial_stale:{region}` warning key when partial.

---

### 2.2 Spot Advisor Versioning Key (Issue #19)

| Field | Value |
|---|---|
| **Change** | Add a staleness check key for Spot Advisor data cached in Redis. |
| **Current Logic** | `backend/scrapers/spot_advisor_scraper.py` — stores data in `spot:advisor:{region}` with no version or freshness key. If the daily scraper fails, stale data is silently served. |
| **Primary File** | `backend/scrapers/spot_advisor_scraper.py` |
| **Dependency Files** | `backend/services/ml_feature_service.py` (reads Spot Advisor data for ML features) |
| **Operation** | `MODIFY` |
| **UI Component** | None |
| **Name Mapping** | None |

**What to change**:
1. Add `spot:advisor:last_updated:{region}` Redis key with timestamp.
2. ML pipeline should check freshness before using the data.

---

### 2.3 RC3 Guard Reset Logic (Issue #10)

| Field | Value |
|---|---|
| **Change** | The RC3 Guard should also reset the Redis counter on confirmed OD reads (not just confirmed SPOT reads). |
| **Current Logic** | `backend/workers/tasks/discovery.py` L720-768 — `rc3:od_streak:{instance_id}` counter has 30-min TTL. Confirmed SPOT reading resets counter immediately, but a clean OD read does **not** — counter can expire silently without triggering the downgrade. |
| **Primary File** | `backend/workers/tasks/discovery.py` |
| **Dependency Files** | None |
| **Operation** | `MODIFY` |
| **UI Component** | None |
| **Name Mapping** | None |

---

### 2.4 Discovery Worker — RC4 Ghost Instance Cleanup

| Field | Value |
|---|---|
| **Change** | After EC2 scan, any DB instance with `state='running'` NOT seen in scan → marked `terminated`. Terminated instances older than 5 min → deleted from DB. |
| **Current Logic** | `backend/workers/tasks/discovery.py` L794-839 — verify RC4 fix exists and the 5-min grace before deletion. |
| **Primary File** | `backend/workers/tasks/discovery.py` |
| **Dependency Files** | None |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

### 2.5 Discovery Worker — Cluster Cleanup Grace Periods

| Field | Value |
|---|---|
| **Change** | Three grace periods: (1) Never delete clusters created <60 min ago, (2) Agent-installed clusters require 2h heartbeat absence, (3) Any cluster with heartbeat <10 min ago preserved. |
| **Current Logic** | `backend/workers/tasks/discovery.py` L583-633 — verify all three grace periods exist. |
| **Primary File** | `backend/workers/tasks/discovery.py` |
| **Dependency Files** | None |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

### 2.6 Emergency Pricing Refresh

| Field | Value |
|---|---|
| **Change** | `pricing_worker.py` has `emergency_pricing_refresh()` triggered when staleness detected. Clears `cluster:{id}:pricing_stale` flag and forces immediate spot price re-fetch. |
| **Current Logic** | `backend/workers/tasks/pricing_worker.py` — verify `emergency_pricing_refresh()` exists and is triggered by staleness detection. |
| **Primary File** | `backend/workers/tasks/pricing_worker.py` |
| **Dependency Files** | `backend/services/aws_pricing_service.py` |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

## Section 3 — Actions

### 3.1 Three-Mode Action System (Mode 1 / Mode 2 / Mode 3)

| Field | Value |
|---|---|
| **Change** | The doc defines three explicitly named modes with distinct behaviors and separate gate logic. Mode 1 = Auto Rebalance Only, Mode 2 = Auto Rightsizing Only (Karpenter required), Mode 3 = Both ON (Synergy Mode). Mode 3 uses Two Independent Binary Gates replacing the old EV Cross-Mode Scoring. |
| **Current Logic** | `backend/workers/tasks/auto_rebalancer.py` (209405 bytes) handles rebalancing. `backend/services/rightsizing_service.py` (43484 bytes) handles rightsizing. The synergy mode with explicit two-gate evaluation exists partially in `backend/services/optimizer_coordinator.py` and `backend/workers/tasks/optimizer_coordinator_worker.py`. The old EV cross-mode scoring may still be present. |
| **Primary File** | `backend/workers/tasks/auto_rebalancer.py` |
| **Dependency Files** | `backend/services/rightsizing_service.py`, `backend/services/optimizer_coordinator.py`, `backend/workers/tasks/optimizer_coordinator_worker.py`, `backend/core/decision_engine.py`, `backend/core/ev_model.py` |
| **Operation** | `MODIFY` |
| **UI Component** | Cluster Details → Optimization Settings. The mode toggle UI needs to clearly show Mode 1 / Mode 2 / Mode 3 states. **Location**: Cluster detail page → Settings tab → Optimization section. Currently shows `auto_rebalance_enabled` and `auto_rightsizing_enabled` toggles. |
| **Name Mapping** | Doc: "Mode 1", "Mode 2", "Mode 3 (Synergy)" → Code: `auto_rebalance_enabled` + `auto_rightsizing_enabled` booleans in `cluster_optimization_settings`. Doc: "Gate 1", "Gate 2" → Code: likely in `optimizer_coordinator.py` as `evaluate_proposal_task`. |

**What to change**:
1. In Mode 3, ensure the **combined execution flow** (both gates pass) creates BOTH `PATCH_CONTAINER_RESOURCES` AND `PATCH_KARPENTER_NODEPOOL` as a single combined action, not two sequential steps.
2. Ensure `rightsizing_target` is locked to `"spot"` when both toggles are ON (synergy mode).
3. Remove any remaining EV cross-mode scoring logic.
4. Log gate rejection reasons separately (`gate_1_rejection`, `gate_2_rejection`) per action in synergy mode.
5. **Mode 1 Gate 1 five-condition formula**: Ensure the gate checks ALL five conditions: `candidate_ev > current_ev` AND `savings >= min_savings_percent` AND `risk < risk_ceiling_percent` AND NOT on cooldown AND passes DryRun capacity check. All five must pass for a rebalance to proceed.
6. **Mode 3 downgrade path**: When Mode 3 combined execution finds no suitable pool (Gate 1 fails but Gate 2 passes), fall back to **Gate 2 result only** — resize pods, let Karpenter provision naturally, no NodePool patch. **Owning file**: `backend/services/optimizer_coordinator.py` (the downgrade branch logic).

---

### 3.2 Detach-Not-Decrement Pattern (ASG Termination)

| Field | Value |
|---|---|
| **Change** | Mode 1 and Mode 3 should use detach-not-decrement pattern: `suspend_processes(['Launch'])` → `detach_instances(ShouldDecrementDesiredCapacity=False)` → `ec2.terminate_instances()` → `resume_processes(['Launch'])`, with a Redis lock `asg:suspend_lock:{asg_name}` (30s TTL) around the suspend window. |
| **Current Logic** | In `auto_rebalancer.py` L1980-2008, the ASG terminate uses `ShouldDecrementDesiredCapacity=True` in the primary path. The detach-not-decrement pattern partially exists in `backend/utils/aws/asg.py` L182 and L247. In the agent `actuator.py` L1174-1238, `decrement_asg=True` is the default. |
| **Primary File** | `backend/workers/tasks/auto_rebalancer.py` |
| **Dependency Files** | `backend/utils/aws/asg.py`, `agent/actuator.py` (L1122-1287), `backend/services/distributed_locks.py` |
| **Operation** | `MODIFY` |
| **UI Component** | None |
| **Name Mapping** | Doc: `asg:suspend_lock:{asg_name}` → Code: may need new Redis key. Doc: `termination_mode="replacement"` → Code: `decrement_asg=True/False` boolean |

**What to change**:
1. Replace `ShouldDecrementDesiredCapacity=True` with the detach-not-decrement pattern in Mode 1 (auto_rebalancer).
2. Add `asg:suspend_lock:{asg_name}` Redis NX lock with 30s TTL.
3. Ensure the `suspend_processes` window covers **only** detach+terminate (~2-3 seconds), NOT the cordon+drain.

---

### 3.3 Resize Guard — Synergy Mode Addition

| Field | Value |
|---|---|
| **Change** | In Mode 3, the resize guard should also monitor node pool risk signals for 2 hours post-execution, in addition to pod-level metrics. |
| **Current Logic** | `backend/workers/tasks/resize_guard_worker.py` (7138 bytes) — monitors CPU stress, pod restarts, and memory pressure only. No pool risk signal monitoring. |
| **Primary File** | `backend/workers/tasks/resize_guard_worker.py` |
| **Dependency Files** | `backend/core/risk_engine.py`, `backend/services/pool_ranking_service.py` |
| **Operation** | `MODIFY` |
| **UI Component** | Cluster Details → Rightsizing → Proposal status panel. Show "Resize Guard Active" status with additional risk signal monitoring indicator. **Location**: Cluster detail page → Rightsizing tab → Proposal cards. |
| **Name Mapping** | None |

---

### 3.4 Mode 1 — WorkloadInspector Node Classification

| Field | Value |
|---|---|
| **Change** | `WorkloadInspector` classifies nodes as `STATELESS_ELIGIBLE` or `STATEFUL_PROTECTED`. Stateful nodes blocked unless `auto_stateful_rightsizing_enabled=True` and approval rules allow. |
| **Current Logic** | `backend/services/workload_inspector.py` — verify classification logic exists. Redis key: `spot:node_classification:{id}`. |
| **Primary File** | `backend/services/workload_inspector.py` |
| **Dependency Files** | `backend/core/decision_engine.py` (Step 2b-2c reads classification) |
| **Operation** | `MODIFY` (verify exists and matches doc) |
| **UI Component** | Cluster Details → Nodes tab. Show classification badge (Stateless/Stateful) per node. **Location**: Cluster detail page → Nodes tab → Node row. |
| **Name Mapping** | None |

---

### 3.5 Mode 1 — Node Evaluation Order & Trigger Events

| Field | Value |
|---|---|
| **Change** | Nodes evaluated in descending hourly cost (most expensive first). Triggers: periodic (~15s), on toggle change (immediate), daily full cycle, risk threshold crossing. |
| **Current Logic** | `backend/workers/tasks/auto_rebalancer.py` — verify sort order and trigger sources. |
| **Primary File** | `backend/workers/tasks/auto_rebalancer.py` |
| **Dependency Files** | None |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

### 3.6 Mode 1 — DryRun Capacity Check & Instance Type Cascade

| Field | Value |
|---|---|
| **Change** | Before spot launch, `ec2.create_fleet(DryRun=True)` validates capacity. On failure, tries next candidate in ML rankings up to `max_instance_type_attempts` (default 6). All exhausted → mark failed, set pool cooldown. |
| **Current Logic** | `auto_rebalancer.py` L408-463 — hardcoded `[:6]` slice. DryRun is always attempted when available, skipped on permission error. |
| **Primary File** | `backend/workers/tasks/auto_rebalancer.py` |
| **Dependency Files** | `backend/models/cluster.py` (add `max_instance_type_attempts` setting) |
| **Operation** | `MODIFY` |
| **UI Component** | Cluster Details → Settings → Advanced. Add configurable instance type cascade limit. **Location**: Settings tab → Advanced section. |
| **Name Mapping** | Doc: `max_instance_type_attempts=6` → Code: hardcoded `[:6]` slice. |

---

### 3.7 Mode 1 — Action Expiry (15-min Auto-Expire)

| Field | Value |
|---|---|
| **Change** | `AgentAction` records in `PENDING` or `PICKED_UP` status for >15 minutes are auto-expired at the start of each rebalancer cycle. |
| **Current Logic** | `auto_rebalancer.py` L2367-2382 — verify auto-expiry logic. |
| **Primary File** | `backend/workers/tasks/auto_rebalancer.py` |
| **Dependency Files** | `backend/models/agent_action.py` |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | Cluster Details → Activity tab. Show expired actions with status badge. **Location**: Activity/Audit section. |
| **Name Mapping** | None |

---

### 3.8 Mode 2 — Rightsizing Two-Gate System Detail

| Field | Value |
|---|---|
| **Change** | Gate 1: Is controller mis-sized? (OVERSIZED or UNDERSIZED). Gate 2: Is delta >20% AND not on resize_cooldown? Both must pass. Karpenter required. Recommendation uses P95 × `resize_headroom_multiplier` (default 1.2). Stateful controllers: recommendation stored in UI only, never auto-executed. |
| **Current Logic** | `backend/services/rightsizing_service.py` — verify Gate 1 and Gate 2 logic, P50/P95/P99 calculation, classification thresholds (OVERSIZED: request >= recommended × 1.5, UNDERSIZED: P95_usage >= request × 0.95). |
| **Primary File** | `backend/services/rightsizing_service.py` |
| **Dependency Files** | `backend/models/rightsizing_proposal.py`, `backend/workers/tasks/optimizer_coordinator_worker.py` |
| **Operation** | `MODIFY` (verify all thresholds match doc) |
| **UI Component** | Cluster Details → Rightsizing tab. Show gate pass/fail reason per proposal. Show classification (OVERSIZED/UNDERSIZED/RIGHT_SIZED). **Location**: Cluster detail → Rightsizing tab → Proposal cards. |
| **Name Mapping** | Doc: "Gate 1", "Gate 2" in Mode 2 → Code: classification + delta check in `rightsizing_service.py`. Different from Mode 3 gates. |

---

### 3.9 Mode 2 — Rightsizing Settings

| Field | Value |
|---|---|
| **Change** | Settings: `rightsizing_target` (default "spot"), `rightsizing_history_window_days` (7), `rightsizing_frequency_days` (1), `resize_cooldown_minutes` (120), `resize_headroom_multiplier` (1.2). |
| **Current Logic** | `backend/models/cluster.py` → `cluster_optimization_settings` or `stateless_runtime_rules` — verify all settings exist with correct defaults. |
| **Primary File** | `backend/models/cluster.py` |
| **Dependency Files** | `backend/services/rightsizing_service.py` (reads these settings) |
| **Operation** | `MODIFY` (verify all exist) |
| **UI Component** | Cluster Details → Settings → Rightsizing section. Show all 5 settings with editable inputs. **Location**: Cluster detail page → Settings tab → Rightsizing section. |
| **Name Mapping** | None |

---

### 3.10 Mode 3 — Conflict Prevention (Concurrency Control)

| Field | Value |
|---|---|
| **Change** | Three layers of concurrency control: (1) Global execution lock `lock:workers.auto_rebalancer` (300s TTL), (2) Per-cluster lock `key_rebalance_lock(cluster_id)` (600s TTL), (3) Stabilization lock via `CooldownController` (5 min). Emergency actions force-clear locks. |
| **Current Logic** | `auto_rebalancer.py` L1398 (global lock), L501-511 (per-cluster lock), L517-520 (stabilization). |
| **Primary File** | `backend/workers/tasks/auto_rebalancer.py` |
| **Dependency Files** | `backend/services/cooldown_controller.py` |
| **Operation** | `MODIFY` (verify all three layers exist) |
| **UI Component** | None |
| **Name Mapping** | None |

---

### 3.11 Mode 1 — VolumeAttachment Cleanup Post-Drain

| Field | Value |
|---|---|
| **Change** | After drain completes, `clear_stuck_volume_attachments(node_name, timeout_seconds=30)` lists all VolumeAttachments for the node, detects stuck ones (has error OR pending > timeout), and force-deletes them. Prevents Multi-Attach errors on replacement node. |
| **Current Logic** | `agent/actuator.py` L372-384 — verify `clear_stuck_volume_attachments()` exists. |
| **Primary File** | `agent/actuator.py` |
| **Dependency Files** | None |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

## Section 4 — ML Model

### 4.1 ML Circuit Breaker Monitoring

| Field | Value |
|---|---|
| **Change** | Track circuit breaker activations in Redis: `ascpai:ml_fail_count` (INCR, 10-min TTL) and `ascpai:ml_degraded` (10-min TTL). |
| **Current Logic** | `backend/workers/tasks/ascpai_worker.py` + `backend/services/pool_ranking_service.py` — ML circuit breaker partially exists. Verify the exact Redis keys match. |
| **Primary File** | `backend/services/pool_ranking_service.py` |
| **Dependency Files** | `backend/workers/tasks/ascpai_worker.py`, `backend/core/redis_client.py` |
| **Operation** | `MODIFY` (verify existing implementation matches doc) |
| **UI Component** | Admin Dashboard → ML Status section. Show circuit breaker state (Normal / Degraded). **Location**: Admin panel or Cluster detail → ML/AI section. |
| **Name Mapping** | Doc: `ascpai:ml_fail_count`, `ascpai:ml_degraded` → verify against code Redis key names. |

---

## Section 5 — Decision Engine

### 5.1 Decision Audit Persistence (Issue #4)

| Field | Value |
|---|---|
| **Change** | Persist decision audit data to the database, not just Redis with 24h TTL. |
| **Current Logic** | `backend/services/observability_logger.py` (6731 bytes) — stores last 100 decisions per cluster in Redis (`obs:decisions:{cluster_id}`, 24h TTL). No DB persistence. |
| **Primary File** | `backend/services/observability_logger.py` |
| **Dependency Files** | `backend/models/` (may need a new `decision_audit` model/table), `backend/core/decision_engine.py` |
| **Operation** | `MODIFY` |
| **UI Component** | Cluster Details → Decision History / Audit Log. Show full decision pipeline trail beyond 24h. **Location**: Cluster detail page → Activity / Audit tab. |
| **Name Mapping** | None |

**What to change**:
1. In `observability_logger.py`, add DB persistence alongside Redis caching.
2. Create a `decision_audit` table or extend `audit_log` to store decision outcomes.
3. Keep Redis for fast debugging (last 100, 24h), add DB for compliance (indefinite).

---

### 5.2 Pool Rankings Cache Miss Handling (Issue #6)

| Field | Value |
|---|---|
| **Change** | When `global_pool_rankings:{region}` is missing from Redis, consider triggering a synchronous rebuild or having a fast-path recalculation instead of waiting up to 1 hour for the next Celery beat. |
| **Current Logic** | `backend/core/decision_engine.py` → `_load_global_rankings()` — returns `None` if key missing. Pipeline rejects the decision with reason `"no_global_rankings"`. No synchronous fallback. |
| **Primary File** | `backend/core/decision_engine.py` |
| **Dependency Files** | `backend/workers/tasks/ascpai_worker.py` (`execute_pool_ranking_pipeline`), `backend/services/pool_ranking_service.py` |
| **Operation** | `MODIFY` |
| **UI Component** | Cluster Details → Health / Status indicators. Show "Pool rankings stale" warning. **Location**: Cluster detail page → Overview tab → Health badges. |
| **Name Mapping** | None |

---

### 5.3 Decision Engine — 15-Step Pipeline & Optimization Profiles

| Field | Value |
|---|---|
| **Change** | Decision Engine runs a 15-step pipeline (L56-84 in `decision_engine.py`). Three optimization profiles: `COST_FIRST` (risk_ceiling=0.25, delta_threshold=0.02), `BALANCED` (0.20, 0.03), `NO_DOWNTIME_FIRST` (0.10, 0.04). Step 13 applies `delta_threshold` as minimum EV improvement gate. |
| **Current Logic** | `backend/core/decision_engine.py` (781 lines) — verify all 15 steps exist and profile constants match. |
| **Primary File** | `backend/core/decision_engine.py` |
| **Dependency Files** | `backend/core/ev_model.py` (evaluate_candidate_ev), `backend/services/diversity_enforcer.py` (Step 12) |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | Cluster Details → Settings → Optimization Profile dropdown (COST_FIRST/BALANCED/NO_DOWNTIME_FIRST). **Location**: Settings tab → Optimization section. |
| **Name Mapping** | Doc: `optimization_mode` → Code: `Cluster.optimization_mode` in DB. Verify enum values match. |

---

### 5.4 Decision Engine — Volatility Guard & Three-Layer Risk Ceiling

| Field | Value |
|---|---|
| **Change** | Step 6: `effective_ceiling = profile.risk_ceiling × volatility_multiplier × trust_phase_multiplier`. Higher volatility → lower multiplier → tighter risk. New clusters start with stricter ceilings that relax over time (`OptimizerState`). |
| **Current Logic** | `backend/core/decision_engine.py` Step 6 — verify three-layer risk ceiling formula. `backend/models/optimizer_state.py` — verify trust phase model. |
| **Primary File** | `backend/core/decision_engine.py` |
| **Dependency Files** | `backend/models/optimizer_state.py`, `backend/workers/tasks/optimizer_coordinator_worker.py` |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | Cluster Details → Overview → Risk ceiling indicator. Show effective ceiling and contributing factors. **Location**: Cluster detail → Overview/Health section. |
| **Name Mapping** | None |

---

### 5.5 Decision Engine — DiversityEnforcer (Step 12)

| Field | Value |
|---|---|
| **Change** | Step 12 filters candidates that would violate diversification constraints. `max_family_diversification_cap_pct` (default 40%) limits any one instance family. `diversify_pools=True` spreads nodes across multiple pools. |
| **Current Logic** | `backend/services/diversity_enforcer.py` — verify diversification logic and deadlock protection. |
| **Primary File** | `backend/services/diversity_enforcer.py` |
| **Dependency Files** | `backend/workers/tasks/control_plane_loop.py` (Step 7 diversification simulation) |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | Cluster Details → Settings → Diversification toggle + family cap slider. **Location**: Settings tab → Optimization → Advanced. |
| **Name Mapping** | Doc: `diversify_pools`, `max_family_diversification_cap_pct` → Code: verify field names in `cluster_optimization_settings`. |

---

## Section 6 — Execution Engine

### 6.1 Rightsizing Execution (Container Patching) — Already Exists

| Field | Value |
|---|---|
| **Change** | `actuator._patch_container_resources()` should support Deployment, StatefulSet, and DaemonSet. |
| **Current Logic** | ✅ **Already implemented** at `agent/actuator.py` L957-1048. Supports all three controller types via strategic merge patch on `spec.template.spec.containers`. |
| **Primary File** | `agent/actuator.py` (L957-1048) |
| **Dependency Files** | `backend/services/rightsizing_service.py` (creates `PATCH_CONTAINER_RESOURCES` actions) |
| **Operation** | None (already exists) |
| **UI Component** | Cluster Details → Rightsizing → Apply button. **Location**: Cluster detail → Rightsizing tab → Proposal action buttons. |
| **Name Mapping** | None |

---

### 6.2 Control Plane Loop — 8-Step Decision Cycle

| Field | Value |
|---|---|
| **Change** | The control plane loop should run 8 steps including a rightsizing baseline step (Step 5) and diversification simulation (Step 7). |
| **Current Logic** | `backend/workers/tasks/control_plane_loop.py` (16455 bytes) — verify that all 8 steps exist. |
| **Primary File** | `backend/workers/tasks/control_plane_loop.py` |
| **Dependency Files** | `backend/services/workload_inspector.py`, `backend/services/diversity_enforcer.py`, `backend/services/rightsizing_service.py`, `backend/core/decision_engine.py` |
| **Operation** | `MODIFY` (verify and fill any missing steps) |
| **UI Component** | None |
| **Name Mapping** | Doc: Steps 1-8 names → Code: `_step1_*` through `_step8_*` method names. |

---

## Section 7 — Karpenter

### 7.1 NodePool Patch JSON Path (Issue #1 — CRITICAL)

| Field | Value |
|---|---|
| **Change** | Fix the NodePool patch path from `spec.template.spec.requirements` to the correct Karpenter v1 path. |
| **Current Logic** | `agent/actuator.py` → `patch_karpenter_nodepool()` (L699-780) — patches `spec.template.spec.requirements`. For Karpenter v1, requirements are at `spec.template.spec.requirements` (this is actually **correct** for Karpenter v1). For v1beta1, they are also at `spec.template.spec.requirements`. The doc flags this as wrong path, but the **actual Karpenter v1 spec** uses `spec.template.spec.requirements`. **Verify against deployed Karpenter version.** |
| **Primary File** | `agent/actuator.py` (L699-780) |
| **Dependency Files** | `backend/services/karpenter_service.py` (36002 bytes) |
| **Operation** | `MODIFY` (verify path against actual CRD) |
| **UI Component** | Cluster Details → Karpenter section → NodePool status. **Location**: Cluster detail page → Karpenter tab. |
| **Name Mapping** | None |

**What to change**:
1. Verify the exact CRD path for the deployed Karpenter version (v1 vs v1beta1).
2. If using Karpenter v1 (`karpenter.sh/v1`), the correct path IS `spec.template.spec.requirements`.
3. If using v1beta1 (`karpenter.sh/v1beta1`), path is also `spec.template.spec.requirements`.
4. The doc's claim about `spec.requirements` being correct may itself be wrong. Test against actual CRD.

---

### 7.2 Karpenter Mode Three-Way Toggle (dry_run / auto / None)

| Field | Value |
|---|---|
| **Change** | Support three Karpenter modes: `None` (not installed), `"dry_run"` (insights only), `"auto"` (full autonomous). |
| **Current Logic** | `backend/services/karpenter_service.py` — `karpenter_mode` field exists on Cluster model. Verify that `"dry_run"` mode properly blocks all EC2 changes. |
| **Primary File** | `backend/services/karpenter_service.py` |
| **Dependency Files** | `backend/models/cluster.py` (Cluster model — `karpenter_mode` field), `backend/api/routes/cluster_routes.py` (API endpoint to set mode) |
| **Operation** | `MODIFY` (verify dry_run enforcement) |
| **UI Component** | Cluster Details → Settings → Karpenter section. Three-way toggle: Off / Insights Only / Auto-Optimize. **Location**: Cluster detail page → Settings tab → Karpenter Mode dropdown/toggle. |
| **Name Mapping** | Doc: `karpenter_mode = "dry_run"` → Code: verify enum values in `cluster.py` or `karpenter_service.py`. |

---

### 7.3 NodePool Auto-Creation Reliability (Issue #11)

| Field | Value |
|---|---|
| **Change** | When NodePool patch fails with 404, the agent should fall back to `CLUSTER_NAME` env var instead of unreliable inference from ConfigMap or node labels. |
| **Current Logic** | `agent/actuator.py` → `patch_karpenter_nodepool()` — on 404, auto-creates NodePool by inferring cluster name from ConfigMap or node labels. No `CLUSTER_NAME` env var fallback. |
| **Primary File** | `agent/actuator.py` (L699-780) |
| **Dependency Files** | `agent/config.py` (add `CLUSTER_NAME` env var) |
| **Operation** | `MODIFY` |
| **UI Component** | None |
| **Name Mapping** | None |

---

### 7.4 Karpenter Install Details (IRSA, AL2023, Access Entry)

| Field | Value |
|---|---|
| **Change** | Install flow: (1) Create SQS queue `KarpenterInterruptionQueue-{cluster_name}`, (2) helm install v1.0.8, (3) IRSA annotation on ServiceAccount, (4) Register `KarpenterNodeRole` access entry, (5) Create default `EC2NodeClass` with `alias: al2023@latest` (dual-arch), (6) Create default `NodePool` with `karpenter.sh/v1`, `consolidationPolicy: WhenUnderutilized`, `consolidateAfter: 30s`. |
| **Current Logic** | `agent/actuator.py` L782-868 (`install_karpenter()`) — verify all 6 steps exist. Uninstall: L1289-1326 (`uninstall_karpenter()`). |
| **Primary File** | `agent/actuator.py` |
| **Dependency Files** | `backend/services/karpenter_service.py` |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | Cluster Details → Karpenter tab → Install/Uninstall buttons. **Location**: Cluster detail page → Karpenter section. |
| **Name Mapping** | None |

---

### 7.5 Karpenter Redis Keys

| Field | Value |
|---|---|
| **Change** | 5 Karpenter-specific Redis keys: `spot:karpenter:installed:{id}` (detection), `spot:karpenter:nodepool_updated:{id}` (30min cooldown), `spot:karpenter:provision_requested:{id}` (15min dedup), `spot:ondemand_fallback:{id}` (12h), `spot:execution_failures:{id}` (10min circuit breaker). |
| **Current Logic** | Verify all 5 keys exist with correct TTLs in `backend/services/karpenter_service.py` and `agent/actuator.py`. |
| **Primary File** | `backend/services/karpenter_service.py` |
| **Dependency Files** | `agent/actuator.py`, `agent/heartbeat.py` |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

## Section 8 — Emergency System

### 8.1 SQS + IMDS Deduplication (Issue #20)

| Field | Value |
|---|---|
| **Change** | Add deduplication for spot interruption events received via both SpotPoller (IMDS) and SQS, to prevent two emergency rebalancing tasks for the same node. |
| **Current Logic** | `agent/poller.py` (detects via IMDS) and `backend/workers/tasks/sqs_consumer.py` (detects via SQS) both trigger emergency rebalancing independently with no deduplication beyond the 15-minute action expiry. |
| **Primary File** | `backend/workers/tasks/termination_monitor.py` |
| **Dependency Files** | `backend/workers/tasks/sqs_consumer.py`, `backend/workers/tasks/emergency_rebalancer.py`, `agent/poller.py` |
| **Operation** | `MODIFY` |
| **UI Component** | None |
| **Name Mapping** | None |

**What to change**:
1. Add a Redis key `emergency:dedup:{instance_id}` (TTL=**2min**, matching the AWS 2-minute termination window) set on first interruption detection inside `detect_termination_notice()` in `termination_monitor.py`.
2. Before creating emergency action in `termination_monitor.py`, check for existing dedup key — if present, skip creating a duplicate action.
3. The dedup belongs in `termination_monitor.py` (the single entry point for both IMDS and SQS events), NOT in `emergency_rebalancer.py`.

---

### 8.2 Emergency Standby-First Path

| Field | Value |
|---|---|
| **Change** | If `maintain_standby=True` and a standby node exists: (1) UNCORDON standby, (2) CORDON interrupted node, (3) DRAIN with `grace_period=90`, `force=True`, (4) Terminate interrupted node (`termination_mode="replacement"`), (5) Mark standby as active, (6) Launch new standby asynchronously. If no standby → normal emergency path (creates `priority=10` RebalancingAction). **Karpenter emergency path**: When Karpenter is installed, emergency termination uses direct `ec2.terminate_instances()` with **zero ASG interaction** — Karpenter manages node inventory separately from ASG DesiredCapacity. No detach, no suspend_processes, no ASG API calls at all. |
| **Current Logic** | `backend/workers/tasks/emergency_rebalancer.py` L115-206 — verify standby-first path exists. Verify `maintain_standby` setting in `cluster_optimization_settings`. Verify Karpenter emergency path uses direct EC2 terminate without ASG calls. |
| **Primary File** | `backend/workers/tasks/emergency_rebalancer.py` |
| **Dependency Files** | `backend/models/cluster.py` (`maintain_standby` setting), `agent/actuator.py`, `backend/services/karpenter_service.py` |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | Cluster Details → Settings → Standby toggle. Cluster Details → Nodes → Show standby node badge. **Location**: Settings tab → Optimization, Nodes tab → Node row. |
| **Name Mapping** | Doc: `maintain_standby` → Code: verify field in `cluster_optimization_settings` table. |

---

### 8.3 InstabilityPropagator — Cross-Cluster Pool Pressure

| Field | Value |
|---|---|
| **Change** | On interruption: (1) `INCR propagator:events:{region}:{az}:{type}` (30-min TTL), (2) `SADD propagator:affected_count:{region}:{az}:{type}` cluster IDs (2h TTL), (3) Compute Bayesian pool pressure, (4) Store pressure (2h TTL), (5) Recompute AZ average, (6) If ≥3 clusters affected → `ESCALATE_ALL`. Runs synchronously within interruption handling. |
| **Current Logic** | `backend/services/instability_propagator.py` (256 lines) — verify all 6 steps exist. Verify SYSTEMIC threshold (≥3 clusters). |
| **Primary File** | `backend/services/instability_propagator.py` |
| **Dependency Files** | `backend/core/risk_engine.py` (`calculate_bayesian_pool_pressure()`), `backend/workers/tasks/termination_monitor.py` |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | Cluster Details → Health → Pool Pressure indicator. Show SYSTEMIC escalation status. **Location**: Cluster detail → Overview/Health section. |
| **Name Mapping** | None |

---

### 8.4 Emergency Drain — 90s Grace Period & Force Override

| Field | Value |
|---|---|
| **Change** | Emergency drain uses `grace_period=90`, `force=True`. At T-90s any pod still running is force-deleted with `grace_period=0`. Hardcoded — not configurable. |
| **Current Logic** | `emergency_rebalancer.py` L186-206 — verify grace period and force flag logic. |
| **Primary File** | `backend/workers/tasks/emergency_rebalancer.py` |
| **Dependency Files** | `agent/actuator.py` (`drain_node()`) |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

## Section 9 — Rules

### 9.1 PDB Check Fail-Safe Direction (Issue #13)

| Field | Value |
|---|---|
| **Change** | Changed fail-safe to return `False` (safe/allow drain) when an error occurs, but only after logging the error. Doc says this matches `kubectl drain` behavior. |
| **Current Logic** | `agent/actuator.py` → `check_pdb_violation()` (L103-128) — verify current fail-safe direction. If it currently returns `True` (block drain) on error, that's the wrong direction per the doc. |
| **Primary File** | `agent/actuator.py` (L103-128) |
| **Dependency Files** | None |
| **Operation** | `MODIFY` |
| **UI Component** | None |
| **Name Mapping** | None |

---

### 9.2 Force-Delete Node — Pod Finalizer Removal (Issue #12)

| Field | Value |
|---|---|
| **Change** | After force-delete, agent should list all pods in `Terminating` state on the deleted node and patch them to remove finalizers. Add `REMOVE_POD_FINALIZERS` action type. |
| **Current Logic** | `agent/actuator.py` → `force_delete_node()` (L254-280) — deletes the K8s node object only. Does **not** remove pod finalizers. No `REMOVE_POD_FINALIZERS` action type exists. |
| **Primary File** | `agent/actuator.py` |
| **Dependency Files** | `backend/models/agent_action.py` (add `REMOVE_POD_FINALIZERS` to enum), `migrations/` (DB migration for new enum value) |
| **Operation** | `MODIFY` |
| **UI Component** | Cluster Details → Nodes → Node action dropdown. Add "Remove Pod Finalizers" button for stuck nodes. **Location**: Cluster detail page → Nodes tab → Node row action menu. |
| **Name Mapping** | Doc: `REMOVE_POD_FINALIZERS` → Code: new action type, does not exist yet. |

**What to change**:
1. In `force_delete_node()`, after deleting the node object, list pods with `field_selector='spec.nodeName={node_name}'` in `Terminating` status.
2. For each terminating pod, `PATCH` to remove finalizers: `metadata.finalizers = []`.
3. Add `REMOVE_POD_FINALIZERS` to `AgentActionType` enum in `backend/models/agent_action.py`.
4. Add handler in `execute_action_v2()` for the new action type.

---

### 9.3 Blacklist Cascade Protection Fix (Issue #14)

| Field | Value |
|---|---|
| **Change** | When >70% of pools are blacklisted, suspend only predictive blacklisting but keep deterministic (actual interruption) blacklisting always active. Currently, cascade suspension incorrectly affects both. |
| **Current Logic** | `backend/services/blacklist_service.py` (L382-422) — verify if cascade protection correctly differentiates between predictive and deterministic blacklisting. |
| **Primary File** | `backend/services/blacklist_service.py` |
| **Dependency Files** | None |
| **Operation** | `MODIFY` |
| **UI Component** | None |
| **Name Mapping** | None |

---

### 9.4 Blacklist Exponential Backoff Max Cap (Issue #16)

| Field | Value |
|---|---|
| **Change** | The backoff TTL doubles per failure up to 7 days (168h). A pool with 5 old failures gets an immediate 7-day blacklist. Consider adding decay or recency weighting. |
| **Current Logic** | `backend/services/blacklist_service.py` → `blacklist_pool()` (L38-109) — base TTL 24h, 2× multiplier, max 168h. Failure counter has 30-day expiry. |
| **Primary File** | `backend/services/blacklist_service.py` |
| **Dependency Files** | None |
| **Operation** | `MODIFY` |
| **UI Component** | Cluster Details → Pool Rankings → Blacklisted Pools section. Show blacklist reason and TTL remaining. **Location**: Cluster detail page → Pool Rankings tab → Blacklisted pools list. |
| **Name Mapping** | None |

---

### 9.5 Cooldown Types — 10 Cooldown Table

| Field | Value |
|---|---|
| **Change** | Doc defines 10 distinct cooldown types with specific Redis keys and TTLs. Key ones: Cluster switch (60min), Pool reuse (120min), Resize per-controller (6h/360min), ASG suspend lock (30s — serializes concurrent detach operations), Stateful per-cluster (48h), Stateful per-instance (48h). |
| **Current Logic** | `backend/services/cooldown_controller.py` — verify all 10 cooldowns exist with correct TTLs and Redis keys. |
| **Primary File** | `backend/services/cooldown_controller.py` |
| **Dependency Files** | `backend/workers/tasks/auto_rebalancer.py`, `backend/workers/tasks/emergency_rebalancer.py` |
| **Operation** | `MODIFY` (verify all exist) |
| **UI Component** | None (backend-only, but cooldown status shown in action details). |
| **Name Mapping** | None |

---

### 9.6 Tiered Blacklist (Decision Engine v3)

| Field | Value |
|---|---|
| **Change** | Five tiers: DryRun 1-2×/24h → 6h TTL, DryRun 3+×/24h → 12h TTL, ML high risk (>0.45) → 24h TTL, Termination event → 24h TTL, Execution DryRun failure → penalty only (no blacklist). Architecture-aware: entries are per `(instance_type, az)`. |
| **Current Logic** | `backend/services/blacklist_service.py` → `blacklist_pool_tiered()` L213-268. Verify all 5 tiers exist. |
| **Primary File** | `backend/services/blacklist_service.py` |
| **Dependency Files** | `backend/core/decision_engine.py` (consumes blacklist data at Step 2) |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | Cluster Details → Pool Rankings → Blacklisted Pools. Show tier and TTL per pool. |
| **Name Mapping** | None |

---

### 9.7 Redis Key Hygiene — Orphaned Key Cleanup

| Field | Value |
|---|---|
| **Change** | `cleanup_redis_keys()` in `blacklist_service.py` L382-422: daily scan finds orphaned `spot:*` keys with no TTL and sets a 24h safety TTL, preventing key explosion. |
| **Current Logic** | `backend/services/blacklist_service.py` — verify `cleanup_redis_keys()` exists as a daily Celery task. |
| **Primary File** | `backend/services/blacklist_service.py` |
| **Dependency Files** | None |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

## Section 10 — Kubernetes Logic

### 10.1 Node Template Labels

| Field | Value |
|---|---|
| **Change** | Apply standard labels to platform-launched nodes: `spot-optimizer/template-id`, `spot-optimizer/allowed-architectures`, `spot-optimizer/launched-by`, `spot-optimizer/termination-mode`. |
| **Current Logic** | `spot-optimizer/launched-by=platform` label exists (used in savings calculation). Verify if `template-id`, `allowed-architectures`, and `termination-mode` labels are applied in `auto_rebalancer.py` or `agent_injector.py`. |
| **Primary File** | `backend/workers/tasks/auto_rebalancer.py` (node launch section) |
| **Dependency Files** | `backend/services/template_service.py`, `backend/models/node_template.py`, `agent/actuator.py` (LABEL_NODE action) |
| **Operation** | `MODIFY` |
| **UI Component** | Cluster Details → Nodes → Node label display. Show template-related labels. **Location**: Cluster detail page → Nodes tab → Node detail/expand panel. |
| **Name Mapping** | Doc: "Node Template" → Code: `NodeTemplate` model in `backend/models/node_template.py`, `template_service.py`. |

---

### 10.2 Detach Instance Action in K8s Actions Table

| Field | Value |
|---|---|
| **Change** | Add `Detach Instance` (`autoscaling:DetachInstances`) as a documented K8s action type. |
| **Current Logic** | `_detach_instance_from_asg()` function may exist in `backend/utils/aws/asg.py`. Verify. |
| **Primary File** | `backend/utils/aws/asg.py` |
| **Dependency Files** | `agent/actuator.py` (if detach runs on agent side) |
| **Operation** | `MODIFY` (verify exists, add if missing) |
| **UI Component** | None |
| **Name Mapping** | Doc: `actuator._detach_instance_from_asg()` → Code: may be in `backend/utils/aws/asg.py` instead. |

---

### 10.3 Drain Logic — Grace Period by Caller

| Field | Value |
|---|---|
| **Change** | Drain grace period varies by caller: Auto rebalancer Mode 1 → 60s/`force=False` (PDB respected), Mode 3 → 60s/`force=False`, Emergency → 90s/`force=True` (PDB bypassed), Spot interruption IMDS → 30s/`force=True`. |
| **Current Logic** | `agent/actuator.py` L282-407 (`drain_node()`) — verify grace period and force flag are controlled by caller parameters. |
| **Primary File** | `agent/actuator.py` |
| **Dependency Files** | `backend/workers/tasks/auto_rebalancer.py`, `backend/workers/tasks/emergency_rebalancer.py` |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

### 10.4 Node Resolution — Fallback Chain

| Field | Value |
|---|---|
| **Change** | Three-step fallback: (1) `payload.node_name`, (2) `_find_node_by_instance_id()` matching `spec.providerID` with `aws://{az}/{instance_id}`, (3) `_find_node_name()` label-based matching (`instance-type` + `zone`). |
| **Current Logic** | `agent/actuator.py` L662-697 — verify all three resolution methods exist. |
| **Primary File** | `agent/actuator.py` |
| **Dependency Files** | None |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

### 10.5 `termination-mode` Label Safety Check

| Field | Value |
|---|---|
| **Change** | Termination logic reads `spot-optimizer/termination-mode` label as secondary safety check. If label says `"replacement"` and caller tries `"scaledown"`, termination is blocked and logged as conflict. **Post-conflict outcome**: The action is marked `FAILED`, the node is uncordoned (if it was cordoned), and no fallback is attempted — the system does not try an alternative termination mode. |
| **Current Logic** | Verify this safety check exists in `agent/actuator.py` `_terminate_node()`. Verify the conflict blocks termination AND marks the action failed AND uncordons the node. |
| **Primary File** | `agent/actuator.py` |
| **Dependency Files** | None |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

## Section 11 — Failure Handling

### 11.1 Orphan Cleanup Using Action Metadata

| Field | Value |
|---|---|
| **Change** | If the DB record of a replacement node is missing, use the `replacement_spot_instance_id` stored in the action metadata to terminate the orphan directly via EC2 API. |
| **Current Logic** | `backend/workers/tasks/auto_rebalancer.py` — verify if orphan cleanup uses action metadata. |
| **Primary File** | `backend/workers/tasks/auto_rebalancer.py` |
| **Dependency Files** | `backend/models/rebalancing_action.py` (action metadata field) |
| **Operation** | `MODIFY` (verify and enhance) |
| **UI Component** | None |
| **Name Mapping** | None |

**What to change**:
1. Verify orphan cleanup uses `replacement_spot_instance_id` from action metadata.
2. **`termination_mode="karpenter"` failure**: When Karpenter fails to terminate a node (e.g., consolidation stalls), the platform should detect the lingering node and fall back to direct EC2 termination. Add a timeout check in the resize guard or a periodic reconciliation task.
3. **TERMINATE phase split by mode**: The TERMINATE phase failure handling must differ by `termination_mode`: `"replacement"` → terminate orphan spot, uncordon original; `"scaledown"` → no orphan (ASG manages); `"karpenter"` → no ASG rollback path available, log and alert only.
4. **Uncordon-after-rollback**: When Phase 2 CORDON fails or Phase 2 DRAIN fails, explicitly uncordon the node before terminating the orphan spot instance. This step must be explicit, not assumed.

---

### 11.2 Circuit Breaker — Emergency Action Exclusion

| Field | Value |
|---|---|
| **Change** | Emergency actions (priority=10) should NOT increment the rollback counter for the circuit breaker. Gate rejections in Mode 3 (no action taken) should also NOT increment it. |
| **Current Logic** | `backend/services/circuit_breaker.py` (10829 bytes) — verify if emergency actions and gate rejections are excluded from rollback counting. |
| **Primary File** | `backend/services/circuit_breaker.py` |
| **Dependency Files** | `backend/workers/tasks/auto_rebalancer.py` (where rollback counting happens) |
| **Operation** | `MODIFY` |
| **UI Component** | Cluster Details → Health → Circuit Breaker Status. **Location**: Cluster detail page → Overview/Health section → Circuit breaker badge. |
| **Name Mapping** | None |

---

### 11.3 Circuit Breaker — State Transitions Detail

| Field | Value |
|---|---|
| **Change** | Three states: NORMAL → CONSERVATIVE (≥2 rollbacks in 1h, risk multiplier 1.3), CONSERVATIVE → HALT (≥3 rollbacks in 1h, ALL automation blocked except emergency), HALT → CONSERVATIVE (30min stable), CONSERVATIVE → NORMAL (2h stable). |
| **Current Logic** | `backend/services/circuit_breaker.py` — verify state transition thresholds and recovery timers match document. |
| **Primary File** | `backend/services/circuit_breaker.py` |
| **Dependency Files** | `backend/core/decision_engine.py` (reads circuit breaker state at pipeline) |
| **Operation** | `MODIFY` (verify matches doc) |
| **UI Component** | Cluster Details → Health → Circuit Breaker. Show current state and countdown to recovery. **Location**: Cluster detail → Overview/Health section. |
| **Name Mapping** | None |

---

### 11.4 Resize Guard — Full 2-Hour Monitoring

| Field | Value |
|---|---|
| **Change** | 2h post-execution monitoring: CPU stress (>85% for 10min → revert), pod restart spike (>baseline×2 → revert), memory pressure (>5 events in 2h → revert). Revert = re-patch to original requests (stateless only). Stateful → alert only, manual rollback. |
| **Current Logic** | `backend/workers/tasks/resize_guard_worker.py` — verify all three checks exist and revert mechanism works. |
| **Primary File** | `backend/workers/tasks/resize_guard_worker.py` |
| **Dependency Files** | `backend/services/rightsizing_service.py` (revert logic) |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | Cluster Details → Rightsizing tab → Proposal cards. Show resize guard status (Active/Passed/Failed). **Location**: Rightsizing tab. |
| **Name Mapping** | None |

---

## Section 6 Addendum — Optimizer Coordinator

### 6.3 Optimizer Coordinator — Phased Timing Strategy

| Field | Value |
|---|---|
| **Change** | Four tasks with different frequencies: `pool_optimization_worker` (30 min), `rightsizing_evaluation_worker` (24h), `evaluate_proposal_task` (event-driven, runs Gate 1+2), `execute_approved_proposal_task` (user/auto trigger). Phase requirements: pool optimization needs `OptimizerState` in `INITIAL_POOL_OPTIMIZATION`/`STABILIZATION`/`COOLDOWN`. Rightsizing needs ≥1h stabilization + ≥24h stability window. |
| **Current Logic** | `backend/workers/tasks/optimizer_coordinator_worker.py` (251 lines) — verify all 4 tasks exist with correct frequencies and phase guards. |
| **Primary File** | `backend/workers/tasks/optimizer_coordinator_worker.py` |
| **Dependency Files** | `backend/services/optimizer_coordinator.py`, `backend/models/optimizer_state.py` |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | Cluster Details → Settings → Optimization → Show current `OptimizerState` phase. **Location**: Settings tab → Optimization section → Phase indicator. |
| **Name Mapping** | Doc: `OptimizerState` phases (INITIAL_POOL_OPTIMIZATION, STABILIZATION, COOLDOWN, etc.) → Code: verify enum in `optimizer_state.py`. |

---

## Additional Questions Sections

### Compliance — Audit Log Retention (Issue #15)

| Field | Value |
|---|---|
| **Change** | Audit log records persist indefinitely with no automatic deletion. For GDPR compliance, a manual cleanup script is provided. Consider adding a retention policy. |
| **Current Logic** | `backend/services/audit_service.py` (5733 bytes), `backend/models/audit_log.py` — no TTL, no automatic archival, no partition strategy. |
| **Primary File** | `backend/services/audit_service.py` |
| **Dependency Files** | `backend/models/audit_log.py`, DB migration for partitioning |
| **Operation** | `MODIFY` |
| **UI Component** | Admin → Audit Log page. Add retention policy settings and archive functionality. **Location**: Admin section → Audit Logs page → Settings gear icon / Admin Settings → Compliance. |
| **Name Mapping** | None |

---

### Failure Notification — External Alerting (Issue #17)

| Field | Value |
|---|---|
| **Change** | The platform has no built-in Slack/PagerDuty/email alerting. It only exposes Prometheus metrics. Consider adding webhook-based notifications. |
| **Current Logic** | `backend/services/notification_service.py` (26883 bytes) — verify what notification channels exist. Likely only internal logging and metrics. |
| **Primary File** | `backend/services/notification_service.py` |
| **Dependency Files** | `backend/workers/tasks/alert_worker.py` |
| **Operation** | `MODIFY` (add webhook/external alerting) |
| **UI Component** | Admin → Notifications/Alerts settings. Add webhook configuration UI. **Location**: Admin section → Settings → Notifications → Add webhook URL, select events (Spot Interruption, Circuit Breaker State Change, Rebalance Failure). |
| **Name Mapping** | None |

---

### Instance Type Cascade Limit (Issue #18)

| Field | Value |
|---|---|
| **Change** | `_launch_spot_instance_direct()` slices the ML-ranked list to `[:6]`. In constrained regions, 6 types may all fail. The limit is hardcoded with no per-cluster override. |
| **Current Logic** | `backend/workers/tasks/auto_rebalancer.py` L408-463 — hardcoded `[:6]` slice. |
| **Primary File** | `backend/workers/tasks/auto_rebalancer.py` |
| **Dependency Files** | `backend/models/cluster.py` (`cluster_optimization_settings` table — add `max_instance_type_attempts` if not present) |
| **Operation** | `MODIFY` |
| **UI Component** | Cluster Details → Settings → Optimization → Advanced section. Add "Max instance type attempts" setting. **Location**: Cluster detail page → Settings tab → Optimization → Advanced settings. |
| **Name Mapping** | Doc: `max_instance_type_attempts` → Code: hardcoded `[:6]` in `auto_rebalancer.py`. Needs to read from cluster settings. |

---

### Savings Formula — Pre-Existing Spot Filter (Issue #3)

| Field | Value |
|---|---|
| **Change** | Realized savings formula should only count instances with `spot-optimizer/launched-by=platform` label. Additionally, verify the **`daily_cluster_stats`** table write path (daily per-cluster snapshots of savings, spot usage %, and cost) and the **`Cluster.realized_savings_monthly`** post-rebalance update hook (recalculated after every successful rebalance and periodically by Celery beat). |
| **Current Logic** | `backend/workers/tasks/savings_calculator.py` (6988 bytes) — verify if it filters by `spot-optimizer/launched-by=platform` tag. Verify `daily_cluster_stats` table insert exists. Verify `Cluster.realized_savings_monthly` is updated after successful rebalance in `auto_rebalancer.py`. |
| **Primary File** | `backend/workers/tasks/savings_calculator.py` |
| **Dependency Files** | `backend/workers/tasks/auto_rebalancer.py` (applies the label at launch time AND should update `realized_savings_monthly` post-rebalance), `backend/models/cluster.py` (`realized_savings_monthly` field, `daily_cluster_stats` model) |
| **Operation** | `MODIFY` (verify filter + aggregation both exist) |
| **UI Component** | Dashboard → Savings overview cards. Ensure displayed savings reflect only platform-launched instances. **Location**: Main dashboard → Savings KPI cards, Cluster detail page → Savings section. |
| **Name Mapping** | None |

**What to change**:
1. Verify `savings_calculator.py` filters to `spot-optimizer/launched-by=platform` instances only.
2. Verify `daily_cluster_stats` table receives daily snapshot inserts (savings, spot_usage_pct, cost) from the savings calculator or a Celery beat task.
3. Verify `Cluster.realized_savings_monthly` is updated in `auto_rebalancer.py` after every successful rebalance completion, and by the periodic Celery beat recalculation.

---

### Multi-Tenancy — Data Isolation

| Field | Value |
|---|---|
| **Change** | Data isolated by `organization_id` → `account_id` → `cluster_id` hierarchy. Each cluster has unique `API_KEY`. Redis keys include `cluster_id`. Node templates scoped to organization, shared across clusters in same org. |
| **Current Logic** | Verify DB queries always filter by `cluster_id` (and `organization_id` via joins). Verify Redis key isolation. |
| **Primary File** | `backend/models/cluster.py` |
| **Dependency Files** | `backend/models/node_template.py`, `backend/core/redis_client.py` |
| **Operation** | `MODIFY` (verify isolation exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

### HA & Scaling — Celery Emergency Queue

| Field | Value |
|---|---|
| **Change** | Dedicated `celery-emergency` worker for `emergency` queue with higher concurrency/priority. Ensures spot interruption handling never blocked by long rebalancing tasks. Redis single-instance (no HA) — restart rebuilds cooldowns/rankings automatically. |
| **Current Logic** | Verify `docker-compose.yml` or Kubernetes manifests have separate `celery-emergency` container targeting the `emergency` queue. |
| **Primary File** | `docker-compose.yml` (or K8s deployment manifests) |
| **Dependency Files** | `backend/workers/tasks/emergency_rebalancer.py` (routes to `emergency` queue) |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | None |
| **Name Mapping** | None |

---

### Upgrade Process — Agent & Backend

| Field | Value |
|---|---|
| **Change** | Agent upgrades via `POST /clusters/{id}/update-agent` (redeploys DaemonSet + Orchestrator). Backend rolling updates via K8s Deployment. DB migrations via Alembic (init container). WebSocket protocol backward-compatible — unknown action types logged as errors but don't crash. No strict version skew policy. |
| **Current Logic** | `backend/api/routes/cluster_routes.py` — verify `update-agent` endpoint exists. Verify Alembic migration runner. |
| **Primary File** | `backend/api/routes/cluster_routes.py` |
| **Dependency Files** | `agent/main.py` (version reporting in heartbeat/user-agent) |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | Cluster Details → Agent tab → Update Agent button. **Location**: Cluster detail → Agent section. |
| **Name Mapping** | None |

---

### Audit Log — Tamper Detection (SHA-256 Checksum)

| Field | Value |
|---|---|
| **Change** | SHA-256 tamper-evidence checksum computed on insert: `hash(actor_id + event + resource + timestamp + diffs)`. Periodic Celery task re-verifies integrity and alerts on mismatch. Audit log model is immutable (no `update()` method). |
| **Current Logic** | `backend/services/audit_service.py` — verify checksum generation. `backend/models/audit_log.py` — verify immutability and `checksum` column. |
| **Primary File** | `backend/services/audit_service.py` |
| **Dependency Files** | `backend/models/audit_log.py` |
| **Operation** | `MODIFY` (verify exists) |
| **UI Component** | Admin → Audit Logs → Show verification status badge per entry. |
| **Name Mapping** | None |

---

## Summary — Files to Change

| File | Operation | Changes Count |
|---|---|---|
| `agent/actuator.py` | MODIFY | 8 (termination_mode, PDB fail-safe, force-delete finalizers, NodePool path, NodePool auto-create, VolumeAttachment cleanup, drain grace, node resolution, termination-mode label check) |
| `agent/main.py` | MODIFY | 2 (thread restart backoff, component architecture verify) |
| `agent/config.py` | MODIFY | 1 (CLUSTER_NAME env var) |
| `agent/poller.py` | MODIFY | 1 (SpotPoller verify) |
| `agent/metrics_collector.py` | MODIFY | 1 (MetricsCollector verify) |
| `agent/heartbeat.py` | MODIFY | 1 (HeartbeatSender verify) |
| `agent/websocket_client.py` | MODIFY | 2 (emergency_command handling, HMAC verify) |
| `agent/pod_metrics_collector.py` | MODIFY | 1 (PodMetricsCollector verify — 358L, 5-min send interval) |
| `backend/routers/agents.py` | MODIFY | 2 (orchestrator auth, Issue #7 priority DESC ordering on polling endpoint) |
| `backend/workers/tasks/auto_rebalancer.py` | MODIFY | 7 (detach-not-decrement, mode 3 gates, node labels, instance cascade, concurrency control, action expiry, evaluation order) |
| `backend/workers/tasks/emergency_rebalancer.py` | MODIFY | 3 (termination_mode, standby-first path, drain override) |
| `backend/workers/tasks/termination_monitor.py` | MODIFY | 1 (emergency dedup key `emergency:dedup:{instance_id}` 2min TTL) |
| `backend/workers/tasks/resize_guard_worker.py` | MODIFY | 2 (pool risk signals, full 2h monitoring) |
| `backend/workers/tasks/discovery.py` | MODIFY | 3 (RC3 guard reset, RC4 ghost cleanup, cluster grace periods) |
| `backend/workers/tasks/pricing_worker.py` | MODIFY | 2 (partial staleness, emergency pricing refresh) |
| `backend/workers/tasks/savings_calculator.py` | MODIFY | 2 (platform-label filter, daily_cluster_stats + realized_savings_monthly verify) |
| `backend/workers/tasks/sqs_consumer.py` | MODIFY | 1 (dedup) |
| `backend/workers/tasks/optimizer_coordinator_worker.py` | MODIFY | 1 (phased timing verify) |
| `backend/workers/tasks/control_plane_loop.py` | MODIFY | 1 (8-step verify) |
| `backend/services/aws_pricing_service.py` | MODIFY | 1 (partial staleness) |
| `backend/services/blacklist_service.py` | MODIFY | 4 (cascade protection, backoff caps, tiered blacklist, Redis hygiene) |
| `backend/services/circuit_breaker.py` | MODIFY | 2 (emergency exclusion, state transition verify) |
| `backend/services/observability_logger.py` | MODIFY | 1 (DB persistence) |
| `backend/services/notification_service.py` | MODIFY | 1 (external alerting) |
| `backend/services/audit_service.py` | MODIFY | 2 (retention policy, tamper detection verify) |
| `backend/services/karpenter_service.py` | MODIFY | 2 (three-mode toggle, Redis keys verify) |
| `backend/services/optimizer_coordinator.py` | MODIFY | 2 (synergy mode gates, Mode 3 downgrade path from combined → Gate 2 only) |
| `backend/services/execution_controller.py` | MODIFY | 1 (termination_mode) |
| `backend/services/workload_inspector.py` | MODIFY | 1 (node classification verify) |
| `backend/services/diversity_enforcer.py` | MODIFY | 1 (diversification constraints verify) |
| `backend/services/cooldown_controller.py` | MODIFY | 1 (10 cooldown types verify) |
| `backend/services/instability_propagator.py` | MODIFY | 1 (cross-cluster propagation verify) |
| `backend/services/rightsizing_service.py` | MODIFY | 2 (two-gate system, settings verify) |
| `backend/core/decision_engine.py` | MODIFY | 3 (pool rankings miss, 15-step pipeline, volatility guard) |
| `backend/core/action_executor.py` | MODIFY | 1 (HMAC signing verify) |
| `backend/core/ev_model.py` | MODIFY | 1 (EV scoring verify) |
| `backend/models/agent_action.py` | MODIFY | 1 (REMOVE_POD_FINALIZERS enum) |
| `backend/models/cluster.py` | MODIFY | 2 (max_instance_type_attempts, rightsizing settings) |
| `backend/models/audit_log.py` | MODIFY | 1 (checksum column verify) |
| `backend/models/optimizer_state.py` | MODIFY | 1 (trust phase verify) |
| `backend/scrapers/spot_advisor_scraper.py` | MODIFY | 1 (versioning key) |
| `backend/utils/aws/asg.py` | MODIFY | 1 (detach-not-decrement verify) |
| `backend/api/routes/cluster_routes.py` | MODIFY | 2 (WebSocket invalidation, update-agent endpoint) |

---

## UI Components — Enhancement Summary

| # | Component | Location in UI | Change Description |
|---|---|---|---|
| 1 | Optimization Settings | Cluster Detail → Settings → Optimization | Show Mode 1/2/3 state clearly; lock `rightsizing_target` to "spot" when both toggles ON (synergy) |
| 2 | Optimization Profile | Cluster Detail → Settings → Optimization | Dropdown: COST_FIRST / BALANCED / NO_DOWNTIME_FIRST |
| 3 | Karpenter Mode Toggle | Cluster Detail → Settings → Karpenter | Three-way toggle: Off / Insights Only (dry_run) / Auto-Optimize (auto) |
| 4 | Agent Health Panel | Cluster Detail → Agent tab | Show per-thread restart counts, DaemonSet vs Deployment status, max restart status |
| 5 | Circuit Breaker Badge | Cluster Detail → Overview / Health | Show NORMAL / CONSERVATIVE / HALT state + recovery countdown |
| 6 | Rightsizing Proposals | Cluster Detail → Rightsizing tab | Show classification (OVERSIZED/UNDERSIZED/RIGHT_SIZED), gate pass/fail reason, resize guard status |
| 7 | Rightsizing Settings | Cluster Detail → Settings → Rightsizing | 5 editable settings: target, history window, frequency, cooldown, headroom multiplier |
| 8 | Pool Rankings → Blacklisted | Cluster Detail → Pool Rankings | Show blacklist tier, reason, TTL remaining, cascade protection status |
| 9 | Savings KPI Cards | Main Dashboard + Cluster Detail | Verify savings reflect only `spot-optimizer/launched-by=platform` instances |
| 10 | Audit Logs | Admin → Audit Logs | Add retention policy config, decision audit history beyond 24h, tamper verification badge |
| 11 | Notifications Config | Admin → Settings → Notifications | Add webhook URL config for external alerting (Slack, PagerDuty, email) |
| 12 | Node Action Menu | Cluster Detail → Nodes tab | Add "Remove Pod Finalizers" button for stuck nodes |
| 13 | Node Detail Panel | Cluster Detail → Nodes tab → Expand | Show template-related labels, classification badge (Stateless/Stateful) |
| 14 | Node Standby Badge | Cluster Detail → Nodes tab | Show standby node indicator when `maintain_standby=True` |
| 15 | Diversification Settings | Cluster Detail → Settings → Advanced | `diversify_pools` toggle + `max_family_diversification_cap_pct` slider |
| 16 | Advanced Settings | Cluster Detail → Settings → Advanced | Add `max_instance_type_attempts` configurable setting (currently hardcoded to 6) |
| 17 | Pricing Staleness | Cluster Detail → Health badges | Show "Pricing partially stale" warning when partial refresh detected |
| 18 | Pool Rankings Health | Cluster Detail → Health badges | Show "Pool rankings stale" when Redis cache miss |
| 19 | Pool Pressure Indicator | Cluster Detail → Health badges | Show SYSTEMIC escalation from InstabilityPropagator |
| 20 | Risk Ceiling Indicator | Cluster Detail → Overview | Show effective ceiling with contributing factors (profile × volatility × trust) |
| 21 | Optimizer Phase | Cluster Detail → Settings → Optimization | Show current `OptimizerState` phase indicator |
| 22 | Agent Disconnect | Cluster Detail → Settings → Agent | Disconnect button should also force-close WebSocket connections |
| 23 | Agent Update | Cluster Detail → Agent tab | Update Agent button to redeploy DaemonSet + Orchestrator |
| 24 | Karpenter Install/Uninstall | Cluster Detail → Karpenter tab | Install/Uninstall buttons with status feedback |
