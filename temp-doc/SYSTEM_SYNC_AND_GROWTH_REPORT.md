# System Sync & Cluster Growth — Root Cause Report

> **Generated:** 2026-03-30
> **Scope:** Ranking System, UI Display, Execution Engine, AWS State, Cluster Growth
> **Status:** Active investigation — all issues sourced from live code reads (not assumptions)

---

## SECTION 1 — WHY EVERYTHING IS OUT OF SYNC

The platform has **four independent systems** that each maintain their own view of "the truth":

| System | Source of Truth | Update Frequency | Key Store |
|--------|----------------|-----------------|-----------|
| **Ranking System** | `global_pool_rankings:{region}` | 65 min TTL (hourly rebuild) | Redis |
| **UI Display** | DB → API → React state | On mount + 30s poll | DB + Redis |
| **Execution Engine** | `market_view_cache:{region}` → `global_pool_rankings` fallback | 1h TTL | Redis |
| **AWS Actual State** | EC2 API / ASG API | Real-time | AWS |
| **DB State** | Discovery sync (every 5 min) | 5 min lag | PostgreSQL |

These four systems are **never fully in sync** because they read different caches at different TTLs. A spot interruption in AWS takes up to 65 minutes to propagate through all four layers.

---

## SECTION 2 — RANKING SYSTEM vs UI vs EXECUTION: 8 CONFIRMED MISMATCHES

### MISMATCH-1: Different Sorting Algorithms (CRITICAL)

**UI endpoint** (`atharvaai_routes.py`) calls `rank_pools()` — sorts pools by **`ml_score`**:
```
ml_score = (savings × 0.4) - (risk × 0.6)    ← ML-weighted composite
```

**Execution engine** (`auto_rebalancer.py:1193`) calls `rank_pools_for_node()` — sorts by **`expected_value`**:
```
expected_value = real_savings_pct × (1.0 - risk_probability)   ← Linear EV
```

**Result:** Pool ranked #1 in the UI may be ranked #3 or lower during actual execution. The user sees one thing, the engine picks another.

**File refs:**
- UI sort: `pool_ranking_service.py` (rank_pools pipeline — ml_score)
- Execution sort: `pool_ranking_service.py:2482` (rank_pools_for_node — expected_value DESC)

---

### MISMATCH-2: Different Cache Keys + Different TTLs

**UI** reads `global_pool_rankings:{region}` — TTL **65 minutes** (3900s)
**Execution** prefers `market_view_cache:{region}` — TTL **60 minutes** (3600s), falls back to global_pool_rankings

```python
# pool_ranking_service.py:2312-2314
raw = self.redis.get(key_market_view_cache(region))      # TTL=3600s
if not raw:
    raw = self.redis.get(key_global_pool_rankings(region)) # TTL=3900s
```

**Result:** 5-minute window where execution has expired cache but UI still shows stale rankings. During that window, execution picks a fallback pool that the UI never showed.

---

### MISMATCH-3: Different Blacklist Sources

**UI** checks individual Redis keys:
```python
# atharvaai_routes.py:348
is_blacklisted = bool(redis.exists(f"blacklist:pool:{pool_key}"))
```

**Execution** reads the `risky_pools` Redis **SET**:
```python
# pool_ranking_service.py:2326
_bl = self.redis.smembers("risky_pools")
```

Two different write paths populate these two different stores. A pool can be in `risky_pools` (written by termination_monitor.py) but NOT in `blacklist:pool:{key}` (written by auto_rebalancer.py), or vice versa.

**Result:** UI shows a pool as "safe" but execution skips it (or the reverse). The same physical pool has two independent blacklist states.

---

### MISMATCH-4: Risk Ceiling — Hardcoded in UI, Per-Cluster in Execution

**UI** (`pool_ranking_service.py:557`): Hard ceiling **50%** — shows ALL pools with risk ≤ 50%

**Execution** reads `ClusterOptimizationSettings.risk_ceiling_percent` (default **25%**):
```python
# pool_ranking_service.py:2399
if pool_risk > risk_ceiling: continue   # risk_ceiling = 0.10-0.25 typically
```

