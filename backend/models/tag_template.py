"""
Tag Template Model
Stores reusable tag sets for quick application
"""
from sqlalchemy import Column, String, DateTime, Boolean, JSON, Text, Integer, SmallInteger, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class TagTemplate(Base):
    """
    Tag Template model for reusable tag sets.
    Allows users to create and save common tag combinations.
    """
    __tablename__ = "tag_templates"

    # Primary Key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    
    # Organization Link
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Template Definition
    name = Column(String(255), nullable=False)                  # e.g., "Cost Center Standard"
    description = Column(Text, nullable=True)                   # Purpose of this template

    # Legacy columns (kept for BulkTagWizard backward compatibility)
    tags = Column(JSON, nullable=True)                          # {"Owner": "TeamA", "Environment": "Prod"}
    resource_scope = Column(String(50), nullable=True, default='all')

    # New structured columns
    scope = Column(JSON, default=list)                          # ["EC2","EBS","RDS"] — resource types this applies to
    tag_schema = Column(JSON, default=list)                     # [{key, required, type, values, pattern, description, weight}]

    # Compliance
    compliance_score = Column(SmallInteger, default=0)          # 0-100, recomputed by scan job
    resource_count = Column(Integer, default=0)                 # Denormalized count from scan

    # Metadata
    is_default = Column(Boolean, default=False, index=True)     # Default template for quick access
    is_active = Column(Boolean, default=True)
    
    # Audit
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organization = relationship("Organization", back_populates="tag_templates")
    creator = relationship("User")
    
    @property
    def tag_count(self) -> int:
        """Number of tags in this template"""
        return len(self.tags) if self.tags else 0
    
    def get_tag_pairs(self) -> list[dict]:
        """Get tags as list of key-value pairs for display"""
        if not self.tags:
            return []
        return [{"key": k, "value": v} for k, v in self.tags.items()]
    
    def __repr__(self):
        return f"<TagTemplate(name={self.name}, tags={self.tag_count})>"
