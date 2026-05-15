# Execution Plan — Phase 3: Reliability, Completeness & Production Hardening
## Spot Optimizer Platform

> **Source:** Gap list from ui-data-readiness.md + SYSTEM_EXECUTION_AUDIT.md + memory.md
> **Validated against:** actual codebase state (audit v11.0, memory.md T-01→T-24 ALL COMPLETE)
> **DO NOT implement without following stated execution order.**
> **State file:** `temp-doc/memory.md` — read before every session, write after every task.

---

## Codebase Ground Truth (Read This First)

These facts override any assumption. Confirmed from SYSTEM_EXECUTION_AUDIT.md v11.0.

| Fact | Confirmed State |
|---|---|
| T-01 → T-24 (prior plan) | ALL COMPLETE — do not re-implement |
| `aws_pricing_service.py` | EXISTS — fetches real-time Spot/OD prices from AWS |
| `pricing_worker.py` | EXISTS — fetches latest Spot pricing; writes `spot:pricing:instance:{type}:{region}` Redis keys |
| `instance_catalog_worker.py` | EXISTS — ingests EC2 instance types with CPU/Mem/ENI capabilities |
| `resource_pricing_service.py` | EXISTS — correlates usage with AWS prices |
| `resource_cost_service.py` | EXISTS — per-workload/namespace cost breakdowns |
| `circuit_breaker.py` | EXISTS — production circuit breaker service |
| `cooldown_controller.py` | EXISTS — time-based lock enforcement |
| `distributed_locks.py` | EXISTS — Redis-backed distributed mutexes |
| `observability_logger.py` | EXISTS — structured JSON logging to DataDog/CloudWatch |
| `audit_service.py` | EXISTS — immutable action trail |
| `execution_controller.py` | EXISTS — 4 methods STUBBED: `_wait_substitute_ready`, `_drain_node`, `_verify_workload_health`, `_terminate_node` |
| `pool_optimization_worker` | EXISTS at line 69 — body is TODO, only records timestamp |
| `AgentActionStatus` enum | `PENDING`, `PICKED_UP`, `COMPLETED`, `FAILED`, `EXPIRED` — NO `RUNNING` |
| `AgentActionType.EVICT_POD` | Correct — NOT `EVICT` |
| New router registration | `backend/core/api_gateway.py` only — NOT `backend/api/__init__.py` |
| `optimize_routes.py` | NEW file (T-03) — different from existing `optimization_routes.py` |
| `aws_pricing_service.py` has `get_spot_price()` | NEEDS_VERIFY before implementation |
| `health.py` worker | EXISTS — cleans zombie nodes, stuck agents, stale Redis keys |
| `circuit_breaker.py` Engine B gap | No circuit breaker for PlacementController (Engine A has one, Engine B does not) |

---

## What Is Explicitly OUT OF SCOPE for This Plan

Do not implement these. They require a dedicated architecture cycle.

- **WorkloadMigration page full workflow** (steps, pre-checks, AWS API validation, blast radius) — architectural engine not justified in this cycle
- **RPS / request-rate metrics pipeline** — requires Prometheus integration or dedicated network proxy; agent cannot collect this
- **Prometheus integration** — no Prometheus in current stack
- **Shadow mode auto-graduation** — manual Redis DEL is the current mechanism; automation not justified yet
- **WIE + WorkloadInspector unification** — dual classification systems; deprecation requires separate cycle

---

## Overview

| Dimension | Count |
|---|---|
| Total new tasks | 26 (P-01 through P-26) |
| New files | 6 |
| Modified files | ~18 |
| New DB columns | 4 |
| New Alembic migrations | 1 |
| New Redis patterns | 1 standardized |
| Batches | 5 |

---

## Dependency Graph

```
BATCH 1 — Foundation: safety primitives that everything else depends on
  P-01  Data freshness decorator + stale detection utility
  P-02  Standardized null/data_ready API contract utility
  P-03  Unified Redis TTL registry
  P-04  Input validation + cluster access guard middleware

BATCH 2 — Data layer hardening: Redis/DB consistency and retry
  P-05  Redis read safety wrapper (fallback + freshness check)
  P-06  Retry decorator for DB/Redis/HTTP writes
  P-07  Partial failure handler for multi-source endpoints
  P-08  Upsert conflict handling audit (node_metadata, hpa_configs)

BATCH 3 — State models: explicit state machines
  P-09  Workload placement state machine (DRIFTING → CONVERGING → AT_TARGET)
  P-10  Node lifecycle states (active / draining / terminating)
  P-11  Pod lifecycle classification (serving / idle / evicting)

BATCH 4 — Engine hardening and completeness
  P-12  Engine B (PlacementController) circuit breaker
  P-13  Feature flags for T-05, T-09, T-13 risky paths
  P-14  ExecutionController stub wiring (4 methods)
  P-15  Pool optimization worker real body
  P-16  Pricing engine: spot vs OD differentiation + region awareness
  P-17  Staleness indicator field in all optimize/* API responses
  P-18  per-batch regression validation hook

BATCH 5 — Observability, cleanup, concurrency, agent compat
  P-19  System health metrics endpoint
  P-20  Centralized failure log (beyond per-workload Redis list)
  P-21  Redis race condition guards for new write paths
  P-22  DB retention policies for new tables
  P-23  Rate limiting on heavy optimize/* endpoints
  P-24  Agent backward compatibility layer
  P-25  Definition-of-done validation checklist runner
  P-26  Concurrency: Redis INCR/DECR for aggregate counters
```

---

## Task Breakdown (Granular)

---

### P-01 — Data Freshness Utility + Stale Detection

**Status:** MISSING
**Batch:** 1
**UI Gap:** `DataFreshness.timestamp`, `DataFreshness.stale_detection`, `StalenessUI.indicator`, `StalenessUI.warning_logic`

**Description:** Create a reusable utility that (a) computes `data_age_seconds` from a stored `updated_at` timestamp, (b) detects stale data via configurable threshold, and (c) provides a decorator to inject `data_updated_at` + `data_age_seconds` + `is_stale` into any endpoint response.

**Files to create:**
- `backend/utils/data_freshness.py` (NEW)

**Files to modify:**
- `backend/api/optimize_routes.py` — apply decorator to T-14, T-17, T-22, T-23, T-24 endpoints

**Required changes:**

1. Create `backend/utils/data_freshness.py`:

```python
from datetime import datetime, timezone
from typing import Optional
from functools import wraps

STALE_THRESHOLD_SECONDS = 120  # configurable via env AURA_STALE_THRESHOLD_SECS

def compute_freshness(updated_at: Optional[datetime]) -> dict:
    """Returns data_updated_at, data_age_seconds, is_stale for any response."""
    if updated_at is None:
        return {"data_updated_at": None, "data_age_seconds": None, "is_stale": True}
    now = datetime.now(timezone.utc)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    age = (now - updated_at).total_seconds()
    return {
        "data_updated_at": updated_at.isoformat(),
        "data_age_seconds": round(age, 1),
        "is_stale": age > STALE_THRESHOLD_SECONDS,
    }

def stale_node_filter(nodes: list, updated_at_field: str = "updated_at") -> list:
    """Exclude nodes whose updated_at is older than STALE_THRESHOLD_SECONDS."""
    from datetime import datetime, timezone
    cutoff = datetime.now(timezone.utc).timestamp() - STALE_THRESHOLD_SECONDS
    result = []
    for n in nodes:
        ts = getattr(n, updated_at_field, None)
        if ts is None:
            continue
        if ts.replace(tzinfo=timezone.utc).timestamp() >= cutoff:
            result.append(n)
    return result
```

2. In `optimize_routes.py`, import `compute_freshness` and append its output to the response dict of these endpoints:
   - `GET /nodes/bin-packing` — use `MAX(node_metadata.updated_at)` for the cluster
   - `GET /workloads/placement/summary` — use `MAX(workload_classifications.classified_at)`
   - `GET /workloads/scaling` — use `MAX(hpa_status_snapshots.snapshot_at)`
   - `GET /workloads/{id}/profiling-detail` — use `MAX(pod_metrics.timestamp)`
   - `GET /workloads/{id}/scaling-detail` — use `MAX(hpa_status_snapshots.snapshot_at)`

3. Apply `stale_node_filter()` in `GET /nodes/bin-packing` before computing bin-packing percentages. Nodes with `updated_at > 120s ago` are excluded and noted in response as `stale_nodes_excluded: N`.

**Dependencies:** None.

**Validation:**
```bash
# Manually SET a node_metadata.updated_at to 5 minutes ago in DB
curl "/api/v1/optimize/nodes/bin-packing?cluster_id={cid}"
# Response must include: data_updated_at, data_age_seconds, is_stale: true, stale_nodes_excluded: 1
```

**Risk:** LOW — additive fields, no mutation of existing logic.

---

### P-02 — Standardized API Response Contract Utility

**Status:** MISSING
**Batch:** 1
**UI Gap:** `UIContract.response_schema`, `UIContract.null_handling`, `UIContract.data_ready_flags`

**Description:** Create a single response wrapper used by all `optimize_routes.py` endpoints to guarantee consistent field presence, null handling, and `data_ready`/`data_ready_reason` flags. Eliminates silent field omissions that break UI rendering.

**Files to create:**
- `backend/utils/api_response.py` (NEW)

**Files to modify:**
- `backend/api/optimize_routes.py` — wrap all new endpoint responses

**Required changes:**

1. Create `backend/utils/api_response.py`:

```python
from typing import Any, Optional

def ok(data: Any, data_ready: bool = True, data_ready_reason: str = "") -> dict:
    """Standard success response. Always includes data_ready and data_ready_reason."""
    return {
        "data_ready": data_ready,
        "data_ready_reason": data_ready_reason,
        **data,
    }

def not_ready(reason: str, partial_data: Optional[dict] = None) -> dict:
    """Response for when required data sources are not yet populated."""
    base = {"data_ready": False, "data_ready_reason": reason}
    if partial_data:
        base.update(partial_data)
    return base

def null_safe(value: Any, default: Any = None) -> Any:
    """Return value if not None, else default. Use for all optional fields."""
    return value if value is not None else default
```

