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
    from backend.core.redis_client import get_redis_client
    from backend.services.dynamic_instance_helpers import get_instance_hourly_price

    org_id = current_user.organization_id
    redis = get_redis_client()

    # Fetch all non-dismissed clusters for this org via account join
    clusters_q = (
        db.query(Cluster)
        .join(Account, Cluster.account_id == Account.id)
        .filter(Account.organization_id == org_id)
        .filter(Cluster.is_dismissed == False)
        .all()
    )

    since_24h = datetime.utcnow() - timedelta(hours=24)

    fleet_items: List[ClusterFleetItem] = []

    for c in clusters_q:
        # Build set of replacement spot instance IDs with active optimization
        # to exclude from fleet view counts until optimization completes.
        _active_repl_ids = set()
        _active_ras_mc = db.query(RebalancingAction).filter(
            RebalancingAction.cluster_id == c.id,
            RebalancingAction.status.in_(['in_progress', 'waiting_agent']),
        ).all()
        for _ra_mc in _active_ras_mc:
            _ra_mc_meta = _ra_mc.action_metadata or {}
            _repl_mc = _ra_mc_meta.get('replacement_spot_instance_id')
            if _repl_mc:
                _active_repl_ids.add(_repl_mc)

        # Instance counts (excluding replacement spot nodes with active optimization)
        _spot_q = db.query(Instance).filter(
            Instance.cluster_id == c.id,
            Instance.lifecycle == InstanceLifecycle.SPOT,
            Instance.state == 'running',
        )
        if _active_repl_ids:
            _spot_q = _spot_q.filter(Instance.instance_id.notin_(_active_repl_ids))
        spot_count = _spot_q.count()
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

        # Real savings: sum (OD_price - spot_price) per spot instance, projected monthly
        spot_instances = db.query(Instance).filter(
            Instance.cluster_id == c.id,
            Instance.lifecycle == InstanceLifecycle.SPOT,
            Instance.state == 'running',
        ).all()

        monthly_savings = 0.0
        for si in spot_instances:
            od_price = get_instance_hourly_price(db, redis, si.instance_type or 'm5.large', c.region or 'ap-south-1')
            # Spot price from Redis
            _sp_key = f"spot_price:{c.region or 'ap-south-1'}:{si.az or ''}:{si.instance_type}"
            _sp_raw = None
            try:
                import json as _json_fleet
                _sp_raw = redis.get(_sp_key)
                if _sp_raw:
                    _sp_val = float(_json_fleet.loads(_sp_raw).get("price", 0))
                else:
                    _sp_val = od_price * 0.35  # conservative fallback
            except Exception:
                _sp_val = od_price * 0.35
            hourly_saving = max(0.0, od_price - _sp_val)
            monthly_savings += hourly_saving * 730
        monthly_savings = round(monthly_savings, 2)

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


@router.get("/actions")
def get_multi_cluster_actions(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Fleet-wide recent rebalancing/optimization actions
    """
    from backend.models.cluster import Cluster
    from backend.models.rebalancing_action import RebalancingAction
    from backend.models.account import Account

    org_id = current_user.organization_id

    # Join RebalancingAction -> Cluster -> Account to securely fetch org-wide actions
    actions_q = (
        db.query(RebalancingAction, Cluster.name.label("cluster_name"))
        .join(Cluster, RebalancingAction.cluster_id == Cluster.id)
        .join(Account, Cluster.account_id == Account.id)
        .filter(Account.organization_id == org_id)
        .order_by(RebalancingAction.created_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for action, cname in actions_q:
        result.append({
            "id": action.id,
            "cluster_id": action.cluster_id,
            "cluster_name": cname,
            "status": action.status,
            "trigger": action.trigger,
            "target_node": getattr(action, 'target_node_name', None),
            "created_at": action.created_at.isoformat() if action.created_at else None,
            "completed_at": action.completed_at.isoformat() if action.completed_at else None,
        })
    return {"actions": result}


@router.get("/trends")
def get_multi_cluster_trends(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Fleet-wide aggregated daily trends: total_nodes, spot_nodes, cost, savings.
    """
    from backend.models.cluster import Cluster
    from backend.models.account import Account
    from backend.models.daily_cluster_stats import DailyClusterStat
    from sqlalchemy import func

    org_id = current_user.organization_id
    since_date = datetime.utcnow().date() - timedelta(days=days)

    # Query DailyClusterStat grouped by date
    trends_q = (
        db.query(
            DailyClusterStat.date_stamp,
            func.sum(DailyClusterStat.total_cost).label('total_cost'),
            func.sum(DailyClusterStat.total_savings).label('total_savings'),
            func.sum(DailyClusterStat.spot_nodes).label('spot_nodes'),
            func.sum(DailyClusterStat.total_nodes).label('total_nodes'),
        )
        .join(Cluster, DailyClusterStat.cluster_id == Cluster.id)
        .join(Account, Cluster.account_id == Account.id)
        .filter(Account.organization_id == org_id)
        .filter(DailyClusterStat.date_stamp >= since_date)
        .group_by(DailyClusterStat.date_stamp)
        .order_by(DailyClusterStat.date_stamp.asc())
        .all()
    )

    series = []
    for t in trends_q:
        date_str = t.date_stamp.isoformat() if t.date_stamp else ""
        spot_pct = round((t.spot_nodes / t.total_nodes) * 100, 1) if t.total_nodes and t.total_nodes > 0 else 0.0
        series.append({
            "date": date_str,
            "cost": float(t.total_cost or 0),
            "savings": float(t.total_savings or 0),
            "spot_nodes": int(t.spot_nodes or 0),
            "total_nodes": int(t.total_nodes or 0),
            "spot_ratio_pct": spot_pct
        })

    return {"trends": series}
