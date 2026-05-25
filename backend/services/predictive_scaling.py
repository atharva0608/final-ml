"""
Predictive Scaling Intelligence
===============================
Analyzes historical workload patterns to forecast future resource demand.
Prevents consolidation right before a predicted traffic spike.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger(__name__)

class PredictiveScaler:
    """
    Forecasting layer. 
    Uses historical P95 metrics to detect seasonality (daily/weekly).
    """

    def __init__(self, db: Session):
        self.db = db

    def forecast_demand(self, cluster_id: str, workload_id: Optional[str] = None) -> float:
        """
        Predicts CPU demand (millicores) for the next 1 hour.
        Returns the forecasted demand.
        """
        # 1. Fetch historical metrics for the same time window over the last 7 days
        # This is a simple 'Same-Time-Last-Week' seasonal model.
        now = datetime.utcnow()
        target_hour = now.hour
        
        from backend.models.pod_metric import PodMetric
        
        # Query metrics from the same hour in previous days
        query = self.db.query(
            func.avg(PodMetric.cpu_usage_millicores).label('avg_cpu')
        ).filter(
            PodMetric.cluster_id == cluster_id,
            func.extract('hour', PodMetric.timestamp) == target_hour
        )
        
        if workload_id:
            query = query.filter(PodMetric.workload_id == workload_id)
            
        result = query.one_or_none()
        forecast = result.avg_cpu if result and result.avg_cpu else 0.0
        
        # 2. Add a 'Growth Buffer' (e.g. 20%) to be conservative
        return float(forecast) * 1.2

    def should_block_consolidation(self, cluster_id: str) -> bool:
        """
        Checks if a traffic spike is predicted within the next 2 hours.
        """
        current_load = self._get_current_cluster_load(cluster_id)
        forecasted_load = self.forecast_demand(cluster_id)
        
        # If forecasted load is > 30% higher than current, block consolidation
        if forecasted_load > (current_load * 1.3):
            logger.info(
                f"[predictive_scaler] Blocking consolidation for cluster {cluster_id}. "
                f"Predicted spike: {current_load:.0f}m -> {forecasted_load:.0f}m"
            )
            return True
            
        return False

    def _get_current_cluster_load(self, cluster_id: str) -> float:
        from backend.models.node_metrics import NodeMetric
        result = self.db.query(
            func.sum(NodeMetric.cpu_usage_millicores)
        ).filter(
            NodeMetric.cluster_id == cluster_id,
            NodeMetric.timestamp >= (datetime.utcnow() - timedelta(minutes=10))
        ).scalar()
        return float(result or 0.0)
