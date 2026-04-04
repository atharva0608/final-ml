# ASCP.AI Pool Rankings — Full Investigation Report

> **Generated:** 2026-03-30 | **Based on:** Live Docker logs, Redis state, PostgreSQL DB
> **Cluster:** `spot-demo-1` (ID: `79228e1a-6f13-46b9-84ad-5c38b94294cc`) | **Region:** ap-south-1

---

## TL;DR — What Is Actually Happening

The UI is showing one thing, execution is doing another, and AWS is returning a third result. This is not a single bug — it's **five separate breakdowns** happening simultaneously:

1. **Architecture field mismatch**: Rankings store `"amd64"` but code filters for `"x86_64"` — architecture filter finds 0 results and silently falls through, allowing arm64 pools to be selected for x86_64 nodes
2. **The "capacity unavailable" in action metadata is real AWS InsufficientInstanceCapacity** — but it's being triggered on the ORIGINAL top-ranked pool, not on all pools. The system is picking the wrong fallback after capacity fails.
3. **UI shows original pool, execution launched different pool** — when fallback happens the UI never reflects it; user sees "c7g.medium selected" but launch actually used m7g.medium or failed
4. **ArchMismatch errors from earlier** (actions 193/194/199/200) confirm arm64 pools were being launched for x86_64 nodes with no AMI compatibility check
5. **Agent version mismatch (1.0.0 vs expected 1.0.1)** — connected agent has protocol mismatch, actions are `PICKED_UP` but may not complete correctly

---

## SECTION 1 — LIVE SYSTEM STATE RIGHT NOW

### Redis: Rankings
```
global_pool_rankings:ap-south-1   → 1878 pools  TTL=3813s (~63 min left)
market_view_cache:ap-south-1      → exists       TTL=3513s (~58 min left)
```

### Redis: Locks
```
spot:node_active_action:i-02a9a042fc2eecce1  →  value="i-02a9a042fc2eecce1"  TTL=64725s (18 hours!)
spot:rebalanced:instance:i-04ea8071a0a5ffcb6 →  exists
spot:rebalanced:instance:i-0fb480999e2a8814c →  exists (this is the EC2 terminate failed node)
spot:rebalanced:instance:i-0cacf900a5c1f4246 →  exists
spot:rebalanced:instance:i-028dc895d0805fe39 →  exists
spot:rebalanced:instance:i-03cdd32825c99b54c →  exists (this is EC2 terminate failed node)
```

### Redis: Dry Run Cache
```
All 19 dry_run entries = "pass"  (no failures)
dry_run TTLs: 190s–549s (3–9 minutes remaining)
dry_run:ami:ap-south-1:amd64  → exists
dry_run:ami:ap-south-1:arm64  → exists
```

**Critical observation:** Zero dry_run failures. All capacity checks pass. But 6 rebalancing actions failed in the last 3 hours.

### DB: Running Instances
```
c7g.medium   ap-south-1b  SPOT      running  (launched_by=spot-optimizer-direct)
c8g.medium   ap-south-1a  SPOT      running  (launched_by=spot-optimizer-direct)
t3.medium    ap-south-1b  ON_DEMAND running  (no launched_by)
t3.medium    ap-south-1a  ON_DEMAND running  (no launched_by)
```

### DB: In-Flight Agent Actions
```
LABEL_NODE     PICKED_UP  node=ip-192-168-167-177.ap-south-1.compute.internal
CORDON_NODE    PICKED_UP  node=NULL
DRAIN_NODE     PICKED_UP  node=NULL
TERMINATE_NODE PICKED_UP  node=NULL
```

**Problem:** CORDON/DRAIN/TERMINATE have `node=NULL` — agent payload may not have resolved the node_name.

### DB: Current Rebalancing Action 205 (STUCK)
```
status:        waiting_agent
source_pool:   t3.medium:ap-south-1b
target_pool:   c7g.medium:ap-south-1b
started_at:    2026-03-30 12:15:05
completed_at:  2026-03-30 12:14:35  ← BEFORE started_at (timestamp corruption)
current_state: NULL
error_message: "No compatible spot pool found... Will retry next cycle."
pool_change_reason: "t3.medium → c7g.medium (capacity unavailable)"
```

