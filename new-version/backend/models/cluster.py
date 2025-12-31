"""
Cluster model - Kubernetes Clusters
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class ClusterStatus(enum.Enum):
    """Cluster status enumeration"""
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class Cluster(Base):
    """
    Kubernetes Cluster model

    Represents EKS clusters discovered from AWS accounts
    """
    __tablename__ = "clusters"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to accounts
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)

    # Cluster details
    name = Column(String(255), nullable=False, index=True)
    region = Column(String(50), nullable=False, index=True)
    vpc_id = Column(String(50), nullable=True)
    api_endpoint = Column(String(255), nullable=True)
    k8s_version = Column(String(20), nullable=True)

    # Status
    status = Column(SQLEnum(ClusterStatus), nullable=False, default=ClusterStatus.PENDING, index=True)

    # Agent connection
    agent_installed = Column(String(1), nullable=False, default="N")  # Y/N
    last_heartbeat = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="clusters")
    instances = relationship("Instance", back_populates="cluster", cascade="all, delete-orphan")
    cluster_policy = relationship("ClusterPolicy", back_populates="cluster", uselist=False, cascade="all, delete-orphan")
    hibernation_schedule = relationship("HibernationSchedule", back_populates="cluster", uselist=False, cascade="all, delete-orphan")
    optimization_jobs = relationship("OptimizationJob", back_populates="cluster", cascade="all, delete-orphan")
    agent_actions = relationship("AgentAction", back_populates="cluster", cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="cluster", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Cluster(id={self.id}, name={self.name}, region={self.region}, status={self.status.value})>"
