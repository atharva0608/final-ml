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

from sqlalchemy.exc import OperationalError

from backend.core.config import settings
from backend.models.base import get_db
from backend.models.cluster import Cluster, ClusterStatus
from backend.utils.retry import with_retry

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
    karpenter_status: Optional[dict] = None
    components: Optional[dict] = None
    
    # Phase 2e metrics
    pod_metrics_per_workload: Optional[dict] = None
    cluster_spot_summary: Optional[dict] = None
    hpa_pdb_data: Optional[dict] = None
    agent_version: Optional[str] = None


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

    # P-24: agent version compat check
    if request.agent_version:
        try:
            from packaging.version import Version
            _min_v = Version(settings.AGENT_MIN_VERSION)
            if Version(request.agent_version) < _min_v:
                logger.warning(
                    "agent_version_deprecated agent_id=%s version=%s min=%s",
                    request.agent_id, request.agent_version, settings.AGENT_MIN_VERSION,
                )
        except Exception:
            pass

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

    # Cache Phase 2e metrics in Redis (Task 5.3)
    try:
        from backend.core.redis_client import get_redis_client
        import json
        from backend.redis_keys import (
            agent_data_pod_metrics_key,
            agent_data_cluster_spot_summary_key,
            agent_data_hpa_pdb_key
        )
        
        _r = get_redis_client()
        if _r:
            # 1. Store heartbeat raw (Task 1.14 legacy)
            _extended_payload = request.dict()
            if request.health:
                _extended_payload.update(request.health)
            _r.setex(f"spot:agent:heartbeat:{cluster.id}", 300, json.dumps(_extended_payload))

            if request.pod_metrics_per_workload is not None:
                _r.setex(agent_data_pod_metrics_key(cluster.id), 120, json.dumps(request.pod_metrics_per_workload))
            if request.cluster_spot_summary is not None:
                _r.setex(agent_data_cluster_spot_summary_key(cluster.id), 120, json.dumps(request.cluster_spot_summary))
                # P1-B: write pending pods count so PlacementController scaling guard reads real data
                _pending = int((request.cluster_spot_summary or {}).get("unhealthy_pending_pods", 0))
                _r.setex(f"spot:cluster:pending_pods:{cluster.id}", 120, str(_pending))
            if request.hpa_pdb_data is not None:
                _r.setex(agent_data_hpa_pdb_key(cluster.id), 300, json.dumps(request.hpa_pdb_data))
                # P0-A: translate cluster-level hpa_pdb into per-workload state keys consumed by
                # PlacementAdvisorService, PlacementRolloutService, and PlacementControllerTask.
                import time as _t
                _now = _t.time()
                _pmw = request.pod_metrics_per_workload or {}
                for _wid, _wls in (request.hpa_pdb_data or {}).items():
                    if not isinstance(_wls, dict):
                        continue
                    # ready_replicas = total running pods (spot + od) from the same heartbeat
                    _wpm = _pmw.get(_wid, {})
                    _ready = int(_wpm.get("spot_pods", 0)) + int(_wpm.get("od_pods", 0))
                    try:
                        _state_payload = {
                            "pdb_min_available":       _wls.get("pdb_min_available"),
                            "hpa_min_replicas":        _wls.get("hpa_min"),
                            "hpa_max_replicas":        _wls.get("hpa_max"),
                            "ready_replicas":          _ready,
                            "updated_at":              _now,
                            "current_spot_pods":       int(_wpm.get("spot_pods", 0)),
                            "current_ondemand_pods":   int(_wpm.get("od_pods", 0)),
                            "has_pdb":                 bool(_wls.get("has_pdb", False)),
                            "has_topology_spread":     bool(_wls.get("has_topology_spread", False)),
                            "has_pod_anti_affinity":   bool(_wls.get("has_pod_anti_affinity", False)),
                            "pod_cpu_cv":              None,
                            "pod_request_rate_cv":     None,
                        }
                    except Exception as _ext_exc:
                        logger.warning(f"[AGENT] T-05 extended state fields failed for {_wid}: {_ext_exc}")
                        _state_payload = {
                            "pdb_min_available": _wls.get("pdb_min_available"),
                            "hpa_min_replicas":  _wls.get("hpa_min"),
                            "hpa_max_replicas":  _wls.get("hpa_max"),
                            "ready_replicas":    _ready,
                            "updated_at":        _now,
                        }
                    _r.setex(
                        f"spot:workload:state:{cluster.id}:{_wid}",
                        300,
                        json.dumps(_state_payload),
                    )
    except Exception as e:
        logger.error(f"Failed to cache Phase 2e heartbeat metrics for {cluster.id}: {e}")
    
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

    # Post-eviction placement validation: verify the pod landed on the correct
    # capacity type (Spot vs On-Demand).  Only runs when eviction itself succeeded;
    # if the agent reported failure, the pod may still be running — no point
    # checking placement.  handle_eviction_result() may override the COMPLETED
    # status to FAILED if the pod ended up on On-Demand.
    if request.success and action.action_type.value == "EVICT_POD":
        try:
            from backend.pipeline.stage3_ppe.controller_service import handle_eviction_result
            from backend.core.redis_client import get_redis_client
            handle_eviction_result(action, db, get_redis_client())
        except Exception as _handler_exc:
            logger.warning(
                f"[agent] Post-eviction placement validation failed for action={action_id}: {_handler_exc}"
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


# ---------------------------------------------------------------------------
# POST /agents/node-metadata/batch — T-09
# ---------------------------------------------------------------------------

class NodeMetadataItem(BaseModel):
    node_name: str
    az: Optional[str] = None
    capacity_type: Optional[str] = None
    nodepool_name: Optional[str] = None
    instance_type: Optional[str] = None
    do_not_disrupt: bool = False
    is_ready: bool = True
    allocatable_cpu_millicores: Optional[float] = None
    allocatable_memory_bytes: Optional[float] = None
    labels: Optional[dict] = None


class NodeMetadataBatchRequest(BaseModel):
    cluster_id: str
    nodes: List[NodeMetadataItem]


@router.post("/node-metadata/batch", summary="Upsert static node metadata from agent")
async def upsert_node_metadata_batch(
    request: NodeMetadataBatchRequest,
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key),
):
    """
    Upserts static per-node properties (AZ, capacity type, nodepool, etc.)
    from the agent's node_metric collection.
    ON CONFLICT (cluster_id, node_name) → UPDATE all fields.
    """
    if cluster.id != request.cluster_id:
        raise HTTPException(status_code=403, detail="API key does not match cluster_id")

    if not settings.FEATURE_NODE_METADATA_PUSH:
        return {"status": "disabled", "message": "Feature flag FEATURE_NODE_METADATA_PUSH=False"}

    from backend.models.node_metadata import NodeMetadata
    from datetime import datetime as _dt
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    if not request.nodes:
        return {"upserted": 0, "cluster_id": request.cluster_id}

    _skipped_nm = sum(1 for n in request.nodes if not n.node_name)
    if _skipped_nm:
        logger.warning("node_metadata_batch_skipped_missing_node_name count=%d", _skipped_nm)
    rows = [
        {
            "id": str(__import__('uuid').uuid4()),
            "cluster_id": request.cluster_id,
            "node_name": n.node_name,
            "az": n.az,
            "capacity_type": n.capacity_type,
            "nodepool_name": n.nodepool_name,
            "instance_type": n.instance_type,
            "do_not_disrupt": n.do_not_disrupt,
            "is_ready": n.is_ready,
            "allocatable_cpu_millicores": n.allocatable_cpu_millicores,
            "allocatable_memory_bytes": n.allocatable_memory_bytes,
            "updated_at": _dt.utcnow(),
        }
        for n in request.nodes
        if n.node_name
    ]

    @with_retry(exceptions=(OperationalError,), max_attempts=3, backoff_seconds=0.5)
    def _bulk_upsert_node_metadata():
        _stmt = pg_insert(NodeMetadata).values(rows)
        _stmt = _stmt.on_conflict_do_update(
            index_elements=["cluster_id", "node_name"],
            set_={
                "az": _stmt.excluded.az,
                "capacity_type": _stmt.excluded.capacity_type,
                "nodepool_name": _stmt.excluded.nodepool_name,
                "instance_type": _stmt.excluded.instance_type,
                "do_not_disrupt": _stmt.excluded.do_not_disrupt,
                "is_ready": _stmt.excluded.is_ready,
                "allocatable_cpu_millicores": _stmt.excluded.allocatable_cpu_millicores,
                "allocatable_memory_bytes": _stmt.excluded.allocatable_memory_bytes,
                "updated_at": _stmt.excluded.updated_at,
            },
        )
        db.execute(_stmt)
        db.commit()

    try:
        _bulk_upsert_node_metadata()
    except OperationalError as exc:
        logger.error("node_metadata_batch_upsert_failed after retries: %s", exc)
        try:
            from backend.services.observability_logger import ObservabilityLogger
            from backend.core.redis_client import get_redis_client as _rl_rc
            _obs_r = _rl_rc()
            ObservabilityLogger(redis_client=_obs_r).log_decision(
                cluster_id=request.cluster_id,
                decision_type="AGENT_BATCH_FAILURE",
                approved=False,
                reason=str(exc),
                metadata={"endpoint": "node-metadata/batch"},
            )
            _obs_r.incr(f"spot:errors:celery_task_failure:{request.cluster_id}")
            _obs_r.expire(f"spot:errors:celery_task_failure:{request.cluster_id}", 86400)
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="Database temporarily unavailable. Retry heartbeat.")

    # node_owner_type population: derive from node labels or structured fields
    # and bulk-UPDATE matching Instance rows.  Fail-safe — any error is logged and ignored.
    try:
        from backend.workers.tasks.auto_rebalancer import _derive_node_owner_type as _derive_owt
        from backend.models.instance import Instance as _Inst

        def _owt_from_item(n: NodeMetadataItem) -> str:
            if n.labels:
                return _derive_owt(n.labels)
            # Fallback when agent doesn't send labels: derive from structured fields
            if n.nodepool_name:
                return "karpenter_dynamic"
            return "unknown"

        _owt_map = {
            n.node_name: _owt_from_item(n)
            for n in request.nodes
            if n.node_name
        }
        _node_names = list(_owt_map.keys())
        _batch_size = 100
        for _i in range(0, len(_node_names), _batch_size):
            _batch = _node_names[_i:_i + _batch_size]
            _insts = db.query(_Inst).filter(
                _Inst.cluster_id == request.cluster_id,
                _Inst.node_name.in_(_batch),
            ).all()
            for _inst in _insts:
                _new_owt = _owt_map.get(_inst.node_name, "unknown")
                if _inst.node_owner_type != _new_owt:
                    _inst.node_owner_type = _new_owt
        db.commit()
        logger.debug(
            "node_owner_type_populated cluster=%s nodes=%d",
            request.cluster_id, len(_node_names),
        )
    except Exception as _owt_exc:
        logger.warning(
            "node_owner_type_population_failed cluster=%s: %s",
            request.cluster_id, _owt_exc,
        )

    return {"upserted": len(rows), "cluster_id": request.cluster_id}


