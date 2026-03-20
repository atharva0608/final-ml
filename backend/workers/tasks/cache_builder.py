"""
Cache Builder — Build global pool rankings cache for a region.
Acquires a distributed lock, fetches pools from Redis spot_price keys,
enriches each pool with OD price, spot advisor rate, vcpu/memory/arch,
filters negative-savings pools, assigns accurate risk tiers,
sorts within tiers, and stores up to GLOBAL_CACHE_SIZE pools in Redis.

Changes (Task 1.4):
  - Pool dicts now include: vcpu, memory_gb, architecture, ondemand_price, savings_pct
  - risk_tier assigned from actual spot advisor interruption rate (not default 15%)
  - Pools where savings_pct <= 0 are filtered out
  - Detailed summary log shows raw/filtered/final counts per reason
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

# Minimal fallback specs for common types (used when DB catalog is empty)
# Format: instance_type → (vcpu, memory_gb, architecture)
_FALLBACK_SPECS = {
    "t3.nano":     (2,  0.5,  "amd64"), "t3.micro":    (2,  1,    "amd64"),
    "t3.small":    (2,  2,    "amd64"), "t3.medium":   (2,  4,    "amd64"),
    "t3.large":    (2,  8,    "amd64"), "t3.xlarge":   (4,  16,   "amd64"),
    "t3.2xlarge":  (8,  32,   "amd64"),
    "t3a.nano":    (2,  0.5,  "amd64"), "t3a.micro":   (2,  1,    "amd64"),
    "t3a.small":   (2,  2,    "amd64"), "t3a.medium":  (2,  4,    "amd64"),
    "t3a.large":   (2,  8,    "amd64"), "t3a.xlarge":  (4,  16,   "amd64"),
    "t3a.2xlarge": (8,  32,   "amd64"),
    "t4g.nano":    (2,  0.5,  "arm64"), "t4g.micro":   (2,  1,    "arm64"),
    "t4g.small":   (2,  2,    "arm64"), "t4g.medium":  (2,  4,    "arm64"),
    "t4g.large":   (2,  8,    "arm64"), "t4g.xlarge":  (4,  16,   "arm64"),
    "t4g.2xlarge": (8,  32,   "arm64"),
    "m5.large":    (2,  8,    "amd64"), "m5.xlarge":   (4,  16,   "amd64"),
    "m5.2xlarge":  (8,  32,   "amd64"), "m5.4xlarge":  (16, 64,   "amd64"),
    "m5.8xlarge":  (32, 128,  "amd64"),
    "m6i.large":   (2,  8,    "amd64"), "m6i.xlarge":  (4,  16,   "amd64"),
    "m6i.2xlarge": (8,  32,   "amd64"), "m6i.4xlarge": (16, 64,   "amd64"),
    "m6a.large":   (2,  8,    "amd64"), "m6a.xlarge":  (4,  16,   "amd64"),
    "m6a.2xlarge": (8,  32,   "amd64"),
    "m6g.medium":  (1,  4,    "arm64"), "m6g.large":   (2,  8,    "arm64"),
    "m6g.xlarge":  (4,  16,   "arm64"), "m6g.2xlarge": (8,  32,   "arm64"),
    "m6g.4xlarge": (16, 64,   "arm64"),
    "m7i.large":   (2,  8,    "amd64"), "m7i.xlarge":  (4,  16,   "amd64"),
    "m7i.2xlarge": (8,  32,   "amd64"), "m7i.4xlarge": (16, 64,   "amd64"),
    "m7g.large":   (2,  8,    "arm64"), "m7g.xlarge":  (4,  16,   "arm64"),
    "m7g.2xlarge": (8,  32,   "arm64"), "m7g.4xlarge": (16, 64,   "arm64"),
    "c5.large":    (2,  4,    "amd64"), "c5.xlarge":   (4,  8,    "amd64"),
    "c5.2xlarge":  (8,  16,   "amd64"), "c5.4xlarge":  (16, 32,   "amd64"),
    "c6i.large":   (2,  4,    "amd64"), "c6i.xlarge":  (4,  8,    "amd64"),
    "c6i.2xlarge": (8,  16,   "amd64"), "c6i.4xlarge": (16, 32,   "amd64"),
    "c6a.large":   (2,  4,    "amd64"), "c6a.xlarge":  (4,  8,    "amd64"),
    "c6a.2xlarge": (8,  16,   "amd64"),
    "c6g.medium":  (1,  2,    "arm64"), "c6g.large":   (2,  4,    "arm64"),
    "c6g.xlarge":  (4,  8,    "arm64"), "c6g.2xlarge": (8,  16,   "arm64"),
    "c6g.4xlarge": (16, 32,   "arm64"),
    "c7i.large":   (2,  4,    "amd64"), "c7i.xlarge":  (4,  8,    "amd64"),
    "c7i.2xlarge": (8,  16,   "amd64"),
    "c7g.large":   (2,  4,    "arm64"), "c7g.xlarge":  (4,  8,    "arm64"),
    "c7g.2xlarge": (8,  16,   "arm64"),
    "r5.large":    (2,  16,   "amd64"), "r5.xlarge":   (4,  32,   "amd64"),
    "r5.2xlarge":  (8,  64,   "amd64"), "r5.4xlarge":  (16, 128,  "amd64"),
    "r6i.large":   (2,  16,   "amd64"), "r6i.xlarge":  (4,  32,   "amd64"),
    "r6i.2xlarge": (8,  64,   "amd64"),
    "r6g.medium":  (1,  8,    "arm64"), "r6g.large":   (2,  16,   "arm64"),
    "r6g.xlarge":  (4,  32,   "arm64"), "r6g.2xlarge": (8,  64,   "arm64"),
    "r7i.large":   (2,  16,   "amd64"), "r7i.xlarge":  (4,  32,   "amd64"),
    "r7g.large":   (2,  16,   "arm64"), "r7g.xlarge":  (4,  32,   "arm64"),
    "i3.large":    (2,  15.25,"amd64"), "i3.xlarge":   (4,  30.5, "amd64"),
    "i3.2xlarge":  (8,  61,   "amd64"),
    "i4i.large":   (2,  16,   "amd64"), "i4i.xlarge":  (4,  32,   "amd64"),
}


def _lookup_od_price(r, region: str, instance_type: str) -> float:
    """Get OD price from Redis. Returns 0.0 if not found."""
    try:
        raw = r.get(f"ondemand_price:{region}:{instance_type}")
        if raw:
            return float(raw)
    except Exception:
        pass
    return 0.0


def _lookup_interruption_rate(r, region: str, instance_type: str) -> float:
    """Get spot advisor interruption rate pct from Redis. Returns 25.0 (worst-case) if not found."""
    try:
        raw = r.get(f"spot_advisor:{region}:{instance_type}:Linux")
        if raw:
            data = json.loads(raw)
            idx = data.get("interruption_index", 4)
            _idx_to_pct = {0: 5.0, 1: 10.0, 2: 15.0, 3: 20.0, 4: 25.0}
            return _idx_to_pct.get(int(idx), 25.0)
    except Exception:
        pass
    return 25.0  # worst-case default if not found


def _lookup_specs(instance_type: str) -> tuple:
    """Return (vcpu, memory_gb, architecture) for an instance type."""
    return _FALLBACK_SPECS.get(instance_type, (0, 0.0, "amd64"))


def build_global_pool_cache(region: str, db=None):
    """
    Build and cache global pool rankings for a region.

    Steps:
    1. Acquire distributed lock (NX + TTL)
    2. Scan Redis for spot_price:{region}:* keys
    3. Enrich each pool with OD price, interruption rate, vcpu/memory/arch
    4. Assign actual risk tier from spot advisor rate
    5. Filter: skip pools where savings_pct <= 0
    6. Sort within tiers by price ascending
    7. Store top GLOBAL_CACHE_SIZE pools in Redis
    8. Log detailed summary (raw / no_od_price / negative_savings / final)
    9. Release lock in finally block
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
        raw_pools = []

        while True:
            cursor, keys = r.scan(cursor, match=f"spot_price:{region}:*", count=500)
            for key in keys:
                try:
                    raw = r.get(key)
                    if not raw:
                        continue
                    data = json.loads(raw)
                    # Key format: spot_price:{region}:{az}:{instance_type}
                    # Keys may be bytes
                    key_str = key.decode() if isinstance(key, bytes) else key
                    parts = key_str.split(':')
                    if len(parts) >= 4:
                        az = parts[2]
                        instance_type = ':'.join(parts[3:])
                        spot_price = float(data.get('price', 0) or 0)
                        if spot_price <= 0:
                            continue
                        raw_pools.append({
                            'instance_type': instance_type,
                            'az': az,
                            'region': region,
                            'spot_price': spot_price,
                        })
                except Exception as parse_err:
                    logger.debug(f"[cache_builder] Parse error for key: {parse_err}")

            if cursor == 0:
                break

        raw_count = len(raw_pools)

        if not raw_pools:
            logger.warning(f"[cache_builder] No spot_price keys found for region {region}")
            return

        # Enrich each pool and apply filters
        pools = []
        no_od_price = 0
        negative_savings = 0
        no_specs = 0

        for p in raw_pools:
            itype = p['instance_type']

            # OD price lookup
            od_price = _lookup_od_price(r, region, itype)
            if od_price <= 0:
                no_od_price += 1
                continue

            # Savings filter
            savings_pct = (od_price - p['spot_price']) / od_price * 100
            if savings_pct <= 0:
                negative_savings += 1
                continue

            # Instance specs
            vcpu, memory_gb, arch = _lookup_specs(itype)
            if vcpu == 0:
                # Unknown type — still include but flag it
                no_specs += 1
                vcpu, memory_gb, arch = 1, 1.0, "amd64"  # minimal defaults

            # Actual risk tier from spot advisor
            interruption_rate = _lookup_interruption_rate(r, region, itype)
            risk_tier = assign_risk_tier(interruption_rate)

            pools.append({
                'instance_type': itype,
                'az': p['az'],
                'region': region,
                'spot_price': p['spot_price'],
                'ondemand_price': od_price,
                'savings_pct': round(savings_pct, 1),
                'interruption_rate_pct': interruption_rate,
                'risk_tier': risk_tier,
                'vcpu': vcpu,
                'memory_gb': memory_gb,
                'architecture': arch,
            })

        if not pools:
            logger.warning(
                f"[cache_builder] All pools filtered out for region {region} "
                f"(raw={raw_count}, no_od_price={no_od_price}, negative_savings={negative_savings})"
            )
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
            f"[cache_builder] Built pool cache for {region}: "
            f"raw_spot_keys={raw_count}, no_od_price={no_od_price}, "
            f"negative_savings={negative_savings}, no_specs={no_specs}, "
            f"final_pool_count={len(top_pools)}"
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
