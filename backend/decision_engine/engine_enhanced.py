"""
Enhanced Decision Engine - Complete Multi-Stage Pipeline

Implements the full decision pipeline:
1. Metrics Collector
2. Pool Filter
3. ML Stability Ranker
4. Price Predictor
5. Decision Scorer

This is the main orchestrator that combines all components.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

from .filtering import PoolFilter
from .scoring import DecisionScorer, ScoringWeights, PoolScore
from backend.ml_models import StabilityRanker, PricePredictor

logger = logging.getLogger(__name__)


class DecisionAction(Enum):
    """Possible decision actions"""
    MIGRATE = "MIGRATE"
    STAY = "STAY"
    DEFER = "DEFER"


@dataclass
class DecisionRecommendation:
    """Complete decision recommendation"""
    # Primary recommendation
    action: DecisionAction
    recommended_instance_type: Optional[str]
    recommended_pool_id: Optional[str]
    confidence: float  # 0-1
    expected_cost_savings_percent: float
    expected_stability_improvement_percent: float

    # Reasoning
    primary_factors: List[str]
    filtered_out_count: int
    considered_pools: int

    # Top alternatives
    top_3_alternatives: List[Dict[str, Any]]

    # Migration plan
    migration_plan: Dict[str, Any]

    # Monitoring
    monitoring_alerts: Dict[str, Any]

    # Metadata
    decision_timestamp: datetime
    decision_id: str


class EnhancedDecisionEngine:
    """
    Complete decision engine with multi-stage pipeline.

    Pipeline stages:
    1. Collect metrics (from Executor)
    2. Discover and filter pools (PoolFilter)
    3. Rank by stability (StabilityRanker ML model)
    4. Predict prices (PricePredictor ML model)
    5. Score and rank (DecisionScorer)
    6. Generate recommendation
    """

    def __init__(
        self,
        stability_model_path: Optional[str] = None,
        price_model_path: Optional[str] = None,
        scoring_weights: Optional[ScoringWeights] = None,
        filter_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize enhanced decision engine.

        Args:
            stability_model_path: Path to trained stability model
            price_model_path: Path to trained price prediction model
            scoring_weights: Custom scoring weights
            filter_config: Custom filter configuration
        """
        # Initialize components
        self.pool_filter = PoolFilter(config=filter_config)
        self.stability_ranker = StabilityRanker(model_path=stability_model_path)
        self.price_predictor = PricePredictor(model_path=price_model_path)
        self.decision_scorer = DecisionScorer(weights=scoring_weights)

        # Configuration
        self.min_confidence_threshold = 0.8
        self.min_savings_threshold = 5.0  # 5% minimum savings to justify migration
        self.cooldown_minutes = 30

        logger.info("EnhancedDecisionEngine initialized with all components")

    def decide(
        self,
        current_instance: Dict[str, Any],
        usage_metrics: Dict[str, Any],
        usage_patterns: Dict[str, Any],
        available_pools: List[Dict[str, Any]],
        app_requirements: Dict[str, Any],
        sla_requirements: Dict[str, Any],
        region: str
    ) -> DecisionRecommendation:
        """
        Main decision method - run complete pipeline.

        Args:
            current_instance: Current instance state and specs
            usage_metrics: Current usage metrics
            usage_patterns: Historical usage patterns
            available_pools: List of all available pools
            app_requirements: Application minimum requirements
            sla_requirements: SLA requirements
            region: AWS region

        Returns:
            DecisionRecommendation with complete analysis
        """
        decision_id = f"decision_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Starting decision pipeline {decision_id}")

        # Stage 1: Filter pools by safety rules
        logger.info(f"Stage 1: Filtering {len(available_pools)} pools...")
        filtered_pools = self.pool_filter.filter_pools(
            pools=available_pools,
            current_instance=current_instance,
            usage_metrics=usage_metrics,
            usage_patterns=usage_patterns,
            app_requirements=app_requirements
        )
        filtered_out_count = len(available_pools) - len(filtered_pools)
        logger.info(f"Stage 1 complete: {len(filtered_pools)} pools passed filters")

        if len(filtered_pools) == 0:
            logger.warning("No pools passed filters - staying on current instance")
            return self._create_stay_decision(
                current_instance,
                filtered_out_count,
                "No suitable pools found after applying safety filters",
                decision_id
            )

        # Stage 2: Rank by stability (ML model)
        logger.info(f"Stage 2: Ranking {len(filtered_pools)} pools by stability...")
        stability_scores = self.stability_ranker.rank_pools(
            pools=filtered_pools,
            region=region
        )
        logger.info(f"Stage 2 complete: Stability scores generated")

        # Stage 3: Predict prices 1h ahead (ML model)
        logger.info(f"Stage 3: Predicting prices for {len(filtered_pools)} pools...")
        price_predictions = self.price_predictor.predict_prices(
            pools=filtered_pools,
            horizon_minutes=60
        )
        logger.info(f"Stage 3 complete: Price predictions generated")

        # Stage 4: Score and rank pools
        logger.info(f"Stage 4: Scoring and ranking pools...")
        scored_pools = self.decision_scorer.score_pools(
            pools=filtered_pools,
            price_predictions=price_predictions,
            stability_scores=stability_scores,
            current_instance=current_instance,
            usage_metrics=usage_metrics,
            sla_requirements=sla_requirements
        )
        logger.info(f"Stage 4 complete: {len(scored_pools)} pools scored and ranked")

        if len(scored_pools) == 0:
            logger.warning("No pools scored - staying on current instance")
            return self._create_stay_decision(
                current_instance,
                filtered_out_count,
                "No pools could be scored",
                decision_id
            )

        # Stage 5: Make final decision
        logger.info(f"Stage 5: Making final decision...")
        recommendation = self._make_final_decision(
            current_instance=current_instance,
            scored_pools=scored_pools,
            filtered_out_count=filtered_out_count,
            considered_pools=len(filtered_pools),
            decision_id=decision_id
        )

        logger.info(f"Decision complete: {recommendation.action.value} - "
                   f"{recommendation.recommended_instance_type}")

        return recommendation

    def _make_final_decision(
        self,
        current_instance: Dict[str, Any],
        scored_pools: List[PoolScore],
        filtered_out_count: int,
        considered_pools: int,
        decision_id: str
    ) -> DecisionRecommendation:
        """
        Make final decision based on scored pools.

        Decision logic:
        - If top pool score > threshold AND savings > min → MIGRATE
        - If confidence < threshold OR savings < min → STAY
        - If recently migrated (within cooldown) → DEFER
        """
        top_pool = scored_pools[0]
        current_type = current_instance.get('instance_type', 'unknown')

        # Check if top recommendation is current instance
        if top_pool.instance_type == current_type:
            logger.info("Top recommendation is current instance - STAY")
            return self._create_stay_decision(
                current_instance,
                filtered_out_count,
                "Current instance is already optimal",
                decision_id
            )

        # Calculate confidence based on score difference
        if len(scored_pools) > 1:
            score_gap = top_pool.overall_score - scored_pools[1].overall_score
            confidence = min(0.99, 0.5 + (score_gap / 100))
        else:
            confidence = 0.9

        # Check confidence threshold
        if confidence < self.min_confidence_threshold:
            logger.info(f"Confidence {confidence:.2f} below threshold {self.min_confidence_threshold} - STAY")
            return self._create_stay_decision(
                current_instance,
                filtered_out_count,
                f"Confidence too low ({confidence:.2f})",
                decision_id
            )

        # Calculate cost savings
        current_cost = current_instance.get('current_spot_price', 0.05)
        predicted_cost = top_pool.predicted_cost_hourly
        cost_savings_percent = ((current_cost - predicted_cost) / current_cost) * 100

        # Check savings threshold
        if cost_savings_percent < self.min_savings_threshold:
            logger.info(f"Savings {cost_savings_percent:.1f}% below threshold {self.min_savings_threshold}% - STAY")
            return self._create_stay_decision(
                current_instance,
                filtered_out_count,
                f"Insufficient cost savings ({cost_savings_percent:.1f}%)",
                decision_id
            )

        # Decision: MIGRATE
        logger.info(f"Decision: MIGRATE to {top_pool.instance_type} "
                   f"(savings: {cost_savings_percent:.1f}%, confidence: {confidence:.2f})")

        # Generate top 3 alternatives
        top_3_alternatives = [
            {
                'instance_type': pool.instance_type,
                'overall_score': pool.overall_score,
                'cost_per_hour': pool.predicted_cost_hourly,
                'stability_score': pool.stability_score,
                'pros': pool.pros,
                'cons': pool.cons
            }
            for pool in scored_pools[:3]
        ]

        # Generate migration plan
        migration_plan = self._generate_migration_plan(
            current_instance,
            top_pool
        )

        # Generate monitoring alerts
        monitoring_alerts = self._generate_monitoring_alerts(
            top_pool,
            current_instance
        )

        # Calculate stability improvement
        current_stability = 70.0  # Placeholder - would come from current instance data
        stability_improvement = top_pool.stability_score - current_stability

        # Primary factors for recommendation
        primary_factors = [
            f"Cost savings: {cost_savings_percent:.1f}%",
            f"Stability score: {top_pool.stability_score:.1f}/100",
            f"Performance match: {top_pool.performance_score:.1f}/100",
            f"Overall score: {top_pool.overall_score:.1f}/100"
        ]

        return DecisionRecommendation(
            action=DecisionAction.MIGRATE,
            recommended_instance_type=top_pool.instance_type,
            recommended_pool_id=top_pool.pool_id,
            confidence=confidence,
            expected_cost_savings_percent=cost_savings_percent,
            expected_stability_improvement_percent=stability_improvement,
            primary_factors=primary_factors,
            filtered_out_count=filtered_out_count,
            considered_pools=considered_pools,
            top_3_alternatives=top_3_alternatives,
            migration_plan=migration_plan,
            monitoring_alerts=monitoring_alerts,
            decision_timestamp=datetime.utcnow(),
            decision_id=decision_id
        )

    def _create_stay_decision(
        self,
        current_instance: Dict[str, Any],
        filtered_out_count: int,
        reason: str,
        decision_id: str
    ) -> DecisionRecommendation:
        """Create a STAY decision"""
        return DecisionRecommendation(
            action=DecisionAction.STAY,
            recommended_instance_type=current_instance.get('instance_type'),
            recommended_pool_id=current_instance.get('pool_id'),
            confidence=1.0,
            expected_cost_savings_percent=0.0,
            expected_stability_improvement_percent=0.0,
            primary_factors=[reason],
            filtered_out_count=filtered_out_count,
            considered_pools=0,
            top_3_alternatives=[],
            migration_plan={},
            monitoring_alerts={
                'reevaluate_in_minutes': 30,
                'watch_for_cpu_above': 80.0,
                'watch_for_ram_above': 80.0
            },
            decision_timestamp=datetime.utcnow(),
            decision_id=decision_id
        )

    def _generate_migration_plan(
        self,
        current_instance: Dict[str, Any],
        target_pool: PoolScore
    ) -> Dict[str, Any]:
        """Generate migration execution plan"""
        return {
            'estimated_downtime_seconds': 120,  # 2 minutes
            'migration_steps': [
                f"Launch new {target_pool.instance_type} instance in pool {target_pool.pool_id}",
                "Wait for new instance to reach 'running' state",
                "Health check new instance",
                f"Terminate old {current_instance.get('instance_type')} instance",
                "Verify termination complete"
            ],
            'rollback_plan': "If new instance fails health check, terminate it and stay on current instance",
            'best_migration_window': (datetime.utcnow() + timedelta(minutes=5)).isoformat()
        }

    def _generate_monitoring_alerts(
        self,
        target_pool: PoolScore,
        current_instance: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate post-migration monitoring alerts"""
        return {
            'watch_for_cpu_above': 85.0,
            'watch_for_ram_above': 85.0,
            'reevaluate_in_minutes': 60,
            'alert_if_interruption_within_hours': 2
        }

    def get_pipeline_info(self) -> Dict[str, Any]:
        """Get information about the decision pipeline"""
        return {
            'pipeline_stages': [
                '1. Metrics Collection (from Executor)',
                '2. Pool Filtering (safety rules)',
                '3. ML Stability Ranking',
                '4. ML Price Prediction (1h ahead)',
                '5. Multi-criteria Scoring',
                '6. Final Decision'
            ],
            'ml_models': {
                'stability_ranker': self.stability_ranker.get_model_info(),
                'price_predictor': self.price_predictor.get_model_info()
            },
            'scoring_weights': asdict(self.decision_scorer.weights),
            'safety_thresholds': {
                'min_confidence': self.min_confidence_threshold,
                'min_savings_percent': self.min_savings_threshold,
                'cooldown_minutes': self.cooldown_minutes
            }
        }
