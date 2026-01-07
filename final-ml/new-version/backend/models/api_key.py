"""
APIKey model - Agent authentication tokens
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid
import secrets
import hashlib


class APIKey(Base):
    """
    API Key model

    Stores hashed API keys for Kubernetes Agent authentication
    """
    __tablename__ = "api_keys"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to clusters
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True)

    # API key (hashed)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)  # SHA-256 hash
    key_prefix = Column(String(8), nullable=False, index=True)  # First 8 chars for display (e.g., "sk-abc12...")

    # Metadata
    description = Column(String(255), nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # Optional expiration

    # Relationships
    cluster = relationship("Cluster", back_populates="api_keys")

    def __repr__(self):
        return f"<APIKey(id={self.id}, prefix={self.key_prefix}, cluster_id={self.cluster_id})>"

    @staticmethod
    def generate_api_key() -> tuple[str, str, str]:
        """
        Generate a new API key

        Returns:
            tuple: (full_key, key_hash, key_prefix)
                - full_key: The actual API key to give to user (store this nowhere!)
                - key_hash: SHA-256 hash to store in database
                - key_prefix: First 8 chars for display purposes
        """
        # Generate secure random key (32 bytes = 64 hex chars)
        full_key = f"sk-{secrets.token_hex(32)}"

        # Hash the key for storage
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()

        # Extract prefix for display
        key_prefix = full_key[:8]

        return (full_key, key_hash, key_prefix)

    @staticmethod
    def hash_key(api_key: str) -> str:
        """
        Hash an API key for verification

        Args:
            api_key: The API key to hash

        Returns:
            SHA-256 hash of the key
        """
        return hashlib.sha256(api_key.encode()).hexdigest()
