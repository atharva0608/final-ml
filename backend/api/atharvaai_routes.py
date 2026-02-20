"""
AtharvaAi API Routes - Pool Selection & Termination Monitoring

Endpoints:
- GET /api/v1/atharvaai/pools/rankings - Get ranked pools
- POST /api/v1/atharvaai/node-templates - Create node filtering template
- GET /api/v1/atharvaai/blacklist - Get globally flagged risky pools
- GET /api/v1/atharvaai/rebalancing/status - Get rebalancing actions status
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from backend.models.base import get_db
from backend.core.redis_client import get_redis_client
from backend.services.pool_ranking_service import PoolRankingService, NodeTemplate
from backend.models.rebalancing_action import RebalancingAction
from backend.models.termination_event import TerminationEvent
from backend.core.logger import logger
from sqlalchemy import func, extract
from datetime import timedelta

router = APIRouter(prefix="/atharvaai", tags=["AtharvaAi"])


# Request/Response Models

class NodeTemplateRequest(BaseModel):
    """User-defined node filtering requirements."""
    architecture: List[str] = Field(..., example=["amd64", "arm64"])
    vcpu_min: int = Field(..., example=2)
    vcpu_max: int = Field(..., example=8)
    memory_gb_min: int = Field(..., example=4)
    memory_gb_max: int = Field(..., example=32)
    allowed_families: Optional[List[str]] = Field(None, example=["m5", "c5", "r5"])
    allowed_sizes: Optional[List[str]] = Field(None, example=["xlarge", "2xlarge"])
    allowed_azs: Optional[List[str]] = Field(None, example=["aps1-az1", "aps1-az2"])
    excluded_instance_types: Optional[List[str]] = Field(None, example=["m5.metal"])


class PoolRankingResponse(BaseModel):
    """Ranked pool response."""
    instance_type: str
    az: str
    architecture: str
    vcpu: int
    memory_gb: float
    spot_price: float
    ondemand_price: float
    savings_pct: float  # 0-1 scale (e.g., 0.93 = 93% savings)
    cost_estimate: float  # USD per day/month
    ml_score: float
    rank: int
    is_flagged: bool  # Flagged by System B
    spot_advisor_rank: int  # 0-5 (AWS interruption frequency)
    timestamp: str


class BlacklistedPoolResponse(BaseModel):
    """Globally flagged risky pool."""
    instance_type: str
    az: str
    flagged_at: str
    ttl_remaining_seconds: int
    reason: str  # "termination_detected" or "high_interruption_rate"


class RebalancingStatusResponse(BaseModel):
    """Rebalancing action status."""
    cluster_id: str
    status: str  # "in_progress", "completed", "failed"
    trigger: str  # "emergency" or "graceful"
    source_pool: str  # instance_type:az
    target_pool: str  # instance_type:az
    started_at: str
    completed_at: Optional[str]
    duration_seconds: Optional[int]
    nodes_affected: Optional[int]
    error_message: Optional[str]


# Endpoints

@router.post("/pools/rankings", response_model=dict)
async def get_pool_rankings(
    template: Optional[NodeTemplateRequest] = None,
    region: str = Query("ap-south-1", description="AWS region"),
    limit: int = Query(10, ge=1, le=100, description="Maximum pools to return"),
    template_id: Optional[str] = Query(None, description="Node template ID to use for filtering"),
    db: Session = Depends(get_db)
):
    """
    Get ranked instance pools using AtharvaAi 8-step pipeline.

    **Pipeline Steps**:
    1. Node Template Filtering
    2. AZ Filtering
    3. Spot Advisor Filter
    4. Global Blacklist Check
    5. Capacity Check
    6. Price Fetch
    7. ML Model Scoring (ONNX inference)
    8. Final Ranking & Caching

    **Returns**: Top N pools sorted by ML score (savings % vs cost).

    **Note**: Either provide template in body OR template_id as query param (not both).
    """
    try:
        # Get Redis client
        redis = get_redis_client()

        # Determine which template to use
        template_applied = None
        if template_id:
            # Fetch template from database
            from backend.services.template_service import get_template_service
            from backend.models.user import User
            from backend.core.dependencies import get_current_user

            template_service = get_template_service(db)
            db_template = db.query(__import__('backend.models.node_template', fromlist=['NodeTemplate']).NodeTemplate).filter_by(id=template_id).first()

            if not db_template:
                raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

            # Convert DB template to NodeTemplateRequest
            template = NodeTemplateRequest(
                architecture=[db_template.architecture] if db_template.architecture else ["x86_64"],
                vcpu_min=2,  # Default values - adjust based on template
                vcpu_max=128,
                memory_gb_min=4,
                memory_gb_max=512,
                allowed_families=db_template.families if db_template.families else None,
                allowed_sizes=None,
                allowed_azs=None,
                excluded_instance_types=None
            )
            template_applied = {"id": db_template.id, "name": db_template.name}
        elif not template:
            raise HTTPException(status_code=400, detail="Either template body or template_id must be provided")

        # Convert request to NodeTemplate
        node_template = NodeTemplate(
            architecture=template.architecture,
            vcpu_range=(template.vcpu_min, template.vcpu_max),
            memory_range=(template.memory_gb_min, template.memory_gb_max),
            allowed_families=template.allowed_families,
            allowed_sizes=template.allowed_sizes,
            allowed_azs=template.allowed_azs,
            excluded_instance_types=template.excluded_instance_types
        )

        # Execute pool ranking pipeline
        ranking_service = PoolRankingService(db, redis)
        ranked_pools = ranking_service.rank_pools(node_template, region, limit)

        # Convert to response models
        pools = []
        for scored_pool in ranked_pools:
            pools.append(PoolRankingResponse(
                instance_type=scored_pool.pool.instance_type,
                az=scored_pool.pool.az,
                architecture=scored_pool.pool.architecture,
                vcpu=scored_pool.pool.vcpu,
                memory_gb=scored_pool.pool.memory_gb,
                spot_price=scored_pool.pool.spot_price,
                ondemand_price=scored_pool.pool.ondemand_price,
                savings_pct=scored_pool.savings_pct,
                cost_estimate=scored_pool.cost_estimate,
                ml_score=scored_pool.ml_score,
                rank=scored_pool.rank,
                is_flagged=scored_pool.is_flagged,
                spot_advisor_rank=scored_pool.pool.spot_advisor_rank,
                timestamp=scored_pool.timestamp.isoformat()
            ))

        return {
            "pools": pools,
            "template_applied": template_applied,
            "region": region,
            "total_results": len(pools)
        }

    except Exception as e:
        logger.error(f"Pool ranking failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pool ranking failed: {str(e)}")


@router.get("/blacklist", response_model=List[BlacklistedPoolResponse])
async def get_blacklisted_pools():
    """
    Get list of globally flagged risky pools (System B).

    Pools are flagged when:
    - Termination notice detected by DaemonSet
    - EventBridge termination event received
    - High interruption rate detected

    **TTL**: 12 hours (auto-expire)
    """
    try:
        # Get Redis client
        redis = get_redis_client()

        # Get all members of risky_pools set
        risky_pools = redis.smembers("risky_pools")

        response = []
        for pool_key in risky_pools:
            pool_key_str = pool_key.decode('utf-8') if isinstance(pool_key, bytes) else pool_key
            instance_type, az = pool_key_str.split(':')

            # Get TTL for this pool
            ttl = redis.ttl(f"risky_pool_meta:{pool_key_str}")

            # Get metadata (reason, timestamp)
            meta_key = f"risky_pool_meta:{pool_key_str}"
            meta_data = redis.get(meta_key)

            if meta_data:
                import json
                meta = json.loads(meta_data)
                flagged_at = meta.get('flagged_at', datetime.utcnow().isoformat())
                reason = meta.get('reason', 'termination_detected')
            else:
                flagged_at = datetime.utcnow().isoformat()
                reason = 'termination_detected'

            response.append(BlacklistedPoolResponse(
                instance_type=instance_type,
                az=az,
                flagged_at=flagged_at,
                ttl_remaining_seconds=ttl if ttl > 0 else 0,
                reason=reason
            ))

        return response

    except Exception as e:
        logger.error(f"Failed to get blacklist: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get blacklist: {str(e)}")


@router.get(
    "/blacklist/check",
    summary="Check if a specific pool is blacklisted",
    description="Quick check for a single instance_type + AZ combination"
)
def check_blacklisted_pool(
    instance_type: str = Query(..., description="Instance type to check, e.g. m5.xlarge"),
    az: str = Query(..., description="Availability zone, e.g. us-east-1a"),
):
    """
    Check if a specific instance_type + az combination is currently blacklisted.
    Returns blacklisted status, risk score, reason, and TTL.
    Used by Right-Sizing to validate recommendations before showing to user.
    """
    import redis
    import json
    from backend.core.config import settings

    try:
        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        pool_key = f"{instance_type}:{az}"

        # Check if in risky_pools set
        is_blacklisted = r.sismember("risky_pools", pool_key)

        if not is_blacklisted:
            return {
                "instance_type": instance_type,
                "az": az,
                "blacklisted": False,
                "risk_score": 0,
                "reason": None,
                "expires_in_seconds": None
            }

        # Get metadata if available
        metadata_key = f"risky_pool_meta:{pool_key}"
        metadata = r.get(metadata_key)
        meta = json.loads(metadata) if metadata else {}
        ttl = r.ttl(metadata_key)

        return {
            "instance_type": instance_type,
            "az": az,
            "blacklisted": True,
            "risk_score": meta.get("risk_score", 5),
            "reason": meta.get("reason", "Recent spot interruption detected"),
            "expires_in_seconds": max(ttl, 0) if ttl > 0 else None
        }
    except Exception as e:
        logger.warning(f"Redis blacklist check failed: {e}")
        return {
            "instance_type": instance_type,
            "az": az,
            "blacklisted": False,
            "risk_score": 0,
            "reason": None,
            "expires_in_seconds": None,
            "warning": "Blacklist check unavailable"
        }


@router.get("/rebalancing/status", response_model=List[RebalancingStatusResponse])
async def get_rebalancing_status(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster ID"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results"),
    db: Session = Depends(get_db)
):
    """
    Get status of auto-rebalancing actions (System B).

    **Rebalancing Types**:
    - **Emergency** (90 seconds): Triggered on termination notice
    - **Graceful** (10 minutes): Proactive rebalancing to safer pools

    **Status Values**:
    - `in_progress`: Currently draining/migrating
    - `completed`: Successfully rebalanced
    - `failed`: Rebalancing failed
    """
    try:
        # Query rebalancing_actions table
        query = db.query(RebalancingAction).order_by(RebalancingAction.started_at.desc())

        # Filter by cluster_id if provided
        if cluster_id:
            query = query.filter(RebalancingAction.cluster_id == cluster_id)

        # Apply limit
        actions = query.limit(limit).all()

        # Convert to response models
        response = []
        for action in actions:
            response.append(RebalancingStatusResponse(
                cluster_id=action.cluster_id,
                status=action.status,
                trigger=action.trigger,
                source_pool=action.source_pool,
                target_pool=action.target_pool,
                started_at=action.started_at.isoformat() if action.started_at else None,
                completed_at=action.completed_at.isoformat() if action.completed_at else None,
                duration_seconds=action.duration_seconds,
                nodes_affected=action.nodes_affected,
                error_message=action.error_message
            ))

        return response

    except Exception as e:
        logger.error(f"Failed to get rebalancing status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get rebalancing status: {str(e)}")


class HeatmapCell(BaseModel):
    day: int  # 0-6 (Sun-Sat) or 1-7 depending on frontend pref. Let's use 0=Monday to match JS often, or just 0-6.
    hour: int  # 0-23
    interruption_count: int
    risk_level: str  # "LOW", "MEDIUM", "HIGH"

class InterruptionHeatmapResponse(BaseModel):
    family: str  # e.g., "m5", "c5"
    heatmap: List[HeatmapCell]

@router.get("/interruption-heatmap", response_model=List[InterruptionHeatmapResponse])
async def get_interruption_heatmap(
    region: str = Query("ap-south-1", description="AWS region"),
    days: int = Query(30, description="Analysis window in days"),
    db: Session = Depends(get_db)
):
    """
    Get 7x24 interruption heatmap by instance family.
    Aggregates TerminationEvent data.
    """
    from backend.models.termination_event import TerminationEvent
    from sqlalchemy import func, text
    
    try:
        # Calculate cutoff date
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        # Aggregate interruptions by family, day_of_week, hour
        # extracting day of week (0-6) and hour (0-23) from detected_at
        
        # SQLite vs Postgres syntax differences handled by SQLAlchemy extract usually
        # But for complex grouping, text() might be safer if flexible
        
        # Extract family from instance_type (e.g., "m5.xlarge" -> "m5")
        # SQL substring logic varies. 
        # For MVP/Demo, let's fetch events and aggregate in Python to be DB-agnostic & safer
        
        events = db.query(
            TerminationEvent.instance_type,
            TerminationEvent.detected_at
        ).filter(
            TerminationEvent.detected_at >= cutoff,
            TerminationEvent.region == region
        ).all()
        
        # Aggregation structure: family -> day -> hour -> count
        agg = {}
        
        for e in events:
            # Extract family
            family = e.instance_type.split('.')[0] # "m5"
            
            # Extract time slots
            # 0=Monday, 6=Sunday
            day = e.detected_at.weekday() 
            hour = e.detected_at.hour
            
            if family not in agg:
                agg[family] = {}
            if day not in agg[family]:
                agg[family][day] = {}
            
            agg[family][day][hour] = agg[family][day].get(hour, 0) + 1
            
        response = []
        
        # If no events, return empty or mock data? 
        # Let's return empty structure if truly empty, but UI might want *something*.
        # For now, real data only.
        
        for family, days_data in agg.items():
            cells = []
            # Fill 7x24 grid ? or just sparse? 
            # UI usually prefers sparse or full. Let's do sparse to save bandwidth, frontend fills 0s.
            for d in range(7):
                for h in range(24):
                    count = days_data.get(d, {}).get(h, 0)
                    if count > 0:
                         # Determine risk
                        if count >= 5: risk = "HIGH"
                        elif count >= 2: risk = "MEDIUM"
                        else: risk = "LOW"
                        
                        cells.append(HeatmapCell(
                            day=d,
                            hour=h,
                            interruption_count=count,
                            risk_level=risk
                        ))
            
            if cells:
                response.append(InterruptionHeatmapResponse(
                    family=family,
                    heatmap=cells
                ))
                
        return response

    except Exception as e:
        logger.error(f"Failed to get heatmap: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get heatmap: {str(e)}")


@router.get("/health")
async def health_check():
    """
    Health check endpoint for AtharvaAi system.
    
    Reports ML pipeline status including circuit breaker state.
    Operators should monitor `ml_status` — if "degraded", fallback scoring
    is active and rankings may be less accurate.
    """
    try:
        redis = get_redis_client()
        ml_degraded = redis.get("atharvaai:ml_degraded")
        ml_fail_count = int(redis.get("atharvaai:ml_fail_count") or 0)
        is_degraded = ml_degraded == b"true" or ml_degraded == "true"
    except Exception:
        is_degraded = False
        ml_fail_count = 0

    return {
        "status": "degraded" if is_degraded else "healthy",
        "service": "AtharvaAi Pool Selection & Termination Monitoring",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "ml_status": "degraded" if is_degraded else "healthy",
        "fallback_active": is_degraded,
        "ml_fail_count_10min": ml_fail_count
    }