# ---------------------------------------------------------------------------
# POST /agents/hpa-configs/batch — T-13
# ---------------------------------------------------------------------------

class HpaConfigItem(BaseModel):
    namespace: str
    workload_name: str
    hpa_name: Optional[str] = None
    min_replicas: Optional[int] = None
    max_replicas: Optional[int] = None
    target_cpu_pct: Optional[int] = None
    current_replicas: Optional[int] = None
    desired_replicas: Optional[int] = None
    scale_up_stabilization_seconds: Optional[int] = None
    scale_down_stabilization_seconds: Optional[int] = None
    cpu_utilization_pct: Optional[int] = None


class HpaConfigBatchRequest(BaseModel):
    cluster_id: str
    hpas: List[HpaConfigItem]


@router.post("/hpa-configs/batch", summary="Upsert HPA configs and append status snapshots")
async def upsert_hpa_configs_batch(
    request: HpaConfigBatchRequest,
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key),
):
    """
    Upserts HPA configuration rows and appends status snapshots.
    ON CONFLICT (cluster_id, namespace, workload_name) → UPDATE config fields.
    Always appends a new hpa_status_snapshots row for each HPA.
    Skips gracefully if no HPAs (KEDA-only cluster).
    """
    if cluster.id != request.cluster_id:
        raise HTTPException(status_code=403, detail="API key does not match cluster_id")

    if not settings.FEATURE_HPA_CONFIG_PUSH:
        return {"status": "disabled", "message": "Feature flag FEATURE_HPA_CONFIG_PUSH=False"}

    from backend.models.hpa_configs import HpaConfig
    from backend.models.hpa_status_snapshots import HpaStatusSnapshot
    from datetime import datetime as _dt
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    if not request.hpas:
        return {"upserted_configs": 0, "inserted_snapshots": 0, "cluster_id": request.cluster_id}

    config_rows = []
    snapshot_rows = []
    now = _dt.utcnow()

    _skipped_hpa = sum(1 for h in request.hpas if not h.namespace or not h.workload_name)
    if _skipped_hpa:
        logger.warning("hpa_configs_batch_skipped_missing_key count=%d", _skipped_hpa)
    for h in request.hpas:
        if not h.namespace or not h.workload_name:
            continue
        config_rows.append({
            "id": str(__import__('uuid').uuid4()),
            "cluster_id": request.cluster_id,
            "namespace": h.namespace,
            "workload_name": h.workload_name,
            "hpa_name": h.hpa_name,
            "min_replicas": h.min_replicas,
            "max_replicas": h.max_replicas,
            "target_cpu_pct": h.target_cpu_pct,
            "current_replicas": h.current_replicas,
            "desired_replicas": h.desired_replicas,
            "scale_up_stabilization_seconds": h.scale_up_stabilization_seconds,
            "scale_down_stabilization_seconds": h.scale_down_stabilization_seconds,
            "updated_at": now,
        })
        snapshot_rows.append({
            "id": str(__import__('uuid').uuid4()),
            "cluster_id": request.cluster_id,
            "namespace": h.namespace,
            "workload_name": h.workload_name,
            "desired_replicas": h.desired_replicas,
            "current_replicas": h.current_replicas,
            "cpu_utilization_pct": h.cpu_utilization_pct,
            "snapshot_at": now,
        })

    @with_retry(exceptions=(OperationalError,), max_attempts=3, backoff_seconds=0.5)
    def _bulk_upsert_hpa_configs():
        _stmt = pg_insert(HpaConfig).values(config_rows)
        _stmt = _stmt.on_conflict_do_update(
            index_elements=["cluster_id", "namespace", "workload_name"],
            set_={
                "hpa_name": _stmt.excluded.hpa_name,
                "min_replicas": _stmt.excluded.min_replicas,
                "max_replicas": _stmt.excluded.max_replicas,
                "target_cpu_pct": _stmt.excluded.target_cpu_pct,
                "current_replicas": _stmt.excluded.current_replicas,
                "desired_replicas": _stmt.excluded.desired_replicas,
                "scale_up_stabilization_seconds": _stmt.excluded.scale_up_stabilization_seconds,
                "scale_down_stabilization_seconds": _stmt.excluded.scale_down_stabilization_seconds,
                "updated_at": _stmt.excluded.updated_at,
            },
        )
        db.execute(_stmt)
        if snapshot_rows:
            _snap_stmt = pg_insert(HpaStatusSnapshot).values(snapshot_rows)
            _snap_stmt = _snap_stmt.on_conflict_do_nothing(
                index_elements=["cluster_id", "workload_name", "snapshot_at"],
            )
            db.execute(_snap_stmt)
        db.commit()

    try:
        _bulk_upsert_hpa_configs()
    except OperationalError as exc:
        logger.error("hpa_configs_batch_upsert_failed after retries: %s", exc)
        try:
            from backend.services.observability_logger import ObservabilityLogger
            from backend.core.redis_client import get_redis_client as _rl_rc
            _obs_r = _rl_rc()
            ObservabilityLogger(redis_client=_obs_r).log_decision(
                cluster_id=request.cluster_id,
                decision_type="AGENT_BATCH_FAILURE",
                approved=False,
                reason=str(exc),
                metadata={"endpoint": "hpa-configs/batch"},
            )
            _obs_r.incr(f"spot:errors:celery_task_failure:{request.cluster_id}")
            _obs_r.expire(f"spot:errors:celery_task_failure:{request.cluster_id}", 86400)
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="Database temporarily unavailable. Retry heartbeat.")

    # Write HPA scaling-event key so PlacementController scaling guard
    # sees an active HPA scale-up and inhibits evictions for 3 minutes.
    try:
        _hpa_scaling_up = any(
            h.desired_replicas is not None
            and h.current_replicas is not None
            and h.desired_replicas > h.current_replicas
            for h in request.hpas
        )
        if _hpa_scaling_up:
            from backend.core.redis_client import get_redis_client as _hpa_rc
            import time as _hpa_t
            _hpa_r = _hpa_rc()
            if _hpa_r:
                _hpa_r.set(
                    f"spot:pc:hpa_scaling_event:{request.cluster_id}",
                    str(_hpa_t.time()),
                    ex=300,  # 5-min TTL; PC checks within 3-min window
                )
    except Exception as _hpa_err:
        logger.warning("hpa_scaling_event_write_failed cluster=%s: %s", request.cluster_id, _hpa_err)

    return {
        "upserted_configs": len(config_rows),
        "inserted_snapshots": len(snapshot_rows),
        "cluster_id": request.cluster_id,
    }


