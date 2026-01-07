"""
MLModel model - ML model registry
"""
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class MLModelStatus(enum.Enum):
    """ML model status enumeration"""
    TESTING = "testing"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"


class MLModel(Base):
    """
    ML Model Registry

    Tracks ML models for interruption prediction and A/B testing
    """
    __tablename__ = "ml_models"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Model metadata
    version = Column(String(50), nullable=False, unique=True, index=True)
    file_path = Column(String(512), nullable=False)  # S3 path or local path
    status = Column(SQLEnum(MLModelStatus), nullable=False, default=MLModelStatus.TESTING, index=True)

    # Performance metrics (JSONB)
    # Structure:
    # {
    #   "accuracy": 0.95,
    #   "precision": 0.93,
    #   "recall": 0.97,
    #   "f1_score": 0.95,
    #   "test_dataset_size": 10000
    # }
    performance_metrics = Column(JSONB, nullable=True)

    # Timestamps
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    validated_at = Column(DateTime, nullable=True)
    promoted_at = Column(DateTime, nullable=True)

    # Relationships
    lab_experiments = relationship("LabExperiment", back_populates="ml_model", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<MLModel(id={self.id}, version={self.version}, status={self.status.value})>"
