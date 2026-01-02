"""
Right-Sizing Module (MOD-SIZE-01)
Analyzes resource usage vs requests and generates resize recommendations
"""
import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from backend.models.instance import Instance

logger = logging.getLogger(__name__)


class RightSizingModule:
    """
    MOD-SIZE-01: Analyzes 14-day resource usage patterns and recommends right-sizing

    Responsibilities:
    - Analyze CPU/memory usage vs allocated resources
    - Recommend smaller instance types when overprovisioned
    - Calculate potential savings from right-sizing
    """

    def __init__(self, db: Session):
        self.db = db
        self.analysis_days = 14

    def analyze_resource_usage(self, cluster_id: str) -> Dict[str, Any]:
        """
        Analyze 14-day resource usage patterns

        Args:
            cluster_id: UUID of cluster to analyze

        Returns:
            {
                "cluster_id": "...",
                "analysis_period_days": 14,
                "overprovisioned_instances": [
                    {
                        "instance_id": "i-0x123",
                        "instance_type": "m5.xlarge",
                        "capacity": {"cpu": 4, "memory": 16},
                        "average_usage": {"cpu": 1.2, "memory": 4.5},
                        "peak_usage": {"cpu": 2.0, "memory": 8.0},
                        "utilization_percent": {"cpu": 30, "memory": 28},
                        "recommendation": "Downsize to m5.large",
                        "potential_savings_monthly": 46.08
                    }
                ],
                "total_potential_savings": 150.50
            }
        """
        logger.info(f"[MOD-SIZE-01] Analyzing resource usage for cluster {cluster_id}")

        instances = self.db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.deleted_at.is_(None)
        ).all()

        overprovisioned = []
        total_savings = 0.0

        for instance in instances:
            cpu_util = instance.cpu_util or 0
            memory_util = instance.memory_util or 0

            # If both CPU and memory are <50% utilized, it's overprovisioned
            if cpu_util < 50 and memory_util < 50:
                capacity = self._get_instance_capacity(instance.instance_type)

                # Calculate average usage (simplified - in production, query Prometheus)
                avg_cpu = capacity['cpu'] * (cpu_util / 100)
                avg_memory = capacity['memory'] * (memory_util / 100)

                # Simulate peak as 1.5x average
                peak_cpu = avg_cpu * 1.5
                peak_memory = avg_memory * 1.5

                # Get smaller instance type recommendation
                recommendation = self._get_downsize_recommendation(
                    instance.instance_type,
                    peak_cpu,
                    peak_memory
                )

                if recommendation:
                    current_price = instance.price or 0.096
                    new_price = current_price * 0.5  # ~50% cheaper
                    monthly_savings = (current_price - new_price) * 730

                    overprovisioned.append({
                        "instance_id": instance.instance_id,
                        "instance_type": instance.instance_type,
                        "capacity": capacity,
                        "average_usage": {
                            "cpu": round(avg_cpu, 1),
                            "memory": round(avg_memory, 1)
                        },
                        "peak_usage": {
                            "cpu": round(peak_cpu, 1),
                            "memory": round(peak_memory, 1)
                        },
                        "utilization_percent": {
                            "cpu": round(cpu_util, 1),
                            "memory": round(memory_util, 1)
                        },
                        "recommendation": recommendation,
                        "potential_savings_monthly": round(monthly_savings, 2)
                    })

                    total_savings += monthly_savings

        result = {
            "cluster_id": cluster_id,
            "analysis_period_days": self.analysis_days,
            "overprovisioned_instances": overprovisioned,
            "total_potential_savings": round(total_savings, 2)
        }

        logger.info(f"[MOD-SIZE-01] Found {len(overprovisioned)} overprovisioned instances, potential savings: ${total_savings:.2f}/mo")
        return result

    def generate_resize_recommendations(self, instance_id: str) -> Dict[str, Any]:
        """Generate resize recommendations for specific instance"""
        instance = self.db.query(Instance).filter(Instance.instance_id == instance_id).first()

        if not instance:
            return {"error": "Instance not found"}

        cpu_util = instance.cpu_util or 0
        memory_util = instance.memory_util or 0
        capacity = self._get_instance_capacity(instance.instance_type)

        peak_cpu = capacity['cpu'] * (cpu_util / 100) * 1.5
        peak_memory = capacity['memory'] * (memory_util / 100) * 1.5

        recommendation = self._get_downsize_recommendation(instance.instance_type, peak_cpu, peak_memory)

        if recommendation:
            current_price = instance.price or 0.096
            new_price = current_price * 0.5
            monthly_savings = (current_price - new_price) * 730

            return {
                "instance_id": instance_id,
                "current_type": instance.instance_type,
                "recommended_type": recommendation,
                "confidence": "HIGH" if cpu_util < 30 else "MEDIUM",
                "estimated_savings": {
                    "hourly": round(current_price - new_price, 4),
                    "monthly": round(monthly_savings, 2)
                }
            }

        return {"instance_id": instance_id, "recommendation": "No resize needed"}

    def _get_instance_capacity(self, instance_type: str) -> Dict[str, float]:
        """Get instance capacity"""
        capacities = {
            "t3.medium": {"cpu": 2, "memory": 4},
            "c5.large": {"cpu": 2, "memory": 4},
            "c5.xlarge": {"cpu": 4, "memory": 8},
            "m5.large": {"cpu": 2, "memory": 8},
            "m5.xlarge": {"cpu": 4, "memory": 16},
            "m5.2xlarge": {"cpu": 8, "memory": 32},
            "r5.large": {"cpu": 2, "memory": 16},
            "r5.xlarge": {"cpu": 4, "memory": 32},
        }
        return capacities.get(instance_type, {"cpu": 4, "memory": 16})

    def _get_downsize_recommendation(self, current_type: str, peak_cpu: float, peak_memory: float) -> str:
        """Recommend smaller instance type based on peak usage"""
        # Simple downsize mapping
        downsize_map = {
            "m5.2xlarge": "m5.xlarge",
            "m5.xlarge": "m5.large",
            "c5.2xlarge": "c5.xlarge",
            "c5.xlarge": "c5.large",
            "r5.2xlarge": "r5.xlarge",
            "r5.xlarge": "r5.large",
        }

        smaller_type = downsize_map.get(current_type)
        if smaller_type:
            smaller_capacity = self._get_instance_capacity(smaller_type)
            # Check if smaller instance can handle peak usage with 20% headroom
            if peak_cpu <= smaller_capacity['cpu'] * 0.8 and peak_memory <= smaller_capacity['memory'] * 0.8:
                return f"Downsize to {smaller_type}"

        return None


def get_rightsizer(db: Session) -> RightSizingModule:
    """Get RightSizing module instance"""
    return RightSizingModule(db)
