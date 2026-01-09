"""
NodeTemplate model - Node configuration templates
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, UniqueConstraint, ARRAY, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class TemplateStrategy(enum.Enum):
    """Template selection strategy"""
    CHEAPEST = "cheapest"
    BALANCED = "balanced"
    PERFORMANCE = "performance"


class DiskType(enum.Enum):
    """EBS disk type"""
    GP3 = "gp3"
    GP2 = "gp2"
    IO1 = "io1"
    IO2 = "io2"


class NodeTemplate(Base):
    """
    Node Template model

    User-defined templates for instance selection
    """
    __tablename__ = "node_templates"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Foreign key to users
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Template configuration
    name = Column(String(255), nullable=False)
    families = Column(ARRAY(String), nullable=False)  # e.g., ['c5', 'c6i', 'm5']
    architecture = Column(String(20), nullable=False, default="x86_64")  # x86_64 or arm64
    strategy = Column(SQLEnum(TemplateStrategy), nullable=False, default=TemplateStrategy.BALANCED)
    disk_type = Column(SQLEnum(DiskType), nullable=False, default=DiskType.GP3)
    disk_size = Column(Integer, nullable=False, default=100)  # GB

    # Default flag
    is_default = Column(String(1), nullable=False, default="N")  # Y/N

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="node_templates")

    # Unique constraint on (user_id, name)
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_template_name"),
    )

    def __repr__(self):
        return f"<NodeTemplate(id={self.id}, name={self.name}, strategy={self.strategy.value}, is_default={self.is_default})>"
