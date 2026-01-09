"""
ClusterPolicy model - Optimization policy configuration
"""
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class ClusterPolicy(Base):
    """
    Cluster Policy model

    Stores optimization policy configuration as JSONB
    """
    __tablename__ = "cluster_policies"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to clusters (one-to-one)
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Policy configuration (JSONB)
    # Structure:
    # {
    #   "karpenter_enabled": true,
    #   "strategy": "spot_only",  # spot_only / hybrid / conservative
    #   "binpack_enabled": true,
    #   "binpack_threshold": 30,  # percentage
    #   "fallback_on_demand": true,
    #   "excluded_namespaces": ["kube-system", "kube-public"]
    # }
    config = Column(JSONB, nullable=False, default={})

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="cluster_policy")

    def __repr__(self):
        return f"<ClusterPolicy(id={self.id}, cluster_id={self.cluster_id})>"
