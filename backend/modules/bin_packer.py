"""
Bin Packing Module (MOD-PACK-01)
Identifies fragmentation and waste in clusters, generates consolidation plans
"""
import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime

from backend.models.instance import Instance
from backend.models.cluster import Cluster

logger = logging.getLogger(__name__)


class BinPackingModule:
    """
    MOD-PACK-01: Analyzes cluster resource fragmentation and generates migration plans

    Responsibilities:
    - Calculate node utilization and identify waste
    - Generate pod consolidation plans
    - Respect PodDisruptionBudgets during migrations
    """

    def __init__(self, db: Session):
        self.db = db

    def analyze_fragmentation(self, cluster_id: str) -> Dict[str, Any]:
        """
        Analyze cluster fragmentation and resource waste

        Logic:
        1. Calculate node utilization (CPU, memory)
        2. Identify underutilized nodes (<30% usage)
        3. Calculate consolidation opportunities
        4. Estimate potential savings

        Args:
            cluster_id: UUID of the cluster to analyze

        Returns:
            {
                "total_nodes": 15,
                "underutilized_nodes": 5,
                "fragmentation_score": 0.65,  # 0-1, higher = more fragmented
                "wasted_resources": {
                    "cpu": 24.5,  # vCPUs
                    "memory": 48.0  # GB
                },
                "consolidation_potential": {
                    "nodes_can_remove": 3,
                    "monthly_savings": 350.0  # USD
                },
                "node_details": [
                    {
                        "instance_id": "i-0x123",
                        "instance_type": "m5.xlarge",
                        "cpu_util": 15.3,
                        "memory_util": 22.1,
                        "status": "UNDERUTILIZED",
                        "action": "CONSOLIDATE"
                    },
                    ...
                ]
            }
        """
        logger.info(f"[MOD-PACK-01] Analyzing fragmentation for cluster {cluster_id}")

        # Query all instances in cluster
        instances = self.db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.deleted_at.is_(None)
        ).all()

        if not instances:
            logger.warning(f"[MOD-PACK-01] No instances found for cluster {cluster_id}")
            return {
                "total_nodes": 0,
                "underutilized_nodes": 0,
                "fragmentation_score": 0.0,
                "wasted_resources": {"cpu": 0, "memory": 0},
                "consolidation_potential": {"nodes_can_remove": 0, "monthly_savings": 0.0},
                "node_details": []
            }

        total_nodes = len(instances)
        underutilized_nodes = 0
        wasted_cpu = 0.0
        wasted_memory = 0.0
        node_details = []

        for instance in instances:
            cpu_util = instance.cpu_util or 0
            memory_util = instance.memory_util or 0
            avg_util = (cpu_util + memory_util) / 2

            # Get instance capacity (simplified - in production, query from instance_family table)
            capacity = self._get_instance_capacity(instance.instance_type)

            # Calculate waste
            cpu_waste = capacity['cpu'] * (1 - cpu_util / 100)
            memory_waste = capacity['memory'] * (1 - memory_util / 100)

            status = "HEALTHY"
            action = "NONE"

            if avg_util < 30:
                status = "UNDERUTILIZED"
                action = "CONSOLIDATE"
                underutilized_nodes += 1
                wasted_cpu += cpu_waste
                wasted_memory += memory_waste

            node_details.append({
                "instance_id": instance.instance_id,
                "instance_type": instance.instance_type,
                "cpu_util": round(cpu_util, 1),
                "memory_util": round(memory_util, 1),
                "avg_util": round(avg_util, 1),
                "status": status,
                "action": action,
                "wasted_cpu": round(cpu_waste, 1),
                "wasted_memory": round(memory_waste, 1)
            })

        # Calculate fragmentation score (0-1, higher = more fragmented)
        fragmentation_score = underutilized_nodes / total_nodes if total_nodes > 0 else 0

        # Estimate consolidation potential
        # Conservative estimate: can remove ~2/3 of underutilized nodes
        nodes_can_remove = int(underutilized_nodes * 0.66)

        # Calculate savings (assuming average $0.096/hr for m5.xlarge)
        avg_price_per_hour = 0.096
        monthly_savings = nodes_can_remove * avg_price_per_hour * 730  # hours per month

        result = {
            "total_nodes": total_nodes,
            "underutilized_nodes": underutilized_nodes,
            "fragmentation_score": round(fragmentation_score, 2),
            "wasted_resources": {
                "cpu": round(wasted_cpu, 1),
                "memory": round(wasted_memory, 1)
            },
            "consolidation_potential": {
                "nodes_can_remove": nodes_can_remove,
                "monthly_savings": round(monthly_savings, 2)
            },
            "node_details": node_details
        }

        logger.info(
            f"[MOD-PACK-01] Cluster {cluster_id}: {underutilized_nodes}/{total_nodes} underutilized, "
            f"can remove {nodes_can_remove} nodes, save ${monthly_savings:.2f}/mo"
        )

        return result

    def generate_migration_plan(
        self,
        cluster_id: str,
        aggressiveness: float = 0.5
    ) -> Dict[str, Any]:
        """
        Generate pod migration plan for consolidation

        Logic:
        1. Identify source nodes (underutilized)
        2. Identify target nodes (can accept more workload)
        3. Create migration plan respecting PodDisruptionBudgets
        4. Return step-by-step execution plan

        Args:
            cluster_id: UUID of the cluster
            aggressiveness: 0.0-1.0, how aggressive to be with migrations
                           0.2 = Conservative (only <20% utilized)
                           0.5 = Moderate (only <50% utilized)
                           0.8 = Aggressive (up to <80% utilized)

        Returns:
            {
                "total_migrations": 15,
                "estimated_duration": "45 minutes",
                "phases": [
                    {
                        "phase": 1,
                        "description": "Drain low-utilization nodes",
                        "steps": [
                            {
                                "action": "CORDON_NODE",
                                "target": "i-0x123",
                                "reason": "Prepare for pod eviction"
                            },
                            {
                                "action": "EVICT_PODS",
                                "source_node": "i-0x123",
                                "destination_node": "i-0x456",
                                "pod_count": 5,
                                "respect_pdb": True
                            },
                            {
                                "action": "TERMINATE_NODE",
                                "target": "i-0x123",
                                "wait_for": "all_pods_running"
                            }
                        ]
                    },
                    ...
                ],
                "rollback_plan": {
                    "enabled": True,
                    "steps": [...]
                },
                "dry_run": False
            }
        """
        logger.info(f"[MOD-PACK-01] Generating migration plan for cluster {cluster_id} (aggressiveness: {aggressiveness})")

        # Analyze current state
        analysis = self.analyze_fragmentation(cluster_id)

        # Identify source and target nodes
        utilization_threshold = aggressiveness * 100  # Convert to percentage
        source_nodes = [
            node for node in analysis['node_details']
            if node['avg_util'] < utilization_threshold
        ]

        target_nodes = [
            node for node in analysis['node_details']
            if node['avg_util'] >= 50 and node['avg_util'] < 80  # Healthy range
        ]

        if not source_nodes:
            logger.info(f"[MOD-PACK-01] No migration opportunities found at aggressiveness {aggressiveness}")
            return {
                "total_migrations": 0,
                "estimated_duration": "0 minutes",
                "phases": [],
                "rollback_plan": {"enabled": False},
                "dry_run": False
            }

        # Build migration plan in phases
        phases = []
        total_migrations = 0

        for i, source in enumerate(source_nodes[:3], 1):  # Limit to 3 nodes per run for safety
            # Estimate pod count (simplified - in production, query from K8s API)
            estimated_pods = max(1, int(source['avg_util'] / 10))  # ~10% util per pod

            # Select target node (round-robin)
            target = target_nodes[i % len(target_nodes)] if target_nodes else None

            if not target:
                logger.warning(f"[MOD-PACK-01] No target node available for {source['instance_id']}")
                continue

            phase = {
                "phase": i,
                "description": f"Migrate workload from {source['instance_id']} to {target['instance_id']}",
                "steps": [
                    {
                        "action": "CORDON_NODE",
                        "target": source['instance_id'],
                        "reason": "Prevent new pod scheduling during migration"
                    },
                    {
                        "action": "EVICT_PODS",
                        "source_node": source['instance_id'],
                        "destination_node": target['instance_id'],
                        "pod_count": estimated_pods,
                        "respect_pdb": True,
                        "max_unavailable": "25%",
                        "timeout": "10m"
                    },
                    {
                        "action": "WAIT_FOR_READY",
                        "target": target['instance_id'],
                        "condition": "all_pods_running",
                        "timeout": "5m"
                    },
                    {
                        "action": "TERMINATE_NODE",
                        "target": source['instance_id'],
                        "method": "graceful",
                        "wait_for": "pod_drain_complete"
                    }
                ]
            }

            phases.append(phase)
            total_migrations += estimated_pods

        # Estimate duration (simplified: 15 min per phase)
        estimated_duration_minutes = len(phases) * 15
        estimated_duration = f"{estimated_duration_minutes} minutes"

        # Rollback plan (in case of failure)
        rollback_plan = {
            "enabled": True,
            "steps": [
                {
                    "action": "UNCORDON_ALL",
                    "description": "Re-enable scheduling on all cordoned nodes"
                },
                {
                    "action": "SCALE_UP_ASG",
                    "count": len(source_nodes),
                    "description": "Restore original node count"
                }
            ]
        }

        plan = {
            "total_migrations": total_migrations,
            "estimated_duration": estimated_duration,
            "phases": phases,
            "rollback_plan": rollback_plan,
            "dry_run": False,
            "metadata": {
                "cluster_id": cluster_id,
                "aggressiveness": aggressiveness,
                "source_node_count": len(source_nodes),
                "target_node_count": len(target_nodes),
                "created_at": datetime.utcnow().isoformat()
            }
        }

        logger.info(f"[MOD-PACK-01] Generated plan with {len(phases)} phases, {total_migrations} total migrations")
        return plan

    # Private helper methods

    def _get_instance_capacity(self, instance_type: str) -> Dict[str, float]:
        """Get CPU and memory capacity for instance type"""
        # Simplified capacity table - in production, query from instance_family table
        capacities = {
            "t3.medium": {"cpu": 2, "memory": 4},
            "c5.large": {"cpu": 2, "memory": 4},
            "c5.xlarge": {"cpu": 4, "memory": 8},
            "c5.2xlarge": {"cpu": 8, "memory": 16},
            "m5.large": {"cpu": 2, "memory": 8},
            "m5.xlarge": {"cpu": 4, "memory": 16},
            "m5.2xlarge": {"cpu": 8, "memory": 32},
            "r5.large": {"cpu": 2, "memory": 16},
            "r5.xlarge": {"cpu": 4, "memory": 32},
            "r5.2xlarge": {"cpu": 8, "memory": 64},
        }

        return capacities.get(instance_type, {"cpu": 4, "memory": 16})  # Default


# Singleton instance
_bin_packer_instance = None

def get_bin_packer(db: Session) -> BinPackingModule:
    """Get or create Bin Packer singleton"""
    global _bin_packer_instance
    if _bin_packer_instance is None:
        _bin_packer_instance = BinPackingModule(db)
    return _bin_packer_instance
