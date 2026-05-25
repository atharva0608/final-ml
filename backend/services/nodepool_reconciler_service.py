import time
import json
import logging
from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.services.karpenter_service import KarpenterService
from backend.services.pool_ranking_service import PoolRankingService

logger = logging.getLogger(__name__)

class NodePoolReconcilerService:
    """
    Task 2.1: NodePool class reconciler.
    Ensures the 4 standard NodePool classes exist and are updated based on ML rankings.
    """
    
    CLASSES = ["on-demand-general", "spot-general", "spot-compute", "spot-memory"]
    REFRESH_RATE_LIMIT_SECONDS = 1800 # 30 minutes
    MAX_AGE_SECONDS = 21600 # 6 hours

    def __init__(self, redis_client):
        self.redis = redis_client
        
    def _is_refresh_needed(self, cluster_id: str, nodepool_class: str) -> bool:
        """
        Refresh triggers:
        1. every 6 hours
        2. OR spot_scheduling_failures_last_15min > 3 AND last_refresh > 30 min ago
        """
        last_refresh_key = f"spot:placement:nodepool_refresh:{cluster_id}:{nodepool_class}"
        raw_ts = self.redis.get(last_refresh_key)
        
        if not raw_ts:
            return True # Never refreshed
            
        last_refresh = float(raw_ts)
        age = time.time() - last_refresh
        
        if age < self.REFRESH_RATE_LIMIT_SECONDS:
            return False # Hard rate limit: min 30 minutes between updates
            
        if age > self.MAX_AGE_SECONDS:
            return True # Older than 6 hours
            
        # Fast-track trigger: > 3 failures
        failure_key = f"spot:placement:scheduling_success:failures_15m:{cluster_id}"
        fails = int(self.redis.get(failure_key) or 0)
        
        if fails > 3:
            logger.info(f"NodePool {nodepool_class} triggered for fast refresh due to {fails} errors")
            return True
            
        return False

    def reconcile_all_classes(self, cluster_id: str, db: Session, active_workload_counts: Dict[str, int] = None):
        """
        Reconcile all 4 standard NodePool classes.
        Spot NodePools are only updated when auto-rebalancing is enabled so that
        Karpenter cannot provision spot nodes until the ML rebalancer is active.
        """
        from backend.models.cluster import Cluster
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            logger.error(f"Cluster {cluster_id} not found for NodePool reconciliation")
            return

        # Determine whether auto-rebalancing is active (source of truth: DB settings row)
        _opt = getattr(cluster, "optimization_settings", None)
        _auto_rebalance_on = bool(getattr(_opt, "auto_rebalance_enabled", False)) if _opt else False

        region = cluster.region or "us-east-1"
        karpenter_svc = KarpenterService(db, self.redis)
        
        for np_class in self.CLASSES:
            if not self._is_refresh_needed(cluster_id, np_class):
                continue

            capacity_type = "on-demand" if "on-demand" in np_class else "spot"

            # When auto-rebalancing is OFF, skip spot NodePool updates entirely.
            # This ensures Karpenter can only provision OD nodes (same type as the
            # existing fleet) until the ML rebalancer is explicitly turned on.
            if capacity_type == "spot" and not _auto_rebalance_on:
                logger.info(
                    f"[reconciler] Skipping spot NodePool '{np_class}' for cluster "
                    f"{cluster_id} — auto-rebalancing is OFF"
                )
                continue
                
            workload_count = (active_workload_counts or {}).get(np_class, 0)
            
            try:
                top_pools = self._get_pools_for_class(np_class, region, db)
                
                result = karpenter_svc.sync_ml_rankings_to_nodepool(
                    cluster_id=cluster_id,
                    top_pools=top_pools,
                    nodepool_name=np_class,
                    capacity_type=capacity_type
                )
                
                if result.get("status") == "success":
                    self.redis.set(f"spot:placement:nodepool_refresh:{cluster_id}:{np_class}", time.time())
                    self._apply_custom_annotations(karpenter_svc, cluster_id, np_class, workload_count)
                    
            except Exception as e:
                logger.error(f"Failed to reconcile NodePool class {np_class} for cluster {cluster_id}: {e}")

    def _apply_custom_annotations(self, karpenter_svc: KarpenterService, cluster_id: str, nodepool_name: str, workload_count: int):
        from backend.models.cluster import Cluster
        from kubernetes import client
        
        cluster = karpenter_svc.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            return
            
        api_client = karpenter_svc._get_k8s_client(cluster)
        custom_api = client.CustomObjectsApi(api_client)
        
        patch = {
            "metadata": {
                "annotations": {
                    "aura.io/managed": "true",
                    "aura.io/nodepool-class": nodepool_name,
                    "aura.io/last-refreshed": datetime.utcnow().isoformat(),
                    "aura.io/workload-count": str(workload_count)
                }
            },
            "spec": {
                "disruption": {
                    "consolidationPolicy": "WhenEmpty",
                    "consolidateAfter": "Never"
                }
            }
        }
        
        try:
            custom_api.patch_cluster_custom_object(
                group="karpenter.sh",
                version="v1",
                plural="nodepools",
                name=nodepool_name,
                body=patch
            )
        except Exception as e:
            logger.warning(f"Failed to patch NodePool {nodepool_name} annotations: {e}")

    def _get_pools_for_class(self, np_class: str, region: str, db: Session) -> List[Dict]:
        pool_ranking_svc = PoolRankingService(db, self.redis)
        
        scored_pools = pool_ranking_svc._get_or_compute_global_rankings(region)
        
        filtered = []
        is_compute = "compute" in np_class
        is_memory = "memory" in np_class
        
        for pool in scored_pools:
            instance_type = pool.pool.instance_type
            az = pool.pool.az
            family = instance_type.split('.')[0]
            
            if is_compute and not family.startswith('c'):
                continue
            if is_memory and not family.startswith('r'):
                continue
            if not is_compute and not is_memory:
                if family.startswith('c') or family.startswith('r') or family.startswith('p') or family.startswith('g'):
                    continue
                    
            filtered.append(pool)
            if len(filtered) >= 10:
                break
                
        if not filtered:
            filtered = scored_pools[:10]
            
        return [
            {"instance_type": p.pool.instance_type, "az": p.pool.az} for p in filtered
        ]
