# Spot Optimizer — Bug Log & Fixes

Recorded: 2026-03-17

---

## BUG-01: Cluster Grew from 3 → 6 Nodes (ASG Decrement Never Ran)

### Symptom
After each rebalancing cycle, the cluster grew by 1 node instead of staying the same size. Starting from 3 nodes, the cluster reached 5–6 nodes within a few hours.

### Root Cause
In the backend EC2 terminate block (`auto_rebalancer.py` ~line 2356), `detach_instances` and the ASG `DesiredCapacity` decrement were both inside the same `try:` block:

```python
try:
    _asg_wa.detach_instances(...)          # Step 3
    _ec2_wa_term.terminate_instances(...)  # Step 4
    _asg_wa.update_auto_scaling_group(..., DesiredCapacity=N-1)  # Step 5 ← SKIPPED if detach fails
finally:
    _asg_wa.resume_processes(...)          # Step 6 — always ran
```

EKS Managed Node Groups auto-terminate the EC2 instance when `kubectl delete node` is called. This removes the instance from the ASG before our backend code runs, causing `detach_instances` to throw a `ValidationError`. Because the exception propagated up the `try` block, Step 5 (decrement) was never reached. After `resume_processes` (Step 6) executed, the ASG had `desired=N` with only `N-1` running instances → ASG auto-launched a new OD replacement node.

