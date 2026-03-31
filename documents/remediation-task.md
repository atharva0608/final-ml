# Backend Docker Log Flooding — Remediation

**Date:** 2026-03-26  
**Status:** FIXED  
**Severity:** HIGH (operational — disk/stdout saturation, unreadable logs)

---

## Problem

The `spot-optimizer-backend` Docker container was flooding stdout with **200+ log lines every 12 seconds** (~17 lines/second), making logs unreadable and consuming excessive I/O.

### Root Cause

Two issues combined:

1. **HTTP Request Logging Middleware** (`backend/core/api_gateway.py`)  
   The `log_requests` middleware logged **every single HTTP request** at `INFO` level with no path filtering. High-frequency polling endpoints generated the bulk of the noise:

   | Path | Calls per 500 lines | Source |
   |------|---------------------|--------|
   | `/api/v1/agents/actions/pending` | 92 | K8s agent polling (every 5s × 3 nodes) |
   | `/api/v1/karpenter/recommendations` | 150+ (when UI active) | Frontend components (Dashboard, ClusterList, RightSizing) |
   | `/api/v1/agents/heartbeat` | 28 | Agent heartbeat (every 30s × 3 nodes) |
   | `/api/v1/agent-metrics/batch` | 16 | Agent metrics push (every 30s) |
   | `/api/v1/clusters` | 12 | Frontend 30s polling |
   | `/health` | 8 | Docker health check |

2. **Verbose Per-Node Metrics Logging** (`backend/routers/metrics.py`)  
   The `receive_metrics_batch` handler logged **every individual node metric** at `INFO` — 8-10 lines per batch (processing, per-node stats, totals, updates, commit). With 30s agent batches this added ~20 extra INFO lines/minute.

---

## Fix Applied

### 1. Middleware Path Exclusions (`backend/core/api_gateway.py`)

Added a `_QUIET_LOG_PATHS` set of high-frequency endpoints. Requests to these paths are only logged if the `api` logger is at `DEBUG` level (effectively silent at the default `INFO` level):

```python
_QUIET_LOG_PATHS: set[str] = {
    "/health",
    "/api/v1/agents/actions/pending",
    "/api/v1/agents/heartbeat",
    "/api/v1/agent-metrics/batch",
    "/api/v1/pod-metrics/batch",
    "/api/v1/karpenter/recommendations",
}
```

The middleware now checks `if request.url.path in _QUIET_LOG_PATHS` and suppresses the `log_request()` call unless DEBUG is enabled.

### 2. Metrics Router De-verbosing (`backend/routers/metrics.py`)

Downgraded 8 per-batch log statements from `logger.info()` to `logger.debug()`:
- Per-node capacity/usage lines
- Totals summary
- Instance update confirmations
- Cluster update/commit confirmations
- Cache hit notifications

The final batch summary (`Received metrics batch from cluster: X pods, Y nodes, Z events`) remains at `INFO`.

---

## Verification

**Before fix:** 200+ lines in 12 seconds (78KB for 200 `--tail` lines)  
**After fix:** Only meaningful events logged — startup, WebSocket connections, pod metric inserts. No polling noise.

```
# Before (sample 500 lines)
  92 /api/v1/agents/actions/pending
  28 /api/v1/agents/heartbeat
  17 /api/v1/clusters/.../nodes/detailed
  16 /api/v1/agent-metrics/batch

# After (50 lines over 30s)
  Startup logs, WebSocket connections, actual business events only
```

---

## Files Modified

| File | Change |
|------|--------|
| `backend/core/api_gateway.py` | Added `_QUIET_LOG_PATHS` set + conditional logging in middleware |
| `backend/routers/metrics.py` | Downgraded 8 per-batch log lines from `INFO` → `DEBUG` |

---

## Notes

- To re-enable verbose request logging for debugging, set `LOG_LEVEL=DEBUG` in environment
- The `_QUIET_LOG_PATHS` set can be extended as new high-frequency endpoints are added
- Non-quiet paths (actual user operations, errors, cluster mutations) continue to log at `INFO`

---

# All 15 Active Problems — Remediation Log

**Date:** 2026-03-26  
**Status:** ALL FIXED  
**Scope:** 2 CRITICAL, 5 HIGH, 8 MEDIUM problems from `documents/problems.md`

---

## P-C1: RightSizing Proposal Pipeline — Field Name Mismatch (FIXED)

