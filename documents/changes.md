Let me read all documents systematically before saying anything.Good. Now I have the full current picture. Let me check the other documents quickly to verify their current state.Now I have the full current state of all six documents. Here is the precise assessment — no padding, no repetition of what was already said.

---

## What the Current Documents Show

---

### What is genuinely resolved — confirmed by the updated audit

The updated `COMPREHENSIVE_AUDIT_REPORT.md` (last verified 2026-03-30) confirms 26 of 42 items fixed. Cross-checking against all other docs:

**All Z-items except Z7/Z9/Z11** — confirmed fixed with exact line numbers.
**N1, N2, N3, N4, N5, N7, N9** — confirmed fixed with exact line numbers.
**BUG-1, 2, 4, 5, 6, 7, 8, 9** — confirmed fixed.
**BUG-3** — partially fixed. The critical lock paths use NX. One low-severity debounce pattern remains at `auto_rebalancer.py:3640`.

The `DIAGNOSTIC_GUIDE.md` has been updated and reflects most of these fixes correctly.

---

### The 9 remaining open issues

These are real, unresolved, and need fixes now. Here they are with precise solutions:

---

#### BUG-10 — Agent endpoints have no authentication (CRITICAL)

**File:** `backend/routers/agents.py` — lines 27, 137, 152, 183, 231

All five agent endpoints accept `authorization: Optional[str] = Header(None)` and never validate it. Any unauthenticated caller can register fake agents, spoof action results, or deregister legitimate agents.

**Fix:**

Create a dedicated agent token validator:
```python
# In agents.py — add near the top
from fastapi import Depends, HTTPException, Header, status

AGENT_API_KEY = os.getenv("AGENT_API_KEY")  # set in backend env, same value as agent API_KEY

def verify_agent_token(authorization: Optional[str] = Header(None)):
    if not AGENT_API_KEY:
        raise HTTPException(status_code=500, detail="AGENT_API_KEY not configured")
    if authorization != f"Bearer {AGENT_API_KEY}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent token"
        )

# Add Depends(verify_agent_token) to all five endpoints:
@router.post("/api/v1/agents/register")
async def register_agent(payload: dict, _: None = Depends(verify_agent_token)):
    ...

@router.post("/api/v1/agents/actions/{action_id}/heartbeat")
async def action_heartbeat(action_id: str, _: None = Depends(verify_agent_token)):
    ...

@router.post("/api/v1/agents/actions/{action_id}/result")
async def action_result(action_id: str, payload: dict, _: None = Depends(verify_agent_token)):
    ...

@router.post("/api/v1/agents/deregister")
async def deregister_agent(payload: dict, _: None = Depends(verify_agent_token)):
    ...

@router.post("/api/v1/agents/heartbeat")
async def agent_heartbeat(payload: dict, _: None = Depends(verify_agent_token)):
    ...
```

`AGENT_API_KEY` is the same value already injected into the agent via the `API_KEY` env var (confirmed in `agent.md` appendix). No new secret needed — reuse the existing one. The agent already sends `Authorization: Bearer {API_KEY}` on all HTTP calls.

**Note on the spot interruption endpoint:** `POST /api/v1/worker/spot-interruption` uses `X-API-Key` header (not `Authorization: Bearer`) per `agent.md` §2. Verify it has its own auth check — if it uses the same `Optional` pattern, apply the same fix with `x_api_key: Optional[str] = Header(None, alias="X-API-Key")`.

---

#### BUG-11 — Missing `Dict` import in `agent/main.py` causes runtime crash (HIGH)

**File:** `agent/main.py` line 16

```python
# Before:
from typing import Optional

# After:
from typing import Optional, Dict
```

This is a one-word fix. The agent crashes immediately on startup without it — `Agent.__init__()` fails at the first line that uses `Dict[str, int]`. Verify no other `typing` imports are missing in the same file while you are there (`List`, `Any`, etc.).

---

#### BUG-12 — `flush_buffer()` drops critical messages on send failure (HIGH)

**File:** `agent/websocket_client.py` lines 245–248

Current code:
```python
while not self.critical_queue.empty():
    try:
        msg = self.critical_queue.get_nowait()
        await self.send_message(msg)
    except Exception:
        break  # message dequeued and gone forever
```

**Fix — re-queue on failure, never drop:**
```python
while not self.critical_queue.empty():
    try:
        msg = self.critical_queue.get_nowait()
    except queue.Empty:
        break
    try:
        await self.send_message(msg)
    except Exception as e:
        logger.error(
            "flush_buffer: failed to send critical message type=%s, "
            "re-queuing. Error: %s",
            msg.get("type"), e
        )
        self.critical_queue.put(msg)  # put back at front
        break  # stop flush — connection may not be ready yet
```

Using `put()` re-queues at the back of the queue, not the front. For strict ordering, replace `queue.Queue()` with `collections.deque` and use `appendleft()` to put back at front. If ordering of action results does not matter to the backend (each result references its own `action_id`), `put()` at the back is fine.

This directly fixes the contradiction in BUG-4/N6 fix — the two-tier queue was designed to never lose critical messages, but `flush_buffer` could still lose them.

