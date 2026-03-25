# Spot Optimizer — Debug Log
**Date:** 2026-03-16
**Branch:** testinglocal

---

## Summary of All Issues Found

| # | Severity | Issue | Status |
|---|----------|-------|--------|
| 1 | 🔴 P0 | Rebalance lock never released → deadlock | ✅ Fixed |
| 2 | 🔴 P0 | `source_instance_type` NameError masking spot launch failures | ✅ Fixed |
| 3 | 🟠 P1 | `node_templates` table schema mismatch → POST 500 | ✅ Fixed |
| 4 | 🟠 P1 | `get_db_contextmanager` missing from `base.py` → ImportError in workers | ✅ Fixed |
| 5 | 🟡 P2 | DB schema not auto-created on startup — manual migrations required | ✅ Fixed |
| 6 | 🟡 P2 | `ath@gmail.com` / `Atharva@123` not seeded on startup | ✅ Fixed |
| 7 | 🟡 P2 | Pool distribution grouping wrong in PoolRankings.jsx | ✅ Fixed |
| 8 | 🟡 P2 | Savings display showing "—" for OD nodes despite fallback | ✅ Fixed |

---

## Issue 1 — Rebalance Lock Never Released (Deadlock)

### Symptom
Auto-rebalancing turned ON but **nothing happens**. Every cycle logs:
```
[auto_rebalancer] Rebalance already in progress for cluster <id> — deferring action 117
```

### Root Cause
In `backend/workers/tasks/auto_rebalancer.py` (`execute_rebalancing_action()`):

```python
_lock_key = key_rebalance_lock(action.cluster_id)
_lock_acquired = _redis.set(_lock_key, action.id, nx=True, ex=600)  # 10-minute TTL
```

The lock is set with `nx=True, ex=600` (only set if absent, 10-minute timeout) but was **never explicitly released** via `_redis.delete(_lock_key)`. Once any rebalancing action failed (e.g., action 116 — spot launch failure), the lock persisted for up to 10 minutes. The next action (117) would enter a defer loop every 15 seconds. If the failure repeated within 10 minutes, the lock would reset and block indefinitely.

### Fix
Added try/finally to guarantee lock release on all exit paths:

```python
# Outside try — so finally can always reference these
_lock_key_release = None
_redis_release = None

try:
    ...
    _lock_acquired = _redis.set(_lock_key, action.id, nx=True, ex=600)
    if _lock_acquired:
        _lock_key_release = _lock_key   # save for finally
        _redis_release = _redis         # save for finally
    ...
except Exception as e:
    action.status = 'failed'
    db.commit()
finally:
    # Always release the lock — success, failure, or unhandled exception
    if _lock_key_release and _redis_release:
        try:
            _redis_release.delete(_lock_key_release)
        except Exception:
            pass
```

**File:** `backend/workers/tasks/auto_rebalancer.py` lines 497–499, 528–531, 1105–1111

**Also:** Deleted the stuck Redis key manually to unblock the deferred action:
```bash
docker exec spot-optimizer-redis redis-cli DEL "rebalance:lock:<cluster-id>"
```

---

## Issue 2 — `source_instance_type` NameError (Spot Launch Silent Failure)

### Symptom
```
Direct spot EC2 launch failed: no spot capacity available for types ['c6i.large', 'c5.large', 't3.medium']. Try again later.
```
No AWS EC2 spot request appears in the AWS console. The error message is completely misleading — "no spot capacity" implies AWS rejected the request, but no request was ever made.

### Root Cause
In `_launch_spot_instance_direct()`:

```python
# Line ~397 — BROKEN:
_src_fam = source_instance_type.split('.')[0] if source_instance_type else ''
#            ^^^^^^^^^^^^^^^^^^^^
#            NameError: `source_instance_type` is not defined
#            The parameter is `source_instance_id` (the EC2 instance ID string)
```

