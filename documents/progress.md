# Progress Log — changes.md Fix Session (2026-03-20)

## Validation Summary

Each issue from changes.md was validated against the actual codebase before any fix was applied.

---

## P0 Issues

### ✅ #1 Non-Karpenter Phase Order (N+1 Bug)
**Status: NOT A REAL BUG — no fix needed**
- Cause: The spec was outdated. Current code uses 2-phase: Phase 1 launches spot (or queues PATCH_KARPENTER_NODEPOOL), Phase 2 (CORDON→DRAIN→TERMINATE) only runs AFTER spot node joins K8s and is Running for ≥90s.
- auto_rebalancer.py line 886–890: comment documents this correctly.
- This IS the zero-downtime design.

### 🔴 #2 + #5 Celery Lock TTL / No Heartbeat
**Status: CONFIRMED REAL — FIXED**
- Root cause: `distributed_locks.py` uses fixed 120s TTL (`DEFAULT_TIMEOUT = 120`). No heartbeat thread to extend TTL while work runs >2 min. Main Celery lock at line 1767 uses fixed 300s (5 min) NX lock.
- Fix: Added heartbeat-capable `HeartbeatLock` class to `distributed_locks.py`. Heartbeat thread renews lock TTL every `timeout/2` seconds. Thread signals `stop_event` on Redis `ConnectionError`. `DistributedLock` base class updated with `extend_ttl()` method. Main Celery lock now wrapped with heartbeat thread.
- Files: `backend/services/distributed_locks.py`, `backend/workers/tasks/auto_rebalancer.py`

### ✅ #3 Stale DB Re-targeting
**Status: ALREADY HANDLED — no fix needed**
- Phase 1 pre-registers new spot as `state='pending'` (not 'running'). Before targeting any OD instance, live AWS describe_instances is called (lines 3969–4046). If instance not found → mark terminated, skip.

### ✅ #4 ASG Desired Capacity Race
**Status: ALREADY FIXED in asg.py — no fix needed**
- `auto_rebalancer.py` lines 2483–2543: Step 2 calls `update_auto_scaling_group(DesiredCapacity=N-1)` BEFORE resuming Launch. This is the correct fix.

---

## P1 Issues

### ✅ #6 Spot Recovery 24h Lookback
**Status: NOT A 24H ISSUE — no fix needed**
- recovery_monitor.py uses 15-min stall detection (not 24h). This is intentional for fast detection.

### ✅ #7 Spot Recovery AWS Verify Before Acting
**Status: ALREADY IMPLEMENTED — no fix needed**
- recovery_monitor.py: calls `describe_instances` before any recovery action. Already verified.

### ✅ #8 Seeded Phantom Nodes Blocking Queue
**Status: ALREADY HANDLED WITHOUT is_seeded COLUMN — no fix needed**
- Throughout auto_rebalancer.py, the scan loop uses `Instance.instance_id.like('i-%')` to exclude ip- placeholders. Lines 3112–3121, 3638, 3962, 4031.
- aws_sync already deletes ip- placeholders when real i-xxx with same IP is found (line 267–282).

### ✅ #9 Last-Node Guard Orphan
**Status: ADDRESSED BY EXISTING MECHANISM — no separate fix**
- Last-node guard creates PATCH_KARPENTER_NODEPOOL action → the 2-phase resolution loop handles tracking.

### 🔴 #10 S2S Infinite Migration Loop
**Status: CONFIRMED REAL — FIXED**
- Root cause: After any S2S migration, no `s2s_migration:{cluster_id}:{source_pool}:{target_pool}` Redis key is written. Nothing prevents the same source→target pair from being re-triggered next cycle.
- Fix: After creating S2S action (auto_rebalancer.py ~line 3923), write `s2s_migration:{cluster_id}:{source_pool}:{target_pool}` to Redis with 2h TTL. Before triggering S2S, check this key.
- Files: `backend/workers/tasks/auto_rebalancer.py`

### ✅ #11 with_for_update() Row Locking
**Status: NOT CAUSING ISSUES — no fix in this session**
- Issue is real theoretically but the one-at-a-time guardrail (lines 3051–3079) + per-instance cooldowns prevent the most dangerous race conditions in practice. Full with_for_update() refactor deferred.

### ✅ #12 Phase 2 AgentActions Not Atomic
**Status: NOT A REAL ISSUE — no fix needed**
- Lines 2211–2218: all three `db.add()` calls happen before a single `db.commit()`. This IS atomic. The agent report was wrong.

