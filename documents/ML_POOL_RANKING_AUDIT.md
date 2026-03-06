# ML Pool Ranking & Redis Cache Audit

> **Audit date**: 2026-03-05  
> **Source**: Live Redis inspection + code trace of `pool_ranking_service.py`

---

## ✅ ML Pipeline — VERIFIED REAL

| Check | Status | Evidence |
|---|---|---|
| ONNX models exist | ✅ | `ml_model/model/classifier_6.onnx` (risk), `regressor_6.onnx` (savings) |
| Models load at runtime | ✅ | `PoolRankingService.__init__()` loads via `onnxruntime.InferenceSession` |
| 45 features engineered | ✅ | `MLFeatureService.engineer_features()` called per pool |
| Circuit breaker | ✅ CLEAN | `degraded=None`, `fail_count=None` (no failures) |
| Risk threshold loaded | ✅ | From `ml_model/risk_threshold.json` → `optimal_threshold` |
| Real differentiated scores | ✅ | **32 unique ML scores**, 6 unique risk levels, 22 unique savings levels |

### ONNX Inference Pipeline (Step 7)
```
per pool:
  1. engineer_features() → 45-feature vector
  2. classifier_6.onnx → risk_probability (0-1)
  3. regressor_6.onnx → predicted_savings (0-1)
  4. Blend risk: 50% ONNX + 50% Spot Advisor rank
  5. Hard filter: REJECT if risk > threshold
  6. Savings fix: if regressor saturates (≥0.99), use Spot Advisor savings%
  7. Final: compute_expected_value(savings, risk) → ml_score
```

---

## ✅ Node Template Integration — VERIFIED

| Path | Template Used |
|---|---|
| `rank_pools()` | Full 8-step pipeline → Tier 2 `_apply_client_filters()` filters by arch, vCPU range, memory range, families, sizes, AZs, exclusions |
| `rank_pools_for_size()` | Creates `NodeTemplate(vcpu±1, memory±2GB)` → calls `rank_pools()` |
| `_step1_node_template_filter()` | Filters raw candidates before ML scoring (in direct pipeline) |
| Auto-rebalancer | Calls `rank_pools_for_size(vcpu, memory_gb, region, limit=8)` |
| Termination monitor | Creates `NodeTemplate(arch, vcpu_range, memory_range)` |
| AtharvaAI API | Builds `NodeTemplate` from cluster's DB template → `rank_pools()` |

---

## ⚠️ Redis Cache — 39 POOLS (NOT 500)

### Live Redis Data
```
KEY: global_pool_rankings:ap-south-1
Pools cached: 39
TTL remaining: 49 min (65 min max)

TOP 5:
  1. t3.nano:ap-south-1a    ML=0.5622  risk=0.1482  savings=0.6600  spot=$0.0016
  2. r5.4xlarge:ap-south-1a  ML=0.5281  risk=0.1482  savings=0.6200  spot=$0.3024
  3. m5.8xlarge:ap-south-1a  ML=0.5055  risk=0.1482  savings=0.5900  spot=$0.5568
  4. m6a.2xlarge:ap-south-1a ML=0.4873  risk=0.1482  savings=0.5700  spot=$0.1284
  5. c6a.2xlarge:ap-south-1a ML=0.4682  risk=0.1482  savings=0.5500  spot=$0.1010

BOTTOM 3:
  37. t3.large:ap-south-1c   ML=0.3273  risk=0.3181  savings=0.4800
  38. m6a.xlarge:ap-south-1a  ML=0.3082  risk=0.2482  savings=0.4100
  39. r6i.large:ap-south-1a   ML=0.2542  risk=0.3482  savings=0.5900

Coverage: 36 unique types | amd64+arm64 | 3 AZs
```

### Why 39, Not 500?

The global pipeline runs these filters before caching:

| Step | Filter | Pools remaining |
|---|---|---|
| Build candidates | 47 types × 3 AZs | ~141 |
| Step 3: Spot Advisor | Reject rank > 3 (>10% interruption) | ~100 |
| Step 4: Blacklist | Reject failure_count ≥ 3 | ~95 |
| Step 7: ML risk cutoff | Reject risk > 0.50 | ~70 |
| Dedup by type | Keep best AZ per type | **~39** |

The pipeline deduplicates by instance type in the global cache (keeps only 1 AZ per type). With 47 catalog types, after risk+blacklist filtering, 36 types survive → 39 entries (some have 2-3 AZs due to identical scores).

### Configuration
```python
GLOBAL_CACHE_LIMIT = 100    # pool_ranking_service.py L36
GLOBAL_CACHE_TTL = 65 * 60  # 65 minutes
```

The limit is 100 but only 39 survive the pipeline filters — this is correct behavior: the system only caches **pools that are actually safe**.

> [!IMPORTANT]
> If you want 500 global safe pools, the `GLOBAL_CACHE_LIMIT` constant at `pool_ranking_service.py` L36 can be changed to 500. However, the real bottleneck is the instance catalog (47 types × 3 AZs = 141 candidates). To reach 500 you'd need to expand the catalog with more instance families (r6g, c6g.xlarge, m7i, etc.) and/or keep multiple AZ entries per type.

---

## ✅ Global Pool Cache Service — CODE EXISTS but NOT CALLED

`GlobalPoolCacheService` (`global_pool_cache_service.py`) is a **separate** caching layer that stores top 50 pools in `spot:rankings:{region}`. Its `get_or_compute_global_rankings()` calls `PoolRankingService.rank_pools()` with a universal template.

**Status**: The Redis key `spot:rankings:ap-south-1` is **empty** — this service is not being invoked by any active Celery task or API route. The system uses `PoolRankingService._get_or_compute_global_rankings()` directly instead (key: `global_pool_rankings:{region}`).

This is not a bug — the `GlobalPoolCacheService` was designed as an optimization layer but the `PoolRankingService` already has its own two-tier caching built in.
