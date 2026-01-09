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
import boto3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from botocore.exceptions import ClientError
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.database.session import get_db
from app.database.models import SpotPriceHistory, OnDemandPricing
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

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

    try:
        # Create EC2 client for this region
        ec2_client = boto3.client('ec2', region_name=region)

        # Query current Spot prices (last hour)
        # Note: describe_spot_price_history returns prices from newest to oldest
        response = ec2_client.describe_spot_price_history(
            StartTime=datetime.utcnow() - timedelta(hours=1),
            ProductDescriptions=[PRODUCT_DESCRIPTION],
            MaxResults=10000  # Maximum allowed
        )

        spot_prices = response.get('SpotPriceHistory', [])

        # Group by instance type + AZ, keep only latest price
        latest_prices = {}
        for price_entry in spot_prices:
            instance_type = price_entry['InstanceType']
            az = price_entry['AvailabilityZone']
            key = f"{instance_type}:{az}"

            # Keep only the newest price (already sorted newest first)
            if key not in latest_prices:
                latest_prices[key] = price_entry

        # Store in database and cache
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
            stats["cache_keys_set"] += 1

        db.commit()

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
    from app.core.celery_app import app as celery_app
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
