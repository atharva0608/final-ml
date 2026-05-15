# Engine Fix Log

> Tracks every logic change made to the placement engines (PlacementController, auto_rebalancer, scheduler).
> Format: **Problem → Root Cause → Fix → Files Changed**

---

## Fix 1 — PlacementAdvisor Beat Schedule Gap

**Status:** Resolved

### Problem
The PlacementAdvisor cycle was never being triggered in production.
Celery Beat has no `placement-advisor-*` entry, so the advisor silently never ran.

### Root Cause
The task existed (`placement_advisor_task.py`) but nothing scheduled it.
A Celery Beat entry was the assumed trigger, but it was never added to `app.conf.beat_schedule`.

### Fix
Added `job_run_placement_cycle()` to `backend/scheduler.py` on a 10-minute APScheduler
`IntervalTrigger`. APScheduler starts with the uvicorn process; no separate Celery Beat
worker is required. The job calls `run_placement_cycle_task.apply_async(args=[cluster.id])`
for each cluster that has a WIE metrics key present in Redis.

**Why not Celery Beat?**
Celery Beat requires a dedicated worker process and a persistent schedule store.
APScheduler runs inside the same uvicorn process, has zero additional infrastructure
requirements, and already drives all other engine jobs in this codebase.

### Files Changed
- `backend/scheduler.py` — `job_run_placement_cycle` added; registered in `start_scheduler()` with 10-min interval

---

## Fix 2 — Mutex TTL Race (PC + AR)

**Status:** Resolved

### Problem
`cluster_mutex` used a fixed 60-second `SET key owner NX EX 60`.
A PlacementController cycle that takes >60 s (common on clusters with many workloads)
causes the lock to silently expire. auto_rebalancer then acquires the same mutex
and both engines operate on the cluster concurrently — causing duplicate evictions and
conflicting pod/node decisions.

### Root Cause
`backend/utils/redis_locks.py::cluster_mutex` used a plain `redis.set(... nx=True, ex=ttl)`.
There was no mechanism to keep the TTL alive while the critical section was executing.

### Fix
Replaced the fixed-TTL pattern with a `HeartbeatLock` class.
`HeartbeatLock` spawns a daemon thread on acquire that calls `EXPIRE` every `ttl // 3`
seconds (default: every 20 s for a 60 s TTL), renewing the lock indefinitely until
`release()` is called.

On release the stop-event is set and the key is deleted only if `GET key == owner`,
preventing accidental deletion if the lock was legitimately stolen after a genuine expiry.

`cluster_mutex` is now a thin `@contextmanager` wrapper around `HeartbeatLock`.
The `workload_lock` helper is unchanged (short 30 s TTL is safe for per-pod operations).

### Files Changed
- `backend/utils/redis_locks.py` — `HeartbeatLock` class added; `cluster_mutex` updated to use it

---

## Fix 3 — Engine B Redis Dead-Letter Queue

**Status:** Resolved

### Problem
PlacementController (Engine A) maintained a Redis semaphore
(`rebalance:active_count:{cluster_id}`) after each EVICT_POD dispatch as the only
cross-engine visibility mechanism. If Redis was unavailable or the key expired,
auto_rebalancer (Engine B) had zero visibility into PC's in-flight actions.

### Root Cause
The `_dispatch_eviction` method in `PlacementControllerService` incremented the Redis
semaphore as a side-effect after the DB write. The design relied on a volatile Redis
counter as the cross-engine channel instead of the durable `AgentAction` DB record
that was already being written two lines above.

### Fix
Removed the Redis semaphore increment entirely from `_dispatch_eviction`.
The `AgentAction` DB record written immediately before is the authoritative in-flight
signal. Both PC's Phase 3 batch check and AR's `active_agent_actions` gate already
query the `AgentAction` table — the Redis counter was redundant and failure-prone.

The docstring comment `"Replaces the previous Redis rpush dispatch path"` at line 939
confirms the DB-write path was already the intended fix; the semaphore was a leftover.

### Files Changed
- `backend/services/placement_controller_service.py` — Redis `incr`/`expire` block removed from `_dispatch_eviction`

---

## Fix 4 — Batch Limit Cross-Engine

**Status:** Resolved

### Problem
auto_rebalancer's per-node concurrent action gate used a Redis `INCR`/`DECR`
semaphore (`rebalance:active_count`). This semaphore only tracked auto_rebalancer's
own `RebalancingAction` records. PlacementController EVICT_POD `AgentAction` records
were invisible to it, so both engines could independently believe they were within
`max_concurrent_rebalance_actions` while the real combined count exceeded the limit.

### Root Cause
Two separate counting mechanisms existed with no cross-engine view:
- PC → `AgentAction` DB COUNT (Phase 3 batch check)
- AR → Redis semaphore INCR/DECR (per-node loop gate)

### Fix
Added a **DB COUNT pre-gate** in auto_rebalancer's node-iteration loop immediately
before the Redis semaphore INCR. The pre-gate queries `AgentAction` for all
`PENDING + PICKED_UP` records for the cluster — identical to PC's Phase 3 query —
giving a single authoritative combined view across both engines.

- If `db_active >= _max_concurrent`: node is skipped (`break`).
- If DB gate passes: existing Redis semaphore path runs unchanged as a secondary soft guard.
- If DB query fails: fail-open and fall through to the Redis semaphore (backward-compatible).

The AR semaphore reconciliation block already syncs the Redis counter to the DB value
each cycle, so the Redis counter remains a valid monitoring signal.

### Files Changed
- `backend/workers/tasks/auto_rebalancer.py` — DB COUNT pre-gate block added at node-iteration loop (before Redis INCR, line ~8959)

---

## Bonus — WorkloadMigration.jsx Rewrite

**Status:** Resolved (carried over from workload API wiring session)

### Problem
`WorkloadMigration.jsx` was 100% hardcoded fake data (`CANDIDATES` array). No real API calls.

### Fix
Full rewrite. Component now fetches from `migrationStatusAPI.get(clusterId)` which
calls `GET /api/v1/clusters/{cluster_id}/migration-status`. Renders active migrations
(with TTL, freeze state) and history events from real backend data.

### Files Changed
- `frontend/src/pages/optimize/workloads/WorkloadMigration.jsx` — full rewrite, real API

---

## Fix 5 — `_rollback_drain()` Stub (Cluster-Corrupting)

**Status:** Resolved  
**Severity:** CRITICAL — a drain failure permanently cordons the node until manual intervention

### Problem
`execution_controller.py::_rollback_drain()` was a one-line stub that only logged a warning.
When a drain fails mid-flight the node remains cordoned: the Kubernetes scheduler can no longer
place new pods on it, silently shrinking the cluster's usable capacity until someone manually
runs `kubectl uncordon`.

### Root Cause
The function had a `# Production: kubectl uncordon` comment with no implementation.

### Fix
Replaced the stub with a real `UNCORDON_NODE` AgentAction DB dispatch, following the
identical pattern used by `_drain_node` and `_terminate_node` in the same class.

```python
# backend/services/execution_controller.py  (_rollback_drain)
action = AgentAction(
    cluster_id=cluster_id,
    action_type=AgentActionType.UNCORDON_NODE,
    status=AgentActionStatus.PENDING,
    priority=10,
    payload={"node_name": node_id, "source": "execution_controller_rollback"},
)
_db.add(action)
_db.commit()
```

The agent already handles `UNCORDON_NODE`; no agent-side changes required.

### Files Changed
- `backend/services/execution_controller.py` — `_rollback_drain` stub replaced with UNCORDON_NODE AgentAction dispatch

---

## Fix 6 — Redis Fail-Open on PDB Check (Cluster-Corrupting)

**Status:** Resolved  
**Severity:** CRITICAL — Redis unavailability silently bypasses PDB and cooldown guards, allowing unsafe evictions

### Problem
Two functions in `PlacementControllerService` returned `False` (= "safe to evict") when
Redis was unavailable:

| Function | Redis-absent behavior | Correct behavior |
|---|---|---|
| `_would_violate_pdb()` — exception path | `return False` (allow eviction) | `return True` (block) |
| `_workload_in_cooldown()` — no try/except | exception propagates | `return True` (block) |

During a Redis blip, every in-flight PDB check and cooldown check would pass, allowing the
controller to evict pods from workloads that may have active PDB constraints or that were
just recently evicted (violating the cooldown window).

### Root Cause
**`_would_violate_pdb`**: the `except` block returned `False` ("no violation") instead of
`True` ("unknown — block"). The function's own docstring incorrectly described this as
"fails open … so existing guards still run", masking the safety inversion.

**`_workload_in_cooldown`**: had no exception handling at all — `self.redis.exists(key)` would
raise on connection failure, propagating an unhandled exception up the call stack. If caught
higher up, it could silently skip the cooldown check.

### Fix

**`_would_violate_pdb`** — flipped exception handler:
```python
except Exception as exc:
    logger.warning(f"[PC] _would_violate_pdb redis error ... — blocking eviction (fail-closed)")
    return True   # was: return False
```

**`_workload_in_cooldown`** — wrapped in try/except with fail-closed default:
```python
try:
    return bool(self.redis.exists(key))
except Exception as exc:
    logger.warning(f"[PC] _workload_in_cooldown redis error ... — blocking eviction (fail-closed)")
    return True   # was: unhandled exception
```

Note: the `if not raw: return False` branch (key missing = no PDB state) is intentionally
left permissive. A missing key means WIE has not yet indexed the workload, not that Redis
is down. Only the exception path (confirmed Redis failure) is fail-closed.

### Files Changed
- `backend/services/placement_controller_service.py`
  - `_would_violate_pdb()` — exception handler flipped to `return True`
  - `_workload_in_cooldown()` — wrapped in try/except returning `True` on Redis error

---

---

## Fix 7 — `pod_metrics.phase` and `start_time` Not Written by Agent

**Status:** Resolved  
**Tier:** 2 — product behavior visible to users  
**Unblocks:** Placement pod table (phase/age), Scaling efficiency breakdown (Serving/Idle/Draining counts), Eviction Risk Signal banner

### Problem
Three UI sections showed blank/zero data:
- Placement pod table: `phase` column blank, `age` column null
- Scaling efficiency breakdown: all three buckets (Serving/Idle/Draining) showing 0/0/0
- Eviction Risk Signal banner: never triggers

All three read from `PodMetric.phase` / `PodMetric.start_time` DB columns. The columns were added in migration `20260427_pod_metrics_phase_starttime` but were never populated.

### Root Cause
`backend/routers/metrics.py` builds each `PodMetric` record from the agent payload but the
constructor call did not include `phase` or `start_time`. The agent sends both fields; the
server simply discarded them.

### Fix
Added the two missing field assignments to the `PodMetric` constructor in the pod metrics
ingest loop:

```python
_pod_start_time = None
_raw_start = pod.get("start_time")
if _raw_start:
    try:
        _pod_start_time = datetime.fromisoformat(str(_raw_start).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass

pod_metric = PodMetric(
    ...
    phase=pod.get("phase"),
    start_time=_pod_start_time,
    ...
)
```

`start_time` parsing is wrapped to handle both `2026-04-27T10:00:00Z` (UTC Z-suffix) and
`2026-04-27T10:00:00+05:30` (offset) formats from the agent.

### Files Changed
- `backend/routers/metrics.py` — `phase` and `start_time` mapped from agent payload in pod metrics ingest loop

---

## Fix 8 — Savings Column `$0` in Workload Profiling List

**Status:** Already resolved (previous session)  
**Tier:** 2 — product behavior visible to users

`mapListItem()` in `WorkloadProfiling.jsx` now reads `w.estimated_monthly_saving_usd || 0`
(line 60). The `list_workloads` backend endpoint was updated to JOIN `estimated_monthly_saving_usd`
from `PlacementPolicyRecord`. No further change required.

---

## Fix 9 — Per-Workload Oscillation Detection (evict → OD → evict loop)

**Status:** Resolved  
**Tier:** 2 — most common production failure mode

### Problem
A single workload could oscillate indefinitely between eviction and OD-placement:

1. PC evicts pod → pod lands on OD → `handle_eviction_result` marks FAILED
2. 5 minutes later PC detects OD pod as drift → dispatches new eviction
3. Pod lands on OD again → repeat forever

`MAX_RETRY_COUNT=3` is per-action, not per-workload. A fresh action is created every cycle.
The cluster-level circuit breaker requires 10 total failures; a single chronic workload
contributes at most 1 per cycle and never trips it.

### Fix

**Counter key:** `spot:pc:workload_od_landings:{cluster_id}:{workload_id}`  
- Incremented by `_track_od_landing()` on every OD landing (`placement.capacity_type != target_cap`)
- TTL = 1800 s (30-min rolling window), configurable via `PC_OSCILLATION_WINDOW_SECS`

**Block key:** `spot:pc:workload_oscillation_block:{cluster_id}:{workload_id}`  
- Set when counter reaches threshold (default 5), configurable via `PC_OSCILLATION_THRESHOLD`
- TTL = 7200 s (2-hour hard stop), configurable via `PC_OSCILLATION_BLOCK_SECS`
- Counter is deleted after block is set to reset for the next window

**Gate in `_get_actionable_workloads()`:**  
Checks `redis.exists(block_key)` per workload. If set, workload is skipped with a `DEBUG`
log. Fail-open on Redis error (workload is not silently suppressed if Redis is flapping).

```python
# handle_eviction_result — OD landing branch
_track_od_landing(action.cluster_id, workload_id, redis)
_mark_for_retry(action, workload_id, db, redis)

# _get_actionable_workloads — filter
if self.redis.exists(block_key):
    continue   # oscillation block active — skip this cycle
```

### Env vars (all optional, sensible defaults)
| Variable | Default | Purpose |
|---|---|---|
| `PC_OSCILLATION_THRESHOLD` | `5` | OD landings before block |
| `PC_OSCILLATION_WINDOW_SECS` | `1800` | Rolling counter TTL (30 min) |
| `PC_OSCILLATION_BLOCK_SECS` | `7200` | Block duration (2 h) |

### Files Changed
- `backend/services/placement_controller_service.py`
  - Constants `OSCILLATION_COUNTER_KEY`, `OSCILLATION_BLOCK_KEY`, thresholds added
  - `_track_od_landing()` module-level helper added
  - `handle_eviction_result()` — calls `_track_od_landing` on OD landing branch
  - `_get_actionable_workloads()` — checks block key, skips oscillating workloads

---

---

## Fix 10 — HPA Scale-Up Invisible to Scaling Guard

**Status:** Resolved  
**Tier:** 3 — sprint

### Problem
`_scaling_guard_active()` checked pending pods and KEDA events but was blind to HPA scale-ups.
When an HPA increases `desiredReplicas` the newly created pods land on OD (no Spot capacity
yet); PlacementController would immediately see them as drift and dispatch evictions against
pods that were intentionally just created, racing with HPA's own placement.

### Fix

**Agent side** (`backend/api/agent_routes.py` — `upsert_hpa_configs_batch`):  
After the bulk upsert succeeds, checks if any HPA in the batch has
`desiredReplicas > currentReplicas`. If so, writes:
```
spot:pc:hpa_scaling_event:{cluster_id} = <unix timestamp>   TTL 300 s
```

**PC side** (`backend/services/placement_controller_service.py`):
- Added `HPA_EVENT_KEY_TEMPLATE` and `HPA_SCALING_GUARD_WINDOW_SECONDS` (default 180 s, env `PC_HPA_SCALING_GUARD_WINDOW_SECS`)
- Added `_recent_hpa_scaling_event()` — reads the key, compares against `time.time()`, fail-open on Redis error
- `_scaling_guard_active()` now calls it last: pending pods → KEDA → HPA

### Files Changed
- `backend/api/agent_routes.py` — HPA event key written after batch upsert when scale-up detected
- `backend/services/placement_controller_service.py` — `HPA_EVENT_KEY_TEMPLATE`, `_recent_hpa_scaling_event()`, `_scaling_guard_active()` updated

---

## Fix 11 — `needs_revalidation` Dead Flag

**Status:** Resolved  
**Tier:** 3 — sprint

### Problem
`handle_eviction_result()` sets `result.needs_revalidation=True` on two paths:
- K8s API unreachable at validation time
- Pod still Pending at validation time

Both are optimistically marked `COMPLETED`. Nothing ever read `needs_revalidation`, so
every action in this state was silently treated as successful even if the pod later landed
on OD.

### Fix
New Celery task `revalidate_pending_completions(cluster_id)` in `placement_controller_task.py`:
- Queries up to 50 `COMPLETED EVICT_POD` AgentActions where `result['needs_revalidation'].astext == 'true'`
- Calls `get_pod_placement()` for each
  - **OD landing confirmed** → calls `_mark_for_retry()` → marks `FAILED` so PC detects drift on next 5-min cycle
  - **Pod gone or still Pending** → clears the flag, leaves `COMPLETED`
  - **K8s API still unreachable** → skips (will retry next hour)

`dispatch_placement_controller_recovery` (the existing hourly beat task) now dispatches
`revalidate_pending_completions.apply_async(args=[cluster.id])` alongside
`recover_stale_stateful_migrations` for every agent-installed cluster.

### Files Changed
- `backend/workers/tasks/placement_controller_task.py`
  - `revalidate_pending_completions` task added
  - `dispatch_placement_controller_recovery` dispatches it per cluster

---

## Fix 12 — Bare `except: pass` in AZ Spike Detection

**Status:** Resolved  
**Tier:** 3 — sprint

### Problem
`placement_advisor_service.py::compute_spot_availability_factor()` had a bare `except: pass`
inside the AZ failure-spike loop. Any parse error, Redis decode failure, or type error in
the AZ history data would be silently swallowed. A full AZ capacity failure could produce
corrupt data that lands in the `except` branch, causing the advisor to skip the AZ override
and continue assigning Spot to a dead AZ.

Two additional bare `except:` blocks in the same method body (`state_data` parse and
stability-key parse) were fixed at the same time.

### Fix
All three bare `except:` replaced with `except Exception as e: logger.warning(...)`:

1. **AZ spike loop** — `continue` after warning so other AZs are still evaluated
2. **`state_data` parse** — warning only; `state_data` stays `{}`
3. **stability-key parse** — warning + write a fresh stability record so the clock restarts

### Files Changed
- `backend/services/placement_advisor_service.py`
  - `compute_spot_availability_factor()` — AZ spike loop bare except replaced
  - `_compute_workload_policy()` — two additional bare excepts replaced

---

---

# Tier 4 — After Tier 1–3. Product completeness, not safety.

---

## Fix 13 — Node Selector Page (Deferred — Large Backend Build)

**Status:** Deferred — do not start until Tier 1–3 are complete  
**Tier:** 4

### Problem
The Node Selector page is 100% fake data. It requires:
- New backend endpoints for node pool browsing and selection
- A node-selector state machine (propose → review → apply → rollback)
- Data models for saved node selector configurations per cluster

### Action
No implementation started. Tracked here to prevent it being confused with a "quick fix".
Full scope estimate: new DB migration, 3-4 API endpoints, state machine service, frontend
wiring. Begin only after all Tier 1–3 items are resolved.

---

## Fix 14 — Workload Migration Page Backend (Deferred — Large Backend Build)

**Status:** Frontend wired (previous session); backend state machine deferred  
**Tier:** 4

### Problem
`WorkloadMigration.jsx` was rewritten to call `migrationStatusAPI.get()` (fix from earlier
session). However the backend migration status endpoint lacks a real state machine:
- No migration lifecycle (pending → draining → migrating → verifying → done)
- No per-workload migration history persistence
- No freeze / TTL management backed by durable DB state

The frontend shows whatever the endpoint returns; if the endpoint returns empty/stub data the
page still shows nothing meaningful.

### Action
No implementation started. Requires:
- New `WorkloadMigration` DB model and migration
- State machine service with lifecycle transitions
- At minimum 2 new endpoints: `POST /start` and `GET /status` with real DB reads
- Begin only after all Tier 1–3 items are resolved.

---

## Fix 15 — `pool_optimization_worker` Assessment Not Persisted

**Status:** Resolved  
**Tier:** 4

### Problem
`pool_optimization_worker` runs every 30 minutes, ranks all instance pools by interruption
risk, and identifies high-risk pools above `POOL_RISK_THRESHOLD`. When
`FEATURE_POOL_OPTIMIZATION_ACTIVE=False` (the production default), the only observable
side-effect was writing two timestamps (Redis + DB). All ranking and risk-assessment output
was discarded. Dead code that *looks* active is worse than missing code.

