"""
Rightsizing Proposal Model - Stores size change proposals
=========================================================================

When the rightsizing service detects over-provisioned resources, it creates a proposal
instead of executing immediately. The Unified Optimizer Coordinator then evaluates
the proposal by:
1. Re-running Spot ML constrained to the new size
2. Calculating combined EV (size savings + pool savings)
3. Comparing Option A (current size + new pool) vs Option B (new size + best pool) vs Option C (do nothing)

Statuses:
- PENDING: Awaiting coordinator evaluation
- APPROVED: Coordinator approved, execution in progress
- REJECTED: Coordinator rejected (insufficient EV gain or failed constraints)
- EXECUTED: Successfully executed
- FAILED: Execution failed
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Float, Integer, Enum as SQLEnum, JSON, Text, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from backend.models.base import Base


class ProposalStatus(str, enum.Enum):
    """Rightsizing proposal status"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class RightsizingProposal(Base):
    """
    Stores rightsizing proposals (size changes) for coordinator evaluation.

    The rightsizing service creates proposals, but does not execute them directly.
    The coordinator evaluates proposals using combined EV calculation.
    """
    __tablename__ = "rightsizing_proposals"
    __table_args__ = (
        Index('idx_rightsizing_cluster_status', 'cluster_id', 'status'),
    )

    id = Column(String, primary_key=True, default=lambda: f"rsprop_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}")
    cluster_id = Column(String, ForeignKey("clusters.id"), nullable=False, index=True)

    # Current state
    current_instance_type = Column(String, nullable=False)
    current_vcpu = Column(Integer, nullable=False)
    current_memory_gb = Column(Float, nullable=False)
    current_pool = Column(String, nullable=False)  # e.g., "m5.large:us-east-1a"
    current_hourly_cost = Column(Float, nullable=False)

    # Proposed new state
    proposed_instance_type = Column(String, nullable=False)
    proposed_vcpu = Column(Integer, nullable=False)
    proposed_memory_gb = Column(Float, nullable=False)
    proposed_hourly_cost = Column(Float, nullable=False)  # Before pool re-optimization

    # Savings (before pool re-optimization)
    estimated_hourly_savings = Column(Float, nullable=False)
    estimated_monthly_savings = Column(Float, nullable=False)
    savings_percentage = Column(Float, nullable=False)

    # Workload data (14-day metrics)
    avg_cpu_utilization_pct = Column(Float, nullable=False)
    p95_cpu_utilization_pct = Column(Float, nullable=False)
    avg_memory_utilization_pct = Column(Float, nullable=False)
    p95_memory_utilization_pct = Column(Float, nullable=False)
    metric_sample_count = Column(Integer, nullable=False)
    metric_window_hours = Column(Float, nullable=False)

    # Proposal status
    status = Column(SQLEnum(ProposalStatus), nullable=False, default=ProposalStatus.PENDING)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    evaluated_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)

    # Coordinator evaluation results (populated after combined EV calculation)
    combined_ev_option_a = Column(Float, nullable=True)  # Current size + new pool
    combined_ev_option_b = Column(Float, nullable=True)  # New size + best pool
    combined_ev_option_c = Column(Float, nullable=True)  # Do nothing
    selected_option = Column(String, nullable=True)  # "A", "B", "C", or None

    # Best pool after re-optimization for new size
    best_pool_for_new_size = Column(String, nullable=True)  # e.g., "m5.xlarge:us-east-1b"
    best_pool_hourly_cost = Column(Float, nullable=True)
    best_pool_risk_score = Column(Float, nullable=True)

    # Rejection reason (if rejected)
    rejection_reason = Column(Text, nullable=True)

    # Full evaluation breakdown (JSON)
    evaluation_breakdown = Column(JSON, nullable=True)

    # ── EV Breakdown Fields (Task 2.1 — Production Hardening) ────
    # Stores full economic EV computation from evaluate_candidate_ev()
    # Nullable because pre-migration proposals won't have this data
    ev_breakdown = Column(JSON, nullable=True)
    net_ev = Column(Float, nullable=True)

    # Relationships
    cluster = relationship("Cluster", back_populates="rightsizing_proposals")

    def __repr__(self):
        return f"<RightsizingProposal {self.id} cluster={self.cluster_id} {self.current_instance_type}→{self.proposed_instance_type} status={self.status}>"

    @property
    def is_pending(self):
        return self.status == ProposalStatus.PENDING

    @property
    def is_approved(self):
        return self.status == ProposalStatus.APPROVED

    @property
    def is_rejected(self):
        return self.status == ProposalStatus.REJECTED

    @property
    def is_executed(self):
        return self.status == ProposalStatus.EXECUTED
