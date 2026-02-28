"""
Alert History Model (Enterprise Remediation Phase 4)
====================================================

Database model for alert delivery tracking and audit trail.

Tracks:
- Alert delivery attempts across all channels
- Success/failure status per channel
- Retry history with timestamps
- Deduplication tracking
- Rate limiting enforcement

Enterprise Guardrails:
- Immutable audit trail (no updates after creation)
- Deduplication using alert fingerprints
- Rate limiting enforcement via time-windowed queries
- Retry tracking with exponential backoff
"""
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Text, JSON, Index
from sqlalchemy.dialects.postgresql import ENUM
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class AlertStatus(enum.Enum):
    """Alert delivery status."""
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    DEDUPLICATED = "DEDUPLICATED"
    RATE_LIMITED = "RATE_LIMITED"
    RETRYING = "RETRYING"


class AlertHistory(Base):
    """
    Alert History Model.

    Immutable audit trail for alert delivery tracking.
    Used for deduplication, rate limiting, and retry logic.
    """
    __tablename__ = "alert_history"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Alert configuration reference
    alert_config_id = Column(String(36), nullable=False, index=True)
    organization_id = Column(String(36), nullable=False, index=True)
    cluster_id = Column(String(36), nullable=True, index=True)

    # Alert details
    alert_type = Column(String(100), nullable=False, index=True)  # AlertType enum value
    severity = Column(String(50), nullable=False, index=True)  # AlertSeverity enum value
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)

    # Deduplication fingerprint (hash of alert type + cluster + region + key details)
    fingerprint = Column(String(64), nullable=False, index=True)

    # Regional scoping
    region = Column(String(50), nullable=True, index=True)

    # Delivery status
    status = Column(
        ENUM(AlertStatus, name="alert_status_enum"),
        nullable=False,
        default=AlertStatus.PENDING,
        index=True
    )

    # Channel delivery tracking
    channels_attempted = Column(JSON, nullable=False, default=list)  # List of channel names
    channels_succeeded = Column(JSON, nullable=False, default=list)  # Successful deliveries
    channels_failed = Column(JSON, nullable=False, default=list)  # Failed deliveries

    # Channel-specific results
    email_sent = Column(Boolean, nullable=True)
    email_error = Column(Text, nullable=True)
    slack_sent = Column(Boolean, nullable=True)
    slack_error = Column(Text, nullable=True)
    pagerduty_sent = Column(Boolean, nullable=True)
    pagerduty_error = Column(Text, nullable=True)
    pagerduty_incident_key = Column(String(255), nullable=True)
    webhook_sent = Column(Boolean, nullable=True)
    webhook_error = Column(Text, nullable=True)
    webhook_signature = Column(String(128), nullable=True)  # HMAC signature sent

    # Retry tracking
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    next_retry_at = Column(DateTime, nullable=True, index=True)
    last_retry_at = Column(DateTime, nullable=True)

    # Rate limiting tracking
    rate_limit_window_start = Column(DateTime, nullable=True)
    rate_limit_count = Column(Integer, nullable=True)

    # Event metadata
    event_data = Column(JSON, nullable=True)  # Original event data
    context = Column(JSON, nullable=True)  # Additional context

    # Timestamps (immutable after creation)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)  # When all deliveries completed

    # Indexes for performance
    __table_args__ = (
        Index("idx_alert_history_fingerprint_created", "fingerprint", "created_at"),
        Index("idx_alert_history_org_type_created", "organization_id", "alert_type", "created_at"),
        Index("idx_alert_history_region_created", "region", "created_at"),
        Index("idx_alert_history_status_retry", "status", "next_retry_at"),
        Index("idx_alert_history_cluster_type", "cluster_id", "alert_type"),
    )

    def __repr__(self):
        return (
            f"<AlertHistory(type={self.alert_type}, "
            f"status={self.status.value if self.status else None}, "
            f"retry={self.retry_count}/{self.max_retries})>"
        )

    @property
    def is_pending(self) -> bool:
        """Check if alert is pending delivery."""
        return self.status == AlertStatus.PENDING

    @property
    def is_sent(self) -> bool:
        """Check if alert was successfully sent."""
        return self.status == AlertStatus.SENT

    @property
    def is_failed(self) -> bool:
        """Check if alert delivery failed."""
        return self.status == AlertStatus.FAILED

    @property
    def can_retry(self) -> bool:
        """Check if alert can be retried."""
        return (
            self.status in [AlertStatus.FAILED, AlertStatus.RETRYING]
            and self.retry_count < self.max_retries
        )

    @property
    def is_deduplicated(self) -> bool:
        """Check if alert was deduplicated."""
        return self.status == AlertStatus.DEDUPLICATED

    @property
    def is_rate_limited(self) -> bool:
        """Check if alert was rate limited."""
        return self.status == AlertStatus.RATE_LIMITED

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "alert_config_id": self.alert_config_id,
            "organization_id": self.organization_id,
            "cluster_id": self.cluster_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "fingerprint": self.fingerprint,
            "region": self.region,
            "status": self.status.value if self.status else None,
            "channels_attempted": self.channels_attempted or [],
            "channels_succeeded": self.channels_succeeded or [],
            "channels_failed": self.channels_failed or [],
            "email_sent": self.email_sent,
            "email_error": self.email_error,
            "slack_sent": self.slack_sent,
            "slack_error": self.slack_error,
            "pagerduty_sent": self.pagerduty_sent,
            "pagerduty_error": self.pagerduty_error,
            "pagerduty_incident_key": self.pagerduty_incident_key,
            "webhook_sent": self.webhook_sent,
            "webhook_error": self.webhook_error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "last_retry_at": self.last_retry_at.isoformat() if self.last_retry_at else None,
            "event_data": self.event_data,
            "context": self.context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
