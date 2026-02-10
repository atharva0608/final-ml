
import enum
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base


class HibernationStrategy(str, enum.Enum):
    NAMESPACE_SLEEP = "NAMESPACE_SLEEP"
    NUCLEAR = "NUCLEAR"
    SNAPSHOT_RESTORE = "SNAPSHOT_RESTORE"


class HibernationSchedule(Base):
    __tablename__ = "hibernation_schedules"

    id = Column(String, primary_key=True)
    cluster_id = Column(String, ForeignKey("clusters.id"), unique=True, nullable=False)

    # 168 chars string (7 days * 24 hours), '1'=On, '0'=Off
    schedule_matrix = Column(String(168), nullable=False)

    timezone = Column(String, default="UTC")

    pre_warm_minutes = Column(Integer, default=30)

    # "Y" or "N" as per service implementation
    is_active = Column(String(1), default="Y")

    # Strategy: NAMESPACE_SLEEP, NUCLEAR, SNAPSHOT_RESTORE
    strategy = Column(String(20), default=HibernationStrategy.NAMESPACE_SLEEP.value)

    # Saved state: ASG capacities, HPA configs, replica counts before sleep
    saved_state = Column(JSON, default={})

    # AZ affinity: volume AZ mappings for snapshot restore
    az_affinity = Column(JSON, default={})

    # Last action tracking
    last_action = Column(String(20), nullable=True)  # SLEEP/WAKE/PREWARM/ERROR
    last_action_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="hibernation_schedule")