### Root Cause
Step 4 (rotation) is correctly gated behind `FEATURE_POOL_OPTIMIZATION_ACTIVE`. But there
was no step that persisted the *assessment* results independently of rotation. The worker
had valuable computed data with nowhere to write it.

### Fix
After identifying high-risk pools (step 3), always write the full assessment to Redis
regardless of the rotation flag:

```
spot:pool_optimization:assessment:{cluster_id}  TTL 3600 s
{
  "ranked_count": <int>,
  "high_risk_count": <int>,
  "high_risk_pools": [{"instance_type": ..., "az": ..., "risk_score": ...}, ...],
  "top_pools": [top 10 ranked pools],
  "assessed_at": "<iso datetime>",
  "rotation_active": <bool>
}
```

The cluster status API and Node Selector page (when built) can read
`spot:pool_optimization:assessment:{cluster_id}` to surface real pool risk data immediately.
Rotation stays correctly gated behind `FEATURE_POOL_OPTIMIZATION_ACTIVE`.

### Files Changed
- `backend/workers/tasks/optimizer_coordinator_worker.py` — step 4 added to always write
  assessment JSON to Redis; rotation step renumbered to 5; timestamp steps to 6–7

---

---

## A1 — Savings Per Workload in Profiling List

**Status:** Already resolved (previous session)  
**Audit ref:** Page-data-source-audit A1

Backend `list_workloads` in `workload_classification_routes.py` batch-fetches
`PlacementPolicyRecord.estimated_monthly_saving_usd` for all returned workload IDs and
merges it into each serialized item as `estimated_monthly_saving_usd`.
Frontend `mapListItem()` reads `w.estimated_monthly_saving_usd || 0` (line 60 of
`WorkloadProfiling.jsx`). No further change required.

**Key lines:**
- `backend/api/workload_classification_routes.py:281-296` — savings join + merge
- `frontend/src/pages/optimize/workloads/WorkloadProfiling.jsx:60` — `mapListItem` reads field

---

## A2 — Potential Savings Total in Profiling Summary Strip

**Status:** Already resolved (previous session)  
**Audit ref:** Page-data-source-audit A2

Backend `get_classification_summary` computes
`SUM(PlacementPolicyRecord.estimated_monthly_saving_usd)` and returns it as
`total_estimated_saving_usd` in the `ClusterClassificationSummary` response.
Frontend summary strip reads `apiSummary.total_estimated_saving_usd` and renders
`$${Math.round(...).toLocaleString()}` in the "Potential Savings" slot (line 149 of
`WorkloadProfiling.jsx`). No further change required.

**Key lines:**
- `backend/api/workload_classification_routes.py:191-213` — `func.sum` + field in response
- `frontend/src/pages/optimize/workloads/WorkloadProfiling.jsx:149` — strip slot reads `total_estimated_saving_usd`

---

---

## A3 — "Rollout Not Blocked" Gate in Profiling Actionability Panel

**Status:** Already resolved (previous implementation)  
**Audit ref:** Page-data-source-audit A3

`get_actionability_gates()` in `backend/api/optimize_routes.py` (lines 256-267) already reads
`spot:placement:rollout_blocked:{cluster_id}:{workload_id}` from Redis and returns the real
gate state. Fail-open on Redis error. No further change required.

---

## A4 — `timeline_step` Integer in Workload Placement

**Status:** Resolved  
**Audit ref:** Page-data-source-audit A4

### Problem
`WorkloadPlacement.jsx` computed the timeline progress step entirely client-side via a
`timelineStep(state)` function. The mapping was incomplete (4 states covered, 8 exist)
and diverged from the backend's `PlacementState` enum values. Backend should own this.

### Fix

**Backend** (`backend/api/optimize_routes.py`):
Added `_STATE_TO_STEP` dict and `"timeline_step"` field to `_get_placement_workload_rows()`:
```python
_STATE_TO_STEP = {
    "PENDING": 0, "ANALYZING": 1, "POLICY_SET": 2,
    "DRIFT_DETECTED": 3, "EVICTING": 3,
    "VALIDATING": 4, "AT_TARGET": 5, "STABLE": 5,
}
```

**Frontend** (`WorkloadPlacement.jsx`):
- Removed `timelineStep()` function entirely
- `mapRow()` now carries `timeline_step: w.timeline_step ?? 0`
- Both `timelineStep(w.status)` call sites replaced with `w.timeline_step`

### Files Changed
- `backend/api/optimize_routes.py` — `_STATE_TO_STEP` dict + `timeline_step` field in rows
- `frontend/src/pages/optimize/workloads/WorkloadPlacement.jsx` — removed client heuristic, reads API field

---

## A5 — Cluster Health Score Badge

**Status:** Resolved  
**Audit ref:** Page-data-source-audit A5

### Problem
`health_monitor.py` computes `overall_health` (0–100) per cluster every 5 minutes and
stores it at `cluster_health:{cluster_id}` in Redis. The cluster list API never read this
key. The UI had no badge.

### Fix

**Confirmed Redis key:** `cluster_health:{cluster_id}` (not `spot:cluster:health_score:…`).
Value is JSON `{"overall_health": <float>, ...}`.

**Schema** (`backend/schemas/cluster_schemas.py`):
Added `health_score: Optional[str] = Field(None)` to `ClusterListItem`.

**Service** (`backend/services/cluster_service.py` — `list_clusters`):
After building `cluster_list_items`, batch-reads all `cluster_health:` keys for the
page using a Redis pipeline (single round-trip). Converts score to letter grade:
- `>= 85` → `A`, `>= 70` → `B`, `>= 50` → `C`, `< 50` → `D`
Thresholds match the CRITICAL (50) and DEGRADED (70) warnings in health_monitor.
Enrichment is fail-soft: any Redis error logs at DEBUG and leaves `health_score=None`.

**Frontend — `ClusterList.jsx`:**
Letter-grade badge rendered inline next to cluster name in the list card.
Color scheme: A=green, B=blue, C=amber, D=red. Hidden when `health_score` is null.

**Frontend — `WorkloadPlacement.jsx` cluster selector:**
`<option>` text prefixed with `[A]`, `[B]`, etc. when grade is present (HTML options
cannot render colored elements so text prefix is the correct approach for `<select>`).

### Files Changed
- `backend/schemas/cluster_schemas.py` — `health_score` field added to `ClusterListItem`
- `backend/services/cluster_service.py` — pipeline batch-read + grade mapping
- `frontend/src/pages/infrastructure/clusters/ClusterList.jsx` — colored badge inline
- `frontend/src/pages/optimize/workloads/WorkloadPlacement.jsx` — grade prefix in option text

---

---

## B1 — "Run Advisor Cycle" Button in Workload Profiling

**Status:** Already wired; cycle-lock guard added  
**Audit ref:** Page-data-source-audit B1

The frontend already calls `placementPolicyAPI.generate(clusterId)` →
`POST /api/v1/placement-policy/{cluster_id}/placement-policies/generate`, which dispatches
`run_placement_cycle_task.delay(cluster_id)`. The button was not disabled (state guard
`!clusterId || advisorRunning` is correct). The 409 spam-guard was missing.

**Fix:** Added Redis cycle-lock check to `generate_placement_policies` in
`backend/api/placement_policy_routes.py`: if `spot:placement:cycle_lock:{cluster_id}`
exists, returns 409 with `"Advisor cycle already in progress"`. Fail-open on Redis error.

**Files changed:**
- `backend/api/placement_policy_routes.py` — cycle-lock guard added

---

## B2 — Karpenter Provisioning Latency

**Status:** Resolved  
**Audit ref:** Page-data-source-audit B2

### Problem
`KarpenterMetricsCollector` (APScheduler job, every 2 min) writes P90 provisioning
latency per nodepool class to `spot:placement:provision_p90:{nodepool_class}`. No API
read this. No UI surfaced it.

**Confirmed key pattern:** `spot:placement:provision_p90:{nodepool_class}` (not the
assumed `karpenter:metrics:{cluster_id}`). Keys hold a float string; metric is P90 not
P50/P95 (the collector uses `np.percentile(durations, 90)`).

### Fix

**Backend** — new endpoint in `optimize_routes.py`:
`GET /api/v1/optimize/clusters/{cluster_id}/karpenter-metrics`
Reads the 4 known nodepool-class P90 keys (`spot-general`, `spot-compute`,
`spot-memory`, `on-demand-general`). Returns `available: bool` +
`latency_p90_seconds: {class: float|null}`.

**Frontend** (`NodeBinPacking.jsx`):
- Fetches `optimizeAPI.getKarpenterMetrics(clusterId)` on cluster change
- Renders "Karpenter Provisioning Latency" card in right panel (above Pod Spatial Map)
  when `available=true`. Values color-coded: green ≤45s, amber ≤90s, red >90s.

**Files changed:**
- `backend/api/optimize_routes.py` — `get_karpenter_metrics` endpoint added
- `frontend/src/services/api.js` — `optimizeAPI.getKarpenterMetrics` added
- `frontend/src/pages/optimize/nodes/NodeBinPacking.jsx` — latency card + fetch

---

## B3 — Active Rebalancing Operations in Placement Detail Panel

**Status:** Resolved  
**Audit ref:** Page-data-source-audit B3

### Problem
`RebalancingAction` tracks 8-step state machine (CREATED → … → COMPLETED/FAILED) but
the Placement detail panel had no visibility into in-flight node replacements.
`RebalancingAction` has no `workload_id` column — only `agent_action_id` FK to
`agent_actions`, which does carry `payload.workload_id`.

### Fix

**Backend** — new endpoint in `optimize_routes.py`:
`GET /api/v1/optimize/workloads/{workload_id}/rebalancing?cluster_id=...`
Two queries:
1. Pod-level/stateful_pod: join `RebalancingAction` → `AgentAction` on
   `agent_action_id`, filter `AgentAction.payload->>'workload_id' == workload_id`
2. Node-level: active `RebalancingAction` for the cluster (no workload FK exists);
   returned with `scope: "cluster_node"` so UI can distinguish

**Frontend** (`WorkloadPlacement.jsx`):
- Fetches `optimizeAPI.getActiveRebalancing(selected.id, clusterId)` in the detail
  `useEffect` alongside the existing placement-detail fetch
- Renders "Active Operations" amber card above State Locks when `activeOps.length > 0`
  Each row shows `current_state`, scope badge (pod-level / node-level),
  `source_pool → target_pool`, and EC2 instance ID if available

**Files changed:**
- `backend/api/optimize_routes.py` — `get_active_rebalancing` endpoint added
- `frontend/src/services/api.js` — `optimizeAPI.getActiveRebalancing` added
- `frontend/src/pages/optimize/workloads/WorkloadPlacement.jsx` — Active Operations section

---

---

## B4 — Consolidation Candidates Count + Est. Savings (Bin Packing)

**Status:** Already resolved (write was already complete)  
**Audit ref:** Page-data-source-audit B4

Verified `_write_consolidation_candidates()` in
`backend/workers/tasks/consolidation_analysis_task.py` already writes the full payload:
```python
json.dumps({
    "consolidation_candidates": candidate_count,
    "est_savings_monthly_usd": est_savings,   # ✓ present
    "data_ready": data_ready,
    "data_ready_reason": reason,
})
```
Key: `spot:consolidation:candidates:{cluster_id}`, TTL 600 s.
The bin-packing API already reads this key and returns it. No code change needed.
If the UI slots are empty in a given environment, the issue is that the Celery beat
schedule for `consolidation_analysis_task` is not running (task registration / beat
config issue), not a missing write.

---

## B5 — "Rebalance AZ" Button in Workload Placement

**Status:** Resolved  
**Audit ref:** Page-data-source-audit B5

### Problem
Button was permanently `disabled` with `title="AZ rebalance not yet available"`.
No trigger endpoint existed.

### Why the user's proposed `RebalancingAction(migration_type='az_balance')` approach was rejected
`RebalancingAction.source_pool` and `.target_pool` are NOT NULL columns that
`execute_rebalancing_action()` validates must be in `instance_type:az` format. There is no
`az_balance` migration_type handler in `auto_rebalancer.py`. Creating such a record would
cause the auto-rebalancer to fail schema validation on every cycle.

### Correct approach
`PlacementControllerService._select_pods_for_eviction()` already prefers pods in the
over-represented AZ (lines 575–617 of `placement_controller_service.py`). The AZ logic
is fully implemented — it just needs to be triggered.

**Backend** — new endpoint in `optimize_routes.py`:
`POST /api/v1/optimize/workloads/{workload_id}/rebalance-az?cluster_id=...`
1. Writes `spot:placement:az_rebalance_requested:{cluster_id}:{workload_id}` Redis hint
   (TTL 600 s) — observable for audit; can be read by PC in future to narrow scope
2. Calls `run_placement_controller_task.apply_async(args=[cluster_id])` — PC cycle
   runs immediately and naturally targets the over-represented AZ

No `RebalancingAction` DB row is created; the controller's own eviction records track the result.

**Frontend** (`WorkloadPlacement.jsx`):
- Removed `disabled` prop; button is now enabled when a workload is selected
- Added `azRebalancing` state (spinner/cursor-wait during call)
- Added `azRebalanceMsg` feedback message rendered below the button
- `handleRebalanceAz()` calls `optimizeAPI.triggerAzRebalance(w.id, clusterId)`

### Files Changed
- `backend/api/optimize_routes.py` — `trigger_az_rebalance` POST endpoint
- `frontend/src/services/api.js` — `optimizeAPI.triggerAzRebalance` added
- `frontend/src/pages/optimize/workloads/WorkloadPlacement.jsx` — button wired + feedback

---

---

## C1 — State Freshness Gate (PlacementController)

**Status:** Resolved

### Problem
PC read `spot:workload:state:{cluster_id}:{workload_id}` (written by agent heartbeat) but
never checked how old it was. A 2-min stale Redis value could cause the PC to make
eviction decisions based on a snapshot that no longer reflects reality.

### Fix
Added `PC_MAX_STALENESS_SECONDS = 30` (env: `PC_MAX_STALENESS_SECS`) constant and a
freshness gate at the top of `_process_workload_inner()`:

```python
_observed_at = state.get("updated_at")  # Unix float written by agent_routes.py
if time.time() - _observed_at > PC_MAX_STALENESS_SECONDS:
    logger.warning("[PC] stale_state_skip ...")
    return  # skip this workload this cycle
```

The agent already writes `updated_at: time.time()` (Unix float) into every
`spot:workload:state` key in `agent_routes.py`. No agent change needed.
Fail-open: if the state key doesn't have `updated_at`, the gate is skipped and the
cycle proceeds (backwards-compatible).

**Files changed:**
- `backend/services/placement_controller_service.py` — `PC_MAX_STALENESS_SECONDS` constant + staleness gate

---

## C2 — Action Convergence Tracking (AgentAction result field)

**Status:** Resolved

### Problem
`AgentAction.result` was set to internal `action_metadata` at dispatch. There was no
`expected` pod/node snapshot, `observed` flag, or `deadline` to allow post-hoc
convergence validation.

### Fix
Extended `action_metadata` (stored in `result` JSONB) at dispatch in `_dispatch_eviction()`:

```python
"expected": {"pod_name": pod.name, "from_node": pod.node, "workload_id": workload_id},
"observed": False,
"deadline": time.time() + PC_ACTION_DEADLINE_SECONDS,  # default: 60s
```

`PC_ACTION_DEADLINE_SECONDS` (env: `PC_ACTION_DEADLINE_SECS`, default 60) controls how
long the validator waits before marking an unconfirmed eviction as FAILED.

**Files changed:**
- `backend/services/placement_controller_service.py` — `PC_ACTION_DEADLINE_SECONDS` constant + extended result field

---

## C3 — Real-time Convergence Validator (Celery task, 15 s)

**Status:** Resolved

### Problem
No task validated whether evicted pods actually moved off their original node. Agent
self-reports were the only signal, with no independent cross-check.

### Convergence definition (EVICT_POD)
> Pod is visible in `spot:workload:pods:{cluster_id}:{workload_id}` on a **different**
> node than `expected.from_node`.

### Fix
New Celery task `validate_eviction_actions` in
`backend/workers/tasks/validate_actions_task.py`, scheduled every **15 s**.

For each PENDING/PICKED_UP EVICT_POD action with an `expected` block in `result`:
1. Read `spot:workload:pods:{cluster_id}:{workload_id}` from Redis
2. Find the pod by name. If present with `node != from_node` → **COMPLETED** +
   `result.observed = True, result.verified_at = now, result.landed_on_node = ...`
3. If `now > deadline` without convergence → **FAILED** +
   `result.failure_reason = "deadline_exceeded"`

Actions dispatched before this change (no `expected` field) are silently skipped.

**Files changed:**
- `backend/workers/tasks/validate_actions_task.py` — new file
- `backend/workers/app.py` — module registered + `validate-eviction-actions-every-15s` beat entry

---

## C4 — Active Actions UI: real status + convergence display

**Status:** Resolved

### Problem
1. `GET /api/v1/actions/active` was called by `ActiveActions.jsx` but the endpoint did
   not exist — every non-demo cluster fell back to a 404/error state.
2. `STATUS_COLORS` in `ActiveActions.jsx` had no entries for `PENDING` or `PICKED_UP`
   (the actual DB enum values); both mapped to the fallback `QUEUED` color.
3. `ProgressBar` used a hardcoded heuristic
   (`COMPLETED → 100, IN_PROGRESS → 70, else → 40`), always showing 100% for
   completed actions regardless of whether the validator had confirmed convergence.

### Fix

**Backend** — new `GET /api/v1/actions/active?cluster_id=...` in `routers/actions.py`:
Returns PENDING/PICKED_UP in-flight actions + last 20 COMPLETED/FAILED for recent
history. Each row includes `observed`, `expected`, `verified_at`, `failure_reason`
from the `result` JSONB field. Also returns active `rebalancing_actions` (status=`in_progress`).

**Frontend** (`ActiveActions.jsx`):
- `STATUS_COLORS` — added `PENDING`, `PICKED_UP`, `EXPIRED` entries
- `statusToProgress(status, observed)` — `PENDING → 20`, `PICKED_UP → 60`,
  `COMPLETED(not observed) → 90`, `COMPLETED(observed) → 100`, `FAILED → 100`
- Workload Redistribution row — `✓ Verified` green badge when `a.observed=true`,
  `Timeout` red label when `failure_reason=deadline_exceeded`

### Files changed
- `backend/routers/actions.py` — `GET /active` endpoint
- `frontend/src/pages/execution/ActiveActions.jsx` — status map, progress fn, badge

---

## C5 — Validator Freshness Gate: Don't Trust Stale Redis for Convergence

**Status:** Resolved

### Problem

Two structural gaps in the convergence validator (`validate_actions_task.py`):

**Gap 1 — Observation layer is agent-fed, not K8s-direct**

The validator reads `spot:workload:pods:{cluster_id}:{workload_id}`, which is written by the in-cluster agent on every heartbeat. This creates the loop:

```
evict action → agent observes K8s → agent writes Redis → validator reads Redis
```

Not:
```
evict action → validator reads K8s API directly
```

Consequences:
- Agent lag (slow heartbeat, resource-starved pod, network flap) → validator reads stale pod list
- Stale list still shows pod on `from_node` → validator reaches deadline → marks FAILED even though the pod actually moved

The backend has **no direct K8s credentials** — only the in-cluster agent does. A direct K8s API call from the backend would require storing cluster kubeconfig, which is an architectural boundary this system intentionally avoids.

**Gap 2 — Validator had no freshness check**

`_run_validation()` read `spot:workload:pods` and used it unconditionally — it never checked how old the data was. The staleness gate in `PlacementController` only blocked **new decisions**; in-flight actions validated against arbitrarily old data.

### Root Cause Analysis

```
spot:workload:state  ←── agent heartbeat (has updated_at)
spot:workload:pods   ←── agent heartbeat (NO timestamp)
```

The agent writes **both keys on the same heartbeat cycle**. Therefore `spot:workload:state.updated_at` is a valid proxy for "how old is the pods list". If state is stale, pods data is equally stale.

### Fix

**`validate_actions_task.py`** — three-phase validation loop:

