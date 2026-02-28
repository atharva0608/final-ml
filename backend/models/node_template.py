from sqlalchemy import Column, String, Integer, Float, Boolean, ForeignKey, DateTime, Enum, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid

class TemplateScope(str, enum.Enum):
    GLOBAL = "GLOBAL"
    CLUSTER = "CLUSTER"

class TemplateStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"

class WorkloadScope(str, enum.Enum):
    STATELESS_ONLY = "STATELESS_ONLY"
    MIXED = "MIXED"

class OptimizationPolicy(str, enum.Enum):
    COST_FIRST = "COST_FIRST"
    NO_DOWNTIME_FIRST = "NO_DOWNTIME_FIRST"
    BALANCED = "BALANCED"

class SubstituteStrategy(str, enum.Enum):
    PREWARMED = "PREWARMED"
    ON_DEMAND = "ON_DEMAND"
    DISABLED = "DISABLED"

class NodeTemplate(Base):
    """
    Global or cluster-scoped template identity.
    """
    __tablename__ = "node_templates"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), nullable=False)
    scope = Column(Enum(TemplateScope), default=TemplateScope.GLOBAL, nullable=False)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relations
    versions = relationship("NodeTemplateVersion", back_populates="template", cascade="all, delete-orphan")
    mappings = relationship("ClusterTemplateMapping", back_populates="template", cascade="all, delete-orphan")

class NodeTemplateVersion(Base):
    """
    Immutable version of a template constraint envelope.
    """
    __tablename__ = "node_template_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    template_id = Column(String(36), ForeignKey("node_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, default=1, nullable=False)
    status = Column(Enum(TemplateStatus), default=TemplateStatus.DRAFT, nullable=False)
    
    constraints_json = Column(JSON, nullable=False)
    
    # Relations
    template = relationship("NodeTemplate", back_populates="versions")
    mappings = relationship("ClusterTemplateMapping", back_populates="version")
    
class ClusterTemplateMapping(Base):
    """
    Mapping assigning exactly one active default template version to a cluster.
    """
    __tablename__ = "cluster_template_mappings"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(String(36), ForeignKey("node_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("node_template_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    is_default = Column(Boolean, default=True, nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('cluster_id', 'is_default', name='uq_cluster_default_template'),
    )

    # Relations
    cluster = relationship("Cluster", back_populates="template_mappings")
    template = relationship("NodeTemplate", back_populates="mappings")
    version = relationship("NodeTemplateVersion", back_populates="mappings")
