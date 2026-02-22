"""
Tag Compliance Score Model
One row per resource per scan — tracks compliance score and status
"""
from sqlalchemy import Column, String, DateTime, SmallInteger, Integer, Numeric, Index, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class TagComplianceScore(Base):
    __tablename__ = "tag_compliance_scores"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    organization_id = Column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False
    )

    # Resource identification
    resource_id = Column(String(100), nullable=False)       # AWS resource ID e.g. i-0abc123
    resource_name = Column(String(255), nullable=True)
    resource_type = Column(String(50), nullable=False)      # 'EC2'|'EBS'|'RDS' etc.

    # Extracted tag values for filtering
    environment = Column(String(50), nullable=True)         # From 'environment' tag
    team = Column(String(100), nullable=True)               # From 'team' tag

    # Compliance data
    score = Column(SmallInteger, nullable=False)             # 0-100
    # Status: 'compliant'|'passing'|'review'|'critical'|'deletion'
    status = Column(String(20), nullable=False)
    tags_present = Column(Integer, nullable=False, default=0)
    monthly_cost = Column(Numeric(10, 2), nullable=False, default=0)

    # Automation
    grace_deadline = Column(DateTime, nullable=True)         # Set when automation rule fires

    scanned_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="tag_compliance_scores")

    __table_args__ = (
        Index("ix_tag_compliance_org_scanned", "organization_id", "scanned_at"),
        Index("ix_tag_compliance_org_type", "organization_id", "resource_type"),
        Index("ix_tag_compliance_org_status", "organization_id", "status"),
        Index("ix_tag_compliance_org_resource", "organization_id", "resource_id"),
    )

    def __repr__(self):
        return f"<TagComplianceScore(resource={self.resource_id}, score={self.score}, status={self.status})>"
