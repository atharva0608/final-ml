# Backend Issues & Root Cause Analysis

## Auto-Rebalancing: Why Cluster Size Grows Instead of Staying Constant

> **Summary**: The auto-rebalancer is designed to swap On-Demand (OD) nodes for Spot nodes 1:1. In practice, multiple code paths cause the cluster to **grow** (launch new nodes without terminating old ones), resulting in more instances than the original cluster size.

---

## 🔴 CRITICAL: Cluster Growth Bugs

### Issue 1: ASG `ShouldDecrementDesiredCapacity=False` on Detach (Lines 2427–2432)

**File**: `auto_rebalancer.py`

**Problem**: When detaching the old OD node from the ASG before termination, the code uses `ShouldDecrementDesiredCapacity=False`. This means the ASG's DesiredCapacity stays at N even though the instance is being removed. While the code later decrements DesiredCapacity manually (line 2469–2474), if the decrement step fails for any reason (network error, IAM permission issue, ASG race condition), the ASG sees `Desired=N` but only `N-1` instances running, so it **auto-launches a new OD replacement** when Launch processes are resumed.

**Impact**: Every failed decrement = 1 extra OD node in the cluster.

**Fix**: Use `ShouldDecrementDesiredCapacity=True` on `detach_instances` call, removing the need for a manual decrement step. Alternatively, set DesiredCapacity to `N-1` BEFORE detaching, so the ASG never sees a shortfall.

---

### Issue 2: Spot Instance Launched BEFORE Old Node Is Terminated (2-Phase Design Flaw)

**File**: `auto_rebalancer.py`, Lines 1007–1256

**Problem**: The 2-phase approach launches a new spot instance in Phase 1 (line 1161), then waits for it to join K8s, and only then creates the CORDON→DRAIN→TERMINATE sequence in Phase 2. This means for the entire duration between Phase 1 and Phase 2 completion (potentially 15–45 minutes), the cluster has **N+1** nodes. If any failure occurs during Phase 2 (drain fails, terminate fails, agent disconnects), the old node is never removed but the new spot is already running.

**Impact**: During normal operation, the cluster temporarily has N+1 nodes. On any Phase 2 failure, this becomes permanent.

**Evidence**: Comments in the code itself acknowledge this: "Cluster size math: we launched 1 spot BEFORE cordon, so total = N" (line 2458). But this math only works if the termination always succeeds.

**Partial Mitigation Exists**: Rollback logic (`_do_rollback_terminate_orphan_spot`) tries to terminate the orphan spot on failure, but it has its own failure modes (see Issue 5).

---

### Issue 3: Last-Node Guard Launches Spot Without Corresponding OD Termination (Lines 3037–3171)

**File**: `auto_rebalancer.py`

**Problem**: When a cluster has only 1 total node, the "last-node guard" launches a new spot instance directly (line 3134) to grow the cluster to 2 nodes, then `continue`s (line 3171) — it does NOT create a rebalancing action to terminate the old OD node. The intent is for "next cycle" to handle the OD→Spot swap, but:
1. The next cycle sees 2 nodes (1 OD + 1 Spot) → creates a new rebalancing action for the OD node
2. If the new spot hasn't fully joined by next cycle, the guard might trigger AGAIN (15-minute Redis cooldown might not be enough)
3. The cluster grows from 1 → 2 permanently if the rebalancing action for the OD node fails

**Impact**: Cluster grows by 1 node for single-node clusters.

---

### Issue 4: Spot Recovery Can Launch Duplicate Replacements (Lines 3173–3343)

**File**: `auto_rebalancer.py`

**Problem**: The spot recovery section looks for directly-launched spot instances that appear terminated in the DB and launches replacements. However:
1. **24-hour lookback** (line 3207) is too aggressive — it can catch instances from old, completed rebalancing cycles that have already been accounted for.
2. **DB state can be stale**: An instance may show as 'terminated' in the DB but be 'running' in AWS (the AWS verify check at line 3235 tries to catch this, but can fail due to IAM issues).
3. **The recovery creates a raw EC2 launch** (line 3315) with no corresponding rebalancing action and no tracking of the launched instance. If the old spot was actually still running, the cluster now has an extra node.

**Impact**: Phantom launches that grow the cluster.

**Comment in code**: "A false positive here causes cascade launches (the bug that spawned 5 instances)" (line 3234) — this has already happened.

---

### Issue 5: Orphan Spot Rollback Uses Fragile Fallback Query (Lines 1634–1645)

