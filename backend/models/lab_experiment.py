"""
LabExperiment model - ML model A/B testing experiments
"""
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class ExperimentStatus(enum.Enum):
    """Lab experiment status enumeration"""
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class LabExperiment(Base):
    """
    Lab Experiment model

    Tracks A/B testing experiments for ML models in The Lab
    """
    __tablename__ = "lab_experiments"

    # Suppress Pydantic warning about model_id field
    model_config = {'protected_namespaces': ()}

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to ml_models
    model_id = Column(String(36), ForeignKey("ml_models.id", ondelete="CASCADE"), nullable=False, index=True)
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True)

    # Test configuration
    instance_id = Column(String(20), nullable=False)  # EC2 instance used for test
    test_type = Column(String(50), nullable=False)  # e.g., "interruption_prediction", "bin_packing"

    # Telemetry data (JSONB)
    # Structure:
    # {
    #   "latency_ms": 15.2,
    #   "accuracy": 0.96,
    #   "predictions_count": 1000,
    #   "memory_usage_mb": 512,
    #   "cpu_usage_percent": 45.3
    # }
    telemetry = Column(JSONB, nullable=False, default={})

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Relationships
    ml_model = relationship("MLModel", back_populates="lab_experiments")
    cluster = relationship("Cluster", backref="lab_experiments")

    def __repr__(self):
        return f"<LabExperiment(id={self.id}, model_id={self.model_id}, test_type={self.test_type})>"