**Severity:** CRITICAL  
**File:** `backend/services/rightsizing_service.py`

**Problem:** `generate_proposals()` referenced non-existent fields on `RightSizingRecommendation`: `savings_monthly_pct`, `recommended_cpu_cores`, `recommended_memory_gb`, `current_avg_cpu_pct`, `current_p95_cpu_pct`, `current_avg_memory_pct`, `current_p95_memory_pct`, `sample_size` — causing `AttributeError` every time the proposal pipeline ran.

**Fix:**
- `rec.savings_monthly_pct` → `rec.savings_pct` (2 locations: filter + proposal)
- `rec.recommended_cpu_cores` → `rec.recommended_cpu_request_millicores / 1000` (2 locations)
- `rec.recommended_memory_gb` → `rec.recommended_memory_request_mb / 1024` (2 locations)
- `rec.current_avg_cpu_pct` → computed from `rec.cpu_avg_millicores / rec.current_cpu_request_millicores * 100`
- `rec.current_p95_cpu_pct` → computed from `rec.cpu_p95_millicores / rec.current_cpu_request_millicores * 100`
- `rec.current_avg_memory_pct` → computed from `rec.memory_avg_mb / rec.current_memory_request_mb * 100`
- `rec.current_p95_memory_pct` → computed from `rec.memory_p95_mb / rec.current_memory_request_mb * 100`
- `rec.sample_size` → `rec.data_points`

---

## P-C2: Agent Injector Credentials Key Mismatch (FIXED)

**Severity:** CRITICAL  
**File:** `backend/services/agent_injector.py`

**Problem:** ASG fallback client at line ~699 used `credentials['AccessKeyId']` (uppercase AWS format) while `_assume_role()` returns lowercase keys (`access_key`, `secret_key`, `session_token`). This raised `KeyError` when the fallback code path executed.

**Fix:** Changed to defensive `.get()` pattern matching the EKS client:
```python
aws_access_key_id=credentials.get('access_key') or credentials.get('AccessKeyId'),
aws_secret_access_key=credentials.get('secret_key') or credentials.get('SecretAccessKey'),
aws_session_token=credentials.get('session_token') or credentials.get('SessionToken'),
```

---

## P-H1: Hardcoded ap-south-1 Pricing in Karpenter Routes (FIXED)

**Severity:** HIGH  
**File:** `backend/api/karpenter_routes.py`

**Problem:** `INSTANCE_SPECS` dictionary hardcoded ap-south-1 hourly prices, used by `_bin_pack_instance()` for all regions.

**Fix:**
- Added `_get_od_price(instance_type, region, redis_client)` helper that looks up OD pricing from Redis (`od_price:{region}:{type}` and `ondemand_price:{region}:{type}`) first, falling back to INSTANCE_SPECS only when Redis is unavailable.
- Modified `_bin_pack_instance()` to accept optional `region` and `redis_client` parameters.
- Updated the primary call site in the recommendations handler to pass `cluster.region` and Redis client.
- INSTANCE_SPECS retained for vCPU/memory specs and as last-resort price fallback.

---

## P-H2: Pool Ranking Global Cache Lock Race Condition (FIXED)

**Severity:** HIGH  
**File:** `backend/services/pool_ranking_service.py`

**Problem:** Redis lock stored value `'1'` — any worker's `finally` block could delete another worker's lock after TTL expiry, causing concurrent pipeline runs.

**Fix:** Implemented fenced locking:
- Lock value is now `uuid.uuid4()` (unique per worker)
- `finally` block only deletes the lock if the stored value matches the worker's UUID
- Prevents a late-finishing worker from releasing a different worker's lock

---

## P-H3: DryRun Budget Starvation — No Retry (FIXED)

**Severity:** HIGH  
**File:** `backend/services/pool_ranking_service.py`

**Problem:** When DryRun budget was exhausted, all pools returned as "unvalidated" with no attempt to reuse previous validation results.

**Fix:**
- When budget is exhausted, the starvation handler now checks Redis for recently-cached validation results (`spot:validated:{region}:{type}:{az}`) and reuses them.
- Successful validations are cached in Redis with 1-hour TTL (`setex`) for starvation retry.
- Starvation metric and logging preserved.

---

## P-H4: SubstituteNode Missing ForeignKey on cluster_id (FIXED)

**Severity:** HIGH  
**File:** `backend/models/substitute_nodes.py`