---

#### BUG-13 — Spot interruption fallback handler is a no-op (MEDIUM)

**File:** `agent/poller.py` lines 170–184

Current code logs a warning and returns if `handle_spot_interruption` is missing. No actual emergency action is taken.

**Fix — implement actual fallback:**
```python
def handle_termination(self, instance_id: str):
    if hasattr(self.actuator, 'handle_spot_interruption'):
        self.actuator.handle_spot_interruption(instance_id)
    else:
        logger.warning(
            "handle_spot_interruption not found on actuator — "
            "executing direct cordon+drain fallback for %s", instance_id
        )
        # Direct fallback: cordon then drain the local node
        my_node = os.getenv('NODE_NAME')
        if not my_node:
            logger.error("NODE_NAME not set — cannot execute fallback cordon/drain")
            return
        # Use the existing cordon and drain methods directly
        # These already have self-guard checks so they are safe to call here
        try:
            self.actuator.cordon_node({"node_name": my_node})
            self.actuator.drain_node({"node_name": my_node, "force": True})
        except Exception as e:
            logger.error("Fallback cordon/drain failed for %s: %s", my_node, e)
```

Wait — the self-guard in `cordon_node` and `drain_node` checks `node_name == NODE_NAME` and rejects it. The fallback is trying to cordon the agent's own node on a spot interruption, which is exactly the right thing to do for an emergency. So the self-guard blocks the fallback.

**Correct approach:** The self-guard is for the case where the **backend** mistakenly sends an action targeting the agent's node. For local emergency self-cordoning on interruption, bypass the guard:

```python
# Add an internal method to actuator.py for emergency self-cordon
def _emergency_self_cordon_drain(self):
    """Called only on IMDS spot interruption — bypasses self-guard intentionally."""
    my_node = os.getenv('NODE_NAME')
    if not my_node:
        logger.error("NODE_NAME not set — cannot self-cordon on interruption")
        return
    try:
        # Call K8s directly, bypassing the self-guard
        self._k8s_client.patch_node(my_node, {"spec": {"unschedulable": True}})
        logger.critical("Emergency self-cordon applied to %s", my_node)
        # Drain follows — evict all pods
        self._evict_all_pods(my_node, force=True)
    except Exception as e:
        logger.error("Emergency self-cordon/drain failed: %s", e)
```

Then in `poller.py` fallback:
```python
self.actuator._emergency_self_cordon_drain()
```

---

#### BUG-14 — Thread-unsafe `component_health` dict in `heartbeat.py` (MEDIUM)

**File:** `agent/heartbeat.py` lines 205, 277, 309

Three threads access `self.component_health` concurrently with no lock.

**Fix:**
```python
# In HeartbeatSender.__init__():
self.component_health: Dict[str, str] = {}
self._health_lock = threading.Lock()

# In set_component_health() (line ~205):
def set_component_health(self, component: str, status: str):
    with self._health_lock:
        self.component_health[component] = status

# In send_heartbeat() (line ~277) — anywhere component_health is read:
with self._health_lock:
    health_snapshot = dict(self.component_health)  # take a copy under lock
# Use health_snapshot outside the lock

# In collect_agent_metrics() (line ~309) — same pattern:
with self._health_lock:
    health_snapshot = dict(self.component_health)
```

Taking a snapshot under the lock then releasing immediately keeps the lock held for the minimum time. Never iterate over `self.component_health` directly outside the lock.

---

#### BUG-15 — `recovery_monitor` subtask failure crashes umbrella task (MEDIUM)

**File:** `backend/workers/tasks/recovery_monitor.py` lines 505–513

**Fix — wrap each `.result` access:**
```python
def _safe_result(task_result, name: str) -> dict:
    try:
        return {"status": "ok", "result": task_result.result}
    except Exception as e:
        logger.error("recovery_monitor subtask %s failed: %s", name, e)
        return {"status": "error", "error": str(e)}

# Replace the current result-gathering block:
return {
    "sync":    _safe_result(r1, "sync_instance_states"),
    "scan":    _safe_result(r2, "scan_orphans"),
    "stalls":  _safe_result(r3, "detect_karpenter_stalls"),
    "cordon":  _safe_result(r4, "recover_stuck_cordoned_nodes"),
}
```

Each subtask result is now wrapped independently. A single DB timeout in `sync_instance_states` no longer prevents `scan_orphans`, `detect_karpenter_stalls`, and `recover_stuck_cordoned_nodes` from running and returning results.

---

#### BUG-16 — Log injection via unvalidated user input in `/fallback` endpoint (MEDIUM)

**File:** `backend/api/cluster_routes.py` lines 445–461

**Fix — sanitize before logging:**
```python
def _sanitize_log_field(value: str, max_len: int = 100) -> str:
    """Strip control characters and limit length for safe logging."""
    if not isinstance(value, str):
        return str(value)[:max_len]
    # Remove newlines, carriage returns, and other control chars
    sanitized = re.sub(r'[\x00-\x1f\x7f]', '_', value)
    return sanitized[:max_len]

# In request_fallback_node():
node_name     = _sanitize_log_field(payload.get("node_name", ""))
reason        = _sanitize_log_field(payload.get("reason", ""))
instance_type = _sanitize_log_field(payload.get("instance_type", ""))
az            = _sanitize_log_field(payload.get("az", ""))

logger.critical(
    "Fallback requested: node=%s reason=%s type=%s az=%s",
    node_name, reason, instance_type, az
    # Use % formatting not f-strings — prevents format string issues
)
```