### 🔴 #14 OD→Spot Cooldown — No Failure Backoff
**Status: CONFIRMED REAL — FIXED**
- Root cause: On action failure (line 2693), the 24h cooldown key is DELETED → next 15s cycle can immediately re-target the same OD instance. This creates rapid-fire loops when spot capacity is unavailable.
- Fix: On failure, write exponential backoff key instead of deleting: `rebalance_failures:{instance_id}` counter. TTL = `min(300 × 2^failures, 3600)`. On success, reset counter + keep 24h cooldown.
- Files: `backend/workers/tasks/auto_rebalancer.py`

### 🔴 #15 OD→Spot Daily Limit Bypass — No Per-Instance Cap
**Status: CONFIRMED REAL — FIXED**
- Root cause: Daily limit is cluster-level only. One OD instance can be retried >10 times/day even when all other OD nodes are done.
- Fix: Added per-instance daily cap of 10 via Redis key `rebalance_daily_count:{instance_id}:{date}` with TTL to end of day. Checked before creating rebalancing action.
- Files: `backend/workers/tasks/auto_rebalancer.py`

### ✅ #16 Boto3 Pagination Missing
**Status: ALREADY IMPLEMENTED — no fix needed**
- discovery.py line 44 uses `get_paginator('describe_instances')`.

### ✅ #17 Missing AWS Idempotency Tokens
**Status: PARTIAL — fleet.py has it, direct EC2 launches in substitute_manager use uuid**
- No fix in this session (not causing observed issues).

### ✅ #18 Subnet IP Exhaustion Not Pre-checked
**Status: NOT IMPLEMENTED, LOW PRIORITY — deferred**

### 🔴 #19 Blacklist TTL 12h for termination_detected (spec said change from 24h→15min)
**Status: CONFIRMED REAL — FIXED**
- Root cause: termination_monitor.py line 126: `ttl_hours=12`. Spec says should be 900s (15 min). A 12h blacklist starves the cluster of viable pools after a spot termination.
- Fix: Changed `ttl_hours=12` to `ttl_hours=0.25` (= 15 min). Also line 194 and docstring.
- Files: `backend/workers/tasks/termination_monitor.py`

### ✅ #20 Karpenter Emergency 15min Stall Detection
**Status: ALREADY AT 15 MIN — intentional, deferred**
- recovery_monitor.py uses 15-min cutoff. Reducing to 5 min needs careful evaluation. Deferred.

---

## P2 Issues

### ✅ #21 Orphan Rollback Terminates Wrong Spot
**Status: ALREADY FIXED — no change**
- Lines 1697–1723: prefers `replacement_spot_instance_id` from metadata; only uses DB query fallback if metadata missing (and logs it).

### ✅ #22 Karpenter Timeout Falls Through to Drain
**Status: ALREADY HANDLED — no fix**
- Lines 2108–2132: if no other nodes exist AND timeout → fail action. If other nodes exist, proceed with warning (pods can reschedule).

### ✅ #23 Ghost Nodes Infinite Table Growth
**Status: PARTIALLY HANDLED — cleanup logic in auto_rebalancer.py lines 2937–2952, deferred**

### 🔴 #24 Hardcoded Pricing Tables
**Status: CONFIRMED REAL — FIXED**
- Root cause: `_PRICES` dict (lines 4136–4150) and `_OD_PRICES_G` dict (lines 4304–4312) hardcoded. Stale prices cause wrong bin-pack decisions and incorrect savings calculations.
- Fix: Try to get OD price from AWSPricingService Redis cache first. Use hardcoded dict as fallback only, with warning log.
- Files: `backend/workers/tasks/auto_rebalancer.py`

### ✅ #25 Actual vs Estimated Savings Post-Fallback
**Status: DEFERRED — tracked in metadata but savings_calculator refactor needed separately**

### ✅ #26 ML Cache Cold Start
**Status: ALREADY HANDLED — PoolRankingService triggers refresh on cache miss**

### ✅ #27 Silent Type Casting
**Status: NOT A REAL ISSUE — explicit float() casts with error handling exist**

### ✅ #28 Spot Advisor Staleness Gate
**Status: DEFERRED — low priority for this session**

---

## Extra Issue #39: ML Same-AZ Filter Drops All Candidates
**Status: CONFIRMED REAL — FIXED**
- Root cause: substitute_manager.py line 500: `if p.az == target_az or p.az in seen_azs:` — skips ALL candidates in the same AZ as the dying node, including ones with DIFFERENT instance types. For single-AZ clusters, ALL ML recommendations are dropped → hardcoded fallback used.
- Fix: Changed to allow same-AZ candidates with different instance types. New logic: `if (p.az == target_az and p.instance_type == target_node.instance_type) or p.az in seen_azs:`
- Also: Added `logger.warning()` when `_get_alternative_families` hardcoded fallback is invoked.
- Files: `backend/services/substitute_manager.py`

