"""
Hibernation Strategy Modules

This package contains modular implementations of hibernation strategies.
Each strategy is isolated in its own module for easy configuration and maintenance.

Available Strategies:
- NAMESPACE_SLEEP: Gentle shutdown (scale workloads to 0, let autoscaler drain nodes)
- NUCLEAR: Hard shutdown (scale ASGs to 0 directly)
- SNAPSHOT_RESTORE: Safe shutdown with EBS snapshots before Nuclear sleep

Usage:
    from backend.Hibernation_strategy import namespace_sleep, nuclear, snapshot_restore

    # Execute sleep
    namespace_sleep.execute_sleep(cluster, schedule, db)

    # Execute wake
    namespace_sleep.execute_wake(cluster, schedule, db)
"""

from .namespace_sleep import NamespaceSleepStrategy
from .nuclear import NuclearStrategy
from .snapshot_restore import SnapshotRestoreStrategy

__all__ = [
    'NamespaceSleepStrategy',
    'NuclearStrategy',
    'SnapshotRestoreStrategy',
]
