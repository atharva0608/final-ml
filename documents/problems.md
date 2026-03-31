# Full Remediation Plan — All Open Issues

> **Status as of 2026-03-30: ALL 19 FIXES IMPLEMENTED ✅**
>
> Based on the audit: 10 previously fixed, 6 false positives/deferred, 19 items remediated in this session.
> Every fix has been applied to the codebase and validated with zero lint/compile errors.

---

## P0 — Critical Fixes ✅ ALL DONE

### N9 — Spec fallback `(0, 0.0)` skips vCPU floor → undersized replacement ✅

**File:** `cache_builder.py` line 260 and `pool_ranking_service.py` lines 2269–2272

**Problem:** Unknown instance type returns `(0, 0.0, 'amd64')`. Since `min_vcpu = 0`, the floor check `if min_vcpu > 0` is skipped entirely. Any pool passes. A 72-vCPU node can get replaced by a 2-vCPU instance.

**Fix — two changes:**

`cache_builder.py` — log and abort instead of returning bad defaults:
```python
vcpu, memory_gb, arch = _lookup_specs(itype)
if vcpu == 0:
    logger.critical(
        "Unknown instance type %s — spec lookup returned (0,0). "
        "Skipping pool ranking to prevent undersized replacement.", itype
    )
    return []  # abort ranking entirely for this node
```

`pool_ranking_service.py` — defensive check even if the above is bypassed:
```python
# Before ranking loop, validate source node specs are usable
if node_info.resource_profile.min_vcpu_required == 0:
    logger.critical("min_vcpu=0 for node %s — refusing to rank pools", node_name)
    return []
```

**Time:** 15 minutes. No test needed beyond confirming the log fires for an unknown type.

---

### BUG-1 + BUG-2 + N6 + BUG-4 — WebSocket disconnect loses action results / drain state ✅

These four are the same root problem: the agent's WebSocket buffer is FIFO with no priority, action results compete with metrics, and there is no delivery acknowledgement. Fixing them together is simpler than fixing each separately.

**Files:** `agent/websocket_client.py`, `agent/actuator.py`

**Fix — three focused changes:**

**Change 1 — separate queues by criticality in `websocket_client.py`:**
```python
import queue

class WebSocketClient:
    def __init__(self, ...):
        # Critical: action results, state transitions (never dropped)
        self.critical_queue = queue.Queue()  # unbounded — these must not be lost
        # Best-effort: metrics, heartbeats (drop oldest when full)
        self.metrics_buffer = collections.deque(maxlen=200)  # ring buffer

    def buffer_message(self, message: dict):
        msg_type = message.get("type", "")
        if msg_type in ("action_result", "action_heartbeat"):
            self.critical_queue.put(message)   # never dropped
        else:
            self.metrics_buffer.append(message)  # oldest dropped when full

    def _flush_on_reconnect(self):
        # Send critical messages first
        while not self.critical_queue.empty():
            self._send(self.critical_queue.get())
        # Then metrics (best-effort)
        for msg in self.metrics_buffer:
            self._send(msg)
        self.metrics_buffer.clear()
```

**Change 2 — action result retry in `actuator.py`:** If the WebSocket send fails, retry via HTTP fallback before giving up:
```python
def report_action_result(self, action_id, result):
    success = self.ws_client.send({"type": "action_result", ...})
    if not success:
        # Fallback: HTTP POST directly to backend
        try:
            requests.post(
                f"{BACKEND_URL}/api/v1/agents/actions/{action_id}/result",
                json=result,
                headers={"Authorization": f"Bearer {API_KEY}"},
                timeout=10
            )
            logger.info("Action result sent via HTTP fallback for %s", action_id)
        except Exception as e:
            logger.error("HTTP fallback also failed for action %s: %s", action_id, e)
            # Message already in critical_queue — will flush on reconnect
```

