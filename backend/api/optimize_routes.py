"""
Optimize Page Routes
====================
Provides endpoints for the Spot Optimizer UI placement/actionability features.

Routes:
  GET /api/v1/optimize/workloads/{workload_id}/placement-state  — T-02
  GET /api/v1/optimize/workloads/{workload_id}/gates            — T-03

All routes registered in api_gateway.py with prefix /api/v1.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time

import redis
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.dependencies import get_current_user
from backend.models.base import get_db
from backend.models.user import User
from backend.models.agent_action import AgentAction, AgentActionStatus, AgentActionType
from backend.models.workload_classification import WorkloadClassificationRecord
from backend.models.placement_policy import PlacementPolicyRecord
from backend.models.pod_metric import PodMetric
from backend.utils.data_freshness import compute_freshness, stale_node_filter
from backend.utils.api_response import ok, not_ready
from backend.utils.redis_safe import safe_get_json, safe_hgetall, safe_lrange_json, safe_ttl
from backend.utils.rate_limit import check_rate_limit
from backend.utils.state_machines import (
    PlacementState, compute_placement_state,
    NodeLifecycleState, compute_node_lifecycle,
    PodLifecycleClass, classify_pod_lifecycle,
)
from backend.utils.validation import (
    validate_cluster_id,
    validate_workload_id,
    validate_node_name,
    assert_cluster_access,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/optimize", tags=["optimize"])


def _safe_fetch(fn, fallback, label: str):
    try:
        return fn()
    except Exception as e:
        logger.warning("Partial failure in %s: %s", label, e)
        return fallback

_SYSTEM_NAMESPACES = frozenset([
    "kube-system",
    "kube-public",
    "kube-node-lease",
    "monitoring",
    "cert-manager",
    "karpenter",
    "keda",
    "ingress-nginx",
])

_SCALING_GUARD_WINDOW_SECONDS = 120


# ---------------------------------------------------------------------------
# GET /optimize/workloads/{workload_id}/placement-state   — T-02
# ---------------------------------------------------------------------------

@router.get(
    "/workloads/{workload_id:path}/placement-state",
    summary="Get placement-state for a workload (cooldowns, batch slots, recent decisions)",
)
def get_placement_state(
    workload_id: str,
    cluster_id: str = Query(..., description="Cluster UUID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns structured placement-state for a single workload including:
    - Cooldown and rollout-blocked status with remaining TTLs
    - Cluster batch slot usage
    - KEDA scaling guard state
    - PDB active flag (from spot:workload:state)
    - Recent decision log entries (from spot:pc:workload_log)
    - In-flight agent action count
    """
    validate_cluster_id(cluster_id)
    validate_workload_id(workload_id)
    assert_cluster_access(cluster_id, db)

    from backend.core.redis_client import get_redis_client

    try:
        redis_client = get_redis_client()
    except Exception:
        redis_client = None

    result: Dict[str, Any] = {
        "workload_id": workload_id,
        "cluster_id": cluster_id,
        "workload_cooldown_active": False,
        "workload_cooldown_expires_in_seconds": 0,
        "rollout_blocked": False,
        "rollout_blocked_expires_in_seconds": 0,
        "cluster_batch_slots_used": 0,
        "cluster_batch_slots_max": 2,
        "keda_scaling_active": False,
        "pdb_active": False,
        "in_flight_actions": 0,
        "recent_decisions": [],
    }

    if redis_client:
        try:
            cooldown_key = f"spot:placement_controller:cooldown:{cluster_id}:{workload_id}"
            cooldown_ttl = safe_ttl(redis_client, cooldown_key) or 0
            if cooldown_ttl > 0:
                result["workload_cooldown_active"] = True
                result["workload_cooldown_expires_in_seconds"] = cooldown_ttl

            rollout_key = f"spot:placement:rollout_blocked:{cluster_id}:{workload_id}"
            rollout_ttl = safe_ttl(redis_client, rollout_key) or 0
            if rollout_ttl > 0:
                result["rollout_blocked"] = True
                result["rollout_blocked_expires_in_seconds"] = rollout_ttl

            batch_val = safe_get_json(redis_client, f"rebalance:active_count:{cluster_id}")
            if batch_val is not None:
                try:
                    result["cluster_batch_slots_used"] = int(batch_val)
                except (ValueError, TypeError):
                    pass

            keda_val = safe_get_json(redis_client, f"spot:keda:last_scale_event:{cluster_id}")
            if keda_val is not None:
                try:
                    result["keda_scaling_active"] = (time.time() - float(keda_val)) < _SCALING_GUARD_WINDOW_SECONDS
                except (ValueError, TypeError):
                    result["keda_scaling_active"] = True

            state_data = safe_get_json(redis_client, f"spot:workload:state:{cluster_id}:{workload_id}", default={})
            result["pdb_active"] = bool(state_data.get("has_pdb", False))

            log_key = f"spot:pc:workload_log:{cluster_id}:{workload_id}"
            result["recent_decisions"] = safe_lrange_json(redis_client, log_key, 0, 9)

        except Exception as exc:
            logger.warning(
                "optimize_placement_state_redis_error",
                extra={"cluster_id": cluster_id, "workload_id": workload_id, "error": str(exc)},
            )

    try:
        in_flight = (
            db.query(func.count(AgentAction.id))
            .filter(
                AgentAction.cluster_id == cluster_id,
                AgentAction.payload.op("->>")(  # JSONB text extraction
                    "workload_id"
                ) == workload_id,
                AgentAction.status.in_(
                    [AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]
                ),
            )
            .scalar()
        )
        result["in_flight_actions"] = in_flight or 0
    except Exception as exc:
        logger.warning(
            "optimize_placement_state_db_error",
            extra={"cluster_id": cluster_id, "workload_id": workload_id, "error": str(exc)},
        )

    return ok(result)


# ---------------------------------------------------------------------------
# GET /optimize/workloads/{workload_id}/gates              — T-03
# ---------------------------------------------------------------------------