2. All 10 endpoints in `optimize_routes.py` must wrap their return dict with `ok(...)` or `not_ready(...)`. No endpoint may return a raw dict without these keys.

3. All optional numeric fields (percentages, counts, savings) must pass through `null_safe()` — never return Python `None` as a bare JSON `null` for fields the UI expects to be 0.

**Standard `data_ready_reason` strings (use exactly these — do not invent new ones):**
```
"node_allocatable_data_pending"   — node_metadata table empty (T-09 not deployed)
"pricing_data_pending"            — instance_catalog / pricing_worker not yet populated
"hpa_data_pending"                — hpa_configs table empty (T-13 not deployed)
"insufficient_history"            — < 7 days of snapshot data for recommendations
"stale_data"                      — data_age_seconds > STALE_THRESHOLD
""                                — data is ready (empty string, not null)
```

**Dependencies:** P-01 (data_freshness utility imports into api_response).

**Validation:**
```bash
curl "/api/v1/optimize/nodes/bin-packing?cluster_id={cid}"
# Every response must have data_ready, data_ready_reason keys
# Optional numeric fields must be 0, not null, when no data available
```

**Risk:** LOW — wrapper is additive. Existing response fields unchanged.

---

### P-03 — Unified Redis TTL Registry

**Status:** MISSING
**Batch:** 1
**UI Gap:** `Cleanup.redis_ttl_strategy`

**Description:** All Redis keys written by this system currently have TTLs scattered across multiple service files with no central reference. Create a single authoritative registry so any developer can find, audit, and change TTL values without grepping 20 files.

**Files to create:**
- `backend/redis_keys.py` already exists — extend it (confirmed from memory.md: Task 5.3 modified `backend/redis_keys.py`)

**Required changes:**

1. Add a `REDIS_TTL` dict to `backend/redis_keys.py` alongside the existing key templates:

```python
# Unified TTL registry — all Redis key TTLs in one place
REDIS_TTL = {
    # Placement Controller
    "workload_state":            300,   # spot:workload:state:{cid}:{wid}
    "workload_log":              3600,  # spot:pc:workload_log:{cid}:{wid}
    "pc_metrics":                3600,  # spot:placement_controller:metrics:{cid}
    "pc_workload_metrics":       3600,  # spot:placement_controller:metrics:{cid}:{wid}
    "placement_summary":         60,    # spot:placement:summary:{cid}
    "cooldown":                  600,   # spot:placement_controller:cooldown:{cid}:{wid}
    "rollout_blocked":           14400, # spot:placement:rollout_blocked:{cid}:{wid} (4h)
    "keda_last_scale":           120,   # spot:keda:last_scale_event:{cid}
    # Consolidation
    "consolidation_candidates":  600,   # spot:consolidation:candidates:{cid}
    # Pricing
    "instance_price":            3600,  # spot:pricing:instance:{type}:{region}
    # Cluster mutex
    "cluster_mutex":             60,    # spot:cluster_mutex:{cid}
    "workload_lock":             30,    # spot:workload_lock:{cid}:{wid}
    "rebalance_active_count":    300,   # rebalance:active_count:{cid}
    # Ondemand fallback
    "ondemand_fallback":         43200, # spot:ondemand_fallback:{cid} (12h)
}
```

2. Find every `self.redis.expire(key, <hardcoded_number>)` call across `placement_controller_service.py`, `optimize_routes.py`, `consolidation_analysis_task.py`, `hpa_recommendation_task.py` and replace the hardcoded number with `REDIS_TTL["<key_type>"]`.

3. **Do NOT change TTL values** — only centralize them. Any TTL change requires explicit sign-off because it affects system safety (cooldown durations, mutex windows).

**Dependencies:** None.

**Validation:**
```bash
grep -r "\.expire(" backend/services/placement_controller_service.py backend/api/optimize_routes.py
# All expire() calls must reference REDIS_TTL["..."] not raw integers
```

**Risk:** LOW — pure refactor, no behavior change.

---

### P-04 — Input Validation + Cluster Access Guard

**Status:** MISSING
**Batch:** 1
**UI Gap:** `Security.input_validation`, `Security.access_control`

**Description:** All new `optimize_routes.py` endpoints accept `cluster_id` and `workload_id` as path/query parameters with no validation. A malformed or unauthorized `cluster_id` currently causes unhandled exceptions or exposes another tenant's data.

**Files to modify:**
- `backend/api/optimize_routes.py`
- `backend/utils/validation.py` (NEW or extend if exists)

**Required changes:**

1. Create/extend `backend/utils/validation.py`:

```python
import re
from fastapi import HTTPException, Depends
from backend.models.cluster import Cluster
from backend.models.base import SessionLocal

CLUSTER_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]{1,64}$')
WORKLOAD_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.\/]{1,253}$')

def validate_cluster_id(cluster_id: str) -> str:
    if not CLUSTER_ID_PATTERN.match(cluster_id):
        raise HTTPException(status_code=422, detail="Invalid cluster_id format")
    return cluster_id

def validate_workload_id(workload_id: str) -> str:
    if not WORKLOAD_ID_PATTERN.match(workload_id):
        raise HTTPException(status_code=422, detail="Invalid workload_id format")
    return workload_id

def assert_cluster_access(cluster_id: str, db) -> None:
    """Raises 404 if cluster_id does not exist in DB. Prevents cross-tenant access."""
    exists = db.query(Cluster.id).filter(Cluster.id == cluster_id).scalar()
    if not exists:
        raise HTTPException(status_code=404, detail="Cluster not found")
```

2. In every `optimize_routes.py` endpoint that accepts `cluster_id`:
   - Add `validate_cluster_id(cluster_id)` as the first line
   - Add `assert_cluster_access(cluster_id, db)` as the second line

3. In endpoints that accept `workload_id` path parameter:
   - Add `validate_workload_id(workload_id)` as the first line

4. For `node_name` path parameter (T-21): validate it matches `[a-zA-Z0-9\-\.]{1,253}`.

**Pre-check:** Confirm `Cluster` model import path from `backend/models/cluster.py` before writing — use actual path found in codebase.

**Dependencies:** None.

**Validation:**
```bash
curl "/api/v1/optimize/nodes/bin-packing?cluster_id=../../etc/passwd"
# Must return 422, not 500
curl "/api/v1/optimize/nodes/bin-packing?cluster_id=nonexistent-cluster-xyz"
# Must return 404, not 500 or empty 200
```

**Risk:** LOW — additive validation. Legitimate requests are unaffected.

---

### P-05 — Redis Read Safety Wrapper

**Status:** MISSING
**Batch:** 2
**UI Gap:** `RedisDBConsistency.fallback`, `RedisDBConsistency.validation`

**Description:** `optimize_routes.py` currently calls `redis_client.get()`, `lrange()`, `hgetall()` with no fallback when keys are absent (Redis restart, key expiry, cold start). This causes `None` being passed to `json.loads()` → `TypeError` at runtime.

**Files to modify:**
- `backend/utils/redis_safe.py` (NEW)
- `backend/api/optimize_routes.py` — replace all bare Redis reads

**Required changes:**

1. Create `backend/utils/redis_safe.py`:

```python
import json
import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

def safe_get_json(redis_client, key: str, default: Any = None) -> Any:
    """GET a Redis key and JSON-decode it. Returns default on miss, expiry, or decode error."""
    try:
        val = redis_client.get(key)
        if val is None:
            return default
        return json.loads(val)
    except (json.JSONDecodeError, TypeError) as e:
        log.warning("Redis safe_get_json failed for key=%s: %s", key, e)
        return default

def safe_hgetall(redis_client, key: str, default: Optional[dict] = None) -> dict:
    """HGETALL a Redis key. Returns default (empty dict) on miss."""
    try:
        result = redis_client.hgetall(key)
        return result if result else (default or {})
    except Exception as e:
        log.warning("Redis safe_hgetall failed for key=%s: %s", key, e)
        return default or {}

def safe_lrange_json(redis_client, key: str, start: int, end: int, default: Optional[list] = None) -> list:
    """LRANGE a Redis LIST and JSON-decode each element. Returns default on miss."""
    try:
        items = redis_client.lrange(key, start, end)
        if not items:
            return default or []
        return [json.loads(i) for i in items if i]
    except Exception as e:
        log.warning("Redis safe_lrange_json failed for key=%s: %s", key, e)
        return default or []

def safe_ttl(redis_client, key: str) -> Optional[int]:
    """TTL a Redis key. Returns None if key absent or error."""
    try:
        ttl = redis_client.ttl(key)
        return ttl if ttl > 0 else None
    except Exception as e:
        log.warning("Redis safe_ttl failed for key=%s: %s", key, e)
        return None
```

2. In `optimize_routes.py`, replace every bare `redis_client.get(...)` / `json.loads(redis_client.get(...))` / `redis_client.lrange(...)` with the safe equivalents.

3. In `T-02` placement-state endpoint, wrap all 5 Redis reads (`cooldown TTL`, `rollout_blocked TTL`, `rebalance:active_count`, `keda_last_scale TTL`, `workload_log lrange`) with safe wrappers.

**Dependencies:** None.

**Validation:**
```bash
# Flush all Redis keys in a test environment
redis-cli FLUSHDB
curl "/api/v1/optimize/workloads/placement/summary?cluster_id={cid}"
# Must return 200 with data_ready: false, NOT 500
```

**Risk:** LOW — pure defensive wrapping, no logic change.

---

### P-06 — Retry Decorator for DB/Redis/HTTP Writes

**Status:** MISSING
**Batch:** 2
**UI Gap:** `ExecutionSafety.retry_logic`

**Description:** Agent batch push endpoints (`/agents/node-metadata/batch`, `/agents/hpa-configs/batch`, `/agents/nodeclaims/batch`) and Celery tasks (`workload_cv_task`, `consolidation_analysis_task`, `hpa_recommendation_task`) have no retry on transient DB or Redis failures. One network blip drops the entire batch silently.

**Files to create:**
- `backend/utils/retry.py` (NEW)

