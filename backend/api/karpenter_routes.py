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
    return {"events": sample_events[:limit], "total": len(sample_events)}


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
    return {
        "period": period,
        "avg_utilization_pct": 78,
        "prev_utilization_pct": 45,
        "optimizations_count": 38,
        "cost_saved": 1240,
        "spot_coverage_pct": 82,
        "clusters": [
            {
                "cluster_id": "prod-web",
                "name": "prod-web",
                "region": "us-east-1",
                "strategy": "balanced",
                "nodes": 12,
                "utilization_pct": 82,
                "spot_pct": 83,
                "cost_current": 520,
                "cost_before": 720,
                "optimizations_24h": 8,
                "status": "active",
            },
            {
                "cluster_id": "prod-api",
                "name": "prod-api",
                "region": "us-east-1",
                "strategy": "balanced",
                "nodes": 18,
                "utilization_pct": 75,
                "spot_pct": 78,
                "cost_current": 780,
                "cost_before": 1100,
                "optimizations_24h": 12,
                "status": "active",
            },
            {
                "cluster_id": "staging",
                "name": "staging-cluster",
                "region": "us-west-2",
                "strategy": "cost-first",
                "nodes": 5,
                "utilization_pct": 88,
                "spot_pct": 100,
                "cost_current": 195,
                "cost_before": 320,
                "optimizations_24h": 6,
                "status": "active",
            },
        ],
        "cost_trend": [
            {"week": "Week 1", "before": 9200, "after": None},
            {"week": "Week 2", "before": 9200, "after": None},
            {"week": "Week 3", "before": 9200, "after": 7500},
            {"week": "Week 4", "before": None, "after": 6800},
            {"week": "Week 5", "before": None, "after": 6500},
            {"week": "Week 6", "before": None, "after": 6440},
        ],
        "instance_distribution": {
            "before": {"m5": 75, "c5": 15, "r5": 10},
            "after": {"m6i": 35, "c6i": 28, "m6a": 18, "r6g": 12, "other": 7},
        },
        "total_saved": 8640,
        "avg_reduction_pct": 32,
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
    Get all pending Karpenter recommendations from clusters in dry_run mode.
    These are optimization opportunities that require manual approval to apply.
    """
    # Query clusters in dry_run mode
    query = db.query(Cluster).filter(Cluster.karpenter_mode == KarpenterMode.DRY_RUN)
    if cluster_id:
        query = query.filter(Cluster.id == cluster_id)

    dry_run_clusters = query.all()

    # Stub recommendations data - in production, this would come from K8s events / database
    recommendations = [
        {
            "id": str(uuid.uuid4()),
            "cluster_id": "prod-web",
            "cluster_name": "prod-web",
            "type": "consolidation",
            "status": "pending",
            "created_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
            "title": "Consolidate 3 under-utilized nodes",
            "description": "Current nodes running at 28-38% utilization. Can consolidate to 2 nodes with 65-70% utilization.",
            "current_instances": ["i-0abc123", "i-0abc124", "i-0abc125"],
            "recommended_instances": ["c6i.xlarge", "m6i.large"],
            "potential_savings_monthly": 420,
            "confidence": "high",
            "risk_level": "low",
            "details": {
                "current_cost_monthly": 840,
                "projected_cost_monthly": 420,
                "current_utilization_avg": 34,
                "projected_utilization_avg": 68,
                "affected_pods": 12,
                "estimated_disruption_seconds": 30,
            }
        },
        {
            "id": str(uuid.uuid4()),
            "cluster_id": "prod-api",
            "cluster_name": "prod-api",
            "type": "right_sizing",
            "status": "pending",
            "created_at": (datetime.utcnow() - timedelta(hours=5)).isoformat(),
            "title": "Right-size over-provisioned instance",
            "description": "Instance i-0def456 (m5.4xlarge) running at 18% CPU, 22% memory. Can downsize to m5.xlarge.",
            "current_instances": ["i-0def456"],
            "recommended_instances": ["m5.xlarge"],
            "potential_savings_monthly": 560,
            "confidence": "high",
            "risk_level": "low",
            "details": {
                "current_type": "m5.4xlarge",
                "current_cost_monthly": 700,
                "projected_type": "m5.xlarge",
                "projected_cost_monthly": 140,
                "cpu_utilization": 18,
                "memory_utilization": 22,
                "affected_pods": 3,
                "pod_constraints_satisfied": True,
            }
        },
        {
            "id": str(uuid.uuid4()),
            "cluster_id": "prod-web",
            "cluster_name": "prod-web",
            "type": "graviton_migration",
            "status": "pending",
            "created_at": (datetime.utcnow() - timedelta(hours=8)).isoformat(),
            "title": "Migrate to Graviton (ARM64)",
            "description": "Workload compatible with ARM64. Switch r5.2xlarge → r6g.2xlarge for 20% cost reduction.",
            "current_instances": ["i-0ghi789"],
            "recommended_instances": ["r6g.2xlarge"],
            "potential_savings_monthly": 136,
            "confidence": "medium",
            "risk_level": "medium",
            "details": {
                "current_type": "r5.2xlarge",
                "current_cost_monthly": 680,
                "projected_type": "r6g.2xlarge",
                "projected_cost_monthly": 544,
                "architecture_change": "amd64 → arm64",
                "compatibility_checked": True,
                "affected_pods": 8,
            }
        },
    ]

    # Filter by status if provided
    if status_filter:
        recommendations = [r for r in recommendations if r["status"] == status_filter]

    # Filter by cluster if provided
    if cluster_id:
        recommendations = [r for r in recommendations if r["cluster_id"] == cluster_id]

    total_potential_savings = sum(r["potential_savings_monthly"] for r in recommendations)

    return {
        "recommendations": recommendations,
        "total_count": len(recommendations),
        "pending_count": len([r for r in recommendations if r["status"] == "pending"]),
        "total_potential_savings_monthly": total_potential_savings,
        "dry_run_clusters": [
            {
                "cluster_id": c.id,
                "name": c.name,
                "mode": c.karpenter_mode.value if c.karpenter_mode else None
            }
            for c in dry_run_clusters
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