The agent already calls `POST /api/v1/agents/actions/{action_id}/result` normally (confirmed in `agent.md`). This just reuses the same endpoint as a fallback.

**Change 3 — action context survives reconnect in `actuator.py`:** Store the current in-progress action ID in memory. On reconnect, send a status ping so the backend knows the agent is still alive and working:
```python
class ActionExecutor:
    def __init__(self):
        self._current_action_id = None  # set when action starts, cleared on complete

    def execute(self, action):
        self._current_action_id = action["id"]
        try:
            # ... existing logic ...
        finally:
            self._current_action_id = None

    def on_reconnect(self):
        # Called by websocket_client when connection restores
        if self._current_action_id:
            self.ws_client.send({
                "type": "action_still_running",
                "action_id": self._current_action_id,
                "timestamp": datetime.utcnow().isoformat()
            })
```

Backend handler for `action_still_running` just refreshes `action_heartbeat:{id}` in Redis and keeps the action in `in_progress` — prevents false rollback while drain is still running.

**Time:** 2–3 hours total for all three changes. They are logically one fix.

---

## P1 — This Week Fixes ✅ ALL DONE

### Z1 — Zombie OD cleanup task never runs (wrong function name in beat) ✅

**File:** `backend/workers/app.py` lines 53–55

**Problem:** Beat schedule points to `cleanup_zombie_nodes` but the actual function is `cleanup_zombie_od_instances_task`.

**Fix — one line change:**
```python
'zombie-od-cleanup-hourly': {
    'task': 'backend.workers.tasks.health.cleanup_zombie_od_instances_task',
    'schedule': 3600.0,  # hourly is fine — these are billing zombies not operational ones
},
```

Keep the existing `zombie-cleanup-every-2-mins` entry pointing to `cleanup_zombie_nodes` if that task does something else. Just add the correct entry for the OD-specific task.

**Time:** 5 minutes.

---

### Z3 — `force_delete_node()` missing self-guard ✅

**File:** `agent/actuator.py` line 266

**Problem:** `cordon_node()` and `drain_node()` have the self-guard. `force_delete_node()` does not.

**Fix:**
```python
def force_delete_node(self, payload):
    node_name = payload.get('node_name')
    if node_name == self._my_node:
        logger.error(
            "Refusing force_delete on own node %s — SELF_DELETE_ATTEMPT", self._my_node
        )
        return {"status": "failed", "error": "SELF_DELETE_ATTEMPT"}
    # rest of existing logic unchanged
```

**Time:** 5 minutes.

---

### Z5 — `sync_cluster_pools_task` not in beat schedule + race condition ✅

**File:** `backend/workers/app.py` and `health.py`

**Problem 1:** Task exists but no beat entry.
**Problem 2:** Sync re-adds pools whose most recent launch failed within the last 5 minutes (race with `srem`).

**Fix — beat entry:**
```python
'sync-cluster-pools-every-30-mins': {
    'task': 'backend.workers.tasks.health.sync_cluster_pools_task',
    'schedule': 1800.0,
},
```

**Fix — race guard in `sync_cluster_pools_task`:**
```python
def sync_cluster_pools(db, redis, cluster_id):
    live_pools = set(...)  # existing logic — get running/pending SPOT instances

    # Guard: exclude pools with a recent launch failure (srem'd in last 5 min)
    # Use the existing dry_run fail cache as a proxy — if dry_run is 'fail', skip
    filtered_pools = set()
    for pool in live_pools:
        instance_type, az = pool.split(":")
        dr_key = f"dry_run:{instance_type}:{az}"
        if redis.get(dr_key) == b"fail":
            continue  # skip — recently failed, srem was correct
        filtered_pools.add(pool)

    redis.delete(f"cluster_pools:{cluster_id}")
    if filtered_pools:
        redis.sadd(f"cluster_pools:{cluster_id}", *filtered_pools)
```

**Time:** 20 minutes.

---

