"""
Cache Builder — Build global pool rankings cache for a region.
Acquires a distributed lock, fetches pools, assigns risk tiers,
sorts within tiers, and stores up to GLOBAL_CACHE_SIZE pools in Redis.
"""
import json
import logging
from datetime import datetime, timezone

from backend.core.redis_client import (
    get_redis_client,
    key_global_pool_rankings,
    key_cache_builder_lock,
)
from backend.core.config import GLOBAL_CACHE_SIZE, GLOBAL_POOL_LOCK_TTL
from backend.services.pool_ranking_service import assign_risk_tier

logger = logging.getLogger(__name__)


def build_global_pool_cache(region: str, db=None):
    """
    Build and cache global pool rankings for a region.

    Steps:
    1. Acquire distributed lock (NX + TTL)
    2. Fetch pool data from Redis/DB
    3. Assign risk tiers
    4. Sort within tiers by price ascending
    5. Store top GLOBAL_CACHE_SIZE pools in Redis
    6. Release lock in finally block
    """
    r = get_redis_client()
    lock_key = key_cache_builder_lock(region)

    # Acquire distributed lock with NX (only set if not exists)
    acquired = r.set(lock_key, '1', nx=True, ex=GLOBAL_POOL_LOCK_TTL)
    if not acquired:
        logger.info(f"[cache_builder] Lock already held for region {region}, skipping")
        return

    try:
        # Fetch raw pool data from spot price cache in Redis
        cursor = 0
        pools = []

        while True:
            cursor, keys = r.scan(cursor, match=f"spot_price:{region}:*", count=500)
            for key in keys:
                try:
                    raw = r.get(key)
                    if not raw:
                        continue
                    data = json.loads(raw)
                    # Key format: spot_price:{region}:{az}:{instance_type}
                    parts = key.split(':')
                    if len(parts) >= 4:
                        az = parts[2]
                        instance_type = ':'.join(parts[3:])
                        price = float(data.get('price', 9999))
                        pools.append({
                            'instance_type': instance_type,
                            'az': az,
                            'region': region,
                            'spot_price': price,
                            'risk_tier': assign_risk_tier(15.0),  # Default tier until advisor data
                        })
                except Exception as parse_err:
                    logger.debug(f"[cache_builder] Parse error for key: {parse_err}")

            if cursor == 0:
                break

        if not pools:
            logger.warning(f"[cache_builder] No pools found for region {region}")
            return

        # Sort by risk tier first, then by price ascending within tier
        pools.sort(key=lambda p: (p['risk_tier'], p['spot_price']))

        # Limit to GLOBAL_CACHE_SIZE
        top_pools = pools[:GLOBAL_CACHE_SIZE]

        # Store in Redis
        cache_key = key_global_pool_rankings(region)
        payload = json.dumps({
            'data': top_pools,
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'count': len(top_pools),
            'region': region,
        })
        r.setex(cache_key, 3600, payload)

        logger.info(
            f"[cache_builder] Cached {len(top_pools)} pools for region {region}"
        )

    except Exception as e:
        logger.error(f"[cache_builder] Failed to build cache for {region}: {e}")
    finally:
        r.delete(lock_key)


try:
    from backend.workers.app import app

    @app.task(name='build_global_pool_cache', bind=False)
    def build_global_pool_cache_task(region: str = 'us-east-1', db=None):
        """Celery task wrapper for build_global_pool_cache."""
        return build_global_pool_cache(region, db)

except ImportError:
    logger.warning("[cache_builder] Celery not available, task scheduling disabled")
