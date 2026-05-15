"""
Pricing Collector (SVC-PRICE-01)
Real-time AWS pricing data collection service

Collects current Spot and On-Demand pricing for all instance types across regions.
Updates Redis cache for fast price lookups used by Spot Optimizer.

Data Sources:
- EC2 Spot Pricing: describe_spot_price_history() API
- On-Demand Pricing: AWS Price List API

Key Features:
- Real-time Spot price collection every 5 minutes
- On-Demand price collection daily
- Multi-region parallel collection
- Redis caching with TTL
- Price history tracking
- Trend analysis

Update Frequency:
- Spot prices: Every 5 minutes
- On-Demand prices: Daily at 1:00 AM UTC

Dependencies:
- boto3 for AWS API calls
- SQLAlchemy for price history storage
- Redis for real-time price cache
"""

import logging
import threading
import boto3
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from botocore.exceptions import ClientError
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from backend.models.base import get_db
from backend.models.pricing import SpotPriceHistory, OnDemandPricing
from backend.core.redis_client import get_redis_client
from backend.core.config import MAX_CONCURRENT_REGION_CALLS

logger = logging.getLogger(__name__)

# Module-level semaphore to limit concurrent region calls
_region_semaphore = threading.Semaphore(MAX_CONCURRENT_REGION_CALLS)

# ── Family-based OD price estimator ──────────────────────────────────────────
# Used by the DescribeInstanceTypeOfferings backfill (Gap 1 / new-type path) when
# a type has no cached OD price yet (e.g. freshly launched instance types).
# Prices are $/hr for .large in us-east-1 reference; multiplied by size factor.
# These are intentionally conservative — refresh_ondemand will overwrite with real
# prices on its next hourly run.
_FAMILY_BASE_OD: dict = {
    't2': 0.023, 't3': 0.0832, 't3a': 0.0752, 't4g': 0.0672,
    'm5': 0.096, 'm5a': 0.086, 'm6i': 0.096, 'm6a': 0.086, 'm6g': 0.077,
    'm7i': 0.1008, 'm7g': 0.0816, 'm8g': 0.0850,
    'c5': 0.085, 'c5a': 0.077, 'c6i': 0.085, 'c6a': 0.077, 'c6g': 0.068,
    'c7i': 0.089, 'c7g': 0.0725, 'c7a': 0.085, 'c8g': 0.0700,
    'r5': 0.126, 'r5a': 0.113, 'r6i': 0.126, 'r6a': 0.113, 'r6g': 0.101,
    'r7i': 0.1323, 'r7g': 0.1071, 'r8g': 0.1150,
    'i3': 0.156, 'i4i': 0.182, 'i4g': 0.165,
    'inf1': 0.228, 'inf2': 0.760, 'trn1': 1.340,
}
_SIZE_MULT_OD: dict = {
    'nano': 0.25, 'micro': 0.5, 'small': 1.0, 'medium': 2.0, 'large': 4.0,
    'xlarge': 8.0, '2xlarge': 16.0, '3xlarge': 24.0, '4xlarge': 32.0,
    '6xlarge': 48.0, '8xlarge': 64.0, '12xlarge': 96.0, '16xlarge': 128.0,
    '24xlarge': 192.0, '32xlarge': 256.0, '48xlarge': 384.0, 'metal': 128.0,
}


def _estimate_od_price(instance_type: str) -> float:
    """Estimate on-demand $/hr for a type with no cached OD price."""
    parts = instance_type.split('.')
    if len(parts) != 2:
        return 0.0
    family, size = parts
    base = _FAMILY_BASE_OD.get(family, 0.0)
    if base <= 0.0:
        return 0.0
    mult = _SIZE_MULT_OD.get(size, 0.0)
    if mult <= 0.0:
        return 0.0
    return round(base * (mult / 4.0), 6)


def _mark_region_degraded(region: str):
    """Mark a region as degraded in Redis for 30 minutes."""
    try:
        redis_client = get_redis_client()
        redis_client.setex(f'degraded:region:{region}', 1800, '1')
    except Exception as e:
        logger.warning(f"[SVC-PRICE-01] Failed to mark region {region} degraded: {e}")


def _is_region_degraded(region: str) -> bool:
    """Check if a region is currently marked as degraded."""
    try:
        redis_client = get_redis_client()
        return bool(redis_client.exists(f'degraded:region:{region}'))
    except Exception:
        return False