### N1 — `respect_pdb_enabled` setting wired to nothing ✅

**Files:** `agent/actuator.py`, backend action creation path

**Problem:** PDB check function exists in the agent but `respect_pdb_enabled` is never read. The `force` parameter controls PDB behaviour but is never set based on the user's setting.

**Fix — backend side:** When creating the DRAIN_NODE action, read `respect_pdb_enabled` from cluster settings and include it in the action payload:
```python
# In auto_rebalancer.py — when building DRAIN_NODE AgentAction payload:
cluster_settings = get_cluster_settings(cluster_id)
action_payload = {
    "node_name": node_name,
    "force": not cluster_settings.respect_pdb_enabled,  # force=True means ignore PDB
    "drain_timeout_minutes": cluster_settings.drain_timeout_minutes,
}
```

**Fix — agent side:** The agent's `drain_node()` already receives `force` in the payload and already has `check_pdb_violation()`. The plumbing just needs to connect them. Verify `drain_node()` uses `payload.get('force', False)` to set its behaviour — if it does, the backend change above is the only change needed.

**Time:** 1 hour including verification.

---

### N2 — `min_savings_percent` never enforced in pool ranking ✅

**File:** `backend/services/pool_ranking_service.py` line 2408

**Problem:** Filter only removes `savings_pct < 0`. Never compares against `min_savings_percent`.

**Fix:** Load the setting and add one filter:
```python
def rank_pools_for_node(self, node_info, cluster_id, ...):
    # Load optimization strategy (already loaded elsewhere — reuse)
    min_savings = getattr(optimization_strategy, 'min_savings_percent', 0) or 0

    for pool in candidate_pools:
        if pool.savings_pct <= 0:
            continue
        if pool.savings_pct < min_savings:  # new filter
            continue
        # ... rest of existing ranking logic
```

If `optimization_strategy` is not already loaded in this function, load it with a single DB query at the top of the function. It is already loaded in the API layer — just pass it through or load it here.

**Time:** 30 minutes including the query.

---

### N5 — `action_heartbeat` set by backend Celery only — worker crash triggers mass rollback ✅

**Files:** `agent/actuator.py`, backend `agents.py`

**Problem:** Agent never writes `action_heartbeat`. If the Celery worker backing up for >120s, all actions are simultaneously marked stale and rolled back.

**Fix — agent sends heartbeat pings during execution:**

Add a new lightweight HTTP endpoint on the backend:
```python
# backend/api/agents.py — new endpoint
@router.post("/api/v1/agents/actions/{action_id}/heartbeat")
def action_heartbeat(action_id: str, ...):
    _redis.setex(f"action_heartbeat:{action_id}", 120, str(time.time()))
    return {"ok": True}
```

In the agent's `actuator.py`, refresh heartbeat every 30s while an action is running:
```python
def _heartbeat_loop(self, action_id: str, stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            requests.post(
                f"{BACKEND_URL}/api/v1/agents/actions/{action_id}/heartbeat",
                headers={"Authorization": f"Bearer {API_KEY}"},
                timeout=5
            )
        except Exception:
            pass  # best-effort — backend Celery still writes as backup
        stop_event.wait(30)

def execute(self, action):
    stop_hb = threading.Event()
    hb_thread = threading.Thread(
        target=self._heartbeat_loop, 
        args=(action["id"], stop_hb), 
        daemon=True
    )
    hb_thread.start()
    try:
        # existing execution logic
    finally:
        stop_hb.set()
        hb_thread.join(timeout=5)
```

The backend Celery heartbeat remains as a secondary fallback. Now both write to the same key — whichever runs wins, which is fine since they both write the same thing.

**Time:** 1.5 hours.

---

### N7 — `launch_blocked` no-join TTL (300s) mismatches join timeout (30 min) ✅

**File:** `auto_rebalancer.py` line 2942