**Files to modify:**
- `backend/api/agent_routes.py` — wrap batch insert handlers
- `backend/workers/tasks/workload_cv_task.py` — wrap DB write loop
- `backend/workers/tasks/consolidation_analysis_task.py` — wrap Redis write
- `backend/workers/tasks/hpa_recommendation_task.py` — wrap DB write

**Required changes:**

1. Create `backend/utils/retry.py`:

```python
import time
import logging
from functools import wraps
from typing import Tuple, Type

log = logging.getLogger(__name__)

def with_retry(
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
    backoff_factor: float = 2.0,
):
    """Decorator: retries the wrapped function on specified exceptions with exponential backoff."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            delay = backoff_seconds
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        log.error("Max retries reached for %s: %s", fn.__name__, e)
                        raise
                    log.warning("Retry %d/%d for %s after %ss: %s",
                                attempt, max_attempts, fn.__name__, delay, e)
                    time.sleep(delay)
                    delay *= backoff_factor
        return wrapper
    return decorator
```

2. In each agent batch endpoint handler, wrap the DB session commit in a try/except that logs and returns HTTP 503 (not 500) on DB failure after retries, so the agent retries on next heartbeat:

```python
from backend.utils.retry import with_retry
from sqlalchemy.exc import OperationalError

@with_retry(exceptions=(OperationalError,), max_attempts=3, backoff_seconds=0.5)
def _bulk_upsert_node_metadata(db, records): ...
```

3. In Celery tasks, wrap the outer loop body (not the task itself — Celery has its own retry mechanism). Use `with_retry` on the per-cluster write call.

**Do NOT wrap Celery tasks with this decorator** — use Celery's built-in `self.retry()`. This decorator is for non-Celery functions called by tasks.

**Dependencies:** None.

**Validation:**
```bash
# Simulate DB failure by temporarily revoking write access in test DB
# Agent batch POST to /agents/node-metadata/batch must return 503 not 500
# After DB restored, next heartbeat cycle must succeed and data must appear
```

**Risk:** LOW — additive. Existing code paths unchanged.

---

### P-07 — Partial Failure Handler for Multi-Source Endpoints

**Status:** MISSING
**Batch:** 2
**UI Gap:** `ExecutionSafety.partial_failure`

**Description:** Several `optimize_routes.py` endpoints aggregate from 3+ sources (DB + Redis + DB). If one source is unavailable (e.g. `hpa_configs` table empty before T-13 ships), the endpoint currently either crashes or returns empty data without explanation. The UI shows nothing with no indication of why.

**Files to modify:**
- `backend/api/optimize_routes.py`

**Required changes:**

1. For every endpoint that reads from multiple sources, wrap each source independently:

```python
# Pattern to use in optimize_routes.py
def _safe_fetch(fn, fallback, label: str):
    """Call fn(); on any exception log it and return fallback. Never propagates."""
    try:
        return fn()
    except Exception as e:
        log.warning("Partial failure in %s: %s — returning fallback", label, e)
        return fallback
```

2. Apply this pattern in these specific endpoints:
   - `GET /workloads/scaling` — wrap `hpa_configs` DB read and `hpa_status_snapshots` read independently
   - `GET /workloads/{id}/scaling-detail` — wrap timeline query and config query independently
   - `GET /workloads/placement/summary` — wrap Redis `spot:workload:state` reads independently (one missing key must not abort the entire summary)
   - `GET /nodes/bin-packing` — wrap `consolidation_candidates` Redis read independently (absent key → `data_ready: false`, not crash)

3. Each partial failure must populate `data_ready_reason` with the appropriate reason string from P-02.

**Dependencies:** P-02 (response contract utility).

**Validation:**
```bash
# Drop hpa_configs table temporarily in test DB
curl "/api/v1/optimize/workloads/scaling?cluster_id={cid}"
# Must return 200 with data_ready: false, data_ready_reason: "hpa_data_pending"
# Must NOT return 500
```

**Risk:** LOW — defensive wrapping. Never changes happy-path behavior.

---

### P-08 — Upsert Conflict Audit and Fix

**Status:** NEEDS_VERIFY
**Batch:** 2
**UI Gap:** `Concurrency.db_conflicts`

**Description:** `node_metadata` and `hpa_configs` tables both use `ON CONFLICT DO UPDATE` upsert patterns (T-09, T-13). The audit confirms the ON CONFLICT clause was written but does not confirm the unique constraint exists in the Alembic migration. If the constraint is missing, the ON CONFLICT silently falls back to an INSERT that duplicates rows.

**Files to modify:**
- `migrations/versions/20260427_*.py` — verify unique constraints

**Required changes:**

1. Read `migrations/versions/20260427_hpa_tables.py` and `migrations/versions/` node_metadata migration. Confirm:
   - `node_metadata`: unique constraint on `(cluster_id, node_name)` exists in the migration
   - `hpa_configs`: unique constraint on `(cluster_id, namespace, workload_name)` exists

2. If either constraint is missing, add it:

```python
# In the migration file's upgrade() function
op.create_unique_constraint(
    "uq_node_metadata_cluster_node",
    "node_metadata",
    ["cluster_id", "node_name"]
)
```

3. Also verify `karpenter_node_claims` has unique constraint on `(cluster_id, node_name)`.

4. Run:
```sql
SELECT constraint_name FROM information_schema.table_constraints
WHERE table_name = 'node_metadata' AND constraint_type = 'UNIQUE';
```
Expected: returns `uq_node_metadata_cluster_node`.

**Dependencies:** None (verification task).

**Validation:**
```bash
# Insert same node_name twice via POST /agents/node-metadata/batch
# Must result in 1 row, not 2
SELECT COUNT(*) FROM node_metadata WHERE cluster_id='test' AND node_name='test-node';
# Must return 1
```

**Risk:** LOW if constraint already exists (no-op). MEDIUM if constraint is missing — adding it to production requires a lock-safe migration (unique constraint add on large table).

---

### P-09 — Workload Placement State Machine

**Status:** MISSING
**Batch:** 3
**UI Gap:** `StateModel.workload_state_machine`

**Description:** The `placement_status` field returned by `GET /workloads/placement/summary` (T-06) currently uses the raw decision log `action` field (`skip`/`evict`/`defer`/`rebalance`) as `placement_status`. This is not a state machine — it is a log entry. The UI needs `DRIFTING`, `CONVERGING`, `AT_TARGET` with explicit transition logic, not raw action names.

**Files to modify:**
- `backend/api/optimize_routes.py` — `_get_placement_workload_rows()` helper
- `backend/utils/state_machines.py` (NEW)

**Required changes:**

1. Create `backend/utils/state_machines.py`:

```python
from enum import Enum
from typing import Optional

class PlacementState(str, Enum):
    AT_TARGET   = "AT_TARGET"
    DRIFTING    = "DRIFTING"
    CONVERGING  = "CONVERGING"
    UNKNOWN     = "UNKNOWN"

def compute_placement_state(
    current_od: Optional[int],
    ondemand_target: Optional[int],
    last_action: Optional[str],  # from decision log: skip/evict/defer/rebalance
) -> PlacementState:
    """
    Transition rules:
      AT_TARGET   : |current_od - ondemand_target| <= 1
      CONVERGING  : current_od > ondemand_target AND last_action in (evict, rebalance)
                    → engine is actively correcting
      DRIFTING    : current_od > ondemand_target AND last_action in (skip, defer, None)
                    → engine is NOT correcting (blocked, cooling down, or no action)
      UNKNOWN     : any input is None
    """
    if current_od is None or ondemand_target is None:
        return PlacementState.UNKNOWN
    drift = current_od - ondemand_target
    if abs(drift) <= 1:
        return PlacementState.AT_TARGET
    if drift > 1:
        if last_action in ("evict", "rebalance"):
            return PlacementState.CONVERGING
        return PlacementState.DRIFTING
    # drift < -1: below target (rare — workload scaled down)
    return PlacementState.AT_TARGET
```

2. In `_get_placement_workload_rows()` in `optimize_routes.py`:
   - Read `current_spot_pods` and `current_ondemand_pods` from `spot:workload:state:{cid}:{wid}` (already done for drift calculation)
   - Read `ondemand_target` from `PlacementPolicyRecord`
   - Extract `last_action` from `lrange(spot:pc:workload_log:{cid}:{wid}, 0, 0)` — already fetched
   - Call `compute_placement_state(current_od, ondemand_target, last_action)`
   - Return as `placement_status` (replaces the raw action field currently used)

**Dependencies:** P-05 (safe Redis reads for workload log).

**Validation:**
```python
from backend.utils.state_machines import compute_placement_state, PlacementState
assert compute_placement_state(5, 5, "skip") == PlacementState.AT_TARGET
assert compute_placement_state(8, 5, "skip") == PlacementState.DRIFTING
assert compute_placement_state(8, 5, "evict") == PlacementState.CONVERGING
assert compute_placement_state(None, 5, "evict") == PlacementState.UNKNOWN
```

**Risk:** LOW — changes the value of `placement_status` in the API response. Frontend must be updated to expect `AT_TARGET`/`DRIFTING`/`CONVERGING` instead of raw action names. Coordinate with frontend before deploying.

---

### P-10 — Node Lifecycle States

**Status:** MISSING
**Batch:** 3
**UI Gap:** `StateModel.node_lifecycle`

**Description:** `node_metadata` table currently stores only `is_ready: bool`. The UI needs `active`, `draining`, `terminating` states. These are derivable from existing data without agent changes.

**Files to modify:**
- `backend/utils/state_machines.py` — add `NodeLifecycleState`
- `backend/api/optimize_routes.py` — apply in `GET /nodes/bin-packing` and `GET /nodes/{node_name}/bin-packing-detail`

**Required changes:**

1. Add to `backend/utils/state_machines.py`:

