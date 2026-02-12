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
    SPOT = "spot"
    ON_DEMAND = "on-demand"


class Instance(Base):
    """
    EC2 Instance model

    Represents EC2 instances discovered from AWS accounts
    """
    __tablename__ = "instances"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to clusters (nullable for standalone EC2 instances)
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=True, index=True)

    # Foreign key to accounts (direct link for standalone instances)
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True, index=True)

    # Instance details
    instance_id = Column(String(20), nullable=False, unique=True, index=True)
    instance_type = Column(String(50), nullable=False, index=True)
    lifecycle = Column(SQLEnum(InstanceLifecycle), nullable=False, index=True)
    az = Column(String(50), nullable=False, index=True)

    # Pricing and metrics
    price = Column(Float, nullable=True)
    cpu_util = Column(Float, nullable=True)  # Percentage (0-100)
    memory_util = Column(Float, nullable=True)  # Percentage (0-100)
    
    # Instance State
    state = Column(String(20), nullable=False, default="running", index=True)
    status = Column(String(20), nullable=True, default="READY")  # For health status: READY, CALIBRATING, UNKNOWN, TERMINATED
    status_message = Column(String(255), nullable=True)
    
    # Architecture (amd64, arm64)
    architecture = Column(String(20), nullable=True, default="amd64")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_heartbeat = Column(DateTime, nullable=True)  # For zombie node detection

    # Relationships
    cluster = relationship("Cluster", back_populates="instances")
    account = relationship("Account", foreign_keys=[account_id])

    # Composite indexes for performance
    __table_args__ = (
        Index("idx_cluster_lifecycle", "cluster_id", "lifecycle"),
        Index("idx_cluster_instance_type", "cluster_id", "instance_type"),
        Index("idx_account_state", "account_id", "state"),
    )

    def __repr__(self):
        return f"<Instance(id={self.id}, instance_id={self.instance_id}, type={self.instance_type}, lifecycle={self.lifecycle.value})>"
