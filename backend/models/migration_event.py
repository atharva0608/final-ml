"""MigrationEvent Model — §15 Stateful Migration Status

Lightweight state-transition log written by auto_rebalancer at each stage
of a workload migration (freeze-start → migrating → soak → complete/failed).

3-5 inserts per migration; queries are filtered by cluster_id + ORDER BY
created_at DESC LIMIT 50 for dashboard display.

Retention: rows older than 30 days are cleaned up by a scheduled task.
"""

from sqlalchemy import Column, Integer, SmallInteger, String, Text, Boolean, DateTime, func, Index
from backend.models.base import Base


class MigrationEvent(Base):
    """Single state-transition record for one workload controller migration."""

    __tablename__ = "migration_event"
    __table_args__ = (
        Index("idx_migration_event_cluster", "cluster_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Context
    cluster_id = Column(Integer, nullable=False, index=True)
    namespace = Column(String(255), nullable=False)
    controller_name = Column(String(255), nullable=False)
    controller_kind = Column(String(50), nullable=False)  # Deployment, StatefulSet, …
    workload_tier = Column(SmallInteger, nullable=True)   # 0-4 per W3.x classification

    # Node routing
    source_node = Column(String(255), nullable=True)  # node being drained
    target_node = Column(String(255), nullable=True)  # where new pod lands (may be NULL until scheduled)

    # State machine
    # Values: freeze-start | migrating | soak | complete | failed
    state = Column(String(50), nullable=False, index=True)

    failure_reason = Column(Text, nullable=True)

    # W7 freeze detail
    # freeze-start: source_safe
    # migrating / soak: target_running (pod seen on new node) | unknown
    pod_location = Column(String(50), nullable=True)   # source_safe | target_running | unknown
    freeze_restored = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    def __repr__(self) -> str:
        return (
            f"<MigrationEvent(id={self.id}, cluster={self.cluster_id}, "
            f"ctrl={self.namespace}/{self.controller_name}, state={self.state})>"
        )