### Fix Applied
`auto_rebalancer.py` (Task #71):
- Wrapped `detach_instances` in its own `try/except` — failure is now non-fatal with a warning log.
- Wrapped `terminate_instances` in its own `try/except` — idempotent if already terminated.
- `update_auto_scaling_group(DesiredCapacity=N-1)` now ALWAYS runs regardless of detach/terminate success.

---

## BUG-02: Post-Drain Readiness Grace 90s (Excessive)

### Symptom
After CORDON/DRAIN/TERMINATE completed, the backend waited 90 seconds before proceeding with EC2 termination. This added unnecessary latency to every migration cycle.

### Root Cause
`_READINESS_GRACE_S = 90` at line 2146. But the 90-second spot stabilisation wait ALREADY happens BEFORE Phase 2 is triggered (waiting for the replacement spot node to become Ready). The post-drain grace is redundant.

### Fix Applied
`auto_rebalancer.py` (Task #71):
- Changed `_READINESS_GRACE_S = 90` → `_READINESS_GRACE_S = 20`.

---

## BUG-03: LABEL_NODE Action Created with Invalid Kwarg

### Symptom
Warning logged every time Phase 2 started:
```
Failed to queue do-not-disrupt annotation: 'action_metadata' is an invalid keyword argument for AgentAction
```
The `karpenter.sh/do-not-disrupt=true` annotation was silently never queued on replacement nodes.

### Root Cause
`AgentAction` model has no `action_metadata` column. The code used:
```python
AgentAction(..., action_metadata={"rebalancing_action_id": ..., "purpose": ...})
```
`action_metadata` is not a valid constructor kwarg.

### Fix Applied
`auto_rebalancer.py` (Task #71):
- Moved `rebalancing_action_id` and `purpose` into `payload` dict (the correct field).

---

## BUG-04: Stale "In Progress" Actions Never Expired (c6i.large Ghost)

### Symptom
Auto-Rebalancer History showed a `c6i.large` entry with "In Progress" status for 5+ hours. No c6i.large instance existed in AWS. A separate `t3.small` "Completed" entry represented a different migration.

### Root Cause
No timeout/expiry mechanism existed for `RebalancingAction` records stuck in `in_progress` or `waiting_agent` state. If:
- A spot EC2 launch succeeded but the K8s node never joined (InsufficientInstanceCapacity after EC2 creation, or kubelet startup failure)
- An unhandled exception left the action in `in_progress` without marking it `failed`
- The agent disconnected mid-operation

...the action would remain in `in_progress`/`waiting_agent` indefinitely, showing as a ghost entry in the history UI.

### Fix Applied
`auto_rebalancer.py` (Task #72):
- Added stale action expiry at the START of each task run (before the `waiting_agent` processing loop).
- Actions in `in_progress` or `waiting_agent` for >45 minutes are marked `failed` with a detailed timeout error message explaining possible causes.
- `completed_at` and `duration_seconds` are set for accurate reporting.

---

## BUG-05: Stabilization Card Shows Lock Countdown Without "Next Check" Timer

### Symptom
When the stabilization lock was active (e.g., "63s remaining"), the card only showed the lock countdown. The "Next check" timer disappeared entirely, leaving users unable to see when the next rebalance cycle would poll.

### Root Cause
The card had four mutually exclusive states. When `cooldownData` was active, it rendered ONLY the lock countdown:
```jsx
<div>01:03</div>
<div>Until next rebalance</div>
```
The `nextCycleSeconds` counter was still ticking but not displayed.

### Fix Applied
`RebalancingTimeline.jsx` (Task #72):
- When `cooldownData` is active, the secondary line now reads:
  `"Stabilization lock · Next check: 00:14"`
- The lock countdown remains the primary (large amber font), and the next-check timer is shown inline on the secondary line.

---

## BUG-06: Auto-Rebalancer History Not Filtered by Cluster

### Symptom
The Auto-Rebalancer History card on the cluster dashboard showed history from ALL clusters, not just the current cluster. This caused confusion (e.g., t3.small "Completed" from a different cluster appearing alongside the current cluster's c6i.large "In Progress").

### Root Cause
`AutoRebalanceAuditCard.jsx` `fetchAuditLog` function called:
```javascript
api.get('/api/v1/ascpai/rebalancing/status?limit=3')
```
No `cluster_id` query parameter was passed, so the backend returned all clusters' history.

### Fix Applied
`AutoRebalanceAuditCard.jsx` (Task #72):
- Added `cluster_id=${clusterId}` to the API call when `clusterId` prop is available.
- Increased `limit` from 3 to 5 for better history coverage.

---

## BUG-07: Recent Failed Migrations Not Shown in Active Node Migrations Timeline

### Symptom
When a migration failed (e.g., `t3a.small` failed with "DRAIN_NODE failed — PDB conflict"), the failure only appeared in the "Auto-Rebalancer History" card but NOT in the "Active Node Migrations" timeline. Users had to check two separate places to understand what happened.

### Root Cause
`RebalancingTimeline.jsx` visible filter excluded `failed` status:
```javascript
const visible = (displayActions || []).filter(a => {
    if (['in_progress', 'waiting_agent'].includes(a.status)) return true;
    if (a.status === 'completed' && a.completed_at) { ... }  // only 'completed'
    return false;
});
```

### Fix Applied
`RebalancingTimeline.jsx` (Task #72):
- Added `a.status === 'failed'` to the completed check — failed migrations from the last hour now appear in the Active Node Migrations timeline with a red border and the full error message.
- Added `pool_change_reason` display — when a pool was planned but fell back to another (e.g., c6i.large → t3.small due to InsufficientInstanceCapacity), a blue info banner shows the trail.

---

## BUG-08: target_az Missing from Action Metadata (Decision Engine Failure Reporting Always Skipped)

### Symptom
The Decision Engine's `report_launch_failure()` was never called, meaning the ML model never learned from failed pool launches. The guard `if _target_type and _target_az:` always evaluated to False because `_target_az` was always empty.

### Root Cause
At action creation time, `action_metadata` only stored `target_instance_type` but not `target_az` or `source_az`. The `_target_az` fallback tried to parse from `_wa.target_pool` but had a logic gap.

### Fix Applied
`auto_rebalancer.py` (Task #70):
- Added `target_az` and `source_az` to action metadata at creation time.
- Added fallback: `_target_az = _wa_meta.get("target_az") or (_wa.target_pool.split(':')[1] if ':' in (_wa.target_pool or '') else "")`.

---

## BUG-09: Wrong Spot Node Detection in waiting_agent Loop

### Symptom
With concurrent rebalancing actions, the waiting_agent loop could accidentally pick up a DIFFERENT action's replacement spot node, causing cross-contamination.

### Root Cause
The loop used `order_by(Instance.created_at.desc()).first()` to find the "newest" spot — this grabs the globally newest spot regardless of which action launched it.

### Fix Applied
`auto_rebalancer.py` (Task #70):
- When `replacement_spot_instance_id` is stored in action metadata (set at Phase 1 launch), the loop now queries for that specific instance ID.
- If not yet running, it `continue`s instead of falling through to the newest-by-date fallback.

---

## Current AWS State (2026-03-17 ~15:40)

| Instance ID | Type | AZ | State | Notes |
|---|---|---|---|---|
| i-0cbc959f4bd1280e6 | t3a.small | ap-south-1a | Running | Source of active S2S migration |
| i-0d9ed1349955de01e | t3.small | ap-south-1a | Running | Spot |
| i-05a6e219eb72967bd | c5.large | ap-south-1a | Initializing | New spot (replacement) |
| i-0052c4d05daa58c84 | t3.medium | ap-south-1a | Running | OD — drain failed (PDB) |
| i-0d9fdf6f3508925f1 | t3a.micro | ap-south-1a | Initializing | Target of active S2S migration |
| i-0097ee072b51c902c | c5.large | ap-south-1a | Running | Existing spot |

**Expected cluster size**: 3 nodes. **Actual**: 6 nodes (cluster grew due to BUG-01 in previous cycles).

**Convergence path**: With BUG-01 fixed (ASG decrement always runs), each new rebalancing cycle will properly decrement ASG desired by 1 after each OD termination. The cluster will converge back to 3 spot nodes over the next few cycles as OD nodes are replaced. PDB-blocked drains (i-0052c4d05daa58c84) will be retried automatically on the next cycle.

---

## Deploy Commands

```bash
# Backend + worker (auto_rebalancer.py changes)
docker-compose -f docker/docker-compose.yml up -d --force-recreate celery-worker celery-beat

# Frontend (RebalancingTimeline.jsx + AutoRebalanceAuditCard.jsx changes)
docker-compose -f docker/docker-compose.yml build frontend
docker-compose -f docker/docker-compose.yml up -d --force-recreate frontend
```
