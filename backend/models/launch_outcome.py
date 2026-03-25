"""LaunchOutcome Model — Step 14 (changes.md)

Tracks actual launch results per pool to feed pool_reputation_service.
One row per RunInstances or CreateFleet call.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, func, Index
from backend.models.base import Base


class LaunchOutcome(Base):
    """Records the outcome of each spot launch attempt for pool reputation tracking."""

    __tablename__ = 'launch_outcomes'
    __table_args__ = (
        Index('idx_launch_outcomes_pool_key', 'pool_key', 'launched_at'),
        Index('idx_launch_outcomes_cluster', 'cluster_id', 'launched_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Pool identification
    pool_key = Column(String(100), nullable=False, index=True)   # "instance_type:az"
    cluster_id = Column(String(100), nullable=False, index=True)
    instance_type = Column(String(50), nullable=False)
    az = Column(String(50), nullable=False)
    region = Column(String(50), nullable=False)

    # Outcome
    # 'success'      — instance launched and joined cluster
    # 'failed'       — RunInstances/CreateFleet returned capacity error
    # 'interrupted'  — spot interruption notice received while running
    outcome = Column(String(20), nullable=False)

    # Pricing
    actual_spot_price_hr = Column(Float, nullable=True)   # price at launch time

    # Lifecycle duration
    uptime_hours = Column(Float, nullable=True)           # hours alive before termination / None if still running
    launched_at = Column(DateTime, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)         # None = still running

    # Failure detail (populated when outcome='failed' or 'interrupted')
    failure_reason = Column(Text, nullable=True)

    # Linked rebalancing action (optional — for traceability)
    rebalancing_action_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return (
            f"<LaunchOutcome(id={self.id}, pool={self.pool_key}, "
            f"outcome={self.outcome}, cluster={self.cluster_id})>"
        )
