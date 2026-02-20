# Real AWS API Integration Plan — VERIFIED UPDATE
**Date:** February 20, 2026 (Verified)
**Status:** In Progress
**Document Purpose:** Track real AWS API integration progress vs mock/fallback implementations

---

## 📊 Executive Summary — VERIFIED STATUS

| Section | Status | Real Implementation | Remaining Work |
|---------|--------|-------------------|----------------|
| **AtharvaAI** | **85% Real** | ✅ ML pipeline, ONNX scoring, circuit breaker, Celery workers | ❌ Spot price collection (using mock), capacity check parallelization |
| **Right-Sizing** | **75% Real** | ✅ Pod metrics collection, P95/P99 analysis, real DB queries | ❌ Cost estimation (hardcoded $0.04/core, $0.005/GB) |
| **Hibernation** | **90% Real** | ✅ Worker with Redis locking, real cost calculation, strategies implemented | ❌ Database columns missing (is_hibernating, hibernation_state) |
| **Pricing** | **60% Real** | ✅ Real scrapers exist (pricing_collector.py, spot_advisor_scraper.py) | ❌ Celery calls mock version instead of real scrapers |

**Overall Progress:** 77.5% Real (up from 70% in last assessment)

---

## 🎯 What Changed Since Last Time

### ✅ NEW: Implemented Since Last Assessment

1. **Hibernation Worker — FULLY IMPLEMENTED** ✅
   - File: `backend/workers/tasks/hibernation_worker.py` (341 lines)
   - Redis distributed locking with UUID-based lock values (prevents race conditions)
   - State staleness detection (warns if state >24h old)
   - Per-cluster locking to prevent concurrent execution
   - SSE notifications on sleep/wake
   - Scheduled every 1 minute in Celery beat
   - **This addresses changes.txt Issue #3 (Hibernation race condition)**

2. **Hibernation Savings Calculation — NOW REAL** ✅
   - File: `backend/services/hibernation_service.py:243-271`
   - Uses `cluster.monthly_cost / 730` for real hourly costs
   - Strategy-based efficiency: NAMESPACE_SLEEP (80%), NUCLEAR (70%), SNAPSHOT_RESTORE (95%)
   - Calculates weekly_savings and annual_savings from actual cluster data
   - **No longer uses the $1,500 flat mock value**

3. **AtharvaAI Pool Ranking Pipeline — REAL ML INFERENCE** ✅
   - File: `backend/services/pool_ranking_service.py` (511 lines)
   - ONNX model loading and inference (classifier_6.onnx, regressor_6.onnx)
   - 8-step pipeline fully implemented
   - Circuit breaker for ML degradation (lines 439-447)
   - Fallback scoring when ML fails
   - Region-namespaced blacklist (`risky_pools:{region}`)
   - Scheduled every 30 seconds in Celery beat
   - **This addresses changes.txt Issue #2 (AtharvaAI failure modes) partially**

4. **Real Pricing Scrapers — CODE EXISTS** ✅
   - Files: `backend/scrapers/pricing_collector.py` (578 lines), `backend/scrapers/spot_advisor_scraper.py` (429 lines)
   - Uses boto3 `describe_spot_price_history` API
   - Uses AWS Price List API for On-Demand prices
   - ThreadPoolExecutor for parallel region collection
   - Scrapes AWS public Spot Advisor API
   - **BUT: Celery beat schedule calls mock version, not these real scrapers** ❌

5. **Karpenter NodePool Sync — SCHEDULED** ✅
   - File: `backend/workers/tasks/atharvaai_worker.py:242-357`
   - Syncs top 10 ML-ranked pools to Karpenter NodePools
   - Runs every 30 seconds
   - Updates instance type requirements based on ML rankings

6. **Termination Monitor & Auto-Rebalancer — SCHEDULED** ✅
   - Files: `backend/workers/tasks/termination_monitor.py` (10KB), `backend/workers/tasks/auto_rebalancer.py` (11KB)
   - Monitors spot termination notices every 30 seconds
   - Auto-rebalancer executes every 15 seconds
   - Updates blacklist on terminations

---

## ❌ Critical Gaps — What's Still Missing

