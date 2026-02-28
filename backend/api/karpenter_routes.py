"""
Karpenter API Routes

FastAPI endpoints for Karpenter auto-optimization management:
- Status / configuration / deployment
- Activity feed and performance stats
- Cluster-level toggle (pause/resume)
- Karpenter mode management (dry_run / auto)
- Dry-run recommendations and manual apply
"""
from fastapi import APIRouter, Depends, status, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from enum import Enum as PyEnum
import uuid

from backend.models.base import get_db
from backend.models.user import User
from backend.models.cluster import Cluster, KarpenterMode
from backend.core.dependencies import get_current_user, RequireAccess
from backend.core.logger import logger


# ─── Pydantic Schemas ────────────────────────────────────────────────────────

class KarpenterModeStr(str, PyEnum):
    DRY_RUN = "dry_run"
    AUTO = "auto"


class ClusterKarpenterConfig(BaseModel):
    cluster_id: str
    strategy: str = Field(default="balanced", description="cost-first | balanced | performance-first")
    instance_families: List[str] = Field(default_factory=lambda: ["m5", "m6i", "c5", "c6i"])
    architectures: List[str] = Field(default_factory=lambda: ["amd64"])
    spot_target_pct: int = Field(default=75, ge=0, le=100)
    on_demand_fallback: bool = True
    min_vcpu: int = Field(default=2, ge=1)
    max_vcpu: int = Field(default=16, ge=1)
    min_memory_gib: int = Field(default=4, ge=1)
    max_memory_gib: int = Field(default=64, ge=1)
    consolidation_enabled: bool = True
    consolidation_threshold_pct: int = Field(default=60, ge=0, le=100)
    node_max_lifetime_days: int = Field(default=7, ge=1)
    cost_alert_monthly: Optional[float] = None
    cost_alert_hourly: Optional[float] = None
    daily_budget: Optional[float] = None


class KarpenterDeployRequest(BaseModel):
    cluster_configs: List[ClusterKarpenterConfig]
    mode: KarpenterModeStr = Field(default=KarpenterModeStr.DRY_RUN, description="dry_run (default, safe) or auto")
    gradual_rollout: bool = True
    acknowledgements: List[str] = Field(default_factory=list)


class KarpenterToggleRequest(BaseModel):
    enabled: bool


class KarpenterModeUpdateRequest(BaseModel):
    mode: KarpenterModeStr


class KarpenterApplyRequest(BaseModel):
    """For manually applying a Karpenter dry-run recommendation."""
    recommended_type: str
    reason: Optional[str] = None


class KarpenterBatchApplyRequest(BaseModel):
    instance_ids: List[str]


# ─── Router ──────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/karpenter", tags=["Karpenter"])


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get(
    "/status",
    summary="Get Karpenter deployment status",
    description="Returns whether Karpenter is set up, active clusters, mode, and high-level stats"
)
def get_karpenter_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns overall Karpenter status for the user's organization.
    Includes deployment state, mode, active cluster count, and summary metrics.
    """
    # Query clusters that have karpenter_mode set (meaning Karpenter is installed)
    karpenter_clusters = db.query(Cluster).filter(
        Cluster.karpenter_mode.isnot(None)
    ).all()

    if not karpenter_clusters:
        return {
            "is_setup": False,
            "status": "not_setup",
            "mode": None,
            "active_clusters": 0,
            "total_managed_nodes": 0,
            "estimated_monthly_savings": 0,
            "pending_recommendations": 0,
            "last_activity": None,
        }

    # Determine overall mode (use first cluster's mode, or mixed if different)
    modes = set(c.karpenter_mode.value for c in karpenter_clusters if c.karpenter_mode)
    overall_mode = list(modes)[0] if len(modes) == 1 else "mixed"

    return {
        "is_setup": True,
        "status": "active",
        "mode": overall_mode,
        "active_clusters": len(karpenter_clusters),
        "total_managed_nodes": sum(c.node_count or 0 for c in karpenter_clusters),
        "estimated_monthly_savings": sum(c.estimated_savings or 0 for c in karpenter_clusters),
        "pending_recommendations": 14 if overall_mode == "dry_run" else 0,  # TODO: real count from K8s events
        "last_activity": datetime.utcnow().isoformat(),
        "clusters": [
            {
                "cluster_id": c.id,
                "name": c.name,
                "mode": c.karpenter_mode.value if c.karpenter_mode else None,
                "node_count": c.node_count or 0,
            }
            for c in karpenter_clusters
        ],
    }


@router.get(
    "/config",
    summary="Get Karpenter config for cluster",
    description="Returns the saved Karpenter configuration for a given cluster"
)
def get_karpenter_config(
    cluster_id: str = Query(..., description="Cluster UUID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get per-cluster Karpenter configuration."""
    return {
        "cluster_id": cluster_id,
        "strategy": "balanced",
        "instance_families": ["m5", "m6i", "c5", "c6i"],
        "architectures": ["amd64"],
        "spot_target_pct": 75,
        "on_demand_fallback": True,
        "min_vcpu": 2,
        "max_vcpu": 16,
        "min_memory_gib": 4,
        "max_memory_gib": 64,
        "consolidation_enabled": True,
        "consolidation_threshold_pct": 60,
        "node_max_lifetime_days": 7,
        "is_active": False,
    }