```python
class NodeLifecycleState(str, Enum):
    ACTIVE      = "ACTIVE"
    DRAINING    = "DRAINING"
    TERMINATING = "TERMINATING"
    NOT_READY   = "NOT_READY"

def compute_node_lifecycle(
    is_ready: bool,
    do_not_disrupt: bool,
    has_pending_drain: bool,  # from AgentAction WHERE type=DRAIN_NODE AND status IN (PENDING, PICKED_UP)
) -> NodeLifecycleState:
    """
    TERMINATING : node has a DRAIN_NODE action in PENDING or PICKED_UP state
    DRAINING    : do_not_disrupt=True AND is_ready=True (Karpenter has locked it for graceful drain)
    NOT_READY   : is_ready=False (kubelet not ready, node condition Unknown/NotReady)
    ACTIVE      : is_ready=True, no pending drain, not disruption-locked
    """
    if has_pending_drain:
        return NodeLifecycleState.TERMINATING
    if not is_ready:
        return NodeLifecycleState.NOT_READY
    if do_not_disrupt:
        return NodeLifecycleState.DRAINING
    return NodeLifecycleState.ACTIVE
```

2. In `GET /nodes/bin-packing`:
   - For each node from `node_metadata`, query `AgentAction` for pending `DRAIN_NODE` actions on that node:
     ```sql
     SELECT node_name FROM agent_actions
     WHERE cluster_id = :cid
       AND action_type = 'DRAIN_NODE'
       AND status IN ('PENDING', 'PICKED_UP')
     ```
   - Compute `lifecycle_state` per node using `compute_node_lifecycle()`
   - Return `lifecycle_state` per node in the response

**Dependencies:** P-09 (state_machines.py must exist).

**Validation:**
```bash
# Manually create a DRAIN_NODE AgentAction for a test node
curl "/api/v1/optimize/nodes/bin-packing?cluster_id={cid}"
# That node's lifecycle_state must be TERMINATING
```

**Risk:** LOW — additive field. Requires one extra DB query per bin-packing request; use `IN` clause to batch all nodes in one query.

---

### P-11 — Pod Lifecycle Classification

**Status:** MISSING
**Batch:** 3
**UI Gap:** `StateModel.pod_classification`

**Description:** `GET /workloads/{id}/pods` (T-15) returns `phase` (Running/Pending/Terminating) but no semantic classification. UI needs `serving`, `idle`, `evicting` for the efficiency breakdown.

**Files to modify:**
- `backend/utils/state_machines.py` — add `PodLifecycleClass`
- `backend/api/optimize_routes.py` — apply in T-15 and T-24 endpoints

**Required changes:**

1. Add to `backend/utils/state_machines.py`:

```python
class PodLifecycleClass(str, Enum):
    SERVING     = "SERVING"
    IDLE        = "IDLE"
    EVICTING    = "EVICTING"
    PENDING     = "PENDING"
    UNKNOWN     = "UNKNOWN"

IDLE_CPU_THRESHOLD_MILLICORES = 10  # pod using < 10m CPU = idle

def classify_pod_lifecycle(
    phase: Optional[str],
    cpu_usage_millicores: Optional[float],
    has_pending_evict: bool,  # from AgentAction WHERE type=EVICT_POD AND pod_name matches
) -> PodLifecycleClass:
    """
    EVICTING : pod has a pending EVICT_POD AgentAction
    PENDING  : phase = Pending
    SERVING  : phase = Running AND cpu_usage >= IDLE_CPU_THRESHOLD_MILLICORES
    IDLE     : phase = Running AND cpu_usage < IDLE_CPU_THRESHOLD_MILLICORES
    UNKNOWN  : phase is None or unrecognized
    """
    if has_pending_evict:
        return PodLifecycleClass.EVICTING
    if phase == "Pending":
        return PodLifecycleClass.PENDING
    if phase == "Running":
        if cpu_usage_millicores is not None and cpu_usage_millicores >= IDLE_CPU_THRESHOLD_MILLICORES:
            return PodLifecycleClass.SERVING
        return PodLifecycleClass.IDLE
    return PodLifecycleClass.UNKNOWN
```

2. In `GET /workloads/{id}/pods` (T-15):
   - For each pod, query AgentAction for pending `EVICT_POD` where `payload->>'pod_name' = pod_name`
   - Compute `lifecycle_class` using `classify_pod_lifecycle()`
   - Return `lifecycle_class` per pod in the response

3. In `GET /workloads/{id}/scaling-detail` (T-24):
   - Return aggregate counts: `serving_count`, `idle_count`, `evicting_count`, `pending_count`

**Dependencies:** P-09, P-10 (state_machines.py).

**Validation:**
```bash
# For a known idle pod (cpu < 10m)
curl "/api/v1/optimize/workloads/{wid}/pods?cluster_id={cid}"
# That pod's lifecycle_class must be IDLE not SERVING
```

**Risk:** LOW — additive classification field. `EVICT_POD` payload JSON query requires `payload->>'pod_name'` — confirm `AgentAction.payload` is JSONB type before writing this query.

---

### P-12 — Engine B (PlacementController) Circuit Breaker

**Status:** MISSING
**Batch:** 4
**Gap Source:** SYSTEM_EXECUTION_AUDIT.md §9: "No Engine B circuit breaker yet (Engine A has `karpenter_service._check_circuit_breaker`)"

**Description:** Engine A (auto_rebalancer) has a Karpenter circuit breaker that trips at 10 failures / 10 min. Engine B (PlacementController) has no circuit breaker — repeated eviction failures accumulate silently with only retry_count on individual AgentAction records. A broken cluster can receive unlimited eviction attempts.

**Files to modify:**
- `backend/services/placement_controller_service.py`
- `backend/utils/circuit_breaker_utils.py` (NEW — thin wrapper around existing `circuit_breaker.py`)

**Required changes:**

1. Check if `backend/services/circuit_breaker.py` has a reusable `check_circuit_breaker(key, threshold, window_seconds)` method. If yes, use it directly. If the interface differs, create `backend/utils/circuit_breaker_utils.py` as a thin adapter.

2. Add circuit breaker check in `run_cycle()` in `placement_controller_service.py`, after the cluster mutex acquisition and before the per-workload loop:

```python
CIRCUIT_BREAKER_THRESHOLD = 10    # failures
CIRCUIT_BREAKER_WINDOW    = 600   # seconds (10 min)
CIRCUIT_BREAKER_COOLDOWN  = 1800  # seconds (30 min)

cb_key = f"spot:pc:circuit_breaker:{cluster_id}"
failure_key = f"spot:pc:failures:{cluster_id}"

if self.redis.get(cb_key):
    log.warning("PlacementController circuit breaker OPEN for cluster %s", cluster_id)
    self._emit_cycle_metrics(cluster_id, circuit_breaker_tripped=1)
    return

# Count recent FAILED AgentActions dispatched by PlacementController
recent_failures = db.query(func.count(AgentAction.id)).filter(
    AgentAction.cluster_id == cluster_id,
    AgentAction.status == AgentActionStatus.FAILED,
    AgentAction.action_type == AgentActionType.EVICT_POD,
    AgentAction.updated_at > datetime.utcnow() - timedelta(seconds=CIRCUIT_BREAKER_WINDOW)
).scalar()

if recent_failures >= CIRCUIT_BREAKER_THRESHOLD:
    self.redis.setex(cb_key, CIRCUIT_BREAKER_COOLDOWN, "1")
    log.error("PlacementController circuit breaker TRIPPED for cluster %s (%d failures)",
              cluster_id, recent_failures)
    return
```

3. Add `circuit_breaker_tripped` counter to the `_emit_cycle_metrics()` payload.

**Dependencies:** None (uses existing `AgentAction` table and Redis).

**Validation:**
```bash
# Simulate 10 FAILED EVICT_POD actions in last 10 min for a test cluster
# Trigger a PlacementController cycle manually
# Redis key spot:pc:circuit_breaker:{cid} must be SET with 1800s TTL
# Subsequent cycles must log "circuit breaker OPEN" and return immediately
```

**Risk:** MEDIUM — modifies the critical inner loop of Engine B. Test on staging first.

---

### P-13 — Feature Flags for High-Risk Code Paths

**Status:** MISSING
**Batch:** 4
**UI Gap:** `ExecutionSafety.feature_flags`

**Description:** Tasks T-05 (heartbeat field alignment), T-09 (node metadata push), T-13 (HPA config push) are HIGH risk with no runtime kill switch. If the new code causes agent instability, the only recovery is a full redeploy. Add env-var feature flags so any path can be disabled instantly without deployment.

**Files to modify:**
- `backend/core/config.py` — add feature flag settings
- `backend/api/agent_routes.py` — gate T-05 new fields and T-09/T-13 batch endpoints
- `agent/heartbeat.py` — gate T-09 node metadata push
- `agent/pod_metrics_collector.py` — gate T-13 HPA config collection

**Required changes:**

1. Add to `backend/core/config.py` (or wherever `settings` is defined):

```python
# Feature flags — set to False to disable without redeployment
FEATURE_NODE_METADATA_PUSH: bool = True      # T-09 agent push
FEATURE_HPA_CONFIG_PUSH: bool = True         # T-13 agent push
FEATURE_HEARTBEAT_EXTENDED_FIELDS: bool = True  # T-05 new Redis fields
FEATURE_PLACEMENT_CONTROLLER_ENABLED: bool = True  # Engine B master switch (already exists — verify)
FEATURE_CONSOLIDATION_ANALYSIS: bool = True  # T-18 Celery task
```

2. In `agent_routes.py`, wrap the T-09 endpoint handler:

```python
@router.post("/agents/node-metadata/batch")
async def ingest_node_metadata_batch(...):
    if not settings.FEATURE_NODE_METADATA_PUSH:
        return {"status": "disabled", "message": "Feature flag FEATURE_NODE_METADATA_PUSH=False"}
    # ... existing implementation
```

3. In `agent/heartbeat.py`, wrap the node metadata send call:

```python
if settings.FEATURE_NODE_METADATA_PUSH:
    await self.send_node_metadata_batch(...)
```

4. In `agent/pod_metrics_collector.py`, wrap the HPA config collection:

```python
if settings.FEATURE_HPA_CONFIG_PUSH:
    await self.send_hpa_configs_batch(...)
```

5. In `agent_routes.py` T-05 heartbeat handler, wrap new field parsing:

```python
if settings.FEATURE_HEARTBEAT_EXTENDED_FIELDS:
    # parse and write has_pdb, current_spot_pods, etc.
    ...
else:
    # use existing 5-field payload only
    ...
```

