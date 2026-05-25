"""
ASCPAi API Routes - Pool Selection & Termination Monitoring

Endpoints:
- GET /api/v1/ascpai/pools/rankings - Get ranked pools
- POST /api/v1/ascpai/node-templates - Create node filtering template
- GET /api/v1/ascpai/blacklist - Get globally flagged risky pools
- GET /api/v1/ascpai/rebalancing/status - Get rebalancing actions status
"""

import json as _json
import math
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

router = APIRouter(prefix="/ascpai", tags=["ASCPAi"])


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
    cost_estimate: float  # Estimated daily spot cost (spot_price × 24 hours)
    ml_score: float  # Composite: (savings × 0.4) - (risk × 0.6)
    rank: int
    is_flagged: bool  # Flagged by global blacklist
    spot_advisor_rank: int  # 0-5 (AWS interruption frequency)
    timestamp: str
    blacklisted: bool = False  # Temporarily blacklisted due to launch failures / terminations
    price_shock: bool = False  # Detected rapid spot price spike (>30% in 1h)
    # C10: Global pool risk visibility
    risk_source: str = "local"                  # "local" | "blend" | "global"
    global_itn_breadth: int = 0                 # distinct clusters affected in last 24 h
    global_itn_severity: Optional[str] = None   # worst event type in ledger; None if no history
    global_confidence: float = 0.0              # how much data backs the score [0, 1]


class BlacklistedPoolResponse(BaseModel):
    """Globally flagged risky pool."""
    instance_type: str
    az: str
    flagged_at: str
    ttl_remaining_seconds: int
    reason: str  # "termination_detected" or "high_interruption_rate"


