"""
ExecutionManifest — DB-primary manifest record (Plan P2/Problem 2/16).

Replaces the Redis-only ManifestStore (TTL 120 s) as the primary store.
Redis is kept as a cache (heartbeat + fast-read) but the DB row is the
source of truth that survives Redis evictions and restarts.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from backend.models.base import Base


class ExecutionManifest(Base):
    __tablename__ = "execution_manifests"

    __table_args__ = (
        Index("idx_em_cluster_status", "cluster_id", "status"),
        Index("idx_em_status", "status"),
    )

    manifest_id   = Column(String(64),  primary_key=True)
    cluster_id    = Column(String(36),  nullable=False, index=True)
    status        = Column(String(20),  nullable=False, default="READY")
    # READY → EXECUTING → COMPLETED | FAILED | EXPIRED

    payload       = Column(JSONB, nullable=False)
    # Full manifest dict as produced by DistributionEngine.build().
    # IMMUTABLE after first write — never patched in-place.
    # Mid-run overrides go to ExecutionOverride rows, not here.

    created_at    = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at    = Column(DateTime, nullable=False, default=datetime.utcnow,
                           onupdate=datetime.utcnow)
    expires_at    = Column(DateTime, nullable=True)
    # TTL sentinel used by TTLMonitor.  NULL = never expires (manual only).

    last_heartbeat = Column(DateTime, nullable=True)
    # Updated by EE every time it completes a group.  TTLMonitor uses
    # NOW() - last_heartbeat > 60 s as the stale signal.

    error_message  = Column(Text, nullable=True)
    resume_index   = Column(Integer, nullable=False, default=0)
    # Index of the next group to execute on crash-resume.
