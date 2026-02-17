"""RebalancingAction Model - System B Auto-Rebalancing Actions

Tracks auto-rebalancing actions triggered by:
- Emergency: 90-second rebalancing on termination notice
- Graceful: 10-minute proactive rebalancing to safer pools
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from backend.models.base import Base


class RebalancingAction(Base):
    """Auto-rebalancing action record."""

    __tablename__ = 'rebalancing_actions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(String(100), nullable=False, index=True)
    trigger = Column(String(20), nullable=False)  # 'emergency' or 'graceful'
    source_pool = Column(String(100), nullable=False)  # 'instance_type:az' (e.g., 'm5.xlarge:aps1-az1')
    target_pool = Column(String(100), nullable=False)  # 'instance_type:az' (new safe pool)
    status = Column(String(20), nullable=False, index=True)  # 'in_progress', 'completed', 'failed'
    nodes_affected = Column(Integer, nullable=True)
    pods_migrated = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    action_metadata = Column('metadata', JSONB, nullable=True)  # Additional context (e.g., termination notice details)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<RebalancingAction(id={self.id}, cluster={self.cluster_id}, {self.source_pool} → {self.target_pool}, status={self.status})>"