**File**: `auto_rebalancer.py`

**Problem**: When rolling back a failed action, `_do_rollback_terminate_orphan_spot` first tries to find the orphan by `replacement_spot_instance_id` from metadata. If that fails, it falls back to "newest SPOT created since action start" (line 1636). In a cluster with concurrent rebalancing actions, this can **terminate the wrong spot instance** — one that belongs to a different, successful rebalancing action. The rollback then leaves the failed action's orphan running.

**Impact**: Wrong spot terminated + orphan left running = cluster grows.

---

### Issue 6: Emergency Rebalancer Terminates Without Guaranteed Replacement (Lines 225–280 of `emergency_rebalancer.py`)

**File**: `emergency_rebalancer.py`

**Problem**: For Karpenter-installed clusters, the emergency rebalancer directly terminates the interrupted instance (line ~270) with only a comment "Karpenter should auto-provision a replacement". But Karpenter may not provision if:
- NodePool has no compatible instance types
- Spot capacity is unavailable in the target AZ
- Karpenter itself is down or misconfigured

There is NO verification that Karpenter actually provisions a replacement. If it doesn't, the cluster shrinks by 1.

**Impact**: Cluster shrinks during emergencies (opposite of growing, but equally problematic for maintaining size).

---

## 🟠 HIGH: Race Conditions & Timing Issues

### Issue 7: Stale DB State Causes Re-Targeting of Already-Terminated Nodes

**File**: `auto_rebalancer.py`, Lines 3441–3451