Add `import re` at the top of the file if not already present.

---

#### N8 — `dry_run` cache key is global across clusters (MEDIUM)

**File:** `auto_rebalancer.py` line 1487

The key is `dry_run:{type}:{az}` with no `cluster_id`. One cluster's failure blocks the pool for all clusters in the region for 300s.

**Fix — reduce fail TTL to 60s (one constant, no key rename):**
```python
_DR_FAIL_TTL = 60    # was 300 — transient capacity failures now self-heal in 1 min
_DR_PASS_TTL = 900   # unchanged
```

This is the least disruptive option. No reader changes needed. If you want full cluster isolation, option B is:
```python
_dr_key = f"dry_run:{cluster_id}:{_lt}:{target_az}"  # add cluster_id
```
But this requires updating every reader of the key — more work, higher risk.

---

#### BUG-3 (remaining) — Non-atomic debounce at line 3640 (MEDIUM, low risk)

**File:** `auto_rebalancer.py` line 3640

```python
# Before (non-atomic):
if not _redis.get(_rlf_debounce_key):
    _redis.setex(_rlf_debounce_key, 60, '1')

# After (atomic):
_redis.set(_rlf_debounce_key, '1', nx=True, ex=60)
```

Worst case of the current bug is two redundant cache rebuilds within 60 seconds. Low severity but trivial to fix.

---

## Document Updates Still Needed

Cross-checking the current `DIAGNOSTIC_GUIDE.md` against the 9 open issues:

**`DIAGNOSTIC_GUIDE.md`** — two stale entries found:

1. **§6 Quick-Reference Redis Keys table** — `rebalance:lock` still says `2400s`. This was changed to `2700s` in NEW-3 fix. Update to `2700s (renewed every 60s; matches 45-min stale action threshold)`.

2. **§6 Quick-Reference Redis Keys table** — `spot:launch_blocked` still says `300s (no-join) or 1800s`. Should be `spot_join_timeout_minutes × 60 (no-join, default 1800s) or 1800s (≥3 failures)`. The body text in §2.5 was already updated correctly — just the quick-reference table at the bottom was missed.

3. **§6 Quick-Reference Redis Keys table** — `dry_run` still says `900s (pass) / 300s (fail)`. The body text in §2.3 correctly says `60s` — the table was not updated. Change to `900s (pass) / 60s (fail, N8 fix)`.

These three are the only stale entries in `DIAGNOSTIC_GUIDE.md`. Everything else in that document accurately reflects the current state.

**`AUTO_REBALANCING_SYSTEM.md`** — after BUG-10 is fixed, add a security note to §6 Security Gates:

```
### Agent Endpoint Authentication (BUG-10 fix)
All 5 agent endpoints (`/register`, `/heartbeat`, `/actions/{id}/heartbeat`,
`/actions/{id}/result`, `/deregister`) require `Authorization: Bearer {AGENT_API_KEY}`.
Token is validated via `Depends(verify_agent_token)`. Unauthenticated requests
return HTTP 401. `AGENT_API_KEY` must be set as a backend env var — same value
as the agent's `API_KEY` env var.
```

**`agent.md`** — after BUG-11 is fixed, update §9 Edge Cases to note: "`Dict` is now imported from `typing` in `agent/main.py` — previously missing, causing a `NameError` crash on agent startup." Remove any text suggesting it was working before.

No other documents need updates for these 9 fixes. `per_node_alternative_pools.md` and `source-validation.md` are unaffected by all 9 remaining open issues.

---

## Summary

| ID | Severity | Fix size | File |
|---|---|---|---|
| BUG-10 | CRITICAL | Add `Depends(verify_agent_token)` to 5 endpoints | `agents.py` |
| BUG-11 | HIGH | Add `Dict` to typing import | `agent/main.py` |
| BUG-12 | HIGH | Re-queue message on flush failure | `websocket_client.py` |
| BUG-13 | MEDIUM | Implement `_emergency_self_cordon_drain()` | `actuator.py`, `poller.py` |
| BUG-14 | MEDIUM | Add `threading.Lock()` around `component_health` | `heartbeat.py` |
| BUG-15 | MEDIUM | Wrap each `.result` in try/except | `recovery_monitor.py` |
| BUG-16 | MEDIUM | Sanitize fields before logging | `cluster_routes.py` |
| N8 | MEDIUM | `_DR_FAIL_TTL = 60` | `auto_rebalancer.py` |
| BUG-3 | MEDIUM | `nx=True, ex=60` at line 3640 | `auto_rebalancer.py` |

BUG-10, BUG-11, and BUG-12 are the only ones with real operational consequences right now. BUG-11 is a crash bug — if it has not manifested yet, the agent is either not being restarted or the code path hasn't been hit in the current running process. Fix it first.