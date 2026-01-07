"""
HibernationSchedule model - Weekly hibernation schedules
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class HibernationSchedule(Base):
    """
    Hibernation Schedule model

    Stores weekly schedule matrix (168 elements - 24 hours x 7 days)
    """
    __tablename__ = "hibernation_schedules"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to clusters (one-to-one)
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Schedule matrix (JSONB)
    # Structure: Array of 168 elements (0 = sleep, 1 = awake)
    # [Mon 00:00, Mon 01:00, ..., Sun 23:00]
    # Example: [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, ...]
    schedule_matrix = Column(JSONB, nullable=False, default=[0] * 168)

    # Timezone
    timezone = Column(String(50), nullable=False, default="UTC")

    # Pre-warm configuration
    prewarm_enabled = Column(String(1), nullable=False, default="N")  # Y/N
    prewarm_minutes = Column(Integer, nullable=False, default=30)  # Minutes before wake time

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="hibernation_schedule")

    def __repr__(self):
        return f"<HibernationSchedule(id={self.id}, cluster_id={self.cluster_id}, timezone={self.timezone})>"
