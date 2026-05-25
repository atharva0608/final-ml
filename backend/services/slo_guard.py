"""
SLO Guard Engine
================
Evaluates application health (latency, error rates, lag) before and after
optimization actions to ensure stability.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class SLOGuard:
    """
    Monitoring layer for application SLOs.
    In production, this would query Prometheus, CloudWatch, or Datadog.
    Current implementation reads from Redis for simulated/cached metrics.
    """

    def __init__(self, redis_client):
        self.redis = redis_client

    def is_workload_healthy(self, cluster_id: str, workload_id: str) -> bool:
        """
        Check if the specific workload is within SLO bounds.
        Returns True if healthy (within bounds), False if unhealthy.
        """
        # 1. Fetch metrics from Redis (provided by the agent or telemetry collector)
        # In a real system, these keys would be populated by a metrics-sync service.
        p95_latency = self._get_metric(cluster_id, workload_id, "p95_latency", 200.0) # ms
        error_rate = self._get_metric(cluster_id, workload_id, "error_rate", 0.01)    # 1%
        kafka_lag = self._get_metric(cluster_id, workload_id, "kafka_lag", 0.0)       # messages
        
        # 2. Define Thresholds (should be configurable via database)
        THRESHOLDS = {
            "p95_latency": 500.0,  # 500ms max
            "error_rate": 0.05,    # 5% max
            "kafka_lag": 1000.0    # 1000 messages max
        }
        
        # 3. Validation Logic
        if p95_latency > THRESHOLDS["p95_latency"]:
            logger.warning(f"[slo_guard] Unhealthy cluster={cluster_id} workload={workload_id}: p95_latency={p95_latency}ms")
            return False
            
        if error_rate > THRESHOLDS["error_rate"]:
            logger.warning(f"[slo_guard] Unhealthy cluster={cluster_id} workload={workload_id}: error_rate={error_rate*100}%")
            return False
            
        if kafka_lag > THRESHOLDS["kafka_lag"]:
            logger.warning(f"[slo_guard] Unhealthy cluster={cluster_id} workload={workload_id}: kafka_lag={kafka_lag}")
            return False
            
        return True

    def _get_metric(self, cluster_id: str, workload_id: str, metric_name: str, default: float) -> float:
        """Fetch metric from Redis cache."""
        try:
            key = f"spot:slo:{cluster_id}:{workload_id}:{metric_name}"
            val = self.redis.get(key)
            if val:
                return float(val.decode() if isinstance(val, bytes) else val)
        except Exception:
            pass
        return default

    def block_optimization(self, cluster_id: str) -> bool:
        """
        Check cluster-wide health. Returns True to block optimizations if
        the cluster is generally unstable (e.g., API server load, DNS pressure).
        """
        api_load = self._get_cluster_metric(cluster_id, "api_server_load", 0.5)
        dns_latency = self._get_cluster_metric(cluster_id, "dns_latency", 50.0)
        
        if api_load > 0.9 or dns_latency > 200.0:
            logger.error(f"[slo_guard] Cluster {cluster_id} unstable: api_load={api_load}, dns_latency={dns_latency}ms")
            return True
            
        return False

    def _get_cluster_metric(self, cluster_id: str, metric_name: str, default: float) -> float:
        """Fetch cluster-level metric from Redis."""
        try:
            key = f"spot:cluster_slo:{cluster_id}:{metric_name}"
            val = self.redis.get(key)
            if val:
                return float(val.decode() if isinstance(val, bytes) else val)
        except Exception:
            pass
        return default
