"""
Substitute State Model
=====================

Tracks substitute node state for safety fallback management.
State machine: IDLE → PREWARMING → READY → ACTIVE → RELEASING → IDLE
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Float
from datetime import datetime
from backend.models.base import Base
import uuid


def generate_uuid():
    return str(uuid.uuid4())


class SubstituteState(Base):
    __tablename__ = "substitute_states"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    cluster_id = Column(String(36), ForeignKey("clusters.id"), nullable=False, index=True)
    substitute_type = Column(String(20), nullable=False)  # "spot" or "on-demand"
    instance_type = Column(String(50), nullable=True)
    active_since = Column(DateTime, nullable=False)
    cost_impact = Column(Float, nullable=True)  # Cost delta vs original
    status = Column(String(20), default="active")  # active, releasing, released
    created_at = Column(DateTime, default=datetime.utcnow)
