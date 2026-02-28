"""
Optimizer State Model - Tracks optimization phase for each cluster
=========================================================================

This model tracks which phase of the unified optimization cycle each cluster is in,
preventing conflicts between Spot ML and Rightsizing optimizers.

Phases:
- INITIAL_POOL_OPTIMIZATION: First 30-60 min after cluster connection, only pool optimization runs
- STABILIZATION: Waiting period before rightsizing evaluation
- RIGHTSIZING_EVALUATION: Rightsizing is evaluating and may propose size changes
- COMBINED_EXECUTION: Coordinator is evaluating Option A vs B vs C
- COOLDOWN: Post-execution cooldown period (6h after resize, 30min after pool switch)

State Transitions:
INITIAL_POOL_OPTIMIZATION → STABILIZATION → RIGHTSIZING_EVALUATION → COMBINED_EXECUTION → COOLDOWN → (back to pool optimization)
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from backend.models.base import Base


class OptimizationPhase(str, enum.Enum):
    """Optimization phase enum"""
    INITIAL_POOL_OPTIMIZATION = "INITIAL_POOL_OPTIMIZATION"
    STABILIZATION = "STABILIZATION"
    RIGHTSIZING_EVALUATION = "RIGHTSIZING_EVALUATION"
    COMBINED_EXECUTION = "COMBINED_EXECUTION"
    COOLDOWN = "COOLDOWN"


class OptimizerState(Base):
    """
    Tracks the current optimization phase for each cluster.

    This prevents race conditions and ensures proper sequencing of optimizations.
    """
    __tablename__ = "optimizer_states"

    id = Column(String, primary_key=True, default=lambda: f"optstate_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
    cluster_id = Column(String, ForeignKey("clusters.id"), nullable=False, unique=True, index=True)

    # Current phase
    current_phase = Column(SQLEnum(OptimizationPhase), nullable=False, default=OptimizationPhase.INITIAL_POOL_OPTIMIZATION)
    phase_started_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Timestamp tracking for each optimizer
    last_pool_optimization_at = Column(DateTime, nullable=True)
    last_rightsizing_check_at = Column(DateTime, nullable=True)
    last_combined_evaluation_at = Column(DateTime, nullable=True)

    # Link to pending rightsizing proposal
    pending_rightsizing_proposal_id = Column(String, ForeignKey("rightsizing_proposals.id"), nullable=True)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="optimization_state")
    pending_proposal = relationship("RightsizingProposal", foreign_keys=[pending_rightsizing_proposal_id])

    def __repr__(self):
        return f"<OptimizerState cluster_id={self.cluster_id} phase={self.current_phase}>"
