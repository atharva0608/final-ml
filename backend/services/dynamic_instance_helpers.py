"""
Dynamic Instance Helpers
========================

Thin helper module that provides functions to fetch instance metadata
(vCPU count, on-demand hourly price) dynamically from the database
(backed by AWS APIs), with graceful fallback to hardcoded estimates.

Used by:
- ascpai_routes.py  (get_node_recommendations, get_cluster_impact)
- pool_ranking_service.py (_load_instance_catalog)
"""

import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session
from redis import Redis

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Hardcoded fallback tables — used ONLY when the DB has no catalog data
# (e.g. first boot before the nightly worker runs).
# ──────────────────────────────────────────────────────────────────────

_FALLBACK_VCPU: Dict[str, int] = {
    "t3.nano": 2, "t3.micro": 2, "t3.small": 2, "t3.medium": 2, "t3.large": 2,
    "t3.xlarge": 4, "t3.2xlarge": 8,
    "t3a.nano": 2, "t3a.micro": 2, "t3a.small": 2, "t3a.medium": 2, "t3a.large": 2,
    "t3a.xlarge": 4, "t3a.2xlarge": 8,
    "t4g.micro": 2, "t4g.small": 2, "t4g.medium": 2, "t4g.large": 2,
    "t4g.xlarge": 4, "t4g.2xlarge": 8,
    "m5.large": 2, "m5.xlarge": 4, "m5.2xlarge": 8, "m5.4xlarge": 16,
    "m6i.large": 2, "m6i.xlarge": 4, "m6i.2xlarge": 8, "m6i.4xlarge": 16,
    "m6g.medium": 1, "m6g.large": 2, "m6g.xlarge": 4, "m6g.2xlarge": 8,
    "c5.large": 2, "c5.xlarge": 4, "c5.2xlarge": 8, "c5.4xlarge": 16,
    "c6i.large": 2, "c6i.xlarge": 4, "c6i.2xlarge": 8, "c6i.4xlarge": 16,
    "c6a.large": 2, "c6a.xlarge": 4,
    "c6g.medium": 1, "c6g.large": 2, "c6g.xlarge": 4, "c6g.2xlarge": 8,
    "r5.large": 2, "r5.xlarge": 4, "r5.2xlarge": 8, "r5.4xlarge": 16,
    "r6i.large": 2, "r6i.xlarge": 4, "r6i.2xlarge": 8,
}

_FALLBACK_HOURLY: Dict[str, float] = {
    "t3.nano": 0.0058, "t3.micro": 0.0116, "t3.small": 0.0232, "t3.medium": 0.0464,
    "t3.large": 0.0928, "t3.xlarge": 0.1856, "t3.2xlarge": 0.3712,
    "t3a.nano": 0.0047, "t3a.micro": 0.0104, "t3a.small": 0.0209, "t3a.medium": 0.0418,
    "t3a.large": 0.0836, "t3a.xlarge": 0.1672, "t3a.2xlarge": 0.3344,
    "t4g.micro": 0.0092, "t4g.small": 0.0184, "t4g.medium": 0.0368,
    "t4g.large": 0.0736, "t4g.xlarge": 0.1472, "t4g.2xlarge": 0.2944,
    "m5.large": 0.096, "m5.xlarge": 0.192, "m5.2xlarge": 0.384,
    "m5.4xlarge": 0.768, "m6i.large": 0.096, "m6i.xlarge": 0.192,
    "c5.large": 0.085, "c5.xlarge": 0.170, "c5.2xlarge": 0.340,
    "c6i.large": 0.085, "c6a.large": 0.0765,
    "r5.large": 0.126, "r5.xlarge": 0.252, "r5.2xlarge": 0.504,
    "c6g.medium": 0.034, "c6g.large": 0.068, "c6g.xlarge": 0.136,
    "m6g.medium": 0.038, "m6g.large": 0.077, "m6g.xlarge": 0.154,
}


# ──────────────────────────────────────────────────────────────────────
# Public helpers
# ──────────────────────────────────────────────────────────────────────

def get_instance_vcpu(
    db: Session,
    instance_type: str,
    region: str = "us-east-1",
) -> int:
    """
    Return vCPU count for an instance type.

    Priority:
      1. InstanceCatalog DB table  (populated by nightly worker)
      2. Hardcoded fallback dict
      3. Default = 2
    """
    try:
        from backend.models.instance_catalog import InstanceCatalog

        row = db.query(InstanceCatalog).filter(
            InstanceCatalog.instance_type == instance_type,
            InstanceCatalog.region == region,
        ).first()

        if row and row.vcpus:
            return int(row.vcpus)
    except Exception as e:
        logger.debug(f"InstanceCatalog lookup failed for {instance_type}: {e}")

    return _FALLBACK_VCPU.get(instance_type) or _estimate_vcpu(instance_type)


