"""
Pod Metrics Cleanup Worker - Maintains 7-day rolling buffer

Deletes pod metrics older than retention period to prevent database bloat.

Default retention: 7 days (168 hours * 12 samples/hour = 2,016 data points per pod)
Runs: Daily at 2 AM UTC
"""
from celery import Task
from datetime import datetime, timedelta
from typing import Dict, Any
import logging

from backend.workers.app import app
from backend.models.base import get_db
from backend.models.pod_metric import PodMetric

logger = logging.getLogger(__name__)


@app.task(bind=True, name="workers.pod_metrics.cleanup_old_metrics")
def cleanup_old_pod_metrics(self: Task, retention_days: int = 7) -> Dict[str, Any]:
    """
    Cleanup pod metrics older than retention period.

    Args:
        retention_days: Number of days to retain metrics (default 7)

    Returns:
        Dict with cleanup statistics
    """
    logger.info(f"[PodMetrics] Starting cleanup (retention: {retention_days} days)")

    db = next(get_db())

    try:
        cutoff_time = datetime.utcnow() - timedelta(days=retention_days)

        # Delete old metrics
        deleted_count = db.query(PodMetric).filter(
            PodMetric.timestamp < cutoff_time
        ).delete()

        db.commit()

        logger.info(f"[PodMetrics] Cleanup complete: deleted {deleted_count} metrics older than {retention_days} days")

        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "deleted_count": deleted_count,
            "cutoff_time": cutoff_time.isoformat(),
            "retention_days": retention_days
        }

    except Exception as e:
        logger.error(f"[PodMetrics] Cleanup failed: {e}")
        db.rollback()
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

    finally:
        db.close()
