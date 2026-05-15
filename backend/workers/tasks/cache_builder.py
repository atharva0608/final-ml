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
    key_market_view_cache,
    key_cache_builder_lock,
)
from backend.core.config import GLOBAL_CACHE_SIZE, GLOBAL_POOL_LOCK_TTL
from backend.services.pool_ranking_service import assign_risk_tier

logger = logging.getLogger(__name__)

# Per-region AZ list — used when building pools from spot_advisor data
_REGION_AZS = {
    'ap-south-1':    ['ap-south-1a', 'ap-south-1b', 'ap-south-1c'],
    'us-east-1':     ['us-east-1a', 'us-east-1b', 'us-east-1c', 'us-east-1d'],
    'us-east-2':     ['us-east-2a', 'us-east-2b', 'us-east-2c'],
    'us-west-1':     ['us-west-1a', 'us-west-1b'],
    'us-west-2':     ['us-west-2a', 'us-west-2b', 'us-west-2c'],
    'eu-west-1':     ['eu-west-1a', 'eu-west-1b', 'eu-west-1c'],
    'eu-west-2':     ['eu-west-2a', 'eu-west-2b', 'eu-west-2c'],
    'eu-central-1':  ['eu-central-1a', 'eu-central-1b', 'eu-central-1c'],
    'ap-southeast-1':['ap-southeast-1a', 'ap-southeast-1b', 'ap-southeast-1c'],
    'ap-southeast-2':['ap-southeast-2a', 'ap-southeast-2b', 'ap-southeast-2c'],
    'ap-northeast-1':['ap-northeast-1a', 'ap-northeast-1b', 'ap-northeast-1c'],
}

# Family base OD prices ($/hr for .large, us-east-1 reference) — last-resort fallback
# Real OD prices are fetched from AWS Pricing API via refresh_ondemand task
_FAMILY_BASE_OD = {
    't2': 0.023, 't3': 0.0832, 't3a': 0.0752, 't4g': 0.0672,
    'm5': 0.096, 'm5a': 0.086, 'm6i': 0.096, 'm6a': 0.086, 'm6g': 0.077,
    'm7i': 0.1008, 'm7g': 0.0816,
    'c5': 0.085, 'c5a': 0.077, 'c6i': 0.085, 'c6a': 0.077, 'c6g': 0.068,
    'c7i': 0.089, 'c7g': 0.0725,
    'r5': 0.126, 'r5a': 0.113, 'r6i': 0.126, 'r6a': 0.113, 'r6g': 0.101,
    'r7i': 0.1323, 'r7g': 0.1071,
    'i3': 0.156, 'i4i': 0.182,
}
_SIZE_MULT = {
    'nano': 0.25, 'micro': 0.5, 'small': 1.0, 'medium': 2.0, 'large': 4.0,
    'xlarge': 8.0, '2xlarge': 16.0, '4xlarge': 32.0, '8xlarge': 64.0,
    '12xlarge': 96.0, '16xlarge': 128.0, '24xlarge': 192.0, '32xlarge': 256.0,
}


def _estimate_od_price(instance_type: str) -> float:
    """Estimate OD price from family/size tables."""
    parts = instance_type.split('.')
    if len(parts) != 2:
        return 0.10
    family, size = parts
    base = _FAMILY_BASE_OD.get(family, 0.10)
    mult = _SIZE_MULT.get(size, 4.0)
    return base * (mult / 4.0)