@router.get(
    "/workloads/{workload_id:path}/gates",
    summary="Evaluate 6 actionability gates for a workload",
)
def get_actionability_gates(
    workload_id: str,
    cluster_id: str = Query(..., description="Cluster UUID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns a list of 6 gate objects: [{gate, pass, status_text}].
    Gates determine whether the optimizer can safely act on a workload.
    """
    validate_cluster_id(cluster_id)
    validate_workload_id(workload_id)
    assert_cluster_access(cluster_id, db)

    from backend.core.redis_client import get_redis_client

    gates: List[Dict[str, Any]] = []

    wc = (
        db.query(WorkloadClassificationRecord)
        .filter(
            WorkloadClassificationRecord.cluster_id == cluster_id,
            WorkloadClassificationRecord.workload_id == workload_id,
        )
        .order_by(WorkloadClassificationRecord.classified_at.desc())
        .first()
    )

    pp = (
        db.query(PlacementPolicyRecord)
        .filter(
            PlacementPolicyRecord.cluster_id == cluster_id,
            PlacementPolicyRecord.workload_id == workload_id,
        )
        .first()
    )

    confidence_pass = wc is not None and wc.confidence_state == "CONFIRMED"
    gates.append({
        "gate": "confidence_state",
        "pass": confidence_pass,
        "status_text": wc.confidence_state if wc else "NO_DATA",
    })

    spot_friendly_pass = wc is not None and wc.spot_friendly is True
    gates.append({
        "gate": "spot_friendly",
        "pass": spot_friendly_pass,
        "status_text": "SPOT_FRIENDLY" if spot_friendly_pass else ("NOT_SPOT_FRIENDLY" if wc else "NO_DATA"),
    })

    spot_target_pass = pp is not None and (pp.spot_target or 0) > 0
    gates.append({
        "gate": "spot_target_gt_zero",
        "pass": spot_target_pass,
        "status_text": f"spot_target={pp.spot_target}" if pp else "NO_POLICY",
    })

    rollout_blocked_pass = True
    try:
        redis_client = get_redis_client()
        rollout_key = f"spot:placement:rollout_blocked:{cluster_id}:{workload_id}"
        rollout_blocked_pass = not bool(redis_client.exists(rollout_key))
    except Exception:
        rollout_blocked_pass = True
    gates.append({
        "gate": "rollout_not_blocked",
        "pass": rollout_blocked_pass,
        "status_text": "NOT_BLOCKED" if rollout_blocked_pass else "BLOCKED",
    })

    namespace = wc.namespace if wc else workload_id.split("/")[0] if "/" in workload_id else ""
    not_system_pass = namespace not in _SYSTEM_NAMESPACES
    gates.append({
        "gate": "not_system_namespace",
        "pass": not_system_pass,
        "status_text": f"namespace={namespace}",
    })

    if wc is not None and wc.classified_at is not None:
        age = datetime.utcnow() - wc.classified_at
        data_fresh_pass = age < timedelta(hours=24)
        age_str = f"{int(age.total_seconds() // 3600)}h ago"
    else:
        data_fresh_pass = False
        age_str = "NO_DATA"
    gates.append({
        "gate": "data_fresh",
        "pass": data_fresh_pass,
        "status_text": age_str,
    })

    return ok({"gates": gates})


# ---------------------------------------------------------------------------
# GET /optimize/workloads/placement/summary     — T-06
# ---------------------------------------------------------------------------

_PLACEMENT_SUMMARY_CACHE_TTL = 60
_PLACEMENT_SUMMARY_CACHE_KEY = "spot:placement:summary:{cluster_id}"

_TIER_LABELS: Dict[str, str] = {
    "Platinum": "100% OD (no spot)",
    "Gold": "70% OD floor",
    "Silver": "50% OD floor",
    "Bronze": "minimum OD",
}


@router.get(
    "/workloads/placement/summary",
    summary="Get placement drift summary for all confirmed workloads",
)
def get_placement_summary(
    cluster_id: str = Query(..., description="Cluster UUID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns placement drift summary: drifting/at-target/converging counts,
    reconcile_pct, last_cycle_at, active_evictions, and per-workload details.
    Result is cached in Redis for 60s (spot:placement:summary:{cluster_id}).
    """
    validate_cluster_id(cluster_id)
    assert_cluster_access(cluster_id, db)

    from backend.core.redis_client import get_redis_client

    redis_client = None
    try:
        redis_client = get_redis_client()
        check_rate_limit(redis_client, f"spot:ratelimit:placement_summary:{cluster_id}", 20, 60)
        cache_key = _PLACEMENT_SUMMARY_CACHE_KEY.format(cluster_id=cluster_id)
        cached = redis_client.get(cache_key)
        if cached:
            cached_data = json.loads(cached)
            if "data_ready" not in cached_data:
                return ok(cached_data)
            return cached_data
    except Exception:
        pass

    # P-01: freshness anchor — MAX(classified_at) for confirmed workloads
    max_classified_at = (
        db.query(func.max(WorkloadClassificationRecord.classified_at))
        .filter(WorkloadClassificationRecord.cluster_id == cluster_id)
        .scalar()
    )

    confirmed_workloads = (
        db.query(WorkloadClassificationRecord, PlacementPolicyRecord)
        .join(
            PlacementPolicyRecord,
            (WorkloadClassificationRecord.cluster_id == PlacementPolicyRecord.cluster_id)
            & (WorkloadClassificationRecord.workload_id == PlacementPolicyRecord.workload_id),
            isouter=True,
        )
        .filter(
            WorkloadClassificationRecord.cluster_id == cluster_id,
            WorkloadClassificationRecord.confidence_state == "CONFIRMED",
        )
        .all()
    )

    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    cpu_by_workload: Dict[str, Optional[float]] = {}
    try:
        cpu_rows = (
            db.query(
                PodMetric.namespace,
                PodMetric.controller_name,
                func.avg(PodMetric.cpu_utilization_pct).label("avg_cpu"),
            )
            .filter(
                PodMetric.cluster_id == cluster_id,
                PodMetric.timestamp > one_hour_ago,
            )
            .group_by(PodMetric.namespace, PodMetric.controller_name)
            .all()
        )
        for row in cpu_rows:
            if row.namespace and row.controller_name:
                key = f"{row.namespace}/{row.controller_name}"
                cpu_by_workload[key] = round(float(row.avg_cpu), 1) if row.avg_cpu is not None else None
    except Exception:
        pass

    drifting, at_target, converging = 0, 0, 0
    workload_list = []

    for wc, pp in confirmed_workloads:
        wid = wc.workload_id
        od_target = (pp.ondemand_target if pp else None) or 0
        spot_target = (pp.spot_target if pp else None) or 0
        savings = float(pp.estimated_monthly_saving_usd) if pp and pp.estimated_monthly_saving_usd else 0.0

        current_od = 0
        current_spot = 0
        if redis_client:
            try:
                raw = redis_client.get(f"spot:workload:state:{cluster_id}:{wid}")
                if raw:
                    st = json.loads(raw)
                    current_od = int(st.get("current_ondemand_pods", 0))
                    current_spot = int(st.get("current_spot_pods", 0))
            except Exception:
                pass

        drift = current_od - od_target
        if abs(drift) <= 1:
            status = "AT_TARGET"
            at_target += 1
        elif drift > 1:
            status = "DRIFTING"
            drifting += 1
        else:
            status = "CONVERGING"
            converging += 1

        workload_list.append({
            "workload_id": wid,
            "placement_status": status,
            "od_excess": max(0, drift),
            "od_required": od_target,
            "spot_count": current_spot,
            "estimated_monthly_saving_usd": savings,
            "cpu_avg_pct": cpu_by_workload.get(wid),
        })

    total_confirmed = len(confirmed_workloads)
    reconcile_pct = round((total_confirmed - drifting) / total_confirmed * 100, 1) if total_confirmed > 0 else None

    last_cycle_at = None
    if redis_client:
        try:
            cycle_data = safe_hgetall(redis_client, f"spot:placement_controller:metrics:{cluster_id}")
            last_cycle_at = cycle_data.get("cycle_ts")
        except Exception:
            pass

    active_evictions = 0
    try:
        active_evictions = (
            db.query(func.count(AgentAction.id))
            .filter(
                AgentAction.cluster_id == cluster_id,
                AgentAction.action_type == AgentActionType.EVICT_POD,
                AgentAction.status.in_(
                    [AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]
                ),
            )
            .scalar()
        ) or 0
    except Exception:
        pass

    freshness = compute_freshness(max_classified_at)
    result = ok(
        {
            "drifting_count": drifting,
            "at_target_count": at_target,
            "converging_count": converging,
            "total_confirmed": total_confirmed,
            "reconcile_pct": reconcile_pct,
            "last_cycle_at": last_cycle_at,
            "active_evictions": active_evictions,
            "workloads": workload_list,
            **freshness,
        },
        data_ready=not freshness["is_stale"],
        data_ready_reason="" if not freshness["is_stale"] else "stale_data",
    )

    if redis_client:
        try:
            redis_client.setex(cache_key, _PLACEMENT_SUMMARY_CACHE_TTL, json.dumps(result))
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# GET /optimize/workloads/profiling/summary     — T-08
# ---------------------------------------------------------------------------

@router.get(
    "/workloads/profiling/summary",
    summary="Get workload profiling summary with savings and tier logic",
)
def get_profiling_summary(
    cluster_id: str = Query(..., description="Cluster UUID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns profiling summary: total potential savings, observation_mode_active,
    traffic_skew_count, and per-workload tier/spot/savings details.
    Source: PlacementPolicyRecord JOIN WorkloadClassificationRecord.
    """
    validate_cluster_id(cluster_id)
    assert_cluster_access(cluster_id, db)

    rows = (
        db.query(WorkloadClassificationRecord, PlacementPolicyRecord)
        .join(
            PlacementPolicyRecord,
            (WorkloadClassificationRecord.cluster_id == PlacementPolicyRecord.cluster_id)
            & (WorkloadClassificationRecord.workload_id == PlacementPolicyRecord.workload_id),
            isouter=True,
        )
        .filter(
            WorkloadClassificationRecord.cluster_id == cluster_id,
        )
        .all()
    )

    traffic_skew_count = (
        db.query(func.count(PlacementPolicyRecord.id))
        .filter(
            PlacementPolicyRecord.cluster_id == cluster_id,
            PlacementPolicyRecord.traffic_skew_detected == True,
        )
        .scalar()
    ) or 0

    potential_savings_usd = 0.0
    workload_list = []

    for wc, pp in rows:
        savings = float(pp.estimated_monthly_saving_usd) if pp and pp.estimated_monthly_saving_usd else 0.0
        potential_savings_usd += savings

        tier_logic_label = _TIER_LABELS.get(wc.tier, wc.tier) if wc.tier else None
        cv_adjustment_note = None
        if pp and pp.pod_cpu_cv is not None and pp.pod_cpu_cv > 0.4:
            cv_adjustment_note = "CV > 0.4 detected — OD baseline raised"

        workload_list.append({
            "workload_id": wc.workload_id,
            "tier": wc.tier,
            "spot_score": wc.spot_score,
            "estimated_monthly_saving_usd": savings,
            "confidence_state": wc.confidence_state,
            "tier_logic_label": tier_logic_label,
            "cv_adjustment_note": cv_adjustment_note,
        })

    return ok({
        "potential_savings_usd": round(potential_savings_usd, 2),
        "observation_mode_active": settings.PLACEMENT_ADVISOR_OBSERVATION_MODE,
        "traffic_skew_count": traffic_skew_count,
        "workloads": workload_list,
    })


# ---------------------------------------------------------------------------
# T-14: GET /optimize/nodes/bin-packing
# ---------------------------------------------------------------------------

_OVERLOAD_THRESHOLD = 85.0


@router.get("/nodes/bin-packing", summary="Per-node CPU/memory packing density")
async def get_node_bin_packing(
    cluster_id: str = Query(...),
    db: Session = Depends(get_db),
):
    validate_cluster_id(cluster_id)
    assert_cluster_access(cluster_id, db)

    from backend.core.redis_client import get_redis_client as _rl_rc
    _rl_redis = _safe_fetch(_rl_rc, None, "rate_limit_redis_bin_packing")
    check_rate_limit(_rl_redis, f"spot:ratelimit:bin_packing:{cluster_id}", 10, 60)

    from backend.models.pod_metric import PodMetric
    from backend.models.node_metadata import NodeMetadata
    from sqlalchemy import func, text

    # P-01: freshness anchor — MAX(node_metadata.updated_at) for this cluster
    max_updated_at = (
        db.query(func.max(NodeMetadata.updated_at))
        .filter(NodeMetadata.cluster_id == cluster_id)
        .scalar()
    )

    if max_updated_at is None:
        return not_ready(
            "node_allocatable_data_pending",
            partial_data={"cluster_id": cluster_id, "nodes": [], "stale_nodes_excluded": 0, "consolidation_candidates": None},
        )

    # Only consider pods seen in the last 30 minutes to exclude terminated pods.
    # Terminated pods stop sending metrics; without a cutoff their last known
    # CPU would still be summed against current node allocatable, giving a
    # false over-estimate of usage (or, if usage was 0, a false under-estimate).
    from datetime import timedelta as _td
    _pod_cutoff = datetime.utcnow() - _td(minutes=30)

    # Track actual freshness: when was the last pod metric received?
    _last_pod_metric_at = (
        db.query(func.max(PodMetric.timestamp))
        .filter(PodMetric.cluster_id == cluster_id)
        .scalar()
    )

    latest_subq = (
        db.query(
            PodMetric.pod_name,
            PodMetric.node_name,
            PodMetric.cpu_request_millicores,
            PodMetric.memory_request_bytes,
            PodMetric.cpu_usage_millicores,
            PodMetric.memory_usage_bytes,
        )
        .filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.timestamp >= _pod_cutoff,   # exclude terminated/stale pods
        )
        .distinct(PodMetric.pod_name)
        .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
        .subquery()
    )

    rows = (
        db.query(
            latest_subq.c.node_name,
            func.sum(latest_subq.c.cpu_request_millicores).label("total_cpu_request"),
            func.sum(latest_subq.c.memory_request_bytes).label("total_mem_request"),
            func.sum(latest_subq.c.cpu_usage_millicores).label("total_cpu_usage"),
            func.sum(latest_subq.c.memory_usage_bytes).label("total_mem_usage"),
            func.count(func.distinct(latest_subq.c.pod_name)).label("pod_count"),
            NodeMetadata.allocatable_cpu_millicores,
            NodeMetadata.allocatable_memory_bytes,
            NodeMetadata.az,
            NodeMetadata.capacity_type,
            NodeMetadata.instance_type,
            NodeMetadata.is_ready,
            NodeMetadata.do_not_disrupt,
            NodeMetadata.updated_at.label("node_updated_at"),
        )
        .join(
            NodeMetadata,
            (NodeMetadata.cluster_id == cluster_id)
            & (NodeMetadata.node_name == latest_subq.c.node_name),
            isouter=True,
        )
        .group_by(
            latest_subq.c.node_name,
            NodeMetadata.allocatable_cpu_millicores,
            NodeMetadata.allocatable_memory_bytes,
            NodeMetadata.az,
            NodeMetadata.capacity_type,
            NodeMetadata.instance_type,
            NodeMetadata.is_ready,
            NodeMetadata.do_not_disrupt,
            NodeMetadata.updated_at,
        )
        .all()
    )

    from backend.pipeline.stage3_ppe.engine import NodeOverheadProfiler
    nodes_with_ts = []
    for r in rows:
        alloc_cpu = float(r.allocatable_cpu_millicores or 1)
        alloc_mem = float(r.allocatable_memory_bytes or 1)

        cpu_requested_pct = min(100.0, round(float(r.total_cpu_request or 0) / alloc_cpu * 100, 1))
        cpu_actual_pct = min(100.0, round(float(r.total_cpu_usage or 0) / alloc_cpu * 100, 1))
        cpu_buffer_pct = round(100.0 - cpu_actual_pct, 1)
        mem_requested_pct = min(100.0, round(float(r.total_mem_request or 0) / alloc_mem * 100, 1))
        mem_actual_pct = min(100.0, round(float(r.total_mem_usage or 0) / alloc_mem * 100, 1))
        mem_buffer_pct = round(100.0 - mem_actual_pct, 1)

        is_overloaded = cpu_actual_pct > _OVERLOAD_THRESHOLD or mem_actual_pct > _OVERLOAD_THRESHOLD

        overhead = NodeOverheadProfiler.profile(
            allocatable_cpu_mc=alloc_cpu,
            allocatable_mem_bytes=alloc_mem,
        )
        nodes_with_ts.append({
            "node_name": r.node_name,
            "az": r.az,
            "capacity_type": r.capacity_type,
            "instance_type": r.instance_type,
            "pod_count": r.pod_count,
            "cpu_requested_pct": cpu_requested_pct,
            "cpu_actual_pct": cpu_actual_pct,
            "cpu_buffer_pct": cpu_buffer_pct,
            "mem_requested_pct": mem_requested_pct,
            "mem_actual_pct": mem_actual_pct,
            "mem_buffer_pct": mem_buffer_pct,
            "is_overloaded": is_overloaded,
            "is_ready": r.is_ready,
            "do_not_disrupt": r.do_not_disrupt,
            "node_updated_at": r.node_updated_at,
            "allocatable_cpu_millicores": r.allocatable_cpu_millicores,
            "allocatable_memory_bytes": r.allocatable_memory_bytes,
            "effective_cpu_mc": overhead["effective_cpu_mc"],
            "effective_mem_bytes": overhead["effective_mem_bytes"],
            "overhead_detail": overhead["overhead_detail"],
        })

    # P-10: batch query for DRAIN_NODE actions in flight
    draining_nodes: set = set()
    try:
        drain_rows = (
            db.query(AgentAction.payload["node_name"].astext)
            .filter(
                AgentAction.cluster_id == cluster_id,
                AgentAction.action_type == AgentActionType.DRAIN_NODE,
                AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
            )
            .all()
        )
        draining_nodes = {r[0] for r in drain_rows if r[0]}
    except Exception:
        pass

    # P-01: filter stale nodes before computing response
    fresh_nodes, stale_count = stale_node_filter(nodes_with_ts, "node_updated_at")

    # Pricing look-up — one query per cluster (keyed by instance_type + capacity_type)
    from backend.models.pricing import OnDemandPricing, SpotPriceHistory
    from backend.models.cluster import Cluster as _ClusterModel
    _cluster_obj = db.query(_ClusterModel).filter(_ClusterModel.id == cluster_id).first()
    _cluster_region = (_cluster_obj.region if _cluster_obj else None) or "us-east-1"

    _instance_types = {n["instance_type"] for n in fresh_nodes if n.get("instance_type")}

    _od_prices: dict = {}
    _spot_prices: dict = {}
    if _instance_types:
        from sqlalchemy import desc as _desc
        _od_rows = (
            db.query(OnDemandPricing.instance_type, OnDemandPricing.price)
            .filter(
                OnDemandPricing.instance_type.in_(_instance_types),
                OnDemandPricing.region == _cluster_region,
            )
            .all()
        )
        _od_prices = {r.instance_type: float(r.price) for r in _od_rows}

        _spot_rows = (
            db.query(SpotPriceHistory.instance_type, SpotPriceHistory.price)
            .filter(
                SpotPriceHistory.instance_type.in_(_instance_types),
                SpotPriceHistory.region == _cluster_region,
            )
            .order_by(SpotPriceHistory.instance_type, _desc(SpotPriceHistory.timestamp))
            .distinct(SpotPriceHistory.instance_type)
            .all()
        )
        _spot_prices = {r.instance_type: float(r.price) for r in _spot_rows}

    _GiB = 1024 ** 3
    _exclude = {"node_updated_at", "is_ready", "do_not_disrupt"}
    nodes_out = []
    for n in fresh_nodes:
        _itype = n.get("instance_type")
        _cap = (n.get("capacity_type") or "").lower()
        if _cap == "spot":
            _price = _spot_prices.get(_itype) or _od_prices.get(_itype)
        else:
            _price = _od_prices.get(_itype)
        _alloc_cpu_m = n.pop("allocatable_cpu_millicores", None) or None
        _alloc_mem_b = n.pop("allocatable_memory_bytes", None) or None
        nodes_out.append({
            **{k: v for k, v in n.items() if k not in _exclude},
            "lifecycle_state": compute_node_lifecycle(
                is_ready=n.get("is_ready", True),
                do_not_disrupt=n.get("do_not_disrupt", False),
                has_pending_drain=n["node_name"] in draining_nodes,
            ).value,
            "vcpu_count": round((_alloc_cpu_m or 0) / 1000) if _alloc_cpu_m else None,
            "memory_gib": round((_alloc_mem_b or 0) / _GiB, 1) if _alloc_mem_b else None,
            "hourly_price_usd": round(_price, 4) if _price else None,
        })

    from backend.core.redis_client import get_redis_client as _get_rc
    redis_client = _safe_fetch(_get_rc, None, "redis_client_bin_packing")
    consolidation_key = f"spot:consolidation:candidates:{cluster_id}"
    consolidation_candidates = safe_get_json(redis_client, consolidation_key) if redis_client else None

    freshness = compute_freshness(max_updated_at)
    pod_freshness = compute_freshness(_last_pod_metric_at)
    data_ready = (consolidation_candidates is not None) and not freshness["is_stale"]
    reason = "" if data_ready else ("stale_data" if freshness["is_stale"] else "pricing_data_pending")

    _pod_age_seconds = None
    if _last_pod_metric_at:
        _pod_age_seconds = round((datetime.utcnow() - _last_pod_metric_at).total_seconds())

    return ok(
        {
            "cluster_id": cluster_id,
            "nodes": nodes_out,
            "stale_nodes_excluded": stale_count,
            "consolidation_candidates": consolidation_candidates,
            "last_pod_metric_at": _last_pod_metric_at.isoformat() if _last_pod_metric_at else None,
            "pod_data_age_seconds": _pod_age_seconds,   # seconds since last agent push
            **freshness,
        },
        data_ready=data_ready,
        data_ready_reason=reason,
    )


# ---------------------------------------------------------------------------
# T-15: GET /optimize/workloads/{workload_id}/pods
# ---------------------------------------------------------------------------

@router.get("/workloads/{workload_id:path}/pods", summary="Pod list with AZ and capacity_type for a workload")
async def get_workload_pods(
    workload_id: str,
    cluster_id: str = Query(...),
    db: Session = Depends(get_db),
):
    validate_cluster_id(cluster_id)
    validate_workload_id(workload_id)
    assert_cluster_access(cluster_id, db)

    from backend.models.pod_metric import PodMetric
    from backend.models.node_metadata import NodeMetadata
    from sqlalchemy import func
    from datetime import datetime as _dt

    workload_name = workload_id.split("/")[-1] if "/" in workload_id else workload_id

    latest_subq = (
        db.query(
            PodMetric.pod_name,
            PodMetric.node_name,
            PodMetric.phase,
            PodMetric.start_time,
            PodMetric.timestamp,
        )
        .filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.controller_name == workload_name,
        )
        .distinct(PodMetric.pod_name)
        .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
        .subquery()
    )

    rows = (
        db.query(
            latest_subq.c.pod_name,
            latest_subq.c.node_name,
            latest_subq.c.phase,
            latest_subq.c.start_time,
            latest_subq.c.timestamp,
            NodeMetadata.az,
            NodeMetadata.capacity_type,
        )
        .join(
            NodeMetadata,
            (NodeMetadata.cluster_id == cluster_id)
            & (NodeMetadata.node_name == latest_subq.c.node_name),
            isouter=True,
        )
        .all()
    )

    # P-11: batch query for EVICT_POD actions in flight for this workload
    evicting_pods: set = set()
    try:
        evict_rows = (
            db.query(AgentAction.payload["pod_name"].astext)
            .filter(
                AgentAction.cluster_id == cluster_id,
                AgentAction.action_type == AgentActionType.EVICT_POD,
                AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
            )
            .all()
        )
        evicting_pods = {r[0] for r in evict_rows if r[0]}
    except Exception:
        pass

    now = _dt.utcnow()
    pods = []
    for r in rows:
        age_seconds = None
        if r.start_time:
            age_seconds = int((now - r.start_time).total_seconds())
        pods.append({
            "name": r.pod_name,
            "node_name": r.node_name,
            "az": r.az,
            "capacity_type": r.capacity_type,
            "phase": r.phase,
            "age_seconds": age_seconds,
            "lifecycle_class": classify_pod_lifecycle(
                phase=r.phase,
                cpu_usage_millicores=None,
                has_pending_evict=r.pod_name in evicting_pods,
            ).value,
        })

    max_pod_ts = _safe_fetch(
        lambda: db.query(func.max(PodMetric.timestamp))
        .filter(PodMetric.cluster_id == cluster_id, PodMetric.controller_name == workload_name)
        .scalar(),
        None, "pods_freshness",
    )
    freshness = compute_freshness(max_pod_ts)
    return ok({
        "cluster_id": cluster_id,
        "workload_id": workload_id,
        "pods": pods,
        **freshness,
    })


# ---------------------------------------------------------------------------
# T-17: GET /optimize/workloads/scaling
# ---------------------------------------------------------------------------

_RECOMMENDATION_BASIS_LABEL = (
    "Based on P95 desired replicas (last 30 days) \u00d7 1.2 safety margin"
)


def _cooldown_assessment(seconds) -> Optional[str]:
    if seconds is None:
        return None
    if seconds < 60:
        return "Too short"
    if seconds < 120:
        return "Adequate"
    return "Optimal"


def _classify_hpa_status(cfg, snapshots_30m, snapshots_24h, has_pending_pods: bool) -> str:
    if cfg.current_replicas is not None and cfg.max_replicas and cfg.current_replicas >= cfg.max_replicas:
        return "AT_MAX"
    if (cfg.desired_replicas is not None and cfg.current_replicas is not None
            and cfg.desired_replicas > cfg.current_replicas and has_pending_pods):
        return "SCALING_UP"
    # Thrashing: > 3 direction changes in 30 min
    if len(snapshots_30m) >= 4:
        direction_changes = sum(
            1 for i in range(1, len(snapshots_30m))
            if (snapshots_30m[i].desired_replicas or 0) != (snapshots_30m[i - 1].desired_replicas or 0)
        )
        if direction_changes > 3:
            return "THRASHING"
    # Overprovisioned
    if snapshots_30m:
        latest_util = next(
            (s.cpu_utilization_pct for s in reversed(snapshots_30m) if s.cpu_utilization_pct is not None),
            None,
        )
        if (latest_util is not None and latest_util < 20
                and cfg.current_replicas is not None
                and cfg.min_replicas is not None
                and cfg.current_replicas > cfg.min_replicas):
            return "OVERPROVISIONED"
    return "OPTIMAL"


@router.get("/workloads/scaling", summary="HPA scaling status classification per workload")
async def get_workloads_scaling(
    cluster_id: str = Query(...),
    db: Session = Depends(get_db),
):
    validate_cluster_id(cluster_id)
    assert_cluster_access(cluster_id, db)

    from backend.core.redis_client import get_redis_client as _rl_rc2
    _rl_redis2 = _safe_fetch(_rl_rc2, None, "rate_limit_redis_scaling")
    check_rate_limit(_rl_redis2, f"spot:ratelimit:workloads_scaling:{cluster_id}", 20, 60)

    from backend.models.hpa_configs import HpaConfig
    from backend.models.hpa_status_snapshots import HpaStatusSnapshot
    from backend.models.pod_metric import PodMetric
    from sqlalchemy import func
    from datetime import datetime as _dt, timedelta as _td

    now = _dt.utcnow()
    cutoff_30m = now - _td(minutes=30)
    cutoff_24h = now - _td(hours=24)

    # P-01: freshness anchor — MAX(hpa_status_snapshots.snapshot_at) for this cluster
    max_snapshot_at = (
        db.query(func.max(HpaStatusSnapshot.snapshot_at))
        .filter(HpaStatusSnapshot.cluster_id == cluster_id)
        .scalar()
    )

    # Build KEDA-managed workload set via KedaService (best-effort)
    keda_managed_names: set = set()
    try:
        from backend.services.keda_service import KedaService
        from backend.core.redis_client import get_redis_client
        _redis = get_redis_client()
        _keda_svc = KedaService(db=db, redis=_redis)
        _scaled_objects = _keda_svc.get_all_scaled_objects(cluster_id)
        for _so in _scaled_objects:
            if getattr(_so, 'scale_target_ref_name', None):
                keda_managed_names.add(_so.scale_target_ref_name)
    except Exception:
        pass

    configs = _safe_fetch(
        lambda: db.query(HpaConfig).filter(HpaConfig.cluster_id == cluster_id).all(),
        [],
        "hpa_configs_query",
    )

    # Pending pods set (from pod_metrics — T-12)
    pending_pods_workloads: set = set()
    try:
        pending_rows = (
            db.query(PodMetric.controller_name)
            .filter(
                PodMetric.cluster_id == cluster_id,
                PodMetric.phase == "Pending",
                PodMetric.timestamp > cutoff_30m,
            )
            .distinct()
            .all()
        )
        pending_pods_workloads = {r[0] for r in pending_rows if r[0]}
    except Exception:
        pass

    workloads_out = []
    total_scale_events_24h = 0
    hpa_misconfigured_count = 0

    for cfg in configs:
        workload_name = cfg.workload_name

        # KEDA-managed: skip HPA classification
        if workload_name in keda_managed_names:
            workloads_out.append({
                "workload_id": f"{cfg.namespace}/{workload_name}",
                "namespace": cfg.namespace,
                "keda_managed": True,
                "status": "KEDA-managed",
                "has_warning": False,
                "cooldown_assessment": None,
                "scale_events_24h": 0,
                "recommendation_basis_label": None,
                "recommended_max_replicas": None,
                "recommended_min_replicas": None,
                "current_replicas": cfg.current_replicas,
                "max_replicas": cfg.max_replicas,
                "min_replicas": cfg.min_replicas,
            })
            continue

        _wn = workload_name
        snapshots_30m = _safe_fetch(
            lambda: db.query(HpaStatusSnapshot)
            .filter(
                HpaStatusSnapshot.cluster_id == cluster_id,
                HpaStatusSnapshot.workload_name == _wn,
                HpaStatusSnapshot.snapshot_at > cutoff_30m,
            )
            .order_by(HpaStatusSnapshot.snapshot_at.asc())
            .all(),
            [],
            "hpa_snapshots_30m",
        )

        snapshots_24h = _safe_fetch(
            lambda: db.query(HpaStatusSnapshot)
            .filter(
                HpaStatusSnapshot.cluster_id == cluster_id,
                HpaStatusSnapshot.workload_name == _wn,
                HpaStatusSnapshot.snapshot_at > cutoff_24h,
            )
            .order_by(HpaStatusSnapshot.snapshot_at.asc())
            .all(),
            [],
            "hpa_snapshots_24h",
        )

        has_pending = workload_name in pending_pods_workloads
        status_str = _classify_hpa_status(cfg, snapshots_30m, snapshots_24h, has_pending)

        # G-T: scale_events_24h
        scale_events_24h = sum(
            1 for i in range(1, len(snapshots_24h))
            if (snapshots_24h[i].desired_replicas or 0) != (snapshots_24h[i - 1].desired_replicas or 0)
        ) if len(snapshots_24h) >= 2 else 0
        total_scale_events_24h += scale_events_24h

        # G-P: has_warning
        has_warning = (
            cfg.recommended_max_replicas is not None
            and cfg.max_replicas is not None
            and abs(cfg.max_replicas - cfg.recommended_max_replicas) > 2
        )

        # G-O: hpa_misconfigured count
        if (cfg.recommended_max_replicas is not None
                and cfg.max_replicas is not None
                and cfg.min_replicas is not None
                and cfg.recommended_min_replicas is not None
                and (
                    cfg.max_replicas > cfg.recommended_max_replicas * 1.5
                    or cfg.min_replicas < cfg.recommended_min_replicas
                )):
            hpa_misconfigured_count += 1

        workloads_out.append({
            "workload_id": f"{cfg.namespace}/{workload_name}",
            "namespace": cfg.namespace,
            "keda_managed": False,
            "status": status_str,
            "current_replicas": cfg.current_replicas,
            "desired_replicas": cfg.desired_replicas,
            "min_replicas": cfg.min_replicas,
            "max_replicas": cfg.max_replicas,
            "target_cpu_pct": cfg.target_cpu_pct,
            "recommended_max_replicas": cfg.recommended_max_replicas,
            "recommended_min_replicas": cfg.recommended_min_replicas,
            "has_warning": has_warning,
            "cooldown_assessment": _cooldown_assessment(cfg.scale_up_stabilization_seconds),
            "scale_events_24h": scale_events_24h,
            "recommendation_basis_label": _RECOMMENDATION_BASIS_LABEL,
        })

    freshness = compute_freshness(max_snapshot_at)
    data_ready = bool(configs) and not freshness["is_stale"]
    reason = "" if data_ready else ("hpa_data_pending" if not configs else "stale_data")
    return ok(
        {
            "cluster_id": cluster_id,
            "summary": {
                "hpa_misconfigured": hpa_misconfigured_count,
                "scale_events_24h": total_scale_events_24h,
                "tracked_workloads": len(workloads_out),
            },
            "workloads": workloads_out,
            **freshness,
        },
        data_ready=data_ready,
        data_ready_reason=reason,
    )


# ---------------------------------------------------------------------------
# T-21: GET /optimize/nodes/{node_name}/bin-packing-detail
# ---------------------------------------------------------------------------

@router.get("/nodes/{node_name}/bin-packing-detail", summary="Pod list for treemap on a specific node")
async def get_node_bin_packing_detail(
    node_name: str,
    cluster_id: str = Query(...),
    db: Session = Depends(get_db),
):
    validate_cluster_id(cluster_id)
    validate_node_name(node_name)
    assert_cluster_access(cluster_id, db)

    from backend.models.pod_metric import PodMetric
    from datetime import datetime as _dt, timedelta as _td

    cutoff = _dt.utcnow() - _td(minutes=30)  # match aggregate query window

    rows = (
        db.query(
            PodMetric.pod_name,
            PodMetric.namespace,
            PodMetric.cpu_request_millicores,
            PodMetric.memory_request_bytes,
            PodMetric.cpu_usage_millicores,
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

    pods = [
        {
            "pod_name": r.pod_name,
            "namespace": r.namespace,
            "cpu_request_millicores": r.cpu_request_millicores,
            "memory_request_bytes": r.memory_request_bytes,
            "cpu_usage_millicores": r.cpu_usage_millicores,
        }
        for r in rows
    ]

    from sqlalchemy import func as _bn_func
    max_pod_ts_node = _safe_fetch(
        lambda: db.query(_bn_func.max(PodMetric.timestamp))
        .filter(PodMetric.cluster_id == cluster_id, PodMetric.node_name == node_name)
        .scalar(),
        None, "bin_packing_detail_freshness",
    )
    freshness = compute_freshness(max_pod_ts_node)
    return ok({"node_name": node_name, "pod_count": len(pods), "pods": pods, **freshness})


# ---------------------------------------------------------------------------
# GET /optimize/nodes/cluster-execution-plan
# ---------------------------------------------------------------------------

@router.get("/nodes/cluster-execution-plan", summary="Current-vs-desired cluster transition plan")
async def get_cluster_execution_plan(
    cluster_id: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Full cluster transition plan (current state → desired state).

    Algorithm:
      1. Classify all workloads via WIE results in DB.
      2. Run PPE per workload — produces node_plan (drain/keep/provision) + movement_plan.
      3. Use packed_pods in provision entries to link drain nodes to their replacement
         provision node: a drain node is REPLACE if any of its pods land on a new
         provision node, else TERMINATE (pods consolidate onto existing nodes).
      4. Return per-node transitions with full pod routing so the UI can render
         "current node X → REPLACE by spot m5.large" or "TERMINATE, pods → existing node Y".
    """
    validate_cluster_id(cluster_id)
    assert_cluster_access(cluster_id, db)

    from backend.models.workload_classification import WorkloadClassificationRecord
    from backend.models.placement_policy import PlacementPolicyRecord
    from backend.models.pod_metric import PodMetric
    from backend.models.node_metadata import NodeMetadata
    from backend.models.node_metrics import NodeMetric
    from backend.models.cluster import ClusterOptimizationSettings as _ClusterOptSettings
    from backend.pipeline.stage3_ppe.engine import PodPlacementEngine
    from backend.pipeline.stage3_ppe.target_builder import build_targets as _build_targets
    from backend.core.redis_client import get_redis_client as _rl_rc
    from datetime import datetime as _dt, timedelta as _td

    _cutoff = _dt.utcnow() - _td(minutes=30)

    # ── Node metadata shared across all workloads ─────────────────────────────
    _node_rows = db.query(NodeMetadata).filter(NodeMetadata.cluster_id == cluster_id).all()
    _latest_nm = (
        db.query(NodeMetric.node_name, NodeMetric.cpu_usage_millicores, NodeMetric.memory_usage_bytes)
        .filter(NodeMetric.cluster_id == cluster_id)
        .distinct(NodeMetric.node_name)
        .order_by(NodeMetric.node_name, NodeMetric.timestamp.desc())
        .all()
    )
    _node_usage = {r.node_name: (r.cpu_usage_millicores or 0, r.memory_usage_bytes or 0) for r in _latest_nm}
    _node_meta_map = {}  # node_name → {instance_type, capacity_type, az}
    nodes_input = []
    for n in _node_rows:
        uc, um = _node_usage.get(n.node_name, (0, 0))
        _node_meta_map[n.node_name] = {
            "instance_type": n.instance_type,
            "capacity_type": n.capacity_type,
            "az": n.az,
        }
        nodes_input.append({
            "node_name": n.node_name,
            "az": n.az,
            "capacity_type": n.capacity_type,
            "instance_type": n.instance_type,
            "allocatable_cpu_millicores": n.allocatable_cpu_millicores,
            "allocatable_memory_bytes": n.allocatable_memory_bytes,
            "used_cpu_millicores": uc,
            "used_memory_bytes": um,
            "pod_count": 0,
        })

    # ── Per-node all-pod count (for UI display — excludes nothing) ─────────
    _SYSTEM_NS = frozenset(["kube-system", "kube-public", "kube-node-lease"])
    _pod_count_rows = (
        db.query(PodMetric.node_name, PodMetric.controller_kind, PodMetric.namespace)
        .filter(
            PodMetric.cluster_id == cluster_id,
            (PodMetric.phase == "Running") | (PodMetric.phase.is_(None)),
            PodMetric.timestamp > _cutoff,
        )
        .distinct(PodMetric.pod_name)
        .all()
    )
    _node_total_pods: dict = {}      # node_name → total pod count
    _node_system_pods: dict = {}     # node_name → DaemonSet + system ns count
    for _pr in _pod_count_rows:
        nn = _pr.node_name or ""
        _node_total_pods[nn] = _node_total_pods.get(nn, 0) + 1
        if (_pr.controller_kind == "DaemonSet") or ((_pr.namespace or "") in _SYSTEM_NS):
            _node_system_pods[nn] = _node_system_pods.get(nn, 0) + 1

    # ── Workload list ─────────────────────────────────────────────────────────
    wc_rows = (
        db.query(WorkloadClassificationRecord)
        .filter(WorkloadClassificationRecord.cluster_id == cluster_id)
        .order_by(WorkloadClassificationRecord.max_spot_replicas.desc().nullslast())
        .limit(25)
        .all()
    )

    # ── Per-node transition accumulator ──────────────────────────────────────
    # node_name → {"type": KEEP|TERMINATE|REPLACE, "replacement_spec": {...}|None,
    #               "pods_leaving": [...], "workload_class": str}
    node_transitions: dict = {}
    # Provision entries with their pod lists (for UI footer)
    global_provisions: list = []
    # Workload class + execution_strategy per drain node
    node_workload_meta: dict = {}  # node_name → {workload_class, execution_strategy}
    # Keep node metadata: instance_type, az, capacity_type, retention_reason
    node_keep_meta: dict = {}    # node_name → metadata dict
    _all_spot_decisions: list = []  # spot_migration_decision dicts from each workload PPE run

    for wc in wc_rows:
        workload_id = wc.workload_id
        controller_name = workload_id.split("/")[-1] if "/" in workload_id else workload_id
        try:
            pod_rows_w = (
                db.query(
                    PodMetric.pod_name,
                    PodMetric.namespace,
                    PodMetric.node_name,
                    PodMetric.controller_kind,
                    PodMetric.cpu_request_millicores,
                    PodMetric.memory_request_bytes,
                    PodMetric.cpu_usage_millicores,
                    PodMetric.memory_usage_bytes,
                )
                .filter(
                    PodMetric.cluster_id == cluster_id,
                    PodMetric.controller_name == controller_name,
                    PodMetric.controller_kind != "DaemonSet",
                    ~PodMetric.namespace.in_(list(_SYSTEM_NS)),
                    (PodMetric.phase == "Running") | (PodMetric.phase.is_(None)),
                    PodMetric.timestamp > _cutoff,
                )
                .distinct(PodMetric.pod_name)
                .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
                .all()
            )
            if not pod_rows_w:
                continue

            # Current pod → node mapping for this workload
            pod_current_node = {r.pod_name: r.node_name or "" for r in pod_rows_w}

            pods_w = [
                {
                    "pod_name": r.pod_name,
                    "namespace": r.namespace or "",
                    "node_name": r.node_name or "",
                    "az": _node_meta_map.get(r.node_name, {}).get("az") or "unknown",
                    "cpu_request_millicores": r.cpu_request_millicores or 0,
                    "memory_request_bytes": r.memory_request_bytes or 0,
                    "cpu_usage_millicores": r.cpu_usage_millicores or 0,
                    "memory_usage_bytes": r.memory_usage_bytes or 0,
                    "workload_id": workload_id,
                }
                for r in pod_rows_w
            ]

            _wie_w = {
                "spot_friendly": wc.spot_friendly,
                "spot_score": wc.spot_score,
                "role": wc.role,
                "min_on_demand_replicas": wc.min_on_demand_replicas,
                "max_spot_replicas": wc.max_spot_replicas,
                "workload_class": getattr(wc, "workload_class", "stateless") or "stateless",
                "disruption_safe": True,
            }

            pp = (
                db.query(PlacementPolicyRecord)
                .filter(
                    PlacementPolicyRecord.cluster_id == cluster_id,
                    PlacementPolicyRecord.workload_id == workload_id,
                )
                .first()
            )
            total_pods = len(pods_w)

            # ── Target Builder gate: skip workloads already at desired distribution ──
            _targets = _build_targets(
                classifications=[{
                    "namespace": wc.namespace,
                    "controller_name": wc.name,
                    "controller_kind": wc.controller_kind,
                    "workload_class": getattr(wc, "workload_class", "stateless") or "stateless",
                    "min_on_demand_replicas": wc.min_on_demand_replicas,
                    "max_spot_replicas": wc.max_spot_replicas,
                    "total_replicas": getattr(wc, "total_replicas", total_pods) or total_pods,
                }],
                live_pods=pods_w,
                live_nodes=nodes_input,
            )
            if _targets and not _targets[0].action_required:
                continue

            if pp and pp.ondemand_target is not None and pp.spot_target is not None:
                _od_t, _sp_t = pp.ondemand_target, pp.spot_target
            elif wc.min_on_demand_replicas is not None and wc.max_spot_replicas is not None:
                _od_t, _sp_t = int(wc.min_on_demand_replicas), int(wc.max_spot_replicas)
            elif not wc.spot_friendly:
                _od_t, _sp_t = total_pods, 0
            else:
                _sp_t = max(0, total_pods - 1)
                _od_t = min(1, total_pods)

            _plan_w = PodPlacementEngine.materialize_plan(
                pods=pods_w,
                nodes=nodes_input,
                wie=_wie_w,
                targets={"ondemand_target": _od_t, "spot_target": _sp_t, "observed_replicas": total_pods},
                cooldown_pods=set(),
                cluster_id=cluster_id,
            )
            _pd = _plan_w.to_dict()
            if _pd.get("spot_migration_decision"):
                _all_spot_decisions.append(_pd["spot_migration_decision"])

            # ── Step 1: Build pod → provision spec map using packed_pods ──────
            # packed_pods in a provision entry are the pods that NEED a new node.
            # Their current node (from pod_current_node) is the drain node being REPLACED.
            # Build a virtual-node-id → prov_spec reverse map (for movement_plan lookup)
            vnode_to_prov_spec: dict = {}  # virtual_node_id → provision spec dict
            pod_to_prov_spec: dict = {}  # pod_name → provision spec dict (from packed_pods)
            for np_entry in (_pd.get("node_plan") or []):
                if np_entry.get("action") != "provision":
                    continue
                # Prefer virtual_node_id; fall back to node_name for backward compat
                _vid = np_entry.get("virtual_node_id") or np_entry.get("node_name", "")
                prov_spec = {
                    "prov_node_name": _vid,
                    "capacity_type": np_entry.get("capacity_type", "spot"),
                    "az": np_entry.get("az"),
                    "instance_type": np_entry.get("instance_type"),
                    "pod_count": np_entry.get("pod_count", 0),
                }
                if _vid:
                    vnode_to_prov_spec[_vid] = prov_spec
                for packed_pod in (np_entry.get("packed_pods") or []):
                    pname = packed_pod.get("pod_name", "")
                    if pname:
                        pod_to_prov_spec[pname] = prov_spec
                # Also collect for global provision list
                global_provisions.append({
                    **prov_spec,
                    "pods": [
                        {
                            "pod_name": p.get("pod_name"),
                            "cpu_request_millicores": p.get("cpu_request_millicores"),
                            "memory_request_mb": round((p.get("memory_request_bytes") or 0) / (1024 * 1024), 1),
                        }
                        for p in (np_entry.get("packed_pods") or [])
                    ],
                })

            # ── Step 2: Process node_plan drain/keep actions ──────────────────
            for np_entry in (_pd.get("node_plan") or []):
                nname = np_entry.get("node_name") or ""
                action = np_entry.get("action", "keep")
                if not nname or action == "provision":
                    continue
                if action == "drain":
                    if node_transitions.get(nname, {}).get("type") not in ("TERMINATE", "REPLACE"):
                        node_transitions[nname] = {"type": "TERMINATE", "replacement_spec": None, "pods_leaving": []}
                    # Track workload_class + execution_strategy for this drain node
                    _wclass = _wie_w.get("workload_class", "stateless")
                    _exec_strat = (
                        "SERIAL" if _wclass == "db" else
                        "BLUE_GREEN" if _wclass in ("stateful", "mixed") else
                        "ROLLING"
                    )
                    if nname not in node_workload_meta:
                        node_workload_meta[nname] = {"workload_class": _wclass, "execution_strategy": _exec_strat}
                elif action == "keep":
                    if nname not in node_transitions:
                        node_transitions[nname] = {"type": "KEEP", "replacement_spec": None, "pods_leaving": []}
                    # Collect keep node metadata for rich keep_nodes output
                    if nname not in node_keep_meta:
                        _cap = (np_entry.get("capacity_type") or "").lower()
                        _is_od = _cap in ("on-demand", "on_demand", "ondemand")
                        _ppr = np_entry.get("reason")
                        node_keep_meta[nname] = {
                            "capacity_type": np_entry.get("capacity_type"),
                            "az": np_entry.get("az"),
                            "instance_type": np_entry.get("instance_type"),
                            "pod_count": np_entry.get("pod_count", 0),
                            "retention_reason": (
                                "drain_reuse" if _ppr == "drain_reuse"
                                else "od_anchor" if _is_od
                                else "fits_pods"
                            ),
                        }

            # ── Step 3: Map movement_plan pods to their transitions ────────────
            for mv in (_pd.get("movement_plan") or []):
                fn = mv.get("from_node") or ""
                if not fn:
                    continue
                trans = node_transitions.get(fn)
                if not trans or trans["type"] == "KEEP":
                    continue  # pod is staying on a keep node, no movement needed

                pod_name = mv.get("pod_name", "")
                to_node_existing = mv.get("to_node")  # real existing node or None
                to_virtual  = mv.get("to_virtual_node")  # synthetic provision ID or None
                to_cap = mv.get("to_capacity_type", "spot")

                # Check if this pod is mapped to a provision node.
                # Primary: packed_pods index (exact CapacityPlanner assignment).
                # Secondary: to_virtual_node in the movement step (BinPacker assignment).
                prov = pod_to_prov_spec.get(pod_name) or (
                    vnode_to_prov_spec.get(to_virtual) if to_virtual else None
                )
                if prov:
                    # Pod goes to NEW provision node → REPLACE
                    trans["type"] = "REPLACE"
                    # replacement_spec: use the first provision entry (representative)
                    if trans["replacement_spec"] is None:
                        trans["replacement_spec"] = {
                            "capacity_type": prov["capacity_type"],
                            "az": prov["az"],
                            "instance_type": prov["instance_type"],
                            "prov_node_name": prov["prov_node_name"],
                        }
                    trans["pods_leaving"].append({
                        "pod_name": pod_name,
                        "to_node": prov["prov_node_name"],          # synthetic virtual ID
                        "to_virtual_node": prov["prov_node_name"],  # explicit virtual field
                        "to_instance_type": prov["instance_type"],
                        "to_capacity_type": prov["capacity_type"],
                        "is_new_node": True,
                    })
                else:
                    # Pod moves to existing node (consolidation / TERMINATE scenario)
                    to_itype = _node_meta_map.get(to_node_existing, {}).get("instance_type") if to_node_existing else None
                    to_cap_existing = _node_meta_map.get(to_node_existing, {}).get("capacity_type", to_cap) if to_node_existing else to_cap
                    trans["pods_leaving"].append({
                        "pod_name": pod_name,
                        "to_node": to_node_existing,
                        "to_instance_type": to_itype,
                        "to_capacity_type": to_cap_existing,
                        "is_new_node": False,
                    })

        except Exception as _e:
            logger.debug(f"cluster_plan_ppe_skip workload={workload_id} err={_e}")
            continue

    # ── AZ-Spread consolidation (enforced when min_topology_spread > 1) ──────
    # When the workload loop found no action needed (all pods already on OD,
    # no spot migration required), we still need to honour the user's minimum
    # AZ spread setting.  We select min_topology_spread nodes to keep
    # (one per AZ, most-loaded first) and mark the remaining nodes as
    # TERMINATE so the UI can show the bin-packed consolidation plan.
    _opt_cfg = db.query(_ClusterOptSettings).filter(
        _ClusterOptSettings.cluster_id == cluster_id
    ).first()
    _min_az_spread = int(getattr(_opt_cfg, 'min_topology_spread', 1) or 1) if _opt_cfg else 1

    _az_spread_applied = False
    if _min_az_spread > 1 and nodes_input:
        # Group all real nodes by AZ
        _az_to_nodes: dict = {}
        for _ni in nodes_input:
            _az = _ni.get('az') or 'unknown'
            _az_to_nodes.setdefault(_az, []).append(_ni)

        # Collect AZs already represented by existing keep entries
        _az_already_kept: dict = {}  # az → node_name
        for _nname, _trans in node_transitions.items():
            if _trans['type'] == 'KEEP':
                for _ni in nodes_input:
                    if _ni['node_name'] == _nname:
                        _az_already_kept[_ni.get('az') or 'unknown'] = _nname
                        break

        # Fill remaining AZs up to min_topology_spread, picking the most-loaded node
        _sorted_azs = sorted(
            _az_to_nodes.keys(),
            key=lambda a: sum(_node_total_pods.get(n['node_name'], 0) for n in _az_to_nodes[a]),
            reverse=True,
        )
        for _az in _sorted_azs:
            if len(_az_already_kept) >= _min_az_spread:
                break
            if _az in _az_already_kept:
                continue
            # Pick most-loaded node in this AZ as the anchor
            _az_nodes_sorted = sorted(
                _az_to_nodes[_az],
                key=lambda n: _node_total_pods.get(n['node_name'], 0),
                reverse=True,
            )
            _chosen = _az_nodes_sorted[0]['node_name']
            _az_already_kept[_az] = _chosen

        _spread_keep_names = set(_az_already_kept.values())

        # Force-keep the selected nodes
        for _nname in _spread_keep_names:
            if _nname not in node_transitions:
                _nmeta = next((n for n in nodes_input if n['node_name'] == _nname), {})
                _cap = _nmeta.get('capacity_type', '') or ''
                _is_od = _cap.lower() in ('on-demand', 'on_demand', 'ondemand')
                node_transitions[_nname] = {'type': 'KEEP', 'replacement_spec': None, 'pods_leaving': []}
                node_keep_meta[_nname] = {
                    'capacity_type': _cap,
                    'az': _nmeta.get('az'),
                    'instance_type': _nmeta.get('instance_type'),
                    'pod_count': _node_total_pods.get(_nname, 0),
                    'retention_reason': 'az_spread',
                }

        # Nodes NOT in the kept set → TERMINATE (consolidation candidates)
        # Build round-robin bin-pack: assign their user pods to kept nodes
        _keep_list_ordered = sorted(
            list(_spread_keep_names),
            key=lambda n: _node_total_pods.get(n, 0),
        )  # least-loaded first gets pods assigned
        _rr_idx = 0

        for _ni in nodes_input:
            _nname = _ni['node_name']
            if _nname in _spread_keep_names:
                continue
            # Only add a TERMINATE entry if there are user (non-system) pods to move
            _total_p = _node_total_pods.get(_nname, 0)
            _sys_p   = _node_system_pods.get(_nname, 0)
            _user_p  = _total_p - _sys_p
            if _user_p <= 0:
                continue
            if _nname not in node_transitions:
                node_transitions[_nname] = {'type': 'TERMINATE', 'replacement_spec': None, 'pods_leaving': []}
                node_workload_meta[_nname] = {'workload_class': 'stateless', 'execution_strategy': 'ROLLING'}
                _az_spread_applied = True

            # Fetch the actual user pod names for this drain node (last 30 min, non-system, non-DS)
            _SYSTEM_NS_AZ = frozenset(['kube-system', 'kube-public', 'kube-node-lease'])
            _pod_rows_drain = (
                db.query(PodMetric.pod_name, PodMetric.namespace)
                .filter(
                    PodMetric.cluster_id == cluster_id,
                    PodMetric.node_name == _nname,
                    PodMetric.controller_kind != 'DaemonSet',
                    ~PodMetric.namespace.in_(list(_SYSTEM_NS_AZ)),
                    PodMetric.timestamp > _cutoff,
                )
                .distinct(PodMetric.pod_name)
                .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
                .limit(50)
                .all()
            )
            for _pr in _pod_rows_drain:
                if not _keep_list_ordered:
                    break
                _dest_node = _keep_list_ordered[_rr_idx % len(_keep_list_ordered)]
                _rr_idx += 1
                node_transitions[_nname]['pods_leaving'].append({
                    'pod_name': _pr.pod_name,
                    'to_node': _dest_node,
                    'to_instance_type': _node_meta_map.get(_dest_node, {}).get('instance_type'),
                    'to_capacity_type': _node_meta_map.get(_dest_node, {}).get('capacity_type', 'ON_DEMAND'),
                    'is_new_node': False,
                })

    # ── Format output ─────────────────────────────────────────────────────────
    drain_nodes = []
    keep_nodes  = []
    for nname, trans in node_transitions.items():
        nm    = _node_meta_map.get(nname, {})
        wmeta = node_workload_meta.get(nname, {})
        if trans["type"] in ("TERMINATE", "REPLACE"):
            drain_nodes.append({
                "node_name": nname,
                "current_instance_type": nm.get("instance_type"),
                "current_capacity_type": nm.get("capacity_type"),
                "current_az": nm.get("az"),
                "transition_type": trans["type"],
                "replacement_spec": trans["replacement_spec"],
                "pods_leaving": trans["pods_leaving"],
                "total_pods_on_node": _node_total_pods.get(nname, 0),
                "system_pods_on_node": _node_system_pods.get(nname, 0),
                "workload_class": wmeta.get("workload_class", "stateless"),
                "execution_strategy": wmeta.get("execution_strategy", "ROLLING"),
            })
        else:
            # Rich keep node object — replaces plain string list
            kmeta = node_keep_meta.get(nname, {})
            _cap_nm = nm.get("capacity_type") or kmeta.get("capacity_type", "")
            _is_od  = (_cap_nm or "").lower() in ("on-demand", "on_demand", "ondemand")
            keep_nodes.append({
                "node_name":        nname,
                "instance_type":    nm.get("instance_type") or kmeta.get("instance_type"),
                "capacity_type":    _cap_nm,
                "az":               nm.get("az") or kmeta.get("az"),
                "pod_count":        kmeta.get("pod_count") or nm.get("pod_count"),
                "retention_reason": kmeta.get("retention_reason") or (
                    "od_anchor" if _is_od else "fits_pods"
                ),
                "retained_workload_classes": [],  # populated when PPE tracks per-keep workload classes
            })

    # Deduplicate provision nodes, attach stable plan_node_id
    seen_prov = set()
    deduped_provisions = []
    for p in global_provisions:
        key = p.get("prov_node_name", "")
        if key and key not in seen_prov:
            seen_prov.add(key)
            plan_node_id = "pn-" + hashlib.sha256(
                f"{cluster_id}:{key}".encode()
            ).hexdigest()[:10]
            deduped_provisions.append({**p, "plan_node_id": plan_node_id})

    # plan_status — authoritative completeness signal consumed by frontend planCompleteness
    _resolved_cnt = sum(1 for p in deduped_provisions if p.get("instance_type"))
    if not deduped_provisions and not drain_nodes:
        plan_status = "no_action"
    elif not deduped_provisions and _az_spread_applied:
        plan_status = "az_spread"   # consolidation driven by min AZ spread setting
    elif not deduped_provisions and drain_nodes:
        plan_status = "consolidation"  # bin-pack pods onto existing nodes, no new provisioning needed
    elif _resolved_cnt == len(deduped_provisions):
        plan_status = "resolved"
    elif _resolved_cnt > 0:
        plan_status = "partial"
    else:
        plan_status = "draft"

    summary = {
        "nodes_terminate": sum(1 for d in drain_nodes if d["transition_type"] == "TERMINATE"),
        "nodes_replace":   sum(1 for d in drain_nodes if d["transition_type"] == "REPLACE"),
        "nodes_keep":      len(keep_nodes),
        "new_nodes_needed": len(deduped_provisions),
        "workloads_processed": len(wc_rows),
        "min_az_spread": _min_az_spread,
    }

    # Aggregate spot_migration_decision: surface the most informative entry
    # (conflict > not_needed > executed) so the UI can show one canonical explanation.
    _REASON_PRIORITY = {
        "spot_target_not_set_by_orchestrator":         4,
        "confidence_provisional_conservative_od_preferred": 3,
        "disruption_safety_blocked_all_spot_pods":     2,
        "existing_od_capacity_absorbed_spot_pods":     1,
        "spot_migration_not_needed":                   0,
        "spot_migration_executed":                    -1,
    }
    _agg_spot_decision: dict = {}
    if _all_spot_decisions:
        _agg_spot_decision = max(
            _all_spot_decisions,
            key=lambda d: _REASON_PRIORITY.get(d.get("reason", ""), 0),
        )

    return ok({
        "cluster_id":             cluster_id,
        "plan_status":            plan_status,
        "drain_nodes":            drain_nodes,
        "keep_nodes":             keep_nodes,
        "provision_nodes":        deduped_provisions,
        "summary":                summary,
        "spot_migration_decision": _agg_spot_decision,
    })


# ---------------------------------------------------------------------------
# GET /optimize/nodes/{node_name}/execution-plan
# ---------------------------------------------------------------------------

@router.get("/nodes/{node_name}/execution-plan", summary="Per-node execution plan: current pods + pending actions + optimization target")
async def get_node_execution_plan(
    node_name: str,
    cluster_id: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Returns a full per-node execution plan:
    - current_pods: pods currently running on this node (latest metrics)
    - pending_actions: agent actions in flight for this node (evictions, drains, terminates)
    - optimization_target: engine-derived recommendation (consolidate, terminate, etc.)
    - node_meta: instance type, capacity type, AZ, resource utilisation
    """
    validate_cluster_id(cluster_id)
    validate_node_name(node_name)
    assert_cluster_access(cluster_id, db)

    from backend.models.pod_metric import PodMetric
    from backend.models.node_metadata import NodeMetadata
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
    from sqlalchemy import func as _fn
    from datetime import datetime as _dt, timedelta as _td

    cutoff = _dt.utcnow() - _td(minutes=30)

    # ── Current pods on this node ─────────────────────────────────────────────
    pod_rows = (
        db.query(
            PodMetric.pod_name,
            PodMetric.namespace,
            PodMetric.controller_name,
            PodMetric.cpu_request_millicores,
            PodMetric.memory_request_bytes,
            PodMetric.cpu_usage_millicores,
            PodMetric.memory_usage_bytes,
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

    current_pods = [
        {
            "pod_name": r.pod_name,
            "namespace": r.namespace,
            "controller": r.controller_name,
            "cpu_request_millicores": r.cpu_request_millicores,
            "memory_request_mb": round((r.memory_request_bytes or 0) / (1024 * 1024), 1),
            "cpu_usage_millicores": r.cpu_usage_millicores,
        }
        for r in pod_rows
    ]

    # ── Node metadata ─────────────────────────────────────────────────────────
    node_meta_row = (
        db.query(NodeMetadata)
        .filter(NodeMetadata.cluster_id == cluster_id, NodeMetadata.node_name == node_name)
        .first()
    )
    node_meta = None
    if node_meta_row:
        node_meta = {
            "instance_type": node_meta_row.instance_type,
            "capacity_type": node_meta_row.capacity_type,
            "az": node_meta_row.az,
            "allocatable_cpu_millicores": node_meta_row.allocatable_cpu_millicores,
            "allocatable_memory_gib": round((node_meta_row.allocatable_memory_bytes or 0) / (1024 ** 3), 1),
            "is_ready": node_meta_row.is_ready,
            "do_not_disrupt": node_meta_row.do_not_disrupt,
        }

    # ── Pending agent actions for this node ───────────────────────────────────
    _node_action_types = [
        AgentActionType.DRAIN_NODE,
        AgentActionType.CORDON_NODE,
        AgentActionType.TERMINATE_NODE,
        AgentActionType.FORCE_DELETE_NODE,
        AgentActionType.UNCORDON_NODE,
    ]
    node_action_rows = (
        db.query(
            AgentAction.id,
            AgentAction.action_type,
            AgentAction.status,
            AgentAction.payload,
            AgentAction.created_at,
        )
        .filter(
            AgentAction.cluster_id == cluster_id,
            AgentAction.action_type.in_(_node_action_types),
            AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
            AgentAction.payload["node_name"].astext == node_name,
        )
        .order_by(AgentAction.created_at.desc())
        .limit(10)
        .all()
    )

    # Evictions of pods currently on this node
    eviction_rows = (
        db.query(
            AgentAction.id,
            AgentAction.payload,
            AgentAction.status,
            AgentAction.created_at,
        )
        .filter(
            AgentAction.cluster_id == cluster_id,
            AgentAction.action_type == AgentActionType.EVICT_POD,
            AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
        )
        .order_by(AgentAction.created_at.desc())
        .limit(50)
        .all()
    )

    # Match evictions to current pods on this node
    current_pod_names = {p["pod_name"] for p in current_pods}
    pending_evictions = [
        {
            "action_id": str(r.id),
            "pod_name": r.payload.get("pod_name"),
            "namespace": r.payload.get("namespace"),
            "status": r.status.value,
            "queued_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in eviction_rows
        if r.payload.get("pod_name") in current_pod_names
    ]

    pending_node_actions = [
        {
            "action_id": str(r.id),
            "action_type": r.action_type.value,
            "status": r.status.value,
            "queued_at": r.created_at.isoformat() if r.created_at else None,
            "payload": r.payload,
        }
        for r in node_action_rows
    ]

    # ── Derive optimization target from utilisation + lifecycle ───────────────
    # Compute buffer from current pods vs node allocatable
    alloc_cpu = float(node_meta_row.allocatable_cpu_millicores or 1) if node_meta_row else 1.0
    alloc_mem = float(node_meta_row.allocatable_memory_bytes or 1) if node_meta_row else 1.0
    used_cpu = sum(p.get("cpu_usage_millicores") or 0 for p in current_pods)
    used_mem_bytes = sum((r.memory_usage_bytes or 0) for r in pod_rows)
    cpu_buf_pct  = round(max(0.0, 100.0 - (used_cpu / alloc_cpu * 100)), 1)
    mem_buf_pct  = round(max(0.0, 100.0 - (used_mem_bytes / alloc_mem * 100)), 1)
    is_overloaded = (used_cpu / alloc_cpu * 100) > 85 or (used_mem_bytes / alloc_mem * 100) > 85

    has_drain = any(a["action_type"] in ("DRAIN_NODE", "TERMINATE_NODE", "FORCE_DELETE_NODE") for a in pending_node_actions)
    has_cordon = any(a["action_type"] == "CORDON_NODE" for a in pending_node_actions)
    cap_type = (node_meta_row.capacity_type or "").lower() if node_meta_row else ""
    is_od = cap_type in ("on_demand", "on-demand", "ondemand")

    if has_drain:
        opt_action = "Terminating"
        opt_detail = "Drain action queued — pods are being migrated away from this node."
        opt_color  = "red"
    elif has_cordon:
        opt_action = "Cordoned"
        opt_detail = "Cordon action queued — no new pods will be scheduled here."
        opt_color  = "amber"
    elif is_overloaded:
        opt_action = "Scale Up / Redistribute"
        opt_detail = f"Node is overloaded — redistribute pods or add capacity."
        opt_color  = "red"
    elif cpu_buf_pct > 80 and mem_buf_pct > 80 and is_od:
        opt_action = "Consolidate → Spot"
        opt_detail = f"{cpu_buf_pct}% CPU free, {mem_buf_pct}% mem free — heavily underutilised OD node; strong spot migration candidate."
        opt_color  = "blue"
    elif cpu_buf_pct > 70 and mem_buf_pct > 70:
        opt_action = "Consolidate"
        opt_detail = f"{cpu_buf_pct}% CPU free, {mem_buf_pct}% mem free — underutilised; candidate for workload consolidation."
        opt_color  = "indigo"
    elif is_od and cpu_buf_pct > 40 and mem_buf_pct > 40:
        opt_action = "Spot Migration Opportunity"
        opt_detail = f"On-demand node with {cpu_buf_pct}% CPU / {mem_buf_pct}% mem free — evaluate migrating spot-friendly workloads."
        opt_color  = "violet"
    else:
        opt_action = "Optimal"
        opt_detail = "Utilisation is healthy — no immediate action needed."
        opt_color  = "green"

    optimization_target = {
        "action": opt_action,
        "detail": opt_detail,
        "color": opt_color,
        "cpu_buffer_pct": cpu_buf_pct,
        "mem_buffer_pct": mem_buf_pct,
        "is_overloaded": is_overloaded,
    }

    max_pod_ts = _safe_fetch(
        lambda: db.query(_fn.max(PodMetric.timestamp))
        .filter(PodMetric.cluster_id == cluster_id, PodMetric.node_name == node_name)
        .scalar(),
        None, "node_execution_plan_freshness",
    )
    freshness = compute_freshness(max_pod_ts)

    return ok({
        "node_name": node_name,
        "cluster_id": cluster_id,
        "node_meta": node_meta,
        "current_pods": current_pods,
        "pending_evictions": pending_evictions,
        "pending_node_actions": pending_node_actions,
        "optimization_target": optimization_target,
        **freshness,
    })


# ---------------------------------------------------------------------------
# T-22: GET /optimize/workloads/{workload_id}/profiling-detail
# ---------------------------------------------------------------------------

@router.get("/workloads/{workload_id:path}/profiling-detail", summary="14-day CPU time-series + workload profiling data")
async def get_workload_profiling_detail(
    workload_id: str,
    cluster_id: str = Query(...),
    db: Session = Depends(get_db),
):
    validate_cluster_id(cluster_id)
    validate_workload_id(workload_id)
    assert_cluster_access(cluster_id, db)

    from backend.models.pod_metric import PodMetric
    from backend.models.workload_classification import WorkloadClassificationRecord
    from backend.models.placement_policy import PlacementPolicyRecord
    from sqlalchemy import func
    from datetime import datetime as _dt, timedelta as _td

    workload_name = workload_id.split("/")[-1] if "/" in workload_id else workload_id
    cutoff_14d = _dt.utcnow() - _td(days=14)

    # P-01: freshness anchor — MAX(pod_metrics.timestamp) for this workload
    max_pm_ts = (
        db.query(func.max(PodMetric.timestamp))
        .filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.controller_name == workload_name,
        )
        .scalar()
    )

    ts_rows = (
        db.query(
            func.date_trunc("day", PodMetric.timestamp).label("day"),
            func.avg(PodMetric.cpu_usage_millicores).label("avg_cpu_millicores"),
            func.avg(PodMetric.memory_usage_bytes).label("avg_mem_bytes"),
        )
        .filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.controller_name == workload_name,
            PodMetric.timestamp > cutoff_14d,
        )
        .group_by(func.date_trunc("day", PodMetric.timestamp))
        .order_by("day")
        .all()
    )

    cpu_timeseries = [
        {
            "day": r.day.date().isoformat() if r.day else None,
            "avg_cpu_millicores": round(r.avg_cpu_millicores or 0),
            "avg_mem_bytes": round(r.avg_mem_bytes or 0),
        }
        for r in ts_rows
    ]

    wc = (
        db.query(WorkloadClassificationRecord)
        .filter(
            WorkloadClassificationRecord.cluster_id == cluster_id,
            WorkloadClassificationRecord.workload_id == workload_id,
        )
        .first()
    )

    pp = (
        db.query(PlacementPolicyRecord)
        .filter(
            PlacementPolicyRecord.cluster_id == cluster_id,
            PlacementPolicyRecord.workload_id == workload_id,
        )
        .first()
    )

    freshness = compute_freshness(max_pm_ts)
    data_ready = max_pm_ts is not None and not freshness["is_stale"]
    reason = "" if data_ready else ("insufficient_history" if max_pm_ts is None else "stale_data")
    cpu_cv_value = (
        (pp.pod_cpu_cv if pp and pp.pod_cpu_cv is not None else None)
        or (wc.cpu_cv if wc else None)
    )
    traffic_skew = (
        (pp.traffic_skew_detected if pp and pp.traffic_skew_detected is not None else None)
        or (wc.traffic_skew_detected if wc else None)
    )
    return ok(
        {
            "workload_id": workload_id,
            "tier": wc.tier if wc else None,
            "spot_score": wc.spot_score if wc else None,
            "confidence_state": wc.confidence_state if wc else None,
            "criticality_score": wc.criticality_score if wc else None,
            "spot_friendly": wc.spot_friendly if wc else None,
            "data_safety": wc.data_safety if wc else None,
            "min_on_demand_replicas": wc.min_on_demand_replicas if wc else None,
            "max_spot_replicas": wc.max_spot_replicas if wc else None,
            "cpu_cv": cpu_cv_value,
            "traffic_skew_detected": traffic_skew,
            "estimated_monthly_saving_usd": pp.estimated_monthly_saving_usd if pp else None,
            "ondemand_target": pp.ondemand_target if pp else None,
            "spot_target": pp.spot_target if pp else None,
            "total_replicas": (pp.ondemand_target or 0) + (pp.spot_target or 0) if pp else None,
            "rollout_eligible": pp.rollout_eligible if pp else None,
            "rollout_blocked_reason": pp.rollout_blocked_reason if pp else None,
            "cpu_timeseries": cpu_timeseries,
            **freshness,
        },
        data_ready=data_ready,
        data_ready_reason=reason,
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# POST /optimize/workloads/{workload_id}/rebalance-az — AZ topology trigger
# ---------------------------------------------------------------------------

@router.post("/workloads/{workload_id:path}/rebalance-az", summary="Trigger AZ-rebalancing for a workload")
def trigger_az_rebalance(
    workload_id: str,
    cluster_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Writes a Redis hint key then triggers a PlacementController cycle.
    The PC already selects pods from the over-represented AZ via
    _build_capacity_map() — no engine modification needed.

    Note: A RebalancingAction is NOT created here because source_pool/target_pool
    are NOT NULL columns that must be in 'instance_type:az' format, which does not
    apply to an AZ-balance request. The PC's eviction logic handles pod targeting.
    """
    validate_cluster_id(cluster_id)
    validate_workload_id(workload_id)
    assert_cluster_access(cluster_id, db)

    from backend.core.redis_client import get_redis_client as _grc_az
    from backend.workers.tasks.placement_controller_task import run_placement_controller_task
    from fastapi import HTTPException

    _r = _grc_az()

    # WP-5: Guard — reject if workload cooldown is active
    cooldown_key = f"spot:placement_controller:workload_cooldown:{cluster_id}:{workload_id}"
    try:
        if _r and _r.exists(cooldown_key):
            ttl = _r.ttl(cooldown_key)
            raise HTTPException(status_code=409, detail=f"Workload cooldown active — retry in {ttl}s")
    except HTTPException:
        raise
    except Exception:
        pass

    # WP-5: Guard — reject if policy says rollout is not eligible
    pp = (
        db.query(PlacementPolicyRecord)
        .filter(
            PlacementPolicyRecord.cluster_id == cluster_id,
            PlacementPolicyRecord.workload_id == workload_id,
        )
        .first()
    )
    if pp is not None and pp.rollout_eligible is False:
        raise HTTPException(
            status_code=409,
            detail=f"Rollout not eligible: {pp.rollout_blocked_reason or 'see placement policy'}",
        )

    hint_key = f"spot:placement:az_rebalance_requested:{cluster_id}:{workload_id}"
    try:
        if _r:
            _r.setex(hint_key, 600, "1")  # 10-min TTL
    except Exception:
        pass  # non-blocking

    run_placement_controller_task.apply_async(args=[cluster_id])
    return {"status": "queued", "workload_id": workload_id, "cluster_id": cluster_id}


# ---------------------------------------------------------------------------
# GET /optimize/workloads/{workload_id}/rebalancing — active node operations
# ---------------------------------------------------------------------------

@router.get("/workloads/{workload_id:path}/rebalancing", summary="Active rebalancing operations affecting a workload")
def get_active_rebalancing(
    workload_id: str,
    cluster_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns in-progress RebalancingAction records relevant to this workload:
    - Pod-level / stateful_pod: joined through agent_action_id → AgentAction.workload_id
    - Node-level: all active cluster-level operations (no workload FK on node actions)
    """
    validate_cluster_id(cluster_id)
    assert_cluster_access(cluster_id, db)

    from backend.models.rebalancing_action import RebalancingAction

    _ACTIVE = ["in_progress"]

    pod_level = (
        db.query(RebalancingAction)
        .join(AgentAction, RebalancingAction.agent_action_id == AgentAction.id)
        .filter(
            RebalancingAction.cluster_id == cluster_id,
            RebalancingAction.status.in_(_ACTIVE),
            RebalancingAction.migration_type.in_(["pod_level", "stateful_pod"]),
            AgentAction.payload.op("->>")(  # JSONB text extraction
                "workload_id"
            ) == workload_id,
        )
        .order_by(RebalancingAction.created_at.desc())
        .limit(5)
        .all()
    )

    node_level = (
        db.query(RebalancingAction)
        .filter(
            RebalancingAction.cluster_id == cluster_id,
            RebalancingAction.status.in_(_ACTIVE),
            RebalancingAction.migration_type == "node_level",
        )
        .order_by(RebalancingAction.created_at.desc())
        .limit(5)
        .all()
    )

    def _serialize(a: "RebalancingAction", scope: str) -> dict:
        return {
            "id": str(a.id),
            "scope": scope,
            "trigger": a.trigger,
            "current_state": a.current_state or a.status,
            "migration_type": a.migration_type,
            "source_pool": a.source_pool,
            "target_pool": a.target_pool,
            "started_at": a.started_at.isoformat() if a.started_at else None,
            "source_instance_id": a.source_instance_id,
        }

    return {
        "active_operations": (
            [_serialize(a, "workload") for a in pod_level]
            + [_serialize(a, "cluster_node") for a in node_level]
        )
    }


# T-23: GET /optimize/workloads/placement (paginated list)
#        GET /optimize/workloads/{workload_id}/placement-detail
# ---------------------------------------------------------------------------

_STATE_TO_STEP: Dict[str, int] = {
    "PENDING":        0,
    "ANALYZING":      1,
    "POLICY_SET":     2,
    "DRIFT_DETECTED": 3,
    "EVICTING":       3,
    "VALIDATING":     4,
    "AT_TARGET":      5,
    "STABLE":         5,
}


def _derive_pod_counts_from_db(cluster_id: str, workload_id: str, db) -> tuple:
    """
    WP-1: Derive current spot/OD pod counts from PodMetric + NodeMetadata when
    the Redis spot:workload:state key is absent or stale.
    Returns (current_spot, current_od).
    """
    from backend.models.node_metadata import NodeMetadata

    controller_name = workload_id.split("/")[-1] if "/" in workload_id else workload_id
    try:
        latest_subq = (
            db.query(PodMetric.pod_name, PodMetric.node_name)
            .filter(
                PodMetric.cluster_id == cluster_id,
                PodMetric.controller_name == controller_name,
                PodMetric.phase == "Running",
            )
            .distinct(PodMetric.pod_name)
            .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
            .subquery()
        )
        pod_rows = (
            db.query(latest_subq.c.pod_name, NodeMetadata.capacity_type)
            .join(
                NodeMetadata,
                (NodeMetadata.cluster_id == cluster_id)
                & (NodeMetadata.node_name == latest_subq.c.node_name),
                isouter=True,
            )
            .all()
        )
        spot = sum(1 for r in pod_rows if (r.capacity_type or "").lower() in ("spot",))
        od = sum(1 for r in pod_rows if (r.capacity_type or "").lower() in ("on-demand", "on_demand", "ondemand"))
        if not pod_rows:
            return None, None
        return spot, od
    except Exception:
        return None, None


def _get_placement_workload_rows(cluster_id: str, db, redis_client):
    """
    Shared helper for T-06 placement/summary and T-23 placement list.
    Returns a list of dicts with per-workload placement fields.
    """
    from backend.models.workload_classification import WorkloadClassificationRecord
    from backend.models.placement_policy import PlacementPolicyRecord
    from backend.models.node_metadata import NodeMetadata

    classified = (
        db.query(WorkloadClassificationRecord)
        .filter(WorkloadClassificationRecord.cluster_id == cluster_id)
        .all()
    )
    classified_ids = {wc.workload_id for wc in classified}

    # WP-7: find controller names in PodMetric that have no classification record
    try:
        unclassified_names = (
            db.query(PodMetric.controller_name, PodMetric.namespace)
            .filter(
                PodMetric.cluster_id == cluster_id,
                PodMetric.controller_name.isnot(None),
                PodMetric.phase == "Running",
            )
            .distinct(PodMetric.controller_name)
            .all()
        )
    except Exception:
        unclassified_names = []

    rows = []

    # Classified workloads
    for wc in classified:
        pp = (
            db.query(PlacementPolicyRecord)
            .filter(
                PlacementPolicyRecord.cluster_id == cluster_id,
                PlacementPolicyRecord.workload_id == wc.workload_id,
            )
            .first()
        )

        state_key = f"spot:workload:state:{cluster_id}:{wc.workload_id}"
        state_data = safe_get_json(redis_client, state_key, default={})

        # WP-1+2: only trust Redis values when state_data is actually populated
        if state_data and "current_ondemand_pods" in state_data:
            current_spot = state_data.get("current_spot_pods", 0)
            current_od = state_data.get("current_ondemand_pods", 0)
            has_pdb = state_data.get("has_pdb", False)
        else:
            # WP-1: fall back to DB-derived counts
            current_spot, current_od = _derive_pod_counts_from_db(cluster_id, wc.workload_id, db)
            has_pdb = getattr(wc, "has_pdb", False)

        spot_target = pp.spot_target if pp else None
        od_required = pp.ondemand_target if pp else None
        od_excess = (current_od - od_required) if (current_od is not None and od_required is not None) else None
        savings = pp.estimated_monthly_saving_usd if pp else 0.0

        log_key = f"spot:pc:workload_log:{cluster_id}:{wc.workload_id}"
        log_entries = safe_lrange_json(redis_client, log_key, 0, 0)
        last_action = log_entries[0].get("action") if log_entries else None

        # WP-2: pass None (not 0) when data is absent so state = UNKNOWN not AT_TARGET
        placement_state = compute_placement_state(
            current_od=current_od,
            ondemand_target=od_required,
            last_action=last_action,
        ).value

        rows.append({
            "workload_id": wc.workload_id,
            "namespace": wc.namespace,
            "placement_status": last_action or "UNKNOWN",
            "placement_state": placement_state,
            "timeline_step": _STATE_TO_STEP.get(placement_state, 0),
            "od_excess": od_excess,
            "od_required": od_required,
            "spot_count": current_spot,
            "spot_target": spot_target,        # WP-8
            "estimated_monthly_saving_usd": savings,
            "pdb_active": has_pdb,
        })

    # WP-7: Append unclassified workloads as PENDING
    for r in unclassified_names:
        wid = f"{r.namespace}/{r.controller_name}" if r.namespace else r.controller_name
        if wid in classified_ids or r.controller_name in classified_ids:
            continue
        rows.append({
            "workload_id": wid,
            "namespace": r.namespace or "",
            "placement_status": "PENDING",
            "placement_state": "PENDING",
            "timeline_step": 0,
            "od_excess": None,
            "od_required": None,
            "spot_count": None,
            "spot_target": None,
            "estimated_monthly_saving_usd": 0.0,
            "pdb_active": False,
        })

    return rows


@router.get("/workloads/placement", summary="Paginated workload placement list")
async def get_workload_placement_list(
    cluster_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    validate_cluster_id(cluster_id)
    assert_cluster_access(cluster_id, db)

    from backend.core.redis_client import get_redis_client as _get_rc
    redis_client = _get_rc()
    rows = _get_placement_workload_rows(cluster_id, db, redis_client)
    total = len(rows)
    start = (page - 1) * page_size
    paginated = rows[start: start + page_size]

    return ok({
        "cluster_id": cluster_id,
        "total_count": total,
        "page": page,
        "page_size": page_size,
        "workloads": paginated,
    })


@router.get("/workloads/{workload_id:path}/placement-detail", summary="Full placement detail for one workload")
async def get_workload_placement_detail(
    workload_id: str,
    cluster_id: str = Query(...),
    db: Session = Depends(get_db),
):
    validate_cluster_id(cluster_id)
    validate_workload_id(workload_id)
    assert_cluster_access(cluster_id, db)

    from backend.core.redis_client import get_redis_client as _get_rc
    redis_client = _get_rc()

    state_key = f"spot:workload:state:{cluster_id}:{workload_id}"
    state_data = safe_get_json(redis_client, state_key, default={})

    # --- State Locks: read from the REAL individual Redis keys (same as placement-state T-02) ---
    _cooldown_key  = f"spot:placement_controller:cooldown:{cluster_id}:{workload_id}"
    _cooldown_ttl  = safe_ttl(redis_client, _cooldown_key) or 0

    _rollout_key   = f"spot:placement:rollout_blocked:{cluster_id}:{workload_id}"
    _rollout_ttl   = safe_ttl(redis_client, _rollout_key) or 0

    _keda_val      = safe_get_json(redis_client, f"spot:keda:last_scale_event:{cluster_id}")
    _keda_active   = False
    if _keda_val is not None:
        try:
            _keda_active = (time.time() - float(_keda_val)) < _SCALING_GUARD_WINDOW_SECONDS
        except (TypeError, ValueError):
            _keda_active = True

    try:
        _in_flight = db.query(AgentAction).filter(
            AgentAction.cluster_id == cluster_id,
            AgentAction.action_type == AgentActionType.EVICT_POD,
            AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
            AgentAction.payload.op("->>")("workload_id") == workload_id,
        ).count()
    except Exception:
        _in_flight = 0

    state_locks = {
        "cooldown_active":           _cooldown_ttl > 0,
        "cooldown_expires_in":       _cooldown_ttl,
        "rollout_blocked":           _rollout_ttl > 0,
        "rollout_blocked_expires_in": _rollout_ttl,
        "keda_scaling_active":       _keda_active,
        "pdb_active":                bool(state_data.get("has_pdb", False)),
        "in_flight_actions":         _in_flight,
    }

    log_key = f"spot:pc:workload_log:{cluster_id}:{workload_id}"
    recent_decisions = safe_lrange_json(redis_client, log_key, 0, 9)

    from backend.models.pod_metric import PodMetric
    from backend.models.node_metadata import NodeMetadata
    from sqlalchemy import func
    from datetime import datetime as _dt

    _wid_parts = workload_id.split("/", 1)
    workload_name = _wid_parts[-1]
    workload_ns   = _wid_parts[0] if len(_wid_parts) == 2 else None
    from datetime import timedelta as _pd_td
    _pd_cutoff = _dt.utcnow() - _pd_td(hours=6)
    _pod_filters = [
        PodMetric.cluster_id == cluster_id,
        PodMetric.controller_name == workload_name,
        PodMetric.timestamp >= _pd_cutoff,
    ]
    if workload_ns:
        _pod_filters.append(PodMetric.namespace == workload_ns)
    latest_subq = (
        db.query(
            PodMetric.pod_name,
            PodMetric.node_name,
            PodMetric.phase,
            PodMetric.start_time,
            PodMetric.timestamp,
            PodMetric.namespace,
            PodMetric.controller_kind,
            PodMetric.cpu_request_millicores,
            PodMetric.memory_request_bytes,
            PodMetric.cpu_usage_millicores,
        )
        .filter(*_pod_filters)
        .distinct(PodMetric.pod_name)
        .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
        .subquery()
    )
    pod_rows = (
        db.query(
            latest_subq.c.pod_name,
            latest_subq.c.node_name,
            latest_subq.c.phase,
            latest_subq.c.start_time,
            latest_subq.c.namespace,
            latest_subq.c.controller_kind,
            latest_subq.c.cpu_request_millicores,
            latest_subq.c.memory_request_bytes,
            latest_subq.c.cpu_usage_millicores,
            NodeMetadata.az,
            NodeMetadata.capacity_type,
        )
        .join(
            NodeMetadata,
            (NodeMetadata.cluster_id == cluster_id)
            & (NodeMetadata.node_name == latest_subq.c.node_name),
            isouter=True,
        )
        .all()
    )
    now = _dt.utcnow()
    pods = [
        {
            "pod_name": r.pod_name,
            "node_name": r.node_name,
            "az": r.az,
            "capacity_type": r.capacity_type,
            "phase": r.phase,
            "age_seconds": int((now - r.start_time).total_seconds()) if r.start_time else None,
            "namespace": r.namespace,
            "controller_kind": r.controller_kind,
            "cpu_request_millicores": r.cpu_request_millicores,
            "memory_request_bytes": r.memory_request_bytes,
            "cpu_usage_millicores": r.cpu_usage_millicores,
        }
        for r in pod_rows
    ]

    # --- Policy lookup (must precede pod plan which uses spot_tgt) ---
    od_target = None
    spot_tgt  = None
    obs_reps  = None
    from backend.redis_keys import placement_policy_key as _ppk
    _policy_raw = redis_client.get(_ppk(cluster_id, workload_id)) if redis_client else None
    if _policy_raw:
        try:
            _pd = json.loads(_policy_raw)
            od_target = _pd.get("ondemand_target")
            spot_tgt  = _pd.get("spot_target")
            obs_reps  = _pd.get("observed_replicas")
        except (json.JSONDecodeError, TypeError):
            pass
    if od_target is None or spot_tgt is None:
        _pp = db.query(PlacementPolicyRecord).filter(
            PlacementPolicyRecord.cluster_id == cluster_id,
            PlacementPolicyRecord.workload_id == workload_id,
        ).first()
        if _pp:
            od_target = _pp.ondemand_target
            spot_tgt  = _pp.spot_target
            obs_reps  = _pp.observed_replicas

    # ── Pod Placement Plan ──────────────────────────────────────────────────
    # Fetch WIE classification for this workload (single lookup, per-workload not per-pod)
    _wie = {}
    if redis_client:
        try:
            _wie_raw = redis_client.get(f"spot:wie:classification:{cluster_id}:{workload_id}")
            if _wie_raw:
                _wie = json.loads(_wie_raw)
        except Exception:
            pass
    _wie_spot_friendly = _wie.get('spot_friendly')   # True / False / None
    _wie_role          = (_wie.get('role') or '').upper()
    _wie_simulated     = False  # will be True when we infer spot_tgt from WIE

    # When no formal policy exists, simulate a target from WIE
    _eff_spot_tgt = spot_tgt
    if _eff_spot_tgt is None:
        if _wie_spot_friendly is False or _wie_role == 'SYSTEM':
            _eff_spot_tgt = 0   # hard OD — WIE says not spot-friendly
        elif _wie_spot_friendly is True:
            _wie_simulated = True
            # Conservative simulation: keep 1 OD anchor, rest eligible for spot
            # (actual assignment still depends on scoring below)

    _SYSTEM_NS = {
        'kube-system', 'kube-public', 'kube-node-lease', 'cert-manager',
        'monitoring', 'istio-system', 'observability', 'logging', 'kube-flannel',
    }

    def _spot_score(p):
        """Rule-based spot candidacy score. Returns (score|None, reason)."""
        # WIE hard gate: SYSTEM role or explicitly not spot-friendly
        if _wie_spot_friendly is False or _wie_role == 'SYSTEM':
            return None, f'wie_not_spot_friendly'
        if (p.get('namespace') or '') in _SYSTEM_NS:
            return None, 'system_namespace'
        if (p.get('controller_kind') or '') == 'DaemonSet':
            return None, 'daemonset'
        score, tags = 5, []
        age      = p.get('age_seconds')          # None means unknown — do NOT penalise
        cpu_req  = p.get('cpu_request_millicores') or 0
        cpu_use  = p.get('cpu_usage_millicores')   or 0
        # Rule 2: prefer older (mature) pods for spot — only when age is known
        if age is not None:
            if age < 300:
                score -= 3; tags.append('new_pod')
            elif age > 3600:
                score += 2; tags.append('mature_pod')
            elif age > 1800:
                score += 1; tags.append('aging_pod')
        # Rule 3: avoid high CPU spikes
        if cpu_req > 0:
            util = cpu_use / cpu_req
            if util > 0.8:
                score -= 2; tags.append('high_cpu')
            elif util < 0.3:
                score += 1; tags.append('low_cpu')
        # WIE bonus: high spot_score from WIE classification
        _wie_ss = _wie.get('spot_score') or 0
        if _wie_ss >= 7:
            score += 1; tags.append('wie_high')
        elif _wie_ss <= 3:
            score -= 1; tags.append('wie_low')
        return score, ','.join(tags) or 'normal'

    _scorable, _skipped = [], []
    for _p in pods:
        _s, _reason = _spot_score(_p)
        _entry = {**_p, 'spot_score': _s if _s is not None else 0, 'reason': _reason}
        (_skipped if _s is None else _scorable).append(_entry)

    # Highest score pods become spot candidates first
    _scorable.sort(key=lambda x: x['spot_score'], reverse=True)
    if _eff_spot_tgt is not None:
        _eff_spot = min(_eff_spot_tgt, len(_scorable))
    else:
        # No policy + WIE unknown: simulate conservatively (1 OD, rest spot)
        _wie_simulated = True
        _eff_spot = max(0, len(_scorable) - 1)
    pod_plan = []
    for _i, _p in enumerate(_scorable):
        pod_plan.append({**_p, 'recommendation': 'spot' if _i < _eff_spot else 'od'})
    pod_plan.extend({**_p, 'recommendation': 'skip'} for _p in _skipped)

    _spot_pods = [_p for _p in pod_plan if _p['recommendation'] == 'spot']
    _od_pods   = [_p for _p in pod_plan if _p['recommendation'] == 'od']
    capacity_plan = {
        'total_cpu_spot_millicores': sum(_p.get('cpu_request_millicores') or 0 for _p in _spot_pods),
        'total_memory_spot_bytes':   sum(_p.get('memory_request_bytes')   or 0 for _p in _spot_pods),
        'total_cpu_od_millicores':   sum(_p.get('cpu_request_millicores') or 0 for _p in _od_pods),
        'total_memory_od_bytes':     sum(_p.get('memory_request_bytes')   or 0 for _p in _od_pods),
        'spot_pod_count':    len(_spot_pods),
        'od_pod_count':      len(_od_pods),
        'skipped_pod_count': len(_skipped),
        'wie_simulated':     _wie_simulated,
        'wie_spot_friendly': _wie_spot_friendly,
        'wie_role':          _wie_role or None,
    }

    _active_pods = [_p for _p in pod_plan if _p['recommendation'] != 'skip']
    _d_nodes = {_p['node_name'] for _p in _active_pods if _p.get('node_name')}
    _d_azs   = {_p['az']        for _p in _active_pods if _p.get('az') and _p.get('az') != 'unknown'}
    topology_constraints = {
        'distinct_nodes':  len(_d_nodes),
        'distinct_azs':    len(_d_azs),
        'min_nodes_ok':    len(_d_nodes) >= 2,
        'az_spread_ok':    len(_d_azs) >= 2 or len(_active_pods) <= 1,
        'anti_affinity_ok': len(_d_nodes) >= 2 or len(_active_pods) <= 1,
    }
    # ── End Pod Placement Plan ───────────────────────────────────────────────

    pd_max_ts = _safe_fetch(
        lambda: db.query(func.max(PodMetric.timestamp))
        .filter(PodMetric.cluster_id == cluster_id, PodMetric.controller_name == workload_name)
        .scalar(),
        None, "placement_detail_freshness",
    )
    freshness = compute_freshness(pd_max_ts)

    # --- Policy summary (od_target/spot_tgt already resolved above before pod plan) ---
    policy_summary = {
        "ondemand_target": od_target,
        "spot_target": spot_tgt,
        "observed_replicas": obs_reps,
    }

    # ── Pod Placement Engine — full materialised plan ──────────────────────
    placement_plan = None
    _eng_spot_tgt = 0
    _eng_od_tgt   = len(pods)
    _target_basis = "unknown"
    try:
        from backend.pipeline.stage3_ppe.engine import PodPlacementEngine
        # Gather nodes from the cluster (only nodes that currently host workload pods + free nodes)
        _node_rows = (
            db.query(NodeMetadata)
            .filter(NodeMetadata.cluster_id == cluster_id)
            .all()
        )
        # Pull live usage from latest node metrics (best-effort)
        from backend.models.node_metrics import NodeMetric
        _latest_node_subq = (
            db.query(
                NodeMetric.node_name,
                NodeMetric.cpu_usage_millicores,
                NodeMetric.memory_usage_bytes,
            )
            .filter(NodeMetric.cluster_id == cluster_id)
            .distinct(NodeMetric.node_name)
            .order_by(NodeMetric.node_name, NodeMetric.timestamp.desc())
            .all()
        )
        _node_usage = {r.node_name: (r.cpu_usage_millicores or 0, r.memory_usage_bytes or 0) for r in _latest_node_subq}
        nodes_input = []
        for n in _node_rows:
            used_cpu, used_mem = _node_usage.get(n.node_name, (0, 0))
            nodes_input.append({
                "node_name": n.node_name,
                "az": n.az,
                "capacity_type": n.capacity_type,
                "instance_type": n.instance_type,
                "allocatable_cpu_millicores": n.allocatable_cpu_millicores,
                "allocatable_memory_bytes": n.allocatable_memory_bytes,
                "used_cpu_millicores": used_cpu,
                "used_memory_bytes": used_mem,
                "pod_count": 0,  # not tracked at node-meta level; engine treats 0 as "unknown"
            })

        if od_target is not None and spot_tgt is not None:
            _eng_od_tgt   = od_target
            _eng_spot_tgt = spot_tgt
            _target_basis = "policy"
        elif _wie.get("min_on_demand_replicas") is not None and _wie.get("max_spot_replicas") is not None:
            # WIE v4.5+ computed constraints — use directly as PPE targets
            _eng_od_tgt   = int(_wie["min_on_demand_replicas"])
            _eng_spot_tgt = int(_wie["max_spot_replicas"])
            _target_basis = "wie_distribution"
        elif _wie_spot_friendly is False or _wie_role == "SYSTEM":
            _eng_spot_tgt = 0
            _eng_od_tgt   = len(pods)
            _target_basis = "wie_not_spot_friendly"
        else:
            # Fallback heuristic (pre-v4.5 classifications without distribution fields)
            _wie_ss = int(_wie.get("spot_score") or 0)
            if _wie_ss >= 6:
                _eng_spot_tgt = len(pods)
                _eng_od_tgt   = 0
                _target_basis = "wie_score_high"
            else:
                _eng_spot_tgt = max(0, len(pods) - 1)
                _eng_od_tgt   = min(1, len(pods))
                _target_basis = "wie_score_moderate"
        _engine_targets = {
            "ondemand_target": _eng_od_tgt,
            "spot_target":     _eng_spot_tgt,
            "observed_replicas": obs_reps if obs_reps is not None else len(pods),
        }
        # Fetch cooldown set for this workload
        _cooldown_pods = set()
        try:
            if redis_client:
                _cd_raw = redis_client.smembers(f"spot:placement:cooldown:{cluster_id}:{workload_id}")
                if _cd_raw:
                    _cooldown_pods = {x.decode() if isinstance(x, bytes) else x for x in _cd_raw}
        except Exception:
            pass

        _wie_for_plan = {**_wie, "disruption_safe": True} if _wie.get("disruption_safe") is False else _wie
        _plan = PodPlacementEngine.materialize_plan(
            pods=pods,
            nodes=nodes_input,
            wie=_wie_for_plan,
            targets=_engine_targets,
            cooldown_pods=_cooldown_pods,
            cluster_id=cluster_id,
        )
        placement_plan = _plan.to_dict()
        # Persist anchor_nodes to Redis so PlacementController can read them (TTL 5 min)
        try:
            _ap = _plan.anchor_plan
            _anchor_list = _ap.get("anchor_nodes", []) if _ap else []
            if _anchor_list and redis_client:
                import json as _json
                redis_client.setex(
                    f"spot:placement:anchor_nodes:{cluster_id}:{workload_id}",
                    300,
                    _json.dumps(_anchor_list),
                )
        except Exception:
            pass  # non-critical — controller fails open if key absent
    except Exception as _ppe_err:
        logger.warning(f"pod_placement_engine_error workload_id={workload_id} error={_ppe_err}")
        placement_plan = {
            "schema_version": "1.0",
            "pod_assignment": {"spot": [], "ondemand": []},
            "movement_plan": [],
            "node_plan": [],
            "az_distribution": {},
            "anchor_plan": {},
            "feasibility": {
                "feasible": False,
                "status": "engine_error",
                "warnings": [f"engine_error: {_ppe_err}"],
                "moves_total": 0,
                "moves_blocked": 0,
            },
        }

    return ok({
        "cluster_id": cluster_id,
        "workload_id": workload_id,
        "state_locks": state_locks,
        "policy": policy_summary,
        "pods": pods,
        "pod_plan": pod_plan,
        "capacity_plan": capacity_plan,
        "topology_constraints": topology_constraints,
        "placement_plan": placement_plan,
        "engine_targets": {
            "spot_target":     _eng_spot_tgt,
            "od_target":       _eng_od_tgt,
            "basis":           _target_basis,
            "total_pods":      len(pods),
            "wie_spot_score":  int(_wie.get("spot_score") or 0),
        },
        "recent_decisions": recent_decisions,
        **freshness,
    })


# ---------------------------------------------------------------------------
# T-24: GET /optimize/workloads/{workload_id}/scaling-detail
# ---------------------------------------------------------------------------

@router.get("/workloads/{workload_id:path}/scaling-detail", summary="120-min HPA snapshot timeline + config for a workload")
async def get_workload_scaling_detail(
    workload_id: str,
    cluster_id: str = Query(...),
    db: Session = Depends(get_db),
):
    validate_cluster_id(cluster_id)
    validate_workload_id(workload_id)
    assert_cluster_access(cluster_id, db)

    from backend.models.hpa_configs import HpaConfig
    from backend.models.hpa_status_snapshots import HpaStatusSnapshot
    from sqlalchemy import func as _func
    from datetime import datetime as _dt, timedelta as _td

    workload_name = workload_id.split("/")[-1] if "/" in workload_id else workload_id
    cutoff_120m = _dt.utcnow() - _td(minutes=120)

    # P-01: freshness anchor — MAX(hpa_status_snapshots.snapshot_at) for this workload
    max_snap_ts = (
        db.query(_func.max(HpaStatusSnapshot.snapshot_at))
        .filter(
            HpaStatusSnapshot.cluster_id == cluster_id,
            HpaStatusSnapshot.workload_name == workload_name,
        )
        .scalar()
    )

    cfg = _safe_fetch(
        lambda: db.query(HpaConfig)
        .filter(HpaConfig.cluster_id == cluster_id, HpaConfig.workload_name == workload_name)
        .first(),
        None,
        "scaling_detail_hpa_config",
    )

    snapshots = _safe_fetch(
        lambda: db.query(HpaStatusSnapshot)
        .filter(
            HpaStatusSnapshot.cluster_id == cluster_id,
            HpaStatusSnapshot.workload_name == workload_name,
            HpaStatusSnapshot.snapshot_at > cutoff_120m,
        )
        .order_by(HpaStatusSnapshot.snapshot_at.asc())
        .all(),
        [],
        "scaling_detail_snapshots",
    )

    scale_events_120m = sum(
        1 for i in range(1, len(snapshots))
        if (snapshots[i].desired_replicas or 0) != (snapshots[i - 1].desired_replicas or 0)
    ) if len(snapshots) >= 2 else 0

    hpa_config_out = None
    if cfg:
        hpa_config_out = {
            "min_replicas": cfg.min_replicas,
            "max_replicas": cfg.max_replicas,
            "target_cpu_pct": cfg.target_cpu_pct,
            "recommended_min": cfg.recommended_min_replicas,
            "recommended_max": cfg.recommended_max_replicas,
            "scale_up_stabilization_seconds": cfg.scale_up_stabilization_seconds,
            "scale_down_stabilization_seconds": cfg.scale_down_stabilization_seconds,
        }

    hpa_snapshots = [
        {
            "snapshot_at": s.snapshot_at.isoformat() if s.snapshot_at else None,
            "desired": s.desired_replicas,
            "current": s.current_replicas,
            "cpu_util_pct": s.cpu_utilization_pct,
        }
        for s in snapshots
    ]

    # P-11: aggregate pod lifecycle counts via PodMetric for this workload
    from backend.models.pod_metric import PodMetric as _PodMetric
    lifecycle_counts = {"serving_count": 0, "idle_count": 0, "evicting_count": 0, "pending_count": 0}
    try:
        from backend.models.agent_action import AgentAction as _AA, AgentActionStatus as _AAS, AgentActionType as _AAT
        _evict_rows = (
            db.query(_AA.payload["pod_name"].astext)
            .filter(
                _AA.cluster_id == cluster_id,
                _AA.action_type == _AAT.EVICT_POD,
                _AA.status.in_([_AAS.PENDING, _AAS.PICKED_UP]),
            )
            .all()
        )
        _evicting_pods = {r[0] for r in _evict_rows if r[0]}
        _pod_rows = (
            db.query(_PodMetric.pod_name, _PodMetric.phase, _PodMetric.cpu_usage_millicores)
            .filter(
                _PodMetric.cluster_id == cluster_id,
                _PodMetric.controller_name == workload_name,
            )
            .distinct(_PodMetric.pod_name)
            .order_by(_PodMetric.pod_name, _PodMetric.timestamp.desc())
            .all()
        )
        for _pr in _pod_rows:
            _lc = classify_pod_lifecycle(
                phase=_pr.phase,
                cpu_usage_millicores=_pr.cpu_usage_millicores,
                has_pending_evict=_pr.pod_name in _evicting_pods,
            )
            if _lc == PodLifecycleClass.SERVING:
                lifecycle_counts["serving_count"] += 1
            elif _lc == PodLifecycleClass.IDLE:
                lifecycle_counts["idle_count"] += 1
            elif _lc == PodLifecycleClass.EVICTING:
                lifecycle_counts["evicting_count"] += 1
            elif _lc == PodLifecycleClass.PENDING:
                lifecycle_counts["pending_count"] += 1
    except Exception:
        pass

    freshness = compute_freshness(max_snap_ts)
    data_ready = max_snap_ts is not None and not freshness["is_stale"]
    reason = "" if data_ready else ("hpa_data_pending" if max_snap_ts is None else "stale_data")
    return ok(
        {
            "workload_id": workload_id,
            "hpa_config": hpa_config_out,
            "hpa_snapshots": hpa_snapshots,
            "scale_events_120m": scale_events_120m,
            **lifecycle_counts,
            **freshness,
        },
        data_ready=data_ready,
        data_ready_reason=reason,
    )


# ---------------------------------------------------------------------------
# P-19 — System Health Endpoint
# ---------------------------------------------------------------------------

@router.get("/clusters/{cluster_id}/karpenter-metrics", summary="Karpenter provisioning P90 latency per nodepool class")
def get_karpenter_metrics(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns Karpenter provisioning P90 latency (seconds) per nodepool class as
    collected by KarpenterMetricsCollector every 2 minutes.
    Keys: spot:placement:provision_p90:{nodepool_class}
    """
    validate_cluster_id(cluster_id)
    assert_cluster_access(cluster_id, db)

    from backend.core.redis_client import get_redis_client as _grc_km
    _r = _grc_km()

    _NODEPOOL_CLASSES = ["spot-general", "spot-compute", "spot-memory", "on-demand-general"]
    latency_by_class: Dict[str, Optional[float]] = {}
    available = False
    if _r:
        for np_cls in _NODEPOOL_CLASSES:
            raw = _r.get(f"spot:placement:provision_p90:{np_cls}")
            if raw is not None:
                try:
                    latency_by_class[np_cls] = round(float(raw), 1)
                    available = True
                except (ValueError, TypeError):
                    latency_by_class[np_cls] = None
            else:
                latency_by_class[np_cls] = None

    return {
        "available": available,
        "latency_p90_seconds": latency_by_class,
    }


@router.get("/system/health", summary="Cluster-level eviction + placement health metrics")
async def get_system_health(
    cluster_id: str = Query(...),
    db: Session = Depends(get_db),
):
    validate_cluster_id(cluster_id)
    assert_cluster_access(cluster_id, db)

    from sqlalchemy import func as _func
    from datetime import datetime as _dt, timedelta as _td

    now = _dt.utcnow()
    cutoff_24h = now - _td(hours=24)

    # Eviction stats — last 24h
    total_evictions_24h = 0
    eviction_success_rate_24h = 0.0
    circuit_breaker_trips_24h = 0
    try:
        total_q = (
            db.query(_func.count(AgentAction.id))
            .filter(
                AgentAction.cluster_id == cluster_id,
                AgentAction.action_type == AgentActionType.EVICT_POD,
                AgentAction.created_at > cutoff_24h,
            )
            .scalar() or 0
        )
        completed_q = (
            db.query(_func.count(AgentAction.id))
            .filter(
                AgentAction.cluster_id == cluster_id,
                AgentAction.action_type == AgentActionType.EVICT_POD,
                AgentAction.status == AgentActionStatus.COMPLETED,
                AgentAction.created_at > cutoff_24h,
            )
            .scalar() or 0
        )
        total_evictions_24h = total_q
        eviction_success_rate_24h = round(completed_q / total_q * 100, 1) if total_q > 0 else 0.0
    except Exception:
        pass

    # PC cycle metrics from Redis
    pc_cycle_count = 0
    try:
        from backend.core.redis_client import get_redis_client as _hrc
        _hr = _safe_fetch(_hrc, None, "health_redis")
        if _hr:
            metrics_key = f"spot:placement_controller:metrics:{cluster_id}"
            metrics_hash = safe_hgetall(_hr, metrics_key, default={})
            pc_cycle_count = int(metrics_hash.get("cycle_count", 0))
            cb_key = f"spot:pc:circuit_breaker:{cluster_id}"
            circuit_breaker_active = bool(_hr.get(cb_key))
            cb_trips_key = f"spot:pc:cb_trips_24h:{cluster_id}"
            circuit_breaker_trips_24h = int(_hr.get(cb_trips_key) or 0)
        else:
            circuit_breaker_active = False
    except Exception:
        circuit_breaker_active = False

    # Placement drift summary for drift_resolution_rate
    at_target_count = 0
    drifting_count = 0
    drift_resolution_rate = 0.0
    try:
        from backend.models.placement_policy import PlacementPolicyRecord as _PPR
        from backend.models.workload_classification import WorkloadClassificationRecord as _WCR
        _wcs = (
            db.query(_WCR.workload_id)
            .filter(_WCR.cluster_id == cluster_id)
            .all()
        )
        for (_wid,) in _wcs:
            from backend.core.redis_client import get_redis_client as _src
            _sr = _safe_fetch(_src, None, "health_state_redis")
            if not _sr:
                break
            _state = safe_get_json(_sr, f"spot:workload:state:{cluster_id}:{_wid}", default={})
            _pp = db.query(_PPR).filter(
                _PPR.cluster_id == cluster_id,
                _PPR.workload_id == _wid,
            ).first()
            _ps = compute_placement_state(
                current_od=_state.get("current_ondemand_pods"),
                ondemand_target=_pp.ondemand_target if _pp else None,
                last_action=None,
            )
            if _ps == PlacementState.AT_TARGET:
                at_target_count += 1
            elif _ps == PlacementState.DRIFTING:
                drifting_count += 1
        total_wl = at_target_count + drifting_count
        drift_resolution_rate = round(at_target_count / total_wl * 100, 1) if total_wl > 0 else 0.0
    except Exception:
        pass

    freshness = compute_freshness(None)
    return ok(
        {
            "eviction_success_rate_24h": eviction_success_rate_24h,
            "total_evictions_24h": total_evictions_24h,
            "drift_resolution_rate": drift_resolution_rate,
            "at_target_count": at_target_count,
            "drifting_count": drifting_count,
            "pc_cycle_count": pc_cycle_count,
            "circuit_breaker_trips_24h": circuit_breaker_trips_24h,
            "circuit_breaker_active": circuit_breaker_active,
            **freshness,
        },
        data_ready=True,
        data_ready_reason="",
    )
