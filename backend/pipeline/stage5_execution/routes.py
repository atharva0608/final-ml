"""
Execution Data API Routes
=========================
Provides the missing frontend-required endpoints:
  GET /api/v1/pods?cluster_id=<id>
  GET /api/v1/agent-actions?cluster_id=<id>&limit=N
  GET /api/v1/nodeclaims?cluster_id=<id>

These aggregate data from existing DB models and serve the
WorkloadInventoryDashboard's live activity feed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.core.dependencies import get_current_user
from backend.models.base import get_db
from backend.models.user import User
from backend.models.pod_metric import PodMetric
from backend.models.agent_action import AgentAction, AgentActionStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["execution-data"])


# ---------------------------------------------------------------------------
# GET /placement-metrics — PlacementController skip reasons and metrics
# ---------------------------------------------------------------------------

@router.get(
    "/placement-metrics",
    summary="Get placement controller metrics and skip reasons",
)
def get_placement_metrics(
    cluster_id: str = Query(..., description="Cluster UUID"),
    workload_id: Optional[str] = Query(None, description="Workload ID for per-workload metrics (namespace/name)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns PlacementController Redis metrics including skip reasons breakdown.
    When workload_id is provided, returns per-workload metrics from
    spot:placement_controller:metrics:{cluster_id}:{workload_id}.
    Otherwise returns cluster-wide metrics.
    Used by WorkloadInventoryDashboard to show real optimization skip reasons.
    """
    from backend.core.redis_client import get_redis_client

    try:
        redis_client = get_redis_client()
        if workload_id:
            metrics_key = f"spot:placement_controller:metrics:{cluster_id}:{workload_id}"
        else:
            metrics_key = f"spot:placement_controller:metrics:{cluster_id}"
        metrics_data = redis_client.hgetall(metrics_key)
        
        # Convert strings to integers and provide defaults
        metrics = {
            "evictions_skipped_capacity": int(metrics_data.get("evictions_skipped_capacity", 0)),
            "evictions_skipped_cooldown": int(metrics_data.get("evictions_skipped_cooldown", 0)),
            "evictions_skipped_scaling_guard": int(metrics_data.get("evictions_skipped_scaling_guard", 0)),
            "evictions_skipped_pod_too_young": int(metrics_data.get("evictions_skipped_pod_too_young", 0)),
            "evictions_skipped_lock_contention": int(metrics_data.get("evictions_skipped_lock_contention", 0)),
            "evictions_skipped_batch_limit": int(metrics_data.get("evictions_skipped_batch_limit", 0)),
            "evictions_attempted": int(metrics_data.get("evictions_attempted", 0)),
            "evictions_succeeded": int(metrics_data.get("evictions_succeeded", 0)),
            "evictions_failed": int(metrics_data.get("evictions_failed", 0)),
        }
        
        # Calculate percentages for skip reasons
        total_skipped = sum([
            metrics["evictions_skipped_capacity"],
            metrics["evictions_skipped_cooldown"], 
            metrics["evictions_skipped_scaling_guard"],
            metrics["evictions_skipped_pod_too_young"],
            metrics["evictions_skipped_lock_contention"],
            metrics["evictions_skipped_batch_limit"]
        ])
        
        skip_reasons = []
        if total_skipped > 0:
            skip_reasons = [
                {"label": "PDB Constraint", "value": round((metrics["evictions_skipped_capacity"] / total_skipped) * 100), "color": "bg-blue-500"},
                {"label": "Cooldown", "value": round((metrics["evictions_skipped_cooldown"] / total_skipped) * 100), "color": "bg-orange-400"},
                {"label": "Scaling Guard", "value": round((metrics["evictions_skipped_scaling_guard"] / total_skipped) * 100), "color": "bg-gray-400"},
                {"label": "Pod Too Young", "value": round((metrics["evictions_skipped_pod_too_young"] / total_skipped) * 100), "color": "bg-yellow-400"},
                {"label": "Lock Contention", "value": round((metrics["evictions_skipped_lock_contention"] / total_skipped) * 100), "color": "bg-red-400"},
                {"label": "Batch Limit", "value": round((metrics["evictions_skipped_batch_limit"] / total_skipped) * 100), "color": "bg-purple-400"}
            ]
        
        return {
            "cluster_id": cluster_id,
            "metrics": metrics,
            "skip_reasons": skip_reasons,
            "total_skipped": total_skipped,
            "success_rate": round((metrics["evictions_succeeded"] / max(metrics["evictions_attempted"], 1)) * 100, 1)
        }
        
    except Exception as e:
        logger.error(f"Failed to get placement metrics for cluster {cluster_id}: {e}")
        return {
            "cluster_id": cluster_id,
            "metrics": {},
            "skip_reasons": [],
            "total_skipped": 0,
            "success_rate": 0
        }