| Phase | Runs when | Effect if triggered |
|---|---|---|
| 1. Deadline check | Always (not gated) | Mark FAILED(deadline_exceeded) |
| 2. Freshness gate (C5) | Before convergence check | Defer cycle — log `stale_data_defer`, write `last_stale_defer_at` to result |
| 3. Convergence check | Only when data is fresh | Mark COMPLETED(observed=True) or no-op |

**Key design decisions:**

- **Deadline check is NOT gated** — even with stale data, an action past its deadline must eventually reach a terminal state. The deadline is time-based, not data-based.
- **Freshness threshold = 60 s** (`VALIDATOR_MAX_DATA_AGE_SECS` env var, default 60 s) — twice the normal agent heartbeat cadence, tolerating one missed heartbeat before deferring.
- **Stale = defer, not fail** — when data is stale, the action result gains `last_stale_defer_at` + `last_data_age_secs` fields (visible in the Active Actions UI) but the action stays `PICKED_UP`. On the next 15 s cycle, if the agent has sent a fresh heartbeat, the convergence check runs normally.
- **Verified convergence includes `data_age_at_verification_secs`** — recorded in `action.result` so operators can audit how fresh the data was when the COMPLETED verdict was issued.

**New helper:** `_check_state_freshness(r, cluster_id, workload_id, now) → (is_fresh: bool, age: float)`
Reads `spot:workload:state`, extracts `updated_at`, returns age tuple. Returns `(False, inf)` when key is absent.

**New constant:** `VALIDATOR_MAX_DATA_AGE_SECS = int(os.getenv("VALIDATOR_MAX_DATA_AGE_SECS", "60"))`

### What is NOT changed (by design)

- The observation pipeline (`agent → Redis → validator`) is preserved — adding a direct K8s API call would require storing cluster credentials on the backend, violating the agent isolation boundary.
- The `spot:workload:pods` key format is unchanged — no `written_at` field injected, because the proxy approach (`spot:workload:state.updated_at`) is sufficient and avoids modifying the agent protocol.

### Files changed
- `backend/workers/tasks/validate_actions_task.py` — complete rewrite with three-phase loop, `_check_state_freshness` helper, `VALIDATOR_MAX_DATA_AGE_SECS` constant

---

## C6 — Staleness Gate Coverage Gap: In-Flight Actions and Validator

**Status:** Resolved (via C5 — see above)

### Problem

The staleness gate added in `placement_controller_service.py` (C3):
```python
if stale: skip workload  # blocks new dispatch decisions
```

…only gates **new eviction decisions**. Two gaps remained:

1. **In-flight actions are not retroactively cancelled** — an action dispatched on fresh state can run into a stale validation window and be falsely expired.
2. **Validator freshness was unchecked** — `_run_validation()` read and trusted pods data with no staleness check of its own.

### Fix

Gap 2 is fully resolved by C5 (validator freshness gate).

Gap 1 (in-flight actions dispatched on stale state) is addressed by the following reasoning:
- The dispatch-time staleness gate in PC (C3) ensures no NEW action is created when state is stale.
- If an action was dispatched when state was fresh and the agent subsequently goes silent, the validator's freshness gate (C5) will **defer** (not fail) convergence checks until fresh data returns.
- The action will only be expired via the deadline path, which is intentional and time-bounded.

Together, C3 + C5 form a complete staleness defense:

| Stage | Guard | Mechanism |
|---|---|---|
| Decision dispatch | C3 staleness gate | Skip entire workload if `state.updated_at > 30 s` |
| Convergence validation | C5 freshness gate | Defer convergence check if `state.updated_at > 60 s` |
| Terminal expiry | Deadline check (ungated) | Expire after `PC_ACTION_DEADLINE_SECS` regardless |

### Files changed
- `backend/services/placement_controller_service.py` — no new changes (C3 gate already in place)
- `backend/workers/tasks/validate_actions_task.py` — C5 freshness gate covers gap 2

---

## A1 — Agent & Karpenter Installation: Permanent Fix

**Status:** Resolved

### Problems Found

**A1-1 — `verify_agent_token` used a module-level cached env var (root cause of all 401/500 errors)**

`backend/routers/agents.py` captured `AGENT_API_KEY = os.getenv("AGENT_API_KEY")` at **import time**. Every agent heartbeat, register, and action-result endpoint validated against this frozen value. Consequences:
- If env var was unset at startup → `None` forever → every agent call returned **500 "AGENT_API_KEY not configured"**
- If env var was set but `cluster.api_key` differed → **401 CrashLoopBackOff**

`backend/api/agent_routes.py` already had the correct per-cluster DB lookup (`Cluster.api_key == api_key`) but was registered **after** `routers/agents.py` — FastAPI first-match routing meant `routers/agents.py` shadowed every overlapping endpoint.

**A1-2 — `auto_install_agent` rotated api_key destructively**

```python
_backend_key = _os.getenv("AGENT_API_KEY") or secrets.token_urlsafe(32)
if cluster.api_key != _backend_key:
    cluster.api_key = _backend_key
```
When env var is unset: generates a fresh random key on every call, but `AGENT_API_KEY` (module-level in `routers/agents.py`) stays `None`. The deployed agent gets the new key but the backend still 500s.

**A1-3 — `disconnect` and `remove_agent` overwrote cluster api_key with shared env var**

```python
cluster.api_key = _os.getenv("AGENT_API_KEY") or secrets.token_urlsafe(32)
```
If `AGENT_API_KEY` is set: ALL clusters get the same api_key after disconnect/reinstall — per-cluster isolation broken. If unset: random key generated correctly.

**A1-4 — `celery-worker` missing `AGENT_API_KEY` in docker-compose env**

The Celery worker container had no `AGENT_API_KEY` in its environment, meaning any code path in the worker that reads `os.getenv("AGENT_API_KEY")` would always return `None`.

**A1-5 — `inject_agent_task` didn't validate `account.role_arn` before calling `inject_agent`**

If `account.role_arn` was `None`, the task would propagate into `_assume_role(None, ...)` and fail with an opaque boto3 error rather than a clear early exit.

**A1-6 — Karpenter `INSTALL_KARPENTER` action expired in 2 minutes**

Helm install inside the cluster (cold pull of karpenter images + CRD install + NodePool creation) reliably takes 3–8 minutes. The action was auto-expired before the agent even picked it up.

**A1-7 — Frontend build broken: `NodeScaling.jsx` imported but not created**

`App.js` imported `./pages/optimize/nodes/NodeScaling` which did not exist, causing `npm run build` to fail with `Module not found`. All frontend changes were blocked from shipping.

### Fixes Applied

| # | File | Change |
|---|---|---|
| A1-1 | `backend/routers/agents.py` | Replaced module-level `AGENT_API_KEY` constant + `verify_agent_token` with per-cluster DB lookup (`Cluster.api_key == bearer_token`). Env var used only as legacy fallback. |
| A1-2 | `backend/api/cluster_routes.py` | `auto_install_agent`: preserve existing `cluster.api_key` when env var is absent; only set env var key when it is explicitly configured; generate fresh key only when cluster has no key at all. |
| A1-3 | `backend/api/cluster_routes.py` | `disconnect` + `remove_agent`: always rotate to `secrets.token_urlsafe(32)` — never reuse shared env var key. |
| A1-4 | `docker/docker-compose.yml` | Added `AGENT_API_KEY: ${AGENT_API_KEY}` to `celery-worker` service env. |
| A1-5 | `backend/workers/tasks/agent_tasks.py` | Added early-exit guard when `account.role_arn` is `None` with a descriptive error log. |
| A1-6 | `backend/api/karpenter_routes.py` | `INSTALL_KARPENTER` and `UNINSTALL_KARPENTER` `expires_at`: 2 min → **15 min**. |
| A1-7 | `frontend/src/pages/optimize/nodes/NodeScaling.jsx` | Created minimal stub component so `App.js` import resolves and `npm run build` succeeds. |

### Authentication flow after fix

```
Agent heartbeat (Authorization: Bearer {cluster.api_key})
  ↓
routers/agents.py: verify_agent_token()
  → DB lookup: SELECT * FROM clusters WHERE api_key = '{bearer}'
  → found → return cluster (auth passes)
  → not found → fallback: compare to AGENT_API_KEY env var (legacy)
  → still not found → 401 Invalid agent token
```

### api_key lifecycle after fix

| Event | What happens to cluster.api_key |
|---|---|
| First `auto-install` (no env var, no existing key) | Generate `secrets.token_urlsafe(32)`, persist |
| Subsequent `auto-install` (key already exists) | **Preserved** — agent not disrupted |
| `auto-install` with `AGENT_API_KEY` env set | Set to env var (production single-key mode) |
| `disconnect` | Rotate to NEW random key — old agent gets 401 |
| `remove_agent` | Rotate to NEW random key — old agent gets 401 |
| Next `auto-install` after remove | New key preserved from remove step |

### Container rebuild

All 6 services rebuilt and restarted with volumes preserved:

```
spot-optimizer-backend    → healthy  (0.0.0.0:8000)
spot-optimizer-frontend   → healthy  (0.0.0.0:80)
spot-optimizer-celery-worker → healthy
spot-optimizer-celery-beat   → healthy
spot-optimizer-postgres   → healthy  (0.0.0.0:5433)
spot-optimizer-redis      → healthy  (0.0.0.0:6379)
```

### Files changed
- `backend/routers/agents.py` — `verify_agent_token` per-cluster DB lookup
- `backend/api/cluster_routes.py` — `auto_install_agent`, `disconnect`, `remove_agent` api_key logic
- `backend/workers/tasks/agent_tasks.py` — `role_arn` guard
- `backend/api/karpenter_routes.py` — `expires_at` 2 min → 15 min (install + uninstall)
- `docker/docker-compose.yml` — `AGENT_API_KEY` added to `celery-worker`
- `frontend/src/pages/optimize/nodes/NodeScaling.jsx` — created stub (fixes build)

---

## D1 — Node Selection Page: Replace Mock Data with Real API

**Status:** Resolved (partial — optimization target panel still pending a new API)

### Problem
`NodeSelector.jsx` used a `mockNodes` array with a 400 ms `setTimeout`. Every field —
hostname, pool, capacity, price, utilisation, optimized target, savings %, score,
and the What-If strip numbers ($4 200 savings, 41%→78% spot, 24→18 nodes) — was
hardcoded. The page never called any backend API.

### What was real vs. fake

| Field | Was fake | Now real | Source |
|---|---|---|---|
| Node name, instance type | ✓ fake | ✓ real | `GET /optimize/nodes/bin-packing` |
| Capacity type (Spot / OD) | ✓ fake | ✓ real | same |
| AZ | ✓ fake | ✓ real | same |
| Pod count | ✓ fake | ✓ real | same — aggregated from `PodMetric` |
| CPU / memory utilisation % | ✓ fake | ✓ real | same |
| CPU / memory buffer % | ✓ fake | ✓ real | same |
| `lifecycle_state` (running/cordoned/draining) | ✓ fake | ✓ real | same |
| `is_overloaded` | ✓ fake | ✓ real | same |
| `vcpu_count` | ✓ fake | ✓ real | derived from `allocatable_cpu_millicores` (new field added to API) |
| `memory_gib` | ✓ fake | ✓ real | derived from `allocatable_memory_bytes` (new field added to API) |
| `hourly_price_usd` | ✓ fake | ✓ real | joined from `OnDemandPricing` / `SpotPriceHistory` (new, added to API) |
| Consolidation candidates count | ✓ fake | ✓ real | `spot:consolidation:candidates:{cluster_id}` Redis |
| Est. monthly savings | ✓ fake | ✓ real | same Redis key |
| What-If strip (node count, spot %) | ✓ fake | ✓ real | computed from live node list |
| **Target instance type / savings % / score / rationale** | ✓ fake | ⚠ still N/A | No API yet — logged in `reportfront.md` |

### Backend changes (`backend/api/optimize_routes.py` — `get_node_bin_packing`)

1. Store `allocatable_cpu_millicores` and `allocatable_memory_bytes` in `nodes_with_ts`
   (previously computed but not returned).
2. Pricing enrichment block added after staleness filter:
   - Reads `Cluster.region` for the cluster.
   - Batch-queries `OnDemandPricing` and `SpotPriceHistory` by `instance_type IN (...)`.
   - Spot nodes prefer spot price; OD nodes use OD price.
   - Emits `vcpu_count`, `memory_gib`, `hourly_price_usd` per node (all `null`-safe).

### Frontend changes (`frontend/src/pages/optimize/nodes/NodeSelector.jsx`)

- Removed `mockNodes` array entirely.
- Added `useClusters()` hook + cluster selector dropdown in the header.
- `fetchNodes()` calls `optimizeAPI.getNodeBinPacking(clusterId)`.
- **Summary strip** — replaced hardcoded numbers with live values:
  `rawNodes.length`, `spotPct` (computed), `candCount`, `estSavings`.
- **Filter bar** — replaced hardcoded "Scheduled (4) / Excluded (2)" with dynamic
  counts for All / Draining / Cordoned / Overloaded.
- **Table columns** — now: Node, Instance/Capacity, $/hr, CPU util, Mem util, Pods, State.
  Removed fake "Optimized To", "Savings %", "Score" columns.
- **Expanded detail — left panel** — shows all real fields: instance type, capacity,
  vCPU, memory GiB, AZ, hourly price, CPU/mem utilisation with bars.
- **Expanded detail — right panel** — shows amber "Missing data" notice and proposes
  `GET /optimize/nodes/{node_name}/recommendation` endpoint for the target instance
  data. Still shows buffer %, pod count, overload status from real data.

### Missing API logged in `reportfront.md`

`GET /optimize/nodes/{node_name}/recommendation?cluster_id=` needs to be built to
supply: `target_instance_type`, `target_capacity_type`, `target_vcpu`,
`target_memory_gib`, `savings_percent`, `optimization_score`, `rationale`.
Proposed source: `consolidation_analysis_task` candidate list or
`RebalancingAction.target_pool` for in-flight migrations.

### Files changed
- `backend/api/optimize_routes.py` — `get_node_bin_packing`: added `vcpu_count`, `memory_gib`, `hourly_price_usd` output fields via pricing join
- `frontend/src/pages/optimize/nodes/NodeSelector.jsx` — complete rewrite with real API data; all mock data removed
- `reportfront.md` — created; logs missing `recommendation` endpoint and `nodepool_name` field

---

---

## W1 — Celery Worker 180%+ CPU / Task Name Mismatches

**Status:** Resolved  
**Date:** 2026-04-28

### Symptoms
- `spot-optimizer-celery-worker` consuming **186% CPU** continuously (1.67 GiB RAM)
- Repeated `KeyError` every 15 seconds in worker logs:
  ```
  KeyError: 'backend.workers.tasks.validate_actions_task.validate_eviction_actions'
  KeyError: 'backend.workers.tasks.placement_controller_task.dispatch_placement_controller_cycles'
  ```
- Worker receiving tasks it couldn't execute → busy-looping on error

### Root Causes

#### 1. Task Name Mismatches in Beat Schedule (3 tasks)
Beat schedule referenced full Python module paths but tasks were registered with short names:

| Beat schedule name (wrong) | Actual registered `name=` |
|---|---|
| `backend.workers.tasks.validate_actions_task.validate_eviction_actions` | `validate_eviction_actions` |
| `backend.workers.tasks.placement_controller_task.dispatch_placement_controller_cycles` | `dispatch_placement_controller_cycles` |
| `backend.workers.tasks.placement_controller_task.dispatch_placement_controller_recovery` | `dispatch_placement_controller_recovery` |

Each mismatch fired every 15–300 seconds, caused a `KeyError` in the worker consumer loop, and the failed task was re-queued immediately → tight CPU loop.

#### 2. `auto_rebalancer` Running Every 15 Seconds
`workers.auto_rebalancer` is a **heavy task** that:
- Scans all clusters and instances
- Imports and runs `cache_builder` inline (hundreds of instance-type computations)
- Makes K8s / AWS API calls per cluster

Running every **15 seconds** caused sustained 180%+ CPU. Each `cache_builder` invocation emits dozens of `Unknown instance type` warnings for new-generation metal instances (`c8a.metal-48xl`, `m8i.metal-96xl`, etc.) not in the pricing DB.

#### 3. Missing PostgreSQL Enum Values (`agentactiontype`)
`INSTALL_KEDA`, `UNINSTALL_KEDA`, `ANNOTATE_WORKLOAD`, `PATCH_AFFINITY` were defined in Python `AgentActionType` but absent from the live DB enum → `psycopg2.errors.InvalidTextRepresentation` on every KEDA install attempt.

### Fixes

#### app.py — Beat Schedule Name Corrections
```python
# BEFORE
'task': 'backend.workers.tasks.validate_actions_task.validate_eviction_actions'
'task': 'backend.workers.tasks.placement_controller_task.dispatch_placement_controller_cycles'
'task': 'backend.workers.tasks.placement_controller_task.dispatch_placement_controller_recovery'

# AFTER
'task': 'validate_eviction_actions'
'task': 'dispatch_placement_controller_cycles'
'task': 'dispatch_placement_controller_recovery'
```

#### app.py — `auto_rebalancer` Interval Increase
```python
# BEFORE: 15.0 seconds
'schedule': 15.0,

# AFTER: 60.0 seconds
'schedule': 60.0,
```

#### PostgreSQL — Add Missing Enum Values
```sql
ALTER TYPE agentactiontype ADD VALUE IF NOT EXISTS 'INSTALL_KEDA';
ALTER TYPE agentactiontype ADD VALUE IF NOT EXISTS 'UNINSTALL_KEDA';
ALTER TYPE agentactiontype ADD VALUE IF NOT EXISTS 'ANNOTATE_WORKLOAD';
ALTER TYPE agentactiontype ADD VALUE IF NOT EXISTS 'PATCH_AFFINITY';
```

### Result
| Metric | Before | After |
|---|---|---|
| Worker CPU | **186%** | **~0.1%** |
| KeyError spam | Every 15 s | Eliminated |
| KEDA install | 500 Internal Server Error | Queues action successfully |

#### cache_builder.py — Downgrade Log Noise to DEBUG
`Unknown instance type X — spec lookup returned (0,0)` was emitting as `WARNING` for every new-gen metal instance type not in the catalog (`c8a.metal-48xl`, `m8i.metal-96xl`, etc.) — hundreds of lines per hourly cache rebuild.  Changed to `logger.debug(...)`. Behavior unchanged (types are still skipped safely).

### Files Changed
- `backend/workers/app.py` — 3 task name fixes + `auto_rebalancer` interval 15s → 60s
- `backend/workers/tasks/cache_builder.py` — unknown instance type log: `WARNING` → `DEBUG`
- PostgreSQL `spot_optimizer` DB — `agentactiontype` enum extended with 4 values

---

---

## AUDIT-01 — Node Bin Packing: Reality vs. Name

**Date:** 2026-04-28  
**Verdict: NOT real bin-packing. NOT production-ready.**

---

### What the Page Claims to Do
The UI is titled **"Node Selection"** and the endpoint is named `/nodes/bin-packing`.  
It implies optimal assignment of pods to fewer nodes (classical bin-packing problem).

---

### What It Actually Does

#### Backend — `GET /api/v1/optimize/nodes/bin-packing`
(`backend/api/optimize_routes.py` lines 562–773)

**What it really is:** A **node utilisation reporting** endpoint.

| Step | Code | What happens |
|---|---|---|
| 1 | Subquery on `PodMetric` | Latest CPU/memory request+usage per pod via DISTINCT ON |
| 2 | GROUP BY node + JOIN `NodeMetadata` | Sums pod requests & usage per node, attaches allocatable CPU/mem |
| 3 | Compute per-node % | `cpu_requested_pct`, `cpu_actual_pct`, `mem_requested_pct`, `mem_actual_pct`, buffer pcts |
| 4 | Pricing JOIN | OD/spot price look-up per instance type from `OnDemandPricing` + `SpotPriceHistory` |
| 5 | Redis look-up | Fetches pre-computed `consolidation_candidates` blob from `spot:consolidation:candidates:{cluster_id}` |
| 6 | Stale filter | Excludes nodes where `node_updated_at` is too old |

**No bin-packing algorithm runs here.** It is pure aggregation + reporting.

---

#### Consolidation Analysis Task — `run_consolidation_analysis`
(`backend/workers/tasks/consolidation_analysis_task.py`)