**Problem:** `cluster_id` column had no `ForeignKey` constraint — orphaned records accumulated when clusters were deleted.

**Fix:** Added `ForeignKey("clusters.id", ondelete="CASCADE")` to the `cluster_id` column. Requires a migration to apply to existing databases.

---

## P-H5: Reputation Multiplier Not Clamped (FIXED)

**Severity:** HIGH  
**File:** `backend/services/pool_ranking_service.py`

**Problem:** `_rep_mult` from `PoolReputationService` was applied directly to ML scores without range validation — negative or extremely large values could corrupt scores.

**Fix:** Clamped `_rep_mult` to `max(0.1, min(10.0, _rep_mult))` before application, preventing score corruption from outlier reputation values.

---

## P-M1: OD Fallback `spot * 3.0` Fabricates Savings (FIXED)

**Severity:** MEDIUM  
**File:** `backend/services/pool_ranking_service.py` (2 locations)

**Problem:** When no OD price was found in Redis or `_ONDEMAND_FALLBACK`, the code used `_spot * 3.0` as a fabricated OD price, giving unknown instances an artificial 67% savings ratio.

**Fix:** Replaced `or _spot * 3.0` with a `continue` (skip the pool) in both the Redis fast-path and DB slow-path. Pools without verified OD pricing are excluded from rankings rather than ranked with fabricated data.

---

## P-M2: Missing Pagination in EKS `list_clusters()` (FIXED)

**Severity:** MEDIUM  
**File:** `backend/services/cluster_service.py`

**Problem:** `eks.list_clusters()` returns max ~100 clusters. No pagination used.

**Fix:** Replaced single call with boto3 paginator:
```python
paginator = eks.get_paginator('list_clusters')
for page in paginator.paginate():
    cluster_names.extend(page.get('clusters', []))
```

---

## P-M3: Missing Pagination in `describe_auto_scaling_groups()` (FIXED)

**Severity:** MEDIUM  
**Files:** `backend/services/agent_injector.py`, `backend/services/hygiene_service.py`

**Problem:** Both files called `describe_auto_scaling_groups()` without pagination (max ~50 ASGs per call).

**Fix:** Replaced both with boto3 paginators:
```python
paginator = asg.get_paginator('describe_auto_scaling_groups')
for page in paginator.paginate():
    groups.extend(page.get('AutoScalingGroups', []))
```

---

## P-M4: PoolCooldown Missing Composite Index (FIXED)

**Severity:** MEDIUM  
**File:** `backend/models/pool_cooldown.py`

**Problem:** Queries filter by both `region` AND `pool_id` but only a single-column index on `pool_id` existed.

**Fix:** Added `Index('idx_region_pool', 'region', 'pool_id')` to `__table_args__`. Requires a migration to apply to existing databases.

---

## P-M5: Missing JSON Validation on Cached Pool Rankings (FIXED)

**Severity:** MEDIUM  
**File:** `backend/services/pool_ranking_service.py`

**Problem:** After `json.loads(cached)`, no type check — corrupted cache could return a non-list type, crashing `_pool_from_dict()`.

**Fix:** Added `isinstance(pool_dicts, list)` check. On type mismatch, logs a warning and deletes the corrupt cache key, allowing a fresh pipeline rebuild.

---

## P-M6: JSONDecodeError Not Caught in Decision Engine (FIXED)

**Severity:** MEDIUM  
**File:** `backend/core/decision_engine.py`

**Problem:** `json.loads(data)` on cached global rankings had no exception handling — truncated JSON crashed the engine instead of falling through to the rebuild path.

**Fix:** Wrapped `json.loads(data)` in `try/except (json.JSONDecodeError, TypeError)`. On error, logs a warning, deletes the corrupt cache key, and falls through to the synchronous rebuild path.

---

## P-M7: Bin-Packing Ignores Memory-Only Underutilization (FIXED)

**Severity:** MEDIUM  
**File:** `backend/api/karpenter_routes.py`

**Problem:** `cpu_pct=0` with `mem_pct>0` entered the bin-packing calculation with zero CPU, producing no-op recommendations for memory-only workloads.

**Fix:** Changed `required_vcpu` and `required_mem` calculations to use `max(cpu_pct, 0)` and `max(mem_pct, 0)` explicitly. When CPU is 0, `required_vcpu` defaults to the 0.25 vCPU floor, allowing memory-driven downsizing to work correctly.

---

## P-M8: Confidence Calculation Ignores Window Coverage (FIXED)

