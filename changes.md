# Spot Optimizer Platform — Complete Implementation Plan

> **Version**: 1.0  
> **Date**: 2026-03-08  
> **Scope**: Full architecture, logic, and implementation details for all core components except ML enhancements (existing 1‑hour ML model remains unchanged).  
> **Key Features**: Data ingestion, global pool caching, decision engine, execution engine (13‑step), emergency service, circuit breaker, recovery monitor, agent architecture, Karpenter integration, removal of volume‑aware rightsizing.  
> **No ML extensions**: Pool lifetime tracking, extended feature vector, and model retraining hooks are **not** included.

---

## Table of Contents

1. [Global Constants & Settings](#1-global-constants--settings)
2. [Data Ingestion Enhancements](#2-data-ingestion-enhancements)
3. [Caching & Redis Key Management](#3-caching--redis-key-management)
4. [Global Pool Caching & Ranking](#4-global-pool-caching--ranking)
5. [Decision Engine](#5-decision-engine)
6. [Execution Engine](#6-execution-engine)
7. [Emergency Service](#7-emergency-service)
8. [Circuit Breaker](#8-circuit-breaker)
9. [Recovery Monitor](#9-recovery-monitor)
10. [Agent Architecture](#10-agent-architecture)
11. [Karpenter Integration](#11-karpenter-integration)
12. [Database Migrations](#12-database-migrations)
13. [Celery Beat Updates](#13-celery-beat-updates)
14. [Frontend Minimal Updates](#14-frontend-minimal-updates)
15. [File Change Summary](#15-file-change-summary)
16. [Implementation Roadmap](#16-implementation-roadmap)

---

## 1. Global Constants & Settings

**File**: `backend/core/config.py` (MODIFY)

Add the following constants block below the existing `Settings` class. These values are used across all services.

```python
# ── Spot Optimizer Global Constants ────────────────────────────────────────
GLOBAL_CACHE_SIZE: int = 500               # max pools per region stored in Redis
GLOBAL_CACHE_TTL: int = 3600               # seconds — 1 hour
CAPACITY_SCORE_DIVISOR: int = 4            # memory_gb / 4 in capacity score
RISK_TIER_THRESHOLDS: list = [0.05, 0.10, 0.15, 0.20]   # tier1..tier4 ceilings
MAX_FAMILY_SHARE: float = 0.40             # 40% max per instance family
PRICE_SPIKE_FACTOR: float = 1.60           # 1.6× 1‑hour average → price shock
LAUNCH_FAILURE_RATIO_THRESHOLD: float = 0.30  # 30% failure ratio → temporary blacklist
REGION_MARKET_HEALTH_TIER1_THRESHOLD: int = 100  # alert if tier1 pools < 100
GLOBAL_POOL_LOCK_TTL: int = 120            # seconds — lock TTL for cache rebuild
SPOT_PRICE_STALENESS_WARN_SECS: int = 1800 # 30 min → low_confidence flag
SPOT_ADVISOR_STALENESS_DAYS: int = 45      # alert if scrape > 45 days old
DEFAULT_INTERRUPTION_RATE_PCT: float = 15.0  # fallback when pool has no data
CREDENTIAL_CACHE_TTL_BUFFER_SECS: int = 300  # expire 5 min before actual expiry
MAX_CONCURRENT_ASSUME_ROLE: int = 50
MAX_CONCURRENT_REGION_CALLS: int = 3
ORPHAN_INSTANCE_TIMEOUT_MIN: int = 15     # minutes before orphan recovery
EMERGENCY_DEDUP_TTL_SECS: int = 600       # 10 min dedup window for interruption events
REBALANCE_BLACKLIST_TIER_HOURS: list = [1, 6, 24]  # decay tiers in hours
CLUSTER_COOLDOWN_MINUTES: int = 60
EMERGENCY_COOLDOWN_MINUTES: int = 120
NODE_FAILURE_COOLDOWN_MINUTES: int = 30
POOL_TERMINATION_BLACKLIST_HOURS: int = 24
RESIZE_COOLDOWN_HOURS: int = 6
```

**Why**: Centralising constants avoids magic numbers and makes tuning easier.

---

## 2. Data Ingestion Enhancements

### 2.1 Master Account Data (Spot, On‑Demand, Instance Catalog)

**Files**: `backend/scrapers/pricing_collector.py`, `backend/workers/tasks/pricing_task.py`

- **Spot prices** – `ec2:DescribeSpotPriceHistory` every 10 minutes per region.  
- **On‑demand prices** – `pricing:GetProducts` every 12 hours.  
- **Instance catalog** – `ec2:DescribeInstanceTypes` daily at 03:00 UTC.  

**Graceful handling**:

- Pagination: always loop until `NextToken` absent.
- Transient failures: exponential backoff with jitter (max 3 retries) using Tenacity.
- After 3 consecutive failures, mark region degraded in Redis: `degraded:region:{region}` with TTL 1800s.
- Client‑side semaphore (`MAX_CONCURRENT_REGION_CALLS`) per region.
- Staleness tracking: store `last_updated` timestamp in Redis. If spot price data > `SPOT_PRICE_STALENESS_WARN_SECS` old, log warning and attach `low_confidence: true` to API responses.

**Code snippet to add in `pricing_collector.py`**:

```python
import redis.asyncio as aioredis
from backend.core.redis_client import redis_client

async def _mark_region_degraded(region: str):
    await redis_client.setex(f"degraded:region:{region}", 1800, "1")

async def _is_region_degraded(region: str) -> bool:
    return await redis_client.exists(f"degraded:region:{region}") > 0

async def _update_spot_price_timestamp(region: str):
    await redis_client.setex(f"spot_prices_updated:{region}", 7200, datetime.now(timezone.utc).isoformat())
```

### 2.2 Client‑Specific Data (Credential Caching)

**File**: `backend/services/cluster_service.py`

Add credential caching for `sts:AssumeRole` calls to reduce STS usage and improve performance.

```python
import asyncio
from datetime import datetime, timezone

_assume_role_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_ASSUME_ROLE)

async def get_client_credentials(account_id: str, role_arn: str) -> dict:
    cache_key = f"credential_cache:{account_id}"
    cached = await redis_client.get(cache_key)
    if cached:
        creds = json.loads(cached)
        expiry = datetime.fromisoformat(creds["expiry"])
        if (expiry - datetime.now(timezone.utc)).total_seconds() > settings.CREDENTIAL_CACHE_TTL_BUFFER_SECS:
            return creds

    async with _assume_role_semaphore:
        sts = boto3.client("sts")
        resp = await asyncio.to_thread(sts.assume_role, RoleArn=role_arn, RoleSessionName=f"spot-optimizer-{account_id[:8]}")
        creds_raw = resp["Credentials"]
        expiry_dt = creds_raw["Expiration"]
        ttl_secs = int((expiry_dt - datetime.now(timezone.utc)).total_seconds() - settings.CREDENTIAL_CACHE_TTL_BUFFER_SECS)
        payload = {
            "AccessKeyId": creds_raw["AccessKeyId"],
            "SecretAccessKey": creds_raw["SecretAccessKey"],
            "SessionToken": creds_raw["SessionToken"],
            "expiry": expiry_dt.isoformat(),
        }
        if ttl_secs > 0:
            await redis_client.setex(cache_key, ttl_secs, json.dumps(payload))
        return payload
```

### 2.3 Spot Advisor Scraper

**Files**: `backend/scrapers/spot_advisor_scraper.py` (MODIFY), `backend/models/spot_advisor_rates.py` (NEW), migration (see §12.1)

- Scrape interruption rate categories from AWS Spot Advisor daily at 02:00 UTC.
- Store in `spot_advisor_rates` table (schema in §12.1).
- Implement fallback chain:
  1. Exact match `(region, instance_type)` → use `interruption_rate_pct`.
  2. Family average: average of all `instance_type` with same family prefix.
  3. Default to `DEFAULT_INTERRUPTION_RATE_PCT` (15%).

Add staleness check: if latest `valid_from` > 45 days ago, log CRITICAL alert.

---

## 3. Caching & Redis Key Management

**File**: `backend/core/redis_client.py` (MODIFY)

Add standardised key‑name helpers to ensure consistency across all services.

```python
def key_global_pool_rankings(region: str) -> str: return f"global_pool_rankings:{region}"
def key_cluster_pools(cluster_id: str) -> str: return f"cluster_pools:{cluster_id}"
def key_cluster_cooldown(cluster_id: str) -> str: return f"spot:cooldown:cluster:{cluster_id}"
def key_node_failure_cooldown(cluster_id: str, node_name: str) -> str: return f"spot:rebalance_failure:{cluster_id}:{node_name}"
def key_blacklist_global(pool_key: str) -> str: return f"blacklist:global:{pool_key}"
def key_risky_pools(region: str) -> str: return f"risky_pools:{region}"
def key_az_pressure(region: str, az: str) -> str: return f"az_pressure:{region}:{az}"
def key_family_usage(cluster_id: str) -> str: return f"cluster_family_usage:{cluster_id}"
def key_pool_launch_failures(pool_key: str) -> str: return f"pool_launch_failures:{pool_key}"
def key_pool_launch_attempts(pool_key: str) -> str: return f"pool_launch_attempts:{pool_key}"
def key_region_market_health(region: str) -> str: return f"region_market_health:{region}"
def key_degraded_region(region: str) -> str: return f"degraded:region:{region}"
def key_cache_builder_lock(region: str) -> str: return f"cache_builder:global_pool_rankings:{region}"
def key_rebalance_lock(cluster_id: str) -> str: return f"rebalance:lock:{cluster_id}"
def key_emergency_seen(instance_id: str) -> str: return f"emergency:seen:{instance_id}"
def key_emergency_in_progress(cluster_id: str) -> str: return f"cluster:{cluster_id}:emergency_in_progress"
def key_substitute_launching(cluster_id: str) -> str: return f"cluster:{cluster_id}:substitute_launching"
def key_cluster_floor(cluster_id: str) -> str: return f"cluster:{cluster_id}:min_floor"
def key_credential_cache(account_id: str) -> str: return f"credential_cache:{account_id}"
def key_rebalance_events(region: str, instance_type: str, az: str) -> str: return f"rebalance:events:{region}:{instance_type}:{az}"
```

Also add a utility function to check cache freshness:

```python
def read_cached_data(redis_key: str, staleness_threshold_secs: int = 1800) -> dict:
    raw = redis_client.get(redis_key)
    if not raw:
        return {"data": None, "low_confidence": True}
    payload = json.loads(raw)
    last_updated = payload.get("last_updated")
    low_confidence = False
    if last_updated:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(last_updated)).total_seconds()
        if age > staleness_threshold_secs:
            low_confidence = True
    return {"data": payload.get("data"), "low_confidence": low_confidence}
```

---

## 4. Global Pool Caching & Ranking

### 4.1 Risk Tier Definition

Pools are categorised by interruption risk (from Spot Advisor or ML):

| Tier | Interruption Rate | Priority |
|------|-------------------|----------|
| 1    | <5%               | Highest  |
| 2    | 5–10%             | Medium   |
| 3    | 10–15%            | Low      |
| 4    | 15–20%            | Fallback |
| 5    | >20%              | Excluded |

### 4.2 Ranking Within Each Tier

1. **Spot price** ascending – cheaper first.  
2. **Capacity score** descending – tie‑breaker: `capacity_score = vcpu + memory_gb / CAPACITY_SCORE_DIVISOR`.  
3. (Optional) **Instance family saturation penalty** – if a family exceeds `MAX_FAMILY_SHARE` in the cluster, apply a penalty.

### 4.3 Cache Builder Task

**New File**: `backend/workers/tasks/cache_builder.py`

**Purpose**: Periodically rebuild the global pool ranking cache per region. Triggered after each spot price fetch and on a 1‑hour heartbeat.

```python
import json
from datetime import datetime, timezone
from backend.core.redis_client import redis_client, key_global_pool_rankings, key_cache_builder_lock
from backend.core.config import settings

def build_global_pool_cache(region: str, db) -> None:
    lock_key = key_cache_builder_lock(region)
    if not redis_client.set(lock_key, "1", nx=True, ex=settings.GLOBAL_POOL_LOCK_TTL):
        return   # another worker is already building

    try:
        pools = _fetch_pools_with_prices_and_risk(region, db)   # see pool_ranking_service.py
        tiers = {1: [], 2: [], 3: [], 4: []}
        for pool in pools:
            tier = assign_risk_tier(pool["interruption_rate_pct"])
            if tier <= 4:
                pool["risk_tier"] = tier
                tiers[tier].append(pool)

        for t in [1,2,3,4]:
            tiers[t].sort(key=lambda p: (p["spot_price"], -compute_capacity_score(p["vcpu"], p["memory_gb"])))

        selected = []
        for t in [1,2,3,4]:
            selected.extend(tiers[t])
            if len(selected) >= settings.GLOBAL_CACHE_SIZE:
                break
        selected = selected[:settings.GLOBAL_CACHE_SIZE]

        payload = {
            "data": selected,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "region": region,
            "tier_counts": {k: len(v) for k,v in tiers.items()}
        }
        redis_client.setex(key_global_pool_rankings(region), settings.GLOBAL_CACHE_TTL, json.dumps(payload))

        if len(tiers[1]) < settings.REGION_MARKET_HEALTH_TIER1_THRESHOLD:
            logger.warning(f"Region {region} has only {len(tiers[1])} tier-1 pools.")
    finally:
        redis_client.delete(lock_key)
```

**Helper functions** (add to `pool_ranking_service.py`):

```python
def assign_risk_tier(interruption_rate_pct: float) -> int:
    rate = interruption_rate_pct / 100.0
    if rate < settings.RISK_TIER_THRESHOLDS[0]: return 1
    if rate < settings.RISK_TIER_THRESHOLDS[1]: return 2
    if rate < settings.RISK_TIER_THRESHOLDS[2]: return 3
    if rate < settings.RISK_TIER_THRESHOLDS[3]: return 4
    return 5

def compute_capacity_score(vcpu: int, memory_gb: float) -> float:
    return vcpu + (memory_gb / settings.CAPACITY_SCORE_DIVISOR)
```

---

## 5. Decision Engine

**File**: `backend/core/decision_engine.py` (MODIFY – full rewrite of `rank_for_node`)

### 5.1 Core Pipeline

The `rank_for_node` method implements the following steps:

1. **Early checks**:
   - If circuit breaker state is `HALT`, return empty list.
   - If region degraded (`degraded:region:{region}` exists), return empty list (log warning).
2. **Load global pool cache** from Redis (`global_pool_rankings:{region}`). If missing, trigger synchronous rebuild.
3. **Derive floor** from node template or current node specs (vCPU, memory, allowed families, AZs).
4. **Apply filters**:
   - Blacklist (global + per‑region risky pools).
   - Node template compliance (vCPU/memory range, families, AZs).
   - Price shock exclusion: if a pool has a `price_shock` key, exclude it.
   - AZ pressure: if AZ pressure > threshold, apply a small risk penalty.
   - Family saturation penalty: if a family exceeds `MAX_FAMILY_SHARE` in the cluster, move those pools to the back.
5. **Double‑gate**: keep only pools that are **cheaper** (spot price < current node's price) AND **safer** (risk < current node's risk).
6. **Trade‑off relaxation**: if no pool passes double‑gate, allow pools up to `trade_off_percentage` more expensive, but still strictly safer.
7. **Fallback to next risk tier**: if still none, expand to the next interruption risk tier (1→2→3→4) and repeat filters.
8. **Dry‑run capacity check** for the top N candidates (configurable, default 3) and remove any that fail. Cache results for 5 minutes.
9. **Return final ranked list** (for UI) or the single best candidate.

### 5.2 Dry‑Run Capacity Check

Add a utility in `pool_ranking_service.py`:

```python
from backend.utils.aws.fleet import dry_run_launch   # see §6.1

async def filter_pools_with_dry_run(pools: list, region: str, session) -> list:
    validated = []
    for pool in pools[:settings.DRY_RUN_CANDIDATE_LIMIT]:
        pool_key = f"{region}:{pool['az']}:{pool['instance_type']}"
        cache_key = f"dry_run:{pool_key}"
        cached = await redis_client.get(cache_key)
        if cached == b"pass":
            validated.append(pool)
            continue
        if cached == b"fail":
            continue
        # perform actual dry-run
        success = await dry_run_launch(region, pool['instance_type'], pool['az'], session)
        if success:
            await redis_client.setex(cache_key, 300, b"pass")
            validated.append(pool)
        else:
            await redis_client.setex(cache_key, 300, b"fail")
    return validated + pools[settings.DRY_RUN_CANDIDATE_LIMIT:]   # keep remaining untested
```

### 5.3 Region Degradation Check

Add at the start of `rank_for_node`:

```python
if await redis_client.exists(f"degraded:region:{region}"):
    logger.warning(f"Region {region} is degraded — no decisions.")
    return []
```

### 5.4 Enhanced Risk Signals (Existing ML Only)

The existing 1‑hour ML model (`ml_model_server.py`) provides `interruption_rate_pct` for pools. The Decision Engine will use that as the primary risk metric. The new signals (AZ pressure, family saturation, etc.) are computed from Redis counters and applied as penalties. No new ML features are added.

### 5.5 Cooldown Checks

Before selecting a node, the Execution Engine (caller) checks cluster cooldown and node failure cooldown using the Redis keys defined earlier.

---

## 6. Execution Engine

### 6.1 New AWS Utilities

**New files**: `backend/utils/aws/asg.py`, `backend/utils/aws/fleet.py`

Provide idempotent functions for ASG operations and Fleet API launches with fallback to `RunInstances`. Include a `dry_run_launch` function.

**Key functions** (detailed implementations in previous answer):

- `suspend_asg_processes`, `resume_asg_processes`
- `lower_min_size`, `restore_min_size`
- `detach_instance_from_asg`
- `get_asg_for_instance`
- `launch_via_fleet_api` (tags instance with action‑id and status=pending)
- `dry_run_launch`

### 6.2 Execution Controller

**New File**: `backend/services/execution_controller.py`

Implements the 13‑step replacement with rollback tracking.

```python
"""
ExecutionController — 13‑step safe node replacement with rollback.
One instance per action. Tracks state for idempotent rollback.
Called by auto_rebalancer and emergency_rebalancer.
"""

class ExecutionController:
    def __init__(self, cluster_id: str, action_id: str = None):
        self.cluster_id = cluster_id
        self.action_id = action_id or str(uuid.uuid4())
        # Rollback tracking
        self._asg_name: Optional[str] = None
        self._asg_suspended: bool = False
        self._new_instance_id: Optional[str] = None
        self._old_instance_id: Optional[str] = None
        self._old_node_name: Optional[str] = None
        self._asg_min_lowered: bool = False
        self._old_min_size: Optional[int] = None
        self._region: Optional[str] = None
        self._session = None   # boto3 session with credentials

    def execute_replacement(self, candidate_node: dict = None, top_pools: list = None,
                            bypass_double_gate: bool = False, db=None) -> dict:
        """Steps 1‑13. Returns result dict."""
        # ... implementation details (see previous answer) ...

    def rollback(self) -> None:
        """Idempotent rollback: resume ASG, uncordon old node, terminate new instance."""
        # ... implementation ...
        # After rollback, record in circuit breaker
        from backend.services.circuit_breaker import record_rollback
        record_rollback(self.cluster_id)
```

### 6.3 Auto Rebalancer Integration

**File**: `backend/workers/tasks/auto_rebalancer.py` (MODIFY)

- Delegate actual replacement to `ExecutionController`.
- Add concurrency lock check (Redis `rebalance:lock:{cluster_id}`) and cluster cooldown check at start.

```python
@shared_task(name="auto_rebalancer.run")
def run_auto_rebalancer(self, cluster_id: str):
    lock_key = key_rebalance_lock(cluster_id)
    if not redis_client.set(lock_key, "1", nx=True, ex=600):
        return {"status": "skipped", "reason": "concurrent_lock"}
    if check_cluster_cooldown(cluster_id):
        redis_client.delete(lock_key)
        return {"status": "skipped", "reason": "cluster_cooldown"}

    controller = ExecutionController(cluster_id=cluster_id)
    try:
        result = controller.execute_replacement()
        return result
    except Exception:
        controller.rollback()
        raise
    finally:
        redis_client.delete(lock_key)
```

### 6.4 Emergency Rebalancer

**New File**: `backend/workers/tasks/emergency_rebalancer.py`

Handles spot interruption events (triggered by Emergency Service). Similar to auto rebalancer but with `bypass_double_gate=True` and overriding cooldowns.

---

## 7. Emergency Service

### 7.1 Event Processor & Handlers

**New files**:

- `backend/services/emergency_event_processor.py` – dispatcher with deduplication.
- `backend/services/emergency_handler.py` – handles termination events.
- `backend/services/rebalance_tracker.py` – tracks rebalance notices and applies decay blacklisting.

**Deduplication**: Redis `emergency:seen:{instance_id}` with TTL `EMERGENCY_DEDUP_TTL_SECS`.

**Termination flow**:
- Acquire cluster emergency lock (`cluster:{id}:emergency_in_progress`).
- If standby available (and `maintain_standby` enabled), uncordon it, drain interrupted node, terminate, and launch new standby async.
- Else, direct replacement via `ExecutionController` (bypass double‑gate).
- Always blacklist pool 24h, set cluster floor, set 2‑hour cluster cooldown.

**Rebalance flow**:
- Increment per‑pool event count in Redis sorted set.
- If count ≥ `REBALANCE_THRESHOLD` (3) in last hour, apply decay‑based blacklisting (1h, 6h, 24h).
- Increase pool's risk multiplier to encourage gradual migration.

### 7.2 Termination Monitor Integration

**File**: `backend/workers/tasks/termination_monitor.py` (MODIFY)

Replace inline handling with call to `emergency_event_processor.process()`.

### 7.3 Agent HTTP Endpoints

**File**: `backend/api/agent_routes.py` (MODIFY)

Add endpoints for Node Agent to report IMDS‑detected events.

```python
@router.post("/spot-interruption")
async def report_spot_interruption(payload: SpotInterruptionPayload, ...):
    result = emergency_event_processor.process("termination", ...)
    return result

@router.post("/rebalance-recommendation")
async def report_rebalance_recommendation(payload: SpotInterruptionPayload, ...):
    result = emergency_event_processor.process("rebalance", ...)
    return result
```

---

## 8. Circuit Breaker

**New File**: `backend/services/circuit_breaker.py`

Implements state machine (NORMAL, CONSERVATIVE, HALT) with Redis storage.

- `record_rollback(cluster_id)`: increments counter, may transition state.
- `get_state(cluster_id)`: returns current state.
- `get_risk_multiplier(cluster_id)`: used by Decision Engine.
- `reset(cluster_id)`: admin API to reset to NORMAL.

**Integration**:

- In `ExecutionController.rollback()`, call `record_rollback()`.
- In `DecisionEngine.rank_for_node()`, if `HALT` return empty list; if `CONSERVATIVE` apply risk multiplier.

**Admin API endpoints** added in `admin_routes.py`:

- `GET /circuit-breakers` – list all cluster states.
- `POST /circuit-breakers/{id}/reset` – reset a breaker.

---

## 9. Recovery Monitor

**New File**: `backend/workers/tasks/recovery_monitor.py`

Scans for orphaned instances (tagged `spot-optimizer:status=pending` and launched >15 minutes ago with no node join). Terminates them and logs.

- Runs every 5 minutes via Celery beat.
- Uses `boto3` to describe instances with filters.
- Checks Redis for `node_joined:{instance_id}` key (written by Node Agent when node joins).
- Terminates orphan and records in `rebalancing_actions`.

---

## 10. Agent Architecture

### 10.1 AgentAction Mechanism

**Decision**: Keep using the existing database `agent_actions` table, **not** CRDs. This avoids changes to the Node Agent.

- Node Agent already polls `/api/v1/actions/pending` (HTTP) and reports results.
- Orchestrator will create `agent_actions` records via `cluster_service.create_agent_action()`.
- No new CRDs, no RBAC changes for CRDs.

**Files to modify**:

- `backend/services/cluster_service.py` – ensure `create_agent_action` writes to DB.
- Node Agent code remains unchanged (already uses HTTP polling).

### 10.2 Node Agent IMDS Polling

Add environment variables to DaemonSet (see Helm chart update). Node Agent must:

- Poll `http://169.254.169.254/latest/meta-data/spot/termination-time` every 5 seconds.
- If 200 response, POST to `/api/v1/agent/spot-interruption` with instance metadata.
- Poll `http://169.254.169.254/latest/meta-data/events/recommendations/rebalance` similarly.

### 10.3 Orchestrator

- Maintain WebSocket connection to backend, with HTTP fallback polling.
- On launch command, copy source node attributes and launch via `fleet.py`.
- After new node joins, POST to `/api/v1/worker/node-joined` to set Redis key.

### 10.4 Helm Chart Updates

**Files**:

- `charts/spot-optimizer-agent/templates/daemonset.yaml`: add env vars for IMDS polling.
- `charts/spot-optimizer-agent/templates/configmap.yaml`: add backend endpoints and poll interval.
- `charts/spot-optimizer-agent/templates/clusterrole.yaml`: ensure Node Agent has permissions for `pods/eviction` and nodes patch (already present).

---

## 11. Karpenter Integration

All existing Karpenter files preserved. Add the following methods to `karpenter_service.py`:

- `detect_karpenter_in_cluster(cluster_id, db)` – checks for NodePool CRD.
- `patch_node_pool_allowed_types(...)` – updates NodePool instance‑type requirement.

**New route** in `karpenter_routes.py`: `GET /detect/{cluster_id}`.

**Launch strategy** in `ExecutionController`:

- If cluster setting `karpenter_mode = 'delegate'` and Karpenter detected → use Karpenter (patch NodePool, then wait for node).
- Otherwise → direct launch via Fleet API.

---

## 12. Database Migrations

### 12.1 New Tables

Create the following tables via Alembic migrations (order matters). Provide migration scripts as in previous answer.

- `spot_advisor_rates`
- `optimizer_proposals`
- `substitute_nodes`
- `circuit_breaker_log`
- `instance_catalog` (if not already present)

### 12.2 Removal of Volume‑Aware Rightsizing

**This is critical**: Remove all traces of the volume‑aware rightsizing feature, which was never implemented but may have left artifacts.

**Steps**:

1. **Create a migration** to drop tables `volume_metrics` and `volume_recommendations` if they exist. (If they don’t exist, no action needed.)

   ```python
   def upgrade():
       op.execute("DROP TABLE IF EXISTS volume_metrics CASCADE")
       op.execute("DROP TABLE IF EXISTS volume_recommendations CASCADE")
   ```

2. **Delete the model file** `backend/models/volume_models.py` (if present).

3. **Clean up `rightsizing_service.py`** – remove any imports of volume models, remove any functions related to volume recommendations, and remove the `volume_enabled` condition from recommendation logic.

4. **Delete volume API endpoints** from `routers/rightsizing.py` and associated schemas.

5. **Delete any volume‑specific Celery tasks** (e.g., `collect_volume_metrics`) and remove them from the beat schedule.

6. **Remove volume toggle from frontend** – ensure no UI component references volume rightsizing (none exist in current inventory, but verify).

7. **Update documentation** – remove any mentions of volume‑aware rightsizing.

---

## 13. Celery Beat Updates

**File**: `backend/workers/app.py` (MODIFY)

Add the following beat schedule entries (preserve existing):

- `recovery-monitor-scan`: every 5 minutes.
- `global-pool-cache-{region}`: hourly, offset per region.
- `spot-advisor-scrape-daily`: daily at 02:00 UTC.
- `instance-catalog-refresh-daily`: daily at 03:00 UTC.
- `ondemand-price-refresh`: every 12 hours.
- `spot-price-ingest-{region}`: every 10 minutes.
- `circuit-breaker-audit-log`: every 10 minutes.

**Queue routing**: add `pricing` and `monitoring` queues.

---

## 14. Frontend Minimal Updates

All changes are additive; no new pages or structural changes.

### 14.1 InterruptionHeatmap.jsx

- Add AZ pressure badges to each cell (display small numeric badge).
- Data from enhanced `/volatility/status` endpoint.

### 14.2 AdminHealth.jsx

- Add circuit breaker status section listing all clusters with state and rollback count.
- Fetch from `/admin/circuit-breakers`.

### 14.3 PoolRankings.jsx

- Add two columns: "Blacklist" (● indicator) and "Signal" (⚡ for price shock).
- Data from enriched pool rankings endpoint.

### 14.4 ClusterList.jsx (OptimizationSettingsTab)

- Add trade‑off percentage slider (0‑50%) with label.
- If Karpenter detected, add mode selector (`direct` / `delegate`).

### 14.5 AutoRebalanceAuditCard.jsx

- Add circuit breaker state badge next to cluster name.

### 14.6 API Client (`api.js`)

Add methods:

- `adminAPI.getCircuitBreakers()`
- `adminAPI.resetCircuitBreaker(clusterId)`
- `atharvaaiAPI.getVolatilityStatusEnriched(region)`
- `karpenterAPI.detectKarpenter(clusterId)`

---

## 15. File Change Summary

### New Files (Create)

| File | Section |
|------|---------|
| `backend/utils/aws/__init__.py` | 6.1 |
| `backend/utils/aws/asg.py` | 6.1 |
| `backend/utils/aws/fleet.py` | 6.1 |
| `backend/services/execution_controller.py` | 6.2 |
| `backend/services/emergency_event_processor.py` | 7.1 |
| `backend/services/emergency_handler.py` | 7.1 |
| `backend/services/rebalance_tracker.py` | 7.1 |
| `backend/services/circuit_breaker.py` | 8 |
| `backend/workers/tasks/recovery_monitor.py` | 9 |
| `backend/workers/tasks/cache_builder.py` | 4.3 |
| `backend/workers/tasks/emergency_rebalancer.py` | 6.4 |
| `backend/models/spot_advisor_rates.py` | 12.1 |
| `backend/models/optimizer_proposal.py` | 12.1 |
| `backend/models/substitute_nodes.py` | 12.1 |
| Alembic migration scripts (6 files) | 12 |

### Modified Files

| File | Changes |
|------|---------|
| `backend/core/config.py` | Add constants |
| `backend/core/redis_client.py` | Add key helpers, freshness check |
| `backend/core/decision_engine.py` | Full rewrite with new pipeline |
| `backend/services/pool_ranking_service.py` | Add risk tier functions, dry‑run filter |
| `backend/services/cluster_service.py` | Add credential caching |
| `backend/services/karpenter_service.py` | Add detection and patch methods |
| `backend/scrapers/pricing_collector.py` | Add staleness, degraded region, semaphore |
| `backend/scrapers/spot_advisor_scraper.py` | Align to new table, add fallback chain |
| `backend/workers/tasks/auto_rebalancer.py` | Delegate to ExecutionController |
| `backend/workers/tasks/termination_monitor.py` | Use EmergencyEventProcessor |
| `backend/workers/tasks/pricing_task.py` | Add new tasks (rebuild, scrape, etc.) |
| `backend/workers/app.py` | Add beat schedule, queues |
| `backend/api/agent_routes.py` | Add spot-interruption and rebalance endpoints |
| `backend/api/admin_routes.py` | Add circuit‑breaker endpoints |
| `backend/api/karpenter_routes.py` | Add detect endpoint |
| `backend/api/atharvaai_routes.py` | Enrich pool rankings response |
| `charts/spot-optimizer-agent/templates/daemonset.yaml` | Add IMDS env vars |
| `charts/spot-optimizer-agent/templates/configmap.yaml` | Add agent configs |
| `charts/spot-optimizer-agent/templates/clusterrole.yaml` | Ensure needed permissions |
| `frontend/src/components/atharvaai/InterruptionHeatmap.jsx` | Add AZ pressure badges |
| `frontend/src/components/admin/AdminHealth.jsx` | Add circuit breaker section |
| `frontend/src/components/atharvaai/PoolRankings.jsx` | Add blacklist and signal columns |
| `frontend/src/components/clusters/ClusterList.jsx` | Add trade‑off slider, karpenter mode |
| `frontend/src/components/atharvaai/AutoRebalanceAuditCard.jsx` | Add CB badge |
| `frontend/src/services/api.js` | Add new API methods |

### Deleted Files

| File | Reason |
|------|--------|
| `backend/models/volume_models.py` | Remove volume feature |
| Any volume‑related migration files | Remove (if present) |

---

## 16. Implementation Roadmap

| Phase | Milestone | Key Tasks | Est. Time |
|-------|-----------|-----------|-----------|
| **P0** | Foundation | – Add global constants to `config.py`<br>– Add Redis key helpers<br>– Run all new migrations (including volume cleanup) | 2 days |
| **P1** | Core Engines | – Implement `pool_ranking_service.py` enhancements<br>– Implement `decision_engine.py` full pipeline<br>– Implement `execution_controller.py` and integrate with auto_rebalancer | 5 days |
| **P2** | AWS Utilities | – Create `asg.py` and `fleet.py`<br>– Add dry‑run capacity check<br>– Integrate into execution flow | 2 days |
| **P3** | Emergency Service | – Create emergency event processor, handler, tracker<br>– Modify termination_monitor and agent routes<br>– Add rebalance tracker | 3 days |
| **P4** | Safety & Recovery | – Implement circuit breaker<br>– Add recovery monitor and Celery beat tasks<br>– Add admin API endpoints | 2 days |
| **P5** | Agent & Karpenter | – Update Helm charts<br>– Add Karpenter detection and patch methods<br>– Integrate launch strategy into ExecutionController | 2 days |
| **P6** | Frontend | – Modify AdminHealth, PoolRankings, ClusterList, etc.<br>– Add new API methods | 2 days |
| **P7** | Testing & QA | – End‑to‑end testing with real AWS<br>– Performance testing<br>– Documentation updates | 3 days |

**Total estimated effort**: ~19 person‑days (3–4 weeks for a small team).

---

This plan provides a complete, actionable guide to transform the Spot Optimizer codebase into a production‑ready platform with all required features and the removal of the volume‑aware rightsizing stub. Follow the file changes and implementation phases in order to ensure a smooth rollout.