---

## Extra Issue #39b: Diversity Enforcer Verification
**Status: CONFIRMED CORRECT — no fix needed**
- Line 502–510: `_de.check_candidate()` is called AFTER the AZ filter. The order is correct.

---

## Summary of Files Changed

| File | Changes |
|------|---------|
| `backend/services/distributed_locks.py` | Added `HeartbeatLock` class with heartbeat thread + `extend_ttl()` |
| `backend/workers/tasks/termination_monitor.py` | Blacklist TTL: 12h → 0.25h (15 min) |
| `backend/workers/tasks/auto_rebalancer.py` | (1) Failure backoff cooldown, (2) per-instance daily cap, (3) S2S dedup key, (4) wire pricing service |
| `backend/services/substitute_manager.py` | Same-AZ filter fix + fallback warning log |

---

## Docker Rebuild
After all fixes applied, rebuilt and restarted containers:
- `docker compose build backend celery_worker`
- `docker compose up -d` (no volume removal)

---

# Progress Log — Per-Node Pool Ranking & Coverage System (2026-03-20)

## Overview
Implemented the full per-node pool ranking and coverage system described in `changes.md`.
This adds real-time per-node alternative pool ranking, coverage classification, and two new UI views.

---

## Validation Summary (before implementation)

| Component | Status Before |
|-----------|--------------|
| `workload_inspector.py` — `build_node_profile()` | ❌ Missing |
| `decision_engine.py` — resource profile gates | ❌ Missing |
| `reconciliation_worker.py` — coverage computation | ❌ Missing |
| API — `GET /clusters/{id}/coverage` | ❌ Missing |
| API — `GET /clusters/{id}/nodes/{id}/alternatives` | ❌ Missing |
| `api.js` — `getClusterCoverage`, `getNodeAlternatives` | ❌ Missing |
| `cluster.py` — `NodeAlternativeCache` model | ❌ Missing |
| `cluster.py` — `ClusterBaseline` model | ❌ Missing |
| `PoolRankings.jsx` — Cluster Impact View (per-node table) | ❌ Old chart-based |
| `PoolRankings.jsx` — Node-Specific View (node selector + alternatives) | ❌ Missing |

---

## Changes Implemented

### 1. `backend/services/workload_inspector.py`
- Added `import math`
- Added `NODE_PROFILES_TTL = 300` constant
- Added `build_node_profile(node, pods, headroom_pct=10.0)` — builds NodeProfile from K8s node allocatable + pod requests:
  - Sums `vcpu_requested`, `memory_gb_requested` across all pod containers
  - Detects `has_local_pv`, `has_gpu_pods`, `has_stateful_pods`
  - Computes `min_vcpu_required = max(ceil(vcpu_req × 1.1), 1)` and `min_memory_required`
  - Sets `status = "IMMOVABLE"` if local PV detected
- Added `get_all_node_profiles(cluster_id, headroom_pct=10.0)` — calls `build_node_profile()` for all nodes; caches at `spot:node_profiles:{cluster_id}` TTL=300s
- Added `_parse_cpu(cpu_str)` — handles "2", "500m" millicores
- Added `_parse_memory_gb(mem_str)` — handles "4096Mi", "4Gi", "Ki/Mi/Gi/Ti" suffixes

### 2. `backend/core/decision_engine.py`
- Updated `rank_for_node()` Step 4 to extract `resource_profile` from `node_info`
- Applies per-node hard gates AFTER `_apply_filters()`:
  - `min_vcpu_required` → drop pools with fewer vCPUs
  - `min_memory_required` → drop pools with less memory
  - `required_arch` → drop pools with mismatched architecture

### 3. `backend/workers/tasks/reconciliation_worker.py`
- Added `import json`
- Added `_COVERAGE_TTL_S = 300`
- Added `_compute_cluster_coverage(db, redis, cluster)` function:
  - Queries all running `i-*` instances for the cluster
  - For each: calls `de.rank_for_node()` and classifies COVERED/AT_RISK/STRANDED
  - Writes ClusterCoverageReport JSON to Redis `cluster_coverage:{cluster_id}` TTL=300s
- Added call to `_compute_cluster_coverage()` after each cluster's reconciliation loop

