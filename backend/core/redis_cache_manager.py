"""
Phase 5: Hierarchical Redis Cache Manager with Key Versioning

Enterprise Requirements:
- Hierarchical cache keys: v2:cluster:{id}:metrics:{type}:{date}
- Cache TTL hierarchy: 5s (hot) → 60s (warm) → 600s (cold)
- Version-based invalidation (no SCAN operations)
- Atomic operations with Lua scripting
- Rate limiting with race condition prevention
- Distributed lock support

Key Design Patterns:
1. Version-based invalidation: Increment version integer to invalidate all keys
2. No SCAN operations (kills Redis performance at scale)
3. Hierarchical TTLs based on data volatility
4. Atomic operations for race condition prevention
"""
import json
import hashlib
from typing import Optional, Any, Dict, List
from datetime import datetime, timedelta
import redis
from backend.core.config import settings


class RedisCacheManager:
    """
    Enterprise-grade Redis cache manager with hierarchical key versioning.

    Features:
    - Hierarchical key namespacing with version control
    - TTL hierarchy: hot (5s) / warm (60s) / cold (600s)
    - Atomic operations with Lua scripting
    - Distributed locking with auto-expiry
    - Rate limiting with race condition prevention
    - Cache invalidation without SCAN
    """

    # =====================================================================
    # Cache Category TTLs (Enterprise Guardrail)
    # =====================================================================
    TTL_HOT = 5          # 5 seconds - Live cluster state
    TTL_WARM = 60        # 1 minute - Pricing data
    TTL_COLD = 600       # 10 minutes - Pool rankings
    TTL_FROZEN = 900     # 15 minutes - Feature vectors
    TTL_DAILY = 86400    # 24 hours - Daily aggregates

    # Lock expiry (prevent deadlock on worker crash)
    LOCK_EXPIRY = 120    # 2 minutes

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    # =====================================================================
    # Version Management (No SCAN Operations)
    # =====================================================================

    def _get_version(self, namespace: str) -> int:
        """
        Get current version for a namespace.

        Version-based invalidation pattern:
        - cluster:{id}:version = 5
        - cluster:{id}:v5:metrics:cpu = {...}
        - To invalidate, increment version to 6
        - Old keys (v5) automatically become stale
        """
        version_key = f"{namespace}:version"
        version = self.redis.get(version_key)
        if version is None:
            # Initialize version
            self.redis.set(version_key, 1)
            return 1
        return int(version)

    def _increment_version(self, namespace: str) -> int:
        """
        Increment version to invalidate all cached data in namespace.

        This is the ONLY way to invalidate cache. Never use SCAN/KEYS.
        """
        version_key = f"{namespace}:version"
        new_version = self.redis.incr(version_key)
        return new_version

    def _build_key(self, namespace: str, *parts: str) -> str:
        """
        Build versioned hierarchical cache key.

        Examples:
        - cluster:abc123:v5:metrics:cpu:2024-02-25
        - cluster:abc123:v5:ranking:spot_pools
        - pricing:v2:us-east-1:m5.large
        """
        version = self._get_version(namespace)
        key_parts = [namespace, f"v{version}"] + list(parts)
        return ":".join(key_parts)

    # =====================================================================
    # Core Cache Operations
    # =====================================================================

    def get(self, namespace: str, *key_parts: str) -> Optional[Any]:
        """
        Get cached value with automatic JSON deserialization.

        Args:
            namespace: Cache namespace (e.g., "cluster:abc123")
            key_parts: Additional key parts (e.g., "metrics", "cpu")

        Returns:
            Cached value or None if not found/expired
        """
        key = self._build_key(namespace, *key_parts)
        value = self.redis.get(key)
        if value is None:
            return None

        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            # Return raw value if not JSON
            return value

    def set(
        self,
        namespace: str,
        value: Any,
        *key_parts: str,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set cached value with automatic JSON serialization.

        Args:
            namespace: Cache namespace
            value: Value to cache (will be JSON serialized)
            key_parts: Additional key parts
            ttl: Time-to-live in seconds (default: TTL_COLD = 10 minutes)

        Returns:
            True if successful
        """
        key = self._build_key(namespace, *key_parts)
        ttl = ttl or self.TTL_COLD

        try:
            serialized = json.dumps(value)
        except TypeError:
            # Fallback to string representation
            serialized = str(value)

        return self.redis.setex(key, ttl, serialized)

    def delete(self, namespace: str, *key_parts: str) -> int:
        """Delete specific cache key."""
        key = self._build_key(namespace, *key_parts)
        return self.redis.delete(key)

    def invalidate_namespace(self, namespace: str) -> int:
        """
        Invalidate all cached data in namespace by incrementing version.

        This is the enterprise-grade way to invalidate cache:
        - No SCAN operations (O(1) operation)
        - Atomic operation
        - Old keys automatically become unreachable

        Args:
            namespace: Namespace to invalidate (e.g., "cluster:abc123")

        Returns:
            New version number
        """
        return self._increment_version(namespace)

    # =====================================================================
    # Cluster-Specific Cache Operations
    # =====================================================================

    def get_cluster_cache(
        self,
        cluster_id: str,
        cache_type: str,
        *additional_keys: str
    ) -> Optional[Any]:
        """
        Get cluster-specific cached data.

        Args:
            cluster_id: Cluster ID
            cache_type: Type of cache (e.g., "metrics", "ranking", "pricing")
            additional_keys: Additional key parts (e.g., date, metric type)

        Returns:
            Cached value or None
        """
        namespace = f"cluster:{cluster_id}"
        return self.get(namespace, cache_type, *additional_keys)

    def set_cluster_cache(
        self,
        cluster_id: str,
        cache_type: str,
        value: Any,
        *additional_keys: str,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set cluster-specific cached data with appropriate TTL.

        TTL Recommendations:
        - "state": TTL_HOT (5s) - Live cluster state
        - "pricing": TTL_WARM (60s) - AWS pricing data
        - "ranking": TTL_COLD (600s) - Pool rankings
        - "features": TTL_FROZEN (900s) - Feature vectors
        - "daily": TTL_DAILY (86400s) - Daily aggregates
        """
        namespace = f"cluster:{cluster_id}"

        # Auto-select TTL based on cache type
        if ttl is None:
            ttl_map = {
                "state": self.TTL_HOT,
                "pricing": self.TTL_WARM,
                "ranking": self.TTL_COLD,
                "features": self.TTL_FROZEN,
                "daily": self.TTL_DAILY,
            }
            ttl = ttl_map.get(cache_type, self.TTL_COLD)

        return self.set(namespace, value, cache_type, *additional_keys, ttl=ttl)

    def invalidate_cluster(self, cluster_id: str) -> int:
        """
        Invalidate all cached data for a cluster.

        Use cases:
        - After cluster configuration change
        - After spot interruption
        - After pricing refresh failure
        """
        namespace = f"cluster:{cluster_id}"
        return self.invalidate_namespace(namespace)

    # =====================================================================
    # Regional Cache Operations
    # =====================================================================

    def get_regional_cache(
        self,
        region: str,
        cache_type: str,
        *additional_keys: str
    ) -> Optional[Any]:
        """
        Get region-specific cached data.

        Use cases:
        - Regional pricing data
        - Regional instance catalog
        - Regional volatility index
        """
        namespace = f"region:{region}"
        return self.get(namespace, cache_type, *additional_keys)

    def set_regional_cache(
        self,
        region: str,
        cache_type: str,
        value: Any,
        *additional_keys: str,
        ttl: Optional[int] = None
    ) -> bool:
        """Set region-specific cached data."""
        namespace = f"region:{region}"
        return self.set(namespace, value, cache_type, *additional_keys, ttl=ttl)

    def invalidate_region(self, region: str) -> int:
        """Invalidate all cached data for a region."""
        namespace = f"region:{region}"
        return self.invalidate_namespace(namespace)

    # =====================================================================
    # Distributed Locks (Race Condition Prevention)
    # =====================================================================

    def acquire_lock(
        self,
        lock_name: str,
        lock_value: str,
        ttl: int = LOCK_EXPIRY
    ) -> bool:
        """
        Acquire distributed lock with automatic expiry.

        Enterprise Guardrail: All locks MUST expire to prevent deadlock on worker crash.

        Args:
            lock_name: Lock identifier (e.g., "substitute:cluster:abc123")
            lock_value: Unique value (e.g., task_id or UUID)
            ttl: Lock expiry in seconds (default: 120s)

        Returns:
            True if lock acquired, False if already locked
        """
        lock_key = f"lock:{lock_name}"
        # SET key value NX EX ttl (atomic operation)
        return self.redis.set(lock_key, lock_value, nx=True, ex=ttl)

    def release_lock(self, lock_name: str, lock_value: str) -> bool:
        """
        Release distributed lock only if we own it.

        Uses Lua script to ensure atomicity (check + delete).
        """
        lock_key = f"lock:{lock_name}"

        # Lua script for atomic check-and-delete
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = self.redis.eval(lua_script, 1, lock_key, lock_value)
        return bool(result)

    def is_locked(self, lock_name: str) -> bool:
        """Check if lock is currently held."""
        lock_key = f"lock:{lock_name}"
        return self.redis.exists(lock_key) > 0

    # =====================================================================
    # Atomic Rate Limiting (Race Condition Prevention)
    # =====================================================================

    def check_rate_limit(
        self,
        key: str,
        limit: int,
        window: int
    ) -> tuple[bool, int]:
        """
        Atomic rate limit check using Lua script.

        Prevents INCR/EXPIRE race condition that could allow unlimited requests.

        Args:
            key: Rate limit key (e.g., "dryrun:cluster:abc123")
            limit: Maximum requests per window
            window: Time window in seconds

        Returns:
            (allowed: bool, current_count: int)
        """
        rate_limit_key = f"ratelimit:{key}"

        # Lua script for atomic increment + expire
        lua_script = """
        local current = redis.call("incr", KEYS[1])
        if current == 1 then
            redis.call("expire", KEYS[1], ARGV[1])
        end
        return current
        """
        current = int(self.redis.eval(lua_script, 1, rate_limit_key, window))
        allowed = current <= limit

        return allowed, current

    def reset_rate_limit(self, key: str) -> bool:
        """Reset rate limit counter."""
        rate_limit_key = f"ratelimit:{key}"
        return self.redis.delete(rate_limit_key) > 0

    # =====================================================================
    # Alert Debouncing (Region-Aware)
    # =====================================================================

    def should_send_alert(
        self,
        alert_type: str,
        region: Optional[str] = None,
        debounce_seconds: int = 300
    ) -> bool:
        """
        Check if alert should be sent (with debouncing).

        Enterprise Guardrail: Debounce must be region-aware for regional events.

        Args:
            alert_type: Type of alert (e.g., "volatility", "pricing_stale", "circuit_breaker")
            region: AWS region (if region-specific alert)
            debounce_seconds: Minimum time between alerts (default: 5 minutes)

        Returns:
            True if alert should be sent, False if recently sent
        """
        key_parts = ["alert", alert_type]
        if region:
            key_parts.append(region)

        alert_key = ":".join(key_parts)
        last_sent = self.redis.get(f"alert:last_sent:{alert_key}")

        if last_sent is None:
            # First time sending this alert
            self.redis.setex(f"alert:last_sent:{alert_key}", debounce_seconds, "1")
            return True

        return False

    # =====================================================================
    # Pricing Freshness Tracking
    # =====================================================================

    def set_pricing_timestamp(self, region: str) -> None:
        """Record last pricing refresh timestamp for region."""
        key = f"pricing:last_updated:{region}"
        self.redis.set(key, datetime.utcnow().isoformat())

    def get_pricing_age(self, region: str) -> Optional[int]:
        """
        Get pricing data age in seconds.

        Returns:
            Age in seconds, or None if never updated
        """
        key = f"pricing:last_updated:{region}"
        timestamp_str = self.redis.get(key)

        if timestamp_str is None:
            return None

        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            age = (datetime.utcnow() - timestamp).total_seconds()
            return int(age)
        except (ValueError, TypeError):
            return None

    def is_pricing_stale(self, region: str, max_age_seconds: int = 900) -> bool:
        """
        Check if pricing data is stale (Enterprise Guardrail).

        Default max age: 15 minutes (900 seconds)
        """
        age = self.get_pricing_age(region)
        if age is None:
            return True  # Never updated = stale
        return age > max_age_seconds

    # =====================================================================
    # Cache Statistics
    # =====================================================================

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache hit/miss rates, memory usage, etc.
        """
        info = self.redis.info()
        stats = self.redis.info("stats")

        return {
            "used_memory_human": info.get("used_memory_human", "N/A"),
            "used_memory_peak_human": info.get("used_memory_peak_human", "N/A"),
            "keyspace_hits": stats.get("keyspace_hits", 0),
            "keyspace_misses": stats.get("keyspace_misses", 0),
            "hit_rate_pct": self._calculate_hit_rate(stats),
            "total_keys": self._count_keys(),
        }

    def _calculate_hit_rate(self, stats: Dict) -> float:
        """Calculate cache hit rate percentage."""
        hits = stats.get("keyspace_hits", 0)
        misses = stats.get("keyspace_misses", 0)
        total = hits + misses

        if total == 0:
            return 0.0

        return round((hits / total) * 100, 2)

    def _count_keys(self) -> int:
        """Count total keys (use DBSIZE, not KEYS)."""
        return self.redis.dbsize()

    # =====================================================================
    # Bulk Operations
    # =====================================================================

    def mget_cluster_caches(
        self,
        cluster_id: str,
        cache_type: str,
        keys: List[str]
    ) -> Dict[str, Any]:
        """
        Get multiple cache values in single round-trip.

        Args:
            cluster_id: Cluster ID
            cache_type: Cache type
            keys: List of cache keys

        Returns:
            Dictionary of key -> value
        """
        namespace = f"cluster:{cluster_id}"
        version = self._get_version(namespace)

        # Build all keys
        cache_keys = [
            f"{namespace}:v{version}:{cache_type}:{key}"
            for key in keys
        ]

        # Single MGET operation
        values = self.redis.mget(cache_keys)

        # Parse JSON values
        result = {}
        for key, value in zip(keys, values):
            if value is None:
                result[key] = None
            else:
                try:
                    result[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[key] = value

        return result

    def mset_cluster_caches(
        self,
        cluster_id: str,
        cache_type: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set multiple cache values with single pipeline.

        Args:
            cluster_id: Cluster ID
            cache_type: Cache type
            data: Dictionary of key -> value
            ttl: TTL for all keys

        Returns:
            True if successful
        """
        namespace = f"cluster:{cluster_id}"
        version = self._get_version(namespace)

        # Use pipeline for atomic batch operation
        pipe = self.redis.pipeline()

        for key, value in data.items():
            cache_key = f"{namespace}:v{version}:{cache_type}:{key}"
            serialized = json.dumps(value)

            if ttl:
                pipe.setex(cache_key, ttl, serialized)
            else:
                pipe.set(cache_key, serialized)

        pipe.execute()
        return True


# =====================================================================
# Factory Function
# =====================================================================

def get_cache_manager(redis_client: redis.Redis) -> RedisCacheManager:
    """
    Factory function to create RedisCacheManager instance.

    Usage:
        from backend.core.redis_client import get_redis_client
        from backend.core.redis_cache_manager import get_cache_manager

        redis = get_redis_client()
        cache = get_cache_manager(redis)

        # Set cluster cache
        cache.set_cluster_cache("abc123", "ranking", pool_data, ttl=600)

        # Get cluster cache
        data = cache.get_cluster_cache("abc123", "ranking")

        # Invalidate cluster cache
        cache.invalidate_cluster("abc123")
    """
    return RedisCacheManager(redis_client)
