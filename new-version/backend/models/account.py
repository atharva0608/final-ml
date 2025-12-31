"""
Account model - AWS Account connections
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SQLEnum
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


class Account(Base):
    """
    AWS Account model

    Represents linked AWS accounts for cluster discovery
    """
    __tablename__ = "accounts"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to users
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # AWS account details
    aws_account_id = Column(String(12), nullable=False)
    role_arn = Column(String(255), nullable=False)
    external_id = Column(String(64), nullable=True)

    # Status
    status = Column(SQLEnum(AccountStatus), nullable=False, default=AccountStatus.PENDING, index=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="accounts")
    clusters = relationship("Cluster", back_populates="account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Account(id={self.id}, aws_account_id={self.aws_account_id}, status={self.status.value})>"