def get_instance_hourly_price(
    db: Session,
    redis: Redis,
    instance_type: str,
    region: str = "ap-south-1",
) -> float:
    """
    Return on-demand hourly price ($/hr) for an instance type.

    Priority:
      1. AWSPricingService (Redis-cached real-time pricing from AWS)
      2. OnDemandPricing DB table (persisted by AWSPricingService)
      3. Hardcoded fallback dict
      4. Estimate based on family/size heuristics
    """
    # 1. Try AWSPricingService (fetches from Redis cache → AWS API)
    try:
        from backend.services.aws_pricing_service import AWSPricingService

        pricing_svc = AWSPricingService(db, redis)
        price = pricing_svc.get_ondemand_price(
            instance_type, region, validate_freshness=False
        )
        if price is not None and price > 0:
            return float(price)
    except Exception as e:
        logger.debug(f"AWSPricingService lookup failed for {instance_type}: {e}")

    # 2. Try OnDemandPricing DB table directly
    try:
        from backend.models.pricing import OnDemandPricing

        row = db.query(OnDemandPricing).filter(
            OnDemandPricing.instance_type == instance_type,
            OnDemandPricing.region == region,
        ).first()
        if row and row.price:
            return float(row.price)
    except Exception as e:
        logger.debug(f"OnDemandPricing DB lookup failed for {instance_type}: {e}")

    # 3. Hardcoded fallback
    if instance_type in _FALLBACK_HOURLY:
        return _FALLBACK_HOURLY[instance_type]

    # 4. Heuristic estimate based on family/size
    return _estimate_price(instance_type)


def load_instance_catalog_from_db(
    db: Session,
    region: str = "us-east-1",
) -> Dict[str, Dict]:
    """
    Load instance catalog from the InstanceCatalog DB table.

    Returns a dict compatible with PoolRankingService.instance_catalog:
      { "m5.large": {"vcpu": 2, "memory_gb": 8, "architecture": "amd64"}, ... }

    Returns empty dict if the table has no rows (caller should fall back to hardcoded).
    """
    try:
        from backend.models.instance_catalog import InstanceCatalog

        rows = db.query(InstanceCatalog).filter(
            InstanceCatalog.region == region,
            InstanceCatalog.current_generation == True,
        ).all()

        if not rows:
            logger.info(
                f"InstanceCatalog DB is empty for region={region}. "
                "Trying any available region as fallback."
            )
            rows = db.query(InstanceCatalog).filter(
                InstanceCatalog.current_generation == True,
            ).all()
            if not rows:
                logger.info(
                    "InstanceCatalog DB is globally empty. "
                    "Run the instance_catalog_worker to populate it."
                )
                return {}

        catalog = {}
        for row in rows:
            # Map AWS architecture names to Kubernetes-style names
            arch = row.architecture
            if arch == "x86_64":
                arch = "amd64"

            catalog[row.instance_type] = {
                "vcpu": int(row.vcpus) if row.vcpus else 0,
                "memory_gb": float(row.memory_gb) if row.memory_gb else 0.0,
                "architecture": arch,
            }

        logger.debug(
            f"Loaded {len(catalog)} instances from InstanceCatalog DB "
            f"(region={region})"
        )
        return catalog

    except Exception as e:
        logger.warning(f"Failed to load InstanceCatalog from DB: {e}")
        return {}


def bulk_get_hourly_prices(
    db: Session,
    redis: Redis,
    instance_types: list,
    region: str = "ap-south-1",
) -> Dict[str, float]:
    """
    Efficiently fetch on-demand hourly prices for a batch of instance types.

    Returns: { "t3.medium": 0.0464, "m5.large": 0.096, ... }
    """
    prices: Dict[str, float] = {}

    # 1. Bulk-fetch from OnDemandPricing DB table in one query
    try:
        from backend.models.pricing import OnDemandPricing

        rows = db.query(OnDemandPricing).filter(
            OnDemandPricing.region == region,
            OnDemandPricing.instance_type.in_(instance_types),
        ).all()

        for row in rows:
            if row.price:
                prices[row.instance_type] = float(row.price)
    except Exception as e:
        logger.debug(f"Bulk OnDemandPricing query failed: {e}")

    # 2. Fill in any missing types from fallback + heuristic
    for it in instance_types:
        if it not in prices:
            prices[it] = _FALLBACK_HOURLY.get(it, _estimate_price(it))

    return prices


def bulk_get_vcpu_counts(
    db: Session,
    instance_types: list,
    region: str = "us-east-1",
) -> Dict[str, int]:
    """
    Efficiently fetch vCPU counts for a batch of instance types.

    Returns: { "t3.medium": 2, "m5.large": 2, ... }
    """
    vcpus: Dict[str, int] = {}

    # 1. Bulk-fetch from InstanceCatalog DB table
    try:
        from backend.models.instance_catalog import InstanceCatalog

        rows = db.query(InstanceCatalog).filter(
            InstanceCatalog.region == region,
            InstanceCatalog.instance_type.in_(instance_types),
        ).all()

        for row in rows:
            if row.vcpus:
                vcpus[row.instance_type] = int(row.vcpus)
    except Exception as e:
        logger.debug(f"Bulk InstanceCatalog query failed: {e}")

    # 2. Fill in any missing types from fallback then heuristic
    for it in instance_types:
        if it not in vcpus:
            vcpus[it] = _FALLBACK_VCPU.get(it) or _estimate_vcpu(it)

    return vcpus