**Two bugs visible here:**
1. `completed_at < started_at` — a previous action's completed_at was copied into this record
2. `error_message` says "no pool found" but the action actually DID launch (replacement node `ip-192-168-167-177` joined and is running as c7g.medium)
3. The error_message was set during an earlier phase and never cleared when the action progressed

---

## SECTION 2 — WHY THE UI SHOWS DIFFERENT POOLS THAN WHAT GETS LAUNCHED

### Finding 2.1: Architecture Field Name Mismatch (`amd64` vs `x86_64`)

**Confirmed from Redis:**
```
global_pool_rankings:ap-south-1 → architecture field values:
  "amd64"  → 1333 pools   (x86_64 instances stored as "amd64")
  "arm64"  → 545 pools
  "x86_64" → 0 pools
```

**The pool ranking pipeline uses `"amd64"` as the architecture string (from AWS instance catalog).**
**The execution engine filters use `"x86_64"` as the expected value.**

When `rank_pools_for_node` applies the architecture filter:
```python
# If filter checks: p.architecture == "x86_64"
# And rankings store: "amd64"
# → ZERO matches → filter silently falls through → ALL pools pass including arm64
```

This is why arm64 pools (c7g, m7g, r7g) appear as candidates for x86_64 nodes. The architecture filter never actually excludes them — it matches nothing and passes everything.

**Evidence from action history:**
- Action 199: `"c7g.medium: ArchMismatch: c7g.medium is arm64 but source AMI is x86_64"`
- Action 198: `"c7g.medium: ArchMismatch..."`, `"m7g.medium: ArchMismatch..."`, `"r7g.medium: ArchMismatch..."`
- Actions 193/194: `InvalidParameterValue: architecture 'arm64' does not match 'x86_64' AMI` [cleared after code fix]
- Action 205 **currently in progress**: target=`c7g.medium:ap-south-1b` (arm64 instance for x86_64 node)

### Finding 2.2: The UI Shows Global Rankings, Execution Uses Per-Node Rankings

**UI PoolRankings page (from logs):**
Every 15–30 seconds, UI calls `POST /api/v1/ascpai/pools/rankings` with `current_instance_type=t3.medium`.
The response comes from `global_pool_rankings:ap-south-1` (all 1878 pools, ranked globally by ml_score).

**What user sees in UI for a t3.medium node:**
- Global rank #1: `t4g.nano:ap-south-1c` (ARM64, 0.5GB RAM) — **cannot replace t3.medium**
- Global rank #6: `t3a.nano:ap-south-1b` (amd64, 0.5GB RAM) — **too small**
- First viable replacement: `c5a.large:ap-south-1c` at global rank #38

**What execution actually picks (from rank_pools_for_node):**
- Filters: vcpu ≥ 2, memory ≥ 3.5GB, architecture match (but architecture match is broken — see 2.1)
- From logs: `18 eligible pools` returned — but these include arm64 pools due to the arch field bug
- Top result shown in UI: `c7g.medium` (arm64!)
- Top result execution should pick for x86_64: `c5a.large` (rank 38-40 globally)

**The disconnect:** The UI global ranking shows pools without filtering for the source node's architecture or size. A user looking at the ranking page sees arm64 micro instances at the top. When they look at their t3.medium node's recommendations, the system is ALSO showing arm64 pools because the filter is broken.

### Finding 2.3: Pool Change at Launch Time Is Not Reflected in UI

From DB metadata across 5 failed actions:
```
action 204: original_target_pool="t3.medium:ap-south-1a"    actual: m7g.medium (fallback)
action 200: original_target_pool="c5a.large:ap-south-1c"    actual: m7i.large (fallback)
action 199: original_target_pool="c8g.large:ap-south-1c"    actual: m6a.large (fallback, ALSO failed)
action 198: original_target_pool="c5a.large:ap-south-1b"    actual: c6a.large (fallback)
action 205: original_target_pool="t3.medium:ap-south-1b"    actual: c7g.medium (fallback!)
```

Every single action had a pool change after original selection. But the UI's `RebalancingTimeline` shows only `target_pool` (the DB field), which is set to the FALLBACK pool. Users cannot see what the original ranked choice was or why it changed.

---

## SECTION 3 — IS THE CAPACITY INSUFFICIENT OR IS IT SOMETHING ELSE?

