"""
Steps 1–2: Cooldown Guard
==========================
Source: backend/services/cooldown_controller.py

PURPOSE
-------
The Cooldown Guard is the FIRST gate in the decision pipeline.
It prevents action flapping (oscillating between pools) and race conditions
between the auto-rebalancer, right-sizer, and substitute manager.

Without cooldowns, the optimizer would:
  - Switch pool A → B → A → B rapidly (wasting migration cost each time)
  - Execute simultaneous operations on the same node (corrupting state)
  - Re-target a node that was just drained (before Karpenter provisions replacement)

THREE COOLDOWN TYPES
--------------------

  1. CLUSTER COOLDOWN (Step 1)
     - Triggered after any pool switch or rebalancing action
     - Duration: 30 minutes
     - Effect: Blocks ALL pool switches for the cluster until stable
     - Redis Key: spot:cooldown:action:cluster:{cluster_id}

  2. POOL COOLDOWN (Step 2)
     - Triggered after switching FROM or TO a specific pool
     - Duration: 30 minutes per pool
     - Effect: Prevents switching back to a recently-used pool
     - Redis Key: spot:cooldown:pool:{pool_key}  (pool_key = "m5.large:us-east-1a")

  3. RESIZE COOLDOWN (Step 11/Coordinator)
     - Triggered after right-sizing a node
     - Duration: 6 hours (longer because resize is higher risk)
     - Effect: Blocks both right-sizing AND pool switches during cooldown
     - Redis Key: spot:cooldown:action:resize:{cluster_id}

  4. SUBSTITUTE COOLDOWN (SubstituteManager)
     - Triggered after deploying a substitute warm spare
     - Duration: 2 hours
     - Effect: Blocks new substitute deployments (prevents duplicate warm spares)
     - Redis Key: spot:cooldown:action:substitute:{cluster_id}

  5. STABILIZATION LOCK (cross-system)
     - Triggered after ANY action (rebalancer, substitute, resize)
     - Duration: 5 minutes
     - Effect: Short-circuit that prevents CONCURRENT operations from different systems
     - Redis Key: spot:stabilization_lock:{cluster_id}

ANTI-FLAPPING RATIONALE
------------------------
The 30-minute pool cooldown means:
  - If pool A → B switch is executed, pool B enters cooldown
  - Even if pool A looks better again 5 minutes later, the switch is blocked
  - This prevents oscillation caused by noisy pricing data

The 10-minute Karpenter provisioning cooldown (in auto_rebalancer.py) means:
  - After draining a node, the auto-rebalancer waits 10 minutes
  - This gives Karpenter time to provision a replacement spot node
  - Without this, all nodes get cordoned before any spot node appears (deadlock)

EMERGENCY BYPASS
-----------------
When ITN_BYPASS_ENABLED=True, spot interruption notices (ITN) bypass
all cooldowns because failing to respond to an ITN causes data loss.
The `is_emergency=True` flag in DecisionEngine.evaluate_action_plan()
triggers this bypass.
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Cooldown Durations (business rules)
# ---------------------------------------------------------------------------

CLUSTER_COOLDOWN_SECONDS = 1800    # 30 minutes after pool switch
POOL_COOLDOWN_SECONDS = 1800       # 30 minutes per pool
RESIZE_COOLDOWN_SECONDS = 21600    # 6 hours after rightsizing
SUBSTITUTE_COOLDOWN_SECONDS = 7200 # 2 hours after substitute deployment
STABILIZATION_LOCK_SECONDS = 300   # 5 minutes cross-system quiet period
KARPENTER_PROVISIONING_COOLDOWN_SECONDS = 600  # 10 minutes for Karpenter to provision


class CooldownController:
    """
    Manages all cooldown timers in Redis.

    All timers are stored as Redis keys with TTL.
    When the key exists → cooldown is active.
    When the key expires → cooldown has ended, action is allowed.
    """

    def __init__(self, redis_client):
        """
        Initialize the cooldown controller.

        Args:
            redis_client: Redis connection (from backend.core.redis_client)
        """
        self.redis = redis_client

    # -------------------------------------------------------------------------
    # STEP 1: Cluster-level cooldown
    # -------------------------------------------------------------------------

    def can_switch(self, cluster_id: str) -> Tuple[bool, int]:
        """
        Check if the cluster is allowed to do a pool switch right now.

        Called at Step 1 of the decision pipeline. If the cluster recently
        executed any action (pool switch, drain, resize), this blocks new actions
        until the cluster reaches a stable state.

        Args:
            cluster_id: Cluster identifier

        Returns:
            (can_switch, remaining_seconds)
            can_switch=True → action allowed
            can_switch=False → wait remaining_seconds before retrying
        """
        cooldown_key = f"spot:cooldown:action:cluster:{cluster_id}"
        ttl = self.redis.ttl(cooldown_key)

        if ttl > 0:
            return False, ttl  # Cooldown active
        return True, 0         # No cooldown, action allowed

    def record_pool_switch_action(self, cluster_id: str):
        """
        Start the cluster cooldown after a pool switch.

        Call this immediately after executing any pool switch action.
        The cluster will be blocked from further switches for 30 minutes.
        """
        cooldown_key = f"spot:cooldown:action:cluster:{cluster_id}"
        self.redis.setex(cooldown_key, CLUSTER_COOLDOWN_SECONDS, "1")

    # -------------------------------------------------------------------------
    # STEP 2: Pool-level cooldown
    # -------------------------------------------------------------------------

    def can_reuse_pool(self, pool_key: str) -> Tuple[bool, int]:
        """
        Check if a specific pool can be used as a migration target.

        Called at Step 2 of the pipeline for each candidate pool.
        Pools that were recently used (source or target of a switch) are
        temporarily blocked to prevent oscillation.

        Args:
            pool_key: "{instance_type}:{az}" e.g. "m5.large:us-east-1a"

        Returns:
            (can_reuse, remaining_seconds)
        """
        cooldown_key = f"spot:cooldown:pool:{pool_key}"
        ttl = self.redis.ttl(cooldown_key)

        if ttl > 0:
            return False, ttl
        return True, 0

    def record_pool_used(self, pool_key: str):
        """
        Mark a pool as recently used (start pool cooldown).

        Call this for BOTH the source and target pool after a successful switch.
        - Source pool: blocked because it just had an interruption risk
        - Target pool: blocked because we're already using it (no need to switch again)

        Args:
            pool_key: "{instance_type}:{az}" e.g. "m5.large:us-east-1a"
        """
        cooldown_key = f"spot:cooldown:pool:{pool_key}"
        self.redis.setex(cooldown_key, POOL_COOLDOWN_SECONDS, "1")

    # -------------------------------------------------------------------------
    # Resize cooldown (used by OptimizerCoordinator)
    # -------------------------------------------------------------------------

    def can_resize(self, cluster_id: str) -> Tuple[bool, int]:
        """
        Check if the cluster can run a rightsizing operation.

        Rightsizing changes the instance type, which is higher-risk than a
        pool switch (requires draining and reprovisioning the node). The 6-hour
        cooldown ensures the cluster is stable before evaluating another resize.

        Args:
            cluster_id: Cluster identifier

        Returns:
            (can_resize, remaining_seconds)
        """
        cooldown_key = f"spot:cooldown:action:resize:{cluster_id}"
        ttl = self.redis.ttl(cooldown_key)

        if ttl > 0:
            return False, ttl
        return True, 0

    def record_resize_action(self, cluster_id: str):
        """
        Start the 6-hour resize cooldown after a rightsizing operation.
        """
        cooldown_key = f"spot:cooldown:action:resize:{cluster_id}"
        self.redis.setex(cooldown_key, RESIZE_COOLDOWN_SECONDS, "1")

    # -------------------------------------------------------------------------
    # Substitute cooldown (used by SubstituteManager)
    # -------------------------------------------------------------------------

    def record_substitute_action(self, cluster_id: str):
        """
        Start the 2-hour substitute cooldown after deploying a warm spare.

        Prevents the SubstituteManager from deploying multiple overlapping
        warm spares for the same cluster.
        """
        cooldown_key = f"spot:cooldown:action:substitute:{cluster_id}"
        self.redis.setex(cooldown_key, SUBSTITUTE_COOLDOWN_SECONDS, "1")

    # -------------------------------------------------------------------------
    # Stabilization lock (cross-system, short-lived)
    # -------------------------------------------------------------------------

    def acquire_stabilization_lock(self, cluster_id: str, reason: str = ""):
        """
        Acquire a 5-minute stabilization lock after ANY cluster action.

        This is the broadest lock — it prevents ALL systems (auto-rebalancer,
        rightsizer, substitute manager) from acting on the cluster simultaneously.

        Flow:
          1. auto_rebalancer executes → acquires stabilization lock
          2. rightsizer tries to run → sees lock → defers
          3. 5 minutes later → lock expires → rightsizer can proceed

        Args:
            cluster_id: Cluster identifier
            reason:     Why the lock is being acquired (for logging)
        """
        lock_key = f"spot:stabilization_lock:{cluster_id}"
        self.redis.setex(lock_key, STABILIZATION_LOCK_SECONDS, reason or "1")

    def is_stabilization_locked(self, cluster_id: str) -> Tuple[bool, int]:
        """
        Check if the cluster's stabilization lock is active.

        Args:
            cluster_id: Cluster identifier

        Returns:
            (is_locked, remaining_seconds)
        """
        lock_key = f"spot:stabilization_lock:{cluster_id}"
        ttl = self.redis.ttl(lock_key)

        if ttl > 0:
            return True, ttl
        return False, 0

    # -------------------------------------------------------------------------
    # Status inspection (for monitoring/UI)
    # -------------------------------------------------------------------------

    def get_action_cooldown_status(self, cluster_id: str) -> dict:
        """
        Get complete cooldown status for a cluster.

        Returns:
            Dict with cooldown state for each timer type.
            Used by OptimizerCoordinator.get_cluster_status() for UI display.
        """
        cluster_ttl = self.redis.ttl(f"spot:cooldown:action:cluster:{cluster_id}")
        resize_ttl = self.redis.ttl(f"spot:cooldown:action:resize:{cluster_id}")
        substitute_ttl = self.redis.ttl(f"spot:cooldown:action:substitute:{cluster_id}")
        stab_ttl = self.redis.ttl(f"spot:stabilization_lock:{cluster_id}")

        return {
            "cluster_cooldown_active": cluster_ttl > 0,
            "cluster_cooldown_remaining_seconds": max(0, cluster_ttl),
            "resize_cooldown_active": resize_ttl > 0,
            "resize_cooldown_remaining_seconds": max(0, resize_ttl),
            "substitute_cooldown_active": substitute_ttl > 0,
            "substitute_cooldown_remaining_seconds": max(0, substitute_ttl),
            "stabilization_lock_active": stab_ttl > 0,
            "stabilization_lock_remaining_seconds": max(0, stab_ttl),
        }
