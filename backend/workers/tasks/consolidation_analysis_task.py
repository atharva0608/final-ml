"""
Consolidation Analysis Task — T-18
=====================================
Identifies node consolidation candidates using a two-branch algorithm.
Runs every 10 minutes. Writes summary to Redis TTL=600s.

Redis key: spot:consolidation:candidates:{cluster_id}

Branch A — Karpenter nodes (nodepool_name NOT NULL):
  Candidate if: do_not_disrupt == False AND is_ready == True AND cpu_util < threshold

Branch B — non-Karpenter nodes:
  Candidate if: is_ready == True AND all pods have no required node affinity
               AND pod CPU+mem requests fit on another node with headroom.

GAP 9 FIX: pricing_data_pending fallback when Redis pricing key absent
           and instance_catalog table does not exist.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from backend.utils.retry import with_retry
from backend.workers.app import app as celery_app

logger = logging.getLogger(__name__)

_KARPENTER_CPU_THRESHOLD_PCT = 20.0
_REDIS_PRICING_PREFIX = "spot:pricing:instance:"
_CONSOLIDATION_KEY = "spot:consolidation:candidates:{cluster_id}"
_CONSOLIDATION_TTL = 600


@celery_app.task(
    name="backend.workers.tasks.consolidation_analysis_task.run_consolidation_analysis",
    bind=True,
    max_retries=2,
    soft_time_limit=300,
)
def run_consolidation_analysis(self) -> None:
    """Dispatches consolidation analysis per cluster."""
    from backend.models.base import SessionLocal
    from backend.models.node_metadata import NodeMetadata
    from sqlalchemy import distinct

    db = SessionLocal()
    try:
        cluster_ids = [
            r[0] for r in db.query(distinct(NodeMetadata.cluster_id)).all()
        ]
        for cluster_id in cluster_ids:
            try:
                _analyze_cluster(db, cluster_id)
            except Exception as exc:
                logger.warning(f"consolidation_analysis_failed cluster={cluster_id}: {exc}")
                try:
                    import redis as _redis_lib
                    from backend.core.config import settings as _s
                    from backend.services.observability_logger import ObservabilityLogger
                    _rc = _redis_lib.from_url(_s.REDIS_URL, decode_responses=True)
                    ObservabilityLogger(redis_client=_rc).log_decision(
                        cluster_id=cluster_id,
                        decision_type="TASK_FAILURE",
                        approved=False,
                        reason=str(exc),
                        metadata={"task": "consolidation_analysis_task"},
                    )
                    _rc.incr(f"spot:errors:celery_task_failure:{cluster_id}")
                    _rc.expire(f"spot:errors:celery_task_failure:{cluster_id}", 86400)
                except Exception:
                    pass
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception(f"consolidation_analysis_task_error: {exc}")
        raise self.retry(exc=exc, countdown=120)
    finally:
        db.close()


def _analyze_cluster(db, cluster_id: str) -> None:
    from backend.models.node_metadata import NodeMetadata
    from backend.core.config import settings
    import redis as redis_lib

    nodes = (
        db.query(NodeMetadata)
        .filter(NodeMetadata.cluster_id == cluster_id, NodeMetadata.is_ready == True)
        .all()
    )

    if not nodes:
        _write_result(
            cluster_id,
            candidate_count=0,
            est_savings=None,
            data_ready=False,
            reason="node_allocatable_data_pending",
        )
        return

    redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
    candidates: List[NodeMetadata] = []

    for node in nodes:
        if node.nodepool_name:
            # Branch A: Karpenter node
            if not node.do_not_disrupt:
                cpu_util = _get_node_cpu_util(db, cluster_id, node.node_name)
                if cpu_util is not None and cpu_util < _KARPENTER_CPU_THRESHOLD_PCT:
                    candidates.append(node)
        else:
            # Branch B: non-Karpenter node
            if _can_drain(db, cluster_id, node.node_name, nodes):
                candidates.append(node)

    est_savings, pricing_reason = _estimate_savings(candidates, redis_client, db=db)

    _write_result(
        cluster_id,
        candidate_count=len(candidates),
        est_savings=est_savings,
        data_ready=True,
        reason=pricing_reason or "",
    )


def _get_node_cpu_util(db, cluster_id: str, node_name: str) -> Optional[float]:
    """Returns average CPU utilisation % across all pods on the node (last 5 min)."""
    from backend.models.pod_metric import PodMetric
    from sqlalchemy import func

    cutoff = datetime.utcnow() - timedelta(minutes=5)
    row = (
        db.query(
            func.sum(PodMetric.cpu_usage_millicores).label("used"),
            func.sum(PodMetric.cpu_request_millicores).label("req"),
        )
        .filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.node_name == node_name,
            PodMetric.timestamp > cutoff,
        )
        .first()
    )
    if not row or not row.req or row.req == 0:
        return None
    return (row.used / row.req) * 100.0


def _can_drain(db, cluster_id: str, node_name: str, all_nodes) -> bool:
    """
    True if all pods on the node:
      1. Have no required node affinity (checked from pod_metadata.affinity)
      2. Their total CPU+mem requests fit on at least one other ready node with headroom.
    """
    from backend.models.pod_metric import PodMetric

    cutoff = datetime.utcnow() - timedelta(minutes=5)
    pod_rows = (
        db.query(
            PodMetric.pod_name,
            PodMetric.cpu_request_millicores,
            PodMetric.memory_request_bytes,
            PodMetric.pod_metadata,
        )
        .filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.node_name == node_name,
            PodMetric.timestamp > cutoff,
        )
        .distinct(PodMetric.pod_name)
        .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
        .all()
    )

    if not pod_rows:
        return True

    for p in pod_rows:
        meta = p.pod_metadata or {}
        affinity = meta.get("affinity") or {}
        if affinity.get("node_affinity_required"):
            return False

    total_cpu = sum((p.cpu_request_millicores or 0) for p in pod_rows)
    total_mem = sum((p.memory_request_bytes or 0) for p in pod_rows)

    for other in all_nodes:
        if other.node_name == node_name:
            continue
        if not other.is_ready:
            continue
        alloc_cpu = other.allocatable_cpu_millicores or 0
        alloc_mem = other.allocatable_memory_bytes or 0
        if alloc_cpu >= total_cpu and alloc_mem >= total_mem:
            return True

    return False


def _estimate_savings(candidates, redis_client, db=None) -> Tuple[Optional[float], Optional[str]]:
    """
    Estimates monthly savings from removing candidate nodes.
    P-16 FIX: computes savings as (od_price - spot_price) * 730 per node.
    Falls back to null if either price is unavailable.
    """
    if not candidates:
        return 0.0, None

    from backend.core.config import settings
    from backend.utils.redis_safe import safe_get_json
    total_monthly = 0.0
    missing_price = False

    try:
        from backend.services.aws_pricing_service import AWSPricingService
        pricing_svc = AWSPricingService(db=db, redis=redis_client) if db else None
    except Exception:
        pricing_svc = None

    for node in candidates:
        instance_type = node.instance_type
        if not instance_type:
            missing_price = True
            continue

        region = getattr(settings, "AWS_REGION", "us-east-1")

        # Spot price from Redis (fast path)
        spot_price = None
        try:
            redis_key = f"{_REDIS_PRICING_PREFIX}{instance_type}:{region}"
            raw = redis_client.get(redis_key)
            if raw:
                spot_price = float(raw)
        except Exception:
            pass

        # OD price from AWSPricingService or Redis fallback
        od_price = None
        try:
            if pricing_svc:
                od_price = pricing_svc.get_ondemand_price(instance_type, region)
            if od_price is None:
                od_raw = redis_client.get(f"spot:pricing:ondemand:{instance_type}:{region}")
                if od_raw:
                    od_price = float(od_raw)
        except Exception:
            pass

        if spot_price is None or od_price is None:
            missing_price = True
            continue

        savings_per_node = max(0.0, od_price - spot_price) * 730
        total_monthly += savings_per_node

    if missing_price and total_monthly == 0.0:
        return None, "pricing_data_pending"

    return round(total_monthly, 2), None


def _write_result(
    cluster_id: str,
    candidate_count: int,
    est_savings: Optional[float],
    data_ready: bool,
    reason: str,
) -> None:
    from backend.core.config import settings
    import redis as redis_lib

    redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
    key = _CONSOLIDATION_KEY.format(cluster_id=cluster_id)
    payload = json.dumps({
        "consolidation_candidates": candidate_count,
        "est_savings_monthly_usd": est_savings,
        "data_ready": data_ready,
        "data_ready_reason": reason,
    })

    @with_retry(exceptions=(ConnectionError, TimeoutError), max_attempts=3, backoff_seconds=1.0)
    def _do_redis_write():
        redis_client.setex(key, _CONSOLIDATION_TTL, payload)

    _do_redis_write()
    logger.debug(
        f"consolidation_candidates_written cluster={cluster_id} "
        f"count={candidate_count} savings={est_savings} data_ready={data_ready}"
    )
