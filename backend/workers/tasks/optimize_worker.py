import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

from sqlalchemy import func, cast, String as SAString
from sqlalchemy.orm import Session

from backend.workers.app import app
from backend.models.base import get_db
from backend.models.cluster import Cluster
from backend.models.pod_metric import PodMetric
from backend.models.node_metadata import NodeMetadata
from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
from backend.models.pricing import OnDemandPricing, SpotPriceHistory
from backend.models.rebalancing_action import RebalancingAction
from backend.models.instance import Instance
from backend.core.logger import logger
from backend.core.redis_client import get_redis_client
from backend.utils.data_freshness import compute_freshness, stale_node_filter
from backend.pipeline.stage3_ppe.engine import NodeOverheadProfiler

_BIN_PACKING_CACHE_KEY = "spot:bin_packing:{cluster_id}"
_BIN_PACKING_CACHE_TTL = 300  # 5 minutes


@app.task(name='workers.compute_node_bin_packing_metrics')
def compute_node_bin_packing_metrics():
    """
    Runs every 1-5 minutes via Celery beat.
    Pre-computes the heavy get_node_bin_packing endpoint data for all active clusters.
    """
    db = next(get_db())
    redis = get_redis_client()

    try:
        from backend.services.bin_packing_service import BinPackingService
        service = BinPackingService(db, redis)
        
        clusters = db.query(Cluster).filter(Cluster.status == 'ACTIVE').all()
        for cluster in clusters:
            try:
                cluster_id = str(cluster.id)
                # This will compute and cache the data in Redis
                service.get_bin_packing_data(cluster_id, force_refresh=True)
                logger.info(f"[optimize_worker] Successfully pre-computed bin packing for {cluster_id}")
            except Exception as e:
                logger.error(f"[optimize_worker] Failed cluster {cluster.id}: {e}")
                
    except Exception as e:
        logger.error(f"[optimize_worker] Failed compute_node_bin_packing_metrics: {e}")
    finally:
        db.close()
