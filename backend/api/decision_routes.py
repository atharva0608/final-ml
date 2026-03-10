"""
Decision Engine API Routes
===========================

Five endpoints for the Decision Engine:
  POST /api/v1/decision/rank-for-node
  POST /api/v1/decision/rank-for-template
  POST /api/v1/decision/report-termination
  POST /api/v1/decision/report-launch-failure
  GET  /api/v1/decision/blacklist
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from backend.models.base import get_db
from backend.core.redis_client import get_redis_client
from backend.core.logger import logger

router = APIRouter(prefix="/api/v1/decision", tags=["Decision Engine"])


# ── Request / Response Models ────────────────────────────────────────────────

class RankForNodeRequest(BaseModel):
    cluster_id: str
    node_name: str
    limit: int = Field(default=10, ge=1, le=50)
    diversify: bool = False


class RankForTemplateRequest(BaseModel):
    cluster_id: str
    template: Dict[str, Any]  # {min_vcpu, min_memory, families, allowed_azs}
    limit: int = Field(default=10, ge=1, le=50)
    diversify: bool = False


class ReportTerminationRequest(BaseModel):
    pool_key: str  # "instance_type:az"
    region: str = "ap-south-1"


class ReportLaunchFailureRequest(BaseModel):
    cluster_id: str
    pool_key: str
    reason: str = "launch_failure"
    region: str = "ap-south-1"


class PoolResponse(BaseModel):
    pools: List[Dict[str, Any]]


class StatusResponse(BaseModel):
    status: str
    failure_count: Optional[int] = None
    blacklisted: Optional[bool] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/rank-for-node", response_model=PoolResponse)
def rank_for_node(req: RankForNodeRequest, db: Session = Depends(get_db)):
    """Return top ranked pools for a specific node."""
    try:
        from backend.services.decision_engine_service import DecisionEngineService

        redis = get_redis_client()
        de = DecisionEngineService(db, redis)
        pools = de.rank_for_node(
            cluster_id=req.cluster_id,
            node_name=req.node_name,
            limit=req.limit,
            diversify=req.diversify,
        )
        return PoolResponse(pools=pools)
    except Exception as e:
        logger.error(f"[DE API] rank-for-node failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rank-for-template", response_model=PoolResponse)
def rank_for_template(req: RankForTemplateRequest, db: Session = Depends(get_db)):
    """Return top ranked pools for a template specification."""
    try:
        from backend.services.decision_engine_service import DecisionEngineService

        redis = get_redis_client()
        de = DecisionEngineService(db, redis)
        pools = de.rank_for_template(
            cluster_id=req.cluster_id,
            template=req.template,
            limit=req.limit,
            diversify=req.diversify,
        )
        return PoolResponse(pools=pools)
    except Exception as e:
        logger.error(f"[DE API] rank-for-template failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report-termination", response_model=StatusResponse)
def report_termination(req: ReportTerminationRequest, db: Session = Depends(get_db)):
    """Report a spot interruption — globally blacklist the pool."""
    try:
        from backend.services.decision_engine_service import DecisionEngineService

        redis = get_redis_client()
        de = DecisionEngineService(db, redis)
        result = de.report_termination(pool_key=req.pool_key, region=req.region)
        return StatusResponse(status=result.get("status", "ok"))
    except Exception as e:
        logger.error(f"[DE API] report-termination failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report-launch-failure", response_model=StatusResponse)
def report_launch_failure(req: ReportLaunchFailureRequest, db: Session = Depends(get_db)):
    """Report a launch failure. Auto-blacklists after threshold."""
    try:
        from backend.services.decision_engine_service import DecisionEngineService

        redis = get_redis_client()
        de = DecisionEngineService(db, redis)
        result = de.report_launch_failure(
            cluster_id=req.cluster_id,
            pool_key=req.pool_key,
            reason=req.reason,
            region=req.region,
        )
        return StatusResponse(
            status="ok",
            failure_count=result.get("failure_count"),
            blacklisted=result.get("blacklisted", False),
        )
    except Exception as e:
        logger.error(f"[DE API] report-launch-failure failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/blacklist")
def get_blacklist(
    region: str = Query(default="ap-south-1"),
    db: Session = Depends(get_db),
):
    """Return global blacklist for a region."""
    try:
        from backend.services.decision_engine_service import DecisionEngineService

        redis = get_redis_client()
        de = DecisionEngineService(db, redis)
        blacklisted = de.get_blacklist(region=region)
        return {"blacklisted_pools": blacklisted}
    except Exception as e:
        logger.error(f"[DE API] blacklist failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
