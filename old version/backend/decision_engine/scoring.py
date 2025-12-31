"""
Multi-Criteria Decision Scoring

Combines all factors (cost, stability, performance, migration risk, SLA)
into a single composite score for ranking pools.

Scoring Algorithm: Weighted sum with normalization
"""

import logging
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
import math

logger = logging.getLogger(__name__)


@dataclass
class ScoringWeights:
    """Configurable weights for scoring factors"""
    predicted_cost: float = 0.30
    stability_score: float = 0.35
    performance_match: float = 0.20
    migration_risk: float = 0.10
    sla_compliance: float = 0.05

    def validate(self):
        """Ensure weights sum to 1.0"""
        total = (self.predicted_cost + self.stability_score +
                self.performance_match + self.migration_risk +
                self.sla_compliance)
        if not math.isclose(total, 1.0, rel_tol=1e-5):
            raise ValueError(f"Scoring weights must sum to 1.0, got {total}")


@dataclass
class PoolScore:
    """Complete scoring breakdown for a pool"""
    pool_id: str
    instance_type: str
    overall_score: float  # 0-100
    rank: int

    # Individual factor scores (0-100)
    cost_score: float
    stability_score: float
    performance_score: float
    migration_score: float
    sla_score: float

    # Raw values
    predicted_cost_hourly: float
    predicted_interruption_prob: float
    performance_match_ratio: float

    # Recommendation
    pros: List[str]
    cons: List[str]