def bulk_get_memory_gb(
    db: Session,
    instance_types: list,
    region: str = "us-east-1",
) -> Dict[str, float]:
    """
    Efficiently fetch memory (in GB) for a batch of instance types.

    Returns: { "t3.medium": 4.0, "m5.large": 8.0, ... }
    """
    mem_gb: Dict[str, float] = {}

    # 1. Bulk-fetch from InstanceCatalog DB table
    try:
        from backend.models.instance_catalog import InstanceCatalog

        rows = db.query(InstanceCatalog).filter(
            InstanceCatalog.region == region,
            InstanceCatalog.instance_type.in_(instance_types),
        ).all()

        for row in rows:
            if row.memory_gb:
                mem_gb[row.instance_type] = float(row.memory_gb)
    except Exception as e:
        logger.debug(f"Bulk InstanceCatalog query failed for memory: {e}")

    # 2. Fill in any missing types from fallback
    for it in instance_types:
        if it not in mem_gb:
            mem_gb[it] = _estimate_memory_gb(it)

    return mem_gb


# ──────────────────────────────────────────────────────────────────────
# Private
# ──────────────────────────────────────────────────────────────────────

def _estimate_vcpu(instance_type: str) -> int:
    """Heuristic vCPU estimate based on size suffix.

    AWS instance vCPU counts follow a consistent doubling pattern by size,
    independent of family. This covers any instance type not in the hardcoded dict.
    """
    parts = instance_type.split(".")
    if len(parts) != 2:
        return 2

    size = parts[1]

    size_vcpu = {
        "nano": 2, "micro": 2, "small": 2, "medium": 2,
        "large": 2, "xlarge": 4, "2xlarge": 8, "3xlarge": 12,
        "4xlarge": 16, "6xlarge": 24, "8xlarge": 32, "9xlarge": 36,
        "12xlarge": 48, "16xlarge": 64, "18xlarge": 72,
        "24xlarge": 96, "32xlarge": 128, "48xlarge": 192,
        "metal": 48,
    }

    return size_vcpu.get(size, 2)


def _estimate_price(instance_type: str) -> float:
    """Heuristic price estimate based on family and size."""
    parts = instance_type.split(".")
    if len(parts) != 2:
        return 0.10

    family, size = parts

    size_multipliers = {
        "nano": 0.25, "micro": 0.5, "small": 1.0, "medium": 2.0,
        "large": 4.0, "xlarge": 8.0, "2xlarge": 16.0, "3xlarge": 24.0,
        "4xlarge": 32.0, "6xlarge": 48.0, "8xlarge": 64.0,
        "9xlarge": 72.0, "12xlarge": 96.0, "16xlarge": 128.0,
        "18xlarge": 144.0, "24xlarge": 192.0, "32xlarge": 256.0,
    }

    family_base = {
        "t2": 0.023, "t3": 0.0832, "t3a": 0.0752, "t4g": 0.0672,
        "m5": 0.096, "m5a": 0.086, "m5n": 0.119,
        "m6i": 0.096, "m6a": 0.086, "m6g": 0.077,
        "c5": 0.085, "c5a": 0.077, "c5n": 0.108,
        "c6i": 0.085, "c6a": 0.077, "c6g": 0.068,
        "r5": 0.126, "r5a": 0.113, "r5n": 0.149,
        "r6i": 0.126, "r6a": 0.113, "r6g": 0.101,
    }

    base = family_base.get(family, 0.10)
    mult = size_multipliers.get(size, 4.0)

    return base * (mult / 4.0)  # normalised to .large = 1.0x

def _estimate_memory_gb(instance_type: str) -> float:
    """Heuristic memory estimate (GB) based on family and size."""
    parts = instance_type.split(".")
    if len(parts) != 2:
        return 4.0

    family, size = parts

    size_multipliers = {
        "nano": 0.25, "micro": 0.5, "small": 1.0, "medium": 2.0,
        "large": 4.0, "xlarge": 8.0, "2xlarge": 16.0, "3xlarge": 24.0,
        "4xlarge": 32.0, "6xlarge": 48.0, "8xlarge": 64.0,
        "9xlarge": 72.0, "12xlarge": 96.0, "16xlarge": 128.0,
        "18xlarge": 144.0, "24xlarge": 192.0, "32xlarge": 256.0,
    }

    # Base memory for a `.large` instance in each family group
    family_base_mem = {
        "t2": 8.0, "t3": 8.0, "t3a": 8.0, "t4g": 8.0,
        "m5": 8.0, "m5a": 8.0, "m5n": 8.0,
        "m6i": 8.0, "m6a": 8.0, "m6g": 8.0,
        "c5": 4.0, "c5a": 4.0, "c5n": 4.0,
        "c6i": 4.0, "c6a": 4.0, "c6g": 4.0,
        "r5": 16.0, "r5a": 16.0, "r5n": 16.0,
        "r6i": 16.0, "r6a": 16.0, "r6g": 16.0,
    }

    base_mem = family_base_mem.get(family, 8.0)
    mult = size_multipliers.get(size, 4.0)

    return base_mem * (mult / 4.0)
