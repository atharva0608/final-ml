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
    predicted_savings: float  # From regressor_6.onnx (0-1, e.g., 0.82 = 82% savings vs on-demand)
    risk_probability: float  # From classifier_6.onnx (0-1, lower = safer)
    expected_value: float  # Risk-adjusted EV = predicted_savings × (1 - risk_probability)
    savings_pct: float  # Legacy alias for predicted_savings
    cost_estimate: float  # Legacy alias for risk_probability
    ml_score: float  # Composite: (savings × 0.4) - (risk × 0.6)
    rank: int
    is_flagged: bool  # Flagged by global blacklist
    spot_advisor_rank: int  # 0-5 (AWS interruption frequency)
    timestamp: str
    blacklisted: bool = False  # Temporarily blacklisted due to launch failures / terminations
    price_shock: bool = False  # Detected rapid spot price spike (>30% in 1h)


class BlacklistedPoolResponse(BaseModel):
    """Globally flagged risky pool."""
    instance_type: str
    az: str
    flagged_at: str
    ttl_remaining_seconds: int
    reason: str  # "termination_detected" or "high_interruption_rate"


class RebalancingStatusResponse(BaseModel):
    """Rebalancing action status with step timeline."""
    cluster_id: str
    status: str  # "in_progress", "waiting_agent", "completed", "failed"
    trigger: str  # "emergency" or "graceful" or "auto_rebalance"
    source_pool: str  # instance_type:az
    target_pool: str  # instance_type:az
    started_at: str
    completed_at: Optional[str]
    duration_seconds: Optional[int]
    nodes_affected: Optional[int]
    error_message: Optional[str]
    # Step timeline — each key is present when that step completed
    current_step: Optional[str]       # provisioning_spot_pool | cordoning_node | draining_pods |
                                      # waiting_for_spot_node | old_node_terminating |
                                      # optimization_complete | failed
    step_1_spot_provisioning: Optional[str]   # ISO timestamp when NodePool patched
    step_2_cordon: Optional[str]              # ISO timestamp when node cordoned
    step_3_draining_pods: Optional[str]       # ISO timestamp when drain completed
    step_4_new_node_joined: Optional[str]     # ISO timestamp when new SPOT node detected
    step_5_old_node_terminated: Optional[str] # ISO timestamp when old OD node terminated
    step_6_optimization_complete: Optional[str]  # ISO timestamp when fully done
    instance_id: Optional[str]               # EC2 instance ID being migrated
    provisioner_type: Optional[str]          # 'karpenter' or 'agent' (direct EC2)


# Endpoints

@router.get("/clusters/{cluster_id}/effective-configuration")
def get_effective_configuration(
    cluster_id: str,
    db: Session = Depends(get_db)
):
    from backend.models.cluster import Cluster
    from backend.models.node_template import ClusterTemplateMapping
    
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
        
    automation = cluster.optimization_settings
    strategy = cluster.optimization_strategy_profile
    stateless = cluster.stateless_rules
    stateful = cluster.stateful_rules
    
    # Check for active template
    active_mapping = db.query(ClusterTemplateMapping).filter(
        ClusterTemplateMapping.cluster_id == cluster_id,
        ClusterTemplateMapping.is_default == True
    ).first()
    
    template_name = "None"
    if active_mapping and active_mapping.template:
        template_name = active_mapping.template.name
        
    # Build effective config unifying the override hierarchy (Cluster Policy > Template > Strategy)
    config = {
        "auto_rebalance": "ON" if (automation and automation.auto_rebalance_enabled) else "OFF",
        "auto_rightsizing": "ON" if (automation and automation.auto_rightsizing_enabled) else "OFF",
        "strategy": strategy.strategy_type.capitalize() if strategy else "Balanced",
        "template": template_name,
        "stateful_spot": "BLOCKED" if (stateful and stateful.block_spot_for_stateful) else "ALLOWED",
        "substitute_mode": stateless.substitute_strategy.capitalize() if stateless else "Prewarmed",
        "target_spot_exposure_pct": automation.target_spot_exposure_pct if automation else 100
    }
    
    return config

