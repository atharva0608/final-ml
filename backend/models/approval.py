"""
Approval Request model for Maker-Checker workflows
"""
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid
from backend.models.base import Base

class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"

class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    requester_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    approver_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    
    # Context
    resource_type = Column(String(50), nullable=False) # e.g. "AWS_RESOURCE"
    resource_id = Column(String(100), nullable=False)  # or "BATCH" if multiple
    action = Column(String(50), nullable=False)        # e.g. "CLEANUP_EXECUTE"
    
    # Payload to execute later
    execution_payload = Column(JSON, nullable=False)   # {"account_id": "...", "action_data": {...}}
    
    status = Column(SAEnum(ApprovalStatus), default=ApprovalStatus.PENDING)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    requester = relationship("User", foreign_keys=[requester_id])
    approver = relationship("User", foreign_keys=[approver_id])
