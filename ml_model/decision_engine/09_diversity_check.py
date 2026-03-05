"""
Step 12: Diversity Enforcement
================================
Source: backend/services/diversity_enforcer.py

PURPOSE
-------
Prevent over-concentration of nodes in a single instance family or AZ.
This limits blast radius — if one family or AZ has a systemic issue
(mass interruption, AZ outage), only a fraction of the cluster is affected.

WHY DIVERSITY MATTERS
-----------------------
Without diversity enforcement:
  - All nodes might be m5.large in us-east-1a
  - If AWS interrupts that AZ or instance family → entire cluster goes down
  - This eliminates the savings from spot entirely (too much risk)

With diversity enforcement:
  - Max 40% of nodes in any single instance family (BALANCED mode)
  - Max 50% of nodes in any single AZ (BALANCED mode)
  - Cluster survives single-family or single-AZ interruptions
  - Remaining nodes handle traffic while Karpenter provisions replacements

TWO DIVERSITY CONSTRAINTS
--------------------------

  1. Instance Family Diversity (max_family_ratio)
     -----------------------------------------------
     Limits how many nodes can use the same instance family (m5, c5, r5, etc.)

     Default ratios by mode:
       COST_FIRST:        40% (0.40)
       BALANCED:          40% (0.40) — default
       NO_DOWNTIME_FIRST: 30% (0.30) — stricter

     Example with 10 total nodes, BALANCED:
       max_family_ratio = 0.40 → max 4 nodes in any family
       Current: m5 × 4, c5 × 3, r5 × 3
       Candidate: m5.xlarge → would make m5 × 5 (50%) → BLOCKED
       Candidate: c5.large → would make c5 × 4 (40%) → ALLOWED

  2. AZ Diversity (max_az_ratio)
     ------------------------------
     Limits how many nodes can be in the same Availability Zone.

     Default ratios by mode:
       COST_FIRST:        50% (0.50)
       BALANCED:          50% (0.50) — default
       NO_DOWNTIME_FIRST: 40% (0.40) — stricter

     Example with 10 nodes, BALANCED:
       max_az_ratio = 0.50 → max 5 nodes per AZ
       Current: us-east-1a × 5, us-east-1b × 3, us-east-1c × 2
       Candidate: m5.large:us-east-1a → would make 1a × 6 (60%) → BLOCKED
       Candidate: m5.large:us-east-1b → would make 1b × 4 (40%) → ALLOWED

DEADLOCK PROTECTION
--------------------
If ALL candidates fail diversity checks (fully saturated cluster):
  - If current pool EV ≥ 0.5 (safe enough): hold current pool, block switch
  - If current pool EV < 0.5 (risky): reject with diversity violation error

This prevents a deadlock where the optimizer keeps trying to switch but
can't because all families are at capacity. Holding is the safer option.

EMERGENCY BYPASS
-----------------
When is_emergency=True (spot interruption notice), diversity checks are skipped.
In an emergency, we must replace the node quickly — diversity is secondary to availability.
"""

from typing import Dict, List, Optional, Tuple