**Severity:** MEDIUM  
**File:** `backend/services/rightsizing_service.py`

**Problem:** `_calculate_confidence()` accepted `window_hours` but never used it. Sparse data (e.g., 7h coverage in a 168h window) with enough data points received "MEDIUM" confidence.

**Fix:** Added window coverage ratio check:
- Expected points = `window_hours × 12` (1 sample per 5 minutes)
- Coverage ratio = `data_points / expected_points`
- HIGH requires `data_points >= min × 5` AND `coverage >= 50%`
- MEDIUM requires `data_points >= min` AND `coverage >= 20%`
- Otherwise LOW

---

## Files Modified

| File | Problems Fixed |
|------|---------------|
| `backend/services/rightsizing_service.py` | P-C1, P-M8 |
| `backend/services/agent_injector.py` | P-C2, P-M3 |
| `backend/api/karpenter_routes.py` | P-H1, P-M7 |
| `backend/services/pool_ranking_service.py` | P-H2, P-H3, P-H5, P-M1, P-M5 |
| `backend/models/substitute_nodes.py` | P-H4 |
| `backend/models/pool_cooldown.py` | P-M4 |
| `backend/core/decision_engine.py` | P-M6 |
| `backend/services/cluster_service.py` | P-M2 |
| `backend/services/hygiene_service.py` | P-M3 |

---

## Migration Notes

Two schema changes (P-H4 and P-M4) require a database migration:
1. `substitute_nodes.cluster_id` → add `ForeignKey("clusters.id", ondelete="CASCADE")`
2. `pool_cooldowns` → add composite index `idx_region_pool(region, pool_id)`

Generate with: `alembic revision --autogenerate -m "add_fk_and_composite_index"`

---

## Runtime Issue Fixes (Post-Deployment)

Three runtime issues discovered after deploying the above fixes:

### R-1: t3a.nano Showing 25% Interruption Rate (Real: <5%)

**Root Cause (3 contributing factors):**

1. **`_lookup_interruption_rate()` in `cache_builder.py`** — Redis-only lookup with worst-case 25.0% default when the `spot_advisor:{region}:{type}:Linux` key doesn't exist (expired TTL, not yet scraped). This 25.0% gets written into `market_view_cache:{region}` and displayed in the UI.

2. **`_ScoredPoolWrapper` in `ascpai_routes.py`** — Recalculated `risk_probability` from `interruption_rate_pct / 100.0` ignoring the ONNX-blended `risk_probability` field already computed by `pool_ranking_service.py` (50/50 blend of ONNX classifier + Spot Advisor rank).

3. **`risk_score` default = 0.25** in node-recommendations handler — When a node's instance type has no stored risk_score in `global_pool_rankings`, it falls back to 0.25 (25%), which maps to the worst interruption bucket.

**Fixes Applied:**

| # | File | Change |
|---|------|--------|
| R-1a | `backend/workers/tasks/cache_builder.py` | Rewrote `_lookup_interruption_rate()` from Redis-only (25.0 fallback) → 4-step chain: Redis → DB (`SpotAdvisorData`) with Redis backfill → family-average scan → conservative 15.0 default |
| R-1b | `backend/api/ascpai_routes.py` | `_ScoredPoolWrapper` now prefers ONNX-blended `risk_probability` when available and meaningful (> 0.20 default); falls back to `interruption_rate_pct / 100.0` only for pools without ONNX scoring |
| R-1c | `backend/api/ascpai_routes.py` | Changed `risk_score` default from `0.25` → `0.10` in node-recommendations handler |

### R-2: Real Pricing Verification & Fallback Gaps

**Finding:** Pricing flow (`bulk_get_hourly_prices()` → AWSPricingService → DB → Redis → hardcoded fallback) is correct. However, `t3a.nano` and `t3.nano` were missing from the hardcoded `_FALLBACK_HOURLY` and `_FALLBACK_VCPU` dicts, causing incorrect fallback pricing if the DB/Redis lookup fails.

**Fixes Applied:**

| # | File | Change |
|---|------|--------|
| R-2a | `backend/services/dynamic_instance_helpers.py` | Added `t3a.nano` ($0.0047/hr, 2 vCPU) and `t3.nano` ($0.0058/hr, 2 vCPU) to `_FALLBACK_HOURLY` and `_FALLBACK_VCPU` dicts |

### R-3: Backend Log Flooding When Opening Cluster Section

