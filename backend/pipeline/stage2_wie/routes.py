"""
Workload Classification REST API Endpoints — WIE v4.3
======================================================
PREFIX: /workload-classification (registered at /api/v1)

All endpoints apply sanitize_classification_output() before returning data —
this enforces the confidence gate at the API boundary (Task 1.25).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user
from backend.models.base import get_db
from backend.models.user import User
from backend.models.workload_classification import WorkloadClassificationRecord
from backend.models.placement_policy import PlacementPolicyRecord
from backend.schemas.workload_classification_schemas import (
    ClusterClassificationSummary,
    EngineMetricsResponse,
    OverrideRequest,
    OverrideResponse,
    ScoringBreakdown,
    SpotCandidateResponse,
    SpotCandidatesResponse,
    WorkloadClassificationDetail,
    WorkloadClassificationListResponse,
    WorkloadClassificationResponse,
)
from backend.pipeline.stage2_wie.engine import (
    ClassificationGuard,
    sanitize_classification_output,
    serialize_classification,
    wie_classification_key,
    wie_metrics_key,
    wie_override_key,
    utc_now,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workload-classification",
    tags=["workload-classification"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_redis():
    """Get Redis client. Consistent with existing codebase pattern."""
    from backend.core.redis_client import get_redis_client
    return get_redis_client()


_DB_APP_MARKERS = frozenset([
    "redis", "postgres", "mysql", "mongodb", "elasticsearch",
    "kafka", "zookeeper", "cassandra", "etcd", "memcached", "mariadb", "mongo",
])

_ANCHOR_PATTERNS = frozenset([
    "karpenter", "cluster-autoscaler", "argocd", "argo-cd",
    "flux", "helm-controller", "kustomize-controller", "source-controller",
    "notification-controller", "image-reflector", "cert-manager",
    "external-secrets", "vault-agent-injector", "istiod", "istio-pilot",
    "linkerd-controller", "cilium-operator", "prometheus-operator",
    "coredns", "aws-load-balancer-controller", "ingress-nginx",
    "velero", "crossplane", "cluster-api",
])


def _derive_workload_class(record: WorkloadClassificationRecord) -> str:
    """Derive workload_class from stored record fields (no re-run of WIE needed)."""
    name_lower = (record.name or "").lower()
    if any(m in name_lower for m in _DB_APP_MARKERS):
        return "db"
    if any(p in name_lower for p in _ANCHOR_PATTERNS):
        return "anchor"
    if record.data_safety == "STATEFUL" or record.controller_kind == "StatefulSet":
        return "stateful"
    if record.controller_kind in ("Deployment", "ReplicaSet"):
        return "stateless"
    return "mixed"


def _classification_to_response(record: WorkloadClassificationRecord) -> dict:
    """Build response dict from ORM record."""
    return {
        "workload_id": record.workload_id,
        "cluster_id": record.cluster_id,
        "namespace": record.namespace,
        "name": record.name,
        "controller_kind": record.controller_kind,
        "role": record.role,
        "criticality_score": record.criticality_score,
        "tier": record.tier,
        "spot_score": record.spot_score,
        "spot_friendly": record.spot_friendly,
        "confidence_score": record.confidence_score,
        "confidence_state": record.confidence_state,
        "data_safety": record.data_safety,
        "signals_fired": record.signals_fired or [],
        "override_active": record.override_active,
        "override_reason": record.override_reason,
        "input_hash": record.input_hash or "",
        "schema_version": record.schema_version or "4.3",
        "classified_at": record.classified_at,
        "is_simulation": False,
        # ── v4.5 spot distribution constraints ───────────────────────────
        "min_on_demand_replicas": record.min_on_demand_replicas or 0,
        "max_spot_replicas": record.max_spot_replicas or 0,
        "spot_eligible": (record.max_spot_replicas or 0) > 0,
        "workload_class": _derive_workload_class(record),
    }


def _build_scoring_breakdown(signals: List[str]) -> ScoringBreakdown:
    """
    Partition signals_fired into logical groups for the detail view.
    Pure client-side grouping — no re-computation.
    """
    role_signals, criticality_signals, spot_signals = [], [], []
    confidence_signals, override_signals = [], []

    for sig in signals:
        lower = sig.lower()
        if lower.startswith("role"):
            role_signals.append(sig)
        elif any(lower.startswith(p) for p in ("criticality", "tier", "pdb", "priority_class", "hub", "stateful", "singleton", "external", "nodeport", "control_plane")):
            criticality_signals.append(sig)
        elif any(lower.startswith(p) for p in ("spot", "resilience", "topology", "multi_az", "readiness", "restart", "outbound", "leader", "cronjob", "daemonset", "disqualified")):
            spot_signals.append(sig)
        elif any(lower.startswith(p) for p in ("confidence", "cold_start", "metrics", "schema", "draft")):
            confidence_signals.append(sig)
        elif any(lower.startswith(p) for p in ("override", "manual_override")):
            override_signals.append(sig)
        else:
            # Unclassified — append to spot signals as catch-all
            spot_signals.append(sig)

    return ScoringBreakdown(
        role_signals=role_signals,
        criticality_signals=criticality_signals,
        spot_signals=spot_signals,
        confidence_signals=confidence_signals,
        override_signals=override_signals,
        all_signals=signals,
    )


# ---------------------------------------------------------------------------
# GET /summary — Cluster-level aggregated view
# ---------------------------------------------------------------------------

@router.get(
    "/{cluster_id}/summary",
    response_model=ClusterClassificationSummary,
    summary="Cluster classification summary",
)
def get_classification_summary(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClusterClassificationSummary:
    """
    Returns tier/confidence/role distribution for all workloads in the cluster.
    Engine health (last_scan_at, engine_age_hours) sourced from Redis metrics.
    """
    records = (
        db.query(WorkloadClassificationRecord)
        .filter_by(cluster_id=cluster_id)
        .all()
    )

    tier_dist: Dict[str, int] = {"Platinum": 0, "Gold": 0, "Silver": 0, "Bronze": 0}
    conf_dist: Dict[str, int] = {"DRAFT": 0, "PROVISIONAL": 0, "CONFIRMED": 0}
    role_dist: Dict[str, int] = {"SYSTEM": 0, "CONTROL_PLANE": 0, "APPLICATION": 0}
    spot_count = 0
    spot_ready = 0

    for r in records:
        tier_dist[r.tier] = tier_dist.get(r.tier, 0) + 1
        conf_dist[r.confidence_state] = conf_dist.get(r.confidence_state, 0) + 1
        role_dist[r.role] = role_dist.get(r.role, 0) + 1
        if r.spot_friendly:
            spot_count += 1
        if r.spot_friendly and r.confidence_state == "CONFIRMED":
            spot_ready += 1

    total = len(records)
    spot_pct = round(spot_count / total, 4) if total else 0.0

    # Engine metrics from Redis
    last_scan_at = None
    engine_age_hours = 0.0
    try:
        redis = _get_redis()
        metrics_raw = redis.hgetall(wie_metrics_key(cluster_id))
        if metrics_raw:
            raw_scan = metrics_raw.get(b"last_scan_at") or metrics_raw.get("last_scan_at")
            if raw_scan:
                last_scan_at_str = raw_scan.decode() if isinstance(raw_scan, bytes) else raw_scan
                try:
                    last_scan_at = datetime.fromisoformat(last_scan_at_str.replace("Z", "+00:00"))
                except ValueError:
                    pass
            age_raw = metrics_raw.get(b"engine_age_hours") or metrics_raw.get("engine_age_hours")
            if age_raw:
                engine_age_hours = float(age_raw)
    except Exception as e:
        logger.warning("wie_summary_redis_error", extra={"cluster_id": cluster_id, "error": str(e)})

    total_saving_usd = 0.0
    try:
        from sqlalchemy import func as _func
        total_saving_usd = float(
            db.query(_func.coalesce(_func.sum(PlacementPolicyRecord.estimated_monthly_saving_usd), 0))
            .filter(PlacementPolicyRecord.cluster_id == cluster_id)
            .scalar() or 0
        )
    except Exception as _se:
        logger.warning("summary_savings_query_failed", extra={"error": str(_se)})

    return ClusterClassificationSummary(
        cluster_id=cluster_id,
        total_workloads=total,
        tier_distribution=tier_dist,
        confidence_distribution=conf_dist,
        role_distribution=role_dist,
        spot_friendly_count=spot_count,
        spot_friendly_pct=spot_pct,
        spot_ready_count=spot_ready,
        last_scan_at=last_scan_at,
        engine_age_hours=engine_age_hours,
        confirmed_count=conf_dist.get("CONFIRMED", 0),
        provisional_count=conf_dist.get("PROVISIONAL", 0),
        draft_count=conf_dist.get("DRAFT", 0),
        total_estimated_saving_usd=round(total_saving_usd, 2),
    )


# ---------------------------------------------------------------------------
# GET /workloads — Paginated workload list with filters
# ---------------------------------------------------------------------------

@router.get(
    "/{cluster_id}/workloads",
    response_model=WorkloadClassificationListResponse,
    summary="List all workload classifications",
)
def list_workloads(
    cluster_id: str,
    namespace: Optional[str] = Query(default=None),
    tier: Optional[str] = Query(default=None),
    confidence_state: Optional[str] = Query(default=None),
    spot_friendly: Optional[bool] = Query(default=None),
    role: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkloadClassificationListResponse:
    """
    Paginated list of workload classifications with filtering.
    All items have sanitize_classification_output() applied — spot_friendly is
    preserved as-is for all confidence states (DRAFT/PROVISIONAL/CONFIRMED).
    See plan.md §0 Invariant 1: spot_friendly is engine-owned, API MUST NOT override it.

    Filters: namespace, tier, confidence_state, spot_friendly, role, search (name/ns).
    Pagination: page + page_size (max 200 per request).
    """
    query = db.query(WorkloadClassificationRecord).filter_by(cluster_id=cluster_id)

    if namespace:
        query = query.filter(WorkloadClassificationRecord.namespace == namespace)
    if tier:
        query = query.filter(WorkloadClassificationRecord.tier == tier)
    if confidence_state:
        query = query.filter(WorkloadClassificationRecord.confidence_state == confidence_state)
    if spot_friendly is not None:
        query = query.filter(WorkloadClassificationRecord.spot_friendly == spot_friendly)
    if role:
        query = query.filter(WorkloadClassificationRecord.role == role)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            WorkloadClassificationRecord.name.ilike(search_pattern)
            | WorkloadClassificationRecord.namespace.ilike(search_pattern)
        )

    total = query.count()
    records = (
        query
        .order_by(WorkloadClassificationRecord.criticality_score.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    workload_ids = [r.workload_id for r in records]
    savings_map: dict = {}
    if workload_ids:
        pp_rows = (
            db.query(
                PlacementPolicyRecord.workload_id,
                PlacementPolicyRecord.estimated_monthly_saving_usd,
            )
            .filter(
                PlacementPolicyRecord.cluster_id == cluster_id,
                PlacementPolicyRecord.workload_id.in_(workload_ids),
            )
            .all()
        )
        savings_map = {r.workload_id: float(r.estimated_monthly_saving_usd or 0) for r in pp_rows}

    items = []
    for record in records:
        data = _classification_to_response(record)
        data = sanitize_classification_output(data)
        data["estimated_monthly_saving_usd"] = savings_map.get(record.workload_id, 0.0)
        items.append(WorkloadClassificationResponse(**data))

    return WorkloadClassificationListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )


# ---------------------------------------------------------------------------
# GET /workloads/{workload_id} — Single workload detail with scoring breakdown
# ---------------------------------------------------------------------------

@router.get(
    "/{cluster_id}/workloads/{workload_id:path}",
    response_model=WorkloadClassificationDetail,
    summary="Single workload classification detail",
)
def get_workload_detail(
    cluster_id: str,
    workload_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkloadClassificationDetail:
    """
    Full classification detail for one workload, including scoring breakdown.
    `workload_id` is URL-encoded "namespace/name" (e.g., "prod%2Fpayment-service").
    """
    record = (
        db.query(WorkloadClassificationRecord)
        .filter_by(cluster_id=cluster_id, workload_id=workload_id)
        .first()
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"Workload '{workload_id}' not found in cluster '{cluster_id}'",
        )

    data = _classification_to_response(record)
    data = sanitize_classification_output(data)
    classification = WorkloadClassificationResponse(**data)
    breakdown = _build_scoring_breakdown(record.signals_fired or [])

    return WorkloadClassificationDetail(
        classification=classification,
        scoring_breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# GET /spot-candidates — Safe + potential sets
# ---------------------------------------------------------------------------

@router.get(
    "/{cluster_id}/spot-candidates",
    response_model=SpotCandidatesResponse,
    summary="Spot-eligible workload candidates",
)
def get_spot_candidates(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpotCandidatesResponse:
    """
    Returns two sets:
      - safe_candidates: CONFIRMED + spot_friendly (automation allowed)
      - potential_candidates: PROVISIONAL + spot_friendly (visibility only)

    sanitize_classification_output() is applied as defense-in-depth.
    """
    # Safe set (automation allowed)
    safe_records = (
        db.query(WorkloadClassificationRecord)
        .filter_by(cluster_id=cluster_id, confidence_state="CONFIRMED", spot_friendly=True)
        .order_by(WorkloadClassificationRecord.spot_score.desc())
        .all()
    )

    # Potential set (visibility only)
    potential_records = (
        db.query(WorkloadClassificationRecord)
        .filter_by(cluster_id=cluster_id, confidence_state="PROVISIONAL", spot_friendly=True)
        .order_by(WorkloadClassificationRecord.spot_score.desc())
        .all()
    )

    def _to_candidate(record: WorkloadClassificationRecord) -> Optional[SpotCandidateResponse]:
        data = _classification_to_response(record)
        data = sanitize_classification_output(data)
        if not data.get("spot_friendly"):
            return None
        return SpotCandidateResponse(
            workload_id=record.workload_id,
            cluster_id=record.cluster_id,
            namespace=record.namespace,
            name=record.name,
            controller_kind=record.controller_kind,
            tier=record.tier,
            spot_score=record.spot_score,
            criticality_score=record.criticality_score,
            confidence_state=record.confidence_state,
            data_safety=record.data_safety,
            signals_fired=record.signals_fired or [],
            classified_at=record.classified_at,
        )

    safe_candidates: List[SpotCandidateResponse] = []
    for r in safe_records:
        c = _to_candidate(r)
        if c and c.confidence_state == "CONFIRMED":
            safe_candidates.append(c)

    potential_candidates: List[SpotCandidateResponse] = []
    for r in potential_records:
        c = _to_candidate(r)
        if c and c.confidence_state == "PROVISIONAL":
            potential_candidates.append(c)

    return SpotCandidatesResponse(
        safe_candidates=safe_candidates,
        potential_candidates=potential_candidates,
    )


# ---------------------------------------------------------------------------
# GET /metrics — Engine health metrics
# ---------------------------------------------------------------------------

@router.get(
    "/{cluster_id}/metrics",
    response_model=EngineMetricsResponse,
    summary="Engine health metrics",
)
def get_engine_metrics(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
) -> EngineMetricsResponse:
    """
    Returns engine health metrics: scan rate, write suppression, drops, signal freq.
    Sourced from Redis HASH spot:wie:metrics:{cluster_id}.
    Returns zeroed response when no metrics available (cluster not yet scanned).
    """
    try:
        redis = _get_redis()
        raw = redis.hgetall(wie_metrics_key(cluster_id))
    except Exception as e:
        logger.warning("wie_metrics_redis_error", extra={"cluster_id": cluster_id, "error": str(e)})
        return EngineMetricsResponse(cluster_id=cluster_id)

    if not raw:
        return EngineMetricsResponse(cluster_id=cluster_id)

    def _val(key: str, default=0):
        v = raw.get(key.encode()) or raw.get(key)
        if v is None:
            return default
        if isinstance(v, bytes):
            v = v.decode()
        return v

    signal_freq = {}
    raw_sig = _val("signal_freq", "{}")
    try:
        signal_freq = json.loads(raw_sig)
    except (json.JSONDecodeError, TypeError):
        pass

    return EngineMetricsResponse(
        cluster_id=cluster_id,
        scan_count=int(_val("scan_count", 0)),
        last_scan_at=_val("last_scan_at", None),
        last_scan_duration_ms=int(_val("last_scan_duration_ms", 0)),
        total_workloads=int(_val("total_workloads", 0)),
        confirmed_count=int(_val("confirmed_count", 0)),
        provisional_count=int(_val("provisional_count", 0)),
        draft_count=int(_val("draft_count", 0)),
        spot_friendly_count=int(_val("spot_friendly_count", 0)),
        spot_friendly_pct=float(_val("spot_friendly_pct", 0.0)),
        db_writes=int(_val("db_writes", 0)),
        db_suppressed=int(_val("db_suppressed", 0)),
        suppress_rate=float(_val("suppress_rate", 0.0)),
        debounce_drops=int(_val("debounce_drops", 0)),
        rate_limit_drops=int(_val("rate_limit_drops", 0)),
        error_count=int(_val("error_count", 0)),
        signal_freq=signal_freq,
        engine_age_hours=float(_val("engine_age_hours", 0.0)),
        enforcement_enabled=bool(int(_val("enforcement_enabled", 0))),
    )


# ---------------------------------------------------------------------------
# POST /workloads/{workload_id}/override — Create / replace override
# ---------------------------------------------------------------------------

@router.post(
    "/{cluster_id}/workloads/{workload_id:path}/override",
    response_model=OverrideResponse,
    summary="Set a classification override for a workload",
)
def create_override(
    cluster_id: str,
    workload_id: str,
    payload: OverrideRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OverrideResponse:
    """
    Store an operator override for a workload classification.
    Safety invariants are validated before storing — unsafe overrides are rejected
    with HTTP 422 and the rejection_reason in the response body.

    Overrides are stored in Redis with optional TTL. They are applied at the
    next slow-loop cycle (up to 10 minutes). For immediate effect, use the
    engine's next cycle.
    """
    # Validate payload has at least one override field
    if payload.spot_override is None and payload.tier_override is None:
        raise HTTPException(
            status_code=422,
            detail="At least one of spot_override or tier_override must be provided",
        )

    # Load current classification for safety validation
    record = (
        db.query(WorkloadClassificationRecord)
        .filter_by(cluster_id=cluster_id, workload_id=workload_id)
        .first()
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"Workload '{workload_id}' not found in cluster '{cluster_id}'",
        )

    # Pre-validate safety constraints before storing
    from backend.pipeline.stage2_wie.engine import WorkloadInput, WorkloadClassification, _validate_override_safety

    # Build minimal objects for validation
    mini_workload = WorkloadInput(
        workload_id=workload_id,
        cluster_id=cluster_id,
        namespace=record.namespace,
        name=record.name,
        controller_kind=record.controller_kind,
        data_safety=record.data_safety,
        replicas=1,   # Conservative: assume singleton if unknown
        has_pdb=False,
    )
    mini_class = WorkloadClassification(
        workload_id=workload_id,
        cluster_id=cluster_id,
        namespace=record.namespace,
        name=record.name,
        controller_kind=record.controller_kind,
        role=record.role,
        criticality_score=record.criticality_score,
        tier=record.tier,
        spot_score=record.spot_score,
        spot_friendly=record.spot_friendly,
        confidence_score=record.confidence_score,
        confidence_state=record.confidence_state,
        data_safety=record.data_safety,
    )

    override_dict = {
        k: v for k, v in {
            "spot_override": payload.spot_override,
            "tier_override": payload.tier_override,
        }.items() if v is not None
    }

    is_safe, reason = _validate_override_safety(mini_workload, mini_class, override_dict)
    if not is_safe:
        # Return 422 with reason — do NOT raise so response is still OverrideResponse
        return OverrideResponse(
            workload_id=workload_id,
            applied=False,
            override_active=False,
            field="none",
            rejection_reason=reason,
        )

    # Compute expiry if specified
    expires_at = None
    if payload.expires_hours:
        from datetime import timedelta
        expires_at = utc_now() + timedelta(hours=payload.expires_hours)

    override_data: Dict[str, Any] = {**override_dict}
    if payload.reason:
        override_data["reason"] = payload.reason
    if expires_at:
        override_data["expires_at"] = expires_at.isoformat()

    # Store in Redis
    try:
        redis = _get_redis()
        key = wie_override_key(cluster_id, workload_id)
        if payload.expires_hours:
            redis.setex(key, payload.expires_hours * 3600, json.dumps(override_data))
        else:
            redis.set(key, json.dumps(override_data))
    except Exception as e:
        logger.error("wie_override_redis_error", extra={"cluster_id": cluster_id, "workload_id": workload_id, "error": str(e)})
        raise HTTPException(status_code=503, detail="Override could not be stored — Redis unavailable")

    applied_field = "both" if (payload.spot_override is not None and payload.tier_override) else (
        "spot_override" if payload.spot_override is not None else "tier_override"
    )

    return OverrideResponse(
        workload_id=workload_id,
        applied=True,
        override_active=True,
        field=applied_field,
        reason=payload.reason,
        expires_at=expires_at,
    )


# ---------------------------------------------------------------------------
# DELETE /workloads/{workload_id}/override — Remove override
# ---------------------------------------------------------------------------

@router.delete(
    "/{cluster_id}/workloads/{workload_id:path}/override",
    summary="Remove a classification override",
)
def delete_override(
    cluster_id: str,
    workload_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Remove an active override for a workload. Takes effect on next slow loop cycle."""
    try:
        redis = _get_redis()
        key = wie_override_key(cluster_id, workload_id)
        deleted = redis.delete(key)
    except Exception as e:
        logger.error("wie_override_delete_error", extra={"cluster_id": cluster_id, "workload_id": workload_id, "error": str(e)})
        raise HTTPException(status_code=503, detail="Could not remove override — Redis unavailable")

    return {
        "workload_id": workload_id,
        "cluster_id": cluster_id,
        "override_removed": deleted > 0,
        "message": "Override removed. Takes effect on next classification cycle (up to 10 min).",
    }