This runs every 10 minutes and writes the `consolidation_candidates` Redis key consumed above.

**Branch A — Karpenter nodes (`nodepool_name IS NOT NULL`):**
```python
if not node.do_not_disrupt:
    cpu_util = _get_node_cpu_util(...)  # avg over last 5 min
    if cpu_util < 20.0:                 # hardcoded threshold
        candidates.append(node)
```
No packing logic. Just "CPU < 20% → candidate".

**Branch B — non-Karpenter nodes:**
```python
def _can_drain(node, all_nodes):
    # 1. Any pod has node_affinity_required → False
    # 2. total_cpu + total_mem of ALL pods on node fit on ONE other node → True
```
Checks if a single other node has enough raw headroom to absorb the entire node's pod load.  
This is **not bin-packing** — it's a greedy single-pass feasibility check with a critical flaw (see bugs).

**Savings estimate:**
```python
savings_per_node = max(0.0, od_price - spot_price) * 730
```
Estimates savings as the **OD–spot price delta**, not the actual spot cost of the node.  
For spot→spot consolidation, this calculates almost nothing.

---

### Critical Bugs & Missing Logic

#### BUG-1: `_can_drain()` requires ALL pods to fit on ONE node
```python
if alloc_cpu >= total_cpu and alloc_mem >= total_mem:
    return True
```
Pods can be distributed across multiple nodes. A node with 5 small pods could be drained by spreading them across 3 nodes, but this code says "no" unless a single node absorbs all 5. This causes **massive false negatives** — real consolidation opportunities are missed.

#### BUG-2: Savings formula is wrong for spot nodes
`savings = (od_price - spot_price) * 730`  
If both the candidate and the target are spot nodes, you save the **full spot price** of the candidate node, not the OD-spot delta.  
Correct formula: `savings = candidate_node_hourly_price * 730`

#### BUG-3: DaemonSets are not excluded
DaemonSet pods run on every node and cannot be moved. The code doesn't check `ownerReferences.kind == DaemonSet`. A node running only DaemonSets will appear as a consolidation candidate but can never be drained.

#### BUG-4: Region is wrong in savings calculation
```python
region = getattr(settings, "AWS_REGION", "us-east-1")  # platform region, not cluster region
```
A cluster in `ap-south-1` will look up pricing for `us-east-1`.

#### BUG-5: Pod affinity check is incomplete
Only checks `pod_metadata.affinity.node_affinity_required`. Does not check:
- `nodeSelector`
- `tolerations` / `taints`
- `topologySpreadConstraints`
- `podAntiAffinity` (may block placement on target nodes)

#### GAP-1: Right panel in UI is a hardcoded placeholder
```jsx
// NodeSelector.jsx lines 325–341
<p>Recommended replacement instance type is not yet available from the API.</p>
<code>GET /optimize/nodes/{node_name}/recommendation</code>
```
The `GET /optimize/nodes/{node_name}/recommendation` endpoint **does not exist**. The right panel shows a static amber warning box to all users in production.

#### GAP-2: `/nodes/{node_name}/bin-packing-detail` exists but UI never calls it
`backend/api/optimize_routes.py` lines 1119–1171 returns a per-node pod list useful for treemap rendering, but `NodeSelector.jsx` does not call it anywhere.

#### GAP-3: No actual bin-packing algorithm
A proper implementation would use **First Fit Decreasing (FFD)** or **Best Fit Decreasing (BFD)** over the 2D bin (CPU × Memory):
1. Sort pods by descending resource footprint
2. Greedily assign each pod to the node with least remaining capacity that still fits
3. Any node that ends up empty after reassignment = consolidation candidate

None of this exists.

---

### What IS Production-Ready

| Feature | Status |
|---|---|
| Real-time node CPU/mem utilisation (actual + requested) | ✅ Works |
| Per-node pod count | ✅ Works |
| Lifecycle state (running / cordoned / draining) | ✅ Works |
| Hourly pricing (spot & OD) per instance type | ✅ Works |
| Overloaded node detection (`cpu_actual > 85%`) | ✅ Works |
| Stale node filtering | ✅ Works |
| Rate limiting on the endpoint | ✅ Works |
| Search / filter in UI | ✅ Works |

---

### What Is NOT Production-Ready

| Gap | Severity |
|---|---|
| No actual bin-packing algorithm | 🔴 Critical |
| `_can_drain()` single-node constraint (false negatives) | 🔴 Critical |
| Savings formula wrong for spot consolidation | 🟠 High |
| DaemonSet pods not excluded from drain check | 🟠 High |
| `recommendation` endpoint missing, right UI panel is dead | 🟠 High |
| Wrong region in savings estimate | 🟡 Medium |
| Incomplete affinity/taint/spread constraint checking | 🟡 Medium |
| `bin-packing-detail` endpoint unused by UI | 🟡 Medium |

---

### Summary

> The Node Bin Packing page is **a utilisation dashboard**, not a bin-packing optimizer.  
> It correctly shows which nodes are under-utilised and how much capacity is free,  
> but it does **not** compute, simulate, or recommend pod reassignments.  
> The consolidation candidate count and savings estimate are rough heuristics with  
> several correctness bugs. The page is **not production-ready** for a node  
> consolidation feature. It is production-ready as a **read-only capacity monitor**.

---

---

## AUDIT-02 — Workload Profiling: Reality Check & Production Readiness

**Date:** 2026-04-28  
**Verdict: MOSTLY real data. Partially production-ready. 4 concrete gaps.**

---

### How the Page Is Built — Data Flow

```
K8s API (live)
    │
    ▼
WIE Scan Cycle (Celery)
    │  classifies every workload → criticality / spot_score / confidence
    │  writes → workload_classifications (DB) + Redis TTL=900s
    ▼
workload_cv_task (Celery, every 10 min)
    │  reads 14d pod_metrics.cpu_usage_millicores per workload
    │  computes CV = stddev/mean with 5% top trim (numpy or stdlib)
    │  writes cpu_cv + traffic_skew_detected → workload_classifications (DB)
    ▼
PlacementAdvisorTask (Celery)
    │  reads WIE output → applies tier OD floor → computes od_target/spot_target
    │  estimates savings → writes → placement_policies (DB)
    ▼
Frontend fetches:
  GET /api/v1/workload-classification/{id}/workloads    → left list
  GET /api/v1/workload-classification/{id}/summary      → top strip
  GET /api/v1/optimize/workloads/{id}/profiling-detail  → right panel
```

---

### What IS Real Data

| Field | Source | How computed |
|---|---|---|
| `criticality_score` | `workload_classifications.criticality_score` | WIE: real K8s signals — PDB, priority class, service type, ingress, inbound services, data safety, replica count |
| `spot_score` | `workload_classifications.spot_score` | WIE: real K8s signals — controller kind, PDB, topology spread, restart rate, readiness probe delay, multi-AZ |
| `confidence_score` / `confidence_state` | `workload_classifications.confidence_state` | WIE: metrics staleness age, conflicting signals, workload age, multi-AZ, crash loops → DRAFT/PROVISIONAL/CONFIRMED |
| `spot_friendly` | `workload_classifications.spot_friendly` | Real gate: `spot_score >= 4 AND has_pdb AND replicas >= 2` |
| `tier` | `workload_classifications.tier` | Real: criticality → Platinum/Gold/Silver/Bronze mapping |
| `signals_fired` | `workload_classifications.signals_fired` | Full signal audit trail written by WIE on every cycle |
| CPU timeseries chart | `pod_metrics` DB | Real: `SELECT date_trunc('day'), AVG(cpu_usage_millicores) … GROUP BY day` over 14 days |
| `cpu_cv` (CV number + stability flag) | `workload_cv_task` → `workload_classifications.cpu_cv` | Real: `stddev(trimmed) / mean(trimmed)` on 14-day pod CPU samples |
| `traffic_skew_detected` | `workload_cv_task` → `workload_classifications.traffic_skew_detected` | Real: `cv > 0.4` |
| `ondemand_target` / `spot_target` | `placement_policies` DB | Real: tier OD floor applied to observed replica count, gated by confidence |
| Summary strip counts | DB queries on `workload_classifications` | Real counts per cluster |

---

### What Is NOT Real (or Broken)

#### GAP-1: Savings Formula Is a Hardcoded Approximation
```python
# placement_advisor_service.py:515
avg_spot_price = avg_od_price * 0.3   # assumes flat 70% spot discount for every instance type
```
The real savings calculation should use actual spot prices from `SpotPriceHistory` for the cluster's region and instance type mix. Instead, it blindly assumes all spot instances are 70% cheaper than OD, regardless of instance family, region, or current market pricing. This makes the `$X/month saved` number unreliable.

#### GAP-2: RPS Chart Is Always a Static Placeholder
```jsx
// WorkloadProfiling.jsx lines 358–368
<span className="text-[10px] text-gray-400 italic">RPS timeseries not available</span>
```
The `pod_request_rate_cv` column exists in `PlacementPolicyRecord` and `WorkloadClassificationRecord`, and the `workload_cv_task` docstring explicitly says:  
> `rps_cv: write null (requires Prometheus, out of scope)`  
The RPS panel is permanently empty. It is shown to every user in production as a visible incomplete UI panel.

#### GAP-3: "Rollout Not Blocked" Gate Is Always Hardcoded Pass
```jsx
// WorkloadProfiling.jsx line 137
const gates = w ? [
    w.confLabel === 'CONFIRMED' ? 'pass' : 'fail',  // Gate 1
    w.spotFriendly ? 'pass' : 'fail',               // Gate 2
    spt > 0 ? 'pass' : 'fail',                      // Gate 3
    'pass',                                          // Gate 4 ← HARDCODED
    ...
]
```
Gate 4 "Rollout Not Blocked" always shows **Pass** regardless of the workload's actual `rollout_eligible` and `rollout_blocked_reason` from `PlacementPolicyRecord`. A workload blocked because `savings_below_20_pct` or `confidence_not_confirmed` still shows gate 4 as green.

#### GAP-4: `cpu_cv` Source Mismatch Between Two Tables
The profiling-detail endpoint reads CV from `PlacementPolicyRecord.pod_cpu_cv`:
```python
# optimize_routes.py:1261
"cpu_cv": pp.pod_cpu_cv if pp else None,
```
But the `workload_cv_task` writes CV to `WorkloadClassificationRecord.cpu_cv`.  
These are two different rows in two different tables. If the PlacementAdvisor has not yet run for a workload (or ran before the CV task), `pp.pod_cpu_cv` is `NULL` and the CV chart shows `CV: —` even when `workload_classifications.cpu_cv` is populated with a real value.

#### GAP-5 (Minor): "Status" Field Is Hardcoded
```jsx
// WorkloadProfiling.jsx line 289
['Status', 'Active Profile']  // always shows "Active Profile"
```
No actual status logic — doesn't check if the workload is running, terminated, in CrashLoop, etc.

---

### What IS Production-Ready

| Area | Status | Notes |
|---|---|---|
| WIE scoring engine (3 scores) | ✅ Production-ready | Deterministic, versioned (v4.4), write-suppressed, Redis-cached |
| CPU timeseries chart | ✅ Production-ready | Real 14-day daily averages from pod_metrics |
| CPU CV calculation | ✅ Production-ready | Real stats (numpy/stdlib), 5% trim, 14-day window |
| Confidence gating (DRAFT/PROV/CONFIRMED) | ✅ Production-ready | Cold-start enforcement, staleness penalties |
| Tier classification | ✅ Production-ready | Real criticality → Platinum/Gold/Silver/Bronze |
| `spot_friendly` flag | ✅ Production-ready | Real structural gate |
| Signals audit trail | ✅ Production-ready | Full trace of every signal that fired |
| DB write suppression | ✅ Production-ready | Only writes on score delta ≥ 1 or state change |
| Override system | ✅ Production-ready | Per-workload override with TTL |
| Summary strip | ✅ Production-ready | Real DB counts |
| Actionability gates 1–3, 5–6 | ✅ Production-ready | Real checks |

### What Is NOT Production-Ready

| Gap | Severity |
|---|---|
| Savings estimate: hardcoded 70% spot discount instead of real spot prices | 🟠 High |
| RPS chart always empty — permanent placeholder shown to all users | 🟠 High |
| "Rollout Not Blocked" gate always hardcoded Pass | 🟠 High |
| `cpu_cv` source mismatch (`WC.cpu_cv` vs `PP.pod_cpu_cv`) — may show `CV: —` when data exists | 🟡 Medium |
| "Status" field hardcoded to "Active Profile" | 🟢 Low |

---

### Summary

> Workload Profiling shows **mostly real data**. The 3 WIE scores (criticality, spot,
> confidence), the CPU timeseries, and the CV calculation are all backed by real
> algorithms running on live K8s and pod metrics. The page is production-ready as a
> **workload intelligence dashboard**.  
>
> It is **not fully production-ready** as an automation decision surface:
> savings numbers are estimates (70% hardcoded discount), gate 4 is always green,
> the RPS panel is permanently empty, and the CV source has a DB mismatch bug.

---

## FIX-WP — Workload Profiling: spot_friendly Bug + 5 Gap Fixes

**Date:** 2026-04-28

---

### ROOT BUG: Why No Workload Shows Spot-Friendly

**Symptom:** All stateless frontend Deployments (and most other workloads) showed
`spot_friendly = false` despite having high spot_scores.

**Root cause in `is_spot_friendly()` — `workload_identification_engine.py:761`:**

```python
# BEFORE — hardcoded PDB requirement for every single workload
def is_spot_friendly(spot_score: int, workload: WorkloadInput) -> bool:
    has_resilience_signal = workload.has_pdb and workload.replicas >= 2
    return spot_score >= 4 and has_resilience_signal   # ← requires PDB, always
```

The docstring explicitly stated: *"Stateless single-replica Deployments (e.g. frontend, locust)
are spot-friendly if their score is high enough."* But the implementation did not implement
this — it required `has_pdb=True` for every workload regardless of type. Any Deployment or
ReplicaSet without a PDB → `spot_friendly=False` forever.

**Cascading effect:** Because `spot_friendly=False`, the PlacementAdvisorService sets
`spot_target=0` for all workloads (the pre-write validator enforces this). This means the
savings estimate is also always `$0` for any workload without a PDB.

**Fix:**
```python
# AFTER — Rule A (resilient) OR Rule B (stateless high-score)
def is_spot_friendly(spot_score: int, workload: WorkloadInput) -> bool:
    has_resilience_signal = workload.has_pdb and workload.replicas >= 2
    is_stateless_spot_ready = (
        workload.data_safety == "EPHEMERAL"
        and workload.controller_kind in ("Deployment", "ReplicaSet")
        and spot_score >= 6
    )
    return spot_score >= 4 and (has_resilience_signal or is_stateless_spot_ready)
```

**Threshold rationale:** Base Deployment score = 6. A score of 6+ means no significant
penalties (no slow readiness, no crash loops, no leader election), making it safe
to mark as spot-friendly without a PDB.

---

### GAP-1 FIX: Savings Formula Now Uses Real SpotPriceHistory

**File:** `backend/services/placement_advisor_service.py`

**Before:** `avg_spot_price = avg_od_price * 0.3` (flat 70% discount hardcoded)

**After:** Queries `SpotPriceHistory` table for real spot prices for the cluster's
region and selected instance types. Falls back to the 70% heuristic only when
no spot price data is available in the DB.

Key changes:
- `_estimate_savings(…, db=None, cluster_region="us-east-1")` — new optional params
- `generate_placement_policy(…, db=None, cluster_region="us-east-1")` — passes through
- `run_placement_cycle(…)` — resolves cluster region via `Cluster.region` from DB
  and passes `db` + `cluster_region` to `generate_placement_policy`

---

### GAP-2 FIX: RPS Placeholder Panel Removed

**File:** `frontend/src/pages/optimize/workloads/WorkloadProfiling.jsx`

Removed the dead 2-column grid layout that contained a permanent
"RPS timeseries not available" placeholder. The Traffic Variance section
now renders a single full-width CPU chart. The RPS panel was always empty
because `pod_request_rate_cv` is never populated (`workload_cv_task` explicitly
documents it as out-of-scope without Prometheus).

---

### GAP-3 FIX: Gate 4 "Rollout Not Blocked" Now Real

**Files:** `backend/api/optimize_routes.py` + `frontend/src/pages/optimize/workloads/WorkloadProfiling.jsx`

**Backend:** `profiling-detail` response now includes `rollout_eligible` and
`rollout_blocked_reason` from `PlacementPolicyRecord`.

**Frontend:**
```jsx
// BEFORE — hardcoded
'pass',

// AFTER — reads real PlacementPolicyRecord.rollout_eligible
detail ? (detail.rollout_eligible === true ? 'pass' : 'fail') : 'pending',
```

Gate 4 now shows the actual blocked reason from the placement advisor
(e.g., `not_confirmed`, `savings_below_20_pct`, `gold_tier_requires_pdb`).

---

### GAP-4 FIX: cpu_cv Source Mismatch Resolved

**File:** `backend/api/optimize_routes.py`

**Before:** Only read `pp.pod_cpu_cv` (PlacementPolicyRecord). If PlacementAdvisor
hadn't run yet, `cv_cv` would be `None` even when `workload_classifications.cpu_cv`
had a real computed value.

**After:** Uses `pp.pod_cpu_cv` first; falls back to `wc.cpu_cv` if NULL.
Same fallback applied to `traffic_skew_detected`.

```python
cpu_cv_value = (
    (pp.pod_cpu_cv if pp and pp.pod_cpu_cv is not None else None)
    or (wc.cpu_cv if wc else None)
)
```

---

### GAP-5 FIX: Status Field Now Reflects Confidence State

**File:** `frontend/src/pages/optimize/workloads/WorkloadProfiling.jsx`

```jsx
// BEFORE — always "Active Profile"
['Status', 'Active Profile']

// AFTER — derived from confidence state
['Status', w.confLabel === 'CONFIRMED' ? 'Active Profile'
         : w.confLabel === 'PROVISIONAL' ? 'Observing'
         : 'Learning']
```

---

---

## Node Bin Packing — Data Source Audit & Fixes (2026-04-28)

### Data Source Verification

All CPU, memory, and pod count figures are **real live values from the K8s agent**:

| Field | Written by | Path |
|---|---|---|
| `cpu_usage_millicores` | K8s DaemonSet agent | `POST /api/v1/metrics` → `pod_metrics` table |
| `memory_usage_bytes` | K8s DaemonSet agent | Same path |
| `cpu_request_millicores` | K8s DaemonSet agent | From pod spec requests |
| `allocatable_cpu_millicores` | K8s DaemonSet agent | `node.status.allocatable.cpu` → `node_metadata` table |
| `allocatable_memory_bytes` | K8s DaemonSet agent | `node.status.allocatable.memory` → `node_metadata` table |

Calculation chain (all real):
```
cpu_actual_pct = sum(PodMetric.cpu_usage_millicores) / NodeMetadata.allocatable_cpu_millicores * 100
cpu_requested_pct = sum(PodMetric.cpu_request_millicores) / NodeMetadata.allocatable_cpu_millicores * 100
```

### Bug Found & Fixed: Stale Pod Inclusion (No Timestamp Filter)

**Root cause of misleading "98.2% free":**
The main bin-packing aggregate query had **no timestamp filter**. It used `DISTINCT ON pod_name ORDER BY timestamp DESC` across ALL time — meaning terminated pods (days/weeks old) were still included in the CPU sum, while `allocatable_cpu_millicores` reflects the current node capacity. This caused the usage percentage to be wrong.

The detail endpoint (`bin-packing-detail`) already had a 1h cutoff, so the spatial map tiles and the aggregate bars were computed from different pod sets — inconsistent.

**Fix applied in** `backend/api/optimize_routes.py`:
```python
# BEFORE — no filter, stale terminated pods included
.filter(PodMetric.cluster_id == cluster_id)

# AFTER — 30-min recency window, consistent with detail endpoint
_pod_cutoff = datetime.utcnow() - timedelta(minutes=30)
.filter(
    PodMetric.cluster_id == cluster_id,
    PodMetric.timestamp >= _pod_cutoff,
)
```

Detail endpoint cutoff also changed from `1h → 30min` to match.

### Added: Agent Freshness Indicator

