"""
OptimizationJob model - Optimization job tracking
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SQLEnum, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class OptimizationJobStatus(enum.Enum):
    """Optimization job status enumeration"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class OptimizationJob(Base):
    """
    Optimization Job model

    Tracks optimization runs for each cluster
    """
    __tablename__ = "optimization_jobs"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to clusters
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True)

    # Job status
    status = Column(SQLEnum(OptimizationJobStatus), nullable=False, default=OptimizationJobStatus.QUEUED, index=True)

    # Results (JSONB)
    # Structure:
    # {
    #   "opportunities_found": 5,
    #   "estimated_savings": 125.50,
    #   "actions_executed": 3,
    #   "actions_failed": 0,
    #   "error_message": null
    # }
    results = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    cluster = relationship("Cluster", back_populates="optimization_jobs")

    # Composite index for performance
    __table_args__ = (
        Index("idx_optimization_cluster_status", "cluster_id", "status"),
        Index("idx_optimization_created_desc", created_at.desc()),
    )

    def __repr__(self):
        return f"<OptimizationJob(id={self.id}, cluster_id={self.cluster_id}, status={self.status.value})>"
