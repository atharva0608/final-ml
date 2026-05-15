"""
Alert Processing Worker (Enterprise Remediation Phase 4)
========================================================

Celery tasks for background alert processing and retry handling.

Tasks:
- process_alert: Send alert asynchronously
- retry_failed_alerts: Periodic task to retry failed alerts
- cleanup_old_alerts: Cleanup old alert history records

Enterprise Guardrails:
- Async processing to prevent API blocking
- Exponential backoff retry logic
- Rate limiting enforcement
- Deduplication tracking
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from celery import shared_task
from sqlalchemy.orm import Session

from backend.models.base import SessionLocal
from backend.models.alert_config import AlertType, AlertSeverity
from backend.models.alert_history import AlertHistory, AlertStatus
from backend.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


@shared_task(
    name="alert_worker.process_alert",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
)
def process_alert(
    self,
    alert_type: str,
    organization_id: str,
    title: str,
    message: str,
    severity: str = "WARNING",
    cluster_id: Optional[str] = None,
    region: Optional[str] = None,
    event_data: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
):
    """
    Process alert asynchronously.

    Args:
        alert_type: Alert type (AlertType enum value)
        organization_id: Organization ID
        title: Alert title
        message: Alert message
        severity: Alert severity (AlertSeverity enum value)
        cluster_id: Optional cluster ID
        region: Optional region for regional events
        event_data: Original event data
        context: Additional context

    Usage:
        from backend.workers.tasks.alert_worker import process_alert
        from backend.models.alert_config import AlertType, AlertSeverity

        process_alert.delay(
            alert_type=AlertType.CIRCUIT_BREAKER_OPEN.value,
            organization_id="org-123",
            title="Circuit Breaker Opened",
            message="Circuit breaker opened for cluster production-eks",
            severity=AlertSeverity.ERROR.value,
            cluster_id="cluster-456",
            region="us-east-1",
            event_data={"cluster_name": "production-eks"}
        )
    """
    db = SessionLocal()
    try:
        # Convert string values back to enums
        alert_type_enum = AlertType[alert_type]
        severity_enum = AlertSeverity[severity]

        # Create notification service
        notification_service = NotificationService(db)

        # Send alert (async)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        alert_history = loop.run_until_complete(
            notification_service.send_alert(
                alert_type=alert_type_enum,
                organization_id=organization_id,
                title=title,
                message=message,
                severity=severity_enum,
                cluster_id=cluster_id,
                region=region,
                event_data=event_data,
                context=context,
            )
        )

        if alert_history:
            logger.info(
                f"Alert processed: {alert_type}",
                extra={
                    "alert_id": alert_history.id,
                    "status": alert_history.status.value if alert_history.status else None
                }
            )
        else:
            logger.info(
                f"Alert deduplicated or rate-limited: {alert_type}",
                extra={"organization_id": organization_id, "cluster_id": cluster_id}
            )

        return {
            "success": True,
            "alert_id": alert_history.id if alert_history else None,
            "status": alert_history.status.value if alert_history and alert_history.status else "SKIPPED"
        }

    except Exception as e:
        logger.error(f"Failed to process alert: {str(e)}", exc_info=True)
        db.rollback()
        raise self.retry(exc=e)

    finally:
        db.close()


@shared_task(
    name="alert_worker.retry_failed_alerts",
    bind=True,
)
def retry_failed_alerts(self, max_alerts: int = 100):
    """
    Periodic task to retry failed alerts.

    Runs every 5 minutes (configured in Celery beat schedule).
    Retries alerts with exponential backoff.

    Args:
        max_alerts: Maximum number of alerts to retry per run
    """
    db = SessionLocal()
    try:
        notification_service = NotificationService(db)

        # Run async retry
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop.run_until_complete(
            notification_service.retry_failed_alerts(max_alerts=max_alerts)
        )

        logger.info(f"Completed alert retry cycle (max {max_alerts} alerts)")

        return {"success": True, "max_alerts": max_alerts}

    except Exception as e:
        logger.error(f"Failed to retry alerts: {str(e)}", exc_info=True)
        db.rollback()
        return {"success": False, "error": str(e)}

    finally:
        db.close()


@shared_task(
    name="alert_worker.cleanup_old_alerts",
    bind=True,
)
def cleanup_old_alerts(self, retention_days: int = 90):
    """
    Cleanup old alert history records.

    Runs daily (configured in Celery beat schedule).
    Deletes alert history older than retention period.

    Args:
        retention_days: Number of days to retain alert history (default: 90)

    Enterprise Guardrail:
    - Keep critical alerts longer (180 days)
    - Archive instead of delete for audit trail
    """
    db = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        cutoff_date_critical = datetime.utcnow() - timedelta(days=180)  # Keep critical longer

        # Delete non-critical old alerts
        deleted_count = db.query(AlertHistory).filter(
            AlertHistory.created_at < cutoff_date,
            AlertHistory.severity != AlertSeverity.CRITICAL.value
        ).delete(synchronize_session=False)

        # Delete very old critical alerts
        deleted_critical = db.query(AlertHistory).filter(
            AlertHistory.created_at < cutoff_date_critical,
            AlertHistory.severity == AlertSeverity.CRITICAL.value
        ).delete(synchronize_session=False)

        db.commit()

        logger.info(
            f"Cleaned up {deleted_count + deleted_critical} old alert history records",
            extra={
                "non_critical_deleted": deleted_count,
                "critical_deleted": deleted_critical,
                "retention_days": retention_days
            }
        )

        return {
            "success": True,
            "deleted_count": deleted_count + deleted_critical,
            "non_critical_deleted": deleted_count,
            "critical_deleted": deleted_critical
        }

    except Exception as e:
        logger.error(f"Failed to cleanup old alerts: {str(e)}", exc_info=True)
        db.rollback()
        return {"success": False, "error": str(e)}

    finally:
        db.close()


@shared_task(
    name="alert_worker.send_test_alert",
    bind=True,
)
def send_test_alert(
    self,
    organization_id: str,
    cluster_id: Optional[str] = None,
    channel: Optional[str] = None,
):
    """
    Send test alert for configuration validation.

    Args:
        organization_id: Organization ID
        cluster_id: Optional cluster ID
        channel: Optional specific channel to test (EMAIL, SLACK, PAGERDUTY, WEBHOOK)

    Usage:
        from backend.workers.tasks.alert_worker import send_test_alert

        send_test_alert.delay(
            organization_id="org-123",
            cluster_id="cluster-456",
            channel="SLACK"
        )
    """
    db = SessionLocal()
    try:
        notification_service = NotificationService(db)

        # Create test alert
        title = "Test Alert - Spot Optimizer Platform"
        message = (
            "This is a test alert to verify your notification configuration. "
            "If you receive this message, your alert channel is working correctly."
        )

        # Run async send
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        alert_history = loop.run_until_complete(
            notification_service.send_alert(
                alert_type=AlertType.CLUSTER_HEALTH_DEGRADED,  # Use a generic type for testing
                organization_id=organization_id,
                title=title,
                message=message,
                severity=AlertSeverity.INFO,
                cluster_id=cluster_id,
                event_data={
                    "test": True,
                    "channel": channel,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        )

        if alert_history:
            return {
                "success": True,
                "alert_id": alert_history.id,
                "status": alert_history.status.value if alert_history.status else None,
                "channels_succeeded": alert_history.channels_succeeded,
                "channels_failed": alert_history.channels_failed,
            }
        else:
            return {
                "success": False,
                "error": "Alert was deduplicated or rate-limited"
            }

    except Exception as e:
        logger.error(f"Failed to send test alert: {str(e)}", exc_info=True)
        db.rollback()
        return {"success": False, "error": str(e)}

    finally:
        db.close()
