"""
Cluster Cooldown Model
=====================

Tracks cluster-level switch cooldown to prevent oscillation.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey
from datetime import datetime
from backend.models.base import Base
import uuid


def generate_uuid():
    return str(uuid.uuid4())


class ClusterCooldown(Base):
    __tablename__ = "cluster_cooldowns"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    cluster_id = Column(String(36), ForeignKey("clusters.id"), nullable=False, index=True)
    last_switch_timestamp = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