# Minimal fallback specs for common types (used when DB catalog is empty)
# Format: instance_type → (vcpu, memory_gb, architecture)
_FALLBACK_SPECS = {
    "t2.nano":     (1,  0.5,  "amd64"), "t2.micro":    (1,  1,    "amd64"),
    "t2.small":    (1,  2,    "amd64"), "t2.medium":   (2,  4,    "amd64"),
    "t2.large":    (2,  8,    "amd64"), "t2.xlarge":   (4,  16,   "amd64"),
    "t2.2xlarge":  (8,  32,   "amd64"),
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
    # Graviton 4 — compute optimized (c8g, c8gn)
    "c8g.medium":  (1,  2,    "arm64"), "c8g.large":   (2,  4,    "arm64"),
    "c8g.xlarge":  (4,  8,    "arm64"), "c8g.2xlarge": (8,  16,   "arm64"),
    "c8g.4xlarge": (16, 32,   "arm64"), "c8g.8xlarge": (32, 64,   "arm64"),
    "c8gn.medium": (1,  2,    "arm64"), "c8gn.large":  (2,  4,    "arm64"),
    "c8gn.xlarge": (4,  8,    "arm64"), "c8gn.2xlarge":(8,  16,   "arm64"),
    "c8gn.4xlarge":(16, 32,   "arm64"),
    # Graviton 4 — general purpose (m8g)
    "m8g.medium":  (1,  4,    "arm64"), "m8g.large":   (2,  8,    "arm64"),
    "m8g.xlarge":  (4,  16,   "arm64"), "m8g.2xlarge": (8,  32,   "arm64"),
    "m8g.4xlarge": (16, 64,   "arm64"), "m8g.8xlarge": (32, 128,  "arm64"),
    # Graviton 4 — memory optimized (r8g)
    "r8g.medium":  (1,  8,    "arm64"), "r8g.large":   (2,  16,   "arm64"),
    "r8g.xlarge":  (4,  32,   "arm64"), "r8g.2xlarge": (8,  64,   "arm64"),
    "r8g.4xlarge": (16, 128,  "arm64"),
    # Graviton 3 — network/storage variants (c6gn, c6gd, m6gd, r6gd)
    "c6gn.medium": (1,  2,    "arm64"), "c6gn.large":  (2,  4,    "arm64"),
    "c6gn.xlarge": (4,  8,    "arm64"), "c6gn.2xlarge":(8,  16,   "arm64"),
    "c6gd.medium": (1,  2,    "arm64"), "c6gd.large":  (2,  4,    "arm64"),
    "c6gd.xlarge": (4,  8,    "arm64"), "c6gd.2xlarge":(8,  16,   "arm64"),
    "m6gd.large":  (2,  8,    "arm64"), "m6gd.xlarge": (4,  16,   "arm64"),
    "m6gd.2xlarge":(8,  32,   "arm64"),
    "m6gn.large":  (2,  8,    "arm64"), "m6gn.xlarge": (4,  16,   "arm64"),
    "r6gd.large":  (2,  16,   "arm64"), "r6gd.xlarge": (4,  32,   "arm64"),
    # a1 (original Graviton)
    "a1.medium":   (1,  2,    "arm64"), "a1.large":    (2,  4,    "arm64"),
    "a1.xlarge":   (4,  8,    "arm64"), "a1.2xlarge":  (8,  16,   "arm64"),
}


def _lookup_od_price(r, region: str, instance_type: str) -> float:
    """Get OD price from Redis. Returns 0.0 if not found.
    Tries both key formats: ondemand_price: (pricing_collector) and od_price: (aws_pricing_service)."""
    try:
        raw = r.get(f"ondemand_price:{region}:{instance_type}")
        if raw:
            return float(raw)
        # Fallback: legacy key format written by aws_pricing_service.get_ondemand_price()
        raw = r.get(f"od_price:{region}:{instance_type}")
        if raw:
            return float(raw)
    except Exception:
        pass
    return 0.0