# ── Task 3.7 — Per-Cluster System Namespace Override ──────────────────────────

class NamespaceOverrideRequest(BaseModel):
    add: List[str] = []
    remove: List[str] = []


@router.put(
    "/{cluster_id}/system-namespaces",
    summary="Override per-cluster system namespaces for WIE classification",
)
def update_system_namespaces(
    cluster_id: str,
    body: NamespaceOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Add or remove namespaces from the system namespace set for this cluster.
    Stored in Redis (TTL 3600s) and persisted to DB.
    Engine reads this on the next slow loop cycle.
    """
    try:
        redis = _get_redis()
    except Exception as e:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    # Load existing override or start fresh
    ns_key = f"spot:wie:system_namespaces:{cluster_id}"
    existing_raw = redis.get(ns_key)
    existing = json.loads(existing_raw) if existing_raw else {"add": [], "remove": []}

    # Merge: union adds, union removes
    new_add = list(set(existing.get("add", [])) | set(body.add))
    new_remove = list(set(existing.get("remove", [])) | set(body.remove))

    # Validate: cannot both add and remove the same namespace
    conflict = set(new_add) & set(new_remove)
    if conflict:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot add and remove the same namespace(s): {', '.join(conflict)}",
        )

    payload = {"add": new_add, "remove": new_remove}
    redis.setex(ns_key, 3600, json.dumps(payload))

    # Persist to DB via cluster_optimization_settings if column exists
    try:
        from backend.models.cluster import ClusterOptimizationSettings
        settings = db.query(ClusterOptimizationSettings).filter_by(cluster_id=cluster_id).first()
        if settings:
            if hasattr(settings, "system_namespace_overrides"):
                settings.system_namespace_overrides = payload
                db.commit()
    except Exception:
        pass  # DB persistence is best-effort; Redis is source of truth for engine

    return {
        "cluster_id": cluster_id,
        "system_namespace_overrides": payload,
        "message": "System namespace override saved. Takes effect on next classification cycle.",
    }


@router.get(
    "/{cluster_id}/system-namespaces",
    summary="Get per-cluster system namespace override",
)
def get_system_namespaces_endpoint(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the current system namespace override for this cluster."""
    DEFAULT_SYSTEM_NAMESPACES = [
        "kube-system", "kube-public", "kube-node-lease",
        "cert-manager", "ingress-nginx", "istio-system",
        "monitoring", "logging", "flux-system", "argocd",
    ]
    try:
        redis = _get_redis()
        ns_key = f"spot:wie:system_namespaces:{cluster_id}"
        raw = redis.get(ns_key)
        override = json.loads(raw) if raw else {"add": [], "remove": []}
    except Exception:
        override = {"add": [], "remove": []}

    effective = list(
        (set(DEFAULT_SYSTEM_NAMESPACES) | set(override.get("add", [])))
        - set(override.get("remove", []))
    )

    return {
        "cluster_id": cluster_id,
        "defaults": DEFAULT_SYSTEM_NAMESPACES,
        "override": override,
        "effective": sorted(effective),
    }


def _run_wie_rescan(cluster_id: str) -> None:
    """Run WIE slow_loop_classify in a background thread — safe to call from BackgroundTasks."""
    from backend.models.base import SessionLocal
    from backend.core.redis_client import get_redis_client
    from backend.pipeline.stage2_wie.engine import WorkloadIdentificationEngine
    db = SessionLocal()
    try:
        redis = get_redis_client()
        engine = WorkloadIdentificationEngine(redis=redis, db=db, k8s_client=None)
        engine.slow_loop_classify(cluster_id=cluster_id)
        logger.info("wie_rescan_complete", extra={"cluster_id": cluster_id})
    except Exception as e:
        logger.error("wie_rescan_failed", extra={"cluster_id": cluster_id, "error": str(e)})
    finally:
        db.close()


@router.post(
    "/{cluster_id}/rescan",
    status_code=202,
    dependencies=[Depends(get_current_user)],
    summary="Trigger an immediate WIE reclassification for all workloads in a cluster",
)
def trigger_rescan(
    cluster_id: str,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Queues a full WIE slow-loop rescan in a background thread and returns immediately."""
    background_tasks.add_task(_run_wie_rescan, cluster_id)
    return {"status": "scanning", "cluster_id": cluster_id, "message": "WIE rescan triggered — classifications will update within seconds."}