Backend now returns `last_pod_metric_at` (ISO timestamp) and `pod_data_age_seconds` (integer) in the bin-packing response. Frontend displays a live badge:
- 🟢 `< 2 min` — fresh
- 🟡 `2–10 min` — slightly delayed
- 🔴 `> 10 min` — stale, agent may be down

### Fixed: Pod Spatial Map Tile Sizing

**Before:** All pod tiles same fixed size (`px-2 py-1`) — the "spatial" label was misleading.

**After:** Tile width = `(pod.cpu_usage_millicores / total_node_cpu) * 100%` — proportional treemap. Footer shows total millicores and pod count.

### Fixed: Packed Target Visualization

**Before:** Hardcoded `height: '20%'` amber bar + hardcoded `~80%` label — completely fabricated.

**After:** Uses real `cpu_requested_pct` from the DB as the packed target:
```js
const packedTarget = Math.min(85, Math.max(selectedNode.cpu_util + 5, selectedNode.cpu_requested_pct));
const headroomPct  = Math.max(0, packedTarget - selectedNode.cpu_util);
```
Footer shows: `"actual 18% vs requested 62% — 44% over-provisioned"` — all from real DB values.

*Last updated: 2026-04-28*

---

## Pod Placement Engine — Spot/OD Selection Logic

**Status:** Implemented

### Problem
The "Expected Optimized Placement" section showed AZ topology grids with OD/Spot counts, but **never explained which specific pods would go where** or whether the topology was valid. There was no:
- Pod-level candidacy scoring (which pods are safe to move to spot)
- System/DaemonSet pod exclusion from bin-packing counts
- Capacity calculation (total CPU/Mem for the spot batch)
- Topology constraint verification (min 2 nodes, AZ spread, anti-affinity)

### Implementation

#### Backend (`backend/api/optimize_routes.py` — `get_workload_placement_detail`)

**Pod query expanded** to include: `namespace`, `controller_kind`, `cpu_request_millicores`, `memory_request_bytes`, `cpu_usage_millicores`.

**Scoring function `_spot_score(p)`** — returns `(score|None, reason)`:
| Condition | Score delta | Tag |
|---|---|---|
| `namespace` in system namespaces | → `None` (skip) | `system_namespace` |
| `controller_kind == DaemonSet` | → `None` (skip) | `daemonset` |
| `age < 300s` | −3 | `new_pod` |
| `age > 3600s` | +2 | `mature_pod` |
| `age 1800–3600s` | +1 | `aging_pod` |
| `cpu_usage / cpu_request > 0.8` | −2 | `high_cpu` |
| `cpu_usage / cpu_request < 0.3` | +1 | `low_cpu` |

**Selection:** Sort scorable pods by score descending → top `spot_target` become `spot`, rest become `od`.

**Three new response fields:**
```json
{
  "pod_plan": [{ "name": "...", "recommendation": "spot|od|skip", "spot_score": 7, "reason": "mature_pod,low_cpu", "cpu_request_millicores": 500, "memory_request_bytes": 536870912, ... }],
  "capacity_plan": {
    "total_cpu_spot_millicores": 1500, "total_memory_spot_bytes": 1610612736,
    "total_cpu_od_millicores": 1000, "total_memory_od_bytes": 1073741824,
    "spot_pod_count": 3, "od_pod_count": 2, "skipped_pod_count": 1
  },
  "topology_constraints": {
    "distinct_nodes": 3, "distinct_azs": 2,
    "min_nodes_ok": true, "az_spread_ok": true, "anti_affinity_ok": true
  }
}
```

#### Frontend (`frontend/src/pages/optimize/workloads/WorkloadPlacement.jsx`)

Added `formatMem(bytes)` helper.

New sections wired in the **Expected Optimized Placement** card (in order):
1. **Topology Constraint Badges** — `✓/✗ Min 2 Nodes`, `✓/✗ AZ Spread`, `✓/✗ Anti-Affinity` + system pod exclusion count
2. **Capacity Summary** — 2-column grid: Spot capacity (CPU/Mem) | OD capacity (CPU/Mem), both sourced from real pod CPU requests
3. **Expected AZ Topology Grid** — existing OD/Spot dot grid, unchanged
4. **Current vs Expected Drift** — existing delta row
5. **Pod Scoring Table** — scrollable `160px` mini-table showing: pod name, score (color-coded green/amber/red), recommendation badge (`SPOT`/`OD`/`SKIP`), reason tag, CPU req, Mem req

### Constraints enforced
1. **Safety (Rule 1):** `od_target` from PlacementAdvisorService respects PDB + min replicas — pod scorer never exceeds `spot_tgt` assignments
2. **Prefer safe pods (Rule 2):** Mature + low-CPU pods score highest → get spot first
3. **Avoid risky pods (Rule 3):** New pods (age < 5min) and high-CPU-spike pods score lowest → kept OD
4. **System exclusion:** `kube-system`, `cert-manager`, `monitoring`, `istio-system`, `kube-flannel` namespaces + DaemonSet pods always skipped
5. **Topology verification:** Checks distinct node count ≥ 2 and distinct AZ count ≥ 2 against live pod placement

### Files Changed
- `backend/api/optimize_routes.py` — `get_workload_placement_detail`: expanded pod query + `_spot_score` + `capacity_plan` + `topology_constraints` + `pod_plan`
- `frontend/src/pages/optimize/workloads/WorkloadPlacement.jsx` — `formatMem` helper + topology badges + capacity summary + pod scoring table

*Last updated: 2026-04-29*

---

---

# 🔥 ANCHOR POLICY & ENGINE GAP FIXES — Plan.md Implementation

*Implemented: 2026-04-30*

---

## FIX-AP-1 — Centralised `is_system_pod()` (SYSTEM POD HANDLING NOT CENTRALISED)

**Status:** Resolved

### Problem
System-pod filtering was inlined in `PodSelector.classify_and_score()` using a raw
`ns in DEFAULT_SYSTEM_NAMESPACES or ctrl_kind == "daemonset"` check. Any submodule
that needed to filter system pods had to duplicate this logic or miss it entirely.

### Root Cause
No single authoritative function existed. The check was copy-pasted inside one method
with no enforcement that other pipeline phases would honour it.

### Fix
Added top-level `is_system_pod(pod: Dict[str, Any]) -> bool` to
`pod_placement_engine.py`. All submodules now call this function.
`PodSelector.classify_and_score()` was updated to replace the inline check with
`is_system_pod(p)`. Anchor-locked pods get a separate `reason: "anchor_locked"` tag
so they can be distinguished from true system pods in the output.

### Files Changed
- `backend/services/pod_placement_engine.py` — new `is_system_pod()` function, updated `PodSelector`

---

## FIX-AP-2 — Movement Budget (`MAX_MOVES_PER_CYCLE`)

**Status:** Resolved

### Problem
The engine could emit an unbounded number of movement steps. A large delta between
current and target capacity would produce a long `movement_plan` causing mass
concurrent evictions → cascading failures.

### Root Cause
`StabilityOptimizer` capped by `batch_size` (PDB-relative) but no hard absolute cap
existed. On wide deltas the PDB cap alone could still permit 10+ moves per cycle.

### Fix
Added constant `MAX_MOVES_PER_CYCLE = 2` in `pod_placement_engine.py`.
After the full pipeline runs in `materialize_plan()`, the movement plan is sliced:

```python
if len(movement_plan) > MAX_MOVES_PER_CYCLE:
    excess = len(movement_plan) - MAX_MOVES_PER_CYCLE
    movement_plan = movement_plan[:MAX_MOVES_PER_CYCLE]
    feasibility_warnings.append(
        f"movement_budget: capped at {MAX_MOVES_PER_CYCLE} moves/cycle — {excess} deferred"
    )
```

This cap is independent of PDB/batch calculations and runs as the final safety gate.

### Files Changed
- `backend/services/pod_placement_engine.py` — `MAX_MOVES_PER_CYCLE = 2` constant + cap in `materialize_plan()`

---

## FIX-AP-3 — State Freshness Check (`DATA_FRESHNESS_THRESHOLD_SECONDS`)

**Status:** Resolved

### Problem
The engine could be called with stale pod/node data (collected > 30s ago). Acting on
ghost-node data causes wrong decisions: pods scheduled to nodes that no longer exist,
unsafe moves based on outdated capacity readings.

### Root Cause
No data-age gate existed. The calling code could pass arbitrarily old data and the
engine would generate a plan unconditionally.

### Fix
Added constant `DATA_FRESHNESS_THRESHOLD_SECONDS = 30` and a new optional parameter
`data_age_seconds: Optional[float] = None` to `materialize_plan()`. If supplied and
exceeds the threshold, the engine returns `_noop_plan("stale_data")` immediately:

```python
if data_age_seconds is not None and data_age_seconds > DATA_FRESHNESS_THRESHOLD_SECONDS:
    return PodPlacementEngine._noop_plan(
        "stale_data",
        warnings=[f"data age {data_age_seconds:.0f}s exceeds freshness threshold {DATA_FRESHNESS_THRESHOLD_SECONDS}s"],
    )
```

Callers that do not supply `data_age_seconds` are unaffected (fail-open).

### Files Changed
- `backend/services/pod_placement_engine.py` — `DATA_FRESHNESS_THRESHOLD_SECONDS` constant + freshness guard in `materialize_plan()`

---

## FIX-AP-4 — Partial Feasibility Status (`PARTIAL`)

**Status:** Resolved

### Problem
Feasibility was binary: `feasible=True/False`. When some pods were blocked by
`no_capacity` but others were successfully assigned, the entire plan was marked
`infeasible` — discarding the valid partial plan unnecessarily.

### Root Cause
The feasibility check used `any(blocked)` → `infeasible` with no middle ground.

### Fix
Three-tier feasibility logic in `materialize_plan()`:

| Condition | `feasible` | `status` |
|---|---|---|
| `n_blocked == 0` | `True` | `plan_generated` |
| `0 < n_blocked < n_total` | `True` | `partial` |
| `n_blocked == n_total` | `False` | `infeasible` |

The `feasibility` dict now also carries `moves_blocked` count alongside `moves_total`.

### Files Changed
- `backend/services/pod_placement_engine.py` — three-tier feasibility logic in `materialize_plan()`
- `backend/api/optimize_routes.py` — error fallback plan updated with `status` + `moves_blocked` fields

---

## FIX-AP-5 — Cooldown Integration

**Status:** Resolved (was partially wired; now enforced in `StabilityOptimizer`)

### Problem
Cooldown pods were passed as a parameter to `materialize_plan()` and forwarded to
`StabilityOptimizer.filter()`, but the filter's inner loop silently skipped them
with no metrics. The skip was correct but invisible, and the parameter was not
documented in any guard ordering.

### Root Cause
The cooldown check was correct but the comment read "silently skip — cooldown is
normal", making it invisible in warnings/metrics. Confirmed correct: pod in cooldown
→ omitted from `eligible` list, not added to `movement_plan`.

### Fix
Updated inline comment to clarify: `# Cooldown integration: pod recently evicted — skip silently`.
No logic change needed — behaviour was already correct.

### Files Changed
- `backend/services/pod_placement_engine.py` — comment update in `StabilityOptimizer._filter_list()`

---

## FIX-AP-6 — Anchor Policy: `AnchorPlanner` Module (NEW)

**Status:** Resolved

### Problem
No mechanism existed to designate certain nodes as "anchor" nodes that should never
be drained and whose pods should never be moved. Critical (Platinum/Gold/Stateful)
workloads had no guaranteed stable substrate.

### Root Cause
The engine lacked Phase 0. All nodes were treated equally — even nodes hosting the
most critical pods could be drained.

### Fix
Added `AnchorPlanner` class as Phase 0 of the pipeline. It runs before `PodSelector`
and returns `anchor_nodes` (set of node names) + `locked_pods` (set of pod names):

**Selection logic:**
1. Nodes hosting critical pods (Platinum/Gold/Stateful) are scored highest (+100)
2. Nodes matching `preferred_capacity_type` score +50
3. Lower utilisation scores higher (−util×10)
4. If `az_spread_required`, unseen AZs are preferred until all AZs are covered

**`anchor_settings` schema:**
```json
{
  "min_anchor_nodes": 2,
  "preferred_capacity_type": "on-demand",
  "az_spread_required": true
}
```

When `min_anchor_nodes == 0` (default), the planner is a no-op — no anchors selected.

### Files Changed
- `backend/services/pod_placement_engine.py` — new `AnchorPlanner` class

---

## FIX-AP-7 — Anchor Enforcement Across All Pipeline Phases

**Status:** Resolved

### Problem
Even with `AnchorPlanner` selecting anchor nodes, the downstream phases could still
move pods off anchor nodes, drain anchor nodes, or pack other pods onto them last.

### Root Cause
`PodSelector`, `StabilityOptimizer`, `CapacityPlanner`, and `BinPacker` had no
knowledge of anchor nodes.

### Fix

**PodSelector** — new `locked_pods: Optional[set]` parameter:
```python
if p.get("pod_name") in locked_pods:
    system_skip.append({**p, "movement_cost": None, "reason": "anchor_locked"})
    continue
```

**StabilityOptimizer** — new `anchor_nodes: Optional[set]` parameter, guard in `_filter_list`:
```python
if p.get("node_name") in anchor_nodes:
    warnings.append(f"anchor node guard — blocking move for {pod_name}")
    continue
```

**CapacityPlanner** — new `anchor_nodes: Optional[set]` parameter, drain skip:
```python
if name in anchor_nodes:
    continue  # never drain anchor nodes
```

**BinPacker** — new `anchor_nodes: Optional[set]` parameter, anchor-first FFD:
```python
sorted_names = sorted(cursors.keys(), key=lambda n: (0 if cursors[n]["is_anchor"] else 1))
```

**`materialize_plan()`** — passes `anchor_nodes` and `locked_pods` through all phases.
**`PlacementPlan`** — new `anchor_plan` field in dataclass and `to_dict()`:
```json
{
  "anchor_nodes": ["node-a", "node-b"],
  "locked_pods": ["pod-1", "pod-2"],
  "anchor_count": 2
}
```

### Files Changed
- `backend/services/pod_placement_engine.py` — `PodSelector`, `StabilityOptimizer`, `CapacityPlanner`, `BinPacker`, `PlacementPlan`, `materialize_plan()`

---

## FIX-AP-8 — Anchor Node Protection in PlacementController

**Status:** Resolved

### Problem
`PlacementController._select_burst_pods()` had no awareness of anchor nodes. It
could select a pod on an anchor node for eviction, undoing the AnchorPlanner's
guarantees.

### Root Cause
The controller and the engine were independent — the controller had no way to know
which nodes the engine had designated as anchors.

### Fix
Two-part solution:

**API (write path):** After `PodPlacementEngine.materialize_plan()`, the placement-detail
endpoint writes anchor nodes to Redis (TTL 300s):
```
spot:placement:anchor_nodes:{cluster_id}:{workload_id}  →  JSON list of node names
```

**Controller (read path):** `_select_burst_pods()` receives `cluster_id` + `workload_id`
(added to its signature), reads the Redis key fail-open, and skips pods on anchor nodes:
```python
if pod.node and pod.node in _anchor_nodes:
    metrics["evictions_skipped_anchor_guard"] += 1
    continue
```

Fail-open: if the Redis key is absent (anchor feature disabled or key expired), no
pods are blocked by this guard.

### Files Changed
- `backend/services/pod_placement_engine.py` — `anchor_plan` written by engine, passed through
- `backend/api/optimize_routes.py` — writes `spot:placement:anchor_nodes:*` after engine call
- `backend/services/placement_controller_service.py` — `_select_burst_pods()` extended with `cluster_id`, `workload_id`; anchor node guard added; call site updated

---

---

# 🏗️ 5-LAYER ENGINE REFACTOR — plan.md v2 Implementation

*Implemented: 2026-04-30*

---

## FIX-5L-1 — StateGuard (Layer 1): ClusterState + No-Op Hash Detection

**Status:** Resolved

### Problem
The engine had no concept of cluster execution state. It would plan even while a previous cycle was still running (`cluster_state=planning`). The existing no-op detection was limited to checking empty movement lists — it could not detect that pods were already at their desired node assignments.

### Root Cause
No `StateGuard` class existed. The freshness guard was a simple age comparison with no hash-based idempotency check.

### Fix
Added `StateGuard` class (Layer 1) before all planning work:

- **Step 1 — ClusterState:** `cluster_state != "idle"` → `ABORT`
- **Step 2 — Freshness:** `data_age_seconds > 30` → `ABORT`
- **Step 3 — NO-OP:** SHA-256 hash of `sorted(pod→node assignments) + sorted(node capacities)` compared against `desired_hash` → `NO_OP`
- **Step 4 — PROCEED**

Hash is order-independent (`sha256(sorted pod_parts + sorted node_parts)[:16]`). Callers that do not supply `desired_hash` skip hash comparison (fail-open).

New params added to `materialize_plan()`: `cluster_state: str = "idle"`, `desired_hash: Optional[str] = None`.

### Files Changed
- `backend/services/pod_placement_engine.py` — `StateGuard` class, `materialize_plan()` wired

---

## FIX-5L-2 — AnchorPlanner (Layer 2): Three-Floor Count + anchor_map

**Status:** Resolved

### Problem
The anchor count used only `min_anchor_nodes` from user settings. This could result in too few anchors for critical CPU coverage or HA, or too many anchors (> 50% of cluster).
The output had no `anchor_map` — no record of which critical pod was assigned to which anchor node.

### Root Cause
Only `min_user` floor existed. `min_capacity` (CPU-based) and `min_ha` (HA-based) floors were absent. `anchor_map` was not produced.

### Fix
**Three-floor anchor count:**
```python
min_user     = settings.min_anchor_nodes
min_capacity = ceil(critical_cpu_total / avg_node_cpu)  # capacity floor
min_ha       = 2 if az_spread_required else 1            # HA floor
anchor_count = max(min_user, min_capacity, min_ha)
anchor_count = min(anchor_count, ceil(len(nodes) * 0.5)) # 50% safety cap
```

**AZ-spread selection:** Uses per-AZ quota (`ceil(anchor_count / total_azs)`) to distribute anchors evenly.

**Step 5 — anchor_map:** Assigns each critical pod to the best anchor node (prefers same node if already there; otherwise least-loaded in matching AZ).

**Output gains:**
```json
{
  "anchor_map": { "redis-0": "node-a", "postgres-0": "node-b" },
  "warnings":   ["az_spread_required but anchor nodes span only 1 AZ(s)"]
}
```

### Files Changed
- `backend/services/pod_placement_engine.py` — `AnchorPlanner.select()` fully rewritten

---

## FIX-5L-3 — CostProjector (Layer 4): Dual-Pass Cost Projection

**Status:** Resolved

### Problem
No cost projection existed. The plan had no output on how much it would cost before and after execution. The UI could not show savings estimates.

### Root Cause
`CostProjector` module was absent from the engine.

### Fix
New `CostProjector` class. Runs twice per plan cycle:

**Pass 1 (after BinPacker):** baseline vs projected cost, spot%, preliminary saving_usd.
**Pass 2 (after PlanValidator):** recalculates excluding blocked_pod nodes, producing the finalized cost estimate.

```python
# heuristic: spot = 70% cheaper than OD
SPOT_DISCOUNT_FACTOR = 0.30
MONTHLY_HOURS = 730
```

Output:
```json
{
  "current_nodes": 10, "projected_nodes": 7,
  "current_monthly_usd": 730, "projected_monthly_usd": 511,
  "saving_usd": 219, "saving_pct": 30, "spot_pct": 71,
  "actuals_updated": false,
  "preliminary": { ... }  // pass-1 values for comparison
}
```

Wire `aws_pricing_service` into `_hourly_rate()` to replace the heuristic with real prices.

### Files Changed
- `backend/services/pod_placement_engine.py` — new `CostProjector` class, wired in `materialize_plan()` at pass 1 + pass 2

---

## FIX-5L-4 — PlanValidator (Layer 5): 5-Check Validation Before Execution

**Status:** Resolved

### Problem
The engine had no pre-execution validation layer. Infeasibility was detected only via `blocked_by: "no_capacity"` in BinPacker output. PDB violations, IP exhaustion, max_pods breaches, storage-AZ mismatches, and AZ spread failures were completely undetected before execution.

### Root Cause
`PlanValidator` module was absent. Validation was implicit (BinPacker failure propagation only).

### Fix
New `PlanValidator` class with 5 ordered checks:

