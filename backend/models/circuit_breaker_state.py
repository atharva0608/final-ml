"""
Circuit Breaker State Model (Enterprise Remediation Phase 8)
=============================================================

Database model for circuit breaker persistence.

Ensures circuit breaker state survives Redis evictions.
DB is the ultimate source of truth.
"""
from sqlalchemy import Column, String, DateTime, Integer, Index
from datetime import datetime
from backend.models.base import Base, generate_uuid


class CircuitBreakerState(Base):
    """
    Circuit Breaker State Model.

    Persists circuit breaker state to DB to prevent Redis flush from resetting tripped breakers.
    """
    __tablename__ = "circuit_breaker_state"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Service identification
    service_name = Column(String(255), nullable=False, unique=True, index=True)  # e.g., "karpenter", "substitute_manager"

    # Circuit breaker state
    state = Column(String(20), nullable=False, default="CLOSED", index=True)  # CLOSED, OPEN, HALF_OPEN
    failure_count = Column(Integer, nullable=False, default=0)
    last_failure_at = Column(DateTime, nullable=True)
    trip_count = Column(Integer, nullable=False, default=0)  # Number of times breaker has tripped

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes for performance
    __table_args__ = (
        Index("idx_service_state", "service_name", "state"),
    )

    def __repr__(self):
        return (
            f"<CircuitBreakerState(service={self.service_name}, "
            f"state={self.state}, failures={self.failure_count})>"
        )

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "service_name": self.service_name,
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure_at": self.last_failure_at.isoformat() if self.last_failure_at else None,
            "trip_count": self.trip_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