**Problem**: The main scan loop queries `Instance.state == 'running'` to find OD nodes (line 3449). But after a successful rebalancing, there's a window where:
1. EC2 instance is terminated in AWS
2. DB record still shows `state='running'` (discovery sync hasn't run yet)
3. Auto-rebalancer targets the same instance for a NEW rebalancing action
4. Phase 1 launches a new spot (cluster grows)
5. Phase 2 tries to terminate the already-terminated instance — may succeed (idempotent) or fail

**Partial Fix Exists**: Lines 3978–3999 check for "recent completed action" and mark the instance as terminated. But this only covers the last 2 hours and requires the JSON metadata query (`op('->>') ('instance_id')`) to work correctly on the DB engine.

**Impact**: Duplicate rebalancing actions for the same source instance = cluster grows by 1 per duplicate.

---

### Issue 8: Phase 1 ↔ Phase 2 Resolution Window (Spot Baseline Race)

**File**: `auto_rebalancer.py`, Lines 1853–1864

**Problem**: Phase 2 resolution checks if `spot_count > spot_baseline` to detect that a new spot joined. But `spot_baseline` is recorded at Phase 1 creation time (line 1314). If another concurrent action's spot joins between Phase 1 creation and Phase 2 resolution, the `spot_count` goes up from a different action's spot, triggering Phase 2 prematurely.

**Partial Fix Exists**: The "pinned replacement" check (line 1870–1877) tries to match the exact `replacement_spot_instance_id`. But if the pre-registered instance hasn't been updated from 'pending' to 'running' in the DB yet, this check fails and falls back to the unreliable `spot_baseline` comparison.

**Impact**: Phase 2 may proceed using a different action's spot replacement → two OD nodes get drained for one spot replacement.

---

### Issue 9: `_seed_instances_from_redis` Creates Phantom OD Nodes (Lines 1429–1555)

**File**: `auto_rebalancer.py`

**Problem**: When the instances table is empty, `_seed_instances_from_redis` creates synthetic Instance records from Redis node telemetry with `lifecycle=ON_DEMAND` (line 1525). These "seeded" instances use `ip-xxx-xxx-xxx-xxx` as instance IDs, not real EC2 `i-xxx` IDs. If discovery later populates the real instances, the seeded records remain as stale phantom nodes (they have `ip-` prefix, not `i-` prefix - there's a cleanup at line 2884, but it only marks them terminated, it doesn't prevent them from being created again on the next cycle if the DB was wiped).

**Bigger Problem**: The seeded instances get targeted for rebalancing (line 3464). But `_launch_spot_instance_direct` requires a real EC2 instance ID to copy AMI/security groups from. If the source is `ip-192-168-14-254`, the spot launch fails, but the action is marked `in_progress` and blocks the cluster's rebalancing queue until the 45-minute stale-action expiry kicks in.

**Impact**: Wasted 45 minutes per seeded instance + blocks real rebalancing.

---

### Issue 10: Concurrent Celery Worker Execution (Lines 1697–1701)

**File**: `auto_rebalancer.py`

**Problem**: The Redis lock `lock:workers.auto_rebalancer` (line 1698) uses `nx=True, ex=300` — a 5-minute TTL. The auto-rebalancer Celery task itself can take longer than 5 minutes (especially with multiple clusters, AWS API calls, and Phase 2 resolution). If it does, the lock expires while still running, and a second Celery worker can start. Both workers now:
1. Process the same clusters
2. Create duplicate rebalancing actions
3. Launch duplicate spot instances

**Impact**: Double actions, double launches → cluster grows.

---

## 🟡 MEDIUM: Logic & Safety Gate Issues

### Issue 11: Cooldown Bypass for OD→Spot Always Applies (Lines 3361–3409)

**File**: `auto_rebalancer.py`

**Problem**: The cooldown between rebalancing actions (default 60 minutes) is bypassed whenever OD nodes exist (line 3404–3408). This means if a rebalancing action fails and the OD node is still running, the next cycle (15 seconds later) immediately creates a new action. With rapid failures, this can cause:
1. Multiple failed actions piling up
2. Multiple spot instances launched (Phase 1 succeeds) but not cleaned up fast enough
3. Cluster grows by N spots before rollback catches up

**Impact**: Rapid-fire spot launches during failure cascades.

---

### Issue 12: Daily Limit Bypass for OD→Spot (Lines 2950–2979)

**File**: `auto_rebalancer.py`

**Problem**: The `max_rebalances_per_24h` limit is bypassed for OD→Spot conversions (lines 2966–2979). This is intentional but dangerous: if rebalancing keeps failing (terminate fails, OD node stays), the same OD node gets re-targeted every cycle with no daily cap. Combined with Issue 11, this creates an unbounded loop of spot launches.

**Impact**: No upper bound on spot launches for a persistently failing cluster.

---

### Issue 13: Karpenter Timeout Proceeds with Drain Anyway (Lines 2064–2069)

**File**: `auto_rebalancer.py`

**Problem**: When the Karpenter spot wait times out but other nodes exist, the code proceeds with CORDON→DRAIN→TERMINATE anyway (line 2065–2069). The assumption is "pods can reschedule if Karpenter doesn't provision". But:
1. If Karpenter never provisions a replacement, the cluster shrinks permanently
2. The drained node's pods need somewhere to go — if remaining nodes are already at capacity, pods enter Pending state
3. No mechanism exists to undo the drain if Karpenter fails to provision

**Impact**: Cluster shrinks by 1 node per timeout.

---

### Issue 14: S2S Diversification Can Trigger Infinite Migrations

**File**: `auto_rebalancer.py`, Lines 3504–3870

**Problem**: The Spot-to-Spot (S2S) diversification logic triggers when `>1 node shares the same pool`. After migrating node A from pool X to pool Y, if the ML ranking changes next cycle and recommends pool X again for a different reason (opportunistic, risk), the S2S logic may migrate another node back to pool X, recreating the "duplicate pool" condition. This creates a cycle:
1. Two nodes on c5.large:us-east-1a → S2S migrates one to m5.large:us-east-1b
2. ML ranking changes → opportunistic trigger migrates m5.large:us-east-1b back to c5.large:us-east-1a (lower risk + better savings)
3. Back to two nodes on c5.large:us-east-1a → S2S triggers again

Each migration creates a temporary N+1 state (Phase 1 launches before Phase 2 terminates).

**Impact**: Cluster grows during each migration cycle.

---

### Issue 15: `detach_instances` Error Handling Is Too Lenient (Lines 2427–2439)

**File**: `auto_rebalancer.py`

**Problem**: When `detach_instances` fails (line 2433), the code logs a warning and continues to terminate + decrement. But if the instance is still attached to the ASG when terminated, the ASG detects the termination and may auto-launch a replacement (since Launch processes are resumed in the `finally` block at line 2491). The manual decrement (line 2469) happens AFTER the terminate, so there's a window where:
1. Instance terminated while still in ASG
2. ASG detects unhealthy instance
3. Launch process resumed
4. ASG launches replacement before the decrement takes effect

**Impact**: Race condition causes ASG to auto-launch OD replacement.

---

## 🔵 LOW: Code Quality & Observability Issues

### Issue 16: `_launch_spot_instance_direct` Error Reporting Is Opaque

**File**: `auto_rebalancer.py` (function defined earlier in the file)

The spot launch function returns a tuple `(instance_id, type, az, error, skipped)`. When it fails, the error string is stored in `action.error_message`, but there's no structured error classification. It's impossible to distinguish between:
- Insufficient capacity (retryable)
- IAM permission denied (not retryable)
- Invalid AMI (configuration error)
- Network timeout (transient)

This makes it hard to apply appropriate retry strategies.

---

### Issue 17: Excessive Use of Inline Imports

**File**: Both `auto_rebalancer.py` and `emergency_rebalancer.py`

The code uses `from ... import ...` inside function bodies and even inside loops (e.g., lines 908, 973, 1040, 1155, etc.). This:
- Makes the code extremely hard to read (4551 lines)
- Hides dependencies
- Can cause import-time side effects on each iteration
- Makes it impossible to mock for unit testing

---

### Issue 18: No Atomic Transaction for Phase 2 Creation

**File**: `auto_rebalancer.py`, Lines 2099–2154

The Phase 2 creation (CORDON → DRAIN → TERMINATE) adds 3 AgentActions and commits. If the commit fails partway (e.g., after CORDON and DRAIN are added but before TERMINATE), the agent will execute CORDON and DRAIN but never receive the TERMINATE action. The old node stays running but cordoned and drained — effectively dead to the cluster without being removed.

---

### Issue 19: Hardcoded Instance Pricing Tables

**File**: `auto_rebalancer.py`, Lines 4041–4055 and 4209–4217

The bin-packing and double-gate selection use hardcoded pricing tables (`_PRICES` and `_OD_PRICES_G`). These prices:
- Are stale (they change with AWS pricing updates)
- Only cover a subset of instance types
- Don't account for regional pricing differences
- Will silently produce wrong results as AWS adds new instance families

---

### Issue 20: No Integration Tests or E2E Flow Validation

The entire 4551-line auto-rebalancer has no test file, no integration tests, and no end-to-end flow validation. Given the complexity of the 2-phase approach, ASG manipulation, concurrent action handling, and rollback logic, the lack of tests means:
- Regressions are introduced silently
- Edge cases (like the ones in this document) are only discovered in production
- The commenting suggests bugs have been found and patched reactively ("the bug that spawned 5 instances")

---

## Summary: Root Cause of Cluster Growth

The **primary** root cause is the **2-Phase Design Pattern**:

1. **Phase 1**: Launch a new spot instance → cluster now has **N+1** nodes
2. **Wait**: For the spot to join K8s (90s–30min)
3. **Phase 2**: Cordon → Drain → Terminate the old OD node → cluster should be back to **N**

Any failure in Phase 2 leaves the cluster at N+1. The auto-rebalancer then sees the old OD node as still running (stale DB) and creates ANOTHER rebalancing action, launching ANOTHER spot → now at N+2. This cascade continues until:
- The 45-minute stale-action expiry kicks in
- The daily limit is hit (if it's not bypassed for OD→Spot)
- Manual intervention stops it

**Secondary causes** amplify the problem:
- ASG DesiredCapacity not being decremented atomically
- Stale DB records causing re-targeting
- Spot recovery launching duplicates
- No upper bound on retry frequency for OD→Spot conversions

---

## Recommended Fix Priority

| Priority | Issue | Estimated Effort |
|----------|-------|------------------|
| P0 | Issue 1 (ASG detach decrement) | 1 hour |
| P0 | Issue 7 (Stale DB re-targeting) | 2 hours |
| P0 | Issue 10 (Celery lock TTL) | 30 min |
| P1 | Issue 2 (2-Phase N+1 design) | 1 day (architecture change) |
| P1 | Issue 3 (Last-node guard) | 2 hours |
| P1 | Issue 4 (Spot recovery duplicates) | 2 hours |
| P1 | Issue 11 (Cooldown bypass) | 1 hour |
| P2 | Issue 5 (Rollback targeting wrong spot) | 2 hours |
| P2 | Issue 8 (Spot baseline race) | 3 hours |
| P2 | Issue 9 (Seeded phantom nodes) | 2 hours |
| P2 | Issue 12 (Daily limit bypass) | 1 hour |
| P2 | Issue 13 (Karpenter timeout drain) | 2 hours |
| P3 | Issue 14 (S2S infinite loop) | 4 hours |
| P3 | Issue 15 (Detach race) | 2 hours |
| P3 | Issues 16–20 (Code quality) | Ongoing |
