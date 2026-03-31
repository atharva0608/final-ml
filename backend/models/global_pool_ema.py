"""
Global Pool EMA Model
=====================

Tracks per-pool exponential moving average (EMA) of interruption rates
across all clusters. One entry per pool_key = 'instance_type:az'.

EMA state is dual-stored in Redis (hot cache, 90-day TTL) and Postgres
(durable). On Redis miss the service falls back to DB and restores Redis.
"""

from sqlalchemy import Column, String, Integer, Numeric, DateTime, Index
from datetime import datetime
from backend.models.base import Base
import uuid


def generate_uuid():
    return str(uuid.uuid4())


class GlobalPoolEMA(Base):
    __tablename__ = "global_pool_ema"
    __table_args__ = (
        Index("idx_global_pool_ema_region", "region"),
        Index("idx_global_pool_ema_last_event", "last_event"),
    )

    pool_key = Column(String(100), primary_key=True)          # 'instance_type:az'
    instance_type = Column(String(50), nullable=False)
    az = Column(String(50), nullable=False)
    region = Column(String(50), nullable=False)
    count = Column(Integer, nullable=False, default=0)         # effective event count (decayed)
    rate = Column(Numeric(5, 2), nullable=False, default=0.0)  # EMA interruption rate (0-25%)
    peak_rate = Column(Numeric(5, 2), nullable=False, default=0.0)
    sample_clusters = Column(Integer, nullable=False, default=0)
    last_event = Column(DateTime, nullable=True)               # last interruption (null if none)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class GlobalPoolEMAHistory(Base):
    __tablename__ = "global_pool_ema_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pool_key = Column(String(100), nullable=False, index=True)
    rate = Column(Numeric(5, 2))
    count = Column(Integer)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
