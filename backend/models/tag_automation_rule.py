"""
Tag Automation Rule Model
Defines rules for automated actions on non-compliant resources
"""
from sqlalchemy import Column, String, DateTime, Boolean, SmallInteger, JSON, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class TagAutomationRule(Base):
    __tablename__ = "tag_automation_rules"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    organization_id = Column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    name = Column(String(255), nullable=False)

    # Trigger expression: 'score < 20' | 'score == 0' | 'missing:owner' | 'unauthorized'
    trigger_expr = Column(String(100), nullable=False)

    # Resource types this rule applies to: ["EC2","RDS"] etc.
    resource_types = Column(JSON, nullable=False, default=list)

    # Grace period in days before action executes
    grace_days = Column(SmallInteger, nullable=False, default=30)

    # Action: 'notify' | 'flag' | 'stop' | 'auto_tag' | 'delete'
    action = Column(String(20), nullable=False)

    # Notification channels: ["email","slack","pagerduty","webhook","jira"]
    notification_channels = Column(JSON, nullable=False, default=list)

    # Safety conditions (AND logic): ["not_system_managed","older_than_30d","has_cost","not_prod",...]
    safety_conditions = Column(JSON, nullable=False, default=list)

    enabled = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime, nullable=True)

    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="tag_automation_rules")
    creator = relationship("User")

    def __repr__(self):
        return f"<TagAutomationRule(name={self.name}, action={self.action}, enabled={self.enabled})>"
