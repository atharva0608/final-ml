# Diagnostic Guide: Stale Data, Unmanaged States, and UX Issues

To systematically investigate stale data, unmanaged states, rebalancing failures, UI update delays, and user experience problems, ask targeted questions about PostgreSQL, Redis, and backend logic. The checklist below is grouped by component.

> **Current Architecture Note (2026-03-30):**
> - All three pool-selection contexts (UI alternatives, action creation, auto-rebalancer execution) now use the unified `PoolRankingService.rank_pools_for_node()` function with the same sort key: `expected_value = savings_pct × (1 − risk_probability)` DESC.
> - The 9-gate `DecisionEngine.rank_for_node()` cascade has been **removed** from `decision_engine.py`.
> - Dead settings have been removed from DB models: `conservative_mode_enabled`, `optimization_target` (from `ClusterOptimizationSettings`), `show_ondemand_only` (from `StatefulRules`), `risk_threshold` (from `NodeTemplateConstraints` schema).
> - NodeTemplate constraints (`allowed_families`, `excluded_families`, `allowed_zones`, `cross_az_rebalance`) are now applied in the rebalancer via `rank_pools_for_node()` — previously they were UI-only.
> - Agent image tag policy changed: `tag: latest` → `tag: "{{ .Chart.AppVersion }}"`, `pullPolicy: Always` → `pullPolicy: IfNotPresent` (N4 fix). Backend logs a version-mismatch warning (not a rejection) when a connecting agent's version ≠ `EXPECTED_AGENT_VERSION = "1.0.0"` (N3 fix).

---

## 1. PostgreSQL (Database) Questions

### 1.1 Cluster & Instance State

**Is the `Cluster` status correct?**
- `status = 'ACTIVE'` for clusters that should be rebalancing?
- `agent_installed = 'Y'` for clusters where the DaemonSet is running?
- `last_heartbeat` within the last 5 minutes?

**Are there stale instances?**
- Count of `Instance` rows with `state = 'running'` but EC2 instance no longer exists (should be marked terminated by reconciliation).
- Count of `Instance` rows with `lifecycle = 'SPOT'` and `state = 'pending'` older than 15 minutes (orphans).

**Are rebalancing actions stuck?**
- Actions with `status = 'in_progress'` or `'waiting_agent'` and `started_at < now() - 45 minutes`.
- Actions with `current_state` unchanged for longer than the per-state timeout (e.g., `draining_pods` > 20 min).
- Actions with `error_message` containing `MISSING_USERDATA`, `PDB_VIOLATION_MAX_RETRIES`, or `InsufficientInstanceCapacity`.
- Actions with `error_message = 'ZOMBIE_EC2_TERMINATED'` indicate the source K8s node was gone (Z4 fix: CORDON returned 404 → backend auto-terminated the ghost EC2 and cleared associated Redis keys). These are self-healing but repeated occurrences suggest stale EC2 data.
- **Stuck cordoned nodes (Z2 fix):** `recovery_monitor` runs `recover_stuck_cordoned_nodes` every 60s to detect failed actions where a cordon was applied but never uncordoned (stuck > 20 min past cordon, or failed with `step_2_cordon` in metadata). It dispatches a new `UNCORDON_NODE` AgentAction automatically. If nodes remain cordoned after recovery attempts, check that the cluster agent is online (heartbeat < 5 min) and no pending UNCORDON already exists.

**Are there orphaned agent actions?**
- `AgentAction` rows with `status = 'PICKED_UP'` and `picked_up_at < now() - 15 minutes` (agent may have crashed).
- **Note (BUG-9 fix):** `reset_stale_agents` now auto-cancels all `PENDING`/`PICKED_UP` `AgentAction`s when a cluster's agent goes offline (heartbeat >5 min). Lingering `PICKED_UP` rows therefore indicate either the agent is still live OR the `reset-stale-agents` Celery task is not running.

---

### 1.2 Pool & Ranking Data

**Is `spot_advisor_data` up-to-date?**
- Latest `updated_at` timestamp for a known region.
- Count of rows per region — should match the AWS Spot Advisor feed.

**Are `global_pool_ema` and `pool_risk_scores` tables populated?**
- Any missing entries for instance types that are actively used?

---

### 1.3 Rightsizing & Auto-Scaling

**Are rightsizing recommendations stale?**
- `RightSizingRecommendation` rows with `generated_at` older than 24 hours for active clusters.

**Are auto-scaling decisions based on stale metrics?**
- Check `Instance.cpu_util` and `memory_util` — are they NULL for many nodes?

---