class RebalancingStatusResponse(BaseModel):
    """Rebalancing action status with step timeline."""
    id: int
    cluster_id: str
    status: str  # "in_progress", "waiting_agent", "completed", "failed"
    trigger: str  # "emergency" or "graceful" or "auto_rebalance"
    source_pool: Optional[str]  # instance_type:az
    target_pool: Optional[str]  # instance_type:az (None for deferred/failed actions)
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
    step_7_pods_rescheduled: Optional[str]       # ISO timestamp when evicted pods confirmed rescheduled
    node_name: Optional[str]                  # K8s node name of the source node
    instance_id: Optional[str]               # EC2 instance ID being migrated
    provisioner_type: Optional[str]          # 'karpenter' or 'agent' (direct EC2)
    original_target_pool: Optional[str]      # Planned pool before capacity fallback
    pool_change_reason: Optional[str]        # Why the pool changed (e.g. InsufficientInstanceCapacity)
    replacement_spot_instance_id: Optional[str]  # EC2 ID of the new spot node launched as replacement
    # Actual instance type / AZ Karpenter provisioned (may differ from target)
    actual_instance_type: Optional[str]
    actual_az: Optional[str]
    # Realized savings from this migration
    realized_savings_hr: Optional[float]
    realized_savings_mo: Optional[float]
    # Verification flags — True when backend confirmed the step via read-back
    step_1_verified: Optional[bool]
    step_2_verified: Optional[bool]
    step_3_verified: Optional[bool]
    step_4_verified: Optional[bool]
    step_5_verified: Optional[bool]
    step_7_verified: Optional[bool]
    # Engine that created this action: 'karpenter' | 'agent' | 'consolidation'
    # Used by the UI to label groups as "Node Rebalancing" vs "Node Consolidation"
    engine_source: Optional[str]


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

    # Resolve effective architecture (intersection of cluster preference + template)
    _arch_pref = getattr(automation, 'architecture_preference', 'both') if automation else 'both'
    _template_archs = None
    _arch_conflict = False
    if active_mapping and active_mapping.version and active_mapping.version.constraints_json:
        _tc = active_mapping.version.constraints_json
        if isinstance(_tc, dict) and 'architecture' in _tc:
            _template_archs = _tc['architecture']  # e.g. ["amd64", "arm64"]

    # Compute resolved architecture
    if _arch_pref in ('amd64', 'arm64') and _template_archs:
        # Normalize: treat x86_64 as amd64 equivalent
        _normalized = set()
        for a in _template_archs:
            _normalized.add(a)
            if a == 'x86_64':
                _normalized.add('amd64')
            elif a == 'amd64':
                _normalized.add('x86_64')
        if _arch_pref not in _normalized:
            _arch_conflict = True
            _resolved_arch = _arch_pref  # User setting wins but flag conflict
        else:
            _resolved_arch = _arch_pref
    elif _arch_pref in ('amd64', 'arm64'):
        _resolved_arch = _arch_pref
    elif _template_archs and len(_template_archs) == 1:
        _a = _template_archs[0]
        _resolved_arch = 'amd64' if _a in ('amd64', 'x86_64') else _a
    else:
        _resolved_arch = 'both'

    # Build effective config unifying the override hierarchy (Cluster Policy > Template > Strategy)
    config = {
        "auto_rebalance": "ON" if (automation and automation.auto_rebalance_enabled) else "OFF",
        "auto_rightsizing": "ON" if (automation and automation.auto_rightsizing_enabled) else "OFF",
        "strategy": (strategy.strategy_type or 'balanced').capitalize() if strategy else "Balanced",
        "template": template_name,
        "stateful_spot": "BLOCKED" if (stateful and stateful.block_spot_for_stateful) else "ALLOWED",
        "substitute_mode": (stateless.substitute_strategy or 'prewarmed').capitalize() if stateless else "Prewarmed",
        "target_spot_exposure_pct": automation.target_spot_exposure_pct if automation else 100,
        "architecture_preference": _arch_pref,
        "resolved_architecture": _resolved_arch,
        "template_architectures": _template_archs,
        "architecture_conflict": _arch_conflict,
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
    node_id: Optional[str] = Query(None, description="EC2 instance ID of source node; enables pod-request-based capacity floor"),
    db: Session = Depends(get_db)
):
    """
    Get ranked instance pools using ASCPAi 8-step pipeline.

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

        # ── Enforce minimum floor at current instance type's specs ────────
        # When current_instance_type is provided, raise vcpu_min / memory_gb_min
        # so that no pool smaller than the source node can appear in the list.
        # e.g. t3.medium = 2 vCPU / 4 GB → t2.micro (1 vCPU / 1 GB) is excluded.
        if current_instance_type:
            try:
                from backend.workers.tasks.cache_builder import (
                    _lookup_specs as _cb_lookup_specs_r,
                )
                _cur_vcpu, _cur_mem, _, _ = _cb_lookup_specs_r(current_instance_type)
                _cur_vcpu = _cur_vcpu or 2
                _cur_mem = _cur_mem or 4.0
                _new_vcpu_min = max(node_template.vcpu_range[0], _cur_vcpu)
                _new_mem_min = max(node_template.memory_range[0], _cur_mem)
                node_template = NodeTemplate(
                    architecture=node_template.architecture,
                    vcpu_range=(_new_vcpu_min, node_template.vcpu_range[1]),
                    memory_range=(_new_mem_min, node_template.memory_range[1]),
                    allowed_families=node_template.allowed_families,
                    allowed_sizes=node_template.allowed_sizes,
                    allowed_azs=node_template.allowed_azs,
                    excluded_instance_types=node_template.excluded_instance_types,
                )
            except Exception:
                pass  # Non-fatal — fall back to original template ranges

        # Execute pool ranking pipeline
        ranking_service = PoolRankingService(db, redis)
        ranked_pools = ranking_service.rank_pools(node_template, region, limit, node_id=node_id)

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
                # C10: global pool risk visibility
                risk_source=getattr(scored_pool, 'risk_source', 'local'),
                global_itn_breadth=getattr(scored_pool, 'global_itn_breadth', 0),
                global_itn_severity=getattr(scored_pool, 'global_itn_severity', None),
                global_confidence=getattr(scored_pool, 'global_confidence', 0.0),
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
    import json

    try:
        # Issue 16 fix: use shared connection pool instead of creating a new connection
        r = get_redis_client()
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

            # Defensive backfill: if the action is completed/failed but
            # step_6 or current_step were never written (e.g. prior DB
            # session corruption), fill them from completed_at so the
            # frontend timeline renders correctly.
            _completed_iso = action.completed_at.isoformat() if action.completed_at else None
            if action.status == 'completed':
                if not _meta.get('step_6_optimization_complete') and _completed_iso:
                    _meta['step_6_optimization_complete'] = _completed_iso
                if not _meta.get('step_5_old_node_terminated') and _completed_iso:
                    _meta['step_5_old_node_terminated'] = _completed_iso
                if _meta.get('current_step') != 'optimization_complete':
                    _meta['current_step'] = 'optimization_complete'

            response.append(RebalancingStatusResponse(
                id=action.id,
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
                step_7_pods_rescheduled=_meta.get("step_7_pods_rescheduled"),
                node_name=(
                    _meta.get("node_name")
                    or _meta.get("target_node_name")
                    or _meta.get("source_node_name")
                ),
                instance_id=_meta.get("instance_id"),
                provisioner_type=_meta.get("provisioner_type"),
                original_target_pool=_meta.get("original_target_pool"),
                pool_change_reason=_meta.get("pool_change_reason"),
                replacement_spot_instance_id=_meta.get("replacement_spot_instance_id"),
                actual_instance_type=action.actual_instance_type,
                actual_az=action.actual_az,
                realized_savings_hr=action.realized_savings_hr if hasattr(action, 'realized_savings_hr') else None,
                realized_savings_mo=action.realized_savings_mo if hasattr(action, 'realized_savings_mo') else None,
                step_1_verified=_meta.get("step_1_verified", True if _meta.get("karpenter_nodepool_updated") else None),
                step_2_verified=_meta.get("step_2_cordon_verified"),
                step_3_verified=_meta.get("step_3_draining_pods_verified"),
                step_4_verified=_meta.get("step_4_verified", True if _meta.get("step_4_new_node_joined") else None),
                step_5_verified=_meta.get("step_5_verified"),
                step_7_verified=_meta.get("step_7_verified"),
                engine_source=(
                    "consolidation" if getattr(action, "source", "auto_rebalancer") == "placement_controller"
                    else _meta.get("provisioner_type") or "karpenter"
                ),
            ))

        return response

    except Exception as e:
        logger.error(f"Failed to get rebalancing status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get rebalancing status: {str(e)}")


@router.post("/rebalancing-actions/{action_id}/approve")
def approve_rebalancing_action(
    action_id: int,
    db: Session = Depends(get_db),
):
    """
    Approve a pending_approval rebalancing action so it executes on the next
    auto-rebalancer cycle.  Used when manual_approval_required=True on the cluster.
    """
    action = db.query(RebalancingAction).filter(RebalancingAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Rebalancing action not found")
    if action.status != "pending_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Action is '{action.status}', not 'pending_approval' — nothing to approve"
        )
    meta = dict(action.action_metadata or {})
    meta["approved_at"] = datetime.utcnow().isoformat()
    action.status = "in_progress"
    action.action_metadata = meta
    db.commit()
    logger.info(f"[approve] Rebalancing action {action_id} approved → in_progress")
    return {"status": "approved", "action_id": action_id}


@router.post("/rebalancing-actions/{action_id}/deny")
def deny_rebalancing_action(
    action_id: int,
    db: Session = Depends(get_db),
):
    """
    Deny (cancel) a pending_approval rebalancing action without executing it.
    """
    action = db.query(RebalancingAction).filter(RebalancingAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Rebalancing action not found")
    if action.status != "pending_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Action is '{action.status}', not 'pending_approval' — nothing to deny"
        )
    meta = dict(action.action_metadata or {})
    meta["denied_at"] = datetime.utcnow().isoformat()
    action.status = "failed"
    action.error_message = "Denied by user (manual_approval_required)"
    action.completed_at = datetime.utcnow()
    action.action_metadata = meta
    db.commit()
    logger.info(f"[deny] Rebalancing action {action_id} denied → failed")
    return {"status": "denied", "action_id": action_id}


@router.post("/rebalancing-actions/{action_id}/force-complete")
def force_complete_rebalancing_action(
    action_id: int,
    db: Session = Depends(get_db),
):
    """
    Fix 17: Force-complete a stuck rebalancing action.
    Sets status to 'completed' and cleans up associated resources.
    Use when an action is stuck in waiting_agent/in_progress and manual
    investigation confirms the replacement is healthy or the action is stale.
    """
    action = db.query(RebalancingAction).filter(RebalancingAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Rebalancing action not found")
    if action.status in ('completed', 'failed'):
        raise HTTPException(
            status_code=400,
            detail=f"Action is already '{action.status}' — cannot force-complete"
        )
    meta = dict(action.action_metadata or {})
    meta["force_completed_at"] = datetime.utcnow().isoformat()
    meta["force_completed_reason"] = "Manual override via API"
    meta["current_step"] = "completed"
    action.status = "completed"
    action.completed_at = datetime.utcnow()
    action.duration_seconds = int(
        (action.completed_at - action.started_at).total_seconds()
    ) if action.started_at else 0
    action.action_metadata = meta

    # Clean up resources (locks, trigger pods, semaphores)
    try:
        from backend.core.redis_client import get_redis_client
        _redis = get_redis_client()
        from backend.workers.tasks.auto_rebalancer import _cleanup_rebalancing_resources
        _cleanup_rebalancing_resources(action, meta, _redis, db)
    except Exception as _cleanup_err:
        logger.warning(f"[force-complete] Resource cleanup failed: {_cleanup_err}")

    db.commit()
    logger.info(f"[force-complete] Rebalancing action {action_id} force-completed")
    return {"status": "force_completed", "action_id": action_id}


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


class SavingsVelocityDataPoint(BaseModel):
    date: str  # "MMM DD" format, e.g., "OCT 1"
    amount: float

class SavingsVelocityResponse(BaseModel):
    last_30_days_total: float
    data_points: List[SavingsVelocityDataPoint]

@router.get("/savings-velocity", response_model=SavingsVelocityResponse)
async def get_savings_velocity(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster ID"),
    days: int = Query(30, description="Analysis window in days"),
    db: Session = Depends(get_db)
):
    """
    Get savings velocity chart data for the last N days.
    
    This computes a cumulative savings curve or daily savings 
    based on realized savings and successful rebalancing actions.
    """
    try:
        from backend.models.cluster import Cluster
        
        # Calculate trailing 30 days starting from today
        today = datetime.utcnow().date()
        cutoff_date = today - timedelta(days=days-1)  # Include today in the N days
        
        # We need sum of realized_savings_monthly across clusters
        # Quick & dirty daily estimation: Realized monthly savings / 30 * days elapsed
        # For a truly realistic chart, we look at RebalancingAction history
        # and accumulate savings over time, but tracking total daily cost reduction
        # requires snapshotting. Since we just have `realized_savings_monthly` now, 
        # let's generate a growth curve that ends at `total_monthly_savings`.
        
        # Get baseline total monthly savings
        query = db.query(Cluster.realized_savings_monthly)
        if cluster_id:
            query = query.filter(Cluster.id == cluster_id)
        
        clusters = query.all()
        total_monthly_savings = sum([c.realized_savings_monthly for c in clusters if c.realized_savings_monthly])
        
        # Let's see if we have any successful rebalancing actions to make the curve dynamic
        # query rebalancing actions mapped to days
        event_query = db.query(
            func.date(RebalancingAction.completed_at).label('date'),
            func.count(RebalancingAction.id).label('action_count')
        ).filter(
            RebalancingAction.status == 'completed',
            RebalancingAction.completed_at >= cutoff_date
        )
        if cluster_id:
            event_query = event_query.filter(RebalancingAction.cluster_id == cluster_id)
            
        action_counts = event_query.group_by(func.date(RebalancingAction.completed_at)).all()
        action_map = {row.date: row.action_count for row in action_counts}
        
        # Generate the daily data points
        # If there are no actions, just make a smooth linear progression
        # ending at the current monthly pace.
        points = []
        cumulative = 0.0
        
        # Base daily rate (if smooth)
        daily_rate = total_monthly_savings / 30.0
        
        for i in range(days):
            current_date = cutoff_date + timedelta(days=i)
            
            # Add some variability based on actions, but basically trend up
            actions_today = action_map.get(current_date, 0)
            
            # Exact linear projection based on real calculated realized savings
            if total_monthly_savings > 0:
                day_val = daily_rate
            else:
                day_val = 0.0
                
            cumulative += day_val
            
            date_str = current_date.strftime("%b %-d").upper() # e.g. "OCT 1"
            points.append(SavingsVelocityDataPoint(
                date=date_str,
                amount=round(cumulative, 2)
            ))
            
        # Normalize the curve so the final point matches the exact expected proportion of total savings
        if len(points) > 0 and points[-1].amount > 0 and total_monthly_savings > 0:
            # Scale the curve so the end point is roughly proportional to the total monthly savings (last 30 days absolute value)
            target_end_value = total_monthly_savings * (days / 30.0)
            scale = target_end_value / points[-1].amount
            for pt in points:
                pt.amount = round(pt.amount * scale, 2)
            final_total = round(target_end_value, 2)
        else:
            final_total = 0.0

        return SavingsVelocityResponse(
            last_30_days_total=final_total,
            data_points=points
        )

    except Exception as e:
        logger.error(f"Failed to get savings velocity: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get savings velocity: {str(e)}")


@router.get("/health")
async def health_check():
    """
    Health check endpoint for ASCPAi system.
    
    Reports ML pipeline status including circuit breaker state.
    Operators should monitor `ml_status` — if "degraded", fallback scoring
    is active and rankings may be less accurate.
    """
    try:
        redis = get_redis_client()
        ml_degraded = redis.get("ascpai:ml_degraded")
        ml_fail_count = int(redis.get("ascpai:ml_fail_count") or 0)
        is_degraded = ml_degraded == b"true" or ml_degraded == "true"
    except Exception:
        is_degraded = False
        ml_fail_count = 0

    return {
        "status": "degraded" if is_degraded else "healthy",
        "service": "ASCPAi Pool Selection & Termination Monitoring",
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
    use_rightsized: bool = Query(False, description="When true, substitute right-sizing recommended values into the bin-packing simulation"),
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
    from sqlalchemy import or_

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    region = getattr(cluster, 'region', None) or 'ap-south-1'

    # Only running instances; deduplicate by K8s node hostname so that
    # real EC2 records (i-xxxx) and daemon-set placeholders (ip-xxx-xxx)
    # for the same physical node are collapsed to one entry.
    # Exclude instances with no instance_type (orphan/ghost records that never joined EKS).
    # NOTE: notin_() excludes NULL rows in SQL, so we use or_(..., is_(None))
    # to keep instances whose status hasn't been set yet (nullable column).
    _all_instances = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.state == 'running',
        Instance.instance_type.isnot(None),
        Instance.instance_type != '',
        Instance.instance_type != 'unknown',
        Instance.instance_id.isnot(None),
        Instance.instance_id != '',
        or_(Instance.status.in_(['READY', 'CALIBRATING']), Instance.status.is_(None)),
    ).all()

    # Prefer agent-reported instances (node_name set, account_id=NULL — ground truth from K8s)
    # over EC2 discovery records (no node_name, account_id set — may duplicate real nodes).
    # When the in-cluster agent is active its records are authoritative; only fall back to
    # all discovery records when no agent instances exist at all.
    _agent_instances = [i for i in _all_instances if i.node_name]
    if _agent_instances:
        _all_instances = _agent_instances

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

    # ── Build candidate pools from market_view_cache (REAL AWS spot prices) ──
    # market_view_cache is built by cache_builder.py (hourly) from live spot_price:* Redis keys.
    # This is the single source of truth for pool prices — no DB or global_pool_rankings fallback.
    import json as _mv_json

    class _PoolInfo:
        __slots__ = ['instance_type', 'az', 'vcpu', 'memory_gb', 'architecture', 'spot_price']
        def __init__(self, d):
            self.instance_type = d['instance_type']
            self.az = d['az']
            self.vcpu = int(d.get('vcpu', 2) or 2)
            self.memory_gb = float(d.get('memory_gb', 4.0) or 4.0)
            self.architecture = d.get('architecture', 'amd64') or 'amd64'
            self.spot_price = float(d.get('spot_price', 0) or 0)

    class _ScoredPoolWrapper:
        __slots__ = ['pool', 'risk_probability', 'predicted_savings', 'interruption_rate_pct']
        def __init__(self, d):
            self.pool = _PoolInfo(d)
            # Prefer ONNX-blended risk_probability when available (from cache_builder ONNX pass),
            # fall back to interruption_rate_pct → risk scale for non-ONNX pools
            if d.get('risk_probability') is not None and d.get('risk_probability') != 0.20:
                self.risk_probability = float(d['risk_probability'])
            else:
                self.risk_probability = float(d.get('interruption_rate_pct', 5) or 5) / 100.0
            # Raw AWS interruption bucket (for display label — NOT for risk filtering)
            self.interruption_rate_pct = float(d.get('interruption_rate_pct', 10) or 10)
            # predicted_savings: prefer explicit field, fall back to savings_pct/100
            self.predicted_savings = float(
                d.get('predicted_savings') or (d.get('savings_pct', 0) / 100.0)
            )

    top_pools: list = []
    _mv_spot_prices: dict = {}  # (instance_type, az) -> spot_price
    _mv_pool_meta: dict = {}    # instance_type -> {vcpu, memory_gb, architecture}

    try:
        from backend.core.redis_client import key_market_view_cache
        _mv_raw = redis.get(key_market_view_cache(region))
        if _mv_raw:
            _mv_data = _mv_json.loads(_mv_raw).get('data', [])
            for _p in _mv_data:
                _itype = _p.get('instance_type', '')
                _az = _p.get('az', '')
                _sp = float(_p.get('spot_price', 0) or 0)
                if _sp > 0:
                    _mv_spot_prices[(_itype, _az)] = _sp
                    _mv_pool_meta[_itype] = {
                        'vcpu': int(_p.get('vcpu', 2) or 2),
                        'memory_gb': float(_p.get('memory_gb', 4.0) or 4.0),
                        'architecture': _p.get('architecture', 'amd64') or 'amd64',
                    }
                    top_pools.append(_ScoredPoolWrapper(_p))
            logger.debug(f"node-recommendations: loaded {len(top_pools)} pools from market_view_cache:{region}")
        else:
            logger.warning(f"node-recommendations: market_view_cache:{region} not found — no pool candidates")
    except Exception as _mv_err:
        logger.warning(f"node-recommendations: market_view_cache load failed: {_mv_err}")

    # ── Supplement: direct Redis lookup for same-type pools not in top-500 cache ──
    # For each current instance type in the cluster, fetch real spot prices from
    # spot_price:{region}:{az}:{type} keys so same-type recommendations always work.
    _known_in_cache = set(itype for (itype, _) in _mv_spot_prices.keys())
    for _cur_itype in _all_instance_types:
        if _cur_itype in _known_in_cache:
            continue  # Already in market_view_cache — no supplemental lookup needed
        # Scan all AZs for this instance type
        _vcpu_fb = VCPU_COUNT.get(_cur_itype, 2)
        _mem_fb = MEM_GB_MAP.get(_cur_itype, 4.0)
        _family = _cur_itype.split('.')[0]
        _arch_fb = 'arm64' if (_family.endswith('g') or _family == 'a1') else 'amd64'
        _supplemental_added = False
        for _az_suffix in ['a', 'b', 'c']:
            _az_name = f"{region}{_az_suffix}"
            _raw_sp = redis.get(f"spot_price:{region}:{_az_name}:{_cur_itype}")
            if not _raw_sp:
                continue
            try:
                _sp_parsed = _mv_json.loads(_raw_sp)
                _sp_val = float(_sp_parsed.get('price', 0) or 0)
            except Exception:
                continue
            if _sp_val <= 0:
                continue
            # Build a synthetic pool entry from Redis spot price + OD price
            _od_val = float(INSTANCE_HOURLY.get(_cur_itype, 0) or 0)
            _sav_pct = (((_od_val - _sp_val) / _od_val) * 100) if _od_val > 0 else 0
            _synthetic = {
                'instance_type': _cur_itype, 'az': _az_name,
                'vcpu': _vcpu_fb, 'memory_gb': _mem_fb, 'architecture': _arch_fb,
                'spot_price': _sp_val, 'ondemand_price': _od_val,
                'savings_pct': round(_sav_pct, 1), 'predicted_savings': round(_sav_pct / 100, 4),
                'interruption_rate_pct': 5.0,  # conservative default for unlisted types
            }
            top_pools.append(_ScoredPoolWrapper(_synthetic))
            _mv_spot_prices[(_cur_itype, _az_name)] = _sp_val
            _mv_pool_meta[_cur_itype] = {'vcpu': _vcpu_fb, 'memory_gb': _mem_fb, 'architecture': _arch_fb}
            _supplemental_added = True
        if _supplemental_added:
            logger.debug(f"node-recommendations: supplemented {_cur_itype} spot prices from Redis (not in market_view_cache)")

    # Total eligible pools after filter (used by UI summary card)
    eligible_pools_count = len(top_pools)


    # ── Load cluster strategy for risk/savings tradeoff ────────────────────
    from backend.models.cluster import OptimizationStrategy
    strategy = cluster.optimization_strategy_profile
    risk_tradeoff_pct = (strategy.risk_savings_tradeoff_pct if strategy else 20) or 20
    risk_ceiling = ((strategy.risk_ceiling_percent if strategy else 25) or 25) / 100.0

    # ── Dynamic risk ceiling: apply regional market factor (same as auto_rebalancer) ──
    _dynamic_risk_ceiling = risk_ceiling
    try:
        _mf_raw = redis.get(f"market_factor:{region}")
        if _mf_raw:
            _dynamic_risk_ceiling = risk_ceiling * float(_mf_raw)
    except Exception:
        pass

    # ── Load diversify_pools + architecture_preference settings ────────────────
    opt = cluster.optimization_settings
    _diversify_enabled = bool(getattr(opt, 'diversify_pools', False)) if opt else False
    _arch_pref = getattr(opt, 'architecture_preference', 'both') or 'both' if opt else 'both'
    # Instance type diversification: 100% = each node must have a unique type;
    # lower % allows more nodes to share the same type (across different AZs).
    _inst_type_div_pct = int(getattr(opt, 'instance_type_diversification_pct', 100) or 100) if opt else 100

    # ── Build occupied pools set for diversification ──────────────────────
    # When diversify is ON, we avoid recommending instance_type:az combos
    # already running in the cluster. This makes the table's Target Pool
    # truly diverse — maximizing savings while not doubling up on pools.
    _occupied_pools = set()   # (instance_type, az) already running in cluster
    _occupied_types = set()   # instance_type already running in cluster
    if _diversify_enabled:
        try:
            _running_for_occ = db.query(Instance.instance_type, Instance.az).filter(
                Instance.cluster_id == cluster_id,
                Instance.state == 'running',
                Instance.instance_type.isnot(None),
            ).all()
            _occupied_pools = {
                (r.instance_type, r.az) for r in _running_for_occ if r.instance_type and r.az
            }
            _occupied_types = {r.instance_type for r in _running_for_occ if r.instance_type}
        except Exception:
            pass

    # ── Sort pools risk-first (lowest risk → highest), savings as tiebreaker ──
    if top_pools:
        top_pools.sort(key=lambda p: (p.risk_probability, -p.predicted_savings))

    # ── Get cached workload classification (stateless vs stateful) ────────
    inspector = WorkloadInspector(redis)
    node_classification = inspector.get_cached_classification(cluster_id) or {}

    recommendations = []
    used_pools = set()  # (instance_type, az) already assigned — prevent two nodes landing on the same pool
    _pool_counts: dict = {}  # (instance_type, az) → count of nodes already assigned to that pool

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
            # K8s health: READY=in cluster, UNKNOWN=EC2 alive but K8s node gone (orphaned)
            "node_health_status": getattr(inst, 'status', None) or 'READY',
        }
        for inst in instances
    ]

    # ── Active migration awareness ─────────────────────────────────────────
    # Find active rebalancing actions for this cluster. Replacement instances
    # are NOT shown as separate nodes — they are part of the migration.
    # Source nodes are marked with migration_info so the UI shows "Migrating".
    _active_replacement_ids = set()  # instance IDs of active replacements (hide from node list)
    _migration_map = {}  # source_instance_id → {replacement_id, replacement_type, action_id}
    try:
        from backend.models.rebalancing_action import RebalancingAction as _RA_mig
        from sqlalchemy import or_ as _or_mig, and_ as _and_mig
        from datetime import timedelta as _td_mig
        # Include actively-running actions AND recently-failed drain actions where the source
        # EC2 is still alive (current_step='failed_drain_ec2_protected').  These nodes are
        # pending a rebalancer retry and must NOT be shown as "Ready" in the UI.
        # Bug fix: drain-retry must also be recent (< 30 min) AND status='failed',
        # otherwise ancient failed actions match current nodes by source_pool fallback.
        _drain_retry_cutoff = datetime.utcnow() - _td_mig(minutes=30)
        _active_actions = db.query(_RA_mig).filter(
            _RA_mig.cluster_id == cluster_id,
            _or_mig(
                _RA_mig.status.in_(['in_progress', 'waiting_agent', 'pending']),
                # Drain-failed: action is 'failed' but source EC2 still running; retry imminent
                # Only match if the action is recent (< 30 min old) to avoid stale ghosts
                _and_mig(
                    _RA_mig.status == 'failed',
                    _RA_mig.action_metadata['current_step'].astext == 'failed_drain_ec2_protected',
                    _RA_mig.created_at >= _drain_retry_cutoff,
                ),
            ),
        ).all()
        for _aa in _active_actions:
            _meta = _aa.action_metadata or {}
            _repl_id = _meta.get('replacement_spot_instance_id')
            _src_id = _meta.get('instance_id')
            if _repl_id:
                _active_replacement_ids.add(_repl_id)
            if _src_id:
                _migration_map[_src_id] = {
                    'replacement_instance_id': _repl_id,
                    'replacement_type': (
                        _meta.get('target_instance_type')
                        or (_aa.target_pool.split(':')[0] if _aa.target_pool else None)
                    ),
                    'replacement_node_name': _meta.get('replacement_spot_node_name'),
                    'action_id': _aa.id,
                    'current_step': _meta.get('current_step'),
                    # Expose action status so UI can distinguish retrying from actively migrating
                    'action_status': _aa.status,
                }
    except Exception as _mig_err:
        logger.warning(f"node-recommendations: migration filter failed: {_mig_err}")

    # Filter out replacement instances — they are part of the migration, not new nodes
    _node_list = [n for n in _node_list if n['instance_id'] not in _active_replacement_ids]

    # ── Instance-type diversification cap ─────────────────────────────────
    # _max_same_type: how many nodes in this batch can share the same instance type.
    # Formula: max(1, round(total_nodes × (1 − div_pct / 100)))
    #   100% → 1  (every node must have a unique type — strictest)
    #   50%, 3 nodes → round(1.5) = 2 (up to 2 nodes may share a type)
    #   0% → total_nodes (no restriction)
    import math as _math
    _total_nodes = len(_node_list)
    _max_same_type = max(1, round(_total_nodes * (1.0 - _inst_type_div_pct / 100.0))) if _total_nodes > 0 else 1
    _type_counts: dict = {}  # instance_type → count of nodes already assigned that type

    # ── Anchor / stable node detection ────────────────────────────────────
    # The anchor node hosts Karpenter system pods and must NOT be converted
    # to spot. It stays at its current OD type + cost in optimized config.
    _anchor_node_name = None
    _anchor_instance_id = None
    try:
        import os as _os_anc
        import redis as _redis_anc
        import json as _json_anc
        _r_anc = _redis_anc.from_url(_os_anc.getenv("REDIS_URL", "redis://redis:6379/0"))
        _sn_raw_anc = _r_anc.get(f"spot:stable_node:{cluster_id}")
        if _sn_raw_anc:
            _sn_data_anc = _json_anc.loads(_sn_raw_anc)
            # Normalise to short hostname (split on '.') to match _node_list
            _anchor_node_name_raw = _sn_data_anc.get('node_name') or ''
            _anchor_node_name = _anchor_node_name_raw.split('.')[0] if _anchor_node_name_raw else None
            _anchor_instance_id = _sn_data_anc.get('instance_id')
    except Exception:
        pass
    # Fallback: an OD node classified as SYSTEM_PROTECTED by WorkloadInspector
    if not _anchor_node_name:
        for _nd_anc in _node_list:
            if 'spot' not in _nd_anc['lifecycle'] and node_classification.get(_nd_anc['node_name']) == "SYSTEM_PROTECTED":
                _anchor_node_name = _nd_anc['node_name']
                break
    # Fallback 2: When Karpenter is installed, one OD node MUST remain as anchor
    # to host Karpenter controller pods (they cannot run on spot).  Pick the
    # first OD node (sorted by name for determinism).  This covers:
    #   - All-OD cluster (new install, no spot yet) → 1 anchor + N-1 spot candidates
    #   - Mixed cluster with multiple OD nodes → still 1 anchor
    #   - Single OD among all-spot → same as before
    # NOTE: Only anchor if Karpenter is actually installed. Without Karpenter,
    # there is no system pod that requires OD protection.
    if not _anchor_node_name:
        _od_nodes = sorted(
            [n for n in _node_list if 'spot' not in n['lifecycle']],
            key=lambda n: n['node_name'],
        )
        _karp_installed = getattr(cluster, 'karpenter_mode', None) is not None
        if _od_nodes and _karp_installed:
            _anchor_node_name = _od_nodes[0]['node_name']

    for node in _node_list:
        instance_type = node["instance_type"]
        az = node["az"]
        lifecycle = node["lifecycle"]
        is_already_spot = 'spot' in lifecycle

        node_name = node["node_name"]
        on_demand_hourly = INSTANCE_HOURLY.get(instance_type, 0.096)

        # ── Anchor node: keep as-is, no spot conversion ─────────────────
        _is_anchor_node = False
        if _anchor_node_name and node_name == _anchor_node_name:
            _is_anchor_node = True
        elif _anchor_instance_id and node.get("instance_id") == _anchor_instance_id:
            _is_anchor_node = True
        
        # Original Provisioned Limits
        current_vcpu = VCPU_COUNT.get(instance_type, 2)
        current_mem = MEM_GB_MAP.get(instance_type, 8.0)
        
        # Real-time Telemetry bounds (with safety floor)
        cpu_util_pct = max(10.0, node["cpu_util"])
        mem_util_pct = max(10.0, node["memory_util"])
        
        # Required compute: actual current usage + 25% safety headroom margin
        required_vcpu_exact = (current_vcpu * (cpu_util_pct / 100.0)) * 1.25
        required_mem_exact = (current_mem * (mem_util_pct / 100.0)) * 1.25
        
        # Minimum: floor at current instance specs to prevent recommending a smaller instance.
        # e.g. t3.medium (2vCPU/4GB) must get a 2vCPU/4GB target, not t3a.small (2vCPU/2GB).
        # This aligns node-recommendations with Per-Node Alternative Pools which also enforces
        # pool_vcpu >= node_vcpu and pool_mem >= node_mem.
        required_vcpu = max(float(current_vcpu), required_vcpu_exact)
        required_mem = max(float(current_mem), required_mem_exact)

        # ── Workload type from WorkloadInspector cache ────────────────────
        cached_status = node_classification.get(node_name)
        if cached_status == "STATEFUL_PROTECTED":
            workload_type = "stateful"
        elif cached_status == "SYSTEM_PROTECTED":
            workload_type = "system"
        else:
            workload_type = "stateless"

        # ── Detect source architecture ──────────────────────────────────
        import re as _arch_re
        _src_family = instance_type.split(".")[0]
        _current_arch = "arm64" if (
            bool(_arch_re.search(r'\dg', _src_family)) or _src_family == "a1"
        ) else "amd64"

        # ── Select safest sized target pool with diversity ──────
        target_type = instance_type  # default: no better pool found
        target_az = az
        spot_price_hourly = on_demand_hourly  # default: no savings
        spot_savings_pct = 0                  # default: no savings (not hardcoded 70%)
        risk_score = float(node["risk_score"]) if node.get("risk_score") is not None else 0.10

        # Price ceilings (two tiers):
        #   OD→SPOT (different type): spot must be strictly cheaper than current OD
        #   S2S (same type, different AZ): allow up to 20% above OD — intentional headroom
        #     for cross-AZ rebalancing where stability/AZ-diversity matters more than pure cost
        _od_max_price = on_demand_hourly if on_demand_hourly > 0 else float('inf')
        _s2s_max_price = (on_demand_hourly * 1.20) if on_demand_hourly > 0 else float('inf')
        # max_acceptable_price is set per-pool in the selection loop based on type match

        chosen_pool = None       # reset per node
        chosen_pool_dict = None  # unified ranking result dict (replaces ORM chosen_pool)

        # For already-SPOT nodes: compute their actual realized savings vs on-demand
        # so the table shows real data ("t3.medium spot saving 54% vs OD") not 0%
        if is_already_spot:
            # Try to get current spot price for this instance type from ranked pools
            _spot_match = next(
                (p for p in top_pools if p.pool.instance_type == instance_type
                 and (not p.pool.az or p.pool.az == az or p.pool.az.startswith(region))),
                None
            ) or next((p for p in top_pools if p.pool.instance_type == instance_type), None)
            _mv_spot_price_cur = (
                _mv_spot_prices.get((instance_type, az))
                or _mv_spot_prices.get((instance_type, ''))
                or next((v for (t, _), v in _mv_spot_prices.items() if t == instance_type), None)
            )
            if _spot_match and _spot_match.pool.spot_price > 0 and on_demand_hourly > 0:
                spot_price_hourly = _spot_match.pool.spot_price
                raw_savings = (on_demand_hourly - spot_price_hourly) / on_demand_hourly * 100
                spot_savings_pct = max(0, round(raw_savings))
                risk_score = _spot_match.risk_probability
            elif _mv_spot_price_cur and on_demand_hourly > 0:
                spot_price_hourly = _mv_spot_price_cur
                raw_savings = (on_demand_hourly - _mv_spot_price_cur) / on_demand_hourly * 100
                spot_savings_pct = max(0, round(raw_savings))
                risk_score = 0.1
            elif _spot_match:
                spot_savings_pct = round(_spot_match.predicted_savings * 100)
                risk_score = _spot_match.risk_probability
            elif on_demand_hourly > 0:
                # No ML pool data for this type — apply conservative 60% spot discount estimate
                spot_price_hourly = on_demand_hourly * 0.4
                spot_savings_pct = 60
                risk_score = 0.2

        if not is_already_spot and not _is_anchor_node and top_pools:
            _total_nodes = len(_node_list)

            _src_arch = _current_arch

            # Use unified ranking function — same formula as UI Per-Node Alternatives.
            from backend.services.pool_ranking_service import PoolRankingService as _PRS_action
            from backend.core.redis_client import get_redis_client as _grc_action
            _prs_action = _PRS_action(db, _grc_action())
            _ranked_pools = _prs_action.rank_pools_for_node(
                node_info={
                    'instance_type': instance_type,
                    'az': az or '',
                    'od_price': on_demand_hourly,
                    'resource_profile': {
                        'min_vcpu_required': required_vcpu,
                        'min_memory_required': required_mem,
                        'architecture': _src_arch,
                    },
                },
                cluster_id=cluster_id,
                region=cluster.region or 'ap-south-1',
                include_dynamic_filters=True,
            )

            # Pick first ranked pool that also satisfies batch-level dedup + price ceiling.
            for _rp in _ranked_pools:
                _pk = (_rp['instance_type'], _rp.get('az', '') or '')
                if _diversify_enabled and _pk in used_pools:
                    continue
                if _diversify_enabled and _type_counts.get(_rp['instance_type'], 0) >= _max_same_type:
                    continue
                _rp_price = float(_rp.get('spot_price', 0) or 0)
                if _rp_price > 0:
                    _is_same = (_rp['instance_type'] == instance_type)
                    _ceil = _s2s_max_price if _is_same else _od_max_price
                    if _rp_price >= _ceil:
                        continue
                elif float(_rp.get('predicted_savings', 0) or 0) <= 0.25:
                    continue
                chosen_pool_dict = _rp
                target_type = _rp['instance_type']
                target_az = _rp.get('az', '') or az
                risk_score = float(_rp.get('risk_probability', 0.1))
                if _diversify_enabled:
                    used_pools.add(_pk)
                    _type_counts[_rp['instance_type']] = _type_counts.get(_rp['instance_type'], 0) + 1
                _pool_counts[_pk] = _pool_counts.get(_pk, 0) + 1
                break

            if chosen_pool_dict:
                _best_price = float(chosen_pool_dict.get('spot_price', 0) or 0)
                if _best_price > 0 and on_demand_hourly > 0:
                    spot_price_hourly = _best_price
                    raw_savings = (on_demand_hourly - _best_price) / on_demand_hourly * 100
                    spot_savings_pct = max(0, round(raw_savings))
                else:
                    spot_price_hourly = on_demand_hourly
                    spot_savings_pct = 0

        cpu_util = float(node.get("cpu_util") or 0.0)

        # Derive interruption rate label from the raw AWS bucket (interruption_rate_pct),
        # NOT from the ONNX composite risk_probability — these are different metrics.
        # Per-Node Alternative Pools also uses interruption_rate_pct, so this keeps labels consistent.
        if chosen_pool_dict:
            _irr_pct = float(chosen_pool_dict.get('interruption_rate_pct', risk_score * 100))
        else:
            _irr_pct = risk_score * 100  # no target pool — use source node composite score
        if _irr_pct < 5:
            interruption_rate = "<5%"
        elif _irr_pct <= 10:
            interruption_rate = "5–10%"
        elif _irr_pct <= 15:
            interruption_rate = "10–15%"
        elif _irr_pct <= 20:
            interruption_rate = "15–20%"
        else:
            interruption_rate = ">20%"

        # ── Determine actual current price ──────────────────────────────────
        # For spot nodes, use live spot price (not OD price) as current_cost.
        # This gives the UI an accurate baseline for savings comparison.
        _actual_current_cost = on_demand_hourly
        if is_already_spot and spot_price_hourly > 0 and spot_price_hourly < on_demand_hourly:
            _actual_current_cost = spot_price_hourly

        # ── Check if this node has an active migration ────────────────────
        _node_migration = _migration_map.get(node["instance_id"])
        # Anchor/stable node must NEVER show as migrating — even if a stale
        # RebalancingAction references it (e.g. action created before the node
        # was designated as anchor, or source_pool fallback matched it).
        # The auto_rebalancer excludes the stable node from batch candidates,
        # so any matching action is stale and should not affect the UI.
        if _is_anchor_node and _node_migration:
            logger.debug(
                f"node-recommendations: suppressing migration_info for anchor node "
                f"{node['instance_id']} (action_id={_node_migration.get('action_id')})"
            )
            _node_migration = None

        # ── Compute target architecture ──────────────────────────────────
        _tgt_family = target_type.split(".")[0]
        _target_arch = "arm64" if (
            bool(_arch_re.search(r'\dg', _tgt_family)) or _tgt_family == "a1"
        ) else "amd64"

        recommendations.append({
            "instance_id": node["instance_id"],
            "node_name": node_name,
            "current_type": instance_type,
            "current_az": node["az"],
            "az": node["az"],    # alias used by frontend source_pool AZ match
            "current_cost": round(_actual_current_cost, 4),
            "od_cost": round(on_demand_hourly, 4),
            "target_type": target_type,
            "target_az": target_az,
            "target_spot_price": round(spot_price_hourly, 4),
            "projected_savings_pct": spot_savings_pct,
            "risk_score": round(risk_score, 3),
            "interruption_rate": interruption_rate,
            "workload_type": workload_type,
            "lifecycle": "spot" if is_already_spot else "on_demand",
            "is_anchor": _is_anchor_node,
            "instance_family": (instance_type or "").split(".")[0],
            "current_arch": _current_arch,
            "target_arch": _target_arch,
            "cross_arch": _current_arch != _target_arch,
            "migration_info": _node_migration,
            # K8s / collector health status. UNKNOWN = EC2 running but not in K8s cluster.
            "node_health_status": node.get("node_health_status") or "READY",
        })

    # ── Pool distribution for diversify visualisation (pool = current_type:az) ──
    _pool_dist: dict = {}
    for _r in recommendations:
        _pk_str = f"{_r['current_type']}:{_r.get('target_az', '')}"
        _pool_dist[_pk_str] = _pool_dist.get(_pk_str, 0) + 1
    _total_nodes_dist = max(1, len(recommendations))
    _pool_shares = {
        pool: {"count": cnt, "pct": round(cnt / _total_nodes_dist * 100)}
        for pool, cnt in _pool_dist.items()
    }

    # ── S2S candidate detection ──────────────────────────────────────────────
    # Mark nodes that would trigger a SPOT→SPOT (same type, cross-AZ) rebalancing action.
    # Triggers:
    #   cross-az:  OD or SPOT node → same instance type in a different AZ
    #   diversify: pool already used by another node (pool_count > 1) — SPOT nodes only
    #   risk:      node's risk_score exceeds risk_ceiling — SPOT nodes only
    try:
        from backend.models.cluster import OptimizationStrategy as _OS_s2s_r
        _os_s2s_r = db.query(_OS_s2s_r).filter_by(cluster_id=cluster_id).first()
        _rceil_s2s_r = (getattr(_os_s2s_r, 'risk_ceiling_percent', 25) or 25) / 100.0
    except Exception:
        _rceil_s2s_r = 0.25

    for _r in recommendations:
        _s2s_trigger = None
        # Cross-AZ same-type: applies to both OD and SPOT nodes
        if _r.get("target_type") == _r.get("current_type") and _r.get("target_az") != _r.get("current_az"):
            _s2s_trigger = f"cross-az: {_r['current_type']} → {_r.get('target_az','?')} (lower interruption AZ)"
        # SPOT-only triggers
        if not _s2s_trigger and _r["lifecycle"] == "spot":
            if _diversify_enabled:
                _pk_str = f"{_r['current_type']}:{_r.get('target_az', '')}"
                if _pool_dist.get(_pk_str, 0) > 1:
                    _s2s_trigger = f"diversify: duplicate pool {_pk_str} ({_pool_dist[_pk_str]} nodes)"
            if not _s2s_trigger and _r["risk_score"] > _rceil_s2s_r:
                _s2s_trigger = f"risk: score {_r['risk_score']:.2f} > {_rceil_s2s_r:.2f} ceiling"
        _r["s2s_candidate"] = _s2s_trigger is not None
        _r["s2s_trigger"] = _s2s_trigger

    # ── Build summary block for the UI ──────────────────────────────────
    _total_current_hourly = sum(r.get("current_cost", 0) for r in recommendations)
    _total_target_hourly = sum(r.get("target_spot_price", 0) or 0 for r in recommendations)
    _total_od_hourly = sum(r.get("od_cost", 0) for r in recommendations)
    _total_monthly_cost = round(_total_current_hourly * 730, 2)
    _total_potential = round(max(0, _total_current_hourly - _total_target_hourly) * 730, 2)

    # ── Karpenter multi-cycle convergence simulation (v2) ───────────────
    # Replaces single-pass FFD with production-grade simulation that mirrors
    # real Karpenter + auto-rebalancer behavior:
    #   - Consistent snapshot (frozen timestamp)
    #   - Virtual cluster state with node/pod transitions
    #   - Multi-cycle convergence loop (max 10 cycles)
    #   - Greedy scheduler (not globally-optimal FFD)
    #   - Redis constraint replay (launch_blocked, blacklist, risky_pools)
    #   - Per-cluster pool view (not shared regional cache)
    #   - Stateless/stateful two-pool separation
    #   - Fragmentation modeling (8% default correction)
    #   - Confidence scoring
    _karpenter_simulation = None
    _karp_mode = getattr(cluster, 'karpenter_mode', None)
    if _karp_mode is not None:
        try:
            from backend.models.pod_metric import PodMetric as _PM_karp
            from sqlalchemy import func as _func_karp
            from datetime import datetime as _dt_karp, timedelta as _td_karp
            from backend.services.simulation_engine import (
                SimNode, SimPod, SimPool, SimRedisState, SimClusterSettings,
                SimulationSnapshot, run_simulation, build_simulation_output,
                SYSTEM_NAMESPACES, DAEMONSET_KINDS, KUBELET_CPU_M, KUBELET_MEM_BYTES,
            )

            _snapshot_frozen_at = _dt_karp.utcnow()

            # ── 1) Gather pod resource demands (latest metric per pod) ────────
            _karp_cutoff = _snapshot_frozen_at - _td_karp(minutes=10)
            _karp_latest_subq = db.query(
                _PM_karp.pod_name,
                _PM_karp.node_name,
                _func_karp.max(_PM_karp.timestamp).label('max_ts')
            ).filter(
                _PM_karp.cluster_id == cluster_id,
                _PM_karp.timestamp >= _karp_cutoff
            ).group_by(_PM_karp.pod_name, _PM_karp.node_name).subquery()

            _karp_pods = db.query(_PM_karp).join(
                _karp_latest_subq,
                (_PM_karp.pod_name == _karp_latest_subq.c.pod_name) &
                (_PM_karp.node_name == _karp_latest_subq.c.node_name) &
                (_PM_karp.timestamp == _karp_latest_subq.c.max_ts)
            ).all()

            # ── Separate DaemonSet pods from user workloads ───────────────────
            _user_pod_demands = []
            _daemonset_demands = []
            _ds_seen = set()

            for _kp in _karp_pods:
                _meta = _kp.pod_metadata or {}
                _ctrl_kind = _kp.controller_kind or _meta.get('owner_kind', '')
                _ns = _kp.namespace or ''
                _is_ds = _ctrl_kind in DAEMONSET_KINDS
                _is_sys = _ns in SYSTEM_NAMESPACES
                _is_stateful = (
                    _ctrl_kind == 'StatefulSet' or
                    any('persistentVolumeClaim' in v
                        for v in (_meta.get('volumes') or [])
                        if isinstance(v, dict))
                )

                _cpu_req = _kp.cpu_request_millicores
                _mem_req = _kp.memory_request_bytes
                _cpu_use = _kp.cpu_usage_millicores or 0
                _mem_use = _kp.memory_usage_bytes or 0

                if _cpu_req and _cpu_req > 0:
                    _cpu_m = _cpu_req
                else:
                    _cpu_m = max(int(_cpu_use * 1.5), 50)

                if _mem_req and _mem_req > 0:
                    _mem_b = _mem_req
                else:
                    _mem_b = max(int(_mem_use * 1.5), 64 * 1024 * 1024)

                _pod_entry = SimPod(
                    pod_name=_kp.pod_name,
                    namespace=_ns,
                    controller_name=_kp.controller_name or '',
                    controller_kind=_ctrl_kind,
                    cpu_millicores=_cpu_m,
                    memory_bytes=_mem_b,
                    is_stateful=_is_stateful,
                    is_daemonset=_is_ds,
                    is_system=_is_sys,
                    node_name=(_kp.node_name or '').split('.')[0],
                    node_selector=_meta.get('node_selector') or None,
                    tolerations=_meta.get('tolerations') or None,
                    has_pod_anti_affinity=bool((_meta.get('affinity') or {}).get('pod_anti_affinity_required')),
                    has_pod_affinity=bool((_meta.get('affinity') or {}).get('pod_affinity_required')),
                    topology_spread_constraints=_meta.get('topology_spread_constraints') or None,
                    cpu_limit_millicores=getattr(_kp, 'cpu_limit_millicores', None),
                    memory_limit_bytes=getattr(_kp, 'memory_limit_bytes', None),
                )

                if _is_ds or _is_sys:
                    _ds_key = (_kp.controller_name or _kp.pod_name.rsplit('-', 1)[0])
                    if _ds_key not in _ds_seen:
                        _ds_seen.add(_ds_key)
                        _daemonset_demands.append(_pod_entry)
                else:
                    _user_pod_demands.append(_pod_entry)

            # Fallback: if no pod metrics, estimate from node-level utilization
            if not _user_pod_demands and not _daemonset_demands and _node_list:
                for _nd in _node_list:
                    _nd_vcpu = VCPU_COUNT.get(_nd['instance_type'], 2)
                    _nd_mem = MEM_GB_MAP.get(_nd['instance_type'], 4.0)
                    _cpu_used = int(_nd_vcpu * 1000 * max(10, _nd.get('cpu_util', 50)) / 100)
                    _mem_used = int(_nd_mem * 1024 * 1024 * 1024 * max(10, _nd.get('memory_util', 50)) / 100)
                    _user_pod_demands.append(SimPod(
                        pod_name=f"node-workload-{_nd['node_name']}",
                        namespace='default',
                        controller_name='',
                        controller_kind='',
                        cpu_millicores=_cpu_used,
                        memory_bytes=_mem_used,
                        is_stateful=False,
                        is_daemonset=False,
                        is_system=False,
                        node_name=_nd['node_name'],
                    ))

            # ── DaemonSet per-node overhead ───────────────────────────────────
            _ds_cpu_overhead = sum(d.cpu_millicores for d in _daemonset_demands)
            _ds_mem_overhead = sum(d.memory_bytes for d in _daemonset_demands)

            # ── Right-sizing substitution ─────────────────────────────────────
            if use_rightsized:
                try:
                    from backend.services.rightsizing_service import RightSizingService as _RSsvc
                    _rs_svc = _RSsvc(db)
                    _rs_recs = _rs_svc.generate_recommendations(cluster_id=cluster_id)
                    _rs_lookup = {}
                    for _rr in _rs_recs:
                        _key = (_rr.namespace, _rr.controller_name)
                        _rs_lookup[_key] = (
                            _rr.recommended_cpu_request_millicores,
                            int(_rr.recommended_memory_request_mb * 1024 * 1024),
                        )
                    _rs_applied = 0
                    for _up in _user_pod_demands:
                        _ctrl = _up.controller_name
                        if not _ctrl:
                            _parts = _up.pod_name.rsplit('-', 2)
                            _ctrl = '-'.join(_parts[:-2]) if len(_parts) >= 3 else '-'.join(_parts[:-1]) if len(_parts) >= 2 else _up.pod_name
                        _key = (_up.namespace, _ctrl)
                        if _key in _rs_lookup:
                            _up.cpu_millicores = _rs_lookup[_key][0]
                            _up.memory_bytes = _rs_lookup[_key][1]
                            _rs_applied += 1
                    logger.info(f"karp-sim: right-sized {_rs_applied}/{len(_user_pod_demands)} pods using {len(_rs_lookup)} recommendations")
                except Exception as _rs_err:
                    logger.warning(f"karp-sim: right-sizing substitution failed: {_rs_err}")

            # ── Build SimNode list from _node_list ────────────────────────────
            import re as _karp_arch_re
            _sim_nodes_list = []
            for _nd in _node_list:
                _nd_family = (_nd['instance_type'] or 'm5.large').split('.')[0]
                _nd_arch = 'arm64' if (bool(_karp_arch_re.search(r'\dg', _nd_family)) or _nd_family == 'a1') else 'amd64'
                _nd_vcpu_v = VCPU_COUNT.get(_nd['instance_type'], 2)
                _nd_mem_v = MEM_GB_MAP.get(_nd['instance_type'], 4.0)
                _nd_price = float(INSTANCE_HOURLY.get(_nd['instance_type'], 0.096) or 0.096)
                # If spot, use spot price from market view
                if _nd['lifecycle'] == 'spot':
                    _sp_key = (_nd['instance_type'], _nd['az'])
                    _nd_price = _mv_spot_prices.get(_sp_key, _nd_price)

                # Workload class from WorkloadInspector classification
                _cached_cls = node_classification.get(_nd['node_name'])
                if _cached_cls == 'STATEFUL_PROTECTED':
                    _wl_class = 'stateful'
                elif _cached_cls == 'SYSTEM_PROTECTED':
                    _wl_class = 'system'
                else:
                    _wl_class = 'stateless'

                _sim_nodes_list.append(SimNode(
                    instance_id=_nd['instance_id'],
                    instance_type=_nd['instance_type'],
                    lifecycle=_nd['lifecycle'],
                    az=_nd['az'],
                    architecture=_nd_arch,
                    vcpu=_nd_vcpu_v,
                    memory_gb=_nd_mem_v,
                    price_hourly=_nd_price,
                    workload_class=_wl_class,
                    status=_nd.get('node_health_status', 'READY'),
                    is_standby=False,
                    node_name=_nd['node_name'],
                    is_anchor=(_nd['node_name'] == _anchor_node_name),
                ))

            # ── Build candidate SimPool list from top_pools ───────────────────
            _sim_pools = []
            _seen_pool_types = set()
            for _tp in top_pools:
                _it = _tp.pool.instance_type
                if _it in _seen_pool_types:
                    continue
                _tp_arch = (_tp.pool.architecture or 'amd64').replace('x86_64', 'amd64')
                if _tp.pool.vcpu < 2 or _tp.pool.memory_gb < 2.0:
                    continue
                _sp = _tp.pool.spot_price
                _od_ref = getattr(_tp.pool, 'ondemand_price', 0) or INSTANCE_HOURLY.get(_it, 0)
                if _sp <= 0:
                    continue
                if _od_ref > 0:
                    _discount = (_od_ref - _sp) / _od_ref
                    if _discount < 0.05 or _discount > 0.90:
                        continue

                _seen_pool_types.add(_it)
                _risk = _tp.risk_probability
                _savings = _tp.predicted_savings
                _ml_score = round(_savings * max(0.0, 1.0 - _risk), 6)

                _sim_pools.append(SimPool(
                    instance_type=_it,
                    az=_tp.pool.az,
                    architecture=_tp_arch,
                    vcpu=_tp.pool.vcpu,
                    memory_gb=_tp.pool.memory_gb,
                    spot_price=_sp,
                    od_price=_od_ref,
                    risk_probability=_risk,
                    ml_score=_ml_score,
                ))

            # ── Build Redis constraint state snapshot ─────────────────────────
            _sim_redis = SimRedisState()
            try:
                # Launch blocked keys: spot:launch_blocked:{cid}:{type}:{az}
                _lb_pattern = f"spot:launch_blocked:{cluster_id}:*"
                _lb_keys = redis.keys(_lb_pattern)
                for _lbk in (_lb_keys or []):
                    _lbk_str = _lbk.decode() if isinstance(_lbk, bytes) else _lbk
                    # Extract {cid}:{type}:{az} part
                    _parts = _lbk_str.replace(f"spot:launch_blocked:", "")
                    _sim_redis.launch_blocked.add(_parts)

                # Global blacklist
                _bl_members = redis.smembers("risky_pools") or set()
                for _bl in _bl_members:
                    _bl_str = _bl.decode() if isinstance(_bl, bytes) else _bl
                    _sim_redis.risky_pools.add(_bl_str)

                # PDB safe percent
                _pdb_raw = redis.get(f"pdb:safe_percent:{cluster_id}")
                if _pdb_raw:
                    _sim_redis.pdb_safe_percent = int(_pdb_raw)
            except Exception as _redis_err:
                logger.debug(f"karp-sim: redis snapshot partial: {_redis_err}")

            # ── Build cluster settings ────────────────────────────────────────
            _opt = cluster.optimization_settings
            _strat = cluster.optimization_strategy_profile
            _sim_settings = SimClusterSettings(
                target_spot_exposure_pct=int(getattr(_opt, 'target_spot_exposure_pct', 100) or 100) if _opt else 100,
                diversify_pools=bool(getattr(_opt, 'diversify_pools', False)) if _opt else False,
                max_family_diversification_cap_pct=int(getattr(_opt, 'max_family_diversification_cap_pct', 40) or 40) if _opt else 40,
                architecture_preference=getattr(_opt, 'architecture_preference', 'both') or 'both' if _opt else 'both',
                min_node_count=int(getattr(_opt, 'min_node_count', 1) or 1) if _opt else 1,
                rebalance_batch_percent=getattr(_opt, 'rebalance_batch_percent', None) if _opt else None,
                risk_ceiling_percent=int(getattr(_strat, 'risk_ceiling_percent', 25) or 25) if _strat else 25,
                risk_savings_tradeoff_pct=int(getattr(_strat, 'risk_savings_tradeoff_pct', 20) or 20) if _strat else 20,
                min_topology_spread=int(getattr(_opt, 'min_topology_spread', 1) or 1) if _opt else 1,
            )

            # ── Assemble the frozen snapshot ──────────────────────────────────
            import uuid
            _all_pods = _user_pod_demands + _daemonset_demands
            _snapshot = SimulationSnapshot(
                snapshot_id=str(uuid.uuid4()),
                frozen_at=_snapshot_frozen_at,
                cluster_id=cluster_id,
                nodes=_sim_nodes_list,
                pods=_all_pods,
                redis_state=_sim_redis,
                cluster_settings=_sim_settings,
                karpenter_mode=str(_karp_mode.value) if hasattr(_karp_mode, 'value') else str(_karp_mode),
                use_rightsized=use_rightsized,
                candidate_pools=_sim_pools,
                ds_cpu_overhead=_ds_cpu_overhead,
                ds_mem_overhead=_ds_mem_overhead,
            )

            # ── Run multi-cycle convergence simulation ────────────────────────
            _sim_result = run_simulation(_snapshot)

            # ── Build enhanced output ─────────────────────────────────────────
            _karpenter_simulation = build_simulation_output(
                result=_sim_result,
                snapshot=_snapshot,
                current_node_count=len(_node_list),
                current_monthly_cost=_total_monthly_cost,
            )

        except Exception as _karp_sim_err:
            logger.warning(f"node-recommendations: karpenter simulation failed: {_karp_sim_err}")
            import traceback; logger.warning(traceback.format_exc())
            _karpenter_simulation = None

    _has_od_nodes = any(r["lifecycle"] != "spot" for r in recommendations)
    return {
        "recommendations": recommendations,
        "summary": {
            "total_nodes": len(recommendations),
            "total_monthly_cost": _total_monthly_cost,
            "total_od_baseline": round(_total_od_hourly * 730, 2),
            "potential_additional_monthly_savings": _total_potential,
            "eligible_pools_count": eligible_pools_count,
        },
        "eligible_pools_count": eligible_pools_count,
        "pool_distribution": _pool_shares,
        "family_distribution": _pool_shares,  # kept for backward compat — same data
        "diversify_enabled": _diversify_enabled,
        "karpenter_simulation": _karpenter_simulation,
        "dynamic_risk_ceiling": round(_dynamic_risk_ceiling, 4),
        "has_od_nodes": _has_od_nodes,
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

    instances = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.state.in_(['running', 'pending']),
    ).all()

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
    _impact_region = cluster.region or 'ap-south-1'
    INSTANCE_HOURLY = bulk_get_hourly_prices(db, redis, _all_impact_types, _impact_region)

    # Load market_view_cache spot prices for accurate savings calculation
    _impact_mv_spot: dict = {}  # (instance_type, az) -> spot_price
    try:
        from backend.core.redis_client import key_market_view_cache
        import json as _imv_json
        _imv_raw = redis.get(key_market_view_cache(_impact_region))
        if _imv_raw:
            for _p in _imv_json.loads(_imv_raw).get('data', []):
                if _p.get('spot_price', 0) > 0:
                    _impact_mv_spot[(_p.get('instance_type', ''), _p.get('az', ''))] = float(_p['spot_price'])
    except Exception:
        pass

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
        rep_az = pool_instances[0]["az"]
        hourly_rate = INSTANCE_HOURLY.get(rep_type, 0.096)
        # Use real spot price from market_view_cache if available, else 65% OD estimate
        _real_spot = (
            _impact_mv_spot.get((rep_type, rep_az))
            or _impact_mv_spot.get((rep_type, ''))
            or next((v for (t, _), v in _impact_mv_spot.items() if t == rep_type), None)
        )
        spot_rate = _real_spot if _real_spot else hourly_rate * 0.35
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
    from backend.models.cluster import Cluster, ClusterOptimizationSettings
    from backend.models.instance import Instance, InstanceLifecycle
    from backend.models.rebalancing_action import RebalancingAction

    # Read per-cluster cooldown from DB (cooldown_override_minutes), default 60 min.
    # This must always match the value used in auto_rebalancer.py so the UI countdown
    # reflects exactly how long the rebalancer will actually wait.
    try:
        _opt = db.query(ClusterOptimizationSettings).filter(
            ClusterOptimizationSettings.cluster_id == cluster_id
        ).first()
        _cooldown_min = getattr(_opt, 'cooldown_override_minutes', None) if _opt else None
        _POST_REBALANCE_COOLDOWN_S = (_cooldown_min * 60) if (_cooldown_min and _cooldown_min > 0) else 3600
        _check_interval = max(15, int(getattr(_opt, 'check_interval_seconds', 15) or 15))
    except Exception:
        _POST_REBALANCE_COOLDOWN_S = 3600
        _check_interval = 15

    try:
        redis = get_redis_client()

        # ── 0. In-progress check (MUST come before cooldown) ──────────────────
        # While an optimization is actively running, do NOT show the cooldown
        # countdown — show "Optimization in progress" instead.
        # Cooldown only makes sense after the action finishes successfully.
        optimization_in_progress = False
        active_action_id = None
        try:
            _active_action = (
                db.query(RebalancingAction)
                .filter(
                    RebalancingAction.cluster_id == cluster_id,
                    RebalancingAction.status.in_(
                        ['in_progress', 'waiting_agent', 'pending', 'pending_approval']
                    ),
                )
                .order_by(RebalancingAction.started_at.desc())
                .first()
            )
            if _active_action:
                optimization_in_progress = True
                active_action_id = str(_active_action.id)
        except Exception:
            pass

        # ── 1. Cooldown detection (only when NOT in-progress) ─────────────────
        cooldown_active = False
        remaining_seconds = 0
        cooldown_reason = None

        if not optimization_in_progress:
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

            # Check post-rebalance window — starts only AFTER last completed action
            if not cooldown_active:
                try:
                    _last = (
                        db.query(RebalancingAction)
                        .filter(
                            RebalancingAction.cluster_id == cluster_id,
                            RebalancingAction.status == "completed",
                            RebalancingAction.trigger == "auto_rebalance",
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

        # ── 1b. Daily limit check ─────────────────────────────────────────────
        daily_limit_reached = False
        daily_limit_used = 0
        daily_limit_max = 5
        try:
            from backend.models.cluster import StatelessRuntimeRules as _SRR_ctx
            _sr = db.query(_SRR_ctx).filter_by(cluster_id=cluster_id).first()
            daily_limit_max = (_sr.max_rebalances_per_24h if _sr else 5) or 5
            daily_limit_used = (
                db.query(RebalancingAction)
                .filter(
                    RebalancingAction.cluster_id == cluster_id,
                    RebalancingAction.trigger == 'auto_rebalance',
                    RebalancingAction.status == 'completed',
                    RebalancingAction.started_at >= datetime.utcnow() - timedelta(hours=24),
                )
                .count()
            )
            daily_limit_reached = (daily_limit_used >= daily_limit_max)
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

        _now = datetime.utcnow()
        _expires_at = (
            (_now + timedelta(seconds=remaining_seconds)).isoformat() + "Z"
            if cooldown_active and remaining_seconds > 0 else None
        )
        # next_check_at: compute from the last-run timestamp recorded by the
        # rebalancer plus the configured check interval.  For custom intervals
        # (> 15s) the Redis gate TTL gives a precise answer.  For the default
        # 15s interval (where the gate isn't used), we fall back to last_run_ts
        # which the rebalancer writes on every cycle.
        _last_check_ttl = -1
        _last_run_ts_raw = None
        try:
            if redis:
                _last_check_ttl = redis.ttl(f"spot:last_check:{cluster_id}")
                _last_run_ts_raw = redis.get(f"spot:last_run_ts:{cluster_id}")
        except Exception:
            pass
        if _last_check_ttl and _last_check_ttl > 0:
            # Custom interval gate is active: next cycle fires when this key expires
            _next_check_at = (_now + timedelta(seconds=_last_check_ttl)).isoformat() + "Z"
        elif _last_run_ts_raw:
            # Default 15s interval: compute from last run timestamp
            try:
                _last_run_epoch = int(_last_run_ts_raw.decode() if isinstance(_last_run_ts_raw, bytes) else _last_run_ts_raw)
                _last_run_dt = datetime.utcfromtimestamp(_last_run_epoch)
                _next_due = _last_run_dt + timedelta(seconds=_check_interval)
                # If the next-due time is already in the past, the cycle is imminent
                _secs_until = max(0, (_next_due - _now).total_seconds())
                _next_check_at = (_now + timedelta(seconds=_secs_until)).isoformat() + "Z"
            except (ValueError, TypeError):
                _next_check_at = (_now + timedelta(seconds=min(15, _check_interval))).isoformat() + "Z"
        else:
            # No data at all: next beat is imminent
            _next_check_at = (_now + timedelta(seconds=min(15, _check_interval))).isoformat() + "Z"

        return {
            "cluster_id": cluster_id,
            "optimization_in_progress": optimization_in_progress,
            "active_action_id": active_action_id,
            "daily_limit_reached": daily_limit_reached,
            "daily_limit_used": daily_limit_used,
            "daily_limit_max": daily_limit_max,
            "cooldown": {
                "active": cooldown_active,
                "remaining_seconds": remaining_seconds,
                "expires_at": _expires_at,
                "reason": cooldown_reason,
            },
            "next_target": next_target,
            "next_check_at": _next_check_at,
            "check_interval_seconds": _check_interval,
            "timestamp": _now.isoformat() + "Z",
        }

    except Exception as e:
        logger.error(f"[rebalancing-context] Failed for {cluster_id}: {e}")
        _fb_now = datetime.utcnow()
        return {
            "cluster_id": cluster_id,
            "optimization_in_progress": False,
            "active_action_id": None,
            "cooldown": {"active": False, "remaining_seconds": 0, "expires_at": None, "reason": None},
            "next_target": None,
            "next_check_at": (_fb_now + timedelta(seconds=_check_interval)).isoformat() + "Z",
            "check_interval_seconds": _check_interval,
            "timestamp": _fb_now.isoformat() + "Z",
        }


# ── Per-Node Coverage & Alternatives (changes.md Part 8) ──────────────────────

@router.get("/clusters/{cluster_id}/coverage")
def get_cluster_coverage(cluster_id: str, db: Session = Depends(get_db)):
    """
    GET /api/v1/ascpai/clusters/{cluster_id}/coverage

    Returns ClusterCoverageReport:
      - total_nodes, covered_nodes, at_risk_nodes, stranded_nodes, immovable_nodes
      - cluster_coverage_pct
      - per_node_summary: [{node_id, instance_type, az, status, alternative_count,
                            best_pool, best_saving_pct, ...}]

    Served from Redis cache (TTL 300s, refreshed by reconciliation_worker every 5 min).
    On cache miss, computes on-demand.
    """
    redis = get_redis_client()
    cache_key = f"cluster_coverage:{cluster_id}"

    try:
        cached = redis.get(cache_key)
        if cached:
            return _json.loads(cached)
    except Exception:
        pass

    # Compute on-demand on cache miss
    from backend.models.cluster import Cluster
    from backend.workers.tasks.reconciliation_worker import _compute_cluster_coverage
    cluster = db.query(Cluster).filter_by(id=cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    report = _compute_cluster_coverage(db, redis, cluster)
    if not report:
        return {
            "cluster_id": cluster_id,
            "total_nodes": 0,
            "covered_nodes": 0,
            "at_risk_nodes": 0,
            "stranded_nodes": 0,
            "immovable_nodes": 0,
            "cluster_coverage_pct": 0.0,
            "per_node_summary": [],
            "computed_at": datetime.utcnow().isoformat(),
        }
    return report


@router.get("/clusters/{cluster_id}/nodes/{node_id}/alternatives")
def get_node_alternatives(
    cluster_id: str,
    node_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    GET /api/v1/ascpai/clusters/{cluster_id}/nodes/{node_id}/alternatives

    Returns per-node alternative pool list for a specific node.
    Pools are filtered by size/arch/risk ceiling, then split:
      - Positive savings (spot < node OD price): always shown, ranked by expected_value desc
      - Negative savings: shown ONLY if positive set is empty AND within trade-off AND lower risk
    Paginated: ?page=1&page_size=20
    """
    import json as _json
    from backend.models.instance import Instance
    from backend.models.cluster import Cluster
    from backend.core.redis_client import (
        get_redis_client, key_market_view_cache, key_global_pool_rankings,
    )
    from backend.workers.tasks.cache_builder import (
        _lookup_specs as _cb_lookup_specs,
        _lookup_od_price as _cb_lookup_od,
    )

    redis = get_redis_client()

    cluster = db.query(Cluster).filter_by(id=cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # Resolve node by DB id or instance_id
    inst = (
        db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.id == node_id,
        ).first()
        or db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.instance_id == node_id,
        ).first()
    )
    if not inst:
        raise HTTPException(status_code=404, detail="Node not found")

    region = getattr(cluster, 'region', None) or 'us-east-1'

    # ── Node specs ────────────────────────────────────────────────────────
    node_vcpu, node_mem, node_arch, _ = _cb_lookup_specs(inst.instance_type)
    node_arch = getattr(inst, 'architecture', None) or node_arch or 'amd64'

    # Fall back to safe minimums if lookup returned zeroes
    node_vcpu = node_vcpu or 2
    node_mem = node_mem or 4.0

    # ── Utilization-aware size requirements ───────────────────────────────
    # Use actual CPU/RAM utilisation from the node's telemetry + 25% headroom,
    # but never go below the current instance's provisioned specs.
    # This prevents recommending a pool whose capacity is technically equal to
    # the instance type but too small for the real workload load.
    _cpu_util_pct = max(10.0, float(getattr(inst, 'cpu_util', 0) or 0))
    _mem_util_pct = max(10.0, float(getattr(inst, 'memory_util', 0) or 0))
    _required_vcpu_exact = (node_vcpu * (_cpu_util_pct / 100.0)) * 1.25
    _required_mem_exact  = (node_mem  * (_mem_util_pct / 100.0)) * 1.25
    # Floor at current provisioned specs — never recommend a smaller instance
    required_vcpu = max(float(node_vcpu), _required_vcpu_exact)
    required_mem  = max(float(node_mem),  _required_mem_exact)

    # ── Node OD price (the baseline for savings) ──────────────────────────
    node_od_price = _cb_lookup_od(redis, region, inst.instance_type)
    if node_od_price <= 0:
        from backend.services.dynamic_instance_helpers import bulk_get_hourly_prices
        _od_lookup = bulk_get_hourly_prices(db, redis, [inst.instance_type], region)
        node_od_price = _od_lookup.get(inst.instance_type) or 0.0

    # ── Node lifecycle and current price (actual cost the node is running at) ──
    import json as _json_alt
    _node_lifecycle = (
        inst.lifecycle.value if hasattr(inst.lifecycle, 'value')
        else str(inst.lifecycle or 'on-demand')
    ).lower()
    _is_spot_node = 'spot' in _node_lifecycle
    node_current_price = node_od_price  # default: OD price
    if _is_spot_node:
        # Look up actual spot price from Redis
        _node_az = getattr(inst, 'az', None) or ''
        _spot_key = f"spot_price:{region}:{_node_az}:{inst.instance_type}"
        _raw_sp = redis.get(_spot_key)
        if _raw_sp:
            try:
                _sp_data = _json_alt.loads(_raw_sp)
                _sp_val = float(_sp_data.get('price', 0) or 0)
                if _sp_val > 0:
                    node_current_price = _sp_val
            except Exception:
                pass

    if node_od_price <= 0:
        return {
            "cluster_id": cluster_id,
            "node_id": node_id,
            "instance_id": inst.instance_id,
            "message": f"On-demand price unavailable for {inst.instance_type} in {region}",
            "total_alternatives": 0, "page": page, "page_size": page_size,
            "total_pages": 0, "alternatives": [],
        }

    # ── Node risk probability (for negative-savings trade-off filter) ─────
    node_risk = None
    try:
        raw_risk = redis.get(f"spot_advisor:{region}:{inst.instance_type}:Linux")
        if raw_risk:
            _rd = _json.loads(raw_risk)
            _idx = int(_rd.get("interruption_index", 4))
            node_risk = {0: 0.05, 1: 0.10, 2: 0.15, 3: 0.20, 4: 0.25}.get(_idx, 0.25)
    except Exception:
        pass

    # ── Unified ranking via rank_pools_for_node ────────────────────────────
    from backend.services.pool_ranking_service import PoolRankingService
    _prs = PoolRankingService(db, redis)
    result = _prs.rank_pools_for_node(
        node_info={
            'instance_type': inst.instance_type,
            'az': getattr(inst, 'az', None) or '',
            'od_price': node_od_price,
            'current_price': node_current_price,  # actual price: spot price for spot nodes, OD for OD nodes
            'risk_score': float(getattr(inst, 'risk_score', 0) or 0),
            'resource_profile': {
                'min_vcpu_required': required_vcpu,
                'min_memory_required': required_mem,
                'architecture': node_arch,
            },
        },
        cluster_id=cluster_id,
        region=region,
        include_dynamic_filters=True,
    )

    # ── No-join block filter ─────────────────────────────────────────────
    # Remove pools that recently failed to join the cluster (launch_blocked).
    _node_az = getattr(inst, 'az', None) or ''
    _nojoin_removed = 0
    _filtered_result = []
    for p in result:
        _blk_key = f"spot:launch_blocked:{cluster_id}:{p.get('instance_type')}:{_node_az}"
        if redis.get(_blk_key):
            _nojoin_removed += 1
            continue
        _filtered_result.append(p)
    result = _filtered_result

    # ── Dry-run capacity check ────────────────────────────────────────────
    # Validate REAL spot capacity via cached RunInstances DryRun results.
    # Only checks cached results (no AWS API calls) to keep the endpoint fast.
    # Pools with cached dry_run:fail are marked; unchecked pools are kept.
    _dryrun_removed = 0
    _dryrun_checked = []
    for p in result:
        _dr_key = f"dry_run:{p.get('instance_type')}:{_node_az}"
        _dr_cached = redis.get(_dr_key)
        if _dr_cached:
            _dr_val = _dr_cached.decode() if isinstance(_dr_cached, bytes) else _dr_cached
            if _dr_val == "fail":
                _dryrun_removed += 1
                continue
        _dryrun_checked.append(p)
    result = _dryrun_checked

    # Sort: would_be_launched first, then remaining rebalancer-eligible pools,
    # then the rest — all within each group still sorted by expected_value DESC.
    result_sorted = (
        [p for p in result if p.get('would_be_launched')] +
        [p for p in result if p.get('rebalancer_eligible') and not p.get('would_be_launched')] +
        [p for p in result if not p.get('rebalancer_eligible')]
    )

    # Count eligible pools for metadata
    _eligible_count = sum(1 for p in result_sorted if p.get('rebalancer_eligible'))
    _launched_pool = next((p for p in result_sorted if p.get('would_be_launched')), None)

    # ── Paginate ──────────────────────────────────────────────────────────
    total = len(result_sorted)
    start = (page - 1) * page_size
    page_data = result_sorted[start:start + page_size]

    # Add rank
    for i, p in enumerate(page_data, start=start + 1):
        p['rank'] = i

    return {
        "cluster_id": cluster_id,
        "node_id": node_id,
        "instance_id": inst.instance_id,
        "node_name": getattr(inst, 'node_name', None) or inst.instance_id,
        "instance_type": inst.instance_type,
        "az": inst.az,
        "architecture": node_arch,
        "current_node": {
            "instance_type": inst.instance_type,
            "az": inst.az,
            "od_price": round(node_od_price, 6),
            "current_price": round(node_current_price, 6),
            "lifecycle": "spot" if _is_spot_node else "on-demand",
            "risk": node_risk,
            "vcpu": node_vcpu,
            "memory_gb": node_mem,
        },
        "rebalancer_gate": {
            "eligible_count": _eligible_count,
            "would_launch": {
                "instance_type": _launched_pool.get('instance_type') if _launched_pool else None,
                "az": _launched_pool.get('az') if _launched_pool else None,
                "pass": _launched_pool.get('rebalancer_pass') if _launched_pool else None,
                "savings_pct": _launched_pool.get('savings_pct') if _launched_pool else None,
            } if _launched_pool else None,
        },
        "computed_at": datetime.utcnow().isoformat(),
        "filters_applied": [
            "blacklist", "vcpu", "memory", "architecture", "risk_ceiling",
            "occupancy", "diversification", "allowed_families",
            "allowed_zones", "cross_az", "rebalancer_double_gate",
            "no_join_block", "dry_run_capacity",
        ],
        "filters_removed": {
            "no_join_block": _nojoin_removed,
            "dry_run_fail": _dryrun_removed,
        },
        "total_alternatives": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "alternatives": page_data,
    }


