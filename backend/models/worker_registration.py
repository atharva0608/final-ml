"""
Worker Registration Model
=========================
Tracks DaemonSet worker heartbeats, instance metadata, and health status.
Each worker registers on startup and sends periodic heartbeats.
"""

from sqlalchemy import Column, String, DateTime, Index
from datetime import datetime
from backend.models.base import Base, generate_uuid


class WorkerRegistration(Base):
    """Tracks a DaemonSet worker's registration and heartbeat status."""

    __tablename__ = "worker_registrations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    cluster_id = Column(String(36), nullable=False, index=True)
    node_name = Column(String(256), nullable=False, index=True)

    # EC2 instance metadata (reported by the agent on startup)
    instance_id = Column(String(64), nullable=True)
    instance_type = Column(String(64), nullable=True)
    az = Column(String(32), nullable=True)
    lifecycle = Column(String(16), nullable=True)  # "on-demand" or "spot"

    # Health
    status = Column(String(16), nullable=False, default="active")  # active | stale | dead
    registered_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_heartbeat = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_worker_reg_cluster_node", "cluster_id", "node_name", unique=True),
    )

    def __repr__(self):
        return (
            f"<WorkerRegistration(node={self.node_name}, cluster={self.cluster_id}, "
            f"status={self.status}, heartbeat={self.last_heartbeat})>"
        )
