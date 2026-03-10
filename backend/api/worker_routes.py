"""
Worker API Routes
=================
Endpoints for DaemonSet agent workers to report data back to the backend:
- Spot interruption alerts
- Node registration and heartbeat
- Node-level metrics
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from backend.core.logger import logger
from backend.models.base import get_db

router = APIRouter(prefix="/worker", tags=["worker"])


# ── Request Models ────────────────────────────────────────────────────────────

class SpotInterruptionRequest(BaseModel):
    cluster_id: str
    node_name: str
    instance_id: str
    action: str = "terminate"
    termination_time: Optional[str] = None


class RegisterNodeRequest(BaseModel):
    cluster_id: str
    node_name: str
    instance_id: Optional[str] = None
    instance_type: Optional[str] = None
    az: Optional[str] = None
    lifecycle: Optional[str] = None  # "on-demand" or "spot"


class HeartbeatRequest(BaseModel):
    cluster_id: str
    node_name: str


class NodeMetricsRequest(BaseModel):
    cluster_id: str
    node_name: str
    cpu_usage_millicores: Optional[float] = None
    cpu_capacity_millicores: Optional[float] = None
    memory_usage_bytes: Optional[float] = None
    memory_capacity_bytes: Optional[float] = None
    disk_usage_bytes: Optional[float] = None
    disk_capacity_bytes: Optional[float] = None
    instance_id: Optional[str] = None
    instance_type: Optional[str] = None
    az: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/spot-interruption")
async def report_spot_interruption(req: SpotInterruptionRequest):
    """
    Receive a spot termination alert from an agent worker.
    Creates an emergency RebalancingAction bypassing the normal double-gate.
    """
    try:
        logger.critical(
            f"🚨 SPOT INTERRUPTION from agent: cluster={req.cluster_id}, "
            f"node={req.node_name}, instance={req.instance_id}, "
            f"termination_time={req.termination_time}"
        )

        from backend.models.base import get_db
        from backend.models.rebalancing_action import RebalancingAction

        db = next(get_db())
        try:
            # Create emergency rebalancing action
            action = RebalancingAction(
                cluster_id=req.cluster_id,
                trigger="emergency",
                source_pool=req.instance_id,
                target_pool="auto",
                status="in_progress",
                started_at=datetime.utcnow(),
                action_metadata={
                    "reason": "spot_interruption_notice",
                    "instance_id": req.instance_id,
                    "node_name": req.node_name,
                    "termination_time": req.termination_time,
                    "initiated_by": "agent_worker",
                },
            )
            db.add(action)
            db.commit()

            logger.info(f"[worker] Created emergency rebalancing action {action.id}")
            return {
                "status": "acknowledged",
                "action_id": action.id,
                "message": "Emergency rebalancing action created",
            }
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    except Exception as e:
        logger.error(f"[worker] Failed to process spot interruption: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register-node")
async def register_node(req: RegisterNodeRequest):
    """
    Register a DaemonSet worker node with the backend.
    Called on agent startup to report instance metadata.
    """
    try:
        from backend.models.base import get_db
        from backend.models.worker_registration import WorkerRegistration

        db = next(get_db())
        try:
            # Upsert: update if exists, create if not
            existing = (
                db.query(WorkerRegistration)
                .filter(
                    WorkerRegistration.cluster_id == req.cluster_id,
                    WorkerRegistration.node_name == req.node_name,
                )
                .first()
            )

            if existing:
                existing.instance_id = req.instance_id or existing.instance_id
                existing.instance_type = req.instance_type or existing.instance_type
                existing.az = req.az or existing.az
                existing.lifecycle = req.lifecycle or existing.lifecycle
                existing.status = "active"
                existing.last_heartbeat = datetime.utcnow()
            else:
                reg = WorkerRegistration(
                    cluster_id=req.cluster_id,
                    node_name=req.node_name,
                    instance_id=req.instance_id,
                    instance_type=req.instance_type,
                    az=req.az,
                    lifecycle=req.lifecycle,
                    status="active",
                )
                db.add(reg)

            db.commit()
            logger.info(f"[worker] Node registered: {req.node_name} (cluster={req.cluster_id})")
            return {"status": "registered", "node_name": req.node_name}

        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[worker] Failed to register node: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heartbeat")
async def worker_heartbeat(req: HeartbeatRequest):
    """
    Update worker heartbeat timestamp. Called periodically by the agent.
    """
    try:
        from backend.models.base import get_db
        from backend.models.worker_registration import WorkerRegistration

        db = next(get_db())
        try:
            reg = (
                db.query(WorkerRegistration)
                .filter(
                    WorkerRegistration.cluster_id == req.cluster_id,
                    WorkerRegistration.node_name == req.node_name,
                )
                .first()
            )

            if reg:
                reg.last_heartbeat = datetime.utcnow()
                reg.status = "active"
                db.commit()
                return {"status": "ok"}
            else:
                return {"status": "not_registered", "message": "Call /register-node first"}

        finally:
            db.close()

    except Exception as e:
        logger.error(f"[worker] Heartbeat failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/node-metrics")
async def receive_node_metrics(req: NodeMetricsRequest):
    """
    Receive node-level metrics from a DaemonSet worker.
    - Stored in NodeMetric table for rightsizing trend analysis.
    - Also UPDATES instances.cpu_util / memory_util so the cluster UI shows live data.
    """
    try:
        from backend.models.base import get_db
        from backend.models.node_metrics import NodeMetric
        from backend.models.instance import Instance

        db = next(get_db())
        try:
            metric = NodeMetric(
                cluster_id=req.cluster_id,
                node_name=req.node_name,
                cpu_usage_millicores=req.cpu_usage_millicores,
                cpu_capacity_millicores=req.cpu_capacity_millicores,
                memory_usage_bytes=req.memory_usage_bytes,
                memory_capacity_bytes=req.memory_capacity_bytes,
                disk_usage_bytes=req.disk_usage_bytes,
                disk_capacity_bytes=req.disk_capacity_bytes,
                instance_id=req.instance_id,
                instance_type=req.instance_type,
                az=req.az,
            )
            db.add(metric)

            # Compute utilization percentages and push live to the instances table
            # so get_cluster_nodes_detailed always reads fresh data.
            cpu_pct = None
            mem_pct = None
            if req.cpu_usage_millicores and req.cpu_capacity_millicores and req.cpu_capacity_millicores > 0:
                cpu_pct = round((req.cpu_usage_millicores / req.cpu_capacity_millicores) * 100, 2)
            if req.memory_usage_bytes and req.memory_capacity_bytes and req.memory_capacity_bytes > 0:
                mem_pct = round((req.memory_usage_bytes / req.memory_capacity_bytes) * 100, 2)

            if cpu_pct is not None or mem_pct is not None:
                # Match by instance_id first, fall back to node_name
                inst = None
                if req.instance_id:
                    inst = db.query(Instance).filter(
                        Instance.cluster_id == req.cluster_id,
                        Instance.instance_id == req.instance_id,
                    ).first()
                if inst is None and req.node_name:
                    inst = db.query(Instance).filter(
                        Instance.cluster_id == req.cluster_id,
                        Instance.node_name == req.node_name,
                    ).first()
                if inst:
                    if cpu_pct is not None:
                        inst.cpu_util = cpu_pct
                    if mem_pct is not None:
                        inst.memory_util = mem_pct
                    inst.updated_at = datetime.utcnow()

            db.commit()
            return {"status": "stored", "cpu_pct": cpu_pct, "mem_pct": mem_pct}

        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    except Exception as e:
        logger.error(f"[worker] Failed to store node metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Node-Joined (T38) ─────────────────────────────────────────────────────────

class NodeJoinedRequest(BaseModel):
    """Sent by the worker when a new node has joined the cluster."""
    instance_id: str
    cluster_id: str
    node_name: Optional[str] = None
    instance_type: Optional[str] = None
    az: Optional[str] = None
    lifecycle: Optional[str] = None  # "spot" or "on-demand"


@router.post("/node-joined")
async def node_joined(req: NodeJoinedRequest, db: Session = Depends(get_db)):
    """
    Record that a new node has joined the cluster.

    - Sets Redis key node_joined:{instance_id} (used by recovery_monitor to skip orphan cleanup)
    - Updates the Instance DB record (lifecycle, az, node_name) if it exists
    """
    # 1. Set Redis flag so orphan scanner knows this instance joined successfully
    try:
        from backend.core.redis_client import get_redis_client
        _redis = get_redis_client()
        _redis.setex(f"node_joined:{req.instance_id}", 7200, "1")  # 2h TTL
        logger.info(f"[worker/node-joined] Set node_joined:{req.instance_id} in Redis")
    except Exception as exc:
        logger.warning(f"[worker/node-joined] Redis set failed: {exc}")

    # 2. Update Instance record if present
    try:
        from backend.models.instance import Instance
        inst = db.query(Instance).filter(Instance.instance_id == req.instance_id).first()
        if inst:
            if req.node_name:
                inst.node_name = req.node_name
            if req.instance_type:
                inst.instance_type = req.instance_type
            if req.az:
                inst.az = req.az
            if req.lifecycle:
                inst.lifecycle = req.lifecycle
            inst.joined_at = datetime.utcnow()
            db.commit()
            logger.info(f"[worker/node-joined] Updated Instance record for {req.instance_id}")
    except Exception as exc:
        logger.warning(f"[worker/node-joined] Instance DB update failed: {exc}")

    return {
        "status": "acknowledged",
        "instance_id": req.instance_id,
        "cluster_id": req.cluster_id,
        "recorded_at": datetime.utcnow().isoformat(),
    }