**Result:** UI can show 40 pools. Execution can only use 15 of them (those under 25% risk). User sees a "good" pool at 35% risk — execution will never pick it.

---

### MISMATCH-5: OD Price Baseline — Three Fallback Keys, None Guaranteed

`auto_rebalancer.py:1180-1190` tries 3 Redis key formats before calling rank_pools_for_node:
```python
for _od_fmt in [
    f"pricing:od:{region}:{type}",         # Format 1 — old key
    f"od_price:{region}:{type}",            # Format 2 — aws_pricing_service writes this
    f"ondemand_price:{region}:{type}",      # Format 3 — dual-write target
]:
    ...
    break
# Falls back to od_price=0.0 if all miss
```

If all 3 miss (cold cache after Redis restart), `od_price=0` is passed to `rank_pools_for_node()`. That function then tries a 4th fallback (`_lookup_od_price` in cache_builder). If that also fails: savings = 0% for all pools → rankings collapse to random order.

---

### MISMATCH-6: Savings Calculation — Frontend Overrides Backend

`PoolRankings.jsx:719-723`:
```javascript
// If backend returns 0% savings for an OD node:
const savingsPct = rec.projected_savings_pct > 0
    ? rec.projected_savings_pct
    : 65;  // ← HARDCODED 65% OVERRIDE

const savingsMo = (rec.current_cost * (savingsPct / 100)) * 720;
```

**Backend** (`savings_calculator.py:112-119`) calculates:
```python
live_savings_hr = source_od_price_hr - current_spot_price_hr
```

**Result:** When backend can't compute savings (missing OD price in Redis), frontend silently shows "65% savings" instead of "unknown". The user sees optimistic numbers that have no backing calculation.

---

### MISMATCH-7: `savings_pct` Field Scaling Bug (PERCENTAGE vs FRACTION)

`pool_ranking_service.py` (rank_pools_for_node output):
- Computes `savings_pct` as a fraction: `0.18` (18%)
- Computes `expected_value = savings_pct × (1 - risk)` ≈ `0.18 × 0.75 = 0.135`
- Then stores `savings_pct = round(savings_pct × 100, 2)` = **18.0** (percentage)
- But `expected_value` was already computed on the fraction `0.135`