**Dependencies:** None.

**Validation:**
```bash
# Set FEATURE_NODE_METADATA_PUSH=False
# POST to /agents/node-metadata/batch
# Must return {"status": "disabled"} not 404 or 500
# node_metadata table must remain unchanged
```

**Risk:** LOW — flags default to True so behavior is unchanged until explicitly disabled.

---

### P-14 — ExecutionController Stub Wiring

**Status:** PENDING (audit confirmed stubs exist)
**Batch:** 4
**Gap Source:** SYSTEM_EXECUTION_AUDIT.md §6: 4 stubbed methods in `execution_controller.py`

**Description:** `execution_controller.py` has 4 methods returning hardcoded `True`. These are called by `emergency_handler.py` and the emergency rebalancer. Silent success means emergency node replacement may "succeed" on paper while doing nothing.

**Files to modify:**
- `backend/services/execution_controller.py`

**Stubbed methods to implement:**

1. **`_wait_substitute_ready(instance_id, timeout_seconds)`**:
   ```python
   # Real implementation: poll AWS EC2 describe-instances until state == 'running'
   # Use existing aws_pricing_service or boto3 client pattern in codebase
   # Pattern: while elapsed < timeout_seconds: check state; sleep 5; raise on timeout
   ```

2. **`_drain_node(node_name)`**:
   ```python
   # Real implementation: create AgentAction(type=DRAIN_NODE) in DB
   # Do NOT call K8s directly — agent executes the drain
   # Return True once AgentAction is COMPLETED (poll with timeout)
   # This replaces the stub that returned True immediately
   ```

3. **`_verify_workload_health(workload_name, namespace, min_ready_replicas)`**:
   ```python
   # Real implementation: query pod_metrics table for the workload
   # Count pods with phase=Running in last 60 seconds
   # Return True if count >= min_ready_replicas
   ```

4. **`_terminate_node(instance_id)`**:
   ```python
   # Real implementation: create AgentAction(type=TERMINATE_NODE) in DB
   # Agent executes EC2 termination
   # Return True once AgentAction is COMPLETED or FAILED
   ```

**Pre-step:** Read `execution_controller.py` fully before implementing. Understand what callers pass as arguments and what they do with the return value.

**Dependencies:** `AgentAction` table (exists), `pod_metrics` table (exists, T-12 migrated).

**Validation:**
```bash
# Trigger an emergency rebalance scenario in staging
# _drain_node must create an AgentAction(DRAIN_NODE) record visible in DB
# SELECT * FROM agent_actions WHERE action_type='DRAIN_NODE' ORDER BY created_at DESC LIMIT 1;
```

**Risk:** HIGH — emergency code path. Test on isolated staging cluster with single node. One mistake here affects live emergency response.

---

### P-15 — Pool Optimization Worker Real Body

**Status:** PENDING (audit: line 69 is TODO + timestamp only)
**Batch:** 4
**Gap Source:** SYSTEM_EXECUTION_AUDIT.md §6, §8

**Description:** `optimizer_coordinator_worker.py` has `pool_optimization_worker` that records a timestamp and does nothing. This is a registered Celery task on a real beat schedule. Every execution is a silent no-op.

**Files to modify:**
- `backend/workers/tasks/optimizer_coordinator_worker.py`

**Required changes:**

1. Read the full file before implementing. Understand what `optimizer_coordinator.py` service provides.

2. Implement a minimal viable body that:
   - Queries clusters with `auto_rebalance_enabled=True`
   - For each cluster, calls `pool_ranking_service.get_ranked_pools(cluster_id)` (already exists)
   - Identifies pools with `interruption_risk_score > threshold` (read threshold from config)
   - For high-risk pools: calls `pool_rotation_service.request_rotation(cluster_id, pool_id)` if it exists
   - Logs the decision (pool ranked, rotation requested or skipped)
   - Writes a Redis key `spot:pool_optimization:last_run:{cluster_id}` with timestamp

3. If `pool_rotation_service.request_rotation()` does not exist, create a minimal version that creates an `AgentAction(type=LABEL_NODE)` to trigger Karpenter NodePool weight adjustment.

4. Do NOT implement complex ML optimization in this task — the goal is to move from "silent no-op" to "reads data, makes logged decision, does not crash."

**Pre-step:** Read `pool_ranking_service.py` interface and `pool_rotation_service.py` interface fully before writing.

**Dependencies:** `pool_ranking_service.py` (existing), `pool_rotation_service.py` (existing).

**Validation:**
```bash
celery call workers.tasks.optimizer_coordinator_worker.pool_optimization_worker
# Must not crash
# redis-cli GET spot:pool_optimization:last_run:{cid} — must be set
# Logs must show ranked pools, not just "timestamp recorded"
```

**Risk:** MEDIUM — affects cluster NodePool weighting. Start with logging-only mode: implement full logic but gate actual rotation behind a new feature flag `FEATURE_POOL_OPTIMIZATION_ACTIVE=False` by default.

---

### P-16 — Pricing Engine: Spot vs OD Differentiation + Region Awareness

**Status:** MISSING
**Batch:** 4
**UI Gap:** `PricingEngine.instance_catalog`, `PricingEngine.spot_vs_od`, `PricingEngine.region_awareness`

**Description:** `consolidation_analysis_task.py` (T-18) and savings calculations in `optimize_routes.py` (T-08) reference `instance_catalog` table and `spot:pricing:instance:{type}:{region}` Redis keys, but the audit confirms `aws_pricing_service.py` and `pricing_worker.py` already exist. The gap is that the new optimize endpoints do not use these existing services — they either use a null fallback or hardcode prices.

**Files to modify:**
- `backend/workers/tasks/consolidation_analysis_task.py` — replace stub pricing with real service call
- `backend/api/optimize_routes.py` (T-08 profiling summary) — replace null savings with real computation

**Required changes:**

1. **Pre-step:** Read `backend/services/aws_pricing_service.py` to find the exact method signature for getting OD price and Spot price for an instance type in a region. Likely: `get_on_demand_price(instance_type, region)` and `get_spot_price(instance_type, region)`. Confirm before writing.

2. In `consolidation_analysis_task.py`, replace:
   ```python
   # Current: fallback to instance_catalog or return null
   ```
   With:
   ```python
   from backend.services.aws_pricing_service import AWSPricingService
   pricing = AWSPricingService()
   od_price = pricing.get_on_demand_price(instance_type, region)
   spot_price = pricing.get_spot_price(instance_type, region)
   savings_per_node = (od_price - spot_price) * 730
   ```

3. In `T-08` profiling summary endpoint, compute actual savings differential:
   ```python
   # Replace: return estimated_monthly_saving_usd from PlacementPolicyRecord as-is
   # Add: spot_saving_pct = (od_price - spot_price) / od_price * 100 per workload
   # Return both estimated_monthly_saving_usd AND spot_saving_pct
   ```

4. Region must come from `cluster.region` (confirm field name in `Cluster` model).

5. If `aws_pricing_service.py` does NOT have `get_spot_price()`, check `pricing_worker.py` for the Redis key write pattern and read directly from Redis using `safe_get_json(redis_client, f"spot:pricing:instance:{instance_type}:{region}")`.

**Dependencies:** P-05 (safe Redis reads for pricing key fallback).

**Validation:**
```sql
-- After pricing_worker runs:
SELECT * FROM instance_catalog WHERE instance_type = 't3.large' LIMIT 1;
-- OR
redis-cli GET "spot:pricing:instance:t3.large:us-east-1"
-- Must have a numeric value, not null
```

**Risk:** LOW — replaces null/fallback with real data. No execution logic changed.

---

### P-17 — Staleness Indicator in All Optimize Endpoints

**Status:** MISSING
**Batch:** 4
**UI Gap:** `DataFreshness.stale_exclusion`, `StalenessUI.indicator`, `StalenessUI.warning_logic`

**Description:** After P-01 adds the `compute_freshness()` utility, this task applies it to every remaining endpoint that doesn't yet have it, and adds the `stale_nodes_excluded` / `stale_workloads_excluded` count to aggregate responses so the UI can show a "some data may be outdated" warning banner.

**Files to modify:**
- `backend/api/optimize_routes.py` — all remaining endpoints not covered by P-01

**Required changes:**

1. Apply `compute_freshness()` to these endpoints not covered in P-01:
   - `GET /workloads/placement/summary` — use `MAX(workload_classifications.classified_at)`
   - `GET /workloads/{id}/placement-detail` — use workload's `classified_at`
   - `GET /workloads/{id}/pods` (T-15) — use `MAX(pod_metrics.timestamp)` for the workload
   - `GET /nodes/{node_name}/bin-packing-detail` (T-21) — use `MAX(pod_metrics.timestamp)` for the node

2. Add `stale_items_excluded: int` to aggregate responses (bin-packing list, placement list, scaling list) — count of items dropped by `stale_node_filter()` or equivalent.

3. Add to all 10 endpoints the standard freshness block at the top level of the response JSON:
   ```json
   {
     "data_updated_at": "2026-04-27T09:41:00Z",
     "data_age_seconds": 42.0,
     "is_stale": false,
     "stale_items_excluded": 0,
     ...rest of response
   }
   ```

**Dependencies:** P-01 (compute_freshness utility), P-02 (api_response wrapper).

**Validation:**
```bash
# Set a workload's classified_at to 10 minutes ago in test DB
curl "/api/v1/optimize/workloads/placement/summary?cluster_id={cid}"
# is_stale must be true, data_age_seconds must be ~600
```

**Risk:** LOW — additive fields only.

---

### P-18 — Per-Batch Regression Validation Hook

**Status:** MISSING
**Batch:** 4
**UI Gap:** `DefinitionOfDone.regression_check`

**Description:** The prior plan's Final Validation Checklist had one regression check: verify `/api/v1/pod-metrics/recommendations` still works. This plan adds 26 tasks modifying shared files. Need a lightweight regression test that runs after every batch.

**Files to create:**
- `scripts/regression_check.sh` (NEW)

**Required changes:**

1. Create `scripts/regression_check.sh`:

