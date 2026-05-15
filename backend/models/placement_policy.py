import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Float,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from backend.models.base import Base

class PlacementPolicyRecord(Base):
    """
    Persistent store for Placement Intelligence Advisor decisions.
    """
    __tablename__ = "placement_policies"

    # Identity
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    workload_id = Column(String(512), nullable=False)
    namespace = Column(String(253), nullable=False)
    name = Column(String(253), nullable=False)
    generated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Phase 1 Inputs
    criticality_tier = Column(String(20), nullable=False)
    confidence_state = Column(String(20), nullable=False)
    spot_friendly = Column(Boolean, nullable=False)

    # Distribution
    observed_replicas = Column(Integer, nullable=False)
    ondemand_target = Column(Integer, nullable=False)
    spot_target = Column(Integer, nullable=False)
    spot_target_raw = Column(Integer, nullable=False)

    # Traffic skew
    traffic_skew_detected = Column(Boolean, nullable=False, default=False)
    skew_signal_source = Column(String(50), nullable=True)
    pod_cpu_cv = Column(Float, nullable=True)
    pod_request_rate_cv = Column(Float, nullable=True)

    # NodePool
    assigned_nodepool_class = Column(String(50), nullable=False)
    spot_instance_families = Column(JSONB, nullable=False, default=list)
    spot_instance_types = Column(JSONB, nullable=False, default=list)

    # Constraints
    baseline_affinity = Column(JSONB, nullable=False, default=dict)
    burst_affinity = Column(JSONB, nullable=False, default=dict)
    topology_spread = Column(JSONB, nullable=True)
    spread_relaxation_tier = Column(Integer, nullable=False, default=0)

    # KEDA
    keda_min_replicas = Column(Integer, nullable=True)
    keda_max_replicas = Column(Integer, nullable=True)

    # Rollout
    rollout_eligible = Column(Boolean, nullable=False, default=False)
    rollout_blocked_reason = Column(String(512), nullable=True)

    # Cost
    estimated_savings_pct = Column(Float, nullable=False, default=0.0)
    estimated_monthly_saving_usd = Column(Float, nullable=False, default=0.0)

    # Actionability
    actionable = Column(Boolean, nullable=False, default=False)
    actionable_blocked_reason = Column(String(512), nullable=True)

    # Audit
    signals_used = Column(JSONB, nullable=False, default=list)
    schema_version = Column(String(10), nullable=False, default="5.10")
    input_hash = Column(String(64), nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("cluster_id", "workload_id", name="uq_placement_policies_cluster_workload"),
        Index("ix_placement_policies_cluster_actionable", "cluster_id", "actionable"),
        Index("ix_placement_policies_cluster_tier", "cluster_id", "criticality_tier"),
        Index("ix_placement_policies_cluster_rollout", "cluster_id", "rollout_eligible"),
        Index("ix_placement_policies_workload_id", "workload_id"),
    )