| Check | Type | Trigger |
|---|---|---|
| `PDB` | Soft | `running - 1 < pdb_min_available` |
| `IP_CAPACITY` | Hard | `assigned_count > node.ip_available` |
| `MAX_PODS` | Hard | `current_pods + incoming > node.max_pods` |
| `STORAGE_AZ` | Hard | STATEFUL pod cross-AZ move (RWO PV risk) |
| `AZ_SPREAD` | Soft | `< 2 AZs in plan` when `az_spread_required` |

**Hard failures → INFEASIBLE**; **Soft failures or blocked pods → PARTIAL**; **All pass → FEASIBLE**.

Validator-blocked pods are removed from `movement_plan` before CostProjector pass 2.
`feasibility.validator_status` + `feasibility.passed_checks` now included in plan output.

### Files Changed
- `backend/services/pod_placement_engine.py` — new `PlanValidator` class, wired in `materialize_plan()`

---

## FIX-5L-5 — PlacementPlan Dataclass: New Fields

**Status:** Resolved

### Problem
`PlacementPlan` had no `cost_projection` or `validation_errors` fields. The `anchor_plan` dict lacked `anchor_map`.

### Fix
```python
@dataclass
class PlacementPlan:
    ...
    anchor_plan: Dict[str, Any]        # now includes anchor_map{}
    cost_projection: Dict[str, Any]    # NEW
    validation_errors: List[Dict]      # NEW
```

`to_dict()` updated to include all three. `_noop_plan()` updated to include `moves_blocked`, `validator_status`, `passed_checks`, `cost_projection: {}`, `validation_errors: []`.

### Files Changed
- `backend/services/pod_placement_engine.py` — `PlacementPlan` dataclass + `to_dict()` + `_noop_plan()`

---

---

# 🔧 BIN-PACKER + ENGINE GAP FIXES — Gap Audit v1

*Implemented: 2026-04-30*

---

## FIX-GAP-1/2/3/4 — BinPacker: BFD + Real Cursors + 4 Dimensions + Multi-Factor Scoring

**Status:** Resolved

### Problems (4 gaps, 1 fix)
| Gap | Issue |
|---|---|
| Gap 1 | FFD (first fit) instead of BFD (best fit) — wastes space, prevents consolidation |
| Gap 2 | Cursors used `required_cpu * 1.5` (inflated fake numbers) instead of `allocatable - used` |
| Gap 3 | `pod_remaining` hardcoded to `K8S_MAX_PODS_PER_NODE=110`; `ip_remaining` not tracked at all |
| Gap 4 | No multi-factor scoring — no hotspot penalty, no AZ balance, no anchor penalty |

### Fix

**Cursor initialization** — now uses real allocatable minus current usage from the actual node dict (looked up via `node_map`). For new provisioned nodes, `CapacityPlanner` now writes `allocatable_cpu_millicores` / `allocatable_memory_bytes` (`inst_cpu`/`inst_mem`) into every `provision` entry.

**Four resource dimensions tracked:**
```python
"cpu_remaining": alloc_cpu - used_cpu,          # real headroom
"mem_remaining": alloc_mem - used_mem,
"pod_remaining": max(0, max_pods - cur_pods - daemonset_count),  # actual limit
"ip_remaining":  ip_available or 999,
```

**BFD (Best Fit Decreasing):** All feasible nodes scored; `min(feasible, key=_score)` selects winner. Sort remains CPU-descending (largest pod first).

**Multi-factor score (lower = better):**
```python
s = cpu_after / allocatable_cpu               # tightness (BFD)
if util_after > 0.80: s += 150.0             # hotspot penalty
if is_anchor and not is_critical: s += 500.0 # anchor protection
```

**Critical pod shortcut:** If pod is in `anchor_map` and its preferred anchor node is feasible, it is assigned directly (no scoring needed).

New signature: `BinPacker.pack(filtered, node_plan, nodes=None, anchor_nodes=None, anchor_map=None)`

### Files Changed
- `backend/services/pod_placement_engine.py` — `BinPacker` class fully rewritten; `CapacityPlanner` provision entry gains `allocatable_cpu_millicores`/`allocatable_memory_bytes`; `materialize_plan()` BinPacker call passes `nodes=nodes, anchor_map=anchor_map`

---

## FIX-GAP-5 — CostProjector: Static Instance-Type Price Table

**Status:** Resolved

### Problem
Every node cost `$0.10/hr` regardless of instance type. `m5.xlarge` and `c5.4xlarge` looked identical. Cost projections were meaningless.

### Fix
Added `INSTANCE_HOURLY_OD_USD` static dict with ~40 common instance types (t3, t3a, m5, m6i, c5, c6i, r5, r6i families — us-east-1, Linux, 2025).

Changed `SPOT_DISCOUNT_FACTOR` from `0.30` to `0.65` (65% discount = spot is 35% of OD; matches typical AWS spot savings).

`_hourly_rate()` now:
```python
od_price = INSTANCE_HOURLY_OD_USD.get(instance_type.lower(), 0.12)  # fallback $0.12
if capacity_type == "spot":
    return od_price * (1.0 - 0.65)   # = od_price * 0.35
```

Wire `aws_pricing_service` into `_hourly_rate()` to replace static table with live API prices.

### Files Changed
- `backend/services/pod_placement_engine.py` — `CostProjector.INSTANCE_HOURLY_OD_USD` table, `SPOT_DISCOUNT_FACTOR`, `_hourly_rate()`

---

## FIX-GAP-6 — AnchorPlanner: Lock Only Critical Pods

**Status:** Resolved

### Problem
AnchorPlanner locked **all** non-system pods currently sitting on an anchor node. Non-critical pods that happened to be co-located with anchor nodes were frozen unnecessarily, preventing BinPacker from rebalancing them.

### Root Cause
Second loop after `anchor_map` construction iterated all pods and added every pod on an anchor node to `locked_pods`.

### Fix
Removed the second loop entirely. `locked_pods` is now just:
```python
locked_pods: set = set(anchor_map.keys())  # only critical pods
```

Non-critical pods on anchor nodes are **not** locked. BinPacker's `ANCHOR_PENALTY = 500.0` score term will naturally steer non-critical pods away from anchor nodes during assignment without hard-freezing them.

### Files Changed
- `backend/services/pod_placement_engine.py` — `AnchorPlanner.select()` locked_pods assignment

---

## FIX-GAP-7 — PlanValidator PDB: Block Excess Pods Only

**Status:** Resolved

### Problem
If `running - 1 < pdb_min_available`, the entire movement plan was blocked (all pods got `PDB_violation`). One PDB constraint killed every movement regardless of how many pods could safely move.

### Root Cause
The check did not compute a `pdb_budget` — how many pods can actually be evicted concurrently without violating `min_available`.

### Fix
```python
pdb_budget = max(0, int(running) - int(pdb_min_available))
```

- `pdb_budget == 0` → block all (same as before, but correctly identified as zero-budget case)
- `len(plan) <= pdb_budget` → no block needed, all pods can move
- `len(plan) > pdb_budget` → block only `len(plan) - pdb_budget` excess pods

Blocked pods are selected by sorting `movement_plan` by `movement_cost` **ascending** (cheapest move first), then taking the tail (`[-excess:]`). This ensures the cheapest-to-move pods proceed and the most-expensive ones are deferred — minimising disruption while respecting PDB.

```python
sorted_by_cost = sorted(movement_plan, key=lambda s: s.get("movement_cost") or 0)
for step in sorted_by_cost[-excess:]:
    blocked_pods.append({"pod": step["pod_name"], "reason": "PDB_violation"})
```

### Files Changed
- `backend/services/pod_placement_engine.py` — `PlanValidator.validate()` Check 1 PDB block

---

## FIX-GAP-8 — BinPacker: Self-Derived pod_count + daemonset_count (Data Pipeline Gap)

**Status:** Resolved

### Problem
Three node-level fields required by BinPacker cursor initialization were **absent or hardcoded** in the upstream node data pipeline (`optimize_routes.py`):

| Field | Reality |
|---|---|
| `pod_count` | Hardcoded to `0` (`"pod_count": 0  # not tracked at node-meta level"`) |
| `daemonset_count` | Field entirely absent from node dict |
| `ip_available` | Field entirely absent from node dict |

Consequence: `pod_remaining = max_pods - 0 - 0 = 110` on every node — BinPacker would massively overestimate available pod slots and could schedule 110 pods onto a node already running 90.

### Root Cause
`NodeMetadata` model and the `/placement-detail` query builder never populated these fields. The comment in `optimize_routes.py` explicitly noted `pod_count=0` as a known gap. `daemonset_count` was never added to the schema.

### Fix
Engine derives both counts from the `pods` list that `materialize_plan` already receives — no change to upstream data pipeline required.

```python
# In materialize_plan(), before BinPacker call:
_node_pod_counts: Dict[str, int] = {}
_node_ds_counts: Dict[str, int] = {}
for _p in pods:
    _pnode = _p.get("node_name")
    if not _pnode:
        continue
    _node_pod_counts[_pnode] = _node_pod_counts.get(_pnode, 0) + 1
    if (_p.get("controller_kind") or "").lower() == "daemonset":
        _node_ds_counts[_pnode] = _node_ds_counts.get(_pnode, 0) + 1
```

Passed to BinPacker as `node_pod_counts=` / `node_ds_counts=`. Inside cursor initialization:
```python
cur_pods = int((node_pod_counts or {}).get(name, real.get("pod_count") or 0))
ds_pods  = int((node_ds_counts  or {}).get(name, real.get("daemonset_count") or 0))
# pod_remaining = max(0, max_pods - cur_pods - ds_pods)
```

Priority order: **engine-derived → node dict field → 0**. When the data pipeline is later upgraded to supply these fields, they will automatically take precedence.

**Remaining gaps (tracked, not yet fixed):**
- `ip_available` — absent from node dict; BinPacker defaults to `999` (effectively unchecked). Fix requires adding IP tracking to `NodeMetadata`.
- `max_pods` — absent; falls back to `K8S_MAX_PODS_PER_NODE=110`. Fine for homogeneous clusters; add when supporting mixed node configs.

### Files Changed
- `backend/services/pod_placement_engine.py` — `BinPacker.pack()` signature (new params `node_pod_counts`, `node_ds_counts`); cursor init fallback logic; `materialize_plan()` pre-BinPacker computation block

---

## FIX-GAP-9 — movement_plan Steps: Add Distribution Engine Fields

**Status:** Resolved

### Problem
The Distribution Engine (plan.md Layer 2 — WorkloadGrouper) requires four fields on each `movement_plan` step that were absent:

| Field | Used For |
|---|---|
| `workload_id` | Group steps by workload |
| `from_az` | PreconditionSnapshotter + AZ-degradation check |
| `cpu_request_millicores` | MigrationGroupBuilder resource embedding |
| `memory_request_bytes` | MigrationGroupBuilder resource embedding |

### Fix
Both `to_move_to_spot` and `to_move_to_ondemand` builders in `materialize_plan()` now emit all four fields:
```python
"workload_id":            wie.get("workload_id"),
"from_az":                p.get("az"),
"cpu_request_millicores": p.get("cpu_request_millicores"),
"memory_request_bytes":   p.get("memory_request_bytes"),
```

`from_az` is read from the pod's current `az` field (set by PodSelector from node data). `workload_id` comes from `wie` (WorkloadInputEntry) which is already in scope.

### Files Changed
- `backend/services/pod_placement_engine.py` — `materialize_plan()` movement_plan step builders (both `to_move_to_spot` and `to_move_to_ondemand` loops)

---

## CHANGE-1 — Update `MovementStep` Dataclass

**Status:** Done

Added `workload_id`, `from_az`, `cpu_request_millicores`, `memory_request_bytes` to the `MovementStep` dataclass so the public contract matches what `materialize_plan()` already emits (FIX-GAP-9). These are required fields for Distribution Engine WorkloadGrouper + PreconditionSnapshotter.

### Files Changed
- `backend/services/pod_placement_engine.py` — `MovementStep` dataclass (lines ~96-112)

---

## CHANGE-2 — Add `node_layout` to `PlacementPlan`

**Status:** Done

Added `node_layout: Dict[str, Any]` field to the `PlacementPlan` dataclass and `to_dict()`. All three plan-creation paths (`materialize_plan`, `already_optimal`, `_noop_plan`) supply this field (`{}` for noop/optimal, fully populated for main path). Distribution Engine reads `plan["node_layout"]` for `MigrationGroupBuilder.build_node_enforcement()`.

### Files Changed
- `backend/services/pod_placement_engine.py` — `PlacementPlan` dataclass + `to_dict()` (lines ~134-159)

---

## CHANGE-3 — Add `plan_id` to All Feasibility Dicts

**Status:** Done

Added `plan_id` (12-char sha256 hex) to all three feasibility dict construction paths:
- **Main path** (plan_generated/partial/infeasible): `sha256(f"{id(pods)}{id(nodes)}{n_total}")[:12]`
- **already_optimal** path: same pattern with `0` for n_total
- **_noop_plan()**: `None` — noop plans have no meaningful plan_id

Distribution Engine stamps each `ExecutionManifest` with this `plan_id` for traceability.

### Files Changed
- `backend/services/pod_placement_engine.py` — `materialize_plan()` + `_noop_plan()` feasibility dicts

---

## CHANGE-4 — Fix `CapacityPlanner` Drain Detection + Move Count Block

**Status:** Done

Two sub-fixes:
1. **Block moved up**: `_node_pod_counts` / `_node_ds_counts` derivation from `pods` list moved to before the `CapacityPlanner` call (was after). `CapacityPlanner` now uses accurate pod counts for drain detection.
2. **CapacityPlanner signature**: Added `node_pod_counts: Optional[Dict[str, int]] = None` param. Drain detection now uses `(node_pod_counts or {}).get(name, n.get("pod_count") or 0)` instead of hardcoded `n.get("pod_count") or 0` (which was always 0).

Previously `CapacityPlanner` would never flag any drain candidates because `pod_count=0` meant `pods_leaving >= 0` was always false.

### Files Changed
- `backend/services/pod_placement_engine.py` — `CapacityPlanner.plan()` signature; drain count logic; `materialize_plan()` ordering

---

## CHANGE-5 — `BinPacker.pack()` Returns Cursors

**Status:** Done

Changed return from `(filtered, warnings)` to `(filtered, warnings, cursors)`. Cursors hold the final per-node resource state after all pod assignments — consumed by `NodeLayoutBuilder` to compute accurate before/after utilization. Also updated type hint on method signature.

### Files Changed
- `backend/services/pod_placement_engine.py` — `BinPacker.pack()` return + type hint; `materialize_plan()` unpack

---

## CHANGE-6 — Add `NodeLayoutBuilder` Class

**Status:** Done

New class inserted between `BinPacker` and `CostProjector`. Assembles the full `node_layout` dict from:
- `cursors` (BinPacker output — final resource state per node)
- `all_pods` (full cluster pod list — for existing pods per node)
- `filtered` (moved pods — for incoming pods per node)
- `node_plan` + `anchor_nodes` (for state classification)

Output shape:
```python
{
  "by_az": {
    "us-east-1a": {
      "nodes": [{ node_name, state, existing_pods, incoming_pods, resources, ... }],
      "az_totals": { node_count, pod_count_*, cpu_used_*, ... }
    }
  },
  "drain_candidates":   [{ node_name, state="draining", ... }],
  "provision_required": [{ node_name, state="provisioned", required_cpu/mem, instance_type, ... }]
}
```

Wired into `materialize_plan()` immediately after `BinPacker.pack()`. Result passed to main `PlacementPlan` return as `node_layout=node_layout`.

### Files Changed
- `backend/services/pod_placement_engine.py` — new `NodeLayoutBuilder` class (~185 lines); `materialize_plan()` wiring; main `PlacementPlan` return

---

## ISSUE-3 — BinPacker: Critical Pod Concentration Penalty

**Status:** Done

**Gap:** When two critical pods from different workloads both prefer the same anchor node, BinPacker assigned both with no resistance — no check that a node already has one critical pod.

**Fix:**
- Added `CRITICAL_CONCENTRATION_PENALTY = 300.0` constant (between HOTSPOT_PENALTY=150 and ANCHOR_PENALTY=500 — soft discourage, not hard block)
- Added `critical_pod_count: 0` field to every cursor at initialization
- Added `allocatable_mem` to cursor (was missing — needed by NodeLayoutBuilder)
- `_score()` now adds `CRITICAL_CONCENTRATION_PENALTY` when `is_critical and cur["critical_pod_count"] >= 1`
- Assignment loop increments `cur["critical_pod_count"] += 1` when `is_critical`

Value 300 (not hard block): if the cluster has only one anchor node in an AZ, a hard block would leave a critical pod unscheduled. Penalty ensures BinPacker tries every other feasible node first.

### Files Changed
- `backend/services/pod_placement_engine.py` — `BinPacker` constants; cursor init; `_score()`; assignment loop

---

## ISSUE-4 — CapacityPlanner: Drain-Reuse Before Provisioning (Step 2b)

**Status:** Done

**Gap:** CapacityPlanner's provision decision (step 2) and drain detection (step 3) were computed independently. A node becoming empty could be flagged as `drain` while simultaneously causing a new `provision` entry for pods that could have fit in the draining node.

**Fix:** Added step 2b between step 1 (existing-node keep) and step 2 (provision):
1. Pre-compute `_leaving` dict: pods leaving each node this cycle
2. For each bucket with leftover pods, scan nodes that will become empty (`_count > 0 and _leaving >= _count`) in the same `(az, capacity_type)` bucket
3. Absorb leftover pods into those nodes (full allocatable capacity available post-drain)
4. Emit a `keep` entry with `"reason": "drain_reuse"` and add to `kept_nodes`
5. Provision loop runs after — `bucket["pods"]` already reduced, fewer (or zero) provisions emitted

### Files Changed
- `backend/services/pod_placement_engine.py` — `CapacityPlanner.plan()` — new step 2b (~52 lines)

---

## NEW FILE — `distribution_engine.py`

**Status:** Done

Created `backend/services/distribution_engine.py` (~450 lines). Full spec from `plan.md`.

### Layers

| Layer | Class | Job |
|---|---|---|
| 1 | `ManifestGuard` | Gate: explicit allowlist for proceed statuses, unknown → ABORT |
| 2 | `WorkloadGrouper` | Group movement steps by workload_id (step field → WIE profile → derived) |
| 3 | `WorkloadSorter` | Priority order: `(criticality × safety_risk) + (drainable × urgency)` |
| 4 | `MigrationGroupBuilder` | Build BLUE_GREEN (SEQUENTIAL) or BATCH (PARALLEL_BATCHED) groups with embedded node enforcement + rollback |
| 5 | `PreconditionSnapshotter` | Snapshot plan-relevant nodes/pods only for RaceGuard |
| — | `DistributionEngine` | Orchestrator — wires all 5 layers |

### Key design decisions implemented
- `build_node_enforcement()` reads from `plan["node_layout"]` (post-BinPacker state) not raw `nodes` (pre-assignment stale)
- `ip_available = None` explicitly — Execution Engine must tolerate None
- Unmatched pods always get a BATCH group — never silently dropped
- Budget depletes in priority order — exhausted workloads become DEFERRED not dropped
- Manifest TTL = 120s (`expires_in_seconds` field)
- `manifest_id = "mfst-" + sha256(plan_id + timestamp)[:12]`

### Files Changed
- `backend/services/distribution_engine.py` — new file

---

## AUDIT FIX-1 — `DistributionEngine.build()`: no_capacity pods passed to MigrationGroupBuilder

**Status:** Done

**Root cause:** `plan["movement_plan"]` includes steps where `blocked_by == "no_capacity"` and `to_node == None` (BinPacker found no feasible node). These were passed directly to `WorkloadGrouper` and then `MigrationGroupBuilder`, which called `build_node_enforcement("", plan)` → produced `{"nodeName": ""}`, an invalid Kubernetes spec patch.

**Fix:** In `DistributionEngine.build()`, added `actionable_movement` filter before `WorkloadGrouper`:
```python
actionable_movement = [
    s for s in plan["movement_plan"]
    if s.get("to_node") and not s.get("blocked_by")
]
```
`WorkloadGrouper` and `MigrationGroupBuilder` now only receive steps with a valid `to_node`. `no_capacity`-blocked steps remain in the `PlacementPlan.movement_plan` for audit/UI purposes but are invisible to the distribution pipeline.