def _lookup_interruption_rate(r, region: str, instance_type: str, db=None) -> float:
    """Get spot advisor interruption rate pct from Redis → DB → family average → 15.0 fallback."""
    _idx_to_pct = {0: 5.0, 1: 10.0, 2: 15.0, 3: 20.0, 4: 25.0}

    # 1. Redis cache (fastest)
    try:
        raw = r.get(f"spot_advisor:{region}:{instance_type}:Linux")
        if raw:
            data = json.loads(raw)
            idx = data.get("interruption_index", 4)
            return _idx_to_pct.get(int(idx), 25.0)
    except Exception:
        pass

    # 2. DB lookup (SpotAdvisorData table)
    if db is not None:
        try:
            from backend.models.pricing import SpotAdvisorData
            record = db.query(SpotAdvisorData).filter(
                SpotAdvisorData.region == region,
                SpotAdvisorData.instance_type == instance_type,
                SpotAdvisorData.os_type == 'Linux',
            ).first()
            if record and record.interruption_index is not None:
                pct = _idx_to_pct.get(record.interruption_index, 15.0)
                # Backfill Redis so next lookup is fast
                try:
                    r.setex(
                        f"spot_advisor:{region}:{instance_type}:Linux",
                        3600,
                        json.dumps({"interruption_index": record.interruption_index,
                                    "savings_percentage": record.savings_percentage or 0})
                    )
                except Exception:
                    pass
                return pct
        except Exception:
            pass

    # 3. Family average from Redis (e.g., t3a family)
    try:
        family = instance_type.split('.')[0]
        _fam_cursor = 0
        _fam_rates = []
        while True:
            _fam_cursor, _fam_keys = r.scan(
                _fam_cursor, match=f"spot_advisor:{region}:{family}.*:Linux", count=50
            )
            for _fk in _fam_keys:
                try:
                    _fraw = r.get(_fk)
                    if _fraw:
                        _fidx = json.loads(_fraw).get("interruption_index")
                        if _fidx is not None:
                            _fam_rates.append(_idx_to_pct.get(int(_fidx), 15.0))
                except Exception:
                    pass
            if _fam_cursor == 0:
                break
        if _fam_rates:
            return round(sum(_fam_rates) / len(_fam_rates), 1)
    except Exception:
        pass

    # 4. Conservative default (not worst-case — 15% = mid-range)
    return 15.0


def _lookup_specs(instance_type: str) -> tuple:
    """Return (vcpu, memory_gb, architecture, is_fallback) for an instance type.
    
    is_fallback=True when the type is completely unknown — callers should
    abort ranking rather than proceeding with default floor values.
    """
    if instance_type in _FALLBACK_SPECS:
        return (*_FALLBACK_SPECS[instance_type], False)
    return _derive_specs_from_type(instance_type)


