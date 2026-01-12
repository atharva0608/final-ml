"""
System Configuration model - Stores global system settings like Safe Mode
"""
from sqlalchemy import Column, String, DateTime
from datetime import datetime
from backend.models.base import Base, generate_uuid


class SystemConfig(Base):
    """
    System configuration key-value store
    Used for global settings like Safe Mode, agent version, platform credentials, etc.
    """
    __tablename__ = "system_configs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(String(500), nullable=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SystemConfig {self.key}={self.value}>"
