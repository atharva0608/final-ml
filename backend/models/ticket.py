
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base

class TicketStatus(enum.Enum):
    PENDING = "PENDING"
    PENDING_CONSENT = "PENDING_CONSENT" # For delegated grants
    APPROVED_ACTIVE = "APPROVED_ACTIVE"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"

class TicketType(enum.Enum):
    ACCESS_WINDOW = "ACCESS_WINDOW"
    ACTION = "ACTION"
    SYSTEM_CLEANUP = "SYSTEM_CLEANUP"

class ReasonCategory(enum.Enum):
    MAINTENANCE = "MAINTENANCE"
    INCIDENT = "INCIDENT"
    DEPLOYMENT = "DEPLOYMENT"
    DEBUGGING = "DEBUGGING"
    AUDIT = "AUDIT"
    OTHER = "OTHER"

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String, primary_key=True) # UUID
    
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    
    # The approver (Team Lead or Admin). Null if self-approved or pending.
    approver_id = Column(String, ForeignKey("users.id"), nullable=True)
    
    # For delegated grants hierarchy
    parent_id = Column(String, ForeignKey("tickets.id"), nullable=True)
    
    type = Column(Enum(TicketType), default=TicketType.ACCESS_WINDOW)
    
    # Resource scoping (Optional)
    resource_id = Column(String, nullable=True)
    
    # Action Type (e.g., "connect", "terminate", "debug")
    action_type = Column(String, nullable=True)
    
    # Audit / Reason
    reason_category = Column(Enum(ReasonCategory), nullable=True)
    reason_text = Column(Text, nullable=True)
    
    duration_hours = Column(Integer, default=1)
    
    status = Column(Enum(TicketStatus), default=TicketStatus.PENDING)
    
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
    
    children = relationship("Ticket", backref="parent", remote_side=[id])