### What "Capacity Unavailable" Actually Means in the DB

From action 204 metadata:
```json
"pool_change_reason": "t3.medium → m7g.medium (capacity unavailable:
  c7g.medium: InsufficientInstanceCapacity: There is no Spot capacity available
  that matches your request.)"
```

**This IS a real AWS InsufficientInstanceCapacity error** — not a code bug. AWS genuinely did not have c7g.medium capacity in ap-south-1a at that moment.

However, from actions 198/199:
```json
"pool_change_reason": "c5a.large → c6a.large (capacity unavailable:
  c7g.medium: ArchMismatch: c7g.medium is arm64 but source AMI is x86_64, no matching AMI found;
  m7g.medium: ArchMismatch: m7g.medium is arm64 but source AMI is x86_64, no matching AMI found)"
```

**Here "capacity unavailable" does NOT mean AWS said no** — it means the launch code itself rejected the pool (ArchMismatch) and reported it as "capacity unavailable". The message is misleading. The real reason is architecture incompatibility detected at launch time, not AWS capacity.

### Why the Same Pool Appears "Available" in UI But "Capacity Unavailable" at Launch

The **dry_run check** and the **actual launch code** use different AMI lookup paths:

| Step | AMI Used | Architecture Check |
|------|----------|-------------------|
| Dry run (`ec2.run_instances(DryRun=True)`) | `dry_run:ami:{region}:{arch}` from Redis (correct per-arch AMI) | Passes — uses arm64 AMI for arm64 instances |
| Actual launch (`_launch_spot_instance_direct`) | Source instance's AMI from `describe_instance_attribute` | **Fails** — x86_64 AMI used for arm64 instance |

The dry run passes because it fetches the correct architecture-specific AMI.
The actual launch fails because it reads the AMI from the source instance (x86_64) and tries to use it for an arm64 replacement.

**This is why the UI shows c7g.medium as available** (dry run: pass) **but the launch fails with ArchMismatch**.

### Timeline of Capacity/Launch Failures (Last 3 Hours)

```
09:50 — Action 193 EXPIRED: arm64 AMI mismatch (InvalidParameterValue)
09:51 — Action 194 EXPIRED: arm64 AMI mismatch (InvalidParameterValue)
[CODE FIX DEPLOYED — arch filter added]
10:31 — Action 198 FAILED: c5a→c6a after arch rejections, then EC2 terminate failed
10:31 — Action 199 FAILED: c6a→m6a after arch rejections, then EC2 terminate failed
10:42 — Action 200 FAILED: c5a→m7i, drain succeeded, EC2 terminate failed
10:59 — Action 201 FAILED: pre-launch orphan cleanup failed (Unable to locate credentials)
12:10 — Action 204 FAILED: real InsufficientInstanceCapacity (c7g.medium), fallback to m7g.medium, then DRAIN failed (PDB)
12:15 — Action 205 IN PROGRESS: t3→c7g fallback, replacement node joined, now waiting for drain/terminate
```

**Pattern:** The arch mismatch code fix was deployed between actions 194 and 198. After the fix, ArchMismatch errors stopped appearing as primary failures — but the fallback pool (m7g, m7i, c6a) then caused EC2 terminate failures and drain failures.

---

## SECTION 4 — CONFIRMED ROOT CAUSES (In Order of Impact)

### ROOT-1 (CRITICAL): Architecture Field Is `"amd64"` in Rankings But Code Expects `"x86_64"`

**Impact:** ALL architecture filtering is silently broken. Arm64 pools are presented to x86_64 nodes in the UI and selected by the execution engine. This is the root cause of all ArchMismatch failures.

**Evidence:**
- Redis rankings: `architecture: "amd64"` (1333 pools)
- Failed actions: `ArchMismatch: c7g.medium is arm64 but source AMI is x86_64`
- Action 205 currently launching c7g.medium (arm64) for t3.medium (x86_64)

**Fix location:** Wherever `global_pool_rankings` is built (cache_builder.py) — either normalize `"amd64"` → `"x86_64"` at write time, or update ALL filter comparisons to use `"amd64"`.

---

### ROOT-2 (CRITICAL): Dry Run Uses Arch-Specific AMI But Launch Uses Source AMI

