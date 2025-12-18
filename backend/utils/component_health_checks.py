"""
Component-Specific Health Check Logic

Each component has customized criteria for determining health status.
"""

from datetime import datetime, timedelta
from database.system_logs import ComponentStatus


class ComponentHealthEvaluator:
    """Evaluates component health based on component-specific criteria"""

    @staticmethod
    def evaluate_health(component: str, health_record) -> str:
        """
        Determine component health status based on component-specific logic

        Args:
            component: Component name
            health_record: ComponentHealth database record

        Returns:
            Status string: 'healthy', 'degraded', or 'down'
        """
        now = datetime.utcnow()
        total = health_record.success_count_24h + health_record.failure_count_24h
        failure_rate = health_record.failure_count_24h / total if total > 0 else 0

        last_activity = health_record.last_success or health_record.last_failure
        is_recently_active = last_activity and (now - last_activity) < timedelta(hours=1)

        # Component-specific evaluation
        if component == 'web_scraper':
            return ComponentHealthEvaluator._evaluate_web_scraper(
                health_record, failure_rate, is_recently_active
            )
        elif component == 'price_scraper':
            return ComponentHealthEvaluator._evaluate_price_scraper(
                health_record, failure_rate, is_recently_active
            )
        elif component == 'redis_cache':
            return ComponentHealthEvaluator._evaluate_redis(
                health_record, failure_rate, is_recently_active
            )
        elif component == 'database':
            return ComponentHealthEvaluator._evaluate_database(
                health_record, failure_rate, is_recently_active
            )
        elif component == 'ml_inference':
            return ComponentHealthEvaluator._evaluate_ml_inference(
                health_record, failure_rate, is_recently_active
            )
        elif component == 'linear_optimizer':
            return ComponentHealthEvaluator._evaluate_linear_optimizer(
                health_record, failure_rate, is_recently_active
            )
        elif component == 'instance_manager':
            return ComponentHealthEvaluator._evaluate_instance_manager(
                health_record, failure_rate, is_recently_active
            )
        elif component == 'api_server':
            return ComponentHealthEvaluator._evaluate_api_server(
                health_record, failure_rate, is_recently_active
            )
        elif component == 'waste_scanner':
            return ComponentHealthEvaluator._evaluate_waste_scanner(
                health_record, failure_rate, is_recently_active
            )
        elif component == 'security_enforcer':
            return ComponentHealthEvaluator._evaluate_security_enforcer(
                health_record, failure_rate, is_recently_active
            )
        else:
            # Default generic evaluation
            return ComponentHealthEvaluator._evaluate_generic(
                health_record, failure_rate, is_recently_active
            )

    @staticmethod
    def _evaluate_web_scraper(health_record, failure_rate, is_recently_active):
        """
        Web Scraper: Fetches AWS Spot Advisor data
        - Should run at least once per hour
        - Critical if not running (spot advisor data becomes stale)
        """
        if not is_recently_active:
            return ComponentStatus.DOWN.value
        if health_record.success_count_24h < 10:  # Should run ~24 times/day
            return ComponentStatus.DEGRADED.value
        if failure_rate > 0.3:
            return ComponentStatus.DEGRADED.value
        return ComponentStatus.HEALTHY.value

    @staticmethod
    def _evaluate_price_scraper(health_record, failure_rate, is_recently_active):
        """
        Price Scraper: Fetches AWS pricing data
        - Should fetch pricing regularly
        - Critical for cost calculations
        """
        if not is_recently_active:
            return ComponentStatus.DOWN.value
        if health_record.success_count_24h < 5:  # Should run several times/day
            return ComponentStatus.DEGRADED.value
        if failure_rate > 0.4:
            return ComponentStatus.DEGRADED.value
        return ComponentStatus.HEALTHY.value

    @staticmethod
    def _evaluate_redis(health_record, failure_rate, is_recently_active):
        """
        Redis Cache: Caching layer
        - Should always be responsive
        - High failure rate = connectivity issues
        - Down if not responsive
        """
        if not is_recently_active:
            return ComponentStatus.DOWN.value
        if health_record.success_count_24h < 20:  # Should have frequent cache ops
            return ComponentStatus.DEGRADED.value
        if failure_rate > 0.1:  # Cache should be very reliable
            return ComponentStatus.DEGRADED.value
        return ComponentStatus.HEALTHY.value

    @staticmethod
    def _evaluate_database(health_record, failure_rate, is_recently_active):
        """
        Database: PostgreSQL operations
        - Critical component - must be responsive
        - Any significant failure rate is concerning
        """
        if not is_recently_active:
            return ComponentStatus.DOWN.value
        if failure_rate > 0.05:  # DB should be very reliable
            return ComponentStatus.DEGRADED.value
        if health_record.success_count_24h < 50:  # Should have many DB ops
            return ComponentStatus.DEGRADED.value
        return ComponentStatus.HEALTHY.value

    @staticmethod
    def _evaluate_ml_inference(health_record, failure_rate, is_recently_active):
        """
        ML Inference: Model predictions for risk scoring
        - Should be making predictions when instances are being evaluated
        - Degraded if not actively used or high failure rate
        """
        if not is_recently_active:
            return ComponentStatus.DOWN.value
        if health_record.success_count_24h < 10:  # Should make predictions regularly
            return ComponentStatus.DEGRADED.value
        if failure_rate > 0.2:
            return ComponentStatus.DEGRADED.value
        return ComponentStatus.HEALTHY.value

    @staticmethod
    def _evaluate_linear_optimizer(health_record, failure_rate, is_recently_active):
        """
        Linear Optimizer: Makes switching decisions
        - Core decision-making component
        - Should be evaluating options regularly
        """
        if not is_recently_active:
            return ComponentStatus.DOWN.value
        if health_record.success_count_24h < 10:
            return ComponentStatus.DEGRADED.value
        if failure_rate > 0.25:
            return ComponentStatus.DEGRADED.value
        return ComponentStatus.HEALTHY.value

    @staticmethod
    def _evaluate_instance_manager(health_record, failure_rate, is_recently_active):
        """
        Instance Manager: Manages instance lifecycle
        - Should be monitoring instances constantly
        - High activity expected
        """
        if not is_recently_active:
            return ComponentStatus.DOWN.value
        if health_record.success_count_24h < 20:
            return ComponentStatus.DEGRADED.value
        if failure_rate > 0.15:
            return ComponentStatus.DEGRADED.value
        return ComponentStatus.HEALTHY.value

    @staticmethod
    def _evaluate_api_server(health_record, failure_rate, is_recently_active):
        """
        API Server: HTTP API health
        - Should always be responsive
        - High availability required
        """
        if not is_recently_active:
            return ComponentStatus.DOWN.value
        if failure_rate > 0.1:
            return ComponentStatus.DEGRADED.value
        if health_record.success_count_24h < 100:  # Should handle many requests
            return ComponentStatus.DEGRADED.value
        return ComponentStatus.HEALTHY.value

    @staticmethod
    def _evaluate_waste_scanner(health_record, failure_rate, is_recently_active):
        """
        Waste Scanner: Scans for unused resources
        - Periodic job, doesn't need to run constantly
        - Degraded if not running at least daily
        """
        now = datetime.utcnow()
        last_activity = health_record.last_success or health_record.last_failure
        hours_since_activity = (now - last_activity).total_seconds() / 3600 if last_activity else 999

        if hours_since_activity > 48:  # Not run in 2 days
            return ComponentStatus.DOWN.value
        if health_record.success_count_24h < 1:  # Should run at least once/day
            return ComponentStatus.DEGRADED.value
        if failure_rate > 0.5:
            return ComponentStatus.DEGRADED.value
        return ComponentStatus.HEALTHY.value

    @staticmethod
    def _evaluate_security_enforcer(health_record, failure_rate, is_recently_active):
        """
        Security Enforcer: Enforces security policies
        - Critical security component
        - Should be checking continuously
        """
        if not is_recently_active:
            return ComponentStatus.DOWN.value
        if health_record.success_count_24h < 10:
            return ComponentStatus.DEGRADED.value
        if failure_rate > 0.1:  # Security checks should be reliable
            return ComponentStatus.DEGRADED.value
        return ComponentStatus.HEALTHY.value

    @staticmethod
    def _evaluate_generic(health_record, failure_rate, is_recently_active):
        """
        Generic fallback evaluation for unknown components
        """
        if failure_rate > 0.5 or not is_recently_active:
            return ComponentStatus.DOWN.value
        elif failure_rate > 0.2 or health_record.success_count_24h < 5:
            return ComponentStatus.DEGRADED.value
        else:
            return ComponentStatus.HEALTHY.value
