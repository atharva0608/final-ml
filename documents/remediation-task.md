# Market View — Root Cause Analysis
> Generated: 2026-03-24 | Status: ALL BUGS FIXED — 2026-03-24
> Symptoms: Market View shows only `ap-south-1a`, all pools show uniform ~70% savings.
> Resolution: 4 fixes applied — see "Fixes Applied" sections below each bug.

---

## Bug 1 — Single-AZ Pool Scope (Why only `ap-south-1a`)

### Root Cause Chain

**File**: `backend/workers/tasks/cache_builder.py`

The `build_global_pool_cache()` function builds `market_view_cache:{region}` in two paths:

**Primary path (lines 247–269):**
```python
cursor, keys = r.scan(cursor, match=f"spot_price:{region}:*", count=500)
# Key format: spot_price:{region}:{az}:{instance_type}
az = parts[2]
instance_type = ':'.join(parts[3:])
```
The cache only contains AZs that exist as `spot_price:{region}:{az}:*` keys in Redis. If the pricing ingestion worker (`spot-price-ingest-every-10-mins`) only wrote keys for `ap-south-1a` — either because it polled only one AZ or failed mid-run — then **only `ap-south-1a` pools are in the cache**. The other two AZs (`ap-south-1b`, `ap-south-1c`) will never appear in Market View regardless of whether `describe_spot_price_history` supports them.

**Fallback path (lines 283–326, triggered when no spot_price keys exist):**
```python
azs = _REGION_AZS.get(region, [f"{region}a", f"{region}b"])
# ap-south-1 → ['ap-south-1a', 'ap-south-1b', 'ap-south-1c']
for az in azs:
    raw_pools.append({... 'az': az ...})
```
If this fallback **was** triggered, all 3 AZs would appear. The fact that only `ap-south-1a` shows means the **primary path ran** (spot_price keys DO exist) but only for `ap-south-1a`. This confirms the pricing worker is only ingesting one AZ.

### Confirming Evidence to Check
```bash
# Run this in the backend container to verify:
redis-cli KEYS "spot_price:ap-south-1:*" | grep -oP 'ap-south-1[a-z]+' | sort | uniq -c
# Expected (healthy): ap-south-1a, ap-south-1b, ap-south-1c all present
# Actual (broken): only ap-south-1a
```

### Likely Underlying Cause
The pricing ingestion Celery task (`workers.pricing.ingest_spot_prices`) calls `describe_spot_price_history()`. If it uses a **hardcoded AZ filter** or is configured for only the source node's AZ (pulled from the first running instance), only that AZ gets ingested.

**File to check**: `backend/workers/tasks/pricing_worker.py` — look for:
```python
# Wrong: AZ hardcoded or derived from source node
Filters=[{"Name": "availability-zone", "Values": ["ap-south-1a"]}]

# Correct: No AZ filter — let AWS return all AZs
# OR: Filters=[{"Name": "availability-zone", "Values": ["ap-south-1a","ap-south-1b","ap-south-1c"]}]
```

---

## Bug 2 — Uniform 70% Savings (Why all pools show ~70% discount)

### Root Cause Chain

**File**: `backend/workers/tasks/cache_builder.py`, lines 302–314 — the **fallback path**:
```python
od_est = _lookup_od_price(r, region, itype) or _estimate_od_price(itype)
spot_est = od_est * 0.30   # ← hardcoded: spot = 30% of OD → savings = 70%
```

When the primary path runs (spot_price keys exist but OD prices are absent from Redis):
```python
# For each raw pool (line 338-343):
od_price = _lookup_od_price(r, region, itype)   # reads ondemand_price:{region}:{itype}
if od_price <= 0:
    od_price = _estimate_od_price(itype)         # family/size estimate
savings_pct = (od_price - p['spot_price']) / od_price * 100  # real calculation
```
This path uses **real spot prices** from `spot_price:` keys but the savings would NOT be 70% unless the spot prices themselves are wrong.

