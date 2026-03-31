# Spot Optimizer — Merged Problems, Fixes & Repeated Mistakes

> **Compiled from**: BUGS_AND_FIXES.md, REBALANCING_DEBUG_LOG.md, FALLBACK_REMOVAL_LOG.md, AUDIT_REPORT.md, GLOBAL_RANKINGS_FIX.md, POOL_RANKINGS_IMPROVEMENTS.md, rebalancing_problem_report.md.resolved, rebalancing_rightsizing_detailed_report.md, NODE_UTILIZATION_FIX.md, NODE_TEMPLATE_FILTER_REMOVAL.md, DECISION_ENGINE_V3_IMPLEMENTATION_STATUS.md, IMPLEMENTATION_STATUS_FINAL.md, FEATURE_VALIDATION_COMPLETE.md, ML_MODEL_DOCUMENTATION.md, change-guide.md, problems_backup_20260326.md (76 problems)
> **Last merged**: 2026-03-30 | **Updated**: 2026-03-30 (added UI perf, ranking sync, cluster growth) | **Focus**: Problems + solutions + repeated mistakes only
> **See also**: `temp-doc/SYSTEM_SYNC_AND_GROWTH_REPORT.md` — full ranking sync + cluster growth root cause analysis

---

## PART 1 — REPEATED / SYSTEMIC MISTAKES

These patterns appeared across **multiple files and multiple sessions**. New code must avoid them.

---

### R-1: Silent Exception Swallowing in Critical Paths

**Pattern**: `except Exception: pass` or `except Exception: continue` inside rebalancing hot paths.

**Where it kept appearing**:
- `auto_rebalancer.py`: ASG `update_min_size()` failure was silently swallowed → MinSize stayed at 1 → ASG terminate failed → fallback to EC2 → cluster grew 3→6 nodes
- `auto_rebalancer.py`: Orphan cleanup failure silently continued → launched new spot node without removing orphan
- `discovery.py`: RC3 Redis failure caught silently → preserved wrong OD lifecycle (fixed: preserve SPOT on Redis fail)
- `emergency_rebalancer.py`: Missing field errors silently failed → nodes never cordoned or drained (P-C1, P-H16)

**Rule**: Only use `except: pass` for **non-critical auxiliary operations** (metrics reporting, Redis arch constraints, credential lookup best-effort). Critical path failures (ASG operations, EC2 launch, orphan cleanup) MUST be re-raised or mark the action FAILED.

---

### R-2: Hardcoded Fallbacks That Caused Incorrect Data

**Pattern**: When a real data source failed, code fell back to a hardcoded value that was often wrong and masked the real problem.

| Where | Hardcoded Value | Problem |
|---|---|---|
| `cache_builder.py` | `od_est * 0.30` (70% savings) | Spot Advisor fallback uniform 70% for ALL pools |
| `aws_pricing_service.py` | Plain string spot price (not JSON) | `cache_builder` JSON parse failed → zero price → 100% savings |
| `karpenter_routes.py` | `ONDEMAND_HOURLY['m5.large'] = 0.096` default | Wrong price used for unrecognized instance types |
| `auto_rebalancer.py` | `[:6]` cascade limit | Hardcoded; no per-cluster override |
| `auto_rebalancer.py` | `pods_migrated = 3` | Always reported 3 regardless of actual count |
| `rebalancing_actions` | `price = 0.096` new instance | Inaccurate cost records |
| Frontend `GlobalRankingsCard.jsx` | `lifecycle: 'spot'` baseline | Spot-to-spot = 100% savings when pricing missing |

**Rule**: When a real data source is unavailable, either fail loudly or use a clearly labeled estimate. Never silently use a value that makes the system appear healthy when it isn't.

---

### R-3: Wrong Redis Key Names / Format Mismatches

**Pattern**: One component writes a key in format A, another component reads format B → data never flows.

