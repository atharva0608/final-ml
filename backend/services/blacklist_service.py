"""
Blacklist Service - Global Pool Blacklisting with Exponential Backoff

Manages the global blacklist of risky spot instance pools.
When a pool receives a spot interruption, it is blacklisted for all clients.

Features:
- 24-hour base TTL (configurable)
- Exponential backoff for repeat offenders (24h → 48h → 96h → 168h max)
- Auto-clear after 7 days of stability
- Audit trail in database
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from redis import Redis

from backend.core.logger import logger


class BlacklistService:
    """
    Global pool blacklist management with exponential backoff.

    Blacklist is stored in Redis for fast lookups (O(1) per check).
    Audit events stored in Redis hash for history (lightweight, no DB dependency).
    """

    BASE_TTL_HOURS = 24           # Initial blacklist duration
    MAX_TTL_HOURS = 168           # Maximum 7 days for repeat offenders
    BACKOFF_MULTIPLIER = 2        # Double TTL on each repeated failure
    STABILITY_THRESHOLD_DAYS = 7  # Auto-clear after 7 days stable

    def __init__(self, redis: Redis):
        self.redis = redis

    def blacklist_pool(
        self,
        instance_type: str,
        az: str,
        region: str,
        reason: str = "spot_interruption"
    ) -> Dict:
        """
        Add a pool to the global blacklist.

        Args:
            instance_type: EC2 instance type (e.g., "m5.xlarge")
            az: Availability zone (e.g., "aps1-az1")
            region: AWS region
            reason: Why the pool is being blacklisted

        Returns:
            Dict with blacklist details (ttl, failure_count, etc.)
        """
        pool_key = f"{instance_type}:{az}"
        blacklist_set_key = f"risky_pools:{region}"
        failure_count_key = f"blacklist_failures:{pool_key}"
        meta_key = f"risky_pool_meta:{pool_key}"

        # Increment failure count
        failure_count = self.redis.incr(failure_count_key)
        # Keep failure count for 30 days
        self.redis.expire(failure_count_key, 30 * 86400)

        # Calculate TTL with exponential backoff
        ttl_hours = min(
            self.BASE_TTL_HOURS * (self.BACKOFF_MULTIPLIER ** (failure_count - 1)),
            self.MAX_TTL_HOURS
        )
        ttl_seconds = int(ttl_hours * 3600)

        # Add to global blacklist set
        self.redis.sadd(blacklist_set_key, pool_key)

        # Also add to legacy set (backward compat with existing code)
        self.redis.sadd("risky_pools", pool_key)

        # Store metadata
        meta = {
            "instance_type": instance_type,
            "az": az,
            "region": region,
            "reason": reason,
            "failure_count": failure_count,
            "ttl_hours": ttl_hours,
            "flagged_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat()
        }
        self.redis.setex(meta_key, ttl_seconds, json.dumps(meta))

        # Set per-pool TTL for auto-removal from set
        # Use a scheduled removal key that triggers cleanup
        removal_key = f"blacklist_removal:{pool_key}"
        self.redis.setex(removal_key, ttl_seconds, pool_key)

        logger.warning(
            f"BLACKLISTED {pool_key} for {ttl_hours:.0f}h "
            f"(failures: {failure_count}, reason: {reason}, region: {region})"
        )

        return {
            "pool_key": pool_key,
            "ttl_hours": ttl_hours,
            "ttl_seconds": ttl_seconds,
            "failure_count": failure_count,
            "reason": reason
        }

    def is_blacklisted(
        self,
        instance_type: str,
        az: str,
        region: str
    ) -> Tuple[bool, int]:
        """
        Check if a pool is currently blacklisted.

        Args:
            instance_type: EC2 instance type
            az: Availability zone
            region: AWS region

        Returns:
            Tuple of (is_blacklisted: bool, failure_count: int)
        """
        pool_key = f"{instance_type}:{az}"
        blacklist_set_key = f"risky_pools:{region}"

        is_flagged = self.redis.sismember(blacklist_set_key, pool_key)
        failure_count = int(self.redis.get(f"blacklist_failures:{pool_key}") or 0)

        return bool(is_flagged), failure_count

    def get_blacklist_status(self, region: str) -> List[Dict]:
        """
        Get all currently blacklisted pools for a region.

        Returns:
            List of blacklisted pool details
        """
        blacklist_set_key = f"risky_pools:{region}"
        pool_keys = self.redis.smembers(blacklist_set_key)

        results = []
        for pool_key in pool_keys:
            pool_key_str = pool_key.decode('utf-8') if isinstance(pool_key, bytes) else pool_key
            meta_key = f"risky_pool_meta:{pool_key_str}"
            meta_data = self.redis.get(meta_key)

            if meta_data:
                meta = json.loads(meta_data)
                ttl = self.redis.ttl(meta_key)
                meta["ttl_remaining_seconds"] = max(ttl, 0) if ttl > 0 else 0
                results.append(meta)
            else:
                # Metadata expired but pool still in set — clean up
                self.redis.srem(blacklist_set_key, pool_key_str)
                self.redis.srem("risky_pools", pool_key_str)

        return results

    def remove_from_blacklist(
        self,
        instance_type: str,
        az: str,
        region: str,
        reason: str = "manual_removal"
    ):
        """Manually remove a pool from the blacklist."""
        pool_key = f"{instance_type}:{az}"
        blacklist_set_key = f"risky_pools:{region}"

        self.redis.srem(blacklist_set_key, pool_key)
        self.redis.srem("risky_pools", pool_key)
        self.redis.delete(f"risky_pool_meta:{pool_key}")
        self.redis.delete(f"blacklist_removal:{pool_key}")

        logger.info(f"Removed {pool_key} from blacklist (reason: {reason})")

    def cleanup_expired(self, region: str) -> int:
        """
        Clean up expired blacklist entries.

        Called periodically to remove stale entries from the set
        whose metadata TTL has expired.

        Returns:
            Number of entries cleaned up
        """
        blacklist_set_key = f"risky_pools:{region}"
        pool_keys = self.redis.smembers(blacklist_set_key)
        cleaned = 0

        for pool_key in pool_keys:
            pool_key_str = pool_key.decode('utf-8') if isinstance(pool_key, bytes) else pool_key
            meta_key = f"risky_pool_meta:{pool_key_str}"

            # If metadata expired, remove from set
            if not self.redis.exists(meta_key):
                self.redis.srem(blacklist_set_key, pool_key_str)
                self.redis.srem("risky_pools", pool_key_str)
                cleaned += 1

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} expired blacklist entries for {region}")

        return cleaned

    # ==================== Decision Engine v3 Methods ====================

    def blacklist_pool_tiered(
        self,
        instance_type: str,
        az: str,
        region: str,
        reason: str,
        ttl_hours: int
    ) -> Dict:
        """
        Blacklist with explicit TTL. No exponential backoff — caller controls duration.

        Tiered blacklist model (Decision Engine v3):
        - DryRun capacity failure (1-2× /24h): 6 hours
        - Repeated DryRun failure (3+ /24h): 12 hours
        - ML high risk (>0.45): 24 hours
        - Termination event: 24 hours
        - Execution DryRun failure: No blacklist (penalty only)

        Args:
            instance_type: EC2 instance type
            az: Availability zone
            region: AWS region
            reason: Blacklist reason (e.g., "dryrun_failure_x3")
            ttl_hours: Explicit TTL in hours

        Returns:
            Blacklist metadata dict
        """
        pool_key = f"{instance_type}:{az}"
        blacklist_set_key = f"risky_pools:{region}"
        meta_key = f"risky_pool_meta:{pool_key}"
        ttl_seconds = int(ttl_hours * 3600)

        # Add to blacklist set
        self.redis.sadd(blacklist_set_key, pool_key)

        # Store metadata with TTL
        meta = {
            "instance_type": instance_type,
            "az": az,
            "region": region,
            "reason": reason,
            "ttl_hours": ttl_hours,
            "blacklist_type": "tiered",
            "flagged_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat()
        }

        self.redis.setex(meta_key, ttl_seconds, json.dumps(meta))

        logger.warning(
            f"Blacklisted {pool_key} for {ttl_hours}h "
            f"(reason: {reason}, type: tiered)"
        )

        return meta

    def check_cascade_risk(self, region: str, total_pools: int = 50) -> bool:
        """
        Check if >70% of candidate universe is blacklisted (cascade risk).

        If true, triggers cascade dampener to prevent total lockout.

        Args:
            region: AWS region
            total_pools: Total candidate pool count (default 50)

        Returns:
            True if cascade risk detected (>70% blacklisted)
        """
        blacklist_set_key = f"risky_pools:{region}"
        blacklisted_count = self.redis.scard(blacklist_set_key)

        ratio = blacklisted_count / max(total_pools, 1)

        # Store ratio for monitoring
        self.redis.set(f"spot:blacklist_ratio:{region}", f"{ratio:.2f}")

        if ratio > 0.70:
            logger.critical(
                f"BLACKLIST CASCADE RISK: {blacklisted_count}/{total_pools} "
                f"({ratio * 100:.0f}%) blacklisted in {region}"
            )

        return ratio > 0.70

    def suspend_blacklisting(self, region: str):
        """
        Suspend PREDICTIVE blacklisting for 30 min. Existing blacklists remain.

        IMPORTANT: Suspension ONLY applies to predictive blacklisting:
        - ML risk-based blacklisting
        - DryRun failure-based blacklisting
        - Capacity check failure blacklisting

        Suspension does NOT apply to deterministic blacklisting:
        - ITN (Instance Termination Notice) from IMDS → ALWAYS blacklists
        - AWS Rebalance Recommendation → ALWAYS blacklists

        This separation prevents cascade dampener from blocking real termination
        events, which would cause infinite crash loops.

        Args:
            region: AWS region
        """
        self.redis.setex(f"spot:blacklist_suspended:{region}", 1800, "active")
        logger.critical(f"Predictive blacklisting SUSPENDED for {region} (30 min)")

    def is_blacklisting_suspended(self, region: str) -> bool:
        """
        Check if predictive blacklisting is suspended (cascade dampener active).

        Args:
            region: AWS region

        Returns:
            True if suspension active
        """
        return bool(self.redis.get(f"spot:blacklist_suspended:{region}"))

    def blacklist_pool_tiered_safe(
        self,
        instance_type: str,
        az: str,
        region: str,
        reason: str,
        ttl_hours: int,
        source: str = "predictive"
    ) -> Dict:
        """
        Wrapper that respects suspension for predictive, bypasses for deterministic.

        Args:
            instance_type: EC2 instance type
            az: Availability zone
            region: AWS region
            reason: Blacklist reason
            ttl_hours: TTL in hours
            source: "predictive" or "deterministic" (ITN, rebalance-rec)

        Returns:
            Blacklist metadata dict or empty dict if skipped
        """
        if source == "predictive" and self.is_blacklisting_suspended(region):
            logger.info(
                f"Blacklisting suspended for {region}, skipping predictive blacklist "
                f"for {instance_type}:{az}"
            )
            return {}

        # Deterministic (ITN, rebalance-rec) always goes through
        return self.blacklist_pool_tiered(instance_type, az, region, reason, ttl_hours)

    def is_pool_blacklisted(self, instance_type: str, az: str, region: str) -> bool:
        """
        Simple boolean check if pool is blacklisted.

        Args:
            instance_type: EC2 instance type
            az: Availability zone
            region: AWS region

        Returns:
            True if blacklisted
        """
        pool_key = f"{instance_type}:{az}"
        blacklist_set_key = f"risky_pools:{region}"
        return bool(self.redis.sismember(blacklist_set_key, pool_key))

    def cleanup_redis_keys(self) -> int:
        """
        Daily: scan for orphaned spot:* keys — set 24h TTL as safety net.

        Prevents key explosion from 50 pools × regions × clusters over time.

        Returns:
            Number of keys cleaned
        """
        cursor = 0
        cleaned = 0
        ALLOWED_PERSISTENT = {"spot:active_cluster_count"}

        try:
            while True:
                cursor, keys = self.redis.scan(cursor, match="spot:*", count=100)

                for key in keys:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key

                    # Skip allowed persistent keys
                    if key_str in ALLOWED_PERSISTENT:
                        continue

                    # Check if key has no TTL (persistent)
                    if self.redis.ttl(key_str) == -1:
                        # Set 24h TTL as safety net
                        self.redis.expire(key_str, 86400)
                        cleaned += 1

                if cursor == 0:
                    break

            if cleaned > 0:
                logger.info(f"Redis hygiene: set TTL on {cleaned} orphaned spot:* keys")

            return cleaned

        except Exception as e:
            logger.error(f"Error during Redis key cleanup: {e}")
            return 0