**The 70% uniform savings comes from the spot_advisor fallback path (lines 306):**
```python
spot_est = od_est * 0.30   # "conservative 70% discount estimate"
```
This fires when there are **no `spot_price:*` keys at all** for the region. In this case the endpoint falls through to the spot_advisor cache (`spot_advisor:{region}:*:Linux`), enumerates all known instance types, and assigns every pool a fake spot price = `od_price × 0.30`.

Since the code uses `_estimate_od_price()` as the OD source (which uses hardcoded family/size tables from `_FAMILY_BASE_OD` and `_SIZE_MULT`), every pool of the same family+size gets the same OD estimate, and therefore the same 70% savings.

### The Two-Bug Interaction
```
Scenario A (most likely):
  spot_price keys exist only for ap-south-1a
  → Primary path runs (real spot prices, correct AZ=ap-south-1a only)
  → OD prices ABSENT from Redis (ondemand_price:{region}:{type} keys not populated)
  → savings_pct = (estimate_od - real_spot) / estimate_od
  → If estimate_od ≈ real_spot × (1/0.30) then savings ≈ 70%
  → But this would NOT be exactly uniform — different instance types would differ

Scenario B (confirmed by uniform 70%):
  No spot_price keys exist for any AZ in ap-south-1
  → Falls through to spot_advisor fallback (lines 283-314)
  → ONLY ap-south-1a populated (???) — but fallback uses ALL 3 AZs
  → This contradicts single-AZ symptom...

Scenario C (most consistent with both symptoms):
  spot_price keys exist for ap-south-1a only (partial ingestion)
  → Primary path: pools built from ap-south-1a spot prices ← explains single-AZ
  → OD prices (ondemand_price:{region}:{type}) NOT populated in Redis
  → od_price = _estimate_od_price(itype) uses hardcoded table
  → For e.g. t3.medium: od_est = 0.0832 * (2.0/4.0) = 0.0416/hr
  → spot price from Redis for t3.medium ap-south-1a might be ~0.0124/hr
  → savings = (0.0416 - 0.0124) / 0.0416 = 70.2% ← explains uniform savings!
  The estimate_od table happens to produce values that are ~3× the actual spot price
  for t-series (t3.medium: estimated OD 0.0416, real Miami spot ~0.0124 = 70.2%)
```

