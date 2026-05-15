"""
ExecutionOverride — Append-only mid-run field override log (Problems 16, 17, 26).

NodeProvisioner writes here instead of mutating the manifest payload.
EE reads and merges overrides onto manifest entries before each group.

Rules:
- append-only: each attempt inserts a new row (no upsert / update)
- attempt_number increments per (manifest_id, node_name, field)
- read_all() returns the LATEST value per (manifest_id, node_name, field)
- read_history() returns ALL rows for full audit lineage
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from backend.models.base import Base


class ExecutionOverride(Base):
    __tablename__ = "execution_overrides"

    __table_args__ = (
        Index("idx_eo_manifest_node", "manifest_id", "node_name"),
        Index("idx_eo_manifest_id",   "manifest_id"),
    )

    id             = Column(Integer, primary_key=True, autoincrement=True)
    manifest_id    = Column(String(64),  nullable=False, index=True)
    node_name      = Column(String(256), nullable=False)
    field          = Column(String(64),  nullable=False)
    # "instance_type" | future fields

    original_value = Column(Text, nullable=True)
    override_value = Column(Text, nullable=False)
    reason         = Column(String(128), nullable=False)
    # e.g. "pool_failure_retry_attempt_1"

    attempt_number = Column(Integer, nullable=False, default=0)
    # Problem 26: monotonically increasing per (manifest_id, node_name, field).
    # Computed by ExecutionOverrideStore.write() — caller doesn't set this.

    created_at     = Column(DateTime, nullable=False, default=datetime.utcnow)
