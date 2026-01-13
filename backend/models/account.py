"""
Account model - AWS Account connections
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SQLEnum, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class AccountStatus(enum.Enum):
    """Account status enumeration"""
    PENDING = "pending"
    SCANNING = "scanning"
    ACTIVE = "active"
    ERROR = "error"
    DISCONNECTED = "disconnected"  # NEW: For disconnect feature


class SyncStatus(enum.Enum):
    """Sync health status for heartbeat"""
    HEALTHY = "healthy"
    WARNING = "warning"
    FAILED = "failed"


class Account(Base):
    """
    AWS Account model

    Represents linked AWS accounts for cluster discovery
    """
    __tablename__ = "accounts"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to Organization
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Creator/Owner of the account connection
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # AWS account details
    aws_account_id = Column(String(12), nullable=False)
    role_arn = Column(String(255), nullable=True)  # Nullable for disconnected accounts
    external_id = Column(String(64), nullable=True)
    region = Column(String(20), nullable=True, default="us-east-1")

    # Status
    status = Column(SQLEnum(AccountStatus), nullable=False, default=AccountStatus.PENDING, index=True)
    
    # NEW: Sync/Heartbeat tracking
    last_sync_at = Column(DateTime, nullable=True)
    sync_status = Column(SQLEnum(SyncStatus), nullable=True, default=SyncStatus.HEALTHY)
    sync_error = Column(Text, nullable=True)
    
    # Default account flag
    is_default = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="accounts")
    user = relationship("User", back_populates="accounts")
    clusters = relationship("Cluster", back_populates="account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Account(id={self.id}, aws_account_id={self.aws_account_id}, status={self.status.value})>"