```bash
#!/bin/bash
# Run after every batch. Fails if any critical endpoint regresses.
set -e
BASE=${API_BASE:-http://localhost:8000}
CID=${TEST_CLUSTER_ID:-test-cluster}

echo "=== Regression Check ==="

# Existing endpoints (must not break)
curl -sf "$BASE/api/v1/pod-metrics/recommendations?cluster_id=$CID" > /dev/null && echo "PASS: right-sizing recommendations"
curl -sf "$BASE/api/v1/workload-classification/clusters/$CID/workloads" > /dev/null && echo "PASS: workload classifications"
curl -sf "$BASE/api/v1/clusters/$CID/placement-policies" > /dev/null && echo "PASS: placement policies"

# New optimize endpoints (from T-01→T-24, must remain functional)
curl -sf "$BASE/api/v1/optimize/workloads/$CID/gates?cluster_id=$CID" > /dev/null && echo "PASS: gates"
curl -sf "$BASE/api/v1/optimize/workloads/placement/summary?cluster_id=$CID" > /dev/null && echo "PASS: placement summary"
curl -sf "$BASE/api/v1/optimize/nodes/bin-packing?cluster_id=$CID" > /dev/null && echo "PASS: bin packing"
curl -sf "$BASE/api/v1/optimize/workloads/scaling?cluster_id=$CID" > /dev/null && echo "PASS: scaling"

echo "=== All regression checks passed ==="
```

2. Add to memory.md procedure: "After each batch, run `scripts/regression_check.sh` and append results to memory.md before starting next batch."

3. If any check fails, mark memory.md with `REGRESSION_DETECTED: <endpoint> after <batch>` and do not proceed until resolved.

**Dependencies:** None (shell script, runs against live dev/staging server).

**Validation:** Script runs to completion with exit code 0 on a clean environment.

**Risk:** LOW — read-only HTTP checks, no mutations.

---

### P-19 — System Health Metrics Endpoint

**Status:** MISSING
**Batch:** 5
**UI Gap:** `Observability.system_metrics`

**Description:** No endpoint exposes system-wide health of the optimization pipeline: decision accuracy (how many evictions successfully landed on Spot), drift resolution rate, PlacementController cycle success rate. This data exists in the DB and Redis — it just needs to be aggregated.

**Files to modify:**
- `backend/api/optimize_routes.py`

**Route:** `GET /api/v1/optimize/system/health?cluster_id=`

**Required changes:**

1. Query:

```python
# Eviction success rate (last 24h)
total_evictions = db.query(func.count(AgentAction.id)).filter(
    AgentAction.cluster_id == cluster_id,
    AgentAction.action_type == AgentActionType.EVICT_POD,
    AgentAction.created_at > datetime.utcnow() - timedelta(hours=24)
).scalar()

successful_evictions = db.query(func.count(AgentAction.id)).filter(
    AgentAction.cluster_id == cluster_id,
    AgentAction.action_type == AgentActionType.EVICT_POD,
    AgentAction.status == AgentActionStatus.COMPLETED,
    AgentAction.created_at > datetime.utcnow() - timedelta(hours=24)
).scalar()

eviction_success_rate = (successful_evictions / total_evictions * 100) if total_evictions > 0 else None
```

2. Read PC cycle metrics from Redis `spot:placement_controller:metrics:{cluster_id}`:
   - Extract `cycle_count`, `evictions_dispatched`, `evictions_skipped_capacity`, `circuit_breaker_tripped`

3. Compute `drift_resolution_rate`:
   - From T-06 placement summary: `at_target_count / total_confirmed * 100`

4. Return:
```json
{
  "eviction_success_rate_24h": 94.2,
  "total_evictions_24h": 48,
  "drift_resolution_rate": 87.5,
  "at_target_count": 14,
  "drifting_count": 2,
  "pc_cycle_count": 288,
  "circuit_breaker_trips_24h": 0,
  "data_updated_at": "...",
  "is_stale": false
}
```

**Dependencies:** P-01 (freshness), P-02 (response contract), P-09 (placement state), P-12 (circuit breaker emits metric).

**Validation:**
```bash
curl "/api/v1/optimize/system/health?cluster_id={cid}"
# eviction_success_rate_24h must match manual SQL count
# drift_resolution_rate must match T-06 at_target_count / total_confirmed
```

**Risk:** LOW — read-only aggregation.

---

### P-20 — Centralized Failure Log

**Status:** MISSING
**Batch:** 5
**UI Gap:** `Observability.error_tracking`

**Description:** Failed agent batch pushes, failed Celery task runs, and failed DB upserts are currently logged only to Celery/uvicorn stdout. `observability_logger.py` exists but is not wired to the new tasks and endpoints added in T-01→T-24. Failures are invisible unless someone reads raw logs.

**Files to modify:**
- `backend/workers/tasks/workload_cv_task.py`
- `backend/workers/tasks/consolidation_analysis_task.py`
- `backend/workers/tasks/hpa_recommendation_task.py`
- `backend/api/agent_routes.py` — batch endpoints

**Required changes:**

1. **Pre-step:** Read `backend/services/observability_logger.py` to find the method signature for structured error logging. Likely: `log_error(event_type, cluster_id, error, context)` or similar.

2. In each Celery task except clause, call `observability_logger.log_error()` with:
   - `event_type`: `"celery_task_failure"`
   - `task_name`: e.g. `"workload_cv_task"`
   - `cluster_id`: current cluster
   - `error`: str(exception)
   - `context`: dict of relevant state (workload_id, step, etc.)

3. In each agent batch endpoint, on DB write failure (after P-06 retries exhausted), log:
   - `event_type`: `"agent_batch_failure"`
   - `endpoint`: route path
   - `cluster_id`: from request
   - `record_count`: number of records that failed

4. Write a Redis counter per error type per cluster (TTL 86400s) to enable the P-19 health endpoint to surface error counts:
   ```python
   redis_client.incr(f"spot:errors:{event_type}:{cluster_id}")
   redis_client.expire(f"spot:errors:{event_type}:{cluster_id}", 86400)
   ```

**Dependencies:** P-06 (retry logic must run before logging permanent failure).

**Validation:**
```bash
# Force a workload_cv_task failure by dropping workload_classifications table temporarily
celery call workers.tasks.workload_cv_task.compute_workload_cv_task
# redis-cli GET spot:errors:celery_task_failure:{cid} — must increment
```

**Risk:** LOW — additive logging. Never affects execution path.

---

### P-21 — Redis Race Condition Guards for New Write Paths

**Status:** MISSING
**Batch:** 5
**UI Gap:** `Concurrency.redis_race`

**Description:** T-01 (`lpush`/`ltrim` to workload log), T-04 (per-workload HSET to metrics), and T-06 (placement summary SETEX) can be written simultaneously by Celery workers and agent heartbeats. Redis is single-threaded for individual commands but not for multi-command sequences — `lpush` + `ltrim` + `expire` is not atomic.

**Files to modify:**
- `backend/services/placement_controller_service.py` — T-01 decision log emit
- `backend/api/optimize_routes.py` — T-06 placement summary cache write

**Required changes:**

1. In `_emit_decision_log()` (T-01), replace the 3-command sequence with a Redis pipeline:

```python
# Current (non-atomic):
self.redis.lpush(key, record)
self.redis.ltrim(key, 0, 9)
self.redis.expire(key, 3600)

# Replace with pipeline (atomic on Redis server):
pipe = self.redis.pipeline()
pipe.lpush(key, record)
pipe.ltrim(key, 0, 9)
pipe.expire(key, REDIS_TTL["workload_log"])
pipe.execute()
```

2. In `GET /workloads/placement/summary` cache write (T-06), use a Lua script or pipeline to prevent two Celery workers writing simultaneously:

```python
# Use SET with NX (only write if key doesn't exist — prevents cache stampede)
# But we DO want to refresh the cache, so use SET with EX instead:
pipe = redis_client.pipeline()
pipe.set(cache_key, json.dumps(result), ex=REDIS_TTL["placement_summary"])
pipe.execute()
# SET is already atomic; pipeline here prevents partial writes in multi-pipeline contexts
```

3. In `_emit_cycle_metrics()` (T-04), the HSET + EXPIRE sequence is already two commands. Wrap in pipeline:

```python
pipe = self.redis.pipeline()
pipe.hset(wl_key, mapping={...})
pipe.expire(wl_key, REDIS_TTL["pc_workload_metrics"])
pipe.execute()
```

**Dependencies:** P-03 (TTL registry must be in place for `REDIS_TTL` references).

**Validation:**
```bash
# Run 10 concurrent agents writing to the same workload log key
# redis-cli LLEN spot:pc:workload_log:{cid}:{wid}
# Must be <= 10 (ltrim enforces this); never > 10 even under concurrency
```

**Risk:** LOW — pipelines are additive changes, fully backward compatible.

---

### P-22 — DB Retention Policies for New Tables

**Status:** MISSING
**Batch:** 5
**UI Gap:** `Cleanup.db_retention`

**Description:** T-09 (`node_metadata` upsert), T-11 (`karpenter_node_claims` upsert), T-12 (`pod_metrics` append-only) all have rows that can grow unbounded. T-13 added `hpa_status_snapshots` cleanup to `pod_metrics_cleanup.py` (30-day retention), but `karpenter_node_claims` and the audit found `pod_metrics_cleanup.py` does not yet clean `node_metadata` stale rows for nodes that no longer exist.

**Files to modify:**
- `backend/workers/tasks/pod_metrics_cleanup.py`

**Required changes:**

1. Read `pod_metrics_cleanup.py` fully. Add these cleanup rules:

```python
# karpenter_node_claims: delete rows for nodes that are no longer in node_metadata
# (node was terminated, Karpenter removed it)
db.execute(text("""
    DELETE FROM karpenter_node_claims knc
    WHERE NOT EXISTS (
        SELECT 1 FROM node_metadata nm
        WHERE nm.cluster_id = knc.cluster_id
          AND nm.node_name = knc.node_name
    )
    AND knc.updated_at < NOW() - INTERVAL '2 hours'
"""))

# node_metadata: delete rows for nodes not seen in last 10 minutes
# (agent stopped reporting this node — it was terminated)
db.execute(text("""
    DELETE FROM node_metadata
    WHERE updated_at < NOW() - INTERVAL '10 minutes'
"""))
```

