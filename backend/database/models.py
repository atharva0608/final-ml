"""
SQLAlchemy Database Models - Production Lab Mode

Defines production database schema for:
- Multi-tenant AWS account management
- Cross-account access with STS AssumeRole
- EC2 instance tracking and configuration
- ML model registry and experiment logging
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from .connection import Base


# ============================================================================
# User Management
# ============================================================================

class UserRole(str, enum.Enum):
    """User role enum"""
    ADMIN = "admin"
    USER = "user"
    LAB = "lab"


class User(Base):
    """User accounts with JWT authentication"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(String(20), default=UserRole.USER.value, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)

    # Relationships
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"


# ============================================================================
# AWS Account Management (Cross-Account Access)
# ============================================================================

class Account(Base):
    """AWS Account configuration for agentless cross-account access"""
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)

    # Account identification
    account_id = Column(String(12), unique=True, nullable=False, index=True)  # AWS Account ID
    account_name = Column(String(100), nullable=False)

    # Environment type
    environment_type = Column(String(20), default='LAB', nullable=False)  # PROD or LAB

    # Cross-account access (STS AssumeRole with ExternalID for confused deputy protection)
    role_arn = Column(String(255), nullable=False)  # arn:aws:iam::123456789012:role/SpotOptimizerRole
    external_id = Column(String(255), nullable=False)  # Mandatory for security

    # AWS region
    region = Column(String(20), default='ap-south-1', nullable=False)

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="accounts")
    instances = relationship("Instance", back_populates="account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Account(id={self.account_id}, name={self.account_name}, env={self.environment_type})>"


# ============================================================================
# EC2 Instance Tracking
# ============================================================================

class Instance(Base):
    """EC2 Instance configuration and tracking for Lab Mode"""
    __tablename__ = "instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)

    # Instance identification
    instance_id = Column(String(50), unique=True, nullable=False, index=True)  # EC2 instance ID
    instance_type = Column(String(20), nullable=False)
    availability_zone = Column(String(20), nullable=False)

    # Lab Mode configuration
    assigned_model_version = Column(String(50))  # e.g., "v2.1.0", NULL = use default
    pipeline_mode = Column(String(20), default='CLUSTER', nullable=False)  # CLUSTER or LINEAR
    is_shadow_mode = Column(Boolean, default=False)  # Read-only mode (no actual switches)

    # Status and metadata
    is_active = Column(Boolean, default=True)
    last_evaluation = Column(DateTime)
    metadata = Column(JSONB)  # Additional instance metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="instances")
    experiment_logs = relationship("ExperimentLog", back_populates="instance", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Instance(id={self.instance_id}, type={self.instance_type}, mode={self.pipeline_mode})>"


# ============================================================================
# ML Model Management
# ============================================================================

class ModelRegistry(Base):
    """ML model version control and registry"""
    __tablename__ = "model_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False)  # e.g., "FamilyStressPredictor"
    version = Column(String(20), nullable=False)  # e.g., "v2.1.0"

    # Model location
    s3_path = Column(String(255))  # S3 URI for model file
    local_path = Column(String(255))  # Local filesystem path
    description = Column(Text)

    # Model metadata
    is_experimental = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    feature_version = Column(String(20))  # Feature schema version compatibility

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))

    # Relationships
    experiment_logs = relationship("ExperimentLog", back_populates="model")

    def __repr__(self):
        return f"<ModelRegistry(name={self.name}, version={self.version}, experimental={self.is_experimental})>"


# ============================================================================
# Experiment Logging
# ============================================================================

class ExperimentLog(Base):
    """Lab Mode experiment logs for R&D analytics"""
    __tablename__ = "experiment_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id = Column(UUID(as_uuid=True), ForeignKey('instances.id', ondelete='CASCADE'), nullable=False, index=True)
    model_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'))

    # Execution metadata
    pipeline_mode = Column(String(20))  # CLUSTER or LINEAR
    is_shadow_run = Column(Boolean, default=False)  # Was this a shadow mode run?

    # ML prediction data
    prediction_score = Column(Float)  # Crash probability
    decision = Column(String(50))  # SWITCH, HOLD, FAILED
    decision_reason = Column(Text)

    # Execution timing
    execution_time = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    execution_duration_ms = Column(Integer)

    # Result data (if SWITCH decision)
    candidates_evaluated = Column(Integer)
    selected_instance_type = Column(String(20))
    selected_availability_zone = Column(String(20))
    old_spot_price = Column(Float)
    new_spot_price = Column(Float)
    projected_hourly_savings = Column(Float)

    # Feature values (for debugging)
    features_used = Column(JSONB)  # Feature vector snapshot

    # Error tracking
    error_message = Column(Text)

    # Relationships
    model = relationship("ModelRegistry", back_populates="experiment_logs")
    instance = relationship("Instance", back_populates="experiment_logs")

    def __repr__(self):
        return f"<ExperimentLog(instance={self.instance_id}, decision={self.decision}, score={self.prediction_score})>"
