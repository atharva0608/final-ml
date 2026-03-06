"""
Multi-Cluster Summary API
Aggregates spot/OD counts, savings estimates, and rebalancing action stats
across all clusters in the organization. Powers the fleet-overview panel
on the main Dashboard.
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user

router = APIRouter(prefix="/multi-cluster", tags=["Multi-Cluster"])


# ── Response schemas ────────────────────────────────────────────────────────

class ClusterFleetItem(BaseModel):
    id: str
    name: str
    region: Optional[str]
    status: Optional[str]
    karpenter_mode: Optional[str]
    spot_nodes: int
    od_nodes: int
    total_nodes: int
    spot_ratio_pct: float
    pending_actions: int
    in_progress_actions: int
    completed_actions_24h: int
    auto_rebalance_enabled: bool
    agent_installed: bool
    monthly_savings_est: float   # rough: spot_nodes * avg_spot_discount

class FleetSummary(BaseModel):
    total_clusters: int
    active_clusters: int
    total_nodes: int
    spot_nodes: int
    od_nodes: int
    spot_ratio_pct: float
    pending_actions: int
    in_progress_actions: int
    completed_actions_24h: int
    monthly_savings_est: float

class MultiClusterSummaryResponse(BaseModel):
    summary: FleetSummary
    clusters: List[ClusterFleetItem]
    generated_at: str


# ── Endpoint ────────────────────────────────────────────────────────────────

@router.get("/summary", response_model=MultiClusterSummaryResponse)
def get_multi_cluster_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Fleet-wide aggregation: spot/OD counts, savings, and rebalancing stats
    across all clusters for the authenticated user's organization.
    """
    from backend.models.cluster import Cluster
    from backend.models.instance import Instance, InstanceLifecycle
    from backend.models.rebalancing_action import RebalancingAction
    from backend.models.account import Account

    org_id = current_user.organization_id

    # Fetch all clusters for this org via account join
    clusters_q = (
        db.query(Cluster)
        .join(Account, Cluster.account_id == Account.id)
        .filter(Account.organization_id == org_id)
        .all()
    )

    since_24h = datetime.utcnow() - timedelta(hours=24)

    fleet_items: List[ClusterFleetItem] = []

    for c in clusters_q:
        # Instance counts
        spot_count = db.query(Instance).filter(
            Instance.cluster_id == c.id,
            Instance.lifecycle == InstanceLifecycle.SPOT,
            Instance.state == 'running',
        ).count()
        od_count = db.query(Instance).filter(
            Instance.cluster_id == c.id,
            Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
            Instance.state == 'running',
        ).count()
        total_nodes = spot_count + od_count
        spot_ratio = round(spot_count / total_nodes * 100, 1) if total_nodes > 0 else 0.0

        # Rebalancing action counts
        pending = db.query(RebalancingAction).filter(
            RebalancingAction.cluster_id == c.id,
            RebalancingAction.status == 'in_progress',
            RebalancingAction.trigger != 'emergency',
        ).count()
        in_prog = db.query(RebalancingAction).filter(
            RebalancingAction.cluster_id == c.id,
            RebalancingAction.status == 'waiting_agent',
        ).count()
        completed_24h = db.query(RebalancingAction).filter(
            RebalancingAction.cluster_id == c.id,
            RebalancingAction.status == 'completed',
            RebalancingAction.completed_at >= since_24h,
        ).count()

        # Rough savings estimate: spot nodes save ~70% vs OD at ~$0.096/h (m5.large baseline)
        _hourly_od_baseline = 0.096
        _spot_discount = 0.70
        monthly_savings = round(spot_count * _hourly_od_baseline * _spot_discount * 720, 2)

        auto_rebalance = getattr(c, 'auto_rebalance_enabled', False) or False

        _status_val = c.status.value if hasattr(c.status, 'value') else str(c.status) if c.status else None
        fleet_items.append(ClusterFleetItem(
            id=str(c.id),
            name=c.name or "",
            region=c.region,
            status=_status_val,
            karpenter_mode=c.karpenter_mode.value if c.karpenter_mode else None,
            spot_nodes=spot_count,
            od_nodes=od_count,
            total_nodes=total_nodes,
            spot_ratio_pct=spot_ratio,
            pending_actions=pending,
            in_progress_actions=in_prog,
            completed_actions_24h=completed_24h,
            auto_rebalance_enabled=bool(auto_rebalance),
            agent_installed=bool(getattr(c, 'agent_installed', False)),
            monthly_savings_est=monthly_savings,
        ))

    # Aggregate totals
    total_spot   = sum(f.spot_nodes for f in fleet_items)
    total_od     = sum(f.od_nodes for f in fleet_items)
    total_nodes_all = total_spot + total_od
    active_clusters = sum(
        1 for c in clusters_q
        if (c.status.value if hasattr(c.status, 'value') else str(c.status)) == 'ACTIVE'
    )

    summary = FleetSummary(
        total_clusters=len(fleet_items),
        active_clusters=active_clusters,
        total_nodes=total_nodes_all,
        spot_nodes=total_spot,
        od_nodes=total_od,
        spot_ratio_pct=round(total_spot / total_nodes_all * 100, 1) if total_nodes_all > 0 else 0.0,
        pending_actions=sum(f.pending_actions for f in fleet_items),
        in_progress_actions=sum(f.in_progress_actions for f in fleet_items),
        completed_actions_24h=sum(f.completed_actions_24h for f in fleet_items),
        monthly_savings_est=round(sum(f.monthly_savings_est for f in fleet_items), 2),
    )

    return MultiClusterSummaryResponse(
        summary=summary,
        clusters=fleet_items,
        generated_at=datetime.utcnow().isoformat(),
    )