@router.post("/pools/rankings", response_model=dict)
async def get_pool_rankings(
    template: Optional[NodeTemplateRequest] = None,
    region: str = Query("ap-south-1", description="AWS region"),
    limit: int = Query(10, ge=1, le=100, description="Maximum pools to return"),
    template_id: Optional[str] = Query(None, description="Node template ID to use for filtering"),
    current_instance_type: Optional[str] = Query(None, description="Current node instance type for real savings calculation"),
    current_instance_lifecycle: Optional[str] = Query(None, description="Current node lifecycle: 'spot' or 'on-demand'"),
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
        # Debug logging
        logger.info(f"Pool rankings request: template_id={template_id}, region={region}, "
                   f"current_instance_type={current_instance_type}, current_instance_lifecycle={current_instance_lifecycle}")

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

        # Get current node price if context provided (for real savings calculation)
        current_node_price = None
        if current_instance_type:
            from backend.services.aws_pricing_service import AWSPricingService
            pricing_service = AWSPricingService(db, redis)

            # Get current node price based on lifecycle
            if current_instance_lifecycle and current_instance_lifecycle.lower() == 'spot':
                # For spot instances, get current spot price (use first AZ as approximation)
                azs = [pool.pool.az for pool in ranked_pools[:3]]  # Get AZ from top pools
                if azs:
                    current_node_price = pricing_service.get_spot_price(
                        current_instance_type,
                        azs[0],
                        region,
                        validate_freshness=False
                    )
            else:
                # For on-demand instances (or unspecified), get on-demand price
                current_node_price = pricing_service.get_ondemand_price(
                    current_instance_type,
                    region,
                    validate_freshness=False
                )

            logger.info(f"Current node {current_instance_type} ({current_instance_lifecycle or 'on-demand'}) price: ${current_node_price}/hr")

        # Convert to response models
        from backend.core.scoring import compute_expected_value

        rankings = []
        for scored_pool in ranked_pools:
            # Calculate real savings if current node price available
            real_savings_pct = scored_pool.predicted_savings  # Default to ML model prediction

            if current_node_price and current_node_price > 0:
                # Real savings: (current_price - suggested_spot_price) / current_price
                suggested_spot_price = scored_pool.pool.spot_price
                real_savings = (current_node_price - suggested_spot_price) / current_node_price
                real_savings_pct = max(0.0, min(1.0, real_savings))  # Clamp to [0, 1]

                logger.debug(
                    f"Pool {scored_pool.pool.instance_type}/{scored_pool.pool.az}: "
                    f"Current=${current_node_price:.4f} vs Suggested=${suggested_spot_price:.4f} "
                    f"→ Real savings={real_savings_pct*100:.1f}%"
                )

            # Recalculate expected value with real savings
            expected_value = compute_expected_value(
                predicted_savings=real_savings_pct,
                risk_probability=scored_pool.risk_probability
            )

            # Check per-pool blacklist and price shock signals from Redis
            pool_key = f"{scored_pool.pool.instance_type}:{scored_pool.pool.az}"
            try:
                is_blacklisted = bool(redis.exists(f"blacklist:pool:{pool_key}"))
                price_shock_val = redis.get(f"price_shock:{pool_key}")
                has_price_shock = price_shock_val is not None
            except Exception:
                is_blacklisted = False
                has_price_shock = False

            rankings.append(PoolRankingResponse(
                instance_type=scored_pool.pool.instance_type,
                az=scored_pool.pool.az,
                architecture=scored_pool.pool.architecture,
                vcpu=scored_pool.pool.vcpu,
                memory_gb=scored_pool.pool.memory_gb,
                spot_price=scored_pool.pool.spot_price,
                ondemand_price=scored_pool.pool.ondemand_price,
                predicted_savings=real_savings_pct,  # Use real savings if available
                risk_probability=scored_pool.risk_probability,
                expected_value=expected_value,
                savings_pct=real_savings_pct,  # Use real savings
                cost_estimate=float(scored_pool.pool.spot_price) * 24.0,  # Legacy alias (per day)
                ml_score=scored_pool.ml_score,
                rank=scored_pool.rank,
                is_flagged=scored_pool.is_flagged,
                spot_advisor_rank=scored_pool.pool.spot_advisor_rank,
                timestamp=scored_pool.timestamp.isoformat(),
                blacklisted=is_blacklisted,
                price_shock=has_price_shock,
            ))

        return {
            "rankings": rankings,
            "template_applied": template_applied,
            "region": region,
            "total_results": len(rankings),
            "current_node_context": {
                "instance_type": current_instance_type,
                "lifecycle": current_instance_lifecycle or "on-demand",
                "price": current_node_price
            } if current_instance_type else None,
            "savings_calculation_mode": "real" if current_node_price else "pool_internal"
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

    **TTL**: 24 hours (auto-expire, exponential backoff for repeat offenders)
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
            _meta = action.action_metadata or {}
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
                error_message=action.error_message,
                current_step=_meta.get("current_step"),
                step_1_spot_provisioning=_meta.get("step_1_spot_provisioning"),
                step_2_cordon=_meta.get("step_2_cordon"),
                step_3_draining_pods=_meta.get("step_3_draining_pods"),
                step_4_new_node_joined=_meta.get("step_4_new_node_joined"),
                step_5_old_node_terminated=_meta.get("step_5_old_node_terminated"),
                step_6_optimization_complete=_meta.get("step_6_optimization_complete"),
                instance_id=_meta.get("instance_id"),
                provisioner_type=_meta.get("provisioner_type"),
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


# ============================================================================
# Decision Engine v3 API Endpoints
# ============================================================================


@router.get("/v3/global-intelligence/status")
async def get_global_intelligence_status(
    region: str = Query("ap-south-1", description="AWS region"),
    db: Session = Depends(get_db)
):
    """
    Returns current state of global intelligence cache.

    Returns: last ranking timestamp, pools evaluated, cache TTL remaining,
    capacity validated count, DryRun budget remaining, and model version.
    """
    try:
        redis = get_redis_client()
        from backend.services.global_pool_cache_service import GlobalPoolCacheService
        import json

        cache_svc = GlobalPoolCacheService(db, redis)
        status = cache_svc.get_cache_status(region)

        # Get cached rankings to count pools and capacity-validated
        cache_key = f"spot:rankings:{region}"
        cached = redis.get(cache_key)
        pools_evaluated = 0
        capacity_validated_count = 0
        last_ranking_timestamp = None

        if cached:
            rankings = json.loads(cached)
            pools_evaluated = len(rankings)
            capacity_validated_count = sum(
                1 for p in rankings if p.get("capacity_status") == "validated"
            )
            if rankings:
                last_ranking_timestamp = rankings[0].get("timestamp")

        # DryRun budget remaining
        active_clusters = int(redis.get("spot:active_cluster_count") or 1)
        max_budget = min(200, max(25, active_clusters * 2))
        used = int(redis.get(f"spot:dryrun_count:{region}") or 0)

        return {
            "region": region,
            "last_ranking_timestamp": last_ranking_timestamp,
            "pools_evaluated": pools_evaluated,
            "cache_ttl_remaining": status.get("ttl_seconds", 0),
            "capacity_validated_count": capacity_validated_count,
            "dryrun_budget_remaining": max(0, max_budget - used),
            "dryrun_budget_total": max_budget,
            "model_version": "6",
            "active_clusters": active_clusters
        }
    except Exception as e:
        logger.error(f"Failed to get global intelligence status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v3/diversity/{cluster_id}")
async def get_cluster_diversity(cluster_id: str):
    """
    Returns family and AZ diversity distribution for the cluster.

    Used by UI to render diversity gauge showing concentration risk.
    """
    try:
        redis = get_redis_client()
        from backend.services.diversity_enforcer import DiversityEnforcer

        enforcer = DiversityEnforcer(redis)
        diversity = enforcer.get_cluster_diversity(cluster_id)

        return {
            "cluster_id": cluster_id,
            **diversity,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get diversity for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v3/state-machine/{cluster_id}")
async def get_state_machine_status(
    cluster_id: str,
    db: Session = Depends(get_db)
):
    """
    Returns current state machine position for the cluster.

    Combines: optimization mode, cooldown status, substitute state,
    and last evaluation result into a single dashboard-ready response.
    """
    try:
        redis = get_redis_client()
        from backend.services.cooldown_controller import CooldownController
        from backend.services.substitute_manager import SubstituteManager
        from backend.models.cluster import Cluster

        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

        cooldown = CooldownController(redis)
        cooldown_status = cooldown.get_cluster_cooldown_status(cluster_id)

        sub_mgr = SubstituteManager(db, redis)
        sub_state = sub_mgr.get_state(cluster_id)

        # Check circuit breaker
        breaker_key = f"spot:cluster_circuit_breaker:{cluster_id}"
        breaker_active = bool(redis.get(breaker_key))

        # Check model mismatch
        mismatch_key = f"spot:model_mismatch:{cluster_id}"
        model_mismatch = bool(redis.get(mismatch_key))

        return {
            "cluster_id": cluster_id,
            "optimization_mode": cluster.optimization_mode or "BALANCED",
            "model_version": cluster.model_version or "6",
            "cooldown": cooldown_status,
            "substitute_state": sub_state.value if hasattr(sub_state, 'value') else str(sub_state),
            "circuit_breaker_active": breaker_active,
            "model_mismatch": model_mismatch,
            "workload_type": cluster.workload_type or "STATELESS",
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get state machine for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class OptimizationModeRequest(BaseModel):
    """Request to change cluster optimization mode."""
    mode: str = Field(..., description="COST_FIRST, BALANCED, or NO_DOWNTIME_FIRST")


@router.put("/v3/cluster/{cluster_id}/optimization-mode")
async def update_optimization_mode(
    cluster_id: str,
    mode: str = Query(..., description="Optimization mode: COST_FIRST, BALANCED, or NO_DOWNTIME_FIRST"),
    db: Session = Depends(get_db)
):
    """
    Switch cluster optimization mode.

    Enforces 30-minute dwell time between mode switches to prevent flapping.
    Valid modes: COST_FIRST, BALANCED, NO_DOWNTIME_FIRST.
    """
    from backend.core.decision_engine import OPTIMIZATION_PROFILES
    from backend.models.cluster import Cluster

    valid_modes = list(OPTIMIZATION_PROFILES.keys())
    if mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{mode}'. Must be one of: {valid_modes}"
        )

    try:
        redis = get_redis_client()

        # Check dwell cooldown (30 min between mode switches)
        dwell_key = f"spot:cooldown:mode_switch:{cluster_id}"
        dwell_ttl = redis.ttl(dwell_key)
        if dwell_ttl and dwell_ttl > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Mode switch cooldown active. Retry in {dwell_ttl}s ({dwell_ttl // 60}m remaining)"
            )

        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

        old_mode = cluster.optimization_mode or "BALANCED"
        cluster.optimization_mode = mode
        db.commit()

        # Set 30-minute dwell cooldown
        redis.setex(dwell_key, 1800, "active")

        logger.info(f"Cluster {cluster_id} mode changed: {old_mode} → {mode}")

        return {
            "cluster_id": cluster_id,
            "old_mode": old_mode,
            "new_mode": mode,
            "dwell_cooldown_seconds": 1800,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update optimization mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ModelVersionRequest(BaseModel):
    """Request to upgrade cluster model version."""
    version: str = Field(..., description="New model version (e.g., '7')")


@router.put("/v3/cluster/{cluster_id}/model-version")
async def update_model_version(
    cluster_id: str,
    payload: ModelVersionRequest,
    db: Session = Depends(get_db)
):
    """
    Admin-only: upgrade cluster model version after retraining.

    Performs ALL 4 steps to prevent cluster from getting stuck:
    1. Update cluster.model_version in DB
    2. Clear model mismatch key (prevent repeated fallback)
    3. Clear cluster cooldown
    4. Trigger immediate evaluation
    """
    from backend.models.cluster import Cluster

    try:
        redis = get_redis_client()

        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

        old_version = cluster.model_version or "6"

        # Step 1: Update cluster.model_version in DB
        cluster.model_version = payload.version
        db.commit()

        # Step 2: Clear model mismatch key — prevent repeated fallback
        redis.delete(f"spot:model_mismatch:{cluster_id}")

        # Step 3: Clear cluster cooldown — allow immediate re-evaluation
        redis.delete(f"spot:cooldown:cluster:{cluster_id}")

        # Step 4: Trigger immediate evaluation (mark for next scheduler cycle)
        redis.setex(f"spot:trigger_eval:{cluster_id}", 300, "pending")

        logger.info(f"Cluster {cluster_id} model upgraded: v{old_version} → v{payload.version}")

        return {
            "cluster_id": cluster_id,
            "old_version": old_version,
            "new_version": payload.version,
            "mismatch_cleared": True,
            "cooldown_cleared": True,
            "evaluation_triggered": True,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update model version: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v3/metrics")
async def get_v3_metrics():
    """
    Returns all Decision Engine v3 observability counters.

    Reads spot:metrics:* keys from Redis. Used by monitoring dashboards.
    """
    try:
        redis = get_redis_client()

        # Read all v3 metric counters
        metric_keys = [
            "spot:metrics:evaluations_total",
            "spot:metrics:switches_total",
            "spot:metrics:holds_total",
            "spot:metrics:fallback_on_demand",
            "spot:metrics:circuit_breaker_tripped",
            "spot:metrics:model_mismatch_itn_bypass",
            "spot:metrics:model_mismatch_auto_fallback",
            "spot:metrics:volatility_blocked_switches",
            "spot:metrics:substitute_deployed",
            "spot:metrics:substitute_promoted",
            "spot:metrics:termination_handled",
            "spot:metrics:drain_validation_failed",
            "spot:metrics:dryrun_starvation_ratio",
            "spot:metrics:deadlock_guard_activated",
        ]

        metrics = {}
        for key in metric_keys:
            val = redis.get(key)
            metric_name = key.replace("spot:metrics:", "")
            metrics[metric_name] = int(val) if val else 0

        return {
            "metrics": metrics,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get v3 metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v3/cooldown/{cluster_id}")
async def get_cooldown_status(cluster_id: str):
    """
    Get cluster cooldown status.

    Returns remaining cooldown time for cluster-level optimizations.
    """
    try:
        redis = get_redis_client()
        from backend.services.cooldown_controller import CooldownController

        controller = CooldownController(redis)
        status = controller.get_cluster_cooldown_status(cluster_id)

        return {
            "cluster_id": cluster_id,
            "cooldown_active": status.get("active", False),
            "remaining_seconds": status.get("remaining_seconds", 0),
            "remaining_minutes": status.get("remaining_minutes", 0),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get cooldown status for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v3/workload-status/{cluster_id}")
async def get_workload_status(cluster_id: str):
    """
    Get workload classification for cluster nodes.

    Returns classification of nodes as STATELESS_ELIGIBLE, STATEFUL, etc.
    """
    try:
        redis = get_redis_client()
        from backend.services.workload_inspector import WorkloadInspector

        inspector = WorkloadInspector(redis, k8s_client=None)
        classification = inspector.get_cached_classification(cluster_id)

        if not classification:
            return {
                "cluster_id": cluster_id,
                "status": "classification_unavailable",
                "nodes": {},
                "eligible_count": 0,
                "total_count": 0,
                "timestamp": datetime.utcnow().isoformat()
            }

        eligible_count = sum(
            1 for status in classification.values()
            if status == "STATELESS_ELIGIBLE"
        )

        return {
            "cluster_id": cluster_id,
            "nodes": classification,
            "eligible_count": eligible_count,
            "total_count": len(classification),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get workload status for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v3/substitute/{cluster_id}")
async def get_substitute_status(
    cluster_id: str,
    db: Session = Depends(get_db)
):
    """
    Get warm spare substitute status for cluster.

    Returns:
      - state: PREWARMING / READY / ACTIVE / RELEASING / IDLE
      - is_warm_spare: true when 24x7 spare is running
      - spare_instance_type / spare_az / spot_price_hourly / monthly_cost
      - compatible_with: "Any node ≤ N vCPU / M GB"
      - next_spare: present when primary is ACTIVE and replacement is prewarming
    """
    try:
        redis = get_redis_client()
        from backend.services.substitute_manager import SubstituteManager

        manager = SubstituteManager(db, redis)
        status = manager.get_substitute_status(cluster_id)

        if status:
            return {
                "cluster_id": cluster_id,
                "state": status.get("state", "IDLE"),
                "is_warm_spare": status.get("is_warm_spare", False),
                "spare_instance_type": status.get("substitute_instance_type"),
                "spare_az": status.get("substitute_az"),
                "spare_lifecycle": status.get("substitute_lifecycle", "spot"),
                "spot_price_hourly": status.get("spot_price_hourly"),
                "monthly_cost": status.get("monthly_cost"),
                "risk_score": status.get("risk_score"),
                "target_vcpu": status.get("target_vcpu"),
                "target_memory_gb": status.get("target_memory_gb"),
                "target_node_instance_type": status.get("target_node_instance_type"),
                "compatible_with": status.get("compatible_with"),
                "started_at": status.get("started_at"),
                "next_spare": status.get("next_spare"),
                "cost_drift": status.get("cost_drift"),
                "timestamp": datetime.utcnow().isoformat()
            }

        return {
            "cluster_id": cluster_id,
            "state": "IDLE",
            "is_warm_spare": False,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get substitute status for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/volatility/status")
async def get_volatility_status(db: Session = Depends(get_db)):
    """
    Get volatility detection system status.

    Returns:
    - baseline_count: Number of family hour baselines in database
    - latest_baseline_date: Most recent baseline date
    - active_families: Number of instance families with baselines
    - regions_covered: Number of regions with baseline data
    - system_status: Overall system health (active/inactive)
    """
    try:
        from backend.models.family_hour_baseline import FamilyHourBaseline

        # Get baseline statistics
        baseline_count = db.query(FamilyHourBaseline).count()

        # Get latest baseline date
        latest = db.query(func.max(FamilyHourBaseline.date)).scalar()

        # Count active families
        active_families = db.query(
            func.count(func.distinct(FamilyHourBaseline.instance_family))
        ).scalar() or 0

        # Count regions covered
        regions_covered = db.query(
            func.count(func.distinct(FamilyHourBaseline.region))
        ).scalar() or 0

        # Determine system status
        system_status = "active" if baseline_count > 0 else "inactive"

        # Build az_pressure map from Redis (key: az_pressure:{az} → float)
        az_pressure = {}
        try:
            _redis = get_redis_client()
            az_pressure_keys = _redis.keys("az_pressure:*") or []
            for k in az_pressure_keys:
                k_str = k.decode('utf-8') if isinstance(k, bytes) else k
                az_name = k_str.replace("az_pressure:", "")
                val = _redis.get(k)
                if val is not None:
                    try:
                        az_pressure[az_name] = float(val)
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

        return {
            "baseline_count": baseline_count,
            "latest_baseline_date": latest.isoformat() if latest else None,
            "active_families": active_families,
            "regions_covered": regions_covered,
            "system_status": system_status,
            "regime": "NORMAL", # Required by frontend UI
            "az_pressure": az_pressure,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get volatility status: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/clusters/{cluster_id}/node-recommendations")
async def get_node_recommendations(
    cluster_id: str,
    db: Session = Depends(get_db),
):
    """
    Per-node recommendations: which nodes are eligible to move to spot,
    which are at risk, with ML risk scores and savings projections.

    Uses real ML pool rankings for target pool selection.
    Rotates different target pools per node to enforce diversity
    (no two nodes assigned the same pool).
    """
    from backend.models.instance import Instance
    from backend.models.cluster import Cluster
    from backend.services.pool_ranking_service import PoolRankingService, NodeTemplate
    from backend.services.workload_inspector import WorkloadInspector, NodeStatus
    from backend.core.redis_client import get_redis_client
    from backend.services.dynamic_instance_helpers import bulk_get_hourly_prices, bulk_get_vcpu_counts, bulk_get_memory_gb

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    region = getattr(cluster, 'region', None) or 'ap-south-1'

    # Only running instances; deduplicate by K8s node hostname so that
    # real EC2 records (i-xxxx) and daemon-set placeholders (ip-xxx-xxx)
    # for the same physical node are collapsed to one entry.
    _all_instances = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.state == 'running',
    ).all()
    _seen: dict = {}
    for _inst in _all_instances:
        # Normalise key: use short hostname so 'ip-192-168-3-201' and
        # 'ip-192-168-3-201.ap-south-1.compute.internal' both map to the same key.
        _key = (_inst.node_name or _inst.instance_id or '').split('.')[0]
        _existing = _seen.get(_key)
        if _existing is None:
            _seen[_key] = _inst
        else:
            _is_real = _inst.instance_id and _inst.instance_id.startswith('i-')
            _ex_real = _existing.instance_id and _existing.instance_id.startswith('i-')
            if _is_real and not _ex_real:
                # Prefer real EC2 record; carry over utilisation from placeholder if available
                if _existing.cpu_util is not None and _inst.cpu_util is None:
                    _inst.cpu_util = _existing.cpu_util
                    _inst.memory_util = _existing.memory_util
                _seen[_key] = _inst
            elif _ex_real and not _is_real:
                # Keep existing real record; update util if placeholder has fresher data
                if _inst.cpu_util is not None and (_existing.cpu_util is None or _existing.cpu_util == 0):
                    _existing.cpu_util = _inst.cpu_util
                    _existing.memory_util = _inst.memory_util
    instances = list(_seen.values())

    # Collect all unique instance types from the cluster nodes
    _all_instance_types = list({(inst.instance_type or "m5.large") for inst in instances})

    # Dynamically fetch on-demand pricing (AWS API → DB → hardcoded fallback)
    redis = get_redis_client()
    INSTANCE_HOURLY = bulk_get_hourly_prices(db, redis, _all_instance_types, region)

    # Dynamically fetch vCPU & Memory limits (InstanceCatalog DB → hardcoded fallback)
    VCPU_COUNT = bulk_get_vcpu_counts(db, _all_instance_types, region)
    MEM_GB_MAP = bulk_get_memory_gb(db, _all_instance_types, region)

    # ── Get real ML pool rankings for this cluster's region ───────────────
    top_pools = []
    try:
        ranking_svc = PoolRankingService(db, redis)
        top_pools = ranking_svc.rank_pools(
            node_template=NodeTemplate(
                architecture=["amd64", "arm64"],
                vcpu_range=(1, 64),
                memory_range=(1, 256),
            ),
            region=region,
            limit=50  # Large limit so size filter has enough candidates
        )
    except Exception as _e:
        logger.warning(f"Pool rankings unavailable for node-recommendations: {_e}")

    # Total eligible pools after filter (used by UI summary card)
    eligible_pools_count = len(top_pools)

    # ── Load cluster strategy for risk/savings tradeoff ────────────────────
    from backend.models.cluster import OptimizationStrategy
    strategy = cluster.optimization_strategy_profile
    risk_tradeoff_pct = (strategy.risk_savings_tradeoff_pct if strategy else 20) or 20
    risk_ceiling = ((strategy.risk_ceiling_percent if strategy else 25) or 25) / 100.0

    # ── Load diversify_pools setting ────────────────────────────────────────
    opt = cluster.optimization_settings
    _diversify_enabled = bool(getattr(opt, 'diversify_pools', False)) if opt else False

    # ── Sort pools risk-first (lowest risk → highest), savings as tiebreaker ──
    if top_pools:
        top_pools.sort(key=lambda p: (p.risk_probability, -p.predicted_savings))

    # ── Get cached workload classification (stateless vs stateful) ────────
    inspector = WorkloadInspector(redis)
    node_classification = inspector.get_cached_classification(cluster_id) or {}

    recommendations = []
    used_types = set()  # Diversity by instance_type so each node gets a different type
    _target_family_counts: dict = {}  # family → # of nodes assigned, for 40% cap when diversify ON

    # Normalise ORM instances to a common dict interface
    _node_list = [
        {
            "instance_id": inst.instance_id or f"node-{str(inst.id)[:8]}",
            # Prefer K8s node hostname (ip-192-168-x-x); fall back to EC2 instance ID
            "node_name": (inst.node_name or "").split('.')[0] or inst.instance_id or f"node-{str(inst.id)[:8]}",
            "instance_type": inst.instance_type or "m5.large",
            "az": inst.az or f"{region}a",
            "lifecycle": (inst.lifecycle.value if hasattr(inst.lifecycle, 'value') else str(inst.lifecycle or 'on-demand')).lower(),
            "cpu_util": float(inst.cpu_util) if getattr(inst, 'cpu_util', None) else 0.0,
            "memory_util": float(inst.memory_util) if getattr(inst, 'memory_util', None) else 0.0,
            "risk_score": float(inst.risk_score) if getattr(inst, 'risk_score', None) else None,
        }
        for inst in instances
    ]

    for node in _node_list:
        instance_type = node["instance_type"]
        az = node["az"]
        lifecycle = node["lifecycle"]
        is_already_spot = 'spot' in lifecycle

        node_name = node["node_name"]
        on_demand_hourly = INSTANCE_HOURLY.get(instance_type, 0.096)
        
        # Original Provisioned Limits
        current_vcpu = VCPU_COUNT.get(instance_type, 2)
        current_mem = MEM_GB_MAP.get(instance_type, 8.0)
        
        # Real-time Telemetry bounds (with safety floor)
        cpu_util_pct = max(10.0, node["cpu_util"])
        mem_util_pct = max(10.0, node["memory_util"])
        
        # Required compute: actual current usage + 25% safety headroom margin
        required_vcpu_exact = (current_vcpu * (cpu_util_pct / 100.0)) * 1.25
        required_mem_exact = (current_mem * (mem_util_pct / 100.0)) * 1.25
        
        # Minimum absolute values to avoid extreme micro-sizing
        required_vcpu = max(1.0, required_vcpu_exact)
        required_mem = max(2.0, required_mem_exact)

        # ── Workload type from WorkloadInspector cache ────────────────────
        cached_status = node_classification.get(node_name)
        if cached_status == "STATEFUL_PROTECTED":
            workload_type = "stateful"
        elif cached_status == "SYSTEM_PROTECTED":
            workload_type = "system"
        else:
            workload_type = "stateless"

        # ── Select safest sized target pool with diversity ──────
        target_type = instance_type  # default: no better pool found
        target_az = az
        spot_price_hourly = on_demand_hourly  # default: no savings
        spot_savings_pct = 0                  # default: no savings (not hardcoded 70%)
        risk_score = float(node["risk_score"]) if node.get("risk_score") is not None else 0.25

        # Maximum price we'll accept: current OD price + tradeoff% headroom
        max_acceptable_price = on_demand_hourly * (1.0 + risk_tradeoff_pct / 100.0)

        chosen_pool = None  # reset per node

        # For already-SPOT nodes: compute their actual realized savings vs on-demand
        # so the table shows real data ("t3.medium spot saving 54% vs OD") not 0%
        if is_already_spot:
            # Try to get current spot price for this instance type from ranked pools
            _spot_match = next(
                (p for p in top_pools if p.pool.instance_type == instance_type
                 and (not p.pool.az or p.pool.az == az or p.pool.az.startswith(region))),
                None
            ) or next((p for p in top_pools if p.pool.instance_type == instance_type), None)
            if _spot_match and _spot_match.pool.spot_price > 0 and on_demand_hourly > 0:
                spot_price_hourly = _spot_match.pool.spot_price
                raw_savings = (on_demand_hourly - spot_price_hourly) / on_demand_hourly * 100
                spot_savings_pct = max(0, round(raw_savings))
                risk_score = _spot_match.risk_probability
            elif _spot_match:
                spot_savings_pct = round(_spot_match.predicted_savings * 100)
                risk_score = _spot_match.risk_probability
            elif on_demand_hourly > 0:
                # No ML pool data for this type — apply conservative 60% spot discount estimate
                spot_price_hourly = on_demand_hourly * 0.4
                spot_savings_pct = 60
                risk_score = 0.2

        if not is_already_spot and top_pools:
            _total_nodes = len(_node_list)

            # Pass 1: Fits required compute + within price ceiling + below risk ceiling + unused type
            for pool in top_pools:
                if pool.pool.instance_type in used_types:
                    continue

                # Diversify: enforce 40% family cap when diversify_pools is ON
                if _diversify_enabled:
                    _pool_fam = pool.pool.instance_type.split('.')[0]
                    if (_target_family_counts.get(_pool_fam, 0) + 1) / max(1, _total_nodes) > 0.40:
                        continue

                pool_vcpu = pool.pool.vcpu
                pool_mem = pool.pool.memory_gb

                # Dynamic Rightsizing check: Does the pool fit the required load?
                # And prevents upscaling to incredibly large nodes if usage is low
                fits_load = (pool_vcpu >= required_vcpu) and (pool_mem >= required_mem)
                not_too_large = (pool_vcpu <= current_vcpu * 2.5) and (pool_mem <= current_mem * 2.5)

                if not (fits_load and not_too_large):
                    continue

                # Risk gate: reject pools above risk ceiling
                if pool.risk_probability > risk_ceiling:
                    continue

                # Price gate: spot price must be below max acceptable
                if pool.pool.spot_price > 0:
                    if pool.pool.spot_price <= max_acceptable_price:
                        chosen_pool = pool
                        break
                else:
                    # No DB price — use ML predicted_savings as proxy (>15% predicted = good)
                    if pool.predicted_savings > 0.15:
                        chosen_pool = pool
                        break

            # Pass 2: Relax price constraint, keep risk ceiling + load fit + diversity
            if chosen_pool is None:
                for pool in top_pools:
                    if pool.pool.instance_type in used_types:
                        continue
                    if _diversify_enabled:
                        _pool_fam = pool.pool.instance_type.split('.')[0]
                        if (_target_family_counts.get(_pool_fam, 0) + 1) / max(1, _total_nodes) > 0.40:
                            continue
                    if pool.risk_probability > risk_ceiling:
                        continue

                    pool_vcpu = pool.pool.vcpu
                    pool_mem = pool.pool.memory_gb

                    if (pool_vcpu >= required_vcpu and pool_mem >= required_mem) and (pool_vcpu <= current_vcpu * 2.5 and pool_mem <= current_mem * 2.5):
                        chosen_pool = pool
                        break

            # NOTE: Pass 3 / Pass 4 removed — they ignored size constraints and caused
            # upsizing (e.g. recommending r5.xlarge for a t3.medium node).
            # If no same-size-or-smaller spot pool fits the constraints, we leave
            # target_type = instance_type (node is already optimal / no suitable spot pool).

            if chosen_pool:
                used_types.add(chosen_pool.pool.instance_type)
                _cf = chosen_pool.pool.instance_type.split('.')[0]
                _target_family_counts[_cf] = _target_family_counts.get(_cf, 0) + 1
                target_type = chosen_pool.pool.instance_type
                target_az = chosen_pool.pool.az
                risk_score = chosen_pool.risk_probability

                # Savings relative to current node's OD price vs target spot price
                if chosen_pool.pool.spot_price > 0 and on_demand_hourly > 0:
                    spot_price_hourly = chosen_pool.pool.spot_price
                    # Savings = (current_OD - target_spot) / current_OD
                    raw_savings = (on_demand_hourly - chosen_pool.pool.spot_price) / on_demand_hourly * 100
                    if raw_savings >= 5:
                        spot_savings_pct = round(raw_savings)
                    else:
                        # Pool isn't cheaper in absolute terms; show its own spot-vs-OD savings
                        spot_savings_pct = round(chosen_pool.predicted_savings * 100)
                else:
                    # No spot price in DB — use ML predicted_savings ratio
                    spot_price_hourly = on_demand_hourly * max(0.1, 1.0 - chosen_pool.predicted_savings)
                    spot_savings_pct = round(chosen_pool.predicted_savings * 100)

        cpu_util = float(node.get("cpu_util") or 0.0)

        # Interruption rate from spot_advisor_rank: 0=<5%, 1=5-10%, 2=10-15%, 3=15-20%, 4=>20%
        INTERRUPTION_LABELS = {0: "<5%", 1: "5–10%", 2: "10–15%", 3: "15–20%", 4: ">20%"}
        try:
            interruption_rank = int(chosen_pool.pool.spot_advisor_rank) if chosen_pool and hasattr(chosen_pool.pool, 'spot_advisor_rank') and chosen_pool.pool.spot_advisor_rank is not None else None
        except Exception:
            interruption_rank = None
        if interruption_rank is not None:
            interruption_rate = INTERRUPTION_LABELS.get(interruption_rank, f"{interruption_rank}")
        else:
            # Estimate from risk_score: 0-0.2 → <5%, 0.2-0.4 → 5-10%, etc.
            if risk_score < 0.2:
                interruption_rate = "<5%"
            elif risk_score < 0.4:
                interruption_rate = "5–10%"
            elif risk_score < 0.6:
                interruption_rate = "10–15%"
            elif risk_score < 0.8:
                interruption_rate = "15–20%"
            else:
                interruption_rate = ">20%"

        recommendations.append({
            "node_name": node_name,
            "current_type": instance_type,
            "current_cost": round(on_demand_hourly, 4),
            "target_type": target_type,
            "target_az": target_az,
            "target_spot_price": round(spot_price_hourly, 4),
            "projected_savings_pct": spot_savings_pct,
            "risk_score": round(risk_score, 3),
            "interruption_rate": interruption_rate,
            "workload_type": workload_type,
            "lifecycle": "spot" if is_already_spot else "on_demand",
            "instance_family": (instance_type or "").split(".")[0],
        })

    # ── Family distribution for diversify visualisation ─────────────────────
    _fam_dist: dict = {}
    for _r in recommendations:
        _fam = _r["instance_family"]
        _fam_dist[_fam] = _fam_dist.get(_fam, 0) + 1
    _total_nodes_dist = max(1, len(recommendations))
    _fam_shares = {
        fam: {"count": cnt, "pct": round(cnt / _total_nodes_dist * 100)}
        for fam, cnt in _fam_dist.items()
    }

    # ── S2S candidate detection ──────────────────────────────────────────────
    # Mark SPOT nodes that would trigger a SPOT→SPOT rebalancing action:
    #   diversify: family share > 40% when diversify_pools=ON
    #   risk:      node's pool risk > 0.4 (no current active ranking available here,
    #              so we use risk_score from the chosen pool as proxy)
    for _r in recommendations:
        _s2s_trigger = None
        if _r["lifecycle"] == "spot":
            if _diversify_enabled:
                _fam = _r["instance_family"]
                _share = _fam_dist.get(_fam, 0) / _total_nodes_dist
                if _share > 0.40:
                    _s2s_trigger = f"diversify: {_fam} at {round(_share * 100)}% (cap 40%)"
            if not _s2s_trigger and _r["risk_score"] > 0.4:
                _s2s_trigger = f"risk: score {_r['risk_score']:.2f} > 0.40 threshold"
        _r["s2s_candidate"] = _s2s_trigger is not None
        _r["s2s_trigger"] = _s2s_trigger

    return {
        "recommendations": recommendations,
        "eligible_pools_count": eligible_pools_count,
        "family_distribution": _fam_shares,
        "diversify_enabled": _diversify_enabled,
    }


@router.get("/clusters/{cluster_id}/impact")
async def get_cluster_impact(
    cluster_id: str,
    db: Session = Depends(get_db),
):
    """
    Cluster impact projection: savings vs risk if all recommendations applied.
    Before/after spot ratio, estimated monthly savings.
    """
    from backend.models.cluster import Cluster
    from backend.models.instance import Instance

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    from backend.services.dynamic_instance_helpers import bulk_get_hourly_prices
    from backend.core.redis_client import get_redis_client

    instances = db.query(Instance).filter(Instance.cluster_id == cluster_id).all()

    _impact_nodes = [
        {
            "instance_type": (i.instance_type or "m5.large"),
            "az": i.az or f"{cluster.region or 'ap-south-1'}a",
            "lifecycle": (i.lifecycle.value if hasattr(i.lifecycle, 'value') else str(i.lifecycle or 'on-demand')).lower(),
            "risk_score": float(i.risk_score) if getattr(i, 'risk_score', None) else 0.25,
        }
        for i in instances
    ]

    total = len(_impact_nodes)

    # Dynamically fetch on-demand pricing (AWS API → DB → hardcoded fallback)
    _all_impact_types = list({n["instance_type"] for n in _impact_nodes})
    redis = get_redis_client()
    INSTANCE_HOURLY = bulk_get_hourly_prices(db, redis, _all_impact_types, cluster.region or 'ap-south-1')

    # Helper: reliably detect SPOT lifecycle regardless of enum vs string
    def _is_spot_lifecycle(inst) -> bool:
        lc = inst.lifecycle
        lc_str = (lc.value if hasattr(lc, 'value') else str(lc or '')).lower()
        return 'spot' in lc_str

    # Group instances by (instance_type, az) pools
    from collections import defaultdict
    pool_groups = defaultdict(list)
    az_counts: dict = defaultdict(int)
    family_counts: dict = defaultdict(int)
    spot_count = 0
    on_demand_count = 0

    for node in _impact_nodes:
        itype = node["instance_type"]
        az = node["az"]
        pool_key = f"{itype} ({az})"
        pool_groups[pool_key].append(node)
        az_counts[az] += 1
        family = itype.split('.')[0] if '.' in itype else itype
        family_counts[family] += 1
        if 'spot' in node["lifecycle"]:
            spot_count += 1
        else:
            on_demand_count += 1

    pools = []
    for pool_key, pool_instances in pool_groups.items():
        on_demand_instances = [i for i in pool_instances if 'spot' not in i["lifecycle"]]
        eligible_count = len(on_demand_instances)
        spot_in_pool = len(pool_instances) - eligible_count

        rep_type = pool_instances[0]["instance_type"]
        hourly_rate = INSTANCE_HOURLY.get(rep_type, 0.096)
        spot_rate = hourly_rate * 0.35  # spot ~65% off
        avg_savings_monthly = round((hourly_rate - spot_rate) * 730, 2)
        total_savings_monthly = round(avg_savings_monthly * eligible_count, 2)

        avg_risk = sum(i.get("risk_score", 0.25) or 0.25 for i in pool_instances) / len(pool_instances)
        is_flagged = avg_risk > 0.55

        cluster_usage_pct = round((len(pool_instances) / total * 100), 1) if total else 0

        pools.append({
            "target_pool": pool_key,
            "eligible_nodes": eligible_count,
            "spot_nodes": spot_in_pool,
            "avg_savings": avg_savings_monthly,
            "total_savings": total_savings_monthly,
            "avg_risk": round(avg_risk, 3),
            "is_flagged": is_flagged,
            "cluster_usage_pct": cluster_usage_pct,
        })

    # Build chart datasets
    az_distribution = [{"az": k, "count": v} for k, v in sorted(az_counts.items())]
    family_distribution = [{"family": k, "count": v} for k, v in sorted(family_counts.items(), key=lambda x: -x[1])]
    spot_ratio = round(spot_count / total * 100) if total > 0 else 0

    return {
        "pools": pools,
        "az_distribution": az_distribution,
        "family_distribution": family_distribution,
        "spot_ratio": spot_ratio,
        "spot_count": spot_count,
        "on_demand_count": on_demand_count,
        "total_nodes": total,
    }


# ── Rebalancing Context ────────────────────────────────────────────────────────
# Unified endpoint that returns:
#  1. Active cooldown (both explicit Redis key AND 10-min post-rebalance window)
#  2. Next ON_DEMAND node to be rebalanced (estimated savings included)
# Used by RebalancingTimeline metadata bar.

@router.get("/v3/rebalancing-context/{cluster_id}")
async def get_rebalancing_context(
    cluster_id: str,
    db: Session = Depends(get_db),
):
    """
    Returns the current rebalancing context for the timeline metadata bar:
    - cooldown: { active, remaining_seconds, reason }
    - next_target: { node, instance_id, instance_type, monthly_savings } or null
    """
    from backend.models.cluster import Cluster
    from backend.models.instance import Instance, InstanceLifecycle
    from backend.models.rebalancing_action import RebalancingAction

    _POST_REBALANCE_COOLDOWN_S = 600  # 10 minutes between rebalances

    try:
        redis = get_redis_client()

        # ── 1. Cooldown detection ──────────────────────────────────────────────
        cooldown_active = False
        remaining_seconds = 0
        cooldown_reason = None

        # Check explicit emergency/manual cooldown key
        try:
            from backend.core.redis_client import key_cluster_cooldown
            _ck = key_cluster_cooldown(cluster_id)
            _ttl = redis.ttl(_ck)
            if _ttl and _ttl > 0:
                cooldown_active = True
                remaining_seconds = int(_ttl)
                cooldown_reason = "cluster_cooldown"
        except Exception:
            pass

        # Check post-rebalance 10-min window (last completed action)
        if not cooldown_active:
            try:
                _last = (
                    db.query(RebalancingAction)
                    .filter(
                        RebalancingAction.cluster_id == cluster_id,
                        RebalancingAction.status == "completed",
                        RebalancingAction.completed_at.isnot(None),
                    )
                    .order_by(RebalancingAction.completed_at.desc())
                    .first()
                )
                if _last and _last.completed_at:
                    _elapsed = (datetime.utcnow() - _last.completed_at).total_seconds()
                    if _elapsed < _POST_REBALANCE_COOLDOWN_S:
                        cooldown_active = True
                        remaining_seconds = int(_POST_REBALANCE_COOLDOWN_S - _elapsed)
                        cooldown_reason = "post_rebalance"
            except Exception:
                pass

        # ── 2. Next target node ────────────────────────────────────────────────
        next_target = None
        try:
            # Get all running ON_DEMAND instances not in per-instance cooldown
            _od_instances = (
                db.query(Instance)
                .filter(
                    Instance.cluster_id == cluster_id,
                    Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
                    Instance.state == "running",
                )
                .all()
            )

            # Filter out instances already rebalanced (24h Redis cooldown)
            for _inst in _od_instances:
                if not _inst.instance_id:
                    continue
                _inst_key = f"spot:rebalanced:instance:{_inst.instance_id}"
                if redis and redis.exists(_inst_key):
                    continue  # in cooldown — skip

                # Also skip placeholders (ip- IDs from Redis seed that have node_name = instance_id)
                # but DO show them if that's the only thing available
                _is_real_ec2 = _inst.instance_id.startswith("i-")
                _display_name = (
                    _inst.node_name.split(".")[0]
                    if _inst.node_name
                    else _inst.instance_id
                )

                # Estimate monthly savings (OD → spot price difference, rough)
                _OD_PRICE = {
                    "t3.micro": 10, "t3.small": 19, "t3.medium": 38, "t3.large": 76,
                    "t3.xlarge": 150, "t3.2xlarge": 300,
                    "m5.large": 88, "m5.xlarge": 175, "m5.2xlarge": 350,
                    "c5.large": 76, "c5.xlarge": 152, "c5.2xlarge": 305,
                    "c6i.large": 80, "c6i.xlarge": 160, "c6i.2xlarge": 320,
                }
                _od_monthly = _OD_PRICE.get(_inst.instance_type or "", 50)
                _spot_discount = 0.65  # ~35% average spot savings
                _monthly_savings = round(_od_monthly * _spot_discount, 1)

                next_target = {
                    "node": _display_name,
                    "instance_id": _inst.instance_id,
                    "instance_type": _inst.instance_type or "unknown",
                    "monthly_savings": _monthly_savings,
                }
                break  # take the first eligible node
        except Exception as _nt_err:
            logger.warning(f"[rebalancing-context] Next target query failed: {_nt_err}")

        return {
            "cluster_id": cluster_id,
            "cooldown": {
                "active": cooldown_active,
                "remaining_seconds": remaining_seconds,
                "reason": cooldown_reason,
            },
            "next_target": next_target,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"[rebalancing-context] Failed for {cluster_id}: {e}")
        return {
            "cluster_id": cluster_id,
            "cooldown": {"active": False, "remaining_seconds": 0, "reason": None},
            "next_target": None,
            "timestamp": datetime.utcnow().isoformat(),
        }