| Write Key | Read Key | Impact |
|---|---|---|
| `od_price:{region}:{type}` | `ondemand_price:{region}:{type}` | cache_builder read 0 → uniform 70% savings |
| `spot_price:...` (plain string) | `spot_price:...` (JSON `{"price":...}`) | AttributeError → all pools silently dropped |
| `rc3:od_streak:{aws_iid}` | `rc3:sync_od_streak:{aws_iid}` (wrong key read in atharvaai_routes.py) | Node status endpoint showed wrong streak |
| `pricing:ec2:{region}:{type}` | `spot_price:{region}:{az}:{type}` | Savings calculator used wrong key format |

**Rule**: All Redis key names must be documented in one place (see `logic.md §18`). Before writing a new key, verify the exact format matches all consumers. Never assume a key format without checking both writer and reader.

---

### R-4: ASG + EC2 Fallback Caused Cluster Growth

**Root cause chain** (appeared in FALLBACK_REMOVAL_LOG.md, REBALANCING_DEBUG_LOG.md, BUGS_AND_FIXES.md):
1. ASG terminate rejected (desired == min)
2. `update_min_size(0)` silently failed (no error check)
3. Fallback: EC2 terminate succeeded — instance gone from K8s
4. ASG desired still = 1, running = 0
5. `resume_asg_processes()` re-enabled `Launch` process
6. ASG auto-launched new OD replacement
7. Repeat → cluster grew 3→6 nodes

**Fix applied**: Branch by node type:
- ASG-managed nodes → ASG terminate ONLY, no EC2 fallback
- Karpenter-managed nodes → EC2 terminate ONLY, no ASG interaction
- MinSize=0 update failure → now FATAL (no continue)
- Orphan cleanup failure → now FATAL (no continue + new spot)

---

### R-5: Missing or Wrong Model Field Names in DB Writes

**Pattern**: Code wrote to a field that didn't exist on the SQLAlchemy model → silent None or crash → records corrupt.

