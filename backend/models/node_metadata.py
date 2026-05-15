"""
Node Metadata DB Model — T-09
==============================
Static per-node properties upserted by the agent on each heartbeat.

Table: node_metadata
Unique constraint: (cluster_id, node_name)
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.models.base import Base


class NodeMetadata(Base):
    __tablename__ = "node_metadata"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    node_name = Column(String(253), nullable=False)

    az = Column(String(64), nullable=True)
    capacity_type = Column(String(20), nullable=True)
    nodepool_name = Column(String(128), nullable=True)
    instance_type = Column(String(64), nullable=True)
    do_not_disrupt = Column(Boolean, nullable=False, server_default="false", default=False)
    is_ready = Column(Boolean, nullable=False, server_default="true", default=True)

    allocatable_cpu_millicores = Column(Float, nullable=True)
    allocatable_memory_bytes = Column(Float, nullable=True)

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("cluster_id", "node_name", name="uq_node_metadata_cluster_node"),
    )

    def __repr__(self) -> str:
        return (
            f"<NodeMetadata cluster_id={self.cluster_id!r} "
            f"node_name={self.node_name!r} "
            f"capacity_type={self.capacity_type!r} "
            f"az={self.az!r}>"
        )
