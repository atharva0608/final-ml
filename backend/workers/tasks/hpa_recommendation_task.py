"""
HPA Recommendation Task — T-16
================================
Computes recommended max_replicas and min_replicas from 30-day P95 history
in hpa_status_snapshots. Runs every 30 minutes via Celery beat.

Algorithm:
  - Query last 30 days of hpa_status_snapshots per workload.
  - Guard: if data window < 7 days, skip (write null).
  - recommended_max = ceil(P95(desired_replicas) * 1.2)
  - recommended_min = max(1, mode(desired_replicas WHERE cpu_utilization_pct < 30))
      NULL guard: if cpu_utilization_pct is NULL for all rows, fall back to max(1, min(desired))
  - Writes to hpa_configs.recommended_max_replicas / recommended_min_replicas.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.exc import OperationalError

from backend.utils.retry import with_retry
from backend.workers.app import app as celery_app

logger = logging.getLogger(__name__)

_RECOMMENDATION_BASIS_LABEL = (
    "Based on P95 desired replicas (last 30 days) \u00d7 1.2 safety margin"
)


@celery_app.task(
    name="backend.workers.tasks.hpa_recommendation_task.compute_hpa_recommendations",
    bind=True,
    max_retries=2,
    soft_time_limit=600,
)
def compute_hpa_recommendations(self) -> None:
    """
    Computes recommended HPA replica counts across all clusters and writes
    to hpa_configs.recommended_max_replicas / recommended_min_replicas.
    """
    from backend.models.base import SessionLocal
    from backend.models.hpa_configs import HpaConfig
    from backend.models.hpa_status_snapshots import HpaStatusSnapshot
    from sqlalchemy import distinct

    db = SessionLocal()
    try:
        cluster_ids = [
            r[0]
            for r in db.query(distinct(HpaConfig.cluster_id)).all()
        ]

        total_updated = 0
        for cluster_id in cluster_ids:
            total_updated += _process_cluster(db, cluster_id)

        db.commit()
        logger.info(
            "hpa_recommendation_task_complete",
            extra={"clusters": len(cluster_ids), "updated": total_updated},
        )

    except Exception as exc:
        db.rollback()
        logger.exception("hpa_recommendation_task_error", extra={"error": str(exc)})
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
                metadata={"task": "hpa_recommendation_task"},
            )
            _rc.incr(f"spot:errors:celery_task_failure:{_cid}")
            _rc.expire(f"spot:errors:celery_task_failure:{_cid}", 86400)
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=120)
    finally:
        db.close()


def _process_cluster(db, cluster_id: str) -> int:
    from backend.models.hpa_configs import HpaConfig
    from backend.models.hpa_status_snapshots import HpaStatusSnapshot

    cutoff_30d = datetime.utcnow() - timedelta(days=30)
    cutoff_7d = datetime.utcnow() - timedelta(days=7)
    updated = 0

    configs = (
        db.query(HpaConfig)
        .filter(HpaConfig.cluster_id == cluster_id)
        .all()
    )

    for cfg in configs:
        snapshots = (
            db.query(HpaStatusSnapshot)
            .filter(
                HpaStatusSnapshot.cluster_id == cluster_id,
                HpaStatusSnapshot.workload_name == cfg.workload_name,
                HpaStatusSnapshot.namespace == cfg.namespace,
                HpaStatusSnapshot.snapshot_at > cutoff_30d,
                HpaStatusSnapshot.desired_replicas.isnot(None),
            )
            .order_by(HpaStatusSnapshot.snapshot_at.asc())
            .all()
        )

        if not snapshots:
            continue

        earliest = min(s.snapshot_at for s in snapshots)
        if (datetime.utcnow() - earliest).days < 7:
            continue

        desired_series = [s.desired_replicas for s in snapshots]
        cpu_util_series = [
            s.cpu_utilization_pct for s in snapshots
            if s.cpu_utilization_pct is not None
        ]

        rec_max = math.ceil(_p95(desired_series) * 1.2)

        if cpu_util_series:
            low_cpu_desired = [
                s.desired_replicas for s in snapshots
                if s.cpu_utilization_pct is not None and s.cpu_utilization_pct < 30
            ]
            if low_cpu_desired:
                rec_min = max(1, _mode(low_cpu_desired))
            else:
                rec_min = max(1, min(desired_series))
        else:
            rec_min = max(1, min(desired_series))

        cfg.recommended_max_replicas = rec_max
        cfg.recommended_min_replicas = rec_min
        updated += 1

    @with_retry(exceptions=(OperationalError,), max_attempts=3, backoff_seconds=1.0)
    def _flush_hpa_writes():
        db.flush()

    if updated > 0:
        _flush_hpa_writes()

    return updated


def _p95(values: List[int]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(math.ceil(0.95 * len(sorted_vals))) - 1
    idx = max(0, min(idx, len(sorted_vals) - 1))
    return float(sorted_vals[idx])


def _mode(values: List[int]) -> int:
    if not values:
        return 1
    counts = Counter(values)
    return counts.most_common(1)[0][0]