# ── Market View API (Task 4.1) ─────────────────────────────────────────────────

@router.get("/clusters/{cluster_id}/market-view")
def get_market_view(
    cluster_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("final_score"),
    sort_order: str = Query("desc"),
    include_unavailable: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    GET /api/v1/ascpai/clusters/{cluster_id}/market-view
    ?page=1&page_size=20&sort_by=final_score&sort_order=desc&include_unavailable=false

    Returns the full ranked pool list from global_pool_cache for the cluster's
    region, paginated. Includes dry-run capacity status per pool.

    Pool categories:
      verified   — dry_run:pass (capacity confirmed, shown first)
      unverified — not yet checked (shown in ranked order)
      unavailable — dry_run:fail (hidden by default, shown with include_unavailable=true)

    Response:
      source_node: {instance_type, region, od_price}
      pagination: {page, page_size, total_valid_pools, total_evaluated, gates_eliminated}
      pools: paginated slice (each pool includes capacity_status, dry_run_cached_at, dry_run_ttl_remaining)
    """
    from backend.models.cluster import Cluster
    from backend.core.redis_client import key_market_view_cache

    redis = get_redis_client()

    cluster = db.query(Cluster).filter_by(id=cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    region = getattr(cluster, 'region', None) or 'us-east-1'

    # ── Per-cluster resource profile for pool filtering ────────────────────
    # Baseline: highest-cost OD node (maximises displayed savings)
    # Min constraints: smallest node's vCPU / memory (no upper bound)
    from backend.models.instance import Instance, InstanceLifecycle
    from backend.workers.tasks.cache_builder import _lookup_specs as _cb_lookup_specs
    from backend.workers.tasks.cache_builder import _lookup_od_price as _cb_lookup_od
    _running_nodes = (
        db.query(Instance)
        .filter(Instance.cluster_id == cluster_id, Instance.state == 'running')
        .all()
    )
    _node_specs = []
    _primary_instance_type = None
    _baseline_od_price = 0.0
    _baseline_instance_type = None
    if _running_nodes:
        from collections import Counter as _Counter
        _type_counts = _Counter(n.instance_type for n in _running_nodes)
        _primary_instance_type = _type_counts.most_common(1)[0][0]
        for _n in _running_nodes:
            _v, _m, _a, _ = _cb_lookup_specs(_n.instance_type)
            if _v > 0:
                _node_specs.append((_v, _m, _n.architecture or _a))
            # Track the highest OD price node
            _n_od = float(_n.price or 0.0)
            if _n_od <= 0:
                _n_od = _cb_lookup_od(redis, region, _n.instance_type)
            if _n_od > _baseline_od_price:
                _baseline_od_price = _n_od
                _baseline_instance_type = _n.instance_type
    if _node_specs:
        _nv = [s[0] for s in _node_specs]
        _nm = [s[1] for s in _node_specs]
        _na = {s[2] for s in _node_specs}
        _filter_min_vcpu = min(_nv)
        _filter_min_mem  = min(_nm) * 0.5
        _filter_archs = set()
        for _a in _na:
            _filter_archs.add(_a)
            if _a in ('amd64', 'x86_64'):
                _filter_archs.update(('amd64', 'x86_64'))
            elif _a == 'arm64':
                _filter_archs.add('arm64')
    else:
        _filter_min_vcpu = 0
        _filter_min_mem = 0.0
        _filter_archs = set()

    # Load market_view_cache (cache_builder output) — fallback to global_pool_rankings (old pipeline)
    raw = redis.get(key_market_view_cache(region))
    _cache_source = "market_view_cache"
    if not raw:
        raw = redis.get(f"global_pool_rankings:{region}")
        _cache_source = "global_pool_rankings"
    if not raw:
        # Both caches empty — trigger inline compute via PoolRankingService and return that
        try:
            from backend.services.pool_ranking_service import PoolRankingService, NodeTemplate
            _prs = PoolRankingService(db, redis)
            _pools = _prs._get_or_compute_global_rankings(region, 500)
            if _pools:
                raw = redis.get(f"global_pool_rankings:{region}")
        except Exception as _e:
            logger.warning(f"[market-view] Inline compute failed: {_e}")
    if not raw:
        return {
            "cluster_id": cluster_id,
            "region": region,
            "message": "Pool cache not yet built. Run cache_builder task first.",
            "pagination": {"page": page, "page_size": page_size, "total": 0, "total_pages": 0},
            "pools": [],
        }

    payload = _json.loads(raw)
    # Handle both new dict format {data: [...], last_updated: ...}
    # and old list format [...] written by pool_ranking_service
    if isinstance(payload, list):
        all_pools = payload
        last_updated = None
    else:
        all_pools = payload.get('data', [])
        last_updated = payload.get('last_updated')

    # ── Task 5.1: enrich each pool with scoring figures ──────────────────────
    total_evaluated = len(all_pools)

    # Baseline: use highest-cost OD node for savings display & price gate
    from backend.models.cluster_baseline import ClusterBaseline
    source_od_price = _baseline_od_price  # highest OD node price
    baseline_data = None
    source_node = None

    baseline = db.query(ClusterBaseline).filter_by(cluster_id=cluster_id).first()
    if baseline:
        baseline_data = {
            "instance_type": baseline.primary_node_type,
            "node_count": baseline.baseline_od_count or 0,
            "monthly_cost": baseline.baseline_monthly_cost,
            "recorded_at": baseline.computed_at.isoformat() if baseline.computed_at else None,
        }

    if source_od_price > 0 and _baseline_instance_type:
        source_node = {
            "instance_type": _baseline_instance_type,
            "instance_id": "highest_od",
            "region": region,
            "od_price_hr": source_od_price,
            "node_count": len(_running_nodes) if _running_nodes else 0,
            "baseline_method": "highest_cost_od_node",
        }
    elif baseline:
        source_od_price = float(baseline.baseline_monthly_cost / (730 * max(baseline.baseline_od_count or 1, 1)))
        source_node = {
            "instance_type": baseline.primary_node_type,
            "instance_id": "baseline",
            "region": region,
            "od_price_hr": source_od_price,
            "node_count": baseline.baseline_od_count or 0,
            "baseline_method": "cluster_baseline",
        }

    # Normalize and enrich pools with Task 3.1 scoring
    now_utc = datetime.utcnow()
    data_ts = None
    if last_updated:
        try:
            from datetime import timezone
            data_ts = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
        except Exception:
            pass

    _profile = "BALANCED"  # TODO: derive from cluster settings
    _weights = {"savings": 0.40, "risk": 0.40, "ml": 0.20}

    gates_eliminated = 0
    enriched = []
    for p in all_pools:
        p = dict(p)
        p.setdefault('vcpu', 0)
        p.setdefault('memory_gb', 0.0)
        p.setdefault('architecture', 'amd64')
        p.setdefault('blacklisted', False)
        p.setdefault('price_shock', False)

        spot_price = float(p.get('spot_price', 0.0) or 0.0)
        od_price = float(p.get('od_price', p.get('ondemand_price', 0.0)) or 0.0)
        az_irr = float(p.get('interruption_rate_pct', p.get('interruption_rate', 15.0)) or 15.0)
        # risk_probability: 0-1 range (from ONNX or interruption_rate_pct/100)
        risk_prob = float(p.get('risk_probability', az_irr / 100.0) or az_irr / 100.0)
        if risk_prob > 1.0:
            risk_prob = risk_prob / 100.0

        # Skip pools with no valid spot price
        if spot_price <= 0:
            gates_eliminated += 1
            continue

        # ── Per-cluster resource profile gates ──────────────────────────
        if _filter_min_vcpu > 0:
            _pool_vcpu = int(p.get('vcpu', 0) or 0)
            _pool_mem  = float(p.get('memory_gb', 0.0) or 0.0)
            _pool_arch = (p.get('architecture') or 'amd64').lower()
            # Architecture gate
            if _filter_archs and _pool_arch not in _filter_archs:
                gates_eliminated += 1
                continue
            # Minimum vCPU gate (no upper bound — large pools are valid opportunities)
            if _pool_vcpu > 0 and _pool_vcpu < _filter_min_vcpu:
                gates_eliminated += 1
                continue
            # Minimum memory gate (no upper bound)
            if _pool_mem > 0 and _pool_mem < _filter_min_mem:
                gates_eliminated += 1
                continue
        # Price gate: spot must be cheaper than highest OD node price (only positive savings)
        if source_od_price > 0 and spot_price >= source_od_price:
            gates_eliminated += 1
            continue

        # ── Compute savings & expected value ────────────────────────────
        # Intrinsic savings (pool's own OD vs spot — for reference)
        intrinsic = (od_price - spot_price) / od_price if od_price > 0 else 0.0
        # Customer savings (vs baseline highest OD node — primary display metric)
        customer = (source_od_price - spot_price) / source_od_price if source_od_price > 0 else intrinsic
        # Expected value = savings × (1 - risk) — primary ranking metric
        ev = customer * (1.0 - risk_prob)

        p['intrinsic_savings_pct'] = round(intrinsic * 100, 2)
        p['customer_savings_pct'] = round(customer * 100, 2)
        p['customer_savings_monthly_per_node'] = round(max(0.0, (source_od_price - spot_price) * 730), 2)
        p['risk_probability'] = round(risk_prob, 4)
        p['expected_value'] = round(ev, 6)

        # Safety score (legacy compat)
        p['safety_score'] = round(max(0.0, 1.0 - az_irr / 25.0), 4)
        savings_score = max(0.0, min(intrinsic / 0.70, 1.0))
        p['savings_score'] = round(savings_score, 4)

        ml_score = float(p.get('ml_score', 0.5) or 0.5)

        # ── Dry Run capacity status ─────────────────────────────────────
        instance_type_p = p.get('instance_type', '')
        az_p = p.get('az', '')
        capacity_status = 'unverified'
        dry_run_cached_at = None
        dry_run_ttl_remaining = None
        capacity_boost = 1.0
        if instance_type_p and az_p:
            try:
                dr_key = f"dry_run:{instance_type_p}:{az_p}"
                dr_cached = redis.get(dr_key)
                if dr_cached:
                    dr_val = dr_cached.decode() if isinstance(dr_cached, bytes) else dr_cached
                    if dr_val == 'pass':
                        capacity_status = 'verified'
                        capacity_boost = 1.05
                    elif dr_val == 'fail':
                        capacity_status = 'unavailable'
                        capacity_boost = 0.0
                    ttl = redis.ttl(dr_key)
                    dry_run_ttl_remaining = max(0, ttl) if ttl and ttl > 0 else None
                    dry_run_cached_at = now_utc.isoformat()
            except Exception:
                pass

        p['capacity_status'] = capacity_status
        p['dry_run_cached_at'] = dry_run_cached_at
        p['dry_run_ttl_remaining'] = dry_run_ttl_remaining

        # final_score: EV × capacity_boost (for sorting)
        p['final_score'] = round(ev * capacity_boost, 6)

        # Unified score (changes.md §6.1) — multi-signal ranking metric
        _rep_mv = float(p.get('reputation_mult', 1.0) or 1.0)
        _uni_mv = (max(0, customer) * 0.8) * (1.0 - risk_prob) * _rep_mv * capacity_boost
        p['unified_score'] = round(_uni_mv, 6)

        # Data age
        if data_ts:
            age_mins = (now_utc - data_ts.replace(tzinfo=None)).total_seconds() / 60
            p['data_age_minutes'] = round(age_mins, 1)
            p['live'] = age_mins < 90
        else:
            p['data_age_minutes'] = None
            p['live'] = False

        # Filter unavailable pools unless include_unavailable requested
        if capacity_status == 'unavailable' and not include_unavailable:
            gates_eliminated += 1
            continue

        enriched.append(p)

    all_pools = enriched

    # Sort — primary: capacity group, secondary: expected_value DESC (EV ranking)
    _capacity_order = {'verified': 0, 'unverified': 1, 'unavailable': 2}
    valid_sort_keys = {'expected_value', 'final_score', 'unified_score', 'spot_price', 'risk_tier',
                       'interruption_rate_pct', 'intrinsic_savings_pct',
                       'customer_savings_pct', 'ml_score', 'safety_score',
                       'capacity_status', 'risk_probability'}
    if sort_by not in valid_sort_keys:
        sort_by = 'expected_value'
    reverse = (sort_order != "asc")
    try:
        all_pools = sorted(
            all_pools,
            key=lambda p: (
                _capacity_order.get(p.get('capacity_status', 'unverified'), 1),
                -(p.get('expected_value', 0) or 0),
            )
        )
        # Re-sort by explicit column if user explicitly chose one other than default
        if sort_by not in ('expected_value', 'final_score'):
            all_pools = sorted(all_pools, key=lambda p: p.get(sort_by, 0) or 0, reverse=reverse)
    except Exception:
        pass

    # Add rank
    for i, p in enumerate(all_pools):
        p['rank'] = i + 1

    # Capacity stats for response
    verified_count = sum(1 for p in all_pools if p.get('capacity_status') == 'verified')
    unverified_count = sum(1 for p in all_pools if p.get('capacity_status') == 'unverified')
    unavailable_count = sum(1 for p in all_pools if p.get('capacity_status') == 'unavailable')

    # Paginate
    total_valid = len(all_pools)
    start = (page - 1) * page_size
    page_data = all_pools[start:start + page_size]

    return {
        "cluster_id": cluster_id,
        "region": region,
        "last_updated": last_updated,
        "source_node": source_node,
        "baseline": baseline_data,
        "resource_filter": {
            "min_vcpu": _filter_min_vcpu,
            "min_memory_gb": round(_filter_min_mem, 1),
            "architectures": sorted(_filter_archs) if _filter_archs else [],
            "baseline_od_price_hr": round(source_od_price, 6),
            "baseline_instance_type": _baseline_instance_type,
            "baseline_method": "highest_cost_od_node",
        } if _filter_min_vcpu > 0 else None,
        "profile": _profile,
        "weights": _weights,
        "capacity_summary": {
            "verified": verified_count,
            "unverified": unverified_count,
            "unavailable": unavailable_count,
        },
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_valid_pools": total_valid,
            "total_pages": max(1, (total_valid + page_size - 1) // page_size),
            "total_evaluated": total_evaluated,
            "gates_eliminated": gates_eliminated,
        },
        "pools": page_data,
    }


# ── Dry Run Check Trigger ────────────────────────────────────────────────────

@router.post("/clusters/{cluster_id}/dry-run-check")
def trigger_dry_run_check(
    cluster_id: str,
    body: dict,
):
    """
    POST /api/v1/ascpai/clusters/{cluster_id}/dry-run-check

    Triggers background dry run capacity checks for specified pool_keys.

    Body: {"pool_keys": ["t3a.medium:ap-south-1a", ...]}
    Returns: {status: "queued", pool_count: N}

    Frontend calls this when Market View loads for pools with capacity_status = "unverified".
    Results are cached in Redis and reflected on next market-view poll.
    """
    from backend.workers.tasks.dry_run_refresher import run_dry_run_checks

    pool_keys = body.get("pool_keys", [])
    if not pool_keys:
        return {"status": "no_pools", "pool_count": 0}

    run_dry_run_checks.delay(cluster_id, pool_keys)
    return {"status": "queued", "pool_count": len(pool_keys)}


# ── Node Status API (Task 13) ─────────────────────────────────────────────────

@router.get("/clusters/{cluster_id}/nodes/{node_id}/status")
def get_node_status(
    cluster_id: str,
    node_id: str,
    db=Depends(get_db),
):
    """
    GET /api/v1/ascpai/clusters/{cluster_id}/nodes/{node_id}/status

    Returns current cooldown, suppression, and risk state for a node.
    Useful for operators to understand why a node is/isn't being rebalanced.
    """
    from backend.models.instance import Instance
    import json as _jstat
    redis = get_redis_client()

    inst = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.instance_id == node_id,
    ).first()
    if not inst:
        # Also try by node_name
        inst = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.node_name == node_id,
        ).first()
    if not inst:
        return {"error": "node not found"}

    iid = inst.instance_id or node_id
    status = {
        "instance_id": iid,
        "instance_type": inst.instance_type,
        "lifecycle": str(inst.lifecycle),
        "az": inst.az,
        "state": inst.state,
        "cooldowns": {},
        "suppression": {},
        "spot_assertion": False,
    }

    if redis:
        try:
            # Rebalancing cooldown (24h after rebalance)
            cd_key = f"spot:rebalanced:instance:{iid}"
            cd_ttl = redis.ttl(cd_key)
            if cd_ttl > 0:
                status["cooldowns"]["rebalanced"] = {"ttl_seconds": cd_ttl}

            # Post-launch cooldown (60s)
            pl_key = f"spot:post_launch_cooldown:{iid}"
            pl_ttl = redis.ttl(pl_key)
            if pl_ttl > 0:
                status["cooldowns"]["post_launch"] = {"ttl_seconds": pl_ttl}

            # S2S suppression after fallback
            s2s_key = f"spot:s2s_suppressed:{iid}"
            s2s_ttl = redis.ttl(s2s_key)
            if s2s_ttl > 0:
                s2s_val = redis.get(s2s_key)
                status["suppression"]["s2s"] = {
                    "ttl_seconds": s2s_ttl,
                    "reason": (s2s_val.decode() if s2s_val else "suppressed"),
                }

            # Spot assertion key (prevents OD downgrade)
            assert_key = f"spot:asserted_spot:{iid}"
            assert_ttl = redis.ttl(assert_key)
            status["spot_assertion"] = assert_ttl > 0
            if assert_ttl > 0:
                status["cooldowns"]["spot_assertion"] = {"ttl_seconds": assert_ttl}

            # RC3 OD streak counter — must match key written by auto_rebalancer.py
            rc3_key = f"rc3:sync_od_streak:{iid}"
            rc3_val = redis.get(rc3_key)
            if rc3_val:
                status["cooldowns"]["rc3_od_streak"] = {
                    "count": int(rc3_val),
                    "threshold": 3,
                    "ttl_seconds": redis.ttl(rc3_key),
                }
        except Exception as _e:
            status["redis_error"] = str(_e)

    return status


# ── Pool Audit API (Task 4.3) ──────────────────────────────────────────────────

@router.get("/clusters/{cluster_id}/nodes/{node_id}/pool-audit")
def get_pool_audit(
    cluster_id: str,
    node_id: str,
    db: Session = Depends(get_db),
):
    """
    GET /api/v1/ascpai/clusters/{cluster_id}/nodes/{node_id}/pool-audit

    Returns the most recent rejection audit for a specific node:
      raw_pool_count, eligible_count, rejection_reasons (dict), computed_at

    Populated after any call to rank_for_node() for this node.
    TTL: 300s.
    """
    from backend.models.instance import Instance

    redis = get_redis_client()

    # Resolve node to get instance_id for the audit key
    inst = (
        db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.id == node_id,
        ).first()
        or db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.instance_id == node_id,
        ).first()
    )

    # Audit key uses instance_id (or the node_id as fallback)
    audit_node_key = inst.instance_id if inst else node_id

    cached = redis.get(f"pool_audit:{cluster_id}:{audit_node_key}")
    if cached:
        return _json.loads(cached)

    # If no cached audit yet, trigger a rank_for_node call to populate it
    if inst:
        from backend.models.cluster import Cluster
        from backend.services.pool_ranking_service import PoolRankingService as _PRS_audit
        cluster = db.query(Cluster).filter_by(id=cluster_id).first()
        if cluster:
            region = getattr(cluster, 'region', None) or 'us-east-1'
            _prs = _PRS_audit(db, redis)
            _results = _prs.rank_pools_for_node(
                node_info={
                    'instance_type': inst.instance_type,
                    'az': inst.az or '',
                    'od_price': float(inst.price or 0),
                    'instance_id': inst.instance_id,
                },
                cluster_id=cluster_id,
                region=region,
                include_dynamic_filters=True,
            )
            return {
                "cluster_id": cluster_id,
                "node_id": node_id,
                "raw_pool_count": len(_results),
                "eligible_count": len(_results),
                "rejection_reasons": {},
                "computed_at": __import__('datetime').datetime.utcnow().isoformat(),
            }

    return {
        "cluster_id": cluster_id,
        "node_id": node_id,
        "raw_pool_count": 0,
        "eligible_count": 0,
        "rejection_reasons": {},
        "computed_at": None,
        "message": "No audit data yet — pool ranking has not been run for this node.",
    }


# ── Task 5.2 — Savings API ─────────────────────────────────────────────────────

@router.get("/clusters/{cluster_id}/savings")
def get_cluster_savings(
    cluster_id: str,
    db: Session = Depends(get_db),
):
    """
    GET /api/v1/ascpai/clusters/{cluster_id}/savings

    Returns savings anchored to ClusterBaseline (immutable onboarding snapshot).
    Uses actual_spot_price_hr from rebalancing_actions — never estimated values.

    Response includes:
      baseline: {instance_type, node_count, monthly_cost, recorded_at}
      current:  {instance_type, node_count, monthly_cost, spot_price_hr}
      realized_savings: {monthly, pct, annual}
      estimated_vs_realized_gap: {monthly, explanation}
      data_freshness, recalculated
    """
    from backend.models.cluster import Cluster
    from backend.models.cluster_baseline import ClusterBaseline
    from backend.models.rebalancing_action import RebalancingAction
    from backend.models.instance import Instance, InstanceLifecycle

    cluster = db.query(Cluster).filter_by(id=cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # ── Baseline (immutable anchor) ────────────────────────────────────────────
    baseline = db.query(ClusterBaseline).filter_by(cluster_id=cluster_id).first()
    baseline_info = None
    baseline_monthly_cost = None
    if baseline:
        baseline_monthly_cost = float(baseline.baseline_monthly_cost or 0)
        baseline_info = {
            "instance_type": baseline.primary_node_type,
            "node_count": baseline.baseline_od_count,
            "monthly_cost": round(baseline_monthly_cost, 2),
            "recorded_at": baseline.computed_at.isoformat() if baseline.computed_at else None,
        }

    # ── Current state ──────────────────────────────────────────────────────────
    platform_flags = ("platform", "spot-optimizer-direct")
    spot_instances = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.state == 'running',
        Instance.lifecycle == InstanceLifecycle.SPOT,
        Instance.launched_by.in_(platform_flags),
    ).all()

    current_monthly_cost = float(cluster.realized_savings_monthly or 0)  # already computed by savings_calculator
    current_info = {
        "node_count": len(spot_instances),
        "monthly_cost": round(current_monthly_cost, 2),
    }
    if spot_instances:
        current_info["instance_type"] = spot_instances[0].instance_type

    # ── Realized savings ───────────────────────────────────────────────────────
    realized_monthly = float(cluster.realized_savings_monthly or 0)
    realized_pct = 0.0
    if baseline_monthly_cost and baseline_monthly_cost > 0:
        realized_pct = round(realized_monthly / baseline_monthly_cost * 100, 2)

    realized_info = {
        "monthly": round(realized_monthly, 2),
        "pct": realized_pct,
        "annual": round(realized_monthly * 12, 2),
    }

    # ── Estimated vs realized gap ──────────────────────────────────────────────
    # Sum savings_gap_hr × 730 for completed actions with fallback (gap > 0)
    gap_actions = db.query(RebalancingAction).filter(
        RebalancingAction.cluster_id == cluster_id,
        RebalancingAction.status == 'completed',
        RebalancingAction.savings_gap_hr.isnot(None),
        RebalancingAction.savings_gap_hr > 0,
    ).all()

    total_gap_mo = sum(float(a.savings_gap_hr or 0) * 730 for a in gap_actions)
    gap_explanation = None
    if gap_actions:
        gap_explanation = (
            f"Fallback occurred in {len(gap_actions)} action(s) — "
            "actual instance type differed from target pool"
        )

    gap_info = {
        "monthly": round(total_gap_mo, 2),
        "explanation": gap_explanation,
    }

    return {
        "cluster_id": cluster_id,
        "baseline": baseline_info,
        "current": current_info,
        "realized_savings": realized_info,
        "estimated_vs_realized_gap": gap_info,
        "data_freshness": cluster.last_assessed.isoformat() if cluster.last_assessed else None,
        "recalculated": "hourly",
    }


# ── EMA Debug Endpoint ──────────────────────────────────────────────────────
@router.get("/pools/{pool_key}/ema-status")
def get_pool_ema_status(
    pool_key: str,
    db: Session = Depends(get_db),
):
    """Return Global EMA stats for a single pool (debug / observability)."""
    from backend.services.global_ema_service import GlobalEMAService

    redis = get_redis_client()
    stats = GlobalEMAService.get_ema_stats(redis, db, pool_key)
    if stats is None:
        return {"pool_key": pool_key, "ema_tracked": False}

    ema_risk, ema_weight = GlobalEMAService.get_ema_risk(redis, db, pool_key)
    confidence = min(0.95, 1.0 - 0.5 ** (stats.get("count", 0) / 200))

    return {
        "pool_key": pool_key,
        "ema_tracked": True,
        "rate": stats.get("rate", 0),
        "count": stats.get("count", 0),
        "peak_rate": stats.get("peak_rate", 0),
        "last_event": stats.get("last_event"),
        "confidence": round(confidence, 4),
        "ema_risk": round(ema_risk, 4),
        "ema_weight": round(ema_weight, 4),
        "sample_clusters": stats.get("sample_clusters", 0),
    }


# ── Optimized Configuration Endpoints ────────────────────────────────────────


class _NodeAssignment(BaseModel):
    """A single node migration assignment: move this node to a new pool."""
    node_id: str
    target_lifecycle: str = "spot"        # "spot", "on-demand", or "terminate" (pure consolidation)
    target_instance_type: str = ""
    target_az: str = ""


class ApplyRecommendedConfigRequest(BaseModel):
    od_node_count: int
    spot_node_count: int
    buffer_node_count: int
    node_assignments: Optional[List[_NodeAssignment]] = None


def _load_pool_rankings(redis, region: str):
    """Load pool data from Redis (market_view_cache → global_pool_rankings fallback)."""
    import json as _j
    from backend.core.redis_client import key_market_view_cache
    raw = redis.get(key_market_view_cache(region))
    if not raw:
        raw = redis.get(f"global_pool_rankings:{region}")
    if not raw:
        return []
    payload = _j.loads(raw)
    if isinstance(payload, list):
        return payload
    return payload.get("data", [])


@router.get("/clusters/{cluster_id}/recommended-config")
def get_recommended_config(
    cluster_id: str,
    od_node_count: Optional[int] = Query(None),
    spot_node_count: Optional[int] = Query(None),
    buffer_node_count: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Compute the optimal cluster configuration using BFD-TSC placement optimizer.

    Returns:
    - current_state: current node/cost breakdown
    - recommended_state: BFD-TSC optimal placement with savings
    - pod_distribution: stateful vs spot-friendly pod counts
    - adjustable_params: slider min/max/recommended for od/spot/buffer counts
    - warnings: placement constraint warnings
    """
    import json as _j
    from backend.models.cluster import Cluster
    from backend.models.instance import Instance
    from backend.services.cluster_service import ClusterService
    from backend.services.dynamic_instance_helpers import bulk_get_hourly_prices
    from backend.modules.placement_optimizer import (
        PlacementOptimizer, build_pools_from_rankings, pods_from_cluster_detail,
    )

    redis = get_redis_client()

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    region = getattr(cluster, "region", None) or "ap-south-1"

    # ── Load pool rankings ────────────────────────────────────────────────────
    rankings_raw = _load_pool_rankings(redis, region)
    available_azs = list({r.get("az", "") for r in rankings_raw if r.get("az")}) or [f"{region}a", f"{region}b"]
    pools = build_pools_from_rankings(rankings_raw, available_azs)

    # ── Get node/pod detail ───────────────────────────────────────────────────
    svc = ClusterService(db)
    try:
        nodes_data = svc.get_cluster_nodes_detailed(cluster_id, "system")
    except Exception as _e:
        raise HTTPException(status_code=503, detail=f"Could not load cluster nodes: {_e}")

    nodes_detailed = nodes_data.get("nodes", [])
    pod_list = pods_from_cluster_detail(nodes_detailed)

    # ── Current cost ─────────────────────────────────────────────────────────
    _instances = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.state == "running",
    ).all()
    _all_types = list({i.instance_type for i in _instances if i.instance_type})
    HOURLY = bulk_get_hourly_prices(db, redis, _all_types, region)
    current_monthly_cost = sum(
        HOURLY.get(i.instance_type, 0.0) * 730 for i in _instances
    )

    # ── Current node breakdown ────────────────────────────────────────────────
    def _lc_str(inst):
        v = inst.lifecycle
        return (v.value if hasattr(v, 'value') else str(v or 'on-demand')).lower().replace('_', '-')
    _od_count   = sum(1 for i in _instances if 'demand' in _lc_str(i))
    _spot_count = sum(1 for i in _instances if _lc_str(i) == 'spot')
    current_state = {
        "od_nodes": _od_count,
        "spot_nodes": _spot_count,
        "total_nodes": len(_instances),
        "monthly_cost": round(current_monthly_cost, 2),
    }

    # ── Slider params ─────────────────────────────────────────────────────────
    optimizer = PlacementOptimizer(available_pools=pools, available_azs=available_azs)
    adjustable_params = optimizer.compute_adjustable_params(
        pod_list, _od_count, _spot_count, 0
    )

    # ── Resolve node counts (query params override adjustable_params default) ─
    _od = od_node_count if od_node_count is not None else adjustable_params["od_node_count"]["recommended"]
    _spot = spot_node_count if spot_node_count is not None else adjustable_params["spot_node_count"]["recommended"]
    _buf = buffer_node_count if buffer_node_count is not None else adjustable_params["buffer_node_count"]["recommended"]

    # ── Run BFD-TSC ───────────────────────────────────────────────────────────
    result = optimizer.compute_optimal_placement(
        pods=pod_list,
        od_node_count=_od,
        spot_node_count=_spot,
        buffer_node_count=_buf,
        current_monthly_cost=current_monthly_cost,
    )

    stateful_count = sum(1 for p in pod_list if p.is_stateful_by_nature)
    daemonset_count = sum(1 for p in pod_list if p.is_daemonset)
    control_plane_count = sum(1 for p in pod_list if p.is_control_plane)
    misplaced_count = nodes_data.get("misplaced_pods", 0)

    return {
        "cluster_id": cluster_id,
        "current_state": current_state,
        "recommended_state": result.to_dict(),
        "pod_distribution": {
            "total": len(pod_list),
            "stateful_by_nature": stateful_count,
            "spot_friendly": len(pod_list) - stateful_count,
            "daemonsets_skipped": daemonset_count,
            "control_plane_spread": control_plane_count,
            "misplaced": misplaced_count,
        },
        "scheduling_rules": {
            "stateful_pods": {
                "placement": "on-demand ONLY",
                "enforcement": "nodeSelector: karpenter.sh/capacity-type=on-demand",
            },
            "control_plane_pods": {
                "placement": "on-demand, SPREAD across nodes",
                "enforcement": "podAntiAffinity: requiredDuringScheduling",
            },
            "stateless_pods": {
                "placement": "spot preferred, on-demand fallback",
                "enforcement": "affinity: preferredDuringScheduling spot (weight 100)",
            },
            "daemonsets": {
                "placement": "every node (automatic)",
                "enforcement": "Kubernetes DaemonSet controller — no optimizer action",
            },
        },
        "adjustable_params": adjustable_params,
        "warnings": result.warnings,
    }