The function parameter is `source_instance_id` (e.g. `"i-0abc123"`), but the code referenced `source_instance_type` (undefined). This triggers a `NameError` which is caught by the outer `except Exception as _e` block and returns `(None, None, None)`. The caller interprets `None` as "no capacity" and logs the misleading message.

### Fix
```python
# Line 397 — FIXED:
_src_instance_type = _src.get("InstanceType", "")  # from describe_instances EC2 API response
_src_fam = _src_instance_type.split('.')[0] if _src_instance_type else ''
```

`_src` is the EC2 `describe_instances` response dict for the source instance, which contains the actual `InstanceType` field.

**File:** `backend/workers/tasks/auto_rebalancer.py` lines 397–399

---

## Issue 3 — `node_templates` Table Schema Mismatch (POST 500)

### Symptom
```
POST /api/v1/node-templates 500 Internal Server Error
null value in column "user_id" violates not-null constraint
```

### Root Cause
An old migration had created the `node_templates` table with the following schema:
```sql
CREATE TABLE node_templates (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    user_id VARCHAR NOT NULL REFERENCES users(id),  -- ← NOT NULL FK
    families TEXT[],
    architecture VARCHAR,
    strategy VARCHAR,
    disk_type VARCHAR,
    disk_size INTEGER,
    is_default BOOLEAN,
    ...
);
```

The current SQLAlchemy model (`backend/models/node_template.py`) has a completely different, cleaner schema:
```sql
id, name, scope, created_by, created_at  -- NO user_id, NO families, etc.
```

`SQLAlchemy create_all` is idempotent — it skips tables that already exist. So the wrong old table persisted across all restarts.

### Fix
```sql
-- Drop old tables (confirmed 0 rows in all):
DROP TABLE IF EXISTS cluster_template_mappings CASCADE;
DROP TABLE IF EXISTS node_template_versions CASCADE;
DROP TABLE IF EXISTS node_templates CASCADE;

-- Recreate with correct schema via create_all (runs on every startup now):
Base.metadata.create_all(bind=engine)
```

---

## Issue 4 — `get_db_contextmanager` Missing from `base.py`

### Symptom
Celery workers crashed on startup:
```
ImportError: cannot import name 'get_db_contextmanager' from 'backend.models.base'
```
Affected: `resize_guard_worker.py`, `optimizer_coordinator_worker.py`, and other Celery tasks.

### Root Cause
Multiple worker files import `get_db_contextmanager` from `backend.models.base`, but the function was never defined in that module. The regular `get_db()` generator existed (for FastAPI dependency injection), but the context manager variant for Celery workers was absent.

### Fix
Added to `backend/models/base.py`:
```python
from contextlib import contextmanager

@contextmanager
def get_db_contextmanager():
    """Context manager for database sessions in Celery workers and background tasks."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

---

## Issue 5 — DB Schema Not Auto-Created on Startup

### Symptom
On every fresh deployment or restart with a new database, manual `alembic upgrade head` was required to create tables. The `create_tables()` function existed but wasn't called, and not all models were imported.

### Root Cause
- `Base.metadata.create_all(bind=engine)` was commented out
- Only a subset of models were imported in `create_tables()`, so some tables were never created
- Missing model imports had wrong class names (e.g. `RdsAnalysis` instead of `RDSInstanceAnalysis`)

### Fix
In `backend/models/base.py`:
1. Imported ALL 40+ models with correct class names
2. Uncommented `Base.metadata.create_all(bind=engine)` — now runs on every startup
3. Wrapped uncertain imports in try/except for resilience
4. `create_tables()` is called from `backend/core/api_gateway.py` on startup

> **Note:** Migrations (`alembic`) are now only needed for seeding foundational data (users, rules), not for schema creation. `create_all` handles schema idempotently.

---

## Issue 6 — `ath@gmail.com` Not Seeded on Startup

### Symptom
After any database wipe or fresh deployment, `ath@gmail.com` / `Atharva@123` login didn't work.

### Fix
Added to `seed_demo_data()` in `backend/models/base.py`:
```python
# Seed Atharva user
ath_email = "ath@gmail.com"
ath_user = db.query(User).filter(User.email == ath_email).first()
if not ath_user:
    ath_user = User(
        email=ath_email,
        password_hash=hash_password("Atharva@123"),
        role=UserRole.SUPER_ADMIN,
        organization_id=ath_org.id,
        access_level=AccessLevel.FULL
    )
    db.add(ath_user)
    db.commit()
