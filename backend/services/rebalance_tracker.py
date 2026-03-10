"""
Rebalance Tracker — Track rebalance events and blacklist pools with tiered TTLs.
"""
import time
import logging
from backend.core.redis_client import get_redis_client, key_rebalance_events, key_blacklist_global
from backend.core.config import REBALANCE_THRESHOLD, REBALANCE_BLACKLIST_TIER_HOURS

logger = logging.getLogger(__name__)


def track_rebalance_event(region: str, instance_type: str, az: str) -> dict:
    """
    Track a rebalance event for a pool. If events exceed REBALANCE_THRESHOLD
    in the last hour, blacklist the pool with tiered TTL.

    Args:
        region: AWS region
        instance_type: EC2 instance type
        az: Availability zone

    Returns:
        Dict with status: 'tracked' or 'blacklisted'
    """
    redis = get_redis_client()
    key = key_rebalance_events(region, instance_type, az)
    now = time.time()

    redis.zadd(key, {str(now): now})
    redis.expire(key, 86400)

    # Count events in last hour
    one_hour_ago = now - 3600
    count = redis.zcount(key, one_hour_ago, '+inf')

    pool_key = f'{instance_type}:{az}'

    if count >= REBALANCE_THRESHOLD:
        # Determine tier based on how many times we've breached
        breach_key = f'rebalance:breaches:{region}:{instance_type}:{az}'
        breaches = redis.incr(breach_key)
        redis.expire(breach_key, 86400)

        hours = REBALANCE_BLACKLIST_TIER_HOURS
        ttl_hours = hours[0] if breaches == 1 else (hours[1] if breaches == 2 else hours[2])
        redis.setex(key_blacklist_global(pool_key), ttl_hours * 3600, '1')

        logger.warning(
            f'[rebalance_tracker] Pool {pool_key} blacklisted for {ttl_hours}h '
            f'(breach #{breaches}, count={count})'
        )
        return {'status': 'blacklisted', 'pool_key': pool_key, 'hours': ttl_hours}

    return {'status': 'tracked', 'count': count}


def get_rebalance_event_count(region: str, instance_type: str, az: str,
                               window_seconds: int = 3600) -> int:
    """Get count of rebalance events for a pool within a time window."""
    redis = get_redis_client()
    key = key_rebalance_events(region, instance_type, az)
    now = time.time()
    return redis.zcount(key, now - window_seconds, '+inf')