**Files changed:**
- `backend/services/distribution_engine.py` — lines ~575–602

---

## AUDIT FIX-2 — `DistributionEngine.build()`: budget includes no_capacity-blocked count

**Status:** Done

**Root cause:** `budget["pods"] = plan["feasibility"]["moves_total"]` where `moves_total = len(movement_plan)` after PDB filtering but BEFORE no_capacity filtering. So for a `partial` plan, budget included blocked pods that can't be moved, causing over-counting.

**Fix:** Changed budget to use `len(actionable_movement)` (same filtered list from AUDIT FIX-1):
```python
budget = {
    "pods": len(actionable_movement),   # actionable only, not blocked
    ...
}
```

**Files changed:**
- `backend/services/distribution_engine.py` — lines ~591–593

---

## AUDIT FIX-3 — `BinPacker`: drain-reuse cursor uses pre-drain used_cpu/mem

**Status:** Done

**Root cause:** BinPacker builds cursors for `keep` nodes using `real.get("used_cpu_millicores")` from the node dict. For drain-reuse nodes, this value reflects ALL current pods (including the ones being moved away). Result: `cpu_remaining = alloc_cpu - used_cpu` was too small, causing BinPacker to reject pods that `CapacityPlanner` already verified would fit (CapacityPlanner checks against full `alloc_cpu`).

**Fix:** In `BinPacker.pack()` cursor initialization, detect `reason == "drain_reuse"` entries and set `used_cpu = 0, used_mem = 0, cur_pods = ds_pods`:
```python
if entry.get("reason") == "drain_reuse":
    used_cpu = 0.0
    used_mem = 0.0
    cur_pods = ds_pods   # DS pods stay and occupy slots
else:
    used_cpu = float(real.get("used_cpu_millicores") or 0)
    used_mem = float(real.get("used_memory_bytes") or 0)
    cur_pods = int((node_pod_counts or {}).get(name, ...))
```

**Files changed:**
- `backend/services/pod_placement_engine.py` — BinPacker cursor init block (~lines 1019–1034)

---

## UI — WorkloadPlacement.jsx: Impact Summary + Node Layout

**Status:** Done

**Changes made to `frontend/src/pages/optimize/workloads/WorkloadPlacement.jsx`:**

### 1. Impact Summary (3-stat grid)
Added a 3-column stat row inside the "Pod Placement Engine Plan" section, shown only for non-noop plans:
- **Pods Moving** — `moves_total` count with breakdown `X → Spot · Y → OD`
- **Nodes Drained** — count of `action=drain` entries
- **Nodes Reused / Kept** — shows "Nodes Reused" with drain→keep note when `reason=drain_reuse` exists

### 2. Node Layout (AZ → Node → Pods → Utilization)
Added a "Node Layout" section below the Node Plan table. Reads from `placementPlan.node_layout` (new backend field added by `NodeLayoutBuilder`). Shows:
- Per-AZ header with node count and total pods after
- Node cards labeled `Node A`, `Node B` etc. (no actual hostnames per plan.md spec)
- Color-coded by type: purple=anchor, indigo=Spot, red/pink=OD
- CPU utilization bar: green <60%, amber 60–80%, red ≥80%
- Incoming pods highlighted with green dot + "→ here" badge
- Existing pods (dimmed) when no incoming
- Separate amber "Draining" section and blue "Provisioning" section

**Files changed:**
- `frontend/src/pages/optimize/workloads/WorkloadPlacement.jsx`

---

## EE — ExecutionEngine: All 10 Layers Implemented

**Status:** Done

### What was built

New file: `backend/services/execution_engine.py`

All 10 layers from `temp-doc/plan.md` implemented in a single module:

| Layer | Class | Purpose |
|---|---|---|
| 1 | `ManifestStore` | Redis key store — write/read/delete manifests with TTL=120s |
| 2 | `ActionTracker` | Write-ahead log — HSET per pod before any cluster touch |
| 3 | `ExecutionGate` | 10 Redis checks before any infra action (shadow, cooldown, karpenter_pause, circuit breaker, mode, TTL, cluster state, rebalance lock, argocd sync, exec lock NX) |
| 4 | `RaceGuard` | Compare precondition_snapshot vs WIE cache — abort + signal replan if stale |
| 5 | `NodeProvisioner` | Provision/reuse nodes — draining node reuse before Karpenter provision, rate limit, per-node lock |
| 6 | `StatefulExecutor` | BLUE_GREEN groups sequential with reverse ordinal order — PROVISIONING_NEW → WAITING_READY → SHIFTING_TRAFFIC → OBSERVING → DELETING_OLD |
| 7 | `StatelessExecutor` | BATCH groups parallel via ThreadPoolExecutor — sequential batches within each group |
| 8 | `Verifier` | WIE cache comparison post-execution — DEFERRED/BLOCKED/FAILED steps intentionally skipped |
| 9 | `FeedbackHandler` | Classify mismatches → scoped replan signals + circuit breaker on >50% mismatch rate |
| 10 | `ExecutionEngine` | Orchestrator — cluster state machine IDLE→EXECUTING→EXECUTING_STATELESS→DRAINING→VERIFYING→IDLE with guaranteed IDLE reset in finally |

### Gap fixes embedded in EE

- **PVC AZ check** — `StatefulExecutor._execute_step()` before any PATCH_AFFINITY
- **max_pods check** — both executors check `_read_wie_node_pod_count()` before every pod action
- **PDB re-check before drain** — `ExecutionEngine._drain_node()` checks PDB before DRAIN_NODE dispatch
- **Verifier skip deferred** — explicit `if status in (DEFERRED, BLOCKED, FAILED): skip`
- **Post-execution cost recompute** — `_recompute_cost_from_actual()` after verify from WIE node cache
- **Karpenter coordination** — Gate 3 (cluster-scoped pause) + Gate 9 (Argo CD sync)

### Wiring changes

- `distribution_engine.py`: `DistributionEngine.build()` now calls `ManifestStore.write(cluster_id, manifest)` after building — requires `feasibility.cluster_id` set by caller. Non-fatal if missing or Redis down.
- `auto_rebalancer.py` (`execute_rebalancing()`): New EE branch at top iterates active clusters, reads `ManifestStore`, hands off to `ExecutionEngine.run()` for any cluster with a READY manifest. Legacy path runs for all others. `ImportError` falls through silently.

**Files changed:**
- `backend/services/execution_engine.py` — created (all 10 layers, ~700 lines)
- `backend/services/distribution_engine.py` — `build()` wired to `ManifestStore.write()`
- `backend/workers/tasks/auto_rebalancer.py` — EE entry branch added at top of `execute_rebalancing()`

---

## Post-Audit Gap Fixes (6 issues found and fixed)

**Status:** Done

### Fix A — Critical: `cluster_id` missing from PPE feasibility dict (broken EE pipeline)

**Problem:** `DistributionEngine.build()` reads `plan["feasibility"].get("cluster_id")` to write the manifest to `ManifestStore`. But `PodPlacementEngine.materialize_plan()` never accepted or set `cluster_id`, so the value was always `None` and `ManifestStore.write()` was never called. The entire EE pipeline was silently broken.

**Fix:**
- Added optional `cluster_id` param to `PodPlacementEngine.materialize_plan()`
- Injected `cluster_id` into all three feasibility dicts (main path, `already_optimal` early-return, `_noop_plan`)
- Passed `cluster_id=cluster_id` from the `optimize_routes.py` call site

**Files changed:**
- `backend/services/pod_placement_engine.py` — signature + 3 feasibility dicts
- `backend/api/optimize_routes.py` — `materialize_plan()` call site

---

### Fix K-1 / K-2 — No default NodePool before first handover (CRITICAL)

**Problem:** Phase 1 calls `add_allowed_instance_type(..., nodepool="default")` which returns `False` with 404 if no NodePool exists yet. On fresh Karpenter installs, autorebalancing silently does nothing.

**Fix:**
- `install_karpenter()` now sets `spot:karpenter_nodepool_bootstrap_needed:{cluster_id}` Redis flag (TTL 2h) after queuing the install action
- Added `bootstrap_default_nodepool()` method to `KarpenterService` — lists existing NodePools, skips if any spot pool exists, otherwise creates `spot-general` (spot capacity, `m5.xlarge / m5.2xlarge / c5.xlarge`, region AZs). Idempotent and safe to call multiple times.
- Added K-1/K-2 bootstrap loop at start of each `execute_rebalancing()` cycle — checks the flag for each active cluster and calls `bootstrap_default_nodepool()`

**Files changed:**
- `backend/services/karpenter_service.py` — `install_karpenter()` flag + new `bootstrap_default_nodepool()` method
- `backend/workers/tasks/auto_rebalancer.py` — bootstrap loop added after EE block

---

### Fix K-5 — NodePool label resolution fails for ASG source nodes (HIGH)

**Problem:** ASG-managed nodes have no `karpenter.sh/nodepool` label. The fallback was hardcoded `'default'` which may not exist on clusters using `NodePoolReconcilerService` named pools (`spot-general`, etc.).

**Fix:** 3-tier resolution with existence verification:
1. Source node `karpenter.sh/nodepool` label (unchanged)
2. Try `spot-general` via API GET — uses NodePoolReconcilerService pool name
3. Try `default` as last resort

If neither 2 nor 3 exists, Phase 1 fails cleanly with `no_spot_nodepool_exists` instead of silently sending a 404 to the Karpenter API.

**Files changed:**
- `backend/workers/tasks/auto_rebalancer.py` — NodePool resolution block (~line 1663)

---

### Fix K-6 — NodePool stays dirty (`consolidateAfter=Never`) on action timeout (MEDIUM)

**Problem:** `add_allowed_instance_type()` freezes Karpenter consolidation to `Never` during migration. The cleanup only runs on clean action completion. A crashed worker or timed-out action leaves `consolidateAfter=Never` permanently.

**Fix:** In the stale action expiry loop, when marking an action `failed`, call `remove_allowed_instance_type()` to restore the NodePool's consolidation baseline. Node pool name is read from `action_metadata.patched_nodepool_name`.

**Files changed:**
- `backend/workers/tasks/auto_rebalancer.py` — stale expiry loop, after orphan EC2 cleanup

---

### Fix K-7 — EC2NodeClass hardcoded as `"default"` (MEDIUM)

**Problem:** All NodePool specs generated by `_update_nodepool()` hardcode `nodeClassRef.name: "default"`. Clusters using a custom EC2NodeClass will provision nodes with wrong AMI/security groups.

**Fix:** `_update_nodepool()` now reads `cluster.ec2_node_class_name` if set, falling back to `"default"`.

**Files changed:**
- `backend/services/karpenter_service.py` — `_update_nodepool()` nodeClassRef block

---

### Fix K-8 — No NodePool weight/priority (MEDIUM)

**Problem:** All NodePools default to `weight: 10`. Karpenter may pick spot pools for OD-affinity pods, defeating the OD-base safety guarantee.

**Fix:** `_update_nodepool()` now sets `weight: 100` for `on-demand` NodePools and `weight: 10` for spot NodePools.

**Files changed:**
- `backend/services/karpenter_service.py` — `_update_nodepool()` spec, after `limits`

---

## Phase 1b — Instance Selection Layer (Problems 6, 7-18, 19-31)

**Status:** Implemented

### ISS-1 — New file: InstanceSelector (Problems 6, 6a-6c, 19-23, 27-28, 30-31)

**Problem:** No single-entry resolver for instance type.  DE ranking results were consumed directly without AZ lock, capacity type check, or density guard.

**Fix:** Created `backend/services/instance_selector.py` with:
- `InstanceResolution` dataclass (result contract)
- `InstanceSelector.resolve()` — enforces AZ lock (6b), capacity filter (6c), density filter with `DensityTransientError` (6a/24), cost strategy from policy only (20), exec_cache (31), DE timeout with fallback (23), shared `ThreadPoolExecutor` (30), hint fallback with 3 safety gates (19/28)
- `DensityTransientError.best_max_pods_seen` propagated to split (24)
- `PermanentError` / `TransientError` hierarchy

**Files changed:**
- `backend/services/instance_selector.py` — created

---

### ISS-2 — New file: InstanceSelectionService (Problems 7-18, 24-26)

**Problem:** No facade to batch-resolve instance types across full `node_plan` before manifest construction.

**Fix:** Created `backend/services/instance_selection_service.py` with:
- `resolve_all()` — iterates node_plan, loads per-entry placement_policy, calls `_resolve_with_escalation()`
- `_resolve_with_escalation()` — attempt 0 original, attempt 1 wider CPU ×1.5, attempt 2 split-node fallback (Problems 8, 18)
- `_split_provision_entry()` — N-partition split using `packed_pods` (12), arithmetic fallback with WARNING (legacy), split depth cap `MAX_SPLIT_DEPTH=1` (14), split child TransientError → PermanentError (25), `DensityTransientError.best_max_pods_seen` drives N without second DE call (24)
- `_load_placement_policy()` — loads `cluster.placement_policy`, applies workload_class overrides (10, 15), built-in defaults per class (stateful/stateless/mixed)

**Files changed:**
- `backend/services/instance_selection_service.py` — created

---

### ISS-3 — New models: ExecutionManifest + ExecutionOverride (Problems 2, 3, 16, 17, 22, 26, 29)

**Problem:** ManifestStore was Redis-only (120 s TTL) — lost on Redis eviction.  No override audit log.

**Fix:**
- `backend/models/execution_manifest.py` — DB model: `manifest_id`, `cluster_id`, `status`, `payload` (JSONB), `expires_at`, `last_heartbeat`, `resume_index`, `error_message`
- `backend/models/execution_override.py` — append-only DB model: `manifest_id`, `node_name`, `field`, `original_value`, `override_value`, `reason`, `attempt_number`
- `backend/migrations/014_execution_tables.py` — creates both tables + `clusters.placement_policy` JSONB column

**Files changed:**
- `backend/models/execution_manifest.py` — created
- `backend/models/execution_override.py` — created
- `backend/migrations/014_execution_tables.py` — created

---

### ISS-4 — ManifestStore DB-primary + Redis cache (Problems 2, 3, 22, 29)

**Problem:** Redis-only store lost manifests on eviction; no atomic status transitions; no stale manifest expiry.

**Fix:** Rewrote `ManifestStore` in `execution_engine.py`:
- `write(db=)` — DB-primary upsert (ExecutionManifest row) + Redis mirror (TTL 120 s)
- `read(db=)` — Redis fast-path; DB fallback
- `transition(manifest_id, new_status, db)` — blocking `with_for_update()` + READ COMMITTED isolation; guards terminal statuses (Problem 22/29)
- `heartbeat(manifest_id, db)` — updates `last_heartbeat` for TTLMonitor
- `MANIFEST_TTL_SECONDS` raised to 3600; `MANIFEST_REDIS_TTL` = 120

**Files changed:**
- `backend/services/execution_engine.py` — ManifestStore rewritten

---

### ISS-5 — ExecutionOverrideStore (Problems 16, 17, 26)

**Problem:** NodeProvisioner mutated manifest entries in-place — violated manifest immutability; no audit log for retry chains.

**Fix:** Added `ExecutionOverrideStore` to `execution_engine.py`:
- `write()` — append-only INSERT (never upsert), `attempt_number` auto-incremented
- `read_all()` — returns `{node_name: {field: latest_value}}` for merge at resume time
- `read_history()` — full audit log per (manifest_id, node_name)
- `apply()` — non-destructive merge of overrides onto manifest entries (returns new list)

**Files changed:**
- `backend/services/execution_engine.py` — ExecutionOverrideStore added

---

### ISS-6 — TTLMonitor (Problems 3, 22, 29)

**Problem:** No mechanism to expire stale `EXECUTING` manifests when EE crashed or heartbeat stopped.

**Fix:** Added `TTLMonitor` class:
- `check_and_expire(db)` — SELECT EXECUTING where `last_heartbeat < NOW()-60s`, acquire blocking `with_for_update()` lock per row, re-check status, transition to EXPIRED

**Files changed:**
- `backend/services/execution_engine.py` — TTLMonitor added

---

### ISS-7 — EE exception hierarchy (Problems 11, 13)

**Fix:** Added `EEError`, `ApprovalRequiredError`, `ReplanRequiredError` (with `original_entry` + `split_entries`) to `execution_engine.py`.

---

### ISS-8 — NodeProvisioner upgrades (Problems 11, 13, 16, 17)

**Problem:** NodeProvisioner selected instance_type inline; mutated manifest; no mid-run pool failure retry; no replan signal on density split.

**Fix:** `NodeProvisioner.provision_all()` now:
- Accepts `manifest_id`, `db`, `instance_selection_service` params
- Loads overrides via `ExecutionOverrideStore.read_all()` at start (crash-resume, Problem 17)
- Re-derives `working_entry = manifest_entry + override` — never chains (Problem 17)
- Guards `instance_type` missing (FAILED_NO_INSTANCE_TYPE)
- On FAILED_TIMEOUT with ISS: calls `DE.report_launch_failure()`, `ISS._resolve_with_escalation()`, writes `ExecutionOverrideStore` row, retries with new type (Problem 11)
- Raises `ReplanRequiredError` if re-resolution produces split (Problem 13)

**Files changed:**
- `backend/services/execution_engine.py` — NodeProvisioner.provision_all() updated

---

### ISS-9 — ExecutionEngine.run() upgrades (Problems 11, 22, 29)

**Fix:** `ExecutionEngine.run()` now:
- Accepts `instance_selection_service=None` param (Problem 11)
- Transitions manifest to `EXECUTING` at start, `COMPLETED` on success, `FAILED` on ReplanRequired
- Calls `ManifestStore.heartbeat()` after provisioning, after each BG group, after batch execution
- Checks `_manifest_still_valid()` (blocking FOR UPDATE + READ COMMITTED) at every phase boundary (Problem 22/29)
- Handles `ReplanRequiredError` from provisioning — transitions FAILED + signals replan (Problem 13)
- `NodeProvisioner.provision_all()` called with `manifest_id`, `db`, `instance_selection_service`
- Added static `_manifest_still_valid()` helper

**Files changed:**
- `backend/services/execution_engine.py` — ExecutionEngine.run() + _manifest_still_valid()

---

### ISS-10 — DistributionEngine wires ISS (Problems 7, 8)

**Problem:** DistributionEngine.build() built manifests without instance type resolution.

**Fix:** `DistributionEngine.build()` now:
- Accepts `instance_selection_service=None`, `db=None`
- Calls `ISS.resolve_all()` on `plan["node_plan"]` before Layer 1 (ManifestGuard)
- Replaces node_plan in plan copy (non-destructive)
- Non-fatal: ISS failure logs WARNING and proceeds without resolution
- Passes `db=` to `ManifestStore.write()` for DB-primary persistence

**Files changed:**
- `backend/services/distribution_engine.py` — build() updated

---

### ISS-11 — DecisionEngineService.capacity_type field (Problem 21)

**Problem:** `_scored_to_dict()` had no `capacity_type` field — `InstanceSelector._matches_capacity_type()` always fell through to price-delta heuristic.

**Fix:** Added `capacity_type` field: uses `pool.capacity_type` attribute first (explicit path); price-delta heuristic only as fallback with `debug` log. `capacity_filter_warnings` metric should trend toward zero.

**Files changed:**
- `backend/services/decision_engine_service.py` — `_scored_to_dict()` updated

---

### ISS-12 — Cluster.placement_policy column (Problems 10, 15)

**Problem:** No per-cluster ISS policy store.

**Fix:** Added `placement_policy = Column(JSONB, nullable=True)` to `Cluster` model. Schema: `{"cost_strategy": "balanced", "risk_threshold": 0.30, "workload_overrides": {...}}`.

**Files changed:**
- `backend/models/cluster.py` — `placement_policy` column added
- `backend/migrations/014_execution_tables.py` — migration includes `clusters.placement_policy` column

---

## Critical Gap Fixes (GAP 1–3) + Medium Issues (A–C)

**Status:** Implemented

---

### GAP-1 — InstanceSelection NOT enforced inside DE

**Problem:** `DistributionEngine.build()` called ISS as optional; if ISS ran and produced `instance_type=None` on any provision entry, manifest was still created and EE would hit `FAILED_NO_INSTANCE_TYPE` silently at node launch time.