def _update_spot_price_timestamp(region: str):
    """Store ISO timestamp of last successful spot price collection for region."""
    try:
        redis_client = get_redis_client()
        redis_client.setex(
            f'spot_prices_updated:{region}',
            7200,
            datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.warning(f"[SVC-PRICE-01] Failed to update spot price timestamp for {region}: {e}")

# AWS regions to monitor
AWS_REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "eu-west-1", "eu-west-2", "eu-central-1",
    "ap-south-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1"
]

# Product description for Linux instances
PRODUCT_DESCRIPTION = "Linux/UNIX"


def collect_spot_prices(regions: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Collect current Spot prices for all instance types across regions

    Args:
        regions: List of AWS regions to query (defaults to all major regions)

    Returns:
        Dict with collection results and statistics
    """
    logger.info("[SVC-PRICE-01] Starting Spot price collection")

    if regions is None:
        regions = AWS_REGIONS

    db = next(get_db())
    redis_client = get_redis_client()

    try:
        stats = {
            "regions_processed": 0,
            "prices_collected": 0,
            "cache_keys_set": 0,
            "errors": 0,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Use thread pool for parallel region queries
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(collect_region_spot_prices, region, db, redis_client): region
                for region in regions
            }

            for future in as_completed(futures):
                region = futures[future]
                try:
                    region_stats = future.result()
                    stats["regions_processed"] += 1
                    stats["prices_collected"] += region_stats["prices_collected"]
                    stats["cache_keys_set"] += region_stats["cache_keys_set"]

                    logger.info(
                        f"[SVC-PRICE-01] Completed {region}: "
                        f"{region_stats['prices_collected']} prices collected"
                    )
                except Exception as e:
                    logger.error(f"[SVC-PRICE-01] Error collecting prices for {region}: {str(e)}")
                    stats["errors"] += 1

        logger.info(f"[SVC-PRICE-01] Spot price collection complete: {stats}")

        return {
            "status": "success",
            "stats": stats
        }

    except Exception as e:
        logger.error(f"[SVC-PRICE-01] Fatal error in price collection: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

    finally:
        db.close()


def collect_region_spot_prices(
    region: str,
    db: Session,
    redis_client
) -> Dict[str, int]:
    """
    Collect Spot prices for a single region

    Args:
        region: AWS region
        db: Database session
        redis_client: Redis client

    Returns:
        Dict with collection statistics
    """
    logger.info(f"[SVC-PRICE-01] Collecting Spot prices for {region}")

    stats = {
        "prices_collected": 0,
        "cache_keys_set": 0
    }

    with _region_semaphore:
        try:
            # Create EC2 client for this region
            ec2_client = boto3.client('ec2', region_name=region)

            # Gap 2 fix: use a 6-hour window instead of 1 hour.
            # Stable, low-demand pools (e.g. t3a.xlarge in ap-south-1b) can go
            # 6-24 h without a price change — they would appear as zero results in
            # a 1-hour window even though they are perfectly valid pools.
            # 6 h captures the most recent price for virtually all pool types.
            # MaxResults=1000 is the *page size* (not a total cap); the NextToken
            # loop below runs to completion so all pages are collected.
            spot_prices = []
            next_token = None
            consecutive_failures = 0

            while True:
                try:
                    kwargs = {
                        'StartTime': datetime.utcnow() - timedelta(hours=6),
                        'ProductDescriptions': [PRODUCT_DESCRIPTION],
                        'MaxResults': 1000,
                    }
                    if next_token:
                        kwargs['NextToken'] = next_token

                    response = ec2_client.describe_spot_price_history(**kwargs)
                    spot_prices.extend(response.get('SpotPriceHistory', []))
                    consecutive_failures = 0

                    next_token = response.get('NextToken')
                    if not next_token:
                        break
                except ClientError as page_err:
                    consecutive_failures += 1
                    logger.warning(f"[SVC-PRICE-01] Page error for {region}: {page_err}")
                    if consecutive_failures >= 3:
                        _mark_region_degraded(region)
                        raise
                    break

            # Group by instance type + AZ, keep only latest price
            # (AWS returns history newest-first so the first occurrence per key is the current price)
            latest_prices = {}
            for price_entry in spot_prices:
                instance_type = price_entry['InstanceType']
                az = price_entry['AvailabilityZone']
                key = f"{instance_type}:{az}"

                # Keep only the newest price (already sorted newest first)
                if key not in latest_prices:
                    latest_prices[key] = price_entry

            # Store in database and cache
            written_cache_keys: set = set()
            for key, price_entry in latest_prices.items():
                instance_type = price_entry['InstanceType']
                az = price_entry['AvailabilityZone']
                price = Decimal(price_entry['SpotPrice'])
                timestamp = price_entry['Timestamp']

                # Store in database for historical tracking
                spot_price_record = SpotPriceHistory(
                    instance_type=instance_type,
                    availability_zone=az,
                    region=region,
                    price=price,
                    timestamp=timestamp,
                    product_description=PRODUCT_DESCRIPTION
                )
                db.add(spot_price_record)
                stats["prices_collected"] += 1

                # Cache in Redis for fast lookup
                cache_key = f"spot_price:{region}:{az}:{instance_type}"
                cache_value = json.dumps({
                    "price": str(price),
                    "timestamp": timestamp.isoformat()
                })

                # Cache with 10-minute TTL (prices update every 5 min, so 10 min is safe)
                redis_client.setex(cache_key, 600, cache_value)
                written_cache_keys.add(cache_key)
                stats["cache_keys_set"] += 1

            db.commit()

            # ── Gap 1 fix: DescribeInstanceTypeOfferings back-fill ──────────────
            # describe_spot_price_history only covers types with recent transactions.
            # DescribeInstanceTypeOfferings returns every type AWS offers for spot in
            # each AZ.  For types+AZs in offerings but missing from price history we
            # write an estimated spot_price key (OD price × 0.35) marked is_estimated.
            try:
                _off_paginator = ec2_client.get_paginator('describe_instance_type_offerings')
                _offering_pairs: set = set()
                for _off_pg in _off_paginator.paginate(LocationType='availability-zone'):
                    for _off in _off_pg.get('InstanceTypeOfferings', []):
                        if _off['Location'].startswith(region):
                            _offering_pairs.add((_off['InstanceType'], _off['Location']))

                _estimated_count = 0
                _now_iso = datetime.utcnow().isoformat()
                for _itype, _az in _offering_pairs:
                    _ck = f"spot_price:{region}:{_az}:{_itype}"
                    if _ck in written_cache_keys:
                        continue  # Real price already written — don't overwrite
                    _od_raw = (
                        redis_client.get(f"ondemand_price:{region}:{_itype}")
                        or redis_client.get(f"od_price:{region}:{_itype}")
                    )
                    _od_price = float(_od_raw) if _od_raw else 0.0
                    if _od_price <= 0.0:
                        # New instance type not yet in refresh_ondemand cache.
                        # Estimate from family/size so this type enters the
                        # scoring universe immediately rather than waiting for
                        # the next daily OD refresh cycle.
                        _od_price = _estimate_od_price(_itype)
                        if _od_price <= 0.0:
                            continue  # Completely unknown family — genuinely skip
                    _est_spot = round(_od_price * 0.35, 6)
                    redis_client.setex(
                        _ck,
                        600,
                        json.dumps({
                            "price": str(_est_spot),
                            "timestamp": _now_iso,
                            "is_estimated": True,
                        }),
                    )
                    _estimated_count += 1

                redis_client.setex(
                    f"instance_type_offerings:{region}:count",
                    90_000,  # 25 hours
                    str(len(_offering_pairs)),
                )
                logger.info(
                    f"[Gap1][SVC-PRICE-01] OfferingsBackfill {region}: "
                    f"total_offerings={len(_offering_pairs)}, "
                    f"history_keys={len(written_cache_keys)}, "
                    f"estimated_added={_estimated_count}"
                )
            except Exception as _offerings_err:
                logger.warning(
                    f"[Gap1][SVC-PRICE-01] DescribeInstanceTypeOfferings backfill "
                    f"failed for {region}: {_offerings_err}"
                )
            # ────────────────────────────────────────────────────────────────────

            _update_spot_price_timestamp(region)

            logger.info(
                f"[SVC-PRICE-01] Stored {stats['prices_collected']} prices for {region}"
            )

            return stats

        except ClientError as e:
            logger.error(f"[SVC-PRICE-01] AWS API error for {region}: {str(e)}")
            raise

        except Exception as e:
            logger.error(f"[SVC-PRICE-01] Unexpected error for {region}: {str(e)}")
            raise


def get_current_spot_price(
    instance_type: str,
    availability_zone: str,
    region: str,
    redis_client=None
) -> Optional[Decimal]:
    """
    Get current Spot price for instance type in AZ

    Checks Redis cache first, falls back to database if not cached.

    Args:
        instance_type: EC2 instance type (e.g., "m5.large")
        availability_zone: Availability zone (e.g., "us-east-1a")
        region: AWS region
        redis_client: Optional Redis client

    Returns:
        Current Spot price as Decimal, or None if not available
    """
    if redis_client is None:
        redis_client = get_redis_client()

    # Try Redis cache first
    cache_key = f"spot_price:{region}:{availability_zone}:{instance_type}"
    cached_data = redis_client.get(cache_key)

    if cached_data:
        data = json.loads(cached_data)
        return Decimal(data["price"])

    # Cache miss - query database
    logger.debug(f"[SVC-PRICE-01] Cache miss for {instance_type} in {availability_zone}")

    db = next(get_db())

    try:
        # Get most recent price from database
        price_record = db.query(SpotPriceHistory).filter(
            and_(
                SpotPriceHistory.instance_type == instance_type,
                SpotPriceHistory.availability_zone == availability_zone,
                SpotPriceHistory.region == region
            )
        ).order_by(desc(SpotPriceHistory.timestamp)).first()

        if price_record:
            # Populate cache
            cache_value = json.dumps({
                "price": str(price_record.price),
                "timestamp": price_record.timestamp.isoformat()
            })
            redis_client.setex(cache_key, 600, cache_value)

            return price_record.price
        else:
            logger.warning(
                f"[SVC-PRICE-01] No price data for {instance_type} in {availability_zone}"
            )
            return None

    finally:
        db.close()


def collect_ondemand_prices(regions: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Collect On-Demand prices using AWS Price List API

    Args:
        regions: List of AWS regions to query

    Returns:
        Dict with collection results
    """
    logger.info("[SVC-PRICE-01] Starting On-Demand price collection")

    if regions is None:
        regions = AWS_REGIONS

    db = next(get_db())
    redis_client = get_redis_client()

    try:
        stats = {
            "regions_processed": 0,
            "prices_collected": 0,
            "cache_keys_set": 0,
            "errors": 0
        }

        # AWS Price List API is only available in us-east-1 and ap-south-1
        pricing_client = boto3.client('pricing', region_name='us-east-1')

        for region in regions:
            try:
                region_stats = collect_region_ondemand_prices(
                    region, pricing_client, db, redis_client
                )
                stats["regions_processed"] += 1
                stats["prices_collected"] += region_stats["prices_collected"]
                stats["cache_keys_set"] += region_stats["cache_keys_set"]

            except Exception as e:
                logger.error(
                    f"[SVC-PRICE-01] Error collecting On-Demand prices for {region}: {str(e)}"
                )
                stats["errors"] += 1

        logger.info(f"[SVC-PRICE-01] On-Demand price collection complete: {stats}")

        return {
            "status": "success",
            "stats": stats
        }

    except Exception as e:
        logger.error(f"[SVC-PRICE-01] Fatal error in On-Demand price collection: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

    finally:
        db.close()


def collect_region_ondemand_prices(
    region: str,
    pricing_client,
    db: Session,
    redis_client
) -> Dict[str, int]:
    """
    Collect On-Demand prices for a single region

    Args:
        region: AWS region
        pricing_client: Boto3 pricing client
        db: Database session
        redis_client: Redis client

    Returns:
        Dict with collection statistics
    """
    logger.info(f"[SVC-PRICE-01] Collecting On-Demand prices for {region}")

    stats = {
        "prices_collected": 0,
        "cache_keys_set": 0
    }

    try:
        # Map region code to Price List API location format
        # e.g., "us-east-1" -> "US East (N. Virginia)"
        location = get_price_list_location(region)

        # Query pricing API
        # Note: This is simplified - in production, would need pagination
        paginator = pricing_client.get_paginator('get_products')

        pages = paginator.paginate(
            ServiceCode='AmazonEC2',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
                {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'}
            ],
            MaxResults=100
        )

        for page in pages:
            for price_item in page.get('PriceList', []):
                # Parse price item (complex nested JSON structure)
                price_data = json.loads(price_item)

                instance_type = price_data.get('product', {}).get('attributes', {}).get('instanceType')
                if not instance_type:
                    continue

                # Extract price from nested structure
                on_demand_terms = price_data.get('terms', {}).get('OnDemand', {})
                if not on_demand_terms:
                    continue

                # Get first (and usually only) price dimension
                for offer_term in on_demand_terms.values():
                    price_dimensions = offer_term.get('priceDimensions', {})
                    for dimension in price_dimensions.values():
                        price_per_unit = dimension.get('pricePerUnit', {}).get('USD')
                        if price_per_unit:
                            price = Decimal(price_per_unit)

                            # Store in database
                            ondemand_record = db.query(OnDemandPricing).filter(
                                and_(
                                    OnDemandPricing.instance_type == instance_type,
                                    OnDemandPricing.region == region
                                )
                            ).first()

                            if ondemand_record:
                                ondemand_record.price = price
                                ondemand_record.updated_at = datetime.utcnow()
                            else:
                                ondemand_record = OnDemandPricing(
                                    instance_type=instance_type,
                                    region=region,
                                    price=price
                                )
                                db.add(ondemand_record)

                            stats["prices_collected"] += 1

                            # Cache in Redis
                            cache_key = f"ondemand_price:{region}:{instance_type}"
                            redis_client.setex(cache_key, 86400, str(price))  # 24h TTL
                            stats["cache_keys_set"] += 1

                            break  # Only need first price dimension

        db.commit()

        logger.info(
            f"[SVC-PRICE-01] Stored {stats['prices_collected']} On-Demand prices for {region}"
        )

        return stats

    except Exception as e:
        logger.error(f"[SVC-PRICE-01] Error collecting On-Demand prices: {str(e)}")
        raise


def get_price_list_location(region: str) -> str:
    """
    Map AWS region code to Price List API location string

    Args:
        region: AWS region code (e.g., "us-east-1")

    Returns:
        Price List location string (e.g., "US East (N. Virginia)")
    """
    region_map = {
        "us-east-1": "US East (N. Virginia)",
        "us-east-2": "US East (Ohio)",
        "us-west-1": "US West (N. California)",
        "us-west-2": "US West (Oregon)",
        "eu-west-1": "EU (Ireland)",
        "eu-west-2": "EU (London)",
        "eu-central-1": "EU (Frankfurt)",
        "ap-south-1": "Asia Pacific (Mumbai)",
        "ap-southeast-1": "Asia Pacific (Singapore)",
        "ap-southeast-2": "Asia Pacific (Sydney)",
        "ap-northeast-1": "Asia Pacific (Tokyo)"
    }

    return region_map.get(region, region)


def calculate_savings_percentage(
    spot_price: Decimal,
    ondemand_price: Decimal
) -> int:
    """
    Calculate savings percentage when using Spot vs On-Demand

    Args:
        spot_price: Current Spot price
        ondemand_price: On-Demand price

    Returns:
        Savings percentage (0-100)
    """
    if ondemand_price == 0:
        return 0

    savings = ((ondemand_price - spot_price) / ondemand_price) * 100
    return int(max(0, min(100, savings)))


def get_price_comparison(
    instance_type: str,
    availability_zone: str,
    region: str,
    redis_client=None
) -> Optional[Dict[str, Any]]:
    """
    Compare Spot vs On-Demand pricing for instance type

    Args:
        instance_type: EC2 instance type
        availability_zone: Availability zone
        region: AWS region
        redis_client: Optional Redis client

    Returns:
        Dict with price comparison, or None if data unavailable
    """
    if redis_client is None:
        redis_client = get_redis_client()

    # Get Spot price
    spot_price = get_current_spot_price(instance_type, availability_zone, region, redis_client)

    # Get On-Demand price
    ondemand_cache_key = f"ondemand_price:{region}:{instance_type}"
    ondemand_price_str = redis_client.get(ondemand_cache_key)

    if spot_price and ondemand_price_str:
        ondemand_price = Decimal(ondemand_price_str)
        savings_pct = calculate_savings_percentage(spot_price, ondemand_price)

        return {
            "instance_type": instance_type,
            "availability_zone": availability_zone,
            "region": region,
            "spot_price": float(spot_price),
            "ondemand_price": float(ondemand_price),
            "savings_percentage": savings_pct,
            "savings_per_hour": float(ondemand_price - spot_price)
        }
    else:
        logger.warning(
            f"[SVC-PRICE-01] Incomplete price data for {instance_type} in {availability_zone}"
        )
        return None


# Celery task wrappers
try:
    from backend.core.celery_app import app as celery_app
    from celery import Task

    @celery_app.task(bind=True, name="scrapers.pricing.collect_spot_prices")
    def collect_spot_prices_task(self: Task) -> Dict[str, Any]:
        """
        Celery task for scheduled Spot price collection

        Runs every 5 minutes via Celery Beat
        """
        return collect_spot_prices()

    @celery_app.task(bind=True, name="scrapers.pricing.collect_ondemand_prices")
    def collect_ondemand_prices_task(self: Task) -> Dict[str, Any]:
        """
        Celery task for scheduled On-Demand price collection

        Runs daily at 1:00 AM UTC via Celery Beat
        """
        return collect_ondemand_prices()

except ImportError:
    logger.warning("[SVC-PRICE-01] Celery not available, task scheduling disabled")