# ---------------------------------------------------------------------------
# POST /agents/nodeclaims/batch — T-11
# ---------------------------------------------------------------------------

class NodeClaimItem(BaseModel):
    node_name: str
    instance_type: Optional[str] = None
    capacity_type: Optional[str] = None
    az: Optional[str] = None
    nodepool_name: Optional[str] = None
    state: Optional[str] = None
    provisioned_at: Optional[str] = None


class NodeClaimsBatchRequest(BaseModel):
    cluster_id: str
    claims: List[NodeClaimItem]


@router.post("/nodeclaims/batch", summary="Upsert Karpenter NodeClaims from watcher")
async def upsert_nodeclaims_batch(
    request: NodeClaimsBatchRequest,
    db: Session = Depends(get_db),
    cluster: Cluster = Depends(validate_api_key),
):
    """
    Upserts NodeClaim CRD data from karpenter_watcher._poll_nodeclaims().
    ON CONFLICT (cluster_id, node_name) → UPDATE all fields.
    """
    if cluster.id != request.cluster_id:
        raise HTTPException(status_code=403, detail="API key does not match cluster_id")

    from backend.models.karpenter_node_claims import KarpenterNodeClaim
    from datetime import datetime as _dt
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    if not request.claims:
        return {"upserted": 0, "cluster_id": request.cluster_id}

    _skipped_nc = sum(1 for c in request.claims if not c.node_name)
    if _skipped_nc:
        logger.warning("nodeclaims_batch_skipped_missing_node_name count=%d", _skipped_nc)
    rows = []
    for c in request.claims:
        if not c.node_name:
            continue
        provisioned_at = None
        if c.provisioned_at:
            try:
                provisioned_at = _dt.fromisoformat(c.provisioned_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        rows.append({
            "id": str(__import__('uuid').uuid4()),
            "cluster_id": request.cluster_id,
            "node_name": c.node_name,
            "instance_type": c.instance_type,
            "capacity_type": c.capacity_type,
            "az": c.az,
            "nodepool_name": c.nodepool_name,
            "state": c.state,
            "provisioned_at": provisioned_at,
            "updated_at": _dt.utcnow(),
        })

    @with_retry(exceptions=(OperationalError,), max_attempts=3, backoff_seconds=0.5)
    def _bulk_upsert_nodeclaims():
        _stmt = pg_insert(KarpenterNodeClaim).values(rows)
        _stmt = _stmt.on_conflict_do_update(
            index_elements=["cluster_id", "node_name"],
            set_={
                "instance_type": _stmt.excluded.instance_type,
                "capacity_type": _stmt.excluded.capacity_type,
                "az": _stmt.excluded.az,
                "nodepool_name": _stmt.excluded.nodepool_name,
                "state": _stmt.excluded.state,
                "provisioned_at": _stmt.excluded.provisioned_at,
                "updated_at": _stmt.excluded.updated_at,
            },
        )
        db.execute(_stmt)
        db.commit()

    try:
        _bulk_upsert_nodeclaims()
    except OperationalError as exc:
        logger.error("nodeclaims_batch_upsert_failed after retries: %s", exc)
        try:
            from backend.services.observability_logger import ObservabilityLogger
            from backend.core.redis_client import get_redis_client as _rl_rc
            _obs_r = _rl_rc()
            ObservabilityLogger(redis_client=_obs_r).log_decision(
                cluster_id=request.cluster_id,
                decision_type="AGENT_BATCH_FAILURE",
                approved=False,
                reason=str(exc),
                metadata={"endpoint": "nodeclaims/batch"},
            )
            _obs_r.incr(f"spot:errors:celery_task_failure:{request.cluster_id}")
            _obs_r.expire(f"spot:errors:celery_task_failure:{request.cluster_id}", 86400)
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="Database temporarily unavailable. Retry heartbeat.")

    return {"upserted": len(rows), "cluster_id": request.cluster_id}


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
