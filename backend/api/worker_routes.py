"""
Worker API Routes
=================
Endpoints for DaemonSet agent workers to report data back to the backend:
- Spot interruption alerts
- Node registration and heartbeat
- Node-level metrics
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from backend.core.logger import logger

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
    Stored for rightsizing trend analysis.
    """
    try:
        from backend.models.base import get_db
        from backend.models.node_metrics import NodeMetric

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
            db.commit()
            return {"status": "stored"}

        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    except Exception as e:
        logger.error(f"[worker] Failed to store node metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