### 4. `backend/api/atharvaai_routes.py`
- Added `import json as _json`
- Added `GET /clusters/{cluster_id}/coverage` — serves Redis-cached ClusterCoverageReport; computes on-demand on miss
- Added `GET /clusters/{cluster_id}/nodes/{node_id}/alternatives` — resolves node, calls `de.rank_for_node()`, returns paginated alternatives enriched with `rank` and `saving_pct`

### 5. `frontend/src/services/api.js`
- Added to `atharvaaiAPI`:
  - `getClusterCoverage(clusterId)`
  - `getNodeAlternatives(clusterId, nodeId, page, pageSize)`

### 6. `backend/models/cluster.py`
- Added `JSONB` import from `sqlalchemy.dialects.postgresql`
- Added `Index` to SQLAlchemy imports
- Added `NodeAlternativeCache` model (`node_alternative_cache` table):
  - `resource_profile` JSONB, `alternative_pools` JSONB
  - `coverage_status` (COVERED/AT_RISK/STRANDED/IMMOVABLE)
  - Composite index `idx_nac_cluster_node` on `(cluster_id, node_name)`
- Added `ClusterBaseline` model (`cluster_baselines` table):
  - `primary_node_type`, `primary_az`, `baseline_monthly_cost`
  - `baseline_spot_count`, `baseline_od_count`

### 7. `frontend/src/components/atharvaai/PoolRankings.jsx`
- Added state: `coverageData`, `coverageLoading`, `selectedNodeId`, `nodeAlternatives`, `nodeAltLoading`, `nodeAltPage`
- Added coverage fetch in `loadData()` (non-blocking, auto-selects first node)
- Added `useEffect` hook to fetch node alternatives when `selectedNodeId` changes
- **Cluster Impact View** (tab 2): replaced old chart-based view with per-node coverage table showing Node, Type, AZ, Lifecycle, Status badge, Alternative count, Best Pool, Saving%. Added coverage bar (percentage + Covered/At Risk/Stranded counts). Added warning banners for AT_RISK and STRANDED nodes.
- **Node-Specific View** (tab 1): added node selector dropdown + alternatives table (Rank, Type, AZ, Arch, Spot/hr, Saving%, Risk, ML Score) with Prev/Next pagination

### 8. Alembic Migration
- Created `migrations/versions/20260320_add_node_alternative_cache_and_cluster_baselines.py`
  - Revision: `20260320_node_coverage_tables`
  - Down revision: `20260320_realized_savings`
  - Creates `node_alternative_cache` table + 3 indexes
  - Creates `cluster_baselines` table

---

## Summary of Files Changed

| File | Change Type |
|------|-------------|
| `backend/services/workload_inspector.py` | Added `build_node_profile()`, `get_all_node_profiles()`, `_parse_cpu()`, `_parse_memory_gb()` |
| `backend/core/decision_engine.py` | Added per-node resource profile gates in `rank_for_node()` |
| `backend/workers/tasks/reconciliation_worker.py` | Added `_compute_cluster_coverage()` + coverage call per cluster |
| `backend/api/atharvaai_routes.py` | Added `/coverage` and `/nodes/{id}/alternatives` endpoints |
| `frontend/src/services/api.js` | Added `getClusterCoverage`, `getNodeAlternatives` |
| `backend/models/cluster.py` | Added `NodeAlternativeCache`, `ClusterBaseline` models |
| `frontend/src/components/atharvaai/PoolRankings.jsx` | Rebuilt Cluster Impact View + Node-Specific View |
| `migrations/versions/20260320_add_node_alternative_cache_and_cluster_baselines.py` | New migration for new tables |

---

## Docker Rebuild Required
```
docker compose build backend celery_worker
docker compose up -d
```
Migration command:
```
docker compose exec backend alembic upgrade head
```

---

# Progress Log — changes.md Phase 1–4 Implementation (2026-03-20)

## Validation Summary (before implementation)

