"""
Invitation model - Manages organization invitations with persistent permissions
"""
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid
from backend.models.user import OrgRole, AccessLevel

class InvitationStatus(enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"

class OrganizationInvitation(Base):
    """
    Model for organization invitations

    Persists role and access_level to ensure deterministic permissions upon acceptance.
    """
    __tablename__ = "organization_invitations"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    
    # Invitation details
    email = Column(String(255), nullable=False, index=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(SQLEnum(InvitationStatus), default=InvitationStatus.PENDING, nullable=False)
    
    # Permissions to grant
    role = Column(SQLEnum(OrgRole), nullable=False, default=OrgRole.MEMBER)
    access_level = Column(SQLEnum(AccessLevel), nullable=False, default=AccessLevel.READ_ONLY)
    
    # Links
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True) # ID of the inviting user
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    inviter = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<Invitation(email={self.email}, role={self.role}, status={self.status})>"