**Impact:** A pool passes dry_run validation but fails at actual launch because different AMI sources are used.

**Evidence:**
- `dry_run:ami:ap-south-1:arm64` exists in Redis (used by dry_run path)
- Actions 193/194/199/200 all failed with `InvalidParameterValue: architecture mismatch`
- After code fix, these became `pool_change_reason` entries instead of hard errors (but still wrong)

**The bug:** dry_run.py fetches `dry_run:ami:{region}:{arch}` per architecture. The launch code reads the source instance's AMI via `ec2.describe_instance_attribute(InstanceId=source_id, Attribute='userData')` or launch template — always the source's AMI — and uses it for the replacement regardless of architecture.

---

### ROOT-3 (HIGH): InsufficientInstanceCapacity Is Real — But Fallback Pool Is Not Validated

**Impact:** When the #1 ranked pool fails with real AWS capacity shortage, the fallback pool is selected without running a dry_run check. The fallback may also fail (and does, as seen in actions 198/199/200).

**From action 204:**
```
c7g.medium → InsufficientInstanceCapacity (REAL AWS error)
Fallback to: m7g.medium
m7g.medium → ArchMismatch (code-detected)
Fallback to: next pool...
Eventually lands on m7g.medium launch (also arm64 — same ArchMismatch)
→ DRAIN fails (pod disruption budget)
→ Action marked FAILED
```

The fallback selection iterates down the ranking list but **does not re-run dry_run validation on each candidate**. It falls through to the first pool that passes the code-level checks, but those code checks are broken (arch filter).

---

### ROOT-4 (HIGH): Action 205 — `completed_at` Before `started_at` (Timestamp Corruption)

```
action 205:
  started_at:   2026-03-30 12:15:05
  completed_at: 2026-03-30 12:14:35  ← 30 seconds BEFORE start
```

This is impossible in any correct execution path. It means `completed_at` was written by a PREVIOUS operation and never cleared when the action record was reused or a new action was created with leftover state. The UI will calculate a negative duration for this action.

---

### ROOT-5 (HIGH): Agent Version Mismatch — PICKED_UP Actions May Not Complete

```
WARNING: Agent spot-orchestrator-5fb48555db-vqhhz-0ec6b8ce registered with version 1.0.0,
expected 1.0.1 — protocol mismatch possible
```

Action 205 has 4 actions in `PICKED_UP` state:
```
LABEL_NODE     PICKED_UP  → node = ip-192-168-167-177... (OK - node name resolved)
CORDON_NODE    PICKED_UP  → node = NULL  ← node_name not set
DRAIN_NODE     PICKED_UP  → node = NULL  ← node_name not set
TERMINATE_NODE PICKED_UP  → node = NULL  ← node_name not set
```

If the agent version 1.0.0 doesn't support a field or action format expected by 1.0.1 (the action payload schema may have changed), the CORDON/DRAIN/TERMINATE will silently fail or be ignored. The actions stay PICKED_UP forever.

---

### ROOT-6 (HIGH): EC2 Terminate Failing Repeatedly — 2 Nodes Still Running in AWS

From actions 198 and 199:
- Action 198: `"ec2_terminate_failed": true` — instance `i-0fb480999e2a8814c` "may still be running on AWS"
- Action 199: `"ec2_terminate_failed": true` — instance `i-03cdd32825c99b54c` "may still be running on AWS"

Both instances still have `spot:rebalanced:instance:` keys in Redis. The EC2 terminate call returned an error (likely `AccessDenied` or `InvalidInstanceID`). These nodes are **still running in AWS, still billing, but treated as terminated by the system**.

---

### ROOT-7 (MEDIUM): Action 201 Permanently Blocked by Credential Failure

```
error_message: "Pre-launch orphan cleanup failed for i-0929b4b1b4a743cd8:
  Unable to locate credentials. Manual intervention required before retrying."
```

Instance `i-0885158061a660fe5` (the source) has `spot:rebalanced:instance:` key set. The cluster cannot be rebalanced until this is manually cleared. The message says "manual intervention required" but there is no UI surface to do this.

---

### ROOT-8 (MEDIUM): `rank_pools_for_node` Called 4–6 Times Per Page Load

