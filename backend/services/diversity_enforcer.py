"""
Diversity Enforcer
=================

Enforces family and AZ diversity constraints for Decision Engine v3.
Prevents clusters from becoming too concentrated in single families or AZs.
"""

from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class DiversityEnforcer:
    """
    Checks diversity constraints before approving pool selections.

    Thresholds are passed from Decision Engine per optimization_mode:
    - COST_FIRST: max_family_ratio=0.4, max_az_ratio=0.5
    - BALANCED: max_family_ratio=0.4, max_az_ratio=0.5
    - NO_DOWNTIME_FIRST: max_family_ratio=0.3, max_az_ratio=0.4
    """

    def __init__(self, redis=None):
        self.redis = redis

    def check_candidate(
        self,
        candidate_pool: Dict,
        cluster_node_distribution: Dict,
        total_nodes: int,
        max_family_ratio: float = 0.4,
        max_az_ratio: float = 0.5
    ) -> Tuple[bool, str]:
        """
        Check if candidate pool passes diversity constraints.

        Args:
            candidate_pool: Pool to check, must have "instance_type" and "az" keys
            cluster_node_distribution: Current distribution dict with keys:
                - "family:m5": count of m5 family nodes
                - "az:us-east-1a": count of nodes in us-east-1a
                - etc.
            total_nodes: Current total node count
            max_family_ratio: Maximum allowed ratio for any single family
            max_az_ratio: Maximum allowed ratio for any single AZ

        Returns:
            (passes: bool, reason: str)
        """
        try:
            instance_type = candidate_pool.get("instance_type")
            az = candidate_pool.get("az")

            if not instance_type or not az:
                return (False, "Missing instance_type or az in candidate pool")

            # Extract family from instance type (e.g., "m5.xlarge" -> "m5")
            family = instance_type.split('.')[0]

            # Check family constraint
            family_key = f"family:{family}"
            family_count = cluster_node_distribution.get(family_key, 0)

            # +1 because we're checking if adding this node would violate
            new_family_count = family_count + 1
            new_total_nodes = total_nodes + 1

            family_ratio = new_family_count / new_total_nodes if new_total_nodes > 0 else 0

            if family_ratio > max_family_ratio:
                reason = (
                    f"Family {family} would exceed {max_family_ratio * 100:.0f}% "
                    f"({new_family_count}/{new_total_nodes} = {family_ratio * 100:.1f}%)"
                )
                logger.info(f"Diversity check FAILED: {reason}")
                return (False, reason)

            # Check AZ constraint
            az_key = f"az:{az}"
            az_count = cluster_node_distribution.get(az_key, 0)

            new_az_count = az_count + 1
            az_ratio = new_az_count / new_total_nodes if new_total_nodes > 0 else 0

            if az_ratio > max_az_ratio:
                reason = (
                    f"AZ {az} would exceed {max_az_ratio * 100:.0f}% "
                    f"({new_az_count}/{new_total_nodes} = {az_ratio * 100:.1f}%)"
                )
                logger.info(f"Diversity check FAILED: {reason}")
                return (False, reason)

            # Passed both checks
            logger.debug(
                f"Diversity check PASSED: {family}={family_ratio:.2f}, {az}={az_ratio:.2f}"
            )
            return (True, "")

        except Exception as e:
            logger.error(f"Error checking diversity: {e}")
            # Fail open on errors — don't block operations
            return (True, "")

    def get_cluster_diversity(self, cluster_id: str, db=None) -> Dict:
        """
        Get current cluster diversity distribution for UI gauge.

        Queries running instances from the DB when a session is provided.
        Falls back to empty structure (safe default) when db is not available.

        Returns:
            {
                "total_nodes": int,
                "family_distribution": {"m5": 10, "c5": 5, ...},
                "az_distribution": {"us-east-1a": 8, "us-east-1b": 7, ...},
                "family_percentages": {"m5": 0.67, "c5": 0.33, ...},
                "az_percentages": {"us-east-1a": 0.53, "us-east-1b": 0.47, ...}
            }
        """
        if db is None:
            return {
                "total_nodes": 0,
                "family_distribution": {},
                "az_distribution": {},
                "family_percentages": {},
                "az_percentages": {},
            }

        try:
            from backend.models.instance import Instance
            instances = db.query(Instance).filter(
                Instance.cluster_id == cluster_id,
                Instance.state == "running",
            ).all()

            family_dist: Dict[str, int] = {}
            az_dist: Dict[str, int] = {}
            total = len(instances)

            for inst in instances:
                if inst.instance_type:
                    fam = inst.instance_type.split(".")[0]
                    family_dist[fam] = family_dist.get(fam, 0) + 1
                if inst.availability_zone:
                    az_dist[inst.availability_zone] = az_dist.get(inst.availability_zone, 0) + 1

            family_pct = {k: round(v / total, 4) for k, v in family_dist.items()} if total else {}
            az_pct = {k: round(v / total, 4) for k, v in az_dist.items()} if total else {}

            return {
                "total_nodes": total,
                "family_distribution": family_dist,
                "az_distribution": az_dist,
                "family_percentages": family_pct,
                "az_percentages": az_pct,
            }
        except Exception as e:
            logger.error(f"get_cluster_diversity({cluster_id}) DB query failed: {e}")
            return {
                "total_nodes": 0,
                "family_distribution": {},
                "az_distribution": {},
                "family_percentages": {},
                "az_percentages": {},
            }

    def compute_distribution_from_nodes(self, nodes: list) -> Dict:
        """
        Compute distribution dict from node list.

        Args:
            nodes: List of node dicts with "instance_type" and "az" keys

        Returns:
            {
                "family:m5": count,
                "az:us-east-1a": count,
                "total": count
            }
        """
        distribution = {}

        for node in nodes:
            instance_type = node.get("instance_type", "")
            az = node.get("az", "")

            if instance_type:
                family = instance_type.split('.')[0]
                family_key = f"family:{family}"
                distribution[family_key] = distribution.get(family_key, 0) + 1

            if az:
                az_key = f"az:{az}"
                distribution[az_key] = distribution.get(az_key, 0) + 1

        distribution["total"] = len(nodes)
        return distribution

    def filter_by_cluster_pools(
        self,
        pools: list,
        cluster_id: str,
    ) -> list:
        """
        Remove pools already in use by the cluster.

        Uses Redis set `cluster_pools:{cluster_id}` to track which pools
        are currently active. Pools are identified by "instance_type:az" keys.

        Args:
            pools: List of pool dicts with "instance_type" and "az" keys
            cluster_id: Cluster ID

        Returns:
            Filtered list of pools not already in use
        """
        cluster_pools_key = f"cluster_pools:{cluster_id}"
        try:
            if not self.redis:
                return pools
            in_use = self.redis.smembers(cluster_pools_key)
            if not in_use:
                return pools

            in_use_str = {
                m.decode() if isinstance(m, bytes) else m
                for m in in_use
            }
            filtered = []
            for p in pools:
                pool_key = f"{p.get('instance_type')}:{p.get('az')}"
                if pool_key not in in_use_str:
                    filtered.append(p)

            logger.info(
                f"Diversity filter: {len(pools)} → {len(filtered)} "
                f"after removing {len(in_use_str)} in-use pools"
            )
            return filtered
        except Exception as e:
            logger.error(f"Error in filter_by_cluster_pools: {e}")
            return pools

    def update_cluster_pools(
        self,
        cluster_id: str,
        instance_type: str,
        az: str,
        add: bool = True,
    ):
        """
        Add or remove a pool from the cluster's active pool set.

        Called when instances are added to or removed from the cluster.

        Args:
            cluster_id: Cluster ID
            instance_type: EC2 instance type
            az: Availability zone
            add: True to add, False to remove
        """
        cluster_pools_key = f"cluster_pools:{cluster_id}"
        pool_key = f"{instance_type}:{az}"
        try:
            if not self.redis:
                return
            if add:
                self.redis.sadd(cluster_pools_key, pool_key)
                logger.debug(f"Added {pool_key} to cluster_pools:{cluster_id}")
            else:
                self.redis.srem(cluster_pools_key, pool_key)
                logger.debug(f"Removed {pool_key} from cluster_pools:{cluster_id}")
        except Exception as e:
            logger.error(f"Error updating cluster_pools: {e}")

