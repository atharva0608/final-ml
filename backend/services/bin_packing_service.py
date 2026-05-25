"""
Bin Packing Service
===================
Calculates and caches per-node CPU/memory packing density metrics.
Used by both the API (on-demand fallback) and the background worker (pre-compute).
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

from sqlalchemy import func, cast, String as SAString, desc as _desc, Boolean
from sqlalchemy.orm import Session
from redis import Redis

from backend.models.node_metadata import NodeMetadata
from backend.models.pod_metric import PodMetric
from backend.models.instance import Instance
from backend.models.cluster import Cluster
from backend.models.pricing import OnDemandPricing, SpotPriceHistory
from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
from backend.models.rebalancing_action import RebalancingAction
from backend.utils.data_freshness import compute_freshness, stale_node_filter
from backend.services.pod_placement_engine import NodeOverheadProfiler

logger = logging.getLogger(__name__)

class BinPackingService:
    _CACHE_KEY = "spot:bin_packing:{cluster_id}"
    _CACHE_TTL = 300  # 5 minutes
    _OVERLOAD_THRESHOLD = 85.0

    def __init__(self, db: Session, redis: Optional[Redis] = None):
        self.db = db
        self.redis = redis

    def get_bin_packing_data(self, cluster_id: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get bin packing data for a cluster.
        Tries Redis cache first, falls back to on-the-fly calculation.
        """
        cache_key = self._CACHE_KEY.format(cluster_id=cluster_id)
        
        if self.redis and not force_refresh:
            try:
                cached = self.redis.get(cache_key)
                if cached:
                    return json.loads(cached).get("data", {})
            except Exception as e:
                logger.warning(f"Failed to fetch bin packing cache for {cluster_id}: {e}")

        # Fallback to on-the-fly calculation
        data = self.compute_bin_packing(cluster_id)
        
        # Cache the result if possible
        if self.redis and data.get("nodes"):
            try:
                result = {"data": data}
                self.redis.setex(cache_key, self._CACHE_TTL, json.dumps(result))
            except Exception as e:
                logger.warning(f"Failed to set bin packing cache for {cluster_id}: {e}")
                
        return data

    def compute_bin_packing(self, cluster_id: str) -> Dict[str, Any]:
        """
        Performs the heavy SQL aggregation to compute packing density.
        """
        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            return {"nodes": [], "error": "cluster_not_found"}

        # 1. Check if we have any metadata at all
        max_updated_at = (
            self.db.query(func.max(NodeMetadata.updated_at))
            .filter(NodeMetadata.cluster_id == cluster_id)
            .scalar()
        )

        if max_updated_at is None:
            return {
                "nodes": [],
                "stale_nodes_excluded": 0,
                "consolidation_candidates": None,
                "is_stale": True,
                "data_age_seconds": None,
                "data_updated_at": None
            }

        _pod_cutoff = datetime.utcnow() - timedelta(minutes=30)
        
        # 2. Get latest pod metrics per pod
        latest_subq = (
            self.db.query(
                PodMetric.pod_name,
                PodMetric.node_name,
                PodMetric.cpu_request_millicores,
                PodMetric.memory_request_bytes,
                PodMetric.cpu_usage_millicores,
                PodMetric.memory_usage_bytes,
                func.coalesce(cast(PodMetric.pod_metadata["has_pdb"].astext, Boolean), False).label("pod_has_pdb")
            )
            .filter(
                PodMetric.cluster_id == cluster_id,
                PodMetric.timestamp >= _pod_cutoff,
            )
            .distinct(PodMetric.pod_name)
            .order_by(PodMetric.pod_name, PodMetric.timestamp.desc())
            .subquery()
        )

        # 3. Aggregate by node
        rows = (
            self.db.query(
                NodeMetadata.node_name,
                func.sum(latest_subq.c.cpu_request_millicores).label("total_cpu_request"),
                func.sum(latest_subq.c.memory_request_bytes).label("total_mem_request"),
                func.sum(latest_subq.c.cpu_usage_millicores).label("total_cpu_usage"),
                func.sum(latest_subq.c.memory_usage_bytes).label("total_mem_usage"),
                func.count(func.distinct(latest_subq.c.pod_name)).label("pod_count"),
                func.bool_or(latest_subq.c.pod_has_pdb).label("node_has_pdb"),
                NodeMetadata.allocatable_cpu_millicores,
                NodeMetadata.allocatable_memory_bytes,
                func.coalesce(NodeMetadata.az, Instance.az).label("az"),
                func.coalesce(NodeMetadata.capacity_type, cast(Instance.lifecycle, SAString)).label("capacity_type"),
                func.coalesce(NodeMetadata.instance_type, Instance.instance_type).label("instance_type"),
                NodeMetadata.is_ready,
                NodeMetadata.do_not_disrupt,
                NodeMetadata.updated_at.label("node_updated_at"),
            )
            .select_from(NodeMetadata)
            .outerjoin(
                Instance,
                (NodeMetadata.cluster_id == Instance.cluster_id)
                & (NodeMetadata.node_name == Instance.node_name)
            )
            .outerjoin(
                latest_subq,
                (NodeMetadata.cluster_id == cluster_id)
                & (NodeMetadata.node_name == latest_subq.c.node_name)
            )
            .filter(NodeMetadata.cluster_id == cluster_id)
            .group_by(
                NodeMetadata.node_name,
                NodeMetadata.allocatable_cpu_millicores,
                NodeMetadata.allocatable_memory_bytes,
                NodeMetadata.az,
                Instance.az,
                NodeMetadata.capacity_type,
                Instance.lifecycle,
                NodeMetadata.instance_type,
                Instance.instance_type,
                NodeMetadata.is_ready,
                NodeMetadata.do_not_disrupt,
                NodeMetadata.updated_at,
            )
            .all()
        )

        _GiB = 1024 ** 3
        nodes_with_ts = []
        for r in rows:
            alloc_cpu = float(r.allocatable_cpu_millicores or 1)
            alloc_mem = float(r.allocatable_memory_bytes or 1)

            cpu_requested_pct = min(100.0, round(float(r.total_cpu_request or 0) / alloc_cpu * 100, 1))
            cpu_actual_pct = min(100.0, round(float(r.total_cpu_usage or 0) / alloc_cpu * 100, 1))
            mem_requested_pct = min(100.0, round(float(r.total_mem_request or 0) / alloc_mem * 100, 1))
            mem_actual_pct = min(100.0, round(float(r.total_mem_usage or 0) / alloc_mem * 100, 1))

            is_overloaded = cpu_actual_pct > self._OVERLOAD_THRESHOLD or mem_actual_pct > self._OVERLOAD_THRESHOLD

            overhead = NodeOverheadProfiler.profile(
                allocatable_cpu_mc=alloc_cpu,
                allocatable_mem_bytes=alloc_mem,
            )

            nodes_with_ts.append({
                "node_name": r.node_name,
                "az": r.az,
                "capacity_type": r.capacity_type,
                "instance_type": r.instance_type,
                "pod_count": r.pod_count or 0,
                "has_pdb_pods": bool(r.node_has_pdb), # Correctly using aggregated column
                "cpu_requested_pct": cpu_requested_pct,
                "cpu_actual_pct": cpu_actual_pct,
                "mem_requested_pct": mem_requested_pct,
                "mem_actual_pct": mem_actual_pct,
                "is_overloaded": is_overloaded,
                "is_ready": r.is_ready,
                "do_not_disrupt": r.do_not_disrupt,
                "node_updated_at": r.node_updated_at,
                "allocatable_cpu_millicores": r.allocatable_cpu_millicores,
                "allocatable_memory_bytes": r.allocatable_memory_bytes,
                "effective_cpu_mc": overhead["effective_cpu_mc"],
                "effective_mem_bytes": overhead["effective_mem_bytes"],
                "overhead_detail": overhead["overhead_detail"],
            })

        # 4. Filter stale and gather pricing
        draining_nodes = set()
        try:
            drain_rows = (
                self.db.query(AgentAction.payload["node_name"].astext)
                .filter(
                    AgentAction.cluster_id == cluster_id,
                    AgentAction.action_type == AgentActionType.DRAIN_NODE,
                    AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
                )
                .all()
            )
            draining_nodes = {r[0] for r in drain_rows if r[0]}
        except Exception:
            pass

        active_rebalancing_nodes = {}
        try:
            rebalance_rows = (
                self.db.query(Instance.node_name, RebalancingAction.status, RebalancingAction.current_state, RebalancingAction.target_pool)
                .join(
                    RebalancingAction,
                    (RebalancingAction.cluster_id == Instance.cluster_id)
                    & (RebalancingAction.source_instance_id == Instance.instance_id),
                )
                .filter(
                    RebalancingAction.cluster_id == cluster_id,
                    RebalancingAction.status.in_(["pending", "in_progress", "waiting_agent", "pending_approval"]),
                    Instance.node_name.isnot(None),
                )
                .all()
            )
            active_rebalancing_nodes = {
                r.node_name: {
                    "status": r.status,
                    "current_state": r.current_state,
                    "target_pool": r.target_pool,
                }
                for r in rebalance_rows if r.node_name
            }
            draining_nodes.update(active_rebalancing_nodes.keys())
        except Exception:
            pass

        fresh_nodes, stale_count = stale_node_filter(nodes_with_ts, "node_updated_at")

        _cluster_region = cluster.region or "us-east-1"
        _instance_types = {n["instance_type"] for n in fresh_nodes if n.get("instance_type")}

        _od_prices = {}
        _spot_prices = {}
        if _instance_types:
            _od_prices = {} # fallback
            try:
                _od_rows = (
                    self.db.query(OnDemandPricing.instance_type, OnDemandPricing.price)
                    .filter(
                        OnDemandPricing.instance_type.in_(_instance_types),
                        OnDemandPricing.region == _cluster_region,
                    )
                    .all()
                )
                _od_prices = {r.instance_type: float(r.price) for r in _od_rows}
            except Exception:
                pass

            _spot_prices = {}
            try:
                _spot_rows = (
                    self.db.query(SpotPriceHistory.instance_type, SpotPriceHistory.price)
                    .filter(
                        SpotPriceHistory.instance_type.in_(_instance_types),
                        SpotPriceHistory.region == _cluster_region,
                    )
                    .order_by(SpotPriceHistory.instance_type, _desc(SpotPriceHistory.timestamp))
                    .distinct(SpotPriceHistory.instance_type)
                    .all()
                )
                _spot_prices = {r.instance_type: float(r.price) for r in _spot_rows}
            except Exception:
                pass

        _GiB = 1024 ** 3
        _exclude = {"node_updated_at", "is_ready", "do_not_disrupt"}
        nodes_out = []
        for n in fresh_nodes:
            _itype = n.get("instance_type")
            _cap = (n.get("capacity_type") or "").lower()
            _price = 0.0
            if _cap in ("spot", "spot-instance"):
                _price = _spot_prices.get(_itype, 0.0)
            else:
                _price = _od_prices.get(_itype, 0.0)

            _alloc_cpu_m = n.get("allocatable_cpu_millicores")
            _alloc_mem_b = n.get("allocatable_memory_bytes")
            
            nn = n["node_name"]
            n_out = {
                **{k: v for k, v in n.items() if k not in _exclude},
                "hourly_price_usd": _price,
                "allocatable_cpu": round(_alloc_cpu_m / 1000.0, 2) if _alloc_cpu_m else None,
                "allocatable_memory_gb": round(_alloc_mem_b / _GiB, 2) if _alloc_mem_b else None,
                "lifecycle_state": "cordoned" if not n["is_ready"] else "running",
            }
            if nn in draining_nodes:
                n_out["lifecycle_state"] = "DRAINING"
            if nn in active_rebalancing_nodes:
                n_out["pending_rebalance"] = True
                rdata = active_rebalancing_nodes[nn]
                n_out["rebalancing_status"] = rdata["status"]
                n_out["rebalancing_state"] = rdata["current_state"]
                n_out["rebalancing_target_pool"] = rdata["target_pool"]
            
            nodes_out.append(n_out)

        nodes_out.sort(key=lambda x: (x.get("is_overloaded", False), x.get("cpu_actual_pct", 0)), reverse=True)
        
        freshness = compute_freshness(max_updated_at)
        return {
            "nodes": nodes_out,
            "stale_nodes_excluded": stale_count,
            "consolidation_candidates": {"count": 0, "est_savings_monthly_usd": 0.0},
            "is_stale": freshness["is_stale"],
            "data_age_seconds": freshness["data_age_seconds"],
            "data_updated_at": freshness["data_updated_at"]
        }
