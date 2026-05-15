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

import os
from backend.workers.app import app
from backend.models.base import get_db
from backend.models.pod_metric import PodMetric
from backend.models.hpa_status_snapshots import HpaStatusSnapshot

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

        # Delete old pod metrics
        deleted_count = db.query(PodMetric).filter(
            PodMetric.timestamp < cutoff_time
        ).delete()

        # T-13: Delete HPA status snapshots older than 30 days
        hpa_cutoff = datetime.utcnow() - timedelta(days=30)
        deleted_hpa_snapshots = db.query(HpaStatusSnapshot).filter(
            HpaStatusSnapshot.snapshot_at < hpa_cutoff
        ).delete()

        # P-22: dry-run gate
        if os.getenv("CLEANUP_DRY_RUN", "false").lower() == "true":
            db.rollback()
            logger.info("[PodMetrics] DRY_RUN mode — no rows deleted")
            return {
                "status": "dry_run",
                "timestamp": datetime.utcnow().isoformat(),
                "deleted_count": 0,
                "deleted_hpa_snapshots": 0,
                "deleted_node_metadata": 0,
                "deleted_karpenter_node_claims": 0,
                "cutoff_time": cutoff_time.isoformat(),
                "retention_days": retention_days,
            }

        # P-22: delete karpenter_node_claims for nodes no longer in node_metadata (2h grace)
        from sqlalchemy import text
        deleted_knc = db.execute(text("""
            DELETE FROM karpenter_node_claims knc
            WHERE NOT EXISTS (
                SELECT 1 FROM node_metadata nm
                WHERE nm.cluster_id = knc.cluster_id AND nm.node_name = knc.node_name
            )
            AND knc.updated_at < NOW() - INTERVAL '2 hours'
        """)).rowcount

        # P-22: delete node_metadata rows not updated in last 10 minutes
        deleted_nm = db.execute(text("""
            DELETE FROM node_metadata
            WHERE updated_at < NOW() - INTERVAL '10 minutes'
        """)).rowcount

        db.commit()

        logger.info(
            f"[PodMetrics] Cleanup complete: deleted {deleted_count} pod metrics older than {retention_days} days; "
            f"deleted {deleted_hpa_snapshots} HPA snapshots older than 30 days; "
            f"deleted {deleted_nm} stale node_metadata rows; "
            f"deleted {deleted_knc} orphaned karpenter_node_claims rows"
        )

        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "deleted_count": deleted_count,
            "deleted_hpa_snapshots": deleted_hpa_snapshots,
            "deleted_node_metadata": deleted_nm,
            "deleted_karpenter_node_claims": deleted_knc,
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
