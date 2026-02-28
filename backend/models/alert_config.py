"""
Alert Configuration Model (Enterprise Remediation Phase 4)
===========================================================

Database model for multi-channel alert configuration.

Supports:
- Email, Slack, PagerDuty, and Webhook notifications
- Region-aware alerting for regional events
- Configurable alert rules and thresholds
- Channel-specific configuration (webhook URLs, emails, etc.)

Enterprise Guardrails:
- HMAC-SHA256 webhook signing for security
- Deduplication window (5 minutes)
- Rate limiting (max 10 alerts/minute per service)
- Retry logic with exponential backoff
"""
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Text, JSON, Index
from sqlalchemy.dialects.postgresql import ENUM
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class AlertChannel(enum.Enum):
    """Alert notification channels."""
    EMAIL = "EMAIL"
    SLACK = "SLACK"
    PAGERDUTY = "PAGERDUTY"
    WEBHOOK = "WEBHOOK"


class AlertSeverity(enum.Enum):
    """Alert severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AlertType(enum.Enum):
    """Alert event types."""
    SPOT_INTERRUPTION = "SPOT_INTERRUPTION"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    CIRCUIT_BREAKER_CLOSED = "CIRCUIT_BREAKER_CLOSED"
    PRICING_STALE = "PRICING_STALE"
    VOLATILITY_HIGH = "VOLATILITY_HIGH"
    JIT_LIMIT_EXCEEDED = "JIT_LIMIT_EXCEEDED"
    PDB_BLOCKED = "PDB_BLOCKED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    NODE_DRAIN_FAILED = "NODE_DRAIN_FAILED"
    KARPENTER_PROVISIONING_TIMEOUT = "KARPENTER_PROVISIONING_TIMEOUT"
    WEBHOOK_DELIVERY_FAILED = "WEBHOOK_DELIVERY_FAILED"
    CLUSTER_HEALTH_DEGRADED = "CLUSTER_HEALTH_DEGRADED"


class AlertConfig(Base):
    """
    Alert Configuration Model.

    Defines alert rules and notification channels for various events.
    Supports region-aware alerting and multi-channel delivery.
    """
    __tablename__ = "alert_config"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Organization scoping
    organization_id = Column(String(36), nullable=False, index=True)
    cluster_id = Column(String(36), nullable=True, index=True)  # Null = org-wide

    # Alert configuration
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    alert_type = Column(
        ENUM(AlertType, name="alert_type_enum"),
        nullable=False,
        index=True
    )
    severity = Column(
        ENUM(AlertSeverity, name="alert_severity_enum"),
        nullable=False,
        default=AlertSeverity.WARNING,
        index=True
    )

    # Notification channels (can have multiple)
    channels = Column(JSON, nullable=False, default=list)  # List of AlertChannel values

    # Channel-specific configuration
    email_recipients = Column(JSON, nullable=True)  # List of email addresses
    slack_webhook_url = Column(String(500), nullable=True)
    slack_channel = Column(String(100), nullable=True)
    pagerduty_integration_key = Column(String(255), nullable=True)
    webhook_url = Column(String(500), nullable=True)
    webhook_hmac_secret = Column(String(255), nullable=True)  # For HMAC signing

    # Alert rules and thresholds
    threshold_value = Column(Integer, nullable=True)  # E.g., number of interruptions
    threshold_window_minutes = Column(Integer, nullable=True, default=5)  # Evaluation window
    region_scope = Column(String(50), nullable=True)  # E.g., "us-east-1" or null for global

    # Deduplication and rate limiting
    dedup_window_minutes = Column(Integer, nullable=False, default=5)
    rate_limit_per_minute = Column(Integer, nullable=False, default=10)

    # Retry configuration
    max_retries = Column(Integer, nullable=False, default=3)
    retry_backoff_seconds = Column(Integer, nullable=False, default=60)  # Base backoff

    # Status
    enabled = Column(Boolean, nullable=False, default=True, index=True)

    # Custom metadata
    alert_metadata = Column(JSON, nullable=True)  # Additional custom fields (renamed to avoid SQLAlchemy reserved name)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(36), nullable=True)  # User ID
    updated_by = Column(String(36), nullable=True)  # User ID

    # Indexes
    __table_args__ = (
        Index("idx_alert_config_org_type", "organization_id", "alert_type"),
        Index("idx_alert_config_cluster_enabled", "cluster_id", "enabled"),
        Index("idx_alert_config_severity", "severity", "enabled"),
    )

    def __repr__(self):
        return (
            f"<AlertConfig(name={self.name}, "
            f"type={self.alert_type.value if self.alert_type else None}, "
            f"severity={self.severity.value if self.severity else None})>"
        )

    @property
    def has_email_channel(self) -> bool:
        """Check if email notifications are enabled."""
        return AlertChannel.EMAIL.value in (self.channels or [])

    @property
    def has_slack_channel(self) -> bool:
        """Check if Slack notifications are enabled."""
        return AlertChannel.SLACK.value in (self.channels or [])

    @property
    def has_pagerduty_channel(self) -> bool:
        """Check if PagerDuty notifications are enabled."""
        return AlertChannel.PAGERDUTY.value in (self.channels or [])

    @property
    def has_webhook_channel(self) -> bool:
        """Check if webhook notifications are enabled."""
        return AlertChannel.WEBHOOK.value in (self.channels or [])

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "cluster_id": self.cluster_id,
            "name": self.name,
            "description": self.description,
            "alert_type": self.alert_type.value if self.alert_type else None,
            "severity": self.severity.value if self.severity else None,
            "channels": self.channels or [],
            "email_recipients": self.email_recipients,
            "slack_webhook_url": self.slack_webhook_url,
            "slack_channel": self.slack_channel,
            "pagerduty_integration_key": self.pagerduty_integration_key,
            "webhook_url": self.webhook_url,
            "threshold_value": self.threshold_value,
            "threshold_window_minutes": self.threshold_window_minutes,
            "region_scope": self.region_scope,
            "dedup_window_minutes": self.dedup_window_minutes,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "max_retries": self.max_retries,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "enabled": self.enabled,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }
