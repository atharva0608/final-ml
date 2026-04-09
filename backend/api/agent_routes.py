"""
Agent Routes - API endpoints for Kubernetes agent communication

These endpoints handle:
- Agent registration (when agent starts up)
- Agent deregistration (when agent shuts down gracefully)
- Heartbeat updates (periodic health checks)
"""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.models.base import get_db
from backend.models.cluster import Cluster, ClusterStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"])


# --- Request/Response Schemas ---

class AgentRegisterRequest(BaseModel):
    cluster_id: str
    agent_id: str
    timestamp: str
    capabilities: List[str] = []
    version: str = "1.0.0"


class AgentDeregisterRequest(BaseModel):
    cluster_id: str
    agent_id: str
    timestamp: str


class AgentHeartbeatRequest(BaseModel):
    cluster_id: str
    agent_id: str
    timestamp: str
    metrics: Optional[dict] = None
    health: Optional[dict] = None


class AgentResponse(BaseModel):
    success: bool
    message: str
    agent_id: Optional[str] = None


# --- Helper function to validate API key ---

def validate_api_key(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
) -> Cluster:
    """
    Validate the agent's API key and return the associated cluster.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    api_key = authorization.replace("Bearer ", "")
    
    cluster = db.query(Cluster).filter(Cluster.api_key == api_key).first()
    if not cluster:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return cluster


# --- Endpoints ---

@router.post("/register", response_model=AgentResponse)
async def register_agent(
    request: AgentRegisterRequest,
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key)
):
    """
    Register an agent with the backend.
    
    This is called when the agent first starts up. It updates the cluster
    status to ACTIVE and records the agent registration.
    """
    # Verify cluster_id matches
    if request.cluster_id != cluster.id:
        raise HTTPException(
            status_code=403, 
            detail="Cluster ID mismatch"
        )
    
    # Update cluster status
    cluster.status = ClusterStatus.ACTIVE
    cluster.agent_installed = "Y"
    cluster.last_heartbeat = datetime.utcnow()
    
    db.commit()

    # Invalidate cluster list cache so UI shows agent-connected status immediately
    try:
        from backend.core.redis_client import get_redis_client
        _r = get_redis_client()
        if _r:
            for _key in _r.scan_iter("clusters:*"):
                _r.delete(_key)
    except Exception:
        pass
    
    return AgentResponse(
        success=True,
        message="Agent registered successfully",
        agent_id=request.agent_id
    )


@router.post("/deregister", response_model=AgentResponse)
async def deregister_agent(
    request: AgentDeregisterRequest,
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key)
):
    """
    Deregister an agent from the backend.
    
    This is called when the agent shuts down gracefully.
    """
    # Verify cluster_id matches
    if request.cluster_id != cluster.id:
        raise HTTPException(
            status_code=403, 
            detail="Cluster ID mismatch"
        )
    
    # Update cluster status to inactive
    cluster.status = ClusterStatus.INACTIVE
    cluster.agent_installed = "N"
    
    db.commit()
    
    return AgentResponse(
        success=True,
        message="Agent deregistered successfully",
        agent_id=request.agent_id
    )


@router.post("/heartbeat", response_model=AgentResponse)
async def agent_heartbeat(
    request: AgentHeartbeatRequest,
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key)
):
    """
    Receive heartbeat from agent.
    
    Updates the last_heartbeat timestamp to track agent health.
    """
    # Verify cluster_id matches
    if request.cluster_id != cluster.id:
        raise HTTPException(
            status_code=403, 
            detail="Cluster ID mismatch"
        )
    
    # Update heartbeat timestamp
    cluster.last_heartbeat = datetime.utcnow()

    # Self-heal: always mark ACTIVE + agent_installed=Y when a live heartbeat arrives.
    # The old condition (only if status != ACTIVE) left the cluster stuck at
    # agent_installed='N' after node-termination events where deregister() fired but
    # new agent pods couldn't recover because status was back to ACTIVE while
    # agent_installed stayed 'N'.
    cluster.status = ClusterStatus.ACTIVE
    cluster.agent_installed = "Y"
    
    db.commit()
    
    return AgentResponse(
        success=True,
        message="Heartbeat received",
        agent_id=request.agent_id
    )


# ─── Action Polling (HTTP fallback for agents without persistent WebSocket) ───

class ActionResultRequest(BaseModel):
    action_id: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    nodes_cordoned: Optional[int] = None
    pods_evicted: Optional[int] = None


@router.get("/actions/pending")
async def get_pending_actions(
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key),
):
    """
    HTTP poll endpoint for agents to fetch pending K8s commands.

    The agent calls this every 15s as a fallback when WebSocket is not available.
    Returns at most 10 PENDING actions, marks them as PICKED_UP.

    Protocol:
      GET /api/v1/agents/actions/pending
      Authorization: Bearer <cluster_api_key>
    """
    from backend.models.agent_action import AgentAction, AgentActionStatus

    # Auto-recover stale PICKED_UP actions: if an agent picked up an action
    # but crashed/restarted before completing it, reset it to PENDING so the
    # new agent instance can pick it up.  Threshold: 2 minutes (actions should
    # complete or heartbeat within that window).
    _stale_cutoff = datetime.utcnow() - timedelta(minutes=2)
    _stale_actions = (
        db.query(AgentAction)
        .filter(
            AgentAction.cluster_id == cluster.id,
            AgentAction.status == AgentActionStatus.PICKED_UP,
            AgentAction.picked_up_at < _stale_cutoff,
        )
        .all()
    )
    for _sa in _stale_actions:
        logger.warning(
            f"Resetting stale PICKED_UP action {_sa.id} ({_sa.action_type.value}) "
            f"to PENDING — picked up at {_sa.picked_up_at}, agent likely crashed"
        )
        _sa.status = AgentActionStatus.PENDING
        _sa.picked_up_at = None
    if _stale_actions:
        db.commit()

    pending = (
        db.query(AgentAction)
        .filter(
            AgentAction.cluster_id == cluster.id,
            AgentAction.status == AgentActionStatus.PENDING,
        )
        # Issue #7: FIFO with priority pre-emption — high-priority emergency actions first
        .order_by(AgentAction.priority.desc(), AgentAction.created_at.asc())
        .limit(10)
        .all()
    )

    # Bug #11 fix: Enforce sequential step ordering for Phase 2 zero-downtime actions.
    # Only release step N when step N-1 is COMPLETED for the same rebalancing_action_id.
    # Actions without zero_downtime_step (e.g. standalone LABEL, EVICT) pass through.
    ready_actions = []
    for action in pending:
        payload = action.payload or {}
        zd_step = payload.get("zero_downtime_step")
        ra_id = payload.get("rebalancing_action_id")
        if zd_step and ra_id and zd_step > 1:
            # Check if the previous step is COMPLETED.
            # ra_id may be stored as int or string in JSONB depending on the code path,
            # so we check both forms for robust matching.
            from sqlalchemy import or_
            _prev_step_int = zd_step - 1
            prev_step_done = (
                db.query(AgentAction)
                .filter(
                    AgentAction.cluster_id == cluster.id,
                    or_(
                        AgentAction.payload.contains({"rebalancing_action_id": ra_id, "zero_downtime_step": _prev_step_int}),
                        AgentAction.payload.contains({"rebalancing_action_id": str(ra_id), "zero_downtime_step": _prev_step_int}),
                        AgentAction.payload.contains({"rebalancing_action_id": int(ra_id) if str(ra_id).isdigit() else ra_id, "zero_downtime_step": _prev_step_int}),
                    ),
                    AgentAction.status == AgentActionStatus.COMPLETED,
                )
                .count() > 0
            )
            if not prev_step_done:
                continue  # Hold back — predecessor not done yet
        ready_actions.append(action)

    commands = []
    for action in ready_actions:
        commands.append({
            "action_id": action.id,
            "action_type": action.action_type.value,
            "payload": action.payload or {},
            "created_at": action.created_at.isoformat(),
            "expires_at": action.expires_at.isoformat(),
        })
        action.status = AgentActionStatus.PICKED_UP
        action.picked_up_at = datetime.utcnow()

    if ready_actions:
        db.commit()

    return {"commands": commands, "count": len(commands)}


@router.post("/actions/{action_id}/result")
async def submit_action_result(
    action_id: str,
    request: ActionResultRequest,
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key),
):
    """
    Agent reports the result of a command it executed.

    Called after the agent finishes CORDON_NODE / DRAIN_NODE / TERMINATE_NODE.
    Updates the AgentAction record and logs the outcome.

    Protocol:
      POST /api/v1/agents/actions/{action_id}/result
      Authorization: Bearer <cluster_api_key>
      Body: { "success": true, "result": {...}, "nodes_cordoned": 1, "pods_evicted": 4 }
    """
    from backend.models.agent_action import AgentAction, AgentActionStatus
    from backend.core.logger import logger

    action = (
        db.query(AgentAction)
        .filter(AgentAction.id == action_id, AgentAction.cluster_id == cluster.id)
        .first()
    )
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    action.status = AgentActionStatus.COMPLETED if request.success else AgentActionStatus.FAILED
    action.completed_at = datetime.utcnow()
    action.result = request.result or {}
    action.error_message = request.error if not request.success else None

    if request.nodes_cordoned is not None:
        action.result = {**(action.result or {}), "nodes_cordoned": request.nodes_cordoned}
    if request.pods_evicted is not None:
        action.result = {**(action.result or {}), "pods_evicted": request.pods_evicted}

    db.commit()

    status_word = "COMPLETED" if request.success else "FAILED"
    logger.info(
        f"[agent] Action {action_id} {status_word} for cluster {cluster.id} "
        f"(type={action.action_type.value})"
    )


# ── T18: Spot Interruption + Rebalance Recommendation Endpoints ─────────────

import logging as _logging
_t18_logger = _logging.getLogger(__name__)


class SpotInterruptionRequest(BaseModel):
    instance_id: str
    node_name: str
    cluster_id: str
    region: str
    az: str
    instance_type: str


@router.post("/spot-interruption")
async def handle_spot_interruption(request: SpotInterruptionRequest):
    """
    Receive a spot interruption notice from agent/IMDS polling.
    Delegates to EmergencyEventProcessor for deduplication and handling.
    """
    try:
        from backend.services.emergency_event_processor import EmergencyEventProcessor
        processor = EmergencyEventProcessor()
        result = processor.process(
            event_type='termination',
            instance_id=request.instance_id,
            node_name=request.node_name,
            cluster_id=request.cluster_id,
            region=request.region,
            az=request.az,
            instance_type=request.instance_type,
        )
        return result
    except Exception as e:
        _t18_logger.error(f"[agent] spot-interruption processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rebalance-recommendation")
async def handle_rebalance_recommendation(request: SpotInterruptionRequest):
    """
    Receive a rebalance recommendation event from agent/IMDS polling.
    Delegates to EmergencyEventProcessor for rebalance tracking.
    """
    try:
        from backend.services.emergency_event_processor import EmergencyEventProcessor
        processor = EmergencyEventProcessor()
        result = processor.process(
            event_type='rebalance',
            instance_id=request.instance_id,
            node_name=request.node_name,
            cluster_id=request.cluster_id,
            region=request.region,
            az=request.az,
            instance_type=request.instance_type,
        )
        return result
    except Exception as e:
        _t18_logger.error(f"[agent] rebalance-recommendation processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Orchestrator command endpoints ────────────────────────────────────────────

class OrchestratorCommandResult(BaseModel):
    """Result reported back by the in-cluster orchestrator after executing a command."""
    action_id: str
    cluster_id: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    executed_at: Optional[str] = None


@router.get("/orchestrator/{cluster_id}/pending-commands")
async def get_pending_commands(
    cluster_id: str,
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key),  # Issue #2: authentication
):
    """
    Return a list of PENDING AgentActions for the given cluster.
    Called by the orchestrator (not the DaemonSet agent) to poll for work.
    """
    # Verify the API key belongs to the requested cluster
    if cluster.id != cluster_id:
        raise HTTPException(status_code=403, detail="API key does not match cluster_id")
    from backend.models.agent_action import AgentAction, AgentActionStatus
    from datetime import datetime as _dt

    pending = (
        db.query(AgentAction)
        .filter(
            AgentAction.cluster_id == cluster_id,
            AgentAction.status == AgentActionStatus.PENDING,
        )
        # Issue #7: FIFO with priority — emergency actions (higher priority) come first
        .order_by(AgentAction.priority.desc(), AgentAction.created_at.asc())
        .limit(20)
        .all()
    )

    commands = []
    for action in pending:
        commands.append({
            "action_id": action.id,
            "action_type": action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type),
            "payload": action.payload or {},
            "created_at": action.created_at.isoformat() if action.created_at else None,
        })
        # Mark as PICKED_UP so we don't re-deliver
        action.status = AgentActionStatus.PICKED_UP
        action.picked_up_at = _dt.utcnow()

    if pending:
        db.commit()

    return {"cluster_id": cluster_id, "commands": commands, "count": len(commands)}


@router.post("/orchestrator/{cluster_id}/command-result")
async def report_command_result(
    cluster_id: str,
    result: OrchestratorCommandResult,
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key),  # Issue #2: authentication
):
    """
    Receive the execution result of a previously issued orchestrator command.
    Updates the AgentAction status to COMPLETED or FAILED.
    """
    # Verify the API key belongs to the requested cluster
    if cluster.id != cluster_id:
        raise HTTPException(status_code=403, detail="API key does not match cluster_id")
    from backend.models.agent_action import AgentAction, AgentActionStatus
    from datetime import datetime as _dt

    if result.cluster_id != cluster_id:
        raise HTTPException(status_code=400, detail="cluster_id mismatch in path vs body")

    action = db.query(AgentAction).filter(AgentAction.id == result.action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail=f"AgentAction {result.action_id} not found")

    action.status = AgentActionStatus.COMPLETED if result.success else AgentActionStatus.FAILED
    action.completed_at = _dt.fromisoformat(result.executed_at) if result.executed_at else _dt.utcnow()
    action.result = result.result
    action.error_message = result.error if not result.success else None
    db.commit()

    return {
        "action_id": result.action_id,
        "cluster_id": cluster_id,
        "status": action.status.value,
        "recorded_at": _dt.utcnow().isoformat(),
    }
