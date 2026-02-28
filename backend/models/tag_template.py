"""
Tag Template Model

Database model for tag templates (reusable tag configurations).
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class TagTemplate(Base):
    """
    Tag Template model.

    Defines reusable tag configurations for resources.
    """
    __tablename__ = "tag_templates"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign keys
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # Template details
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Tag configuration
    tags = Column(JSON, nullable=False, default=dict)  # Tag key-value pairs

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="tag_templates")

    def __repr__(self):
        return f"<TagTemplate(id={self.id}, name={self.name}, org={self.organization_id})>"