**Problem:** Hardcoded 300s. System waits up to 30 minutes for join. Between minute 5 and 30, same pool can be launched again → orphan EC2.

**Fix — one line:**
```python
# Get the configured join timeout for this cluster
_join_timeout_s = (
    cluster_settings.spot_join_timeout_minutes or 30
) * 60

# Use it for the launch_blocked TTL instead of hardcoded 300
_redis.setex(
    f"spot:launch_blocked:{cluster_id}:{instance_type}:{az}",
    _join_timeout_s,   # was hardcoded 300
    "no_join"
)
```

`_join_timeout_s` is already computed a few lines above (line 2599 in the audit). Just use the same variable.

**Time:** 5 minutes.

---

### BUG-3 — Non-atomic Redis `get → check → set` race ✅

**File:** `auto_rebalancer.py` lines 1592, 3055–3070, 3560, 3703–3713

**Problem:** Pattern `if not redis.get(key): redis.setex(key, TTL, value)` is a read-check-write race. Two workers can both read-miss and both write → counter jumps, double-launches.

**Fix — use `nx=True` (already used correctly at line 878):** Replace the unsafe pattern everywhere it appears with the atomic version:

```python
# UNSAFE (current):
if not _redis.get(_fkey):
    _redis.setex(_fkey, TTL, value)

# SAFE (fix):
_redis.set(_fkey, value, nx=True, ex=TTL)
# nx=True means: only set if key does not exist — atomic in Redis
```

For counters specifically, use `INCR` which is always atomic:
```python
# UNSAFE (current at lines 3055–3060):
_failure_count = int(_redis.get(_fkey_h3c) or 0)
if _failure_count == 0:
    _failure_count = int(_redis.incr(_failure_key) or 1)

# SAFE:
_failure_count = _redis.incr(_failure_key)  # atomic — no race
_redis.expire(_failure_key, 86400)          # set TTL after incr
```

Go through all four locations (1592, 3055, 3560, 3703) and apply the same pattern.

**Time:** 1 hour for all four locations plus a quick review pass.

---

## P2 — Sprint Fixes ✅ ALL DONE

### N3 — No agent version check ✅

**File:** `backend/routers/agents.py` lines 38–101

**Fix — log a warning and store mismatch flag:**
```python
EXPECTED_AGENT_VERSION = "1.0.0"  # bump this constant when protocol changes

version = payload.get("version")
if version != EXPECTED_AGENT_VERSION:
    logger.warning(
        "Agent %s on cluster %s registered with version %s, expected %s — "
        "protocol mismatch possible during rolling deploy",
        payload.agent_id, payload.cluster_id, version, EXPECTED_AGENT_VERSION
    )
# Do not reject — just flag. Agent still works, operator is informed.
```

No rejection, no breaking change. Visibility only.

**Time:** 10 minutes.

---

### N4 — `tag: latest` causes invisible agent divergence ✅

**File:** `charts/spot-optimizer-agent/values.yaml`

**Fix — deployment process change:**
```yaml
# values.yaml
image:
  repository: atharva608/spot-optimizer-agent
  tag: "{{ .Chart.AppVersion }}"   # set at release time
  pullPolicy: IfNotPresent          # only pull if not already present
```

In `Chart.yaml`, set `appVersion: 1.0.0` and bump it on each release. CI/CD pipeline builds the image, tags it with the version, pushes it, then Helm deploys with that version. Never deploy `latest` to production.

**Time:** 30 minutes to change values and update CI pipeline.

---

### N8 — `dry_run` cache is global — one cluster blocks all clusters ✅

**File:** `auto_rebalancer.py` line 1466

**Fix — option B (simpler):** Reduce fail TTL from 300s to 60s. Pass TTL stays at 900s.

```python
_DR_FAIL_TTL = 60    # was 300 — reduced so transient failures self-heal faster
_DR_PASS_TTL = 900   # unchanged
```

