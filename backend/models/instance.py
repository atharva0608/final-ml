"""
Instance model - EC2 Instances
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Float, Integer, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class InstanceLifecycle(enum.Enum):
    """Instance lifecycle enumeration"""
    SPOT = "SPOT"
    ON_DEMAND = "ON_DEMAND"


class Instance(Base):
    """
    EC2 Instance model

    Represents EC2 instances discovered from AWS accounts
    """
    __tablename__ = "instances"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to clusters
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True)

    # Instance details
    instance_id = Column(String(20), nullable=False, unique=True, index=True)
    instance_type = Column(String(50), nullable=False, index=True)
    lifecycle = Column(SQLEnum(InstanceLifecycle), nullable=False, index=True)
    az = Column(String(50), nullable=False, index=True)

    # Pricing and metrics
    price = Column(Float, nullable=True)
    cpu_util = Column(Float, nullable=True)  # Percentage (0-100)
    memory_util = Column(Float, nullable=True)  # Percentage (0-100)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="instances")

    # Composite indexes for performance
    __table_args__ = (
        Index("idx_cluster_lifecycle", "cluster_id", "lifecycle"),
        Index("idx_cluster_instance_type", "cluster_id", "instance_type"),
    )

    def __repr__(self):
        return f"<Instance(id={self.id}, instance_id={self.instance_id}, type={self.instance_type}, lifecycle={self.lifecycle.value})>"