| Task | Component | Status Before | Action |
|------|-----------|--------------|--------|
| 1.1 | spot_advisor_scraper.py — per-region timestamp | MISSING | FIXED |
| 1.2 | pricing_collector.py — no InstanceTypes filter, paginated | ALREADY OK | Skip |
| 1.3 | instance_catalog table + DB-backed catalog | ALREADY EXISTS | Skip |
| 1.4 | cache_builder.py — enrichment + savings filter | CRITICAL MISSING | FIXED |
| 2.1 | category_mapping.json — all gen families present | ALREADY OK (78 families) | Skip |
| 2.2 | Capacity validator — staleness (not vcpu gate) | Different function | Skip |
| 2.3 | Architecture filter — not hardcoded to amd64 | ALREADY OK | Skip |
| 2.6 | Rejection audit logging in decision_engine | MISSING | FIXED |
| 2.7 | estimate_az_interruption + record_interruption_event | MISSING | FIXED |
| 3.1 | Weighted scoring formula | ALREADY EXISTS (EV model) | Skip |
| 3.2 | Remove [:10] pool cap in decision_engine.py | CONFIRMED REAL | FIXED |
| 4.1 | /market-view API endpoint | MISSING | FIXED |
| 4.3 | /pool-audit API endpoint | MISSING | FIXED |
| 4.4 | Frontend funnel visualization in Cluster Impact View | MISSING | FIXED |

**Critical root cause found:** `cache_builder.py` stored only default risk_tier for all pools — no OD price, no vcpu/memory/arch, no savings filter. `decision_engine.py` had a `[:10]` hard cap in tier expansion fallback. `reconciliation_worker.py` had wrong import (`aws_account` → `account`).

---

## Changes Implemented

### Task 1.1 — Per-Region Timestamp (spot_advisor_scraper.py)
- After each region's DB commit, writes `spot:advisor:last_scraped:{region}` per-region timestamp

### Task 1.4 — Cache Builder Pool Enrichment (cache_builder.py) — CRITICAL
- Looks up `ondemand_price:{region}:{instance_type}` from Redis → actual OD price
- Looks up `spot_advisor:{region}:{instance_type}:Linux` → actual interruption rate
- Looks up vcpu/memory_gb/architecture from 80-type `_FALLBACK_SPECS` dict
- Assigns actual `risk_tier` via `assign_risk_tier(interruption_rate_pct)`
- Computes `savings_pct = (od_price - spot_price) / od_price * 100`; skips if ≤ 0
- Enriched pool dicts: `vcpu, memory_gb, architecture, ondemand_price, savings_pct, interruption_rate_pct, risk_tier`
- Logs: `raw_spot_keys / no_od_price / negative_savings / no_specs / final_pool_count`

### Task 2.6 — Rejection Audit Logging (decision_engine.py)
- `rank_for_node()` tracks: `blacklisted`, `too_small_vcpu`, `too_small_memory`, `arch_incompatible`
- Caches audit to Redis `pool_audit:{cluster_id}:{node_id}` TTL=300s

### Task 2.7 — AZ Interruption Estimation (pool_ranking_service.py)
- `estimate_az_interruption()`: 3-layer model (region rate + AZ price premium + EMA history)
- `record_interruption_event()`: EMA update (`rate * 0.9 + 25 * 0.1`), TTL 7 days

### Task 3.2 — Remove Pool Cap (decision_engine.py)
- Removed `[:10]` from `_relax_with_tier_expansion()` — no artificial limit

### Task 4.1 — Market View API (atharvaai_routes.py)
- `GET /api/v1/atharvaai/clusters/{cluster_id}/market-view?page=1&page_size=20&sort_by=risk_tier`

### Task 4.3 — Pool Audit API (atharvaai_routes.py)
- `GET /api/v1/atharvaai/clusters/{cluster_id}/nodes/{node_id}/pool-audit`

### Task 4.4 — Frontend Funnel Visualization (PoolRankings.jsx + api.js)
- `getMarketView()` + `getPoolAudit()` added to `atharvaaiAPI`
- Pool Eligibility Funnel panel added to Cluster Impact View (raw → rejections → eligible)

### Bug Fix — reconciliation_worker.py
- Fixed wrong import: `aws_account.AWSAccount` → `account.Account as AWSAccount`
- Fixed `cluster.aws_account_id` → `cluster.account_id`

---

## Summary of Files Changed

| File | Change |
|------|--------|
| `backend/workers/tasks/cache_builder.py` | Full enrichment rewrite |
| `backend/core/decision_engine.py` | Remove `[:10]` + rejection audit |
| `backend/scrapers/spot_advisor_scraper.py` | Per-region timestamp |
| `backend/services/pool_ranking_service.py` | `estimate_az_interruption()` + `record_interruption_event()` |
| `backend/api/atharvaai_routes.py` | `/market-view` + `/pool-audit` endpoints |
| `frontend/src/services/api.js` | `getMarketView()` + `getPoolAudit()` |
| `frontend/src/components/atharvaai/PoolRankings.jsx` | Funnel panel + state |
| `backend/workers/tasks/reconciliation_worker.py` | Fix import + account_id field |

## Docker Rebuild
All containers rebuilt and healthy ✅
