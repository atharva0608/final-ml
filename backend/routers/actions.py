"""
Action Management Router

Handles action queuing and execution for agent clusters.
Actions can be evictions, node operations, or deployment updates.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from ..models.base import get_db
from ..models.cluster import Cluster
from ..models.user import User
from ..models.agent_action import AgentAction, AgentActionStatus, AgentActionType
from ..core.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])
logger = logging.getLogger(__name__)


@router.get("/poll")
async def poll_actions(
    cluster_id: str = Query(..., description="Cluster ID to poll actions for"),
    db: Session = Depends(get_db)
):
    """
    Poll for pending actions for a specific cluster.

    Used by agents to check for pending actions to execute.
    Returns actions in PENDING status for the specified cluster.
    """
    try:
        # Find pending actions for this cluster
        actions = db.query(AgentAction).filter(
            AgentAction.cluster_id == cluster_id,
            AgentAction.status == AgentActionStatus.PENDING
        ).order_by(AgentAction.created_at).limit(10).all()

        # Mark actions as PICKED_UP
        for action in actions:
            action.status = AgentActionStatus.PICKED_UP
            action.picked_up_at = datetime.utcnow()

        db.commit()

        # Format response for agent
        action_list = []
        for action in actions:
            action_list.append({
                "id": str(action.id),
                "type": action.action_type.value,
                "parameters": action.payload or {},
                "signature": "",  # TODO: Implement HMAC signature
                "created_at": action.created_at.isoformat() if action.created_at else None
            })

        logger.info(f"Cluster {cluster_id} polled {len(action_list)} actions")

        return {
            "cluster_id": cluster_id,
            "actions": action_list,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error polling actions for cluster {cluster_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to poll actions: {str(e)}"
        )


@router.get("/active")
async def get_active_actions(
    cluster_id: str = Query(..., description="Cluster ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns PENDING and PICKED_UP agent_actions for a cluster, plus a recent
    window of COMPLETED/FAILED actions so the UI can show the full picture.
    Frontend polls this at /api/v1/actions/active?cluster_id=...
    """
    from backend.models.rebalancing_action import RebalancingAction
    from sqlalchemy import or_, and_
    from datetime import timedelta

    in_flight = (
        db.query(AgentAction)
        .filter(
            AgentAction.cluster_id == cluster_id,
            AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
        )
        .order_by(AgentAction.created_at.desc())
        .limit(50)
        .all()
    )

    _agent_terminal_cutoff = datetime.utcnow() - timedelta(hours=4)
    recent_terminal = (
        db.query(AgentAction)
        .filter(
            AgentAction.cluster_id == cluster_id,
            AgentAction.status.in_([AgentActionStatus.COMPLETED, AgentActionStatus.FAILED]),
            AgentAction.created_at >= _agent_terminal_cutoff,
        )
        .order_by(AgentAction.created_at.desc())
        .limit(20)
        .all()
    )

    def _serialize_action(a: AgentAction) -> dict:
        result = a.result or {}
        return {
            "id": str(a.id),
            "action_type": a.action_type.value,
            "status": a.status.value,
            "payload": a.payload or {},
            "retry_count": getattr(a, "retry_count", 0),
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "picked_up_at": a.picked_up_at.isoformat() if a.picked_up_at else None,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            "observed": result.get("observed", False),
            "expected": result.get("expected"),
            "verified_at": result.get("verified_at"),
            "failure_reason": result.get("failure_reason"),
        }

    # Active statuses are always returned.
    # Terminal statuses (failed/completed) stay visible for 24 h so the UI
    # can render a FAILED/COMPLETED badge instead of silently dropping nodes.
    _ra_cutoff = datetime.utcnow() - timedelta(hours=24)
    rebalancing_actions = (
        db.query(RebalancingAction)
        .filter(
            RebalancingAction.cluster_id == cluster_id,
            or_(
                RebalancingAction.status.in_(["in_progress", "waiting_agent", "pending"]),
                and_(
                    RebalancingAction.status.in_(["failed", "completed"]),
                    RebalancingAction.created_at >= _ra_cutoff,
                ),
            ),
        )
        .order_by(RebalancingAction.created_at.desc())
        .limit(20)
        .all()
    )

    def _serialize_ra(ra: RebalancingAction) -> dict:
        _meta = ra.action_metadata or {}
        _engine_source = (
            "consolidation"
            if getattr(ra, "source", "auto_rebalancer") == "placement_controller"
            else (_meta.get("provisioner_type") or "karpenter")
        )
        return {
            "id": str(ra.id),
            "trigger": ra.trigger,
            "source_pool": ra.source_pool,
            "target_pool": ra.target_pool,
            "source_node_name": _meta.get("source_node_name") or _meta.get("node_name"),
            "current_state": ra.current_state or ra.status,
            "status": ra.status,
            "action_step": ra.action_step,
            "migration_type": getattr(ra, "migration_type", None),
            "engine_source": _engine_source,
            "started_at": ra.started_at.isoformat() if ra.started_at else None,
            "completed_at": ra.completed_at.isoformat() if ra.completed_at else None,
            "error_message": ra.error_message,
            "nodes_affected": ra.nodes_affected,
            "pods_migrated": ra.pods_migrated,
            "node_name": (
                _meta.get("node_name")
                or _meta.get("source_node_name")
                or _meta.get("instance_id")
            ),
        }

    all_agent_actions = [_serialize_action(a) for a in in_flight + recent_terminal]
    active_count = len(in_flight)

    # Fetch pending/approved rightsizing proposals so the UI can show scheduled actions
    scheduled_actions = []
    try:
        from backend.models.rightsizing_proposal import RightsizingProposal, ProposalStatus
        proposals = (
            db.query(RightsizingProposal)
            .filter(
                RightsizingProposal.cluster_id == cluster_id,
                RightsizingProposal.status.in_([ProposalStatus.PENDING, ProposalStatus.APPROVED]),
            )
            .order_by(RightsizingProposal.id.desc())
            .limit(20)
            .all()
        )
        for p in proposals:
            scheduled_actions.append({
                "id": str(p.id),
                "action_type": "PATCH_CONTAINER_RESOURCES",
                "status": "SCHEDULED",
                "proposal_status": p.status.value,
                "payload": {
                    "is_rightsizing": True,
                    "workload_name": getattr(p, "workload_name", None) or getattr(p, "workload_id", None),
                    "current_resources": f"{p.current_vcpu}vCPU / {p.current_memory_gb}GB",
                    "target_resources": f"{p.proposed_vcpu}vCPU / {p.proposed_memory_gb}GB",
                    "estimated_savings": round(p.estimated_monthly_savings, 2),
                    "current_instance_type": p.current_instance_type,
                    "proposed_instance_type": p.proposed_instance_type,
                },
                "created_at": p.id,
            })
    except Exception:
        pass

    return {
        "agent_actions": all_agent_actions,
        "rebalancing_actions": [_serialize_ra(ra) for ra in rebalancing_actions],
        "scheduled_actions": scheduled_actions,
        "cluster_state": {
            "active_count": active_count,
            "batch_limit": 10,
            "mutex": False,
        },
    }