**UI reads both fields.** If UI multiplies `savings_pct` (thinking it's a fraction) by 100 again → shows `1800%`.
If UI reads `expected_value` as a percentage (thinking it's 0–100) → shows `0.135%`.

---

### MISMATCH-8: Cost Estimate — UI Shows Daily, Execution Never Reads It

`atharvaai_routes.py:367`:
```python
cost_estimate = float(scored_pool.pool.spot_price) * 24.0  # daily cost
```

The execution engine (`auto_rebalancer.py`) never reads `cost_estimate` back. It always re-fetches the spot price from Redis for its own calculation. If the cached spot price used to build rankings has changed since the ranking was built (up to 65 min ago), the `cost_estimate` shown in UI is stale relative to what execution will use.

---

## SECTION 3 — WHY AWS STATE AND DB STATE ARE OUT OF SYNC

### SYNC-1: Discovery Overwrites In-Progress Node State (CRITICAL)

`discovery.py:891` unconditionally sets:
```python
existing.state = 'running'
```

There is **no check** for an active `RebalancingAction` record before overwriting. If:
- `auto_rebalancer` is draining a node at T=0
- `discovery` runs at T=3min (mid-drain)
- `discovery` marks node as `state='running'`
- `auto_rebalancer` at T=4min sees `state='running'` and may start a new action

**Race window:** 5 minutes (discovery interval).

---

### SYNC-2: Lifecycle Downgrade Requires 15 Minutes of Evidence

RC3 guard in `discovery.py:866` requires 3 consecutive OD reads before marking a SPOT node as OD. Each discovery cycle = 5 minutes → **15 minutes** before a false downgrade resolves.

If AWS API intermittently omits `InstanceLifecycle='spot'` (known AWS inconsistency), the node flickers between SPOT and OD in the DB for 15-minute windows. UI shows OD, billing shows SPOT.

---

### SYNC-3: Terminated Instance Cleanup Too Aggressive

`discovery.py:951`: Cutoff is `timedelta(minutes=5)` — terminated instances **deleted from DB after 5 minutes**.

The comment says "30 min" but the code says 5 min. A node terminated at T=0:
- T=5min: Deleted from DB
- T=3min: UI still showing it (from 30s poll cache)
- T=6min: Node vanishes from UI suddenly without explanation

---

### SYNC-4: Termination Monitor Doesn't Update Instance.state

`termination_monitor.py` detects a spot interruption and:
1. Blacklists the pool
2. Logs the event
3. Triggers `emergency_rebalancer`

But it does **NOT** set `Instance.state = 'terminating'` or `'terminated'`. The emergency rebalancer sets `interrupted.state = 'terminating'` (`emergency_rebalancer.py:421`), but only after it runs. If emergency rebalancer is delayed (queue busy), the DB shows the node as `'running'` while AWS is actively reclaiming it.

---

### SYNC-5: Instance.price Updated Every 5 Minutes — Breaks Historical Savings

`discovery.py:892`: `price = hourly_price` is written on every discovery scan.

`savings_calculator.py:112-119` uses `source_od_price_hr` (snapshotted at action creation time) vs `current_spot_price_hr` (live from Redis).

If spot prices drop by 20% between action creation and completion, the "realized savings" calculation overstates savings because the OD baseline was snapshotted at action creation but the spot price used is live.

---

## SECTION 4 — WHAT IS CAUSING CLUSTER GROWTH

The cluster grows (adds nodes without removing old ones) via **15 distinct vectors**. The most critical 6:

---

### GROWTH-V1: EC2 Terminate Fails — Both Nodes Running (MOST COMMON)

**File:** `auto_rebalancer.py:3401-3418`

Flow:
1. Replacement spot launched successfully ✓
2. Source OD terminate via ASG or direct EC2 → **exception thrown**
3. `spot:term_failed:{instance_id}` key set (4h TTL)
4. Action marked `failed`
5. Replacement spot: **still running** (billing starts)
6. Source OD: **still running** (billing continues)

**Cluster grows by 1 node.** After 4 hours, the term_failed key expires and the cycle may repeat.

The rollback at line 3442 (`_do_rollback_terminate_orphan_spot`) terminates the **replacement spot**, not the source. So after rollback: source is alive, replacement is dead, net = 0 growth. But if the rollback ALSO fails (line 3442 exception caught silently) → net = +1 growth.

---

### GROWTH-V2: Drain/Cordon Fails + Rollback Fails

**File:** `auto_rebalancer.py:3078, 2111`

Flow:
1. Replacement spot launched ✓
2. CORDON source node → **fails** (kubectl error)
3. Rollback: terminate orphan spot via `_do_rollback_terminate_orphan_spot()`
4. If rollback **also throws exception** → caught silently
5. Replacement spot: **still running**
6. Source: **still running, not cordoned**

Both nodes alive. Cluster grew by 1.

---

### GROWTH-V3: Action Stuck in `waiting_agent` — Phase 3 Never Executes

**File:** `auto_rebalancer.py:2513-2629`

Execution flow phases:
- Phase 1: Launch replacement spot
- Phase 2: Wait for spot to join K8s (detected via `node_joined:{iid}` Redis key)
- Phase 3: Cordon + drain source, then terminate it

**If the action gets stuck in Phase 2** (replacement joins but Redis key write fails, or agent dies):
- Phase 3 never runs
- Source OD: alive, receiving traffic
- Replacement spot: alive, also receiving traffic (Kubernetes already scheduled pods to it)
- **Both billable** until stale-action expiry (45 minutes)

Even when stale expiry runs at 45 minutes, orphan cleanup may fail (see GROWTH-V6).

---

### GROWTH-V4: Per-Node Action Lock Expires Before Completion

**File:** `auto_rebalancer.py:5915-5918`

Lock: `spot:node_active_action:{instance_id}` — TTL = **86400s (24h)**

If a rebalancing action somehow runs for > 24 hours (cluster paused, Celery worker crash, network partition), the lock expires. Next cycle:
- Checks lock: **not found** (expired)
- Creates new `RebalancingAction` for same source instance
- Launches **second replacement spot**
- Now: source + first replacement + second replacement = **3 nodes**

---

### GROWTH-V5: Emergency Rebalancer — Karpenter Auto-Provisions Before Old Node Terminates

**File:** `emergency_rebalancer.py:136-148, 349-422`

Karpenter path:
1. CORDON interrupted node → queued to agent
2. Karpenter sees cordoned node immediately → **auto-provisions replacement**
3. DRAIN + TERMINATE queued to agent (but may not run yet)
4. Old interrupted node: still running (drain queued, not started)
5. Karpenter replacement: already provisioning

For the next 2–5 minutes: interrupted node (not yet drained) + Karpenter replacement (provisioning) = **+1 node temporarily**.

If the agent TERMINATE_NODE action fails (agent offline, IAM error), the old node stays. Cluster net = +1.

---

### GROWTH-V6: Stale Action Orphan Cleanup Is Silently Skipped

**File:** `auto_rebalancer.py:2372-2379`

When an action is expired (>45 min stale):
```python
try:
    _do_rollback_terminate_orphan_spot(...)
except Exception as _ex:
    logger.warning(f"orphan cleanup failed: {_ex}")
    # ACTION STILL MARKED FAILED — orphan spot remains
```

The exception is caught, logged at WARNING level, and the action is marked failed. The orphan spot instance is **never retried for cleanup**. It runs indefinitely until the next full discovery cycle catches it as an orphan — but only if it has no `node_joined` Redis key.

If the orphan spot successfully joined K8s (has pods scheduled to it), `scan_orphans` skips it. The node runs forever with no associated rebalancing action, no owner, no cleanup.

---

### GROWTH-V7: Replacement Joins K8s + Source Terminate Fails → Retry After 4h → Second Replacement

**File:** `auto_rebalancer.py:3401-3418, 1405-1480`

Timeline:
- T=0: Replacement spot launched
- T=5min: Replacement joins K8s, pods scheduled
- T=6min: Source OD terminate fails — `spot:term_failed:{instance_id}` set (4h)
- T=6min: Cluster size = source + replacement = **+1**
- T=4h: term_failed key expires
- T=4h+1: Pre-launch orphan check runs (`auto_rebalancer.py:1405-1480`)
- The first replacement now has `node_name` set (joined K8s) → NOT detected as orphan
- New replacement launched for same source
- T=4h+3min: Cluster size = source + first replacement + second replacement = **+2**

---

### GROWTH SUMMARY TABLE

| Vector | Root Cause | Growth | Auto-Cleans? |
|--------|-----------|--------|-------------|
| V1: EC2 terminate + rollback both fail | Exception at 3418 + 3442 | +1 | No — requires manual cleanup |
| V2: Drain fail + rollback fail | Exception at 3078 + 2111 | +1 | No |
| V3: Stuck in waiting_agent | Phase 3 unreachable | +1 | After 45min stale expiry (if cleanup works) |
| V4: Action lock expires (>24h) | 86400s TTL | +2 | No |
| V5: Karpenter emergency + agent failure | Race between Karpenter and TERMINATE action | +1 | Only if drain completes |
| V6: Stale action orphan cleanup fails silently | Exception swallowed at 2379 | +1 | No |
| V7: 4h retry launches 2nd replacement | First replacement joined K8s, not detected as orphan | +2 | No |
| V8: Phase 3 never runs after K8s join | Agent down during drain/terminate window | +1 | After 45min stale expiry |
| V9: `replacement_spot_instance_id` missing | Metadata corruption | +2 | No — both run |

**Worst case scenario:** V4 + V7 + V9 all trigger for the same cluster simultaneously → **+5 nodes** with zero automatic cleanup.

---

## SECTION 5 — UI PERFORMANCE: WHY EVERY EVENT TAKES TIME

### P1 (CRITICAL): 1 Re-render Per Second — RebalancingTimeline

`RebalancingTimeline.jsx:133`: Unconditional `setInterval(() => setTick(t+1), 1000)` runs **always**, even when no rebalancing is active. This forces React to re-render the entire timeline component + all children **60 times per minute**.

When `RebalancingTimeline` is embedded inside `ClusterDetails` (which it is), the entire cluster detail page re-renders 60×/minute. Every re-render: re-runs `rebalancingActions.map()`, recomputes inline styles for all nodes, recalculates badge conditions.

---

### P2 (CRITICAL): 12 API Calls on Every Cluster Click

`ClusterDetails.jsx:160-172`: On every cluster navigation, fires 12 simultaneous HTTP requests. Browser allows max 6 concurrent connections → 6 requests queue. User sees blank screen for 1–3 seconds.

None of these 12 calls are cached client-side. Switching between clusters re-fires all 12.

---

### P3 (CRITICAL): Karpenter Polls Every 4 Seconds Per Cluster

`ClusterList.jsx:1105-1125`: `setInterval(fetchKarpenterStatus, 4000)`. For 5 open clusters = 75 API calls/minute just for Karpenter status. Each API call hits the DB (no Redis cache on this endpoint).

---

### P4 (CRITICAL): Blacklist API — 2000+ Redis Round Trips Per Request

`atharvaai_routes.py:412-442`: Iterates `risky_pools` SET, calls `redis.ttl()` + `redis.get()` for each member. With 1000 pools: **2000 sequential Redis calls** per HTTP request. Latency: 200–800ms just for the loop.

---

### P5 (CRITICAL): Metrics Batch — N+1 DB Queries + `db.flush()` Per Node

`metrics.py:154-200`: For each node in the batch: one `db.query().filter().first()` (full table scan via OR condition) + one `db.flush()`. For 20 nodes = 40 DB round-trips per batch. This is why node metrics appear seconds after they're collected.

---

### P6 (HIGH): Market View — O(N) Python Loop Over 2000+ Pools Per Request

`atharvaai_routes.py:2588`: Iterates all 2000+ pools in Python, applies per-pool transformation. Loads entire `market_view_cache` into memory per request. No server-side pre-filtering or pagination. Latency: 300–500ms per request.

---

### P7 (HIGH): Activity Log — All N DOM Nodes Rendered (No Virtualization)

`ClusterDetails.jsx:806-837`: `rebalancingActions.map()` renders every action as a DOM node. A cluster running for weeks has 500–2000+ actions. All rendered = 10,000+ DOM nodes. This alone explains visible stutter on the Activity Log tab.

---

### P8 (HIGH): No AbortController — Stale Data Flash on Navigation

None of the 12 `useEffect` API calls use `AbortController`. Navigate cluster A → B: all 12 requests for A continue running. When they resolve (500ms–2s), they call `setState` on the now-showing cluster B component → stale data briefly flashes.

---

### P9 (HIGH): 1991+ Pool Filter Runs Synchronously on Render Thread

`PoolRankings.jsx`: Every filter change (region, architecture, risk) re-runs `array.filter()` over 1991+ pools synchronously on the React render thread. No `useDeferredValue` or `useMemo`. Causes 50–100ms UI freeze per keystroke.

---

### P10 (MEDIUM): 30s Poll Fires Immediately on Mount → 15 Simultaneous Calls

`ClusterDetails.jsx`: Effect 1 fires 12 calls. Effect 2's `setInterval` also fires once on mount (no guard). Combined = **15 simultaneous API calls** on component mount before the user sees any data.

---

## SECTION 6 — COMPLETE LOAD WATERFALL (Why Every Event Is Slow)

```
T=0ms    User clicks cluster
T=0ms    ClusterDetails mounts → 12 parallel HTTP calls fire + 3 more (poll fires immediately)
T=0ms    Browser: 6-connection limit → 9 requests queue behind first 6
T=50ms   Backend receives /rebalancing/status → loops N actions, dict-unpacks per action (no cache)
T=100ms  Backend receives /nodes/detailed → N+1 DB queries for pod metrics
T=200ms  Backend receives /market-view → loads 2000 pool dicts, O(N) Python loop
T=200ms  Queued requests 7-15 start (unblocked)
T=400ms  Backend /blacklist → 2000 Redis calls start
T=500ms  First 6 responses → React starts rendering partial data
T=600ms  RebalancingTimeline mounts → 1s tick timer starts (60 re-renders/minute begin)
T=800ms  Remaining responses arrive → multiple setState calls → re-render cascade
T=1000ms UI fully loaded (1s blank screen to user)
T=1001ms Tick fires → full re-render begins
T=2000ms 30s poll timer re-fires → 3 more API calls
T=2001ms Next tick → re-render
... repeats until component unmounts
```

---

## SECTION 7 — PRIORITY FIX LIST

### STOP CLUSTER GROWTH (Immediate)

| Priority | Fix | File | Line |
|----------|-----|------|------|
| P0 | Verify orphan rollback returns error and retries (don't silently swallow) | auto_rebalancer.py | 3442, 2379 |
| P0 | Add `spot:node_active_action` check before launching 2nd replacement after 4h retry | auto_rebalancer.py | 1405-1480 |
| P0 | discovery.py: Check for active RebalancingAction before setting `state='running'` | discovery.py | 891 |
| P1 | Fix terminated instance cleanup: change `timedelta(minutes=5)` to `timedelta(minutes=30)` | discovery.py | 951 |
| P1 | termination_monitor: Set `Instance.state = 'terminating'` immediately on detection | termination_monitor.py | 172-185 |
| P1 | scan_orphans: Also scan nodes with `node_name` set if their action is marked `failed` | recovery_monitor.py | 182-300 |

### FIX RANKING SYNC (High)

| Priority | Fix | Impact |
|----------|-----|--------|
| P1 | Make UI and execution use the same sorting key (`expected_value` or `ml_score`, pick one) | Ranking mismatch |
| P1 | Unify blacklist: write BOTH `blacklist:pool:{key}` AND `risky_pools` SET on every blacklist event | Blacklist mismatch |
| P1 | Standardize `savings_pct` field: always percentage (0-100), never fraction | Scaling bug |
| P2 | Fix risk ceiling: UI and execution should use same `ClusterOptimizationSettings.risk_ceiling_percent` | Risk ceiling mismatch |
| P2 | Remove 65% hardcoded savings fallback in frontend | False savings display |

### FIX UI PERFORMANCE (High)

| Priority | Fix | Impact |
|----------|-----|--------|
| P1 | RebalancingTimeline: Only start 1s tick when countdown is active | Eliminates 60 re-renders/min |
| P1 | Fix blacklist API: use Redis pipeline instead of N individual calls | 800ms → 10ms |
| P1 | Fix metrics.py: batch load instances before loop, single commit at end | 40 DB ops → 2 |
| P1 | Add AbortController to all 12 ClusterDetails API calls | Eliminates stale data flash |
| P2 | Paginate activity log (max 20 rows) | Eliminates 10K DOM nodes |
| P2 | Add `useMemo` to recommendation arrays, PoolRankings filter | Eliminates CPU waste |
| P2 | Add page visibility guard to all polling intervals | Reduces background API load |
| P3 | Create batch endpoint `GET /clusters/{id}/full` to replace 12 individual calls | 1s load → 200ms |

---

## SECTION 8 — SYSTEM ARCHITECTURE FLAW (ROOT CAUSE OF ALL SYNC ISSUES)

The fundamental problem is that **there is no single shared state machine**. Each subsystem independently decides what is "true":

```
AWS EC2 API ──────────────────────────────────────────────┐
                                                           │
Discovery (5min) ──→ DB (PostgreSQL) ──→ API ──→ UI       │
                                                           │ All 4 read
Termination Monitor ──→ Redis blacklist ──→ Execution     │ different
                                                           │ sources at
Pool Ranking Service ──→ Redis cache (65min TTL) ──→ UI   │ different
                                                           │ times
Auto Rebalancer ──→ Redis + DB ──→ Agent ──→ AWS ─────────┘
```

**The fix is a write-through state machine:** every component that changes state (discovery, termination, rebalancer, emergency handler) must write to **one canonical state store** (Redis or DB) that ALL readers use consistently. Currently, each component writes to its own store without notifying the others.