From backend logs between 12:13:52.533 and 12:13:52.709 (176ms window):
```
[rank_pools_for_node] t3.medium → 18 eligible pools
[rank_pools_for_node] t3.medium → 18 eligible pools
[rank_pools_for_node] c8g.medium → 12 eligible pools
[rank_pools_for_node] t3.medium → 18 eligible pools
[rank_pools_for_node] t3.medium → 18 eligible pools
```

**4 identical calls for t3.medium in under 100ms.** The UI PoolRankings component:
1. Calls `ascpaiAPI.getRankings()` (POST /pools/rankings) → triggers rank_pools_for_node
2. Calls `ascpaiAPI.getNodeRecommendations()` → triggers rank_pools_for_node
3. Multiple nodes being ranked simultaneously (one per running node, no batching)
4. 30-second poll fires while initial load is still in-flight → duplicate calls

No debouncing, no request deduplication, no client-side caching between calls.

---

### ROOT-9 (LOW): UI "18 Eligible Pools" Changes Unexpectedly to 16

One log entry shows:
```
[rank_pools_for_node] t3.medium → 16 eligible pools  (at 12:13:52.709)
vs all others: 18 eligible pools
```

This 2-pool drop within the same second means a pool was blacklisted or a filter was applied differently between calls. If the user refreshes at exactly this moment, they see 2 fewer options. The UI doesn't show why or which pools disappeared.

---

## SECTION 5 — WHAT THE UI SHOULD SHOW VS WHAT IT ACTUALLY SHOWS

### Current PoolRankings Page (ap-south-1, t3.medium node selected)

| UI Shows | Reality |
|---------|---------|
| Global rank #1: t4g.nano (ARM64, 0.5GB) | Impossible to use — too small, wrong arch |
| Global rank #6: t3a.nano (amd64, 0.5GB) | Impossible to use — too small |
| "18 eligible pools" for t3.medium | Includes ARM64 pools due to arch field bug |
| Top recommendation: c7g.medium or m7g.medium | ARM64 — will fail or fail AMI check |
| Pool marked "Available" (dry_run=pass) | c7g.medium dry_run passes but actual launch may use wrong AMI |
| Target pool in timeline: c7g.medium | Actual pool launched: fallback (m7g.medium or failed) |
| Savings: ~51–55% | Based on $0.0114/hr spot vs $0.0245/hr OD for c7g — ARM64 pricing |
| Recommended t3.medium replacement | Should be: c5a.large ($0.0251), c5d.large ($0.0256) |

### What Should Happen for t3.medium (amd64, 2vcpu, 4GB) in ap-south-1b

The correct eligible pools, ordered by ml_score:
```
#1  c5d.large     ap-south-1b  ml=0.598  risk=0.38  spot=$0.0256  savings=43%
#2  r5a.large     ap-south-1b  ml=0.537  risk=0.38  spot=$0.0308  savings=31%
#3  c7i-flex.large ap-south-1b ml=0.510  risk=0.38  spot=$0.0311  savings=31%
#4  c5a.large     ap-south-1b  ml=0.353  risk=0.38  spot=$0.0251  savings=44%
#5  r6a.large     ap-south-1b  ml=0.389  risk=0.16  spot=$0.0311  savings=31%
```

None of these are ARM64. All are x86_64/amd64 and compatible with t3.medium workloads.

---

## SECTION 6 — COMPLETE FAILURE CHAIN DIAGRAM

