# Per-Node Alternative Pools — Complete Technical Reference

> All facts verified against the codebase with exact file paths, function names, and line references.

---

## Table of Contents

1. [What Is a "Pool"?](#1-what-is-a-pool)
2. [How Pools Are Generated (Source Data)](#2-how-pools-are-generated-source-data)
3. [How Pools Are Scored (ML + Heuristics)](#3-how-pools-are-scored-ml--heuristics)
4. [How Pools Are Stored (Redis Schema)](#4-how-pools-are-stored-redis-schema)
5. [How Per-Node Alternatives Are Fetched (API)](#5-how-per-node-alternatives-are-fetched-api)
6. [How Pools Are Chosen for Auto-Rebalancing (Unified Ranking)](#6-how-pools-are-chosen-for-auto-rebalancing-unified-ranking)
7. [How Pool Rankings Are Updated](#7-how-pool-rankings-are-updated)
8. [All Possible Concerns & Edge Cases](#8-all-possible-concerns--edge-cases)
9. [Appendix: Redis Key Reference](#9-appendix-redis-key-reference)
10. [UI Recommendation vs Rebalancer Selection vs AWS Launch — The Three-Way Comparison](#10-ui-recommendation-vs-rebalancer-selection-vs-aws-launch--the-three-way-comparison)
    - [10.9 User-Configured Settings and Their Effect on Each Context](#109-user-configured-settings-and-their-effect-on-each-context)

---

## 1. What Is a "Pool"?

A **pool** is a unique combination of `(instance_type, availability_zone)` in a given AWS region. For example:

```
m5.large : ap-south-1a
m5.large : ap-south-1b
c5.xlarge : ap-south-1a
```

Each pool has an associated spot price, on-demand price, interruption risk, vCPU/memory specs, and ML-derived scores. The system maintains a ranked list of all available pools per region and filters them per-node at query/selection time.

---

## 2. How Pools Are Generated (Source Data)

### Entry Point

**File**: `backend/workers/tasks/cache_builder.py`  
**Function**: `build_global_pool_cache(region: str, db=None)` — line 312  
**Celery Task**: `build_global_pool_cache_task` — line 626

```python
@app.task(name='build_global_pool_cache', bind=False)
def build_global_pool_cache_task(region: str = 'us-east-1'):
    db = next(get_db())
    try:
        return build_global_pool_cache(region, db=db)
    finally:
        db.close()
```

### 4-Tier Data Stack

All data is sourced from Redis keys written by background workers, not from live AWS API calls at query time:

#### Tier 1 — Spot Price (Primary)

**Redis key pattern**: `spot_price:{region}:{az}:{instance_type}`  
**Example**: `spot_price:ap-south-1:ap-south-1a:m5.large`  
**Written by**: Pricing worker, every 10 minutes  
**Used for**: Current spot cost per (instance_type, AZ)

```python
# cache_builder.py line 340
while True:
    cursor, keys = r.scan(cursor, match=f"spot_price:{region}:*", count=500)
    # Iterates all AZ × instance_type combinations in region
```

#### Tier 2 — On-Demand Price

**Redis key pattern**: `ondemand_price:{region}:{instance_type}`  
**Fallback**: Family-based estimate via `_estimate_od_price(itype)` when key absent  
**Used for**: Calculating savings percentage relative to on-demand cost

```python
# cache_builder.py line 417
od_price = _lookup_od_price(r, region, itype)
if od_price <= 0:
    od_price = _estimate_od_price(itype)  # Family-based fallback
```

#### Tier 3 — AWS Spot Advisor (Interruption Rates)

**Redis key pattern**: `spot_advisor:{region}:{instance_type}:Linux`  
**Data fields**: `interruption_rate` (0–100%), `savings_percentage`  
**Converted to**: `risk_tier` (0–4) via `assign_risk_tier(interruption_rate)`  
**Used as**: Fallback when `spot_price` keys are absent for a given AZ

#### Tier 4 — Instance Specifications

**Source**: Internal `_lookup_specs(itype)` utility  
**Returns**: `(vcpu: int, memory_gb: float, architecture: str, is_fallback: bool)`  
**Fallback when unknown type**: `(1, 1.0, "amd64", True)` — `is_fallback=True` signals that the specs are heuristic-derived, not from the known spec table.

```python
# cache_builder.py line 437
vcpu, memory_gb, arch, is_fallback = _lookup_specs(itype)
if is_fallback:
    # NEW-2 fix: rank_pools_for_node() aborts with empty list
    # to avoid ranking against inaccurate baselines
    log.critical("fallback specs for %s — skipping node", itype)
```

### Savings Filter (Generation-Time)

Pools with zero or negative savings (spot price ≥ on-demand price) are discarded during generation:

```python
# cache_builder.py line 430
savings_pct = (od_price - spot_price) / od_price * 100
if savings_pct <= 0:
    continue  # Skip zero/negative savings pools
```

Pools with no on-demand price data are also skipped:

```python
# cache_builder.py line 423
if od_price <= 0:
    continue
```

### Risk Threshold at Generation Time

The risk threshold is intentionally set to 1.0 (disabled) during cache building:

```python
# cache_builder.py line 522
_prs.risk_threshold = 1.0  # No hard risk cutoff — let endpoints filter
```

This means **all pools are stored regardless of risk level**. Risk filtering happens per-node at query time (see §5 and §6).

---

## 3. How Pools Are Scored (ML + Heuristics)

### ML Models

**File**: `backend/services/pool_ranking_service.py`  
**Function**: `_step7_ml_scoring(pools, region)` — line 1131  
**Models**: Two ONNX models

| Model | Output | Meaning |
|---|---|---|
| **Classifier** | `risk_probability` (0–1) | Probability of interruption; lower = safer |
| **Regressor** | `predicted_savings` (0–1) | Predicted savings ratio; higher = better |

If ONNX models are available they are used. Otherwise the placeholder formula is applied:

```python
# cache_builder.py line 456 (placeholder before ONNX)
_safety = max(0.0, 1.0 - interruption_rate / 100.0)
ml_score = round((savings_pct / 100.0) * _safety, 4)
```

### Scoring Fields in Stored Pool Object

| Field | Range | Meaning |
|---|---|---|
| `ml_score` | 0–1 | Composite ML ranking score (higher = better) |
| `predicted_savings` | 0–1 | Regressor output (ONNX) |
| `risk_probability` | 0–1 | Classifier output: interruption risk |
| `spot_advisor_rank` | 0–4 | AWS risk tier derived from interruption rate |
| `savings_pct` | float | `(od_price - spot_price) / od_price × 100` |

### Risk Tier Mapping

| `risk_tier` | Interruption Rate | Interpretation |
|---|---|---|
| 0 | <5% | Very stable |
| 1 | 5–10% | Low risk |
| 2 | 10–20% | Moderate |
| 3 | 20–50% | High risk |
| 4 | >50% | Very high risk |

---

## 4. How Pools Are Stored (Redis Schema)

Pools are stored **globally per region**, not per-node or per-cluster. Per-node filtering happens at query time.

### Primary Cache

**Key**: `global_pool_rankings:{region}`  
**TTL**: 3900 seconds (65 minutes)  
**Format**: JSON array (list of pool dicts)  
**Max count**: ~1500 pools per region (`GLOBAL_CACHE_LIMIT`)

```python
# cache_builder.py line 604
r.setex(f'global_pool_rankings:{region}', 3900, json.dumps(_ranked_dicts))
```

**Pool object schema**:
```json
{
  "instance_type": "m5.large",
  "az": "ap-south-1a",
  "architecture": "x86_64",
  "vcpu": 2,
  "memory_gb": 8.0,
  "spot_price": 0.045,
  "ondemand_price": 0.096,
  "spot_advisor_rank": 1,
  "has_capacity": true,
  "capacity_uncertain": false,
  "predicted_savings": 0.5312,
  "risk_probability": 0.08,
  "ml_score": 0.4588,
  "is_flagged": false,
  "rank": 1,
  "timestamp": "2026-03-29T10:15:00Z",
  "capacity_status": null,
  "capacity_validated_at": null
}
```

### Secondary Cache (Market View)

**Key**: `market_view_cache:{region}`  
**TTL**: 3600 seconds (60 minutes)  
**Format**: JSON object with `data` key (wrapper object)  
**Count**: ~500–1000 pools (subset of global_pool_rankings)

```python
payload = json.dumps({
    'data': top_pools,
    'last_updated': '2026-03-29T10:15:00Z',
    'count': len(top_pools),
    'region': 'ap-south-1',
})
r.setex(cache_key, 3600, payload)
```

### Cache Priority

Both caches contain the same pool data but `market_view_cache` is the preferred source (smaller, faster). When it is absent the system falls back to `global_pool_rankings`:

```
market_view_cache:{region}   ← preferred (fetched first)
        ↓ (absent)
global_pool_rankings:{region} ← fallback
        ↓ (absent)
Return empty / GATE3_FAIL
```

### Scope

| Dimension | Scope |
|---|---|
| Per-region | Yes — separate keys per region |
| Per-cluster | No — shared across all clusters in a region |
| Per-node | No — filtering applied at query/selection time |

---

## 5. How Per-Node Alternatives Are Fetched (API)

### Endpoint

```
GET /api/v1/ascpai/clusters/{cluster_id}/nodes/{node_id}/alternatives
    ?page=1&page_size=20
```

**File**: `backend/api/ascpai_routes.py`  
**Function**: `get_node_alternatives(cluster_id, node_id, page, page_size, db)` — line 2367

### Step-by-Step Fetch Flow

#### Step 1 — Resolve Node (lines 2389–2401)

Looks up the `Instance` row by `node_id` (accepts either DB id or EC2 instance ID):

```python
inst = (
    db.query(Instance).filter(Instance.id == node_id).first()
    or db.query(Instance).filter(Instance.instance_id == node_id).first()
)
```

Raises `HTTP 404` if not found.

#### Step 2 — Unified Pool Ranking

Calls `PoolRankingService.rank_pools_for_node()` — the same function used by action creation
and the auto-rebalancer — with `include_dynamic_filters=True`:

```python
from backend.services.pool_ranking_service import PoolRankingService
ranked = PoolRankingService(db, redis).rank_pools_for_node(
    node_info={
        'instance_type': inst.instance_type,
        'az': inst.az or '',
        'od_price': INSTANCE_HOURLY.get(inst.instance_type, 0),
        'resource_profile': {
            'min_vcpu_required': required_vcpu,
            'min_memory_required': required_mem,
            'architecture': src_arch,
        },
    },
    cluster_id=cluster_id,
    region=region,
    include_dynamic_filters=True,
)
```

`rank_pools_for_node()` applies all filters and returns pools sorted by
`expected_value = savings_pct × (1 − risk_probability)` DESC.
See §6 for the definitive filter list and their implementation details.
Only positive-savings pools are returned (pools where `savings_pct < 0` are dropped inside `rank_pools_for_node` at `pool_ranking_service.py:2408–2410`).

#### Step 3 — Paginate

```python
total = len(ranked)
start = (page - 1) * page_size
page_data = ranked[start:start + page_size]
```

### Response Structure

```json
{
  "cluster_id": "prod-cluster",
  "node_id": "i-0abc123",
  "instance_type": "m5.large",
  "total_alternatives": 145,
  "total_pages": 8,
  "computed_at": "2026-03-29T10:15:00Z",
  "filters_applied": [
    "blacklist", "vcpu", "memory", "architecture", "risk_ceiling",
    "occupancy", "diversification", "allowed_families", "allowed_zones", "cross_az"
  ],
  "alternatives": [
    {
      "instance_type": "m5.xlarge",
      "az": "ap-south-1a",
      "spot_price": 0.076,
      "ondemand_price": 0.192,
      "savings_pct": 60.4,
      "expected_value": 0.554,
      "unified_score": 0.4128,
      "risk_probability": 0.08,
      "interruption_rate_pct": 8.0,
      "spot_advisor_rank": 1,
      "rank": 1
    }
  ]
}
```

---

## 6. How Pools Are Chosen for Auto-Rebalancing (Unified Ranking)

The auto-rebalancer uses `PoolRankingService.rank_pools_for_node()` — the same unified function as
the UI alternatives endpoint — to select which pool to provision a replacement spot node in.

**File**: `backend/services/pool_ranking_service.py`  
**Function**: `rank_pools_for_node(node_info, cluster_id, region, include_dynamic_filters=True, force_type=None) -> list`

**`force_type`** (optional str): When set, restricts the returned pool list to pools of this instance type only (`pool_ranking_service.py:2334–2336`: `if force_type and itype != force_type: continue`). Designed for:
- **S2S same-type rebalancing** — when a spot node fails and must be replaced with the same type.
- **OD→Spot when rightsizing is disabled** — forces same type as source (see §10.7).

> **Implementation note (code-verified):** As of 2026-03-29, **no caller actually passes `force_type`**. All four call sites (`auto_rebalancer.py:1155`, `ascpai_routes.py:1722`, `ascpai_routes.py:2357`, `ascpai_routes.py:2942`) omit it (defaulting to `None`). Same-type enforcement when `auto_rightsizing_enabled=False` is achieved by pre-setting `ml_instance_types = [source_instance_type]` before the call (`auto_rebalancer.py:1133–1143`), not via `force_type`. The parameter exists as implemented but unused infrastructure.

The 9-gate `DecisionEngine.rank_for_node()` system has been **removed**. The unified function
applies all filters in a single pass and ranks by `expected_value = savings_pct × (1 − risk_probability)` DESC.

### What `rank_pools_for_node` Does

1. Loads cluster settings (`risk_ceiling`, `arch_pref`, `diversify_enabled`) from DB
2. Loads NodeTemplate constraints (`allowed_families`, `excluded_families`, `allowed_zones`, `cross_az_rebalance`) from DB
3. Derives node floors from `node_info.resource_profile` (`min_vcpu_required`, `min_memory_required`, `architecture`)
4. Loads pool cache from Redis (`market_view_cache` → `global_pool_rankings` fallback)
5. Applies all filters in sequence:

| Filter | Logic |
|---|---|
| **Blacklist** | Skip pools in Redis global blacklist |
| **vCPU floor** | `pool_vcpu >= min_vcpu_required` |
| **Memory floor** | `pool_mem >= min_memory_required` |
| **Architecture** | Match `architecture` from resource_profile |
| **Risk ceiling** | `risk_probability <= risk_ceiling` (default 0.25). Note: `risk_ceiling_percent` from `OptimizationStrategy` (0–100 integer) is divided by 100 at `pool_ranking_service.py:2220`: `risk_ceiling = (getattr(_os, 'risk_ceiling_percent', 25) or 25) / 100.0` |
| **Allowed/Excluded families** | From NodeTemplate constraints |
| **Allowed zones** | From NodeTemplate constraints |
| **Cross-AZ restriction** | From NodeTemplate `cross_az_rebalance` flag. When `False`, only pools in the source node's AZ are kept (`pool_ranking_service.py:2380`). **Warning:** disabling cross-AZ rebalance may significantly limit savings if the cheapest spot pool is in a different AZ. |
| **Occupancy** | Skip `(type, az)` already running/pending in cluster (when `diversify_enabled`) |
| **Family diversification cap** | Max 2 pools per family in results (when `diversify_enabled`) |

6. Computes `savings_pct`, `expected_value`, `risk_probability`, `interruption_rate_pct` for each pool
7. Drops all negative-savings pools
8. Sorts by `expected_value` DESC

Returns the same ranked list whether called by the UI endpoint or the rebalancer.

### Pool Selection from the Returned List

The auto-rebalancer at execution time calls `rank_pools_for_node()` with current cluster state
and takes candidate types from the result:

```python
_ranked_ml = PoolRankingService(db, redis).rank_pools_for_node(
    node_info={
        'instance_type': source_instance_type,
        'az': target_az,
        'od_price': _od_price_rb,  # Real OD price from Redis; 0 triggers internal fallback
        'resource_profile': {'min_vcpu_required': vcpu, 'min_memory_required': mem, 'architecture': arch},
    },
    cluster_id=cluster_id,
    region=cluster.region,
    include_dynamic_filters=True,
)
# Prepend the action's intended type, deduplicate
ml_instance_types = list(dict.fromkeys([target_instance_type] + [p['instance_type'] for p in _ranked_ml]))[:8]
```

After ranking, a **launch-blocked filter** removes pools that previously failed for this cluster:

```python
# auto_rebalancer.py lines 1170–1190
_candidate_types = [
    t for t in _candidate_types
    if not _blk_redis.get(f"spot:launch_blocked:{action.cluster_id}:{t}:{target_az}")
]
```

**Two TTL tiers for `spot:launch_blocked`:**

| Trigger | TTL | Code Location |
|---|---|---|
| Spot node launched but **failed to join K8s** within timeout | **300 s (5 min)** | `auto_rebalancer.py:2887–2910` |
| **≥3 `InsufficientInstanceCapacity`** failures for same type:AZ per cluster | **1800 s (30 min)** | `auto_rebalancer.py:1604–1630` |

The 300s block prevents immediate re-targeting of a pool that just had a no-join failure. The 1800s block is more aggressive, applied only after repeated capacity failures (tracked via `spot:capacity_failures:{cluster_id}:{type}:{az}` counter with 1h TTL).

### `rank_pools_for_size` — Legacy Function (Secondary Paths)

A separate function `rank_pools_for_size(vcpu, memory_gb, region, allowed_families, architecture, limit)` exists in `pool_ranking_service.py:2050`. It is used in **secondary code paths** that do **not** apply NodeTemplate constraints, occupancy dedup, or family diversification:

| Path | File:Line | Why Not `rank_pools_for_node` |
|---|---|---|
| Warm-spare (standby) launch | `substitute_manager.py:540, 1042` | No source node context available |
| Optimizer coordinator (rightsizing) | `optimizer_coordinator.py:397` | Size-constrained scoring only |
| Cache warmer pre-warming | `cache_warmer.py:95` | Pre-warming doesn't need NodeTemplate |
| Decision engine service | `decision_engine_service.py:122, 172` | Karpenter / API path |
| Auto-rebalancer Phase 1/2 fallback | `auto_rebalancer.py:3723, 4006` | Recovery / node-pool support paths |

**Impact:** Pools selected via `rank_pools_for_size` may include families excluded by NodeTemplate, pools in disallowed AZs, or types already occupied in the cluster. Operators should be aware that standby and opportunistic spot actions bypass the full constraint set.

### Audit Cache

After each call, the UI endpoint provides `computed_at` and `filters_applied` in the response.
The `/pool-audit` API endpoint (`ascpai_routes.py:2920–2960`) returns a real-time count from `rank_pools_for_node()`.

**Redis key**: `pool_audit:{cluster_id}:{instance_id}` (TTL 300 s)

**Note:** The `pool_audit` key is **computed on-demand** — it is not written by a background process. When a cached value exists it is returned directly; otherwise a fresh `rank_pools_for_node()` call is triggered. The `rejection_reasons` field is currently always `{}` (breakdown by filter type is not yet implemented):

```json
{
  "cluster_id": "prod-cluster",
  "node_id": "i-0abc123",
  "raw_pool_count": 42,
  "eligible_count": 42,
  "rejection_reasons": {},
  "computed_at": "2026-03-29T10:15:00Z"
}
```

---

## 7. How Pool Rankings Are Updated

### Scheduled Rebuild — Every 60 Minutes

**Schedule**: Celery beat — every 60 minutes  
**Task**: `build_global_pool_cache_task` (`backend/workers/tasks/cache_builder.py` line 626)  
**Scope**: One region per invocation (default `us-east-1`; multi-region requires separate invocations)

Full rebuild process:
1. Scan all `spot_price:{region}:*` keys
2. Look up OD prices and specs
3. Score all pools with ONNX models (or fallback formula)
4. Sort by `ml_score` descending
5. Write `global_pool_rankings:{region}` (TTL 3900 s) and `market_view_cache:{region}` (TTL 3600 s)

### Event-Driven Refresh (Debounced)

Two events trigger an accelerated rebuild via Celery `apply_async`:

| Event | Source file | Redis debounce |
|---|---|---|
| After spot instance termination | `emergency_rebalancer.py` line 102 | `ranking_refresh_pending:{region}` TTL 60 s |
| After launch failure | `auto_rebalancer.py` line 3505 | `ranking_refresh_pending:{region}` TTL 60 s |

```python
# emergency_rebalancer.py line 102
_refresh_debounce_key = f'ranking_refresh_pending:{_er_region}'
if not _redis.get(_refresh_debounce_key):
    _redis.setex(_refresh_debounce_key, 60, '1')  # At most 1 rebuild per 60 s
    build_global_pool_cache.apply_async(args=[_er_region], countdown=5)
```

The 60-second debounce key prevents multiple simultaneous rebuild triggers for the same region.

### Blacklist-Driven Incremental Update

When a pool is blacklisted (e.g., after repeated launch failures), a targeted update avoids a full rebuild:

**Function**: `update_global_cache_on_blacklist(instance_type, az, region)` — `pool_ranking_service.py` line 862

```
1. Load global_pool_rankings:{region} from Redis
2. Remove the blacklisted pool_key (instance_type:az)
3. Find N replacement pools not yet in cache
4. Score the replacements
5. Insert them and re-sort by ml_score
6. Write back to Redis (preserve remaining TTL)
```

This is an **n=n replacement** — one pool out, one replacement in — so the cache count stays stable.

### Stale Rankings Detection

**In `auto_rebalancer.py`**: If the `generated_at` field in the cached payload is >70 minutes old, a CRITICAL warning is logged (debounced once per hour per region via `ranking_stale_warned:{region}`).

**Behaviour**: Non-blocking — rebalancing continues with stale data but the warning is emitted for operational visibility.

**In `auto_rebalancer.py`** (line 3651): If the cache key is **completely absent** (cache miss):

```python
if not _rankings:
    logger.critical('[auto_rebalancer] Pool rankings cache absent for %s. Skipping.', region)
    _pm4_skip_cluster = True  # Skip entire cluster for this cycle
    continue
```

This prevents a DB overload fallback (the previous behaviour was to fall through to full DB pipeline — 240 calls/hour per cluster).

---

## 8. All Possible Concerns & Edge Cases

### 8.1 Cache Miss — Both Caches Absent

**Scenario**: Redis restart, cold start, or TTL expiry between scheduled runs.

**Impact**:
- `rank_pools_for_node()` returns `[]` → rebalancing skipped for all nodes until cache is rebuilt
- UI endpoint returns `{"message": "Pool cache not yet built.", "total_alternatives": 0}`

**Recovery**:
```bash
# Manual trigger via Celery
celery -A backend.workers.app call build_global_pool_cache --args '["ap-south-1"]'
```
Or wait up to 60 minutes for the scheduled rebuild.

---

### 8.2 Stale Cache (>70 Minutes Old)

**Scenario**: Celery beat is delayed or failed; pool rankings weren't refreshed.

**Impact**:
- Rebalancing proceeds with old spot prices and risk scores
- A node may be rebalanced to a pool that has since become more expensive or interrupted
- CRITICAL log emitted once per hour per region

**Detection**:
```bash
redis-cli GET market_view_cache:ap-south-1 | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('last_updated'))"
```

**Mitigation**: The `generated_at` field in the cache is checked. No automatic block — the system notes staleness but continues.

---

### 8.3 All Filters Rejected — No Alternative Found

**Scenario**: Every compatible pool is blacklisted, exceeds the risk ceiling, fails vCPU/memory requirements, or is excluded by NodeTemplate constraints.

**Impact**: `rank_pools_for_node()` returns `[]`. Rebalancing is skipped. No action taken on the node.

**What is logged**:
```
[pool_ranking] No pools passed filters for node {node_id} in region {region}
```

**Common causes**:
1. Pool cache too small for the region (few instance types available)
2. Node's instance type has no cheaper alternatives in the same AZ
3. Architecture constraint too restrictive (e.g., arm64 only, no arm64 spot pools available)
4. NodeTemplate `allowed_instance_families` or `excluded_instance_families` eliminates all candidates
5. All remaining pools are in the global blacklist

---

### 8.4 Zero Current Price (Unknown Node Price)

**Scenario**: The source node's `spot_price` field is 0 or missing.

**Impact on ranking**: If `od_price` is 0 AND the internal `_lookup_od_price()` fallback also fails, the function falls back to pre-computed `predicted_savings` from the pool cache. Rankings remain reasonable but are not node-specific. The rebalancer now looks up the real OD price from Redis (`pricing:od:{region}:{type}`) before calling `rank_pools_for_node` to minimize this risk.

**Risk**: Nodes with unknown pricing may not get rebalanced even when cheaper alternatives exist.

**Mitigation**: Price is fetched from `spot_price:{region}:{az}:{itype}` Redis keys during cache build. If still missing, the on-demand price is used as a fallback baseline. Price is re-verified before the actual EC2 launch — the spot launch request confirms pricing at provision time.

---

### 8.5 Concurrent Rebalancing Selection

**Concurrency control**:
- `rebalance:lock:{cluster_id}` (Redis, 2400-second TTL, extended by heartbeat every 60s) prevents two Celery workers from rebalancing the same cluster simultaneously. Key is generated by `key_rebalance_lock()` in `redis_client.py`. TTL is deliberately shorter than the 45-min stale action threshold to avoid a race on worker crash.
- `lock:node_action:{cluster_id}` (Redis, 1200-second mutex — Z10 fix, was 180s) prevents parallel drains.
- DB state machine uses optimistic locking: `UPDATE WHERE current_state = :from_state` — only one worker can advance the state.

**Gap**: Pool selection itself is not locked. Two workers selecting pools in the same moment (for different nodes in different clusters) draw from the same Redis cache independently — there is no reservation mechanism to prevent both from selecting the same `(instance_type, az)` target pool.

**Impact**: Two nodes may be migrated to the same pool simultaneously, concentrating spot exposure. EC2 may have insufficient capacity for both.

---

### 8.6 Architecture Preference Not Validated Against Karpenter

**Scenario**: If `ClusterOptimizationSettings.architecture_preference = "arm64"` but the Karpenter NodePool only supports `amd64`, the architecture filter in `rank_pools_for_node()` will filter out all `amd64` pools, leaving only `arm64` alternatives. The Karpenter launch may then fail.

**Mitigation**: Launch failures trigger `ranking_refresh_pending:{region}` which rebuilds the cache and resets instance failures, but architecture conflicts are not explicitly detected.

---

### 8.7 Market View Cache vs Global Rankings — Format Mismatch

The two caches have different JSON shapes:
- `global_pool_rankings:{region}` → raw JSON **array**
- `market_view_cache:{region}` → JSON **object** with `"data"` key

The parse logic handles both:
```python
payload = json.loads(raw)
all_pools = payload if isinstance(payload, list) else payload.get('data', [])
```

This format detection ensures either cache shape can be consumed without errors.

---

### 8.8 Region Scope vs Multi-Region Clusters

`build_global_pool_cache_task` takes a single `region` argument. If a Kubernetes cluster spans multiple regions (uncommon but possible in multi-region setups), each region requires a separate Celery beat schedule entry. The current default only covers `us-east-1`. Additional regions must be explicitly added or called separately.

---

### 8.9 Small Cache Starves Node-Specific Alternatives

**Scenario**: `market_view_cache` stores ~500–1000 pools. For niche instance types (e.g., GPU instances, very large instances like `u-6tb1.metal`), the pool may not appear in the top-N cached pools.

**Impact**: `rank_pools_for_node()` returns `[]` for those nodes — no alternatives are shown in the UI and no rebalancing occurs.

**Mitigation**: The cache builder attempts to include a diverse set of instance families. For truly niche types, manual cache expansion or a region-specific build may be needed.

---

## 9. Appendix: Redis Key Reference

| Key | Format | TTL | Written By | Purpose |
|---|---|---|---|---|
| `global_pool_rankings:{region}` | JSON array | 3900 s | `cache_builder.py` | Primary pool cache |
| `market_view_cache:{region}` | JSON object w/ `data` | 3600 s | `cache_builder.py` | Secondary pool cache (preferred) |
| `spot_price:{region}:{az}:{itype}` | JSON object | ~10 min | Pricing worker | Live spot prices |
| `ondemand_price:{region}:{itype}` | Float string | — | Pricing worker | OD price for savings calc |
| `spot_advisor:{region}:{itype}:Linux` | JSON object | — | Pricing worker | AWS interruption rate |
| `ranking_refresh_pending:{region}` | `"1"` | 60 s | auto_rebalancer, emergency_rebalancer | Debounce fast-path refresh |
| `ranking_stale_warned:{region}` | `"1"` | 3600 s | auto_rebalancer | Debounce stale-cache CRITICAL log |
| `pool_audit:{cluster_id}:{node}` | JSON object | 300 s | ascpai_routes.py | Per-call filter rejection audit |
| `key_blacklist_global({pool_key})` | any | varies | blacklist_service | Pool hard blacklist |
| `pool:launch_failures:{pool_key}` | integer string | 7 days | auto_rebalancer | Failure counter for blacklisting |
| `native_spot_status:{cluster_id}:{ng}` | JSON | 300 s | karpenter_routes.py | Native spot status API cache |

---

## 10. UI Recommendation vs Rebalancer Selection vs AWS Launch — The Three-Way Comparison

This section explains the critical differences between what **the UI displays as recommendations**, what **the auto-rebalancer actually selects**, and what **actually gets launched on AWS** — including how the scoring differs between each context.

---

### 10.1 Overview: Three Distinct Contexts

```
┌─────────────────────────────────────────────────────────────────────┐
│  CONTEXT 1: UI Alternatives List                                    │
│  Source: GET /alternatives endpoint                                 │
│  Function: PoolRankingService.rank_pools_for_node()                │
│  Sort key: expected_value = savings × (1 - risk_probability)       │
│  "Recommended" = rank 1 in list (no explicit flag)                 │
│  Purpose: Show user what pools are theoretically available          │
└─────────────────────────────────────────────────────────────────────┘
          = (same function, same sort key)
┌─────────────────────────────────────────────────────────────────────┐
│  CONTEXT 2: Rebalancing Action Target Pool                          │
│  Source: PoolRankingService.rank_pools_for_node() + action creation │
│  Sort key: expected_value = savings × (1 - risk_probability)       │
│  Selected pool = ranked_pools[0] after unified filtering            │
│  Purpose: What pool to provision the replacement spot node in        │
└─────────────────────────────────────────────────────────────────────┘
          ≠ (further filtered by launch-blocked + architecture + AWS capacity)
┌─────────────────────────────────────────────────────────────────────┐
│  CONTEXT 3: Actual AWS RunInstances Call                            │
│  Source: _launch_spot_instance_direct() in auto_rebalancer.py       │
│  Loop: ml_instance_types[:8] — tries each in order                  │
│  First successful launch wins (capacity-based cascade)              │
│  Purpose: Which EC2 instance actually gets created                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 10.2 Context 1: What the UI Shows as "Recommendation"

**File**: `backend/api/ascpai_routes.py` — `get_node_alternatives()` line 2367  
**Endpoint**: `GET /api/v1/ascpai/clusters/{cluster_id}/nodes/{node_id}/alternatives`

#### There is no explicit "recommended" flag

The UI alternatives list does not have a dedicated `is_recommended: true` field. The **first item in the returned list (`rank: 1`)** is the implicit recommendation — it has the highest `expected_value`.

#### How the UI list is sorted

```python
# ascpai_routes.py lines 2643–2676
positive.sort(key=lambda p: p['expected_value'], reverse=True)
```

**Sort formula** — `expected_value`:
```
expected_value = savings_pct × (1 - pool_risk_probability)
```

Where `savings_pct` is computed **relative to the source node's on-demand price** (not the pool's own OD price):
```python
savings_pct = (node_od_price - pool_spot_price) / node_od_price
```

**Additional UI-only score** (`unified_score`) shown in the response but not used for ranking:
```python
unified_score = (max(0, savings_pct) * 0.8) * (1.0 - pool_risk) * rep_mult * cap_mult
```
- `rep_mult`: bonus for same instance family as current node
- `cap_mult`: bonus (1.1×) for pools with `has_capacity = True`

The `unified_score` is displayed to users in the UI but the **actual sort order** uses `expected_value`.

#### What the UI list shows (summary)

| Field displayed | Formula | Purpose |
|---|---|---|
| `savings_pct` | `(node_od - pool_spot) / node_od × 100` | % savings vs source node cost |
| `expected_value` | `savings_pct × (1 - risk_prob)` | Risk-adjusted savings (ranking key) |
| `unified_score` | `(savings × 0.8) × (1-risk) × rep_mult × cap_mult` | Composite display score |
| `risk_probability` | ONNX classifier output (0–1) | Interruption likelihood |
| `interruption_rate_pct` | From spot_advisor Redis key | Historical AWS interruption % |
| `rank` | Position in sorted list (1 = best) | Display order |

---

### 10.3 Context 2: What the Auto-Rebalancer Selects as Target Pool

**File**: `backend/workers/tasks/auto_rebalancer.py` — execution block (line ~1147)  
**Function**: `PoolRankingService.rank_pools_for_node()` (`pool_ranking_service.py`) — **same function as the UI**

#### Sorting formula (unified — identical to the UI)

```python
expected_value = savings_pct * (1.0 - risk_probability)   # DESC
```

The rebalancer calls `rank_pools_for_node()` with the source node's specs. The sort key is the same
`expected_value` formula used by the UI alternatives endpoint — the pool ranked #1 in the UI will also be
the top candidate for rebalancing (subject to occupancy constraints).

#### Filters applied inside `rank_pools_for_node`

| Filter | Logic |
|---|---|
| **Blacklist** | Skip pools in Redis global blacklist |
| **vCPU floor** | `pool_vcpu >= min_vcpu_required` |
| **Memory floor** | `pool_mem >= min_memory_required` |
| **Architecture** | Match source node arch from `resource_profile` |
| **Risk ceiling** | `risk_probability <= risk_ceiling` (from `OptimizationStrategy`) |
| **Allowed/Excluded families** | From NodeTemplate constraints |
| **Allowed zones** | From NodeTemplate constraints |
| **Cross-AZ restriction** | From NodeTemplate `cross_az_rebalance` flag |
| **Occupancy** | Skip `(type, az)` already running/pending in cluster |
| **Family diversification cap** | Max 2 pools per family when `diversify_pools=True` |

#### What is stored as `target_pool` in `RebalancingAction`

The action record stores:
```python
action.target_pool = f"{chosen_pool_dict['instance_type']}:{chosen_pool_dict['az']}"
# Example: "c5.large:ap-south-1a"
```

This is the **intended** pool at action-creation time. Between creation and execution, the actual instance type may change (see §10.4).

---

### 10.4 Context 3: What Actually Launches on AWS

**File**: `backend/workers/tasks/auto_rebalancer.py`  
**Function**: `_launch_spot_instance_direct()` — lines 700–870

#### Re-ranking at execution time (lines 1147–1230)

When the action is actually executed, **the pool list is re-computed** using the unified function:

```python
# auto_rebalancer.py line ~1147
_ranked_ml = PoolRankingService(db, _grc_ml()).rank_pools_for_node(
    node_info={
        'instance_type': source_instance_type,
        'az': target_az or '',
        'od_price': _od_price_rb,  # Real OD price from Redis; 0 triggers internal fallback
        'resource_profile': {'min_vcpu_required': vcpu, 'min_memory_required': mem, 'architecture': arch},
    },
    cluster_id=action.cluster_id,
    region=cluster.region or 'ap-south-1',
    include_dynamic_filters=True,
)
```

This produces an updated list. The `target_instance_type` from the action record is injected at **position 0** of the candidate list, followed by the ranked fallbacks:

```python
ml_instance_types = list(dict.fromkeys(
    [target_instance_type] +           # Action's intended type first
    [p['instance_type'] for p in _ranked_ml]  # ranked fallbacks
))[:8]
```

A launch-blocked filter then checks:
```
spot:launch_blocked:{cluster_id}:{instance_type}:{az}   (set on repeated no-join failures)
```

The final `ml_instance_types` list (max 8 entries) is the **cascade list** passed to the launch function.

#### Architecture filter (lines 1248–1285)

Before launching, instance types are filtered by:
1. `ClusterOptimizationSettings.architecture_preference` (arm64 / amd64 / both)
2. Source node's architecture (detected via `DescribeInstanceTypes` API with 7-day Redis cache)
3. Node template constraint intersect (if a `ClusterTemplateMapping` exists)

If architecture filter removes all candidates, the source instance type is used as the sole fallback.

#### The actual RunInstances loop (lines 760–860)

```python
for _itype in (target_instance_types or ["t3.medium"])[:_max_attempts]:  # max 6 attempts
    _client_token = hashlib.sha256(
        f"{source_instance_id}:{_itype}".encode()
    ).hexdigest()  # idempotent — same source + type → same token

    _run_kwargs = {
        "ImageId":      _ami_id,         # COPIED from source node
        "InstanceType": _itype,          # Current candidate in cascade
        "MinCount": 1, "MaxCount": 1,
        "ClientToken":  _client_token,   # Deduplication
        "NetworkInterfaces": [{
            "DeviceIndex": 0,
            "SubnetId": _target_subnet,  # Derived from target_az (first available)
            "Groups": _sg_ids,           # COPIED from source node
            "AssociatePublicIpAddress": _src_has_public_ip,  # COPIED
        }],
        "InstanceMarketOptions": {
            "MarketType": "spot",
            "SpotOptions": {"SpotInstanceType": "one-time"},  # No persistent request
        },
    }
    # Optional fields added if present on source:
    # "UserData" — EKS bootstrap script (base64)
    # "IamInstanceProfile" — COPIED from source node
    # "KeyName" — COPIED from source node

    _run_resp = _ec2.run_instances(**_run_kwargs)
    # If successful: return instance_id, actual_itype, actual_az
```

**If `InsufficientInstanceCapacity`, `SpotMaxPriceTooLow`, `InstanceLimitExceeded`, or `Unsupported` is returned by AWS**, the loop skips to the next candidate type and continues.

**Rightmost fallback**: If all 6 candidates fail, returns `None` (launch failed, action remains pending for retry).

#### Key AWS parameters — exact values

| Parameter | Value | Source |
|---|---|---|
| `InstanceType` | First successful type from cascade list | ML-ranked + diversification |
| `ImageId` | AMI from source node | `DescribeInstances` on source |
| `SubnetId` | First available subnet in `target_az` (same VPC as source) | `DescribeSubnets` call |
| `SpotInstanceType` | `"one-time"` (no persistent request) | Hardcoded |
| `MaxPrice` | **Not set** — launches at current market rate | No price cap enforced |
| `ClientToken` | SHA256(`source_instance_id:instance_type`) | Idempotent dedup |
| `UserData` | EKS bootstrap script (copied from source or fetched from node group) | 3-level fallback |
| `IamInstanceProfile` | ARN copied from source node | `DescribeInstances` on source |
| `AssociatePublicIpAddress` | Copied from source node's public IP presence | Security: EKS API access |

---

### 10.5 Unified Sort Order Across All Contexts

All three pool-selection contexts now use the same `rank_pools_for_node()` function and the same sort key:

| Context | Sort Key | Formula | Extra Filters |
|---|---|---|---|
| **UI alternatives list** | `expected_value` | `savings_pct × (1 - risk_probability)` | None beyond vCPU/mem/arch/risk/blacklist |
| **Action creation (target pool)** | `expected_value` | Same unified formula | + Occupancy, family diversification via `rank_pools_for_node` filters |
| **Execution-time re-rank** | `expected_value` | Same unified formula | + Launch-blocked key check |
| **Actual AWS launch** | Cascade order from re-rank | First in list that AWS accepts | + AWS capacity availability (runtime) |

The pool ranked #1 in the UI alternatives view will also be the top candidate for the rebalancer (assuming occupancy constraints are met). **The pool launched by AWS may still differ** from the action's `target_pool` if:
1. AWS rejects the top candidate with `InsufficientInstanceCapacity`
2. The launch-blocked check at execution removes a candidate
3. Architecture filter at execution further narrows the list

---

### 10.6 How the **target_instance_type** Flows Through the System

```
1. Pool cache (global_pool_rankings / market_view_cache)
   └── Pool data with spot_price, interruption_rate, vcpu, memory, etc.

2. Action creation → rank_pools_for_node() (unified function)
   └── filters: blacklist + vCPU + mem + arch + risk + occupancy + families + zones + diversification
       sort: expected_value = savings_pct × (1 − risk_probability) DESC
       top candidate → action.target_pool = "c5.large:ap-south-1a"
                        action.target_instance_type = "c5.large"

3. Action execution → rank_pools_for_node() called again with fresh cluster state
   └── [target_instance_type] prepended to re-ranked list
       ↓ launch-blocked check (spot:launch_blocked:{cluster_id}:{type}:{az})
       ↓ architecture filter (source node arch + node template intersect)
       = final ml_instance_types = ["c5.large", "m5.large", "c5a.large", ...]

4. _launch_spot_instance_direct() loop
   └── Try "c5.large" → AWS responds InsufficientInstanceCapacity
       Try "m5.large" → AWS returns i-0abc123 in ap-south-1a ✓

5. action.action_metadata["actual_instance_type"] = "m5.large"
   action.action_metadata["skipped_types"] = {"c5.large": "InsufficientInstanceCapacity: ..."}
```

The `action_metadata` JSON field stores `skipped_types` so the deviation from the planned pool is recorded and auditable.

---

### 10.7 Rightsizing Interaction: When Pool Size Changes

If `auto_rightsizing_enabled = True` in `ClusterOptimizationSettings`, the auto-rebalancer may select an instance **smaller** than the source instance:

```python
# auto_rebalancer.py lines 1130–1143
if not (_opt_for_check and _opt_for_check.auto_rightsizing_enabled):
    # Rightsizing OFF: reject types smaller than source
    target_instance_type = source_instance_type
    ml_instance_types = [source_instance_type]
```

When rightsizing is off, the system **forces same-size replacement only** — the ML ranking is overridden to use the source instance type as sole candidate. This is achieved by setting `target_instance_type = source_instance_type` and `ml_instance_types = [source_instance_type]` before the `rank_pools_for_node()` call (`auto_rebalancer.py:1133–1143`), **not** by passing `force_type` (see §6 implementation note). The UI still shows alternatives of any size, but the actual launch would be same-size only.

---

### 10.8 Summary Table: What Each Context Uses

| Question | UI Alternatives | Rebalancer (Action Creation) | AWS Launch |
|---|---|---|---|
| **Where pools come from** | `market_view_cache` → `global_pool_rankings` | `rank_pools_for_node()` on same Redis caches | First available in cascade list |
| **Ranking function** | `rank_pools_for_node()` (unified) | `rank_pools_for_node()` (same function) | N/A — tries types in list order |
| **Sort key** | `expected_value` | `expected_value` (identical formula) | AWS capacity lottery |
| **Savings formula** | `savings_pct × (1 − risk_probability)` | Same formula | N/A |
| **Risk filter** | `risk_probability ≤ risk_ceiling` | Same (`risk_ceiling` from `OptimizationStrategy`) | None (AWS doesn't know about risk) |
| **Diversification** | When `diversify_pools=True` | When `diversify_pools=True` | Re-applied via launch-blocked keys |
| **Architecture filter** | `arch_pref` setting + `resource_profile` | Same (inside `rank_pools_for_node`) | Source node arch + API verification |
| **NodeTemplate filters** | Applied (families, zones, cross_az) | Applied (same code path) | N/A |
| **Price ceiling** | None | None (EV captures savings) | **No max_price set on RunInstances** |
| **Fallback behavior** | Empty list if no positive-savings pool | Defer action to next cycle | Try next type in cascade list |
| **What "rank 1" means** | Best EV for this node | Same — identical ranking | First type AWS has capacity for |

---

### 10.9 User-Configured Settings and Their Effect on Each Context

Every configurable setting is grouped by which context it actually affects.  
**"Stored only"** means the setting exists in the DB but is never read by pool-selection or launch code.

---

#### 10.9.1 Settings From `ClusterOptimizationSettings`

| Setting | Default | UI Alternatives | Rebalancer Pool Selection | AWS Launch |
|---|---|---|---|---|
| `auto_rebalance_enabled` | `False` | — | **Cluster skipped entirely** if `False` (`auto_rebalancer.py:3582`) | — |
| `auto_rightsizing_enabled` | `False` | Display in effective-config | **Allows downsizing**; if `False` → forces replacement to same instance type only (`auto_rebalancer.py:1133`) | — |
| `auto_stateful_rightsizing_enabled` | `False` | — | Enables stateful rightsizing sub-task (`auto_rebalancer.py:5746`) | — |
| `diversify_pools` | `False` | **Yes** — adds occupancy dedup in alternatives table (`ascpai_routes.py:1553`) | **Yes** — S2S diversify-violation trigger; bypasses cooldown; filters `(type,az)` pairs already occupied (`auto_rebalancer.py:4377`, `4629`) | — |
| `instance_type_diversification_pct` | `100` | **Yes** — caps max same-type count per cluster in the **node recommendations** endpoint only (`ascpai_routes.py:1557–1615`): `_max_same_type = max(1, round(total_nodes × (1.0 - pct / 100.0)))`. **Not applied** in the per-node `/alternatives` endpoint — that endpoint calls `rank_pools_for_node()` directly without post-filtering by this setting. | **No** — not enforced in rebalancer loop; rebalancer uses a fixed "max 2 pools per family" cap inside `rank_pools_for_node` regardless of this setting | — |
| `architecture_preference` | `"both"` | **Yes** — shown in effective-config; applied during UI alternatives filtering (`ascpai_routes.py:1554`) | **Yes** — intersects `ml_instance_types` with allowed architectures (`auto_rebalancer.py:1245`) | No (filtering happens before launch) |
| `max_instance_type_attempts` | `6` | — | — | **Yes** — sets cascade list length: `ml_instance_types[:max_attempts]` in the `run_instances` loop (`auto_rebalancer.py:762`) |
| `max_concurrent_rebalance_actions` | `1` | — | **Concurrency gate**: skips scheduling new actions if in-flight count ≥ this value (`auto_rebalancer.py:5236`) | — |
| `manual_approval_required` | `False` | Shown | Actions created as `pending_approval` instead of `in_progress` (`auto_rebalancer.py:5625`) | — |
| `cooldown_override_minutes` | `NULL` (→ 3600 s) | — | Sets inter-action cooldown (`spot:cooldown:action:{cluster_id}` key); bypassed when OD nodes present or diversify-violation detected (`auto_rebalancer.py:4356`) | — |
| `spot_join_timeout_minutes` | `NULL` (→ 30 min) | — | Phase 2 timeout: how long to wait for new spot node to join EKS before failing the action (`auto_rebalancer.py:2568`) | — |
| `drain_timeout_minutes` | `15` | — | Drain phase: max wait before forced EC2 terminate of source node (`auto_rebalancer.py:2844`) | — |
| `max_family_diversification_cap_pct` | `40` | — | S2S family cap threshold: if one family exceeds `ceil(cap% × total_nodes)`, S2S rebalance is triggered (`auto_rebalancer.py:4631`) | — |
| `maintain_standby` | `False` | — | Triggers standby warm-spare launch if no warm node exists (`auto_rebalancer.py:3384`, `3956`) | — |
| `check_interval_seconds` | `15` | — | Rate-limits how often the cluster is processed per Celery beat tick (`auto_rebalancer.py:3615`) | — |
| `target_spot_exposure_pct` | `100` | Display only (`ascpai_routes.py:176`) | **Stored only** | — |
| `failure_cooldown_minutes` | `30` | — | **Stored only** | — |
| `min_node_count` / `scale_down_*` | various | — | **Stored only** (active only when `enable_ascp_auto_scaler=True`) | — |

---

#### 10.9.2 Settings From `OptimizationStrategy`

| Setting | Default | UI Alternatives | Rebalancer Pool Selection | AWS Launch |
|---|---|---|---|---|
| `risk_ceiling_percent` | `25` | **Yes** — pools with `risk_probability > risk_ceiling/100` are excluded from the alternatives list (`ascpai_routes.py:1549`) | **Yes** — used in S2S trigger gate (`auto_rebalancer.py:4639`) and OD→Spot Pass 1 (`auto_rebalancer.py:5503`) | — |
| `risk_savings_tradeoff_pct` | `20` | **Yes** — applied in UI sort (Pass 2 tradeoff logic, `ascpai_routes.py:1548`) | **Yes** — max allowed price = `cheapest_spot + (OD − cheapest_spot) × tradeoff%` in Pass 2 (`auto_rebalancer.py:5502`) and S2S (`auto_rebalancer.py:4640`) | — |
| `strategy_type` | `"BALANCED"` | Display in effective-config (`ascpai_routes.py:172`) | **Stored only** — not enforced in ranking | — |
| `min_savings_percent` | `15` | — | **Yes (N2 fix)** — now enforced by `rank_pools_for_node()`. Pools with `savings_pct` below this threshold are excluded from the ranked list. Previously stored-only; now has runtime effect. | — |
| `volatility_tolerance_percent` | `20` | — | **Stored only** | — |
| `migration_penalty_multiplier` | `1.5` | — | **Stored only** | — |
| `diversity_strictness_level` | `"Medium"` | — | **Stored only** | — |

---

#### 10.9.3 Settings From `NodeTemplateVersion.constraints_json` (`NodeTemplateConstraints`)

These settings are enforced by `PoolRankingService.rank_pools_for_node()`, which is now the shared code path for both the UI and the rebalancer.

| Setting | Applied in UI? | Applied in rebalancer? | Notes |
|---|---|---|---|
| `architectures` | **Yes** — via `resource_profile.architecture` in `rank_pools_for_node` | **Yes** — same code path | Reduces candidates to matching arch |
| `min_vcpu` / `max_vcpu` | **Yes** — `pool_ranking_service.py` | **Yes** — via `resource_profile.min_vcpu_required` | Rebalancer derives from source node specs |
| `min_memory` / `max_memory` | **Yes** | **Yes** — via `resource_profile.min_memory_required` | Rebalancer derives from source node specs |
| `allowed_families` | **Yes** | **Yes** — loaded from NodeTemplate inside `rank_pools_for_node` | Families like `c5`, `m5` allowlist. ⚠ Not validated against region availability — listing unavailable families silently eliminates candidates |
| `excluded_families` | **Yes** (default: `["metal","g","p","trn","inf","i"]`) | **Yes** | GPU/metal/specialized families excluded. ⚠ Over-excluding may leave zero candidates |
| `allowed_zones` | **Yes** | **Yes** — loaded from NodeTemplate | ⚠ **Not validated against VPC subnet availability.** Listing an AZ with no subnets will cause all launches targeting that AZ to fail silently. Verify subnets exist before configuring. |
| `cross_az_rebalance` | **Yes** | **Yes** — loaded from NodeTemplate (`pool_ranking_service.py:2380`: `if not cross_az_rebalance and source_az and az != source_az: continue`) | Prevents cross-AZ moves when `False`. **Warning:** disabling this may significantly limit savings — the cheapest spot pool is often in a different AZ. Safe to disable only for zonal PVC/stateful workloads. Default: `True`. |
| `optimization_policy` | — | **Stored only** | `COST_FIRST` / `RISK_FIRST` / `BALANCED` — not enforced |
| `savings_threshold` | — | **Stored only** | Not enforced |

> ⚠ **NodeTemplate constraints are NOT automatically validated against cluster reality.** `rank_pools_for_node()` enforces whatever is stored in `NodeTemplateConstraints` at call time, but there is no background check confirming that `allowed_zones` match actual subnet availability, that `allowed_families` are available in the region, or that Karpenter NodePool configuration supports the constrained families/zones. Misconfigured constraints (e.g. `allowed_zones` listing an AZ with no subnets, or `excluded_families` accidentally excluding all viable types) will cause `rank_pools_for_node()` to return an empty list, silently skipping rebalancing for affected nodes until the constraint is corrected.

---

#### 10.9.4 Settings From `StatelessRuntimeRules`

| Setting | Default | Effect |
|---|---|---|
| `max_rebalances_per_24h` | `5` | **Actively enforced**: daily S2S action cap (`auto_rebalancer.py:3858`). OD→SPOT moves bypass this limit. |
| `substitute_strategy` | `"PREWARMED"` | Shown in effective-config (`ascpai_routes.py:175`); controls `SubstituteManager` state machine |
| `instance_diversification_enabled` | `True` | **Stored only** — returned via API but not read in execution |
| `respect_pdb_enabled` | `True` | **Stored only** |
| `prewarm_minutes` | `0` | **Stored only** |
| `resize_cooldown_minutes` | `120` | **Stored only** — the actual cooldown is controlled by a Redis key `spot:cooldown:action:resize:{cluster_id}`, set separately |
| `resize_headroom_multiplier` | `1.2` | **Stored only** |
| `volatility_safety_multiplier` | `1.35` | **Stored only** |
| `fresh_cluster_stabilization_minutes` | `1440` | **Stored only** |

---

#### 10.9.5 Settings From `StatefulRules`

| Setting | Default | Effect |
|---|---|---|
| `block_spot_for_stateful` | `True` | Shown in effective-config (`ascpai_routes.py:174`); enforced in stateful rightsizing gate |
| `require_approval` | `True` | **Gate** in stateful rightsizing sub-task — actions set to `pending_approval` (`auto_rebalancer.py:5752`) |
| `manual_resize_allowed` | `True` | **Stored only** |
| `max_downscale_percent` | `25` | **Stored only** |

---

#### 10.9.6 Critical Gaps — Settings That Exist But Have No Runtime Effect

Several settings are defined in models and returned via API (so users can configure them and seemingly expect them to work) but are never read by execution code:

| Setting | Table | Why it matters |
|---|---|---|
| `optimization_policy` | `NodeTemplateConstraints` | `COST_FIRST` / `RISK_FIRST` / `BALANCED` — not enforced |
| `savings_threshold` | `NodeTemplateConstraints` | Not enforced |
| `respect_pdb_enabled` | `StatelessRuntimeRules` | PodDisruptionBudget is NOT checked before drain in current code |
| `max_rebalances_per_24h` | `StatelessRuntimeRules` | Only caps **S2S** (spot-to-spot), not OD→Spot moves |
