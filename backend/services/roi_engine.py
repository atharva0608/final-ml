"""
ROI Engine
==========
Calculates the Return on Investment for a specific optimization action.
Prevents "churning" (moving workloads for negligible savings).
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ROIEngine:
    """
    Economic decision layer.
    ROI = (Projected Savings - Migration Cost) * Confidence
    """

    # Estimated "cost" to move a single pod (unit: USD).
    # This accounts for: startup latency, image pull, risk of failure, cache warmup.
    # In enterprise, this should be higher for Tier 1 (DBs).
    BASE_MIGRATION_COST_PER_POD = 0.50  # $0.50 per pod move

    # Minimum monthly savings required to justify any movement.
    MIN_SAVINGS_THRESHOLD_USD = 10.00  # $10/month

    def __init__(self, db_session=None, cluster_obj=None):
        self.db = db_session
        self.cluster = cluster_obj

    def evaluate_action(self, 
                        projected_savings_mo: float, 
                        pods_affected: int, 
                        workload_tier: int = 3) -> bool:
        """
        Evaluate if a migration is economically justified.
        Returns True if action should proceed, False to block.
        """
        # 0. Savings Plan / RI Over-coverage Check
        # If we have idle Savings Plans, the "cost" of On-Demand is $0.
        if self.db and self.cluster:
            try:
                from backend.services.cost_intelligence import CostIntelligence
                ci = CostIntelligence(self.db, self.cluster)
                if ci.get_savings_plan_utilization() < 0.95: # < 95% utilized
                    logger.info(f"[roi_engine] Blocked: Savings Plans under-utilized. Use free OD capacity instead.")
                    return False
            except Exception:
                pass
        # 1. Base savings check
        if projected_savings_mo < self.MIN_SAVINGS_THRESHOLD_USD:
            logger.info(f"[roi_engine] Blocked: savings ${projected_savings_mo:.2f} < threshold ${self.MIN_SAVINGS_THRESHOLD_USD}")
            return False

        # 2. Migration cost calculation
        # Tier 1 (Stateful/DB) costs 10x more to move due to risk/quorum rebalance.
        tier_multiplier = 10 if workload_tier == 1 else 2 if workload_tier == 2 else 1
        migration_cost = pods_affected * self.BASE_MIGRATION_COST_PER_POD * tier_multiplier

        # 3. Simple ROI logic: Must pay off migration cost within 1 week (conservative)
        # projected_savings_week = projected_savings_mo / 4.3
        # if projected_savings_week < migration_cost:
        
        # Or even simpler: Savings for 1 month must be at least 3x the migration cost.
        if projected_savings_mo < (migration_cost * 3):
            logger.info(
                f"[roi_engine] Blocked: savings ${projected_savings_mo:.2f} vs "
                f"cost ${migration_cost:.2f} (pods={pods_affected}, tier={workload_tier}). "
                f"ROI too low."
            )
            return False

        logger.info(f"[roi_engine] Approved: projected savings ${projected_savings_mo:.2f} justifies migration cost.")
        return True
