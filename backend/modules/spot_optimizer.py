"""
Spot Optimization Engine (MOD-SPOT-01)
Balances Price vs Stability for instance selection
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from redis import Redis

from backend.core.config import settings
from backend.models.instance import Instance
from backend.models.cluster import Cluster
from backend.schemas.metric_schemas import ChartData, PieData

logger = logging.getLogger(__name__)


class SpotOptimizationEngine:
    """
    MOD-SPOT-01: Core intelligence module for Spot instance optimization

    Responsibilities:
    - Select best instance types balancing price vs interruption risk
    - Detect optimization opportunities (waste, overprovisioning)
    - Calculate savings projections
    """

    def __init__(self, db: Session, redis_client: Redis):
        self.db = db
        self.redis = redis_client
        self.price_weight = 0.6
        self.risk_weight = 0.4

    def select_best_instance(
        self,
        pod_requirements: Dict[str, Any],
        region: str,
        availability_zones: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Select best instance type for pod requirements

        Logic:
        1. Query Redis for current Spot prices
        2. Query Global Risk Tracker for flagged pools
        3. Filter out risky pools
        4. Score: (Price * 0.6) + (Risk * 0.4)
        5. Return sorted candidate list

        Args:
            pod_requirements: Dict with cpu, memory, gpu requirements
            region: AWS region (e.g., 'us-east-1')
            availability_zones: List of AZs to consider

        Returns:
            List of candidate instances sorted by score (best first)
            [
                {
                    "instance_type": "c5.large",
                    "lifecycle": "SPOT",
                    "az": "us-east-1a",
                    "price": 0.045,
                    "risk_score": 0.12,
                    "total_score": 0.075,
                    "recommendation": "SAFE"
                },
                ...
            ]
        """
        logger.info(f"[MOD-SPOT-01] Selecting best instance for pod requirements in {region}")

        # Extract requirements
        cpu_required = pod_requirements.get('cpu', 2)
        memory_required = pod_requirements.get('memory', 4)  # GB
        gpu_required = pod_requirements.get('gpu', 0)

        # Get candidate instance types based on requirements
        candidates = self._get_candidate_instances(cpu_required, memory_required, gpu_required)

        # Fetch Spot prices from Redis for each candidate
        scored_candidates = []

        for instance_type in candidates:
            for az in availability_zones:
                # Check if this pool is flagged as risky in global risk tracker
                risk_key = f"RISK:{az}:{instance_type}"
                is_risky = self.redis.get(risk_key)

                if is_risky:
                    logger.warning(f"[MOD-SPOT-01] Skipping {instance_type} in {az} - flagged as risky")
                    continue

                # Query Spot price from Redis
                price_key = f"spot_prices:{region}:{instance_type}:{az}"
                spot_price = self.redis.get(price_key)

                if not spot_price:
                    # Use fallback static pricing
                    spot_price = self._get_fallback_price(instance_type)
                else:
                    spot_price = float(spot_price)

                # Get historical risk score (0-1, where 1 = highest risk)
                risk_score = self._get_historical_risk(instance_type, az, region)

                # Calculate total score: lower is better
                # Price component: normalize to 0-1 (assuming max $1/hr)
                price_component = min(spot_price, 1.0)

                # Total score
                total_score = (price_component * self.price_weight) + (risk_score * self.risk_weight)

                # Recommendation
                if risk_score < 0.2:
                    recommendation = "SAFE"
                elif risk_score < 0.5:
                    recommendation = "CAUTION"
                else:
                    recommendation = "AVOID"

                scored_candidates.append({
                    "instance_type": instance_type,
                    "lifecycle": "SPOT",
                    "az": az,
                    "price": spot_price,
                    "risk_score": risk_score,
                    "total_score": total_score,
                    "recommendation": recommendation
                })

        # Sort by total score (best first)
        scored_candidates.sort(key=lambda x: x['total_score'])

        # Add On-Demand fallback option as last resort
        if scored_candidates:
            best_spot = scored_candidates[0]
            on_demand_price = self._get_on_demand_price(best_spot['instance_type'])

            scored_candidates.append({
                "instance_type": best_spot['instance_type'],
                "lifecycle": "ON_DEMAND",
                "az": availability_zones[0],
                "price": on_demand_price,
                "risk_score": 0.0,  # On-Demand has no interruption risk
                "total_score": on_demand_price * self.price_weight,  # Only price matters
                "recommendation": "FALLBACK"
            })

        logger.info(f"[MOD-SPOT-01] Selected {len(scored_candidates)} candidates")
        return scored_candidates

    def detect_opportunities(self, cluster_id: str) -> List[Dict[str, Any]]:
        """
        Detect optimization opportunities in a cluster

        Logic:
        - Find On-Demand instances with <30% utilization
        - Identify Spot replacement candidates
        - Find overprovisioned instances

        Args:
            cluster_id: UUID of the cluster to analyze

        Returns:
            List of opportunities:
            [
                {
                    "opportunity_type": "od_to_spot",
                    "instance_id": "i-0x123",
                    "instance_type": "m5.large",
                    "current_cost": 0.096,
                    "potential_cost": 0.038,
                    "savings": 0.058,
                    "savings_percent": 60.4,
                    "utilization": 25.3,
                    "risk": "LOW",
                    "recommendation": "Replace with Spot",
                    "priority": "HIGH"
                },
                ...
            ]
        """
        logger.info(f"[MOD-SPOT-01] Detecting opportunities for cluster {cluster_id}")

        # Query all instances in cluster
        instances = self.db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.deleted_at.is_(None)
        ).all()

        opportunities = []

        for instance in instances:
            # Skip if already Spot
            if instance.lifecycle == "SPOT":
                continue

            # Check utilization
            cpu_util = instance.cpu_util or 0
            memory_util = instance.memory_util or 0
            avg_util = (cpu_util + memory_util) / 2

            # Opportunity: On-Demand with low utilization → Spot
            if avg_util < 30:
                spot_price = self._get_fallback_price(instance.instance_type) * 0.4  # ~60% discount
                current_cost = instance.price or self._get_on_demand_price(instance.instance_type)
                savings = current_cost - spot_price
                savings_percent = (savings / current_cost) * 100

                opportunities.append({
                    "opportunity_type": "od_to_spot",
                    "instance_id": instance.instance_id,
                    "instance_type": instance.instance_type,
                    "current_cost": round(current_cost, 4),
                    "potential_cost": round(spot_price, 4),
                    "savings": round(savings, 4),
                    "savings_percent": round(savings_percent, 1),
                    "utilization": round(avg_util, 1),
                    "risk": "LOW" if avg_util < 20 else "MEDIUM",
                    "recommendation": "Replace with Spot",
                    "priority": "HIGH" if savings > 0.05 else "MEDIUM"
                })

        # Sort by potential savings (highest first)
        opportunities.sort(key=lambda x: x['savings'], reverse=True)

        logger.info(f"[MOD-SPOT-01] Found {len(opportunities)} opportunities, total savings: ${sum(o['savings'] for o in opportunities):.2f}/hr")
        return opportunities

    def get_savings_projection(self, cluster_id: str) -> ChartData:
        """
        Calculate savings projection for a cluster

        Logic:
        - Simulate Spot replacement for all On-Demand instances
        - Calculate bin packing savings
        - Return chart data for frontend visualization

        Args:
            cluster_id: UUID of the cluster

        Returns:
            ChartData schema with:
            - Unoptimized cost
            - Optimized cost
            - Savings breakdown
        """
        logger.info(f"[MOD-SPOT-01] Calculating savings projection for cluster {cluster_id}")

        # Get current state
        instances = self.db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.deleted_at.is_(None)
        ).all()

        current_monthly_cost = 0
        optimized_monthly_cost = 0

        for instance in instances:
            current_price = instance.price or self._get_on_demand_price(instance.instance_type)
            current_monthly = current_price * 730  # hours per month
            current_monthly_cost += current_monthly

            # If On-Demand, calculate Spot equivalent
            if instance.lifecycle == "ON_DEMAND":
                spot_price = current_price * 0.4  # ~60% discount
                optimized_monthly = spot_price * 730
            else:
                optimized_monthly = current_monthly  # Already Spot

            optimized_monthly_cost += optimized_monthly

        total_savings = current_monthly_cost - optimized_monthly_cost
        savings_percent = (total_savings / current_monthly_cost * 100) if current_monthly_cost > 0 else 0

        # Build chart data
        chart_data = {
            "labels": ["Current", "Optimized"],
            "datasets": [
                {
                    "label": "Monthly Cost",
                    "data": [
                        round(current_monthly_cost, 2),
                        round(optimized_monthly_cost, 2)
                    ],
                    "backgroundColor": ["#ef4444", "#10b981"]
                }
            ],
            "summary": {
                "current_cost": round(current_monthly_cost, 2),
                "optimized_cost": round(optimized_monthly_cost, 2),
                "total_savings": round(total_savings, 2),
                "savings_percent": round(savings_percent, 1)
            }
        }

        logger.info(f"[MOD-SPOT-01] Projection: ${current_monthly_cost:.2f} → ${optimized_monthly_cost:.2f}, savings: ${total_savings:.2f} ({savings_percent:.1f}%)")
        return chart_data

    # Private helper methods

    def _get_candidate_instances(self, cpu: int, memory: int, gpu: int) -> List[str]:
        """Get instance types that meet requirements"""
        # Simplified logic - in production, query from instance_family table
        if gpu > 0:
            return ["g4dn.xlarge", "g4dn.2xlarge", "p3.2xlarge"]
        elif cpu <= 2 and memory <= 4:
            return ["t3.medium", "t3a.medium", "c5.large", "m5.large"]
        elif cpu <= 4 and memory <= 8:
            return ["c5.xlarge", "m5.xlarge", "r5.large"]
        elif cpu <= 8 and memory <= 16:
            return ["c5.2xlarge", "m5.2xlarge", "r5.xlarge"]
        else:
            return ["c5.4xlarge", "m5.4xlarge", "r5.2xlarge"]

    def _get_historical_risk(self, instance_type: str, az: str, region: str) -> float:
        """Get historical interruption risk from Redis or database"""
        # Query interruption history
        risk_history_key = f"interruption_history:{region}:{az}:{instance_type}"
        interruption_count = self.redis.get(risk_history_key)

        if interruption_count:
            # Normalize: 0 interruptions = 0.0, 10+ = 1.0
            return min(int(interruption_count) / 10.0, 1.0)

        # Fallback: use static risk scores based on AWS Spot Advisor data
        static_risks = {
            "c5.large": 0.05,
            "c5.xlarge": 0.08,
            "m5.large": 0.12,
            "m5.xlarge": 0.15,
            "r5.large": 0.10,
            "r5.xlarge": 0.18,
            "t3.medium": 0.03,
            "g4dn.xlarge": 0.25,
        }

        return static_risks.get(instance_type, 0.20)  # Default 20% risk

    def _get_fallback_price(self, instance_type: str) -> float:
        """Get fallback Spot price when Redis data unavailable"""
        # Static pricing for common instance types (approximate)
        static_prices = {
            "t3.medium": 0.0208,
            "c5.large": 0.045,
            "c5.xlarge": 0.085,
            "m5.large": 0.050,
            "m5.xlarge": 0.096,
            "r5.large": 0.063,
            "r5.xlarge": 0.126,
            "g4dn.xlarge": 0.30,
        }
        return static_prices.get(instance_type, 0.10)

    def _get_on_demand_price(self, instance_type: str) -> float:
        """Get On-Demand price"""
        spot_price = self._get_fallback_price(instance_type)
        return spot_price / 0.4  # Reverse the ~60% Spot discount


# Singleton instance
_engine_instance = None

def get_spot_optimizer(db: Session, redis_client: Redis) -> SpotOptimizationEngine:
    """Get or create Spot Optimizer singleton"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = SpotOptimizationEngine(db, redis_client)
    return _engine_instance
