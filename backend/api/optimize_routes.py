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
from sqlalchemy import cast, func
from sqlalchemy import String as SAString
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
    from backend.services.bin_packing_service import BinPackingService
    
    _rl_redis = _safe_fetch(_rl_rc, None, "rate_limit_redis_bin_packing")
    check_rate_limit(_rl_redis, f"spot:ratelimit:bin_packing:{cluster_id}", 10, 60)

    # Permanent Fix: Use BinPackingService which handles cache + on-demand fallback
    service = BinPackingService(db, _rl_redis)
    data = service.get_bin_packing_data(cluster_id)
    
    if not data.get("nodes"):
        return not_ready(
            "node_allocatable_data_pending",
            partial_data={"cluster_id": cluster_id, "nodes": [], "stale_nodes_excluded": 0, "consolidation_candidates": None},
        )
        
    return ok(data)



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
    import math

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
            (PodMetric.phase == "Running") | (PodMetric.phase.is_(None)),
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

    _PLAN_CACHE_TTL = 25  # seconds — slightly under the 30s frontend poll interval
    _plan_cache_key = f"spot:cep:{cluster_id}"
    _plan_redis = None
    try:
        _plan_redis = _rl_rc()
        _cached = _plan_redis.get(_plan_cache_key)
        if _cached:
            return ok(json.loads(_cached))
    except Exception:
        _plan_redis = None

    _cutoff = _dt.utcnow() - _td(minutes=30)

    draining_nodes: set = set()
    try:
        from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
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

    active_rebalancing_nodes: set = set()
    try:
        from backend.models.rebalancing_action import RebalancingAction
        from backend.models.instance import Instance
        rebalance_rows = (
            db.query(Instance.node_name)
            .join(
                RebalancingAction,
                (RebalancingAction.cluster_id == Instance.cluster_id)
                & (RebalancingAction.source_instance_id == Instance.instance_id),
            )
            .filter(
                RebalancingAction.cluster_id == cluster_id,
                RebalancingAction.status.in_(["pending", "in_progress", "waiting_agent", "pending_approval"]),
                Instance.node_name.isnot(None),
            )
            .all()
        )
        active_rebalancing_nodes = {r.node_name for r in rebalance_rows if r.node_name}
    except Exception:
        pass

    # Exclude instances whose EC2/cloud state is terminated/terminating.
    # NodeMetadata rows persist long after the instance is gone, so without this
    # the plan oscillates every cycle as terminated nodes cycle in/out of
    # draining_nodes (only excluded while DRAIN_NODE is PICKED_UP, re-included
    # after the action completes).
    _terminated_instance_nodes: set = set()
    try:
        from backend.models.instance import Instance as _InstPlan
        _term_rows = (
            db.query(_InstPlan.node_name)
            .filter(
                _InstPlan.cluster_id == cluster_id,
                _InstPlan.state.in_(["terminated", "terminating", "stopped"]),
                _InstPlan.node_name.isnot(None),
            )
            .all()
        )
        _terminated_instance_nodes = {r[0] for r in _term_rows if r[0]}
    except Exception:
        pass

    # Belt-and-suspenders: also exclude nodes whose consolidation TERMINATE_NODE
    # action completed in the last 4 h (handles the race where the instance row
    # hasn't been refreshed yet by the metrics agent).
    _recently_terminated_nodes: set = set()
    try:
        from backend.models.agent_action import AgentAction as _AATerm, AgentActionType as _AATType
        _term_cutoff = _dt.utcnow() - _td(hours=4)
        _rterm_rows = (
            db.query(_AATerm.payload["node_name"].astext)
            .filter(
                _AATerm.cluster_id == cluster_id,
                _AATerm.action_type == _AATType.TERMINATE_NODE,
                _AATerm.payload["consolidation_drain"].astext == "true",
                _AATerm.status == "COMPLETED",
                _AATerm.created_at > _term_cutoff,
            )
            .all()
        )
        _recently_terminated_nodes = {r[0] for r in _rterm_rows if r[0]}
    except Exception:
        pass

    _nodes_to_ignore = (
        draining_nodes
        | active_rebalancing_nodes
        | _terminated_instance_nodes
        | _recently_terminated_nodes
    )

    from backend.models.instance import Instance
    from sqlalchemy import func
    
    _node_rows_raw = (
        db.query(
            NodeMetadata.node_name,
            NodeMetadata.updated_at,
            NodeMetadata.allocatable_cpu_millicores,
            NodeMetadata.allocatable_memory_bytes,
            func.coalesce(NodeMetadata.capacity_type, cast(Instance.lifecycle, SAString)).label("capacity_type"),
            func.coalesce(NodeMetadata.az, Instance.az).label("az"),
            func.coalesce(NodeMetadata.instance_type, Instance.instance_type).label("instance_type"),
        )
        .outerjoin(
            Instance,
            (Instance.cluster_id == NodeMetadata.cluster_id)
            & (Instance.node_name == NodeMetadata.node_name)
        )
        .filter(NodeMetadata.cluster_id == cluster_id)
        .all()
    )
    
    # Also fetch active instances that might have lost their NodeMetadata completely,
    # but still exist in the cluster and might have pods on them.
    _active_instances = (
        db.query(Instance)
        .filter(Instance.cluster_id == cluster_id, Instance.state == "running")
        .all()
    )
    _instance_map = {i.node_name: i for i in _active_instances if i.node_name}
    
    _node_rows = []
    _seen_nodes = set()
    _now = _dt.utcnow()
    from backend.utils.data_freshness import STALE_THRESHOLD_SECONDS
    for n in _node_rows_raw:
        if n.node_name:
            _seen_nodes.add(n.node_name)
        if n.updated_at is None or (_now - n.updated_at).total_seconds() > STALE_THRESHOLD_SECONDS:
            _nodes_to_ignore.add(n.node_name)
            # Even if ignored for new placements, we MUST keep its metadata in _node_meta_map 
            # so the UI can render its details if it has straggler pods.
            _node_rows.append(n)
        else:
            _node_rows.append(n)
            
    # Add any running instances missing from NodeMetadata entirely
    class _MockNode:
        def __init__(self, node_name, capacity_type, az, instance_type):
            self.node_name = node_name
            self.capacity_type = capacity_type
            self.az = az
            self.instance_type = instance_type
            self.allocatable_cpu_millicores = None
            self.allocatable_memory_bytes = None
            
    for node_name, inst in _instance_map.items():
        if node_name not in _seen_nodes:
            _node_rows.append(_MockNode(
                node_name=node_name,
                capacity_type=inst.lifecycle,
                az=inst.az,
                instance_type=inst.instance_type,
            ))
    _latest_nm = (
        db.query(NodeMetric.node_name, NodeMetric.cpu_usage_millicores, NodeMetric.memory_usage_bytes)
        .filter(NodeMetric.cluster_id == cluster_id)
        .distinct(NodeMetric.node_name)
        .order_by(NodeMetric.node_name, NodeMetric.timestamp.desc())
        .all()
    )
    _node_usage = {r.node_name: (r.cpu_usage_millicores or 0, r.memory_usage_bytes or 0) for r in _latest_nm}
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
        .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
        .all()
    )
    _node_total_pods: dict = {}      # node_name → total pod count
    _node_system_pods: dict = {}     # node_name → DaemonSet + system ns count
    for _pr in _pod_count_rows:
        nn = _pr.node_name or ""
        _node_total_pods[nn] = _node_total_pods.get(nn, 0) + 1
        if (_pr.controller_kind == "DaemonSet") or ((_pr.namespace or "") in _SYSTEM_NS):
            _node_system_pods[nn] = _node_system_pods.get(nn, 0) + 1

    _node_meta_map = {}  # node_name → {instance_type, capacity_type, az}
    nodes_input = []
    for n in _node_rows:
        uc, um = _node_usage.get(n.node_name, (0, 0))
        _node_meta_map[n.node_name] = {
            "instance_type": n.instance_type,
            "capacity_type": n.capacity_type,
            "az": n.az,
        }
        
        if n.node_name in _nodes_to_ignore:
            continue
            
        nodes_input.append({
            "node_name": n.node_name,
            "az": n.az,
            "capacity_type": n.capacity_type,
            "instance_type": n.instance_type,
            "allocatable_cpu_millicores": n.allocatable_cpu_millicores,
            "allocatable_memory_bytes": n.allocatable_memory_bytes,
            "used_cpu_millicores": uc,
            "used_memory_bytes": um,
            # Provide real pod_count so AnchorPlanner scoring works correctly.
            "pod_count": _node_total_pods.get(n.node_name, 0),
        })

    # Freshness check: use the NEWEST NodeMetadata updated_at (minimum age) to
    # determine whether the agent is actively reporting.  Previously this used
    # max() which returned the age of the oldest/stalest record — one replaced
    # node left in the table caused StateGuard to abort every plan with a false
    # "stale state" warning even though the agent was running fine for all other nodes.
    import time as _time_s1
    _nodes_fetched_at = _time_s1.time()
    _node_ages = [
        (_now - _nr.updated_at).total_seconds()
        for _nr in _node_rows if _nr.updated_at
    ]
    # Freshest record = smallest age.  If even the freshest is > threshold the
    # agent is genuinely not reporting; otherwise data is current enough to plan.
    _node_max_age: float = min(_node_ages) if _node_ages else 0.0



    # ── Cluster planning settings ───────────────────────────────────────────
    _cluster_opt = (
        db.query(_ClusterOptSettings)
        .filter(_ClusterOptSettings.cluster_id == cluster_id)
        .first()
    )
    _plan_all_classified = bool(getattr(_cluster_opt, 'plan_all_classified_workloads', False))

    # ── Workload list ─────────────────────────────────────────────────────────
    wc_rows = (
        db.query(WorkloadClassificationRecord)
        .filter(WorkloadClassificationRecord.cluster_id == cluster_id)
        .order_by(WorkloadClassificationRecord.max_spot_replicas.desc().nullslast())
        .limit(500)
        .all()
    )

    # ── Batch prefetch: pod metrics + policies for ALL workloads (2 queries) ───
    # Without this, the PPE loop issues 2 queries × N workloads (N×2 round-trips).
    # We fetch all rows in one shot and group in Python.
    _wc_ctrl_names: set = {
        (wc.workload_id.split("/")[-1] if "/" in wc.workload_id else wc.workload_id)
        for wc in wc_rows
    }
    _batch_pod_rows = (
        db.query(
            PodMetric.pod_name,
            PodMetric.namespace,
            PodMetric.node_name,
            PodMetric.controller_name,
            PodMetric.controller_kind,
            PodMetric.cpu_request_millicores,
            PodMetric.memory_request_bytes,
            PodMetric.cpu_usage_millicores,
            PodMetric.memory_usage_bytes,
        )
        .filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.controller_name.in_(list(_wc_ctrl_names)),
            PodMetric.controller_kind != "DaemonSet",
            ~PodMetric.namespace.in_(list(_SYSTEM_NS)),
            (PodMetric.phase == "Running") | (PodMetric.phase.is_(None)),
            PodMetric.timestamp > _cutoff,
        )
        .distinct(PodMetric.pod_name)
        .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
        .all()
    ) if _wc_ctrl_names else []
    _pods_by_ctrl: dict = {}
    for _bpr in _batch_pod_rows:
        _ctrl_key = (_bpr.controller_name or "").split("/")[-1]
        _pods_by_ctrl.setdefault(_ctrl_key, []).append(_bpr)

    _wc_wids = [wc.workload_id for wc in wc_rows]
    _pp_map: dict = {
        _pp.workload_id: _pp
        for _pp in db.query(PlacementPolicyRecord)
        .filter(
            PlacementPolicyRecord.cluster_id == cluster_id,
            PlacementPolicyRecord.workload_id.in_(_wc_wids),
        )
        .all()
    } if _wc_wids else {}

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
            pod_rows_w = _pods_by_ctrl.get(controller_name, [])
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
                "confidence_state": "CONFIRMED" if _plan_all_classified else wc.confidence_state,
                "confidence_override": bool(_plan_all_classified),
                "min_on_demand_replicas": wc.min_on_demand_replicas,
                "max_spot_replicas": wc.max_spot_replicas,
                "workload_class": getattr(wc, "workload_class", "stateless") or "stateless",
                "disruption_safe": True,
            }

            pp = _pp_map.get(workload_id)
            total_pods = len(pods_w)

            # ── Target Builder gate: skip workloads already at desired distribution ──
            # When plan_all_classified_workloads is True, this gate is bypassed so that
            # ALL classified workloads get explicit pod routing (no silent k8s-drain reliance).
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
            if _targets and not _targets[0].action_required and not _plan_all_classified:
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
                # Fix 1: pass node data age so StateGuard aborts on stale data
                data_age_seconds=_node_max_age,
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
                    # KEEP nodes are anchor nodes — they must never become drain targets.
                    # If PPE wants to drain a node already locked as KEEP by a previous
                    # workload, skip the drain: the out-of-place pod will be picked up by
                    # Step 5 and routed to the correct capacity-type keep node.
                    if node_transitions.get(nname, {}).get("type") not in ("TERMINATE", "REPLACE", "KEEP"):
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
                                "drain_reuse"     if _ppr == "drain_reuse"
                                else "already_optimal" if _ppr == "already_optimal"
                                else "od_anchor"  if _is_od
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

        # Strategy: min_topology_spread is a FLOOR — keep at least that many OD
        # nodes in distinct AZs.  If those nodes can absorb all cluster pods,
        # mark the rest as TERMINATE.  If not, keep adding nodes until capacity
        # is met (or suggest spot for overflow).

        # Compute total user pods across all nodes
        _total_user_pods_cluster = sum(
            _node_total_pods.get(ni['node_name'], 0) - _node_system_pods.get(ni['node_name'], 0)
            for ni in nodes_input
        )

        # Compute allocatable CPU per node (from raw node rows)
        _node_alloc_cpu: dict = {}
        for _nr in _node_rows:
            _node_alloc_cpu[_nr.node_name] = int((_nr.allocatable_cpu_millicores or 4000) * 0.85)

        # Total CPU demand (sum of all DISTINCT user pod requests across cluster)
        _total_cpu_demand = 0
        try:
            from sqlalchemy import literal_column
            _distinct_pods_sub = (
                db.query(
                    PodMetric.pod_name,
                    PodMetric.cpu_request_millicores,
                )
                .filter(
                    PodMetric.cluster_id == cluster_id,
                    PodMetric.controller_kind != "DaemonSet",
                    ~PodMetric.namespace.in_(list(_SYSTEM_NS)),
                    (PodMetric.phase == "Running") | (PodMetric.phase.is_(None)),
                    PodMetric.timestamp > _cutoff,
                )
                .distinct(PodMetric.pod_name)
                .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
                .subquery()
            )
            _cpu_demand_rows = (
                db.query(func.sum(_distinct_pods_sub.c.cpu_request_millicores))
                .scalar()
            )
            _total_cpu_demand = int(_cpu_demand_rows or 0)
        except Exception:
            _total_cpu_demand = _total_user_pods_cluster * 100  # fallback ~100m per pod

        # Rank all nodes by allocatable CPU descending (biggest first = best anchors)
        _all_nodes_ranked = sorted(
            nodes_input,
            key=lambda n: _node_alloc_cpu.get(n['node_name'], 0),
            reverse=True,
        )

        # Phase 1: Greedily pick nodes from distinct AZs until min_topology_spread
        _chosen_azs: set = set()
        _spread_keep_names: set = set()
        _spread_keep_cpu: int = 0
        for _ni in _all_nodes_ranked:
            _az = _ni.get('az') or 'unknown'
            if _az in _chosen_azs:
                continue  # already have a node from this AZ
            _spread_keep_names.add(_ni['node_name'])
            _chosen_azs.add(_az)
            _spread_keep_cpu += _node_alloc_cpu.get(_ni['node_name'], 0)
            if len(_chosen_azs) >= _min_az_spread:
                break

        # Phase 2: If selected nodes can't absorb all CPU demand, add more nodes.
        # ONLY add nodes from AZs NOT already covered by Phase 1 (_chosen_azs).
        # Same-AZ redundant nodes are NEVER added here — the Phase-1 node for
        # that AZ already provides sufficient capacity; adding a twin would
        # permanently block consolidation for the entire cluster.
        _remaining = [n for n in _all_nodes_ranked if n['node_name'] not in _spread_keep_names]
        for _ni in _remaining:
            if _spread_keep_cpu >= _total_cpu_demand:
                break  # enough capacity already
            _this_az_p2 = _ni.get('az') or 'unknown'
            if _this_az_p2 in _chosen_azs:
                continue  # skip same-AZ duplicate — consolidation candidate
            _spread_keep_names.add(_ni['node_name'])
            _chosen_azs.add(_this_az_p2)
            _spread_keep_cpu += _node_alloc_cpu.get(_ni['node_name'], 0)

        # Clear ALL existing pods_leaving from node_transitions.  The PPE
        # workload loop may have routed pods to nodes that AZ-spread will now
        # TERMINATE; keeping those stale entries would corrupt the routing table.
        # The AZ-spread round-robin + Step 5 rebuild correct routing below.
        for _trans in node_transitions.values():
            _trans['pods_leaving'] = []

        # Force-keep the selected nodes
        for _nname in _spread_keep_names:
            _nmeta = next((n for n in nodes_input if n['node_name'] == _nname), {})
            _cap = _nmeta.get('capacity_type', '') or ''
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
            # Override KEEP → TERMINATE for nodes not in the spread set
            # (PPE may have marked them KEEP because "already optimal", but
            # consolidation requires moving pods off excess nodes)
            _existing = node_transitions.get(_nname)
            if _existing is None or _existing.get('type') == 'KEEP':
                # Never terminate a node that has active/in-progress agent ops
                # (drain, terminate) — those are handled by the actuator already.
                # But od_anchor retention is only a soft PPE hint, NOT a hard
                # exclusion. In a pure OD cluster every node gets od_anchor, which
                # would permanently block all consolidation. Only preserve od_anchor
                # nodes when they are the SOLE representative of their AZ and we
                # don't yet have min_az_spread coverage.
                _existing_reason = node_keep_meta.get(_nname, {}).get('retention_reason')
                if _existing_reason == 'od_anchor':
                    # Check if removing this node would violate AZ spread
                    _this_az = _node_meta_map.get(_nname, {}).get('az') or 'unknown'
                    _azs_covered = set(
                        _node_meta_map.get(k, {}).get('az')
                        for k in _spread_keep_names
                    )
                    if _this_az not in _azs_covered:
                        # Only AZ representative — keep it to honour spread
                        _spread_keep_names.add(_nname)
                        logger.debug(
                            "az_spread_anchor_protected cluster=%s node=%s reason=sole_az_rep",
                            cluster_id, _nname,
                        )
                        continue
                    # AZ already covered → safe to terminate this od_anchor node
                node_transitions[_nname] = {'type': 'TERMINATE', 'replacement_spec': None, 'pods_leaving': []}
                node_workload_meta[_nname] = {'workload_class': 'stateless', 'execution_strategy': 'ROLLING'}
                node_keep_meta.pop(_nname, None)
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

    # ── Step 5: Ensure every app pod on a drain node has an explicit destination ──
    # ALL running non-DaemonSet non-system pods on TERMINATE/REPLACE nodes that are
    # not yet in pods_leaving must receive a destination node.  Two label categories
    # (kept for UI display) but the routing logic is identical for both:
    #   - is_compliant_drain=True  : WIE classified this workload (in wc_rows) but
    #     Target Builder skipped it (already at desired OD/Spot ratio).
    #   - is_unclassified=True     : no WCR entry — WIE has never classified it.
    # Assignment uses capacity-aware least-loaded-first:
    #   projected_load(n) = current_pods(n) + incoming_from_plan(n) + step5_assigned(n)
    # This ensures the plan is self-consistent — we can consolidate 4 nodes → 2 nodes
    # only when every pod has an explicit destination.
    _drain_node_names = [n for n, t in node_transitions.items() if t["type"] in ("TERMINATE", "REPLACE")]
    if _drain_node_names:
        # Build controller set from the FULL WCR table — not the limit(500) subset of wc_rows —
        # so workloads beyond the processing limit are still marked as WIE-known in Step 5.
        _wie_known_controllers: set = set(
            row[0]
            for row in db.query(WorkloadClassificationRecord.name)
            .filter(WorkloadClassificationRecord.cluster_id == cluster_id)
            .all()
        )

        # ── Keep-node capacity tracker ───────────────────────────────────────
        _keep_node_names = [n for n, t in node_transitions.items() if t["type"] == "KEEP"]

        # Count pods already incoming to each keep node from Steps 1-4 PPE plan
        _keep_incoming: dict = {n: 0 for n in _keep_node_names}
        for _dn, _dtr in node_transitions.items():
            if _dtr["type"] not in ("TERMINATE", "REPLACE"):
                continue
            for _pl in _dtr.get("pods_leaving", []):
                _dest = _pl.get("to_node")
                if _dest and _dest in _keep_incoming:
                    _keep_incoming[_dest] = _keep_incoming[_dest] + 1

        # Track CPU millicores assigned in Step 5 per keep node
        _keep_step5_cpu: dict = {n: 0 for n in _keep_node_names}
        # Rough CPU capacity per keep node (allocatable minus DaemonSet/system headroom)
        _keep_cpu_cap: dict = {}
        for _nm_row in _node_rows:
            if _nm_row.node_name in _keep_node_names:
                _alloc = _nm_row.allocatable_cpu_millicores or 4000
                _keep_cpu_cap[_nm_row.node_name] = int(_alloc * 0.85)  # 15% headroom

        def _pick_dest(pod_cpu_m: int):
            """Return (node_name, itype, cap_type) for the keep node with most remaining capacity."""
            if not _keep_node_names:
                return None, None, None
            _best = min(
                _keep_node_names,
                key=lambda n: (
                    _node_total_pods.get(n, 0)
                    + _keep_incoming.get(n, 0)
                    + _keep_step5_cpu.get(n, 0) // max(pod_cpu_m, 50)
                ),
            )
            _keep_step5_cpu[_best] = _keep_step5_cpu.get(_best, 0) + max(pod_cpu_m, 50)
            return (
                _best,
                _node_meta_map.get(_best, {}).get("instance_type"),
                _node_meta_map.get(_best, {}).get("capacity_type"),
            )

        _already_planned: dict = {
            n: {p["pod_name"] for p in node_transitions[n].get("pods_leaving", [])}
            for n in _drain_node_names
        }
        try:
            _aug_rows = (
                db.query(
                    PodMetric.pod_name,
                    PodMetric.node_name,
                    PodMetric.controller_name,
                    PodMetric.cpu_request_millicores,
                )
                .filter(
                    PodMetric.cluster_id == cluster_id,
                    PodMetric.node_name.in_(_drain_node_names),
                    PodMetric.controller_kind != "DaemonSet",
                    ~PodMetric.namespace.in_(list(_SYSTEM_NS)),
                    (PodMetric.phase == "Running") | (PodMetric.phase.is_(None)),
                    PodMetric.timestamp > _cutoff,
                )
                .distinct(PodMetric.pod_name)
                .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
                .all()
            )
            for _ur in _aug_rows:
                _nn = _ur.node_name or ""
                if _nn not in _already_planned:
                    continue
                if _ur.pod_name in _already_planned[_nn]:
                    continue
                _ctrl = (_ur.controller_name or "").split("/")[-1]
                _is_wie_known = _ctrl in _wie_known_controllers
                _pod_cpu = int(_ur.cpu_request_millicores or 50)
                _dest_node, _dest_itype, _dest_cap = _pick_dest(_pod_cpu)
                node_transitions[_nn]["pods_leaving"].append({
                    "pod_name": _ur.pod_name,
                    "to_node": _dest_node,
                    "to_instance_type": _dest_itype,
                    "to_capacity_type": _dest_cap,
                    "is_new_node": False,
                    "is_unclassified": not _is_wie_known,
                    "is_compliant_drain": _is_wie_known,
                })
        except Exception as _ue:
            logger.warning("step5_augment_error cluster=%s err=%s", cluster_id, _ue)

    # ── Step 6: Final mutual-exclusivity reconciliation ───────────────────────
    # After all PPE runs, a node can still appear in both KEEP and TERMINATE
    # if two separate workloads gave conflicting signals (e.g. workload A wants
    # to drain it, workload B keeps it as an OD anchor).  Rule: KEEP always wins
    # — a node kept for any workload must not be simultaneously drained.
    # Step 6a: Drop terminated nodes from node_transitions entirely.
    # They were excluded from nodes_input but PPE may have still classified
    # their pods as needing to move, adding the node as TERMINATE. We do NOT
    # want them in keep_nodes OR drain_nodes — their pods are already gone.
    _dead_nodes = _terminated_instance_nodes | _recently_terminated_nodes
    for _dn in list(node_transitions.keys()):
        if _dn in _dead_nodes:
            del node_transitions[_dn]

    # Step 6b: Force-KEEP nodes that are ACTIVELY draining or mid-rebalance.
    # This is intentionally limited to live in-flight operations only — NOT
    # terminated nodes (handled above).
    _active_live_nodes = draining_nodes | active_rebalancing_nodes
    _collision_nodes = []
    for _nname, _trans in list(node_transitions.items()):
        _is_actively_managed = _nname in _active_live_nodes
        if _is_actively_managed:
            # Node is under active rebalancing/drain — lock it as KEEP so UI
            # shows "Rebalancing in Progress" and PPE cannot schedule further drains.
            if _trans["type"] in ("TERMINATE", "REPLACE"):
                _collision_nodes.append(_nname)
                node_transitions[_nname] = {
                    "type": "KEEP",
                    "replacement_spec": None,
                    "pods_leaving": [],
                    "_active_rebalancing": True,
                }
    if _collision_nodes:
        logger.warning(
            "cluster_plan_collision_resolved cluster=%s nodes=%s reason=active_rebalancing_forced_keep",
            cluster_id, _collision_nodes,
        )

    # Step 6c: Honour do_not_disrupt flag — Karpenter anchor nodes and any node
    # the user has annotated with karpenter.sh/do-not-disrupt=true must NEVER
    # appear as drain/terminate candidates in the consolidation plan.
    _dnd_nodes = {n.node_name for n in _node_rows if getattr(n, "do_not_disrupt", False)}
    _dnd_forced_keep = []
    for _dnd in _dnd_nodes:
        if _dnd in node_transitions and node_transitions[_dnd].get("type") in ("TERMINATE", "REPLACE"):
            _dnd_forced_keep.append(_dnd)
            node_transitions[_dnd] = {
                "type": "KEEP",
                "replacement_spec": None,
                "pods_leaving": [],
                "_do_not_disrupt": True,
            }
    if _dnd_forced_keep:
        logger.info(
            "cluster_plan_dnd_forced_keep cluster=%s nodes=%s",
            cluster_id, _dnd_forced_keep,
        )

    # ── Log nodes skipped entirely due to active operations ──────────────────
    if _nodes_to_ignore:
        logger.info(
            "cluster_plan_nodes_ignored cluster=%s count=%d draining=%s rebalancing=%s terminated=%s",
            cluster_id,
            len(_nodes_to_ignore),
            sorted(draining_nodes),
            sorted(active_rebalancing_nodes),
            sorted(_dead_nodes),
        )

    # ── Batch prefetch pods_staying for ALL keep nodes (1 query vs N) ─────────
    _keep_nnames_batch = [n for n, t in node_transitions.items() if t["type"] == "KEEP"]
    _pods_staying_cutoff = _dt.utcnow() - _td(minutes=5)
    _pods_staying_by_node: dict = {}
    if _keep_nnames_batch:
        try:
            _batch_ks = (
                db.query(
                    PodMetric.pod_name,
                    PodMetric.node_name,
                    PodMetric.cpu_request_millicores,
                    PodMetric.memory_request_bytes,
                )
                .filter(
                    PodMetric.cluster_id == cluster_id,
                    PodMetric.node_name.in_(_keep_nnames_batch),
                    PodMetric.controller_kind != "DaemonSet",
                    ~PodMetric.namespace.in_(list(_SYSTEM_NS)),
                    PodMetric.phase.notin_(["Succeeded", "Failed", "Unknown"]),
                    PodMetric.timestamp > _pods_staying_cutoff,
                )
                .distinct(PodMetric.pod_name)
                .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
                .all()
            )
            for _ksr in _batch_ks:
                _pods_staying_by_node.setdefault(_ksr.node_name, []).append(_ksr)
        except Exception:
            pass

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
            # Build pods_staying: pods currently running on this keep node that are NOT moving.
            # Use a 5-min freshness window (not the 30-min _cutoff) so that recently-terminated
            # pods (e.g. old ReplicaSet pod after a rolling restart) don't appear alongside the
            # new replacement pod. The agent reports pod metrics every ~1 min so 5 min gives
            # 5 missed-report tolerance for live pods.
            _keep_pods_staying = [
                {
                    "pod_name": r.pod_name,
                    "cpu_request_millicores": r.cpu_request_millicores,
                    "memory_request_mb": round((r.memory_request_bytes or 0) / (1024 * 1024), 1),
                    "routing_source": "staying",
                }
                for r in _pods_staying_by_node.get(nname, [])
            ]
            keep_nodes.append({
                "node_name":        nname,
                "instance_type":    nm.get("instance_type") or kmeta.get("instance_type"),
                "capacity_type":    _cap_nm,
                "az":               nm.get("az") or (None if kmeta.get("az") == "unknown" else kmeta.get("az")),
                "pod_count":        kmeta.get("pod_count") or nm.get("pod_count"),
                "retention_reason": kmeta.get("retention_reason") or (
                    "od_anchor" if _is_od else "fits_pods"
                ),
                "retained_workload_classes": [],
                "pods_staying": _keep_pods_staying,
            })

    # ── Compute pods_incoming for each keep node from drain_nodes.pods_leaving ──
    _keep_incoming_pods: dict = {kn["node_name"]: [] for kn in keep_nodes}
    for _dn in drain_nodes:
        for _pl in _dn.get("pods_leaving", []):
            _dest = _pl.get("to_node")
            if _dest and _dest in _keep_incoming_pods:
                _keep_incoming_pods[_dest].append({
                    "pod_name": _pl["pod_name"],
                    "from_node": _dn["node_name"],
                    "from_instance_type": _dn.get("current_instance_type"),
                    "routing_source": (
                        "ppe_migration" if not _pl.get("is_compliant_drain") and not _pl.get("is_unclassified")
                        else "step5_classified" if _pl.get("is_compliant_drain")
                        else "step5_unclassified"
                    ),
                })
    for kn in keep_nodes:
        kn["pods_incoming"] = _keep_incoming_pods.get(kn["node_name"], [])

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
        # Distinguish: no WC data yet (new cluster, never scanned) vs genuinely optimal.
        # Empty wc_rows means the analysis engine hasn't run yet — surface as 'none'
        # so the frontend prompts the user to scan rather than showing "at target state".
        plan_status = "no_action" if wc_rows else "none"
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

    # ── Flat pod routing table — all app pods, one row each ──────────────────────────
    # Consolidates drain_nodes.pods_leaving + keep_nodes.pods_staying into a
    # single lookup for full end-to-end pod routing visibility.
    _pod_routing_table: list = []
    for _dn in drain_nodes:
        _from_node = _dn["node_name"]
        for _pm in _dn["pods_leaving"]:
            _to = _pm.get("to_node")
            _routing_src = (
                "ppe_migration" if not _pm.get("is_compliant_drain") and not _pm.get("is_unclassified")
                else "step5_classified" if _pm.get("is_compliant_drain")
                else "step5_unclassified"
            )
            _pod_routing_table.append({
                "pod_name": _pm["pod_name"],
                "from_node": _from_node,
                "from_capacity_type": _dn.get("current_capacity_type"),
                "to_node": _to,
                "to_capacity_type": _pm.get("to_capacity_type"),
                "to_instance_type": _pm.get("to_instance_type"),
                "is_new_node": _pm.get("is_new_node", False),
                "routing_source": _routing_src,
            })
    for _kn in keep_nodes:
        for _ks in _kn.get("pods_staying", []):
            _pod_routing_table.append({
                "pod_name": _ks["pod_name"],
                "from_node": _kn["node_name"],
                "from_capacity_type": _kn.get("capacity_type"),
                "to_node": _kn["node_name"],
                "to_capacity_type": _kn.get("capacity_type"),
                "to_instance_type": _kn.get("instance_type"),
                "is_new_node": False,
                "routing_source": "staying",
            })

    # ── Orchestration Context ───────────────────────────────────────
    # Check if a global lock is held (Karpenter race mitigation)
    _lock_active = False
    _lock_key = f"rebalance:lock:{cluster_id}"
    if _plan_redis and _plan_redis.exists(_lock_key):
        _lock_active = True

    _plan_payload = {
        "cluster_id":             cluster_id,
        "plan_status":            plan_status,
        "drain_nodes":            drain_nodes,
        "keep_nodes":             keep_nodes,
        "provision_nodes":        deduped_provisions,
        "draining_nodes":         sorted(draining_nodes),
        "rebalancing_nodes":      sorted(active_rebalancing_nodes),
        "karpenter_lock_active":   _lock_active, # UI indicator for Blocker 2
        "global_orchestration_lock": _lock_active,
        "summary":                {
            **summary,
            "total_pods_in_plan": len(_pod_routing_table),
            "pods_moving":   sum(1 for p in _pod_routing_table if p["from_node"] != p["to_node"]),
            "pods_staying":  sum(1 for p in _pod_routing_table if p["from_node"] == p["to_node"]),
            "pods_to_spot":  sum(1 for p in _pod_routing_table if (p.get("to_capacity_type") or "").lower() == "spot"),
            "pods_to_od":    sum(1 for p in _pod_routing_table if (p.get("to_capacity_type") or "").lower() in ("on-demand", "on_demand", "ondemand")),
            "nodes_skipped_active_ops": len(_nodes_to_ignore),
        },
        "pod_routing_table":      _pod_routing_table,
        "spot_migration_decision": _agg_spot_decision,
    }
    if _plan_redis:
        try:
            _plan_redis.setex(_plan_cache_key, _PLAN_CACHE_TTL, json.dumps(_plan_payload, default=str))
        except Exception:
            pass
    return ok(_plan_payload)



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
            (PodMetric.phase == "Running") | (PodMetric.phase.is_(None)),
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

    has_drain  = any(a["action_type"] in ("DRAIN_NODE", "TERMINATE_NODE", "FORCE_DELETE_NODE") for a in pending_node_actions)
    has_cordon = any(a["action_type"] == "CORDON_NODE" for a in pending_node_actions)
    cap_type = (node_meta_row.capacity_type or "").lower() if node_meta_row else ""
    is_od = cap_type in ("on_demand", "on-demand", "ondemand")

    # ── Cluster-plan state: check whether this node is actively managed ───────
    # The heuristic below has no access to the cluster plan context.  Without
    # this check, a KEEP node with low utilisation returns "Consolidate → Spot"
    # (because it looks idle) even though the plan explicitly protects it as an
    # OD anchor.  We check AgentAction DRAIN + RebalancingAction to detect this.
    _is_actively_draining_plan = False
    _is_actively_rebalancing_plan = False
    try:
        from backend.models.rebalancing_action import RebalancingAction as _RA
        from backend.models.instance import Instance as _Inst
        _ra_row = (
            db.query(_RA)
            .join(
                _Inst,
                (_RA.cluster_id == _Inst.cluster_id)
                & (_RA.source_instance_id == _Inst.instance_id),
            )
            .filter(
                _RA.cluster_id == cluster_id,
                _RA.status.in_(["pending", "in_progress", "waiting_agent", "pending_approval"]),
                _Inst.node_name == node_name,
            )
            .first()
        )
        if _ra_row:
            _is_actively_rebalancing_plan = True
    except Exception:
        pass

    if has_drain:
        opt_action = "Terminating"
        opt_detail = "Drain action queued — pods are being migrated away from this node."
        opt_color  = "red"
    elif has_cordon:
        opt_action = "Cordoned"
        opt_detail = "Cordon action queued — no new pods will be scheduled here."
        opt_color  = "amber"
    elif _is_actively_rebalancing_plan:
        # Node is mid-flight in a RebalancingAction — cluster plan controls it.
        # Do not return heuristic guidance that contradicts the plan state.
        opt_action = "Rebalancing in Progress"
        opt_detail = (
            "This node is currently under an active rebalancing operation. "
            "The optimizer will resume normal analysis once the operation completes."
        )
        opt_color  = "blue"
        # Surface buffer pct for informational display only (not decision basis)
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
        # Surface rebalancing flag so frontend can display plan-aware label even
        # when the cluster plan data hasn't loaded yet in the session.
        "is_actively_rebalancing": _is_actively_rebalancing_plan,
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
    import math

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

    # ── RIGHTSIZING PROPOSAL for this workload (Phase 3) ─────────────────
    # Compute on-the-fly from pod_metrics so the Resource Utilization card
    # in the frontend has real P95/burst_ratio/throttle_risk data.
    proposal_dict = None
    if max_pm_ts is not None:
        try:
            from backend.services.rightsizing_service import RightSizingService as _RSS
            _rss = _RSS(db)
            _namespace = wc.namespace if wc else workload_id.split("/")[0] if "/" in workload_id else None
            _proposals = _rss.generate_recommendations(
                cluster_id=cluster_id,
                namespace=_namespace,
                analysis_window_hours=168,
                min_data_points=50,
            )
            for _p in _proposals:
                if _p.controller_name == workload_name:
                    proposal_dict = _p.model_dump() if hasattr(_p, "model_dump") else _p.dict()
                    break
        except Exception as _pe:
            logger.warning(f"[profiling-detail] proposal lookup failed for {workload_name}: {_pe}")

        # If the recommendation engine skipped this workload because of confidence,
        # freshness, draft state, or sample count gates, still return a read-only
        # utilization snapshot so the frontend can show Resource Utilization for
        # every workload with pod metrics.
        if proposal_dict is None:
            try:
                metric_rows = (
                    db.query(PodMetric)
                    .filter(
                        PodMetric.cluster_id == cluster_id,
                        PodMetric.controller_name == workload_name,
                        PodMetric.timestamp > _dt.utcnow() - _td(hours=168),
                    )
                    .order_by(PodMetric.timestamp)
                    .all()
                )

                def _percentile(values, pct):
                    if not values:
                        return 0
                    sorted_values = sorted(values)
                    idx = int((pct / 100) * (len(sorted_values) - 1))
                    return sorted_values[min(idx, len(sorted_values) - 1)]

                if metric_rows:
                    latest_metric = metric_rows[-1]
                    cpu_values = [m.cpu_usage_millicores or 0 for m in metric_rows]
                    mem_values = [m.memory_usage_bytes or 0 for m in metric_rows]
                    cpu_avg = sum(cpu_values) / len(cpu_values) if cpu_values else 0
                    mem_avg = sum(mem_values) / len(mem_values) if mem_values else 0
                    cpu_p95 = _percentile(cpu_values, 95)
                    cpu_p99 = _percentile(cpu_values, 99)
                    mem_p95 = _percentile(mem_values, 95)
                    mem_p99 = _percentile(mem_values, 99)
                    current_cpu_request = latest_metric.cpu_request_millicores or None
                    current_memory_request_bytes = latest_metric.memory_request_bytes or None
                    current_memory_request_mb = (
                        math.ceil(current_memory_request_bytes / (1024 * 1024))
                        if current_memory_request_bytes else None
                    )
                    burst_ratio = cpu_p99 / max(cpu_avg, 1.0)

                    jvm_signals = (
                        "java", "spring", "jvm", "tomcat", "quarkus", "micronaut",
                        "openjdk", "amazoncorretto", "adoptopenjdk",
                    )
                    is_jvm = any(signal in workload_name.lower() for signal in jvm_signals)
                    if not is_jvm and mem_avg > 0 and (mem_p99 / max(mem_avg, 1.0)) > 1.8:
                        is_jvm = True

                    burst_threshold = 3.0 if is_jvm else 5.0
                    proposal_dict = {
                        "cluster_id": cluster_id,
                        "namespace": wc.namespace if wc else (workload_id.split("/")[0] if "/" in workload_id else "default"),
                        "controller_kind": wc.controller_kind if wc else None,
                        "controller_name": workload_name,
                        "current_cpu_request_millicores": current_cpu_request,
                        "current_memory_request_mb": current_memory_request_mb,
                        "current_replica_count": len({m.pod_name for m in metric_rows if m.pod_name}) or 1,
                        "cpu_p95_millicores": int(cpu_p95),
                        "cpu_p99_millicores": int(cpu_p99),
                        "memory_p95_mb": math.ceil(mem_p95 / (1024 * 1024)),
                        "memory_p99_mb": math.ceil(mem_p99 / (1024 * 1024)),
                        "cpu_avg_millicores": int(cpu_avg),
                        "memory_avg_mb": math.ceil(mem_avg / (1024 * 1024)),
                        "recommended_cpu_request_millicores": None,
                        "recommended_memory_request_mb": None,
                        "current_cost_monthly": 0,
                        "recommended_cost_monthly": 0,
                        "savings_monthly": 0,
                        "savings_pct": 0,
                        "data_points": len(metric_rows),
                        "analysis_window_hours": 168,
                        "confidence": "LOW" if len(metric_rows) < 50 else "MEDIUM",
                        "is_oversized": False,
                        "is_undersized": False,
                        "recommendation_action": "NO_CHANGE",
                        "burst_ratio": round(burst_ratio, 2),
                        "throttle_risk": burst_ratio > burst_threshold,
                        "workload_hint": "JVM" if is_jvm else "NORMAL",
                        "currently_spiking": False,
                        "is_actionable": False,
                        "best_pool": None,
                        "utilization_only": True,
                    }
            except Exception as _ue:
                logger.warning(f"[profiling-detail] utilization fallback failed for {workload_name}: {_ue}")

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
            "proposal": proposal_dict,
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
            # v4.6 workload class fields — used by frontend status bar and badges
            "workload_class": getattr(wc, "workload_class", "stateless"),
            "wie_role": getattr(wc, "role", None),
            "min_on_demand_replicas": getattr(wc, "min_on_demand_replicas", None),
            "max_spot_replicas": getattr(wc, "max_spot_replicas", None),
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
    # 10 minutes: short enough to exclude terminated/restarted pod entries, long
    # enough that a running pod whose metrics tick every 30-60 s is always included.
    _pd_cutoff = _dt.utcnow() - _pd_td(minutes=10)
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
        .filter((PodMetric.phase == "Running") | (PodMetric.phase.is_(None)))
        .distinct(PodMetric.pod_name)
        .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
        .subquery()
    )
    # ── Bug fix: pre-build node→{az, capacity_type} lookup map from ALL NodeMetadata
    # rows for this cluster in ONE query. This replaces the outer-join approach which
    # returned NULL az when a NodeMetadata row didn't exist for a given node yet.
    # Multiple pods on the same node (very common — AZ repeats per node) all get the
    # correct AZ without any join ambiguity.
    _nm_rows_all = (
        db.query(NodeMetadata.node_name, NodeMetadata.az, NodeMetadata.capacity_type)
        .filter(NodeMetadata.cluster_id == cluster_id)
        .all()
    )
    _node_meta_cache: dict = {
        r.node_name: {"az": r.az, "capacity_type": r.capacity_type}
        for r in _nm_rows_all
        if r.node_name
    }

    # Simple pod query — no join needed since we resolve from _node_meta_cache
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
        )
        .filter(latest_subq.c.node_name.isnot(None))
        .all()
    )
    now = _dt.utcnow()

    # Redis WIE node state key — fallback when NodeMetadata is missing for a node
    # Written by agent heartbeat: spot:wie:node_state:{cluster_id}:{node_name}
    import json as _pd_json

    def _resolve_node_meta(node_name: str) -> dict:
        """Return {az, capacity_type} for a node, with Redis WIE fallback."""
        if not node_name:
            return {"az": "Unscheduled", "capacity_type": None}

        cached = _node_meta_cache.get(node_name)
        if cached and cached.get("az"):
            return cached
        # Fallback: Redis WIE node state
        try:
            _raw = redis_client.get(f"spot:wie:node_state:{cluster_id}:{node_name}")
            if _raw:
                _st = _pd_json.loads(_raw)
                _az = _st.get("az") or _st.get("availability_zone")
                _ct = _st.get("capacity_type") or _st.get("instance_lifecycle")
                if _az or _ct:
                    # Populate cache so subsequent pods on same node don't re-hit Redis
                    _node_meta_cache[node_name] = {"az": _az, "capacity_type": _ct}
                    return _node_meta_cache[node_name]
        except Exception:
            pass
        return cached or {"az": None, "capacity_type": None}

    pods = [
        {
            "pod_name": r.pod_name,
            "node_name": r.node_name,
            "az": _resolve_node_meta(r.node_name).get("az"),
            "capacity_type": _resolve_node_meta(r.node_name).get("capacity_type"),
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
    _pod_node_names = {p.get("node_name") for p in pods if p.get("node_name")}

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
        from backend.models.instance import Instance
        from sqlalchemy import func
        # Gather nodes from the cluster (only nodes that currently host workload pods + free nodes)
        _node_rows = (
            db.query(
                NodeMetadata.node_name,
                NodeMetadata.updated_at,
                func.coalesce(NodeMetadata.capacity_type, cast(Instance.lifecycle, SAString)).label("capacity_type"),
                func.coalesce(NodeMetadata.az, Instance.az).label("az"),
                func.coalesce(NodeMetadata.instance_type, Instance.instance_type).label("instance_type"),
                NodeMetadata.allocatable_cpu_millicores,
                NodeMetadata.allocatable_memory_bytes,
            )
            .outerjoin(
                Instance,
                (Instance.cluster_id == NodeMetadata.cluster_id)
                & (Instance.node_name == NodeMetadata.node_name)
            )
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
                NodeMetric.timestamp,
            )
            .filter(NodeMetric.cluster_id == cluster_id)
            .distinct(NodeMetric.node_name)
            .order_by(NodeMetric.node_name, NodeMetric.timestamp.desc())
            .all()
        )
        _node_usage = {r.node_name: (r.cpu_usage_millicores or 0, r.memory_usage_bytes or 0) for r in _latest_node_subq}
        _node_metric_ts = {r.node_name: r.timestamp for r in _latest_node_subq if r.node_name and r.timestamp}
        _now_detail = _dt.utcnow()
        nodes_input = []
        _node_freshness_ages: list[float] = []
        for n in _node_rows:
            _meta_age = (_now_detail - n.updated_at).total_seconds() if n.updated_at else None
            _metric_ts = _node_metric_ts.get(n.node_name)
            _metric_age = (_now_detail - _metric_ts).total_seconds() if _metric_ts else None
            _is_pod_host = n.node_name in _pod_node_names
            _is_fresh_candidate = (
                (_metric_age is not None and _metric_age <= 300)
                or (_meta_age is not None and _meta_age <= 300)
            )
            if not _is_pod_host and not _is_fresh_candidate:
                continue

            used_cpu, used_mem = _node_usage.get(n.node_name, (0, 0))
            if _metric_age is not None:
                _node_freshness_ages.append(_metric_age)
            elif _meta_age is not None and _is_pod_host:
                _node_freshness_ages.append(_meta_age)
            nodes_input.append({
                "node_name": n.node_name,
                "az": n.az,
                "capacity_type": n.capacity_type,
                "instance_type": n.instance_type,
                "allocatable_cpu_millicores": n.allocatable_cpu_millicores,
                "allocatable_memory_bytes": n.allocatable_memory_bytes,
                "used_cpu_millicores": used_cpu,
                "used_memory_bytes": used_mem,
                # Fix 2 (detail): pod_count=0 here; workload-detail PPE runs per-workload
                # so BinPacker uses pod list directly — node-level count not needed.
                "pod_count": 0,
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
        _state_age_candidates = []
        if pd_max_ts:
            _state_age_candidates.append((_now_detail - pd_max_ts).total_seconds())
        if _node_freshness_ages:
            _state_age_candidates.append(max(_node_freshness_ages))
        _detail_state_age = max(_state_age_candidates) if _state_age_candidates else None

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
            data_age_seconds=_detail_state_age,
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
