"""
Tag Automation Log Model
Audit trail for automation rule executions
"""
from sqlalchemy import Column, String, DateTime, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class TagAutomationLog(Base):
    __tablename__ = "tag_automation_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    organization_id = Column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    rule_id = Column(
        String(36), ForeignKey("tag_automation_rules.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    resource_id = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=False)

    # Action taken: matches rule.action
    action_taken = Column(String(20), nullable=False)

    # Human-readable reason e.g. "Score 8 — below threshold of 60"
    reason = Column(Text, nullable=False)

    monthly_cost = Column(Numeric(10, 2), nullable=True)

    # Outcome: 'success'|'failed'|'skipped'|'pending_approval'
    outcome = Column(String(20), nullable=False, default="success")
    error_message = Column(Text, nullable=True)

    executed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="tag_automation_logs")
    rule = relationship("TagAutomationRule")

    def __repr__(self):
        return f"<TagAutomationLog(resource={self.resource_id}, action={self.action_taken}, outcome={self.outcome})>"
