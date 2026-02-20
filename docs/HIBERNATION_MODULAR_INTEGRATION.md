# Hibernation Strategy Modular Integration - Complete

**Date**: 2026-02-18
**Status**: ✅ Complete
**Integration Type**: Modular Architecture Refactoring

---

## Overview

Successfully refactored the hibernation worker to use modular, configurable strategy implementations. All hibernation logic has been extracted from the main worker file into separate, editable strategy modules in `backend/Hibernation_strategy/`.

---

## Architecture Changes

### Before (Monolithic)

```
backend/workers/tasks/hibernation_worker.py (1306 lines)
├── _namespace_sleep() - 186 lines inline
├── _namespace_wake() - 112 lines inline
├── _nuclear_sleep() - 108 lines inline
├── _nuclear_wake() - 86 lines inline
├── _snapshot_sleep() - 91 lines inline
└── _snapshot_wake() - 16 lines inline
```

**Issues**:
- All logic embedded in worker file
- Configuration parameters scattered throughout
- Hard to modify individual strategies
- No separation of concerns
- Testing strategies requires mocking entire worker

### After (Modular)

```
backend/Hibernation_strategy/
├── __init__.py                    # Strategy exports
├── namespace_sleep.py             # NamespaceSleepStrategy (600+ lines)
├── nuclear.py                     # NuclearStrategy (450+ lines)
└── snapshot_restore.py            # SnapshotRestoreStrategy (550+ lines)

backend/workers/tasks/hibernation_worker.py (reduced to ~850 lines)
├── _namespace_sleep() - 25 lines (delegates to strategy)
├── _namespace_wake() - 25 lines (delegates to strategy)
├── _nuclear_sleep() - 20 lines (delegates to strategy)
├── _nuclear_wake() - 20 lines (delegates to strategy)
├── _snapshot_sleep() - 35 lines (delegates to strategy)
└── _snapshot_wake() - 28 lines (delegates to strategy)
```

**Benefits**:
- ✅ Each strategy is self-contained and independently testable
- ✅ Configuration parameters clearly defined at module level
- ✅ Easy to modify rules and logic for individual strategies
- ✅ Clear separation of concerns
- ✅ Strategies can be imported and used elsewhere
- ✅ Maintains backward compatibility with existing API

---

## New Modular Structure

### 1. `backend/Hibernation_strategy/__init__.py`

```python
from .namespace_sleep import NamespaceSleepStrategy
from .nuclear import NuclearStrategy
from .snapshot_restore import SnapshotRestoreStrategy

__all__ = [
    'NamespaceSleepStrategy',
    'NuclearStrategy',
    'SnapshotRestoreStrategy',
]
```

### 2. `backend/Hibernation_strategy/namespace_sleep.py`

**Configuration Parameters (Editable)**:
```python
SYSTEM_NAMESPACES = ['kube-system', 'kube-public', 'kube-node-lease', 'spot-optimizer']
GRACE_PERIOD_SECONDS = 30
WAIT_FOR_READINESS = True
MAX_WAIT_SECONDS = 300
SLEEP_ORDER = ['hpas', 'deployments', 'statefulsets']
WAKE_ORDER = ['statefulsets', 'deployments', 'hpas']
```

**Class Methods**:
- `execute_sleep(cluster, schedule, db, k8s_clients)` → Dict
- `execute_wake(cluster, schedule, db, k8s_clients)` → Dict
- Helper methods: `_scale_hpas()`, `_scale_deployments()`, `_scale_statefulsets()`, etc.

**Strategy Metadata**:
```python
STRATEGY_RULES = {
    'name': 'Namespace Sleep',
    'code': 'NAMESPACE_SLEEP',
    'wake_time_minutes': 2,
    'cost_savings_percent': 80,
    'safety_level': 'HIGH',
    'best_for': 'Stateless applications, dev/test environments'
}
```

### 3. `backend/Hibernation_strategy/nuclear.py`

**Configuration Parameters (Editable)**:
```python
MIN_DESIRED_CAPACITY = 1
SCALE_DOWN_TIMEOUT = 600  # 10 minutes
SCALE_UP_TIMEOUT = 480    # 8 minutes
WAIT_FOR_NODES = True
NODE_READY_TIMEOUT = 300
HONOR_COOLDOWN = False
TERMINATION_POLICIES = ['OldestInstance', 'Default']
```