## 2. Redis Questions

### 2.1 Locks & Concurrency

**Is the cluster lock held for too long?**
- Key: `rebalance:lock:{cluster_id}`
- TTL remaining vs. expected action duration.
- Any locks without a heartbeat (no recent `EXPIRE`)?

**Are there stale `node_action` locks?**
- `lock:node_action:{cluster_id}` with TTL > 1200s and no active drain (Z10 fix raised this timeout from 180s to 1200s to accommodate longer drain operations — a TTL significantly above 1200s indicates a stuck lock).

---

### 2.2 Cooldowns & Throttling

**Is a cluster stuck in cooldown?**
- `spot:cooldown:action:{cluster_id}` TTL — is it much longer than expected?
- `spot:stabilization_lock:{cluster_id}` still present after 90 seconds.

**Are per-instance cooldowns preventing rebalancing?**
- `spot:rebalanced:instance:{instance_id}` — does it expire as expected?
- `rebalance_failures:{instance_id}` — failure count and last failure timestamp.

---

### 2.3 Cache Freshness

**Is the pool cache stale?**

| Key | Freshness Signal |
|---|---|
| `market_view_cache:{region}` | Check `last_updated` field inside the JSON payload |
| `global_pool_rankings:{region}` | Compare `generated_at` with current time — >70 minutes = stale |
| `ranking_stale_warned:{region}` | Presence indicates CRITICAL log was emitted |

**Are spot prices fresh?**
- `spot_price:{region}:{az}:{type}` — TTL remaining (should be < 600 s).
- Any missing keys for instance types that should have spot prices?

**Are dry-run cache entries blocking valid pools?**
- `dry_run:{type}:{az}` with value `fail` — **fail TTL is 60 s (1 min, N8 fix — was 300s)**, pass TTL is 900 s (15 min).
- Check if capacity actually exists now (fail entries expire faster to allow re-check).
- The rebalancer checks dry-run cache at execution time and runs synchronous dry-run for uncached pools (max 5 API calls per cycle to avoid throttling).

---

### 2.4 Agent & Node State

**Are agents reporting correctly?**
- `node_joined:{instance_id}` — present for newly launched spot instances?
- `action_heartbeat:{action_id}` — being refreshed by **two writers**: the backend Celery worker every ~15s (each rebalancer cycle) AND the in-cluster agent every 30s via `_action_heartbeat_loop()` in `actuator.py` (N5 fix). If both writers stop for >120s, the action is considered stale. A missing key indicates both have stopped.