@router.post("/clusters/{cluster_id}/apply-recommended-config")
def apply_recommended_config(
    cluster_id: str,
    body: ApplyRecommendedConfigRequest,
    db: Session = Depends(get_db),
):
    """
    Apply a recommended configuration by creating staggered RebalancingAction records.

    Each OD→Spot migration is staggered by 30 s to avoid thundering-herd behaviour.
    The auto_rebalancer beat task skips actions whose scheduled_start_at is in the
    future, so the stagger is honoured without any additional worker changes.

    Returns action IDs and an estimated completion timeline.
    """
    from backend.models.cluster import Cluster
    from backend.models.instance import Instance

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    region = getattr(cluster, "region", None) or "ap-south-1"
    now = datetime.utcnow()
    STAGGER_DELAY_SECONDS = 30

    # Determine which nodes to migrate: use explicit assignments or auto-detect OD nodes
    migrations = []
    if body.node_assignments:
        for assignment in body.node_assignments:
            if assignment.target_lifecycle in ("spot", "terminate"):
                migrations.append(assignment)
    else:
        # Auto-detect: pick all on-demand nodes up to the excess (current_od - requested_od)
        od_instances = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.state == "running",
            Instance.lifecycle.in_(["on-demand", None]),
        ).all()
        # Sort by cheapest first to migrate cheapest OD nodes to spot
        od_instances.sort(key=lambda i: i.instance_type or "")
        current_od = len(od_instances)
        excess_od = max(0, current_od - body.od_node_count)

        # ── Consolidation vs Spot-replacement logic ──────────────────────
        # Count current spot nodes to determine if user wants new spots.
        spot_instances = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.state == "running",
            Instance.lifecycle == "spot",
        ).count()
        # How many NEW spot nodes are requested beyond what already exist?
        new_spots_requested = max(0, body.spot_node_count - spot_instances)

        # Assign excess OD: first N go to spot replacement, remainder are
        # pure consolidation (drain to remaining OD → terminate, no spot launch).
        od_to_spot      = min(excess_od, new_spots_requested)
        od_to_terminate  = excess_od - od_to_spot

        for idx, inst in enumerate(od_instances[:excess_od]):
            source_az = inst.az or f"{region}a"
            if idx < od_to_spot:
                # OD→Spot replacement: Karpenter will provision a spot node
                _target_lifecycle = "spot"
            else:
                # Pure consolidation: drain pods to remaining OD nodes, terminate
                _target_lifecycle = "terminate"
            migrations.append(_NodeAssignment(
                node_id=inst.instance_id or inst.node_name or "",
                target_lifecycle=_target_lifecycle,
                target_instance_type=inst.instance_type or "",
                target_az=source_az,
            ))

        logger.info(
            "apply_recommended_config: cluster=%s excess_od=%d od_to_spot=%d "
            "od_to_terminate=%d current_od=%d current_spot=%d requested_od=%d "
            "requested_spot=%d",
            cluster_id, excess_od, od_to_spot, od_to_terminate,
            current_od, spot_instances, body.od_node_count, body.spot_node_count,
        )

    if not migrations:
        return {
            "action_ids": [],
            "message": "No migrations required for the requested configuration.",
            "estimated_timeline_seconds": 0,
        }

    # Cap concurrent migrations to 3 (safe default)
    _max_parallel = min(len(migrations), 3)

    action_ids = []
    for idx, migration in enumerate(migrations):
        # Stagger: group by max_parallel slots
        stagger_group = idx // _max_parallel
        scheduled_at = now + timedelta(seconds=stagger_group * STAGGER_DELAY_SECONDS)

        # Look up the actual instance for source_pool
        _inst = None
        if migration.node_id:
            _inst = db.query(Instance).filter(
                Instance.cluster_id == cluster_id,
                Instance.instance_id == migration.node_id,
            ).first()
            if _inst is None:
                _inst = db.query(Instance).filter(
                    Instance.cluster_id == cluster_id,
                    Instance.node_name == migration.node_id,
                ).first()

        source_az = (
            (_inst.az if _inst else None) or migration.target_az or f"{region}a"
        )
        source_type = (
            (_inst.instance_type if _inst else None) or migration.target_instance_type or "m5.large"
        )
        source_pool = f"{source_type}:{source_az}"

        # Target pool: spot version of the source; caller may override via target_instance_type.
        # If target_lifecycle == "spot", annotate the target pool key so the rebalancer
        # knows this is an OD→Spot migration (not an OD→OD noop).
        target_type = migration.target_instance_type or source_type
        target_az   = migration.target_az or source_az
        target_pool = f"{target_type}:{target_az}"

        # Safety: skip actions where source_pool == target_pool with no lifecycle change.
        # This prevents spurious "Graceful Rebalance / WAITING_AGENT" entries that show
        # "t3.large:ap-south-1a → t3.large:ap-south-1a" when no actual migration is needed.
        _is_noop = (source_pool == target_pool) and (migration.target_lifecycle not in ("spot", "terminate"))
        if _is_noop:
            logger.info(
                "apply_recommended_config: skipping noop action source=%s target=%s lifecycle=%s",
                source_pool, target_pool, migration.target_lifecycle,
            )
            continue

        action = RebalancingAction(
            cluster_id=cluster_id,
            trigger="manual_apply",
            source_pool=source_pool,
            target_pool=target_pool,
            source_instance_id=migration.node_id or None,
            status="in_progress",
            started_at=now,
            action_metadata={
                "initiated_by": "apply_recommended_config",
                "od_node_count": body.od_node_count,
                "spot_node_count": body.spot_node_count,
                "buffer_node_count": body.buffer_node_count,
                "scheduled_start_at": scheduled_at.isoformat(),
                "stagger_group": stagger_group,
                "target_lifecycle": migration.target_lifecycle,
            },
        )
        db.add(action)
        db.flush()
        action_ids.append(action.id)

    db.commit()

    estimated_groups = max(1, math.ceil(len(migrations) / _max_parallel))
    estimated_timeline = estimated_groups * STAGGER_DELAY_SECONDS + 600  # +10 min per migration

    return {
        "action_ids": action_ids,
        "message": f"Queued {len(migrations)} migration(s) with {_max_parallel} concurrent max.",
        "estimated_timeline_seconds": estimated_timeline,
    }