@router.post("/{action_id}/result")
async def update_action_result(
    action_id: str,
    result: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    Update the result of an action execution.

    Called by agents after executing an action to report success/failure.
    """
    try:
        # Find the action
        action = db.query(AgentAction).filter(AgentAction.id == action_id).first()

        if not action:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Action {action_id} not found"
            )

        # Update action with result
        success = result.get("success", False)
        action.status = AgentActionStatus.COMPLETED if success else AgentActionStatus.FAILED
        action.result = result
        action.completed_at = datetime.utcnow()
        action.error_message = result.get("error") or result.get("message") if not success else None

        db.commit()

        logger.info(f"Action {action_id} result updated: {action.status}")

        return {
            "success": True,
            "action_id": action_id,
            "status": action.status.value,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating action result for {action_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update action result: {str(e)}"
        )


@router.post("/")
async def create_action(
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new action for execution on a cluster.

    Queues an action to be picked up by the cluster agent.
    """
    try:
        cluster_id = payload.get("cluster_id")
        action_type = payload.get("action_type")
        parameters = payload.get("parameters", {})

        # Verify cluster exists
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )

        # Validate action type
        try:
            action_type_enum = AgentActionType(action_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action type: {action_type}"
            )

        # Create the action
        new_action = AgentAction(
            cluster_id=cluster_id,
            action_type=action_type_enum,
            payload=parameters,
            status=AgentActionStatus.PENDING
        )

        db.add(new_action)
        db.commit()
        db.refresh(new_action)

        logger.info(f"Created action {new_action.id} for cluster {cluster_id}")

        return {
            "success": True,
            "action_id": str(new_action.id),
            "cluster_id": cluster_id,
            "status": new_action.status.value,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating action: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create action: {str(e)}"
        )


