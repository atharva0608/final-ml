"""
Karpenter API Routes

FastAPI endpoints for Karpenter auto-optimization management:
- Status / configuration / deployment
- Activity feed and performance stats
- Cluster-level toggle (pause/resume)
"""
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import uuid

from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user, RequireAccess
from backend.core.logger import logger


# ─── Pydantic Schemas ────────────────────────────────────────────────────────

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
    gradual_rollout: bool = True
    acknowledgements: List[str] = Field(default_factory=list)


class KarpenterToggleRequest(BaseModel):
    enabled: bool


# ─── Router ──────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/karpenter", tags=["Karpenter"])


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get(
    "/status",
    summary="Get Karpenter deployment status",
    description="Returns whether Karpenter is set up, active clusters, and high-level stats"
)
def get_karpenter_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns overall Karpenter status for the user's organization.
    Includes deployment state, active cluster count, and summary metrics.
    """
    # In a real implementation this would query the KarpenterService
    # and cluster state. For now we return a representative stub so the
    # frontend can render all UI states (not-setup / active / paused).
    return {
        "is_setup": False,
        "status": "not_setup",  # not_setup | deploying | active | paused
        "active_clusters": 0,
        "total_managed_nodes": 0,
        "estimated_monthly_savings": 0,
        "last_activity": None,
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
    description="Partial update of Karpenter configuration"
)
def update_karpenter_config(
    cluster_id: str,
    updates: Dict[str, Any],
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Patch cluster-level Karpenter settings."""
    logger.info(f"Updating Karpenter config for cluster {cluster_id}")
    return {"cluster_id": cluster_id, "updated_fields": list(updates.keys()), "success": True}


@router.post(
    "/deploy",
    summary="Deploy Karpenter to selected clusters",
    description="Triggers Karpenter installation and NodePool creation"
)
def deploy_karpenter(
    payload: KarpenterDeployRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Kicks off Karpenter deployment:
    1. Install Karpenter controller (Helm)
    2. Create IAM roles
    3. Deploy NodePool configs
    4. Set up monitoring
    """
    logger.info(f"Deploying Karpenter to {len(payload.cluster_configs)} clusters by user {current_user.id}")
    deployment_id = str(uuid.uuid4())
    return {
        "deployment_id": deployment_id,
        "status": "deploying",
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
    # Stub data matching the wireframe
    sample_events = [
        {
            "id": str(uuid.uuid4()),
            "timestamp": (datetime.utcnow() - timedelta(minutes=3)).isoformat(),
            "cluster": "prod-web",
            "type": "consolidation",
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
            "timestamp": (datetime.utcnow() - timedelta(minutes=12)).isoformat(),
            "cluster": "prod-api",
            "type": "instance_switch",
            "title": "Switched to Graviton instance",
            "details": ["r5.2xlarge → r6g.2xlarge (ARM64)"],
            "savings_daily": 68,
        },
        {
            "id": str(uuid.uuid4()),
            "timestamp": (datetime.utcnow() - timedelta(minutes=18)).isoformat(),
            "cluster": "prod-web",
            "type": "spot_replacement",
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