2. **IMPORTANT:** The node_metadata 10-minute window must be larger than the agent heartbeat interval + one missed heartbeat. If the agent heartbeats every 60s, use 3 minutes minimum. Confirm agent heartbeat interval from `agent/main.py` before setting the threshold.

3. Add a log line after each cleanup: `log.info("Cleanup: deleted %d stale node_metadata rows", deleted_count)`.

**Dependencies:** T-09, T-11 (tables must exist).

**Validation:**
```sql
-- After cleanup task runs, confirm a terminated node's row is removed
-- Insert a row with updated_at = NOW() - INTERVAL '20 minutes'
INSERT INTO node_metadata (cluster_id, node_name, updated_at, ...) VALUES ('test', 'dead-node', NOW() - INTERVAL '20 minutes', ...);
-- Run cleanup task
-- SELECT COUNT(*) FROM node_metadata WHERE node_name='dead-node' — must be 0
```

**Risk:** MEDIUM — deletes real data. Run on staging first with logging only (`--dry-run` mode) before enabling actual deletes.

---

### P-23 — Rate Limiting on Heavy Optimize Endpoints

**Status:** MISSING
**Batch:** 5
**UI Gap:** `Performance.api_rate_limit`, `Performance.query_guardrails`

**Description:** `GET /nodes/bin-packing` and `GET /workloads/placement/summary` both trigger expensive SQL JOINs on `pod_metrics`. The 60s Redis cache mitigates repeat calls, but a single thundering herd (UI refresh by 50 users at once after a Redis flush) can overwhelm the DB. Add simple per-cluster rate limiting.

**Files to modify:**
- `backend/api/optimize_routes.py`
- `backend/utils/rate_limit.py` (NEW)

**Required changes:**

1. Create `backend/utils/rate_limit.py`:

```python
import redis as redis_lib
from fastapi import HTTPException

def check_rate_limit(redis_client, key: str, max_calls: int, window_seconds: int) -> None:
    """
    Raises HTTP 429 if key has been called more than max_calls times in window_seconds.
    Uses Redis INCR + EXPIRE — atomic enough for rate limiting (not financial transactions).
    """
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, window_seconds)
    if count > max_calls:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {max_calls} requests per {window_seconds}s."
        )
```

2. In `GET /nodes/bin-packing` (T-14), add at the start of the handler (after validation):

```python
check_rate_limit(
    redis_client,
    key=f"spot:ratelimit:bin_packing:{cluster_id}",
    max_calls=10,   # 10 requests per cluster
    window_seconds=60
)
```

3. Apply the same rate limiting to:
   - `GET /workloads/placement/summary` — 20 req/60s per cluster
   - `GET /workloads/scaling` — 20 req/60s per cluster

4. **Add query time guardrail** to all `pod_metrics` JOINs: add `AND timestamp > NOW() - INTERVAL '2 hours'` if not already present. This limits the table scan window even if the 1-hour filter in T-14 was changed by mistake.

**Dependencies:** None.

**Validation:**
```bash
# Call /nodes/bin-packing 11 times in quick succession for same cluster_id
for i in {1..11}; do curl -o /dev/null -sw "%{http_code}\n" "/api/v1/optimize/nodes/bin-packing?cluster_id={cid}"; done
# First 10 must return 200, 11th must return 429
```

**Risk:** LOW — 429 is explicit and documented. Frontend must handle 429 with retry-after.

---

### P-24 — Agent Backward Compatibility Layer

**Status:** MISSING
**Batch:** 5
**UI Gap:** `AgentCompatibility.version_mismatch`, `AgentCompatibility.backward_support`

**Description:** T-09, T-12, T-13 added new fields to agent payloads. If an old agent version (pre-T-09) sends a heartbeat without `node_metadata`, the backend currently processes the partial payload silently. If it sends a heartbeat WITH new fields that have a schema mismatch, Pydantic raises a validation error that rejects the entire heartbeat.

**Files to modify:**
- `backend/api/agent_routes.py` — heartbeat and batch endpoints
- `backend/schemas/` — relevant request schemas

**Required changes:**

1. Make all new agent push fields `Optional` with defaults in the Pydantic request schemas:

```python
# In NodeMetadataBatchRequest schema
class NodeMetadataRecord(BaseModel):
    node_name: str
    az: Optional[str] = None           # Old agents don't send this
    capacity_type: Optional[str] = None  # Old agents don't send this
    instance_type: Optional[str] = None
    nodepool_name: Optional[str] = None
    allocatable_cpu_millicores: Optional[int] = None
    allocatable_memory_bytes: Optional[int] = None
    is_ready: bool = True
    do_not_disrupt: bool = False
```

2. In each batch endpoint handler, skip records with missing required fields and log a warning (do not reject the entire batch):

```python
valid_records = []
skipped = 0
for record in batch.records:
    if record.node_name is None or record.cluster_id is None:
        skipped += 1
        continue
    valid_records.append(record)
if skipped:
    log.warning("Skipped %d records in node-metadata batch due to missing required fields", skipped)
```

3. Add `agent_version: Optional[str] = None` to the heartbeat schema. If agent version is older than a configurable minimum (`settings.AGENT_MIN_VERSION`), log a deprecation warning but do NOT reject the heartbeat.

**Dependencies:** None.

**Validation:**
```bash
# POST to /agents/node-metadata/batch with records missing 'az' field
curl -X POST "/api/v1/agents/node-metadata/batch" -d '{"records": [{"node_name": "test", "is_ready": true}]}'
# Must return 200 (not 422) — old agent payload accepted
# node_metadata row for 'test' must be inserted with az=null
```

**Risk:** LOW — makes schemas more permissive. No existing code breaks.

---

### P-25 — Definition-of-Done Validation Runner

**Status:** MISSING
**Batch:** 5
**UI Gap:** `DefinitionOfDone.task_completion`

**Description:** The prior plan had a Final Validation Checklist in markdown. This plan adds 26 tasks — the checklist needs to be machine-runnable, not manual. Create a script that validates every P-task's completion criteria.

**Files to create:**
- `scripts/validate_plan_phase3.py` (NEW)

**Required changes:**

Create `scripts/validate_plan_phase3.py` that runs each validation from this plan's tasks:

```python
#!/usr/bin/env python3
"""
Phase 3 plan completion validator.
Run: python scripts/validate_plan_phase3.py --cluster-id 
Each check prints PASS / FAIL / SKIP.
"""
import sys, requests, redis, psycopg2

BASE_URL = "http://localhost:8000/api/v1"
CLUSTER_ID = sys.argv[sys.argv.index("--cluster-id") + 1] if "--cluster-id" in sys.argv else "test"

checks = [
    # P-01: Freshness fields present
    ("P-01 freshness fields", lambda: "data_age_seconds" in requests.get(f"{BASE_URL}/optimize/nodes/bin-packing?cluster_id={CLUSTER_ID}").json()),
    # P-02: data_ready field present
    ("P-02 data_ready field", lambda: "data_ready" in requests.get(f"{BASE_URL}/optimize/nodes/bin-packing?cluster_id={CLUSTER_ID}").json()),
    # P-04: invalid cluster_id returns 404
    ("P-04 invalid cluster 404", lambda: requests.get(f"{BASE_URL}/optimize/nodes/bin-packing?cluster_id=INVALID_XYZ").status_code == 404),
    # P-09: placement_status is state-machine value
    ("P-09 placement state values", lambda: requests.get(f"{BASE_URL}/optimize/workloads/placement/summary?cluster_id={CLUSTER_ID}").json().get("workloads", [{}])[0].get("placement_status") in (None, "AT_TARGET", "DRIFTING", "CONVERGING", "UNKNOWN")),
    # P-19: system health endpoint exists
    ("P-19 system health endpoint", lambda: requests.get(f"{BASE_URL}/optimize/system/health?cluster_id={CLUSTER_ID}").status_code in (200, 202)),
    # P-23: rate limit enforced
    ("P-23 rate limit 429", lambda: any(
        requests.get(f"{BASE_URL}/optimize/nodes/bin-packing?cluster_id={CLUSTER_ID}").status_code == 429
        for _ in range(15)
    )),
    # Regression checks
    ("REG pod-metrics/recommendations", lambda: requests.get(f"{BASE_URL}/pod-metrics/recommendations?cluster_id={CLUSTER_ID}").status_code == 200),
    ("REG workload-classifications", lambda: requests.get(f"{BASE_URL}/workload-classification/clusters/{CLUSTER_ID}/workloads").status_code == 200),
    ("REG placement-policies", lambda: requests.get(f"{BASE_URL}/clusters/{CLUSTER_ID}/placement-policies").status_code == 200),
]

failures = 0
for name, check in checks:
    try:
        result = check()
        print(f"{'PASS' if result else 'FAIL'}: {name}")
        if not result:
            failures += 1
    except Exception as e:
        print(f"ERROR: {name} — {e}")
        failures += 1

print(f"\n{len(checks) - failures}/{len(checks)} checks passed")
sys.exit(0 if failures == 0 else 1)
```

**Dependencies:** All P-tasks must be complete before running.

**Validation:** Script exits 0 on clean environment.

**Risk:** None — read-only validation script.

---

### P-26 — Concurrency: Redis INCR/DECR for Aggregate Counters

**Status:** MISSING
**Batch:** 5
**UI Gap:** `Concurrency.redis_race`

**Description:** `rebalance:active_count:{cluster_id}` is already using INCR/DECR correctly (existing code). But the `scale_events_24h` counter in T-17 is recomputed from `hpa_status_snapshots` at query time — not stored atomically. Under concurrent writes, the snapshot table can have race conditions where two Celery workers write conflicting snapshots for the same workload at the same timestamp.

**Files to modify:**
- `backend/api/agent_routes.py` — `POST /agents/hpa-configs/batch` endpoint

**Required changes:**

1. In the `POST /agents/hpa-configs/batch` handler, when inserting to `hpa_status_snapshots`, use `INSERT ... ON CONFLICT DO NOTHING` for the `(cluster_id, workload_name, snapshot_at)` combination to prevent duplicate snapshot rows from concurrent agent heartbeats:

