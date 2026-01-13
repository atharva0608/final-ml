"""
Organization model - Multi-tenancy root
"""
from sqlalchemy import Column, String, DateTime, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid

class Organization(Base):
    """
    Organization model for multi-tenancy
    
    All resources (Accounts, Clusters) belong to an Organization.
    Users belong to an Organization.
    """
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    
    # Organization ownership - the user who created this organization
    owner_user_id = Column(String(36), nullable=True)  # Set after user is created
    
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True)
    billing_email = Column(String(255), nullable=True)
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_customer_id = Column(String(255), nullable=True)
    status = Column(String(50), default="active")
    
    # Governance & RBAC Settings
    is_governance_enabled = Column(Boolean, default=False)      # "Automated Governance" Toggle
    is_strict_approval_mode = Column(Boolean, default=False)    # If True, even Admins need approval
    governance_config = Column(JSON, default={})                # JSON config for specific actions
    required_tags = Column(JSON, default=["Owner", "Environment"])  # Feature 2: Required tag keys for compliance

    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="organization", cascade="all, delete-orphan")
    teams = relationship("Team", back_populates="organization", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Organization(id={self.id}, name={self.name})>"