**Class Methods**:
- `execute_sleep(cluster, schedule, db, aws_credentials)` → Dict
- `execute_wake(cluster, schedule, db, aws_credentials)` → Dict
- Helper methods: `_get_cluster_asgs()`, `_wait_for_asg_instances()`

**Strategy Metadata**:
```python
STRATEGY_RULES = {
    'name': 'Nuclear',
    'code': 'NUCLEAR',
    'wake_time_minutes': 8,
    'cost_savings_percent': 99,
    'safety_level': 'MEDIUM',
    'best_for': 'Maximum cost reduction, non-critical environments'
}
```

### 4. `backend/Hibernation_strategy/snapshot_restore.py`

**Configuration Parameters (Editable)**:
```python
SNAPSHOT_TIMEOUT = 1800  # 30 minutes
SNAPSHOT_DESCRIPTION_PREFIX = "SpotOptimizer-Hibernation"
KEEP_SNAPSHOTS_DAYS = 7
PARALLEL_SNAPSHOTS = 5
VERIFY_SNAPSHOTS = True
RESTORE_WAIT_TIME = 60
TRACK_AZ_AFFINITY = True
```

**Class Methods**:
- `execute_sleep(cluster, schedule, db, aws_credentials, k8s_clients=None)` → Dict
- `execute_wake(cluster, schedule, db, aws_credentials)` → Dict
- `cleanup_old_snapshots(cluster, aws_credentials)` → Dict
- Helper methods: `_get_cluster_volumes()`, `_wait_for_snapshots()`, `_build_az_affinity_map()`

**Strategy Metadata**:
```python
STRATEGY_RULES = {
    'name': 'Snapshot & Restore',
    'code': 'SNAPSHOT_RESTORE',
    'wake_time_minutes': 12,
    'cost_savings_percent': 90,
    'safety_level': 'HIGHEST',
    'best_for': 'Databases, stateful workloads requiring data safety'
}
```

---

## Worker Integration

### Updated `hibernation_worker.py`

**Imports**:
```python
from backend.Hibernation_strategy import (
    NamespaceSleepStrategy,
    NuclearStrategy,
    SnapshotRestoreStrategy
)
```

**Strategy Dispatch Functions** (Example):

```python
def _namespace_sleep(cluster: Cluster, schedule: HibernationSchedule, db: Session) -> None:
    """
    Namespace Sleep using modular NamespaceSleepStrategy.
    Delegates to backend.Hibernation_strategy.namespace_sleep module.
    """
    logger.info(f"[WORK-HIB-01] Starting Namespace Sleep for {cluster.name}")

    account = db.query(Account).filter(Account.id == cluster.account_id).first()
    credentials = _get_assumed_credentials(account, cluster)
    core_v1, apps_v1, autoscaling_v1 = _get_k8s_clients(cluster, credentials)

    k8s_clients = {
        'core_v1': core_v1,
        'apps_v1': apps_v1,
        'autoscaling_v1': autoscaling_v1
    }

    # Instantiate and execute strategy
    strategy = NamespaceSleepStrategy()
    result = strategy.execute_sleep(cluster, schedule, db, k8s_clients)

    # Log action
    _log_action(db, cluster, schedule, "NAMESPACE_SLEEP", "completed", result)
```

**Pattern Applied to All Strategies**:
- ✅ Namespace Sleep: Delegates to `NamespaceSleepStrategy`
- ✅ Nuclear: Delegates to `NuclearStrategy`
- ✅ Snapshot & Restore: Delegates to `SnapshotRestoreStrategy`

---

## Editable Configuration

### How to Modify Strategy Behavior

**Example: Change Nuclear Sleep Timeout**

1. Open `backend/Hibernation_strategy/nuclear.py`
2. Locate configuration section (lines 32-58):
   ```python
   # Minimum capacity to restore (ensures at least N nodes on wake)
   MIN_DESIRED_CAPACITY = 1

   # Scale-down timeout (seconds) - max time to wait for nodes to terminate
   SCALE_DOWN_TIMEOUT = 600  # 10 minutes
   ```
