"""
Pool Cooldown Model
==================

Tracks pool-level failure cooldown to prevent reuse of problematic pools.
"""

from sqlalchemy import Column, String, DateTime
from datetime import datetime
from backend.models.base import Base
import uuid


def generate_uuid():
    return str(uuid.uuid4())


class PoolCooldown(Base):
    __tablename__ = "pool_cooldowns"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    pool_id = Column(String(100), nullable=False, index=True)  # "instance_type:az"
    last_failure_timestamp = Column(DateTime, nullable=False)
    region = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
