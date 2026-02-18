
import enum
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base
from backend.models.hibernation_schedule_clusters import hibernation_schedule_clusters


class HibernationStrategy(str, enum.Enum):
    NAMESPACE_SLEEP = "NAMESPACE_SLEEP"
    NUCLEAR = "NUCLEAR"
    SNAPSHOT_RESTORE = "SNAPSHOT_RESTORE"


class ScheduleType(str, enum.Enum):
    WEEKLY = "WEEKLY"          # 168 hours (7 days × 24 hours)
    DAILY = "DAILY"            # 31 days (on/off per day)
    MONTHLY = "MONTHLY"        # 744 hours (31 days × 24 hours)
    HYBRID = "HYBRID"          # Weekly pattern + date overrides


class HibernationSchedule(Base):
    __tablename__ = "hibernation_schedules"

    id = Column(String, primary_key=True)
    # cluster_id removed in favor of Many-to-Many relationship
    
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    # Schedule type: WEEKLY (168h), DAILY (31d), MONTHLY (744h), HYBRID (weekly + overrides)
    schedule_type = Column(String(20), default=ScheduleType.WEEKLY.value)

    # Schedule matrix - variable length based on type:
    # WEEKLY: 168 chars, DAILY: 31 chars, MONTHLY: 744 chars
    schedule_matrix = Column(Text, nullable=False)

    # Date-specific overrides for HYBRID mode: {"2026-12-25": 0, "2026-12-31": 0}
    date_overrides = Column(JSON, default={})

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
    clusters = relationship("Cluster", secondary=hibernation_schedule_clusters, backref="hibernation_schedules")
