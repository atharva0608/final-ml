"""
Per-pool adaptive interruption ledger — Postgres backup table.

Primary store is Redis (global_pool_ledger:{pool_key}).  C1: key is global —
no cluster_id — so all tenants share the same risk signal for a given pool.
This table is written
periodically by the hourly decay task so data survives Redis restarts.

  pool_key          — "instance_type:az", e.g. "m5.xlarge:us-east-1a"
  node_hours_observed — running total of node-hours seen for this pool
  interruption_count  — total interruptions ever recorded
  raw_itn_score       — decayed score in [0, 1]; increases on interruption,
                        asymptotically decays toward 0 over STABILITY_HALF_LIFE
  confidence          — 1 - exp(-node_hours_observed / TAU); rises as we
                        accumulate evidence and falls toward 0 when data is sparse
  last_interruption_ts — UTC timestamp of the most recent interruption (NULL if none)
  last_updated        — UTC timestamp of the last write
  C2 severity breakdown (all default 0, added in 20260410_adaptive_itn_severity.py):
  itn_warning_count        — 2-min AWS ITN notice count
  actual_termination_count — node actually killed by AWS count
  rebalance_notice_count   — AWS rebalance recommendation count
  peak_simultaneous_itn    — max concurrent ITNs observed at one moment
"""

from sqlalchemy import Column, String, Float, Integer, DateTime, Index, func

from backend.models.base import Base


class AdaptiveItnLedger(Base):
    __tablename__ = "adaptive_itn_ledger"

    pool_key = Column(String(200), primary_key=True, nullable=False)
    node_hours_observed = Column(Float, nullable=False, default=0.0)
    interruption_count = Column(Integer, nullable=False, default=0)
    # C2: severity breakdown counters
    itn_warning_count = Column(Integer, nullable=False, default=0)
    actual_termination_count = Column(Integer, nullable=False, default=0)
    rebalance_notice_count = Column(Integer, nullable=False, default=0)
    peak_simultaneous_itn = Column(Integer, nullable=False, default=0)
    raw_itn_score = Column(Float, nullable=False, default=0.0)
    confidence = Column(Float, nullable=False, default=0.0)
    last_interruption_ts = Column(DateTime, nullable=True)
    last_updated = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_adaptive_itn_ledger_pool_key", "pool_key"),
        Index("ix_adaptive_itn_ledger_last_updated", "last_updated"),
    )
