"""
Workload CPU Coefficient of Variation Task — T-07
=================================================
Computes 14-day trimmed CPU CV per workload and persists to workload_classifications.

Run every 10 minutes via Celery beat.

Algorithm:
  1. For each cluster, fetch all WorkloadClassificationRecord rows.
  2. For each workload, query 14 days of pod_metrics.cpu_usage_millicores.
  3. Trim top 5%: samples = sorted(samples)[:int(len(samples) * 0.95)]
  4. cpu_cv = stddev(samples) / mean(samples)  if mean > 0 else 0.0
  5. traffic_skew_detected = (cpu_cv > 0.4)
  6. rps_cv: write null (requires Prometheus, out of scope).

NOTE: This task is separate from PlacementAdvisorService._compute_cv() — that
is a live in-cycle computation. This task provides a 14-day persisted value for
UI display. Both coexist for different purposes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.exc import OperationalError

from backend.utils.retry import with_retry
from backend.workers.app import app as celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="backend.workers.tasks.workload_cv_task.compute_workload_cv",
    bind=True,
    max_retries=2,
    soft_time_limit=600,
)
def compute_workload_cv(self) -> None:
    """
    Compute 14-day CPU CV for all workloads across all clusters.
    Writes cpu_cv and traffic_skew_detected to workload_classifications.
    """
    from backend.core.database import SessionLocal
    from backend.models.workload_classification import WorkloadClassificationRecord
    from backend.models.pod_metric import PodMetric
    from sqlalchemy import distinct

    db = SessionLocal()
    try:
        cluster_ids = [
            r[0] for r in db.query(distinct(WorkloadClassificationRecord.cluster_id)).all()
        ]

        for cluster_id in cluster_ids:
            _compute_for_cluster(db, cluster_id)

        db.commit()
        logger.info("workload_cv_task_complete", extra={"clusters": len(cluster_ids)})

    except Exception as exc:
        db.rollback()
        logger.exception("workload_cv_task_error", extra={"error": str(exc)})
        try:
            import redis as _redis_lib
            from backend.core.config import settings as _s
            from backend.services.observability_logger import ObservabilityLogger
            _rc = _redis_lib.from_url(_s.REDIS_URL, decode_responses=True)
            _cid = cluster_ids[0] if cluster_ids else "unknown"
            ObservabilityLogger(redis_client=_rc).log_decision(
                cluster_id=_cid,
                decision_type="TASK_FAILURE",
                approved=False,
                reason=str(exc),
                metadata={"task": "workload_cv_task"},
            )
            _rc.incr(f"spot:errors:celery_task_failure:{_cid}")
            _rc.expire(f"spot:errors:celery_task_failure:{_cid}", 86400)
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()


def _compute_for_cluster(db, cluster_id: str) -> None:
    from backend.models.workload_classification import WorkloadClassificationRecord
    from backend.models.pod_metric import PodMetric
    from sqlalchemy import func

    cutoff = datetime.utcnow() - timedelta(days=14)

    workloads = (
        db.query(WorkloadClassificationRecord)
        .filter(WorkloadClassificationRecord.cluster_id == cluster_id)
        .all()
    )

    if not workloads:
        return

    cpu_rows = (
        db.query(
            PodMetric.namespace,
            PodMetric.controller_name,
            PodMetric.cpu_usage_millicores,
        )
        .filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.timestamp > cutoff,
            PodMetric.cpu_usage_millicores.isnot(None),
        )
        .all()
    )

    samples_by_workload: dict = {}
    for row in cpu_rows:
        if row.namespace and row.controller_name:
            key = f"{row.namespace}/{row.controller_name}"
            samples_by_workload.setdefault(key, []).append(float(row.cpu_usage_millicores))

    for wc in workloads:
        wid = wc.workload_id
        samples = samples_by_workload.get(wid)
        if not samples or len(samples) < 2:
            continue

        try:
            samples_sorted = sorted(samples)
            trim_idx = max(1, int(len(samples_sorted) * 0.95))
            trimmed = samples_sorted[:trim_idx]

            cpu_cv = _compute_cv(trimmed)
            wc.cpu_cv = round(cpu_cv, 4)
            wc.traffic_skew_detected = cpu_cv > 0.4
        except Exception as exc:
            logger.warning(
                "workload_cv_compute_error",
                extra={"workload_id": wid, "error": str(exc)},
            )

    @with_retry(exceptions=(OperationalError,), max_attempts=3, backoff_seconds=1.0)
    def _flush_cv_writes():
        db.flush()

    _flush_cv_writes()


def _compute_cv(samples: List[float]) -> float:
    try:
        import numpy as np
        arr = np.array(samples)
        mean = float(np.mean(arr))
        if mean <= 0:
            return 0.0
        return float(np.std(arr, ddof=1)) / mean
    except ImportError:
        pass

    import statistics
    mean = statistics.mean(samples)
    if mean <= 0:
        return 0.0
    return statistics.stdev(samples) / mean