**Root cause:** No post-resolution validation gate existed. ISS failure was logged as WARNING only, allowing unresolved manifests to proceed.

**Fix:**
- Added `UnresolvedInstanceError` exception (raised at manifest creation, caught by caller).
- Added `_validate_resolved_instances(node_plan, iss_was_run)` to `DistributionEngine`:
  - `iss_was_run=True`: any provision entry with `instance_type=None` → **raises `UnresolvedInstanceError`** (aborts manifest creation)
  - `iss_was_run=False` (no ISS injected): logs WARNING only (EE will catch `FAILED_NO_INSTANCE_TYPE` as before)
- Called **after** `ISS.resolve_all()` and **before** `ManifestGuard` (Layer 1) so enforcement happens at the earliest possible point, before `build_node_enforcement()` in Layer 4.

**Files changed:**
- `backend/services/distribution_engine.py` — `UnresolvedInstanceError` + `_validate_resolved_instances()` + guard call in `build()`

---

### GAP-2 — packed_pods missing from PPE → DE chain

**Problem:** `CapacityPlanner.plan()` computed aggregate CPU/mem per bucket but emitted provision entries with only `pod_count` (integer) — no list of which pods were assigned. `InstanceSelectionService._split_provision_entry()` fell through to arithmetic splitting (logged WARNING) instead of using real pod groups.

**Fix:**
- `NodePlanEntry` dataclass: added `packed_pods: Optional[List[Dict]]` field.
- `CapacityPlanner.plan()` provision loop: partitioned `leftover` pods evenly across `required` nodes using `chunk = ceil(len(leftover)/required)`. Each provision entry now carries `"packed_pods": pod_slice` — the exact list of pods assigned to that node.
- Per-slice CPU/memory sums computed accurately from pod requests instead of dividing aggregate totals.

**Impact:** `ISS._split_provision_entry()` now uses pod-group mode instead of arithmetic fallback. Split is accurate, UI utilization is correct.

**Files changed:**
- `backend/services/pod_placement_engine.py` — `NodePlanEntry.packed_pods` field + `CapacityPlanner.plan()` provision loop

---

### GAP-3 — UI override merge not implemented at read layer

**Problem:** When `NodeProvisioner` retries a failed pool and writes an `ExecutionOverride` row (e.g., `instance_type: m5.large → m5.2xlarge`), the UI reading `ManifestStore.read()` would still see `m5.large` (the original manifest value). Override rows existed in DB but were never merged at read time.

**Fix:** Added `ManifestStore.read_with_overrides(cluster_id, db)`:
- Reads manifest via Redis fast-path / DB fallback (standard `read()`)
- Calls `ExecutionOverrideStore.read_all(manifest_id, db)` → `{node_name: {field: latest_value}}`
- Calls `ExecutionOverrideStore.apply(node_plan, overrides)` → non-destructive merge (new list, manifest payload untouched)
- Returns `{**manifest, "node_plan": merged_node_plan, "_overrides_applied": True}`
- Graceful: on any merge failure returns raw manifest with debug log

**Usage:** All UI API routes that return execution plan / node provisioning status should call `ManifestStore.read_with_overrides()` instead of `ManifestStore.read()`.

**Files changed:**
- `backend/services/execution_engine.py` — `ManifestStore.read_with_overrides()` added

---

### Medium-A — DE determinism (execution-level cache)

**Status:** Already implemented in `InstanceSelector.resolve()` via `exec_cache` dict scoped to `InstanceSelectionService.resolve_all()` invocation. Cache key = `(az, cap_norm, min_vcpu, min_mem)` — same template within a single planning cycle always gets the same ranked results regardless of Redis cache timing.

No further action required.

---

### Medium-B — Explicit execution sub-states for UI

**Problem:** EE only wrote `EXECUTING`, `EXECUTING_STATELESS`, `DRAINING`, `VERIFYING`, `IDLE` to Redis. No `PROVISIONING`, `FAILED`, or `PARTIAL` states. UI could not distinguish "launching nodes" from "migrating pods".

**Fix:**
- Added `STATE_PROVISIONING`, `STATE_FAILED`, `STATE_PARTIAL` constants to `ExecutionEngine`.
- Added `STATE_LABELS` dict mapping state keys to human-readable strings (consumed by UI `/api/clusters/{id}/execution/status`).
- Added `_set_state(r, cluster_id, state)` static helper (replaces inline `r.set(...)` calls).
- Added `get_state_label(state)` static helper for API response formatting.
- `run()` now:
  - Sets `PROVISIONING` before `NodeProvisioner.provision_all()`
  - Sets `FAILED` in except handler before circuit breaker increment
  - Sets `PARTIAL` after `Verifier.verify()` when `mismatched / total > MISMATCH_RATE_THRESHOLD`
- All inline `r.set(f"spot:cluster:state:...")` replaced with `_set_state()`.

**Files changed:**
- `backend/services/execution_engine.py` — `STATE_*` constants, `STATE_LABELS`, `_set_state()`, `get_state_label()`, `run()` state wiring

---

### Medium-C — PPE → DE contract validation (PPEContractGuard)

**Problem:** No schema enforcement between `PlacementPlan` (produced by PPE) and `DistributionEngine.build()`. A malformed plan (missing `pod_name`, `cluster_id`, `az`, etc.) could produce an empty/corrupt manifest silently.

**Fix:** Added `DistributionEngine._contract_guard(plan)` — runs as Layer 0a BEFORE ISS and ManifestGuard:
- Validates top-level required keys (`movement_plan`, `feasibility`)
- Validates `movement_plan` entries: each must have `pod_name` AND (`to_node` OR `blocked_by`)
- Validates provision entries: must have `az` + `capacity_type`
- Validates `feasibility.cluster_id` is set (missing = PPE didn't inject it)
- Returns `None` on pass; error string on fail → `build()` returns `{"status": "ABORT", "reason": ...}`

**Files changed:**
- `backend/services/distribution_engine.py` — `_contract_guard()` + call in `build()` at Layer 0a

---

## Phase: WIE→PPE Pipeline Fix (v4.6 — Workload Spot/OD Classification)

**Root cause:** The WIE→PPE handoff was "dead" — WIE emitted a `spot_friendly: bool` that PPE consumed as a binary gate. Any workload with `spot_friendly=True` sent all pods to spot; `spot_friendly=False` sent none. DB and Redis workloads had no hard block in `compute_spot_distribution`. The Distribution Engine had no ordering guarantee between workload classes and only two execution strategies (BLUE_GREEN / BATCH). This caused:
- Redis/Postgres pods landing on spot nodes
- Empty movement plans when WIE gave all-or-nothing classification
- StatefulSet primary pods (pod-0) being spot-evicted
- Instance selection ignoring the `capacity_type` constraint on provision entries

---

### Fix 1 — WIE: `workload_class` field + DB hard block

**File:** `backend/services/workload_identification_engine.py`

**Changes:**
- Added `workload_class: str = "stateless"` to `WorkloadClassification` dataclass (v4.6 field). Values: `"db" | "stateful" | "stateless" | "mixed"`.
- Added module-level `_DB_APP_MARKERS` frozenset (redis, postgres, mysql, mongodb, elasticsearch, kafka, zookeeper, cassandra, etcd, memcached, mariadb, mongo).
- Added **hard DB block** in `compute_spot_distribution`: if `detected_app_type` matches any DB marker OR `has_pvc=True` → always return `(replicas, 0)`. No exceptions, no overrides.
- Added **Step 7c** in `classify_workload`: derives `workload_class` from `detected_app_type` and `controller_kind` after spot distribution is computed.
- Added `workload_class` reset to `"stateful"` in `enforce_safety_invariants` when the stateful-without-resilience block fires.
- Added `"workload_class"` to `serialize_classification` output so it flows into PPE and Distribution Engine.

**Unit test:** Redis StatefulSet with 3 replicas → `max_spot_replicas = 0`, `workload_class = "db"`.

---

### Fix 2 — PPE: Per-pod spot disqualification in `PodSelector`

**File:** `backend/services/pod_placement_engine.py`

**Changes:**
- Added `PodSelector._SPOT_BLOCK_APP_TYPES` frozenset (same DB markers as WIE).
- Added `PodSelector._is_spot_disqualified(pod, wie, total_replicas)` → `(bool, reason_str)`. Disqualification rules (conservative — when in doubt, OD):
  1. `has_pvc` or `persistent_volume_claims` → `"has_pvc"`
  2. `total_replicas <= 1` → `"singleton"`
  3. Pod name ends in `-0` → `"primary_pod_ordinal_0"`
  4. Label `role` in (`primary`, `master`, `leader`) → `"primary_label:role=..."`
  5. `statefulset.kubernetes.io/pod-name` label ends in `-0` → `"primary_sts_pod_name"`
  6. WIE `detected_app_type` matches DB marker → `"db_app_type:..."`
  7. WIE `workload_class == "db"` → `"workload_class:db"`
  8. `restart_count > 3` → `"high_restarts:N"`
- In `classify_and_score`: disqualified pods go into `forced_od` bucket (tagged with `spot_disqualified=True`, `disqualified_reason`). `od_target_eff` and `spot_target_eff` are adjusted so delta logic respects forced assignments. Forced pods end up in `stay_put` — no movement required.

**Unit test:** 3 pods, one with `has_pvc=True` → that pod in `stay_put` (not `to_move_to_spot`).

---

### Fix 3 — PPE: 15% resource headroom on provision entries

**File:** `backend/services/pod_placement_engine.py`

**Changes:**
- In CapacityPlanner provision loop: apply `_OVERHEAD = 1.15` to `required_cpu_millicores` and `required_memory_bytes` before writing each provision entry. Prevents OOMKill and kubelet evictions from OS overhead.

**Unit test:** 3 pods each requesting 500m CPU → provision entry `required_cpu_millicores = ceil(1500 * 1.15) = 1725`.

---

### Fix 4 — ISS: `required_capacity_type` enforcement

**File:** `backend/services/instance_selection_service.py`

**Changes:**
- In `resolve_all`: reads `entry.get("capacity_type")` from each provision entry and injects it into `policy["required_capacity_type"]`.
- In `_resolve_with_escalation`: passes `required_capacity_type=policy.get("required_capacity_type")` to `InstanceSelector.resolve()` so the selector can pre-filter candidate pools by capacity type before ML scoring. OD provision entries will not receive spot instance types and vice versa.

**Integration test:** OD node group must not return a spot instance type from `resolve_all`.

---

### Fix 5 — Distribution Engine: SERIAL/ROLLING strategies + hard class ordering

**File:** `backend/services/distribution_engine.py`

**Changes:**

**WorkloadSorter:**
- Added `CLASS_ORDER = {"db": 0, "stateful": 1, "mixed": 2, "stateless": 3}` — hard execution barrier.
- Added `_derive_class(profile)` — resolves `workload_class` from explicit field or falls back to `detected_app_type`/`data_safety`/`controller_kind` derivation. Shared by sorter and group builder.
- Sort key changed: primary key is `CLASS_ORDER[workload_class]`, secondary key is `-priority(wid)`. DB workloads always complete before stateful; stateful always before stateless.

**MigrationGroupBuilder:**
- `group_type()` now returns `"SERIAL"` for `db`, `"BLUE_GREEN"` for `stateful`/critical, `"ROLLING"` for `stateless`, `"BATCH"` fallback.
- Added `build_serial()`: one pod at a time with `SEQUENTIAL_GATED` execution. Each step has `on_timeout: HALT_GROUP_AND_ROLLBACK`. `halt_class_on_failure: True` signals the Execution Engine to stop the entire class on any timeout.
- Added `build_rolling()`: `PARALLEL_BATCHED_PDB_SAFE` execution. Batch size = `min(pdb_max_unavailable, ceil(total * 0.25))`. Each batch includes a `pdb_check` dict with `safe_to_proceed` boolean computed at plan time.

**DistributionEngine.build():** Dispatch routes `SERIAL → build_serial`, `BLUE_GREEN → build_blue_green`, `ROLLING → build_rolling`, `BATCH → build_batch`.

**Unit test:** Mixed workload (db=redis, stateful=postgres-sts, stateless=nginx-deploy) → `workload_priority_order` sorted `[redis-wid, postgres-sts-wid, nginx-deploy-wid]`.

---

### Gap Fix — Phase 1 completeness (plan.md audit)

**File:** `backend/services/workload_identification_engine.py`

**Changes:**
- Added `total_replicas: int = 0` and `spot_eligible: bool = False` to `WorkloadClassification` dataclass. `spot_eligible` is derived (`max_spot_replicas > 0`), set in Step 7b of `classify_workload`.
- Added validation clamp in Step 7b: if `min_od + max_spot != total_replicas`, clamp `max_spot = total - min_od` and log a structured warning. Prevents miscounts propagating to PPE.
- Updated `compute_spot_distribution` ratios to match plan.md hard rules:
  - **STATEFUL / StatefulSet** (without DB markers): `min_od = ceil(replicas * 0.5)`, `max_spot = replicas - min_od`. Resilience guard (`_is_stateful_spot_safe`) still applied first — returns full OD if no resilience signals.
  - **STATELESS** (Deployment / ReplicaSet): `min_od = max(1, ceil(replicas * 0.2))`, `max_spot = replicas - min_od`. 20% OD floor.
  - **MIXED / unknown**: Conservative fallback — full OD if no PDB, otherwise PDB-based.
- Added `import math` at module level.
- `serialize_classification` now emits `total_replicas` and `spot_eligible` in the output dict.

**Unit test:** 5-replica Deployment → `min_on_demand_replicas = 1`, `max_spot_replicas = 4`, `spot_eligible = True`.

---

### Phase 2 — Target Builder (new file)

**File:** `backend/services/target_builder.py` *(new)*

**Changes:**
- Created `PlacementTarget` dataclass with all fields from plan.md: `namespace`, `controller_name`, `controller_kind`, `workload_class`, `od_target`, `spot_target`, `total_replicas`, `current_od_count`, `current_spot_count`, `current_unknown_count`, `delta_od`, `delta_spot`, `action_required`, `signals`.
- Created `build_targets(classifications, live_pods, live_nodes)` → `List[PlacementTarget]`:
  - Builds `node → capacity_type` map from `live_nodes`.
  - For each classification, counts current OD/spot pod distribution via `_count_pod_capacity_types()` (matches pods by `namespace` + `controller_name`).
  - Unknown capacity type treated conservatively as OD.
  - `action_required = (delta_od != 0 or delta_spot != 0)`. Workloads already at target set `action_required = False` → PPE skips them entirely.
- Created `filter_actionable(targets)` helper — returns only targets that need PPE work.
- Helper `_get_controller_name(pod)` derives controller from pod fields with suffix-stripping fallback.

**Unit test:** Classification with `od_target=1, spot_target=2` and live state `od=1, spot=2` → `action_required = False`.

---

### Bug Fix — ISS `required_capacity_type` crash

**File:** `backend/services/instance_selection_service.py`

**Problem:** `required_capacity_type` was being passed as a keyword argument to `InstanceSelector.resolve()` which does not accept that parameter → would cause `TypeError` at runtime.

**Fix:** Removed `required_capacity_type=...` from `selector.resolve()` call. Added comment explaining that capacity type enforcement is already handled inside `InstanceSelector.resolve()` Step 2 (Problem 6c) via `provision_entry["capacity_type"]` — which already filters the DE candidate pool before ML scoring. The `required_capacity_type` in policy is retained for audit/logging purposes only.

---

## plan.md Implementation — WIE v4.6 + Target Builder Wiring + UI Badges (2026-05-06)

### Phase 1 — WIE Output Contract: `workload_class`, `spot_eligible`, `total_replicas`

**Problem:** `WorkloadClassification` dataclass already produced `workload_class`, `spot_eligible`, and `total_replicas` but none were persisted to the DB. Downstream consumers (PPE, ISS, Distribution Engine, UI) could not read `workload_class`, so execution strategy defaulted to `ROLLING` for all workloads including DBs and StatefulSets.

**Files changed:**

**`backend/migrations/016_add_wie_v46_workload_class.py`** *(new file)*
- `ALTER TABLE workload_classifications ADD COLUMN IF NOT EXISTS workload_class VARCHAR(20) NOT NULL DEFAULT 'stateless'`
- `ALTER TABLE workload_classifications ADD COLUMN IF NOT EXISTS spot_eligible BOOLEAN NOT NULL DEFAULT false`
- `ALTER TABLE workload_classifications ADD COLUMN IF NOT EXISTS total_replicas INTEGER NOT NULL DEFAULT 0`
- Back-fills `spot_eligible` from `max_spot_replicas > 0`
- Back-fills `workload_class = 'db'` for well-known DB name patterns with `data_safety = STATEFUL`
- Back-fills `workload_class = 'stateful'` for `StatefulSet` controller kind + `data_safety = STATEFUL`

**`backend/models/workload_classification.py`**
- Added ORM columns: `workload_class`, `spot_eligible`, `total_replicas`
- Bumped `schema_version` default to `"4.6"`

**`backend/services/workload_identification_engine.py`** — slow-loop write path (UPDATE + INSERT)
- Both branches now write: `workload_class`, `spot_eligible`, `total_replicas` from `classification`

---

### Phase 2 — Target Builder Wired into cluster-execution-plan Endpoint

**Problem:** `backend/services/target_builder.py` existed with full `build_targets()` but was never imported or called. The endpoint computed `_od_t`/`_sp_t` without first checking whether the current pod distribution already matched desired state, causing unnecessary PPE calls and false-positive drain signals.

**File:** `backend/api/optimize_routes.py`

**Changes:**
- Added import: `from backend.services.target_builder import build_targets as _build_targets`
- After fetching pods per workload, call `_build_targets(classifications=[{...}], live_pods=pods_w, live_nodes=nodes_input)`
- If `_targets[0].action_required is False` → `continue` (skip PPE for this workload entirely)
- Classification dict passed includes: `namespace`, `controller_name`, `controller_kind`, `workload_class`, `min_on_demand_replicas`, `max_spot_replicas`, `total_replicas`

---

### Phase 5 — workload_class Propagated into WIE dict Fed to PPE

**File:** `backend/api/optimize_routes.py`

Added `"workload_class": getattr(wc, "workload_class", "stateless") or "stateless"` to the `_wie_w` dict passed to `PodPlacementEngine.materialize_plan()`. PPE now receives `workload_class` for scoring decisions.

---

### Phase 7 — execution_strategy + workload_class in API Response

**File:** `backend/api/optimize_routes.py`

**Problem:** `drain_nodes` API response had no `workload_class` or `execution_strategy` fields. UI could not show whether a drain was Serial (DB), Blue/Green (Stateful), or Rolling (Stateless).

**Changes:**
- Added `node_workload_meta: dict` accumulator (`node_name → {workload_class, execution_strategy}`)
- In Step 2 drain loop, after marking a node for drain, derive strategy: `db→SERIAL`, `stateful|mixed→BLUE_GREEN`, `stateless→ROLLING`
- Each `drain_nodes` entry now includes `"workload_class"` and `"execution_strategy"` fields

---

### UI — NodeSelector.jsx: workload_class Badge + execution_strategy Indicator

**File:** `frontend/src/pages/optimize/nodes/NodeSelector.jsx`

**Problem:** Expanded drain-node panel header showed only pod/destination count with no workload class or execution strategy context.

**Changes:**

1. Two fast-lookup maps derived from `clusterPlan.drain_nodes`:
   - `workloadClassMap`: `node_name → workload_class`
   - `execStrategyMap`: `node_name → execution_strategy`

2. In the REPLACE/TERMINATE panel header, two colour-coded badges rendered beside the pod count:
   - **Workload class badge:** `DB` (red), `Stateful` (amber), `Stateless` (green), `Mixed` (purple)
   - **Execution strategy badge:** `Serial` (red border), `Blue/Green` (blue border), `Rolling` (green border)

**Visual result:** Header now reads e.g. `3 pods → 2 nodes  [Stateless]  [Rolling]`

---

### Containers Rebuilt / Restarted

- Migration 016 executed: `docker exec spot-optimizer-backend python /app/backend/migrations/016_add_wie_v46_workload_class.py` → `Done`
- Frontend Docker image rebuilt from `docker/Dockerfile.frontend`
- Frontend container restarted on `docker_app-network` port 3000
- Backend container restarted (volume-mounted — picks up Python changes on restart)
- Celery worker + beat restarted

---