@router.get("/timeline")
async def get_actions_timeline(
    cluster_id: str = Query(..., description="Cluster ID"),
    limit: int = Query(100, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns a unified, time-sorted event feed of agent_actions + rebalancing_actions
    for use by EventTimeline.jsx. All statuses included (in-flight + recent terminal).
    """
    from backend.models.rebalancing_action import RebalancingAction

    agent_actions = (
        db.query(AgentAction)
        .filter(AgentAction.cluster_id == cluster_id)
        .order_by(AgentAction.created_at.desc())
        .limit(limit)
        .all()
    )

    rebalancing_actions = (
        db.query(RebalancingAction)
        .filter(RebalancingAction.cluster_id == cluster_id)
        .order_by(RebalancingAction.created_at.desc())
        .limit(50)
        .all()
    )

    _STATE_PROGRESS = {
        "CREATED": 5, "POOL_SELECTED": 15, "SOURCE_CORDONED": 30,
        "SOURCE_DRAINED": 50, "REPLACEMENT_LAUNCHING": 65,
        "REPLACEMENT_READY": 80, "SOURCE_TERMINATING": 90,
        "COMPLETED": 100, "FAILED": 100,
    }

    def _severity(status: str) -> str:
        if status in ("FAILED", "failed"):      return "error"
        if status in ("COMPLETED", "completed"): return "success"
        if status in ("PENDING",):               return "info"
        return "warning"

    def _ra_progress(ra) -> int:
        return _STATE_PROGRESS.get(ra.current_state or "", 33)

    def _duration(started, ended=None):
        if not started: return None
        end = ended or datetime.utcnow()
        if isinstance(started, str):
            from datetime import datetime as _dt
            try: started = _dt.fromisoformat(started)
            except: return None
        return int((end - started).total_seconds())

    events = []

    for a in agent_actions:
        result = a.result or {}
        payload = a.payload or {}
        node = payload.get("node_name") or payload.get("node")
        workload = payload.get("workload_name") or payload.get("workload_id") or payload.get("deployment_name")
        # Derive granular lifecycle phase from ActionTracker Redis for EVICT_POD actions
        _phase = None
        try:
            from backend.core.redis_client import get_redis_client as _tl_redis
            _r = _tl_redis()
            if _r and a.action_type.value in ("EVICT_POD", "PATCH_AFFINITY"):
                _pod = payload.get("pod_name") or node or ""
                # Scan recent execution keys for this pod
                _pattern = f"spot:ee:action:{cluster_id}:*:{_pod}"
                _keys = _r.keys(_pattern)
                if _keys:
                    _raw = _r.hgetall(_keys[0])
                    _phase = (_raw.get(b"phase") or _raw.get("phase") or b"").decode() if isinstance(_raw.get(b"phase") or _raw.get("phase") or b"", bytes) else (_raw.get(b"phase") or _raw.get("phase") or "")
        except Exception:
            pass
        events.append({
            "id": f"aa-{a.id}",
            "event_type": "agent_action",
            "action_type": a.action_type.value,
            "status": a.status.value,
            "severity": _severity(a.status.value),
            "priority": getattr(a, "priority", 0),
            "title": a.action_type.value.replace("_", " ").title(),
            "node": node,
            "workload": workload,
            "payload": a.payload or {},
            "retry_count": getattr(a, "retry_count", 0),
            "error_message": a.error_message,
            "observed": result.get("observed", False),
            "failure_reason": result.get("failure_reason"),
            "phase": _phase or None,
            "timestamp": a.created_at.isoformat() if a.created_at else None,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            "duration_seconds": _duration(a.created_at, a.completed_at),
        })

    for ra in rebalancing_actions:
        dur = _duration(ra.started_at, ra.completed_at)
        events.append({
            "id": f"ra-{ra.id}",
            "event_type": "rebalancing",
            "action_type": "NODE_REBALANCE",
            "status": ra.status,
            "severity": _severity(ra.status),
            "priority": 10 if ra.trigger == "emergency" else 0,
            "title": f"{'Emergency' if ra.trigger == 'emergency' else 'Graceful'} Rebalance",
            "node": ra.source_pool,
            "workload": None,
            "payload": {
                "source_pool": ra.source_pool,
                "target_pool": ra.target_pool,
                "trigger": ra.trigger,
                "nodes_affected": ra.nodes_affected,
                "pods_migrated": ra.pods_migrated,
                "estimated_savings_mo": ra.estimated_savings_mo,
            },
            "retry_count": 0,
            "error_message": ra.error_message,
            "current_state": ra.current_state,
            "action_step": getattr(ra, "action_step", None),
            "progress": _ra_progress(ra),
            "timestamp": ra.started_at.isoformat() if ra.started_at else (ra.created_at.isoformat() if ra.created_at else None),
            "completed_at": ra.completed_at.isoformat() if ra.completed_at else None,
            "duration_seconds": dur,
        })

    events.sort(key=lambda e: e["timestamp"] or "", reverse=True)
    return {"cluster_id": cluster_id, "events": events[:limit]}


@router.get("/{action_id}")
async def get_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get details of a specific action.
    """
    try:
        action = db.query(AgentAction).filter(AgentAction.id == action_id).first()

        if not action:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Action {action_id} not found"
            )

        return {
            "id": str(action.id),
            "cluster_id": action.cluster_id,
            "action_type": action.action_type.value,
            "parameters": action.payload,
            "status": action.status.value,
            "result": action.result,
            "error_message": action.error_message,
            "created_at": action.created_at.isoformat() if action.created_at else None,
            "picked_up_at": action.picked_up_at.isoformat() if action.picked_up_at else None,
            "completed_at": action.completed_at.isoformat() if action.completed_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching action {action_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch action: {str(e)}"
        )


@router.get("/cluster/{cluster_id}")
async def list_cluster_actions(
    cluster_id: str,
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all actions for a specific cluster.
    """
    try:
        # Verify cluster exists
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )

        # Get actions
        actions = db.query(AgentAction).filter(
            AgentAction.cluster_id == cluster_id
        ).order_by(AgentAction.created_at.desc()).limit(limit).all()

        return {
            "cluster_id": cluster_id,
            "total": len(actions),
            "actions": [
                {
                    "id": str(action.id),
                    "action_type": action.action_type.value,
                    "status": action.status.value,
                    "created_at": action.created_at.isoformat() if action.created_at else None,
                    "completed_at": action.completed_at.isoformat() if action.completed_at else None
                }
                for action in actions
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing actions for cluster {cluster_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list actions: {str(e)}"
        )