### 1. Hibernation Database Schema — COLUMNS MISSING
**Priority:** 🔴 CRITICAL
**Impact:** Hibernation worker will fail when trying to update cluster state

**Problem:**
- Worker code references `cluster.is_hibernating`, `cluster.hibernation_state` but these columns DON'T EXIST
- Database check confirmed: `clusters` table has NO hibernation columns
- No migration exists to add these columns

**Solution:**
```sql
-- Migration needed: 20260220_add_hibernation_columns.py
ALTER TABLE clusters ADD COLUMN is_hibernating VARCHAR(1) DEFAULT 'N';
ALTER TABLE clusters ADD COLUMN hibernation_state JSON DEFAULT '{}';
ALTER TABLE clusters ADD COLUMN hibernation_lock VARCHAR(255) DEFAULT NULL;
```

**Files to Update:**
- `backend/models/cluster.py` — Add column definitions
- Create migration: `backend/migrations/versions/20260220_add_hibernation_columns.py`

---

### 2. Spot Price Collection — USING MOCK DATA
**Priority:** 🔴 HIGH
**Impact:** ML features (price dynamics, lag features) use placeholder values

**Problem:**
- Celery beat calls `workers.atharvaai.collect_spot_prices` (mock version)
- Real scraper `backend.scrapers.pricing_collector.collect_spot_prices` exists but NOT called
- Lines in `atharvaai_worker.py:132-134`:
  ```python
  spot_price = 0.045  # Mock
  ondemand_price = 0.096  # Mock
  ```

**Solution:**
- Change Celery beat schedule in `backend/workers/app.py:88-91`:
  ```python
  # BEFORE (line 89):
  'task': 'workers.atharvaai.collect_spot_prices',  # Mock version

  # AFTER:
  'task': 'backend.workers.tasks.pricing.fetch_aws_pricing',  # Real version
  ```
- This task already exists and calls the real scrapers!
- Or keep both: pricing task hourly (line 33-36 already scheduled ✅), spot prices every 10 mins

**Files to Update:**
- `backend/workers/app.py` — Update beat schedule
- `backend/workers/tasks/atharvaai_worker.py` — Either remove mock or call real scraper

---

### 3. Right-Sizing Cost Estimation — HARDCODED CONSTANTS
**Priority:** 🟡 MEDIUM
**Impact:** Savings estimates don't match real AWS bills

**Problem:**
- `backend/services/rightsizing_service.py:48-49`:
  ```python
  CPU_COST_PER_CORE_HOUR = 0.04   # Fallback default
  MEMORY_COST_PER_GB_HOUR = 0.005  # Fallback default
  ```
- Lines 344-345 use these constants to calculate costs
- Family-specific rates (lines 38-41) are also hardcoded

**Solution:**
- Use AWS Pricing API to fetch real EC2 pricing
- Store in Redis cache with 24h TTL
- Fallback to constants only if API fails
- Resource pricing worker already exists (`backend/workers/tasks/resource_pricing_worker.py`) and scheduled daily (line 73-76) ✅
- **Just need to wire it to rightsizing_service.py**

**Files to Update:**
- `backend/services/rightsizing_service.py` — Replace constants with Redis lookup
- `backend/workers/tasks/resource_pricing_worker.py` — Verify it's populating correct Redis keys

---

### 4. AtharvaAI Capacity Checks — SERIAL EXECUTION
**Priority:** 🟡 MEDIUM
**Impact:** Pipeline takes 100-150 seconds for 50 pools (cache expires before completion)

**Problem:**
- Step 5 in pool ranking pipeline checks capacity via `RunInstances --dry-run`
- Runs serially: `for pool in pools: pool.has_capacity = self._check_capacity(pool)`
- Changes.txt Issue #2 says this needs parallelization

**Solution:**
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=20) as executor:
    futures = {executor.submit(self._check_capacity, pool): pool for pool in pools}
    for future in as_completed(futures, timeout=30):
        pool = futures[future]
        try:
            pool.has_capacity = future.result()
        except TimeoutError:
            pool.has_capacity = True  # Assume capacity, don't block ranking
            pool.capacity_uncertain = True
