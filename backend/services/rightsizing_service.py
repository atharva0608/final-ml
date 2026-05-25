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
import json
import statistics
import math

from backend.models.pod_metric import PodMetric
from backend.models.cluster import Cluster
from backend.schemas.pod_metric_schemas import RightSizingRecommendation
from backend.core.logger import logger
from backend.services.cooldown_controller import CooldownController
from backend.services.workload_inspector import WorkloadInspector, NodeStatus
from backend.services.global_pool_cache_service import GlobalPoolCacheService
from backend.services.blacklist_service import BlacklistService
from backend.core.decision_engine import DecisionEngine
from backend.core.scoring import compute_expected_value


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
        # Initialize Redis client for pricing lookups
        try:
            from backend.core.redis_client import get_redis_client
            self.redis = get_redis_client()
        except Exception as e:
            logger.warning(f"Failed to initialize Redis client: {e}")
            self.redis = None

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

        # Check instance-aware mode from cluster settings
        instance_aware = False
        try:
            opt_settings = cluster.optimization_settings
            if opt_settings and getattr(opt_settings, 'instance_aware_rightsizing', False):
                instance_aware = True
                logger.info(f"Instance-aware rightsizing ENABLED for cluster {cluster_id}")
        except Exception:
            pass

        # ── METRIC FRESHNESS (ENH 6) ─────────────────────────────────
        # Reject rightsizing if latest metrics are stale (> 5 min lag)
        try:
            latest_metric = self.db.query(PodMetric).filter(
                PodMetric.cluster_id == cluster_id
            ).order_by(PodMetric.timestamp.desc()).first()
            if latest_metric:
                lag_minutes = (datetime.utcnow() - latest_metric.timestamp).total_seconds() / 60
                if lag_minutes > 5:
                    logger.warning(f"Metric lag {lag_minutes:.0f}m for cluster {cluster_id}, skipping rightsizing")
                    return []
            else:
                logger.warning(f"No metrics found for cluster {cluster_id}")
                return []
        except Exception as e:
            logger.warning(f"Metric freshness check failed: {e}")

        # 1. CHECK CLUSTER COOLDOWN
        cooldown = CooldownController(self.redis)
        can_switch, remaining = cooldown.can_switch(cluster_id)
        if not can_switch:
            logger.info(f"Cluster {cluster_id} in cooldown ({remaining}s), no recommendations")
            return []

        # 2. CHECK NODE CLASSIFICATION
        # Skip node-level classification check for now - we'll do pod-level analysis
        # and filter recommendations based on workload type
        inspector = WorkloadInspector(self.redis, k8s_client=None)
        classification = inspector.get_cached_classification(cluster_id)

        # If no cached classification, proceed anyway - we'll analyze all pods
        if not classification:
            logger.info(f"No cached node classification for {cluster_id} - proceeding with pod analysis")
            eligible_nodes = None  # Analyze all nodes
        else:
            eligible_nodes = [
                node for node, status in classification.items()
                if status == NodeStatus.STATELESS_ELIGIBLE
            ]
            if not eligible_nodes:
                logger.info(f"No stateless-eligible nodes in {cluster_id}")
                return []

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
                    # v4.3 WIE confidence gate — skip DRAFT workloads (insufficient data)
                    # Only applies when WIE engine has run (Redis key exists). Missing = no gate (backward compatible).
                    if self.redis:
                        _wie_key = (
                            f"spot:wie:classification:{cluster_id}:"
                            f"{controller_info['namespace']}/{controller_info['controller_name']}"
                        )
                        _wie_raw = self.redis.get(_wie_key)
                        if _wie_raw:
                            import json as _wie_json
                            _wie = _wie_json.loads(_wie_raw)
                            if _wie.get("confidence_state") == "DRAFT":
                                logger.info(
                                    f"Skipping {controller_info['controller_name']}: "
                                    f"WIE confidence=DRAFT (insufficient observation data)"
                                )
                                continue

                    # Instance-aware filtering: check if a better spot pool exists
                    if instance_aware:
                        pool_exists, pool_info = self._check_better_pool_exists(
                            cluster_id=cluster_id,
                            recommended_cpu_m=recommendation.recommended_cpu_request_millicores,
                            recommended_memory_mb=recommendation.recommended_memory_request_mb,
                            region=getattr(cluster, 'region', 'us-east-1')
                        )
                        recommendation.is_actionable = pool_exists
                        recommendation.best_pool = pool_info
                        if not pool_exists:
                            logger.info(
                                f"Skipping {controller_info['controller_name']}: "
                                f"instance-aware check — no better spot pool found"
                            )
                            continue  # Skip this recommendation
                    else:
                        recommendation.is_actionable = True
                        recommendation.best_pool = None

                    recommendations.append(recommendation)

            except Exception as e:
                logger.error(f"Failed to analyze controller {controller_info['controller_name']}: {e}")
                continue

        logger.info(f"Generated {len(recommendations)} initial right-sizing recommendations for cluster {cluster_id}")

        # 3. INTERSECT WITH GLOBAL RANKINGS AND APPLY DELTA ALIGNMENT
        # TODO: Re-enable when Decision Engine v3 is fully integrated
        # For now, skip this advanced filtering and return base recommendations
        # if recommendations:
        #     # Get cluster optimization profile
        #     mode = cluster.optimization_mode or "BALANCED"
        #     profile = DecisionEngine.OPTIMIZATION_PROFILES.get(mode, DecisionEngine.OPTIMIZATION_PROFILES["BALANCED"])
        #
        #     # Determine region from cluster
        #     region = getattr(cluster, 'region', 'us-east-1')
        #
        #     # Intersect with global rankings
        #     cache = GlobalPoolCacheService(self.db, self.redis)
        #     global_rankings = cache.get_or_compute_global_rankings(region)
        #
        #     # Filter by: in global rankings AND below mode risk ceiling AND not blacklisted AND capacity ok
        #     blacklist_svc = BlacklistService(self.redis)
        #     safe_pools = [
        #         p for p in global_rankings
        #         if p["risk_probability"] <= profile["risk_ceiling"]
        #         and p.get("capacity_status") != "unavailable"
        #         and not blacklist_svc.is_pool_blacklisted(p["instance_type"], p["az"], region)
        #     ]
        #     safe_types = {p["instance_type"] for p in safe_pools}
        #
        #     # Filter recommendations to only include safe instance types
        #     # Note: For pod right-sizing, we don't have instance_type, so we skip this filter
        #     # This logic is primarily for instance-level recommendations
        #     logger.info(f"Found {len(safe_pools)} safe instance pools for cluster {cluster_id}")
        #
        #     # Re-score using shared scoring utility (if applicable)
        #     # For pod right-sizing, we calculate expected value from savings
        #     for rec in recommendations:
        #         # Default risk probability for pod right-sizing (can be enhanced later)
        #         risk_prob = 0.05 if rec.confidence == "HIGH" else 0.10 if rec.confidence == "MEDIUM" else 0.15
        #         rec.expected_value = compute_expected_value(
        #             rec.savings_monthly, risk_prob
        #         )
        #         rec.risk_prob = risk_prob
        #         rec.capacity_status = "validated"
        #
        #     # Sort by expected value descending
        #     recommendations.sort(key=lambda r: getattr(r, 'expected_value', 0), reverse=True)
        #
        #     # DELTA ALIGNMENT: Only show recommendations where delta >= threshold
        #     # Get current pool savings and risk (if available)
        #     current_pool_savings = 0.0
        #     current_pool_risk = 0.0
        #
        #     # For pod right-sizing, we calculate current EV from current costs
        #     if recommendations:
        #         # Calculate baseline expected value (current state)
        #         current_ev = compute_expected_value(current_pool_savings, current_pool_risk)
        #
        #         # Filter recommendations where improvement >= min_savings_threshold
        #         min_delta = profile.get("min_savings_threshold", 0.0)
        #         recommendations = [
        #             r for r in recommendations
        #             if getattr(r, 'expected_value', 0) - current_ev >= min_delta
        #         ]
        #
        #         # Return top 3 recommendations
        #         recommendations = recommendations[:3]
        #
        #         logger.info(f"After delta alignment: {len(recommendations)} recommendations (min_delta=${min_delta:.2f})")

        logger.info(f"Final: {len(recommendations)} right-sizing recommendations for cluster {cluster_id}")

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
        ).order_by(PodMetric.timestamp).all()

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
        current_cpu_request = latest_metric.cpu_request_millicores or None
        current_memory_request_bytes = latest_metric.memory_request_bytes or None
        current_memory_request_mb = math.ceil(current_memory_request_bytes / (1024 * 1024)) if current_memory_request_bytes else None

        # ── PHASE-AWARE SAFETY BUFFER (ENH 1) ──────────────────────────
        # Get phase-aware buffer (Phase 0=30%, Phase 1=25%, Phase 2=20%)
        safety_buffer = self.SAFETY_BUFFER_PCT
        try:
            from backend.services.optimizer_coordinator import OptimizerCoordinator
            coordinator = OptimizerCoordinator(self.db, self.redis)
            trust = coordinator.get_cluster_trust_phase(cluster_id)
            safety_buffer = trust["safety_buffer_pct"]
            logger.info(f"Phase-aware buffer: {safety_buffer}% (Phase {trust['phase']})")
        except Exception:
            pass

        # ── VOLATILITY-AWARE BUFFER (ENH 8) ────────────────────────────
        # Further increase safety buffer in volatile markets
        try:
            if self.redis:
                cluster_obj = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
                region = cluster_obj.region if cluster_obj else "us-east-1"
                is_volatile = self.redis.get(f"spot:volatility_regime:{region}")
                if is_volatile in (b"true", "true", b"active", "active"):
                    safety_buffer = max(safety_buffer, 35)  # Increase to at least 35% in volatile markets
                    logger.info(f"Volatile market: safety buffer increased to {safety_buffer}%")
        except Exception:
            pass

        # Calculate recommended requests (P95 + dynamic buffer)
        recommended_cpu = int(cpu_stats['p95'] * (1 + safety_buffer / 100))
        recommended_memory_bytes = int(memory_stats['p95'] * (1 + safety_buffer / 100))
        recommended_memory_mb = math.ceil(recommended_memory_bytes / (1024 * 1024))

        # ── P99 FALLBACK FLOOR (ENH 3) ───────────────────────────────
        # Proposed size must exceed P99 * 1.3 to handle bursts safely
        p99_cpu_floor = int(cpu_stats['p99'] * 1.3)
        p99_memory_floor = int(memory_stats['p99'] * 1.3)
        recommended_cpu = max(recommended_cpu, p99_cpu_floor)
        recommended_memory_bytes = max(recommended_memory_bytes, p99_memory_floor)
        recommended_memory_mb = math.ceil(recommended_memory_bytes / (1024 * 1024))

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
            memory_mb=current_memory_request_mb or math.ceil(memory_stats['avg'] / (1024 * 1024)),
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

        # ── CONFIDENCE GATE (ENH 2) ──────────────────────────────────────
        # Block proposals from low-confidence evaluations
        if confidence == "LOW":
            logger.info(f"Skipping {controller_name}: LOW confidence ({len(metrics)} samples)")
            return None

        # Volatility check — skip only extreme spike workloads (P50 < 5% of P99)
        if cpu_stats.get('p99', 0) > 0:
            cpu_volatility = (cpu_stats['p99'] - cpu_stats['p50']) / cpu_stats['p99']
            if cpu_volatility > 0.95:
                logger.warning(f"Skipping {controller_name}: extreme CPU spike workload ({cpu_volatility:.2f})")
                return None

        # ── BURST RATIO & JVM DETECTION (Phase 2B) ───────────────────────
        burst_ratio = cpu_stats['p99'] / max(cpu_stats['avg'], 1.0)

        _jvm_name_signals = ['java', 'spring', 'jvm', 'tomcat', 'quarkus', 'micronaut',
                             'openjdk', 'amazoncorretto', 'adoptopenjdk']
        is_jvm = any(s in controller_name.lower() for s in _jvm_name_signals)
        if not is_jvm and current_cpu_request and current_memory_request_bytes:
            _mem_mb = current_memory_request_bytes / (1024.0 * 1024.0)
            _cpu_cores = current_cpu_request / 1000.0
            if _cpu_cores > 0 and (_mem_mb / _cpu_cores) > 4:
                is_jvm = True
        if not is_jvm:
            _mem_growth = memory_stats['p99'] / max(memory_stats['avg'], 1.0)
            if _mem_growth > 1.8:
                is_jvm = True

        workload_hint = "JVM" if is_jvm else "NORMAL"
        _burst_threshold = 3.0 if is_jvm else 5.0
        throttle_risk = burst_ratio > _burst_threshold

        if is_jvm:
            _p99_jvm_floor = int(cpu_stats['p99'] * 1.6)
            recommended_cpu = max(recommended_cpu, _p99_jvm_floor)
            _rec_mem_bytes = int(memory_stats['p95'] * (1 + safety_buffer / 100))
            recommended_memory_mb = math.ceil(_rec_mem_bytes / (1024 * 1024))
            recommended_cost = self._estimate_cost(recommended_cpu, recommended_memory_mb, replica_count)
            savings_monthly = max(0, current_cost - recommended_cost)
            savings_pct = (savings_monthly / current_cost * 100) if current_cost > 0 else 0

        if throttle_risk and recommendation_action == "REDUCE":
            recommendation_action = "OBSERVE"
            savings_monthly = 0.0
            savings_pct = 0.0
            logger.info(
                f"[rightsizing] {controller_name}: REDUCE→OBSERVE "
                f"burst_ratio={burst_ratio:.1f} threshold={_burst_threshold} jvm={is_jvm}"
            )

        # ── ACTIVE SPIKE DETECTION (Phase 2B) ────────────────────────────
        currently_spiking = False
        if self.redis:
            try:
                _spike_key = f"spike:active:{cluster_id}:{namespace}/{controller_name}"
                currently_spiking = bool(self.redis.exists(_spike_key))
            except Exception:
                pass

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
            memory_p95_mb=math.ceil(memory_stats['p95'] / (1024 * 1024)),
            memory_p99_mb=math.ceil(memory_stats['p99'] / (1024 * 1024)),
            cpu_avg_millicores=int(cpu_stats['avg']),
            memory_avg_mb=math.ceil(memory_stats['avg'] / (1024 * 1024)),
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
            recommendation_action=recommendation_action,
            burst_ratio=round(burst_ratio, 2),
            throttle_risk=throttle_risk,
            workload_hint=workload_hint,
            currently_spiking=currently_spiking,
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

        index = int((percentile / 100) * (len(sorted_values) - 1))
        index = min(index, len(sorted_values) - 1)  # Ensure within bounds

        return sorted_values[index]

    def _estimate_cost(self, cpu_millicores: int, memory_mb: int, replica_count: int) -> float:
        """
        Estimate monthly cost based on resource requests and replica count.

        Uses Redis pricing cache if available, falls back to instance family costs,
        then to default rates.

        Args:
            cpu_millicores: CPU request in millicores
            memory_mb: Memory request in MB
            replica_count: Number of replicas

        Returns:
            Estimated monthly cost in USD
        """
        cpu_cores = cpu_millicores / 1000.0
        memory_gb = memory_mb / 1024.0

        # Try to get pricing from Redis cache (populated by resource_pricing_worker)
        cpu_rate = None
        mem_rate = None

        if self.redis:
            try:
                # Try to get pricing for common instance family based on cpu:mem ratio
                ratio = cpu_cores / memory_gb if memory_gb > 0 else 0

                # Determine likely instance family based on ratio
                # c-family: ~1:2 ratio, m-family: ~1:4 ratio, r-family: ~1:8 ratio
                if ratio >= 0.4:  # High CPU ratio
                    family = "c5"
                elif ratio >= 0.2:  # Balanced
                    family = "m5"
                else:  # High memory ratio
                    family = "r5"

                # Try to get rates from Redis
                cpu_key = f"pricing:ec2:{family}:cpu_per_core_hour"
                mem_key = f"pricing:ec2:{family}:mem_per_gb_hour"

                cpu_cached = self.redis.get(cpu_key)
                mem_cached = self.redis.get(mem_key)

                if cpu_cached:
                    cpu_rate = float(cpu_cached)
                if mem_cached:
                    mem_rate = float(mem_cached)

                if cpu_rate and mem_rate:
                    logger.debug(f"Using Redis pricing for {family}: CPU=${cpu_rate}/core/hr, MEM=${mem_rate}/GB/hr")
            except Exception as e:
                logger.warning(f"Failed to get pricing from Redis: {e}")

        # Fallback to instance family costs if Redis lookup failed
        if cpu_rate is None or mem_rate is None:
            # Determine family based on CPU:memory ratio
            ratio = cpu_cores / memory_gb if memory_gb > 0 else 0

            if ratio >= 0.4:
                family_key = "c5"
            elif ratio >= 0.2:
                family_key = "m5"
            else:
                family_key = "r5"

            family_rates = self.INSTANCE_FAMILY_COSTS.get(family_key)
            if family_rates:
                cpu_rate = family_rates[0]
                mem_rate = family_rates[1]
                logger.debug(f"Using family pricing for {family_key}: CPU=${cpu_rate}/core/hr, MEM=${mem_rate}/GB/hr")

        # Final fallback to default rates
        if cpu_rate is None:
            cpu_rate = self.CPU_COST_PER_CORE_HOUR
        if mem_rate is None:
            mem_rate = self.MEMORY_COST_PER_GB_HOUR

        # Cost per hour
        cpu_cost_hour = cpu_cores * cpu_rate
        memory_cost_hour = memory_gb * mem_rate
        total_cost_hour = (cpu_cost_hour + memory_cost_hour) * replica_count

        # Monthly cost (730 hours/month)
        monthly_cost = total_cost_hour * 730

        return monthly_cost

    def _calculate_confidence(self, data_points: int, window_hours: int, min_data_points: int) -> str:
        """
        Calculate confidence level for recommendation based on data quality.

        Considers both data point count and window coverage ratio to ensure
        sparse data over long windows doesn't receive inflated confidence.
        """
        # Window coverage: expect ~1 data point per 5 minutes (12/hour)
        expected_points = max(1, window_hours * 12)
        coverage_ratio = data_points / expected_points  # 0.0 – 1.0+

        if data_points >= min_data_points * 5 and coverage_ratio >= 0.5:
            return "HIGH"
        elif data_points >= min_data_points and coverage_ratio >= 0.2:
            return "MEDIUM"
        else:
            return "LOW"

    # ========================================================================
    # PROPOSAL-ONLY MODE (Unified Optimizer Coordination)
    # ========================================================================

    def create_rightsizing_proposals(
        self,
        cluster_id: str,
        min_savings_pct: float = 10.0,
        stability_window_hours: int = 24,
        include_stateful: bool = True,
    ) -> List[str]:
        """
        Create rightsizing proposals instead of immediate recommendations.

        This method is used by the Unified Optimizer Coordinator to implement
        the phased optimization approach from problems.md:

        - Only proposes, never executes directly
        - Requires ≥24 hour stability window
        - Requires ≥10-15% minimum savings delta
        - Coordinator evaluates proposals with combined EV calculation

        Args:
            cluster_id: Cluster to analyze
            min_savings_pct: Minimum savings percentage required (default 10%)
            stability_window_hours: Required stability window (default 24 hours)

        Returns:
            List of created proposal IDs
        """
        from backend.models.rightsizing_proposal import RightsizingProposal, ProposalStatus

        # Generate recommendations using existing logic
        recommendations = self.generate_recommendations(
            cluster_id=cluster_id,
            analysis_window_hours=stability_window_hours,  # Use stability window for analysis
            min_data_points=100
        )

        # W4.2/W4.3 — Tier-based filtering.
        # TIER_0 (DaemonSet / system) is ALWAYS excluded — never rightsize
        # workloads that must never migrate.
        # TIER_1 (ANCHORED_MANUAL / stateful databases) excluded unless
        # include_stateful=True (i.e. auto_stateful_rightsizing_enabled toggle).
        if self.redis:
            tier_filtered = []
            for rec in recommendations:
                try:
                    tier_key = (
                        f"spot:workload_tier:{cluster_id}:"
                        f"{rec.namespace}/{rec.controller_name}"
                    )
                    tier_raw = self.redis.get(tier_key)
                    tier_data = json.loads(tier_raw) if tier_raw else {}
                    tier = tier_data.get("tier", 4)  # default TIER_4 (permissive)
                    if tier == 0:
                        logger.debug(
                            f"[RightSizing] Skipping TIER_0 controller "
                            f"{rec.namespace}/{rec.controller_name} (NEVER_MIGRATE)"
                        )
                        continue
                    if tier == 1 and not include_stateful:
                        logger.debug(
                            f"[RightSizing] Skipping TIER_1 controller "
                            f"{rec.namespace}/{rec.controller_name} "
                            f"(auto_stateful_rightsizing disabled)"
                        )
                        continue
                    tier_filtered.append(rec)
                except Exception:
                    tier_filtered.append(rec)  # fail-open: include on any error
            recommendations = tier_filtered

        # Filter by minimum savings percentage
        filtered_recs = [
            rec for rec in recommendations
            if rec.savings_pct and rec.savings_pct >= min_savings_pct
        ]

        logger.info(
            f"Filtered {len(recommendations)} recommendations to {len(filtered_recs)} "
            f"meeting {min_savings_pct}% savings threshold"
        )

        # ── TEMPLATE ENFORCEMENT (FIX 1 — P0) ────────────────────────
        # Load cluster's active template constraints and reject proposals
        # that violate template bounds BEFORE storing them.
        from backend.models.node_template import ClusterTemplateMapping, NodeTemplateVersion

        template_constraints = None
        active_mapping = self.db.query(ClusterTemplateMapping).filter(
            ClusterTemplateMapping.cluster_id == cluster_id,
            ClusterTemplateMapping.is_default == True
        ).first()

        if active_mapping and active_mapping.version_id:
            version = self.db.query(NodeTemplateVersion).filter(
                NodeTemplateVersion.id == active_mapping.version_id
            ).first()
            if version and version.constraints_json:
                template_constraints = version.constraints_json
                logger.info(f"Loaded template constraints for cluster {cluster_id}")

        if template_constraints:
            template_filtered = []
            for rec in filtered_recs:
                proposed_vcpu = max(1, int(rec.recommended_cpu_request_millicores / 1000))
                proposed_memory_gb = max(1, int(rec.recommended_memory_request_mb / 1024))
                proposed_type = self._suggest_instance_type(proposed_vcpu, proposed_memory_gb)
                proposed_family = proposed_type.split('.')[0] if proposed_type else ""

                min_v = template_constraints.get("min_vcpu", 1)
                max_v = template_constraints.get("max_vcpu", 256)
                min_m = template_constraints.get("min_memory_gb", 1)
                max_m = template_constraints.get("max_memory_gb", 1024)
                allowed = template_constraints.get("allowed_families", [])
                excluded = template_constraints.get("excluded_families", [])

                if not (min_v <= proposed_vcpu <= max_v):
                    logger.warning(f"Template rejected: {proposed_vcpu} vCPU outside [{min_v}, {max_v}]")
                    continue
                if not (min_m <= proposed_memory_gb <= max_m):
                    logger.warning(f"Template rejected: {proposed_memory_gb} GB outside [{min_m}, {max_m}]")
                    continue
                if allowed and proposed_family not in allowed:
                    logger.warning(f"Template rejected: family {proposed_family} not in allowed list")
                    continue
                if proposed_family in excluded:
                    logger.warning(f"Template rejected: family {proposed_family} is excluded")
                    continue

                template_filtered.append(rec)

            logger.info(f"Template enforcement: {len(filtered_recs)} → {len(template_filtered)}")
            filtered_recs = template_filtered

        # Get cluster for node info
        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise ValueError(f"Cluster {cluster_id} not found")

        # Create proposals for each filtered recommendation
        proposal_ids = []

        for rec in filtered_recs:
            try:
                # Estimate current instance type and costs
                # TODO: Get actual current node info from cluster
                current_instance_type = "m5.large"  # Placeholder
                current_vcpu = 2
                current_memory_gb = 8
                current_hourly_cost = 0.096  # Placeholder

                # Calculate proposed instance type from resource requirements
                proposed_vcpu = max(1, int(rec.recommended_cpu_request_millicores / 1000))
                proposed_memory_gb = max(1, int(rec.recommended_memory_request_mb / 1024))
                proposed_instance_type = self._suggest_instance_type(proposed_vcpu, proposed_memory_gb)
                proposed_hourly_cost = self._estimate_instance_cost(proposed_vcpu, proposed_memory_gb, "m5")

                # Create proposal
                proposal = RightsizingProposal(
                    cluster_id=cluster_id,
                    current_instance_type=current_instance_type,
                    current_vcpu=current_vcpu,
                    current_memory_gb=current_memory_gb,
                    current_pool=f"{current_instance_type}:current-az",  # Placeholder
                    current_hourly_cost=current_hourly_cost,
                    proposed_instance_type=proposed_instance_type,
                    proposed_vcpu=proposed_vcpu,
                    proposed_memory_gb=proposed_memory_gb,
                    proposed_hourly_cost=proposed_hourly_cost,
                    estimated_hourly_savings=(current_hourly_cost - proposed_hourly_cost),
                    estimated_monthly_savings=rec.savings_monthly,
                    savings_percentage=rec.savings_pct,
                    avg_cpu_utilization_pct=round(rec.cpu_avg_millicores / rec.current_cpu_request_millicores * 100, 2) if rec.current_cpu_request_millicores else 0,
                    p95_cpu_utilization_pct=round(rec.cpu_p95_millicores / rec.current_cpu_request_millicores * 100, 2) if rec.current_cpu_request_millicores else 0,
                    avg_memory_utilization_pct=round(rec.memory_avg_mb / rec.current_memory_request_mb * 100, 2) if rec.current_memory_request_mb else 0,
                    p95_memory_utilization_pct=round(rec.memory_p95_mb / rec.current_memory_request_mb * 100, 2) if rec.current_memory_request_mb else 0,
                    metric_sample_count=rec.data_points,
                    metric_window_hours=float(stability_window_hours),
                    status=ProposalStatus.PENDING
                )

                # ── Task 3.3: Inject EV breakdown into proposals ──────
                # Compute full economic EV and store at creation time so
                # the coordinator reads the same number downstream
                try:
                    from backend.core.ev_model import evaluate_candidate_ev, get_dynamic_capacity_failure_probability
                    
                    proposal_savings = current_hourly_cost - proposed_hourly_cost
                    risk_score = 0.05 if rec.confidence == "HIGH" else 0.10 if rec.confidence == "MEDIUM" else 0.15
                    current_volatility = 0.0  # Default — could be read from Redis
                    pool_id = f"{proposed_instance_type}:{cluster.region or 'us-east-1'}"
                    
                    if self.redis:
                        cap_fail_prob = get_dynamic_capacity_failure_probability(
                            self.redis, pool_id, cluster.region or "us-east-1"
                        )
                    else:
                        cap_fail_prob = 0.05
                    
                    ev_breakdown = evaluate_candidate_ev(
                        savings=proposal_savings,
                        final_risk=risk_score,
                        normalized_volatility=current_volatility,
                        capacity_failure_probability=cap_fail_prob,
                        downtime_cost_per_hour=100.0,
                        risk_horizon_hours=2.0,
                        recovery_time_hours=0.5,
                    )
                    
                    proposal.ev_breakdown = ev_breakdown  # JSONField — stores full dict
                    proposal.net_ev = ev_breakdown["ev"]   # FloatField — for quick sorting
                except Exception as ev_err:
                    logger.warning(f"Failed to compute EV breakdown for proposal: {ev_err}")
                    # Proposal still created without EV breakdown — fallback path

                self.db.add(proposal)
                self.db.commit()
                self.db.refresh(proposal)

                proposal_ids.append(proposal.id)
                logger.info(f"Created rightsizing proposal {proposal.id} for cluster {cluster_id}")

            except Exception as e:
                logger.error(f"Failed to create proposal for recommendation: {e}")
                continue

        return proposal_ids
    # ========================================================================
    # INSTANCE-AWARE RIGHTSIZING — Double-Gate Pool Check
    # ========================================================================

    def _check_better_pool_exists(
        self,
        cluster_id: str,
        recommended_cpu_m: int,
        recommended_memory_mb: int,
        region: str = "us-east-1"
    ) -> tuple:
        """
        Check if a better spot pool exists for the recommended resource profile.

        Double gate:
          1. risk < ceiling (default 0.15)
          2. spot price < on-demand price for equivalent instance

        Args:
            cluster_id: Cluster ID
            recommended_cpu_m: Recommended CPU in millicores
            recommended_memory_mb: Recommended memory in MB
            region: AWS region

        Returns:
            (exists: bool, pool_info: dict | None)
        """
        try:
            cache = GlobalPoolCacheService(self.db, self.redis)
            blacklist_svc = BlacklistService(self.redis)

            # Get global rankings for this region
            global_rankings = cache.get_or_compute_global_rankings(region)
            if not global_rankings:
                logger.info(f"No global rankings available for region {region}")
                return (False, None)

            # Determine target instance size from recommended resources
            target_vcpu = max(1, int(recommended_cpu_m / 1000))
            target_memory_gb = max(1, int(recommended_memory_mb / 1024))

            # Get on-demand price for equivalent size
            od_hourly = self._estimate_instance_cost(target_vcpu, target_memory_gb, "m5")

            # Risk ceiling: accept pools with risk < 15%
            RISK_CEILING = 0.15

            # Filter candidates: match resource profile, below risk ceiling,
            # below on-demand price, not blacklisted
            best_candidate = None
            best_ev = -float('inf')

            for pool in global_rankings:
                pool_type = pool.get("instance_type", "")
                pool_az = pool.get("az", "")
                pool_risk = pool.get("risk_probability", 1.0)
                pool_price = pool.get("spot_price", float('inf'))
                pool_vcpu = pool.get("vcpus", 0)
                pool_memory = pool.get("memory_gb", 0)

                # Size gate: pool must fit the recommended workload
                if pool_vcpu < target_vcpu or pool_memory < target_memory_gb:
                    continue

                # Don't over-provision by more than 2x
                if pool_vcpu > target_vcpu * 2 or pool_memory > target_memory_gb * 2:
                    continue

                # Double gate #1: risk < ceiling
                if pool_risk > RISK_CEILING:
                    continue

                # Double gate #2: spot price < on-demand price
                if pool_price >= od_hourly:
                    continue

                # Blacklist check
                if blacklist_svc.is_pool_blacklisted(pool_type, pool_az, region):
                    continue

                # Capacity check
                if pool.get("capacity_status") == "unavailable":
                    continue

                # Select by highest expected savings (lowest price * lowest risk)
                savings = od_hourly - pool_price
                ev = savings * (1 - pool_risk)
                if ev > best_ev:
                    best_ev = ev
                    best_candidate = {
                        "instance_type": pool_type,
                        "az": pool_az,
                        "risk_score": round(pool_risk, 4),
                        "spot_price": round(pool_price, 4),
                        "od_price": round(od_hourly, 4),
                        "predicted_savings_pct": round((1 - pool_price / od_hourly) * 100, 1) if od_hourly > 0 else 0,
                        "ev": round(best_ev, 4),
                    }

            if best_candidate:
                logger.info(
                    f"Instance-aware: found better pool {best_candidate['instance_type']} "
                    f"in {best_candidate['az']} — savings {best_candidate['predicted_savings_pct']}%"
                )
                return (True, best_candidate)
            else:
                logger.info(f"Instance-aware: no pool passes double gate for {target_vcpu}vCPU/{target_memory_gb}GB")
                return (False, None)

        except Exception as e:
            logger.warning(f"Instance-aware pool check failed, defaulting to actionable: {e}")
            return (True, None)  # Fail open — don't block recommendations on errors

    def _suggest_instance_type(self, vcpu: int, memory_gb: float) -> str:
        """
        Suggest an instance type based on vCPU and memory requirements.

        TODO: Replace with actual AWS instance type selection logic.
        """
        # Simple heuristic: use m5 family (general purpose)
        if vcpu <= 1:
            return "m5.large" if memory_gb <= 8 else "m5.xlarge"
        elif vcpu <= 2:
            return "m5.large" if memory_gb <= 8 else "m5.xlarge"
        elif vcpu <= 4:
            return "m5.xlarge" if memory_gb <= 16 else "m5.2xlarge"
        elif vcpu <= 8:
            return "m5.2xlarge" if memory_gb <= 32 else "m5.4xlarge"
        else:
            return "m5.4xlarge"

    def _estimate_instance_cost(self, vcpu: int, memory_gb: float, family: str) -> float:
        """
        Estimate hourly cost for given resources.

        Args:
            vcpu: Number of vCPUs
            memory_gb: Memory in GB
            family: Instance family (e.g., "m5")

        Returns:
            Estimated hourly cost in USD
        """
        # Get family-specific costs or use defaults
        cpu_cost_per_core, mem_cost_per_gb = self.INSTANCE_FAMILY_COSTS.get(
            family,
            (self.CPU_COST_PER_CORE_HOUR, self.MEMORY_COST_PER_GB_HOUR)
        )

        return (vcpu * cpu_cost_per_core) + (memory_gb * mem_cost_per_gb)
