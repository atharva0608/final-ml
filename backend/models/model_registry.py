"""
Model Registry Model (Enterprise Remediation Phase 2)
======================================================

Database model for ML model versioning and feature schema tracking.

Stores model versions with their feature schema versions to enforce
immutable feature schema validation at inference time.
"""
from sqlalchemy import Column, String, DateTime, Boolean, Index
from datetime import datetime
from backend.models.base import Base, generate_uuid


class ModelRegistry(Base):
    """
    Model Registry Model.

    Tracks ML model versions, their feature schema versions, and ONNX paths.
    Enforces runtime validation: assert model.feature_schema_version == feature_schema.version
    """
    __tablename__ = "model_registry"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Model identification
    model_version = Column(String(10), nullable=False, unique=True, index=True)  # e.g., "v6"
    model_name = Column(String(255), nullable=False)  # e.g., "classifier_6" or "regressor_6"

    # Feature schema tracking
    feature_schema_version = Column(String(10), nullable=False, index=True)  # e.g., "v1"

    # Model artifact paths
    onnx_path = Column(String(500), nullable=False)  # Path to ONNX model file

    # Deployment status
    is_active = Column(Boolean, nullable=False, default=False, index=True)  # Currently deployed
    deployed_at = Column(DateTime, nullable=True)  # When deployed to production
    deprecated_at = Column(DateTime, nullable=True)  # When deprecated

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes for performance
    __table_args__ = (
        Index("idx_model_version_schema", "model_version", "feature_schema_version"),
        Index("idx_active_models", "is_active", "deployed_at"),
    )

    def __repr__(self):
        return (
            f"<ModelRegistry(model_version={self.model_version}, "
            f"feature_schema={self.feature_schema_version}, active={self.is_active})>"
        )

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "model_version": self.model_version,
            "model_name": self.model_name,
            "feature_schema_version": self.feature_schema_version,
            "onnx_path": self.onnx_path,
            "is_active": self.is_active,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "deprecated_at": self.deprecated_at.isoformat() if self.deprecated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
