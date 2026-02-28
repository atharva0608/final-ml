"""
Agent Identity Model

Stores agent identity information including public keys for JWT validation.
Implements OIDC federation trust for Kubernetes ServiceAccount tokens.
"""
from sqlalchemy import Column, String, Text, DateTime, Boolean, JSON, Integer
from sqlalchemy.sql import func
from backend.models.base import Base, generate_uuid


class AgentIdentity(Base):
    """
    Agent Identity - Stores agent public keys and identity for OIDC federation

    Enterprise Security Model:
    - Agents authenticate via Kubernetes ServiceAccount JWT tokens
    - Backend validates token signature using public key from OIDC discovery
    - No static secrets stored in cluster - only ServiceAccount tokens
    - Supports certificate rotation via public key updates
    """
    __tablename__ = "agent_identities"

    # Primary key
    id = Column(String, primary_key=True, default=generate_uuid)

    # Cluster association
    cluster_id = Column(String, nullable=False, index=True, unique=True)

    # OIDC Configuration
    oidc_issuer = Column(String, nullable=False)  # EKS OIDC provider URL
    oidc_audience = Column(String, nullable=False, default="sts.amazonaws.com")

    # ServiceAccount Identity
    service_account_namespace = Column(String, nullable=False, default="spot-optimizer")
    service_account_name = Column(String, nullable=False, default="spot-agent-sa")

    # Public Key Storage (CRITICAL: Only public keys, NEVER private keys)
    # This stores the public key from the OIDC provider for token signature verification
    public_key_pem = Column(Text, nullable=True)  # PEM-encoded public key
    public_key_algorithm = Column(String, nullable=False, default="RS256")  # JWT algorithm

    # JWKS (JSON Web Key Set) from OIDC discovery
    # Contains multiple keys for rotation support
    jwks_json = Column(JSON, nullable=True)
    jwks_last_updated = Column(DateTime(timezone=True), nullable=True)

    # Certificate Thumbprint (for AWS IAM OIDC provider)
    # Used to pin the OIDC provider certificate
    certificate_thumbprint = Column(String, nullable=True, index=True)

    # Token Validation Configuration
    max_token_age_seconds = Column(Integer, nullable=False, default=3600)  # 1 hour max
    require_nbf_claim = Column(Boolean, nullable=False, default=True)  # Require "not before"
    require_exp_claim = Column(Boolean, nullable=False, default=True)  # Require expiration

    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    last_token_validated_at = Column(DateTime(timezone=True), nullable=True)
    validation_failure_count = Column(Integer, nullable=False, default=0)

    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Metadata
    agent_metadata = Column(JSON, nullable=False, default=dict)  # Renamed to avoid SQLAlchemy reserved name

    def __repr__(self):
        return f"<AgentIdentity(cluster_id='{self.cluster_id}', issuer='{self.oidc_issuer}')>"

    def to_dict(self):
        """Convert to dictionary representation"""
        return {
            "id": self.id,
            "cluster_id": self.cluster_id,
            "oidc_issuer": self.oidc_issuer,
            "oidc_audience": self.oidc_audience,
            "service_account_namespace": self.service_account_namespace,
            "service_account_name": self.service_account_name,
            "public_key_algorithm": self.public_key_algorithm,
            "certificate_thumbprint": self.certificate_thumbprint,
            "max_token_age_seconds": self.max_token_age_seconds,
            "is_active": self.is_active,
            "last_token_validated_at": self.last_token_validated_at.isoformat() if self.last_token_validated_at else None,
            "validation_failure_count": self.validation_failure_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