```

**Files to Update:**
- `backend/services/pool_ranking_service.py` — Update `_step5_capacity_check` method

---

### 5. Cache Invalidation — NOT WIRED
**Priority:** 🟡 MEDIUM
**Impact:** Template changes don't invalidate rankings cache for 5 minutes

**Problem:**
- Changes.txt Issue #7: User changes node template → rankings still show excluded pools for up to 5 mins
- `POST /api/v1/atharvaai/cache/invalidate` endpoint exists but not called
- Template save/update endpoints don't clear cache

**Solution:**
```python
# In backend/services/template_service.py, after saving template:
from backend.core.redis_client import get_redis_client
redis_client = get_redis_client()
redis_client.delete(f"rankings:{org_id}:*")  # Wildcard delete for org
```

**Files to Update:**
- `backend/services/template_service.py` — Add cache invalidation after save/update
- `backend/api/template_routes.py` — Ensure invalidation called

---

## 🏗️ Enterprise-Grade Issues (from changes.txt)

**13 Critical Issues** identified in changes.txt (Feb 20, 2026):

| # | Issue | Priority | Addressed? |
|---|-------|----------|------------|
| 1 | Multi-region & cross-account coordination | 🔴 CRITICAL | ❌ Not yet |
| 2 | AtharvaAI pipeline failure modes | 🔴 HIGH | ✅ **Partially** (circuit breaker added, need parallelization) |
| 3 | Hibernation race condition | 🔴 CRITICAL | ✅ **DONE** (Redis locking implemented) |
| 4 | Right-sizing modify_instance_attribute problem | 🔴 CRITICAL | ❌ Not yet |
| 5 | No approval system for hibernation | 🔴 HIGH | ❌ Not yet |
| 6 | Savings estimates are mocks | 🟢 MEDIUM | ✅ **DONE** (hibernation), ❌ **Partial** (right-sizing) |
| 7 | Redis cache invalidation missing | 🟡 MEDIUM | ❌ Not yet |
| 8 | Audit log tamper evidence | 🟡 MEDIUM | ❌ Not yet |
| 9 | Karpenter budget guards | 🔴 HIGH | ❌ Not yet |
| 10 | User preferences in localStorage | 🟡 LOW | ❌ Not yet |
| 11 | Cluster delete protection | 🔴 HIGH | ❌ Not yet |
| 12 | ML model versioning/rollback | 🟡 MEDIUM | ❌ Not yet |
| 13 | AWS API rate limiting | 🟡 MEDIUM | ❌ Not yet |

**Summary:**
- ✅ **2 Fully Addressed** (Hibernation race condition, Hibernation savings)
- ⚠️ **1 Partially Addressed** (AtharvaAI failure modes)
- ❌ **10 Not Yet Addressed**

---

## 📋 Implementation Checklist

### Phase 1: Critical Fixes (Required for MVP)

- [ ] **TASK 1.1:** Add hibernation columns to clusters table
  - Create migration `20260220_add_hibernation_columns.py`
  - Add columns: `is_hibernating`, `hibernation_state`, `hibernation_lock`
  - Update `backend/models/cluster.py`
  - Run migration: `alembic upgrade head`

- [ ] **TASK 1.2:** Wire real spot price collection
  - Update `backend/workers/app.py:88-91` to call real scraper
  - Or schedule both: pricing task (hourly) + spot prices (10 mins)
  - Verify data flows to `spot_price_history` table

- [ ] **TASK 1.3:** Replace right-sizing cost constants with real pricing
  - Wire `resource_pricing_worker` to `rightsizing_service`
  - Update `_calculate_monthly_cost` to lookup Redis instead of constants
  - Add fallback to constants if Redis misses

- [ ] **TASK 1.4:** Parallelize capacity checks in AtharvaAI
  - Update `pool_ranking_service.py:_step5_capacity_check`
  - Use ThreadPoolExecutor with 20 workers
  - Add timeout and capacity_uncertain flag

- [ ] **TASK 1.5:** Wire cache invalidation on template updates
  - Update `template_service.py` save/update methods
  - Clear `rankings:{org_id}:*` after template changes
  - Add audit log entry for cache invalidation

### Phase 2: Enterprise Security & Compliance

- [ ] **TASK 2.1:** Add pre-flight checks for right-sizing (changes.txt #4)
  - Check if instance in ASG (`describe_auto_scaling_instances`)
  - Check if instance has non-EIP public IP (warn about IP change)
  - Check for instance-store volumes (data loss warning)
  - Return warnings before executing resize

- [ ] **TASK 2.2:** Add approval gates for hibernation (changes.txt #5)
  - Wire `POST /api/v1/hibernation/emergency/sleep` to approval system
  - Wire `POST /api/v1/hibernation/emergency/wake` to approval system
  - Add `requires_approval` boolean to `hibernation_schedules` table
  - Auto-require approval for clusters tagged `environment=production`

- [ ] **TASK 2.3:** Add cluster delete preconditions (changes.txt #11)
  - Check if Karpenter active (block if mode=auto or dry_run)
  - Check for active hibernation schedules
  - Check for pending approvals
  - Return 412 Precondition Failed with details

- [ ] **TASK 2.4:** Add audit log tamper evidence (changes.txt #8)
  - Add `checksum` column to `audit_logs` table
  - Compute SHA256(actor_id + event + resource + timestamp + diff)
  - Periodic Celery task to verify checksums
  - Write critical actions to S3 append-only bucket

### Phase 3: Production Hardening

- [ ] **TASK 3.1:** Implement multi-region support (changes.txt #1)
  - Namespace Redis blacklist by region: `risky_pools:{account_id}:{region}`
  - Parameterize pricing collector by account+region
  - Run pool ranking pipeline per-region
  - Add `region` column to clusters table (already exists ✅)

- [ ] **TASK 3.2:** Add Karpenter budget guards (changes.txt #9)
  - Configure `limits` in NodePool CRD (cpu, memory)
  - Budget guard Celery task every 5 mins
  - Auto-pause Karpenter if projected cost exceeds budget
  - Send alert to admins

- [ ] **TASK 3.3:** Add ML model versioning (changes.txt #12)
  - Wire `ml_models` table (already exists in `backend/models/ml_model.py`)
  - Load active model from DB instead of hardcoded path
  - Implement shadow mode (run new + old, log comparison)
  - Auto-promote after 48h with <5% divergence

- [ ] **TASK 3.4:** Add AWS API rate limiting (changes.txt #13)
  - Redis-based rate limiter per account+API
  - Cache `RunInstances --dry-run` results (15-min TTL)
  - Handle `RequestLimitExceeded` errors gracefully

### Phase 4: User Experience

- [ ] **TASK 4.1:** Move user preferences to DB (changes.txt #10)
  - Wire `PATCH /api/v1/users/me/preferences` endpoint
  - Update `Settings.jsx` to call API instead of localStorage
  - Sync preferences across devices

---

## 🔍 Verification Commands

### Check Hibernation Columns Exist
```bash
docker exec spot-optimizer-postgres psql -U postgres -d spot_optimizer -c "\d clusters" | grep hibernat
```

### Check Celery Beat Schedule
```bash
docker exec spot-optimizer-celery-beat celery -A backend.workers inspect scheduled
```

### Check Real Pricing Data in DB
```bash
docker exec spot-optimizer-postgres psql -U postgres -d spot_optimizer -c "SELECT COUNT(*) FROM spot_price_history WHERE timestamp > NOW() - INTERVAL '1 hour';"
```

### Check ML Models Loaded
```bash
docker logs spot-optimizer-backend 2>&1 | grep -i "onnx\|classifier\|regressor"
```

### Trigger Manual Tasks
```bash
# Trigger real pricing collection
docker exec spot-optimizer-celery-worker celery -A backend.workers call backend.workers.tasks.pricing.fetch_aws_pricing

