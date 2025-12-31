"""
Pool Filtering Rules

Implements safety rules to filter out unsuitable instance pools based on
current usage patterns. Prevents CPU bottlenecks, OOM crashes, and performance
degradation during migrations.
"""

import logging
from typing import Dict, List, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Result of filtering operation"""
    passed: bool
    reason: str
    rule_name: str


class PoolFilter:
    """
    Filters instance pools based on current usage and safety rules.

    Implements 6 core filtering rules:
    1. CPU Safety - Prevent CPU bottleneck crashes
    2. RAM Safety - Prevent out-of-memory crashes
    3. Moderate Usage Protection - Conservative downsizing
    4. Peak Consideration - Handle historical peaks
    5. Burstable Credits - Check CPU credit balance
    6. Application Minimums - Respect app requirements
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize filter with configuration"""
        self.config = config or {}

        # Thresholds
        self.high_cpu_threshold = self.config.get('high_cpu_threshold', 80.0)
        self.high_ram_threshold = self.config.get('high_ram_threshold', 80.0)
        self.moderate_cpu_threshold = self.config.get('moderate_cpu_threshold', 50.0)
        self.peak_cpu_threshold = self.config.get('peak_cpu_threshold', 70.0)
        self.min_cpu_credits = self.config.get('min_cpu_credits', 100)

        logger.info(f"PoolFilter initialized with thresholds: "
                   f"high_cpu={self.high_cpu_threshold}, "
                   f"high_ram={self.high_ram_threshold}")

    def filter_pools(
        self,
        pools: List[Dict[str, Any]],
        current_instance: Dict[str, Any],
        usage_metrics: Dict[str, Any],
        usage_patterns: Dict[str, Any],
        app_requirements: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Filter pools based on all safety rules.

        Args:
            pools: List of candidate pools
            current_instance: Current instance specs
            usage_metrics: Current usage metrics
            usage_patterns: Historical usage patterns
            app_requirements: Application minimum requirements

        Returns:
            List of pools that passed all filters
        """
        passed_pools = []
        filtered_out = {}

        for pool in pools:
            results = self._apply_all_rules(
                pool,
                current_instance,
                usage_metrics,
                usage_patterns,
                app_requirements
            )

            # Check if all rules passed
            failed_rules = [r for r in results if not r.passed]

            if not failed_rules:
                passed_pools.append(pool)
                logger.debug(f"Pool {pool['instance_type']} passed all filters")
            else:
                # Log why it was filtered out
                reasons = [f"{r.rule_name}: {r.reason}" for r in failed_rules]
                filtered_out[pool['instance_type']] = reasons
                logger.debug(f"Pool {pool['instance_type']} filtered out: {reasons}")

        logger.info(f"Filtered {len(pools)} pools → {len(passed_pools)} passed, "
                   f"{len(filtered_out)} filtered out")

        return passed_pools

    def _apply_all_rules(
        self,
        pool: Dict[str, Any],
        current_instance: Dict[str, Any],
        usage_metrics: Dict[str, Any],
        usage_patterns: Dict[str, Any],
        app_requirements: Dict[str, Any]
    ) -> List[FilterResult]:
        """Apply all filtering rules to a single pool"""
        results = []

        # Rule 1: CPU Safety
        results.append(self._rule_cpu_safety(pool, current_instance, usage_metrics))

        # Rule 2: RAM Safety
        results.append(self._rule_ram_safety(pool, current_instance, usage_metrics))

        # Rule 3: Moderate Usage Protection
        results.append(self._rule_moderate_usage(pool, current_instance, usage_metrics))

        # Rule 4: Peak Consideration
        results.append(self._rule_peak_consideration(pool, current_instance, usage_patterns))

        # Rule 5: Burstable Credits
        results.append(self._rule_burstable_credits(pool, current_instance, usage_metrics))

        # Rule 6: Application Minimums
        results.append(self._rule_application_minimums(pool, app_requirements))

        return results

    def _rule_cpu_safety(
        self,
        pool: Dict[str, Any],
        current_instance: Dict[str, Any],
        usage_metrics: Dict[str, Any]
    ) -> FilterResult:
        """
        Rule 1: CPU Safety - Prevent CPU bottleneck crashes

        Logic: IF current_cpu_usage > 80% THEN pool.cpu_cores >= current_instance.cpu_cores
        """
        current_cpu = usage_metrics.get('cpu_usage_percent', 0)

        if current_cpu > self.high_cpu_threshold:
            current_cores = current_instance.get('specifications', {}).get('cpu_cores', 0)
            pool_cores = pool.get('specifications', {}).get('cpu_cores', 0)

            if pool_cores < current_cores:
                return FilterResult(
                    passed=False,
                    reason=f"High CPU usage ({current_cpu:.1f}%) requires >= {current_cores} cores, pool has {pool_cores}",
                    rule_name="CPU_SAFETY"
                )

        return FilterResult(passed=True, reason="CPU safety check passed", rule_name="CPU_SAFETY")

    def _rule_ram_safety(
        self,
        pool: Dict[str, Any],
        current_instance: Dict[str, Any],
        usage_metrics: Dict[str, Any]
    ) -> FilterResult:
        """
        Rule 2: RAM Safety - Prevent out-of-memory crashes

        Logic: IF current_ram_usage > 80% THEN pool.ram_gb >= current_instance.ram_gb
        """
        current_ram = usage_metrics.get('ram_usage_percent', 0)

        if current_ram > self.high_ram_threshold:
            current_ram_gb = current_instance.get('specifications', {}).get('ram_gb', 0)
            pool_ram_gb = pool.get('specifications', {}).get('ram_gb', 0)

            if pool_ram_gb < current_ram_gb:
                return FilterResult(
                    passed=False,
                    reason=f"High RAM usage ({current_ram:.1f}%) requires >= {current_ram_gb}GB, pool has {pool_ram_gb}GB",
                    rule_name="RAM_SAFETY"
                )

        return FilterResult(passed=True, reason="RAM safety check passed", rule_name="RAM_SAFETY")

    def _rule_moderate_usage(
        self,
        pool: Dict[str, Any],
        current_instance: Dict[str, Any],
        usage_metrics: Dict[str, Any]
    ) -> FilterResult:
        """
        Rule 3: Moderate Usage Protection - Conservative downsizing

        Logic: IF current_cpu_usage > 50% THEN pool.cpu_cores >= current_instance.cpu_cores
        """
        current_cpu = usage_metrics.get('cpu_usage_percent', 0)

        if current_cpu > self.moderate_cpu_threshold:
            current_cores = current_instance.get('specifications', {}).get('cpu_cores', 0)
            pool_cores = pool.get('specifications', {}).get('cpu_cores', 0)

            if pool_cores < current_cores:
                return FilterResult(
                    passed=False,
                    reason=f"Moderate CPU usage ({current_cpu:.1f}%) prevents downsizing below {current_cores} cores",
                    rule_name="MODERATE_USAGE_PROTECTION"
                )

        return FilterResult(passed=True, reason="Moderate usage check passed", rule_name="MODERATE_USAGE_PROTECTION")

    def _rule_peak_consideration(
        self,
        pool: Dict[str, Any],
        current_instance: Dict[str, Any],
        usage_patterns: Dict[str, Any]
    ) -> FilterResult:
        """
        Rule 4: Peak Consideration - Handle historical peaks

        Logic: IF peak_cpu_last_24h > 70% THEN pool.cpu_cores >= current_instance.cpu_cores
        """
        peak_cpu = usage_patterns.get('peak_cpu_last_24h', 0)

        if peak_cpu > self.peak_cpu_threshold:
            current_cores = current_instance.get('specifications', {}).get('cpu_cores', 0)
            pool_cores = pool.get('specifications', {}).get('cpu_cores', 0)

            if pool_cores < current_cores:
                return FilterResult(
                    passed=False,
                    reason=f"Peak CPU ({peak_cpu:.1f}%) requires >= {current_cores} cores for recurring loads",
                    rule_name="PEAK_CONSIDERATION"
                )

        return FilterResult(passed=True, reason="Peak consideration check passed", rule_name="PEAK_CONSIDERATION")

    def _rule_burstable_credits(
        self,
        pool: Dict[str, Any],
        current_instance: Dict[str, Any],
        usage_metrics: Dict[str, Any]
    ) -> FilterResult:
        """
        Rule 5: Burstable Credits - Check CPU credit balance

        Logic: IF instance_family == 't*' AND cpu_credits < threshold
               THEN consider non-burstable OR larger burstable
        """
        current_type = current_instance.get('instance_type', '')

        # Check if current is burstable (t-series)
        if current_type.startswith('t'):
            cpu_credits = usage_metrics.get('cpu_credits_remaining', float('inf'))

            if cpu_credits < self.min_cpu_credits:
                pool_type = pool.get('instance_type', '')
                pool_cores = pool.get('specifications', {}).get('cpu_cores', 0)
                current_cores = current_instance.get('specifications', {}).get('cpu_cores', 0)

                # Allow if:
                # 1. Non-burstable instance, OR
                # 2. Larger burstable instance
                is_non_burstable = not pool_type.startswith('t')
                is_larger_burstable = pool_type.startswith('t') and pool_cores > current_cores

                if not (is_non_burstable or is_larger_burstable):
                    return FilterResult(
                        passed=False,
                        reason=f"Low CPU credits ({cpu_credits:.0f}) requires non-burstable or larger burstable instance",
                        rule_name="BURSTABLE_CREDITS"
                    )

        return FilterResult(passed=True, reason="Burstable credits check passed", rule_name="BURSTABLE_CREDITS")

    def _rule_application_minimums(
        self,
        pool: Dict[str, Any],
        app_requirements: Dict[str, Any]
    ) -> FilterResult:
        """
        Rule 6: Application Minimums - Respect app requirements

        Logic: pool.cpu_cores >= app.min_cpu AND pool.ram_gb >= app.min_ram
        """
        min_cpu = app_requirements.get('min_cpu_cores', 0)
        min_ram = app_requirements.get('min_ram_gb', 0)

        pool_cpu = pool.get('specifications', {}).get('cpu_cores', 0)
        pool_ram = pool.get('specifications', {}).get('ram_gb', 0)

        if pool_cpu < min_cpu:
            return FilterResult(
                passed=False,
                reason=f"Pool has {pool_cpu} cores but app requires minimum {min_cpu} cores",
                rule_name="APPLICATION_MINIMUMS"
            )

        if pool_ram < min_ram:
            return FilterResult(
                passed=False,
                reason=f"Pool has {pool_ram}GB RAM but app requires minimum {min_ram}GB",
                rule_name="APPLICATION_MINIMUMS"
            )

        return FilterResult(passed=True, reason="Application minimums check passed", rule_name="APPLICATION_MINIMUMS")
