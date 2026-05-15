"""
HPA Status Snapshots DB Model — T-13
=======================================
Append-only time-series of HPA runtime state. 30-day retention.
Cleaned up by pod_metrics_cleanup task.

Table: hpa_status_snapshots
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)

from backend.models.base import Base


class HpaStatusSnapshot(Base):
    __tablename__ = "hpa_status_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    namespace = Column(String(253), nullable=False)
    workload_name = Column(String(253), nullable=False)

    desired_replicas = Column(Integer, nullable=True)
    current_replicas = Column(Integer, nullable=True)
    cpu_utilization_pct = Column(Integer, nullable=True)

    snapshot_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_hpa_snapshot_cluster_workload_time", "cluster_id", "workload_name", "snapshot_at"),
        Index("idx_hpa_snapshot_cluster_time", "cluster_id", "snapshot_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<HpaStatusSnapshot cluster_id={self.cluster_id!r} "
            f"workload={self.namespace}/{self.workload_name} "
            f"desired={self.desired_replicas} at={self.snapshot_at}>"
        )