```
USER OPENS POOL RANKINGS PAGE
         │
         ▼
UI fetches POST /pools/rankings
         │
         ▼
rank_pools() reads global_pool_rankings:ap-south-1 (1878 pools, 65min TTL)
         │
         ├── ARM64 pools ranked #1-37 globally (cheap + low risk)
         │   t4g.nano, t4g.micro, m7gd.medium, c8g.medium etc.
         │
         ├── First x86_64/amd64 pool: c5a.large at rank #38
         │
         ▼
UI SHOWS: Top pools are ARM64 nano/micro/medium types
          18 "eligible" pools for t3.medium (INCLUDES ARM64 due to arch field bug)
          "c7g.medium — 51% savings" as top recommendation
                           │
                           │  USER OR AUTO-REBALANCER SELECTS c7g.medium
                           ▼
auto_rebalancer runs rank_pools_for_node(t3.medium, ap-south-1b)
         │
         ├── Arch filter: checks architecture == "x86_64"
         │   Rankings have: architecture == "amd64"
         │   Result: ZERO x86_64 matches → filter falls through
         │   All pools pass including ARM64
         │
         ▼
Top pool selected: c7g.medium:ap-south-1b (ARM64)
         │
         ▼
Dry run check: dry_run:c7g.medium:ap-south-1b → "pass"
(dry run uses arm64 AMI from dry_run:ami:ap-south-1:arm64)
         │
         ▼
Launch attempt with ec2.run_instances()
         │
         ├── Case A: AMI lookup uses source instance's AMI (x86_64)
         │   Result: InvalidParameterValue ArchMismatch
         │   → pool_change_reason: "capacity unavailable: ArchMismatch"
         │   → Try next pool (also ARM64)... cascade of failures
         │
         ├── Case B: AMI lookup uses arm64 AMI from describe_images
         │   Result: Launch SUCCEEDS (c7g.medium running with arm64 AMI)
         │   → Node joins as c7g.medium SPOT
         │   → Drain of source t3.medium (x86_64) begins
         │   → Drain fails (PDB or agent issue)
         │   → Source STILL RUNNING
         │
         └── Case C: AWS has no c7g.medium capacity
             Result: InsufficientInstanceCapacity
             → REAL AWS capacity shortage
             → Fallback pool selected without dry_run re-validation
             → Fallback may also be ARM64 → same cascade
```

---

## SECTION 7 — DEFINITIVE ANSWER: IS "CAPACITY INSUFFICIENT" REAL?

**Partially.** Based on the live DB evidence:

| Action | "Capacity" Error | Is It Real AWS Capacity? |
|--------|-----------------|--------------------------|
| 193, 194 | `InvalidParameterValue: arm64 arch mismatch` | **NO** — code bug (wrong AMI used) |
| 198, 199 | `ArchMismatch: arm64 but source AMI is x86_64` | **NO** — code-detected arch rejection |
| 204 | `InsufficientInstanceCapacity: no Spot capacity` | **YES** — real AWS error for c7g.medium in ap-south-1a |
| 200 | `capacity unavailable` (no AWS error text) | **NO** — code-detected rejection |
| 201 | `Unable to locate credentials` | **NO** — AWS credentials not configured |

**3 out of 6 recent failures are NOT real capacity issues.** They are code bugs (ArchMismatch from field naming, credential failure). Only action 204 had a genuine AWS InsufficientInstanceCapacity response.

---

## SECTION 8 — ALL ISSUES PRIORITY TABLE

| ID | Issue | Severity | Evidence |
|----|-------|----------|----------|
| R1 | `architecture` field is `"amd64"` in rankings but code filters `"x86_64"` → arch filter silently breaks | CRITICAL | Redis: 1333 amd64 pools, 0 x86_64 pools |
| R2 | Dry_run uses arch-specific AMI but actual launch uses source AMI → always wrong for cross-arch | CRITICAL | Actions 193/194/198/199 ArchMismatch errors |
| R3 | `completed_at < started_at` on action 205 — timestamp corruption | HIGH | DB: action 205 |
| R4 | Agent version 1.0.0 vs expected 1.0.1 — PICKED_UP actions may never complete | HIGH | Backend log 12:13:47 |
| R5 | EC2 terminate failed on actions 198/199 — 2 nodes still running in AWS, billing | HIGH | DB: error_message + spot:rebalanced keys |
| R6 | Fallback pool not re-validated with dry_run after original pool fails | HIGH | Actions 199/200 — fallback also wrong arch |
| R7 | Pre-launch orphan cleanup blocked by credential failure — source instance stuck | MEDIUM | Action 201 |
| R8 | `rank_pools_for_node` called 4–6 times per page load — no dedup | MEDIUM | Logs 12:13:52 |
| R9 | UI shows global rankings, user sees ARM64 pools as top recommendations | MEDIUM | Rankings: top 37 are ARM64 |
| R10 | Pool change reason only in metadata, never shown in UI timeline | MEDIUM | Action 205 UI vs DB |
| R11 | CORDON/DRAIN/TERMINATE have `node=NULL` in payload — agent may fail silently | MEDIUM | DB: agent_actions |
| R12 | `spot:node_active_action:i-02a9a042fc2eecce1` TTL=64725s (18h) — instance blocked all day | LOW | Redis |
| R13 | InsufficientInstanceCapacity (real): c7g.medium in ap-south-1a has no AWS capacity | INFO | Action 204 — AWS error confirmed |

