"""RebalancingAction Model - System B Auto-Rebalancing Actions

Tracks auto-rebalancing actions triggered by:
- Emergency: 90-second rebalancing on termination notice
- Graceful: 10-minute proactive rebalancing to safer pools
"""

from sqlalchemy import Column, Integer, String, DateTime, Float, Text, func, Index, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from backend.models.base import Base


class RebalancingAction(Base):
    """Auto-rebalancing action record."""

    __tablename__ = 'rebalancing_actions'
    __table_args__ = (
        Index('idx_rebalancing_cluster_status', 'cluster_id', 'status'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(String(100), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True)
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
    # Issue #25 (legacy columns — kept for backward compat)
    realized_savings_hourly_usd = Column(Float, nullable=True)
    realized_savings_monthly_usd = Column(Float, nullable=True)

    # Task 4.2 — written at action creation (decision time)
    source_od_price_hr = Column(Float, nullable=True)   # OD price of the replaced node
    target_spot_price_hr = Column(Float, nullable=True) # intended pool spot price
    estimated_savings_hr = Column(Float, nullable=True)
    estimated_savings_mo = Column(Float, nullable=True)

    # Task 4.2 — written at action completion (actual outcome)
    actual_instance_type = Column(String(50), nullable=True)  # may differ from target if fallback
    actual_az = Column(String(50), nullable=True)
    actual_spot_price_hr = Column(Float, nullable=True)
    realized_savings_hr = Column(Float, nullable=True)
    realized_savings_mo = Column(Float, nullable=True)
    realized_savings_pct = Column(Float, nullable=True)
    savings_gap_hr = Column(Float, nullable=True)  # estimated - realized (0 if no fallback)

    created_at = Column(DateTime, server_default=func.now())

    # Pillar 1 — State Machine: declarative execution state
    # Transitions: CREATED → POOL_SELECTED → SOURCE_CORDONED → SOURCE_DRAINED
    #              → REPLACEMENT_LAUNCHING → REPLACEMENT_READY → SOURCE_TERMINATING
    #              → COMPLETED | FAILED | DRAIN_TIMEOUT
    current_state = Column(String(30), nullable=True, index=True)

    # Step 16 (changes.md) — extended state machine columns
    state_entered_at = Column(DateTime, nullable=True)                       # when current_state was entered
    state_history = Column(JSONB, nullable=True)                             # [{state, entered_at, exited_at}]
    lock_version = Column(Integer, nullable=True, server_default='0')        # optimistic-lock counter
    source_instance_id = Column(String(50), nullable=True, index=True)       # EC2 instance ID of replaced node

    def __repr__(self):
        return f"<RebalancingAction(id={self.id}, cluster={self.cluster_id}, {self.source_pool} → {self.target_pool}, status={self.status})>"
