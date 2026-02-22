"""
Tag Scoring Configuration Model
One row per organization — defines how compliance scores are calculated
"""
from sqlalchemy import Column, String, DateTime, SmallInteger, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class TagScoringConfig(Base):
    __tablename__ = "tag_scoring_configs"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    organization_id = Column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
    )

    # Scoring mode: 'weighted' | 'all' | 'custom'
    mode = Column(String(20), nullable=False, default="weighted")

    # Minimum passing score (0-100), used when mode='weighted'
    threshold = Column(SmallInteger, nullable=False, default=60)

    # Array of required key strings, used when mode='custom'
    required_keys = Column(JSON, nullable=False, default=list)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="tag_scoring_config")

    def __repr__(self):
        return f"<TagScoringConfig(org={self.organization_id}, mode={self.mode}, threshold={self.threshold})>"