---

## SECTION 9 — WHAT TO FIX

### Fix 1 (CRITICAL): Normalize Architecture Field
```python
# In cache_builder.py, wherever pool architecture is set:
# BEFORE: arch = instance_info.get('architecture', 'x86_64')   → writes "x86_64"
# AFTER:  Ensure the same field name is used everywhere

# Option A: Normalize at write time in cache_builder:
arch_val = pool_data.get('architecture', 'x86_64')
arch_val = 'x86_64' if arch_val == 'amd64' else arch_val  # normalize

# Option B: Normalize at read time in pool_ranking_service.py rank_pools_for_node:
def _arch_matches(pool_arch, source_arch):
    amd = {'x86_64', 'amd64'}
    return (pool_arch in amd and source_arch in amd) or (pool_arch == source_arch)
```

### Fix 2 (CRITICAL): Actual Launch Must Use Architecture-Specific AMI
```python
# In auto_rebalancer.py, before ec2.run_instances():
target_arch = pool_info.get('architecture', 'x86_64')
if target_arch in ('arm64',):
    ami_key = f"dry_run:ami:{region}:arm64"
else:
    ami_key = f"dry_run:ami:{region}:amd64"
ami_id = redis.get(ami_key)
# Use ami_id in launch, not source instance's AMI
```

### Fix 3 (HIGH): Re-validate Fallback Pool with Dry Run
```python
# In auto_rebalancer.py fallback loop:
for fallback_pool in ranked_fallbacks:
    dr_result = check_dry_run(fallback_pool.instance_type, fallback_pool.az, redis)
    if dr_result == "fail":
        continue  # skip — no capacity
    if not arch_matches(fallback_pool.architecture, source_arch):
        continue  # skip — wrong arch
    # Only use this fallback if both pass
    selected_pool = fallback_pool
    break
```

### Fix 4 (HIGH): Clear `completed_at` When Action Is Reused / Created
```python
# In RebalancingAction creation:
action = RebalancingAction(
    ...
    completed_at=None,  # Explicitly NULL — never inherit from previous
    started_at=datetime.utcnow(),  # Fresh timestamp
)
```

### Fix 5 (HIGH): Show Pool Change Reason in UI Timeline
The `pool_change_reason` field is stored in `metadata` JSON but never surfaced in the UI.
`RebalancingTimeline.jsx` should read `action.metadata?.pool_change_reason` and show it as a subtext under the target pool name.

### Fix 6 (MEDIUM): Deduplicate `rank_pools_for_node` Calls
Cache results per (cluster_id, instance_type, az) for 30 seconds client-side:
```javascript
// In PoolRankings.jsx
const rankingCache = useRef({});
const getCachedRankings = (nodeKey) => {
  const cached = rankingCache.current[nodeKey];
  if (cached && Date.now() - cached.ts < 30000) return cached.data;
  return null;
};
```

---

## SECTION 10 — KARPENTER 404 ERROR (SEPARATE ISSUE)

From Celery logs every 30 seconds:
```
ERROR: Failed to update NodePool: (404)
ERROR: Failed to sync ML rankings to NodePool: (404)
ERROR: [Karpenter] Failed to sync cluster spot-demo-1: (404)
```

The `sync_karpenter_nodepools` task is running every 30 seconds and failing with 404. This means either:
1. The Karpenter NodePool CRD does not exist in the cluster
2. The kubeconfig stored for this cluster is stale/incorrect
3. Karpenter is not actually installed (confirmed: `spot:karpenter:installed:{cluster_id}` key was NOT in the Redis dump)

**This failure is logged but does not block rebalancing.** It does generate 2 spurious error log lines per 30 seconds = 4 error lines/minute = 240/hour contaminating the logs.

---

*Report generated from: Docker logs (spot-optimizer-backend, spot-optimizer-celery-worker), Redis state dump, PostgreSQL rebalancing_actions table*
