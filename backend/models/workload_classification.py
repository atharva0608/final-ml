"""
Workload Classification DB Model — WIE v4.4
============================================
Persistent store for workload classification records.

Table: workload_classifications

Write suppression: Records are only written when score_delta >= 1,
spot_friendly changes, tier changes, confidence_state changes,
OR input_hash doesn't match (new classification inputs).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from backend.models.base import Base


class WorkloadClassificationRecord(Base):
    __tablename__ = "workload_classifications"

    # ── Primary key ─────────────────────────────────────────────────────────
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ── Cluster FK ──────────────────────────────────────────────────────────
    cluster_id = Column(
        String(36),
        ForeignKey("clusters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Workload identity ────────────────────────────────────────────────────
    workload_id = Column(String(512), nullable=False)       # "namespace/name"
    namespace = Column(String(253), nullable=False)
    name = Column(String(253), nullable=False)
    controller_kind = Column(String(50), nullable=False)

    # ── Engine outputs ────────────────────────────────────────────────────────
    role = Column(String(20), nullable=False)               # SYSTEM / CONTROL_PLANE / APPLICATION
    criticality_score = Column(Integer, nullable=False)
    tier = Column(String(20), nullable=False)               # Platinum / Gold / Silver / Bronze
    spot_score = Column(Integer, nullable=False)
    spot_friendly = Column(Boolean, nullable=False)
    confidence_score = Column(Integer, nullable=False)
    confidence_state = Column(String(20), nullable=False)   # DRAFT / PROVISIONAL / CONFIRMED
    data_safety = Column(String(20), nullable=False)        # STATEFUL / CACHE / EPHEMERAL

    # ── Traceability ──────────────────────────────────────────────────────────
    signals_fired = Column(JSONB, nullable=False, default=list)

    # ── Override metadata ─────────────────────────────────────────────────────
    override_active = Column(Boolean, nullable=False, default=False)
    override_reason = Column(String(512), nullable=True)

    # ── Content fingerprint ───────────────────────────────────────────────────
    input_hash = Column(String(100), nullable=False, default="")
    # ── v4.4 placement intent signals ─────────────────────────────────────────
    az_spread_required = Column(Boolean, nullable=False, server_default="false", default=False)
    disruption_safe = Column(Boolean, nullable=False, server_default="false", default=False)

    # ── v4.5 spot distribution constraints ───────────────────────────────────
    min_on_demand_replicas = Column(Integer, nullable=False, server_default="0", default=0)
    max_spot_replicas = Column(Integer, nullable=False, server_default="0", default=0)

    # ── v4.6 workload class + eligibility ─────────────────────────────────────
    workload_class = Column(String(20), nullable=False, server_default="stateless", default="stateless")
    spot_eligible = Column(Boolean, nullable=False, server_default="false", default=False)
    total_replicas = Column(Integer, nullable=False, server_default="0", default=0)

    schema_version = Column(String(10), nullable=False, default="4.6")

    # ── Computed CV metrics (populated by workload_cv_task, migration 20260427) ──
    cpu_cv = Column(Float, nullable=True)
    traffic_skew_detected = Column(Boolean, nullable=True)

    # ── Timestamps — always UTC ───────────────────────────────────────────────
    classified_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    cluster = relationship("Cluster", back_populates=None, lazy="select")

    # ── Indexes ───────────────────────────────────────────────────────────────
    __table_args__ = (
        # Uniqueness: one classification record per workload per cluster
        UniqueConstraint(
            "cluster_id", "workload_id",
            name="uq_workload_classification_cluster_workload",
        ),
        # Query patterns: tier-based filtering per cluster
        Index("ix_wc_cluster_tier", "cluster_id", "tier"),
        # Query patterns: confidence state filtering per cluster
        Index("ix_wc_cluster_confidence", "cluster_id", "confidence_state"),
        # Query patterns: spot-eligible lookup
        Index("ix_wc_cluster_spot", "cluster_id", "spot_friendly", "confidence_state"),
        # Query patterns: workload_id lookup without cluster_id
        Index("ix_wc_workload_id", "workload_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<WorkloadClassificationRecord "
            f"cluster_id={self.cluster_id!r} "
            f"workload_id={self.workload_id!r} "
            f"tier={self.tier!r} "
            f"confidence_state={self.confidence_state!r} "
            f"spot_friendly={self.spot_friendly!r}>"
        )