Option A (add cluster_id to key) is cleaner but requires updating every reader of the key. Option B is one constant change with the same practical effect at most cluster counts.

**Time:** 5 minutes.

---

### BUG-5 — Cluster deletion does not clear Redis keys ✅

**File:** `backend/api/cluster_routes.py` lines 183–245

**Fix — add a cleanup block after the DB delete:**
```python
def delete_cluster(cluster_id, db, redis):
    # ... existing DB and AWS cleanup ...

    # Clear Redis keys scoped to this cluster
    # Pattern-delete all cluster-scoped keys
    patterns = [
        f"cluster_pools:{cluster_id}",
        f"rebalance:lock:{cluster_id}",
        f"spot:cooldown:action:{cluster_id}",
        f"spot:stabilization_lock:{cluster_id}",
        f"lock:node_action:{cluster_id}",
        f"spot:launch_blocked:{cluster_id}:*",
    ]
    for pattern in patterns:
        if "*" in pattern:
            # Scan-delete for wildcard patterns
            cursor = 0
            while True:
                cursor, keys = redis.scan(cursor, match=pattern, count=100)
                if keys:
                    redis.delete(*keys)
                if cursor == 0:
                    break
        else:
            redis.delete(pattern)

    logger.info("Cleared Redis keys for deleted cluster %s", cluster_id)
```

Do not try to clean every single key. The six patterns above cover the ones with no TTL or long TTLs. Keys with short TTLs (< 1 hour) self-expire and do not need explicit cleanup.

**Time:** 1 hour.

---

### BUG-6 — Missing TTL on `karpenter_routes.py` Redis `.set()` ✅

**File:** `backend/api/karpenter_routes.py` line 491

**Fix:**
```python
# Was:
_redis.set(_cfg_key, value)

# Fix:
_redis.set(_cfg_key, value, ex=86400)  # 24h TTL — config refreshed on next API call
```

Check all other `.set()` calls in `karpenter_routes.py` for the same pattern. If there are more, apply the same fix to each.

**Time:** 15 minutes.

---

### BUG-7 — `max_concurrent_actions` limit can be exceeded by concurrent workers ✅

**File:** `auto_rebalancer.py` lines 3950+

**Problem:** Check-then-queue is not atomic. Two workers read the same count and both proceed.

**Fix — use a Redis counter as a distributed semaphore:**
```python
_semaphore_key = f"rebalance:active_count:{cluster_id}"

# Atomically increment and check
current = _redis.incr(_semaphore_key)
_redis.expire(_semaphore_key, 300)  # safety TTL

if current > _max_concurrent:
    # We over-incremented — decrement back and skip
    _redis.decr(_semaphore_key)
    continue  # skip this cluster this cycle

try:
    # Queue the action
    _create_rebalancing_action(...)
finally:
    # Decrement when action completes or fails
    # This should also happen in the action completion handler
    _redis.decr(_semaphore_key)
```

Also decrement in the action completion/failure handler so the counter stays accurate across the action's full lifecycle.

**Time:** 45 minutes.

---

### BUG-8 — State transition fails silently without retry ✅

**File:** `auto_rebalancer.py` lines 900–915

**Problem:** `_sm_transition()` returns `False` on conflict but caller does nothing with it.

**Fix — add one retry with a short delay:**
```python
def _sm_transition(db, action_id, from_state, to_state, max_retries=2):
    for attempt in range(max_retries + 1):
        result = db.execute(
            text("UPDATE rebalancing_actions SET current_state = :to_state "
                 "WHERE id = :action_id AND current_state = :from_state"),
            {"to_state": to_state, "action_id": action_id, "from_state": from_state}
        )
        db.commit()
        if result.rowcount == 1:
            return True
        if attempt < max_retries:
            time.sleep(0.1 * (attempt + 1))  # 100ms, 200ms
            # Re-read current state before retrying
            current = db.query(RebalancingAction).get(action_id)
            if current.current_state != from_state:
                logger.warning(
                    "State transition %s→%s for action %s aborted — "
                    "current state is %s (another worker won)",
                    from_state, to_state, action_id, current.current_state
                )
                return False  # another worker already transitioned — this is OK
    logger.error(
        "State transition %s→%s for action %s failed after %d attempts",
        from_state, to_state, action_id, max_retries + 1
    )
    return False
```

