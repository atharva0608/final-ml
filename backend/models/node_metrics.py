"""
Node Metrics Model
==================
Stores node-level telemetry reported by DaemonSet workers.
Used for rightsizing trend analysis and dashboard display.
"""

from sqlalchemy import Column, String, Float, DateTime, Index
from datetime import datetime
from backend.models.base import Base, generate_uuid


class NodeMetric(Base):
    """Per-node metrics snapshot reported by the agent DaemonSet worker."""

    __tablename__ = "node_metrics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    cluster_id = Column(String(36), nullable=False, index=True)
    node_name = Column(String(256), nullable=False, index=True)

    # Resource usage
    cpu_usage_millicores = Column(Float, nullable=True)
    cpu_capacity_millicores = Column(Float, nullable=True)
    memory_usage_bytes = Column(Float, nullable=True)
    memory_capacity_bytes = Column(Float, nullable=True)
    disk_usage_bytes = Column(Float, nullable=True)
    disk_capacity_bytes = Column(Float, nullable=True)

    # Instance metadata (denormalized for fast queries)
    instance_id = Column(String(64), nullable=True)
    instance_type = Column(String(64), nullable=True)
    az = Column(String(32), nullable=True)

    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_node_metric_cluster_ts", "cluster_id", "timestamp"),
        Index("idx_node_metric_node_ts", "node_name", "timestamp"),
    )

    def __repr__(self):
        return f"<NodeMetric(node={self.node_name}, cluster={self.cluster_id}, ts={self.timestamp})>"
