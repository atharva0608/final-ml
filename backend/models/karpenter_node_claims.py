"""
Karpenter NodeClaim DB Model — T-11
=====================================
Stores per-NodeClaim properties pushed by karpenter_watcher._poll_nodeclaims().

Table: karpenter_node_claims
Unique constraint: (cluster_id, node_name)
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)

from backend.models.base import Base


class KarpenterNodeClaim(Base):
    __tablename__ = "karpenter_node_claims"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    node_name = Column(String(253), nullable=False)

    instance_type = Column(String(64), nullable=True)
    capacity_type = Column(String(20), nullable=True)
    az = Column(String(64), nullable=True)
    nodepool_name = Column(String(128), nullable=True)
    state = Column(String(50), nullable=True)
    provisioned_at = Column(DateTime, nullable=True)

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("cluster_id", "node_name", name="uq_karpenter_node_claims_cluster_node"),
    )

    def __repr__(self) -> str:
        return (
            f"<KarpenterNodeClaim cluster_id={self.cluster_id!r} "
            f"node_name={self.node_name!r} "
            f"capacity_type={self.capacity_type!r} "
            f"state={self.state!r}>"
        )