# ---------------------------------------------------------------------------
# GET /rollout-status — Rollout success and timeout tracking
# ---------------------------------------------------------------------------

@router.get(
    "/rollout-status",
    summary="Get rollout success rate and active timeouts",
)
def get_rollout_status(
    cluster_id: str = Query(..., description="Cluster UUID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns rollout success rate and currently timing out workloads.
    Used by WorkloadInventoryDashboard to show real rollout status.
    """
    try:
        # Get recent RebalancingAction records for success rate
        recent_actions = db.query(AgentAction)\
            .filter(AgentAction.cluster_id == cluster_id)\
            .filter(AgentAction.action_type.in_(["scale", "eviction"]))\
            .order_by(desc(AgentAction.created_at))\
            .limit(100)\
            .all()
        
        if not recent_actions:
            return {
                "cluster_id": cluster_id,
                "success_rate": 0,
                "total_actions": 0,
                "active_timeouts": []
            }
        
        # Calculate success rate
        completed_actions = [a for a in recent_actions if a.status in ["COMPLETED", "FAILED"]]
        successful_actions = [a for a in completed_actions if a.status == "COMPLETED"]
        success_rate = round((len(successful_actions) / len(completed_actions)) * 100, 1) if completed_actions else 0
        
        # Find potentially timing out actions (pending > 10 minutes)
        from datetime import datetime, timedelta
        timeout_threshold = datetime.utcnow() - timedelta(minutes=10)
        
        pending_actions = db.query(AgentAction)\
            .filter(AgentAction.cluster_id == cluster_id)\
            .filter(AgentAction.status == "PENDING")\
            .filter(AgentAction.created_at < timeout_threshold)\
            .order_by(desc(AgentAction.created_at))\
            .limit(10)\
            .all()
        
        active_timeouts = []
        for action in pending_actions:
            age_minutes = int((datetime.utcnow() - action.created_at).total_seconds() / 60)
            timeout_limit = 10  # Default 10 minute timeout
            
            # Some actions might have different timeout limits
            if action.metadata and isinstance(action.metadata, dict):
                timeout_limit = action.metadata.get("timeout_minutes", 10)
            
            progress_pct = min((age_minutes / timeout_limit) * 100, 100)
            color = "bg-red-400" if progress_pct >= 90 else "bg-gray-400" if progress_pct >= 50 else "bg-green-400"
            
            active_timeouts.append({
                "workload_id": action.workload_id,
                "action_type": action.action_type,
                "age_minutes": age_minutes,
                "timeout_limit": timeout_limit,
                "progress_pct": progress_pct,
                "color": color
            })
        
        return {
            "cluster_id": cluster_id,
            "success_rate": success_rate,
            "total_actions": len(recent_actions),
            "active_timeouts": active_timeouts
        }
        
    except Exception as e:
        logger.error(f"Failed to get rollout status for cluster {cluster_id}: {e}")
        return {
            "cluster_id": cluster_id,
            "success_rate": 0,
            "total_actions": 0,
            "active_timeouts": []
        }


# ---------------------------------------------------------------------------
# GET /pods — Latest pod-level metrics per pod for a cluster
# ---------------------------------------------------------------------------

@router.get(
    "/pods",
    summary="List latest pod metrics for a cluster",
)
def list_pods(
    cluster_id: str = Query(..., description="Cluster UUID"),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns the most recent PodMetric record per pod for the given cluster.
    Used by WorkloadInventoryDashboard to calculate live drift metrics.
    """
    # Subquery: max timestamp per (cluster_id, namespace, pod_name)
    from sqlalchemy import func

    latest_ts_subq = (
        db.query(
            PodMetric.cluster_id,
            PodMetric.namespace,
            PodMetric.pod_name,
            func.max(PodMetric.timestamp).label("max_ts"),
        )
        .filter(PodMetric.cluster_id == cluster_id)
        .group_by(PodMetric.cluster_id, PodMetric.namespace, PodMetric.pod_name)
        .subquery()
    )

    records = (
        db.query(PodMetric)
        .join(
            latest_ts_subq,
            (PodMetric.cluster_id == latest_ts_subq.c.cluster_id)
            & (PodMetric.namespace == latest_ts_subq.c.namespace)
            & (PodMetric.pod_name == latest_ts_subq.c.pod_name)
            & (PodMetric.timestamp == latest_ts_subq.c.max_ts),
        )
        .limit(limit)
        .all()
    )

    items = []
    for r in records:
        meta = r.pod_metadata or {}
        items.append(
            {
                "pod_name": r.pod_name,
                "namespace": r.namespace,
                "node_name": r.node_name,
                "controller_kind": r.controller_kind,
                "controller_name": r.controller_name,
                # Expose capacity_type from pod_metadata if the agent populates it
                "capacity_type": meta.get("capacity_type", "unknown"),
                "status": meta.get("status", "Running"),
                "workload_id": f"{r.namespace}/{r.controller_name}" if r.controller_name else None,
                "cpu_usage_millicores": r.cpu_usage_millicores,
                "cpu_request_millicores": r.cpu_request_millicores,
                "memory_usage_bytes": r.memory_usage_bytes,
                "cpu_usage_pct": r.cpu_utilization_pct,
                "memory_usage_pct": r.memory_utilization_pct,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
        )

    return {"items": items, "total": len(items), "cluster_id": cluster_id}


# ---------------------------------------------------------------------------
# GET /agent-actions — Recent agent actions for a cluster
# ---------------------------------------------------------------------------

@router.get(
    "/agent-actions",
    summary="List agent actions for a cluster",
)
def list_agent_actions(
    cluster_id: str = Query(..., description="Cluster UUID"),
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None, description="Filter by status: PENDING, PICKED_UP, COMPLETED, FAILED"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns recent AgentAction records for the given cluster,
    ordered newest-first. Used by the Live Activity tab in the
    WorkloadInventoryDashboard.
    """
    query = db.query(AgentAction).filter(AgentAction.cluster_id == cluster_id)

    if status:
        try:
            status_enum = AgentActionStatus[status.upper()]
            query = query.filter(AgentAction.status == status_enum)
        except KeyError:
            pass  # Ignore invalid status filter

    records = (
        query
        .order_by(desc(AgentAction.created_at))
        .limit(limit)
        .all()
    )

    items = []
    for r in records:
        items.append(
            {
                "id": r.id,
                "cluster_id": r.cluster_id,
                "action_type": r.action_type.value if r.action_type else None,
                "status": r.status.value if r.status else None,
                "payload": r.payload or {},
                "priority": r.priority,
                "retry_count": r.retry_count,
                "result": r.result,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "picked_up_at": r.picked_up_at.isoformat() if r.picked_up_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            }
        )

    return {"items": items, "total": len(items), "cluster_id": cluster_id}


# ---------------------------------------------------------------------------
# GET /nodeclaims — Karpenter NodeClaim stubs (no CRD table yet)
# ---------------------------------------------------------------------------

@router.get(
    "/execution/status/{cluster_id}",
    summary="Get current Execution Engine state for a cluster",
)
def get_execution_status(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns the current Execution Engine state, active manifest, overrides, and
    verification snapshot for the given cluster.
    """
    try:
        from backend.pipeline.stage5_execution.engine import ManifestStore
        manifest = ManifestStore.read(cluster_id, db=db)
    except Exception:
        manifest = None

    state = "IDLE"
    overrides = None
    verification = None

    if manifest:
        raw_status = manifest.get("status", "")
        if raw_status in ("EXECUTING",):
            state = "EXECUTING"
        elif raw_status in ("READY",):
            state = "READY"
        elif raw_status in ("COMPLETED", "DONE"):
            state = "COMPLETED"
        elif raw_status in ("FAILED", "ERROR"):
            state = "FAILED"
        else:
            state = (raw_status or "IDLE").upper()
        overrides = manifest.get("overrides")
        verification = manifest.get("verification")

    return {
        "cluster_id": cluster_id,
        "state": state,
        "manifest": manifest,
        "overrides": overrides,
        "verification": verification,
    }


@router.get(
    "/nodeclaims",
    summary="List Karpenter NodeClaims for a cluster",
)
def list_nodeclaims(
    cluster_id: str = Query(..., description="Cluster UUID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Placeholder endpoint. Returns empty list until Karpenter NodeClaim
    CRD data is synced into the database by the agent.
    """
    return {"items": [], "total": 0, "cluster_id": cluster_id}
