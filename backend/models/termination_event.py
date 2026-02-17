"""TerminationEvent Model - System B Termination Detection Log

Tracks spot instance termination notices from:
- EventBridge: AWS-provided termination notices (2-minute warning)
- DaemonSet: Node-level termination detection
- Manual: User-initiated termination flags
"""

from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from backend.models.base import Base


class TerminationEvent(Base):
    """Spot instance termination event record."""

    __tablename__ = 'termination_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_type = Column(String(50), nullable=False, index=True)
    az = Column(String(20), nullable=False, index=True)
    region = Column(String(20), nullable=False)
    cluster_id = Column(String(100), nullable=True, index=True)
    instance_id = Column(String(50), nullable=True)  # AWS instance ID (i-xxxxx)
    node_name = Column(String(100), nullable=True)  # Kubernetes node name
    detected_at = Column(DateTime, nullable=False, index=True)
    source = Column(String(20), nullable=False)  # 'daemonset', 'eventbridge', 'manual'
    action_taken = Column(String(50), nullable=True)  # 'flagged', 'rebalanced', 'none'
    event_metadata = Column('metadata', JSONB, nullable=True)  # Additional context (e.g., termination time, reason)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<TerminationEvent(id={self.id}, pool={self.instance_type}:{self.az}, source={self.source}, action={self.action_taken})>"

    @property
    def pool_key(self) -> str:
        """Returns pool identifier in format 'instance_type:az'."""
        return f"{self.instance_type}:{self.az}"