| File | Wrong Field Used | Correct Field |
|---|---|---|
| `emergency_rebalancer.py` (P-C1) | `id=generate_uuid()`, `source_instance_type`, `action_type`, `trigger_reason` | `trigger`, `source_pool`, `target_pool`, `started_at`, `source_instance_id` |
| `emergency_rebalancer.py` (P-H16) | Same set of non-existent fields | Same fix |
| `karpenter_service.py` (GAP-C2) | `cluster.settings` (doesn't exist) | `cluster.optimization_settings.maintain_standby` |
| `atharvaai_routes.py` (GAP-C3) | `rc3:od_streak:{iid}` (never written) | `rc3:sync_od_streak:{iid}` |

**Rule**: Before using `model.field_name`, verify the field exists in the SQLAlchemy model class. Check `backend/models/` before writing.

---

### R-6: Cooldown / Lock Not Set in All Exit Paths

**Pattern**: 2-hour emergency cooldown was set AFTER a `return` statement (unreachable code) or only in some branches.

- `emergency_rebalancer.py` GAP-C1: cooldown code was after `return result` → unreachable. Fixed: moved before return.
- The Karpenter emergency path (Path 1) still does NOT set the 2-hour cooldown — it returns before the cooldown code. This is intentional (Karpenter manages its own lifecycle).

**Rule**: When adding a cooldown/lock at the end of a function, verify there is no early `return` that bypasses it.

---

### R-7: DB Fallback When Redis Cache Missing (P-M4 pattern)

**Pattern**: When a Redis cache key was missing (cold start, Redis restart, TTL expiry), the code fell through to a **full DB query pipeline**, triggering 240+ heavy DB calls/hour during Redis restarts.

- `auto_rebalancer.py` (P-M4): cache miss → `rank_pools_for_size()` DB fallback on every 15s beat → connection pool exhausted
- `emergency_rebalancer.py` Issue 14: no `build_global_pool_cache` trigger after failure events → cache stayed cold

**Fix**: On `global_pool_rankings:{region}` miss → set `_pm4_skip_cluster = True` + continue (no DB fallback). Log CRITICAL once per hour. Also add debounced cache rebuild trigger (TTL=60s, countdown=5s) on termination events.

---

### R-8: Stale Expiry / Action Never Completed

**Pattern**: Actions got stuck in `in_progress` forever with no timeout. This blocked the one-at-a-time guard → no new rebalancing possible.

- `RebalancingAction` had no expiry logic for actions stuck >45 minutes
- `AgentAction` in `PENDING` state >15 min → never expired → rebalancer skipped all clusters

**Fix**: Added expiry logic — actions stuck >45 min are auto-expired. `PENDING` AgentActions >15 min are treated as stale and ignored by the one-at-a-time guard.

---

## PART 2 — CRITICAL BUGS & FIXES BY COMPONENT

---

### C-1: Auto-Rebalancer Critical Fixes

| # | Problem | Root Cause | Fix |
|---|---|---|---|
| BUG-01 | Cluster grew 3→6 nodes | ASG fallback to EC2 (see R-4) | Branch by node type; no cross-path fallback |
| BUG-09 | Wrong spot node detected in `waiting_agent` loop | Used newest-by-date heuristic instead of stored ID | Use `replacement_spot_instance_id` from action metadata |
| P-M4 | Cache miss triggered 240 DB calls/hour | Fallback to DB on Redis miss | Skip cluster on miss; log CRITICAL; trigger rebuild |
| P-M6 | Per-cluster interval gate never fired at default 15s | `_check_interval > 15` (should be `>= 15`) | Changed to `>=`; TTL = `max(1, interval - 14)` |
| changes.md §2.2 | Overlapping drains on same node | No per-node action lock | `spot:node_active_action:{instance_id}` (600s) |
| Issue 18 | Only 6 instance types tried in cascade | Hardcoded `[:6]` with no override | Document; add `max_instance_type_attempts` setting |

---

### C-2: Emergency Rebalancer Critical Fixes

| # | Problem | Root Cause | Fix |
|---|---|---|---|
| P-C1 | Interrupted nodes never cordoned/drained | `RebalancingAction` created with non-existent field names | Use correct fields: `trigger`, `source_pool`, `target_pool`, `started_at`, `source_instance_id` |
| P-C2 | Stale expiry didn't roll back orphan spot | Wrong rollback helper called | Stale expiry calls `_do_rollback_terminate_orphan_spot()` |
| P-H16 | `emergency` status stuck forever | Same non-existent field bug as P-C1 in emergency path | Same fix — correct ORM field names |
| GAP-C1 | 2-hour cooldown unreachable | Code placed after `return result` | Moved before return in both standby + normal paths |
| GAP-C2 | `cluster.settings` AttributeError | Attribute doesn't exist on Cluster model | Use `cluster.optimization_settings.maintain_standby` |

**Execution path order** (verified 2026-03-27):
1. **Karpenter** (checked FIRST): `spot:karpenter:installed:{cluster_id}` → `_execute_karpenter_emergency()` — CORDON+DRAIN+TERMINATE with `termination_mode="karpenter"`, `priority=10`. No 2h cooldown set.
2. **Standby failover** (if `maintain_standby=True`): UNCORDON standby → CORDON interrupted → DRAIN → TERMINATE. Sets 2h cooldown.
3. **Normal emergency** (fallback): `RebalancingAction` with `trigger='emergency'`, `priority=10`. Sets 2h cooldown.

---

### C-3: ML Pipeline & Pricing Critical Fixes

| # | Problem | Root Cause | Fix |
|---|---|---|---|
| Pricing bug 1 | All spot prices read as 0 → 100% savings everywhere | `_refresh_regional_pricing()` wrote plain string; `cache_builder` expected JSON `{"price":...}` | Write JSON format; `cache_builder` parses `.get('price')` |
| Pricing bug 2 | OD price always 0 in cache_builder | `get_ondemand_price()` wrote `od_price:` key; `cache_builder` read `ondemand_price:` key | Dual-write BOTH keys on every OD price fetch |
| Pricing bug 3 | Spot_advisor savings uniform 70% | Fallback `od_est * 0.30` hardcoded; SA key never read | Read `savings_percentage` from `spot_advisor:{region}:{type}:Linux`; 70% only as last resort |
| Pricing bug 4 | Pricing worker never consumed tasks | Worker started without `-Q pricing` flag → tasks routed to `pricing` queue, worker only listened to `celery` | `docker-compose.yml`: worker command `-Q celery,pricing` |
| P4 cache key bug | `get_redis` not defined in atharvaai_routes.py | `Depends(get_redis)` — function doesn't exist | Use `get_redis_client()` directly in function body |
| ML variable swap (Issue 1) | Classifier output stored as `savings_pct`; regressor as `cost_estimate` | Variable name swap in inference loop | Correct mapping: classifier → `risk_probability`; regressor → `predicted_savings` |
| 100% savings in GlobalRankingsCard | Spot-to-spot comparison with missing pricing data | `lifecycle: 'spot'` baseline → `(price - 0) / price = 100%` | Change baseline to `lifecycle: 'on-demand'` |
| Ranking all same score | Sort by `ml_score` only; all pools had 0.57 | No tie-breaker | Sort by `(ml_score, predicted_savings)` tuple — savings as tie-breaker |

---

### C-4: Discovery / Lifecycle Detection Fixes

| # | Problem | Root Cause | Fix |
|---|---|---|---|
| P-M3 | RC3 streak expired mid-count | TTL=5min; Celery beat jitter caused observation 2 of 3 to expire | Doubled TTL to 10min (`rc3:sync_od_streak:{iid}`) |
| P-H4 last-node guard | `scan_orphans()` terminated newly-launched spot as orphan | New spot not registered before discovery ran | On last-node launch: create `Instance` DB record + set `spot:asserted_spot:{id}` (300s) |
| Ghost cluster cleanup | Agent clusters hard-deleted with 2h grace — wrong | Code marks agent clusters as DEGRADED | Correct: agent clusters → DEGRADED (not deleted); 10-min heartbeat grace period |
| P-M5 orphan scan | Pass 1 ran against platform account in all-cross-account setups | No guard for "all clusters use assumed roles" | Pass 1 only runs when at least one cluster has `aws_role_arn IS NULL` |
| P-C4 Karpenter stall | `detect_karpenter_stalls()` used platform creds for cross-account | No STS assume_role for cross-account clusters | Call STS `assume_role` before EC2 client; skip cluster on assume_role failure |

---

### C-5: Right-Sizing Bugs

| # | Problem | Root Cause | Fix |
|---|---|---|---|
| RS-1 (AUDIT) | `recommended_type` always = `current_type` | No bin-packing implemented | `_bin_pack_instance()`: `required = max(0.25, current × util/100 × 1.30)`; find cheapest type that fits |
| RS-2 (AUDIT) | No spot pool suggestion for stateless nodes | Missing `PoolRankingService` call | After bin-pack: call `rank_pools()` for stateless non-spot nodes; return top-1 as `spot_pool` |
| Node utilization showing 0% | Agent pod metrics not aggregated correctly | Utilization read from pod-level before aggregation | Aggregate pod metrics per node; fallback to raw `cpu_util`/`memory_util` from Instance record |
| Template filter applied client-side | Double filtering: server returns wrong results if client also filters | Filter applied in both API response and UI | Move filter to backend; remove client-side duplicate |
| Hardcoded `architecture='amd64'` | Graviton nodes misclassified | No architecture detection | Read architecture from Instance record |

---

### C-6: Circuit Breaker & Stabilization Fixes

| # | Problem | Root Cause | Fix |
|---|---|---|---|
| P13 (changes.md) | Redis restart wiped stabilization lock → cluster burst | Stabilization lock stored only in Redis | Add `ClusterCooldownState` DB table; `acquire_stabilization_lock()` persists to DB; auto_rebalancer re-hydrates from DB on Redis miss |
| P8 (changes.md) | `state_entered_at` never set | No trigger — field stayed NULL on state transitions | PostgreSQL `BEFORE UPDATE OF current_state` trigger auto-sets `state_entered_at = NOW()` |
| Circuit breaker threshold doc wrong | Docs said "3+ times" | Code uses `>5` failures in 10 minutes | Corrected: threshold is `>5` ONNX failures in 10 minutes |
| STABILIZATION_LOCK_TTL doc wrong | docs.md said `= 300` | Actual constant = 60 | Fixed: `STABILIZATION_LOCK_TTL = 60` |

---

### C-7: Frontend / UI Bugs

| # | Problem | Root Cause | Fix |
|---|---|---|---|
| BUG-05 | Stabilization card missing "Next Check" timer | UI showed lock but no countdown | Added lock countdown + next-check inline |
| BUG-06 | Rebalancing history not filtered by cluster | `getRebalancingStatus()` called without `cluster_id` | Added `cluster_id` param to API call |
| BUG-07 | Failed migrations not in timeline | `failed` status not included in filter | Added `failed` to status filter |
| BUG-08 | `target_az` missing from action metadata | Not written at action creation | Added `target_az` + `source_az` to action metadata |
| BUG-03 | `LABEL_NODE` action invalid kwarg | `action_metadata` passed as positional | Moved to `payload` dict |
| GAP-C4 Activity Log | Clicking Activity Log tab showed nothing | No render block for Activity Log tab | Added `rebalancingActions` list render block |
| GAP-m1 cost_estimate | Comment said "alias for risk_probability" | Wrong documentation | `cost_estimate = spot_price × 24` (daily cost) |
| P-C17/C18 | Hardcoded fake safety metrics + exposure charts | Static fake data in frontend components | Replaced with real API data; removed hardcoded values |
| P-H20/21/22 | Hardcoded `128` cluster count, 94% efficiency, fake SVG charts | Demo placeholders never removed | Replaced with `clusters.length`, "—", "Data pending" |

---

### C-8: Database / Schema Fixes

| # | Problem | Root Cause | Fix |
|---|---|---|---|
| BUG (debug log) | `node_templates` table schema mismatch on startup | Old table with wrong schema | Dropped and recreated table |
| P-M2 | `spot:term_failed:{id}` TTL too short | TTL=5400s (90min) — expired before OD launched | Changed to 14400s (4h) |
| P-M1 | `cluster.node_count` stale during rebalancing | Only updated by discovery every 5min | `_sync_instance_state_from_aws` now sets `node_count = spot_count + od_count` |
| P-C3 | ASG `asg_suspended=True` not committed immediately | DB commit deferred — other workers read stale value | Committed immediately after suspend call |
| Missing `get_db_contextmanager` | Import error on startup | Function existed in mental model but not in code | Added `get_db_contextmanager()` context manager to `base.py` |

---

### C-9: Celery / Worker Bugs

| # | Problem | Root Cause | Fix |
|---|---|---|---|
| Pricing tasks never ran | `ingest_spot_prices` + `refresh_ondemand` referenced in beat but not implemented | `@app.task` decorators missing — `NotRegistered` Celery error every 10min | Added task implementations in `pricing_worker.py` |
| Double-fire on instance catalog | Duplicate `instance-catalog-refresh-nightly` beat entry (86400s) | Copy-paste in `app.py` | Removed duplicate; canonical entry is `crontab(hour=3)` |
| Issue 14 | Cache cold after failure events | No trigger to rebuild `global_pool_rankings` after ITN | Added debounced trigger: `ranking_refresh_pending:{region}` (TTL=60s, countdown=5s) in both rebalancer files |
| P9 (changes.md) | No warning when pool rankings stale | No check on `global_pool_rankings:{region}` TTL | Guard 2.5: check TTL; log CRITICAL + `ranking_stale_warned:{region}` (3600s dedup) when TTL==-2 |

---

## PART 3 — PROBLEMS STATUS SUMMARY (from problems_backup_20260326.md — 76 total)

| Status | Count |
|---|---|
| ✅ FIXED | 66 |
| ⚠️ PARTIALLY FIXED | 5 |
| N/A (code removed) | 4 |
| ❌ UNFIXED | 0 |

### Key Partially-Fixed Items (still need attention)

| # | Issue | Status | Gap |
|---|---|---|---|
| P-M4-related | ML decoupling | PARTIAL | Main path reads Redis; 7+ sub-paths still have `rank_pools_for_size` fallback |
| Rate-based CB | Sliding window circuit breaker | NOT IMPLEMENTED | Code uses INCR counter, not sorted-set sliding window |
| §2.1 | Stabilization lock 5min minimum | NOT IMPLEMENTED | `STABILIZATION_LOCK_TTL = 60` (1 min, not 5 min) |
| §3.1 | AWS token bucket rate limiter | NOT IMPLEMENTED | No `aws_rate_limiter.py` |
| §6.1 | Spot price margin guard | NOT IMPLEMENTED | No pre-check for spot > OD price |

---

## PART 4 — CRITICAL IMPLEMENTATION RULES (never violate)

1. **Redis key format contracts** — JSON for spot prices, plain string for OD prices. Dual-write OD to both `od_price:` and `ondemand_price:`. See `logic.md §18`.

2. **No cross-path EC2/ASG fallback** — ASG-managed nodes use ASG terminate only. Karpenter-managed use EC2 only. No cross-path fallback.

3. **Emergency path order** — Karpenter checked FIRST, then standby, then normal. 2h cooldown set for standby+normal only.

4. **Per-node action lock required** — Always check `spot:node_active_action:{instance_id}` before creating any `RebalancingAction`.

5. **P-M4 guard** — When `global_pool_rankings:{region}` is absent, skip the cluster. Never fall through to DB pipeline.

6. **RebalancingAction fields** — Use: `trigger`, `source_pool`, `target_pool`, `started_at`, `source_instance_id`, `action_metadata`. NOT: `id=generate_uuid()`, `source_instance_type`, `action_type`, `trigger_reason`.

7. **ClusterCooldownState DB persistence** — After acquiring Redis stabilization lock, always persist to `ClusterCooldownState` table. Check DB on Redis miss.

8. **Pricing tasks need `-Q pricing` flag** — Worker must listen to `celery,pricing` queues or pricing tasks never execute.

9. **`ScoredPool.predicted_savings` is immutable** — Never mutate after ONNX inference. S2S comparison depends on original ONNX value. `PoolRankingResponse.predicted_savings` is separate and can be recomputed.

10. **Always verify `cluster.optimization_settings`** — `cluster.settings` does not exist. Use `cluster.optimization_settings` (relationship). `cluster.karpenter_mode` is a direct column.

---

## PART 5 — UI PERFORMANCE ISSUES (added 2026-03-30)

### P-UI-1 (CRITICAL): 1 Re-render Per Second — RebalancingTimeline

`RebalancingTimeline.jsx:133`: `setInterval(() => setTick(t+1), 1000)` fires unconditionally even when no rebalancing is active. Forces 60 React re-renders/minute for the entire component tree.
**Fix:** Only start timer when `cooldownExpiresAt || nextCheckAt` is non-null.

### P-UI-2 (CRITICAL): 12 API Calls on Every Cluster Click

`ClusterDetails.jsx:160-172`: Fires 12 simultaneous HTTP requests on every cluster mount. Browser 6-connection limit queues 6 of them → 1–3s blank screen.
**Fix:** Create single batch endpoint `GET /clusters/{id}/full`, or serialize non-critical calls.

### P-UI-3 (CRITICAL): Karpenter Status Polled Every 4 Seconds

`ClusterList.jsx:1105-1125`: `setInterval(fetchKarpenterStatus, 4000)` per cluster. 5 open clusters = 75 req/min. No Redis cache on this endpoint.
**Fix:** Increase to 30s poll. Add Redis cache with 10s TTL on the endpoint.

### P-UI-4 (CRITICAL): Blacklist API — 2000+ Sequential Redis Round Trips

`atharvaai_routes.py:412-442`: `redis.smembers("risky_pools")` then N individual `redis.get()` + `redis.ttl()` calls. With 1000 pools = 2000 Redis calls per HTTP request (200–800ms).
**Fix:** Use `redis.pipeline()` to batch all calls into one round trip.

### P-UI-5 (CRITICAL): Metrics Batch — N+1 DB Queries + `db.flush()` Per Node

`metrics.py:154-200`: One `db.query().filter().first()` per node (full table scan via OR condition on unindexed columns) + one `db.flush()` per node. 20 nodes = 40 DB round-trips.
**Fix:** Pre-load all cluster instances into dict before loop. Single `db.commit()` at end.

### P-UI-6 (HIGH): Market View — O(N) Loop Over 2000+ Pools Per Request

`atharvaai_routes.py:2588`: Python loop over all cached pools per request. No server-side pre-filter. Loads full `market_view_cache` into memory. 300–500ms per call.

### P-UI-7 (HIGH): Activity Log — All N DOM Nodes Without Virtualization

`ClusterDetails.jsx:806-837`: Renders all `rebalancingActions` as DOM nodes. Clusters running for weeks = 2000+ actions = 10,000+ DOM nodes. Visible stutter.
**Fix:** Paginate to 20 rows, add "Load more" button.

### P-UI-8 (HIGH): No AbortController — Stale Data Flash on Navigation

All 12 `useEffect` calls lack `AbortController`. Navigating away mid-load causes stale setState on new cluster view.
**Fix:** `const controller = new AbortController()` in each effect, `return () => controller.abort()`.

### P-UI-9 (HIGH): 30s Poll Fires Immediately on Mount → 15 Simultaneous Calls

`ClusterDetails.jsx`: Effect 1 (12 calls) + Effect 2 poll fires immediately on mount (3 calls) = 15 simultaneous calls before any data is shown.
**Fix:** Add `setTimeout(pollNodeData, 30000)` for first poll — no immediate fire.

### P-UI-10 (MEDIUM): PoolRankings Filter Runs Synchronously Over 1991+ Pools

`PoolRankings.jsx`: Every filter change re-runs `.filter()` over full dataset on render thread. 50–100ms freeze per keystroke.
**Fix:** `useMemo` for filtered list + `useDeferredValue` for filter inputs.

---

## PART 6 — RANKING SYSTEM SYNC ISSUES (added 2026-03-30)

> Full analysis in `temp-doc/SYSTEM_SYNC_AND_GROWTH_REPORT.md §2`

| Mismatch | UI | Execution | Impact |
|----------|-----|-----------|--------|
| Sorting key | `ml_score` via `rank_pools()` | `expected_value` via `rank_pools_for_node()` | Different pool picked |
| Cache key | `global_pool_rankings:{region}` (65min TTL) | `market_view_cache:{region}` (60min TTL) | 5-min divergence window |
| Blacklist source | `blacklist:pool:{key}` individual keys | `risky_pools` Redis SET | Pool safe in UI, skipped by execution |
| Risk ceiling | Hard 50% | Per-cluster 10–25% | UI shows 2× more pools than execution allows |
| Savings fallback | 65% hardcoded if backend returns 0 | 0% (no override) | False savings display |
| OD price source | Single lookup | 3-key fallback + 4th `_lookup_od_price` | Different baseline → different rank order |
| `savings_pct` scale | Fraction (0-1) assumed | Percentage (0-100) returned | 100× scaling bug |

---

## PART 7 — CLUSTER GROWTH VECTORS (added 2026-03-30)

> Full analysis in `temp-doc/SYSTEM_SYNC_AND_GROWTH_REPORT.md §4`

Top 5 confirmed growth vectors (see full report for all 9):

| Vector | File:Line | Mechanism | Auto-Cleaned? |
|--------|-----------|-----------|--------------|
| EC2 terminate fails + rollback also fails | auto_rebalancer.py:3418,3442 | Exception swallowed → source + replacement both running | No |
| Stale action orphan cleanup fails silently | auto_rebalancer.py:2379 | Exception swallowed → orphan spot runs indefinitely | No — if node joined K8s |
| Action stuck in `waiting_agent` forever | auto_rebalancer.py:2513 | Phase 3 (terminate source) never executes | After 45min expiry (if cleanup works) |
| Per-node lock expires (>24h action) | auto_rebalancer.py:5917 | Second action created for same source instance | No |
| Discovery overwrites `state='running'` mid-drain | discovery.py:891 | No active-action check before state overwrite | No |

**Root cause of all growth vectors:** Exception handlers in rollback paths use `except Exception: logger.warning(...)` — silent swallow. The cluster grows whenever ANY exception occurs in a cleanup/rollback path.
