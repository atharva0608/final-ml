"""
Right-Sizing Service - Analyzes pod metrics to generate cost optimization recommendations

This service implements Gap 2 from changelogic.txt analysis:
- Queries pod_metrics time-series data
- Calculates P95/P99 CPU/memory usage percentiles
- Generates right-sizing recommendations with safety buffers
- Estimates cost savings
- Assigns confidence levels based on data quality
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
import statistics

from backend.models.pod_metric import PodMetric
from backend.models.cluster import Cluster
from backend.schemas.pod_metric_schemas import RightSizingRecommendation
from backend.core.logger import logger


class RightSizingService:
    """
    Service for analyzing pod resource usage and generating right-sizing recommendations.
    """

    # Configuration constants
    SAFETY_BUFFER_PCT = 20  # Add 20% buffer above P95 usage for safety
    OVERSIZED_THRESHOLD_PCT = 50  # Flag as oversized if usage < 50% of request
    UNDERSIZED_THRESHOLD_PCT = 95  # Flag as undersized if P99 usage > request

    # Cost estimation — tiered by instance family for accuracy
    # TODO: Replace with real AWS Pricing API data for production use
    # These are on-demand rates for us-east-1 as of 2024 (approximate)
    INSTANCE_FAMILY_COSTS = {
        # family: (cpu_cost_per_core_hour, memory_cost_per_gb_hour)
        "m5": (0.048, 0.006),    # General purpose
        "m6i": (0.046, 0.006),   # Current-gen general purpose
        "c5": (0.042, 0.005),    # Compute optimized
        "c6i": (0.040, 0.005),   # Current-gen compute optimized
        "r5": (0.063, 0.008),    # Memory optimized
        "r6i": (0.063, 0.008),   # Current-gen memory optimized
        "t3": (0.021, 0.003),    # Burstable
        "t3a": (0.019, 0.003),   # AMD Burstable
    }
    # Fallback if family not found (weighted average across common families)
    CPU_COST_PER_CORE_HOUR = 0.04   # Fallback default
    MEMORY_COST_PER_GB_HOUR = 0.005  # Fallback default

    def __init__(self, db: Session):
        self.db = db

    def generate_recommendations(
        self,
        cluster_id: str,
        namespace: Optional[str] = None,
        analysis_window_hours: int = 168,
        min_data_points: int = 100
    ) -> List[RightSizingRecommendation]:
        """
        Generate right-sizing recommendations for workloads in a cluster.

        Args:
            cluster_id: Cluster to analyze
            namespace: Optional namespace filter
            analysis_window_hours: Time window to analyze (default 7 days = 168 hours)
            min_data_points: Minimum metrics required for recommendation

        Returns:
            List of right-sizing recommendations
        """
        # Validate cluster exists
        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise ValueError(f"Cluster {cluster_id} not found")

        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=analysis_window_hours)

        # Get distinct controllers (workloads) in cluster
        controllers = self._get_controllers(cluster_id, namespace, start_time, end_time)

        recommendations = []

        for controller_info in controllers:
            try:
                recommendation = self._analyze_controller(
                    cluster_id=cluster_id,
                    namespace=controller_info['namespace'],
                    controller_kind=controller_info['controller_kind'],
                    controller_name=controller_info['controller_name'],
                    start_time=start_time,
                    end_time=end_time,
                    min_data_points=min_data_points,
                    analysis_window_hours=analysis_window_hours
                )

                if recommendation:
                    recommendations.append(recommendation)

            except Exception as e:
                logger.error(f"Failed to analyze controller {controller_info['controller_name']}: {e}")
                continue

        logger.info(f"Generated {len(recommendations)} right-sizing recommendations for cluster {cluster_id}")

        return recommendations

    def _get_controllers(
        self,
        cluster_id: str,
        namespace: Optional[str],
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """
        Get distinct controllers (workloads) that have metrics in the time range.

        Returns:
            List of dicts with namespace, controller_kind, controller_name
        """
        query = self.db.query(
            PodMetric.namespace,
            PodMetric.controller_kind,
            PodMetric.controller_name
        ).filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.timestamp >= start_time,
            PodMetric.timestamp <= end_time,
            PodMetric.controller_name.isnot(None)  # Must have controller
        )

        if namespace:
            query = query.filter(PodMetric.namespace == namespace)

        # Get distinct controllers
        controllers = query.distinct().all()

        return [
            {
                'namespace': c.namespace,
                'controller_kind': c.controller_kind,
                'controller_name': c.controller_name
            }
            for c in controllers
        ]

    def _analyze_controller(
        self,
        cluster_id: str,
        namespace: str,
        controller_kind: str,
        controller_name: str,
        start_time: datetime,
        end_time: datetime,
        min_data_points: int,
        analysis_window_hours: int
    ) -> Optional[RightSizingRecommendation]:
        """
        Analyze a single controller (Deployment, StatefulSet, etc.) and generate recommendation.

        Args:
            cluster_id: Cluster ID
            namespace: Namespace
            controller_kind: Controller type
            controller_name: Controller name
            start_time: Analysis window start
            end_time: Analysis window end
            min_data_points: Minimum metrics required
            analysis_window_hours: Analysis window in hours

        Returns:
            RightSizingRecommendation or None if insufficient data
        """
        # Fetch all pod metrics for this controller in time range
        metrics = self.db.query(PodMetric).filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.namespace == namespace,
            PodMetric.controller_kind == controller_kind,
            PodMetric.controller_name == controller_name,
            PodMetric.timestamp >= start_time,
            PodMetric.timestamp <= end_time
        ).all()

        if len(metrics) < min_data_points:
            logger.debug(f"Insufficient data for {controller_name}: {len(metrics)} < {min_data_points}")
            return None

        # Calculate statistics
        cpu_stats = self._calculate_statistics(
            [m.cpu_usage_millicores for m in metrics]
        )
        memory_stats = self._calculate_statistics(
            [m.memory_usage_bytes for m in metrics]
        )

        # Get current configuration from latest metric
        latest_metric = metrics[-1]  # Assuming ordered by timestamp
        current_cpu_request = latest_metric.cpu_request_millicores
        current_memory_request_bytes = latest_metric.memory_request_bytes
        current_memory_request_mb = int(current_memory_request_bytes / (1024 * 1024)) if current_memory_request_bytes else None

        # Calculate recommended requests (P95 + 20% buffer)
        recommended_cpu = int(cpu_stats['p95'] * (1 + self.SAFETY_BUFFER_PCT / 100))
        recommended_memory_bytes = int(memory_stats['p95'] * (1 + self.SAFETY_BUFFER_PCT / 100))
        recommended_memory_mb = int(recommended_memory_bytes / (1024 * 1024))

        # Determine current replica count (approximate from distinct pods)
        replica_count = self.db.query(func.count(func.distinct(PodMetric.pod_name))).filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.namespace == namespace,
            PodMetric.controller_name == controller_name,
            PodMetric.timestamp >= end_time - timedelta(hours=1)  # Last hour
        ).scalar() or 1

        # Estimate costs
        current_cost = self._estimate_cost(
            cpu_millicores=current_cpu_request or cpu_stats['avg'],
            memory_mb=current_memory_request_mb or int(memory_stats['avg'] / (1024 * 1024)),
            replica_count=replica_count
        )

        recommended_cost = self._estimate_cost(
            cpu_millicores=recommended_cpu,
            memory_mb=recommended_memory_mb,
            replica_count=replica_count
        )

        savings_monthly = max(0, current_cost - recommended_cost)
        savings_pct = (savings_monthly / current_cost * 100) if current_cost > 0 else 0

        # Determine recommendation action and safety flags
        is_oversized = False
        is_undersized = False
        recommendation_action = "NO_CHANGE"

        if current_cpu_request:
            cpu_usage_pct = (cpu_stats['avg'] / current_cpu_request) * 100
            if cpu_usage_pct < self.OVERSIZED_THRESHOLD_PCT:
                is_oversized = True
                recommendation_action = "REDUCE"
            elif cpu_stats['p99'] > current_cpu_request * (self.UNDERSIZED_THRESHOLD_PCT / 100):
                is_undersized = True
                recommendation_action = "INCREASE"

        # Determine confidence level based on data quality
        confidence = self._calculate_confidence(
            data_points=len(metrics),
            window_hours=analysis_window_hours,
            min_data_points=min_data_points
        )

        return RightSizingRecommendation(
            cluster_id=cluster_id,
            namespace=namespace,
            controller_kind=controller_kind,
            controller_name=controller_name,
            current_cpu_request_millicores=current_cpu_request,
            current_memory_request_mb=current_memory_request_mb,
            current_replica_count=replica_count,
            cpu_p95_millicores=int(cpu_stats['p95']),
            cpu_p99_millicores=int(cpu_stats['p99']),
            memory_p95_mb=int(memory_stats['p95'] / (1024 * 1024)),
            memory_p99_mb=int(memory_stats['p99'] / (1024 * 1024)),
            cpu_avg_millicores=int(cpu_stats['avg']),
            memory_avg_mb=int(memory_stats['avg'] / (1024 * 1024)),
            recommended_cpu_request_millicores=recommended_cpu,
            recommended_memory_request_mb=recommended_memory_mb,
            current_cost_monthly=round(current_cost, 2),
            recommended_cost_monthly=round(recommended_cost, 2),
            savings_monthly=round(savings_monthly, 2),
            savings_pct=round(savings_pct, 1),
            data_points=len(metrics),
            analysis_window_hours=analysis_window_hours,
            confidence=confidence,
            is_oversized=is_oversized,
            is_undersized=is_undersized,
            recommendation_action=recommendation_action
        )

    def _calculate_statistics(self, values: List[float]) -> Dict[str, float]:
        """
        Calculate statistical metrics (avg, P50, P95, P99) for a list of values.

        Args:
            values: List of numeric values (CPU millicores or memory bytes)

        Returns:
            Dict with avg, p50, p95, p99, min, max
        """
        if not values:
            return {'avg': 0, 'p50': 0, 'p95': 0, 'p99': 0, 'min': 0, 'max': 0}

        sorted_values = sorted(values)

        return {
            'avg': statistics.mean(values),
            'p50': statistics.median(values),
            'p95': self._percentile(sorted_values, 95),
            'p99': self._percentile(sorted_values, 99),
            'min': min(values),
            'max': max(values)
        }

    def _percentile(self, sorted_values: List[float], percentile: float) -> float:
        """
        Calculate percentile from sorted list of values.

        Args:
            sorted_values: Pre-sorted list of values
            percentile: Percentile to calculate (0-100)

        Returns:
            Value at specified percentile
        """
        if not sorted_values:
            return 0

        index = int((percentile / 100) * len(sorted_values))
        index = min(index, len(sorted_values) - 1)  # Ensure within bounds

        return sorted_values[index]

    def _estimate_cost(self, cpu_millicores: int, memory_mb: int, replica_count: int) -> float:
        """
        Estimate monthly cost based on resource requests and replica count.

        Simplified cost model - can be enhanced with actual instance pricing.

        Args:
            cpu_millicores: CPU request in millicores
            memory_mb: Memory request in MB
            replica_count: Number of replicas

        Returns:
            Estimated monthly cost in USD
        """
        cpu_cores = cpu_millicores / 1000.0
        memory_gb = memory_mb / 1024.0

        # Cost per hour
        cpu_cost_hour = cpu_cores * self.CPU_COST_PER_CORE_HOUR
        memory_cost_hour = memory_gb * self.MEMORY_COST_PER_GB_HOUR
        total_cost_hour = (cpu_cost_hour + memory_cost_hour) * replica_count

        # Monthly cost (730 hours/month)
        monthly_cost = total_cost_hour * 730

        return monthly_cost

    def _calculate_confidence(self, data_points: int, window_hours: int, min_data_points: int) -> str:
        """
        Calculate confidence level for recommendation based on data quality.

        Args:
            data_points: Number of metric data points collected
            window_hours: Analysis window in hours
            min_data_points: Minimum required data points

        Returns:
            Confidence level: HIGH, MEDIUM, or LOW
        """
        # Expected data points: 12 samples/hour (every 5 minutes)
        expected_points = window_hours * 12

        # Calculate coverage percentage
        coverage_pct = (data_points / expected_points) * 100

        if coverage_pct >= 80:
            return "HIGH"
        elif coverage_pct >= 50:
            return "MEDIUM"
        else:
            return "LOW"