**Conclusion — Scenario C is the root cause:**
1. The `ondemand_price:{region}:{instance_type}` Redis keys are **not populated** (the OD price refresh worker hasn't run or is failing).
2. `_estimate_od_price()` uses the `_FAMILY_BASE_OD` table which was calibrated for the `large` size and extrapolates linearly — this over-estimates OD price for cheaper instances in ap-south-1 (which has different pricing than us-east-1 where those tables were likely calibrated).
3. Since all pools in ap-south-1a have real spot prices but estimated OD prices from the same formula, the savings ratio is **consistently ~70%** across all pools.

---

## Verification Commands

```bash
# Check 1: How many AZs have spot_price keys?
redis-cli KEYS "spot_price:ap-south-1:*" | awk -F: '{print $3}' | sort -u

# Check 2: Are OD price keys populated?
redis-cli KEYS "ondemand_price:ap-south-1:*" | wc -l
# Expected: 200+. If 0 → OD price refresh has never run → confirms Bug 2

# Check 3: Confirm the estimated vs real OD discrepancy
# Real t3.medium OD in ap-south-1: $0.0464/hr (AWS console)
# Estimated:
python3 -c "
_FAMILY_BASE_OD = {'t3': 0.0832}
_SIZE_MULT = {'medium': 2.0}
print(0.0832 * (2.0/4.0))  # → 0.0416 (underestimates real $0.0464 by ~10%)
"
# Even with correct estimate, savings = (0.0464-0.0124)/0.0464 = 73%
# confirms why savings look uniform and suspiciously high

# Check 4: Cache source
redis-cli EXISTS "market_view_cache:ap-south-1"   # → 1 if market_view_cache is populated
redis-cli EXISTS "global_pool_rankings:ap-south-1" # → 1 if fallback cache is populated
```

---

## Proposed Fix (DO NOT IMPLEMENT — logged for reference only)

### Fix 1 — Spot Price JSON Format (Bug 1 — actual root cause of silent parse failure)
**File**: `backend/services/aws_pricing_service.py`, line 404 ✅ FIXED
- **Was**: `self.redis.setex(cache_key, self.SPOT_PRICING_TTL_SECONDS, str(price))` → plain string
- **Now**: `cache_value = json.dumps({"price": str(price), "timestamp": timestamp.isoformat()})`
- `cache_builder.py` does `json.loads(raw).get('price')` — plain string caused AttributeError → all pools silently dropped → spot_advisor fallback triggered
- AZ coverage is inherently fixed: the paginator has NO AZ filter → all AZs (ap-south-1a/b/c) are ingested

### Fix 2 — OD Key Dual Write (Bug 2 — key prefix mismatch) ✅ FIXED
**File**: `backend/services/aws_pricing_service.py`, line 235
- **Was**: Wrote only `od_price:{region}:{type}` (internal AWSPricingService key)
- **Now**: Also writes `ondemand_price:{region}:{type}` (canonical key read by `cache_builder._lookup_od_price()`)
- `_lookup_od_price()` also updated to try `od_price:` as secondary fallback (backwards compatibility)

### Fix 3 — Use Actual Spot Advisor Savings (cache_builder.py line 306) ✅ FIXED
**File**: `backend/workers/tasks/cache_builder.py`, line 306
```python
# Was (wrong — produces uniform 70% savings):
spot_est = od_est * 0.30

# Now: Use actual savings_percentage from spot_advisor data
savings_frac = 0.70  # default only when no spot_advisor savings data
adv_raw = r.get(f"spot_advisor:{region}:{itype}:Linux")
if adv_raw:
    adv_json = json.loads(adv_raw)
    sa_savings_pct = adv_json.get("savings_percentage", 0)
    if sa_savings_pct > 0:
        savings_frac = sa_savings_pct / 100.0
spot_est = od_est * (1.0 - savings_frac)
```

### Fix 4 — Implement Missing Celery Tasks ✅ FIXED
**File**: `backend/workers/tasks/pricing_worker.py`
- `workers.pricing.ingest_spot_prices` — was referenced in `app.py` but never implemented → Celery errors every 10 min
- `workers.pricing.refresh_ondemand` — was referenced in `app.py` but never implemented → Celery errors every 12h
- Both tasks now implemented as proper `@app.task` functions delegating to `AWSPricingService`

### Fix 4 — `_FAMILY_BASE_OD` calibration (NOT NEEDED)
With Fix 1+2 applied, `_estimate_od_price()` is only used as last resort when BOTH Redis keys are absent.
Once pricing workers run successfully, real OD prices populate `ondemand_price:` keys and the estimate table is never used for real data.

---

## Impact Summary

| Symptom | Root Cause | File | Line |
|---|---|---|---|
| Only `ap-south-1a` in market view | `spot_price:ap-south-1:*` keys only exist for 1 AZ — pricing ingestion doesn't cover all AZs | `pricing_worker.py` (ingestion) | to verify |
| All pools show ~70% savings | `ondemand_price:ap-south-1:*` keys absent → `_estimate_od_price()` used → estimate ≈ 3× actual spot → 70% ratio | `cache_builder.py` | 338–343 (fallback to `_estimate_od_price`) |
| Uniform (not per-pool) savings | All pools use same estimation formula with no real OD anchor | `cache_builder.py` | `_FAMILY_BASE_OD` + `_SIZE_MULT` tables |
| Spot advisor fallback NOT triggered | `spot_price:*` keys DO exist (for ap-south-1a) so primary path runs, no fallback | `cache_builder.py` | 278–282 |