3. Edit the value:
   ```python
   SCALE_DOWN_TIMEOUT = 900  # 15 minutes
   ```
4. Restart Celery worker:
   ```bash
   cd docker
   docker-compose restart celery-worker
   ```

**Example: Add New System Namespace to Namespace Sleep**

1. Open `backend/Hibernation_strategy/namespace_sleep.py`
2. Locate configuration (lines 34-36):
   ```python
   SYSTEM_NAMESPACES = [
       'kube-system', 'kube-public', 'kube-node-lease',
       'spot-optimizer', 'istio-system', 'prometheus'
   ]
   ```
3. Add your namespace:
   ```python
   SYSTEM_NAMESPACES = [
       'kube-system', 'kube-public', 'kube-node-lease',
       'spot-optimizer', 'istio-system', 'prometheus',
       'my-monitoring-namespace'  # NEW
   ]
   ```
4. Restart Celery worker

---

## Strategy Class Interface

### Standard Interface Contract

All strategy classes implement the following interface:

```python
class HibernationStrategy:
    """Base hibernation strategy interface (not enforced, but recommended pattern)"""

    def execute_sleep(self, cluster, schedule, db: Session, **kwargs) -> Dict[str, Any]:
        """
        Execute hibernation (sleep) for the cluster.

        Args:
            cluster: Cluster model instance
            schedule: HibernationSchedule model instance
            db: SQLAlchemy database session
            **kwargs: Strategy-specific parameters (aws_credentials, k8s_clients, etc.)

        Returns:
            Dict with sleep results (status, affected_resources, timestamp, etc.)
        """
        raise NotImplementedError

    def execute_wake(self, cluster, schedule, db: Session, **kwargs) -> Dict[str, Any]:
        """
        Execute cluster wake-up.

        Args:
            cluster: Cluster model instance
            schedule: HibernationSchedule model instance
            db: SQLAlchemy database session
            **kwargs: Strategy-specific parameters

        Returns:
            Dict with wake results (status, restored_resources, timestamp, etc.)
        """
        raise NotImplementedError
```

---

## Files Modified

### Backend Files (2 modified)

1. **`backend/workers/tasks/hibernation_worker.py`**
   - Added strategy imports
   - Replaced inline implementations with strategy delegates
   - Reduced from ~1306 lines to ~850 lines
   - Maintained all existing helper functions (_get_k8s_clients, _get_assumed_credentials, etc.)

2. **`backend/Hibernation_strategy/__init__.py`** (NEW)
   - Strategy exports and package initialization

### New Strategy Modules (3 files)

1. **`backend/Hibernation_strategy/namespace_sleep.py`** (NEW - 600+ lines)
   - NamespaceSleepStrategy class
   - Editable configuration parameters
   - Complete K8s scaling logic
   - Strategy metadata

2. **`backend/Hibernation_strategy/nuclear.py`** (NEW - 450+ lines)
   - NuclearStrategy class
   - Editable configuration parameters
   - ASG scaling logic
   - Strategy metadata

3. **`backend/Hibernation_strategy/snapshot_restore.py`** (NEW - 550+ lines)
   - SnapshotRestoreStrategy class
   - Editable configuration parameters
   - EBS snapshot logic + Nuclear sleep
   - Strategy metadata

---

## Testing

### Verify Integration

```bash
# 1. Backend starts without import errors
cd docker
docker-compose restart backend

# Check logs
docker logs spot-optimizer-backend --tail 100

# 2. Celery worker loads strategies correctly
docker-compose restart celery-worker

# Check worker logs
docker logs spot-optimizer-celery-worker --tail 100

# Expected output:
# [INFO] Loaded hibernation strategy: NamespaceSleepStrategy
# [INFO] Loaded hibernation strategy: NuclearStrategy
# [INFO] Loaded hibernation strategy: SnapshotRestoreStrategy
```

### Test Strategy Execution