Two retries with 100ms/200ms delay is enough. If another worker genuinely won the transition, the re-read catches it and returns cleanly.

**Time:** 30 minutes.

---

### BUG-9 — Stale agent reset does not cancel pending actions ✅

**File:** `backend/workers/tasks/health.py` lines 90–115

**Problem:** `_reset_stale_agents()` marks cluster `agent_installed='N'` but leaves pending DRAIN/CORDON actions in queue. They stay `waiting_agent` for 45 minutes, locking the cluster.

**Fix — cancel pending actions when marking agent stale:**
```python
def _reset_stale_agents(db, redis):
    stale_clusters = (
        db.query(Cluster)
        .filter(
            Cluster.agent_installed == 'Y',
            Cluster.last_heartbeat < datetime.utcnow() - timedelta(minutes=5)
        )
        .all()
    )
    for cluster in stale_clusters:
        # Existing: mark cluster offline
        cluster.agent_installed = 'N'
        cluster.status = 'DISCOVERED'

        # NEW: cancel all pending AgentActions for this cluster
        pending_actions = (
            db.query(AgentAction)
            .filter(
                AgentAction.cluster_id == cluster.id,
                AgentAction.status.in_(['PENDING', 'PICKED_UP'])
            )
            .all()
        )
        for action in pending_actions:
            action.status = 'CANCELLED'
            # Also expire the action heartbeat so the rebalancer picks it up fast
            redis.delete(f"action_heartbeat:{action.id}")

        # NEW: mark associated RebalancingActions as failed
        stuck_rebalances = (
            db.query(RebalancingAction)
            .filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.status.in_(['in_progress', 'waiting_agent'])
            )
            .all()
        )
        for ra in stuck_rebalances:
            ra.status = 'failed'
            ra.error_message = 'AGENT_WENT_OFFLINE'
            ra.completed_at = datetime.utcnow()

        db.commit()

        logger.warning(
            "Cluster %s agent went stale — cancelled %d pending actions, "
            "failed %d stuck rebalances",
            cluster.id, len(pending_actions), len(stuck_rebalances)
        )
```

This brings the cluster out of lockdown in 5 minutes instead of 45 minutes.

**Time:** 1 hour.

---

### Z10 — Outdated comment says "180s" ✅

**File:** `ml_model/execution_engine/01_action_queue.py` line 68

```python
# lock:node_action:{cluster_id} — TTL: 1200s (20 min), renewed during drain
# (was 180s — updated to 1200s to match max drain timeout)
```

**Time:** 2 minutes.

---

## Full Implementation Order — COMPLETED