**Are there stuck spot-interruption deduplications?**
- `emergency:dedup:{instance_id}` — TTL should be 300 s (Problem #20 fix, was 120s). This is the **event-level dedup key** — it suppresses duplicate interruption signals from SQS, IMDS, and EventBridge for the same instance. Unexpectedly long TTL means a dedup key from a different context leaked.
- `emergency:rebalance:{instance_id}` — per-node **action lock**, TTL **120 s** (Z13 fix, was 600s). Prevents a second emergency rebalance from starting while the first is still running. If present and the expected emergency rebalance isn't running, check for a Celery worker crash that held the lock without completing.

**Is `spot:prevent_orphan_termination` blocking orphan cleanup?**
- `spot:prevent_orphan_termination:{instance_id}` — TTL 3600s (1 hour). Set manually by operators via Redis CLI SETEX for debugging. If unexpectedly present, an operator may have forgotten to clean up. Key expires automatically after 1 hour.

---

### 2.5 Blacklists

**Are pools globally blacklisted unnecessarily?**
- `risky_pools:{region}` — size and expiry of `risky_pool_meta:{pool_key}`.
- `blacklist_failures:{pool_key}` — failure count and last failure reason.

**Are per-cluster blocks misconfigured?**
- `spot:launch_blocked:{cluster_id}:{type}:{az}` — two TTL tiers:
  - `spot_join_timeout_minutes × 60` (default 1800s / 30 min, N7 fix — was hardcoded 300s) — set on no-join timeout (spot didn't join K8s in time).
  - 1800 s (30 min) — set after ≥ 3 capacity failures for that `(type, az)` in the cluster.

---

## 3. Backend Logic (Celery, API, Services)

### 3.1 Celery Workers & Tasks

**Is the auto-rebalancer task running on schedule?**
- Check Celery beat logs for `auto-rebalancer-every-15-secs`.
- Any workers stuck or deadlocked?

**Is `reset_stale_agents` performing full cleanup on agent loss?**
- Since BUG-9: on agent offline, this task should cancel `PENDING`/`PICKED_UP` `AgentAction`s, fail `in_progress`/`waiting_agent` `RebalancingAction`s with `AGENT_WENT_OFFLINE`, and delete `action_heartbeat:{id}` Redis keys.
- If stuck actions persist long after an agent went offline, verify the task is running and check for DB errors in its log output.

**Are there long-running tasks blocking others?**
- Celery queue length and active task counts for `auto_rebalancer`, `recovery_monitor`, `cache_builder`.

**Is the pool cache builder completing successfully?**
- Task: `build_global_pool_cache_task`
- Last run timestamp and duration.
- Any exceptions such as `JSONDecodeError` or DB connection issues.

---

### 3.2 API & Gateway

**Are WebSocket connections stable?**
- Number of connected agents per cluster.
- Any frequent disconnections or reconnections?
- With the two-tier message buffer (BUG-4/N6 fix): critical messages (`action_result`, `heartbeat`) go to an unbounded queue and are never dropped; metrics go to a ring buffer (maxlen=200, oldest dropped when full). If action results appear missing after a reconnect, verify the critical queue is being flushed — check agent logs for `flush_buffer` and `critical_queue` entries.

**Is the agent version matching backend expectations?**
- Check backend logs for `agent version mismatch` warnings on registration (N3 fix). A mismatch is non-blocking but indicates a stale agent image is deployed. Check Helm chart `image.tag` — should be `{{ .Chart.AppVersion }}` (not `latest`).

**Are high-frequency endpoints causing log floods?**
- Check request rates for:
  - `GET /api/v1/agents/actions/pending`
  - `POST /api/v1/agent-metrics/batch`
- Are these endpoints properly excluded from verbose logging?

---

### 3.3 State Machine & Rollback

**Are state transitions atomic?**
- Look for actions in `in_progress` with mismatched `current_state` and `status` fields.
- Check for optimistic lock failures (`lock_version` conflicts).

**Is rollback logic correctly cleaning up resources?**
- Verify that when an action fails, the replacement spot instance is terminated and metadata is cleared.
- Check for leftover `asg_name_used` in metadata without a corresponding termination.

**Is PDB respect configured correctly for drain?**
- Check `StatelessRuntimeRules.respect_pdb_enabled` for the cluster. When `True` (default), drain respects PDBs (5 retries, 10s backoff, fails with `PDB_VIOLATION_MAX_RETRIES`). When `False`, the backend passes `force=True` in the DRAIN_NODE payload, bypassing PDB checks entirely (N1 fix).
- If drains are timing out or failing with `PDB_VIOLATION_MAX_RETRIES` unexpectedly, verify this setting.

---

### 3.4 Pool Ranking & Filtering

**Is `rank_pools_for_node` returning unexpected empty lists?**
- Enable debug logging to see which filters eliminated all pools.
- Filters applied (in order): blacklist, vCPU floor, memory floor, architecture, risk ceiling, allowed/excluded families (NodeTemplate), allowed zones, cross-AZ restriction, occupancy (running+pending instances), family diversification cap (max 2 per family when `diversify_pools=True`), `min_savings_percent` threshold (N2 fix — now enforced).
- All contexts (UI, action creation, rebalancer execution) use this same function.
- Check `pool_audit:{cluster_id}:{node}` keys for rejection reason breakdowns.

**Did `rank_pools_for_node` abort due to fallback specs?**
- If the source node's instance type is not in the spec table, `_lookup_specs()` returns `is_fallback=True` and the function logs CRITICAL and returns an empty list (NEW-2 fix). Check logs for `CRITICAL: fallback specs` messages.

**Are node specifications correctly derived?**
- For a problematic node, log the `_lookup_specs` result — does it match what AWS reports for that instance type?
- `rank_pools_for_node` derives `min_vcpu_required` and `min_memory_required` from `node_info.resource_profile`.

**Is `rank_pools_for_size` (legacy) causing issues in secondary paths?**
- `rank_pools_for_size` is still used for: standby launches, opportunistic conversions, OD→Spot Pass 1/2 in some paths.
- These paths do **not** apply NodeTemplate constraints (families, zones, cross-AZ) — only `rank_pools_for_node` does.

---

### 3.5 User Experience (UI)

**Why does the UI show different pools than what the system attempts?**
- UI alternatives and action creation both call `rank_pools_for_node()` — the same function with the same sort key (`expected_value`).
- Differences can still occur due to: timing (pool cache refreshed between UI view and action creation), occupancy changes (new instances launched/terminated between views), and dry-run/launch-blocked filters applied only at execution time.
- Compare timestamps: `computed_at` in the `/alternatives` response vs. `created_at` on the action.

**Why do UI updates feel slow?**
- Check Redis latency for `market_view_cache` and `global_pool_rankings`.
- Are there many pending actions or large pagination sizes in API responses?

**Why are savings estimates inaccurate?**
- Verify that the UI uses the **source node's on-demand price** (not the pool's own OD price).
- Check if `source_od_price` is ever `0` (missing from DB or Redis).

---

## 4. Cross-Component Checks

| Area | What to Check |
|---|---|
| **Time synchronisation** | Are all services (backend, Redis, agents) using NTP? Clock skew can cause TTL mismatches. |
| **Log aggregation** | Are CRITICAL and ERROR logs being alerted? e.g. `[DE] Global pool rankings for region %s are %d minutes old!` |
| **Resource limits** | Are Celery workers memory/CPU bound? Is Redis at its memory limit (check eviction policy)? |
| **Cluster re-onboarding** | After deleting and re-adding a cluster, verify no stale Redis keys remain from the old cluster (BUG-5 fix: `DELETE /clusters/{id}` now performs comprehensive Redis cleanup via direct key deletion + wildcard scan-delete). If stale keys persist, check if deletion completed successfully. |

---

## 5. Removed Settings (No Longer in DB)

The following settings have been removed from DB models and should **not** be queried or configured:

| Setting | Former Table | Removed Because |
|---|---|---|
| `conservative_mode_enabled` | `ClusterOptimizationSettings` | Was never read by any active code path |
| `optimization_target` | `ClusterOptimizationSettings` | `"spot"` / `"cost"` / `"risk"` — no sort or filter ever used it |
| `show_ondemand_only` | `StatefulRules` | Was never read by any active code path |
| `risk_threshold` | `NodeTemplateConstraints` (schema) | Overridden by `OptimizationStrategy.risk_ceiling_percent` everywhere |

A migration (`20260328_drop_unused_settings_columns.py`) drops the `conservative_mode_enabled` and `optimization_target` columns from `cluster_optimization_settings` and `show_ondemand_only` from `stateful_rules`.

---

## 6. Quick-Reference: Key Redis Keys

| Key Pattern | Purpose | Normal TTL |
|---|---|---|
| `rebalance:lock:{cluster_id}` | Cluster-level concurrency lock | 2700 s (renewed every 60s; matches 45-min stale action threshold — NEW-3 fix) |
| `spot:cooldown:action:{cluster_id}` | Inter-action cooldown | 3600 s (configurable) |
| `spot:stabilization_lock:{cluster_id}` | Post-action grace period | 60–90 s |
| `spot:rebalanced:instance:{id}` | Per-instance rebalance cooldown | 86400 s (24 h) |
| `rebalance_failures:{id}` | Exponential backoff counter | 86400 s |
| `spot:launch_blocked:{cluster_id}:{type}:{az}` | No-join timeout / capacity failure block | `spot_join_timeout_minutes × 60` (no-join, default 1800s) or 1800 s (≥3 failures) |
| `market_view_cache:{region}` | Unified pool cache with pricing | 3600 s (1 h) |
| `global_pool_rankings:{region}` | Fallback pool cache | 3900 s (65 min) |
| `dry_run:{type}:{az}` | Capacity dry-run result | 900 s (pass) / 60 s (fail — N8 fix, was 300s) |
| `blacklist_failures:{pool_key}` | Launch failure counter | 6 h |
| `risky_pools:{region}` | Global blacklist set of pool keys | varies per pool |
| `risky_pool_meta:{pool_key}` | Blacklist metadata (reason, timestamp) | matches pool blacklist duration |
| `node_joined:{instance_id}` | Spot node K8s join confirmation | set on join, cleared after action |
| `action_heartbeat:{action_id}` | Action liveness signal | 120 s (refreshed by backend Celery worker every ~15s AND by agent `_action_heartbeat_loop()` every 30s — N5 fix; dual-writer) |
| `emergency:dedup:{instance_id}` | Spot interruption dedup | 300 s (5 min — Problem #20 fix; was 120s) |
| `emergency:rebalance:{instance_id}` | Per-node emergency rebalance lock | 120 s (Z13 fix; was 600s) |
| `pool_audit:{cluster_id}:{node}` | Filter rejection stats from `rank_pools_for_node` | 300 s |

---

By systematically answering these questions, you can pinpoint the root cause of stale data, unmanaged states, rebalancing failures, and UI inconsistencies. The answers will guide you to the exact code or configuration that needs fixing.