```bash
# Trigger manual sleep (from backend container)
docker exec spot-optimizer-celery-worker celery -A backend.workers call \
  workers.hibernation.manual_sleep \
  --args='["cluster-123"]' \
  --kwargs='{"strategy": "NAMESPACE_SLEEP"}'

# Trigger manual wake
docker exec spot-optimizer-celery-worker celery -A backend.workers call \
  workers.hibernation.manual_wake \
  --args='["cluster-123"]'
```

---

## Benefits of Modular Architecture

### 1. **Maintainability**
- Each strategy is isolated in its own file
- Easy to locate and modify specific strategy logic
- Clear separation between strategy logic and worker orchestration

### 2. **Configurability**
- All configuration parameters defined at module level
- No need to search through code to find settings
- Edit rules without touching core worker logic

### 3. **Testability**
- Each strategy can be tested independently
- Mock dependencies (K8s clients, AWS clients) for unit tests
- Integration tests can verify strategy execution in isolation

### 4. **Extensibility**
- Easy to add new strategies (create new module, implement interface)
- Strategies can be imported and used in other parts of the system
- Strategy metadata enables dynamic UI generation

### 5. **Reusability**
- Strategies can be called from API routes for manual triggers
- Can be used in CLI tools for ad-hoc hibernation
- Shared logic extracted into helper methods

---

## Strategy Comparison

| Strategy | Wake Time | Savings | Safety | Use Case | Configuration File |
|----------|-----------|---------|--------|----------|-------------------|
| **Namespace Sleep** | ~2 min | ~80% | HIGH | Stateless apps, dev/test | `namespace_sleep.py` |
| **Nuclear** | ~8 min | ~99% | MEDIUM | Max cost reduction | `nuclear.py` |
| **Snapshot & Restore** | ~12 min | ~90% | HIGHEST | Databases, stateful workloads | `snapshot_restore.py` |

---

## Next Steps

### Immediate (Completed ✅)
- ✅ Create modular strategy files
- ✅ Implement NamespaceSleepStrategy
- ✅ Implement NuclearStrategy
- ✅ Implement SnapshotRestoreStrategy
- ✅ Update hibernation_worker.py to use strategies
- ✅ Test worker imports strategies correctly

### Future Enhancements

1. **Add Strategy Comparison API Endpoint**
   ```python
   GET /api/v1/hibernation/strategies
   # Returns list of strategies with metadata from STRATEGY_RULES
   ```

2. **Strategy Validation API**
   ```python
   POST /api/v1/hibernation/validate-strategy
   # Validates strategy configuration before execution
   ```

3. **Strategy Testing CLI**
   ```bash
   python -m backend.Hibernation_strategy.namespace_sleep --test
   # Dry-run strategy with test cluster
   ```

4. **Add Fourth Strategy: "Cryosleep"**
   - Combines Snapshot + Namespace Sleep
   - Faster wake than Nuclear (no ASG scaling)
   - Safer than Namespace Sleep (has snapshots)
   - Wake time: ~5 minutes, Savings: ~85%

---

## Troubleshooting

### Issue: Strategy Import Error

**Symptom**: `ImportError: cannot import name 'NamespaceSleepStrategy'`

**Fix**:
```bash
# Ensure __init__.py exists
ls backend/Hibernation_strategy/__init__.py

# Restart Python processes
docker-compose restart backend celery-worker
```

### Issue: Configuration Changes Not Applied

**Symptom**: Modified configuration parameters but behavior unchanged

**Fix**:
```bash
# Celery doesn't auto-reload like FastAPI
docker-compose restart celery-worker celery-beat
```

### Issue: Strategy Execution Fails

**Symptom**: `AttributeError: 'NuclearStrategy' object has no attribute 'execute_sleep'`

**Fix**: Verify strategy class implements required methods (`execute_sleep`, `execute_wake`)

---

## Summary

✅ **Modular hibernation strategy system complete**
✅ **All 3 strategies extracted into separate files**
✅ **Worker successfully refactored to delegate to strategies**
✅ **Configuration parameters clearly defined and editable**
✅ **Backward compatible with existing API and database**

The hibernation system is now fully modular, maintainable, and extensible. Each strategy can be independently modified, tested, and deployed without affecting other strategies or the core worker logic.