def _derive_specs_from_type(instance_type: str) -> tuple:
    """
    Derive (vcpu, memory_gb, architecture) from instance family/size.
    Returns (0, 0.0, 'amd64') only for completely unknown formats.
    """
    parts = instance_type.split('.')
    if len(parts) != 2:
        return (0, 0.0, 'amd64', True)
    family, size = parts

    # vCPU counts by size
    vcpu_map = {
        'nano': 2, 'micro': 2, 'small': 2, 'medium': 2, 'large': 2,
        'xlarge': 4, '2xlarge': 8, '3xlarge': 12, '4xlarge': 16,
        '6xlarge': 24, '8xlarge': 32, '9xlarge': 36, '10xlarge': 40,
        '12xlarge': 48, '16xlarge': 64, '18xlarge': 72, '24xlarge': 96,
        '32xlarge': 128, '48xlarge': 192, '56xlarge': 224, '112xlarge': 448,
        'metal': 96,
    }
    vcpu = vcpu_map.get(size, 0)
    if vcpu == 0:
        return (0, 0.0, 'amd64', True)

    # Architecture: Graviton instances have "g" after a generation digit (e.g. c6g, m8g, c8gn, r6gd).
    # This regex matches digit-then-g which is the Graviton marker in AWS naming.
    # GPU instances (g4dn, g5, g6) start WITH "g" and don't match \dg.
    import re as _re
    _is_graviton = bool(_re.search(r'\dg', family)) or family == 'a1'
    arch = 'arm64' if _is_graviton else 'amd64'

    # Memory-to-vCPU ratio by family type
    # general purpose: ~4 GB/vCPU at large (8GB / 2vCPU)
    # compute optimized: ~2 GB/vCPU at large (4GB / 2vCPU)
    # memory optimized: ~8 GB/vCPU at large (16GB / 2vCPU)
    # storage optimized: varies
    family_prefix = family.lower()

    if family_prefix in ('t2', 't3', 't3a', 't4g'):
        # T-series: nano=0.5, micro=1, small=2, medium=4, large=8, xlarge=16, 2xl=32
        _t_mem = {'nano': 0.5, 'micro': 1, 'small': 2, 'medium': 4, 'large': 8,
                  'xlarge': 16, '2xlarge': 32}
        mem = _t_mem.get(size, vcpu * 4.0)
    elif family_prefix in ('c5', 'c5a', 'c5n', 'c6i', 'c6a', 'c6g', 'c6gn', 'c6gd',
                           'c7i', 'c7g', 'c7a', 'c8g', 'c8gn',
                           'c4', 'c3', 'cc2'):
        mem = vcpu * 2.0  # compute optimized ~2GB/vCPU
    elif family_prefix in ('r5', 'r5a', 'r5n', 'r6i', 'r6a', 'r6g', 'r7i', 'r7g', 'r7a',
                           'r4', 'r3', 'x1', 'x1e', 'x2idn', 'x2iedn', 'u-', 'z1d'):
        mem = vcpu * 8.0  # memory optimized ~8GB/vCPU
    elif family_prefix in ('i3', 'i3en', 'i4i', 'i4g', 'i2', 'd2', 'd3', 'd3en', 'h1'):
        mem = vcpu * 7.5  # storage optimized ~7.5GB/vCPU
    elif family_prefix in ('g4dn', 'g5', 'g5g', 'p3', 'p4d', 'p4de', 'p3dn', 'inf1', 'inf2',
                           'trn1', 'dl1'):
        mem = vcpu * 4.0  # accelerated ~4GB/vCPU (rough estimate)
    else:
        # default general purpose: ~4GB/vCPU
        mem = vcpu * 4.0

    return (vcpu, round(mem, 2), arch, False)


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
            logger.warning(
                f"[cache_builder] No spot_price:* keys for {region} — "
                f"falling back to spot_advisor data"
            )
            # Fallback: enumerate from spot_advisor:{region}:*:Linux keys
            azs = _REGION_AZS.get(region, [f"{region}a", f"{region}b"])
            adv_cursor = 0
            seen_types = set()
            while True:
                adv_cursor, adv_keys = r.scan(
                    adv_cursor, match=f"spot_advisor:{region}:*:Linux", count=200
                )
                for adv_key in adv_keys:
                    try:
                        adv_key_str = adv_key.decode() if isinstance(adv_key, bytes) else adv_key
                        # key = spot_advisor:{region}:{instance_type}:Linux
                        parts = adv_key_str.split(':')
                        if len(parts) < 4:
                            continue
                        itype = ':'.join(parts[2:-1])  # handle types like 'm5.large'
                        if itype in seen_types:
                            continue
                        seen_types.add(itype)
                        # Estimate OD price and spot price
                        od_est = _lookup_od_price(r, region, itype) or _estimate_od_price(itype)
                        if od_est <= 0:
                            continue
                        # Use actual savings_percentage from spot_advisor data if available
                        # (spot_advisor:{region}:{itype}:Linux key has "savings_percentage" field)
                        savings_frac = 0.70  # default: conservative 70% savings estimate
                        try:
                            adv_raw = r.get(f"spot_advisor:{region}:{itype}:Linux")
                            if adv_raw:
                                adv_json = json.loads(adv_raw)
                                sa_savings_pct = adv_json.get("savings_percentage", 0)
                                if sa_savings_pct and sa_savings_pct > 0:
                                    savings_frac = sa_savings_pct / 100.0
                        except Exception:
                            pass
                        spot_est = od_est * (1.0 - savings_frac)
                        for az in azs:
                            raw_pools.append({
                                'instance_type': itype,
                                'az': az,
                                'region': region,
                                'spot_price': spot_est,
                                '_is_estimated': True,
                            })
                    except Exception:
                        pass
                if adv_cursor == 0:
                    break
            raw_count = len(raw_pools)
            if not raw_pools:
                logger.warning(f"[cache_builder] No spot_advisor data for {region} either")
                return
            logger.info(
                f"[cache_builder] Built {raw_count} raw pools from spot_advisor "
                f"fallback ({len(seen_types)} types × {len(azs)} AZs) for {region}"
            )

        # Enrich each pool and apply filters
        pools = []
        no_od_price = 0
        negative_savings = 0
        no_specs = 0

        for p in raw_pools:
            itype = p['instance_type']

            # OD price lookup — fall back to family-based estimate
            od_price = _lookup_od_price(r, region, itype)
            if od_price <= 0:
                od_price = _estimate_od_price(itype)
            if od_price <= 0:
                no_od_price += 1
                continue

            # Savings filter
            savings_pct = (od_price - p['spot_price']) / od_price * 100
            if savings_pct <= 0:
                negative_savings += 1
                continue

            # Instance specs
            vcpu, memory_gb, arch, _ = _lookup_specs(itype)
            if vcpu == 0:
                # N9 fix: Unknown instance type — skip entirely to prevent undersized replacement.
                # A (0,0) fallback would bypass vCPU/memory floor filters downstream,
                # allowing a 72-vCPU node to be replaced by a 2-vCPU instance.
                logger.debug(
                    "[cache_builder] Unknown instance type %s — spec lookup returned (0,0). "
                    "Skipping to prevent undersized replacement.", itype
                )
                no_specs += 1
                continue

            # Actual risk tier from spot advisor
            interruption_rate = _lookup_interruption_rate(r, region, itype, db=db)
            risk_tier = assign_risk_tier(interruption_rate)

            # ML score — computed after pool list is built via ONNX (see below).
            # Placeholder so the pool dict is always complete.
            _safety = max(0.0, 1.0 - interruption_rate / 100.0)
            ml_score = round((savings_pct / 100.0) * _safety, 4)  # overwritten below if ONNX available

            pools.append({
                'instance_type': itype,
                'az': p['az'],
                'region': region,
                'spot_price': p['spot_price'],
                'ondemand_price': od_price,
                'savings_pct': round(savings_pct, 1),
                'predicted_savings': round(savings_pct / 100.0, 4),
                'interruption_rate_pct': interruption_rate,
                'risk_tier': risk_tier,
                'spot_advisor_rank': risk_tier,  # 0=safest (<5%), 4=riskiest (>20%)
                'vcpu': vcpu,
                'memory_gb': memory_gb,
                'architecture': arch,
                'ml_score': ml_score,
                'is_flagged': False,
                'blacklisted': False,
                'price_shock': False,
            })

        if not pools:
            logger.warning(
                f"[cache_builder] All pools filtered out for region {region} "
                f"(raw={raw_count}, no_od_price={no_od_price}, negative_savings={negative_savings})"
            )
            return

        # ── ONNX ML scoring pass ──────────────────────────────────────────────
        # Replace the simple formula ml_score with real ONNX scores when db is available.
        # Without this, all pools use savings*safety which ignores historical volatility.
        # NOTE: We disable the hard risk gate here (threshold=1.0) because
        # the per-node and market-view endpoints apply their own risk ceiling.
        # The cache should contain ALL scored pools so endpoints can filter.
        if db is not None:
            try:
                from backend.services.pool_ranking_service import (
                    PoolRankingService, InstancePool
                )
                _prs = PoolRankingService(db, r)
                # Disable hard risk gate for cache building — let endpoints filter
                _prs.risk_threshold = 1.0
                if _prs.classifier_session and _prs.regressor_session:
                    _instance_pools = [
                        InstancePool(
                            instance_type=p['instance_type'],
                            az=p['az'],
                            spot_price=p['spot_price'],
                            ondemand_price=p['ondemand_price'],
                            vcpu=p['vcpu'],
                            memory_gb=p['memory_gb'],
                            architecture=p['architecture'],
                            spot_advisor_rank=int(p['risk_tier']),
                        )
                        for p in pools
                    ]
                    _scored = _prs._step7_ml_scoring(_instance_pools, region)
                    # Build lookup: (instance_type, az) → (ml_score, predicted_savings, risk_prob)
                    _score_map = {
                        (sp.pool.instance_type, sp.pool.az): sp
                        for sp in _scored
                    }
                    # Re-map ml_score and mark pools eliminated by risk gate
                    onnx_pools = []
                    for p in pools:
                        sp = _score_map.get((p['instance_type'], p['az']))
                        if sp is None:
                            continue  # Eliminated by ONNX risk gate — skip
                        p['ml_score'] = round(sp.ml_score, 6)
                        p['predicted_savings'] = round(sp.predicted_savings, 4)
                        p['risk_probability'] = round(sp.risk_probability, 4)
                        onnx_pools.append(p)
                    if onnx_pools:
                        pools = onnx_pools
                        logger.info(
                            f"[cache_builder] ONNX scoring applied for {region}: "
                            f"{len(pools)} pools (eliminated {raw_count - len(pools)} by risk gate)"
                        )
            except Exception as _onnx_err:
                logger.warning(f"[cache_builder] ONNX scoring skipped: {_onnx_err}")

        # Sort by risk tier first, then by price ascending within tier
        pools.sort(key=lambda p: (p['risk_tier'], p['spot_price']))

        # Limit to GLOBAL_CACHE_SIZE
        top_pools = pools[:GLOBAL_CACHE_SIZE]

        # Store in Redis — market_view_cache for Market View UI
        cache_key = key_market_view_cache(region)
        payload = json.dumps({
            'data': top_pools,
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'count': len(top_pools),
            'region': region,
        })
        r.setex(cache_key, 3600, payload)

        # Also populate global_pool_rankings:{region} in the format expected by
        # pool_ranking_service._pool_from_dict() so pool rankings API gets a cache hit
        # instead of running the expensive inline pipeline (which blocks for 10+ minutes
        # due to ONNX scoring 3000+ pools when the risk gate is tight).
        try:
            _now_iso = datetime.now(timezone.utc).isoformat()
            _ranked_dicts = []
            for _i, _p in enumerate(top_pools):
                _savings = _p.get('predicted_savings', 0) or 0
                _risk = _p.get('risk_probability', 0.20) or 0.20
                _ml = _p.get('ml_score', _savings - _risk) or 0.0
                _ranked_dicts.append({
                    'instance_type': _p['instance_type'],
                    'az': _p['az'],
                    'architecture': _p.get('architecture', 'x86_64'),
                    'vcpu': _p.get('vcpu', 2),
                    'memory_gb': _p.get('memory_gb', 4.0),
                    'spot_price': _p.get('spot_price', 0.0),
                    'ondemand_price': _p.get('ondemand_price', 0.0),
                    'spot_advisor_rank': int(_p.get('risk_tier', 2)),
                    'has_capacity': True,
                    'capacity_uncertain': False,
                    'predicted_savings': round(float(_savings), 4),
                    'risk_probability': round(float(_risk), 4),
                    'ml_score': round(float(_ml), 6),
                    'is_flagged': False,
                    'rank': _i + 1,
                    'timestamp': _now_iso,
                    'capacity_status': None,
                    'capacity_validated_at': None,
                })
            r.setex(f'global_pool_rankings:{region}', 3900, json.dumps(_ranked_dicts))
            logger.info(
                f"[cache_builder] Also wrote global_pool_rankings:{region} "
                f"({len(_ranked_dicts)} pools) for pool rankings API"
            )
        except Exception as _gpr_err:
            logger.warning(f"[cache_builder] global_pool_rankings cross-write failed: {_gpr_err}")

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
    def build_global_pool_cache_task(region: str = 'us-east-1'):
        """Celery task wrapper for build_global_pool_cache.
        Opens a DB session so the 4-tier interruption_rate lookup (Redis → DB → family → default)
        can use Tier 2 (SpotAdvisorData table) when Redis keys have expired.
        """
        from backend.models.base import get_db
        db = next(get_db())
        try:
            return build_global_pool_cache(region, db=db)
        finally:
            db.close()

except ImportError:
    logger.warning("[cache_builder] Celery not available, task scheduling disabled")
