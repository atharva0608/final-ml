"""
Decision Engine - Main decision logic

This module contains the unified Decision Engine that processes all inputs
and makes decisions about whether to stay, switch, or fallback.

See docs/master-session-memory.md for complete design documentation.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Possible actions the decision engine can recommend"""
    STAY = "STAY"
    SWITCH_TO_SPOT = "SWITCH_TO_SPOT"
    FALLBACK_ONDEMAND = "FALLBACK_ONDEMAND"


class UsageClassification(Enum):
    """Instance resource utilization classification"""
    OVER_PROVISIONED = "OVER_PROVISIONED"
    RIGHT_SIZED = "RIGHT_SIZED"
    UNDER_PROVISIONED = "UNDER_PROVISIONED"


@dataclass
class DecisionConfig:
    """Configuration parameters for decision engine"""
    # Baseline thresholds
    baseline_discount: float = 60.0
    baseline_volatility: float = 0.10
    discount_margin: float = 5.0
    volatility_factor_max: float = 1.5

    # Decision thresholds
    min_future_discount_gain: float = 3.0
    min_future_risk_improvement: float = 0.05
    cooldown_minutes: int = 10

    # Usage classification thresholds
    over_provisioned_cpu_max: float = 30.0
    over_provisioned_mem_max: float = 40.0
    under_provisioned_cpu_min: float = 80.0
    under_provisioned_mem_min: float = 80.0

    # Feature flags
    fallback_to_ondemand_enabled: bool = True
    allow_rightsize_down: bool = True
    allow_rightsize_up: bool = True
    dry_run_mode: bool = False


@dataclass
class Decision:
    """Output of decision engine"""
    action_type: ActionType
    target_instance_type: Optional[str] = None
    target_pool_id: Optional[str] = None
    reason: str = ""
    cooldown_until: Optional[datetime] = None
    decision_metadata: Optional[Dict[str, Any]] = None


class DecisionEngine:
    """
    Unified Decision Engine for spot optimization.

    Processes instance state, usage, pricing, and predictions to make
    intelligent decisions about staying, switching, or falling back.
    """

    def __init__(self, config: Optional[DecisionConfig] = None):
        """
        Initialize decision engine.

        Args:
            config: Configuration parameters (uses defaults if not provided)
        """
        self.config = config or DecisionConfig()
        logger.info("Decision Engine initialized with config: %s", self.config)

    def decide(
        self,
        instance_state: Dict[str, Any],
        usage_metrics: Dict[str, Any],
        pricing_snapshot: Dict[str, Any],
        predictions: Dict[str, Any],
    ) -> Decision:
        """
        Main decision method - analyze all inputs and make decision.

        Args:
            instance_state: Current instance state (from Executor)
            usage_metrics: Usage metrics (from Executor)
            pricing_snapshot: Current pricing (from Executor)
            predictions: 1-hour ahead predictions (from ML model)

        Returns:
            Decision object with recommended action
        """
        logger.info(f"Making decision for instance {instance_state.get('instance_id')}")

        # TODO: Implement full decision logic per master-session-memory.md
        # For now, return a placeholder decision

        return Decision(
            action_type=ActionType.STAY,
            reason="Decision engine not yet fully implemented",
            cooldown_until=datetime.utcnow() + timedelta(minutes=self.config.cooldown_minutes)
        )

    def classify_usage(self, usage_metrics: Dict[str, float]) -> UsageClassification:
        """
        Classify instance as over/right/under-provisioned.

        Args:
            usage_metrics: CPU, memory metrics with p95 values

        Returns:
            UsageClassification enum
        """
        cpu_p95 = usage_metrics.get('cpu_p95', 50.0)
        mem_p95 = usage_metrics.get('memory_p95', 50.0)

        # Over-provisioned: both CPU and memory low
        if (cpu_p95 < self.config.over_provisioned_cpu_max and
            mem_p95 < self.config.over_provisioned_mem_max):
            return UsageClassification.OVER_PROVISIONED

        # Under-provisioned: either CPU or memory high
        if (cpu_p95 > self.config.under_provisioned_cpu_min or
            mem_p95 > self.config.under_provisioned_mem_min):
            return UsageClassification.UNDER_PROVISIONED

        # Right-sized: everything in between
        return UsageClassification.RIGHT_SIZED

    def is_current_pool_future_ok(
        self,
        predicted_discount: float,
        predicted_volatility: float
    ) -> bool:
        """
        Check if current pool will be acceptable in 1 hour.

        Args:
            predicted_discount: Predicted discount for current pool
            predicted_volatility: Predicted volatility for current pool

        Returns:
            True if pool predicted to be OK
        """
        discount_ok = (predicted_discount >=
                      self.config.baseline_discount - self.config.discount_margin)
        volatility_ok = (predicted_volatility <=
                        self.config.baseline_volatility * self.config.volatility_factor_max)

        return discount_ok and volatility_ok