@router.get("/clusters/{cluster_id}/recommended-config/yaml")
def get_recommended_config_yaml(
    cluster_id: str,
    db: Session = Depends(get_db),
):
    """
    Generate Karpenter NodePool YAML for the cluster.

    Behaviour depends on cluster optimization settings:
    - Both auto_rebalance AND auto_rightsizing OFF (or not installed):
        Returns a single permissive on-demand NodePool that lets Karpenter
        handle scheduling and consolidation normally — no spot, no tight
        resource limits, WhenEmpty consolidation only.  This prevents the
        "17/17 pods: Node pod capacity exhausted" issue caused by small
        t3.medium instances being the only type in a restrictive NodePool.
    - Either feature ON:
        Returns BFD-TSC optimised two-NodePool layout (stateful-od +
        stateless-spot) with realistic headroom limits.
    """
    import json as _j
    import math as _math
    from fastapi.responses import Response
    from backend.models.cluster import Cluster, ClusterOptimizationSettings
    from backend.models.instance import Instance
    from backend.services.cluster_service import ClusterService
    from backend.services.dynamic_instance_helpers import bulk_get_hourly_prices
    from backend.modules.placement_optimizer import (
        PlacementOptimizer, build_pools_from_rankings, pods_from_cluster_detail,
    )

    redis = get_redis_client()

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    region = getattr(cluster, "region", None) or "ap-south-1"
    cluster_name = getattr(cluster, "name", cluster_id)

    # ── Check feature flags ────────────────────────────────────────────────────
    _opt = db.query(ClusterOptimizationSettings).filter_by(cluster_id=cluster_id).first()
    _rebalance_on   = bool(_opt and getattr(_opt, "auto_rebalance_enabled", False))
    _rightsizing_on = bool(_opt and getattr(_opt, "auto_rightsizing_enabled", False))
    _optimize_active = _rebalance_on or _rightsizing_on

    # ── AZ list (used in all modes) ────────────────────────────────────────────
    rankings_raw = _load_pool_rankings(redis, region)
    available_azs = sorted(
        {r.get("az", "") for r in rankings_raw if r.get("az")}
    ) or [f"{region}a", f"{region}b", f"{region}c"]
    az_list_yaml = "\n".join(f'        - "{az}"' for az in available_azs)

    # General-purpose instance types: xlarge+ chosen so that AWS CNI can
    # assign ≥58 pods per node (avoids the 17/17 ENI exhaustion on t3.medium).
    # Karpenter will pick the best-fit type from this list at launch time.
    _GP_INSTANCES = [
        "m5.large",  "m5.xlarge",  "m5.2xlarge",  "m5.4xlarge",
        "m5a.large", "m5a.xlarge", "m5a.2xlarge", "m5a.4xlarge",
        "m6i.large", "m6i.xlarge", "m6i.2xlarge", "m6i.4xlarge",
        "m6a.large", "m6a.xlarge", "m6a.2xlarge",
        "c5.large",  "c5.xlarge",  "c5.2xlarge",  "c5.4xlarge",
        "c6i.large", "c6i.xlarge", "c6i.2xlarge",
        "r5.large",  "r5.xlarge",  "r5.2xlarge",
        "r6i.large", "r6i.xlarge",
    ]
    _gp_yaml = "\n".join(f'        - "{t}"' for t in _GP_INSTANCES)

    # ════════════════════════════════════════════════════════════════════════════
    # NORMAL MODE  –  both features OFF
    # Single on-demand NodePool; Karpenter manages consolidation independently.
    # WhenEmpty consolidation only — avoids disrupting running pods.
    # No tight limits — the cluster can scale out freely when pods need capacity.
    # ════════════════════════════════════════════════════════════════════════════
    if not _optimize_active:
        yaml_doc = f"""\
# Generated by Spot Optimizer — Normal Karpenter Mode
# Both auto-rebalancing and auto-rightsizing are DISABLED.
# Karpenter will provision on-demand nodes from a broad instance family list,
# consolidate only when nodes are fully empty, and scale freely.
#
# Cluster: {cluster_name} ({cluster_id})
# Region:  {region}
---
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: default
  namespace: karpenter
spec:
  template:
    spec:
      nodeClassRef:
        apiVersion: karpenter.k8s.aws/v1beta1
        kind: EC2NodeClass
        name: default
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: topology.kubernetes.io/zone
          operator: In
          values:
{az_list_yaml}
        # Broad instance-type list: xlarge+ avoids the 17-pod ENI limit
        # present on t3.medium/t3.small and similar micro/small types.
        - key: node.kubernetes.io/instance-type
          operator: In
          values:
{_gp_yaml}
  # Generous headroom: allows the cluster to grow up to 200 vCPU / 800 GiB.
  # Increase if you have larger workloads.
  limits:
    cpu: 200
    memory: 800Gi
  disruption:
    # WhenEmpty: only reclaim nodes that have no workload pods — never
    # evict running pods just to bin-pack. This is the safest setting when
    # the spot optimizer is not active.
    consolidationPolicy: WhenEmpty
    consolidateAfter: 30s
"""
        return Response(content=yaml_doc, media_type="application/x-yaml")

    # ════════════════════════════════════════════════════════════════════════════
    # OPTIMIZED MODE  –  at least one feature ON  (BFD-TSC two-NodePool layout)
    # ════════════════════════════════════════════════════════════════════════════
    pools = build_pools_from_rankings(rankings_raw, available_azs)

    svc = ClusterService(db)
    try:
        nodes_data = svc.get_cluster_nodes_detailed(cluster_id, "system")
    except Exception as _e:
        raise HTTPException(status_code=503, detail=f"Could not load cluster nodes: {_e}")

    nodes_detailed = nodes_data.get("nodes", [])
    pod_list = pods_from_cluster_detail(nodes_detailed)

    _instances = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.state == "running",
    ).all()
    _all_types = list({i.instance_type for i in _instances if i.instance_type})
    HOURLY = bulk_get_hourly_prices(db, redis, _all_types, region)
    current_monthly_cost = sum(HOURLY.get(i.instance_type, 0.0) * 730 for i in _instances)

    def _lc_str2(inst):
        v = inst.lifecycle
        return (v.value if hasattr(v, 'value') else str(v or 'on-demand')).lower().replace('_', '-')
    _od_count   = sum(1 for i in _instances if 'demand' in _lc_str2(i))
    _spot_count = sum(1 for i in _instances if _lc_str2(i) == 'spot')

    optimizer = PlacementOptimizer(available_pools=pools, available_azs=available_azs)
    params = optimizer.compute_adjustable_params(pod_list, _od_count, _spot_count, 0)
    _od   = params["od_node_count"]["recommended"]
    _spot = params["spot_node_count"]["recommended"]
    _buf  = params["buffer_node_count"]["recommended"]

    result = optimizer.compute_optimal_placement(
        pods=pod_list,
        od_node_count=_od,
        spot_node_count=_spot,
        buffer_node_count=_buf,
        current_monthly_cost=current_monthly_cost,
    )

    # ── Instance types: seed from BFD-TSC result, expand with size variants
    # so Karpenter has flex when a specific type is unavailable, and can pick
    # a larger node when pod capacity on a smaller instance would be exhausted.
    def _expand_instance_types(base_types: list, fallbacks: list) -> list:
        """Return base types + their 2xlarge/4xlarge siblings + fallbacks."""
        expanded = set(base_types)
        for t in list(base_types):
            if "." in t:
                family, _size = t.split(".", 1)
                expanded.update({f"{family}.xlarge", f"{family}.2xlarge", f"{family}.4xlarge"})
        expanded.update(fallbacks)
        return sorted(expanded)

    od_base    = list({n.pool.instance_type for n in result.od_nodes + result.buffer_nodes}) or ["m5.xlarge"]
    spot_base  = list({n.pool.instance_type for n in result.spot_nodes}) or ["m5.xlarge", "m5a.xlarge", "c5.xlarge"]
    _od_fallbacks   = ["m5.xlarge", "m5.2xlarge", "m6i.xlarge", "m6i.2xlarge"]
    _spot_fallbacks = ["m5.xlarge", "m5a.xlarge", "c5.xlarge", "m6i.xlarge", "m6a.xlarge"]

    od_types   = _expand_instance_types(od_base, _od_fallbacks)
    spot_types = _expand_instance_types(spot_base, _spot_fallbacks)

    od_types_yaml   = "\n".join(f'        - "{t}"' for t in od_types)
    spot_types_yaml = "\n".join(f'        - "{t}"' for t in spot_types)

    # ── Limits: headroom = 3× recommended counts so Karpenter can scale out
    # during rollouts or burst without hitting a hard wall.
    _total_nodes   = len(_instances) or 1
    _od_cpu_limit  = max(_od * 3, _total_nodes + 4) * 4   # vCPU
    _od_mem_limit  = max(_od * 3, _total_nodes + 4) * 16  # GiB
    _sp_cpu_limit  = max((_spot + _buf) * 3, _total_nodes + 4) * 4
    _sp_mem_limit  = max((_spot + _buf) * 3, _total_nodes + 4) * 16

    yaml_doc = f"""\
# Generated by Spot Optimizer — Optimized Configuration
# Cluster: {cluster_name} ({cluster_id})
# Region:  {region}
# Mode:    {'rebalance+rightsizing' if (_rebalance_on and _rightsizing_on) else 'rebalance' if _rebalance_on else 'rightsizing'}
#
# Architecture:
#   stateful-od:    On-demand only.  Stateful workloads (DBs, PVC) + control plane.
#                   Use nodeSelector: karpenter.sh/capacity-type=on-demand
#   stateless-spot: Spot preferred.  Stateless apps (API, frontend, workers).
#                   Use affinity: preferredDuringScheduling spot.
#   Weight 5 > 10 means Karpenter prefers spot for new pods (lower = preferred).
---
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: stateful-od
  namespace: karpenter
  labels:
    spot-optimizer/role: stateful-od
spec:
  # Weight 5: lower priority — stateful pods arrive here only when they
  # explicitly set nodeSelector: karpenter.sh/capacity-type=on-demand.
  weight: 5
  template:
    metadata:
      labels:
        spot-optimizer/lifecycle: on-demand
        spot-optimizer/role: stateful-od
    spec:
      nodeClassRef:
        apiVersion: karpenter.k8s.aws/v1beta1
        kind: EC2NodeClass
        name: default
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: topology.kubernetes.io/zone
          operator: In
          values:
{az_list_yaml}
        - key: node.kubernetes.io/instance-type
          operator: In
          values:
{od_types_yaml}
  limits:
    cpu: {_od_cpu_limit}
    memory: {_od_mem_limit}Gi
  disruption:
    consolidationPolicy: WhenEmpty
    consolidateAfter: 30s
---
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: stateless-spot
  namespace: karpenter
  labels:
    spot-optimizer/role: stateless-spot
spec:
  # Weight 10: higher priority — pods without explicit nodeSelector land on
  # spot (preferred). Stateless workloads default here for cost savings.
  weight: 10
  template:
    metadata:
      labels:
        spot-optimizer/lifecycle: spot
        spot-optimizer/role: stateless-spot
    spec:
      nodeClassRef:
        apiVersion: karpenter.k8s.aws/v1beta1
        kind: EC2NodeClass
        name: default
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot"]
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: topology.kubernetes.io/zone
          operator: In
          values:
{az_list_yaml}
        - key: node.kubernetes.io/instance-type
          operator: In
          values:
{spot_types_yaml}
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              spot-optimizer/lifecycle: spot
  limits:
    cpu: {_sp_cpu_limit}
    memory: {_sp_mem_limit}Gi
  disruption:
    consolidationPolicy: WhenUnderutilized
    consolidateAfter: 120s
"""

    return Response(content=yaml_doc, media_type="application/x-yaml")