**Root Cause:** When the UI cluster section opens, it polls multiple endpoints at high frequency:
- `ClusterDetails.jsx`: `node-recommendations` + `rebalancing/status` + `nodes/detailed` every 30s
- `PoolRankings.jsx`: every 30s (5s when unverified pools exist)
- `ClusterList.jsx`: every 15s (4s for Karpenter)

This produces up to **74+ requests/minute** to cluster endpoints. These endpoints:
1. Were NOT in `_QUIET_LOG_PATHS` → middleware logged every request at INFO
2. Had internal `logger.info()` calls that fired on every request (lines 1425, 1471) → 222+ INFO messages/minute

**Fixes Applied:**

| # | File | Change |
|---|------|--------|
| R-3a | `backend/core/api_gateway.py` | Added `_QUIET_LOG_PREFIXES` tuple for prefix-based matching of dynamic cluster endpoints (`/api/v1/ascpai/clusters/`, `/api/v1/clusters/`, `/api/v1/ascpai/rebalancing/`). Middleware now checks both exact and prefix matches. |
| R-3b | `backend/api/ascpai_routes.py` | Downgraded `logger.info()` → `logger.debug()` for per-request pool-loading and spot-price-supplement log lines in node-recommendations |

### Files Modified (Runtime Fixes)

| File | Issue(s) |
|------|----------|
| `backend/workers/tasks/cache_builder.py` | R-1a |
| `backend/api/ascpai_routes.py` | R-1b, R-1c, R-3b |
| `backend/services/dynamic_instance_helpers.py` | R-2a |
| `backend/core/api_gateway.py` | R-3a |

---

## Runtime Issue Fixes — Round 2

### R-4: Market View Shows 15.0% Fallback Interruption Rate for ALL Pools

**Root Cause (2 converging issues):**

1. **Celery task wrapper passed `db=None`** — `build_global_pool_cache_task()` in cache_builder.py called `build_global_pool_cache(region, db=None)`, which meant the 4-tier `_lookup_interruption_rate()` fallback chain skipped Tier 2 (DB lookup) entirely. With Tier 1 (Redis) also empty (12h TTL expired), it fell through to Tier 4 (hardcoded 15.0%).

2. **Spot advisor scraper 12h Redis TTL vs 24h schedule** — Scraper ran daily but Redis keys expired after 12h. During the 12-24h gap, all 19,000+ `spot_advisor:*` keys were gone, making both Tier 1 (Redis) and Tier 3 (family average scan) return nothing.

3. **Market-view endpoint had its own 25.0% fallback** — `az_irr = float(p.get('interruption_rate_pct', 25.0) or 25.0)` at the API layer would replace any missing/zero value with 25.0% even if cache_builder stored a different fallback.

**Fixes Applied:**