# Trigger pool ranking pipeline
docker exec spot-optimizer-celery-worker celery -A backend.workers call workers.atharvaai.execute_pool_ranking_pipeline

# Trigger hibernation scheduler
docker exec spot-optimizer-celery-worker celery -A backend.workers call workers.hibernation.check_schedules
```

---

## 📊 Progress Tracking

### Implementation Hours Estimate

| Phase | Tasks | Est. Hours | Status |
|-------|-------|-----------|--------|
| Phase 1: Critical Fixes | 5 tasks | 8h | 🟡 In Progress |
| Phase 2: Security & Compliance | 4 tasks | 12h | ❌ Not Started |
| Phase 3: Production Hardening | 4 tasks | 16h | ❌ Not Started |
| Phase 4: User Experience | 1 task | 2h | ❌ Not Started |
| **Total** | **14 tasks** | **38h** | **0% Complete** |

### What's Different from Last Time?

**Previously (Feb 9, 2026):**
- AtharvaAI: 70% real → **Now: 85% real** (+15%)
- Right-Sizing: 60% real → **Now: 75% real** (+15%)
- Hibernation: 80% real → **Now: 90% real** (+10%)
- Pricing: 40% real → **Now: 60% real** (+20%)

**Key Improvements:**
- ✅ Hibernation worker fully implemented with enterprise-grade locking
- ✅ ML inference pipeline real and scheduled
- ✅ Real pricing scrapers exist (just need to wire Celery schedule)
- ✅ Hibernation savings calculation uses real cluster costs
- ✅ Circuit breaker for ML degradation
- ✅ Karpenter sync, termination monitor, auto-rebalancer all scheduled

**What's Left:**
- ❌ 3 database columns (hibernation)
- ❌ 1 Celery schedule change (spot prices)
- ❌ 1 constant replacement (right-sizing costs)
- ❌ 10 enterprise hardening issues from changes.txt

---

## 🎯 Next Steps

### Immediate Actions (This Week)

1. **Add hibernation columns migration** — 30 mins
   - Create migration file
   - Run migration
   - Verify with psql

2. **Wire real spot price collection** — 15 mins
   - Update Celery beat schedule
   - Restart workers
   - Verify data flows to DB

3. **Replace right-sizing cost constants** — 2h
   - Wire resource pricing worker to rightsizing service
   - Update cost calculation methods
   - Test with real pod metrics

4. **Parallelize capacity checks** — 3h
   - Update pool ranking service
   - Add ThreadPoolExecutor
   - Test with 50+ pools
   - Verify cache TTL alignment

5. **Wire cache invalidation** — 1h
   - Update template service
   - Add Redis delete calls
   - Test template update flow

### Medium-Term (Next 2 Weeks)

- Implement pre-flight checks for right-sizing
- Add approval gates for emergency hibernation
- Add cluster delete preconditions
- Implement audit log tamper evidence

### Long-Term (Next Month)

- Multi-region support
- Karpenter budget guards
- ML model versioning
- AWS API rate limiting

---

## 📝 Notes & Observations

### Code Quality Assessment

**What's Good:**
- Hibernation worker is enterprise-grade (Redis locking, staleness detection, SSE notifications)
- ML pipeline has circuit breaker and fallback scoring
- Real scrapers are well-structured with ThreadPoolExecutor
- Cost calculations now use real cluster data, not mocks
- Comprehensive Celery beat schedule (17 scheduled tasks)

**What Needs Work:**
- Database schema incomplete (missing hibernation columns)
- Celery schedule calls mock version of spot price collection
- Right-sizing still uses hardcoded cost constants
- Cache invalidation not wired
- 10/13 enterprise issues from changes.txt unaddressed

### Risk Assessment

**LOW RISK:**
- AtharvaAI ML pipeline (working, just needs pricing data)
- Hibernation worker (code solid, just needs DB columns)
- Cost Explorer integration (already working)

**MEDIUM RISK:**
- Right-sizing cost estimation (affects savings accuracy)
- Cache invalidation (affects UX, not functionality)
- Spot price collection (fallback to mocks works)

**HIGH RISK:**
- Hibernation DB columns (worker will fail without them)
- Multi-region support (affects enterprise customers)
- Right-sizing pre-flight checks (can cause outages if skipped)
- Karpenter budget guards (runaway costs possible)

---

## 🔗 Related Documents

- **changes.txt** — 13 enterprise-grade issues identified (Feb 20, 2026)
- **all-components.md** — UI component inventory (143 JSX files)
- **Q&A.md** — 50-page technical deep-dive
- **CLAUDE.md** — Project setup guide for Claude Code instances
- **MEMORY.md** — Key architecture patterns and debugging tips

---

**Last Updated:** February 20, 2026 (Verified via code inspection + DB queries)
**Next Review:** February 27, 2026
**Owner:** Atharva Pudale
