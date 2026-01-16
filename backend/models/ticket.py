from sqlalchemy import Column, String, ForeignKey, DateTime, Enum, Text, Integer
from sqlalchemy.orm import relationship, backref
from datetime import datetime
import uuid
import enum
from backend.models.base import Base

class TicketType(str, enum.Enum):
    ACTION = "ACTION"
    ACCESS_WINDOW = "ACCESS_WINDOW"

class TicketStatus(str, enum.Enum):
    PENDING = "PENDING"
    PENDING_CONSENT = "PENDING_CONSENT" # New status for delegated access
    APPROVED_ACTIVE = "APPROVED_ACTIVE"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    COMPLETED = "COMPLETED"

class ReasonCategory(str, enum.Enum):
    MAINTENANCE = "MAINTENANCE"
    COST_OPT = "COST_OPT"
    INCIDENT = "INCIDENT"
    TESTING = "TESTING"
    OTHER = "OTHER"

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Parent Ticket (for bulk grants / delegation grouping)
    parent_id = Column(String(36), ForeignKey("tickets.id"), nullable=True, index=True)

    # User who needs access
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    # Organization context
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    
    # Approver (Team Lead usually) - Nullable if pending or system auto-approved
    approver_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    
    # Metadata
    type = Column(Enum(TicketType), nullable=False)
    status = Column(Enum(TicketStatus), default=TicketStatus.PENDING, index=True)
    
    # Target
    resource_id = Column(String(100), nullable=True) # e.g. "i-1234567890abcdef0"
    action_type = Column(String(100), nullable=True) # e.g. "TERMINATE_INSTANCE"
    
    # Justification
    reason_category = Column(Enum(ReasonCategory), nullable=False)
    reason_text = Column(Text, nullable=True)
    
    # Time Constraints
    duration_hours = Column(Integer, nullable=False) # Helper for "how long requested"
    expires_at = Column(DateTime, nullable=True) # Set upon approval/activation
    approved_at = Column(DateTime, nullable=True) # When Admin/Lead approved (for Grants, this is creation time)
    activated_at = Column(DateTime, nullable=True) # When User CONSENTED (Timer starts here for grants)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="mytickets")
    approver = relationship("User", foreign_keys=[approver_id], backref="approved_tickets")
    organization = relationship("Organization")
    
    # Self-referential relationship for Parent/Child tickets
    children = relationship("Ticket", 
        backref=backref("parent", remote_side=[id]),
        cascade="all, delete-orphan"
    )

