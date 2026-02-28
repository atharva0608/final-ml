"""
Credential Cache Model - Encrypted STS Temporary Credentials

Stores short-lived AWS STS credentials with AES-256 encryption at rest.
Enterprise Guardrails:
- Maximum session duration: 900 seconds (15 minutes)
- All credentials encrypted with AES-256-GCM
- Auto-rotation at 80% lifetime (12 minutes for 15-min sessions)
- Audit all credential requests
"""
from sqlalchemy import Column, String, DateTime, Text, Integer, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class CredentialCache(Base):
    """
    STS Temporary Credential Cache

    Stores encrypted AWS STS credentials for Just-In-Time access.
    All credential fields are AES-256 encrypted at rest.
    """
    __tablename__ = "credential_cache"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign keys
    account_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    approval_id = Column(String(36), nullable=True, index=True)  # Link to JIT approval

    # Encrypted credential fields (AES-256-GCM encrypted)
    encrypted_access_key = Column(Text, nullable=False)
    encrypted_secret_key = Column(Text, nullable=False)
    encrypted_session_token = Column(Text, nullable=False)

    # Credential metadata (NOT encrypted - safe to log)
    role_arn = Column(String(255), nullable=False)
    session_name = Column(String(128), nullable=False)
    region = Column(String(20), nullable=False, default="us-east-1")

    # Expiration tracking (from AWS STS response)
    issued_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)  # From STS response

    # Auto-rotation tracking
    rotation_threshold_at = Column(DateTime, nullable=False)  # 80% of lifetime
    last_rotated_at = Column(DateTime, nullable=True)
    rotation_count = Column(Integer, nullable=False, default=0)

    # Status
    is_active = Column(String(10), nullable=False, default='true')  # 'true' or 'false' as string
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(String(36), nullable=True)  # User ID who revoked

    # Audit fields
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_accessed_at = Column(DateTime, nullable=True)  # Track usage
    access_count = Column(Integer, nullable=False, default=0)

    # Composite indexes for performance
    __table_args__ = (
        Index('idx_credential_active_user', 'user_id', 'is_active'),
        Index('idx_credential_expiration', 'expires_at', 'is_active'),
        Index('idx_credential_rotation', 'rotation_threshold_at', 'is_active'),
    )

    def __repr__(self):
        return f"<CredentialCache(id={self.id}, user_id={self.user_id}, role_arn={self.role_arn}, expires_at={self.expires_at})>"

    def is_expired(self) -> bool:
        """Check if credential is expired"""
        return datetime.utcnow() >= self.expires_at

    def needs_rotation(self) -> bool:
        """Check if credential needs rotation (80% lifetime)"""
        return datetime.utcnow() >= self.rotation_threshold_at

    def is_valid(self) -> bool:
        """Check if credential is valid (active and not expired)"""
        return self.is_active == 'true' and not self.is_expired()
