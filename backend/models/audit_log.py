"""
AuditLog model - Immutable audit trail
"""
from sqlalchemy import Column, String, DateTime, Index, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class AuditOutcome(enum.Enum):
    """Audit log outcome enumeration"""
    SUCCESS = "success"
    FAILURE = "failure"


class ResourceType(enum.Enum):
    """Resource type enumeration"""
    CLUSTER = "cluster"
    INSTANCE = "instance"
    TEMPLATE = "template"
    POLICY = "policy"
    HIBERNATION = "hibernation"
    USER = "user"
    ACCOUNT = "account"


class AuditLog(Base):
    """
    Audit Log model - Immutable compliance trail

    Records all system actions for compliance and debugging
    """
    __tablename__ = "audit_logs"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Timestamp with milliseconds
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    # Actor information
    actor_id = Column(String(36), nullable=False, index=True)  # User ID or system
    actor_name = Column(String(255), nullable=False)

    # Event details
    event = Column(String(255), nullable=False, index=True)  # Action performed
    resource = Column(String(255), nullable=False)  # Resource affected
    resource_type = Column(SQLEnum(ResourceType), nullable=False, index=True)
    outcome = Column(SQLEnum(AuditOutcome), nullable=False, default=AuditOutcome.SUCCESS)

    # Request context
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(512), nullable=True)

    # Before/after state (JSONB)
    diff_before = Column(JSONB, nullable=True)
    diff_after = Column(JSONB, nullable=True)

    # Indexes for query performance
    __table_args__ = (
        Index("idx_audit_timestamp_desc", timestamp.desc()),
        Index("idx_audit_actor_timestamp", "actor_id", timestamp.desc()),
        Index("idx_audit_resource_type_timestamp", "resource_type", timestamp.desc()),
    )

    def __repr__(self):
        return f"<AuditLog(id={self.id}, event={self.event}, actor={self.actor_name}, outcome={self.outcome.value})>"

    # Note: This model is immutable - no update() method should be implemented
    # Updates should be prevented at the application layer
