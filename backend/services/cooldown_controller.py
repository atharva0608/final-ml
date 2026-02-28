"""
Cooldown Controller
==================

Anti-flapping enforcement for Decision Engine v3.
Prevents rapid oscillation between pools and clusters.
"""

from redis import Redis
from typing import Tuple
import logging

logger = logging.getLogger(__name__)


class CooldownController:
    """
    Manages cooldown enforcement to prevent flapping.

    Three types of cooldowns:
    1. Cluster-level: Prevents switching within N minutes
    2. Pool-level: Prevents reusing a failed pool within N minutes
    3. Action-specific: Different durations for different optimization actions

    Action-specific cooldowns (per problems.md):
    - POOL_SWITCH: 30 min (frequent optimization is safe)
    - RESIZE: 6 hours (size changes need long stabilization)
    - SUBSTITUTE: 2 hours (fallback from spot termination)
    """

    # Default cooldowns
    DEFAULT_CLUSTER_COOLDOWN_MIN = 60  # 1 hour
    DEFAULT_POOL_COOLDOWN_MIN = 120  # 2 hours

    # Action-specific cooldowns (for unified optimizer coordination)
    COOLDOWN_POOL_SWITCH_MIN = 30   # Pool optimization can run frequently
    COOLDOWN_RESIZE_MIN = 360        # Size changes need 6 hours stabilization
    COOLDOWN_SUBSTITUTE_MIN = 120    # Substitute fallback needs 2 hours

    def __init__(self, redis: Redis):
        self.redis = redis

    def can_switch(self, cluster_id: str, cooldown_minutes: int = None) -> Tuple[bool, int]:
        """
        Check if cluster can switch pools.

        Args:
            cluster_id: Cluster identifier
            cooldown_minutes: Override default cooldown (default 60 min)

        Returns:
            (can_switch: bool, remaining_seconds: int)
        """
        if cooldown_minutes is None:
            cooldown_minutes = self.DEFAULT_CLUSTER_COOLDOWN_MIN

        key = f"spot:cooldown:cluster:{cluster_id}"

        try:
            ttl = self.redis.ttl(key)

            if ttl > 0:
                logger.info(f"Cluster {cluster_id} cooldown active: {ttl}s remaining")
                return (False, ttl)

            return (True, 0)

        except Exception as e:
            logger.error(f"Error checking cluster cooldown: {e}")
            # Fail open on errors — don't block operations
            return (True, 0)

    def can_reuse_pool(self, pool_id: str) -> Tuple[bool, int]:
        """
        Check if pool can be reused (not in failure cooldown).

        Args:
            pool_id: Pool identifier (format: "instance_type:az")

        Returns:
            (can_reuse: bool, remaining_seconds: int)
        """
        key = f"spot:cooldown:pool:{pool_id}"

        try:
            ttl = self.redis.ttl(key)

            if ttl > 0:
                logger.info(f"Pool {pool_id} cooldown active: {ttl}s remaining")
                return (False, ttl)

            return (True, 0)

        except Exception as e:
            logger.error(f"Error checking pool cooldown: {e}")
            # Fail open on errors — don't block operations
            return (True, 0)

    def record_switch(self, cluster_id: str, cooldown_minutes: int = None):
        """
        Record a cluster switch and activate cooldown.

        Args:
            cluster_id: Cluster identifier
            cooldown_minutes: Override default cooldown (default 60 min)
        """
        if cooldown_minutes is None:
            cooldown_minutes = self.DEFAULT_CLUSTER_COOLDOWN_MIN

        key = f"spot:cooldown:cluster:{cluster_id}"

        try:
            self.redis.setex(key, cooldown_minutes * 60, "active")
            logger.info(f"Cluster {cluster_id} cooldown activated for {cooldown_minutes} min")

        except Exception as e:
            logger.error(f"Error recording cluster cooldown: {e}")

    def record_pool_failure(self, pool_id: str, cooldown_minutes: int = None):
        """
        Record a pool failure and activate cooldown.

        Args:
            pool_id: Pool identifier (format: "instance_type:az")
            cooldown_minutes: Override default cooldown (default 120 min)
        """
        if cooldown_minutes is None:
            cooldown_minutes = self.DEFAULT_POOL_COOLDOWN_MIN

        key = f"spot:cooldown:pool:{pool_id}"

        try:
            self.redis.setex(key, cooldown_minutes * 60, "failed")
            logger.info(f"Pool {pool_id} cooldown activated for {cooldown_minutes} min")

        except Exception as e:
            logger.error(f"Error recording pool cooldown: {e}")

    def override_for_emergency(self, cluster_id: str):
        """
        Override cluster cooldown for emergency situations (e.g., termination notice).

        Args:
            cluster_id: Cluster identifier
        """
        key = f"spot:cooldown:cluster:{cluster_id}"

        try:
            self.redis.delete(key)
            logger.warning(f"Cluster {cluster_id} cooldown OVERRIDDEN for emergency")

        except Exception as e:
            logger.error(f"Error overriding cluster cooldown: {e}")

    def get_cluster_cooldown_status(self, cluster_id: str) -> dict:
        """
        Get cluster cooldown status for UI display.

        Returns:
            {
                "active": bool,
                "remaining_seconds": int,
                "remaining_minutes": int
            }
        """
        can_switch, remaining_seconds = self.can_switch(cluster_id)

        return {
            "active": not can_switch,
            "remaining_seconds": remaining_seconds,
            "remaining_minutes": remaining_seconds // 60
        }

    # ========================================================================
    # ACTION-SPECIFIC COOLDOWNS (Unified Optimizer Coordination)
    # ========================================================================

    def can_resize(self, cluster_id: str) -> Tuple[bool, int]:
        """
        Check if cluster can perform a resize action (rightsizing).
        Uses 6-hour cooldown to prevent size oscillation.

        Args:
            cluster_id: Cluster identifier

        Returns:
            (can_resize: bool, remaining_seconds: int)
        """
        key = f"spot:cooldown:action:resize:{cluster_id}"

        try:
            ttl = self.redis.ttl(key)

            if ttl > 0:
                logger.info(f"Cluster {cluster_id} resize cooldown active: {ttl}s remaining")
                return (False, ttl)

            return (True, 0)

        except Exception as e:
            logger.error(f"Error checking resize cooldown: {e}")
            return (True, 0)

    def record_resize_action(self, cluster_id: str):
        """
        Record a resize action and activate 6-hour cooldown.

        Args:
            cluster_id: Cluster identifier
        """
        key = f"spot:cooldown:action:resize:{cluster_id}"

        try:
            self.redis.setex(key, self.COOLDOWN_RESIZE_MIN * 60, "resize")
            logger.info(f"Cluster {cluster_id} resize cooldown activated for {self.COOLDOWN_RESIZE_MIN} min (6 hours)")

        except Exception as e:
            logger.error(f"Error recording resize cooldown: {e}")

    def record_pool_switch_action(self, cluster_id: str):
        """
        Record a pool switch action and activate 30-minute cooldown.

        Args:
            cluster_id: Cluster identifier
        """
        key = f"spot:cooldown:action:pool_switch:{cluster_id}"

        try:
            self.redis.setex(key, self.COOLDOWN_POOL_SWITCH_MIN * 60, "pool_switch")
            logger.info(f"Cluster {cluster_id} pool switch cooldown activated for {self.COOLDOWN_POOL_SWITCH_MIN} min")

        except Exception as e:
            logger.error(f"Error recording pool switch cooldown: {e}")

    def record_substitute_action(self, cluster_id: str):
        """
        Record a substitute fallback action and activate 2-hour cooldown.

        Args:
            cluster_id: Cluster identifier
        """
        key = f"spot:cooldown:action:substitute:{cluster_id}"

        try:
            self.redis.setex(key, self.COOLDOWN_SUBSTITUTE_MIN * 60, "substitute")
            logger.info(f"Cluster {cluster_id} substitute cooldown activated for {self.COOLDOWN_SUBSTITUTE_MIN} min (2 hours)")

        except Exception as e:
            logger.error(f"Error recording substitute cooldown: {e}")

    def get_action_cooldown_status(self, cluster_id: str) -> dict:
        """
        Get comprehensive action cooldown status for UI display.

        Returns:
            {
                "resize": {"active": bool, "remaining_seconds": int, "remaining_minutes": int},
                "pool_switch": {"active": bool, "remaining_seconds": int, "remaining_minutes": int},
                "substitute": {"active": bool, "remaining_seconds": int, "remaining_minutes": int}
            }
        """
        result = {}

        for action_type, key_suffix in [
            ("resize", "resize"),
            ("pool_switch", "pool_switch"),
            ("substitute", "substitute")
        ]:
            key = f"spot:cooldown:action:{key_suffix}:{cluster_id}"

            try:
                ttl = self.redis.ttl(key)

                result[action_type] = {
                    "active": ttl > 0,
                    "remaining_seconds": ttl if ttl > 0 else 0,
                    "remaining_minutes": (ttl // 60) if ttl > 0 else 0
                }

            except Exception as e:
                logger.error(f"Error checking {action_type} cooldown: {e}")
                result[action_type] = {
                    "active": False,
                    "remaining_seconds": 0,
                    "remaining_minutes": 0
                }

        return result

    # ========================================================================
    # STABILIZATION LOCK (Task 4.1)
    # ========================================================================

    STABILIZATION_LOCK_TTL = 300  # 5 minutes

    def acquire_stabilization_lock(self, cluster_id: str, reason: str = "execution") -> bool:
        """
        Acquire a stabilization lock after any execution action.
        Prevents any optimization for 5 minutes, giving the cluster time
        to reach a new steady state.

        Returns True if lock was acquired, False if already locked.
        """
        key = f"spot:stabilization_lock:{cluster_id}"
        try:
            acquired = self.redis.set(key, reason, nx=True, ex=self.STABILIZATION_LOCK_TTL)
            if acquired:
                logger.info(f"Stabilization lock acquired for {cluster_id}: {reason}")
            else:
                logger.info(f"Stabilization lock already held for {cluster_id}")
            return bool(acquired)
        except Exception as e:
            logger.error(f"Error acquiring stabilization lock: {e}")
            return False

    def is_stabilization_locked(self, cluster_id: str) -> Tuple[bool, int]:
        """
        Check if a stabilization lock is active.

        Returns:
            (is_locked: bool, remaining_seconds: int)
        """
        key = f"spot:stabilization_lock:{cluster_id}"
        try:
            ttl = self.redis.ttl(key)
            return (ttl > 0, max(ttl, 0))
        except Exception as e:
            logger.error(f"Error checking stabilization lock: {e}")
            return (False, 0)

    def release_stabilization_lock(self, cluster_id: str):
        """Release stabilization lock early (e.g., for emergency override)."""
        key = f"spot:stabilization_lock:{cluster_id}"
        try:
            self.redis.delete(key)
            logger.info(f"Stabilization lock released for {cluster_id}")
        except Exception as e:
            logger.error(f"Error releasing stabilization lock: {e}")
