# Fallback Removal — Root Cause & Fix Log
**Date:** 2026-03-16
**Branch:** testinglocal
**Problem:** Cluster grew from original size (3 nodes) to 6 nodes. Stale OD instances stayed running.

---

## Root Cause: Cluster Grew from 3 → 6 Nodes

### The Chain of Events
1. Auto-rebalancer tried to terminate the last OD node in the ASG
2. AWS rejected `terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=True)` because `desired == min` (e.g., 1 == 1 — can't go below min)
3. The `MinSize=0` update that was supposed to allow the decrement failed silently (`except Exception as _min_err: logger.warning(...)` — code continued)
4. ASG terminate then also failed (min constraint still in place)
5. **Fallback triggered**: code fell back to `ec2.terminate_instances(InstanceIds=[instance_id])`
6. Direct EC2 terminate **succeeded** — instance was gone from EC2
7. **BUT**: ASG `DesiredCapacity` remained = 1, `MinSize` unchanged
8. `resume_asg_processes()` re-enabled the ASG Launch process
9. ASG saw: desired=1, running=0 → **auto-launched a new OD replacement**
10. This repeated across multiple cycles → cluster grew from 3 → 6 nodes

---

## All Fallbacks Found and Their Impact

### 🔴 CRITICAL — Cluster Growth

#### 1. ASG terminate → Direct EC2 fallback (auto_rebalancer.py ~L2053)
**Before:**
```python
except Exception as _asg_err:
    logger.warning("ASG terminate failed — trying direct EC2 terminate")

if not _terminated:
    try:
        _ec2_wa.terminate_instances(InstanceIds=[_wa_instance_id])
        _terminated = True
    except Exception as _ec2_err:
        logger.warning("Direct EC2 also failed")
```
**Why it's broken:** Direct EC2 removes the instance but ASG `DesiredCapacity` stays = 1. When `resume_asg_processes()` runs, ASG relaunches an OD replacement → **cluster grows by 1 node per failed terminate**.

**Fix:** Removed direct EC2 fallback entirely. Logic is now:
- If node is in ASG (`asg_name_used` in metadata): use ASG terminate ONLY
- If node is NOT in ASG (Karpenter-managed): use direct EC2 ONLY
- On failure: log ERROR, mark `ec2_terminate_failed=True`, action fails, cluster state unchanged

#### 2. MinSize=0 failure silently continued (auto_rebalancer.py ~L2040)
**Before:**
```python
try:
    _asg_wa.update_auto_scaling_group(AutoScalingGroupName=..., MinSize=0)
except Exception as _min_err:
    logger.warning("Could not lower ASG min_size")  # SILENTLY CONTINUED
# Then tried terminate anyway — which also fails, triggering EC2 fallback
```
**Fix:** MinSize=0 update failure now propagates as an exception (no inner try/except). If it fails, the terminate also fails, the outer except catches it, action is marked failed cleanly.

#### 3. Orphan cleanup failure silently continued (auto_rebalancer.py ~L933)
**Before:**
```python
except Exception as _oe:
    logger.warning("Pre-launch orphan check failed")
    # SILENTLY CONTINUED → launched new spot on top of potentially existing orphan
```
**Why it's broken:** If a previous failed action left an orphan spot instance running and cleanup fails, launching a new spot creates a duplicate node the cluster didn't originally have.

**Fix:** Failure is now fatal — action fails immediately:
```python
except Exception as _oe:
    logger.error("Pre-launch orphan cleanup FAILED — aborting action")
    action.status = 'failed'
    action.error_message = f"Pre-launch orphan cleanup failed for {_pf_orphan}: {_oe}. Manual intervention required."
    db.commit()
    return
```
Same treatment for outer orphan detection failure.

---

### 🟠 HIGH — Stale Data / Misclassification

#### 4. RC3 guard Redis failure → immediate SPOT→OD downgrade (auto_rebalancer.py ~L206)
**Before:**
```python
except Exception:
    db_inst.lifecycle = real_lifecycle  # immediately downgraded SPOT→OD
    changed = True
```
**Why it's broken:** Redis transient error caused a SPOT instance to be classified as OD in the DB. This triggered unnecessary OD→SPOT rebalancing on an already-SPOT node, creating confusion and stale actions.

**Fix:** Redis failure preserves current lifecycle (SPOT stays SPOT):
```python
except Exception as _rc3_err:
    logger.warning(f"RC3 guard Redis error: {_rc3_err} — keeping current lifecycle (no change)")
    # Don't change lifecycle
```

---

## What Was NOT Changed (Intentional Fallbacks Kept)

| Location | Fallback | Why Kept |
|----------|----------|----------|
| Credential account lookup | `except: pass` | No state change — just means platform creds used instead of assumed role |
| `report_launch_attempt/failure` | `except: pass` | Metrics only — no cluster state change |
| Redis arch constraints | `except: pass` | Uses safe default (both archs) — no cluster state change |
| ASG info retrieval at pre-step | `except: pass` | Uses conservative defaults (2 desired, 1 min) — worst case: action fails cleanly without growth |
| Instance cooldown set | Warning + continue | Cooldown is advisory — not setting it means same instance may be retried sooner, not a state corruption |

---

## Files Changed

| File | Lines | Change |
|------|-------|--------|
| `backend/workers/tasks/auto_rebalancer.py` | ~206-208 | RC3 guard: keep SPOT on Redis failure |
| `backend/workers/tasks/auto_rebalancer.py` | ~2015-2083 | Terminate: ASG-path vs EC2-path, no cross-fallback |
| `backend/workers/tasks/auto_rebalancer.py` | ~933-941 | Orphan cleanup failure: fail action instead of continuing |

---

## Verification

After deploying this fix:
1. **Cluster count stays stable** — if terminate fails, action is marked `failed`, cluster unchanged
2. **Redis logs** will show `RC3 guard Redis error — keeping current lifecycle` instead of silent SPOT→OD downgrade
3. **Orphan failures** will log `Pre-launch orphan cleanup FAILED — aborting action`
4. **Terminate failures** will log `EC2 terminate FAILED — no fallback applied`
5. Check Redis: no persistent `rebalance:lock:*` keys after action completes (lock still released via try/finally)

## Manual Cleanup Required (AWS Console)

The 6 running instances in the screenshot (vs original 3) are surplus OD nodes launched by ASG after the fallback terminated EC2 without decrementing desired. Steps to restore:
1. In AWS Console → Auto Scaling Groups → find `spot-demo-2-standard-workers-*`
2. Reduce `Desired Capacity` to 3 (or original intended size)
3. Terminate the 3 excess instances (choose the extra c5.large ones)
4. Verify cluster shows correct node count in UI
