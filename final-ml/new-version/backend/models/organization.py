"""
Organization model - Grouping for accounts and users
"""
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid

class Organization(Base):
    """
    Organization model for grouping multiple accounts
    """
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to users (if any) or just used as a grouping
    # For now, keeping it simple as needed by report_worker.py

    def __repr__(self):
        return f"<Organization(id={self.id}, name={self.name})>"
