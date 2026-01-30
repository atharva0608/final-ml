
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base

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
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="hibernation_schedule")