```sql
INSERT INTO hpa_status_snapshots (cluster_id, namespace, workload_name, desired_replicas, current_replicas, cpu_utilization_pct, snapshot_at)
VALUES (:cid, :ns, :wn, :dr, :cr, :cpu, :ts)
ON CONFLICT (cluster_id, workload_name, snapshot_at) DO NOTHING
```

2. This requires a unique constraint on `(cluster_id, workload_name, snapshot_at)` in the Alembic migration. Check `migrations/versions/20260427_hpa_tables.py` — add it if missing (similar to P-08).

3. For `hpa_configs` upsert (already ON CONFLICT DO UPDATE), verify the upsert correctly updates `updated_at = NOW()` so freshness tracking works.

**Dependencies:** P-08 (constraint audit), T-13 (tables exist).

**Validation:**
```bash
# Send identical hpa-configs batch twice in rapid succession
# SELECT COUNT(*) FROM hpa_status_snapshots WHERE workload_name='test' AND snapshot_at=NOW()::timestamp(0)
# Must return 1, not 2
```

**Risk:** LOW — ON CONFLICT DO NOTHING is safe and additive.

---

## Explicitly Out of Scope

- **WorkloadMigration page full workflow** — dedicated engine cycle required
- **RPS / request-rate metrics** — Prometheus integration required; agent cannot collect
- **Shadow mode auto-graduation** — manual Redis DEL is correct; automation deferred
- **WIE + WorkloadInspector unification** — deprecation requires separate release cycle
- **Pool reputation / EMA changes** — existing services work correctly; no gap
- **Engine A (auto_rebalancer) changes** — already production-grade 623KB state machine; no new gaps identified

---

## Known Risks

1. **P-09 Workload placement_status value change (MEDIUM):** Changing `placement_status` from raw action name to state machine value (`AT_TARGET`/`DRIFTING`/`CONVERGING`) is a breaking API change for any frontend code reading the old values. Coordinate with frontend before deploying P-09. Consider a `placement_state` field (new name) alongside the old `placement_status` field during a 1-sprint transition window.

2. **P-14 ExecutionController stubs (HIGH):** These are emergency code paths. A regression here causes emergency node replacement to silently "succeed" while doing nothing. Deploy P-14 changes to a single staging cluster with a live Spot interruption simulation before production.

3. **P-22 node_metadata cleanup window (HIGH):** If the cleanup interval (10 min) is shorter than the agent restart time after a crash, nodes will be deleted and re-inserted constantly. Confirm agent restart time from `agent/main.py` before setting the threshold.

4. **P-12 Circuit breaker false positives (MEDIUM):** If `CIRCUIT_BREAKER_THRESHOLD=10` is too low for high-activity clusters, the breaker may trip during normal operations. Set `CIRCUIT_BREAKER_THRESHOLD` via env var so it can be tuned per cluster without redeploy.

5. **P-15 Pool optimization (MEDIUM):** `pool_optimization_worker` has been a no-op for the entire lifetime of the system. Activating it with feature flag `FEATURE_POOL_OPTIMIZATION_ACTIVE=False` by default is safe. But the first activation on a real cluster must be monitored carefully — it will trigger NodePool weight changes that feed back into Karpenter provisioning decisions.

---

## Conflict Resolution Summary

| Conflict | Resolution |
|---|---|
| `placement_status` value (raw action vs state machine) | P-09 introduces state machine values. Add `placement_state` (new field) alongside old `placement_status` for one sprint transition. |
| `aws_pricing_service.py` interface unknown | P-16 requires reading the file first to find exact method names before writing any call |
| `circuit_breaker.py` vs new `circuit_breaker_utils.py` | P-12: use existing service directly if interface matches; create thin adapter only if it doesn't |
| `observability_logger.py` interface unknown | P-20 requires reading the file first to find exact method signature |
| `node_metadata` cleanup interval vs agent restart time | P-22: confirm agent heartbeat interval from `agent/main.py` before choosing 10-min threshold |
| ON CONFLICT constraint may already exist | P-08 and P-26: verify before adding — duplicate constraint creation fails migrations |

---

## Execution Order (Strict)

```
BATCH 1 — Foundation utilities (must exist before all other batches):
  1.  P-01  Data freshness utility + stale node filter
  2.  P-02  Standardized API response contract + null_safe()
  3.  P-03  Unified Redis TTL registry (refactor only)
  4.  P-04  Input validation + cluster access guard

BATCH 2 — Data layer hardening:
  5.  P-05  Redis read safety wrappers (replace all bare Redis reads)
  6.  P-06  Retry decorator for DB/Redis writes
  7.  P-07  Partial failure handler for multi-source endpoints
  8.  P-08  Upsert conflict constraint audit + fix

BATCH 3 — State machines (P-09 before P-10 before P-11):
  9.  P-09  Workload placement state machine (creates state_machines.py)
  10. P-10  Node lifecycle states (extends state_machines.py)
  11. P-11  Pod lifecycle classification (extends state_machines.py)

BATCH 4 — Engine hardening:
  12. P-12  PlacementController circuit breaker
  13. P-13  Feature flags for risky code paths
  14. P-14  ExecutionController stub wiring
  15. P-15  Pool optimization worker real body
  16. P-16  Pricing engine: Spot vs OD + region
  17. P-17  Staleness indicator in all endpoints (depends on P-01, P-02)
  18. P-18  Per-batch regression validation script

BATCH 5 — Observability, cleanup, concurrency, agent compat:
  19. P-19  System health metrics endpoint (depends on P-09, P-12)
  20. P-20  Centralized failure log (depends on P-06)
  21. P-21  Redis pipeline guards for race conditions (depends on P-03)
  22. P-22  DB retention policy for new tables
  23. P-23  Rate limiting on heavy endpoints
  24. P-24  Agent backward compatibility layer
  25. P-25  Definition-of-done validation runner
  26. P-26  HPA snapshot upsert concurrency fix (depends on P-08)
```

---

## Final Validation Checklist

Before marking this plan complete, every item must PASS:

**Batch 1 (Foundation):**
- [ ] All `optimize_routes.py` responses include `data_updated_at`, `data_age_seconds`, `is_stale` fields (P-01)
- [ ] All responses include `data_ready`, `data_ready_reason` fields (P-02)
- [ ] All `redis.expire()` calls use `REDIS_TTL["..."]` from `redis_keys.py` (P-03)
- [ ] `curl "/api/v1/optimize/nodes/bin-packing?cluster_id=INVALID"` returns 404 (P-04)
- [ ] `curl "/api/v1/optimize/nodes/bin-packing?cluster_id=../../etc"` returns 422 (P-04)

**Batch 2 (Data layer):**
- [ ] `redis-cli FLUSHDB` → all optimize endpoints return 200 with `data_ready: false`, not 500 (P-05)
- [ ] Simulated DB failure → batch endpoint returns 503 not 500 after retries (P-06)
- [ ] Dropped `hpa_configs` table → `/workloads/scaling` returns 200 with `data_ready_reason: "hpa_data_pending"` (P-07)
- [ ] `SELECT COUNT(*) FROM node_metadata WHERE cluster_id='test' AND node_name='test-node'` = 1 after double-insert (P-08)

**Batch 3 (State machines):**
- [ ] `placement_status` values in `/placement/summary` are only `AT_TARGET`, `DRIFTING`, `CONVERGING`, or `UNKNOWN` (P-09)
- [ ] Node with pending `DRAIN_NODE` action shows `lifecycle_state: TERMINATING` in `/nodes/bin-packing` (P-10)
- [ ] Pod with cpu < 10m shows `lifecycle_class: IDLE` in `/workloads/{id}/pods` (P-11)

**Batch 4 (Engine hardening):**
- [ ] After 10 `EVICT_POD` failures: `redis-cli GET spot:pc:circuit_breaker:{cid}` must be SET (P-12)
- [ ] `FEATURE_NODE_METADATA_PUSH=False` → POST to `/agents/node-metadata/batch` returns `{"status": "disabled"}` (P-13)
- [ ] `_drain_node()` creates `AgentAction(DRAIN_NODE)` record in DB (P-14)
- [ ] `celery call pool_optimization_worker` → `redis-cli GET spot:pool_optimization:last_run:{cid}` is SET (P-15)
- [ ] `/workloads/profiling/summary` returns non-null `spot_saving_pct` per workload (P-16)
- [ ] All 10 optimize endpoints return `is_stale: true` when data is older than 120s (P-17)
- [ ] `scripts/regression_check.sh` exits 0 (P-18)

**Batch 5 (Observability):**
- [ ] `GET /api/v1/optimize/system/health?cluster_id={cid}` returns `eviction_success_rate_24h` (P-19)
- [ ] Forced Celery task failure → `redis-cli GET spot:errors:celery_task_failure:{cid}` increments (P-20)
- [ ] 10 concurrent writes to workload log → `redis-cli LLEN spot:pc:workload_log:{cid}:{wid}` ≤ 10 (P-21)
- [ ] Terminated node's `node_metadata` row deleted after cleanup task runs (P-22)
- [ ] 11 rapid requests to `/nodes/bin-packing` → 11th returns 429 (P-23)
- [ ] Old agent payload missing `az` field → `/agents/node-metadata/batch` returns 200, row inserted with `az=null` (P-24)
- [ ] `python scripts/validate_plan_phase3.py --cluster-id {cid}` exits 0 (P-25)
- [ ] Duplicate HPA snapshot insert → `SELECT COUNT(*)` = 1 not 2 (P-26)

**Regression (must pass after every batch):**
- [ ] `GET /api/v1/pod-metrics/recommendations` returns 200
- [ ] `GET /api/v1/workload-classification/clusters/{cid}/workloads` returns 200
- [ ] `GET /api/v1/clusters/{cid}/placement-policies` returns 200
- [ ] `GET /api/v1/optimize/workloads/{wid}/gates?cluster_id={cid}` returns 6 gate objects
- [ ] `GET /api/v1/optimize/workloads/placement/summary?cluster_id={cid}` returns 200