class DecisionScorer:
    """
    Multi-criteria decision scorer.

    Combines cost, stability, performance, migration risk, and SLA compliance
    into a single score for each pool.
    """

    def __init__(self, weights: ScoringWeights = None):
        """
        Initialize scorer with weights.

        Args:
            weights: ScoringWeights object (uses defaults if not provided)
        """
        self.weights = weights or ScoringWeights()
        self.weights.validate()

        logger.info(f"DecisionScorer initialized with weights: {self.weights}")

    def score_pools(
        self,
        pools: List[Dict[str, Any]],
        price_predictions: List[Any],
        stability_scores: List[Any],
        current_instance: Dict[str, Any],
        usage_metrics: Dict[str, Any],
        sla_requirements: Dict[str, Any]
    ) -> List[PoolScore]:
        """
        Score all pools and return ranked list.

        Args:
            pools: List of candidate pools
            price_predictions: List of PricePrediction objects
            stability_scores: List of StabilityScore objects
            current_instance: Current instance specs
            usage_metrics: Current usage metrics
            sla_requirements: SLA requirements

        Returns:
            List of PoolScore objects sorted by overall_score descending
        """
        scored_pools = []

        # Create lookup dicts for predictions and stability
        price_dict = {p.pool_id: p for p in price_predictions}
        stability_dict = {s.pool_id: s for s in stability_scores}

        for pool in pools:
            pool_id = pool.get('pool_id', 'unknown')

            # Get predictions for this pool
            price_pred = price_dict.get(pool_id)
            stability = stability_dict.get(pool_id)

            if not price_pred or not stability:
                logger.warning(f"Missing predictions for pool {pool_id}, skipping")
                continue

            score = self._score_single_pool(
                pool,
                price_pred,
                stability,
                current_instance,
                usage_metrics,
                sla_requirements
            )

            scored_pools.append(score)

        # Sort by overall score descending
        scored_pools.sort(key=lambda x: x.overall_score, reverse=True)

        # Assign ranks
        for rank, score in enumerate(scored_pools, 1):
            score.rank = rank

        logger.info(f"Scored and ranked {len(scored_pools)} pools")
        return scored_pools

    def _score_single_pool(
        self,
        pool: Dict[str, Any],
        price_pred: Any,
        stability: Any,
        current_instance: Dict[str, Any],
        usage_metrics: Dict[str, Any],
        sla_requirements: Dict[str, Any]
    ) -> PoolScore:
        """Score a single pool across all factors"""

        # Factor 1: Predicted Cost
        cost_score = self._score_cost(price_pred, stability)

        # Factor 2: Stability
        stability_score = stability.stability_score  # Already 0-100

        # Factor 3: Performance Match
        performance_score, perf_ratio = self._score_performance(
            pool,
            current_instance,
            usage_metrics
        )

        # Factor 4: Migration Risk
        migration_score = self._score_migration_risk(pool, current_instance)

        # Factor 5: SLA Compliance
        sla_score = self._score_sla_compliance(stability, sla_requirements)

        # Calculate overall score (weighted sum)
        overall_score = (
            cost_score * self.weights.predicted_cost +
            stability_score * self.weights.stability_score +
            performance_score * self.weights.performance_match +
            migration_score * self.weights.migration_risk +
            sla_score * self.weights.sla_compliance
        )

        # Generate pros/cons
        pros, cons = self._generate_pros_cons(
            pool,
            cost_score,
            stability_score,
            performance_score,
            migration_score,
            sla_score
        )

        return PoolScore(
            pool_id=pool.get('pool_id', 'unknown'),
            instance_type=pool.get('instance_type', 'unknown'),
            overall_score=overall_score,
            rank=0,  # Will be set later
            cost_score=cost_score,
            stability_score=stability_score,
            performance_score=performance_score,
            migration_score=migration_score,
            sla_score=sla_score,
            predicted_cost_hourly=price_pred.predicted_price_1h,
            predicted_interruption_prob=stability.predicted_interruption_probability_24h,
            performance_match_ratio=perf_ratio,
            pros=pros,
            cons=cons
        )

    def _score_cost(self, price_pred: Any, stability: Any) -> float:
        """
        Score based on predicted cost including interruption risk.

        Formula: predicted_price * (1 + predicted_interruption_probability * migration_cost_multiplier)
        Lower total cost = higher score

        Normalized to 0-100 scale
        """
        # Migration cost multiplier (cost of handling interruption)
        migration_cost_multiplier = 2.0  # Assume migration costs 2x hourly rate

        # Effective cost including interruption risk
        effective_cost = price_pred.predicted_price_1h * (
            1 + stability.predicted_interruption_probability_24h * migration_cost_multiplier
        )

        # Normalize to 0-100 (inverse - lower cost = higher score)
        # Assume max reasonable cost is 2x predicted price
        max_cost = price_pred.predicted_price_1h * 2
        cost_score = (1 - (effective_cost / max_cost)) * 100

        # Clamp to 0-100
        return max(0, min(100, cost_score))

    def _score_performance(
        self,
        pool: Dict[str, Any],
        current_instance: Dict[str, Any],
        usage_metrics: Dict[str, Any]
    ) -> Tuple[float, float]:
        """
        Score based on performance match.

        Optimal is 1.2-1.5x current usage (slight overprovisioning for safety)

        Returns: (score, match_ratio)
        """
        # Get specs
        pool_cpu = pool.get('specifications', {}).get('cpu_cores', 1)
        pool_ram = pool.get('specifications', {}).get('ram_gb', 1)

        current_cpu = current_instance.get('specifications', {}).get('cpu_cores', 1)
        current_ram = current_instance.get('specifications', {}).get('ram_gb', 1)

        # Get actual usage
        cpu_usage_pct = usage_metrics.get('cpu_usage_percent', 50) / 100
        ram_usage_pct = usage_metrics.get('ram_usage_percent', 50) / 100

        # Calculate actual usage in absolute terms
        actual_cpu_used = current_cpu * cpu_usage_pct
        actual_ram_used = current_ram * ram_usage_pct

        # Calculate match ratios (pool capacity / actual usage)
        cpu_ratio = pool_cpu / actual_cpu_used if actual_cpu_used > 0 else 1.5
        ram_ratio = pool_ram / actual_ram_used if actual_ram_used > 0 else 1.5

        # Average ratio
        avg_ratio = (cpu_ratio + ram_ratio) / 2

        # Optimal range: 1.2 - 1.5
        # Score peaks at 1.35
        optimal_ratio = 1.35
        optimal_range = 0.15

        # Calculate score based on distance from optimal
        distance = abs(avg_ratio - optimal_ratio)
        performance_score = max(0, 100 - (distance / optimal_range) * 100)

        return performance_score, avg_ratio

    def _score_migration_risk(
        self,
        pool: Dict[str, Any],
        current_instance: Dict[str, Any]
    ) -> float:
        """
        Score based on migration risk.

        Lower risk for:
        - Same instance family (e.g., m5.large → m5.xlarge)
        - Similar specs
        - Same generation

        Higher risk for:
        - Cross-family (e.g., t3 → c5)
        - Different generation
        - Major spec differences
        """
        current_type = current_instance.get('instance_type', '')
        pool_type = pool.get('instance_type', '')

        # Parse instance types
        current_family = current_type.split('.')[0] if '.' in current_type else current_type
        pool_family = pool_type.split('.')[0] if '.' in pool_type else pool_type

        # Base score
        score = 70.0

        # Same family bonus
        if current_family == pool_family:
            score += 20.0
        else:
            # Cross-family penalty
            score -= 15.0

        # Same size bonus
        current_size = current_type.split('.')[1] if '.' in current_type else 'medium'
        pool_size = pool_type.split('.')[1] if '.' in pool_type else 'medium'

        if current_size == pool_size:
            score += 10.0

        # Clamp to 0-100
        return max(0, min(100, score))

    def _score_sla_compliance(
        self,
        stability: Any,
        sla_requirements: Dict[str, Any]
    ) -> float:
        """
        Binary gate: 100 if meets SLA, 0 if not.
        """
        max_interruption_rate = sla_requirements.get('max_interruption_rate_percent', 5.0) / 100
        required_uptime = sla_requirements.get('required_uptime_percent', 99.0) / 100

        # Check if predicted interruption rate is within SLA
        predicted_interruption = stability.predicted_interruption_probability_24h

        if predicted_interruption <= max_interruption_rate:
            return 100.0
        else:
            return 0.0

    def _generate_pros_cons(
        self,
        pool: Dict[str, Any],
        cost_score: float,
        stability_score: float,
        performance_score: float,
        migration_score: float,
        sla_score: float
    ) -> Tuple[List[str], List[str]]:
        """Generate human-readable pros and cons"""
        pros = []
        cons = []

        # Cost
        if cost_score > 80:
            pros.append(f"Excellent cost efficiency ({cost_score:.0f}/100)")
        elif cost_score < 50:
            cons.append(f"Higher cost ({cost_score:.0f}/100)")

        # Stability
        if stability_score > 85:
            pros.append(f"Very stable pool ({stability_score:.0f}/100)")
        elif stability_score < 60:
            cons.append(f"Lower stability ({stability_score:.0f}/100)")

        # Performance
        if performance_score > 80:
            pros.append(f"Optimal resource match ({performance_score:.0f}/100)")
        elif performance_score < 60:
            cons.append(f"Resource mismatch ({performance_score:.0f}/100)")

        # Migration
        if migration_score > 80:
            pros.append("Low migration risk (same family)")
        elif migration_score < 60:
            cons.append("Higher migration risk (cross-family)")

        # SLA
        if sla_score == 100:
            pros.append("Meets all SLA requirements")
        else:
            cons.append("Does not meet SLA requirements")

        # Default messages
        if not pros:
            pros.append("Acceptable option")
        if not cons:
            cons.append("No major concerns")

        return pros, cons
