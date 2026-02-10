
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, Integer, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid

class ApprovalStatus(enum.Enum):
    PENDING = "PENDING"
    PENDING_CONSENT = "PENDING_CONSENT" # For delegated grants
    APPROVED_ACTIVE = "APPROVED_ACTIVE"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"

class ApprovalType(enum.Enum):
    ACCESS_WINDOW = "ACCESS_WINDOW"
    ACTION = "ACTION"
    SYSTEM_CLEANUP = "SYSTEM_CLEANUP"
    JIT_FEATURE = "JIT_FEATURE"  # Feature-specific time-bound access

class JITScope(enum.Enum):
    """Scope of JIT access grant"""
    SELF = "SELF"          # User can only act on their own resources
    TEAM = "TEAM"          # User can act on team resources
    ORGANIZATION = "ORGANIZATION"  # User can act on org-wide resources
    GLOBAL = "GLOBAL"      # User can act on any resource (highest privilege)

class ReasonCategory(enum.Enum):
    MAINTENANCE = "MAINTENANCE"
    INCIDENT = "INCIDENT"
    DEPLOYMENT = "DEPLOYMENT"
    DEBUGGING = "DEBUGGING"
    AUDIT = "AUDIT"
    OTHER = "OTHER"

class Approval(Base):
    __tablename__ = "approvals"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)

    # The approver (Team Lead or Admin). Null if self-approved or pending.
    approver_id = Column(String, ForeignKey("users.id"), nullable=True)

    # For delegated grants hierarchy
    parent_id = Column(String, ForeignKey("approvals.id"), nullable=True)

    type = Column(Enum(ApprovalType), default=ApprovalType.ACCESS_WINDOW)

    # JIT Feature-Specific Access
    feature_id = Column(String(100), nullable=True, index=True)  # e.g., "hygiene:execute", "compute:terminate"
    jit_scope = Column(Enum(JITScope), default=JITScope.TEAM)  # Scope of granted access
    jit_metadata = Column(JSON, nullable=True)  # Additional feature-specific data

    # Resource scoping (Optional)
    resource_id = Column(String, nullable=True)

    # Action Type (e.g., "connect", "terminate", "debug")
    action_type = Column(String, nullable=True)

    # Audit / Reason
    reason_category = Column(Enum(ReasonCategory), nullable=True)
    reason_text = Column(Text, nullable=True)

    duration_hours = Column(Integer, default=1)

    # Auto-approval for trusted roles (bypasses manual approval)
    auto_approved = Column(Boolean, default=False)

    status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True) # When the window actually starts
    expires_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    approver = relationship("User", foreign_keys=[approver_id])
    organization = relationship("Organization")

    children = relationship("Approval", backref="parent", remote_side=[id])