else:
    # Always ensure password is correct
    if not verify_password("Atharva@123", ath_user.password_hash):
        ath_user.password_hash = hash_password("Atharva@123")
        db.commit()
```

---

## Issue 7 — Pool Distribution Grouping Wrong (PoolRankings.jsx)

### Symptom
"Pool Distribution" chart showed 3 separate bars for the same instance type (e.g. 3 × `t3.medium`) differentiated by target AZ, instead of grouping them together as "t3.medium (OD): 3 nodes, 100%".

### Root Cause
The backend's `pool_distribution` field used `current_type:target_az` as the grouping key (the AZ the rebalancer would target, not the node's current AZ). Frontend was splitting by `:` to extract type — but this gave `"t3.medium"` for `"t3.medium:ap-south-1a"` (wrong split semantics, inconsistent display).

### Fix
Compute distribution client-side from `nodeRecommendations`, grouping by `lifecycle + instance_type`:
```javascript
const _distMap = {};
recs.forEach(rec => {
    const _lc = rec.lifecycle === 'spot' ? 'SPOT' : 'OD';
    const _key = `${rec.current_type} (${_lc})`;
    if (!_distMap[_key]) _distMap[_key] = { count: 0, pct: 0 };
    _distMap[_key].count++;
});
// e.g. result: { "t3.medium (OD)": { count: 3, pct: 100 } }
```

**File:** `frontend/src/components/ascpai/PoolRankings.jsx`

---

## Issue 8 — Savings Showing "—" for OD Nodes

### Symptom
"Projected Savings" column showed `—` for all OD nodes even when a 65% fallback was supposed to display.

### Root Cause
The display condition checked `rec.projected_savings_pct > 0` (the raw API field, which is `0` for OD nodes), but the computed `savingsPct` variable correctly had `65` from the fallback. The wrong variable was checked.

### Fix
```jsx
// Before:
{rec.projected_savings_pct > 0 ? `${savingsMo}/mo` : '—'}

// After:
{savingsPct > 0 ? `${savingsMo}/mo` : '—'}
```

Also improved the backend savings calculation (`backend/api/ascpai_routes.py`) to:
1. First try real savings from Redis pool rankings cache (`global_pool_rankings:{region}`)
2. Fall back to `chosen_pool.predicted_savings` if available
3. Final fallback: 65% savings (35% of on-demand price)

---

## Deployment Steps

After these fixes, rebuild and restart:
```bash
# From project root
docker-compose -f docker/docker-compose.yml build backend
docker-compose -f docker/docker-compose.yml up -d --force-recreate backend celery-worker celery-beat
```

`create_all` + `seed_demo_data` run automatically on backend startup — no manual migration commands needed.

---

## Verification Checklist

- [ ] `ath@gmail.com` / `Atharva@123` login works after fresh restart
- [ ] `POST /api/v1/node-templates` returns 201 (not 500)
- [ ] Auto-rebalancing creates a spot EC2 request visible in AWS console
- [ ] Rebalance lock is released after each action (check Redis: no persistent `rebalance:lock:*` keys after action completes)
- [ ] Pool Distribution chart groups correctly (e.g. "t3.medium (OD): 3 nodes")
- [ ] Savings column shows values for OD nodes (not "—")
- [ ] No `ImportError: get_db_contextmanager` in worker logs
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
 
 