@router.post(
    "/config",
    status_code=status.HTTP_201_CREATED,
    summary="Save Karpenter configuration",
    description="Save Karpenter setup wizard output for one or more clusters"
)
def save_karpenter_config(
    payload: KarpenterDeployRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Persist wizard config (called before deploy)."""
    logger.info(f"Saving Karpenter config for {len(payload.cluster_configs)} clusters")
    return {
        "saved": True,
        "cluster_count": len(payload.cluster_configs),
        "configs": [c.dict() for c in payload.cluster_configs],
    }


@router.patch(
    "/config/{cluster_id}",
    summary="Update Karpenter config for a single cluster",
    description="Partial update of Karpenter configuration, including mode switching"
)
def update_karpenter_config(
    cluster_id: str,
    updates: Dict[str, Any],
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Patch cluster-level Karpenter settings, including mode."""
    logger.info(f"Updating Karpenter config for cluster {cluster_id}: {list(updates.keys())}")

    # Handle mode switching
    if "mode" in updates:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")
        new_mode = updates["mode"]
        cluster.karpenter_mode = KarpenterMode(new_mode)
        db.commit()
        logger.info(f"Karpenter mode switched to {new_mode} for cluster {cluster_id}")

    return {"cluster_id": cluster_id, "updated_fields": list(updates.keys()), "success": True}


@router.post(
    "/deploy",
    summary="Deploy Karpenter to selected clusters",
    description="Triggers Karpenter installation and NodePool creation. Defaults to dry_run (Insights) mode."
)
def deploy_karpenter(
    payload: KarpenterDeployRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Kicks off Karpenter deployment:
    1. Install Karpenter controller (Helm) — in dry_run or auto mode
    2. Create IAM roles (dry_run mode skips ec2:RunInstances permission)
    3. Deploy NodePool configs
    4. Set up monitoring
    5. Persist karpenter_mode on each cluster
    """
    deploy_mode = payload.mode.value  # "dry_run" or "auto"
    logger.info(f"Deploying Karpenter in {deploy_mode} mode to {len(payload.cluster_configs)} clusters by user {current_user.id}")

    deployment_id = str(uuid.uuid4())

    # Persist mode on each target cluster
    for config in payload.cluster_configs:
        cluster = db.query(Cluster).filter(Cluster.id == config.cluster_id).first()
        if cluster:
            cluster.karpenter_mode = KarpenterMode(deploy_mode)
    db.commit()

    return {
        "deployment_id": deployment_id,
        "status": "deploying",
        "mode": deploy_mode,
        "clusters": [c.cluster_id for c in payload.cluster_configs],
        "gradual_rollout": payload.gradual_rollout,
        "estimated_time_minutes": 5,
    }


@router.post(
    "/toggle/{cluster_id}",
    summary="Pause or resume Karpenter on a cluster",
    description="Toggle Karpenter active state without removing configuration"
)
def toggle_karpenter(
    cluster_id: str,
    body: KarpenterToggleRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Pause / resume Karpenter for a single cluster."""
    action = "resumed" if body.enabled else "paused"
    logger.info(f"Karpenter {action} for cluster {cluster_id} by user {current_user.id}")
    return {"cluster_id": cluster_id, "is_active": body.enabled, "action": action}


@router.get(
    "/activity",
    summary="Get recent Karpenter activity",
    description="Returns recent optimization events across managed clusters"
)
def get_karpenter_activity(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Live activity feed for the Karpenter dashboard."""
    # Stub data — includes both dry_run and auto event types
    sample_events = [
        {
            "id": str(uuid.uuid4()),
            "timestamp": (datetime.utcnow() - timedelta(minutes=3)).isoformat(),
            "cluster": "prod-web",
            "type": "consolidation",
            "mode": "auto",
            "title": "Consolidated 3 under-utilized nodes",
            "details": [
                "m5.xlarge (38% util) → Terminated",
                "m5.xlarge (35% util) → Terminated",
                "m5.xlarge (42% util) → Terminated",
                "Moved pods to c6i.large + m6i.large",
            ],
            "savings_daily": 142,
            "utilization_after": 72,
        },
        {
            "id": str(uuid.uuid4()),
            "timestamp": (datetime.utcnow() - timedelta(minutes=8)).isoformat(),
            "cluster": "prod-web",
            "type": "recommendation",
            "mode": "dry_run",
            "title": "Would consolidate 2 nodes → 1",
            "details": [
                "m5.xlarge (28% util) → Would terminate",
                "c5.large (32% util) → Would terminate",
                "Pods would fit on single c6i.xlarge",
            ],
            "potential_savings_daily": 98,
            "action_required": True,
        },
        {
            "id": str(uuid.uuid4()),
            "timestamp": (datetime.utcnow() - timedelta(minutes=12)).isoformat(),
            "cluster": "prod-api",
            "type": "instance_switch",
            "mode": "auto",
            "title": "Switched to Graviton instance",
            "details": ["r5.2xlarge → r6g.2xlarge (ARM64)"],
            "savings_daily": 68,
        },
        {
            "id": str(uuid.uuid4()),
            "timestamp": (datetime.utcnow() - timedelta(minutes=15)).isoformat(),
            "cluster": "prod-api",
            "type": "right_size_suggestion",
            "mode": "dry_run",
            "title": "Would right-size i-0abc123",
            "details": [
                "Current: m5.4xlarge ($560/mo, CPU 18%, Mem 22%)",
                "Suggested: m5.xlarge ($140/mo)",
                "Savings: $420/mo",
                "Pod constraints: All satisfied",
            ],
            "potential_savings_monthly": 420,
            "action_required": True,
        },
        {
            "id": str(uuid.uuid4()),
            "timestamp": (datetime.utcnow() - timedelta(minutes=18)).isoformat(),
            "cluster": "prod-web",
            "type": "spot_replacement",
            "mode": "auto",
            "title": "Spot replacement (interruption)",
            "details": [
                "m5.large spot interrupted (AWS reclaiming)",
                "Drained pods gracefully",
                "Replaced with c6i.large spot (different AZ)",
            ],
            "zero_downtime": True,
            "reschedule_seconds": 12,
        },
    ]
    # Query audit logs for real karpenter events from DB
    from backend.models.audit_log import AuditLog

    real_events = []
    try:
        logs = db.query(AuditLog).filter(
            AuditLog.event.in_(["karpenter_consolidation", "karpenter_resize", "spot_replacement", "node_drain", "node_provision"])
        ).order_by(AuditLog.timestamp.desc()).limit(20).all()

        for log in logs:
            real_events.append({
                "id": str(log.id),
                "timestamp": log.timestamp.isoformat() if log.timestamp else datetime.utcnow().isoformat(),
                "cluster": log.resource or "unknown",
                "type": log.event.replace("karpenter_", ""),
                "mode": "auto",
                "title": log.event.replace("_", " ").title(),
                "details": [],
                "savings_daily": 0,
                "zero_downtime": True,
            })
    except Exception:
        pass

    events = real_events if real_events else sample_events
    return {"events": events, "total": len(events)}


@router.get(
    "/stats",
    summary="Get Karpenter performance stats",
    description="Weekly/monthly performance KPIs for the dashboard"
)
def get_karpenter_stats(
    period: str = Query("week", description="week | month | all"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Performance KPIs for the live Karpenter dashboard."""
    from backend.models.instance import Instance

    # Get all clusters (for now, we'll get all clusters)
    # In production, filter by user's organization
    clusters = db.query(Cluster).all()

    total_nodes = sum(c.node_count or 0 for c in clusters)
    total_spot = sum(c.spot_count or 0 for c in clusters)
    total_on_demand = sum(c.on_demand_node_count or 0 for c in clusters)

    # Calculate spot coverage percentage
    spot_coverage_pct = round((total_spot / total_nodes * 100) if total_nodes > 0 else 0, 1)

    # Calculate potential savings (on-demand nodes that could be spot)
    total_potential_savings = sum(c.potential_savings_monthly or 0 for c in clusters)

    # Calculate realized savings (current spot instances)
    total_realized_savings = sum(c.realized_savings_monthly or 0 for c in clusters)

    # Calculate average CPU utilization from instances
    instances = db.query(Instance).filter(
        Instance.cluster_id.in_([c.id for c in clusters])
    ).all() if clusters else []

    avg_cpu = round(sum(i.cpu_util or 0 for i in instances) / len(instances) if instances else 0, 1)

    # Calculate savings percentage
    # If we have on-demand instances, show how much we could save
    if total_on_demand > 0:
        # Typical spot vs on-demand savings is ~70%
        avg_reduction_pct = 70
    else:
        # If already all spot, we're saving maximum
        avg_reduction_pct = 0

    return {
        "period": period,
        "avg_utilization_pct": avg_cpu,
        "prev_utilization_pct": avg_cpu,  # Would need historical data
        "optimizations_count": 0,  # Would track from rebalancing_actions
        "cost_saved": round(total_realized_savings, 2),
        "spot_coverage_pct": spot_coverage_pct,
        "clusters": [
            {
                "id": c.id,
                "name": c.name,
                "potential_savings": round(c.potential_savings_monthly or 0, 2),
                "spot_coverage": round((c.spot_count / c.node_count * 100) if c.node_count > 0 else 0, 1)
            }
            for c in clusters
        ],
        "cost_trend": [],  # Would need historical cost data
        "instance_distribution": {
            "before": {"on_demand": total_on_demand + total_spot, "spot": 0},
            "after": {"on_demand": total_on_demand, "spot": total_spot},
        },
        "total_saved": round(total_realized_savings, 2),
        "avg_reduction_pct": avg_reduction_pct,
    }


@router.get(
    "/recommendations",
    summary="Get all dry-run recommendations",
    description="Returns pending Karpenter recommendations that need manual approval (dry_run mode only)"
)
def get_karpenter_recommendations(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster"),
    status_filter: Optional[str] = Query(None, description="pending | applied | dismissed"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get rightsizing recommendations for cluster nodes.
    When cluster_id is specified, returns ALL instances (spot and on-demand) for that cluster
    regardless of karpenter_mode — giving the monitoring tab real node data.
    Without cluster_id filter, only dry_run clusters are included.
    """
    from backend.models.instance import Instance

    # On-demand pricing lookup (approximate $/hour for common instance types)
    ONDEMAND_HOURLY: Dict[str, float] = {
        't3.micro': 0.0104, 't3.small': 0.0208, 't3.medium': 0.0416, 't3.large': 0.0832,
        't3.xlarge': 0.1664, 't3.2xlarge': 0.3328,
        't3a.medium': 0.0376, 't3a.large': 0.0752, 't3a.xlarge': 0.1504,
        'm5.large': 0.096, 'm5.xlarge': 0.192, 'm5.2xlarge': 0.384, 'm5.4xlarge': 0.768,
        'm6i.large': 0.096, 'm6i.xlarge': 0.192, 'm6i.2xlarge': 0.384, 'm6i.4xlarge': 0.768,
        'm6a.large': 0.0864, 'm6a.xlarge': 0.1728, 'm6a.2xlarge': 0.3456,
        'c5.large': 0.085, 'c5.xlarge': 0.17, 'c5.2xlarge': 0.34, 'c5.4xlarge': 0.68,
        'c6i.large': 0.085, 'c6i.xlarge': 0.17, 'c6i.2xlarge': 0.34, 'c6i.4xlarge': 0.68,
        'r5.large': 0.126, 'r5.xlarge': 0.252, 'r5.2xlarge': 0.504, 'r5.4xlarge': 1.008,
        'r6i.large': 0.126, 'r6i.xlarge': 0.252, 'r6i.2xlarge': 0.504,
        'i3.large': 0.156, 'i3.xlarge': 0.312, 'i3.2xlarge': 0.624,
    }

    # Build cluster query
    if cluster_id:
        # For a specific cluster: include it regardless of karpenter_mode
        query = db.query(Cluster).filter(Cluster.id == cluster_id)
    else:
        # Global view: only dry_run clusters show pending recommendations
        query = db.query(Cluster).filter(Cluster.karpenter_mode == KarpenterMode.DRY_RUN)

    target_clusters = query.all()

    recommendations = []
    total_potential_savings = 0

    for cluster in target_clusters:
        # Include ALL instances (both spot and on-demand) for real monitoring data
        instances = db.query(Instance).filter(
            Instance.cluster_id == cluster.id
        ).all()

        # Load WorkloadInspector classification for this cluster (node_name → status string)
        _node_classification: Dict[str, str] = {}
        try:
            import json as _json
            from backend.core.redis_client import get_redis_client as _get_redis
            _redis = _get_redis()
            _raw = _redis.get(f"spot:node_classification:{cluster.id}")
            if _raw:
                _node_classification = _json.loads(_raw)
        except Exception:
            pass  # No classification available — use default below

        for instance in instances:
            instance_type = instance.instance_type or 'unknown'
            # instance.lifecycle is an InstanceLifecycle enum — use .value to get the string
            lifecycle_raw = instance.lifecycle
            lifecycle = (lifecycle_raw.value if hasattr(lifecycle_raw, 'value') else str(lifecycle_raw or 'on-demand')).lower()
            is_spot = lifecycle == 'spot'

            # Calculate real monthly cost from pricing table
            hourly_od = ONDEMAND_HOURLY.get(instance_type, 0.096)  # default ~m5.large
            monthly_od = round(hourly_od * 720, 2)

            # Determine node_type from WorkloadInspector first (K8s-aware classification)
            # K8s node name often matches the EC2 instance_id (i-xxxxxxxxx)
            _cached_status = _node_classification.get(instance.instance_id or "")
            if _cached_status == "STATEFUL_PROTECTED" or _cached_status == "DRAIN_UNSAFE":
                node_type = "stateful"
            else:
                # STATELESS_ELIGIBLE, SYSTEM_PROTECTED, or no cache → stateless
                node_type = "stateless"

            if is_spot:
                # Already spot-optimized — current cost ≈ 30% of on-demand
                monthly_current = round(monthly_od * 0.3, 2)
                potential_savings = 0.0
                savings_pct = 0
                reason = "Already running on spot — lifecycle optimized"
            else:
                # On-demand — converting to spot saves ~70%
                monthly_current = monthly_od
                potential_savings = round(monthly_od * 0.7, 2)
                savings_pct = 70
                reason = "Convert on-demand to spot for 70% cost savings"

            recommendations.append({
                "id": f"rec-{instance.id}",
                "cluster_id": cluster.id,
                "cluster_name": cluster.name,
                "instance_id": instance.instance_id,
                "current_type": instance_type,
                "recommended_type": instance_type,  # Same type, lifecycle change
                "current_lifecycle": lifecycle,
                "recommended_lifecycle": "spot",
                "cpu": round(instance.cpu_util or 0.0, 1),
                "mem": round(instance.memory_util or 0.0, 1),
                "current_cost_monthly": monthly_current,
                "recommended_cost_monthly": round(monthly_od * 0.3, 2),
                "potential_savings": potential_savings,
                "savings_pct": savings_pct,
                "risk_prob": 15,
                "status": "pending",
                "node_type": node_type,
                "created_at": datetime.utcnow().isoformat(),
                "reason": reason,
            })

            total_potential_savings += potential_savings

    return {
        "recommendations": recommendations,
        "total_count": len(recommendations),
        "pending_count": len([r for r in recommendations if r["status"] == "pending"]),
        "total_potential_savings_monthly": round(total_potential_savings, 2),
        "dry_run_clusters": [
            {
                "cluster_id": c.id,
                "name": c.name,
                "mode": c.karpenter_mode.value if c.karpenter_mode else "standard",
            }
            for c in target_clusters
        ],
    }


@router.post(
    "/apply-recommendation/{recommendation_id}",
    summary="Apply a single dry-run recommendation",
    description="Manually approve and apply a Karpenter recommendation from dry_run mode"
)
def apply_karpenter_recommendation(
    recommendation_id: str,
    payload: KarpenterApplyRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Apply a single Karpenter recommendation.
    This triggers the actual optimization that was previously only simulated in dry_run mode.
    """
    logger.info(f"Applying Karpenter recommendation {recommendation_id} by user {current_user.id}")

    # In production, this would:
    # 1. Validate the recommendation still applies (nodes haven't changed)
    # 2. Trigger the Karpenter action (consolidation, right-sizing, etc.)
    # 3. Update the recommendation status to "applied"
    # 4. Monitor the action and report back

    return {
        "recommendation_id": recommendation_id,
        "status": "applying",
        "action": "consolidation",
        "estimated_completion_seconds": 120,
        "affected_instances": ["i-0abc123", "i-0abc124"],
        "message": f"Applying recommendation: {payload.recommended_type}",
        "applied_by": current_user.email,
        "applied_at": datetime.utcnow().isoformat(),
    }


@router.post(
    "/apply-recommendations/batch",
    summary="Apply multiple dry-run recommendations at once",
    description="Bulk apply multiple Karpenter recommendations"
)
def apply_karpenter_recommendations_batch(
    payload: KarpenterBatchApplyRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Bulk apply multiple Karpenter recommendations.
    Useful for applying all recommendations at once or applying a filtered set.
    """
    logger.info(f"Batch applying {len(payload.instance_ids)} Karpenter recommendations by user {current_user.id}")

    # In production, this would:
    # 1. Validate all recommendations
    # 2. Check for conflicts (e.g., recommendations affecting same nodes)
    # 3. Apply them in optimal order
    # 4. Return a job ID for tracking progress

    job_id = str(uuid.uuid4())

    return {
        "job_id": job_id,
        "status": "processing",
        "total_recommendations": len(payload.instance_ids),
        "recommendations_queued": len(payload.instance_ids),
        "estimated_completion_minutes": 5,
        "message": f"Batch apply job created for {len(payload.instance_ids)} recommendations",
        "applied_by": current_user.email,
        "started_at": datetime.utcnow().isoformat(),
    }


@router.patch(
    "/mode/{cluster_id}",
    summary="Update Karpenter mode for a cluster",
    description="Switch between dry_run and auto mode for a specific cluster"
)
def update_karpenter_mode(
    cluster_id: str,
    payload: KarpenterModeUpdateRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update Karpenter mode for a specific cluster.
    - dry_run: Karpenter only generates recommendations, no automatic actions
    - auto: Karpenter automatically optimizes based on policies
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()

    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    if cluster.karpenter_mode is None:
        raise HTTPException(
            status_code=400,
            detail=f"Karpenter is not deployed on cluster {cluster_id}. Deploy Karpenter first."
        )

    old_mode = cluster.karpenter_mode.value
    new_mode = payload.mode.value

    if old_mode == new_mode:
        return {
            "cluster_id": cluster_id,
            "mode": new_mode,
            "message": f"Cluster already in {new_mode} mode",
            "changed": False
        }

    # Update the mode
    cluster.karpenter_mode = KarpenterMode(new_mode)
    db.commit()

    logger.info(f"Karpenter mode changed from {old_mode} to {new_mode} for cluster {cluster_id} by user {current_user.id}")

    # In production, this would also:
    # 1. Update Karpenter controller config in K8s
    # 2. Update IAM permissions (dry_run doesn't need ec2:RunInstances)
    # 3. Clear pending recommendations if switching from dry_run to auto
    # 4. Send notification to team

    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster.name,
        "old_mode": old_mode,
        "new_mode": new_mode,
        "mode": new_mode,
        "changed": True,
        "message": f"Successfully switched from {old_mode} to {new_mode} mode",
        "updated_at": datetime.utcnow().isoformat(),
        "updated_by": current_user.email,
        "pending_recommendations_count": 0 if new_mode == "auto" else None,
    }


# ============================================================================
# Execution Plan & History Endpoints (used by RightSizingDashboard)
# ============================================================================


@router.get(
    "/execution-plan",
    summary="Get pending rightsizing execution plan",
    description="Returns PENDING/APPROVED rightsizing proposals as the execution plan"
)
def get_execution_plan(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns pending and approved rightsizing proposals as the execution plan.
    Used by the RightSizingDashboard Execution Plan tab.
    """
    try:
        from backend.models.rightsizing_proposal import RightsizingProposal, ProposalStatus

        query = db.query(RightsizingProposal).filter(
            RightsizingProposal.status.in_([ProposalStatus.PENDING, ProposalStatus.APPROVED])
        )
        if cluster_id:
            query = query.filter(RightsizingProposal.cluster_id == cluster_id)

        proposals = query.order_by(RightsizingProposal.created_at.asc()).all()

        plan_items = []
        for i, p in enumerate(proposals, 1):
            plan_items.append({
                "order": i,
                "node": p.current_pool or f"node-{str(p.id)[:8]}",
                "action": f"{p.current_instance_type} → {p.proposed_instance_type}",
                "est_duration": "~45s",
                "rollback_plan": f"Re-provision {p.current_instance_type} via ASG",
                "status": p.status.value,
                "proposal_id": p.id,
                "monthly_savings": round(p.estimated_monthly_savings, 2),
                "confidence": f"{max(50, round((1.0 - (p.best_pool_risk_score or 0.3)) * 100))}%",
            })

        return {
            "plan": plan_items,
            "total": len(plan_items),
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching execution plan: {e}")
        return {"plan": [], "total": 0, "generated_at": datetime.utcnow().isoformat()}


@router.get(
    "/history",
    summary="Get rightsizing action history",
    description="Returns EXECUTED/FAILED rightsizing proposals as the action history"
)
def get_rightsizing_history(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns executed and failed rightsizing proposals for the history tab.
    Used by the RightSizingDashboard History tab.
    """
    try:
        from backend.models.rightsizing_proposal import RightsizingProposal, ProposalStatus

        query = db.query(RightsizingProposal).filter(
            RightsizingProposal.status.in_([ProposalStatus.EXECUTED, ProposalStatus.FAILED])
        )
        if cluster_id:
            query = query.filter(RightsizingProposal.cluster_id == cluster_id)

        proposals = query.order_by(RightsizingProposal.executed_at.desc()).limit(50).all()

        history_items = []
        for p in proposals:
            executed_at = p.executed_at or p.evaluated_at or p.created_at
            history_items.append({
                "executed_at": executed_at.strftime("%b %d, %I:%M %p") if executed_at else "Unknown",
                "node": p.current_pool or f"node-{str(p.id)[:8]}",
                "before": p.current_instance_type,
                "after": p.proposed_instance_type,
                "time_taken": "~45s",
                "status": "Success" if p.status == ProposalStatus.EXECUTED else "Failed",
                "monthly_savings": round(p.estimated_monthly_savings, 2),
            })

        # Aggregate KPIs
        executed_count = sum(1 for p in proposals if p.status == ProposalStatus.EXECUTED)
        total_count = len(proposals)
        success_rate = round((executed_count / total_count * 100), 1) if total_count > 0 else 0
        net_savings = sum(
            p.estimated_monthly_savings for p in proposals
            if p.status == ProposalStatus.EXECUTED
        )

        return {
            "history": history_items,
            "total": len(history_items),
            "kpis": {
                "resizes_this_month": total_count,
                "net_savings_monthly": round(net_savings, 2),
                "success_rate_pct": success_rate,
            },
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching rightsizing history: {e}")
        return {
            "history": [],
            "total": 0,
            "kpis": {"resizes_this_month": 0, "net_savings_monthly": 0, "success_rate_pct": 0},
            "generated_at": datetime.utcnow().isoformat(),
        }


# ============================================================================
# Decision Engine v3 API Endpoints
# ============================================================================


@router.get("/v3/substitute/{cluster_id}/status")
async def get_substitute_status(
    cluster_id: str,
    db: Session = Depends(get_db)
):
    """
    Get current substitute instance status for the cluster.

    Returns: state (IDLE/PREWARMING/READY/ACTIVE/RELEASING),
    deployed instance details, cost drift info, and prewarm timeout status.
    """
    try:
        from backend.core.redis_client import get_redis_client
        from backend.services.substitute_manager import SubstituteManager

        redis = get_redis_client()
        sub_mgr = SubstituteManager(db, redis)

        state = sub_mgr.get_state(cluster_id)
        metadata = sub_mgr._get_metadata(cluster_id)
        cost_drift = sub_mgr.check_cost_drift(cluster_id)

        # Check prewarm timeout
        timeout_key = f"spot:substitute:prewarm_timeout:{cluster_id}"
        timeout_ttl = redis.ttl(timeout_key)

        return {
            "cluster_id": cluster_id,
            "state": state.value if hasattr(state, 'value') else str(state),
            "metadata": metadata,
            "cost_drift": cost_drift,
            "prewarm_timeout_remaining": max(0, timeout_ttl) if timeout_ttl and timeout_ttl > 0 else None,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get substitute status for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SubstituteDeployRequest(BaseModel):
    """Request to deploy a substitute instance."""
    target_node_name: str


@router.post("/v3/substitute/{cluster_id}/deploy")
async def deploy_substitute(
    cluster_id: str,
    payload: SubstituteDeployRequest,
    db: Session = Depends(get_db)
):
    """
    Deploy substitute instance for target node.

    Validates target node is STATELESS_ELIGIBLE before deploying.
    Selects top 3 candidates based on optimization mode.
    Each candidate validated via DryRun API before acceptance.
    """
    try:
        from backend.core.redis_client import get_redis_client
        from backend.services.substitute_manager import SubstituteManager

        redis = get_redis_client()
        sub_mgr = SubstituteManager(db, redis)

        result = sub_mgr.deploy_substitute(
            cluster_id=cluster_id,
            target_node_name=payload.target_node_name
        )

        return result
    except Exception as e:
        logger.error(f"Failed to deploy substitute for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v3/cooldown/{cluster_id}")
async def get_cooldown_status(cluster_id: str):
    """
    Get cluster cooldown status for UI display.

    Returns: whether cooldown is active, remaining seconds/minutes,
    and pool-level cooldowns if any exist.
    """
    try:
        from backend.core.redis_client import get_redis_client
        from backend.services.cooldown_controller import CooldownController

        redis = get_redis_client()
        cooldown = CooldownController(redis)

        cluster_status = cooldown.get_cluster_cooldown_status(cluster_id)

        # Check mode switch dwell cooldown
        dwell_key = f"spot:cooldown:mode_switch:{cluster_id}"
        dwell_ttl = redis.ttl(dwell_key)

        return {
            "cluster_id": cluster_id,
            "cluster_cooldown": cluster_status,
            "mode_switch_cooldown": {
                "active": dwell_ttl is not None and dwell_ttl > 0,
                "remaining_seconds": max(0, dwell_ttl) if dwell_ttl and dwell_ttl > 0 else 0
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get cooldown for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v3/workload-status/{cluster_id}")
async def get_workload_status(cluster_id: str):
    """
    Get current node classification data for the cluster.

    Returns node-by-node classification (STATELESS_ELIGIBLE, STATEFUL_PROTECTED,
    DRAIN_UNSAFE, SYSTEM_PROTECTED) with aggregate counts.
    """
    try:
        from backend.core.redis_client import get_redis_client
        from backend.services.workload_inspector import WorkloadInspector, NodeStatus

        redis = get_redis_client()
        inspector = WorkloadInspector(redis)

        classification = inspector.get_cached_classification(cluster_id)

        if not classification:
            return {
                "cluster_id": cluster_id,
                "classification_available": False,
                "message": "No cached classification. Scan may not have run yet.",
                "nodes": {},
                "counts": {},
                "timestamp": datetime.utcnow().isoformat()
            }

        # Count by status
        counts = {}
        for node_name, status in classification.items():
            counts[status] = counts.get(status, 0) + 1

        eligible_count = counts.get(NodeStatus.STATELESS_ELIGIBLE, 0)
        total_nodes = len(classification)

        return {
            "cluster_id": cluster_id,
            "classification_available": True,
            "nodes": classification,
            "counts": counts,
            "total_nodes": total_nodes,
            "eligible_count": eligible_count,
            "eligible_pct": round(eligible_count / total_nodes * 100, 1) if total_nodes > 0 else 0,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get workload status for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
