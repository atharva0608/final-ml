import os
import json
from datetime import datetime, timezone
import redis
from backend.core.config import settings

def get_redis_client():
    """
    Get a Redis client connection
    """
    return redis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True
    )


def get_redis():
    """
    FastAPI Depends-compatible Redis dependency.
    Yields a Redis client connection.
    """
    client = get_redis_client()
    try:
        yield client
    finally:
        client.close()


# ── Redis Key Helpers ──────────────────────────────────────────────────────

def get_backend_public_url() -> str:
    """Return the live backend public URL (set by middleware on every request).
    Falls back to BACKEND_PUBLIC_URL env var, then localhost."""
    try:
        r = get_redis_client()
        url = r.get("platform:backend_public_url")
        if url:
            return url
    except Exception:
        pass
    return os.getenv("BACKEND_PUBLIC_URL", "https://localhost:8000")

def key_global_pool_rankings(region: str) -> str: return f"global_pool_rankings:{region}"
def key_market_view_cache(region: str) -> str: return f"market_view_cache:{region}"
def key_cluster_pools(cluster_id: str) -> str: return f"cluster_pools:{cluster_id}"
def key_cluster_cooldown(cluster_id: str) -> str: return f"spot:cooldown:cluster:{cluster_id}"
def key_node_failure_cooldown(cluster_id: str, node_name: str) -> str: return f"spot:rebalance_failure:{cluster_id}:{node_name}"
def key_blacklist_global(pool_key: str) -> str: return f"blacklist:global:{pool_key}"
def key_risky_pools(region: str) -> str: return f"risky_pools:{region}"
def key_az_pressure(region: str, az: str) -> str: return f"az_pressure:{region}:{az}"
def key_family_usage(cluster_id: str) -> str: return f"cluster_family_usage:{cluster_id}"
def key_pool_launch_failures(pool_key: str) -> str: return f"pool_launch_failures:{pool_key}"
def key_pool_launch_attempts(pool_key: str) -> str: return f"pool_launch_attempts:{pool_key}"
def key_region_market_health(region: str) -> str: return f"region_market_health:{region}"
def key_degraded_region(region: str) -> str: return f"degraded:region:{region}"
def key_cache_builder_lock(region: str) -> str: return f"cache_builder:market_view_cache:{region}"
def key_rebalance_lock(cluster_id: str) -> str: return f"rebalance:lock:{cluster_id}"
def key_emergency_seen(instance_id: str) -> str: return f"emergency:seen:{instance_id}"
def key_emergency_in_progress(cluster_id: str) -> str: return f"cluster:{cluster_id}:emergency_in_progress"
def key_substitute_launching(cluster_id: str) -> str: return f"cluster:{cluster_id}:substitute_launching"
def key_cluster_floor(cluster_id: str) -> str: return f"cluster:{cluster_id}:min_floor"
def key_credential_cache(account_id: str) -> str: return f"credential_cache:{account_id}"
def key_rebalance_events(region: str, instance_type: str, az: str) -> str: return f"rebalance:events:{region}:{instance_type}:{az}"


def read_cached_data(redis_key: str, staleness_threshold_secs: int = 1800) -> dict:
    _r = get_redis_client()
    raw = _r.get(redis_key)
    if not raw:
        return {"data": None, "low_confidence": True}
    payload = json.loads(raw)
    last_updated = payload.get("last_updated")
    low_confidence = False
    if last_updated:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(last_updated)).total_seconds()
        if age > staleness_threshold_secs:
            low_confidence = True
    return {"data": payload.get("data"), "low_confidence": low_confidence}

