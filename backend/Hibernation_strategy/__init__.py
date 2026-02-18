"""
Hibernation Strategy Implementations

Exports all three hibernation strategies:
- NamespaceSleepStrategy: Scale workloads to 0
- NuclearStrategy: Terminate worker nodes
- SnapshotRestoreStrategy: Snapshot + full shutdown
"""
from backend.hibernation_strategy.namespace_sleep import NamespaceSleepStrategy
from backend.hibernation_strategy.nuclear import NuclearStrategy
from backend.hibernation_strategy.snapshot_restore import SnapshotRestoreStrategy

__all__ = [
    "NamespaceSleepStrategy",
    "NuclearStrategy",
    "SnapshotRestoreStrategy"
]