| # | File | Change |
|---|------|--------|
| R-4a | `backend/workers/tasks/cache_builder.py` | Celery task now opens a DB session via `get_db()` and passes it to `build_global_pool_cache(region, db=db)` so Tier 2 (SpotAdvisorData table) is always available |
| R-4b | `backend/scrapers/spot_advisor_scraper.py` | Changed Redis TTL from 43200s (12h) → 90000s (25h) so keys survive between daily scraper runs |
| R-4c | `backend/api/ascpai_routes.py` | Changed market-view `az_irr` fallback from `25.0` → `15.0` (conservative mid-range, consistent with cache_builder's Tier 4 default) |

**Verification:** After fixes, re-ran scraper + cache rebuild:
- t3a.nano ap-south-1: `irr=5.0% tier=0` (was 15.0%)
- 19,353 spot_advisor Redis keys with 25h TTL
- All pools in market_view_cache now show real AWS Spot Advisor rates

### R-5: Node-Specific View Not Working (Empty Per-Node Panel)

**Root Cause:**

`_compute_cluster_coverage()` in reconciliation_worker.py line 59 filtered instances with `Instance.instance_id.like('i-%')`, which only matches AWS EC2-style IDs (`i-0809418326227869e`). Running nodes with Kubernetes-style IDs (`ip-192-168-87-214`) were excluded, causing `total_nodes: 0` → empty `per_node_summary` → frontend condition `coverageData?.per_node_summary?.length > 0` evaluated false → entire Per-Node Alternatives panel hidden.

**Fix Applied:**

| # | File | Change |
|---|------|--------|
| R-5a | `backend/workers/tasks/reconciliation_worker.py` | Changed instance filter from `Instance.instance_id.like('i-%')` → `Instance.instance_id.like('i-%') \| Instance.instance_id.like('ip-%')` at line 59 (coverage computation). Line 265 left as `i-%` only since it validates against AWS EC2 API results. |

**Verification:** After fix, coverage report for spot-demo-1 cluster:
- `total_nodes: 3` (was 0)
- All 3 nodes `COVERED` with 224 alternatives each
- Per-Node Alternatives panel now visible in UI

### Files Modified (Round 2)

| File | Issue(s) |
|------|----------|
| `backend/workers/tasks/cache_builder.py` | R-4a |
| `backend/scrapers/spot_advisor_scraper.py` | R-4b |
| `backend/api/ascpai_routes.py` | R-4c |
| `backend/workers/tasks/reconciliation_worker.py` | R-5a |

---

## Runtime Issue Fixes — Round 3

### R-6: Market View Shows Irrelevant Pools (No Per-Cluster Resource Filtering)

**Symptom:** For a cluster with t3.medium nodes (2 vCPU, 4 GB), the Market View recommended pools like `i7i.12xlarge` (48 vCPU), `c7i.24xlarge` (96 vCPU), and `r7i.12xlarge` (48 vCPU). The "Your Saving" column showed 70-78% savings by comparing each pool's spot price to its own on-demand price instead of the source node's OD price.

**Root Cause (3 issues):**

1. **No per-cluster resource filtering** — The market-view endpoint (`GET /api/v1/ascpai/clusters/{id}/market-view`) loaded ALL pools from the global `market_view_cache:{region}` (built hourly without cluster context) and never applied vCPU, memory, architecture, or price filters. Every instance type × AZ combination in the region was shown.

2. **source_od_price falling back to 0** — The endpoint tried to get the source OD price from `Instance.price` (DB field), but the Instance model had `price=0.0` for running nodes. Without a `ClusterBaseline` either, `source_od_price` stayed at 0, causing `customer_savings_pct` to fall back to `intrinsic` savings (pool's own OD price vs spot price). This made a $3.12/hr `r7i.12xlarge` spot instance appear to save 72% compared to its own $11.36/hr OD price — completely misleading for a $0.0448/hr t3.medium cluster.

3. **No Redis fallback for source OD price** — The endpoint had no fallback to look up the OD price from Redis (`ondemand_price:{region}:{type}`) when the DB field was empty.

**Fixes Applied:**

| # | File | Change |
|---|------|--------|
| R-6a | `backend/api/ascpai_routes.py` | Added per-cluster resource profile computation: queries all running instances, derives vCPU/memory/architecture via `_lookup_specs()`, computes filter bounds (min_vcpu, max_vcpu=min*2, min_mem=min*0.5, max_mem=max*2) |
| R-6b | `backend/api/ascpai_routes.py` | Added 4 filter gates in the pool enrichment loop: architecture match, vCPU range, memory range, and price gate (`spot_price < source_od_price`) |
| R-6c | `backend/api/ascpai_routes.py` | Added Redis fallback for `source_od_price`: when `Instance.price` is 0 and no baseline exists, looks up `_lookup_od_price(redis, region, primary_instance_type)` from Redis |
| R-6d | `backend/api/ascpai_routes.py` | Added `resource_filter` field to API response showing applied filter bounds (vcpu_range, memory_gb_range, architectures, source_od_price_hr) |

**Verification:** For spot-demo-1 cluster (3× t3.medium, ap-south-1):
- Before: 269 pools shown (including 48+ vCPU instances), customer_savings based on pool's own OD price
- After: 21 pools (248 eliminated), all 2 vCPU / 2-8 GB memory, amd64 arch
- Filter: vcpu=[2,4], mem=[2.0, 8.0]GB, source_od_price=$0.0448/hr
- Customer savings correctly calculated against t3.medium OD price
- No i7i.12xlarge, r7i.12xlarge, c7i.24xlarge, or any oversized pools

### Files Modified (Round 3)

| File | Issue(s) |
|------|----------|
| `backend/api/ascpai_routes.py` | R-6a, R-6b, R-6c, R-6d |

---

## Round 4 — R-7: OD Prices Wrong / Missing for Most Instance Types

### Problem
- UI shows m7i.large ap-south-1c: spot=$0.0302, **OD=$0.0990** — AWS official OD is **$0.1061**
- Only **12** OD prices existed in Redis for ap-south-1 (all from hardcoded default set: m5, c5, r5, t3)
- All other instance types (~600+) used `_estimate_od_price()` fallback with hardcoded family tables
- `_FAMILY_BASE_OD['m7i'] = 0.099` was wrong (real = $0.1061)

### Root Cause
`_get_required_instance_types_for_region()` in `aws_pricing_service.py` returned only **12 hardcoded types** (m5.large/xlarge/2xlarge, c5.large/xlarge/2xlarge, r5.large/xlarge/2xlarge, t3.medium/large/xlarge). It had a `TODO` to query actual cluster types but never implemented it. The `refresh_ondemand` task (every 12h) only fetched OD prices from AWS Pricing API for those 12 types — so m7i, m6i, c7i, c6g, r7i, and hundreds of other instance types had **no real OD price** in Redis.

### Fix

| ID | File | Change |
|----|------|--------|
| R-7a | `backend/services/aws_pricing_service.py` | Rewrote `_get_required_instance_types_for_region()`: scans Redis `spot_price:{region}:*` keys to collect ALL unique instance types, merges with cluster-active types from DB, plus baseline default set. Now returns 600+ types instead of 12. |
| R-7b | `backend/workers/tasks/cache_builder.py` | Updated `_FAMILY_BASE_OD` fallback table: m7i 0.099→0.1008, m7g 0.080→0.0816, c7i 0.088→0.089, c7g 0.070→0.0725, r7i 0.130→0.1323, r7g 0.104→0.1071 (us-east-1 reference values) |

**Verification:**
- Before: 12 OD prices in Redis for ap-south-1, m7i.large OD = $0.099 (estimated)
- After: **678** OD prices in Redis for ap-south-1, m7i.large OD = **$0.10605** (from AWS Pricing API)
- Cache rebuild: `no_od_price=0` (was previously many), all 1991 spot pools have real OD prices
- Market view cache: m7i.large ap-south-1c → spot=$0.0302 od=$0.1061 savings=71.5%

### Files Modified (Round 4)

| File | Issue(s) |
|------|----------|
| `backend/services/aws_pricing_service.py` | R-7a |
| `backend/workers/tasks/cache_builder.py` | R-7b |

---

## Round 5 — R-8: Market View Baseline = Highest-Cost OD Node

### Problem
Market view was using the **primary/first OD node** as the baseline for savings calculations and price gate. This hides the maximum potential savings and can filter out valid opportunities when a cluster has mixed instance sizes. Additionally, upper bounds on vCPU/memory (from R-6) blocked larger spot pools that could be valid alternatives for the most expensive node.

### Design Decision
The baseline OD price should be the **highest-cost node** among running instances because:
- Maximises displayed savings (largest denominator)
- Price gate `spot_price < highest_od_price` includes all valid opportunities
- Larger spot pools that are cheaper than the most expensive node are shown
- Minimum resource constraints (smallest node's vCPU/memory) still filter out undersized pools

### Fix

| ID | File | Change |
|----|------|--------|
| R-8a | `backend/api/ascpai_routes.py` | Cluster profile now tracks `_baseline_od_price` = highest OD price among all running nodes (looked up from `Instance.price` → Redis fallback). `_baseline_instance_type` tracks which node provided the baseline. |
| R-8b | `backend/api/ascpai_routes.py` | Removed upper bounds: `_filter_max_vcpu` and `_filter_max_mem` eliminated. Only `_filter_min_vcpu` and `_filter_min_mem` enforced — large pools can appear if they're cheaper than the baseline. |
| R-8c | `backend/api/ascpai_routes.py` | `source_od_price` derived from `_baseline_od_price` (highest node) instead of first OD Instance query. Removed redundant `primary_od` query. |
| R-8d | `backend/api/ascpai_routes.py` | `source_node` response includes `baseline_method: "highest_cost_od_node"`, `resource_filter` reports `min_vcpu`, `min_memory_gb`, `baseline_od_price_hr`, `baseline_instance_type` (no range fields). |

**Verification — spot-demo-1 (3× t3.medium, ap-south-1):**
- baseline: t3.medium @ $0.0448/hr (highest = only type)
- 28 valid pools (was 21 with upper bounds), 294 eliminated by gates
- m7i.large ap-south-1c: spot=$0.0302 od=$0.1061 customer_savings=32.59%
- No upper vCPU/memory bound — pools up to any size visible if spot < $0.0448

**Verification — k8s-cluster (4 nodes, us-east-1):**
- baseline: c5.large @ $0.085/hr
- 48 valid pools, 204 eliminated
- i4i.large us-east-1c: spot=$0.0411 od=$0.1820 savings=51.65%

### Files Modified (Round 5)

| File | Issue(s) |
|------|----------|
| `backend/api/ascpai_routes.py` | R-8a, R-8b, R-8c, R-8d |

---

## Round 6 — R-9: Per-Node Alternatives Positive/Negative Split + Market-View EV Ranking

### Problem

**Per-node alternatives** showed pools with negative savings (more expensive than the current node) mixed in with positive-savings options. The old `DecisionEngine.rank_for_node()` used the node's *spot price* (not OD) as baseline, and trade-off/tier-expansion gates let expensive pools through. No separation of positive vs negative savings sets.

**Market view** used a weighted composite score (`0.40 × savings + 0.40 × safety + 0.20 × ML`) instead of the expected-value formula specified by the user.

### Root Cause

1. **Per-node**: `rank_for_node()` Gate 6 (`_apply_double_gate`) compared pools to the node's spot price, not its OD price. Gates 7-8 (trade-off, tier expansion) further relaxed filters, allowing negative-savings pools even when plenty of positive ones existed.
2. **Market view**: Ranking used arbitrary weight coefficients instead of the EV formula `savings_pct × (1 - risk_probability)`.

### Fix Details

| ID | File | Change |
|----|------|--------|
| R-9a | `backend/api/ascpai_routes.py` | **Complete rewrite of `get_node_alternatives()`** — no longer delegates to `DecisionEngine.rank_for_node()`. Directly loads global pool cache, filters by min vCPU/memory/arch/risk ceiling (no upper bounds), computes `savings_pct = (node_od_price - spot_price) / node_od_price` and `expected_value = savings_pct × (1 - risk_probability)`. Splits into positive (savings ≥ 0) and negative (savings < 0) sets. Positive: always shown, sorted by EV desc. Negative: shown ONLY if positive set is empty AND `savings_pct ≥ -(tradeoff_pct/100)` AND `pool_risk < node_risk`. Response includes `current_node`, `filters_applied`, `positive_count`, `negative_savings_shown`. |
| R-9b | `backend/api/ascpai_routes.py` | **Market-view enrichment updated with EV**. Added `risk_probability` field (0-1 range). Compute `expected_value = customer_savings × (1 - risk_probability)`. `final_score = EV × capacity_boost`. Moved gate filters (spot ≤ 0, resource profile, price gate) BEFORE enrichment to avoid wasted computation. Removed old weighted composite (`0.40 × savings + 0.40 × safety + 0.20 × ML`), soft_penalty, ml_tier from scoring. |
| R-9c | `backend/api/ascpai_routes.py` | **Market-view sort updated**: Primary sort by `expected_value` desc (within capacity group: verified > unverified > unavailable). Default sort_by changed from `final_score` to `expected_value`. Added `expected_value` and `risk_probability` to valid sort keys. |

**Verification — k8s-cluster (c5.large, us-east-1):**

*Market view:*
- 48 valid pools, 277 eliminated, baseline $0.085/hr
- #1 c7a.medium us-east-1f: spot=$0.0078 savings=90.8% risk=0.2122 EV=0.7155
- All positive savings: ✓, EV monotonically decreasing: ✓

*Per-node alternatives (ip-192-168-97-74, c5.large):*
- positive_count=25, negative_savings_shown=false
- #1 c7a.medium us-east-1f: spot=$0.0078 savings=90.82% risk=0.2122 EV=0.7155

**Verification — spot-demo-1 (t3.medium, ap-south-1):**

*Market view:*
- 28 valid pools, 294 eliminated, baseline $0.0448/hr
- #1 t3a.small ap-south-1a: spot=$0.0052 savings=88.4% risk=0.3122 EV=0.6080
- All positive savings: ✓, EV monotonically decreasing: ✓

*Per-node alternatives (ip-192-168-87-214, t3.medium):*
- positive_count=11, negative_savings_shown=false
- #1 m7i.large ap-south-1c: spot=$0.0300 savings=33.04% risk=0.2122 EV=0.2603

### Files Modified (Round 6)

| File | Issue(s) |
|------|----------|
| `backend/api/ascpai_routes.py` | R-9a, R-9b, R-9c |
