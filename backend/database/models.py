"""
SQLAlchemy Database Models

Defines all database tables as SQLAlchemy ORM models.
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
    LAB = "lab"  # Lab Mode users


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

    # Rate limiting
    active_sessions_count = Column(Integer, default=0)
    last_login = Column(DateTime)

    # Relationships
    sandbox_sessions = relationship("SandboxSession", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"


# ============================================================================
# Sandbox Mode
# ============================================================================

class SandboxSession(Base):
    """Sandbox testing sessions"""
    __tablename__ = "sandbox_sessions"

    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    # Temporary credentials
    temp_username = Column(String(50), unique=True, nullable=False)
    temp_password_hash = Column(String(255), nullable=False)

    # AWS credentials (encrypted)
    aws_access_key_encrypted = Column(Text, nullable=False)
    aws_secret_key_encrypted = Column(Text, nullable=False)
    aws_region = Column(String(20), default='ap-south-1')

    # Target instance
    target_instance_id = Column(String(50), nullable=False)
    target_instance_type = Column(String(20))
    target_availability_zone = Column(String(20))

    # Session lifecycle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)

    # Relationships
    user = relationship("User", back_populates="sandbox_sessions")
    actions = relationship("SandboxAction", back_populates="session", cascade="all, delete-orphan")
    savings = relationship("SandboxSavings", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SandboxSession(id={self.session_id}, user={self.user_id}, active={self.is_active})>"


class SandboxAction(Base):
    """Sandbox action logs"""
    __tablename__ = "sandbox_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('sandbox_sessions.session_id', ondelete='CASCADE'), nullable=False)

    action_type = Column(String(50), nullable=False)  # AMI_CREATE, SPOT_LAUNCH, INSTANCE_STOP, etc.
    action_status = Column(String(20), nullable=False)  # SUCCESS, FAILED, IN_PROGRESS
    action_details = Column(JSONB)

    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    execution_time_ms = Column(Integer)
    error_message = Column(Text)

    # Relationships
    session = relationship("SandboxSession", back_populates="actions")

    def __repr__(self):
        return f"<SandboxAction(type={self.action_type}, status={self.action_status})>"


class SandboxSavings(Base):
    """Sandbox savings analytics"""
    __tablename__ = "sandbox_savings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('sandbox_sessions.session_id', ondelete='CASCADE'), nullable=False)

    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    old_instance_type = Column(String(20))
    new_instance_type = Column(String(20))
    old_spot_price = Column(Float)
    new_spot_price = Column(Float)
    projected_hourly_savings = Column(Float)

    # Relationships
    session = relationship("SandboxSession", back_populates="savings")

    def __repr__(self):
        return f"<SandboxSavings(session={self.session_id}, savings=${self.projected_hourly_savings:.4f}/hr)>"


# ============================================================================
# Lab Mode
# ============================================================================

class ModelRegistry(Base):
    """ML model version control"""
    __tablename__ = "model_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False)
    version = Column(String(20), nullable=False)

    s3_path = Column(String(255))
    local_path = Column(String(255))
    description = Column(Text)

    is_experimental = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))

    # Relationships
    instance_configs = relationship("InstanceConfig", back_populates="assigned_model")
    experiment_logs = relationship("ExperimentLog", back_populates="model")

    def __repr__(self):
        return f"<ModelRegistry(name={self.name}, version={self.version}, experimental={self.is_experimental})>"


class InstanceConfig(Base):
    """Per-instance pipeline configuration"""
    __tablename__ = "instance_config"

    instance_id = Column(String(50), primary_key=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))

    # Pipeline config
    pipeline_mode = Column(String(20), default='CLUSTER_FULL', nullable=False)  # CLUSTER_FULL or SINGLE_LINEAR

    # Model assignment
    assigned_model_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'))

    # Feature flags
    enable_bin_packing = Column(Boolean, default=True)
    enable_right_sizing = Column(Boolean, default=True)
    enable_family_stress = Column(Boolean, default=True)

    # Region
    aws_region = Column(String(20), default='ap-south-1')

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assigned_model = relationship("ModelRegistry", back_populates="instance_configs")
    experiment_logs = relationship("ExperimentLog", back_populates="instance_config")

    def __repr__(self):
        return f"<InstanceConfig(id={self.instance_id}, mode={self.pipeline_mode}, model={self.assigned_model_id})>"


class ExperimentLog(Base):
    """Lab Mode experiment logs"""
    __tablename__ = "experiment_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id = Column(String(50), ForeignKey('instance_config.instance_id'), nullable=False)
    model_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'))
    model_version = Column(String(20))

    # Prediction data
    prediction_score = Column(Float)
    decision = Column(String(50))  # SWITCH, HOLD, FAILED

    # Execution data
    execution_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    execution_duration_ms = Column(Integer)

    # Result data
    candidates_evaluated = Column(Integer)
    selected_instance_type = Column(String(20))
    selected_availability_zone = Column(String(20))
    spot_price = Column(Float)
    on_demand_price = Column(Float)
    projected_savings = Column(Float)

    # Error tracking
    error_message = Column(Text)

    # Metadata
    pipeline_mode = Column(String(20))
    metadata = Column(JSONB)

    # Relationships
    model = relationship("ModelRegistry", back_populates="experiment_logs")
    instance_config = relationship("InstanceConfig", back_populates="experiment_logs")

    def __repr__(self):
        return f"<ExperimentLog(instance={self.instance_id}, decision={self.decision}, model={self.model_version})>"
