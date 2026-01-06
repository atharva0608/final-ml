"""
Cluster Event Model
Tracks events related to cluster lifecycle and scaling activities
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

from backend.models.base import Base

class ClusterEvent(Base):
    __tablename__ = "cluster_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id = Column(UUID(as_uuid=True), ForeignKey("clusters.id"), nullable=False)
    event_type = Column(String, nullable=False)
    source = Column(String, nullable=False)  # e.g., "aws", "k8s", "spot_optimizer"
    severity = Column(String, default="INFO")
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    cluster = relationship("Cluster", backref="events")