| # | ID | What | Status | File(s) Changed |
|---|---|---|---|---|
| 1 | N9 | Spec fallback abort (skip pool on vcpu=0) | ✅ Done | `cache_builder.py`, `pool_ranking_service.py` |
| 2 | BUG-1/2/4/N6 | WebSocket priority queues + HTTP fallback + action context | ✅ Done | `websocket_client.py`, `agents.py` |
| 3 | Z1 | Beat schedule for zombie OD cleanup | ✅ Done | `app.py` |
| 4 | Z3 | `force_delete_node()` self-guard | ✅ Done | `actuator.py` |
| 5 | N7 | `launch_blocked` TTL matches join timeout | ✅ Done | `auto_rebalancer.py` |
| 6 | Z5 | Beat schedule entry + dry_run race guard in sync task | ✅ Done | `app.py`, `health.py` |
| 7 | N2 | `min_savings_percent` enforced in pool ranking | ✅ Done | `pool_ranking_service.py` |
| 8 | N5 | Agent-side action heartbeat (30s loop + HTTP endpoint) | ✅ Done | `agents.py`, `actuator.py`, `websocket_client.py` |
| 9 | N1 | Wire `respect_pdb_enabled` to drain payload | ✅ Done | `auto_rebalancer.py` (2 locations) |
| 10 | BUG-3 | Atomic Redis NX pattern (interval gate race) | ✅ Done | `auto_rebalancer.py` |
| 11 | BUG-9 | Cancel pending actions when stale agent detected | ✅ Done | `health.py` |
| 12 | BUG-7 | `max_concurrent` Redis INCR/DECR semaphore | ✅ Done | `auto_rebalancer.py` (creation + completion) |
| 13 | BUG-8 | State transition retry with 100ms/200ms backoff | ✅ Done | `auto_rebalancer.py` |
| 14 | BUG-5 | Redis key cleanup on cluster delete | ✅ Done | `cluster_routes.py` |
| 15 | N8 | `dry_run` fail TTL 300s → 60s | ✅ Done | `dry_run.py` |
| 16 | BUG-6 | 24h TTL on karpenter Redis `.set()` | ✅ Done | `karpenter_routes.py` |
| 17 | N3 | Agent version warning on registration | ✅ Done | `agents.py` |
| 18 | N4 | Pin Helm image tags to `Chart.AppVersion` | ✅ Done | `values.yaml` |
| 19 | Z10 | Fix outdated 180s → 1200s comment | ✅ Done | `01_action_queue.py` |

---

## Implementation Notes (What Actually Changed)

### BUG-1 dependency — HTTP action result endpoint
Created `POST /api/v1/agents/actions/{action_id}/result` in `backend/routers/agents.py`.
The BUG-1 HTTP fallback in `websocket_client.py` posts to this endpoint when WebSocket send fails.
Updates `AgentAction.status/result`, clears `action_heartbeat:{id}` so rebalancer picks it up immediately.

### BUG-3 — What was actually racy
Only the per-cluster interval gate (`spot:last_check:{cluster_id}`) was a true get→exists→setex race.
The other three locations in the audit (lines 1592, 3055, 3560) use `setex`/`incr` directly — already atomic.
Fixed the gate with `redis.set(key, "1", nx=True, ex=TTL)` — acquires slot atomically.

### BUG-7 — Semaphore lifecycle
- **Acquire**: `redis.incr(rebalance:active_count:{cluster_id})` → decrement back if over limit
- **Release**: decremented in the action completion/failure resolution block (~line 3568)
- Safety TTL of 300s on the counter prevents indefinite lock if worker crashes before release
- Falls back to DB query when Redis unavailable

### BUG-9 — Lockdown duration
Before fix: cluster locked for up to 45 minutes (stale action expiry).
After fix: cluster freed within 5 minutes (stale agent detection interval).

### N8 — Scope of dry_run TTL change
`DRY_RUN_FAIL_TTL` constant is in `backend/utils/aws/dry_run.py` (not `auto_rebalancer.py`).
All callsites (`_cache_result`, `invalidate_dry_run_cache`, `batch_dry_run`) use the constant — one change covers all paths.

### Z5 — Race guard implementation
`sync_cluster_pools_task` now checks `dry_run:{type}:{az}` in Redis before adding each pool back.
If the dry_run value is `"fail"`, the pool is excluded from the rebuilt set — prevents re-adding a pool that was just `srem`'d after a capacity failure.

---

## What This Plan Deliberately Did Not Do

- No new Celery workers or services — all fixes go into existing tasks
- No DB schema changes
- No changes to pool ranking logic beyond the one `min_savings_percent` filter
- No agent protocol changes beyond the one new `/heartbeat` endpoint and `action_still_running` message type
- The WebSocket fix does not change how messages are sent — only how they are buffered before sending