class DiversityEnforcer:
    """
    Checks and enforces instance family and AZ diversity constraints.

    The node distribution is read from Redis (cached current state of the cluster).
    All checks are performed against this cached state — no real-time K8s API calls.
    """

    def __init__(self, redis_client=None):
        """
        Args:
            redis_client: Redis connection (optional, for future caching)
        """
        self.redis = redis_client

    def check_candidate(
        self,
        candidate_pool: Dict,
        cluster_node_distribution: Dict,
        total_nodes: int,
        max_family_ratio: float = 0.4,
        max_az_ratio: float = 0.5,
    ) -> Tuple[bool, str]:
        """
        Check if adding this candidate would violate diversity constraints.

        Called in DecisionEngine Step 12 for each remaining candidate pool.
        Returns (passes, reason) so the caller can log why specific pools were blocked.

        Args:
            candidate_pool:           Pool dict with instance_type and az
            cluster_node_distribution: Current node counts by family and AZ.
                                       Format:
                                         {
                                           "family_counts": {"m5": 4, "c5": 3, ...},
                                           "az_counts": {"us-east-1a": 5, ...}
                                         }
            total_nodes:              Total number of nodes in cluster (denominator)
            max_family_ratio:         Maximum fraction for any instance family (0.0–1.0)
            max_az_ratio:             Maximum fraction for any AZ (0.0–1.0)

        Returns:
            (passes, reason)
            passes=True  → candidate respects diversity constraints → eligible
            passes=False → candidate would violate a constraint → blocked
            reason       → human-readable explanation (for logging)
        """
        if total_nodes == 0:
            return True, "No nodes yet — diversity check skipped"

        instance_type = candidate_pool.get("instance_type", "")
        az = candidate_pool.get("az", "")
        family = instance_type.split(".")[0] if "." in instance_type else instance_type

        family_counts = cluster_node_distribution.get("family_counts", {})
        az_counts = cluster_node_distribution.get("az_counts", {})

        # ── Check 1: Instance family concentration ──────────────────────────
        current_family_count = family_counts.get(family, 0)
        # Adding one more node of this family would result in:
        new_family_count = current_family_count + 1
        new_family_ratio = new_family_count / total_nodes

        if new_family_ratio > max_family_ratio:
            return (
                False,
                f"Family '{family}' would be {new_family_ratio:.1%} of cluster "
                f"(max {max_family_ratio:.0%}): {new_family_count}/{total_nodes} nodes"
            )

        # ── Check 2: AZ concentration ────────────────────────────────────────
        if az:
            current_az_count = az_counts.get(az, 0)
            new_az_count = current_az_count + 1
            new_az_ratio = new_az_count / total_nodes

            if new_az_ratio > max_az_ratio:
                return (
                    False,
                    f"AZ '{az}' would be {new_az_ratio:.1%} of cluster "
                    f"(max {max_az_ratio:.0%}): {new_az_count}/{total_nodes} nodes"
                )

        return True, "Passes diversity constraints"

    def get_cluster_distribution(self, cluster_id: str, instances: List[Dict]) -> Dict:
        """
        Build the cluster node distribution dict from current instance list.

        This is precomputed and passed to check_candidate() for each pool.
        Computing it once and reusing avoids redundant iteration.

        Args:
            cluster_id: Cluster identifier (for caching, future use)
            instances:  List of instance dicts with instance_type and az/availability_zone

        Returns:
            {
                "family_counts": {"m5": 4, "c5": 3},
                "az_counts": {"us-east-1a": 5, "us-east-1b": 2}
            }
        """
        family_counts = {}
        az_counts = {}

        for inst in instances:
            instance_type = inst.get("instance_type", "")
            az = inst.get("az") or inst.get("availability_zone", "")

            if instance_type:
                family = instance_type.split(".")[0] if "." in instance_type else instance_type
                family_counts[family] = family_counts.get(family, 0) + 1

            if az:
                az_counts[az] = az_counts.get(az, 0) + 1

        return {
            "family_counts": family_counts,
            "az_counts": az_counts
        }

    def filter_diverse_candidates(
        self,
        candidate_pools: List[Dict],
        cluster_node_distribution: Dict,
        total_nodes: int,
        max_family_ratio: float = 0.4,
        max_az_ratio: float = 0.5,
    ) -> Tuple[List[Dict], List[str]]:
        """
        Filter a candidate list to only diversity-compliant pools.

        Wrapper that calls check_candidate() for each pool and collects reasons.

        Args:
            candidate_pools:           List of pool dicts
            cluster_node_distribution: From get_cluster_distribution()
            total_nodes:               Total cluster node count
            max_family_ratio:          From optimization profile
            max_az_ratio:              From optimization profile

        Returns:
            (passing_candidates, rejection_reasons)
            passing_candidates: Pools that respect diversity
            rejection_reasons:  Why each failing pool was blocked (for logging)
        """
        passing = []
        reasons = []

        for pool in candidate_pools:
            passes, reason = self.check_candidate(
                candidate_pool=pool,
                cluster_node_distribution=cluster_node_distribution,
                total_nodes=total_nodes,
                max_family_ratio=max_family_ratio,
                max_az_ratio=max_az_ratio,
            )
            if passes:
                passing.append(pool)
            else:
                reasons.append(f"{pool.get('instance_type')}:{pool.get('az')} — {reason}")

        return passing, reasons
